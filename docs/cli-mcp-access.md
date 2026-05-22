# CLI und MCP Access

Diese Seite bündelt den operativen Zugriff über CLI und MCP-stdio.

## CLI Nutzung

```bash
# Config-Dateien auflisten
fhem-mcp --config-root tests/fixtures list_config_files

# Konfigdatei lesen
fhem-mcp --config-root tests/fixtures read_config_file fhem.cfg

# Geräte aus einer Datei auflisten
fhem-mcp --config-root tests/fixtures list_devices fhem.cfg

# Gerätedetails lesen
fhem-mcp --config-root tests/fixtures get_device fhem.cfg lamp

# Neue Phase-1 Tools
fhem-mcp --config-root tests/fixtures list_groups fhem.cfg
fhem-mcp --config-root tests/fixtures list_rooms fhem.cfg
fhem-mcp --config-root tests/fixtures list_attributes fhem.cfg tempSensor
fhem-mcp --config-root tests/fixtures find_devices_by_attr fhem.cfg room Sensors
fhem-mcp --config-root tests/fixtures find_devices_by_type fhem.cfg MQTT2_DEVICE
fhem-mcp --config-root tests/fixtures list_includes fhem.cfg
fhem-mcp --config-root tests/fixtures list_config_summary fhem.cfg
fhem-mcp --config-root tests/fixtures search_config "attr tempSensor room" fhem.cfg
fhem-mcp --config-root tests/fixtures find_references "tempSensor" fhem.cfg
fhem-mcp --config-root tests/fixtures validate_config fhem.cfg
fhem-mcp --config-root tests/fixtures get_device_full tempSensor
```

Alternativ über Python-Modul:

```bash
python -m fhem_mcp --config-root tests/fixtures list_config_files
```

## MCP stdio Entry-Point

```bash
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS mcp-stdio
```

Unterstützte MCP-Methoden in Phase 1:

- `initialize`
- `tools/list`
- `tools/call` für die Phase-1 Source-View Tools

## IDE/Agent Integration

Für MCP-Clients muss der laufende stdio-Servermodus (`mcp-stdio`) verwendet werden, damit `initialize` und `tools/*` über eine persistente JSON-RPC-Session funktionieren.

Beispiel-Konfiguration:

```json
{
  "mcpServers": {
    "fhem": {
      "command": "python",
      "args": [
        "-m",
        "fhem_mcp",
        "--config-root",
        "/ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS",
        "mcp-stdio"
      ]
    }
  }
}
```

## Verbindung testen

```bash
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS mcp-stdio
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS list_devices fhem.cfg
```
