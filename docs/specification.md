# FHEM MCP Server Specification

## Goal
Expose FHEM configuration and runtime state safely to AI agents through MCP.

## Key constraint
FHEM's parser is integrated in fhem.pl and applies the configuration while parsing. Therefore, this project must not attempt to use the production parser directly for static analysis.

## Architecture
Source View + Runtime View + Sandbox Validation.

## Phase 1 tools
- list_config_files
- read_config_file
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

## Phase 2+ tools
- Runtime View queries (jsonlist2, HTTP/Telnet adapters)
- get_device_state
- get_readings
- find_references
- propose_patch
- preview_patch
- validate_patch
- any write/apply workflows

## Out of scope
- full FHEM-compatible parser
- automatic production writes
- uncontrolled live set commands
- direct production rereadcfg
