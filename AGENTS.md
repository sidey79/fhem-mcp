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

Versioning policy:
- Use Semantic Versioning (SemVer): `MAJOR.MINOR.PATCH`.
- Every feature branch must include a version bump before merge.
- The version source of truth is `pyproject.toml` in `[project].version`.

SemVer bump rules:
- `PATCH`: bug fixes, refactoring without behavior change, docs-only runtime-neutral updates.
- `MINOR`: backward-compatible new features, new MCP tools, additive APIs.
- `MAJOR`: breaking changes in APIs, tool contracts, behavior, or required configuration.

Branch and PR rules:
- A PR from a feature branch is not complete unless the version is increased according to scope.
- If uncertain between two bump levels, choose the higher one.
- Do not reuse an already released version.

Release tagging rules:
- Docker image tags must align with `pyproject.toml` version.
- `latest` is mutable and only updated from `main` after successful CI.
