"""Conservative changed-line -> base/head Python symbol mapping.

Inputs are complete parser records for both versions, never DB rows from one
snapshot reused for both. Exact patch/source agreement is verified before any
classification. No repository code is executed. No DB/network/file writes.
"""
import ast
import copy
from collections import defaultdict

from reposcope.contracts.diff import (
    DiffPatch, LineSymbolMapping, MappingGap, SymbolChange, SymbolDiffReport,
    SymbolVersion, ranges,
)
from reposcope.contracts.parsing import ParsedFile


def _files(records):
    result = {}
    for value in records:
        if not isinstance(value, ParsedFile):
            raise TypeError("Pass ParsedFile records")
        owned = ParsedFile.model_validate(value.model_dump())
        if owned.file_path in result:
            raise ValueError("Duplicate parser inventory path")
        result[owned.file_path] = owned
    return result


def _normalized(text):
    return text.replace("\r\n", "\n")


def _line_text(row):
    text = _normalized(row.text)
    first_line = row.base_line == 1 if row.kind == "-" else row.head_line == 1
    if first_line:
        text = text.removeprefix("\ufeff")
    if row.no_newline and text.endswith("\n"):
        return text[:-1]
    return text


def _lines(text):
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _verify(file, base, head):
    old = _lines(_normalized(base.source_text if base is not None else ""))
    expected = _normalized(head.source_text if head is not None else "")
    output, cursor = [], 0
    for hunk in file.hunks:
        old_pos = hunk.base_start - 1 if hunk.base_count else hunk.base_start
        new_pos = hunk.head_start - 1 if hunk.head_count else hunk.head_start
        if old_pos < cursor or old_pos > len(old):
            raise ValueError("Hunk base coordinate is outside source or overlaps")
        output.extend(old[cursor:old_pos])
        if len(output) != new_pos:
            raise ValueError("Hunk head coordinate disagrees with preceding edits")
        cursor = old_pos
        for row in hunk.lines:
            content = _line_text(row)
            if row.kind != "+":
                if cursor >= len(old) or old[cursor] != content:
                    raise ValueError("Patch context/deletion does not match base source")
                cursor += 1
            if row.kind != "-":
                output.append(content)
    output.extend(old[cursor:])
    if "".join(output) != expected:
        raise ValueError("Applying the complete patch does not reproduce head source")


def _nodes(parsed):
    tree = ast.parse(parsed.source_text, filename=parsed.file_path)
    raw = parsed.source_text.encode("utf-8")
    starts = [0] + [i + 1 for i, b in enumerate(raw) if b == 10]
    nodes = {}
    def visit(node, parent=None, prefix=""):
        named = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        if named:
            kind = "class" if isinstance(node, ast.ClassDef) else "method" if isinstance(parent, ast.ClassDef) else "function"
            qualname = prefix + node.name
            key = (starts[node.lineno - 1] + node.col_offset, kind, qualname)
            nodes[key] = node
            parent, prefix = node, qualname + "."
        for child in ast.iter_child_nodes(node):
            visit(child, parent, prefix)
    visit(tree)
    result = {}
    for symbol in parsed.symbols:
        key = (symbol.definition_start_byte, symbol.kind, symbol.qualname)
        node = nodes.get(key)
        if node is None or node.name != symbol.name:
            raise ValueError("Parser symbol does not match AST identity")
        result[symbol.local_key] = node
    if len(result) != len(nodes):
        raise ValueError("Parser inventory omits or duplicates AST definitions")
    return result


def _signature(node):
    header = copy.deepcopy(node)
    header.body = []
    return ast.dump(header, include_attributes=False)


def _content(parsed, symbol):
    return _normalized(parsed.source_text.encode("utf-8")[
        symbol.content_start_byte:symbol.content_end_byte].decode("utf-8"))


def _version(parsed, symbol):
    return SymbolVersion(path=parsed.file_path, **{
        k: getattr(symbol, k) for k in ("local_key", "name", "qualname", "kind",
            "start_line", "end_line", "content_start_line", "content_end_line")})


