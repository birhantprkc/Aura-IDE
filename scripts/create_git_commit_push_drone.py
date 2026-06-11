"""Create and globally save the "Git Commit & Push" Drone."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from aura.config import load_workspace_root
from aura.drones.capabilities import CapabilityBinding, CapabilityRequirement
from aura.drones.definition import DroneBudget, DroneDefinition
from aura.drones.store import DroneStore


def main() -> None:
    workspace_root = load_workspace_root() or Path.cwd()
    if not workspace_root.is_dir():
        print(f"Workspace root {workspace_root} is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    # Generate a unique id from the Drone name
    drone_id = DroneStore.next_id(workspace_root, "Git Commit & Push")

    instructions = (
        "You are Aura's Git Commit & Push Drone \u2014 a write-capable repository assistant. "
        "When triggered, follow this exact workflow:\n\n"
        "### Phase 1: Inspect\n"
        "1. Run `git status` (via run_terminal_command) and also use the `git_status` tool to "
        "understand the working tree state.\n"
        "2. Run `git diff` and `git diff --staged` (via run_terminal_command) to see what changed.\n"
        "3. Run `git branch --show-current` and `git remote -v` (via run_terminal_command) to "
        "identify the branch and remote.\n"
        "4. Check `git log --oneline -5` for recent commit style in this repo.\n\n"
        "### Phase 2: Classify Files\n"
        "For each untracked or modified file, decide whether it belongs in the commit:\n"
        "- **Always include**: source files (.py, .js, .ts, .rs, .go, .java, .c, .cpp, .h, .cs, "
        ".rb, .php, .swift, .kt, .scala, .r, .sql, .sh, .bash, .zsh, .fish, .ps1, .toml, .yaml, "
        ".yml, .json, .xml, .cfg, .ini, .conf, .md, .rst, .txt, .css, .scss, .less, .html, .htm, "
        ".jsx, .tsx, .vue, .svelte, .astro, .graphql, .proto, .tf, .dockerfile, .makefile, .cmake, "
        ".nim, .zig, .odin), test files, configuration files, documentation.\n"
        "- **Always skip**: files matching these patterns (case-insensitive): `*.log`, `*.pyc`, "
        "`__pycache__/`, `*.pyo`, `*.class`, `*.o`, `*.obj`, `*.exe`, `*.dll`, `*.so`, `*.dylib`, "
        "`*.a`, `*.lib`, `*.pdb`, `*.ilk`, `*.exp`, `*.suo`, `*.user`, `*.cache`, `*.DS_Store`, "
        "`Thumbs.db`, `*.tmp`, `*.temp`, `*.swp`, `*.swo`, `*~`, `.env`, `.env.*`, `*.secret`, "
        "`*.key`, `*.pem`, `*.crt`, `credentials*`, `secrets*`, `*.token`, `node_modules/`, "
        "`.venv/`, `venv/`, `env/`, `.env/`, `vendor/`, `bower_components/`, `.pytest_cache/`, "
        "`.mypy_cache/`, `.ruff_cache/`, `dist/`, `build/`, `out/`, `target/`, `.next/`, `.nuxt/`, "
        "`coverage/`, `.coverage`, `*.egg-info/`, `*.whl`, `.terraform/`, `*.lock` "
        "(package-lock.json and yarn.lock are OK \u2014 only skip lock files inside cache/vendor dirs).\n"
        "- **Ambiguous/Questionable**: If a file doesn\u2019t clearly fit either category, "
        "or if there are many (5+) untracked files that look like project files but could be "
        "generated, STOP and produce an output with:\n"
        "  - Section: \u201c**\u26a0\ufe0f Needs Decision**\u201d\n"
        "  - List the ambiguous files with their paths and a brief description of what they look like\n"
        "  - Section: \u201c**\u2705 Auto-Staged**\u201d listing what you would stage automatically\n"
        "  - Section: \u201c**\ud83d\udeab Auto-Skipped**\u201d listing what you would skip automatically\n"
        "  - Ask the user which ambiguous files to include, then stop. Do not commit anything.\n\n"
        "### Phase 3: Stage\n"
        "1. Run `git add <file1> <file2> ...` (via run_terminal_command) for all files classified "
        "as \u201calways include\u201d. Use explicit paths, never `git add .` or `git add -A`.\n"
        "2. Never stage files classified as \u201calways skip\u201d.\n"
        "3. If git add fails for any file, report the error and stop.\n\n"
        "### Phase 4: Generate Commit Message\n"
        "1. Analyze the staged diff (`git diff --staged`) to understand the actual changes.\n"
        "2. Generate a clean, descriptive commit message following conventional commits style "
        "when appropriate (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).\n"
        "3. The message should have a short (\u226472 char) subject line, a blank line, and a "
        "bullet-point body summarizing key changes.\n"
        "4. Use `git log --oneline -5` to match the repo\u2019s existing commit style if it "
        "differs from conventional commits.\n"
        "5. Never fabricate changes \u2014 the message must reflect only what\u2019s actually "
        "in the diff.\n\n"
        "### Phase 5: Commit\n"
        "1. Run `git commit -m \"...\"` using the generated message.\n"
        "2. Use the local git user.name/user.email (no overriding \u2014 respect existing config).\n"
        "3. Never use `--amend`, `--force`, or any destructive flags.\n"
        "4. If commit fails, report the error and stop.\n\n"
        "### Phase 6: Push\n"
        "1. Determine the remote: check for an upstream tracking branch "
        "(`git rev-parse --abbrev-ref @{upstream}`). If set, use that remote. "
        "Otherwise use `origin`.\n"
        "2. Run `git push <remote> <branch>`.\n"
        "3. Never use `--force`, `--force-with-lease`, or `-f`.\n"
        "4. If no remote is configured or the remote URL is inaccessible, stop and tell the user: "
        "\u201cNo remote configured for branch <branch>. Please set up a remote with: "
        "git remote add origin <url>\u201d\n"
        "5. If push fails (e.g., rejected due to remote changes), stop and tell the user exactly "
        "what happened. Suggest `git pull --rebase` but do NOT run it.\n\n"
        "### Phase 7: Receipt\n"
        "Always produce the final receipt with the sections listed in the output_contract. "
        "If anything was skipped or needs a decision, include that in the receipt.\n\n"
        "## Safety Boundaries (HARD RULES):\n"
        "- NEVER force push (`-f`, `--force`, `--force-with-lease`).\n"
        "- NEVER amend previous commits (`--amend`).\n"
        "- NEVER switch branches (`git checkout`, `git switch`).\n"
        "- NEVER stash or delete files (`git stash`, `git clean`, `git reset --hard`).\n"
        "- NEVER run `git add .`, `git add -A`, or `git add *`.\n"
        "- NEVER include secrets, env files, or credentials in commits.\n"
        "- NEVER rebase or squash.\n"
        "- If anything is uncertain, STOP and ask the user.\n"
        "- Only push to `origin` or the configured upstream tracking remote.\n\n"
        "## Access Requirements:\n"
        "- Local git installation (run `git --version` at start to verify).\n"
        "- Valid push credentials (SSH or HTTPS) already configured in the environment.\n"
        "- If git is not found or credentials are missing, report and stop."
    )

    output_contract = (
        "Return a structured receipt with exactly these sections:\n"
        "1. **Files Staged** \u2014 list of files staged for commit.\n"
        "2. **Files Skipped** \u2014 list of files intentionally skipped and why.\n"
        "3. **Commit Message** \u2014 the generated commit message.\n"
        "4. **Commit Hash** \u2014 the full commit SHA.\n"
        "5. **Branch** \u2014 the branch name committed to.\n"
        "6. **Remote** \u2014 the remote name and URL pushed to.\n"
        "7. **Push Result** \u2014 success or failure with details.\n"
        "If the Drone stops early due to ambiguous files or missing remote, return a clear "
        "status explaining what needs user decision."
    )

    allowed_tools = (
        "run_terminal_command",
        "git_status",
        "git_diff",
        "git_log",
        "git_show",
        "git_branch_list",
        "get_workspace_snapshot",
        "read_file",
        "grep_search",
        "glob",
        "list_directory",
        "run_diagnostic_command",
    )

    capability_requirements = (
        CapabilityRequirement(
            capability="execute terminal commands",
            purpose="Run git add, git commit, git push, and read-only git inspection commands "
            "in a shell",
        ),
        CapabilityRequirement(
            capability="inspect git status",
            purpose="Read the git working tree status to see staged, unstaged, and untracked files",
        ),
        CapabilityRequirement(
            capability="read git diffs",
            purpose="Inspect unstaged and staged diffs to understand what changed for commit "
            "message generation",
        ),
        CapabilityRequirement(
            capability="stage files for commit",
            purpose="Run git add to stage relevant changed files while skipping junk",
        ),
        CapabilityRequirement(
            capability="commit changes",
            purpose="Run git commit with a generated message using local user.name/email config",
        ),
        CapabilityRequirement(
            capability="push to remote",
            purpose="Push current branch to configured remote (origin or upstream tracking remote)",
        ),
    )

    capability_bindings = (
        CapabilityBinding(
            capability="execute terminal commands",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses run_terminal_command for shell execution",
        ),
        CapabilityBinding(
            capability="inspect git status",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses git_status tool and run_terminal_command for git status",
        ),
        CapabilityBinding(
            capability="read git diffs",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses git_diff tool and run_terminal_command for git diff",
        ),
        CapabilityBinding(
            capability="stage files for commit",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses run_terminal_command for git add",
        ),
        CapabilityBinding(
            capability="commit changes",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses run_terminal_command for git commit",
        ),
        CapabilityBinding(
            capability="push to remote",
            route_kind="generated_code",
            source="aura_codegen",
            tool_names=(),
            setup_status="pending",
            setup_notes="Uses run_terminal_command for git push",
        ),
    )

    setup_steps = (
        "Verify git is installed: run `git --version`",
        "Verify the workspace is a git repository",
        "Confirm push credentials are configured (SSH key or HTTPS credential helper)",
    )

    first_run_test = (
        "Run in a test repository with mixed unstaged changes and some junk files "
        "(e.g., .log, .tmp, __pycache__/, .env); verify: "
        "(1) only source files are staged, (2) junk files are skipped, "
        "(3) a meaningful commit message is generated, (4) commit succeeds, "
        "(5) push to origin succeeds, (6) final receipt includes all required sections. "
        "Also test with ambiguous untracked files to confirm it stops and asks for user "
        "decision before proceeding."
    )

    drone = DroneDefinition(
        id=drone_id,
        name="Git Commit & Push",
        description=(
            "Inspects git working tree, stages relevant changes (skipping junk), generates "
            "a descriptive commit message, commits, and pushes to the configured remote. "
            "Reports a receipt with commit hash, branch, remote URL, and push status."
        ),
        instructions=instructions,
        write_policy="normal_diff_approval",
        allowed_tools=allowed_tools,
        output_contract=output_contract,
        budget=DroneBudget(max_tool_rounds=12, timeout_seconds=300),
        scope="global",
        enabled=True,
        created_by="user",
        capability_requirements=capability_requirements,
        capability_bindings=capability_bindings,
        setup_steps=setup_steps,
        first_run_test=first_run_test,
    )

    DroneStore.validate_drone(drone)
    DroneStore.save_drone(workspace_root, drone)

    # Verify the saved drone loads correctly
    loaded = DroneStore.load_drone(workspace_root, drone_id)
    if loaded is None:
        print("ERROR: Saved drone could not be loaded back.", file=sys.stderr)
        sys.exit(1)

    assert loaded.id == drone_id
    assert loaded.name == "Git Commit & Push"
    assert loaded.write_policy == "normal_diff_approval"
    assert loaded.scope == "global"
    assert loaded.enabled is True
    assert loaded.budget.max_tool_rounds == 12
    assert loaded.budget.timeout_seconds == 300
    assert len(loaded.capability_requirements) == 6
    assert len(loaded.capability_bindings) == 6
    assert len(loaded.setup_steps) == 3
    assert loaded.first_run_test == first_run_test

    print(f"Drone saved successfully: id={drone_id}")
    print(f"Saved to global drones directory.")


if __name__ == "__main__":
    main()
