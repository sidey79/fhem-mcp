from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(StrictModel):
    pass


class RelativePathArgs(StrictModel):
    relative_path: str


class DeviceArgs(RelativePathArgs):
    device_name: str


class ListDevicesArgs(RelativePathArgs):
    format: Literal["full", "table"] = "full"
    include_source: bool = True
    limit: int | None = None
    cursor: str | None = None


class GetDeviceArgs(DeviceArgs):
    format: Literal["full", "compact"] = "full"
    include_source: bool = False
    include_raw: bool = False


class ListGroupsArgs(StrictModel):
    relative_path: str | None = None
    group_name: str | None = None


class ListRoomsArgs(StrictModel):
    relative_path: str | None = None


class ListAttributesArgs(RelativePathArgs):
    device_name: str | None = None


class FindByAttrArgs(RelativePathArgs):
    attribute: str
    value: str | None = None


class FindByTypeArgs(RelativePathArgs):
    device_type: str


class ListConfigSummaryArgs(StrictModel):
    relative_path: str | None = None


class SearchConfigArgs(StrictModel):
    pattern: str
    relative_path: str | None = None


class ValidateConfigArgs(StrictModel):
    relative_path: str | None = None


class GetDeviceFullArgs(StrictModel):
    device_name: str


class ReadLiveConfigHttpArgs(StrictModel):
    base_url: str
    config_path: str = "fhem.cfg"
    fwcsrf: str | None = None
    timeout_seconds: float = 5.0
    username: str | None = None
    password: str | None = None
    ca_file: str | None = None
    ca_path: str | None = None


class ReadLiveLogHttpArgs(StrictModel):
    base_url: str
    log_path: str = "./log/fhem-%Y-%m-%d.log"
    fwcsrf: str | None = None
    timeout_seconds: float = 5.0
    username: str | None = None
    password: str | None = None
    ca_file: str | None = None
    ca_path: str | None = None
    contains: str | None = None
    regex: str | None = None
    since: str | None = None
    until: str | None = None
    max_lines: int | None = 500
    ignore_case: bool = False
    response_format: Literal["text", "paged"] = "text"
    cursor: str | None = None
    context_lines: int = 0


class ListLiveLogsHttpArgs(StrictModel):
    base_url: str
    fwcsrf: str | None = None
    timeout_seconds: float = 5.0
    username: str | None = None
    password: str | None = None
    ca_file: str | None = None
    ca_path: str | None = None


class GetLiveDeviceHttpArgs(ListLiveLogsHttpArgs):
    device_name: str


class RunLiveGetHttpArgs(GetLiveDeviceHttpArgs):
    get_parameters: str


class RunLiveSetHttpArgs(GetLiveDeviceHttpArgs):
    set_parameters: str


class ObserveLiveEventsHttpArgs(StrictModel):
    base_url: str
    duration_seconds: int = 10
    event_monitor_filter: str = ".*"
    device_regex: str | None = None
    event_regex: str | None = None
    max_events: int = 500
    fwcsrf: str | None = None
    timeout_seconds: float = 5.0
    username: str | None = None
    password: str | None = None
    ca_file: str | None = None
    ca_path: str | None = None


TOOL_DEFINITIONS: dict[str, tuple[str, type[BaseModel]]] = {
    "list_config_files": ("List all .cfg files under config root", EmptyArgs),
    "read_config_file": ("Read one config file", RelativePathArgs),
    "read_live_config_http": ("Read one live FHEM config via HTTP cmd=style edit", ReadLiveConfigHttpArgs),
    "read_live_log_http": ("Read live FHEM log via HTTP with optional filters", ReadLiveLogHttpArgs),
    "list_live_logs_http": ("List live FHEM logs via HTTP jsonlist2 TYPE=FileLog", ListLiveLogsHttpArgs),
    "get_live_device_http": ("Get one authoritative live FHEM device snapshot via HTTP jsonlist2", GetLiveDeviceHttpArgs),
    "run_live_get_http": ("Run one device-specific FHEM GET via enabled HTTP access", RunLiveGetHttpArgs),
    "run_live_set_http": ("Run one device-specific FHEM SET via enabled HTTP access", RunLiveSetHttpArgs),
    "observe_live_events_http": ("Observe the FHEMWEB Event Monitor via bounded HTTP raw event longpoll", ObserveLiveEventsHttpArgs),
    "list_devices": ("List parsed devices; supports token-efficient table output", ListDevicesArgs),
    "get_device": ("Get one parsed device; supports compact output", GetDeviceArgs),
    "list_groups": ("List group attribute values to devices", ListGroupsArgs),
    "list_rooms": ("List room attribute values to devices", ListRoomsArgs),
    "list_attributes": ("List attributes for one or all devices", ListAttributesArgs),
    "find_devices_by_attr": ("Find devices by attribute/value", FindByAttrArgs),
    "find_devices_by_type": ("Find devices by device type", FindByTypeArgs),
    "list_includes": ("List include directives and resolved targets", RelativePathArgs),
    "list_config_summary": ("Short summary over config(s)", ListConfigSummaryArgs),
    "search_config": ("Search a text pattern in config files", SearchConfigArgs),
    "validate_config": ("Basic config validation", ValidateConfigArgs),
    "get_device_full": ("Find one device repo-wide", GetDeviceFullArgs),
}


def build_tool_list() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, (description, model) in TOOL_DEFINITIONS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        tools.append({"name": name, "description": description, "inputSchema": schema})
    return tools
