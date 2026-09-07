import ast
import unittest

from autodoc_py.data import class_fields, module_data


class DataTests(unittest.TestCase):
    def test_vuer_type_aliases_keep_expressions_and_attribute_docstrings(self):
        tree = ast.parse('''IDType = Union[UUID, str]
"""An identifier."""
CoroutineFn = Callable[[], Coroutine]
"""Returns a coroutine."""
EventHandler = Callable[[ClientEvent, "VuerProxy"], None]
SocketHandler = Callable[["VuerProxy"], Coroutine]
''')
        declarations = module_data(tree)
        self.assertEqual(list(declarations), ['IDType', 'CoroutineFn', 'EventHandler', 'SocketHandler'])
        self.assertTrue(all(node._autodoc_kind == 'type alias' for node in declarations.values()))
        self.assertEqual(declarations['IDType']._autodoc_doc, 'An identifier.')
        self.assertEqual(declarations['CoroutineFn']._autodoc_doc, 'Returns a coroutine.')
        self.assertEqual(declarations['EventHandler']._autodoc_doc, '')
        self.assertEqual(ast.unparse(declarations['IDType'].value), 'Union[UUID, str]')

    def test_explicit_alias_annotations_and_pep604(self):
        declarations = module_data(ast.parse('''A: TypeAlias = list[str]
B: typing.TypeAlias = "Other"
C: "typing_extensions.TypeAlias" = int | str
D = int | str
items: list[str] = []
'''))
        for name in 'ABCD':
            self.assertEqual(declarations[name]._autodoc_kind, 'type alias')
        self.assertEqual(declarations['items']._autodoc_kind, 'attribute')

    def test_constants_and_chained_assignments_do_not_execute(self):
        tree = ast.parse('''raise RuntimeError("Do not import")
LIMIT = 12
OPTIONS = {"safe": True}
LEFT = RIGHT = 3
value: str
__all__ = ["LIMIT"]
_private = 1
EnvVar = _EnvVar()
dangerous = execute()
''')
        declarations = module_data(tree)
        self.assertEqual(list(declarations), ['LIMIT', 'OPTIONS', 'LEFT', 'RIGHT', 'value'])
        self.assertTrue(all(node._autodoc_kind == 'attribute' for node in declarations.values()))
        self.assertEqual(ast.unparse(declarations['LEFT']), 'LEFT = 3')
        self.assertEqual(ast.unparse(declarations['RIGHT']), 'RIGHT = 3')
        self.assertFalse(hasattr(tree.body[1], '_autodoc_kind'))
        self.assertIsNone(declarations['value'].value)

    def test_class_fields_keep_annotations_defaults_and_descriptors(self):
        tree = ast.parse('''class Euler:
    x: int
    order: str = "XYZ"
    """Rotation order."""
    unit = "rad"
    field = Field(default=3)
    _cache = {}
    def compute(self):
        self.runtime = 1
''')
        fields = class_fields(tree.body[0])
        self.assertEqual([node.name for node in fields], ['x', 'order', 'unit', 'field'])
        self.assertEqual(ast.unparse(fields[0].annotation), 'int')
        self.assertIsNone(fields[0].value)
        self.assertEqual(fields[1].value.value, 'XYZ')
        self.assertEqual(fields[1]._autodoc_doc, 'Rotation order.')
        self.assertEqual(ast.unparse(fields[3].value), 'Field(default=3)')
        self.assertTrue(all(node._autodoc_kind == 'attribute' for node in fields))

    def test_only_adjacent_strings_are_attribute_docs(self):
        declarations = module_data(ast.parse('''first = 1
second = 2
"""Only second."""
third = 3
42
"""Not third."""
first = 4
'''))
        self.assertEqual(declarations['first'].value.value, 4)
        self.assertEqual(declarations['first']._autodoc_doc, '')
        self.assertEqual(declarations['second']._autodoc_doc, 'Only second.')
        self.assertEqual(declarations['third']._autodoc_doc, '')

    @unittest.skipUnless(hasattr(ast, 'TypeAlias'), 'PEP 695 requires Python 3.12')
    def test_pep695_alias_retains_type_parameters(self):
        declarations = module_data(ast.parse('type Sequence[T] = list[T]\n"""A sequence."""'))
        node = declarations['Sequence']
        self.assertEqual(node._autodoc_kind, 'type alias')
        self.assertEqual(node._autodoc_doc, 'A sequence.')
        self.assertEqual(len(node._autodoc_type_params), 1)
        self.assertEqual(ast.unparse(node), 'Sequence = list[T]')


if __name__ == '__main__':
    unittest.main()
