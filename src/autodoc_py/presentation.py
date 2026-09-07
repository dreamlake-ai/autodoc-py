"""Semantic, framework-independent Python reference cards emitted as MDX."""
import ast
import copy
import html
import re
import textwrap


def escape(value):
    return html.escape(str(value), quote=True).replace('{', '&#123;').replace('}', '&#125;').replace('_', '&#95;').replace('*', '&#42;').replace('`', '&#96;')


def documentation(raw):
    """Extract Google and Sphinx parameter fields without running directives."""
    params, types, returns, raises, narrative = {}, {}, {}, {}, []
    lines = (raw or '').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        rst = re.match(r'^:(param|type|returns?|rtype|raises?)\s*([^:]*):\s*(.*)', line)
        google = re.match(r'^(Args|Arguments|Parameters|Keyword Args|Returns|Yields|Raises):\s*$', line)
        if rst:
            kind, name, value = rst.groups(); j = i + 1
            while j < len(lines) and lines[j].startswith(' '):
                value += ' ' + lines[j].strip(); j += 1
            if kind == 'param':
                pieces = name.strip().split(); key = pieces[-1] if pieces else ''
                params[key] = value
                if len(pieces) > 1: types[key] = ' '.join(pieces[:-1])
            elif kind == 'type': types[name.strip()] = value
            elif kind == 'rtype': returns['type'] = value
            elif kind.startswith('return'): returns['description'] = value
            else: raises[name.strip()] = value
            i = j; continue
        if google:
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].startswith(' ')): j += 1
            body = textwrap.dedent('\n'.join(lines[i+1:j])).strip()
            kind = google[1]
            if body:
                if kind in {'Returns', 'Yields'}:
                    first, _, rest = body.partition('\n')
                    if ':' in first:
                        typ, desc = first.split(':', 1); returns.update(type=typ.strip(), description=(desc+' '+rest).strip())
                    else: returns['description'] = body
                else:
                    key = None
                    for item in body.splitlines():
                        match = re.match(r'^([*\w][\w.*-]*)(?:\s*\((.*?)\))?:\s*(.*)', item)
                        if match:
                            key, typ, desc = match.groups()
                            (raises if kind == 'Raises' else params)[key] = desc
                            if typ: types[key] = typ
                        elif key and item.strip():
                            target = raises if kind == 'Raises' else params
                            target[key] += ' ' + item.strip()
                i = j; continue
        narrative.append(line); i += 1
    return '\n'.join(narrative).strip(), params, types, returns, raises


def type_markup(value, index=None, module=None, url_prefix='/api'):
    """Link only locally resolved types; never guess an external target."""
    text = ast.unparse(value) if isinstance(value, ast.AST) else str(value or '')
    exports = index.exports(module, public=False) if index and module else {}
    result, pos = [], 0
    for match in re.finditer(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', text):
        result.append(escape(text[pos:match.start()])); name = match[0]
        resolved = exports.get(name)
        if resolved:
            owner, node = resolved
            route = index.route(owner, url_prefix) + '#' + node.name.lower()
            result.append(f'<a className="py-api-type" href="{html.escape(route, quote=True)}">{escape(name)}</a>')
        else: result.append(f'<span className="py-api-type">{escape(name)}</span>')
        pos = match.end()
    result.append(escape(text[pos:]))
    return ''.join(result) or '—'


def parameters(node, bound=False):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): return []
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    rows = []
    for n, (arg, default) in enumerate(zip(positional, defaults)):
        if bound and n == 0 and arg.arg in {'self', 'cls', '_cls'}: continue
        rows.append((arg.arg, arg.annotation, default, 'positional-only' if n < len(args.posonlyargs) else ''))
    if args.vararg: rows.append(('*' + args.vararg.arg, args.vararg.annotation, None, 'variadic'))
    rows += [(arg.arg, arg.annotation, default, 'keyword-only') for arg, default in zip(args.kwonlyargs, args.kw_defaults)]
    if args.kwarg: rows.append(('**' + args.kwarg.arg, args.kwarg.annotation, None, 'variadic'))
    return rows


