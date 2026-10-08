from reposcope.ingestion.scanner import (
    detect_extension,
    detect_language,
    hash_content,
    scan_repository,
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


def test_scan_repository(tmp_path):
    main_content = b"def hello(): pass\n"
    utils_content = b"class Util: pass\n"

    # Write exact bytes so the fixture is identical across platforms.
    (tmp_path / "main.py").write_bytes(main_content)
    (tmp_path / "utils.py").write_bytes(utils_content)
    (tmp_path / "ignore.bin").write_bytes(b"\x00\x01\x02")

    files = scan_repository(tmp_path)
    paths = [file.relative_path for file in files]

    assert len(files) == 2
    assert paths == ["main.py", "utils.py"]

    main_file = files[0]
    assert main_file.extension == ".py"
    assert main_file.content_hash == hash_content(main_content)
    assert main_file.size_bytes == len(main_content)

    utils_file = files[1]
    assert utils_file.extension == ".py"
    assert utils_file.content_hash == hash_content(utils_content)
    assert utils_file.size_bytes == len(utils_content)