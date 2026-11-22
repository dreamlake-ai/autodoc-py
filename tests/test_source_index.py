"""SourceIndex computes each export table once; the output does not change."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc_py import SourceIndex, assignment_aliases, generate
from autodoc_py.data import module_data
from autodoc_py.grouped import generate_grouped


def uncached_exports(self, module, seen=None, public=True):
    return SourceIndex._resolve_exports(self, module, seen, public)


def uncached_declarations(self, module, tree):
    return module_data(tree), assignment_aliases(tree)


FILES = {
    # ``make`` links Alias, which __all__ leaves out: the public and the full export
    # tables of this module differ, and the page uses both.
    '__init__.py': '"""Sample."""\nfrom .core import *\nfrom .models import Model, DEFAULT, Alias\n'
                   '__all__ = ["Engine", "Model", "DEFAULT", "engine", "make"]\n'
                   'def make(alias: Alias) -> Engine:\n    """Make an engine."""\n',
    'core.py': 'from .models import Model, Alias\nfrom . import util\n'
               'class Base:\n    def run(self, model: Model) -> Alias:\n        """Run."""\n'
               'class Engine(Base):\n    """An engine."""\n'
               '    def step(self, value: Alias, other: "Model | None" = None) -> list[Model]:\n'
               '        """Step."""\n'
               'engine = Engine()\n',
    'models.py': 'from typing import Union\nfrom .core import Engine\n'
                 'Alias = Union[int, str]\n"""An alias."""\n'
                 'DEFAULT: int = 3\n"""The default."""\n'
                 'class Model:\n    """A model."""\n    size: Alias = 1\n'
                 '    def fit(self, engine: Engine, alias: Alias = DEFAULT) -> "Model":\n'
                 '        """Fit."""\n',
    'util.py': 'from .core import *\nfrom .models import *\n'
               'def helper(model: Model, engine: Engine) -> Alias:\n    """Help."""\n',
}


class SourceIndexCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'sample'
        self.source.mkdir()
        for name, text in FILES.items():
            (self.source / name).write_text(text)

    def snapshot(self, output):
        return {str(p.relative_to(output)): p.read_bytes()
                for p in sorted(output.rglob('*')) if p.is_file()}

    def build_both(self, build):
        cached = build(self.root / 'cached')
        with mock.patch.object(SourceIndex, 'exports', uncached_exports), \
                mock.patch.object(SourceIndex, 'declarations', uncached_declarations):
            uncached = build(self.root / 'uncached')
        return cached, uncached

    def test_module_pages_are_byte_identical(self):
        def build(output):
            generate(self.source, output, 'sample', source_url='https://example.com/sample')
            return self.snapshot(output)
        cached, uncached = self.build_both(build)
        self.assertTrue(any(name.endswith('+Page.mdx') for name in cached))
        self.assertEqual(cached, uncached)

    def test_grouped_pages_are_byte_identical(self):
        page_map = {'pages': [
            dict(slug='core', title='Core', description='Core API', modules=['sample', 'sample.core']),
            dict(slug='models', title='Models', description='Model API',
                 modules=['sample.models', 'sample.util']),
        ]}

        def build(output):
            generate_grouped(self.source, output, 'sample', page_map, url_prefix='/reference')
            return self.snapshot(output)
        cached, uncached = self.build_both(build)
        self.assertEqual(cached, uncached)

    def test_each_export_table_is_resolved_once(self):
        sources = {}
        for name in FILES:
            module = 'sample' if name == '__init__.py' else 'sample.' + name[:-3]
            path = self.source / name
            sources[module] = (path, ast.parse(path.read_text()))
        index = SourceIndex(sources, 'sample')
        with mock.patch.object(SourceIndex, '_resolve_exports', autospec=True,
                               side_effect=SourceIndex._resolve_exports) as resolve:
            first = index.exports('sample.util', public=False)
            calls = resolve.call_count
            for _ in range(5):
                self.assertEqual(index.exports('sample.util', public=False), first)
            self.assertEqual(resolve.call_count, calls)
        # Callers get a copy: changing it does not change the index.
        first.clear()
        self.assertIn('helper', index.exports('sample.util', public=False))


if __name__ == '__main__':
    unittest.main()
