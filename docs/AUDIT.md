# Audit and hardening — 0.1.2a1

Date: 2026-09-23. Source: JY-S022-P001 / 0.1.1-partial / run-0001 / product.
Reviewed structural parsing, reading order, serialization, fidelity and tests.
Original source is preserved separately from this release checkout.

## Repaired findings

- Fidelity trusted a node digest without comparing AST content to the supplied
  source. Rehashing rewritten text or metadata could pass. AST v2 binds exact
  source, schema/version, counts and nodes; every consumer validates a fresh
  deterministic parse, and fidelity separately compares the supplied source.
- Round-trip shape checks omitted levels, ordered flags, parents, code info and
  table separators. Full AST/source agreement now validates all those fields.
- Serialization discarded whitespace, numbering, empty code-body distinctions,
  table column structure and trailing content. Exact-source serialization replaces
  reformatting; editing is performed by changing source and reparsing.
- Unclosed fences could receive PASS and be omitted from reading order. They now
  produce explicit syntax errors, FAIL fidelity and remain visible in reading order.
- Three-backtick prefix matching closed longer fences early and accepted closing
  info text. Fence length/type/indentation and closer shape are now checked;
  tilde fences are supported and content is preserved.
- Table stripping removed empty boundary cells and split escaped pipes. Escaped
  delimiter handling, empty cells and separator column/alignment data are retained.
- Unbounded line spans allowed enormous coverage expansion; malformed objects,
  deep/cyclic ASTs and invalid Unicode could crash consumers. Source/AST budgets,
  strict JSON-like values, bounded spans/diagnostics and explicit errors repair
  those paths. Consumers reject altered ASTs rather than silently degrading.

## Verification and release

24 baseline tests passed. 65 source and installed-wheel tests pass after changes:
41 new regressions cover rehashed tampering, exact bytes/line endings, metadata,
code/table edge cases, malformed resource bounds and 100 seeded mixed documents.
Two inherited expectations changed: unclosed-fence fidelity now FAILs while
roundtrip remains stable, and reading_order raises ValueError on altered ASTs.
The inherited no-file/no-socket side-effect check remains in the suite.

CHECK_RUNS.json records current tests and BASELINE_CHECK_RUNS.json preserves
original evidence. CI covers Linux Python 3.10/3.12/3.14 and Windows 3.12.
These checks are not full CommonMark conformance, independent semantic fidelity
certification or an OS resource-isolation proof.

Version 0.1.1-partial -> 0.1.2a1, AST/report schemas v1 -> v2. Reparse original
source to migrate; discarded v1 whitespace cannot be reconstructed. Added
packaging, pinned-action CI, security notes, README and Apache 2.0 LICENSE/NOTICE
naming RUSSELL PHILIP SMITHSON. There is no vendored third-party code or runtime
dependency to upgrade; no build-tool vulnerability scan is claimed.

The original 85-control/686-row certification program, QAM/PDF/DOCX/OCR and
governance integrations remain outside this partial candidate.
