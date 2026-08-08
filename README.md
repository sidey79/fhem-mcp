# FHEM MCP Server

Ein sicherheitsorientierter MCP-Server, der FHEM-Konfigurationen und ausgewählte Laufzeitdaten sicher für AI-Agenten zugänglich macht. Die Architektur trennt statische Quelldateien bewusst vom autoritativen Zustand einer laufenden FHEM-Instanz.

## Architektur

- **Source View:** Liest `fhem.cfg` und Include-Dateien für Quellzuordnung, Suche und Best-Effort-Validierung.
- **Runtime View:** Fragt eine laufende FHEM-Instanz über HTTP ab: passive Snapshots sowie global aktivierbare Geräte-GETs und -SETs; FHEM `allowed` bleibt die Autorisierungsgrenze.
- **Sandbox Validation:** Ist für spätere Patch-Validierung vorgesehen; Produktions-FHEM wird nicht verändert.

Der Parser bildet FHEM absichtlich nicht vollständig nach. FHEMs Parser ist mit der Ausführung von Befehlen und dem Aufbau von Perl-Laufzeitstrukturen gekoppelt; für den aktiven Zustand bleibt daher die Runtime View maßgeblich.

## Aktueller Funktionsumfang

- Lesen von FHEM-Config-Dateien (`*.cfg`)
- Best-Effort Parsing von:
  - `define`
  - `attr`
  - `include`
- Quellpositions-Tracking (Datei + Zeilennummer)
- Read-only Tool-Funktionen (kein Write/Apply)
- Autoritativer Runtime-Snapshot eines einzelnen Geräts per FHEM-HTTP/`jsonlist2`
- Unabhängig aktivierbare gerätespezifische FHEM-GETs und -SETs über HTTP
- MCP Tool-Schemas sind über Pydantic-Modelle typisiert und werden als JSON-Schema für MCP generiert

Nicht enthalten:

- Vollständiger Runtime View Adapter (Telnet, freie `devspec`- und Massenabfragen)
- Separate State-/Readings-Komfort-Tools
- Patch-Proposal/Preview/Validation
- Produktionsänderungen an FHEM
- Freie FHEM-Befehle wie `delete`, `shutdown`, `rereadcfg`, `define` oder `attr`
- Vollständige FHEM-kompatible Parser-Reimplementierung

## Implementierte MCP-Server-Funktionen

