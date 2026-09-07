"""Check rendered API meaning independently of markup whitespace and span layout."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from autodoc_py import SourceIndex, render
from autodoc_py.grouped import generate_grouped


class Element:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def text(self):
        return ''.join(c.text if isinstance(c, Element) else c for c in self.children)

    def find(self, tag=None, css=None):
        found = []
        for child in self.children:
            if isinstance(child, Element):
                classes = child.attrs.get('classname', child.attrs.get('class', '')).split()
                if (tag is None or child.tag == tag) and (css is None or css in classes):
                    found.append(child)
                found.extend(child.find(tag, css))
        return found


class ParsedHTML(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs))

    def handle_endtag(self, tag):
        for n in range(len(self.stack) - 1, 0, -1):
            if self.stack[n].tag == tag:
                del self.stack[n:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


class PresentationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def render_source(self, source):
        path = self.root / 'api.py'
        path.write_text(source)
        index = SourceIndex({'sample': (self.root / '__init__.py', ast.parse('')),
                             'sample.api': (path, ast.parse(source))})
        markup = render(path, 'sample.api', index=index)
        return markup, ParsedHTML(markup).root

    def card(self, tree, name):
        return next(card for card in tree.find('section', 'py-api')
                    if card.find('code', 'py-api-name')[0].text.endswith('.' + name))

    def signature(self, card):
        return card.find('pre', 'py-api-signature')[0].text

    def test_parameter_modes_defaults_and_return_type_links(self):
        _, tree = self.render_source('''class Result: pass
async def build(value: int, /, label: str = "x", *, result: Result, enabled: bool = False) -> Result:
    """Build a result.

    Args:
        value: Input value.
        result: Existing result.
    Returns:
        Result: Built value.
    """
''')
        card = self.card(tree, 'build')
        self.assertEqual(self.signature(card), "async build(value: int, /, label: str = 'x', *, result: Result, enabled: bool = False) → Result")
        rows = [[cell.text for cell in row.find('td')] for row in card.find('tr') if row.find('td')]
        self.assertIn(['value', 'intpositional-only', 'Input value.'], rows)
        self.assertIn(['result', 'Resultkeyword-only', 'Existing result.'], rows)
        self.assertIn(['enabled', 'bool = False', 'Keyword-only parameter.'], rows)
        self.assertTrue(any(a.text == 'Result' and a.attrs.get('href') == '/api/api#result' for a in card.find('a')))
        self.assertIn('Built value.', card.text)

    def test_namedtuple_fields_defaults_and_base_links(self):
        _, tree = self.render_source('''from typing import NamedTuple
class Euler(NamedTuple):
    x: int
    y: int
    z: int
    order: str = "XYZ"
class Degrees(Euler):
    unit: str = "deg"
''')
        euler = self.card(tree, 'Euler')
        self.assertEqual(euler.find('span', 'py-api-kind')[0].text, 'named tuple')
        self.assertEqual(self.signature(euler), "Euler(x: int, y: int, z: int, order: str = 'XYZ')")
        self.assertIn('Attributes', euler.text)
        self.assertTrue(any([c.text for c in r.find('td')] == ['order', "str = 'XYZ'", '—'] for r in euler.find('tr')))
        degrees = self.card(tree, 'Degrees')
        self.assertEqual(degrees.find('p', 'py-api-meta')[0].text, 'Bases: Euler')
        self.assertTrue(any(a.attrs.get('href') == '/api/api#euler' for a in degrees.find('a')))
        self.assertIn('Inherited members', degrees.text)

    def test_property_static_and_class_methods_have_correct_call_shapes(self):
        _, tree = self.render_source('''class Client:
    @property
    def name(self) -> str:
        """Display name."""
    @staticmethod
    def convert(value: int, /, *, unit="m") -> str: pass
    @classmethod
    def create(cls, name: str) -> "Client": pass
''')
        property_card = self.card(tree, 'Client.name')
        self.assertEqual(property_card.find('span', 'py-api-kind')[0].text, 'property')
        self.assertEqual(self.signature(property_card), 'Client.name: str')
        self.assertNotIn('Parameters', property_card.text)
        static = self.card(tree, 'Client.convert')
        self.assertEqual(static.find('span', 'py-api-kind')[0].text, 'static method')
        self.assertEqual(self.signature(static), "Client.convert(value: int, /, *, unit = 'm') → str")
        classmethod = self.card(tree, 'Client.create')
        self.assertEqual(classmethod.find('span', 'py-api-kind')[0].text, 'class method')
        self.assertEqual(self.signature(classmethod), "Client.create(name: str) → 'Client'")

    def test_type_aliases_keep_docs_and_alias_expression(self):
        _, tree = self.render_source('''from typing import Union
IDType = Union[str, int]
"""An external identifier."""
''')
        card = self.card(tree, 'IDType')
        self.assertEqual(card.find('span', 'py-api-kind')[0].text, 'type alias')
        self.assertEqual(self.signature(card), 'IDType = Union[str, int]')
        self.assertIn('An external identifier.', card.text)

    def test_signature_and_doc_fields_cannot_inject_mdx(self):
        markup, tree = self.render_source('''def safe(value: "<Danger>{annotation}" = "<script>{danger}</script>", other=None):
    """Use safe values.

    :param value: <img src=x onerror=bad>{expression}
    :type other: <Injected>{type_expression}
    :returns: <iframe>{return_expression}
    """
''')
        self.assertFalse(tree.find('script'))
        self.assertFalse(tree.find('img'))
        self.assertFalse(tree.find('iframe'))
        self.assertNotIn('<Danger>', markup)
        for name in ('annotation', 'danger', 'expression', 'type_expression', 'return_expression'):
            self.assertNotIn('{' + name + '}', markup)
            self.assertIn('{' + name + '}', tree.text)
        self.assertIn('<script>{danger}</script>', self.signature(self.card(tree, 'safe')))

    def test_grouped_html_type_links_target_namespaced_declarations(self):
        source = self.root / 'sample'
        source.mkdir()
        (source / '__init__.py').write_text('')
        (source / 'base.py').write_text('class Base: pass\n')
        (source / 'child.py').write_text('from .base import Base\nclass Child(Base):\n    def clone(self, other: Base) -> Base: pass\n')
        output = self.root / 'pages'
        config = {'pages': [
            {'slug': 'foundation', 'title': 'Foundation', 'description': 'Base types', 'modules': ['sample', 'sample.base']},
            {'slug': 'clients', 'title': 'Clients', 'description': 'Client types', 'modules': ['sample.child']},
        ]}
        generate_grouped(source, output, 'sample', config, url_prefix='/reference')
        child = ParsedHTML((output / 'clients/+Page.mdx').read_text()).root
        foundation = ParsedHTML((output / 'foundation/+Page.mdx').read_text()).root
        ids = {a.attrs.get('id') for a in foundation.find('a')}
        links = [a for a in child.find('a', 'py-api-type') if a.text == 'Base']
        self.assertGreaterEqual(len(links), 3)
        for link in links:
            self.assertEqual(link.attrs['href'], '/reference/foundation#sample.base--base')
            self.assertIn(link.attrs['href'].partition('#')[2], ids)


    def test_writable_property_preserves_getter_type_and_documentation(self):
        _, tree = self.render_source('''class Client:
    @property
    def name(self) -> str:
        """Display name from the getter."""
    @name.setter
    def name(self, value: str) -> None:
        """Set the name."""
''')
        cards = [card for card in tree.find('section', 'py-api')
                 if card.find('code', 'py-api-name')[0].text.endswith('.Client.name')]
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(self.signature(card), 'Client.name: str')
        self.assertEqual(card.find('span', 'py-api-kind')[0].text, 'property')
        self.assertIn('Writable property', card.text)
        self.assertIn('Display name from the getter.', card.text)
        self.assertNotIn('Parameters', card.text)

    def test_constructor_parameter_separators_match_method_signatures(self):
        _, tree = self.render_source('''class Config:
    def __init__(self, value: int, /, label="x", *, strict: bool = True): pass
class Variadic:
    def __init__(self, value, /, *items: str, flag=False, **options): pass
class Empty:
    def __init__(self): pass
''')
        expected = {
            'Config': "(value: int, /, label = 'x', *, strict: bool = True)",
            'Variadic': "(value, /, *items: str, flag = False, **options)",
            'Empty': "()",
        }
        for name, arguments in expected.items():
            with self.subTest(name=name):
                self.assertEqual(self.signature(self.card(tree, name)), name + arguments)
                self.assertEqual(self.signature(self.card(tree, name + '.__init__')),
                                 name + '.__init__' + arguments)

if __name__ == '__main__':
    unittest.main()
