"""Pure symbol mapping with independent AST-built extraction fixtures.

These fixtures construct ParsedFile DTOs without the production symbol parser;
parser/patch integration is tested separately in test_diff_symbol_integration.
"""
import ast
from dataclasses import replace
import hashlib
import difflib
import pytest
from pydantic import ValidationError

from reposcope.contracts.parsing import ParsedFile, ParsedSymbol, make_local_key
from reposcope.contracts.diff import DiffPatch, FileDiff, DiffHunk, DiffLine, LineRange, SymbolChange
from reposcope.impact.symbol_mapper import map_diff_to_symbols


def parsed(source, path="app.py"):
    raw = source.encode("utf-8")
    starts = [0] + [i + 1 for i, b in enumerate(raw) if b == 10]
    symbols = []
    def visit(node, parent=None):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "method" if parent and parent.kind == "class" else "function"
            qualname = parent.qualname + "." + node.name if parent else node.name
            start = starts[node.lineno - 1] + node.col_offset
            end = starts[node.end_lineno - 1] + node.end_col_offset
            content_line = min([node.lineno] + [d.lineno for d in node.decorator_list])
            content_start = starts[content_line - 1]
            symbol = ParsedSymbol(
                local_key=make_local_key(path, kind, qualname, start),
                parent_key=parent.local_key if parent else None, name=node.name, qualname=qualname, kind=kind,
                start_line=node.lineno, end_line=node.end_lineno,
                definition_start_byte=start, definition_end_byte=end,
                content_start_line=content_line, content_end_line=node.end_lineno,
                content_start_byte=content_start, content_end_byte=end,
                signature=None if kind == "class" else "independent fixture signature",
                docstring=None, parameters=[], is_async=isinstance(node, ast.AsyncFunctionDef),
                cyclomatic_complexity=None if kind == "class" else 1,
                complexity_policy=None if kind == "class" else "independent-fixture",
            )
            symbols.append(symbol); parent = symbol
        for child in ast.iter_child_nodes(node):
            visit(child, parent)
    visit(ast.parse(source))
    symbols.sort(key=lambda s:(s.definition_start_byte,s.definition_end_byte,s.local_key))
    digest = hashlib.sha256(raw).hexdigest()
    return ParsedFile(file_path=path, source_sha256=digest, parse_buffer_sha256=digest,
                      source_text=source, symbols=symbols)


