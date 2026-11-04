from reposcope.contracts.resolution import make_module_key
from reposcope.parsing.detectors import detect_routes
from reposcope.parsing.python_parser import parse_python


def detect(source):
    parsed = parse_python(
        source.encode("utf-8"),
        file_path="api.py",
    )
    result = detect_routes(
        parsed,
        module_key=make_module_key(".", "api.py"),
    )
    return parsed, result


def test_fastapi_alias_and_async_handler():
    parsed, result = detect(
        'from fastapi import FastAPI as API\n'
        'app = API()\n'
        '@app.get("/users")\n'
        'async def list_users():\n'
        '    return []\n'
    )

    assert len(result.endpoints) == 1

    endpoint = result.endpoints[0]

    assert endpoint.framework == "fastapi"
    assert endpoint.receiver == "app"
    assert endpoint.method == "GET"
    assert endpoint.path == "/users"
    assert endpoint.handler_key == parsed.symbols[0].local_key

    assert [edge.kind for edge in result.edges] == [
        "EXPOSES",
        "CALLS",
    ]

    assert result.edges[0].source_key == make_module_key(".", "api.py")
    assert result.edges[0].target_key == endpoint.key

    assert result.edges[1].source_key == endpoint.key
    assert result.edges[1].target_key == endpoint.handler_key

    assert result.gaps == ()


def test_flask_multiple_explicit_methods():
    _, result = detect(
        'from flask import Flask\n'
        'app = Flask(__name__)\n'
        '@app.route("/users", methods=["POST", "GET"])\n'
        'def users():\n'
        '    return "ok"\n'
    )

    assert [endpoint.method for endpoint in result.endpoints] == [
        "GET",
        "POST",
    ]

    assert all(
        endpoint.framework == "flask"
        for endpoint in result.endpoints
    )
    assert all(
        endpoint.path == "/users"
        for endpoint in result.endpoints
    )

    assert len(result.edges) == 4
    assert len({endpoint.key for endpoint in result.endpoints}) == 2
    assert result.gaps == ()


def test_unrelated_receiver_does_not_emit_routes():
    _, result = detect(
        'app = object()\n'
        '@app.get("/users")\n'
        'def users():\n'
        '    return []\n'
    )

    assert result.endpoints == ()
    assert result.edges == ()


def test_reassigned_receiver_does_not_emit_routes():
    _, result = detect(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n'
        'app = object()\n'
        '@app.get("/users")\n'
        'def users():\n'
        '    return []\n'
    )

    assert result.endpoints == ()
    assert result.edges == ()


def test_dynamic_path_produces_gap():
    _, result = detect(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n'
        'PATH = "/users"\n'
        '@app.get(PATH)\n'
        'def users():\n'
        '    return []\n'
    )

    assert result.endpoints == ()
    assert result.edges == ()
    assert len(result.gaps) == 1
    assert result.gaps[0].rule_id == "routes.unsupported"


def test_unicode_evidence_matches_source_bytes():
    parsed, result = detect(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n'
        '@app.get("/café")\n'
        'def users():\n'
        '    return []\n'
    )

    assert len(result.endpoints) == 1

    endpoint = result.endpoints[0]
    evidence = endpoint.evidence
    buffer = parsed.source_text.encode("utf-8")

    assert endpoint.path == "/café"
    assert (
        buffer[evidence.start_byte:evidence.end_byte].decode("utf-8")
        == evidence.expression
    )
    assert evidence.expression == 'app.get("/café")'


def test_import_alias_shadowing_does_not_emit_routes():
    _, result = detect(
        'from fastapi import FastAPI\n'
        'FastAPI = other_factory\n'
        'app = FastAPI()\n'
        '@app.get("/users")\n'
        'def users():\n'
        '    return []\n'
    )

    assert result.endpoints == ()
    assert result.edges == ()