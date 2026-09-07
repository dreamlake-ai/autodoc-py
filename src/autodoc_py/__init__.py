"""Generate Dockit MDX from Python source without importing the package."""
import argparse
import ast
import json
from pathlib import Path
import re


def prose(value):
    """Escape MDX expressions/JSX outside fenced and inline code."""
    parts = re.split(r'(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~|`[^`\n]+`)', value, flags=re.S)
    return ''.join(part if index % 2 else part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('{', '&#123;').replace('}', '&#125;') for index, part in enumerate(parts))


def signature(node):
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(base) for base in node.bases]
        bases += [ast.unparse(keyword) for keyword in node.keywords]
        return f"class {node.name}" + (f"({', '.join(bases)})" if bases else '')
    prefix = 'async def' if isinstance(node, ast.AsyncFunctionDef) else 'def'
    result = f'{prefix} {node.name}({ast.unparse(node.args)})'
    if node.returns:
        result += f' -> {ast.unparse(node.returns)}'
    return result


def declaration(node, qualified, source_url):
    lines = [f'## {qualified}', '', '```python', signature(node), '```', '']
    if source_url:
        lines += [f'[Source]({source_url}#L{node.lineno})', '']
    doc = ast.get_docstring(node)
    if doc:
        lines += [prose(doc), '']
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (not child.name.startswith('_') or child.name == '__init__'):
                lines += declaration(child, f'{qualified}.{child.name}', source_url)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and not child.target.id.startswith('_'):
                lines += ['```python', ast.unparse(child), '```', '']
    return lines


def render(path, module, section='Python API', order=0, source_url=None):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    lines = ['---', f'title: {json.dumps(module)}', f'section: {json.dumps(section)}', f'order: {order}', f'description: {json.dumps("Python API reference for " + module)}', '---', '', f'# {module}', '']
    if ast.get_docstring(tree):
        lines += [prose(ast.get_docstring(tree)), '']
    exports = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets):
            try:
                value = ast.literal_eval(node.value)
                if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                    exports = set(value)
            except (ValueError, TypeError):
                pass
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in exports if exports is not None else not node.name.startswith('_'):
                lines += declaration(node, node.name, source_url)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not node.target.id.startswith('_'):
            lines += ['```python', ast.unparse(node), '```', '']
    return '\n'.join(lines)


def generate(source, output, module, section='Python API', source_url=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError(f'Package directory does not exist: {source}')
    paths = sorted(path for path in source.rglob('*.py') if not any(part.startswith('.') or part in {'__pycache__', '__tests__', 'tests'} for part in path.relative_to(source).parts))
    if not paths:
        raise ValueError(f'No Python sources found in {source}')
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
        pages.append((target, render(path, name, section, len(pages), url)))
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
    return len(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Package directory (for example src/vuer)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--module', required=True, help='Import name of the source package')
    parser.add_argument('--section', default='Python API')
    parser.add_argument('--source-url', help='URL of the package directory at this exact revision')
    args = parser.parse_args()
    try:
        count = generate(args.source, args.output, args.module, args.section, args.source_url)
    except (ValueError, SyntaxError, OSError) as error:
        parser.error(str(error))
    print(f'Generated {count} Dockit API pages in {args.output}')
