# Markdown Fidelity Parser

**0.1.2a1 — experimental partial candidate, JY-S022-P001 / E02**

A small Python library that parses a documented Markdown subset into source-
bound ASTs, reports reading order, serializes the original text losslessly, and
checks structural fidelity. Parsing, verification and serialization perform no
file/network I/O. This is not a complete CommonMark parser or Markdown renderer.

## Install and use

Python 3.10+; no third-party runtime dependencies.

~~~sh
python -m pip install .
python -m unittest discover -s tests -t .
~~~

~~~python
from e02.core import parse_document, reading_order, serialize, verify_fidelity

source = "# Guide\n\n- Read the instructions\n"
ast = parse_document(source)
assert serialize(ast) == source
assert verify_fidelity(source, ast)["verdict"] == "PASS"
print(reading_order(ast))
~~~

## Supported syntax

- ATX headings at the start of a line, one through six # characters followed
  by space/tab. Each heading carries its level and nearest preceding lower-level
  heading as parent; same-level siblings correctly replace each other.
- Plain paragraphs: contiguous nonblank, nonstructural lines. Reading text joins
  stripped lines with spaces; the original spacing and line breaks remain in source_text.
- Flat bullet and numbered list items. Ordered/unordered identity is retained,
  while original numbering and indentation remain in source_text.
- Rows with outer unescaped | delimiters. Empty boundary cells and escaped pipes
  are preserved. Delimiter cells require three or more dashes and optional edge
  colons; column count and alignment are retained. Width consistency is not a
  table-schema check, and pipes in inline code need escaping in this subset.
- Backtick or tilde fences of at least three characters, indented zero to three
  spaces. Closers must use the same character, be at least as long, and contain
  only optional trailing spaces/tabs. Info text and all body whitespace remain.
  An unclosed fence becomes an explicit error node and makes fidelity FAIL.

Nested list structure, inline Markdown, HTML semantics, indented-code blocks,
setext headings, links/entities and full CommonMark conformance are not modeled.
Unsupported constructs remain plain text when they do not match this subset.
A PASS means consistency for this grammar, not semantic understanding of every
Markdown feature. No HTML sanitization or rendering is supplied.

## AST v2 and fidelity

AST fields: schema, parser_version, source_text, source_digest, source_line_count,
nodes and ast_digest. Nodes have sequential stable IDs, one-based inclusive line
spans, heading parent IDs and kind-specific data. IDs are stable for unchanged
input, not persistent identities after insertion. CR, LF and CRLF delimit lines;
other Unicode separator characters remain content. Blank lines outside nodes
are not reading-order entries but are retained in source_text.

source_digest hashes the exact original UTF-8 bytes. ast_digest binds all other
AST fields, including parser/schema version, source text, count and node metadata.
Digests are deterministic consistency checks, not signatures or authorization.
The AST contains the complete original document; treat it with the same access
controls and retention as the source.

serialize(ast) validates the AST against a fresh parse and returns the exact
original string, including final newline, line endings, numbering and whitespace.
It does not normalize Markdown syntax. Edit the source and parse again; mutation
of AST fields is not an editing API. reading_order and serialize reject malformed,
altered or legacy ASTs with ValueError instead of silently dropping content.
Error nodes remain visible in reading_order with their error field.

verify_fidelity(text, ast) checks exact-source agreement, metadata/digest integrity,
line coverage, ordering, deterministic serialization and syntax errors. Recomputing
a digest after rewriting nodes cannot make those nodes match the supplied original
text. Replacing both the text and AST is outside this consistency boundary: no
trusted external source, identity or signature is established by the library.

Malformed ASTs return FAIL with bounded diagnostics. Invalid source types raise
TypeError; invalid Unicode or resource-limit violations raise ValueError. A
preserved unclosed fence has round_trip_stable=true but verdict=FAIL. The legacy
digest_matches_nodes report key is retained as an alias for digest_matches_ast;
in v2 it covers the complete AST body, not nodes alone. Fidelity schema is
e02/fidelity/v2. At most 1,000 examples are returned per diagnostic list; total
uncovered line count remains available.

## Resource limits

Source: 1 MiB of UTF-8, 20,000 lines, 16,384 characters per line and 10,000 nodes.
AST: 150,000 JSON values (including object keys), 12 nesting levels, 8 MiB total
string bytes, 1 MiB per string and 32-bit-magnitude integer fields. These limits
apply together; some documents reach the AST value budget before the node cap.
Parsing enforces the same budget used by AST consumers. Arbitrary Python objects,
cycles, floats/nonfinite values, invalid Unicode and nonstring keys are refused.
Coverage expansion is capped at 40,000 line visits for an untrusted AST.

The library runs in-process; these budgets are not an OS sandbox, hard execution
deadline or protection against concurrent caller mutation/hostile Python subclasses.
Use plain JSON-like built-in data and stable inputs. Reading-order text and source
content remain untrusted and must be escaped by any downstream renderer.

## Verification and migration

65 tests: 24 inherited checks and 41 new regressions, including 100 seeded mixed-
document roundtrips, rehashed content/metadata tampering, exact-source retention,
fence/table parsing and hostile AST bounds. Source and installed-wheel results:
[CHECK_RUNS](docs/CHECK_RUNS.json). CI covers Linux Python 3.10/3.12/3.14 and Windows
3.12. See [AUDIT](docs/AUDIT.md) and [SECURITY](SECURITY.md).

0.1.1-partial -> 0.1.2a1 changes AST/report schemas to v2. Reparse the original
source to migrate v1 ASTs; a v1 AST cannot recover discarded whitespace. Serialization
now returns exact source instead of reformatted Markdown. Unclosed fences no
longer PASS, and reading_order fails explicitly for tampered input. Those two
inherited expectations were updated; the source baseline remains separate.

The original 85 parent controls, 686 child rows, QAM integrations, PDF/DOCX/OCR
ingestion, governance receipts, certification and formal platform qualification
remain outside this partial candidate. Test success does not certify them.

## License

Copyright 2026 **RUSSELL PHILIP SMITHSON**.
[Apache License 2.0](LICENSE), with [NOTICE](NOTICE).
No third-party source is vendored; see [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES.md).
