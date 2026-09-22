# Serveur MCP "agenda" — tools calendrier (doc §40 : Calendar workflow).
#
# Lancé en stdio par le registry (app/mcp/registry.py). Implémente
# trois tools : check_availability, create_event, list_events.
#
# Persistance : JSON sous data/mcp/calendar.json (créé à la première
# écriture). VOLONTAIREMENT simple — pas d'OAuth Google réelle ici
# (cf. limites du plan) ; l'interface MCP est stable, un vrai backend
# Google Calendar pourra remplacer la couche de persistance sans
# toucher au contrat des tools.
#
# Sécurité (§41) : pas de secret manipulé, pas d'exécution de code,
# outils à effet limité à l'agenda de l'utilisateur.
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agenda")

# Racine backend (app/infrastructure/mcp/servers/calendar_server.py → 4 parents) :
# le store par défaut reste déterministe quel que soit le CWD du subprocess
# MCP. MCP_CALENDAR_STORE permet l'override (tests).
# REFACTOR : ce fichier est dans app/infrastructure/mcp/servers/ →
# parents[4] = backend/ (qui contient data/mcp/calendar.json).
# Avant le déménagement, parents[4] valait la racine du repo (sans
# data/) : l'ancrage backend/ est la cible correcte.
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_STORE = Path(
    os.getenv(
        "MCP_CALENDAR_STORE",
        str(_BACKEND_ROOT / "data" / "mcp" / "calendar.json"),
    )
)


def _load() -> list[dict]:
    """Charge les événements persistés (liste vide si absent)."""
    if not _STORE.exists():
        return []
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    return []


def _save(events: list[dict]) -> None:
    """Persiste les événements (crée le répertoire parent au besoin)."""
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _parse_dt(value: str) -> datetime | None:
    """Parse ISO ( tolerant : date seule ou datetime )."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


@mcp.tool()
def check_availability(start: str, end: str) -> dict:
    """Vérifie si l'utilisateur est disponible sur le créneau [start, end].

    Args:
        start: début ISO (ex: "2026-09-21T14:00:00").
        end: fin ISO (ex: "2026-09-21T15:00:00").

    Retourne {available: bool, conflicts: [...]} — les conflits listent
    les événements chevauchant le créneau demandé.
    """
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s is None or e is None or e <= s:
        return {
            "available": False,
            "conflicts": [],
            "error": "Créneau invalide (dates ISO start<end attendues)",
        }

    conflicts = [
        {
            "id": ev.get("id"),
            "title": ev.get("title"),
            "start": ev.get("start"),
            "end": ev.get("end"),
        }
        for ev in _load()
        if _overlap(
            s, e, _parse_dt(ev.get("start", "")), _parse_dt(ev.get("end", ""))
        )
    ]
    return {"available": not conflicts, "conflicts": conflicts}


@mcp.tool()
def create_event(title: str, start: str, end: str) -> dict:
    """Crée un événement dans l'agenda de l'utilisateur.

    Args:
        title: intitulé de l'événement.
        start: début ISO.
        end: fin ISO.

    Retourne l'événement créé {id, title, start, end, created}. Refuse
    un créneau invalide ou déjà occupé (available=False, nothing created).
    """
    s = _parse_dt(start)
    e = _parse_dt(end)
    if not title.strip() or s is None or e is None or e <= s:
        return {
            "created": False,
            "error": "Paramètres invalides (title, start<end ISO requis)",
        }

    events = _load()
    conflicts = [
        ev
        for ev in events
        if _overlap(
            s, e, _parse_dt(ev.get("start", "")), _parse_dt(ev.get("end", ""))
        )
    ]
    if conflicts:
        return {
            "created": False,
            "error": "Créneau déjà occupé",
            "conflicts": [
                {"id": c.get("id"), "title": c.get("title")} for c in conflicts
            ],
        }

    new_id = f"evt-{len(events) + 1:04d}"
    event = {
        "id": new_id,
        "title": title.strip(),
        "start": s.isoformat(),
        "end": e.isoformat(),
        "created": datetime.now().isoformat(),
    }
    events.append(event)
    _save(events)
    return {"created": True, **event}


@mcp.tool()
def list_events(days: int = 7) -> dict:
    """Liste les événements à venir (défaut : 7 jours).

    Args:
        days: horizon en jours (max 90).

    Retourne {events: [...], count: int} triés chronologiquement.
    """
    horizon = max(1, min(int(days), 90))
    now = datetime.now()
    upcoming = []
    for ev in _load():
        s = _parse_dt(ev.get("start", ""))
        if s is None:
            continue
        if now <= s <= now + timedelta(days=horizon):
            upcoming.append(ev)
    upcoming.sort(key=lambda ev: ev.get("start", ""))
    return {"events": upcoming, "count": len(upcoming)}


if __name__ == "__main__":
    # Démarrage stdio — invoqué par MultiServerMCPClient.
    sys.exit(mcp.run(transport="stdio"))
