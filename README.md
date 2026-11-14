# Weckerle ⏰

Web-App, mit der man Zeitpläne erstellt, nach denen PCs per **Wake-on-LAN** eingeschaltet
und per **SSH** heruntergefahren werden. Ausgeliefert als Docker-Container.

## Stand

- [x] Schritt 1: Grundgerüst (FastAPI, SQLite, Docker, automatischer Build)
- [ ] Schritt 2: Geräte verwalten, manuell ein- und ausschalten
- [ ] Schritt 3: Zeitpläne und Scheduler
- [ ] Schritt 4: Login, sichere Zugangsdaten, Feinschliff

## Starten mit Docker

```bash
docker compose up -d
```

Danach ist die App unter `http://<host>:8000` erreichbar. Die Datenbank liegt im Volume
`weckerle-data`.

Der Container läuft mit `network_mode: host`, weil Wake-on-LAN-Pakete als Broadcast ins
lokale Netz gehen und aus einem normalen Docker-Bridge-Netz nicht ankommen. Das Host-Netzwerk
funktioniert nur unter Linux (z. B. NAS, Raspberry Pi, Server), nicht mit Docker Desktop.

## Image

Jeder Push auf `main` baut über GitHub Actions ein Image für `amd64` und `arm64` und
veröffentlicht es als `ghcr.io/simonloeffler1993/weckerle:latest`. Tags wie `v1.0.0`
erzeugen zusätzlich versionierte Images.

## Entwicklung

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

| Variable | Standard | Bedeutung |
|---|---|---|
| `PORT` | `8000` | Port der Weboberfläche (nur im Container) |
| `WECKERLE_DATA_DIR` | `./data` (Container: `/data`) | Ordner für die SQLite-Datenbank |
| `TZ` | – | Zeitzone, wichtig für die Zeitpläne |
