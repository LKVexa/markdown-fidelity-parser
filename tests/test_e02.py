import socket
import unittest

from e02.core import parse_document, reading_order, serialize, verify_fidelity

DOC = """\
# Guide

Intro paragraph spanning
two lines.

## Setup

- install python
- run tests
1. first step

| name | value |
| --- |
| port | 8080 |

```python
print("hi")
```

## Usage

Final words.
"""


class Parsing(unittest.TestCase):
    def setUp(self):
        self.ast = parse_document(DOC)
        self.by_kind = {}
        for n in self.ast["nodes"]:
            self.by_kind.setdefault(n["kind"], []).append(n)

    def test_node_kinds(self):
        self.assertEqual(len(self.by_kind["heading"]), 3)
        self.assertEqual(len(self.by_kind["paragraph"]), 2)
        self.assertEqual(len(self.by_kind["list_item"]), 3)
        self.assertEqual(len(self.by_kind["table_row"]), 2)
        self.assertEqual(len(self.by_kind["code_block"]), 1)

    def test_multiline_paragraph_span(self):
        p = self.by_kind["paragraph"][0]
        self.assertEqual(p["text"], "Intro paragraph spanning two lines.")
        self.assertEqual(p["lines"], [3, 4])

    def test_heading_hierarchy(self):
        h1 = self.by_kind["heading"][0]
        setup = self.by_kind["heading"][1]
        usage = self.by_kind["heading"][2]
        self.assertIsNone(h1["parent"])
        self.assertEqual(setup["parent"], h1["id"])
        self.assertEqual(usage["parent"], h1["id"])   # sibling pops Setup
        items = self.by_kind["list_item"]
        self.assertTrue(all(i["parent"] == setup["id"] for i in items))

    def test_ordered_vs_bullet(self):
        flags = [i["ordered"] for i in self.by_kind["list_item"]]
        self.assertEqual(flags, [False, False, True])

    def test_code_block_and_table(self):
        cb = self.by_kind["code_block"][0]
        self.assertEqual(cb["text"], 'print("hi")')
        self.assertEqual(cb["info"], "python")
        self.assertEqual(self.by_kind["table_row"][0]["cells"],
                         ["name", "value"])

    def test_unclosed_fence_is_error_node(self):
        ast = parse_document("```py\nno end")
        self.assertEqual(ast["nodes"][-1]["kind"], "error")

    def test_stable_digest(self):
        self.assertEqual(self.ast["ast_digest"],
                         parse_document(DOC)["ast_digest"])


class ReadingOrder(unittest.TestCase):
    def test_linearization_order_and_depth(self):
        ro = reading_order(parse_document(DOC))
        texts = [e["text"] for e in ro]
        self.assertLess(texts.index("Guide"), texts.index("Setup"))
        self.assertLess(texts.index("install python"), texts.index("Usage"))
        items = [e for e in ro if e["kind"] == "list_item"]
        self.assertTrue(all(e["depth"] == 2 for e in items))


class Fidelity(unittest.TestCase):
    def test_pass_on_clean_document(self):
        ast = parse_document(DOC)
        rep = verify_fidelity(DOC, ast)
        self.assertEqual(rep["verdict"], "PASS", rep)
        self.assertEqual(rep["structural_fidelity"]["uncovered_lines"], [])
        self.assertTrue(rep["round_trip_stable"])

    def test_tampered_ast_fails(self):
        ast = parse_document(DOC)
        ast["nodes"] = [n for n in ast["nodes"] if n["kind"] != "paragraph"]
        rep = verify_fidelity(DOC, ast)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertTrue(rep["structural_fidelity"]["uncovered_lines"])

    def test_text_mutation_detected(self):
        ast = parse_document(DOC)
        for n in ast["nodes"]:
            if n["kind"] == "paragraph":
                n["text"] = "rewritten content"
                break
        rep = verify_fidelity(DOC, ast)
        # round trip still stable (self-consistent), but coverage holds;
        # digest no longer matches a fresh parse
        self.assertNotEqual(ast_digest_fresh(), rep["ast_digest"])

    def test_zero_side_effects(self):
        import builtins
        opened = []
        real_open, real_socket = builtins.open, socket.socket
        builtins.open = lambda *a, **k: (opened.append(a), real_open(*a, **k))[1]
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError)
        try:
            ast = parse_document(DOC)
            verify_fidelity(DOC, ast)
            serialize(ast)
        finally:
            builtins.open, socket.socket = real_open, real_socket
        self.assertEqual(opened, [])

    def test_deterministic(self):
        a = verify_fidelity(DOC, parse_document(DOC))
        b = verify_fidelity(DOC, parse_document(DOC))
        self.assertEqual(a, b)


