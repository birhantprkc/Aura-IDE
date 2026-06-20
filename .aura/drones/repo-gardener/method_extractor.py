"""Deterministic method extraction — zero model, pure AST transform."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractResult:
    ok: bool
    new_source: str | None
    error: str | None
    stats: dict | None = None


def extract_method(
    source: str,
    target_func_name: str,
    start_line: int,  # 1-based, inclusive
    end_line: int,    # 1-based, inclusive
    helper_name: str,
) -> ExtractResult:
    """Extract a contiguous block of top-level statements from a function into a helper.

    Pure AST transform — no model calls.
    The helper is inserted in the same scope (class or module) as the original function,
    immediately before it.
    """
    # ------------------------------------------------------------------
    # Step 1 — Parse & find function
    # ------------------------------------------------------------------
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ExtractResult(False, None, f"syntax error: {e}")

    func_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    parent_node: ast.Module | ast.ClassDef | None = None  # the scope containing F

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_func_name:
            func_node = node
            parent_node = tree
            break
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == target_func_name:
                    func_node = item
                    parent_node = node
                    break
            if func_node:
                break

    if func_node is None or parent_node is None:
        return ExtractResult(False, None, f"function '{target_func_name}' not found")

    if isinstance(parent_node, ast.ClassDef):
        return ExtractResult(False, None, "method extraction not supported in v1 (function is inside a class)")

    # ------------------------------------------------------------------
    # Step 2 — Span validation
    # ------------------------------------------------------------------
    body = func_node.body
    if not body:
        return ExtractResult(False, None, "span is not a clean statement run at function top level")

    start_idx: int | None = None
    end_idx: int | None = None

    for i, stmt in enumerate(body):
        if stmt.lineno == start_line:
            start_idx = i
            break

    if start_idx is None:
        return ExtractResult(False, None, "span is not a clean statement run at function top level")

    # Walk forward from start_idx to find the end of the span
    for i in range(start_idx, len(body)):
        stmt_end = getattr(body[i], "end_lineno", None) or body[i].lineno
        if stmt_end == end_line:
            # Verify all statements between start_idx and i are fully within the span
            all_contained = True
            for j in range(start_idx, i + 1):
                s = body[j]
                s_start = s.lineno
                s_end = getattr(s, "end_lineno", None) or s.lineno
                if s_start < start_line or s_end > end_line:
                    all_contained = False
                    break
            if all_contained:
                end_idx = i
                break
        elif stmt_end > end_line:
            # Past the end — no clean match
            break

    if end_idx is None:
        return ExtractResult(False, None, "span is not a clean statement run at function top level")

    # Double-check first/last alignment
    if body[start_idx].lineno != start_line:
        return ExtractResult(False, None, "span is not a clean statement run at function top level")
    last_end = getattr(body[end_idx], "end_lineno", None) or body[end_idx].lineno
    if last_end != end_line:
        return ExtractResult(False, None, "span is not a clean statement run at function top level")

    block_stmts = body[start_idx : end_idx + 1]

    # ------------------------------------------------------------------
    # Step 3 — Refuse dangerous constructs
    # ------------------------------------------------------------------
    for stmt in block_stmts:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.Return, ast.Break, ast.Continue)):
                return ExtractResult(False, None, "block contains return/break/continue")
            if isinstance(node, (ast.Yield, ast.YieldFrom)):
                return ExtractResult(False, None, "block contains yield/yield from")
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                return ExtractResult(False, None, "block contains global/nonlocal")
            if isinstance(node, ast.Await):
                return ExtractResult(False, None, "block contains await")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return ExtractResult(False, None, "block contains nested function/class definition")
            if isinstance(node, ast.ClassDef):
                return ExtractResult(False, None, "block contains nested function/class definition")
            if isinstance(node, ast.Delete):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        return ExtractResult(False, None, "block contains del of a name")
            if isinstance(node, ast.NamedExpr):
                return ExtractResult(False, None, "block contains walrus operator (:=)")
            if isinstance(node, ast.ExceptHandler) and node.name is not None:
                return ExtractResult(False, None, "block contains except ... as name")

    # ------------------------------------------------------------------
    # Step 4 — Collision guard
    # ------------------------------------------------------------------
    for node in parent_node.body:
        name_to_check: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name_to_check = node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name_to_check = target.id
                    break
        if name_to_check == helper_name:
            return ExtractResult(
                False, None,
                f"helper name '{helper_name}' collides with existing symbol at line {node.lineno}",
            )

    # ------------------------------------------------------------------
    # Step 5 — Live-variable analysis (function-local only)
    # ------------------------------------------------------------------
    # 5a — Collect function-local names
    local_names: set[str] = set()

    # Parameters
    for arg in func_node.args.args:
        local_names.add(arg.arg)
    if func_node.args.vararg:
        local_names.add(func_node.args.vararg.arg)
    if func_node.args.kwarg:
        local_names.add(func_node.args.kwarg.arg)
    for arg in func_node.args.kwonlyargs:
        local_names.add(arg.arg)
    for arg in func_node.args.posonlyargs:
        local_names.add(arg.arg)

    # Comprehension-local names: excluded from threading as params
    comp_local_names: set[str] = set()
    for node_in_func in ast.walk(func_node):
        if isinstance(node_in_func, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for sub in ast.walk(node_in_func):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    comp_local_names.add(sub.id)

    # Store targets in the entire function
    for node_in_func in ast.walk(func_node):
        if isinstance(node_in_func, ast.Name) and isinstance(node_in_func.ctx, ast.Store):
            local_names.add(node_in_func.id)
        if isinstance(node_in_func, ast.ExceptHandler) and node_in_func.name is not None:
            local_names.add(node_in_func.name)
        if isinstance(node_in_func, ast.AugAssign):
            if isinstance(node_in_func.target, ast.Name):
                local_names.add(node_in_func.target.id)

    local_names = local_names - comp_local_names

    # 5b — live_in: ordered event pass
    def _collect_expr_events(node: ast.AST, unconditional: bool) -> list[tuple[str, str, bool]]:
        events: list[tuple[str, str, bool]] = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                if isinstance(sub.ctx, ast.Load):
                    events.append((sub.id, "load", unconditional))
                elif isinstance(sub.ctx, ast.Store):
                    events.append((sub.id, "store", unconditional))
        return events

    def _collect_store_events(target: ast.AST, unconditional: bool) -> list[tuple[str, str, bool]]:
        events: list[tuple[str, str, bool]] = []
        if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
            events.append((target.id, "store", unconditional))
        elif isinstance(target, (ast.Subscript, ast.Attribute)):
            events.extend(_collect_expr_events(target, unconditional))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                if isinstance(elt, ast.Starred):
                    events.extend(_collect_store_events(elt.value, unconditional))
                else:
                    events.extend(_collect_store_events(elt, unconditional))
        elif isinstance(target, ast.Starred):
            events.extend(_collect_store_events(target.value, unconditional))
        return events

    def _collect_events(stmt: ast.AST, unconditional: bool) -> list[tuple[str, str, bool]]:
        events: list[tuple[str, str, bool]] = []
        if isinstance(stmt, ast.Assign):
            events.extend(_collect_expr_events(stmt.value, unconditional))
            for target in stmt.targets:
                events.extend(_collect_store_events(target, unconditional))
        elif isinstance(stmt, ast.AnnAssign):
            if stmt.value:
                events.extend(_collect_expr_events(stmt.value, unconditional))
            events.extend(_collect_store_events(stmt.target, unconditional))
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                events.append((stmt.target.id, "load", unconditional))
            events.extend(_collect_expr_events(stmt.value, unconditional))
            if isinstance(stmt.target, ast.Name):
                events.append((stmt.target.id, "store", unconditional))
            if isinstance(stmt.target, (ast.Subscript, ast.Attribute)):
                events.extend(_collect_expr_events(stmt.target, unconditional))
        elif isinstance(stmt, ast.Expr):
            events.extend(_collect_expr_events(stmt.value, unconditional))
        elif isinstance(stmt, ast.Raise):
            if stmt.exc:
                events.extend(_collect_expr_events(stmt.exc, unconditional))
            if stmt.cause:
                events.extend(_collect_expr_events(stmt.cause, unconditional))
        elif isinstance(stmt, ast.Assert):
            events.extend(_collect_expr_events(stmt.test, unconditional))
            if stmt.msg:
                events.extend(_collect_expr_events(stmt.msg, unconditional))
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                events.extend(_collect_expr_events(stmt.value, unconditional))
        elif isinstance(stmt, ast.If):
            events.extend(_collect_expr_events(stmt.test, True))
            for body_stmt in stmt.body:
                events.extend(_collect_events(body_stmt, False))
            for orelse_stmt in stmt.orelse:
                events.extend(_collect_events(orelse_stmt, False))
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            events.extend(_collect_expr_events(stmt.iter, True))
            events.extend(_collect_store_events(stmt.target, unconditional))
            for body_stmt in stmt.body:
                events.extend(_collect_events(body_stmt, False))
            for orelse_stmt in stmt.orelse:
                events.extend(_collect_events(orelse_stmt, False))
        elif isinstance(stmt, ast.While):
            events.extend(_collect_expr_events(stmt.test, True))
            for body_stmt in stmt.body:
                events.extend(_collect_events(body_stmt, False))
            for orelse_stmt in stmt.orelse:
                events.extend(_collect_events(orelse_stmt, False))
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                events.extend(_collect_expr_events(item.context_expr, True))
                if item.optional_vars:
                    events.extend(_collect_store_events(item.optional_vars, unconditional))
            for body_stmt in stmt.body:
                events.extend(_collect_events(body_stmt, False))
        elif isinstance(stmt, ast.Try):
            for body_stmt in stmt.body:
                events.extend(_collect_events(body_stmt, False))
            for handler in stmt.handlers:
                for body_stmt in handler.body:
                    events.extend(_collect_events(body_stmt, False))
            for orelse_stmt in stmt.orelse:
                events.extend(_collect_events(orelse_stmt, False))
            for final_stmt in stmt.finalbody:
                events.extend(_collect_events(final_stmt, False))
        elif isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    events.append((target.id, "store", unconditional))
                elif isinstance(target, (ast.Subscript, ast.Attribute)):
                    events.extend(_collect_expr_events(target, unconditional))
        elif isinstance(stmt, (ast.Pass, ast.Global, ast.Nonlocal)):
            pass
        else:
            # Fallback for unrecognised statement types — skip silently
            pass
        return events

    unconditionally_killed: set[str] = set()
    live_in: set[str] = set()
    events_in_order: list[tuple[str, str, bool]] = []
    for stmt in block_stmts:
        events_in_order.extend(_collect_events(stmt, True))
    for name, action, unconditional in events_in_order:
        if name not in local_names:
            continue
        if action == "load":
            if name not in unconditionally_killed:
                live_in.add(name)
        elif action == "store":
            if unconditional:
                unconditionally_killed.add(name)

    # 5c — live_out: stored in block AND loaded after block in F
    block_stores: set[str] = set()
    for stmt in block_stmts:
        for node_in_block in ast.walk(stmt):
            if isinstance(node_in_block, ast.Name) and isinstance(node_in_block.ctx, ast.Store):
                if node_in_block.id in local_names:
                    block_stores.add(node_in_block.id)
            if isinstance(node_in_block, ast.AugAssign):
                if isinstance(node_in_block.target, ast.Name):
                    block_stores.add(node_in_block.target.id)

    after_loads: set[str] = set()
    for stmt in func_node.body[end_idx + 1 :]:
        for node_after in ast.walk(stmt):
            if isinstance(node_after, ast.Name) and isinstance(node_after.ctx, ast.Load):
                if node_after.id in local_names:
                    after_loads.add(node_after.id)

    live_out = block_stores & after_loads

    # 5d — Sort by first reference line in block
    def _first_ref_line(name: str) -> int:
        for stmt in block_stmts:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and node.id == name:
                    return node.lineno
                if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                    return node.lineno
        return 999999

    sorted_live_in = sorted(live_in, key=_first_ref_line)
    sorted_live_out = sorted(live_out, key=_first_ref_line)

    # ------------------------------------------------------------------
    # Step 6 — Rewrite
    # ------------------------------------------------------------------
    source_lines = source.splitlines()

    # Determine indentation
    func_line_str = source_lines[func_node.lineno - 1]
    func_indent = len(func_line_str) - len(func_line_str.lstrip())
    body_indent = func_indent + 4

    # Find the first line of F (including decorators)
    f_first_line = func_node.lineno
    if func_node.decorator_list:
        f_first_line = min(d.lineno for d in func_node.decorator_list)

    f_start_0 = f_first_line - 1  # 0-based index of first line belonging to F
    f_end_0: int = (func_node.end_lineno or func_node.lineno)  # 1-based → use as 0-based exclusive end

    block_start_0 = block_stmts[0].lineno - 1
    block_end_0: int = (getattr(block_stmts[-1], "end_lineno", None) or block_stmts[-1].lineno)

    # 6a — Build helper function lines
    params_str = ", ".join(sorted_live_in)
    helper_lines: list[str] = []
    helper_lines.append(f"{' ' * func_indent}def {helper_name}({params_str}):")

    block_source_lines = source_lines[block_start_0:block_end_0]
    for line in block_source_lines:
        helper_lines.append(line)

    if len(sorted_live_out) == 1:
        helper_lines.append(f"{' ' * body_indent}return {sorted_live_out[0]}")
    elif len(sorted_live_out) > 1:
        ret_tuple = ", ".join(sorted_live_out)
        helper_lines.append(f"{' ' * body_indent}return ({ret_tuple})")

    # 6b — Build call line
    if len(sorted_live_out) == 0:
        call_line = f"{' ' * body_indent}{helper_name}({params_str})"
    elif len(sorted_live_out) == 1:
        call_line = f"{' ' * body_indent}{sorted_live_out[0]} = {helper_name}({params_str})"
    else:
        lhs = ", ".join(sorted_live_out)
        call_line = f"{' ' * body_indent}{lhs} = {helper_name}({params_str})"

    # 6c — Assemble new source
    before_f = source_lines[:f_start_0]
    f_def_and_before_block = source_lines[f_start_0:block_start_0]
    f_after_block = source_lines[block_end_0:f_end_0]
    after_f = source_lines[f_end_0:]

    new_parts: list[str] = []
    new_parts.extend(before_f)
    new_parts.extend(helper_lines)
    new_parts.extend(f_def_and_before_block)
    new_parts.append(call_line)
    new_parts.extend(f_after_block)
    new_parts.extend(after_f)

    ends_with_newline = source.endswith("\n")
    new_source = "\n".join(new_parts)
    if ends_with_newline:
        new_source += "\n"

    # ------------------------------------------------------------------
    # Static resolution backstop
    # ------------------------------------------------------------------
    # 4a - Re-parse to verify
    try:
        new_tree = ast.parse(new_source)
    except SyntaxError as e:
        return ExtractResult(False, None, f"rewrite produced unparseable source: {e}")

    # 4b - Build module-level globals
    module_globals: set[str] = set()
    module_globals.update(dir(builtins))
    for top_stmt in new_tree.body:
        if isinstance(top_stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_globals.add(top_stmt.name)
        elif isinstance(top_stmt, ast.Assign):
            for target in top_stmt.targets:
                if isinstance(target, ast.Name):
                    module_globals.add(target.id)
        elif isinstance(top_stmt, ast.AnnAssign):
            if isinstance(top_stmt.target, ast.Name):
                module_globals.add(top_stmt.target.id)
        elif isinstance(top_stmt, ast.Import):
            for alias in top_stmt.names:
                module_globals.add(alias.asname or alias.name)
        elif isinstance(top_stmt, ast.ImportFrom):
            for alias in top_stmt.names:
                module_globals.add(alias.asname or alias.name)

    # 4c - Call-site check: find F in new tree
    new_func_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in new_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_func_name:
            new_func_node = node
            break
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == target_func_name:
                    new_func_node = item
                    break
            if new_func_node:
                break

    if new_func_node is None:
        return ExtractResult(False, None, f"call-site references unresolved name '{target_func_name}' (target function not found in rewritten source)")

    names_available_in_F: set[str] = set()
    for arg in new_func_node.args.args:
        names_available_in_F.add(arg.arg)
    if new_func_node.args.vararg:
        names_available_in_F.add(new_func_node.args.vararg.arg)
    if new_func_node.args.kwarg:
        names_available_in_F.add(new_func_node.args.kwarg.arg)
    for arg in new_func_node.args.kwonlyargs:
        names_available_in_F.add(arg.arg)
    for arg in new_func_node.args.posonlyargs:
        names_available_in_F.add(arg.arg)
    for node_in_F in ast.walk(new_func_node):
        if isinstance(node_in_F, ast.Name) and isinstance(node_in_F.ctx, ast.Store):
            names_available_in_F.add(node_in_F.id)
        if isinstance(node_in_F, ast.AugAssign):
            if isinstance(node_in_F.target, ast.Name):
                names_available_in_F.add(node_in_F.target.id)
    names_available_in_F.update(module_globals)

    for name in sorted_live_in:
        if name not in names_available_in_F:
            return ExtractResult(False, None, f"call-site references unresolved name '{name}' (live-in analysis unsafe)")

    # 4d - Helper free-variable check
    new_helper_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in new_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == helper_name:
            new_helper_node = node
            break
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == helper_name:
                    new_helper_node = item
                    break
            if new_helper_node:
                break

    if new_helper_node is None:
        return ExtractResult(False, None, f"helper references unresolved free name '{helper_name}' (helper not found in rewritten source)")

    helper_params: set[str] = set()
    for arg in new_helper_node.args.args:
        helper_params.add(arg.arg)
    if new_helper_node.args.vararg:
        helper_params.add(new_helper_node.args.vararg.arg)
    if new_helper_node.args.kwarg:
        helper_params.add(new_helper_node.args.kwarg.arg)
    for arg in new_helper_node.args.kwonlyargs:
        helper_params.add(arg.arg)
    for arg in new_helper_node.args.posonlyargs:
        helper_params.add(arg.arg)

    helper_assigned: set[str] = set()
    for node_in_H in ast.walk(new_helper_node):
        if isinstance(node_in_H, ast.Name) and isinstance(node_in_H.ctx, ast.Store):
            helper_assigned.add(node_in_H.id)
        if isinstance(node_in_H, ast.AugAssign):
            if isinstance(node_in_H.target, ast.Name):
                helper_assigned.add(node_in_H.target.id)

    helper_comp_local: set[str] = set()
    for node_in_H in ast.walk(new_helper_node):
        if isinstance(node_in_H, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for sub in ast.walk(node_in_H):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    helper_comp_local.add(sub.id)

    helper_loads: set[str] = set()
    for node_in_H in ast.walk(new_helper_node):
        if isinstance(node_in_H, ast.Name) and isinstance(node_in_H.ctx, ast.Load):
            helper_loads.add(node_in_H.id)

    helper_free_vars = helper_loads - helper_params - helper_assigned - helper_comp_local

    for free_name in helper_free_vars:
        if free_name not in module_globals:
            return ExtractResult(False, None, f"helper references unresolved free name '{free_name}'")

    # ------------------------------------------------------------------
    # Step 7 — Stats
    # ------------------------------------------------------------------
    lines_moved = block_end_0 - block_start_0
    func_lines_before = f_end_0 - f_start_0
    func_lines_after = len(f_def_and_before_block) + 1 + len(f_after_block)

    stats = {
        "params": sorted_live_in,
        "returns": sorted_live_out,
        "lines_moved": lines_moved,
        "func_lines_before": func_lines_before,
        "func_lines_after": func_lines_after,
    }

    return ExtractResult(True, new_source, None, stats)
