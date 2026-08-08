# FHEM MCP Server Specification

## Goal
Expose FHEM configuration and runtime state safely to AI agents through MCP.

## Key constraint
FHEM's parser is integrated in fhem.pl and applies the configuration while parsing. Therefore, this project must not attempt to use the production parser directly for static analysis.

## Architecture
Source View + Runtime View + Sandbox Validation.

## Implemented tools
- list_config_files
- read_config_file
- read_live_config_http(base_url?, config_path?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- read_live_log_http(base_url?, log_path?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?, contains?, regex?, since?, until?, max_lines?, ignore_case?, response_format?, cursor?, context_lines?)
- list_live_logs_http(base_url?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- observe_live_events_http(base_url?, duration_seconds?, event_monitor_filter? raw regex / TYPE=<type>, device_regex?, event_regex?, max_events?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- get_live_device_http(base_url?, device_name, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- run_live_get_http(device_name, get_parameters, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- run_live_set_http(device_name, set_parameters, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)
- list_devices
- get_device
- list_groups(relative_path?, group_name?)
- list_rooms(relative_path?)
- list_attributes(relative_path, device_name?)
- find_devices_by_attr(relative_path, attribute, value?)
- find_devices_by_type(relative_path, device_type)
- list_includes(relative_path)
- list_config_summary(relative_path?)
- search_config(pattern, relative_path?)
- validate_config(relative_path?)
- get_device_full(device_name)

### Runtime View contract
`get_live_device_http` runs the read-only FHEM command `jsonlist2 <device_name>` for one literal, conservatively validated device name. It does not accept arbitrary `devspec` expressions, field selections, or FHEM commands.

For MCP calls, all read-only HTTP tools use `active_runtime_base_url` when `base_url` is omitted. An explicit `base_url` overrides that default. Active Phase 2 GET/SET tools never expose an endpoint override.

An unknown device returns `null`. A matching device returns this normalized shape:

```json
{
  "name": "lamp",
  "internals": {"TYPE": "dummy"},
  "attributes": {"room": "Living"},
  "readings": {
    "state": {"value": "on", "time": "2026-07-15 12:00:00"}
  },
  "possible_sets": "off on",
  "possible_attributes": "room alias"
}
```

Malformed JSON, a missing `Results` member, a structurally invalid result, or more than one exact match is an error. The tool is read-only and must never issue `set`, `delete`, `shutdown`, `rereadcfg`, or another modifying command.

`run_live_get_http` and `run_live_set_http` are Phase 2 active runtime access. This is an intentional extension beyond the unchanged Phase 1 read-only scope and requires explicit operator enablement. They are disabled by default and enabled independently at server startup with `--enable-get` and `--enable-set`. Enabling either requires an operator-approved `--active-runtime-base-url`; startup fails without it, and active tool schemas do not expose `base_url`. The server constructs only `get <literal-device> <validated-parameters>` or `set <literal-device> <validated-parameters>` and sends it URL-encoded with `XHR=1` and optional `fwcsrf`. Empty parameters, `devspec` device expressions, semicolons, NUL, line breaks, tabs, and other control characters are rejected before network access.

Authorization is delegated to FHEM after global enablement. The active-runtime endpoint is immutable for the server lifetime and cannot be selected or overridden by MCP callers. Active CSRF-token and command requests reject every HTTP redirect so credentials and mutations cannot leave the approved endpoint. Deployments should use a dedicated FHEMWEB `apiWeb` instance protected by `allowed`, narrow `allowfrom`, HTTPS, authentication, and CSRF. The MCP server intentionally does not duplicate device- or option-level policy.

GET results and SET results contain the literal device name, first option, trimmed parameters, and unchanged FHEM response text. Module errors remain response text because generic success/error interpretation is not reliable. Connection, TLS, validation, and disabled-feature failures are tool errors. GET handlers can block or have side effects; SET explicitly changes runtime state. No arbitrary FHEM command, `delete`, `shutdown`, `rereadcfg`, `define`, or `attr` pass-through is exposed.

## Future tools
- Broader Runtime View queries (Telnet adapters, arbitrary searches, bulk queries, and extended live tools)
- get_device_state
- get_readings
- find_references
- propose_patch
- preview_patch
- validate_patch
- any write/apply workflows

## Out of scope
- full FHEM-compatible parser
- automatic production configuration writes
- uncontrolled live set commands
- direct production rereadcfg
