import ast
import logging
from .types import CraftDecision, CraftIssue, ProposalCapsule, node_in_ranges, line_in_ranges

_log = logging.getLogger(__name__)

def _is_narration_comment(line_text: str) -> bool:
    stripped = line_text.strip()
    if not stripped.startswith("#"):
        return False
    text = stripped[1:].strip().lower()
    prefixes = [
        "initialize", "process", "loop through", "iterate through", 
        "create", "check if", "this function", "this method"
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            return True
    return False

def _is_private_helper_docstring_line(line_text: str) -> bool:
    stripped = line_text.strip()
    if not (stripped.startswith('"""') and stripped.endswith('"""')):
        return False
    if len(stripped) < 6:
        return False
    inner = stripped[3:-3].strip().lower()
    targets = [
        "helper", "internal helper", "private helper",
        "utility function", "utility method", "small helper"
    ]
    return inner in targets

class CraftEngine:
    def process_proposal(self, capsule: ProposalCapsule) -> CraftDecision:
        if capsule.language != "python" or not str(capsule.path).endswith(".py"):
            return CraftDecision(approved=True, cleaned_code=capsule.proposed_code)
            
        # Phase A: Cleanup
        cleaned_code = capsule.proposed_code
        try:
            # Strip markdown fences
            if cleaned_code.startswith("```python\n") and cleaned_code.endswith("\n```"):
                cleaned_code = cleaned_code[10:-4]
            elif cleaned_code.startswith("```python\r\n") and cleaned_code.endswith("\r\n```"):
                cleaned_code = cleaned_code[11:-5]
                
            lines = cleaned_code.splitlines()
            new_lines = []
            
            # Identify single-line function docstrings (very basic heuristic without full AST pass first)
            # Actually, to do docstrings safely we might want AST. 
            # But the prompt says "boilerplate private-helper docstrings: single-line """...""" docstrings on a def".
            # We will just filter lines if they match the exact strings.
            for i, line in enumerate(lines):
                line_num = i + 1
                # Should we clean this line?
                should_clean = True
                if not capsule.is_new_file and capsule.changed_line_ranges:
                    if not line_in_ranges(line_num, capsule.changed_line_ranges):
                        should_clean = False
                        
                if should_clean:
                    if _is_narration_comment(line):
                        continue
                    if _is_private_helper_docstring_line(line):
                        continue
                new_lines.append(line)
                
            temp_code = "\n".join(new_lines) + ("\n" if cleaned_code.endswith("\n") else "")
            
            # Verify parses
            ast.parse(temp_code)
            cleaned_code = temp_code
            
        except SyntaxError as e:
            # Fall back to raw
            pass
        except Exception as e:
            _log.warning("CraftEngine Phase A failed: %s", e)
            
        # Phase B: Blockers
        issues = []
        try:
            tree = ast.parse(cleaned_code)
        except SyntaxError as e:
            issues.append(CraftIssue(
                line=e.lineno or 0,
                column=e.offset or 0,
                code="syntax-error",
                message=f"Syntax error: {e.msg}",
                suggestion="Fix the syntax error."
            ))
            return CraftDecision(approved=False, cleaned_code=cleaned_code, issues=issues)
            
        is_test_file = "/test" in str(capsule.path).replace("\\", "/") or "test" in capsule.path.stem.lower()

        for node in ast.walk(tree):
            if not capsule.is_new_file and capsule.changed_line_ranges:
                if not node_in_ranges(node, capsule.changed_line_ranges):
                    continue
                    
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # B2: Stub body
                if len(node.body) == 1:
                    stmt = node.body[0]
                    is_stub = False
                    if isinstance(stmt, ast.Pass):
                        is_stub = True
                    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
                        is_stub = True
                    elif isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                        is_stub = True
                        
                    if is_stub:
                        issues.append(CraftIssue(
                            line=node.lineno,
                            column=node.col_offset,
                            code="stub-body-pass",
                            message=f"Function '{node.name}' has a stub body.",
                            suggestion="Implement the function fully. Do not leave placeholders."
                        ))
                        
                # B4: Scaffolding keywords
                if not is_test_file:
                    name_lower = node.name.lower()
                    if any(kw in name_lower for kw in ["demo", "placeholder", "dummy", "mockwindow", "mockwidget"]):
                        issues.append(CraftIssue(
                            line=node.lineno,
                            column=node.col_offset,
                            code="demo-scaffolding",
                            message=f"Function '{node.name}' appears to be demo or mock scaffolding.",
                            suggestion="Do not include demo or placeholder functions in production code."
                        ))

            elif isinstance(node, ast.ClassDef):
                if not is_test_file:
                    name_lower = node.name.lower()
                    if any(kw in name_lower for kw in ["demo", "placeholder", "dummy", "mockwindow", "mockwidget"]):
                        issues.append(CraftIssue(
                            line=node.lineno,
                            column=node.col_offset,
                            code="demo-scaffolding",
                            message=f"Class '{node.name}' appears to be demo or mock scaffolding.",
                            suggestion="Do not include demo or placeholder classes in production code."
                        ))

            elif isinstance(node, ast.ExceptHandler):
                # B3: Silent exception swallowing
                is_bare = node.type is None
                
                is_swallowed = False
                swallow_code = ""
                
                if is_bare:
                    is_swallowed = True
                    swallow_code = "bare-except"
                else:
                    # check if except Exception
                    if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                        if len(node.body) == 1:
                            if isinstance(node.body[0], ast.Pass):
                                is_swallowed = True
                                swallow_code = "swallow-except-pass"
                            elif isinstance(node.body[0], ast.Return):
                                if isinstance(node.body[0].value, ast.Constant) and node.body[0].value.value is None:
                                    is_swallowed = True
                                    swallow_code = "swallow-except-return-none"
                                elif node.body[0].value is None: # bare return
                                    is_swallowed = True
                                    swallow_code = "swallow-except-return-none"
                                    
                if is_swallowed:
                    issues.append(CraftIssue(
                        line=node.lineno,
                        column=node.col_offset,
                        code=swallow_code or "bare-except",
                        message="Exception handler silently swallows exceptions.",
                        suggestion="Handle the exception properly, log it, or raise it. Do not swallow exceptions silently."
                    ))

        if issues:
            return CraftDecision(approved=False, cleaned_code=cleaned_code, issues=issues)
            
        return CraftDecision(approved=True, cleaned_code=cleaned_code)
