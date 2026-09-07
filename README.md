# autodoc-py

Generate Python API reference pages for [DreamLake Dockit](https://dockit.dreamlake.ai). Python 3.10+; no runtime dependencies. Source is parsed with Python's AST, never imported, so historical versions do not need their dependencies installed and application startup code does not execute.

```sh
python -m pip install git+https://github.com/dreamlake-ai/autodoc-py.git
autodoc-py src/vuer --module vuer --output docs/pages/api \
  --section 'Python API' \
  --source-url https://github.com/vuer-ai/vuer/blob/main/src/vuer
```

For reproducible builds, pin installation to a commit and use the documented revision's commit SHA in `--source-url`. Run the command on each version branch against its matching source directory (`vuer` or `src/vuer`). Set `--url-prefix` when the public API root differs from `/api`; links use absolute routes so they work with or without trailing slashes. The output follows Dockit's `pages/**/+Page.mdx` convention and includes frontmatter for navigation and search.

The generator emits module docstrings, public classes and functions, class methods and constructors, annotated and assigned class attributes, signatures, and source links. Local explicit and star imports produce linked public re-export indexes; local base classes contribute inherited member lists. Literal `__all__` controls which locally defined classes/functions are included. Private modules and tests are skipped. MDX expression and JSX characters in prose are escaped, while inline and fenced code are preserved. A manifest tracks generated files so removed modules disappear without deleting manual pages. All Python files are parsed before output changes.

This is static source documentation: dynamically generated members, external-package re-exports and inheritance, module-qualified base expressions, and runtime signatures are not resolved. Local inheritance is resolved in base declaration order with overridden names suppressed; this is not a complete Python C3 method-resolution implementation. Docstrings retain their text; Sphinx roles and directives are not executed. Use the preserved Sphinx builds when exact historical Sphinx rendering is required. Syntax must be supported by the Python interpreter running the generator.

Development:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Historical compatibility: `validation/vuer-tags-2026-09-07.json` records successful source generation and generated link/anchor checks across all 149 upstream Vuer tags, including the original `tassa/`, intermediate `vuer/`, and modern `src/vuer/` package layouts. This checks source compatibility and internal links, not historical runtime behavior or MDX compilation. Re-run with:

```sh
python validation/audit_vuer_tags.py /path/to/vuer --report /tmp/vuer-audit.json
```