| Methode | Kurzbeschreibung | Beispiel-Output |
|---|---|---|
| `list_config_files()` | Listet alle `.cfg`-Dateien unterhalb des Config-Roots. | `["fhem.cfg", "extras.cfg"]` |
| `read_config_file(relative_path)` | Liest den Rohinhalt einer Config-Datei. | `"define lamp dummy\nattr lamp alias Living Room Lamp"` |
| `read_live_config_http(base_url?, config_path?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Liest eine Live-Config read-only per FHEM-HTTP (`cmd=style edit ...`), holt `fwcsrf` dynamisch (oder nutzt Override) unterstützt optional Basic Auth und optionale CA-Parameter für TLS-Verifikation. | `"define lamp dummy\n..."` |
| `read_live_log_http(base_url?, log_path?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?, contains?, regex?, since?, until?, max_lines?, ignore_case?, response_format?, cursor?, context_lines?)` | Liest ein Live-Log read-only per FHEM-HTTP (`cmd=style edit ...`) und erlaubt optionale Zeilenfilter (Substring/Regex/Zeitfenster/Limit). Der additive paged-Modus liefert unveränderte Originalzeilen mit Cursor und optionalen Kontextzeilen. | `"2026.05.25 12:00:00 1: ..."` |
| `list_live_logs_http(base_url?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Listet verfügbare Live-Logs read-only per FHEM-HTTP (`cmd=jsonlist2 TYPE=FileLog`) inkl. Log-Pattern und aktueller Datei je FileLog-Device. | `{"log_patterns":["./log/fhem-%Y-%m-%d.log"]}` |
| `observe_live_events_http(base_url?, duration_seconds?, event_monitor_filter?, device_regex?, event_regex?, max_events?, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Beobachtet den FHEMWEB Event Monitor read-only für eine begrenzte Zeit per HTTP-Longpoll (`inform=type=raw;filter=...;fmt=JSON`), nutzt einen Raw-Event-Regex (`TYPE=<type>` wird übersetzt) und liefert Events plus Zusammenfassung. | `{"event_count":2,"summary":{"devices":{"lamp":2}}}` |
| `get_live_device_http(base_url?, device_name, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Liest genau ein aktives Gerät read-only per FHEM-HTTP (`cmd=jsonlist2 <device_name>`). Freie `devspec`-Ausdrücke und FHEM-Befehle sind nicht erlaubt. | `{"name":"lamp","internals":{"TYPE":"dummy"},"attributes":{"room":"Living"},"readings":{"state":{"value":"on","time":"2026-07-15 12:00:00"}},"possible_sets":"off on","possible_attributes":"room alias"}` |
| `run_live_get_http(device_name, get_parameters, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Führt bei globalem `--enable-get` einen gerätespezifischen FHEM-GET aus; FHEM/`allowed` autorisiert den Zugriff. | `{"device_name":"Weather","get_option":"forecast","get_parameters":"forecast tomorrow","response":"sunny"}` |
| `run_live_set_http(device_name, set_parameters, fwcsrf?, timeout_seconds?, username?, password?, ca_file?, ca_path?)` | Führt bei globalem `--enable-set` einen gerätespezifischen FHEM-SET aus; FHEM/`allowed` autorisiert den Zugriff. | `{"device_name":"lamp","set_option":"on","set_parameters":"on","response":""}` |
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
| `validate_config(relative_path?)` | Basisprüfung auf doppelte Geräte, kaputte `define/attr` und fehlende Includes. | `{"errors":[{"type":"missing_include","include_path":"missing.cfg"}]}` |
| `get_device_full(device_name)` | Sucht Gerät repo-weit und liefert vollständige Device-Struktur. | `{"name":"tempSensor","device_type":"MQTT2_DEVICE","attributes":[...]} ` |

`get_live_device_http` liefert bei einem unbekannten Gerät `null`. Bei einem Treffer ist die normalisierte Antwort immer ein Objekt mit `name`, `internals`, `attributes`, `readings`, `possible_sets` und `possible_attributes`. `internals` und `attributes` sind Schlüssel/Wert-Objekte; jedes Reading enthält `value` und `time`. Der Aufruf liest ausschließlich Laufzeitdaten und führt insbesondere kein `set`, `delete`, `shutdown` oder `rereadcfg` aus.

Bei allen read-only HTTP-Tools ist `base_url` im MCP-Aufruf optional. Ohne Angabe verwenden sie die beim Serverstart mit `--active-runtime-base-url` konfigurierte URL; eine im Tool-Aufruf angegebene URL überschreibt diesen Default. Phase-2-GET/SET akzeptieren weiterhin keinen URL-Override.

### Beispiel: aktives Gerät abfragen

```bash
fhem-mcp \
  --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS \
  get_live_device_http \
  https://fhem.example:8083/fhem \
  lamp
```

Der gleiche Aufruf steht MCP-Clients als Tool `get_live_device_http` zur Verfügung. Für geschützte Instanzen unterstützt das Tool zusätzlich Basic Auth, einen optionalen CSRF-Token und eigene CA-Pfade für TLS.

### Phase-2-Zugriff: aktive FHEM-GETs und -SETs

Diese bewusst aufgenommene Phase-2-Erweiterung liegt außerhalb des weiterhin unveränderten Phase-1-Read-only-Scopes. Sie muss vom Betreiber ausdrücklich aktiviert werden.

GET und SET sind standardmäßig deaktiviert und werden unabhängig beim Serverstart freigeschaltet: Sobald einer der Schalter aktiv ist, muss der Betreiber denselben Startprozess mit `--active-runtime-base-url` fest an den vorgesehenen, durch `allowed` geschützten FHEMWEB-Endpunkt binden.

```bash
# GET aktivieren
fhem-mcp \
  --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS \
  --enable-get \
  --active-runtime-base-url https://fhem.example:8083/fhem \
  run_live_get_http Weather "forecast tomorrow"

# SET aktivieren
fhem-mcp \
  --config-root /ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS \
  --enable-set \
  --active-runtime-base-url https://fhem.example:8083/fhem \
  run_live_set_http lamp "on"
```

Die Schalter gelten ebenso für `mcp-stdio`. Der MCP-Server setzt ausschließlich `get <literal-device> <validated-parameters>` beziehungsweise `set <literal-device> <validated-parameters>` zusammen. Freie `devspec`, Semikolon, NUL, Zeilenumbrüche und andere Steuerzeichen sind verboten. Die FHEM-Antwort wird unverändert in `response` geliefert.

Nach der globalen Aktivierung übernimmt FHEM die Autorisierung. MCP-Aufrufer können diesen gebundenen Endpoint weder auswählen noch überschreiben. Aktive CSRF- und Befehlsanfragen folgen keinen HTTP-Redirects; jede 30x-Antwort wird als Fehler zurückgegeben. Für externe Automation wird eine dedizierte FHEMWEB-Instanz (`apiWeb`) empfohlen, die durch ein `allowed`-Device auf die gewünschten Benutzer, Geräte und Befehle begrenzt ist. Zusätzlich sollten `allowfrom`, HTTPS, Basic Auth und CSRF-Schutz passend konfiguriert bleiben. Der MCP-Server bildet diese FHEM-Policy bewusst nicht nach.

GET ist nicht universell nebenwirkungsfrei; SET verändert den FHEM-Laufzeitzustand ausdrücklich. Beide sind **active runtime access**. `get_live_device_http` bleibt davon getrennt und liefert ausschließlich einen passiven `jsonlist2`-Snapshot. Andere FHEM-Kommandos wie `delete`, `shutdown`, `rereadcfg`, `define` oder `attr` werden nicht angeboten.

## Parser-Verhalten

Der Parser ist absichtlich **best-effort**:

- ignoriert Leerzeilen und Kommentare (`# ...`)
- ignoriert Perl-Block-Zeilen, die mit `{` beginnen
- unterstützt einfache mehrzeilige Einträge per Zeilenfortsetzung mit `\`
- parst keine komplexen Perl-Strukturen und keine Laufzeit-semantische Auflösung

## Installation

```bash
docker pull ghcr.io/sidey79/fhem-mcp:latest
```

Das veröffentlichte Image aus der GitHub Container Registry ist die aktuelle
Installationsmethode. Ein lokaler Build oder eine Installation aus dem
Quellcode ist für den normalen Betrieb nicht erforderlich.

## CLI und MCP Zugriff

Die vollständige CLI/MCP-Nutzung (inkl. `mcp-stdio`, IDE-Beispiel und Testkommandos) ist hier dokumentiert:

- `docs/cli-mcp-access.md`
- `docs/streamable-http.md` für Streamable HTTP mit Docker Compose

## Debug-Logging (optional)

Für MCP-Handshake-Debugging kann Logging über eine Umgebungsvariable aktiviert werden:

```bash
FHEM_MCP_DEBUG=1 python -m fhem_mcp --config-root /ABSOLUTER/PFAD/ZU/CONFIG mcp-stdio
```

Bei aktivem Schalter schreibt der Server Debug-Ausgaben nach `/tmp/fhem-mcp-handshake.log`.

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

## Docker: MCP-Server in Agent einbinden

Den MCP-Server im Agent-Host direkt mit dem veröffentlichten GHCR-Image über
`docker run` starten. Wichtig ist `-i` (stdio offen lassen) und ein
Read-only-Mount auf den FHEM-Config-Ordner:

```json
{
  "mcpServers": {
    "fhem": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-v",
        "/ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS:/config:ro",
        "ghcr.io/sidey79/fhem-mcp:latest",
        "--config-root",
        "/config",
        "mcp-stdio"
      ]
    }
  }
}
```

Hinweise:
- Der Host-Pfad muss absolut sein.
- `:ro` hält den Zugriff im Container read-only.
- Falls dein Agent in einem Container läuft, muss der Mount-Pfad aus Sicht dieses Agent-Containers gültig sein.

## Docker Compose: Streamable HTTP

Die optionale Bridge stellt denselben stdio-Server im gemeinsamen Docker-Netz
unter `http://fhem-mcp-http:8000/mcp` als zustandsbehaftetes Streamable HTTP
bereit. Sie veröffentlicht keinen Host-Port und aktiviert weder GET noch SET.

