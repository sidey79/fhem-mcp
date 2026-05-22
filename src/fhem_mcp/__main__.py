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

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    server = FhemMcpServer(config_root=args.config_root)

    if args.command == "mcp-stdio":
        StdioMcpServer(config_root=args.config_root).run(instream=__import__("sys").stdin, outstream=__import__("sys").stdout)
        return

    if args.command == "list_config_files":
        result = server.list_config_files()
    elif args.command == "read_config_file":
        result = server.read_config_file(args.relative_path)
    elif args.command == "list_devices":
        result = server.list_devices(args.relative_path)
    elif args.command == "get_device":
        result = server.get_device(args.relative_path, args.device_name)
    else:
        parser.error(f"unknown command: {args.command}")
        return

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
