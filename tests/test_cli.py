from pathlib import Path
from unittest.mock import patch

from fhem_mcp.__main__ import _build_parser, main

def test_get_live_device_http_cli_contract() -> None:
    args = _build_parser().parse_args(
        [
            "--config-root",
            "tests/fixtures",
            "get_live_device_http",
            "https://zeus:8088/fhem",
            "living.room-lamp",
            "--fwcsrf",
            "csrf_123",
            "--timeout-seconds",
            "2.5",
        ]
    )

    assert args.config_root == Path("tests/fixtures")
    assert args.command == "get_live_device_http"
    assert args.base_url == "https://zeus:8088/fhem"
    assert args.device_name == "living.room-lamp"
    assert args.fwcsrf == "csrf_123"
    assert args.timeout_seconds == 2.5


def test_read_live_log_http_cli_paged_contract() -> None:
    args = _build_parser().parse_args(
        [
            "--config-root",
            "tests/fixtures",
            "read_live_log_http",
            "https://zeus:8088/fhem",
            "./log/fhem.log",
            "--contains",
            "ERROR",
            "--max-lines",
            "25",
            "--response-format",
            "paged",
            "--cursor",
            "50",
            "--context-lines",
            "2",
        ]
    )

    assert args.command == "read_live_log_http"
    assert args.response_format == "paged"
    assert args.cursor == "50"
    assert args.context_lines == 2
    assert args.max_lines == 25


def test_compact_device_cli_contracts() -> None:
    parser = _build_parser()
    list_args = parser.parse_args(
        [
            "--config-root",
            "tests/fixtures",
            "list_devices",
            "fhem.cfg",
            "--format",
            "table",
            "--no-include-source",
            "--limit",
            "25",
            "--cursor",
            "25",
        ]
    )
    get_args = parser.parse_args(
        [
            "--config-root",
            "tests/fixtures",
            "get_device",
            "fhem.cfg",
            "lamp",
            "--format",
            "compact",
            "--include-source",
            "--include-raw",
        ]
    )

    assert list_args.format == "table"
    assert list_args.include_source is False
    assert list_args.limit == 25
    assert list_args.cursor == "25"
    assert get_args.format == "compact"
    assert get_args.include_source is True
    assert get_args.include_raw is True


def test_compact_device_cli_forwards_output_options() -> None:
    with patch("sys.argv", [
        "fhem-mcp",
        "--config-root",
        "tests/fixtures",
        "list_devices",
        "fhem.cfg",
        "--format",
        "table",
        "--no-include-source",
        "--limit",
        "25",
        "--cursor",
        "25",
    ]), patch("fhem_mcp.__main__.FhemMcpServer") as server_class:
        server_class.return_value.list_devices.return_value = {}
        main()

    server_class.return_value.list_devices.assert_called_once_with(
        "fhem.cfg", "table", False, 25, "25"
    )

    with patch("sys.argv", [
        "fhem-mcp",
        "--config-root",
        "tests/fixtures",
        "get_device",
        "fhem.cfg",
        "lamp",
        "--format",
        "compact",
        "--include-source",
        "--include-raw",
    ]), patch("fhem_mcp.__main__.FhemMcpServer") as server_class:
        server_class.return_value.get_device.return_value = {}
        main()

    server_class.return_value.get_device.assert_called_once_with(
        "fhem.cfg", "lamp", "compact", True, True
    )


def test_run_live_get_http_cli_allowlist_contract_and_deduplication() -> None:
    args = _build_parser().parse_args([
        "--config-root", "tests/fixtures",
        "--allow-get", "Weather:forecast",
        "--allow-get", "Weather:forecast",
        "run_live_get_http", "https://zeus:8088/fhem", "Weather", "forecast tomorrow",
        "--fwcsrf", "token",
    ])
    assert frozenset(args.allow_get) == frozenset({("Weather", "forecast")})
    assert args.get_parameters == "forecast tomorrow"
