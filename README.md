# autodoc-py

Generate Python API reference pages for [DreamLake Dockit](https://dockit.dreamlake.ai). Python 3.10+; no runtime dependencies. Source is parsed with Python's AST, never imported, so historical versions do not need their dependencies installed and application startup code does not execute.

```sh
python -m pip install git+https://github.com/dreamlake-ai/autodoc-py.git
autodoc-py src/vuer --module vuer --output docs/pages/api \
  --section 'Python API' \
  --source-url https://github.com/vuer-ai/vuer/blob/main/src/vuer
```

For reproducible builds, pin installation to a commit and use the documented revision's commit SHA in `--source-url`. Run the command on each version branch against its matching source directory (`vuer` or `src/vuer`). The output follows Dockit's `pages/**/+Page.mdx` convention and includes frontmatter for navigation and search.

The generator emits module docstrings, public classes and functions, class methods and constructors, annotations, signatures, and source links. Literal `__all__` controls which locally defined classes/functions are included. Private modules and tests are skipped. MDX expression and JSX characters in prose are escaped, while inline and fenced code are preserved. A manifest tracks generated files so removed modules disappear without deleting manual pages. All Python files are parsed before output changes.

This is static source documentation: dynamically generated members, inherited members, imported re-exports, and runtime signatures are not resolved. Docstrings retain their text; Sphinx roles and directives are not executed. Use the preserved Sphinx builds when exact historical Sphinx rendering is required. Syntax must be supported by the Python interpreter running the generator.

Development:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```
