"""Read documented Python data declarations without evaluating their values."""
import ast
import copy


def _type_annotation(annotation):
    """Recognize explicit TypeAlias declarations, including qualified spellings."""
    if isinstance(annotation, ast.Name):
        return annotation.id == 'TypeAlias'
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == 'TypeAlias'
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value in {'TypeAlias', 'typing.TypeAlias', 'typing_extensions.TypeAlias'}
    return False


def _alias_expression(value):
    # A subscription or union in an unannotated assignment is conventional alias
    # syntax. Keep the expression intact rather than importing its referenced types.
    return (isinstance(value, ast.Subscript)
            or isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr))


def _declarations(body, *, module):
    type_alias = getattr(ast, 'TypeAlias', ())
    for index, original in enumerate(body):
        explicit_alias = bool(type_alias) and isinstance(original, type_alias)
        if isinstance(original, ast.Assign):
            targets = original.targets
            annotation = None
        elif isinstance(original, ast.AnnAssign):
            targets = [original.target]
            annotation = original.annotation
        elif explicit_alias:
            targets = [original.name]
            annotation = None
        else:
            continue
        value = getattr(original, 'value', None)
        # Public singleton constructors are handled by assignment_aliases. Class
        # defaults may be calls (e.g. a Field descriptor); record their source only.
        if module and isinstance(value, ast.Call):
            continue
        following = body[index + 1] if index + 1 < len(body) else None
        doc = (following.value.value if isinstance(following, ast.Expr)
               and isinstance(following.value, ast.Constant)
               and isinstance(following.value.value, str) else '')
        for target in targets:
            if not isinstance(target, ast.Name) or target.id.startswith('_'):
                continue
            node = copy.deepcopy(original)
            if explicit_alias:
                # TypeAlias.name is itself an AST node. Normalize to Assign so
                # the common .name metadata does not invalidate ast.unparse.
                node = ast.copy_location(ast.Assign(targets=[copy.deepcopy(target)],
                                         value=copy.deepcopy(value)), original)
                node._autodoc_type_params = copy.deepcopy(original.type_params)
            # Split chained assignments into independently linkable declarations.
            if isinstance(node, ast.Assign):
                node.targets = [copy.deepcopy(target)]
            node.name = target.id
            node._autodoc_kind = ('type alias' if explicit_alias or _type_annotation(annotation)
                                 or module and annotation is None and _alias_expression(value)
                                 else 'attribute')
            node._autodoc_doc = doc
            yield node


def module_data(tree):
    """Return public aliases/constants from direct module-level declarations.

    Assignment metadata retains its original AST annotation and value, along with
    a public name, declaration kind, and immediately following attribute docstring.
    Later declarations of the same name replace earlier ones.
    """
    return {node.name: node for node in _declarations(tree.body, module=True)}


def class_fields(class_node):
    """Return declared public class fields, without inferring runtime attributes."""
    return list(_declarations(class_node.body, module=False))
