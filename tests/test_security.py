import copy
import hashlib
import json
import random
import unittest
from unittest.mock import patch

from e02 import core


def rehash(ast):
    body = {key: value for key, value in ast.items() if key != 'ast_digest'}
    ast['ast_digest'] = 'sha256:' + hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return ast


class SourceBinding(unittest.TestCase):
    def test_rehashed_rewrite_fails(self):
        ast = core.parse_document('# H\noriginal')
        ast['nodes'][1]['text'] = 'rewritten'
        report = core.verify_fidelity('# H\noriginal', rehash(ast))
        self.assertTrue(report['digest_matches_ast'])
        self.assertFalse(report['source_matches_ast'])
        self.assertEqual(report['verdict'], 'FAIL')

    def test_rehashed_heading_level_change_fails(self):
        ast = core.parse_document('# H')
        ast['nodes'][0]['level'] = 2
        self.assertEqual(core.verify_fidelity('# H', rehash(ast))['verdict'], 'FAIL')

    def test_rehashed_ordered_flag_change_fails(self):
        ast = core.parse_document('- item')
        ast['nodes'][0]['ordered'] = True
        self.assertEqual(core.verify_fidelity('- item', rehash(ast))['verdict'], 'FAIL')

    def test_rehashed_parent_change_fails(self):
        ast = core.parse_document('# H\npara')
        ast['nodes'][1]['parent'] = None
        self.assertEqual(core.verify_fidelity('# H\npara', rehash(ast))['verdict'], 'FAIL')

    def test_rehashed_source_replacement_fails_against_original(self):
        replacement = core.parse_document('other')
        self.assertEqual(core.verify_fidelity('original', replacement)['verdict'], 'FAIL')

    def test_metadata_is_bound(self):
        for key, value in (('schema', 'other'), ('parser_version', '0'),
                           ('source_line_count', 999), ('source_digest', 'sha256:'+'0'*64)):
            ast = core.parse_document('original')
            ast[key] = value
            with self.subTest(key=key):
                self.assertEqual(core.verify_fidelity('original', rehash(ast))['verdict'], 'FAIL')

    def test_extra_fields_fail(self):
        ast = core.parse_document('x')
        ast['approved'] = True
        self.assertEqual(core.verify_fidelity('x', rehash(ast))['verdict'], 'FAIL')

    def test_whitespace_and_line_endings_bound(self):
        ast = core.parse_document('# H\r\nx  \r\n')
        for other in ('# H\nx  \n', '# H\r\nx\r\n', '# H\r\nx  \r\n\r\n'):
            self.assertFalse(core.verify_fidelity(other, ast)['source_matches_ast'])

    def test_consumers_reject_tampered_ast(self):
        ast = core.parse_document('x')
        ast['nodes'][0]['text'] = 'y'
        rehash(ast)
        for consumer in (core.reading_order, core.serialize):
            with self.subTest(consumer=consumer.__name__), self.assertRaises(ValueError):
                consumer(ast)

    def test_consumers_return_detached_results(self):
        ast = core.parse_document('# H\ntext')
        expected = copy.deepcopy(ast)
        reading = core.reading_order(ast)
        reading[0]['text'] = 'changed'
        core.verify_fidelity(ast['source_text'], ast)
        self.assertEqual(ast, expected)