def lines(text):
    parts = text.replace("\r\n", "\n").split("\n")
    return [p+"\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def patch(before, after, old_path="app.py", new_path="app.py"):
    old, new = lines(before or ""), lines(after or "")
    rows = []
    for op, a, b, c, d in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op == "equal":
            rows.extend(DiffLine(kind=" ", text=old[i], base_line=i+1, head_line=c+i-a+1) for i in range(a,b))
        else:
            rows.extend(DiffLine(kind="-", text=old[i], base_line=i+1) for i in range(a,b))
            rows.extend(DiffLine(kind="+", text=new[i], head_line=i+1) for i in range(c,d))
    status = "ADDED" if before is None else "REMOVED" if after is None else "RENAMED" if old_path != new_path else "MODIFIED"
    hunks = () if before == after else (DiffHunk(base_start=1 if old else 0,base_count=len(old),
        head_start=1 if new else 0,head_count=len(new),lines=tuple(rows)),)
    return DiffPatch(files=(FileDiff(base_path=old_path if before is not None else None,
        head_path=new_path if after is not None else None,status=status,hunks=hunks),))


def analyze(before, after, old_path="app.py", new_path="app.py"):
    return map_diff_to_symbols(patch(before,after,old_path,new_path),
        [parsed(before,old_path)] if before is not None else [],
        [parsed(after,new_path)] if after is not None else [])


def classifications(report):
    return [(c.classification,(c.head_symbol or c.base_symbol).qualname) for c in report.changes]


@pytest.mark.parametrize("before,after,expected", [
    (None,"def added():\n    pass\n",[("ADDED","added")]),
    ("def removed():\n    pass\n",None,[("REMOVED","removed")]),
    ("def f():\n    return 1\n","def f():\n    return 2\n",[("BODY_CHANGED","f")]),
    ("def f(x):\n    return x\n","def f(x,y=1):\n    return x+y\n",[("SIGNATURE_CHANGED","f")]),
    ("def f(x):\n    return x\n","def f(x: int) -> int:\n    return x\n",[("SIGNATURE_CHANGED","f")]),
    ("def f():\n    pass\n","async def f():\n    pass\n",[("SIGNATURE_CHANGED","f")]),
    ("def f():\n    pass\n","@decorator\ndef f():\n    pass\n",[("SIGNATURE_CHANGED","f")]),
    ("class C(Base):\n    pass\n","class C(Other):\n    pass\n",[("SIGNATURE_CHANGED","C")]),
    ("def old():\n    pass\n","def new():\n    pass\n",[("ADDED","new"),("REMOVED","old")]),
    ("def f():\n    pass\n","def f( ):\n    pass\n",[("BODY_CHANGED","f")]),
    ("def f():\n    'old docs'\n    pass\n","def f():\n    'new docs'\n    pass\n",[("BODY_CHANGED","f")]),
])
def test_classifications(before,after,expected):
    report=analyze(before,after)
    assert classifications(report)==expected
    assert not report.gaps


def test_insertion_only_maps_head_and_matches_base_identity():
    report=analyze("def f():\n    pass\n","def f():\n    x = 1\n    pass\n")
    change=report.changes[0]
    assert change.classification=="BODY_CHANGED"
    assert change.base_symbol is not None and change.head_symbol is not None
    assert change.base_changed_ranges==()
    assert [(r.start,r.end) for r in change.head_changed_ranges]==[(2,2)]


def test_deletion_only_preserves_head_counterpart():
    report=analyze("def f():\n    x = 1\n    pass\n","def f():\n    pass\n")
    change=report.changes[0]
    assert change.classification=="BODY_CHANGED" and change.head_symbol is not None
    assert change.head_changed_ranges==()


def test_unchanged_hunk_context_not_reported():
    report=analyze("def f():\n    return 1\n\ndef g():\n    return 2\n",
                   "def f():\n    return 1\n\ndef g():\n    return 3\n")
    assert classifications(report)==[("BODY_CHANGED","g")]


def test_shifted_unchanged_symbols_not_added_or_removed():
    report=analyze("def f():\n    return 1\n","# module comment\n\ndef f():\n    return 1\n")
    assert not report.changes
    assert any(g.code=="MODULE_LEVEL_CHANGE" for g in report.gaps)


def test_method_edit_does_not_redundantly_change_parent_class():
    report=analyze("class C:\n    def f(self):\n        return 1\n",
                   "class C:\n    def f(self):\n        return 2\n")
    assert classifications(report)==[("BODY_CHANGED","C.f")]


def test_nested_edit_owned_by_innermost_function():
    report=analyze("def outer():\n    def inner():\n        return 1\n    return inner()\n",
                   "def outer():\n    def inner():\n        return 2\n    return inner()\n")
    assert classifications(report)==[("BODY_CHANGED","outer.inner")]


def test_file_rename_with_body_edit_preserves_both_paths():
    report=analyze("def f():\n    return 1\n","def f():\n    return 2\n","old.py","new.py")
    assert classifications(report)==[("BODY_CHANGED","f")]
    assert report.changes[0].base_symbol.path=="old.py"
    assert report.changes[0].head_symbol.path=="new.py"


def test_pure_rename_reports_file_but_no_symbol_modification():
    source="def f():\n    pass\n"
    report=analyze(source,source,"old.py","new.py")
    assert report.patch.files[0].status=="RENAMED"
    assert not report.changes and not report.gaps


def test_duplicate_names_are_ambiguous_not_arbitrarily_paired():
    before="def f():\n    return 1\ndef f():\n    return 2\n"
    report=analyze(before,before.replace("return 2","return 3"))
    assert not report.changes
    assert any(g.code=="AMBIGUOUS_SYMBOL_IDENTITY" for g in report.gaps)


def test_same_method_name_different_classes_not_ambiguous():
    before="class A:\n    def f(self):\n        return 1\nclass B:\n    def f(self):\n        return 2\n"
    report=analyze(before,before.replace("return 2","return 3"))
    assert classifications(report)==[("BODY_CHANGED","B.f")]


def test_missing_source_is_gap_not_added_or_removed():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=map_diff_to_symbols(patch(before,after),[],[parsed(after)])
    assert not report.changes
    assert [(g.code,g.side) for g in report.gaps]==[("MISSING_SOURCE","base")]


def test_stale_or_incomplete_patch_does_not_classify():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=map_diff_to_symbols(patch(before,after),[parsed(before)],[parsed(after.replace("2","3"))])
    assert not report.changes
    assert report.gaps[0].code=="PATCH_SOURCE_MISMATCH"


def test_wrong_base_context_does_not_classify():
    before="def f():\n    return 1\n";after=before.replace("1","2")
    report=map_diff_to_symbols(patch(before,after),[parsed(before.replace("1","9"))],[parsed(after)])
    assert report.gaps[0].code=="PATCH_SOURCE_MISMATCH"


def test_unicode_names_and_no_trailing_newline():
    report=analyze("def café():\n    return 'é'","def café():\n    return 'à'")
    assert classifications(report)==[("BODY_CHANGED","café")]


def test_crlf_is_normalized_for_coordinate_validation():
    report=analyze("def f():\r\n    return 1\r\n","def f():\r\n    return 2\r\n")
    assert classifications(report)==[("BODY_CHANGED","f")]


def test_empty_file_addition_has_no_invented_symbols():
    report=analyze(None,"")
    assert not report.changes and not report.gaps


@pytest.mark.parametrize("kind",["binary","copy","non_python"])
def test_unsupported_entries_produce_explicit_gaps(kind):
    file=FileDiff(base_path="a.py",head_path="a.py",status="MODIFIED")
    if kind=="binary": file=file.model_copy(update={"binary":True})
    elif kind=="copy": file=file.model_copy(update={"status":"COPIED","head_path":"b.py"})
    else: file=FileDiff(base_path="README.md",head_path="README.md",status="MODIFIED")
    report=map_diff_to_symbols(DiffPatch(files=(file,)),[],[])
    assert len(report.gaps)==1 and not report.changes


def test_revision_labels_preserved_without_inventing_snapshot_ids():
    report=map_diff_to_symbols(DiffPatch(),[],[],base_revision="base-sha",head_revision="head-sha")
    assert report.base_revision=="base-sha" and report.head_revision=="head-sha"
    assert report.model_dump(mode="json")["changes"]==[]


def test_empty_patch_and_duplicate_inventory():
    assert not map_diff_to_symbols(DiffPatch(),[],[]).changes
    record=parsed("pass\n")
    with pytest.raises(ValueError,match="Duplicate"):
        map_diff_to_symbols(DiffPatch(),[record,record],[])


@pytest.mark.parametrize("path",["../x.py","/x.py","a\\b.py","a//b.py","C:/x.py"])
def test_unsafe_contract_paths_rejected(path):
    with pytest.raises(ValueError):
        FileDiff(base_path=None,head_path=path,status="ADDED")


def test_invalid_dto_ranges_and_classification_sides():
    with pytest.raises(ValueError): LineRange(start=2,end=1)
    with pytest.raises(ValueError): SymbolChange(classification="ADDED")
    with pytest.raises(ValueError): DiffLine(kind="+",text="x\n",base_line=1,head_line=1)
    with pytest.raises(ValueError): DiffHunk(base_start=1,base_count=1,head_start=1,head_count=0,lines=())


@pytest.mark.parametrize("flag",["symlink","submodule"])
def test_non_source_git_entries_are_not_parsed(flag):
    file=FileDiff(base_path="app.py",head_path="app.py",status="MODIFIED",**{flag:True})
    report=map_diff_to_symbols(DiffPatch(files=(file,)),[],[])
    assert report.gaps[0].code=="NON_SOURCE_ENTRY" and not report.changes


def test_unicode_line_separator_inside_string_is_not_a_git_line():
    before="def f():\n    return 'a\u2028b'\n";after=before.replace("a\u2028b","a\u2028c")
    report=analyze(before,after)
    assert classifications(report)==[("BODY_CHANGED","f")] and not report.gaps
