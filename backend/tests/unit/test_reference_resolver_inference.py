"""Regression tests for bounded annotation/receiver propagation."""
import pytest

from reposcope.parsing.binding_index import build_binding_index
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.reference_resolver import resolve_references
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.resolver import collect_references
from reposcope.parsing.scope_index import build_scope_index


def analyze(sources):
    parsed = [parse_python(text.encode("utf-8"), file_path=path)
              for path, text in sources.items()]
    repo = build_repo_index(parsed)
    collection = collect_references(build_binding_index(build_scope_index(repo)))
    return repo, resolve_references(collection)


def result(results, expression, path="app.py"):
    return next(r for r in results if r.reference.file_path == path
                and r.reference.reference_kind == "call"
                and r.reference.expression == expression)


def inferred(repo, results, expression, qualname, path="app.py"):
    r = result(results, expression, path)
    assert r.status == "INFERRED"
    assert r.confidence == 0.5
    assert len(r.targets) == 1
    assert repo.definitions_by_local_key[r.targets[0].symbol_key].qualname == qualname


USER = "class User:\n    def display(self): pass\n"


def test_local_constructor_assignment():
    repo, results = analyze({"app.py": USER + "user = User()\nuser.display()\n"})
    inferred(repo, results, "user.display()", "User.display")


def test_annotated_function_return():
    repo, results = analyze({"models.py": USER,
        "app.py": "from models import User\ndef make() -> User:\n    return User()\nu = make()\nu.display()\n"})
    inferred(repo, results, "u.display()", "User.display")


def test_annotated_parameter():
    repo, results = analyze({"app.py": USER + "def show(u: User):\n    u.display()\n"})
    inferred(repo, results, "u.display()", "User.display")


def test_string_return_annotation():
    repo, results = analyze({"app.py": USER + "def make() -> 'User':\n    return User()\nu = make()\nu.display()\n"})
    inferred(repo, results, "u.display()", "User.display")


def test_constructor_attribute_and_generator_scope():
    source = (
        "class Repo:\n"
        "    def all(self): return []\n"
        "class Service:\n"
        "    def __init__(self, repository: Repo):\n"
        "        self.repository = repository\n"
        "    def run(self):\n"
        "        return (x for x in self.repository.all())\n"
    )
    repo, results = analyze({"app.py": source})
    inferred(repo, results, "self.repository.all()", "Repo.all")


def test_annotated_method_return():
    source = USER + (
        "class Service:\n"
        "    def get(self) -> User: return User()\n"
        "    def run(self):\n"
        "        user = self.get()\n"
        "        user.display()\n"
    )
    repo, results = analyze({"app.py": source})
    inferred(repo, results, "user.display()", "User.display")


FORWARDER = (
    "from functools import wraps\n"
    "def trace(func):\n"
    "    @wraps(func)\n"
    "    def wrapped(*args, **kwargs):\n"
    "        print(f'Calling {func.__name__}')\n"
    "        return func(*args, **kwargs)\n"
    "    return wrapped\n"
)


def test_structural_forwarding_decorator_not_name_allowlist():
    source = USER + (
        "from decorators import trace\n"
        "class Service:\n"
        "    @trace\n"
        "    def get(self) -> User: return User()\n"
        "    @trace\n"
        "    def run(self):\n"
        "        user = self.get()\n"
        "        user.display()\n"
        "service = Service()\n"
        "service.get()\n"
    )
    repo, results = analyze({"decorators.py": FORWARDER, "app.py": source})
    inferred(repo, results, "service.get()", "Service.get")
    inferred(repo, results, "user.display()", "User.display")


@pytest.mark.parametrize("tail", [
    "u = unknown\nu.display()\n",
    "del u\nu.display()\n",
    "if flag:\n    u = unknown\nu.display()\n",
])
def test_rebinding_deletion_and_branch_uncertainty(tail):
    _, results = analyze({"app.py": USER + "u = User()\n" + tail})
    assert result(results, "u.display()").status == "UNRESOLVED"


def test_recursive_return_chain_is_bounded():
    _, results = analyze({"app.py": "def factory(): return factory()\nx = factory()\nx.run()\n"})
    assert result(results, "x.run()").status == "UNRESOLVED"


def test_unknown_decorator_is_not_trusted():
    _, results = analyze({"decorators.py": "def trace(func): return unknown\n",
        "app.py": "from decorators import trace\nclass S:\n    @trace\n    def run(self): pass\ns = S()\ns.run()\n"})
    assert result(results, "s.run()").status == "UNRESOLVED"


def test_async_call_is_not_its_awaited_result():
    _, results = analyze({"app.py": USER + "async def make() -> User: return User()\nu = make()\nu.display()\n"})
    assert result(results, "u.display()").status == "UNRESOLVED"


def test_multiple_attribute_writes_prevent_inference():
    source = (
        "class Repo:\n    def all(self): pass\n"
        "class Service:\n"
        "    def __init__(self, repository: Repo):\n        self.repository = repository\n"
        "    def replace(self):\n        self.repository = unknown\n"
        "    def run(self):\n        self.repository.all()\n"
    )
    _, results = analyze({"app.py": source})
    assert result(results, "self.repository.all()").status == "UNRESOLVED"
