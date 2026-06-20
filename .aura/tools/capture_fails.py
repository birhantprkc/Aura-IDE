import subprocess, sys
result = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_capability_resolver.py', '--tb=line', '-v'],
    capture_output=True, text=True, cwd='C:\\Projects\\Aura-Harness2'
)
# Print just FAILED lines
for line in result.stdout.split('\n'):
    if 'FAILED' in line:
        print(line)
