from __future__ import annotations

import argparse
import json
from pathlib import Path

from .server import FhemMcpServer
from .stdio_server import StdioMcpServer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fhem-mcp",
        description="Phase 1 read-only FHEM MCP skeleton CLI",
    )
    parser.add_argument("--config-root", type=Path, required=True, help="Root folder containing .cfg files")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("mcp-stdio", help="Run JSON-RPC MCP server over stdio")
    sub.add_parser("list_config_files", help="List all .cfg files below config-root")

    read_cmd = sub.add_parser("read_config_file", help="Read one config file")
    read_cmd.add_argument("relative_path", help="Path relative to config-root")

    list_dev = sub.add_parser("list_devices", help="List parsed devices from one config file")
    list_dev.add_argument("relative_path", help="Path relative to config-root")

    get_dev = sub.add_parser("get_device", help="Get one parsed device from one config file")
    get_dev.add_argument("relative_path", help="Path relative to config-root")
    get_dev.add_argument("device_name", help="Device name")

    list_groups = sub.add_parser("list_groups", help="List group attributes mapped to devices")
    list_groups.add_argument("relative_path", nargs="?", default=None, help="Optional path relative to config-root")
    list_groups.add_argument("group_name", nargs="?", default=None, help="Optional exact group name filter")

    list_rooms = sub.add_parser("list_rooms", help="List room attributes mapped to devices")
    list_rooms.add_argument("relative_path", nargs="?", default=None, help="Optional path relative to config-root")

    list_attributes = sub.add_parser("list_attributes", help="List attributes for devices")
    list_attributes.add_argument("relative_path", help="Path relative to config-root")
    list_attributes.add_argument("device_name", nargs="?", default=None, help="Optional device name")

    find_attr = sub.add_parser("find_devices_by_attr", help="Find devices by attribute")
    find_attr.add_argument("relative_path", help="Path relative to config-root")
    find_attr.add_argument("attribute", help="Attribute name")
    find_attr.add_argument("value", nargs="?", default=None, help="Optional exact value")

    find_type = sub.add_parser("find_devices_by_type", help="Find devices by device type")
    find_type.add_argument("relative_path", help="Path relative to config-root")
    find_type.add_argument("device_type", help="Device type")

    list_includes = sub.add_parser("list_includes", help="List include directives with resolution info")
    list_includes.add_argument("relative_path", help="Path relative to config-root")

    summary = sub.add_parser("list_config_summary", help="Summarize devices, types, rooms and groups")
    summary.add_argument("relative_path", nargs="?", default=None, help="Optional path relative to config-root")

    search = sub.add_parser("search_config", help="Search text pattern in config files")
    search.add_argument("pattern", help="Search pattern")
    search.add_argument("relative_path", nargs="?", default=None, help="Optional path relative to config-root")

    validate = sub.add_parser("validate_config", help="Validate basic config issues")
    validate.add_argument("relative_path", nargs="?", default=None, help="Optional path relative to config-root")

    full = sub.add_parser("get_device_full", help="Find one device across all config files")
    full.add_argument("device_name", help="Device name")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    server = FhemMcpServer(config_root=args.config_root)

    if args.command == "mcp-stdio":
        StdioMcpServer(config_root=args.config_root).run(instream=__import__("sys").stdin.buffer, outstream=__import__("sys").stdout.buffer)
        return

    if args.command == "list_config_files":
        result = server.list_config_files()
    elif args.command == "read_config_file":
        result = server.read_config_file(args.relative_path)
    elif args.command == "list_devices":
        result = server.list_devices(args.relative_path)
    elif args.command == "get_device":
        result = server.get_device(args.relative_path, args.device_name)
    elif args.command == "list_groups":
        result = server.list_groups(args.relative_path, args.group_name)
    elif args.command == "list_rooms":
        result = server.list_rooms(args.relative_path)
    elif args.command == "list_attributes":
        result = server.list_attributes(args.relative_path, args.device_name)
    elif args.command == "find_devices_by_attr":
        result = server.find_devices_by_attr(args.relative_path, args.attribute, args.value)
    elif args.command == "find_devices_by_type":
        result = server.find_devices_by_type(args.relative_path, args.device_type)
    elif args.command == "list_includes":
        result = server.list_includes(args.relative_path)
    elif args.command == "list_config_summary":
        result = server.list_config_summary(args.relative_path)
    elif args.command == "search_config":
        result = server.search_config(args.pattern, args.relative_path)
    elif args.command == "validate_config":
        result = server.validate_config(args.relative_path)
    elif args.command == "get_device_full":
        result = server.get_device_full(args.device_name)
    else:
        parser.error(f"unknown command: {args.command}")
        return

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
