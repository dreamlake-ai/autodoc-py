"""Small, conservative Google-style docstring to Markdown formatter.

Formatting is deliberately separate from MDX escaping. Only recognized section
bodies are transformed; ordinary Markdown is left intact.
"""
import re
import textwrap


_SECTION = re.compile(r"^( *)(Args|Arguments|Parameters|Keyword Args|Returns|Yields|Raises|Attributes|Example|Examples):\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _code(body):
    marker = '`' * max(3, 1 + max((len(m[0]) for m in re.finditer(r'`+', body)), default=0))
    return f'{marker}python\n{body}\n{marker}'


def _fields(body):
    """Turn field descriptions into list items, preserving continuation lines."""
    result = []
    for line in body.splitlines():
        field = re.match(r'^([*\w][\w.*-]*(?:\s*\([^\n]+\))?):\s*(.*)$', line)
        if field:
            name, description = field.groups()
            # Include type annotations with the parameter label, as readable code.
            result.append(f'- `{name}`: {description}')
        elif line.strip():
            result.append(('  ' if result and any(item.startswith('- ') for item in result) else '') + line.lstrip())
        else:
            result.append('')
    return '\n'.join(result)


def format_docstring(raw: str) -> str:
    """Format indented Google sections without mistaking ordinary prose for code.

    Callers should supply ``ast.get_docstring``'s cleaned text, then apply their
    usual MDX escaping to this result. Example code keeps literal braces and
    comments inside explicit fences because MDX does not support indented code.
    """
    lines = raw.splitlines()
    result = []
    active = None
    index = 0
    while index < len(lines):
        line = lines[index]
        marker = _FENCE.match(line)
        if active:
            result.append(line)
            if re.fullmatch(r' {0,3}' + re.escape(active[0]) + '{' + str(len(active)) + r',}[ \t]*', line):
                active = None
            index += 1
            continue
        if marker:
            active = marker[1]
            result.append(line)
            index += 1
            continue
        section = _SECTION.match(line)
        if not section:
            result.append(line)
            index += 1
            continue
        indent = len(section[1])
        end = index + 1
        while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip(' ')) > indent):
            end += 1
        body = textwrap.dedent('\n'.join(lines[index + 1:end])).strip('\n')
        if not body:
            result.append(line)
            index += 1
            continue
        title = section[2]
        result.extend([f'**{title}**', ''])
        if title in {'Example', 'Examples'}:
            # Already-fenced examples and Markdown lists remain Markdown.
            if _FENCE.match(body) or re.match(r'(?:[-*+] |\d+[.)] )', body):
                result.append(body)
            else:
                result.append(_code(body))
        else:
            result.append(_fields(body))
        result.append('')
        index = end
    return '\n'.join(result).rstrip('\n')
