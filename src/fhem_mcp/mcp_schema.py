from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(StrictModel):
    pass


class RelativePathArgs(StrictModel):
    relative_path: str


class DeviceArgs(RelativePathArgs):
    device_name: str


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


TOOL_DEFINITIONS: dict[str, tuple[str, type[BaseModel]]] = {
    "list_config_files": ("List all .cfg files under config root", EmptyArgs),
    "read_config_file": ("Read one config file", RelativePathArgs),
    "read_live_config_http": ("Read one live FHEM config via HTTP cmd=cat", ReadLiveConfigHttpArgs),
    "list_devices": ("List parsed devices from one config file", RelativePathArgs),
    "get_device": ("Get one parsed device from one config file", DeviceArgs),
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
