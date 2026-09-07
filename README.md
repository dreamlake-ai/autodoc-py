# autodoc-py

Generate Python API reference pages for [DreamLake Dockit](https://dockit.dreamlake.ai). Python 3.10+; no runtime dependencies. Source is parsed with Python's AST, never imported, so historical versions do not need their dependencies installed and application startup code does not execute.

```sh
python -m pip install dreamlake-autodoc-py==0.2.0a1
autodoc-py src/vuer --module vuer --output docs/pages/api \
  --section 'Python API' \
  --source-url https://github.com/vuer-ai/vuer/blob/main/src/vuer
```

For reproducible builds, pin installation to a commit and use the documented revision's commit SHA in `--source-url`. Run the command on each version branch against its matching source directory (`vuer` or `src/vuer`). Set `--url-prefix` when the public API root differs from `/api`; links use absolute routes so they work with or without trailing slashes. The output follows Dockit's `pages/**/+Page.mdx` convention and includes frontmatter for navigation and search.

The generator emits module docstrings, public classes and functions, class methods and constructors, annotated and assigned class attributes, signatures, and source links. Local explicit and star imports produce linked public re-export indexes; local base classes contribute inherited member lists. Literal `__all__` controls which locally defined classes/functions are included. Private modules and tests are skipped. MDX expression and JSX characters in prose are escaped, while inline and fenced code are preserved. A manifest tracks generated files so removed modules disappear without deleting manual pages. All Python files are parsed before output changes.

## Group modules into topic pages

By default, each public module gets its own page. Use `--page-map api-pages.json` to combine related modules into a small set of reader-facing pages, each with an API index and its functions, classes, and methods:

```sh
autodoc-py src/example --module example --output docs/pages/api \
  --page-map api-pages.json
```

```json
{
  "pages": [
    {
      "slug": "configuration",
      "title": "Configuration",
      "description": "Create and load configuration objects.",
      "modules": ["example", "example.config"],
      "symbols": {"example.config": ["Config", "load"]}
    },
    {
      "slug": "cli",
      "title": "Command-line interface",
      "description": "Parse arguments and generate command help.",
      "modules": ["example.cli", "example.cli.*"]
    }
  ],
  "exclude": {"example.legacy*": "Historical compatibility implementation"}
}
```

`modules` accepts exact names or glob patterns; every public module must belong to exactly one page or match an explicit exclusion. Patterns must match existing modules. The optional `symbols` mapping selects names per module; omit it to include that module's public API. Omitted symbols or excluded modules cannot remain targets of generated API links. Each page may also set `intro` and `order`.

Heading anchors include the source module, such as `/api/configuration#example.config--config`, so identically named symbols from different modules remain distinct. Generated re-export and inheritance links point into these topic pages. `.autodoc-routes.json` records the old module routes and anchors for configuring redirects in your host; the generator does not install redirects itself.

Public singleton assignments such as `EnvVar = _EnvVar()` document the local class's API under the public instance name, without executing its constructor. Google-style `Args`, `Returns`, and related sections become readable Markdown; indented `Example` and `Examples` blocks become fenced Python code, preserving comments and literal braces. Existing Markdown fences and lists are preserved.

This is static source documentation: dynamically generated members, external-package re-exports and inheritance, module-qualified base expressions, and runtime signatures are not resolved. Local inheritance is resolved in base declaration order with overridden names suppressed; this is not a complete Python C3 method-resolution implementation. Docstrings retain their text; Sphinx roles and directives are not executed. Use the preserved Sphinx builds when exact historical Sphinx rendering is required. Syntax must be supported by the Python interpreter running the generator.

The distribution name is `dreamlake-autodoc-py`; the command is `autodoc-py`. It is a standard Python package built with setuptools, compatible with both pip and uv. Until a PyPI release is available, install from Git as above or run directly with uv:

```sh
uvx --from git+https://github.com/dreamlake-ai/autodoc-py.git autodoc-py --help
```

See [usage and integration](https://dockit.dreamlake.ai/python-autodoc/usage) and [release notes](https://dockit.dreamlake.ai/python-autodoc/release-notes).

Development:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
# Build the wheel and source distribution with uv:
uv build
```

Historical compatibility: `validation/vuer-tags-2026-09-07.json` records successful source generation and generated link/anchor checks across all 149 upstream Vuer tags, including the original `tassa/`, intermediate `vuer/`, and modern `src/vuer/` package layouts. This checks source compatibility and internal links, not historical runtime behavior or MDX compilation. Re-run with:

```sh
python validation/audit_vuer_tags.py /path/to/vuer --report /tmp/vuer-audit.json
```

### Python reference display

Generated pages include API cards with constructor and callable signatures,
linked local types, parameter/default tables, return values, bases, attributes,
and labeled properties/static/class/async methods. Public type aliases and
trailing attribute docstrings are included. Google and Sphinx parameter fields
are formatted without executing directives. The generator copies `autodoc.css`
next to its output and imports it from each page; no shell patch is needed.

NamedTuple/dataclass field signatures reflect source declarations. Dynamically
created APIs and external inherited constructors are not executed or inferred.
