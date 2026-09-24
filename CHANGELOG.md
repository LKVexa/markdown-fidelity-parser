# 0.1.2a1 — 2026-09-23

- Bind AST v2 and fidelity v2 to exact source and all semantic metadata.
- Serialize losslessly; reject modified/legacy ASTs at every consumer.
- Make unclosed fences fail fidelity while retaining visible error content.
- Parse bounded fence lengths/types, escaped table pipes and empty cells.
- Bound source/AST structures, coverage expansion and diagnostics.
- Add 41 regressions, packaging, CI, README and Apache 2.0 LICENSE/NOTICE.
- Original program certifications remain open.

# Changelog — E02 Document Reader & Parser (JY-S022-P001)

## 0.1.1-partial — 2026-09-14 (maintenance run-0001, audit A019)

Baseline fingerprint: build-0001 product.zip
sha256 `bb38ec540310b5e80cdd613d8abea262317ac0d47ca78532c84f2c863682b90d`
(6951 bytes); baseline version 0.1.0-partial; baseline suite 13/13 PASS.
All findings below were reproduced live on the unmodified baseline
before fixing (probe log kept in audit records).

### Fixes (repairs only — patch bump)

- **A019-F1 — serialize() silently dropped unclosed-fence content.**
  Observed: `serialize(parse_document("# T\n```py\nsecret..."))`
  returned only `"# T\n"` — the error node's body was lost from the
  canonical form and `verify_fidelity` reported round_trip FAIL on a
  correctly parsed document. Expected: canonical form preserves all
  accounted source content and round-trips. Fixed: error nodes now
  carry `text`/`info`/`parent`; serialize emits the open fence and
  body; round trip is stable and verdict is PASS.
- **A019-F2 — tamper detection crashed instead of failing.**
  Observed: tampered/malformed ASTs escaped `verify_fidelity` (the
  tamper gate) and `reading_order` as bare KeyError/TypeError —
  missing `lines`, kind changed to `table_row` without `cells`,
  `lines` of wrong type, NaN or non-serializable values injected into
  nodes, empty ast dict. Expected: FAIL verdict with defects listed.
  Fixed: `verify_fidelity` validates structure and returns
  `verdict: FAIL` with a new `malformed_ast` list; `_digest` now uses
  strict canonical JSON (`allow_nan=False`) so NaN/Infinity are
  refused; `reading_order` degrades gracefully on malformed nodes.
- **A019-F3 — undocumented bare exceptions on non-str input.**
  Observed: `parse_document(None)` -> AttributeError;
  `parse_document(b"# x")` -> opaque re-module TypeError. Fixed:
  documented TypeError contract with clear message in
  `parse_document` and `verify_fidelity` (text argument).

Also added: native `__version__` constant; 11 focused regression tests
(24 total).

### Compatibility

- Public API unchanged (`parse_document`, `reading_order`,
  `serialize`, `verify_fidelity`, `VERSION`). AST schema `e02/ast/v1`
  unchanged for well-formed documents; error nodes gain `text`,
  `info`, `parent` fields (additive). Fidelity report gains
  `malformed_ast` (additive). Documents containing NaN-bearing
  tampered nodes now FAIL instead of crashing.
- No baseline test asserted the old weaker behavior; none needed
  changes.

### Rollback

Restore build-0001 `product.zip` (sha256 above). No data migrations;
the module is a pure function library with no persistent state.

## 0.1.0-partial — build-0001

Initial partial candidate.
