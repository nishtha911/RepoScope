"""Build complete symbol chunks from Track 1 parser output."""

import json
from codecs import BOM_UTF8
from hashlib import sha256

from pydantic import ValidationError

from reposcope.contracts.chunking import (
    ChunkDraft,
    SOURCE_SEPARATOR,
)
from reposcope.contracts.parsing import ParsedFile, ParsedSymbol


class ChunkingError(ValueError):
    """Raised when parser output cannot safely produce chunk drafts."""


def _validate_parsed_file(parsed_file: ParsedFile) -> ParsedFile:
    """Revalidate input, including models changed after construction."""
    if not isinstance(parsed_file, ParsedFile):
        raise TypeError(
            "parsed_file must be a ParsedFile instance."
        )

    try:
        validated = ParsedFile.model_validate(
            parsed_file.model_dump()
        )
    except (ValidationError, UnicodeError) as exc:
        raise ChunkingError(
            "Invalid parser output or source-buffer metadata."
        ) from exc

    buffer = validated.source_text.encode("utf-8")

    if sha256(buffer).hexdigest() != validated.parse_buffer_sha256:
        raise ChunkingError(
            "Parse-buffer hash does not match source_text."
        )

    # The parser supports UTF-8 with or without a leading BOM.
    # Its source_text omits that leading BOM.
    compatible_source_hashes = {
        sha256(buffer).hexdigest(),
        sha256(BOM_UTF8 + buffer).hexdigest(),
    }

    if validated.source_sha256 not in compatible_source_hashes:
        raise ChunkingError(
            "Original-source hash is inconsistent with the "
            "supported UTF-8 source buffer."
        )

    return validated


def _build_header(
    parsed_file: ParsedFile,
    symbol: ParsedSymbol,
) -> str:
    """Serialize the proposed v1 metadata header deterministically."""
    metadata = {
        "file_path": parsed_file.file_path,
        "qualname": symbol.qualname,
        "kind": symbol.kind,
        "signature": symbol.signature,
        "docstring": symbol.docstring,
    }

    return json.dumps(
        metadata,
        ensure_ascii=False,
        indent=2,
    )


def build_symbol_chunks(
    parsed_file: ParsedFile,
) -> list[ChunkDraft]:
    """
    Build one draft per class/function/method definition.

    Bodies use complete parser-supplied content ranges.
    No token/line splitting, truncation, file reads, or DB writes occur.

    Enclosing and nested definitions intentionally overlap.
    Whole-definition correctness depends on the parser supplying
    complete, correct source ranges.
    """
    validated = _validate_parsed_file(parsed_file)
    buffer = validated.source_text.encode("utf-8")

    chunks: list[ChunkDraft] = []

    for symbol in validated.symbols:
        start = symbol.content_start_byte
        end = symbol.content_end_byte

        if not 0 <= start < end <= len(buffer):
            raise ChunkingError(
                f"Invalid content range for {symbol.qualname}."
            )

        try:
            body_text = buffer[start:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChunkingError(
                f"Content range crosses a UTF-8 boundary "
                f"for {symbol.qualname}."
            ) from exc

        header_text = _build_header(validated, symbol)

        try:
            chunk = ChunkDraft(
                symbol_key=symbol.local_key,
                file_path=validated.file_path,
                source_sha256=validated.source_sha256,
                parse_buffer_sha256=validated.parse_buffer_sha256,
                qualname=symbol.qualname,
                kind=symbol.kind,
                start_line=symbol.content_start_line,
                end_line=symbol.content_end_line,
                header_text=header_text,
                body_text=body_text,
                text=header_text + SOURCE_SEPARATOR + body_text,
            )
        except ValidationError as exc:
            raise ChunkingError(
                f"Could not construct chunk for {symbol.qualname}."
            ) from exc

        chunks.append(chunk)

    return chunks