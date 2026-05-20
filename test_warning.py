import ast
import warnings

code = "a = \"\\e\""
print("code:", code)

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    ast.parse(code)
    for warning in w:
        print(warning.message)
