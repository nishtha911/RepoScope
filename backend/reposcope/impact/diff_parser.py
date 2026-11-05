"""Read unified diffs with unidiff. Never apply patches or access the filesystem."""
from reposcope.contracts.diff import DiffHunk, DiffLine, DiffPatch, FileDiff, validate_path


class DiffParseError(ValueError):
    pass


def _decoded_path(value):
    # New unidiff releases decode Git quoting. Retain a safe fallback for a
    # source_file/target_file that is still C-quoted (including UTF-8 octal).
    if not isinstance(value, str) or not value:
        raise DiffParseError("Diff entry lacks a valid filename")
    if not value.startswith('"'):
        return value
    if not value.endswith('"'):
        raise DiffParseError("Unterminated quoted filename")
    raw, index, result = value[1:-1], 0, bytearray()
    escapes = {"n":10, "r":13, "t":9, "b":8, "f":12, "v":11, "a":7, '"':34, "\\":92}
    while index < len(raw):
        char = raw[index]
        if char != "\\":
            result.extend(char.encode("utf-8")); index += 1
            continue
        index += 1
        if index == len(raw):
            raise DiffParseError("Invalid filename escape")
        char = raw[index]
        if char in "01234567":
            digits = raw[index:index + 3]
            if len(digits) != 3 or any(c not in "01234567" for c in digits) or int(digits, 8) > 255:
                raise DiffParseError("Invalid filename octal escape")
            result.append(int(digits, 8)); index += 3
        elif char in escapes:
            result.append(escapes[char]); index += 1
        else:
            raise DiffParseError("Unsupported filename escape")
    try:
        return result.decode("utf-8")
    except UnicodeDecodeError:
        raise DiffParseError("Filename is not valid UTF-8") from None


def parse_unified_diff(text, *, max_bytes=5_000_000, max_files=1000, max_lines=200000):
    """Return validated side-specific coordinates and original patch-line text.

    Supports ordinary unified and git unified diffs. Combined merge diffs are
    rejected. Binary, copy and metadata-only entries are retained for explicit
    downstream handling, not silently interpreted as changed source lines.
    Empty/whitespace-only input is an empty patch. No path is opened on disk.
    """
    if not isinstance(text, str):
        raise TypeError("Patch must be decoded UTF-8 text")
    for name, value in (("max_bytes", max_bytes), ("max_files", max_files), ("max_lines", max_lines)):
        if type(value) is not int or value < 1:
            raise ValueError(name + " must be a positive integer")
    if "\0" in text:
        raise DiffParseError("Patch contains a NUL byte")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise DiffParseError("Patch is not valid Unicode text") from None
    if size > max_bytes or text.count("\n") + 1 > max_lines:
        raise DiffParseError("Patch exceeds its input budget")
    if not text.strip():
        return DiffPatch()
    if any(line.startswith(("diff --cc ", "diff --combined ", "@@@")) for line in text.split("\n")):
        raise DiffParseError("Combined merge diffs are not supported")
    from unidiff import PatchSet
    from unidiff.errors import UnidiffParseError
    try:
        parsed = PatchSet(text)
        if not parsed:
            raise DiffParseError("Input contains no supported file diff")
        if len(parsed) > max_files:
            raise DiffParseError("Patch exceeds max_files")
        files = []
        for file in parsed:
            info = str(file.patch_info or "")
            base = _decoded_path(file.source_file)
            head = _decoded_path(file.target_file)
            new_file = base == "/dev/null" or any(l.startswith("new file mode ") for l in info.splitlines())
            removed_file = head == "/dev/null" or any(l.startswith("deleted file mode ") for l in info.splitlines())
            git_style = (info.startswith("diff --git ") or
                         (base.startswith("a/") and head.startswith("b/")) or
                         (base == "/dev/null" and head.startswith("b/")) or
                         (head == "/dev/null" and base.startswith("a/")))
            if git_style:
                base = base[2:] if base.startswith("a/") else base
                head = head[2:] if head.startswith("b/") else head
            base = None if base == "/dev/null" or new_file else validate_path(base)
            head = None if head == "/dev/null" or removed_file else validate_path(head)
            copied = any(l.startswith("copy from ") for l in info.splitlines())
            status = ("ADDED" if base is None else "REMOVED" if head is None else
                      "COPIED" if copied else "RENAMED" if base != head else "MODIFIED")
            hunks = []
            for hunk in file:
                lines = []
                for row in hunk:
                    if row.line_type == "" and row.value in {"\n", "\r\n"}:
                        continue
                    if row.line_type == "\\":
                        if not lines or lines[-1].no_newline:
                            raise DiffParseError("Unattached or duplicate no-newline marker")
                        lines[-1] = lines[-1].model_copy(update={"no_newline": True})
                        continue
                    if row.line_type not in {" ", "+", "-"}:
                        raise DiffParseError("Unsupported hunk line type")
                    lines.append(DiffLine(kind=row.line_type, text=row.value,
                        base_line=row.source_line_no, head_line=row.target_line_no))
                hunks.append(DiffHunk(base_start=hunk.source_start, base_count=hunk.source_length,
                    head_start=hunk.target_start, head_count=hunk.target_length, lines=tuple(lines)))
            files.append(FileDiff(base_path=base, head_path=head, status=status,
                binary=bool(file.is_binary_file), symlink=bool(getattr(file, "is_symlink", False)),
                submodule=bool(getattr(file, "is_submodule", False)), hunks=tuple(hunks)))
        return DiffPatch(files=tuple(files))
    except (UnidiffParseError, ValueError, IndexError, TypeError) as exc:
        if isinstance(exc, DiffParseError):
            raise
        raise DiffParseError("Malformed, unsafe or unsupported unified diff") from exc
