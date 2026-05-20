import sys
from pathlib import Path
from aura.craft.types import ProposalCapsule, ChangeIntent
from aura.craft.reference_checker import ReferenceChecker

code = 'def foo():\n    return undefined_variable\n'

capsule = ProposalCapsule(
    path=Path('test.py'),
    language='python',
    tool_name='write_file',
    original_code='',
    proposed_code=code,
    changed_line_ranges=[(1, 4)],
    intent=ChangeIntent.unknown,
)
print('capsule created', flush=True)

checker = ReferenceChecker()
print('checker created', flush=True)

issues = checker.check(capsule, workspace_root=Path.cwd())
print('Issues found:', len(issues), flush=True)
for issue in issues:
    print(' -', issue.severity.value, issue.code, issue.message, flush=True)

if len(issues) > 0:
    print('Smoke test PASSED', flush=True)
else:
    print('Smoke test FAILED: expected issues but got none', flush=True)
