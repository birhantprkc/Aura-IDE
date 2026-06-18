# Drones

Drones are reusable folder-backed workers. A Drone is registered from a folder
that contains a manifest (`drone.json`) and an entrypoint program. Any language
that reads JSON from stdin and writes JSON to stdout works.

## How they work

A Drone declares a command entrypoint in its manifest. When you run it, Aura
launches the command, sends one JSON object on stdin, and reads one JSON result
from stdout. That result is also the Drone's **receipt** — it proves what
happened and includes enough detail to judge the work without re-running.

## Running Drones

- **Run** — Start a single Drone run from the main UI or the Drone Workbay.
- **Loop** — Toggle looping to run a Drone repeatedly until stopped. Each lap
  is one bounded run. The Drone should be safe to re-run.
- **Delete** — Remove the Drone from the project roster. The folder stays on
  disk until you explicitly clean it up.

## Drone Workbay

The Drone Workbay shows standalone saved Drone cards. From each card you can
Run the Drone once, toggle Loop for repeated runs, or Delete it. Each run
produces a receipt you can browse from the Workbay. Read-only Drones run in
parallel for safe background investigation. Write-capable Drones follow the
same diff-approval cycle as any Worker.

## Manifest example

Every Drone needs a `drone.json` manifest with at minimum these fields:

```json
{
  "id": "source-scout",
  "name": "Source Scout",
  "description": "Collects source candidates matching a topic.",
  "instructions": "Given a topic string, search public sources and return matching candidates.",
  "write_policy": "read_only",
  "entrypoint": {
    "kind": "command",
    "command": ["python", "main.py"],
    "protocol": "json-stdio"
  },
  "output_contract": {
    "oneOf": [
      {
        "type": "object",
        "properties": {
          "ok": {"const": true},
          "candidates": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "title": {"type": "string"},
                "source": {"type": "string"},
                "url": {"type": "string"},
                "snippet": {"type": "string"}
              }
            }
          },
          "summary": {"type": "string"}
        },
        "required": ["ok", "candidates", "summary"]
      },
      {
        "type": "object",
        "properties": {
          "ok": {"const": false},
          "error": {"type": "string"},
          "summary": {"type": "string"}
        },
        "required": ["ok", "error", "summary"]
      }
    ]
  }
}
```

Optional manifest fields such as `input_contract` and `cargo_contract` can
document expected input shape and structured intermediate data. See
`aura/drones/drone_construction.md` for the full construction spec.

## Receipts

Every run produces a receipt — the Drone's stdout JSON object. Receipts are
stored per project so you can review past runs, check summaries, and understand
what the Drone accomplished without re-running it.
