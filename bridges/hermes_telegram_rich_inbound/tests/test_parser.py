import unittest
from plugin import render_rich


def p(text): return {'type': 'paragraph', 'text': text}

class ParserTests(unittest.TestCase):
    def test_paragraphs_and_inline_url_targets(self):
        value = {'blocks': [p(['Hello ', {'type': 'bold', 'text': 'world'}, ' ',
                    {'type': 'url', 'text': {'type': 'italic', 'text': 'site'}, 'url': 'https://example.invalid/a'}]), p('Next')]}
        self.assertEqual(render_rich(value), 'Hello world site (https://example.invalid/a)\n\nNext')

    def test_nested_numbered_and_bullet_lists(self):
        value = {'blocks': [p('Items'), {'type': 'list', 'items': [
            {'label': '1.', 'blocks': [p('Outer'), {'type': 'list', 'items': [
                {'label': '•', 'blocks': [p('Inner')]}]}]},
            {'label': '2.', 'blocks': [p('Last')]}]}, p('End')]}
        self.assertEqual(render_rich(value), 'Items\n\n1. Outer\n   \n   • Inner\n2. Last\n\nEnd')

    def test_unknown_material_visible(self):
        value = {'blocks': [p('known'), {'type': 'future', 'payload': 'DO NOT LOSE', 'url': 'https://example.invalid/u'}]}
        result = render_rich(value)
        self.assertIn('unsupported', result)
        self.assertIn('DO NOT LOSE', result)
        self.assertIn('https://example.invalid/u', result)

    def test_extra_fields_not_silently_dropped(self):
        result = render_rich({'blocks': [dict(p('hello'), future='important')], 'is_rtl': True})
        self.assertIn('hello', result)
        self.assertIn('important', result)
        self.assertIn('is_rtl', result)

    def test_checkbox_and_list_metadata(self):
        result = render_rich({'blocks': [{'type': 'list', 'items': [
            {'label': 'a)', 'blocks': [p('Done')], 'has_checkbox': True, 'is_checked': True, 'value': 2, 'type': 'a'}]}]})
        self.assertIn('a) [x] Done', result)
        self.assertIn('value', result)

    def test_empty_visible(self):
        self.assertEqual(render_rich({'blocks': []}), '[rich_message empty]')

    def test_malformed_visible(self):
        for value in (None, [], {}, {'blocks': None}, {'blocks': [p(None)]}):
            with self.subTest(value=value):
                self.assertIn('[rich_message error:', render_rich(value))

    def test_depth_limit_visible(self):
        value = 'end'
        for _ in range(40): value = {'type': 'bold', 'text': value}
        self.assertIn('[rich_message error: depth limit', render_rich({'blocks': [p(value)]}))

    def test_output_limit_visible(self):
        result = render_rich({'blocks': [p('x' * 40000)]})
        self.assertIn('[rich_message error:', result)
        self.assertLess(len(result), 100)

    def test_node_limit_visible(self):
        self.assertIn('[rich_message error: node limit', render_rich({'blocks': [p('') for _ in range(5000)]}))

    def test_indentation_amplification_is_bounded(self):
        import tracemalloc
        value = {'blocks': [{'type': 'list', 'items': [
            {'label': 'a' * 25000, 'blocks': [p('\n' * 400)]}]}]}
        tracemalloc.start()
        result = render_rich(value)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertIn('[rich_message error: output limit', result)
        self.assertLess(peak, 2_000_000)

    def test_code_and_quote_rendering_preserves_multiline_boundaries(self):
        cases = [
            (p({'type': 'code', 'text': '/stop'}), '`/stop`'),
            (p({'type': 'code', 'text': '`/stop`'}), '`` `/stop` ``'),
            ({'type': 'pre', 'text': '```\n/stop\n```'}, '````\n```\n/stop\n```\n````'),
            ({'type': 'expandable_blockquote', 'text': '/stop\nnext'}, '> /stop\n> next'),
            ({'type': 'pullquote', 'text': '/stop\n\nnext'}, '> /stop\n> \n> next'),
        ]
        for block, expected in cases:
            with self.subTest(block=block):
                self.assertEqual(render_rich({'blocks': [block]}), expected)

    def test_cycle_bounded(self):
        value = {'blocks': []}; value['blocks'].append(value)
        self.assertIn('[rich_message error: depth limit', render_rich(value))
