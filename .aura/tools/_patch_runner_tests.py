"""Patch test_drone_chain_runner.py to add mock_runner.assert_not_called() calls."""

import pathlib


def run(file_path: str = "tests/test_drone_chain_runner.py") -> dict:
    """Add mock_runner.assert_not_called() after both ValueError assertions.

    Args:
        file_path: Path to the test file.

    Returns:
        Dict with success status and message.
    """
    path = pathlib.Path(file_path)
    content = path.read_text(encoding="utf-8")

    # First test: blank goal_id - ends with drone_lookup block followed by blank line then @patch
    old1 = (
        '            drone_lookup={"drone-a": drone},\n'
        "        )\n"
        "\n"
        "\n"
        '@patch("aura.drones.chain_runner.run_read_only_drone_sync")\n'
        "def test_run_chain_fails_unknown_goal_id_multigoal("
    )
    new1 = (
        '            drone_lookup={"drone-a": drone},\n'
        "        )\n"
        "    mock_runner.assert_not_called()\n"
        "\n"
        "\n"
        '@patch("aura.drones.chain_runner.run_read_only_drone_sync")\n'
        "def test_run_chain_fails_unknown_goal_id_multigoal("
    )

    if old1 not in content:
        return {"ok": False, "error": "First hunk not found"}

    content = content.replace(old1, new1, 1)

    # Second test: unknown goal_id - the LAST occurrence of the drone_lookup block
    old2 = (
        '            drone_lookup={"drone-a": drone},\n'
        "        )"
    )
    new2 = (
        '            drone_lookup={"drone-a": drone},\n'
        "        )\n"
        "    mock_runner.assert_not_called()"
    )

    # Find the last occurrence (should be the second test)
    idx = content.rfind(old2)
    if idx == -1:
        return {"ok": False, "error": "Second hunk not found"}

    content = content[:idx] + new2 + content[idx + len(old2):]

    path.write_text(content, encoding="utf-8")
    return {"ok": True, "message": "Patched successfully"}
