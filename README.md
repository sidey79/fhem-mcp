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

Nicht enthalten in Phase 1:

- Produktionsänderungen an FHEM
- `set/delete/shutdown/rereadcfg`
- Vollständige FHEM-kompatible Parser-Reimplementierung

## Implementierte MCP-Server-Funktionen

Aktuell stellt `FhemMcpServer` folgende Methoden bereit:

1. `list_config_files()`
   - Listet alle `.cfg` Dateien unterhalb des konfigurierten Wurzelpfads.
2. `read_config_file(relative_path)`
   - Liest eine konkrete Datei (inkl. Pfad-Escape-Schutz).
3. `list_devices(relative_path)`
   - Gibt geparste Geräte (`define`) inkl. Typ und Source-Zeile zurück.
4. `get_device(relative_path, device_name)`
   - Gibt ein einzelnes Gerät inkl. Attribute (`attr`) zurück.

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

## Starten / CLI Nutzung

Es gibt eine kleine CLI für lokale Tests:

```bash
# Config-Dateien auflisten
fhem-mcp --config-root tests/fixtures list_config_files

# Konfigdatei lesen
fhem-mcp --config-root tests/fixtures read_config_file fhem.cfg

# Geräte aus einer Datei auflisten
fhem-mcp --config-root tests/fixtures list_devices fhem.cfg

# Gerätedetails lesen
fhem-mcp --config-root tests/fixtures get_device fhem.cfg lamp
```

Alternativ über Python-Modul:

```bash
python -m fhem_mcp --config-root tests/fixtures list_config_files
```


## Echter MCP stdio Entry-Point

Zusätzlich zur CLI gibt es jetzt einen MCP-JSON-RPC Startmodus über stdio:

```bash
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS mcp-stdio
```

Dieser Modus ist für IDE/Agent-Hosts gedacht, die MCP-Server per `command` + `args` über stdio starten.
Unterstützte MCP-Methoden in Phase 1:

- `initialize`
- `tools/list`
- `tools/call` für:
  - `list_config_files`
  - `read_config_file`
  - `list_devices`
  - `get_device`

## MCP-Server in IDE als KI-Agent einbinden

> Hinweis: Dieses Repository enthält aktuell ein Phase‑1 Skeleton mit lokalem CLI. Für die IDE-Integration wird derselbe Startbefehl als MCP-Server-Command hinterlegt.

### 1) Server-Kommando festlegen

Nimm als Startkommando:

```bash
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS list_config_files
```

Für echte MCP-Clients wird später typischerweise ein dedizierter MCP-Transport-Startpunkt genutzt (z. B. stdio-Server). Bis dahin kannst du die vorhandenen read-only Funktionen lokal über denselben Python-Einstieg testen.

### 2) Beispiel-Konfiguration für MCP-Clients (JSON)

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
        "list_config_files"
      ]
    }
  }
}
```

### 3) Beispiel in VS Code (Pattern)

Falls dein Agent-Plugin eine MCP-Konfigurationsdatei verlangt, trägst du denselben `command` + `args` Block dort ein. Danach IDE/Plugin neu starten und prüfen, ob der Server erreichbar ist.

### 4) Verbindung testen

Unabhängig von der IDE zuerst lokal testen:

```bash
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS list_config_files
python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS list_devices fhem.cfg
```

Wenn diese Befehle funktionieren, sind Python-Umgebung und Pfade korrekt.

## Tests ausführen

```bash
pytest
```