class Hardening(unittest.TestCase):
    """New tests for 0.1.1-partial repairs (A019-F1..F3)."""

    # F1: unclosed-fence content must survive canonical serialization
    def test_error_node_content_preserved_in_serialize(self):
        doc = "# T\n```py\nsecret line 1\nsecret line 2"
        ast = parse_document(doc)
        canon = serialize(ast)
        self.assertIn("secret line 1", canon)
        self.assertIn("secret line 2", canon)

    def test_error_node_round_trip_stable_but_verdict_fails(self):
        doc = "# T\n```py\nsecret line 1\nsecret line 2"
        ast = parse_document(doc)
        rep = verify_fidelity(doc, ast)
        self.assertTrue(rep["round_trip_stable"], rep)
        self.assertEqual(rep["verdict"], "FAIL", rep)
        self.assertTrue(rep["syntax_errors"])

    # F2: tamper gate returns FAIL, never a bare KeyError/TypeError
    def test_tamper_missing_lines_fails_not_crashes(self):
        ast = parse_document("# H\npara\n")
        del ast["nodes"][0]["lines"]
        rep = verify_fidelity("# H\npara\n", ast)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertTrue(rep["malformed_ast"])

    def test_tamper_kind_change_fails_not_crashes(self):
        ast = parse_document("# H\npara\n")
        ast["nodes"][1]["kind"] = "table_row"   # no 'cells' key
        rep = verify_fidelity("# H\npara\n", ast)
        self.assertEqual(rep["verdict"], "FAIL")
        # AST consumers now fail explicitly instead of silently dropping content.
        with self.assertRaises(ValueError):
            reading_order(ast)

    def test_tamper_nan_strict_canonicalization_fails(self):
        ast = parse_document("x\n")
        ast["nodes"][0]["text"] = float("nan")
        rep = verify_fidelity("x\n", ast)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertFalse(rep["digest_matches_nodes"])

    def test_tamper_unserializable_object_fails(self):
        ast = parse_document("x\n")
        ast["nodes"][0]["text"] = object()
        rep = verify_fidelity("x\n", ast)
        self.assertEqual(rep["verdict"], "FAIL")

    def test_tamper_lines_wrong_type_fails(self):
        ast = parse_document("x\n")
        ast["nodes"][0]["lines"] = "1,1"
        rep = verify_fidelity("x\n", ast)
        self.assertEqual(rep["verdict"], "FAIL")

    def test_empty_ast_dict_fails_not_crashes(self):
        rep = verify_fidelity("x", {})
        self.assertEqual(rep["verdict"], "FAIL")

    # F3: documented TypeError contract for non-str input
    def test_parse_non_str_raises_typeerror(self):
        with self.assertRaises(TypeError):
            parse_document(None)
        with self.assertRaises(TypeError):
            parse_document(b"# x")

    def test_verify_non_str_text_raises_typeerror(self):
        with self.assertRaises(TypeError):
            verify_fidelity(None, parse_document("x"))

    # clean documents still PASS after hardening
    def test_clean_doc_unaffected(self):
        rep = verify_fidelity(DOC, parse_document(DOC))
        self.assertEqual(rep["verdict"], "PASS")
        self.assertEqual(rep["malformed_ast"], [])


def ast_digest_fresh():
    return parse_document(DOC)["ast_digest"]


if __name__ == "__main__":
    unittest.main()
