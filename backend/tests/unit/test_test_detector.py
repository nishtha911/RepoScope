from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.resolver_pipeline import analyze_python_files
from reposcope.parsing.test_detector import detect_test_links


def detect(sources):
    parsed_files = [
        parse_python(source.encode("utf-8"), file_path=path)
        for path, source in sources.items()
    ]
    analysis = analyze_python_files(parsed_files)
    result = detect_test_links(parsed_files, analysis.edges)
    names = {
        symbol.local_key: symbol.name
        for parsed in parsed_files
        for symbol in parsed.symbols
    }
    return result, names


def test_direct_call_links_implementation_to_test():
    result, names = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "from users import create_user\n"
            "def test_create_user():\n"
            "    assert create_user() == 1\n"
        ),
    })
    assert len(result.links) == 1
    link = result.links[0]
    assert link.rule == "direct_call"
    assert names[link.implementation_key] == "create_user"
    assert names[link.test_key] == "test_create_user"
    assert len(link.reference_keys) == 1
    assert result.edges[0].source_key == link.implementation_key
    assert result.edges[0].target_key == link.test_key
    assert result.edges[0].kind == "TESTED_BY"


def test_two_hop_path_through_local_test_helper():
    result, names = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "from users import create_user\n"
            "def exercise():\n"
            "    return create_user()\n"
            "def test_creation():\n"
            "    assert exercise() == 1\n"
        ),
    })
    assert len(result.links) == 1
    link = result.links[0]
    assert link.rule == "two_hop_call"
    assert tuple(names[key] for key in link.call_path) == (
        "test_creation", "exercise", "create_user",
    )
    assert len(link.reference_keys) == 2
    assert link.confidence == 0.8


def test_naming_fallback_uses_matching_module_stem():
    result, names = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "def test_create_user():\n"
            "    assert True\n"
        ),
    })
    assert len(result.links) == 1
    link = result.links[0]
    assert link.rule == "name_match"
    assert names[link.implementation_key] == "create_user"
    assert link.call_path == ()
    assert link.confidence == 0.5


def test_ambiguous_naming_does_not_emit_edge():
    result, _ = detect({
        "first/users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "second/users.py": (
            "def create_user():\n"
            "    return 2\n"
        ),
        "tests/test_users.py": (
            "def test_create_user():\n"
            "    assert True\n"
        ),
    })
    assert result.links == ()
    assert result.edges == ()
    assert len(result.gaps) == 1
    assert result.gaps[0].rule_id == "tests.ambiguous_name"


def test_three_hop_implementation_is_not_linked():
    result, _ = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "from users import create_user\n"
            "def inner():\n"
            "    return create_user()\n"
            "def outer():\n"
            "    return inner()\n"
            "def test_creation():\n"
            "    assert outer() == 1\n"
        ),
    })
    assert result.links == ()
    assert result.edges == ()
    assert len(result.gaps) == 1


def test_test_class_method_is_discovered():
    result, names = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "from users import create_user\n"
            "class TestUsers:\n"
            "    def test_creation(self):\n"
            "        assert create_user() == 1\n"
        ),
    })
    assert len(result.links) == 1
    link = result.links[0]
    assert link.rule == "direct_call"
    assert names[link.test_key] == "test_creation"
    assert names[link.implementation_key] == "create_user"


def test_nested_test_named_function_is_not_discovered():
    result, _ = detect({
        "users.py": (
            "def create_user():\n"
            "    return 1\n"
        ),
        "tests/test_users.py": (
            "from users import create_user\n"
            "def helper():\n"
            "    def test_creation():\n"
            "        return create_user()\n"
            "    return test_creation\n"
        ),
    })
    assert result.links == ()
    assert result.edges == ()
    assert result.gaps == ()


def test_helper_cycle_does_not_create_links_or_loop():
    result, _ = detect({
        "tests/test_users.py": (
            "def first():\n"
            "    return second()\n"
            "def second():\n"
            "    return first()\n"
            "def test_cycle():\n"
            "    first()\n"
        ),
    })
    assert result.links == ()
    assert result.edges == ()
    assert len(result.gaps) == 1


def test_direct_and_two_hop_implementation_targets_are_retained():
    result, names = detect({
        "users.py": (
            "def inner():\n"
            "    return 1\n"
            "def outer():\n"
            "    return inner()\n"
        ),
        "tests/test_users.py": (
            "from users import outer\n"
            "def test_flow():\n"
            "    assert outer() == 1\n"
        ),
    })
    associations = {
        (names[link.implementation_key], link.rule)
        for link in result.links
    }
    assert associations == {
        ("outer", "direct_call"),
        ("inner", "two_hop_call"),
    }