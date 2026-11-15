# Weckerle ⏰

Web-App, mit der man Zeitpläne erstellt, nach denen PCs per **Wake-on-LAN** eingeschaltet
und per **SSH** heruntergefahren werden. Ausgeliefert als Docker-Container.

## Funktionen

- Geräte anlegen (Name, IP/Hostname, MAC-Adresse, Broadcast-Adresse, SSH-Zugang)
- Per Knopf einschalten (Magic Packet) und ausschalten (SSH-Befehl)
- Online-Anzeige (prüft, ob der SSH-Port erreichbar ist, aktualisiert sich alle 15 s)
- Zeitpläne pro Gerät: Aktion, Uhrzeit, Wochentage, pausierbar
- Protokoll aller Aktionen (manuell und per Zeitplan) mit Ergebnis
- Anmeldung mit Benutzername und Passwort
- SSH per eigenem Schlüssel der App (empfohlen) oder per Passwort; Passwörter werden verschlüsselt gespeichert
- Linux, Windows (OpenSSH-Server) und macOS als Ziel

## Installation

Auf einem Linux-Rechner im selben Netz wie die PCs (z. B. NAS, Raspberry Pi, Server):

```bash
curl -O https://raw.githubusercontent.com/SimonLoeffler1993/weckerle/main/docker-compose.yml
docker compose up -d
```

Danach `http://<host>:8000` öffnen und beim ersten Aufruf den Zugang anlegen.

Wichtig:

- Der Container läuft mit `network_mode: host`, weil Wake-on-LAN-Pakete als Broadcast ins
  lokale Netz gehen und aus einem normalen Docker-Bridge-Netz nicht ankommen. Das funktioniert
  nur unter Linux, nicht mit Docker Desktop auf Windows oder macOS.
- Alle Daten (Datenbank, geheimer Schlüssel, SSH-Schlüssel der App) liegen im Volume `/data`.
  Wer statt des Volumes einen Ordner einbindet, muss ihn dem Benutzer mit der UID 1000 geben
  (`chown 1000:1000 ./data`).
- Die App läuft bewusst mit nur einem Prozess, damit Zeitpläne nicht doppelt ausgeführt werden.

## Ziel-PCs vorbereiten

**Wake-on-LAN:** Im BIOS/UEFI aktivieren und beim Netzwerkadapter erlauben
(Linux: `sudo ethtool -s eth0 wol g`, Windows: Geräte-Manager → Netzwerkadapter →
Energieverwaltung und „Wake on Magic Packet“). WoL klappt in der Regel nur per Kabel.

**Ausschalten per SSH:**

1. SSH-Server einrichten (Linux: `openssh-server`, Windows: optionales Feature „OpenSSH-Server“).
2. Den öffentlichen Schlüssel aus *Einstellungen* in die `authorized_keys` des Benutzers eintragen
   (Linux: `~/.ssh/authorized_keys`; Windows-Administratoren:
   `C:\ProgramData\ssh\administrators_authorized_keys`). Alternativ ein Passwort hinterlegen.
3. Linux: Damit `sudo -n shutdown -h now` ohne Passwort klappt, per `sudo visudo` ergänzen:
   `benutzer ALL=(root) NOPASSWD: /usr/sbin/shutdown, /usr/bin/systemctl suspend`

Der SSH-Befehl zum Ausschalten ist pro Gerät frei änderbar. Für jedes Betriebssystem gibt es
Vorlagen, die den Befehl per Auswahl ausfüllen:

| | Herunterfahren (Standard) | Standby |
|---|---|---|
| Linux | `sudo -n shutdown -h now` | `sudo -n systemctl suspend` |
| Windows | `shutdown /s /t 0` | `rundll32.exe powrprof.dll,SetSuspendState 0,1,0` |
| macOS | `sudo -n shutdown -h now` | `pmset sleepnow` |

Windows: Ist der Ruhezustand aktiviert, geht `SetSuspendState` in den Ruhezustand statt in Standby
(abschalten mit `powercfg /hibernate off`).

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `PORT` | `8000` | Port der Weboberfläche |
| `TZ` | `Europe/Berlin` | Zeitzone für die Zeitpläne |
| `WECKERLE_ADMIN_USERNAME` | `admin` | Benutzername, wenn das Passwort per Variable gesetzt wird |
| `WECKERLE_ADMIN_PASSWORD` | – | Setzt das Admin-Passwort beim Start (sonst Einrichtung im Browser) |
| `WECKERLE_SECURE_COOKIES` | `0` | `1`, wenn die App hinter einem HTTPS-Reverse-Proxy läuft |
| `WECKERLE_DATA_DIR` | `/data` | Datenordner |
| `WECKERLE_SSH_TIMEOUT` | `10` | Timeout für SSH in Sekunden |

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

Die Tests prüfen unter anderem, dass das Magic Packet wirklich gesendet wird, und fahren einen
eingebauten Test-SSH-Server per Schlüssel und Passwort „herunter“.
