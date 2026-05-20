import os

file_path = "aura/conversation/tools/_write_mixin.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import_str = """
try:
    from aura.craft import CraftEngine, ProposalCapsule, ChangeIntent, line_in_ranges
except ImportError:
    CraftEngine = None
"""

# Insert import after from aura.conversation.tools._types import ApprovalRequest, ToolExecResult
# and the other imports at the top
insert_idx = content.find("from aura.conversation.tools import registry as _reg")
if insert_idx != -1:
    content = content[:insert_idx] + import_str + "\n" + content[insert_idx:]
else:
    print("Could not find insertion point for imports")

craft_funcs = """
import difflib

def _compute_craft_line_ranges(proposal: dict) -> list[tuple[int, int]]:
    proposed_lines = proposal.get("new_content", "").splitlines()
    if proposal.get("is_new_file"):
        return [(0, len(proposed_lines) + 1)]
    
    old_content = proposal.get("old_content")
    new_content = proposal.get("new_content")
    if old_content is not None and new_content is not None:
        old_lines = old_content.splitlines()
        matcher = difflib.SequenceMatcher(None, old_lines, proposed_lines)
        ranges = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                ranges.append((j1 + 1, j2 + 1))
        return ranges
    return [(0, len(proposed_lines) + 1)]


def _maybe_craft_proposal(proposal: dict, tool_name: str) -> ToolExecResult | None:
    if CraftEngine is None:
        return None
        
    env = os.environ.get("AURA_CRAFT", "1")
    if env == "0":
        return None
        
    observe_env = os.environ.get("AURA_CRAFT_OBSERVE", "0")
    is_observe = observe_env == "1"
    
    rel_path = proposal.get("rel_path", "")
    if not rel_path.endswith(".py"):
        return None
        
    try:
        capsule = ProposalCapsule(
            path=Path(rel_path),
            language="python",
            tool_name=tool_name,
            original_code=proposal.get("old_content", ""),
            proposed_code=proposal["new_content"],
            changed_line_ranges=_compute_craft_line_ranges(proposal),
            is_new_file=proposal.get("is_new_file", False),
        )
        
        decision = CraftEngine().process_proposal(capsule)
        
        if is_observe:
            if not decision.approved:
                _log.info("[craft:observe] %s blocked: %s", rel_path, [i.code for i in decision.issues])
            return None
            
        if not decision.approved:
            issues_payload = []
            for i in decision.issues:
                issues_payload.append({
                    "code": i.code,
                    "line": i.line,
                    "message": i.message,
                    "suggestion": i.suggestion
                })
            return ToolExecResult(
                ok=False, 
                payload={
                    "ok": False, 
                    "error": "Code quality review failed before approval.", 
                    "path": rel_path, 
                    "issues": issues_payload
                }
            )
            
        proposal["new_content"] = decision.cleaned_code
        return None
    except Exception:
        _log.exception("CraftEngine failed for %s", rel_path)
        return None
"""

class_idx = content.find("class WriteHandlersMixin:")
if class_idx != -1:
    content = content[:class_idx] + craft_funcs + "\n\n" + content[class_idx:]
else:
    print("Could not find class WriteHandlersMixin")

# Now replace the specific locations in _handle_write
write_file_target = """            if proposal.get("is_new_file", False):
                gate_error = _maybe_humanize_proposal(proposal)
                if gate_error is not None:
                    return gate_error"""

write_file_replacement = """            if proposal.get("is_new_file", False):
                gate_error = _maybe_humanize_proposal(proposal)
                if gate_error is not None:
                    return gate_error
                craft_error = _maybe_craft_proposal(proposal, "write_file")
                if craft_error is not None:
                    return craft_error"""

content = content.replace(write_file_target, write_file_replacement)

edit_file_target = """            if os.environ.get("AURA_HUMANIZER_EDIT_FILE", "") == "1":
                _maybe_observe_humanizer(proposal)"""

edit_file_replacement = """            if os.environ.get("AURA_HUMANIZER_EDIT_FILE", "") == "1":
                _maybe_observe_humanizer(proposal)
            if os.environ.get("AURA_CRAFT_EDIT_FILE", "") == "1":
                craft_error = _maybe_craft_proposal(proposal, "edit_file")
                if craft_error is not None:
                    return craft_error"""

content = content.replace(edit_file_target, edit_file_replacement)

edit_symbol_target = """            gate_error = _maybe_humanize_proposal(proposal)
            if gate_error is not None:
                return gate_error"""

edit_symbol_replacement = """            gate_error = _maybe_humanize_proposal(proposal)
            if gate_error is not None:
                return gate_error
            craft_error = _maybe_craft_proposal(proposal, "edit_symbol")
            if craft_error is not None:
                return craft_error"""

content = content.replace(edit_symbol_target, edit_symbol_replacement)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
