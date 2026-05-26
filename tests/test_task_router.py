from aura.conversation.task_router import TaskLane, classify_user_request


def test_undo_routes_to_built_in_undo() -> None:
    route = classify_user_request("/undo")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "undo"


def test_natural_language_undo_routes_to_built_in_undo() -> None:
    route = classify_user_request("undo the most recent commit but keep changes")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "undo"


def test_long_natural_language_undo_routes_to_built_in_undo() -> None:
    route = classify_user_request(
        "undo the most recent commit but keep all working tree changes "
        "uncommitted for review"
    )

    assert route.lane == TaskLane.built_in_action
    assert route.action == "undo"


def test_soft_reset_head_routes_to_built_in_undo() -> None:
    route = classify_user_request("soft reset HEAD~1")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "undo"


def test_git_reset_soft_head_routes_to_built_in_undo() -> None:
    route = classify_user_request("git reset --soft HEAD~1")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "undo"


def test_git_status_routes_to_built_in_status() -> None:
    route = classify_user_request("git status")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "git_status"


def test_show_git_status_routes_to_built_in_status() -> None:
    route = classify_user_request("show git status")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "git_status"


def test_show_git_diff_routes_to_built_in_diff() -> None:
    route = classify_user_request("show git diff")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "git_diff"


def test_show_git_log_routes_to_built_in_log() -> None:
    route = classify_user_request("show git log")

    assert route.lane == TaskLane.built_in_action
    assert route.action == "git_log"


def test_fix_request_routes_to_implementation() -> None:
    route = classify_user_request("fix the create variations feature")

    assert route.lane == TaskLane.implementation


def test_run_pytest_routes_to_validation() -> None:
    route = classify_user_request("run pytest")

    assert route.lane == TaskLane.validation


def test_docs_lookup_routes_to_research() -> None:
    route = classify_user_request("look up ComfyUI docs")

    assert route.lane == TaskLane.research
