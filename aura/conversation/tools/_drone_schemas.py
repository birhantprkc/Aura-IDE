"""Tool definition schemas for Drone-related tools."""

from __future__ import annotations

from typing import Any

LAUNCH_READ_ONLY_DRONE_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "launch_read_only_drone",
        "description": (
            "Launch a saved read-only Drone in the background for a focused "
            "investigation sub-task. Returns immediately with a run_id. "
            "Use check_drone_run later to retrieve results. "
            "Use this when the task is a focused side investigation (bug tracing, "
            "impact scouting, test discovery) that would otherwise burn tool calls "
            "or clutter the main conversation. Do NOT use for tiny tasks where "
            "direct inspection is faster."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drone_id": {
                    "type": "string",
                    "description": "The id of the saved read-only Drone to run (from Available Drones list).",
                },
                "goal": {
                    "type": "string",
                    "description": "What the Drone should investigate or accomplish. Be specific so the Drone's instructions can guide it precisely.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional: why you are launching this Drone. Used only for logging.",
                },
            },
            "required": ["drone_id", "goal"],
        },
    },
}


RUN_READ_ONLY_DRONE_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_read_only_drone",
        "description": (
            "Run a saved read-only Drone directly in the background to handle a "
            "focused sub-task. Returns results synchronously."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drone_id": {
                    "type": "string",
                    "description": "The id of the saved read-only Drone to run (from Available Drones list).",
                },
                "goal": {
                    "type": "string",
                    "description": "What the Drone should investigate or accomplish. Must be non-empty.",
                },
            },
            "required": ["drone_id", "goal"],
        },
    },
}


CHECK_DRONE_RUN_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_drone_run",
        "description": (
            "Check the status of a previously launched read-only Drone run. "
            "Returns queued/running/completed/failed/timed_out state. "
            "If completed, includes summary, tool call counts, and elapsed time. "
            "Optionally wait a few seconds for completion (capped at 10s)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The run_id returned from launch_read_only_drone.",
                },
                "wait_seconds": {
                    "type": "number",
                    "description": "Optional: seconds to wait for completion (capped at 10). Default 0 (return immediately).",
                },
                "include_receipt": {
                    "type": "boolean",
                    "description": "If true, include the full receipt in the result. Default false.",
                },
            },
            "required": ["run_id"],
        },
    },
}


REGISTER_DRONE_FOLDER_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "register_drone_folder",
        "description": (
            "Validate and register a completed folder-backed Drone. "
            "The folder must already contain drone.json and an entrypoint program. "
            "The manifest must declare a command entrypoint with json-stdio protocol. "
            "Registration validates the folder structure and copies it into "
            "Aura's global Drone directory. Real Drone behavior is checked "
            "when the user runs the Drone from Workbay."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative path to the completed Drone folder, "
                        "for example .aura/drone-build/source-scout."
                    ),
                },
            },
            "required": ["folder_path"],
        },
    },
}
