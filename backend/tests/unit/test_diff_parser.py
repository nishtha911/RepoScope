import pytest
from reposcope.impact.diff_parser import parse_unified_diff, DiffParseError, _decoded_path

PATCH = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def f():
-    return 1
+    return 2
"""


def test_modified_file_side_coordinates():
    patch=parse_unified_diff(PATCH)
    file=patch.files[0]
    assert file.status=="MODIFIED" and file.base_path==file.head_path=="app.py"
    assert [(r.start,r.end) for r in file.base_ranges]==[(2,2)]
    assert [(r.start,r.end) for r in file.head_ranges]==[(2,2)]
    removed,added=file.hunks[0].lines[1:]
    assert removed.base_line==2 and removed.head_line is None
    assert added.head_line==2 and added.base_line is None


def test_added_and_removed_files():
    added="--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+def f():\n+    pass\n"
    deleted="--- a/old.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def f():\n-    pass\n"
    patch=parse_unified_diff(added+deleted)
    assert [f.status for f in patch.files]==["ADDED","REMOVED"]
    assert patch.files[0].base_path is None and patch.files[1].head_path is None


def test_zero_context_insertion_is_not_file_addition():
    raw="--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+# new comment\n"
    assert parse_unified_diff(raw).files[0].status=="MODIFIED"


def test_zero_context_deletion_is_not_file_removal():
    raw="--- a/app.py\n+++ b/app.py\n@@ -1 +0,0 @@\n-# removed comment\n"
    assert parse_unified_diff(raw).files[0].status=="MODIFIED"


def test_multiple_hunks_keep_separate_line_ranges():
    raw="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-a\n+b\n@@ -10 +10 @@\n-c\n+d\n"
    file=parse_unified_diff(raw).files[0]
    assert len(file.hunks)==2
    assert [(r.start,r.end) for r in file.base_ranges]==[(1,1),(10,10)]


def test_no_newline_markers_belong_to_previous_side():
    raw="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n"
    rows=parse_unified_diff(raw).files[0].hunks[0].lines
    assert len(rows)==2 and all(r.no_newline for r in rows)


def test_plain_headers_and_timestamp():
    raw="--- app.py\t2026-01-01\n+++ app.py\t2026-01-02\n@@ -1 +1 @@\n-a\n+b\n"
    file=parse_unified_diff(raw).files[0]
    assert file.base_path==file.head_path=="app.py"


def test_plain_a_directory_is_not_blindly_stripped():
    raw="--- a/file.py\n+++ a/file.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert parse_unified_diff(raw).files[0].base_path=="a/file.py"


def test_rename_only_retained_without_inventing_line_edits():
    raw="diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
    file=parse_unified_diff(raw).files[0]
    assert file.status=="RENAMED" and not file.hunks
    assert file.base_path=="old.py" and file.head_path=="new.py"


def test_binary_diff_retained_as_binary():
    raw="diff --git a/image.png b/image.png\nindex 1234567..7654321 100644\nBinary files a/image.png and b/image.png differ\n"
    file=parse_unified_diff(raw).files[0]
    assert file.binary and not file.hunks


def test_mode_only_retained():
    raw="diff --git a/app.py b/app.py\nold mode 100644\nnew mode 100755\n"
    file=parse_unified_diff(raw).files[0]
    assert file.status=="MODIFIED" and not file.hunks


def test_empty_added_file_metadata():
    raw="diff --git a/empty.py b/empty.py\nnew file mode 100644\nindex 0000000..e69de29\n"
    file=parse_unified_diff(raw).files[0]
    assert file.status=="ADDED" and file.base_path is None and not file.hunks


def test_spaces_in_git_paths():
    raw="diff --git a/my file.py b/my file.py\n--- a/my file.py\n+++ b/my file.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert parse_unified_diff(raw).files[0].head_path=="my file.py"


def test_git_quoted_filename():
    raw='diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n--- "a/caf\\303\\251.py"\n+++ "b/caf\\303\\251.py"\n@@ -1 +1 @@\n-a\n+b\n'
    assert parse_unified_diff(raw).files[0].head_path=="café.py"


@pytest.mark.parametrize("path",["../bad.py","/absolute.py","C:/bad.py"])
def test_unsafe_paths_rejected(path):
    raw=f"--- {path}\n+++ {path}\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(DiffParseError):parse_unified_diff(raw)


def test_duplicate_file_entries_rejected():
    with pytest.raises(DiffParseError):parse_unified_diff(PATCH+PATCH)


def test_truncated_hunk_rejected():
    with pytest.raises(DiffParseError):parse_unified_diff("--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n-x\n+y\n")


def test_max_files_rejected():
    second=PATCH.replace("app.py","other.py")
    with pytest.raises(DiffParseError):parse_unified_diff(PATCH+second,max_files=1)


@pytest.mark.parametrize("raw",["diff --cc app.py\n", "diff --combined app.py\n", "@@@ -1 -1 +1 @@@\n", "bad\0patch"])
def test_preflight_invalid_patch_forms(raw):
    with pytest.raises(DiffParseError):parse_unified_diff(raw)


def test_preflight_budgets_and_empty_input():
    assert not parse_unified_diff("").files
    with pytest.raises(DiffParseError):parse_unified_diff(PATCH,max_bytes=1)
    with pytest.raises(DiffParseError):parse_unified_diff(PATCH,max_lines=1)
    with pytest.raises(TypeError):parse_unified_diff(b"bytes")
    with pytest.raises(ValueError):parse_unified_diff("",max_files=True)


def test_path_decoder_utf8_octal_and_escaping():
    assert _decoded_path('"a/caf\\303\\251.py"')=="a/café.py"
    assert _decoded_path('"a/space\\tname.py"')=="a/space\tname.py"
    assert _decoded_path("a/plain.py")=="a/plain.py"
    with pytest.raises(DiffParseError):_decoded_path('"unfinished')
