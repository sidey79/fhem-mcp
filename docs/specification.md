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
- search_config
- list_devices
- get_device
- get_attributes
- find_references
- get_device_state
- get_readings
- propose_patch
- preview_patch
- validate_patch

## Out of scope
- full FHEM-compatible parser
- automatic production writes
- uncontrolled live set commands
- direct production rereadcfg
