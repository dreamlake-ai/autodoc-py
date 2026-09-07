"""Generate Dockit MDX from Python source without importing the package."""
import argparse
import ast
import copy
import json
from pathlib import Path
import re
import tokenize
from .docstrings import format_docstring
from .data import module_data


def fence(value: str, language: str = "python") -> str:
    """Choose a fence longer than any backtick run in the source."""
    longest = max((len(m.group()) for m in re.finditer(r"`+", value)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{value}\n{marker}"


def prose(value: str) -> str:
    """Preserve Markdown code, escape MDX expressions and JSX in prose.

    Python docstrings are data, never executable MDX. RST roles/directives are
    retained as readable text; this is intentionally not a Sphinx interpreter.
    """
    lines = []
    active = None
    for line in value.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if active:
            lines.append(line)
            if re.fullmatch(r" {0,3}" + re.escape(active[0]) + "{" + str(len(active)) + r",}[ \t]*", line):
                active = None
            continue
        if marker:
            active = marker[1]
            lines.append(line)
            continue
        # Inline code is literal in MDX and should retain exact syntax.
        parts = re.split(r"((?<!`)(`+)(?!`).*?(?<!`)\2(?!`))", line)
        # re.split also returns the captured delimiter; remove those captures.
        parts = [part for i, part in enumerate(parts) if i % 3 != 2]
        for i in range(0, len(parts), 2):
            parts[i] = (parts[i].replace("&", "&amp;")
                        .replace("<", "&lt;").replace(">", "&gt;")
                        .replace("{", "&#123;").replace("}", "&#125;"))
        escaped = "".join(parts)
        # MDX recognizes ESM declarations even without JSX or braces.
        esm = re.match(r"^( {0,3})(import|export)\s", escaped)
        if esm:
            start = len(esm[1])
            escaped = escaped[:start] + "&#" + str(ord(escaped[start])) + ";" + escaped[start + 1:]
        lines.append(escaped)
    if active:
        lines.append(active)
    return "\n".join(lines)


def assignment_aliases(tree):
    """Resolve local public singleton constructors statically; never call them."""
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in classes:
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith('_'):
                    alias = copy.deepcopy(classes[node.value.func.id])
                    alias.name = target.id
                    alias.lineno = node.lineno
                    alias._autodoc_assignment = ast.unparse(node)
                    result[target.id] = alias
    return result


def signature(node):
    if hasattr(node, '_autodoc_assignment'):
        return node._autodoc_assignment
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return ast.unparse(node)
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(base) for base in node.bases]
        bases += [ast.unparse(keyword) for keyword in node.keywords]
        return f"class {node.name}" + (f"({', '.join(bases)})" if bases else '')
    prefix = 'async def' if isinstance(node, ast.AsyncFunctionDef) else 'def'
    result = f'{prefix} {node.name}({ast.unparse(node.args)})'
    if node.returns:
        result += f' -> {ast.unparse(node.returns)}'
    return result


def declaration(node, qualified, source_url, index=None, module=None, url_prefix='/api'):
    from .presentation import render_declaration
    return render_declaration(node, qualified, source_url, index, module, url_prefix)


class SourceIndex:
    """Resolve local public re-exports and base classes without executing code."""
    def __init__(self, sources, root=None):
        self.sources = sources
        self.root = root or min(sources, key=lambda name: len(name.split('.')))

    def route(self, module, url_prefix):
        relative = module[len(self.root):].strip('.').replace('.', '/')
        return url_prefix.rstrip('/') + ('/' + relative if relative else '')

    def exports(self, module, seen=None, public=True):
        seen = set() if seen is None else set(seen)
        if module in seen or module not in self.sources:
            return {}
        seen.add(module)
        path, tree = self.sources[module]
        result = {}
        explicit = None
        nodes = list(tree.body)
        for statement in tree.body:
            if isinstance(statement, ast.Try):
                nodes.extend(n for n in statement.body if isinstance(n, (ast.Import, ast.ImportFrom)))
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                result[node.name] = (module, node)
            elif isinstance(node, ast.ImportFrom):
                base = module if path.name == '__init__.py' else module.rpartition('.')[0]
                if node.level:
                    pieces = base.split('.')
                    imported = '.'.join(pieces[:len(pieces) - node.level + 1] + ([node.module] if node.module else []))
                else:
                    imported = node.module or ''
                available = self.exports(imported, seen)
                for alias in node.names:
                    if alias.name == '*':
                        result.update(available)
                    elif alias.name in available:
                        result[alias.asname or alias.name] = available[alias.name]
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets):
                try:
                    explicit = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
        result.update({name: (module, node) for name, node in module_data(tree).items()})
        result.update({name: (module, node) for name, node in assignment_aliases(tree).items()})
        if not public:
            return result
        return {name: value for name, value in result.items() if name in explicit} if isinstance(explicit, (list, tuple)) else {name: value for name, value in result.items() if not name.startswith('_')}

    def inherited(self, module, node, seen=None):
        seen = set() if seen is None else set(seen)
        identity = (module, node.name)
        if identity in seen:
            return []
        seen.add(identity)
        def names(item):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return [item.name]
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                return [item.target.id]
            if isinstance(item, ast.Assign):
                return [target.id for target in item.targets if isinstance(target, ast.Name)]
            return []
        own = {name for child in node.body for name in names(child)}
        result = []
        available = self.exports(module, public=False)
        for base in node.bases:
            resolved = available.get(ast.unparse(base))
            if not resolved or not isinstance(resolved[1], ast.ClassDef):
                continue
            base_module, base_node = resolved
            candidates = [(name, base_module, base_node.name) for child in base_node.body for name in names(child)]
            candidates += self.inherited(base_module, base_node, seen)
            for name, owner_module, owner_class in candidates:
                if name not in own and (not name.startswith('_') or name == '__init__'):
                    own.add(name)
                    result.append((name, owner_module, owner_class))
        return result


