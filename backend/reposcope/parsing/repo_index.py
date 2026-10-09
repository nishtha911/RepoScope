"""Repository indexing for the two-pass Python resolver.

Stage 1:
- Validate configured source roots.
- Own validated copies of ParsedFile records.
- Build module and definition lookup maps.
- Preserve duplicate importable module-name candidates.

Lexical scopes and binding collection are added in the next stage.
"""

import hashlib
import keyword
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping

from pydantic import ValidationError

from reposcope.contracts.parsing import (
    ParsedFile,
    ParsedSymbol,
    make_local_key,
)
from reposcope.contracts.resolution import (
    ModuleInfo,
    ResolverTarget,
    make_module_key,
)


class RepoIndexError(ValueError):
    """Explicit repository-index validation failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        file_path: str | None = None,
    ) -> None:
        self.code = code
        self.file_path = file_path

        location = f" [{file_path}]" if file_path is not None else ""
        super().__init__(f"{code}{location}: {message}")


@dataclass(frozen=True)
class RepoIndex:
    """Owned parser records and read-only lookup mappings.

    The containers are read-only. Contained Pydantic records remain
    mutable and must be treated as read-only by consumers.
    """

    source_roots: tuple[str, ...]
    files_by_path: Mapping[str, ParsedFile]
    modules_by_path: Mapping[str, ModuleInfo]
    modules_by_key: Mapping[str, ModuleInfo]
    modules_by_name: Mapping[str, tuple[ModuleInfo, ...]]
    definitions_by_local_key: Mapping[str, ParsedSymbol]

    def module_candidates(
        self,
        module_name: str,
    ) -> tuple[ModuleInfo, ...]:
        return self.modules_by_name.get(module_name, ())

    def module_for_file(self, file_path: str) -> ModuleInfo:
        module = self.modules_by_path.get(file_path)

        if module is None:
            raise RepoIndexError(
                "UNKNOWN_FILE",
                "file is not present in the repository index",
                file_path=file_path,
            )

        return module

    def module_target(self, file_path: str) -> ResolverTarget:
        module = self.module_for_file(file_path)

        return ResolverTarget(
            target_kind="module",
            module_key=module.module_key,
            file_path=module.file_path,
            symbol_key=None,
        )

    def validate_target(
        self,
        target: ResolverTarget,
    ) -> ModuleInfo | ParsedSymbol:
        """Check target membership, not lookup or import semantics."""
        try:
            checked = ResolverTarget.model_validate(
                target.model_dump()
            )
        except ValidationError as exc:
            raise RepoIndexError(
                "INVALID_TARGET",
                str(exc),
            ) from exc

        module = self.modules_by_key.get(checked.module_key)

        if module is None:
            raise RepoIndexError(
                "UNKNOWN_TARGET_MODULE",
                "target module is not present in the index",
                file_path=checked.file_path,
            )

        if module.file_path != checked.file_path:
            raise RepoIndexError(
                "TARGET_FILE_MISMATCH",
                "target does not belong to its indexed module",
                file_path=checked.file_path,
            )

        if checked.target_kind == "module":
            return module

        definition = self.definitions_by_local_key.get(
            checked.symbol_key
        )

        if definition is None:
            raise RepoIndexError(
                "UNKNOWN_TARGET_SYMBOL",
                "target definition is not present in the index",
                file_path=checked.file_path,
            )

        return definition


def _validate_source_roots(
    source_roots: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(source_roots, tuple) or not source_roots:
        raise RepoIndexError(
            "INVALID_SOURCE_ROOTS",
            "source_roots must be a nonempty tuple",
        )

    for root in source_roots:
        if not isinstance(root, str) or not root.strip():
            raise RepoIndexError(
                "INVALID_SOURCE_ROOT",
                "each source root must be a nonblank string",
            )

        if root == ".":
            continue

        parts = root.split("/")

        if (
            root.startswith("/")
            or "\\" in root
            or "\x00" in root
            or any(part in ("", ".", "..") for part in parts)
            or ":" in parts[0]
        ):
            raise RepoIndexError(
                "INVALID_SOURCE_ROOT",
                f"source root is not a canonical relative path: {root!r}",
            )

    if len(set(source_roots)) != len(source_roots):
        raise RepoIndexError(
            "DUPLICATE_SOURCE_ROOT",
            "configured source roots must be unique",
        )

    paths = [PurePosixPath(root) for root in source_roots]

    for position, first in enumerate(paths):
        for second in paths[position + 1:]:
            if first in second.parents or second in first.parents:
                raise RepoIndexError(
                    "OVERLAPPING_SOURCE_ROOTS",
                    f"source roots overlap: {str(first)!r}, "
                    f"{str(second)!r}",
                )

    return tuple(sorted(source_roots))


def _source_root_for(
    file_path: str,
    source_roots: tuple[str, ...],
) -> str:
    path = PurePosixPath(file_path)

    for root in source_roots:
        try:
            path.relative_to(PurePosixPath(root))
        except ValueError:
            continue

        return root

    raise RepoIndexError(
        "FILE_OUTSIDE_SOURCE_ROOTS",
        "file does not belong to any configured source root",
        file_path=file_path,
    )


def _module_name_for(
    file_path: str,
    source_root: str,
) -> str | None:
    relative = PurePosixPath(file_path).relative_to(
        PurePosixPath(source_root)
    )
    parts = list(relative.parts)

    if relative.suffix != ".py":
        raise RepoIndexError(
            "UNSUPPORTED_MODULE_FILE",
            "Python module records must identify .py files",
            file_path=file_path,
        )

    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = relative.stem

    if not parts or not all(
        part.isidentifier() and not keyword.iskeyword(part)
        for part in parts
    ):
        return None

    return ".".join(parts)


def _copy_and_validate_file(parsed_file: ParsedFile) -> ParsedFile:
    if not isinstance(parsed_file, ParsedFile):
        raise RepoIndexError(
            "INVALID_PARSED_FILE",
            "input entries must be ParsedFile instances",
        )

    try:
        owned = ParsedFile.model_validate(parsed_file.model_dump())
    except ValidationError as exc:
        raise RepoIndexError(
            "INVALID_PARSED_FILE",
            str(exc),
            file_path=parsed_file.file_path,
        ) from exc

    buffer = owned.source_text.encode("utf-8")
    buffer_hash = hashlib.sha256(buffer).hexdigest()

    if buffer_hash != owned.parse_buffer_sha256:
        raise RepoIndexError(
            "PARSE_BUFFER_HASH_MISMATCH",
            "source_text does not match its parse-buffer hash",
            file_path=owned.file_path,
        )

    # Under the approved UTF-8/UTF-8-BOM policy, original bytes
    # are either this buffer or this buffer with a leading BOM.
    possible_original_hashes = {
        buffer_hash,
        hashlib.sha256(b"\xef\xbb\xbf" + buffer).hexdigest(),
    }

    if owned.source_sha256 not in possible_original_hashes:
        raise RepoIndexError(
            "SOURCE_HASH_MISMATCH",
            "original-byte hash is inconsistent with the source buffer",
            file_path=owned.file_path,
        )

    for symbol in owned.symbols:
        expected_key = make_local_key(
            owned.file_path,
            symbol.kind,
            symbol.qualname,
            symbol.definition_start_byte,
        )

        if symbol.local_key != expected_key:
            raise RepoIndexError(
                "INVALID_DEFINITION_IDENTITY",
                "definition local_key does not match its metadata",
                file_path=owned.file_path,
            )

        if not (
            0
            <= symbol.content_start_byte
            <= symbol.definition_start_byte
            < symbol.definition_end_byte
            <= symbol.content_end_byte
            <= len(buffer)
        ):
            raise RepoIndexError(
                "INVALID_DEFINITION_RANGE",
                "definition/content ranges are inconsistent",
                file_path=owned.file_path,
            )

    return owned


def build_repo_index(
    parsed_files: list[ParsedFile],
    *,
    source_roots: tuple[str, ...] = (".",),
) -> RepoIndex:
    """Build the module/definition portion of the repository index."""
    roots = _validate_source_roots(source_roots)

    files: dict[str, ParsedFile] = {}

    for parsed_file in parsed_files:
        owned = _copy_and_validate_file(parsed_file)

        if owned.file_path in files:
            raise RepoIndexError(
                "DUPLICATE_FILE_PATH",
                "provide exactly one source version for each file path",
                file_path=owned.file_path,
            )

        files[owned.file_path] = owned

    modules_by_path: dict[str, ModuleInfo] = {}
    modules_by_key: dict[str, ModuleInfo] = {}
    candidates: dict[str, list[ModuleInfo]] = {}
    definitions: dict[str, ParsedSymbol] = {}

    for file_path in sorted(files):
        parsed_file = files[file_path]
        root = _source_root_for(file_path, roots)

        module = ModuleInfo(
            module_key=make_module_key(root, file_path),
            file_path=file_path,
            source_root=root,
            module_name=_module_name_for(file_path, root),
        )

        modules_by_path[file_path] = module
        modules_by_key[module.module_key] = module

        if module.module_name is not None:
            candidates.setdefault(module.module_name, []).append(
                module
            )

        for symbol in parsed_file.symbols:
            if symbol.local_key in definitions:
                raise RepoIndexError(
                    "DUPLICATE_SYMBOL_KEY",
                    "definition identity already exists in the index",
                    file_path=file_path,
                )

            definitions[symbol.local_key] = symbol

    ordered_candidates = {
        name: tuple(
            sorted(
                modules,
                key=lambda module: module.module_key,
            )
        )
        for name, modules in sorted(candidates.items())
    }

    return RepoIndex(
        source_roots=roots,
        files_by_path=MappingProxyType(
            dict(sorted(files.items()))
        ),
        modules_by_path=MappingProxyType(modules_by_path),
        modules_by_key=MappingProxyType(
            dict(sorted(modules_by_key.items()))
        ),
        modules_by_name=MappingProxyType(ordered_candidates),
        definitions_by_local_key=MappingProxyType(
            dict(sorted(definitions.items()))
        ),
    )