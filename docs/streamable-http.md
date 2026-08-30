# Streamable HTTP mit Docker Compose

Der bestehende Server bleibt ein stdio-MCP-Server. Das in `pyproject.toml`
(`proxy`-Extra) gepinnte `mcp-proxy` übersetzt diesen Transport in
zustandsbehaftetes Streamable HTTP.
Legacy HTTP+SSE wird nicht als öffentliche Schnittstelle angeboten.

## Start

Setze `FHEM_CONFIG_PATH` auf den absoluten Pfad des Verzeichnisses, das die
FHEM-Konfiguration enthält, und starte den Service:

```bash
export FHEM_CONFIG_PATH=/ABSOLUTER/PFAD/ZU/FHEM/CONFIG
docker compose up -d
docker compose ps
```

Der Service ist nur im benannten Docker-Netz `fhem-mcp` erreichbar. Es gibt
absichtlich kein `ports:`-Mapping zum Host. Die FHEM-Konfiguration wird
read-only nach `/config` eingebunden. GET und SET bleiben deaktiviert.

Der MCP-Endpunkt lautet innerhalb des Netzes:

```text
http://fhem-mcp-http:8000/mcp
```

Der Proxy-Status ist containerintern unter `/status` verfügbar und wird vom
Compose-Healthcheck verwendet.

## Clients mit dem Netzwerk verbinden

Ein bereits existierender Container kann dem Netz gezielt beitreten:

```bash
docker network connect fhem-mcp open-webui
docker network connect fhem-mcp n8n
```

Alternativ kann dessen Compose-Datei das vorhandene Netz referenzieren:

```yaml
services:
  client:
    networks:
      - fhem-mcp

networks:
  fhem-mcp:
    external: true
```

In Open WebUI wird eine Verbindung vom Typ **MCP (Streamable HTTP)** mit der
URL `http://fhem-mcp-http:8000/mcp` angelegt.

Im n8n **MCP Client Tool** wird als Transport **Streamable HTTP** gewählt und
dieselbe URL eingetragen.

## Sicherheitsgrenze

Die Mitgliedschaft im Docker-Netz `fhem-mcp` ist die Vertrauensgrenze. Die
Bridge authentifiziert eingehende Clients nicht. Verbinde daher nur
vertrauenswürdige Container mit diesem Netz.

Soll der Endpoint auf dem Docker-Host, im LAN oder im Internet erreichbar
sein, darf nicht einfach ein Host-Port ergänzt werden. Schalte einen separat
konfigurierten Reverse-Proxy davor, der TLS und eingehende Authentifizierung
erzwingt und ausschließlich `/mcp` an diesen Service weiterleitet.

Die Standardkonfiguration:

- läuft als unprivilegierter Benutzer;
- verwendet ein read-only Root-Dateisystem und ein begrenztes `/tmp`-tmpfs;
- entfernt alle Linux-Capabilities und setzt `no-new-privileges`;
- aktiviert kein CORS;
- aktiviert weder `--enable-get` noch `--enable-set`.

## Kompatibilität und Test

Der stdio-Server kann ebenfalls direkt aus GHCR gestartet werden:

```bash
docker run --rm -i \
  -v "$FHEM_CONFIG_PATH:/config:ro" \
  ghcr.io/sidey79/fhem-mcp:0.11.2 --config-root /config mcp-stdio
```

Ein vollständiger Bridge-Smoke-Test wird in CI ausgeführt. Lokal kann er nach
dem Start innerhalb des Containers ausgeführt werden:

```bash
docker compose exec -T fhem-mcp-http \
  python - http://127.0.0.1:8000 < scripts/smoke_streamable_http.py
```