def _ownership(parsed, changed_ranges, side):
    mappings, owned, gaps = [], defaultdict(set), []
    for span in changed_ranges:
        keys, unmapped = set(), []
        for line in range(span.start, span.end + 1):
            candidates = [s for s in parsed.symbols if s.content_start_line <= line <= s.content_end_line]
            if not candidates:
                unmapped.append(line)
                continue
            width = min(s.content_end_byte - s.content_start_byte for s in candidates)
            nearest = [s for s in candidates if s.content_end_byte - s.content_start_byte == width]
            if len(nearest) != 1:
                gaps.append(MappingGap(code="AMBIGUOUS_LINE_OWNER", path=parsed.file_path,
                    side=side, detail="More than one equally narrow symbol owns this line", lines=ranges([line])))
                continue
            key = nearest[0].local_key
            keys.add(key); owned[key].add(line)
        mappings.append(LineSymbolMapping(path=parsed.file_path, side=side,
            changed_range=span, symbol_keys=tuple(sorted(keys)), unmapped_lines=tuple(unmapped)))
        if unmapped:
            gaps.append(MappingGap(code="MODULE_LEVEL_CHANGE", path=parsed.file_path, side=side,
                detail="Changed lines are outside extracted definitions; no function/class identity invented",
                lines=ranges(unmapped)))
    return mappings, owned, gaps


def map_diff_to_symbols(patch, base_files, head_files, *, base_revision=None, head_revision=None):
    """Pair unique (kind, qualname) identities within each file pair.

    Renamed files pair through explicit diff paths. Renamed functions/moves
    between files are conservative REMOVED+ADDED, not guessed identity matches.
    Innermost ownership avoids reporting ancestor classes for every method edit.
    SIGNATURE_CHANGED takes precedence over BODY_CHANGED. Body classification
    means textual definition/decorator content changed with a stable structural
    header; it can include comments/formatting and is not a runtime claim.
    """
    if not isinstance(patch, DiffPatch):
        raise TypeError("Pass a DiffPatch")
    patch = DiffPatch.model_validate(patch.model_dump())
    base_files, head_files = _files(base_files), _files(head_files)
    changes, mappings, gaps = [], [], []
    for file in patch.files:
        path = file.head_path or file.base_path
        if file.binary:
            gaps.append(MappingGap(code="BINARY_FILE", path=path, detail="Binary payload is not Python source"))
            continue
        if file.symlink or file.submodule:
            gaps.append(MappingGap(code="NON_SOURCE_ENTRY", path=path, detail="Symlink/submodule entry is not ordinary Python source"))
            continue
        if file.status == "COPIED":
            gaps.append(MappingGap(code="COPY_UNSUPPORTED", path=path, detail="Copy identity is not inferred as a rename"))
            continue
        if any(p is not None and not p.endswith(".py") for p in (file.base_path, file.head_path)):
            gaps.append(MappingGap(code="UNSUPPORTED_FILE_TYPE", path=path, detail="Symbol mapping currently supports Python files only"))
            continue
        old = base_files.get(file.base_path)
        new = head_files.get(file.head_path)
        missing = False
        for side, filename, parsed in (("base", file.base_path, old), ("head", file.head_path, new)):
            if filename is not None and parsed is None:
                missing = True
                gaps.append(MappingGap(code="MISSING_SOURCE", path=filename, side=side,
                    detail="Complete parser/source record for this version is required"))
        if missing:
            continue
        try:
            _verify(file, old, new)
        except ValueError as exc:
            gaps.append(MappingGap(code="PATCH_SOURCE_MISMATCH", path=path, detail=str(exc)))
            continue
        try:
            old_nodes = _nodes(old) if old else {}
            new_nodes = _nodes(new) if new else {}
        except (SyntaxError, ValueError, RecursionError) as exc:
            gaps.append(MappingGap(code="INVALID_SYMBOL_INVENTORY", path=path,
                detail="AST/source inventory cannot be verified: " + str(exc)))
            continue
        old_owned, new_owned = {}, {}
        for side, parsed, spans in (("base", old, file.base_ranges), ("head", new, file.head_ranges)):
            if parsed is not None:
                mapped, owned, extra = _ownership(parsed, spans, side)
                mappings.extend(mapped); gaps.extend(extra)
                if side == "base": old_owned = owned
                else: new_owned = owned
        old_groups, new_groups = defaultdict(list), defaultdict(list)
        for parsed, groups in ((old, old_groups), (new, new_groups)):
            if parsed is not None:
                for symbol in parsed.symbols:
                    groups[(symbol.kind, symbol.qualname)].append(symbol)
        for identity in sorted(set(old_groups) | set(new_groups)):
            old_group, new_group = old_groups[identity], new_groups[identity]
            if not any(s.local_key in old_owned for s in old_group) and not any(s.local_key in new_owned for s in new_group):
                continue
            if len(old_group) > 1 or len(new_group) > 1:
                gaps.append(MappingGap(code="AMBIGUOUS_SYMBOL_IDENTITY", path=path,
                    detail="Duplicate kind/qualified-name definitions cannot be paired uniquely: " + identity[1]))
                continue
            before = old_group[0] if old_group else None
            after = new_group[0] if new_group else None
            if before is None:
                classification = "ADDED"
            elif after is None:
                classification = "REMOVED"
            elif _signature(old_nodes[before.local_key]) != _signature(new_nodes[after.local_key]):
                classification = "SIGNATURE_CHANGED"
            elif _content(old, before) != _content(new, after):
                classification = "BODY_CHANGED"
            else:
                continue
            changes.append(SymbolChange(classification=classification,
                base_symbol=_version(old, before) if before else None,
                head_symbol=_version(new, after) if after else None,
                base_changed_ranges=ranges(old_owned.get(before.local_key, ())) if before else (),
                head_changed_ranges=ranges(new_owned.get(after.local_key, ())) if after else ()))
    changes.sort(key=lambda c: ((c.head_symbol or c.base_symbol).path,
        (c.head_symbol or c.base_symbol).qualname, c.classification,
        (c.head_symbol or c.base_symbol).start_line))
    return SymbolDiffReport(patch=patch, changes=tuple(changes), line_mappings=tuple(mappings),
        gaps=tuple(gaps), base_revision=base_revision, head_revision=head_revision)


