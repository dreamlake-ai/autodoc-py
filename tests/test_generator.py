import tempfile
import unittest
from pathlib import Path
from autodoc_py import generate, prose
from test_presentation import ParsedHTML


class GeneratorTests(unittest.TestCase):
    def test_import_free_signatures_and_mdx(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'package'
            source.mkdir()
            (source / '__init__.py').write_text('raise RuntimeError("must never import")\n')
            (source / 'api.py').write_text('''"""Module with <tags> and {expressions}."""
from missing_dependency import Something
class Client(Something):
    """A client."""
    active: bool = True
    def __init__(self, url: str = "https://example.com"):
        """Create a client."""
    async def run(self, /, value: dict[str, int], *, timeout=10) -> None:
        """Use `{"key": 1}` safely."""
    def _private(self): pass
''')
            output = root / 'pages'
            self.assertEqual(generate(source, output, 'sample', source_url='https://example.com/blob/ref/sample'), 2)
            page = (output / 'api/+Page.mdx').read_text()
            self.assertIn('async Client.run(value: dict[str, int], *, timeout = 10) → None',
                          [node.text for node in ParsedHTML(page).root.find('pre', 'py-api-signature')])
            self.assertIn('&lt;tags&gt; and &#123;expressions&#125;', page)
            self.assertIn('`{"key": 1}`', page)
            self.assertIn('https://example.com/blob/ref/sample/api.py#L3', page)
            self.assertNotIn('_private', page)

    def test_stale_pages_removed_but_manual_pages_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'package'
            source.mkdir()
            (source / '__init__.py').write_text('')
            (source / 'old.py').write_text('def old(): pass')
            output = root / 'pages'
            generate(source, output, 'sample')
            (output / 'manual.mdx').write_text('manual')
            (source / 'old.py').unlink()
            generate(source, output, 'sample')
            self.assertFalse((output / 'old/+Page.mdx').exists())
            self.assertEqual((output / 'manual.mdx').read_text(), 'manual')

    def test_parse_failure_does_not_change_existing_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'package'
            source.mkdir()
            (source / '__init__.py').write_text('"""Original"""')
            output = root / 'pages'
            generate(source, output, 'sample')
            original = (output / '+Page.mdx').read_text()
            (source / '__init__.py').write_text('"""Changed"""')
            (source / 'broken.py').write_text('def invalid syntax')
            with self.assertRaises(SyntaxError):
                generate(source, output, 'sample')
            self.assertEqual((output / '+Page.mdx').read_text(), original)

    def test_explicit_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '__init__.py').write_text('__all__ = ["_public"]\ndef _public(): pass\ndef excluded(): pass')
            generate(root, root / 'out', 'sample')
            page = (root / 'out/+Page.mdx').read_text()
            signatures = [node.text for node in ParsedHTML(page).root.find('pre', 'py-api-signature')]
            self.assertIn('_public()', signatures)
            self.assertNotIn('excluded()', signatures)

    def test_local_reexports_and_inherited_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'package'
            source.mkdir()
            (source / '__init__.py').write_text('from .child import *')
            (source / 'base.py').write_text('class Base:\n    tag = "base"\n    count: int = 3\n    def __init__(self, value=1): pass\n    def run(self): pass')
            (source / 'child.py').write_text('from .base import Base\n__all__ = ["Child"]\nclass Child(Base):\n    tag = "child"')
            output = root / 'pages'
            generate(source, output, 'sample')
            page = (output / '+Page.mdx').read_text()
            self.assertIn('[`Child`](/api/child#child)', page)
            child = (output / 'child/+Page.mdx').read_text()
            self.assertIn('`count` — from [`sample.base.Base`](/api/base#base)', child)
            self.assertIn('`__init__` — from [`sample.base.Base`](/api/base#base)', child)
            self.assertNotIn('`tag` — from', child)
            self.assertIn(["tag", "'child'", "—"],
                          [[cell.text for cell in row.find("td")]
                           for row in ParsedHTML(child).root.find("tr")])

    def test_fenced_code_preserved(self):
        text = 'Text {value}\n```python\nx = {"a": 1}\n```'
        self.assertEqual(prose(text), 'Text &#123;value&#125;\n```python\nx = {"a": 1}\n```')


if __name__ == '__main__':
    unittest.main()
