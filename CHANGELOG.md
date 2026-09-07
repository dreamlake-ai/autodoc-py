# Changelog

## 0.2.0a1 — 2026-09-07

- Add optional `--page-map` topic pages with module patterns, explicit exclusions, per-module symbol selection, API indexes, and namespaced anchors. Module-per-page output remains the default.
- Rewrite generated API links for grouped pages and emit `.autodoc-routes.json` to support host redirects. Validate coverage and link targets before replacing generated output.
- Document public singleton assignments backed by local classes without importing or executing the package.
- Format Google-style argument and return sections and fence indented examples for MDX.
- Harden MDX escaping for ESM declarations and backtick fences, and respect declared Python source encodings.
- Include the README, public project links, and SPDX license metadata in Python distributions; document installation and builds with uv.

### Python reference presentation

- Styled API cards with callable signatures, parameter/default tables, return types, and local type links.
- Type aliases, documented constants and attributes, NamedTuple fields, properties, and method kinds.
- Google and Sphinx parameter fields and literal Python examples.
- Automatically included, theme-aware CSS without a frontend runtime dependency.