def parameter_table(rows, descriptions, types, index, module, url_prefix):
    if not rows and not descriptions: return []
    all_rows = list(rows); known = {r[0].lstrip('*') for r in rows}
    for key in descriptions:
        if key.lstrip('*') not in known: all_rows.append((key, None, None, 'documented keyword'))
    out = ['<p className="py-api-section-label">Parameters</p>', '<table className="py-api-fields">\n<thead><tr><th>Parameter</th><th>Type / default</th><th>Description</th></tr></thead>\n<tbody>']
    for name, annotation, default, mode in all_rows:
        key = name.lstrip('*'); doc = descriptions.get(name, descriptions.get(key, ''))
        typ = type_markup(annotation or types.get(key), index, module, url_prefix)
        state = (' = ' + escape(ast.unparse(default))) if default is not None else (mode or 'required')
        detail = escape(doc) or ('Keyword-only parameter.' if mode == 'keyword-only' else '—')
        out.append(f'<tr><td><code>{escape(name)}</code></td><td><code>{typ}</code><br /><span className="py-api-default">{state}</span></td><td>{detail}</td></tr>')
    return out + ['</tbody>\n</table>', '']


def decorators(node):
    return [ast.unparse(d) for d in getattr(node, 'decorator_list', [])]


def kind(node, qualified):
    if hasattr(node, '_autodoc_kind'): return node._autodoc_kind
    if hasattr(node, '_autodoc_assignment'): return 'callable singleton'
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b).split('.')[-1] for b in node.bases]
        if 'NamedTuple' in bases: return 'named tuple'
        if 'TypedDict' in bases: return 'typed dictionary'
        if any(d.split('(')[0].endswith('dataclass') for d in decorators(node)): return 'dataclass'
        return 'class'
    decs = decorators(node)
    if 'property' in decs or any(d.endswith('.setter') for d in decs): return 'property'
    prefix = 'async ' if isinstance(node, ast.AsyncFunctionDef) else ''
    if 'classmethod' in decs: return prefix + 'class method'
    if 'staticmethod' in decs: return prefix + 'static method'
    return prefix + ('method' if '.' in qualified else 'function')


def constructor(node):
    if not isinstance(node, ast.ClassDef): return None
    return next((n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == '__init__'), None)


def parameter_signature(rows, index, module, url_prefix):
    """Render Python call separators consistently for functions and constructors."""
    parts = []
    for position, (name, annotation, default, mode) in enumerate(rows):
        if mode == 'keyword-only' and (position == 0 or rows[position - 1][3] not in {'keyword-only', 'variadic'}):
            parts.append('*')
        part = '<span className="py-api-param">' + escape(name) + '</span>'
        if annotation:
            part += ': ' + type_markup(annotation, index, module, url_prefix)
        if default is not None:
            part += ' = <span className="py-api-default">' + escape(ast.unparse(default)) + '</span>'
        parts.append(part)
        if mode == 'positional-only' and (position + 1 == len(rows) or rows[position + 1][3] != 'positional-only'):
            parts.append('/')
    return ', '.join(parts)


def signature_markup(node, qualified, index, module, url_prefix):
    from . import signature
    category = kind(node, qualified)
    if isinstance(node, ast.ClassDef) and not hasattr(node, '_autodoc_assignment'):
        ctor = constructor(node)
        rows = parameters(ctor, True) if ctor else []
        if category in {'named tuple', 'dataclass', 'typed dictionary'} and not ctor:
            rows = [(n.target.id, n.annotation, n.value, '') for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and not n.target.id.startswith('_')]
        if ctor is not None or rows:
            return escape(qualified) + '(' + parameter_signature(rows, index, module, url_prefix) + ')'
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if category == 'property':
            return escape(qualified) + (': ' + type_markup(node.returns,index,module,url_prefix) if node.returns else '')
        rows = parameters(node, '.' in qualified and 'staticmethod' not in decorators(node))
        result = ('async ' if isinstance(node, ast.AsyncFunctionDef) else '') + escape(qualified) + '(' + parameter_signature(rows, index, module, url_prefix) + ')'
        if node.returns: result += ' → '+type_markup(node.returns,index,module,url_prefix)
        return result
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        result = escape(node.name)
        if getattr(node, 'annotation', None): result += ': ' + type_markup(node.annotation, index, module, url_prefix)
        if getattr(node, 'value', None):
            value = type_markup(node.value, index, module, url_prefix) if category == 'type alias' else escape(ast.unparse(node.value))
            result += ' = ' + value
        return result
    return escape(signature(node))


