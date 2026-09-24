# Security boundaries

The parser is a pure in-process library over caller-provided text/ASTs. It does
not load files, fetch URLs, render HTML or execute document content. Bounded
inputs reduce memory/CPU exposure but do not provide process isolation or a
hard execution deadline. Use stable built-in JSON-like objects, without concurrent
mutation or hostile subclasses.

AST v2 embeds the entire original source. Apply source-equivalent access and
retention controls. Hashes provide consistency only; they neither authenticate
the supplied source nor certify semantic completeness. An attacker controlling
both source and AST can supply a self-consistent replacement. PASS applies only
to the documented Markdown subset; unsupported semantics are not validated.

Malformed ASTs fail validation rather than silently dropping content. Unclosed
fences fail fidelity despite being preserved. Error and reading-order text stay
untrusted. Any renderer must escape/sanitize output according to its own context.

No third-party runtime packages are required. No build-tool vulnerability scan,
formal certification or platform qualification is claimed. Report defects using
synthetic documents and AST samples that do not contain confidential content.
