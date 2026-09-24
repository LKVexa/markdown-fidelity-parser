"""Bounded Markdown-subset parsing with exact-source fidelity, without I/O.

This is not a full CommonMark renderer. AST v2 includes the original source so
serialization is lossless, and every consumer validates a fresh deterministic
parse. Digests provide consistency, not authentication.
"""
from __future__ import annotations
import hashlib
import json
import re

VERSION = "0.1.2a1"
__version__ = VERSION
MAX_SOURCE_BYTES = 1024 * 1024
MAX_LINES = 20000
MAX_LINE_LENGTH = 16384
MAX_NODES = 10000
MAX_AST_BYTES = 8 * 1024 * 1024
MAX_AST_VALUES = 150000
MAX_DIAGNOSTICS = 1000


def _digest(obj):
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _source(text):
    if type(text) is not str:
        raise TypeError("source must be a string")
    if len(text) > MAX_SOURCE_BYTES:
        raise ValueError("source byte budget exceeded")
    try:
        raw = text.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("source must contain valid Unicode scalar values") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source byte budget exceeded")
    # Only CR, LF and CRLF delimit source lines; other Unicode separators are data.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n") if normalized else []
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE_LENGTH for line in lines):
        raise ValueError("source line budget exceeded")
    return lines, "sha256:" + hashlib.sha256(raw).hexdigest()