def analyze_python_diff(patch_text, base_sources, head_sources, *, base_revision=None, head_revision=None,
                        max_source_bytes=2_000_000, max_total_source_bytes=20_000_000):
    """Convenience adapter: raw patch + complete raw source bytes per side.

    Parses only Python paths mentioned by the patch. Missing/invalid source is
    reported as a gap rather than pretending a missing parse means deletion.
    Does not fetch base/head versions or connect to a database.
    """
    from collections.abc import Mapping
    from reposcope.impact.diff_parser import parse_unified_diff
    from reposcope.parsing.python_parser import parse_python, PythonParserError
    for name, value in (("max_source_bytes", max_source_bytes), ("max_total_source_bytes", max_total_source_bytes)):
        if type(value) is not int or value < 1:
            raise ValueError(name + " must be a positive integer")
    patch = parse_unified_diff(patch_text)
    parsed_sides, parse_gaps, used_bytes = [], [], 0
    for side, sources in (("base", base_sources), ("head", head_sources)):
        if not isinstance(sources, Mapping):
            raise TypeError("Source inventories must map paths to bytes")
        paths = {getattr(f, side + "_path") for f in patch.files if not f.binary and not f.symlink and not f.submodule and f.status != "COPIED"}
        parsed = []
        for path in sorted(p for p in paths if p is not None and p.endswith(".py")):
            if path not in sources:
                continue
            if not isinstance(sources[path], bytes):
                raise TypeError("Source values must be raw bytes")
            if len(sources[path]) > max_source_bytes or used_bytes + len(sources[path]) > max_total_source_bytes:
                parse_gaps.append(MappingGap(code="SOURCE_BUDGET_EXCEEDED", path=path, side=side,
                    detail="Complete source omitted because an explicit source-byte budget was exceeded"))
                continue
            used_bytes += len(sources[path])
            try:
                parsed.append(parse_python(sources[path], file_path=path))
            except PythonParserError:
                parse_gaps.append(MappingGap(code="SOURCE_PARSE_ERROR", path=path, side=side,
                    detail="Source version cannot be parsed under the supported Python policy"))
        parsed_sides.append(parsed)
    report = map_diff_to_symbols(patch, *parsed_sides, base_revision=base_revision, head_revision=head_revision)
    return report.model_copy(update={"gaps": report.gaps + tuple(parse_gaps)})
