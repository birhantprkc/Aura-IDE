# Drones

Drones are reusable folder-backed workers. A Drone is registered from a folder
that contains:

- `drone.json` (the manifest)
- a runtime entrypoint file (e.g. `main.py` for the Python adapter)
- optional support files such as `requirements.txt` and `README.md`

Drones declare a `runtime` and `entrypoint` in their manifest. Python is the
current built-in runtime adapter, but the Drone product contract is runtime-
backed and not Python-specific. `route`, `input_contract`, and
`cargo_contract` are optional but recommended for new Drones. Existing Drones
without them still work.

```json
{
  "id": "source-scout",
  "name": "Source Scout",
  "description": "Collects source candidates.",
  "runtime": "python",
  "entrypoint": "main:run",
  "instructions": "Collect candidates and return cargo.",
  "write_policy": "read_only",
  "allowed_tools": [],
  "output_contract": "Return candidate cargo.",
  "route": {
    "type": "feed",
    "targets": ["https://www.reddit.com/r/.../.rss", "https://hn.algolia.com/api/v1/search"],
    "auth": "none",
    "reason": "Reddit RSS and HN Algolia provide public, machine-readable sources.",
    "fallback": "HN Algolia if Reddit RSS is rate-limited"
  },
  "cargo_contract": {
    "type": "candidate_list",
    "description": "List of source candidates matching the query",
    "schema": {
      "type": "object",
      "properties": {
        "candidates": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "source": {"type": "string"},
              "url": {"type": "string"},
              "snippet": {"type": "string"},
              "timestamp": {"type": "string"},
              "matched_topic": {"type": "string"},
              "reason": {"type": "string"}
            }
          }
        }
      }
    }
  },
  "input_contract": {
    "type": "search_query",
    "description": "Topic or keywords to search for",
    "schema": {
      "type": "object",
      "properties": {
        "query": {"type": "string"},
        "max_results": {"type": "integer", "default": 20}
      }
    }
  }
}
```

`allowed_tools` is a compatibility field for older UI surfaces. New Drones run
through their folder entrypoint, not through an LLM tool menu.

Use `/drone make <brief>` to enter Drone Architect mode. Aura may use the
Planner/Worker harness to author the folder, but registration goes through
`register_drone_folder`, which validates the manifest and runs a safe readiness
launch (trial run) before installing the Drone globally.
