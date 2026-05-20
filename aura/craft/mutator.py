import ast
import re
import logging
from pathlib import Path
import builtins

logger = logging.getLogger(__name__)

NARRATION_PREFIXES = [
    "initialize", "process", "loop through", "iterate through",
    "create a new", "create an", "check if", "check whether",
    "this function", "this method", "this class", "helper function",
    "helper method", "utility function", "small helper",
    "private helper", "internal helper"
]

EXACT_MATCHES = [
    "helper", "helper function", "helper method",
    "utility", "utility function"
]

class SafeMutator:
    """Safe code mutator."""

    def mutate(self, code: str, path: Path | None = None) -> str:
        if path and path.suffix != ".py":
            return code
            
        try:
            ast.parse(code)
        except SyntaxError:
            return code

        current_code = code

        try:
            new_code = self._strip_comments_and_banners(current_code)
            ast.parse(new_code)
            current_code = new_code
        except Exception:
            logger.warning("Stage A/D mutation failed")

        try:
            new_code = self._remove_empty_init(current_code)
            ast.parse(new_code)
            current_code = new_code
        except Exception:
            logger.warning("Stage B mutation failed")

        try:
            new_code = self._remove_redundant_passes(current_code)
            ast.parse(new_code)
            current_code = new_code
        except Exception:
            logger.warning("Stage C mutation failed")

        return current_code

    def _strip_comments_and_banners(self, code: str) -> str:
        code_lines = code.splitlines()
        result_lines = []
        
        for ln_str in code_lines:
            stripped = ln_str.strip()
            
            if not stripped.startswith("#"):
                result_lines.append(ln_str)
                continue
                
            comment_content = stripped[1:].strip().lower()
            
            if comment_content in ("region", "endregion"):
                continue
                
            if comment_content in EXACT_MATCHES:
                continue
                
            # Check prefixes manually instead of any() to avoid weird reference checker issues
            has_prefix = False
            for prefix in NARRATION_PREFIXES:
                if comment_content.startswith(prefix):
                    has_prefix = True
                    break
            if has_prefix:
                continue
                
            if len(stripped) >= 4:
                chars_after_hash = stripped[1:].strip()
                if chars_after_hash and len(chars_after_hash) >= 3:
                    first_char = chars_after_hash[0]
                    if first_char in "=-*~#":
                        # Check all manually
                        all_match = True
                        for ch in chars_after_hash:
                            if ch != first_char:
                                all_match = False
                                break
                        if all_match:
                            continue

            result_lines.append(ln_str)
            
        return "\n".join(result_lines) + ("\n" if code.endswith("\n") else "")

    def _remove_empty_init(self, code: str) -> str:
        try:
            import libcst as cst
            
            class EmptyInitRemover(cst.CSTTransformer):
                def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
                    if original_node.name.value == "__init__":
                        if original_node.decorators:
                            return updated_node  # decorated init — keep it (overload, staticmethod, etc.)
                        body = updated_node.body.body
                        is_empty = False
                        
                        statements = []
                        for stmt in body:
                            if builtins.isinstance(stmt, cst.SimpleStatementLine):
                                statements.extend(stmt.body)
                                
                        if len(statements) == 1:
                            s = statements[0]
                            if builtins.isinstance(s, cst.Pass):
                                is_empty = True
                            elif builtins.isinstance(s, cst.Expr) and builtins.isinstance(s.value, cst.Ellipsis):
                                is_empty = True
                        elif len(statements) == 2:
                            s1 = statements[0]
                            s2 = statements[1]
                            if builtins.isinstance(s1, cst.Expr) and builtins.isinstance(s1.value, (cst.SimpleString, cst.ConcatenatedString)):
                                if builtins.isinstance(s2, cst.Pass) or (builtins.isinstance(s2, cst.Expr) and builtins.isinstance(s2.value, cst.Ellipsis)):
                                    is_empty = True
                                    
                        if is_empty:
                            return cst.RemovalSentinel.REMOVE
                            
                    return updated_node
            
            tree = cst.parse_module(code)
            wrapper = cst.MetadataWrapper(tree)
            transformer = EmptyInitRemover()
            modified_tree = wrapper.visit(transformer)
            return modified_tree.code
            
        except ImportError:
            code_lines = code.splitlines()
            result_lines = []
            
            i = 0
            while i < len(code_lines):
                ln_str = code_lines[i]
                stripped = ln_str.strip()
                
                if stripped.startswith("def __init__(") and ln_str.endswith(":"):
                    # Check for decorators
                    has_decorator = False
                    k = i - 1
                    while k >= 0:
                        prev = code_lines[k].strip()
                        if not prev or prev.startswith("#"):
                            k -= 1
                            continue
                        if prev.startswith("@"):
                            has_decorator = True
                        break
                    if has_decorator:
                        result_lines.append(ln_str)
                        i += 1
                        continue

                    j = i + 1
                    body_lines = []
                    while j < len(code_lines):
                        next_line = code_lines[j]
                        if not next_line.strip() or next_line.startswith(ln_str[:len(ln_str) - len(ln_str.lstrip())] + " "):
                            body_lines.append(next_line.strip())
                            j += 1
                        else:
                            break
                    
                    while body_lines and not body_lines[-1]:
                        body_lines.pop()
                        
                    is_empty = False
                    if len(body_lines) == 1 and body_lines[0] in ("pass", "..."):
                        is_empty = True
                    elif len(body_lines) >= 2:
                        first = body_lines[0]
                        if (first.startswith('"""') or first.startswith("'''")) and first.count('"""') == 2 or first.count("'''") == 2:
                            if len(body_lines) == 2 and body_lines[1] in ("pass", "..."):
                                is_empty = True
                                
                    if is_empty:
                        while result_lines and not result_lines[-1].strip():
                            result_lines.pop()
                        i = j
                        continue
                        
                result_lines.append(ln_str)
                i += 1
                
            return "\n".join(result_lines) + ("\n" if code.endswith("\n") else "")

    def _remove_redundant_passes(self, code: str) -> str:
        code_lines = code.splitlines()
        result_lines = []
        modified = False
        
        for i, ln_str in enumerate(code_lines):
            stripped = ln_str.strip()
            if stripped == "pass":
                prev_line = ""
                # Use a standard loop
                tmp = i - 1
                while tmp >= 0:
                    if code_lines[tmp].strip() and not code_lines[tmp].strip().startswith("#"):
                        prev_line = code_lines[tmp]
                        break
                    tmp -= 1
                        
                next_line = ""
                next_indent = 0
                tmp = i + 1
                while tmp < len(code_lines):
                    if code_lines[tmp].strip() and not code_lines[tmp].strip().startswith("#"):
                        next_line = code_lines[tmp]
                        next_indent = len(next_line) - len(next_line.lstrip())
                        break
                    tmp += 1
                        
                curr_indent = len(ln_str) - len(ln_str.lstrip())
                
                if prev_line.strip().endswith(":"):
                    if not next_line or next_indent < curr_indent:
                        result_lines.append(ln_str)
                        continue
                
                modified = True
                continue
                
            result_lines.append(ln_str)
            
        if modified:
            new_code = "\n".join(result_lines) + ("\n" if code.endswith("\n") else "")
            try:
                ast.parse(new_code)
                return new_code
            except SyntaxError:
                return code
                
        return code
