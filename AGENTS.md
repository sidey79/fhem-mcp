# Agent instructions

Build a FHEM MCP server.

Core principle:
Do not try to fully reimplement FHEM's parser. FHEM's config parsing is coupled with applying commands and creating Perl runtime structures. Treat static config parsing as best-effort only.

Architecture:
- Source View: reads fhem.cfg and include files for source mapping, diffs, patches and review.
- Runtime View: queries a running FHEM instance for the authoritative active model.
- Sandbox Validation: validates risky changes in an isolated FHEM test instance.

Phase 1 scope:
- read-only config access
- parse define, attr, include comments and source locations
- expose devices and attributes through MCP tools
- read-only runtime access via jsonlist2 or HTTP/Telnet
- propose patches as diffs
- validate patches
- no automatic production apply

Safety:
- no uncontrolled shell execution
- no direct set/delete/shutdown/rereadcfg in phase 1
- all changes must be proposed as patches
- every patch must be reversible
- production FHEM must not be modified by tests

Preferred stack:
- Python
- pytest
- typed data models
- clear adapter interfaces