def render_declaration(node, qualified, source_url, index=None, module=None, url_prefix='/api'):
    from . import prose, fence
    from .docstrings import format_docstring
    from .data import class_fields
    category=kind(node,qualified)
    raw = getattr(node,'_autodoc_doc',None) or (ast.get_docstring(node) if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) else '')
    narrative, docs, types, returns, raises = documentation(raw)
    heading=('###' if '.' in qualified else '##') + f' `{qualified}`'
    lines=[heading,'','<section className="py-api">','<div className="py-api-header">',f'<span className="py-api-kind">{escape(category)}</span>',f'<code className="py-api-name">{escape((module + '.') if module else '')}{escape(qualified)}</code>']
    if source_url: lines.append(f'<a className="py-api-source" href="{html.escape(source_url, quote=True)}#L{node.lineno}">Source ↗</a>')
    lines += ['</div>',f'<pre className="py-api-signature"><code>{signature_markup(node,qualified,index,module,url_prefix)}</code></pre>']
    if isinstance(node,ast.ClassDef) and node.bases:
        lines += ['<p className="py-api-meta">Bases: '+', '.join(type_markup(b,index,module,url_prefix) for b in node.bases)+'</p>']
    if getattr(node, '_autodoc_writable', False): lines += ['<p className="py-api-meta">Writable property</p>']
    lines += ['<div className="py-api-description">','']
    if narrative: lines += [prose(format_docstring(narrative)), '']
    callable_node=constructor(node) if isinstance(node,ast.ClassDef) else node
    if isinstance(node,ast.ClassDef) and callable_node:
        _, initdocs, inittypes, _, _ = documentation(ast.get_docstring(callable_node))
        docs={**initdocs,**docs};types={**inittypes,**types}
    rows=parameters(callable_node, isinstance(node,ast.ClassDef) or ('.' in qualified and 'staticmethod' not in decorators(node)))
    if isinstance(node,ast.ClassDef) and category in {'named tuple','dataclass','typed dictionary'} and not callable_node:
        rows=[(n.target.id,n.annotation,n.value,'') for n in node.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and not n.target.id.startswith('_')]
    if category != 'property': lines += parameter_table(rows,docs,types,index,module,url_prefix)
    ret = getattr(node,'returns',None) or returns.get('type')
    if ret or returns:
        label='Type' if category=='property' else 'Returns'
        lines += [f'<p className="py-api-section-label">{label}</p>', '<p>'+('<code>'+type_markup(ret,index,module,url_prefix)+'</code>' if ret else '')+((' — ' if ret else '')+escape(returns['description']) if returns.get('description') else '')+'</p>','']
    if raises:
        lines += ['<p className="py-api-section-label">Raises</p>','<ul>'+''.join('<li><code>'+type_markup(n,index,module,url_prefix)+'</code> — '+escape(d)+'</li>' for n,d in raises.items())+'</ul>','']
    if isinstance(node,ast.ClassDef):
        fields=class_fields(node)
        if fields:
            lines += ['<p className="py-api-section-label">Attributes</p>','<table className="py-api-fields">\n<thead><tr><th>Name</th><th>Type / value</th><th>Description</th></tr></thead>\n<tbody>']
            for field in fields:
                annotation=getattr(field,'annotation',None);value=getattr(field,'value',None)
                display=type_markup(annotation,index,module,url_prefix) if annotation else ''
                if value: display += (' = ' if display else '')+escape(ast.unparse(value))
                lines.append(f'<tr><td><a id="{escape(qualified.lower()+chr(46)+field.name.lower())}" /><code>{escape(field.name)}</code></td><td><code>{display or "—"}</code></td><td>{escape(field._autodoc_doc) or "—"}</td></tr>')
            lines += ['</tbody>\n</table>','']
        if index:
            inherited=index.inherited(module,node)
            if inherited:
                lines += ['<p className="py-api-section-label">Inherited members</p>','']
                for name,owner,owner_class in inherited:
                    route=index.route(owner,url_prefix)+'#'+owner_class.lower()
                    lines += [f'- `{name}` — from [`{owner}.{owner_class}`]({route})']
                lines += ['']
    lines += ['</div>','</section>','']
    if isinstance(node,ast.ClassDef):
        members={}
        for child in node.body:
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):
                if child.name in members and any(d.endswith('.setter') for d in decorators(child)):
                    members[child.name]._autodoc_writable = True
                else: members[child.name] = child
        for name,child in members.items():
            if not name.startswith('_') or name=='__init__' or (hasattr(node,'_autodoc_assignment') and name in {'__call__','__matmul__','__or__','__getitem__'}):
                lines += render_declaration(child,f'{qualified}.{name}',source_url,index,module,url_prefix)
    return lines