class ParserRegressions(unittest.TestCase):
    def test_long_fence_does_not_close_at_shorter_fence(self):
        source = '````py\n```\nbody\n````'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['text'], '```\nbody')
        self.assertEqual(core.verify_fidelity(source, ast)['verdict'], 'PASS')

    def test_closer_cannot_have_info_text(self):
        source = '```\n```not-a-closer\n```'
        self.assertEqual(core.parse_document(source)['nodes'][0]['text'], '```not-a-closer')

    def test_tilde_fences_and_long_closer(self):
        source = '  ~~~python\nx\n ~~~~~'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['kind'], 'code_block')
        self.assertEqual(ast['nodes'][0]['info'], 'python')
        self.assertEqual(core.serialize(ast), source)

    def test_mismatched_fence_retained(self):
        source = '~~~\n```\n~~~'
        self.assertEqual(core.parse_document(source)['nodes'][0]['text'], '```')

    def test_unclosed_fence_fails_but_preserves_content(self):
        source = '# H\n```py\nbody\n\n'
        ast = core.parse_document(source)
        report = core.verify_fidelity(source, ast)
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertTrue(report['round_trip_stable'])
        self.assertTrue(report['syntax_errors'])
        self.assertEqual(core.serialize(ast), source)
        self.assertEqual(core.reading_order(ast)[-1]['kind'], 'error')

    def test_empty_code_block(self):
        source = '```\n```\n'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['text'], '')
        self.assertEqual(core.serialize(ast), source)

    def test_code_trailing_blank_lines_preserved(self):
        source = '```\n  spaced  \n\n\n```\n\n'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['text'], '  spaced  \n\n')
        self.assertEqual(core.serialize(ast), source)

    def test_paragraph_marker_not_reinterpreted_by_serialization(self):
        source = '    # literal indentation\n    continuation\n'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['kind'], 'paragraph')
        self.assertEqual(core.serialize(ast), source)
        self.assertEqual(core.verify_fidelity(source, ast)['verdict'], 'PASS')

    def test_all_empty_boundary_table_cells_retained(self):
        ast = core.parse_document('||x||\n|||')
        self.assertEqual(ast['nodes'][0]['cells'], ['', 'x', ''])
        self.assertEqual(ast['nodes'][1]['cells'], ['', ''])

    def test_escaped_table_pipes(self):
        ast = core.parse_document(r'| a\|b | c |')
        self.assertEqual(ast['nodes'][0]['cells'], ['a|b', 'c'])

    def test_even_backslashes_allow_table_delimiter(self):
        ast = core.parse_document('| a'+chr(92)*2+'| b |')
        self.assertEqual(ast['nodes'][0]['cells'], ['a'+chr(92)*2, 'b'])

    def test_escaped_final_pipe_is_plain_text(self):
        ast = core.parse_document('| a '+chr(92)+'|')
        self.assertEqual(ast['nodes'][0]['kind'], 'paragraph')

    def test_separator_column_alignment_preserved(self):
        source = '| :--- | ---: | :---: | --- |'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['alignments'], ['left', 'right', 'center', None])
        self.assertEqual(core.serialize(ast), source)

    def test_short_dashes_are_table_data(self):
        self.assertEqual(core.parse_document('| - | -- |')['nodes'][0]['kind'], 'table_row')

    def test_heading_stack_after_decrease(self):
        ast = core.parse_document('# A\n### C\n## B\n# D\ntext')
        nodes = ast['nodes']
        self.assertEqual(nodes[2]['parent'], nodes[0]['id'])
        self.assertIsNone(nodes[3]['parent'])
        self.assertEqual(nodes[4]['parent'], nodes[3]['id'])

    def test_empty_heading_roundtrip(self):
        source = '# \n'
        ast = core.parse_document(source)
        self.assertEqual(ast['nodes'][0]['text'], '')
        self.assertEqual(core.verify_fidelity(source, ast)['verdict'], 'PASS')

    def test_unicode_line_separator_is_data(self):
        source = 'first\u2028second'
        ast = core.parse_document(source)
        self.assertEqual(ast['source_line_count'], 1)
        self.assertEqual(ast['nodes'][0]['text'], source)

    def test_empty_and_blank_documents(self):
        for source in ('', '\n', '\r\n\n', ' \t\n'):
            with self.subTest(source=repr(source)):
                ast = core.parse_document(source)
                self.assertEqual(core.serialize(ast), source)
                self.assertEqual(core.verify_fidelity(source, ast)['verdict'], 'PASS')

    def test_seeded_source_roundtrips(self):
        randomizer = random.Random(22001)
        fragments = ['# H', '## B', '- item', '7. item', 'para  ', '| a | b |',
                     '| :--- | ---: |', '~~~\ncode\n~~~', '    # literal', '']
        for _ in range(100):
            source = '\n'.join(randomizer.choices(fragments, k=12))
            ast = core.parse_document(source)
            self.assertEqual(core.serialize(ast), source)
            self.assertEqual(core.verify_fidelity(source, ast)['verdict'], 'PASS')


class MalformedInput(unittest.TestCase):
    def test_huge_and_negative_spans_fail_without_expansion(self):
        for span in ([-1, 1], [1, 10**100], [2, 1], [0, 0], [True, 1], [1, False]):
            ast = core.parse_document('x')
            ast['nodes'][0]['lines'] = span
            with self.subTest(span=span):
                self.assertEqual(core.verify_fidelity('x', ast)['verdict'], 'FAIL')

    def test_repeated_wide_spans_have_bounded_diagnostics(self):
        source = 'x\n'*100
        ast = core.parse_document(source)
        ast['nodes'] = [copy.deepcopy(ast['nodes'][0]) for _ in range(1000)]
        report = core.verify_fidelity(source, ast)
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertLessEqual(len(report['structural_fidelity']['overlapping_lines']), core.MAX_DIAGNOSTICS)

    def test_nonjson_and_nonobject_asts_fail(self):
        for value in (None, [], 42, 'x', {'nodes': [None]}, {'nodes': [object()]}, {'x': float('nan')}):
            self.assertEqual(core.verify_fidelity('x', value)['verdict'], 'FAIL')

    def test_cyclic_ast_fails(self):
        ast = core.parse_document('x')
        ast['cycle'] = ast
        self.assertEqual(core.verify_fidelity('x', ast)['verdict'], 'FAIL')

    def test_boolean_metadata_cannot_equal_integer(self):
        ast = core.parse_document('# H')
        ast['source_line_count'] = True
        self.assertEqual(core.verify_fidelity('# H', rehash(ast))['verdict'], 'FAIL')

    def test_surrogate_source_rejected(self):
        with self.assertRaises(ValueError):
            core.parse_document('\ud800')

    def test_source_byte_limit(self):
        with self.assertRaises(ValueError):
            core.parse_document('x'*(core.MAX_SOURCE_BYTES+1))
        with patch.object(core, 'MAX_SOURCE_BYTES', 8):
            with self.assertRaises(ValueError):
                core.parse_document('界'*3)

    def test_line_count_and_length_limits(self):
        for source in ('x\n'*(core.MAX_LINES+1), 'x'*(core.MAX_LINE_LENGTH+1)):
            with self.assertRaises(ValueError):
                core.parse_document(source)

    def test_node_budget(self):
        with patch.object(core, 'MAX_NODES', 2):
            with self.assertRaises(ValueError):
                core.parse_document('# A\n# B\n# C')

    def test_parser_enforces_ast_budget(self):
        with patch.object(core, 'MAX_AST_VALUES', 10):
            with self.assertRaises(ValueError):
                core.parse_document('# H')

    def test_consumer_missing_schema_fields(self):
        for consumer in (core.serialize, core.reading_order):
            with self.assertRaises(ValueError):
                consumer({'nodes': []})

    def test_no_false_empty_document_pass_for_forged_ast(self):
        ast = {'nodes': [], 'ast_digest': core._digest([])}
        self.assertEqual(core.verify_fidelity('', ast)['verdict'], 'FAIL')
