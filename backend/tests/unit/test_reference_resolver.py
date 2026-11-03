import pytest

from reposcope.parsing.binding_index import build_binding_index
from reposcope.parsing.reference_resolver import resolve_references, resolved_edges
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.resolver import collect_references
from reposcope.parsing.scope_index import build_scope_index


def analyze(files, roots=(".",)):
    parsed = [parse_python(text.encode("utf-8"), file_path=path)
              for path, text in files.items()]
    repo = build_repo_index(parsed, source_roots=roots)
    collection = collect_references(build_binding_index(build_scope_index(repo)))
    return repo, resolve_references(collection)


def find(results, expression, kind="call", path="app.py"):
    return next(r for r in results if r.reference.expression == expression
                and r.reference.reference_kind == kind and r.reference.file_path == path)


def check(repo, result, qualname, status="EXACT"):
    assert result.status == status
    assert result.confidence == (0.5 if status == "INFERRED" else 1.0)
    assert repo.definitions_by_local_key[result.targets[0].symbol_key].qualname == qualname


@pytest.mark.parametrize("statement,call", [
    ("from utils import helper", "helper()"),
    ("from utils import helper as h", "h()"),
    ("import utils", "utils.helper()"),
    ("import utils as u", "u.helper()"),
])
def test_imported_calls(statement, call):
    repo, results = analyze({"utils.py": "def helper(): return 1\n",
                             "app.py": statement + "\n" + call + "\n"})
    check(repo, find(results, call), "helper")


def test_relative_import():
    repo, results = analyze({"pkg/__init__.py": "", "pkg/utils.py": "def helper(): pass\n",
                             "pkg/app.py": "from .utils import helper as h\nh()\n"})
    check(repo, find(results, "h()", path="pkg/app.py"), "helper")


def test_package_dotted_import():
    repo, results = analyze({"pkg/__init__.py": "", "pkg/utils.py": "def helper(): pass\n",
                             "app.py": "import pkg.utils\npkg.utils.helper()\n"})
    check(repo, find(results, "pkg.utils.helper()"), "helper")


def test_reexport():
    repo, results = analyze({"pkg/__init__.py": "from .utils import helper\n",
                             "pkg/utils.py": "def helper(): pass\n",
                             "app.py": "from pkg import helper\nhelper()\n"})
    check(repo, find(results, "helper()"), "helper")


def test_imported_base():
    repo, results = analyze({"base.py": "class Base: pass\n",
                             "app.py": "from base import Base\nclass Child(Base): pass\n"})
    check(repo, find(results, "Base", kind="base_class"), "Base")


def test_class_member():
    repo, results = analyze({"app.py": "class Service:\n    def run(self): pass\nService.run(None)\n"})
    check(repo, find(results, "Service.run(None)"), "Service.run")


def test_self_receiver_is_inferred():
    repo, results = analyze({"app.py": "class Service:\n    def helper(self): pass\n    def run(self):\n        self.helper()\n"})
    check(repo, find(results, "self.helper()"), "Service.helper", "INFERRED")


@pytest.mark.parametrize("source,expression", [
    ("import missing\nmissing.run()\n", "missing.run()"),
    ("from utils import helper\nhelper = unknown\nhelper()\n", "helper()"),
    ("if flag:\n    from utils import helper\nhelper()\n", "helper()"),
    ("def run(helper):\n    helper()\n", "helper()"),
    ("helper()\nfrom utils import helper\n", "helper()"),
    ("from utils import *\nhelper()\n", "helper()"),
    ("class S:\n    def helper(self): pass\n    def run(self):\n        self = unknown\n        self.helper()\n", "self.helper()"),
])
def test_unsupported_or_shadowed_is_unresolved(source, expression):
    _, results = analyze({"utils.py": "def helper(): pass\n", "app.py": source})
    assert find(results, expression).status == "UNRESOLVED"


def test_import_cycle_terminates():
    _, results = analyze({"a.py": "from b import helper\n", "b.py": "from a import helper\n",
                          "app.py": "from a import helper\nhelper()\n"})
    assert find(results, "helper()").status == "UNRESOLVED"


def test_duplicate_module_candidates_preserved():
    _, results = analyze({"left/utils.py": "def helper(): pass\n",
                          "right/utils.py": "def helper(): pass\n",
                          "left/app.py": "from utils import helper\nhelper()\n"}, ("left", "right"))
    result = find(results, "helper()", path="left/app.py")
    assert result.status == "AMBIGUOUS"
    assert len(result.targets) == 2


def test_edges_and_result_coverage():
    _, results = analyze({"app.py": "class Base: pass\nclass Child(Base): pass\ndef helper(): pass\nhelper()\nunknown()\n"})
    edges = resolved_edges(results)
    assert {e.kind for e in edges} == {"CALLS", "INHERITS"}
    assert len({r.reference.reference_key for r in results}) == len(results)
    assert any(r.status == "UNRESOLVED" for r in results)

def test_instance_dictionary_write_does_not_block_imported_class():
    repo, results = analyze({
        "store.py": (
            "class Repo:\n"
            "    def __init__(self):\n"
            "        self.items = {}\n"
            "    def add(self, key, value):\n"
            "        self.items[key] = value\n"
        ),
        "app.py": (
            "from store import Repo\n"
            "Repo()\n"
        ),
    })

    check(repo, find(results, "Repo()"), "Repo")


def test_instance_dictionary_write_does_not_block_module_imported_call():
    repo, results = analyze({
        "errors.py": (
            "class Missing(Exception):\n"
            "    pass\n"
        ),
        "store.py": (
            "from errors import Missing\n"
            "class Repo:\n"
            "    def __init__(self):\n"
            "        self.items = {}\n"
            "    def add(self, key, value):\n"
            "        self.items[key] = value\n"
            "    def fail(self):\n"
            "        raise Missing()\n"
        ),
        "app.py": "",
    })

    check(
        repo,
        find(results, "Missing()", path="store.py"),
        "Missing",
    )


def test_reassigned_receiver_keeps_namespace_uncertainty():
    _, results = analyze({
        "store.py": (
            "class Repo:\n"
            "    def write(self, key, value):\n"
            "        self = unknown\n"
            "        self.items[key] = value\n"
        ),
        "app.py": (
            "from store import Repo\n"
            "Repo()\n"
        ),
    })

def test_stdlib_dataclass_constructor_is_resolved():
    repo, results = analyze({
        "models.py": (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class User:\n"
            "    name: str\n"
        ),
        "app.py": (
            "from models import User\n"
            "User('Soham')\n"
        ),
    })

    check(repo, find(results, "User('Soham')"), "User")


def test_aliased_stdlib_dataclass_is_resolved():
    repo, results = analyze({
        "models.py": (
            "from dataclasses import dataclass as dc\n"
            "@dc\n"
            "class User:\n"
            "    name: str\n"
        ),
        "app.py": (
            "from models import User\n"
            "User('Soham')\n"
        ),
    })

    check(repo, find(results, "User('Soham')"), "User")


def test_custom_decorator_named_dataclass_is_not_trusted():
    _, results = analyze({
        "models.py": (
            "def dataclass(cls):\n"
            "    return unknown\n"
            "@dataclass\n"
            "class User:\n"
            "    pass\n"
        ),
        "app.py": (
            "from models import User\n"
            "User()\n"
        ),
    })

    assert find(results, "User()").status == "UNRESOLVED"
