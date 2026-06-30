from aura.conversation.planner_stream_hygiene import PlannerStreamHygiene


def test_planner_stream_hygiene_suppresses_fake_implementation_chatter():
    hygiene = PlannerStreamHygiene()

    visible = "".join(
        [
            hygiene.filter_delta("Now I have a thorough understanding. "),
            hygiene.filter_delta("Let me implement this. "),
            hygiene.filter_delta("I can't write files directly, so let me prepare the capsule. "),
            hygiene.flush(),
        ]
    )

    assert visible == ""


def test_planner_stream_hygiene_keeps_real_question():
    hygiene = PlannerStreamHygiene()

    visible = hygiene.filter_delta("Which file should I update?") + hygiene.flush()

    assert visible == "Which file should I update?"


def test_planner_stream_hygiene_sanitizes_done_content():
    hygiene = PlannerStreamHygiene()

    sanitized = hygiene.sanitize_message_text(
        "Now I have the full context. The target file is missing; which path should I use?"
    )

    assert "Now I have" not in sanitized
    assert sanitized == "The target file is missing; which path should I use?"
