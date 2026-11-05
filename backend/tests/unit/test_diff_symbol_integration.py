"""Actual unidiff -> existing Tree-sitter parser -> side-aware mapper."""
import difflib
import pytest
from reposcope.impact.symbol_mapper import analyze_python_diff
from reposcope.impact.diff_parser import parse_unified_diff


def raw_patch(before,after,old_path="app.py",new_path="app.py",context=3):
    return "".join(difflib.unified_diff(
        (before or "").splitlines(keepends=True), (after or "").splitlines(keepends=True),
        fromfile="a/"+old_path if before is not None else "/dev/null",
        tofile="b/"+new_path if after is not None else "/dev/null", n=context))


def analyze(before,after,old_path="app.py",new_path="app.py",context=3):
    return analyze_python_diff(raw_patch(before,after,old_path,new_path,context),
        {old_path:before.encode()} if before is not None else {},
        {new_path:after.encode()} if after is not None else {})


@pytest.mark.parametrize("before,after,expected", [
    (None,"def f():\n    pass\n","ADDED"),
    ("def f():\n    pass\n",None,"REMOVED"),
    ("def f():\n    return 1\n","def f():\n    return 2\n","BODY_CHANGED"),
    ("def f(x=1):\n    return x\n","def f(x=2):\n    return x\n","SIGNATURE_CHANGED"),
    ("class C:\n    def f(self):\n        return 1\n","class C:\n    def f(self):\n        return 2\n","BODY_CHANGED"),
    ("def f():\n    pass\n","@decorator\ndef f():\n    pass\n","SIGNATURE_CHANGED"),
])
def test_real_parser_classification(before,after,expected):
    report=analyze(before,after)
    assert len(report.changes)==1
    assert report.changes[0].classification==expected
    assert not report.gaps
    assert report.model_dump(mode="json")["changes"][0]["classification"]==expected


def test_zero_context_insertion_at_beginning_not_added_function():
    before="def f():\n    pass\n";after="# comment\n"+before
    report=analyze(before,after,context=0)
    assert report.patch.files[0].status=="MODIFIED"
    assert not report.changes
    assert any(g.code=="MODULE_LEVEL_CHANGE" for g in report.gaps)


def test_multihunk_new_and_old_coordinates_after_line_shift():
    before="def first():\n    return 1\n"+"\n"*10+"def last():\n    return 2\n"
    after="def first():\n    extra = 1\n    return 1\n"+"\n"*10+"def last():\n    return 3\n"
    report=analyze(before,after,context=1)
    assert len(report.patch.files[0].hunks)==2
    assert {c.head_symbol.qualname for c in report.changes}=={"first","last"}
    last=next(c for c in report.changes if c.head_symbol.qualname=="last")
    assert last.head_symbol.start_line==last.base_symbol.start_line+1
    assert not report.gaps


def test_explicit_file_rename_and_changed_source():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=analyze(before,after,"old.py","new.py")
    change=report.changes[0]
    assert change.base_symbol.path=="old.py" and change.head_symbol.path=="new.py"
    assert change.classification=="BODY_CHANGED"


def test_invalid_source_has_gap_not_invented_removal():
    before="def f():\n    pass\n";after="def f(:\n    pass\n"
    report=analyze(before,after)
    assert not report.changes
    assert any(g.code=="SOURCE_PARSE_ERROR" for g in report.gaps)


def test_missing_source_version_has_gap():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=analyze_python_diff(raw_patch(before,after),{}, {"app.py":after.encode()})
    assert not report.changes and any(g.code=="MISSING_SOURCE" for g in report.gaps)


def test_no_newline_at_eof_patch_validates_both_versions():
    patch="--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n\\ No newline at end of file\n+    return 2\n\\ No newline at end of file\n"
    report=analyze_python_diff(patch,{"app.py":b"def f():\n    return 1"},{"app.py":b"def f():\n    return 2"})
    assert len(report.changes)==1 and report.changes[0].classification=="BODY_CHANGED"
    assert not report.gaps


def test_unicode_names_use_utf8_byte_offsets():
    before="def café(x):\n    return 'é'\n";after=before.replace("'é'","'à'")
    report=analyze(before,after)
    assert report.changes[0].head_symbol.qualname=="café"
    assert not report.gaps


def test_report_is_deterministic_and_does_not_mutate_input_sources():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    raw=raw_patch(before,after)
    old={"app.py":before.encode()};new={"app.py":after.encode()}
    a=analyze_python_diff(raw,old,new,base_revision="base",head_revision="head")
    b=analyze_python_diff(raw,old,new,base_revision="base",head_revision="head")
    assert a.model_dump(mode="json")==b.model_dump(mode="json")
    assert old["app.py"]==before.encode() and new["app.py"]==after.encode()


def test_utf8_bom_in_patch_and_original_source():
    before="def f():\n    return 1\n";after="def f(x=1):\n    return x\n"
    raw=raw_patch("\ufeff"+before,"\ufeff"+after)
    report=analyze_python_diff(raw,{"app.py":b"\xef\xbb\xbf"+before.encode()},
        {"app.py":b"\xef\xbb\xbf"+after.encode()})
    assert report.changes[0].classification=="SIGNATURE_CHANGED" and not report.gaps


def test_source_budget_reports_gap_instead_of_partial_classification():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=analyze_python_diff(raw_patch(before,after),{"app.py":before.encode()},
        {"app.py":after.encode()},max_source_bytes=1)
    assert not report.changes
    assert any(g.code=="SOURCE_BUDGET_EXCEEDED" for g in report.gaps)
