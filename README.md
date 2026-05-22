# FHEM MCP Server (Phase 1 Skeleton)

Dieses Repository enthält ein **read-only** Grundgerüst für einen FHEM MCP Server gemäß `docs/specification.md`.

## Phase-1 Umfang

- Lesen von FHEM-Config-Dateien (`*.cfg`)
- Best-Effort Parsing von:
  - `define`
  - `attr`
  - `include`
- Quellpositions-Tracking (Datei + Zeilennummer)
- Read-only Tool-Funktionen (kein Write/Apply)

Nicht enthalten in Phase 1 (Phase 2+):

- Runtime View Adapter (`jsonlist2`, HTTP/Telnet)
- State/Readings Runtime-Tools
- Patch-Proposal/Preview/Validation
- Produktionsänderungen an FHEM
- `set/delete/shutdown/rereadcfg`
- Vollständige FHEM-kompatible Parser-Reimplementierung

## Implementierte MCP-Server-Funktionen

| Methode | Kurzbeschreibung | Beispiel-Output |
|---|---|---|
| `list_config_files()` | Listet alle `.cfg`-Dateien unterhalb des Config-Roots. | `["fhem.cfg", "extras.cfg"]` |
| `read_config_file(relative_path)` | Liest den Rohinhalt einer Config-Datei. | `"define lamp dummy\nattr lamp alias Living Room Lamp"` |
| `list_devices(relative_path)` | Listet Geräte aus Entry-Config inkl. Includes mit Typ und Source-Position. | `[{"name":"lamp","device_type":"dummy","source_file":".../fhem.cfg","source_line":2}]` |
| `get_device(relative_path, device_name)` | Liefert ein Gerät mit `define`-Details und allen zugehörigen `attr`-Einträgen. | `{"name":"lamp","device_type":"dummy","attributes":[...]} ` |
| `list_groups(relative_path?, group_name?)` | Wertet `attr <device> group ...` aus und gruppiert auf Gruppenname. | `{"Licht":["tempSensor"],"Klima":["tempSensor"]}` |
| `list_rooms(relative_path?)` | Wertet `attr <device> room ...` inkl. Mehrfachräume/Hierarchien aus. | `{"Sensors":["tempSensor"],"system->Datenbank":["tempSensor"]}` |
| `list_attributes(relative_path, device_name?)` | Gibt Attribute je Gerät oder für ein einzelnes Gerät strukturiert zurück. | `{"tempSensor":[{"name":"room","value":"Sensors,system->Datenbank"}]}` |
| `find_devices_by_attr(relative_path, attribute, value?)` | Findet Geräte mit bestimmtem Attribut, optional mit exaktem Wert. | `[{"name":"tempSensor","matching_attribute":"genericDeviceType","matching_value":"light"}]` |
| `find_devices_by_type(relative_path, device_type)` | Findet Geräte eines bestimmten Typs. | `[{"name":"tempSensor","device_type":"MQTT2_DEVICE"}]` |
| `list_includes(relative_path)` | Zeigt Include-Struktur mit Auflösung und Existenzstatus. | `[{"include_path":"extras.cfg","resolved_path":"extras.cfg","exists":true}]` |
| `list_config_summary(relative_path?)` | Liefert Kurzüberblick über Geräte, Typen, Raum-/Gruppenzuordnungen und Quellen. | `{"device_count":2,"type_counts":{"MQTT2_DEVICE":1,"dummy":1}}` |
| `search_config(pattern, relative_path?)` | Sucht Textmuster in Configs (bei Entry-File inkl. Include-Baum). | `[{"file":"extras.cfg","line":2,"text":"attr tempSensor room Sensors,system->Datenbank"}]` |
| `find_references(reference, relative_path?)` | Heuristische Referenzsuche mit Scoring (`0.0..1.0`) und Confidence. | `[{"file":"extras.cfg","line":2,"score":0.95,"confidence":"high"}]` |
| `validate_config(relative_path?)` | Basisprüfung auf doppelte Geräte, kaputte `define/attr` und fehlende Includes. | `{"errors":[{"type":"missing_include","include_path":"missing.cfg"}]}` |
| `get_device_full(device_name)` | Sucht Gerät repo-weit und liefert vollständige Device-Struktur. | `{"name":"tempSensor","device_type":"MQTT2_DEVICE","attributes":[...]} ` |

## Parser-Verhalten

Der Parser ist absichtlich **best-effort**:

- ignoriert Leerzeilen und Kommentare (`# ...`)
- ignoriert Perl-Block-Zeilen, die mit `{` beginnen
- unterstützt einfache mehrzeilige Einträge per Zeilenfortsetzung mit `\`
- parst keine komplexen Perl-Strukturen und keine Laufzeit-semantische Auflösung

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## CLI und MCP Zugriff

Die vollständige CLI/MCP-Nutzung (inkl. `mcp-stdio`, IDE-Beispiel und Testkommandos) ist hier dokumentiert:

- `docs/cli-mcp-access.md`

## Beispiel-Konfiguration für MCP-Clients

Viele IDEs/Agent-Hosts verwenden eine MCP-Serverliste ähnlich diesem Muster:

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

## Tests ausführen

```bash
pytest
```
