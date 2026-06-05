from __future__ import annotations

from aura.conversation.tools.registry import ToolRegistry


def _tool_names(registry: ToolRegistry) -> set[str]:
    return {tool["function"]["name"] for tool in registry.tool_defs()}


def test_worker_mode_exposes_patch_first_edit_surface(tmp_workspace):
    names = _tool_names(ToolRegistry(tmp_workspace, mode="worker"))
    assert "patch_file" in names
    assert "write_file" in names


def test_worker_mode_hides_low_level_edit_tools_by_default(tmp_workspace):
    names = _tool_names(ToolRegistry(tmp_workspace, mode="worker"))
    assert "apply_edit_transaction" not in names
    assert "edit_file" not in names
    assert "edit_symbol" not in names
    assert "edit_line_range" not in names


def test_worker_low_level_edit_tool_escape_hatch(monkeypatch, tmp_workspace):
    monkeypatch.setenv("AURA_WORKER_LOW_LEVEL_EDIT_TOOLS", "1")
    names = _tool_names(ToolRegistry(tmp_workspace, mode="worker"))
    assert "apply_edit_transaction" in names
    assert "edit_file" in names
    assert "edit_symbol" in names
    assert "edit_line_range" in names
    assert "patch_file" in names


def test_apply_edit_transaction_schema_advertises_symbol_aliases(tmp_workspace):
    registry = ToolRegistry(tmp_workspace, mode="single")
    tools = {
        tool["function"]["name"]: tool
        for tool in registry.tool_defs()
    }

    operation_properties = (
        tools["apply_edit_transaction"]["function"]["parameters"]["properties"]
        ["operations"]["items"]["properties"]
    )

    for name in (
        "symbol_name",
        "function_name",
        "method_name",
        "class_name",
        "name",
        "new_definition",
        "occurrence",
        "allow_multiple",
    ):
        assert name in operation_properties

    assert (
        tools["apply_edit_transaction"]["function"]["parameters"]["properties"]
        ["operations"]["items"]["additionalProperties"]
        is False
    )


def test_patch_file_schema_is_worker_existing_file_path(tmp_workspace):
    registry = ToolRegistry(tmp_workspace, mode="worker")
    tools = {
        tool["function"]["name"]: tool
        for tool in registry.tool_defs()
    }

    patch_desc = tools["patch_file"]["function"]["description"]
    write_desc = tools["write_file"]["function"]["description"]

    assert "Use this for normal existing-file edits" in patch_desc
    assert "re-read the file" in patch_desc
    assert "do not switch between edit tools" in patch_desc
    assert "new files" in write_desc
    assert "intentional full-file replacement" in write_desc
    assert "use patch_file instead" in write_desc
