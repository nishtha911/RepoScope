from reposcope.ingestion.scanner import (
    detect_extension,
    detect_language,
    hash_content,
)


def test_extension_detection():
    assert detect_extension("src/service.PY") == ".py"
    assert detect_extension("src/App.tsx") == ".tsx"
    assert detect_extension("README") == ""


def test_language_detection():
    assert detect_language("service.py") == "python"
    assert detect_language("App.tsx") == "typescript"
    assert detect_language("data.xyz") == "unknown"


def test_sha256_known_value():
    assert hash_content(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e"
        "1b161e5c1fa7425e73043362938b9824"
    )


def test_hash_changes_when_content_changes():
    assert hash_content(b"hello") != hash_content(b"Hello")