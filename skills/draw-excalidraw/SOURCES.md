# Sources and design basis

This package is an independent local compiler; it does not vendor Excalidraw source code.

Design/API references:
- Excalidraw JSON scene schema and binary files
- Excalidraw public library (`.excalidrawlib`) APIs and library item format
- Excalidraw public libraries catalog
- Excalidraw MCP design notes about standard native JSON and model feedback
- Dagre for directed graph layout
- ELK.js for larger/compound directed layouts
- Lucide / Iconify JSON for generic icons
- Simple Icons / Iconify JSON for brand icons

Third-party runtime dependencies keep their own licenses:
- `@dagrejs/dagre`: MIT
- `elkjs`: EPL-2.0 OR GPL-3.0-or-later (package dual-license declaration)
- `@iconify-json/lucide`: ISC icon set data
- `@iconify-json/simple-icons`: CC0 package; individual brand/trademark rights may still apply

Downloaded `.excalidrawlib` files remain subject to their source library's terms and any applicable trademark/vendor policies. The library manager downloads only on explicit use.
