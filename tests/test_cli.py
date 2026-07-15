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
