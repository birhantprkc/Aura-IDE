"""
Impact-ranked picker — selects exactly ONE target per lap.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast

from mapper import FileHealth, Candidate


@dataclass(frozen=True)
class Chosen:
    kind: str
    path: str
    detail: str
    line: int
    reason: str
    file_score: float


def pick(
    health_map: list[FileHealth],
    candidates: list[Candidate],
) -> Chosen | None:
    """Pick the single highest-impact target from available candidates.

    Tier 1 policy (deterministic only):
    - Consider only ``"unused_import"`` candidates with ``confidence == "high"``.
    - Rank by: (1) descending FileHealth.score of the candidate's file,
      (2) shallowest path depth (fewer parts = closer to root),
      (3) path alphabetical for determinism.
    - Return the top candidate wrapped in a ``Chosen``, or ``None`` if no eligible
      candidates exist.

    The candidate-to-``FileHealth`` match is done by comparing the trailing path
    components of ``Candidate.path`` (a full path) with ``FileHealth.path``
    (relative to target_root). This avoids needing ``target_root`` in scope.
    """
    # -- Filter to eligible candidates ---------------------------------------
    eligible = [
        c
        for c in candidates
        if c.kind == "unused_import" and c.confidence == "high"
    ]
    if not eligible:
        return None

    # -- Build file_score lookup (candidate full path → FileHealth.score) ----
    file_scores: dict[str, float] = {}

    for fh in health_map:
        fh_parts = Path(fh.path).parts
        for c in eligible:
            c_parts = Path(c.path).parts
            # Match if the trailing components of the candidate path
            # equal the FileHealth's relative path components.
            if len(c_parts) >= len(fh_parts) and c_parts[-len(fh_parts):] == fh_parts:
                file_scores[c.path] = fh.score
                break  # first match wins

    # -- Sort: (-score, depth, path) -----------------------------------------
    def sort_key(c: Candidate) -> tuple[float, int, str]:
        score = file_scores.get(c.path, 0.0)
        depth = len(Path(c.path).parts)
        return (-score, depth, c.path)

    eligible.sort(key=sort_key)
    best = eligible[0]
    best_score = file_scores.get(best.path, 0.0)

    reason = (
        f"removing unused '{best.detail}' import from {best.path} "
        f"— highest-entropy file, score {best_score}"
    )

    return Chosen(
        kind=best.kind,
        path=best.path,
        detail=best.detail,
        line=best.line,
        reason=reason,
        file_score=best_score,
    )


def pick_refactor(
    health_map: list[FileHealth],
    target_root: Path | None = None,
) -> Chosen | None:
    """Pick a refactor target when deterministic debris is exhausted.

    Scans highest-score files first, respecting caps.is_editable.
    Target kinds in priority order:

    1. ``dead_function`` — a provably-dead function in a file with
       ``fan_in == 0``, skipping dunders and private names.
    2. ``simplify_function`` — an oversized function (largest_function_lines ≥ 60).
    3. ``extract_cluster`` — a god file (mixed_responsibility, function_count ≥ 3).

    Reads file contents to identify specific function names and line numbers.
    Returns ``None`` when no viable target is found.
    """
    from caps import is_editable

    # Sort health_map by score descending
    ranked = sorted(health_map, key=lambda fh: (-fh.score, fh.path))

    # -- Priority 1: dead_function in fan_in == 0 files -----------------------
    for fh in ranked:
        if fh.fan_in > 0 or fh.function_count == 0:
            continue
        if not is_editable(fh.path):
            continue

        full = _resolve_full_path(fh.path, target_root)
        if full is None:
            continue

        try:
            src = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        try:
            tree = ast.parse(src, filename=str(full))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if name.startswith("__") and name.endswith("__"):
                continue  # dunder
            if name.startswith("_"):
                continue  # private
            # Check __all__ — skip if this name is exported
            if _is_in_all(tree, name):
                continue

            return Chosen(
                kind="dead_function",
                path=str(full),
                detail=name,
                line=node.lineno,
                reason=(
                    f"dead function '{name}' in {fh.path} "
                    f"(fan_in={fh.fan_in}, score={fh.score})"
                ),
                file_score=fh.score,
            )

    # -- Priority 2: simplify_function (oversized) ---------------------------
    for fh in ranked:
        if fh.largest_function_lines < 60:
            continue
        if not is_editable(fh.path):
            continue

        full = _resolve_full_path(fh.path, target_root)
        if full is None:
            continue

        try:
            src = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        try:
            tree = ast.parse(src, filename=str(full))
        except SyntaxError:
            continue

        best_node = None
        best_size = 0
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is not None and node.lineno is not None:
                size = node.end_lineno - node.lineno
                if size > best_size:
                    best_size = size
                    best_node = node

        if best_node and best_size >= 60:
            return Chosen(
                kind="simplify_function",
                path=str(full),
                detail=best_node.name,
                line=best_node.lineno,
                reason=(
                    f"oversized function '{best_node.name}' "
                    f"({best_size} lines) in {fh.path} (score={fh.score})"
                ),
                file_score=fh.score,
            )

    # -- Priority 3: extract_cluster from god file ---------------------------
    for fh in ranked:
        if not fh.mixed_responsibility or fh.function_count < 3:
            continue
        if not is_editable(fh.path):
            continue

        full = _resolve_full_path(fh.path, target_root)
        if full is None:
            continue

        return Chosen(
            kind="extract_cluster",
            path=str(full),
            detail="extract cluster",
            line=1,
            reason=(
                f"god file {fh.path} ({fh.function_count} functions, "
                f"fan_out={fh.fan_out}, mixed responsibility, score={fh.score})"
            ),
            file_score=fh.score,
        )

    return None


def _resolve_full_path(rel_path: str, target_root: Path | None) -> Path | None:
    """Resolve a relative path against target_root."""
    if target_root is None:
        return None
    p = Path(target_root) / rel_path
    return p if p.is_file() else None


def _is_in_all(tree: ast.AST, name: str) -> bool:
    """Check if *name* is listed in a module-level ``__all__``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and elt.value == name:
                                return True
    return False