```bash
export FHEM_CONFIG_PATH=/ABSOLUTER/PFAD/ZU/DEINEN/FHEM/CONFIGS
docker compose up -d
```

Open WebUI verwendet den Typ **MCP (Streamable HTTP)**, n8n das **MCP Client
Tool** mit Streamable-HTTP-Transport. Beide Clients müssen dem benannten Netz
`fhem-mcp` beitreten. Die Betriebs- und Sicherheitshinweise stehen in
[`docs/streamable-http.md`](docs/streamable-http.md). Eine Veröffentlichung auf
Host, LAN oder Internet erfordert einen separaten authentifizierenden
TLS-Reverse-Proxy.

## Tests ausführen

```bash
pytest
```


## LLM-optimierte Ausgabeformate

Die erste additive Ausbaustufe stellt für `list_devices` eine tokenarme Tabellenausgabe bereit. Ohne `format` bleibt die bisherige Ausgabe erhalten.

```json
{
  "relative_path": "fhem.cfg",
  "format": "table",
  "include_source": false,
  "limit": 100,
  "cursor": null
}
```

Die Antwort überträgt Spaltennamen nur einmal und unterstützt begrenzte, fortsetzbare Ergebnisse. Eine kompakte Meta-Sektion kennzeichnet ausgelassene Daten und zeigt dem LLM die Parameter für einen Folgeaufruf:

