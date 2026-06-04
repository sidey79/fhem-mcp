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

    live_read = sub.add_parser("read_live_config_http", help="Read one live config via FHEM HTTP cmd=style edit")
    live_read.add_argument("base_url", help="FHEM web endpoint, e.g. http://127.0.0.1:8083/fhem")
    live_read.add_argument("config_path", nargs="?", default="fhem.cfg", help="Config path on live system")
    live_read.add_argument("--fwcsrf", default=None, help="Optional FHEM CSRF token (otherwise fetched dynamically)")
    live_read.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout in seconds")
    live_read.add_argument("--username", default=None, help="Optional basic auth username")
    live_read.add_argument("--password", default=None, help="Optional basic auth password")
    live_read.add_argument("--ca-file", default=None, help="Optional CA bundle file for HTTPS verification")
    live_read.add_argument("--ca-path", default=None, help="Optional CA directory for HTTPS verification")

    live_log = sub.add_parser("read_live_log_http", help="Read one live log via FHEM HTTP cmd=style edit")
    live_log.add_argument("base_url", help="FHEM web endpoint, e.g. http://127.0.0.1:8083/fhem")
    live_log.add_argument("log_path", nargs="?", default="./log/fhem-%Y-%m-%d.log", help="Log path on live system")
    live_log.add_argument("--fwcsrf", default=None, help="Optional FHEM CSRF token (otherwise fetched dynamically)")
    live_log.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout in seconds")
    live_log.add_argument("--username", default=None, help="Optional basic auth username")
    live_log.add_argument("--password", default=None, help="Optional basic auth password")
    live_log.add_argument("--ca-file", default=None, help="Optional CA bundle file for HTTPS verification")
    live_log.add_argument("--ca-path", default=None, help="Optional CA directory for HTTPS verification")
    live_log.add_argument("--contains", default=None, help="Optional substring filter")
    live_log.add_argument("--regex", default=None, help="Optional regex filter")
    live_log.add_argument("--since", default=None, help="Optional lower timestamp bound (YYYY-MM-DD HH:MM:SS)")
    live_log.add_argument("--until", default=None, help="Optional upper timestamp bound (YYYY-MM-DD HH:MM:SS)")
    live_log.add_argument("--max-lines", type=int, default=500, help="Optional line limit (tail semantics)")
    live_log.add_argument("--ignore-case", action="store_true", help="Case-insensitive contains/regex filtering")

    list_live_logs = sub.add_parser("list_live_logs_http", help="List live logs via FHEM HTTP jsonlist2 TYPE=FileLog")
    list_live_logs.add_argument("base_url", help="FHEM web endpoint, e.g. http://127.0.0.1:8083/fhem")
    list_live_logs.add_argument("--fwcsrf", default=None, help="Optional FHEM CSRF token (otherwise fetched dynamically)")
    list_live_logs.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout in seconds")
    list_live_logs.add_argument("--username", default=None, help="Optional basic auth username")
    list_live_logs.add_argument("--password", default=None, help="Optional basic auth password")
    list_live_logs.add_argument("--ca-file", default=None, help="Optional CA bundle file for HTTPS verification")
    list_live_logs.add_argument("--ca-path", default=None, help="Optional CA directory for HTTPS verification")

    observe_events = sub.add_parser("observe_live_events_http", help="Observe FHEMWEB Event Monitor via bounded HTTP raw event longpoll")
    observe_events.add_argument("base_url", help="FHEM web endpoint, e.g. http://127.0.0.1:8083/fhem")
    observe_events.add_argument("--duration-seconds", type=int, default=10, help="Observation duration, 1-60 seconds")
    observe_events.add_argument("--event-monitor-filter", default=".*", help="FHEM raw event regex; TYPE=<type> is translated")
    observe_events.add_argument("--device-regex", default=None, help="Optional local device regex filter")
    observe_events.add_argument("--event-regex", default=None, help="Optional local event regex filter")
    observe_events.add_argument("--max-events", type=int, default=500, help="Maximum events to return, 1-5000")
    observe_events.add_argument("--fwcsrf", default=None, help="Optional FHEM CSRF token (otherwise fetched dynamically)")
    observe_events.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP read timeout in seconds")
    observe_events.add_argument("--username", default=None, help="Optional basic auth username")
    observe_events.add_argument("--password", default=None, help="Optional basic auth password")
    observe_events.add_argument("--ca-file", default=None, help="Optional CA bundle file for HTTPS verification")
    observe_events.add_argument("--ca-path", default=None, help="Optional CA directory for HTTPS verification")

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
    elif args.command == "read_live_config_http":
        result = server.read_live_config_http(args.base_url, args.config_path, args.fwcsrf, args.timeout_seconds, args.username, args.password, args.ca_file, args.ca_path)
    elif args.command == "read_live_log_http":
        result = server.read_live_log_http(
            args.base_url,
            args.log_path,
            args.fwcsrf,
            args.timeout_seconds,
            args.username,
            args.password,
            args.ca_file,
            args.ca_path,
            args.contains,
            args.regex,
            args.since,
            args.until,
            args.max_lines,
            args.ignore_case,
        )
    elif args.command == "list_live_logs_http":
        result = server.list_live_logs_http(
            args.base_url,
            args.fwcsrf,
            args.timeout_seconds,
            args.username,
            args.password,
            args.ca_file,
            args.ca_path,
        )
    elif args.command == "observe_live_events_http":
        result = server.observe_live_events_http(
            args.base_url,
            args.duration_seconds,
            args.event_monitor_filter,
            args.device_regex,
            args.event_regex,
            args.max_events,
            args.fwcsrf,
            args.timeout_seconds,
            args.username,
            args.password,
            args.ca_file,
            args.ca_path,
        )
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