def render(path, module, section='Python API', order=0, source_url=None, index=None, url_prefix='/api', include=None):
    with tokenize.open(path) as stream:
        tree = ast.parse(stream.read(), filename=str(path))
    lines = ['---', f'title: {json.dumps(module)}', f'section: {json.dumps(section)}', f'order: {order}', f'description: {json.dumps("Python API reference for " + module)}', '---', '', f'# {module}', '']
    if ast.get_docstring(tree):
        lines += [prose(format_docstring(ast.get_docstring(tree))), '']
    exports = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets):
            try:
                value = ast.literal_eval(node.value)
                if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                    exports = set(value)
            except (ValueError, TypeError):
                pass
    definitions = {node.name: node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if definitions[node.name] is not node:
                continue
            if include is not None and node.name not in include:
                continue
            if node.name in exports if exports is not None else not node.name.startswith('_'):
                lines += declaration(node, node.name, source_url, index, module, url_prefix)
    for name, node in module_data(tree).items():
        if (include is None or name in include) and (exports is None or name in exports):
            lines += declaration(node, name, source_url, index, module, url_prefix)
    for name, node in assignment_aliases(tree).items():
        if (include is None or name in include) and (exports is None or name in exports):
            lines += declaration(node, name, source_url, index, module, url_prefix)
    if index:
        reexports = [(name, owner, node) for name, (owner, node) in index.exports(module).items() if owner != module]
        if reexports:
            lines += ['## Public imports', '', 'These symbols are available from this module. Their definitions are documented in the linked modules.', '']
            for name, owner, node in reexports:
                route = index.route(owner, url_prefix)
                lines += [f'- [`{name}`]({route}#{node.name.lower()}) — `{owner}.{node.name}`']
            lines += ['']
    return '\n'.join(lines)


def generate(source, output, module, section='Python API', source_url=None, url_prefix='/api'):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError(f'Package directory does not exist: {source}')
    paths = sorted(path for path in source.rglob('*.py') if not any(part.startswith('.') or part in {'__pycache__', '__tests__', 'tests'} for part in path.relative_to(source).parts))
    if not paths:
        raise ValueError(f'No Python sources found in {source}')
    sources = {}
    for path in paths:
        components = list(path.relative_to(source).with_suffix('').parts)
        if components[-1] == '__init__':
            components.pop()
        with tokenize.open(path) as stream:
            sources['.'.join([module, *components])] = (path, ast.parse(stream.read(), filename=str(path)))
    index = SourceIndex(sources, module)
    pages = []
    # Parse every file before writing, so syntax errors cannot produce half a build.
    for path in paths:
        relative = path.relative_to(source)
        components = list(relative.with_suffix('').parts)
        if components[-1] == '__init__':
            components.pop()
        if any(part.startswith('_') for part in components):
            continue
        name = '.'.join([module, *components])
        target = output.joinpath(*components, '+Page.mdx')
        url = f'{source_url.rstrip("/")}/{relative.as_posix()}' if source_url else None
        pages.append((target, render(path, name, section, len(pages), url, index, url_prefix)))
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / '.autodoc-py.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    current = [str(path.relative_to(output)) for path, _ in pages]
    for old in previous:
        stale = (output / old).resolve()
        if stale.is_relative_to(output) and old not in current and stale.is_file():
            stale.unlink()
    for path, content in pages:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    manifest.write_text(json.dumps(current, indent=2) + '\n')
    add_styles(output, pages)
    return len(pages)


def add_styles(output, pages):
    """Ship the renderer stylesheet with generated pages, independent of Dockit."""
    import os
    from importlib.resources import files
    (output / 'autodoc.css').write_text(files('autodoc_py').joinpath('api.css').read_text())
    for path, _ in pages:
        text = path.read_text()
        css = os.path.relpath(output / 'autodoc.css', path.parent).replace(os.sep, '/')
        if not css.startswith('.'): css = './' + css
        text = re.sub(r'^(---\n.*?\n---\n)', lambda m: m[0] + '\nimport ' + json.dumps(css) + '\n', text, count=1, flags=re.S)
        path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Package directory (for example src/vuer)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--module', required=True, help='Import name of the source package')
    parser.add_argument('--section', default='Python API')
    parser.add_argument('--url-prefix', default='/api', help='Public route of the generated API root')
    parser.add_argument('--page-map', type=Path, help='JSON topic pages with title, slug, description and module patterns')
    parser.add_argument('--source-url', help='URL of the package directory at this exact revision')
    args = parser.parse_args()
    try:
        if args.page_map:
            from .grouped import generate_grouped
            count = generate_grouped(args.source, args.output, args.module, args.page_map, args.section, args.source_url, args.url_prefix)
        else:
            count = generate(args.source, args.output, args.module, args.section, args.source_url, args.url_prefix)
    except (ValueError, SyntaxError, OSError) as error:
        parser.error(str(error))
    print(f'Generated {count} Dockit API pages in {args.output}')