```json
{
  "meta": {
    "format": "table",
    "complete": false,
    "omitted": ["source"],
    "request_details": {"include_source": true}
  },
  "columns": ["name", "type"],
  "rows": [["lamp", "dummy"]],
  "count": 1,
  "truncated": false
}
```

Bei paginierten Tabellenantworten enthält `omitted` außerdem `"remaining_rows"`; `request_more.cursor` entspricht `next_cursor` und führt die Pagination mit unverändertem Spaltenschema fort. `request_details` beschreibt davon getrennt einen erneuten Abruf ausgelassener Detailfelder.

`get_device` unterstützt zusätzlich `format="compact"`. Dabei werden Attribute als Map ausgegeben; Quellreferenzen und Definitionsteile sind über `include_source` beziehungsweise `include_raw` optional. Compact-Geräte nennen in `meta.omitted` insbesondere ausgelassene Quellen, Definitionen und Rohzeilen. Mit `request_more: {"format": "full"}` ist der vollständige Folgeaufruf explizit beschrieben.

Die vollständigen Legacy-Ausgaben bleiben in Version 0.8 über `format="full"` der Standard. Weitere Listenwerkzeuge werden nach demselben DTO-Vertrag schrittweise ergänzt.


### Exakte und paginierte Logsuche

Logs bleiben absichtlich Rohtext: Treffer werden weder normalisiert noch zusammengefasst. Der kompatible Standard `response_format="text"` liefert weiterhin eine Zeichenkette. Für große Treffermengen liefert `response_format="paged"` einen kleinen Envelope um die unveränderten Originalzeilen:

```json
{
  "base_url": "https://fhem.example:8088/fhem",
  "contains": "ERROR",
  "since": "2026-07-31 18:00:00",
  "max_lines": 100,
  "response_format": "paged",
  "context_lines": 1
}
```

```json
{
  "meta": {
    "format": "raw",
    "complete": false,
    "omitted": ["other_matches"],
    "request_more": {"response_format": "paged", "cursor": "eyJpIjo0MjAsImgiOiJhYmMxMjMiLCJxIjoiZGVmNDU2In0"}
  },
  "text": "2026.07.31 18:05:20 3: exact original log message\n...",
  "matched": 479,
  "returned_matches": 100,
  "returned_lines": 187,
  "truncated": true,
  "next_cursor": "eyJpIjo0MjAsImgiOiJhYmMxMjMiLCJxIjoiZGVmNDU2In0"
}
```

Die Pagination beginnt bei den neuesten Treffern. Cursor sind opak und an die konkrete Trefferzeile sowie die verwendeten Filter gebunden; bei Logrotation, verändertem Anker oder geänderter Abfrage wird ein veralteter Cursor abgelehnt. Innerhalb jeder Seite bleiben Treffer und Kontext chronologisch geordnet. `context_lines` ergänzt originale Nachbarzeilen und kann deshalb dazu führen, dass `returned_lines` größer als `returned_matches` ist. Die Reduktion entsteht ausschließlich durch Filter, Zeitfenster, Limit und Pagination; nicht durch eine verlustbehaftete Umformatierung. FHEM überträgt die Logdatei derzeit weiterhin vollständig zum MCP-Server, der sie anschließend lokal filtert.
