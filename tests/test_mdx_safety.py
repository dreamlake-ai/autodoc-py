import tempfile
import unittest
from pathlib import Path
from autodoc_py import generate, prose, fence


class MdxSafetyTests(unittest.TestCase):
    def test_esm_docstring_lines_cannot_become_imports(self):
        actual = prose('import os\nexport default thing\nUse `{x}` and <Thing> {value}.')
        self.assertIn('&#105;mport os', actual)
        self.assertIn('&#101;xport default thing', actual)
        self.assertIn('`{x}`', actual)
        self.assertIn('&lt;Thing&gt; &#123;value&#125;', actual)

    def test_long_fences_keep_embedded_triple_backticks_literal(self):
        text = '````python\nx = "```"\ny = {"a": 1}\n````'
        self.assertEqual(prose(text), text)
        self.assertTrue(fence('"```"').startswith('````python'))

    def test_matching_inline_delimiters_and_indented_esm(self):
        self.assertEqual(prose("Use ``a ` {value} `` safely."), "Use ``a ` {value} `` safely.")
        self.assertIn("&#123;value&#125;", prose("Unclosed `a {value}"))
        self.assertEqual(prose("  import os"), "  &#105;mport os")

    def test_code_fence_with_info_is_not_a_closing_fence(self):
        text = "```python\n```text\nx = {1}\n```"
        self.assertEqual(prose(text), text)

    def test_declared_encoding_for_historical_python_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'pkg'
            source.mkdir()
            (source / '__init__.py').write_bytes(b'# coding: latin-1\n"""caf\xe9"""\n')
            generate(source, root / 'pages', 'pkg')
            self.assertIn('café', (root / 'pages/+Page.mdx').read_text())


if __name__ == '__main__':
    unittest.main()
