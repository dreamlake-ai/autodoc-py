"""Explicit topic pages for projects whose source modules are not reader-facing units."""
import ast
import fnmatch
import json
from pathlib import Path
import re
import tokenize


def anchor(text):
    return re.sub(r'[^a-z0-9_.-]', '', text.lower().replace(' ', '-'))


def generate_grouped(source, output, module, config, section='Python API', source_url=None, url_prefix='/api'):
    from . import SourceIndex, render, add_styles
    source, output = Path(source).resolve(), Path(output).resolve()
    spec = json.loads(Path(config).read_text()) if isinstance(config, (str, Path)) else config
    sources = {}
    for path in sorted(source.rglob('*.py')):
        parts = list(path.relative_to(source).with_suffix('').parts)
        if any(p.startswith('.') or p in {'tests', '__tests__', '__pycache__'} for p in parts):
            continue
        if parts[-1] == '__init__': parts.pop()
        if any(p.startswith('_') for p in parts): continue
        with tokenize.open(path) as stream:
            sources['.'.join([module, *parts])] = (path, ast.parse(stream.read(), filename=str(path)))
    if not sources: raise ValueError('No public Python modules found')
    index = SourceIndex(sources, module)
    groups = spec['pages']
    assigned, slugs = {}, set()
    for group in groups:
        slug = group['slug']
        if not slug or not re.fullmatch(r'[a-z0-9]+(?:[-/][a-z0-9]+)*', slug) or slug in slugs:
            raise ValueError(f'Invalid or duplicate page slug: {slug}')
        slugs.add(slug)
        for pattern in group['modules']:
            matched = [name for name in sources if fnmatch.fnmatchcase(name, pattern)]
            if not matched: raise ValueError(f'Module pattern matches nothing: {pattern}')
            for name in matched:
                if name in assigned: raise ValueError(f'Module assigned more than once: {name}')
                assigned[name] = group
    excluded = spec.get('exclude', {})
    for name in sources:
        if name not in assigned and not any(fnmatch.fnmatchcase(name, p) for p in excluded):
            raise ValueError(f'Module needs a page or an explicit exclusion: {name}')
    def route(name):
        return url_prefix.rstrip('/') + '/' + assigned[name]['slug']
    def target(name, fragment=''):
        return route(name) + '#' + anchor(name) + ('--' + fragment if fragment else '')
    old_routes = {url_prefix.rstrip('/') + ('/' + '/'.join(name.split('.')[len(module.split('.')):]) if name != module else ''): name for name in sources}
    def rewrite(match):
        url = match.group(1)
        path, _, fragment = url.partition('#')
        if '--' in fragment or fragment in {anchor(name) for name in assigned}:
            return match.group(0)
        name = old_routes.get(path.rstrip('/'))
        if name in assigned: return '](' + target(name, fragment) + ')'
        return match.group(0)
    pages, migration = [], {}
    for group in groups:
        names = [name for name in sources if assigned.get(name) is group]
        lines = ['---', f'title: {json.dumps(group["title"])}', f'section: {json.dumps(section)}', f'order: {group.get("order", len(pages))}', f'description: {json.dumps(group["description"])}', 'tocLevel: 3', '---', '', '# ' + group['title'], '', group.get('intro', group['description']), '', '## API index', '', '| Name | Kind | Defined in |', '| --- | --- | --- |']
        bodies = []
        for name in names:
            path, tree = sources[name]
            url = source_url.rstrip('/') + '/' + path.relative_to(source).as_posix() if source_url else None
            include = group.get("symbols", {}).get(name)
            text = render(path, name, section, 0, url, index, url_prefix, include)
            body = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.S).strip()
            # Namespace every heading, including docstring headings. Fences are opaque.
            used, fenced, out = {}, None, []
            for line in body.splitlines():
                fence = re.match(r'^\s*(`{3,}|~{3,})', line)
                if fence:
                    mark = fence[1]
                    if fenced is None: fenced = mark
                    elif mark[0] == fenced[0] and len(mark) >= len(fenced): fenced = None
                    out.append(line); continue
                heading = re.match(r'^(#{1,6}) (.+)$', line) if fenced is None else None
                if heading:
                    level, label = len(heading[1]), heading[2]
                    display_level = 4 if level == 2 and '.' in label.strip('`') else min(level + 1, 6)
                    slug = anchor(label)
                    count = used.get(slug, 0); used[slug] = count + 1
                    if count: slug += '-' + str(count)
                    ident = anchor(name) if level == 1 else anchor(name) + '--' + slug
                    out += [f'<a id="{ident}" />', '', '#' * display_level + ' ' + label]
                    migration[next(k for k,v in old_routes.items() if v == name) + ('#' + slug if level > 1 else '')] = route(name) + '#' + ident
                else:
                    def namespace_id(match):
                        return 'id="' + anchor(name) + '--' + match[1] + '"'
                    out.append(re.sub(r'id="([^"]+)"', namespace_id, line))
            bodies.append('\n'.join(out))
            for symbol, (owner, node) in index.exports(name).items():
                if owner != name or (include is not None and symbol not in include): continue
                kind = getattr(node, '_autodoc_kind', None) or ('singleton' if hasattr(node, '_autodoc_assignment') else ('class' if isinstance(node, ast.ClassDef) else 'function'))
                lines.append(f'| [`{symbol}`]({target(name, anchor(node.name))}) | {kind} | `{name}` |')
        lines += ['', *bodies, '']
        content = re.sub(r'\]\(([^)]+)\)', rewrite, '\n'.join(lines))
        content = re.sub(r'href="([^"]+)"', lambda m: 'href="' + rewrite(m)[2:-1] + '"' if rewrite(m).startswith('](') else m[0], content)
        pages.append((output / group['slug'] / '+Page.mdx', content))
    destinations = {url_prefix.rstrip('/') + '/' + str(path.parent.relative_to(output)): set(re.findall(r'<a id="([^"]+)"', content)) for path, content in pages}
    for _, content in pages:
        for href in re.findall(r'\]\(([^)]+)\)', content):
            path, _, fragment = href.partition('#')
            if path in destinations and fragment and '--' in fragment and fragment not in destinations[path]:
                raise ValueError(f'Link targets a symbol omitted from its page: {href}')
            if path in old_routes and path not in destinations and old_routes[path] not in assigned:
                raise ValueError(f'Link targets an excluded module: {href}')
    # Validate everything before replacing files; only remove files owned by this generator.
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / '.autodoc-py.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    current = [str(p.relative_to(output)) for p,_ in pages]
    for old in previous:
        stale = (output / old).resolve()
        if stale.is_relative_to(output) and old not in current and stale.is_file(): stale.unlink()
    for path, content in pages:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    manifest.write_text(json.dumps(current, indent=2) + '\n')
    (output / '.autodoc-routes.json').write_text(json.dumps(migration, indent=2) + '\n')
    add_styles(output, pages)
    return len(pages)
