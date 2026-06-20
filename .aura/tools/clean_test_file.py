"""Remove resolve_capability references from test_tool_registry.py."""
import re
import sys

path = "tests/test_tool_registry.py"
with open(path, "r") as f:
    content = f.read()

original_len = len(content)

# Remove lines containing "resolve_capability" from EXPECTED_TOOLS set and planner test
content = re.sub(r'^[ \t]+"resolve_capability",\n', "", content, flags=re.MULTILINE)

# Remove TestResolveCapability class
content = re.sub(
    r"\nclass TestResolveCapability:.*?(?=\nclass |\n# |\Z)",
    "",
    content,
    flags=re.DOTALL,
)

with open(path, "w") as f:
    f.write(content)

print(f"Removed {original_len - len(content)} bytes")
cnt = content.count("resolve_capability")
print(f"Remaining 'resolve_capability' occurrences: {cnt}")
