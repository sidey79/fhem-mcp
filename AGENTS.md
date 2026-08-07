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

Phase 2 active runtime scope (explicit opt-in extension):
- device-specific GET over HTTP, enabled only with the global `--enable-get` switch
- device-specific SET over HTTP, enabled only with the independent global `--enable-set` switch
- both active command families are disabled by default
- enabling either command family requires one operator-approved `active_runtime_base_url` fixed at server startup
- MCP callers cannot select or override the active-runtime endpoint
- active-runtime CSRF and command requests must reject HTTP redirects
- FHEM `allowed` is the authoritative device/command authorization layer after enablement
- only literal device names and validated device-specific parameters are accepted
- no arbitrary FHEM command execution, `devspec`, `delete`, `shutdown`, `rereadcfg`, `define`, or `attr` pass-through

Safety:
- no uncontrolled shell execution
- no direct set/delete/shutdown/rereadcfg in phase 1
- all Phase 1 configuration changes must be proposed as patches
- every proposed patch must be reversible
- Phase 2 SET changes runtime state only after explicit `--enable-set`; authorization remains in FHEM `allowed`
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
