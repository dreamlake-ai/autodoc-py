"""Reader-facing grouping keeps API links intact without importing the package."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from autodoc_py import generate
from autodoc_py.grouped import generate_grouped


class GroupedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'sample'
        self.source.mkdir()
        self.output = self.root / 'pages'
        self.write('__init__.py', '')

    def write(self, name, content):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def group(self, slug, *modules, **kwargs):
        return dict(slug=slug, title=slug.title(), description='API for ' + slug,
                    modules=list(modules), **kwargs)

    def build(self, *pages, **kwargs):
        return generate_grouped(self.source, self.output, 'sample',
                                {'pages': list(pages), **kwargs}, url_prefix='/reference')

    def snapshot(self):
        return {str(p.relative_to(self.output)): p.read_bytes()
                for p in self.output.rglob('*') if p.is_file()}

    def assert_internal_links_resolve(self):
        pages = {('/reference/' + str(p.parent.relative_to(self.output))): p.read_text()
                 for p in self.output.rglob('+Page.mdx')}
        for body in pages.values():
            for route, fragment in re.findall(r'\]\((/reference/[^)#]+)#([^)]+)\)', body):
                self.assertIn(route, pages, route)
                self.assertIn('id="' + fragment + '"', pages[route], route + '#' + fragment)

    def test_same_symbol_names_get_distinct_anchors_and_migration_targets(self):
        self.write('first.py', 'class Client:\n    def run(self): pass\n')
        self.write('second.py', 'class Client:\n    def run(self): pass\n')
        self.build(self.group('clients', 'sample', 'sample.first', 'sample.second'))
        page = (self.output / 'clients/+Page.mdx').read_text()
        for module in ('first', 'second'):
            self.assertIn(f'id="sample.{module}--client"', page)
            self.assertIn(f'id="sample.{module}--client.run"', page)
            self.assertIn(f'[`Client`](/reference/clients#sample.{module}--client)', page)
        anchors = re.findall(r'<a id="([^"]+)"', page)
        self.assertEqual(len(anchors), len(set(anchors)))
        migration = json.loads((self.output / '.autodoc-routes.json').read_text())
        self.assertEqual(migration['/reference/first#client'],
                         '/reference/clients#sample.first--client')
        self.assertEqual(migration['/reference/second#client.run'],
                         '/reference/clients#sample.second--client.run')
        self.assert_internal_links_resolve()

    def test_reexports_and_inherited_members_link_across_groups(self):
        self.write('__init__.py', 'from .child import Child\n')
        self.write('base.py', 'class Base:\n    count: int = 2\n    def run(self): pass\n')
        self.write('child.py', 'from .base import Base\n__all__ = ["Child"]\nclass Child(Base): pass\n')
        self.build(self.group('overview', 'sample'), self.group('foundation', 'sample.base'),
                   self.group('clients', 'sample.child'))
        overview = (self.output / 'overview/+Page.mdx').read_text()
        child = (self.output / 'clients/+Page.mdx').read_text()
        self.assertIn('[`Child`](/reference/clients#sample.child--child)', overview)
        self.assertIn('`run` — from [`sample.base.Base`](/reference/foundation#sample.base--base)', child)
        self.assertIn('`count` — from [`sample.base.Base`](/reference/foundation#sample.base--base)', child)
        self.assert_internal_links_resolve()

    def test_module_to_group_migration_removes_only_manifest_owned_pages(self):
        self.write('old.py', 'def run(): pass\n')
        generate(self.source, self.output, 'sample')
        manual = self.output / 'manual/+Page.mdx'
        manual.parent.mkdir()
        manual.write_text('handwritten guide')
        outside = self.root / 'outside.mdx'
        outside.write_text('outside output')
        manifest = self.output / '.autodoc-py.json'
        old = json.loads(manifest.read_text())
        manifest.write_text(json.dumps(old + ['../outside.mdx']))
        self.build(self.group('configuration', 'sample', 'sample.old'))
        self.assertFalse((self.output / '+Page.mdx').exists())
        self.assertFalse((self.output / 'old/+Page.mdx').exists())
        self.assertEqual(manual.read_text(), 'handwritten guide')
        self.assertEqual(outside.read_text(), 'outside output')
        self.assertEqual(json.loads(manifest.read_text()), ['configuration/+Page.mdx'])
        self.build(self.group('core', 'sample', 'sample.old'))
        self.assertFalse((self.output / 'configuration/+Page.mdx').exists())
        self.assertEqual(manual.read_text(), 'handwritten guide')

    def test_invalid_group_configs_leave_previous_build_untouched(self):
        self.write('api.py', 'def run(): pass\n')
        valid = self.group('core', 'sample', 'sample.api')
        self.build(valid)
        original = self.snapshot()
        invalid = [
            [self.group('../escape', 'sample', 'sample.api')],
            [valid, self.group('core', 'sample')],
            [valid, self.group('duplicate', 'sample.api')],
            [self.group('missing', 'sample', 'sample.missing')],
            [self.group('incomplete', 'sample')],
            [valid, {'slug': 'missing-metadata', 'modules': []}],
        ]
        for pages in invalid:
            with self.subTest(pages=pages):
                with self.assertRaises((ValueError, KeyError)):
                    self.build(*pages)
                self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.root / 'escape').exists())

    def test_invalid_first_build_does_not_create_output(self):
        with self.assertRaises(ValueError):
            self.build(self.group('core', 'sample.nonexistent'))
        self.assertFalse(self.output.exists())

    def test_public_singleton_is_documented_without_executing_constructor(self):
        marker = self.root / 'executed'
        self.write('__init__.py', 'from .env import EnvVar\n')
        self.write('env.py', f'''from pathlib import Path
raise RuntimeError("never import this package")
class _EnvVar:
    """Read environment values lazily."""
    def __init__(self):
        Path({str(marker)!r}).write_text("executed")
        raise RuntimeError("never execute constructors")
    def __call__(self, name: str, default=None):
        """Read one variable."""
    def __or__(self, fallback):
        """Set a fallback."""
    def _resolve(self): pass
EnvVar = _EnvVar()
''')
        self.build(self.group('overview', 'sample'),
                   self.group('environment', 'sample.env', symbols={'sample.env': ['EnvVar']}))
        page = (self.output / 'environment/+Page.mdx').read_text()
        self.assertIn('EnvVar = _EnvVar()', page)
        self.assertIn('### `EnvVar`', page)
        self.assertIn('#### `EnvVar.__call__`', page)
        self.assertIn('#### `EnvVar.__or__`', page)
        self.assertIn('| singleton |', page)
        self.assertNotIn('### _EnvVar', page)
        self.assertNotIn('_resolve', page)
        self.assertFalse(marker.exists())
        self.assert_internal_links_resolve()


    def test_group_slug_matching_module_route_preserves_index_targets(self):
        self.write('cli/__init__.py', 'from .parse import parse_args\ndef help_text(): pass\n')
        self.write('cli/parse.py', 'def parse_args(): pass\n')
        self.build(self.group('overview', 'sample'),
                   self.group('cli', 'sample.cli', 'sample.cli.parse'))
        page = (self.output / 'cli/+Page.mdx').read_text()
        self.assertIn('[`help_text`](/reference/cli#sample.cli--help_text)', page)
        self.assertIn('[`parse_args`](/reference/cli#sample.cli.parse--parse_args)', page)
        self.assertNotIn('#sample.cli--sample.', page)
        self.assert_internal_links_resolve()

    def test_excluded_or_filtered_cross_references_fail_before_writes(self):
        self.write('__init__.py', 'from .api import Client\n')
        self.write('api.py', 'class Client: pass\n')
        self.build(self.group('overview', 'sample'), self.group('clients', 'sample.api'))
        original = self.snapshot()
        invalid = [
            {'pages': [self.group('overview', 'sample')], 'exclude': ['sample.api']},
            {'pages': [self.group('overview', 'sample'),
                       self.group('clients', 'sample.api', symbols={'sample.api': []})]},
        ]
        for spec in invalid:
            with self.subTest(spec=spec):
                with self.assertRaisesRegex(ValueError, 'Link targets'):
                    generate_grouped(self.source, self.output, 'sample', spec,
                                     url_prefix='/reference')
                self.assertEqual(self.snapshot(), original)

if __name__ == '__main__':
    unittest.main()
