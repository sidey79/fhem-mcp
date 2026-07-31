from pathlib import Path

from fhem_mcp.__main__ import _build_parser


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
