"""Static test linking from bounded CALLS paths and conservative names."""

from collections import defaultdict
from pathlib import PurePosixPath

from reposcope.contracts.detection import (
    DerivedEdge,
    DetectionEvidence,
    DetectionGap,
)
from reposcope.contracts.test_linking import (
    TestLink,
    TestLinkingResult,
)


def _is_test_file(path):
    name = PurePosixPath(path).name
    return name.startswith("test_") and name.endswith(".py")


def _is_test_area(path):
    parts = PurePosixPath(path).parts
    return _is_test_file(path) or any(
        part in {"tests", "test"}
        for part in parts[:-1]
    )


def _target_key(target):
    if target.target_kind == "symbol":
        return target.symbol_key
    return None


def _test_symbols(parsed_files):
    tests = {}

    for parsed in parsed_files:
        if not _is_test_file(parsed.file_path):
            continue

        by_key = {
            symbol.local_key: symbol
            for symbol in parsed.symbols
        }

        for symbol in parsed.symbols:
            if not symbol.name.startswith("test_"):
                continue

            if (
                symbol.kind == "function"
                and symbol.parent_key is None
            ):
                tests[symbol.local_key] = symbol

            elif symbol.kind == "method":
                parent = by_key.get(symbol.parent_key)

                if (
                    parent is not None
                    and parent.kind == "class"
                    and parent.parent_key is None
                    and parent.name.startswith("Test")
                ):
                    tests[symbol.local_key] = symbol

    return tests


def _evidence(parsed, symbol, rule):
    buffer = parsed.source_text.encode("utf-8")
    start = symbol.definition_start_byte
    end = symbol.definition_end_byte

    return DetectionEvidence(
        file_path=parsed.file_path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        start_byte=start,
        end_byte=end,
        expression=buffer[start:end].decode("utf-8"),
        rule_id=f"tests.{rule}",
    )


def detect_test_links(
    parsed_files,
    call_edges,
) -> TestLinkingResult:
    """Link implementation functions/methods to discovered tests.

    call_edges must be resolver AnalysisEdge records. Only resolved CALLS
    edges are traversed, with a hard limit of two hops.

    Naming fallback requires:
    - No implementation call path was found for the test.
    - Exact name equality after stripping the test_ function prefix.
    - Matching test-file and implementation-file stems.
    - Exactly one eligible implementation candidate.

    Naming matches are inferred associations, not call-path evidence.
    """
    parsed_files = tuple(parsed_files)

    files = {
        parsed.file_path: parsed
        for parsed in parsed_files
    }

    symbols = {}
    paths = {}

    for parsed in parsed_files:
        for symbol in parsed.symbols:
            symbols[symbol.local_key] = symbol
            paths[symbol.local_key] = parsed.file_path

    tests = _test_symbols(parsed_files)

    implementations = {
        key: symbol
        for key, symbol in symbols.items()
        if symbol.kind in {"function", "method"}
        and not _is_test_area(paths[key])
    }

    adjacency = defaultdict(list)

    for edge in call_edges:
        if (
            edge.kind != "CALLS"
            or edge.status not in {"EXACT", "INFERRED"}
        ):
            continue

        source = _target_key(edge.source)
        target = _target_key(edge.target)

        if source not in symbols or target not in symbols:
            continue

        if (
            symbols[source].kind not in {"function", "method"}
            or symbols[target].kind not in {"function", "method"}
        ):
            continue

        adjacency[source].append(edge)

    for edges in adjacency.values():
        edges.sort(
            key=lambda edge: (
                _target_key(edge.target),
                edge.reference_key,
            )
        )

    links = []
    derived = []
    gaps = []
    seen = set()

    def add_link(test_key, implementation_key, rule, path, refs, confidence):
        identity = (
            test_key,
            implementation_key,
            rule,
            path,
            refs,
        )

        if identity in seen:
            return

        seen.add(identity)

        link = TestLink(
            implementation_key=implementation_key,
            test_key=test_key,
            rule=rule,
            confidence=confidence,
            call_path=path,
            reference_keys=refs,
        )

        links.append(link)

        derived.append(
            DerivedEdge(
                source_key=implementation_key,
                target_key=test_key,
                kind="TESTED_BY",
                confidence=confidence,
                evidence=_evidence(
                    files[paths[test_key]],
                    tests[test_key],
                    rule,
                ),
            )
        )

    for test_key in sorted(tests):
        found_call_link = False

        for first in adjacency.get(test_key, ()):
            middle = _target_key(first.target)

            # Do not treat one discovered test as another test's helper.
            if middle in tests:
                continue

            if middle in implementations:
                add_link(
                    test_key,
                    middle,
                    "direct_call",
                    (test_key, middle),
                    (first.reference_key,),
                    first.confidence,
                )
                found_call_link = True

            for second in adjacency.get(middle, ()):
                target = _target_key(second.target)

                if (
                    target not in implementations
                    or len({test_key, middle, target}) != 3
                ):
                    continue

                add_link(
                    test_key,
                    target,
                    "two_hop_call",
                    (test_key, middle, target),
                    (
                        first.reference_key,
                        second.reference_key,
                    ),
                    min(first.confidence, second.confidence) * 0.8,
                )
                found_call_link = True

        if found_call_link:
            continue

        test_symbol = tests[test_key]
        expected_name = test_symbol.name.removeprefix("test_")
        expected_module = PurePosixPath(
            paths[test_key]
        ).stem.removeprefix("test_")

        candidates = sorted(
            key
            for key, symbol in implementations.items()
            if symbol.name == expected_name
            and PurePosixPath(paths[key]).stem == expected_module
        )

        if len(candidates) == 1:
            add_link(
                test_key,
                candidates[0],
                "name_match",
                (),
                (),
                0.5,
            )
        else:
            gaps.append(
                DetectionGap(
                    file_path=paths[test_key],
                    start_line=test_symbol.start_line,
                    rule_id=(
                        "tests.ambiguous_name"
                        if candidates
                        else "tests.no_supported_link"
                    ),
                    reason=(
                        "Multiple implementation candidates match "
                        "the test name and module stem"
                        if candidates
                        else "No implementation call path within two hops "
                        "or unique supported naming match"
                    ),
                )
            )

    return TestLinkingResult(
        links=tuple(links),
        edges=tuple(derived),
        gaps=tuple(gaps),
    )