_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_BULLET = re.compile(r"^[ \t]*[-*+][ \t]+(.*)$")
_ORDERED = re.compile(r"^[ \t]*[0-9]+[.)][ \t]+(.*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SEPARATOR = re.compile(r":?-{3,}:?")


def _fence(line):
    match = _FENCE.fullmatch(line)
    if match is None or (match[1][0] == "`" and "`" in match[2]):
        return None
    return match[1], match[2].strip() or None


def _closing_fence(line, marker):
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    content = stripped.rstrip(" \t")
    return len(content) >= len(marker) and set(content) == {marker[0]}


def _table_cells(line):
    row = line.strip()
    if len(row) < 2 or not row.startswith("|") or not row.endswith("|"):
        return None
    # The final pipe must be an unescaped delimiter.
    slash_count = len(row[:-1]) - len(row[:-1].rstrip("\\"))
    if slash_count % 2:
        return None
    cells, current, slashes = [], [], 0
    for char in row[1:-1]:
        if char == "|":
            if slashes % 2:
                current.pop()
                current.append(char)
            else:
                cells.append("".join(current).strip())
                current = []
            slashes = 0
        else:
            current.append(char)
            slashes = slashes + 1 if char == "\\" else 0
    cells.append("".join(current).strip())
    return cells


def _structural(line):
    return (_fence(line) is not None or _HEADING.match(line) is not None or
            _BULLET.match(line) is not None or _ORDERED.match(line) is not None or
            _table_cells(line) is not None)


def parse_document(text):
    """Return a bounded AST v2 including exact original source and provenance."""
    lines, source_digest = _source(text)
    nodes, stack = [], []
    index = 0

    def add(kind, start, end, **fields):
        if len(nodes) >= MAX_NODES:
            raise ValueError("node budget exceeded")
        node = {"id": f"n{len(nodes):04d}", "kind": kind, "lines": [start, end],
                "parent": stack[-1][1] if stack else None, **fields}
        nodes.append(node)
        return node

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        opener = _fence(line)
        if opener is not None:
            marker, info = opener
            start = index
            index += 1
            body = []
            while index < len(lines) and not _closing_fence(lines[index], marker):
                body.append(lines[index])
                index += 1
            fields = {"text": "\n".join(body), "info": info, "fence": marker}
            if index == len(lines):
                add("error", start + 1, len(lines), error="unclosed code fence", **fields)
                break
            add("code_block", start + 1, index + 1, **fields)
            index += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading[1])
            while stack and stack[-1][0] >= level:
                stack.pop()
            node = add("heading", index + 1, index + 1, level=level, text=heading[2].strip())
            stack.append((level, node["id"]))
            index += 1
            continue
        item = _BULLET.match(line) or _ORDERED.match(line)
        if item:
            add("list_item", index + 1, index + 1, ordered=bool(_ORDERED.match(line)), text=item[1].strip())
            index += 1
            continue
        cells = _table_cells(line)
        if cells is not None:
            if all(_SEPARATOR.fullmatch(cell) for cell in cells):
                alignments = ["center" if c.startswith(":") and c.endswith(":") else
                              "left" if c.startswith(":") else "right" if c.endswith(":") else None for c in cells]
                add("table_separator", index + 1, index + 1, cells=cells, alignments=alignments)
            else:
                add("table_row", index + 1, index + 1, cells=cells)
            index += 1
            continue
        start, paragraph = index, []
        while index < len(lines) and lines[index].strip() and not _structural(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        add("paragraph", start + 1, index, text=" ".join(paragraph))
    ast = {"schema": "e02/ast/v2", "parser_version": VERSION, "source_text": text,
           "source_digest": source_digest, "source_line_count": len(lines), "nodes": nodes}
    _json_budget(ast)
    ast["ast_digest"] = _digest(ast)
    return ast


def _json_budget(value):
    """Reject non-JSON objects, cycles and excessive structures before hashing."""
    pending, count, size = [(value, 0)], 0, 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_AST_VALUES or depth > 12:
            raise ValueError("AST structure budget exceeded")
        if type(item) is dict:
            if len(item) > MAX_AST_VALUES:
                raise ValueError("AST object budget exceeded")
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("AST keys must be strings")
                pending.append((key, depth + 1))
                pending.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > MAX_AST_VALUES:
                raise ValueError("AST array budget exceeded")
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > MAX_SOURCE_BYTES:
                raise ValueError("AST string budget exceeded")
            try:
                size += len(item.encode("utf-8"))
            except UnicodeError as exc:
                raise ValueError("AST contains invalid Unicode") from exc
        elif type(item) is int:
            if item.bit_length() > 32:
                raise ValueError("AST integer budget exceeded")
        elif item is not None and type(item) is not bool:
            raise ValueError("AST values must use the schema's JSON types")
        if size > MAX_AST_BYTES:
            raise ValueError("AST byte budget exceeded")


def _checked_ast(ast):
    _json_budget(ast)
    if type(ast) is not dict or type(ast.get("source_text")) is not str:
        raise ValueError("AST v2 with source_text is required")
    expected = parse_document(ast["source_text"])
    # Canonical JSON equality distinguishes bool from int and rejects extra fields.
    if _digest(ast) != _digest(expected):
        raise ValueError("AST does not match its source, schema, metadata and digest")
    return expected


def reading_order(ast):
    """Validated document order; error content remains visible with its error field."""
    checked = _checked_ast(ast)
    result, depth = [], {None: 0}
    for node in checked["nodes"]:
        kind = node["kind"]
        if kind == "heading":
            depth[node["id"]] = node["level"]
        if kind == "table_separator":
            continue
        entry = {"id": node["id"], "kind": kind, "depth": depth[node["parent"]],
                 "text": " | ".join(node["cells"]) if kind == "table_row" else node["text"]}
        if kind == "error":
            entry["error"] = node["error"]
        result.append(entry)
    return result


def serialize(ast):
    """Return exact source text after validating all AST fields. No Markdown rewriting."""
    return _checked_ast(ast)["source_text"]


def verify_fidelity(text, ast):
    """Report exact-source fidelity; valid preserved syntax errors still fail verdict."""
    lines, source_digest = _source(text)
    malformed, nodes = [], []
    budget_ok = True
    try:
        _json_budget(ast)
        if type(ast) is not dict or type(ast.get("nodes")) is not list or len(ast["nodes"]) > MAX_NODES:
            raise ValueError("AST nodes missing or outside budget")
        nodes = ast["nodes"]
    except ValueError as exc:
        malformed.append(str(exc))
        budget_ok = False
    covered, overlaps, out_of_order = {}, [], []
    last_end, coverage_work = 0, 0
    for index, node in enumerate(nodes):
        if type(node) is not dict:
            malformed.append("node must be an object")
            break
        span, node_id = node.get("lines"), node.get("id")
        if type(node_id) is not str or len(node_id) > 32:
            node_id = f"index:{index}"
        if type(span) is not list or len(span) != 2 or any(type(v) is not int for v in span) or not 1 <= span[0] <= span[1] <= len(lines):
            malformed.append("node has invalid source span")
            continue
        coverage_work += span[1] - span[0] + 1
        if coverage_work > 2 * MAX_LINES:
            malformed.append("coverage span budget exceeded")
            break
        if span[0] <= last_end:
            out_of_order.append(node_id)
        last_end = span[1]
        for line in range(span[0], span[1] + 1):
            if line in covered and len(overlaps) < MAX_DIAGNOSTICS:
                overlaps.append({"line": line, "nodes": [covered[line], node_id]})
            covered[line] = node_id
    gaps = [i+1 for i, line in enumerate(lines) if line.strip() and i+1 not in covered]
    recomputed, digest_matches, source_matches, round_trip = None, False, False, False
    if budget_ok:
        try:
            recomputed = _digest({k: v for k, v in ast.items() if k != "ast_digest"})
            digest_matches = recomputed == ast.get("ast_digest")
            expected = parse_document(text)
            source_matches = _digest(ast) == _digest(expected)
            checked = _checked_ast(ast)
            round_trip = parse_document(serialize(checked)) == checked
        except (ValueError, TypeError) as exc:
            malformed.append(str(exc))
    errors = [{"id": n["id"], "lines": n["lines"], "error": n["error"]}
              for n in parse_document(text)["nodes"] if n["kind"] == "error"]
    ok = not (malformed or gaps or overlaps or out_of_order or errors) and digest_matches and source_matches and round_trip
    return {"schema": "e02/fidelity/v2",
        "structural_fidelity": {"uncovered_lines": gaps[:MAX_DIAGNOSTICS], "overlapping_lines": overlaps,
                                "uncovered_line_count": len(gaps)},
        "reading_order_consistent": not out_of_order and not malformed, "out_of_order_nodes": out_of_order[:MAX_DIAGNOSTICS],
        "round_trip_stable": round_trip, "digest_matches_nodes": digest_matches,
        "digest_matches_ast": digest_matches, "source_matches_ast": source_matches,
        "source_digest": source_digest, "ast_digest": recomputed,
        "malformed_ast": malformed[:MAX_DIAGNOSTICS], "syntax_errors": errors,
        "verdict": "PASS" if ok else "FAIL",
        "note": "bounded Markdown-subset consistency checks; hashes are not authentication; certification remains a separate human decision"}
