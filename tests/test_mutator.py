import pytest
from pathlib import Path
from aura.craft.mutator import SafeMutator

@pytest.fixture
def mutator():
    return SafeMutator()

def test_narration_comment_stripping(mutator):
    code = '''
def foo():
    # Helper method
    x = [] # keep inline comment
    return x
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "Initialize the list" not in res
    assert "Helper method" not in res
    assert "this function does things" not in res
    assert "# keep inline comment" in res
    assert "def foo():" in res
    
def test_decorative_banner_removal(mutator):
    code = '''
# ========================================
# CONFIGURATION
# ----------------------------------------
def setup():
    pass
# ****************************************
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "===" not in res
    assert "---" not in res
    assert "***" not in res
    assert "CONFIGURATION" in res # Not a matching banner, just text
    assert "def setup():" in res

def test_empty_init_removal_pass(mutator):
    code = '''
class MyClass:
    def __init__(self):
        pass

    def other(self):
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" not in res
    assert "def other(self):" in res

def test_empty_init_removal_docstring_pass(mutator):
    code = '''
class MyClass:
    def __init__(self):
        """Init."""
        pass
        
    def other(self):
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" not in res
    assert '"""Init."""' not in res
    assert "def other(self):" in res

def test_empty_init_removal_ellipsis(mutator):
    code = '''
class MyClass:
    def __init__(self):
        ...

    def other(self):
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" not in res
    assert "def other(self):" in res

def test_preservation_of_non_narration_comments(mutator):
    code = '''
# Non-narration comment about a weird hack
def foo():
    pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "Non-narration comment" in res

def test_no_changes_non_python(mutator):
    code = '# Initialize text'
    res = mutator.mutate(code, Path("test.txt"))
    assert "Initialize text" in res

def test_invalid_syntax_falls_back(mutator):
    code = '''
def foo()
    pass # helper function
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "helper function" in res

def test_redundant_pass_removal(mutator):
    code = '''
def foo():
    pass
    print("hi")
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "pass" not in res
    assert 'print("hi")' in res

def test_only_pass_kept(mutator):
    code = '''
def foo():
    pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "pass" in res

def test_nested_classes(mutator):
    code = '''
class Outer:
    class Inner:
        def __init__(self):
            pass
        
        def bar(self):
            pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" not in res
    assert "def bar(self):" in res


def test_decorated_init_preserved(mutator):
    """@overload def __init__ with ... must NOT be removed"""
    code = '''
class Foo:
    @overload
    def __init__(self, x: int) -> None: ...
    def __init__(self, x: int | None = None) -> None:
        self.x = x or 0
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "@overload" in res  # decorator preserved
    assert "def __init__" in res  # both inits preserved (overload + real)

def test_empty_init_only_pass_not_removed_when_decorated(mutator):
    """@staticmethod def __init__ must NOT be removed even with empty body"""
    code = '''
class Foo:
    @staticmethod
    def __init__():
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "@staticmethod" in res
    assert "def __init__" in res

def test_non_init_empty_method_preserved(mutator):
    """Only __init__ methods are removed, not other methods"""
    code = '''
class Foo:
    def setup():
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def setup()" in res
    assert "pass" in res

def test_class_with_actual_work_in_init_not_removed(mutator):
    """__init__ with actual statements is NOT removed"""
    code = '''
class Foo:
    def __init__(self):
        self.x = 1
        self.y = 2
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" in res
    assert "self.x = 1" in res

def test_empty_init_multi_line_signature(mutator):
    """Multi-line __init__ signature with empty body is still caught"""
    code = '''
class Foo:
    def __init__(
        self,
        x: int = 0,
        y: str = "hi",
    ):
        pass
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "def __init__" not in res
    assert "def foo(self):" not in res  # no phantom lines

def test_narration_comment_inline_preserved(mutator):
    """Inline comments (after code) are never removed"""
    code = '''
x = []  # Initialize the list
y = {}  # Process items
'''
    res = mutator.mutate(code, Path("test.py"))
    assert "Initialize the list" in res  # inline comment preserved!
    assert "Process items" in res
