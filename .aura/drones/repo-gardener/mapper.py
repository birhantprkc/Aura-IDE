"""Repository health mapping — frozen dataclasses and pure functions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileHealth:
    path: str
    lines: int
    class_count: int
    function_count: int
    import_count: int
    top_level_symbols: int
    largest_function_lines: int
    largest_class_lines: int
    fan_in: int
    fan_out: int
    mixed_responsibility: bool
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    kind: str
    path: str
    detail: str
    confidence: str
    line: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATIC_SKIP: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", "build", "dist", ".aura",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_health_to_dict(fh: FileHealth) -> dict:
    return {
        "path": fh.path,
        "lines": fh.lines,
        "class_count": fh.class_count,
        "function_count": fh.function_count,
        "import_count": fh.import_count,
        "top_level_symbols": fh.top_level_symbols,
        "largest_function_lines": fh.largest_function_lines,
        "largest_class_lines": fh.largest_class_lines,
        "fan_in": fh.fan_in,
        "fan_out": fh.fan_out,
        "mixed_responsibility": fh.mixed_responsibility,
        "score": fh.score,
        "reasons": list(fh.reasons),
    }


def _resolve_from_module(
    base_module: str,
    rel_stem: str,
    level: int,
    module: str | None,
) -> str | None:
    """Resolve a relative import's FROM module to an absolute module path.

    *rel_stem* is the file path relative to target_root, without extension
    and without a leading ``/__init__`` suffix (e.g. ``"gui/main_window"``).
    *level* is the number of dots (1 for ``.``, 2 for ``..``).
    *module* is the dotted module name after the dots, or None.
    """
    if rel_stem.endswith("/__init__") or rel_stem == "__init__":
        pkg_parts = (
            rel_stem.replace("/__init__", "").split("/")
            if rel_stem != "__init__"
            else []
        )
    else:
        pkg_parts = rel_stem.split("/")[:-1]

    if level > len(pkg_parts) + 1:
        return None

    parent_parts = pkg_parts[: len(pkg_parts) - (level - 1)]

    if module:
        resolved_parts = parent_parts + module.split(".")
    else:
        resolved_parts = parent_parts[:]

    if not resolved_parts:
        return base_module
    return f"{base_module}.{'.'.join(resolved_parts)}"


def _get_bound_names(alias: ast.alias) -> list[str]:
    """Return the name(s) that would appear in code for this import alias."""
    if alias.asname:
        return [alias.asname]
    if "." in alias.name:
        return [alias.name.split(".")[0]]
    return [alias.name]


def _collect_module_to_file(
    files: list[Path], target_root: Path, base_module: str
) -> dict[str, Path]:
    """Build a mapping from absolute module path -> file Path.

    Prefers ``.py`` files over ``__init__.py`` when both exist.
    """
    mapping: dict[str, Path] = {}

    for f in files:
        rel = f.relative_to(target_root)
        stem = str(rel.with_suffix(""))
        if stem.endswith("__init__"):
            if stem == "__init__":
                mod = base_module
            else:
                mod = f"{base_module}.{stem.replace('/', '.')[:-9]}"
        else:
            mod = f"{base_module}.{stem.replace('/', '.')}"

        existing = mapping.get(mod)
        if existing is None or (
            existing.name == "__init__.py" and f.name != "__init__.py"
        ):
            mapping[mod] = f

    return mapping


# ---------------------------------------------------------------------------
# Public pure functions
# ---------------------------------------------------------------------------


def walk(target_root: Path) -> list[Path]:
    """Recursively collect *.py* files from *target_root*.

    Prunes ``STATIC_SKIP`` directories and any directory containing
    ``pyvenv.cfg`` (venv detection).  Uses an explicit stack for
    controlled traversal.  Returns a sorted list of paths.
    """
    if not target_root.is_dir():
        return []

    result: list[Path] = []
    stack: list[Path] = [target_root]

    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except PermissionError:
            continue

        dirs: list[Path] = []
        for entry in entries:
            if entry.is_dir():
                if entry.name in STATIC_SKIP:
                    continue
                if (entry / "pyvenv.cfg").is_file():
                    continue
                dirs.append(entry)
            elif entry.suffix == ".py":
                result.append(entry)

        for d in reversed(dirs):
            stack.append(d)

    result.sort(key=lambda p: str(p))
    return result


def compute_file_health(
    rel_path: str,
    source: str,
    tree: ast.AST,
    fan_in: int,
    fan_out: int,
) -> FileHealth:
    """Compute health metrics for a single Python file from its AST."""
    lines = source.count("\n") + 1

    classes: list[ast.ClassDef] = [
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
    ]
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    imports: list[ast.Import | ast.ImportFrom] = [
        n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
    ]

    class_count = len(classes)
    function_count = len(functions)
    import_count = len(imports)

    top_level_symbols = sum(
        1
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    )

    largest_function_lines = 0
    for fn in functions:
        if fn.end_lineno is not None and fn.lineno is not None:
            size = fn.end_lineno - fn.lineno
            if size > largest_function_lines:
                largest_function_lines = size

    largest_class_lines = 0
    for cl in classes:
        if cl.end_lineno is not None and cl.lineno is not None:
            size = cl.end_lineno - cl.lineno
            if size > largest_class_lines:
                largest_class_lines = size

    # -- Mixed responsibility ------------------------------------------------
    reasons: list[str] = []
    mixed = False

    subsystem_roots: set[str] = set()
    for imp in imports:
        if isinstance(imp, ast.Import):
            for alias in imp.names:
                parts = alias.name.split(".")
                if len(parts) >= 2:
                    subsystem_roots.add(f"{parts[0]}.{parts[1]}")
        elif isinstance(imp, ast.ImportFrom):
            if imp.module and "." in imp.module:
                parts = imp.module.split(".")
                if len(parts) >= 2:
                    subsystem_roots.add(f"{parts[0]}.{parts[1]}")

    if len(subsystem_roots) >= 2:
        mixed = True
        reasons.append(f"imports from {', '.join(sorted(subsystem_roots))}")

    if class_count >= 2 and function_count >= 8:
        mixed = True
        reasons.append("high class+function density")

    # -- Score ---------------------------------------------------------------
    score = 0.0

    if lines > 400:
        add = (lines - 400) / 100
        score += add
        reasons.append(f"{lines} lines")

    if largest_function_lines > 60:
        add = (largest_function_lines - 60) / 20
        score += add
        reasons.append(f"function spans {largest_function_lines} lines")

    if largest_class_lines > 300:
        add = (largest_class_lines - 300) / 50
        score += add
        reasons.append(f"class spans {largest_class_lines} lines")

    if fan_out > 0:
        score += fan_out * 0.5
        reasons.append(f"imports {fan_out} sibling modules")

    if mixed:
        score += 3.0

    score = round(score, 1)

    return FileHealth(
        path=rel_path,
        lines=lines,
        class_count=class_count,
        function_count=function_count,
        import_count=import_count,
        top_level_symbols=top_level_symbols,
        largest_function_lines=largest_function_lines,
        largest_class_lines=largest_class_lines,
        fan_in=fan_in,
        fan_out=fan_out,
        mixed_responsibility=mixed,
        score=score,
        reasons=tuple(reasons),
    )


def build_import_graph(
    files: list[Path],
    target_root: Path,
) -> dict[Path, tuple[int, int, set[str]]]:
    """Build an import graph for the given *files*.

    Returns a dict mapping each file to ``(fan_in, fan_out, sibling_modules)``.

    *   ``fan_in``  – number of *other* files that import this file's module.
    *   ``fan_out`` – number of distinct sibling modules this file imports.
    *   ``sibling_modules`` – the set of sibling module paths imported.
    """
    base_module = target_root.name

    mod_to_file = _collect_module_to_file(files, target_root, base_module)

    file_outputs: dict[Path, set[str]] = {}

    for f in files:
        rel = f.relative_to(target_root)
        stem = str(rel.with_suffix(""))
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(f))
        except SyntaxError:
            file_outputs[f] = set()
            continue

        sibling_mods: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if mod == base_module or mod.startswith(base_module + "."):
                        sibling_mods.add(mod)

            elif isinstance(node, ast.ImportFrom):
                if node.level is not None and node.level > 0:
                    resolved = _resolve_from_module(
                        base_module, stem, node.level, node.module
                    )
                    if resolved is not None:
                        sibling_mods.add(resolved)
                elif node.module:
                    mod = node.module
                    if mod == base_module or mod.startswith(base_module + "."):
                        sibling_mods.add(mod)

        file_outputs[f] = sibling_mods

    # -- Compute fan_in -----------------------------------------------------
    file_inputs: dict[Path, set[Path]] = {f: set() for f in files}

    for f in files:
        rel = f.relative_to(target_root)
        stem = str(rel.with_suffix(""))

        if stem.endswith("__init__"):
            own_mod = (
                base_module
                if stem == "__init__"
                else f"{base_module}.{stem.replace('/', '.')[:-9]}"
            )
        else:
            own_mod = f"{base_module}.{stem.replace('/', '.')}"

        for other_f, outputs in file_outputs.items():
            if other_f is f:
                continue
            if own_mod in outputs:
                file_inputs[f].add(other_f)

    # -- Assemble result ----------------------------------------------------
    result: dict[Path, tuple[int, int, set[str]]] = {}
    for f in files:
        result[f] = (
            len(file_inputs[f]),
            len(file_outputs[f]),
            file_outputs[f],
        )

    return result


def detect_unused_imports(
    file_path: Path,
    source: str,
    tree: ast.AST,
    exported_names: frozenset[str] = frozenset(),
) -> list[Candidate]:
    """Detect unused imports in a single file.

    Returns a list of ``Candidate`` objects (empty if none found or the
    file should be entirely skipped).
    """
    # -- Hard skip: __init__.py ----------------------------------------------
    if file_path.name == "__init__.py":
        return []

    # -- Hard skip: star imports ---------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(n.name == "*" for n in node.names):
                return []

    # -- Collect __all__ names -----------------------------------------------
    all_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    val = node.value
                    if isinstance(val, (ast.List, ast.Tuple)):
                        for elt in val.elts:
                            if isinstance(elt, ast.Constant) and isinstance(
                                elt.value, str
                            ):
                                all_names.add(elt.value)

    # -- Collect names used inside TYPE_CHECKING blocks ----------------------
    type_checking_names: set[str] = set()

    class _TCChecker(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            is_tc = False
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                is_tc = True
            elif (
                isinstance(node.test, ast.Attribute)
                and isinstance(node.test.value, ast.Name)
                and node.test.value.id == "typing"
                and node.test.attr == "TYPE_CHECKING"
            ):
                is_tc = True

            if is_tc:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name):
                        type_checking_names.add(sub.id)
            self.generic_visit(node)

    _TCChecker().visit(tree)

    # -- Collect guarded (conditional) import line numbers -------------------
    guarded_lines: set[int] = set()

    class _GuardedFinder(ast.NodeVisitor):
        def __init__(self) -> None:
            self._depth = 0

        def _enter_ctx(self, node: ast.AST) -> None:
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1

        def visit_Try(self, node: ast.Try) -> None:
            self._enter_ctx(node)

        def visit_If(self, node: ast.If) -> None:
            self._enter_ctx(node)

        def visit_Match(self, node: ast.Match) -> None:
            self._enter_ctx(node)

        def visit_Import(self, node: ast.Import) -> None:
            if self._depth > 0:
                guarded_lines.add(node.lineno)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if self._depth > 0:
                guarded_lines.add(node.lineno)
            self.generic_visit(node)

    _GuardedFinder().visit(tree)

    # -- Collect all import binding info -------------------------------------
    import_bindings: list[tuple[str, int]] = []

    def _has_noqa(node: ast.AST, source_lines: list[str]) -> bool:
        end = node.end_lineno if node.end_lineno is not None else node.lineno
        for lineno in range(node.lineno, end + 1):
            if "# noqa" in source_lines[lineno - 1].lower():
                return True
        return False

    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if _has_noqa(node, source_lines):
                continue
            for alias in node.names:
                import_bindings.append((alias.asname or alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            if _has_noqa(node, source_lines):
                continue
            for alias in node.names:
                import_bindings.append((alias.asname or alias.name, node.lineno))

    # -- Collect all actually-used names in the module body ------------------
    used_names: set[str] = set()
    used_attribute_bases: set[str] = set()

    class _UsageCollector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            used_names.add(node.id)
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if isinstance(node.value, ast.Name):
                used_attribute_bases.add(node.value.id)
            self.generic_visit(node)

    _UsageCollector().visit(tree)

    used_names.update(type_checking_names)

    # -- Evaluate each binding -----------------------------------------------
    candidates: list[Candidate] = []

    for bound_name, lineno in import_bindings:
        if lineno in guarded_lines:
            continue

        if bound_name in all_names:
            continue

        if bound_name in exported_names:
            continue

        found = False
        if bound_name in used_names or bound_name in used_attribute_bases:
            found = True

        if not found and "." in bound_name:
            root = bound_name.split(".")[0]
            if root in used_names or root in used_attribute_bases:
                found = True

        if found:
            continue

        candidates.append(
            Candidate(
                kind="unused_import",
                path=str(file_path),
                detail=bound_name,
                confidence="high",
                line=lineno,
            )
        )

    return candidates


def rank_files(health_map: list[FileHealth]) -> list[FileHealth]:
    """Sort files by descending score (ties broken alphabetically by path)."""
    return sorted(health_map, key=lambda h: (-h.score, h.path))
