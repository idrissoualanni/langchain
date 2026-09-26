# Serveur MCP "agenda" — tools calendrier (doc §40 : Calendar workflow).
#
# Lancé en stdio par le registry (app/mcp/registry.py). Implémente
# trois tools : check_availability, create_event, list_events.
#
# STOCKAGE EN BASE ( migration Neon ) : table calendar_events. Anciennement
# JSON sous data/mcp/calendar.json — éphémère sur Render, perdu à chaque
# redéploiement. Le contrat des tools est inchangé ; seul le stockage bouge.
#
# Isolation : MCP_CAL_USER_ID propagé en env du subprocess stdio. NULL =
# legacy global ( événements antérieurs à l'isolation ) — jamais rattaché
# arbitrairement à un utilisateur.
#
# Sécurité (§41) : pas de secret manipulé, pas d'exécution de code,
# outils à effet limité à l'agenda de l'utilisateur.
from __future__ import annotations

import os
import sys

from mcp.server.fastmcp import FastMCP

from app.services.storage.calendar_events import (
    CalendarError,
    check_availability as db_check_availability,
    create_event as db_create_event,
    list_events as db_list_events,
)

mcp = FastMCP("agenda")

# user_id : propagé par toolset.py via l'env du subprocess. None accepté
# ( legacy global ) — mais un serveur qui isole devrait toujours recevoir
# le sien. On logge rien ici : un env absent = legacy, pas une erreur.
_USER_ID = os.getenv("MCP_CAL_USER_ID") or None
_USER_ID = _USER_ID.strip() or None if _USER_ID else None


@mcp.tool()
def check_availability(start: str, end: str) -> dict:
    """Vérifie si l'utilisateur est disponible sur le créneau [start, end].

    Args:
        start: début ISO (ex: "2026-09-21T14:00:00").
        end: fin ISO (ex: "2026-09-21T15:00:00").

    Retourne {available: bool, conflicts: [...]} — les conflits listent
    les événements chevauchant le créneau demandé. Intersection
    d'intervalles calculée en SQL.
    """
    try:
        return db_check_availability(_USER_ID, start, end)
    except CalendarError as exc:
        return {"available": False, "conflicts": [], "error": str(exc)}


@mcp.tool()
def create_event(title: str, start: str, end: str) -> dict:
    """Crée un événement dans l'agenda de l'utilisateur.

    Args:
        title: intitulé de l'événement.
        start: début ISO.
        end: fin ISO.

    Retourne l'événement créé {id, title, start, end, created}. Refuse
    un créneau invalide ou déjà occupé (nothing created).
    """
    try:
        event = db_create_event(_USER_ID, title, start, end)
        return {"created": True, **event}
    except CalendarError as exc:
        return {"created": False, "error": str(exc)}


@mcp.tool()
def list_events(days: int = 7) -> dict:
    """Liste les événements à venir (défaut : 7 jours).

    Args:
        days: horizon en jours (max 90).

    Retourne {events: [...], count: int} triés chronologiquement.
    """
    try:
        events = db_list_events(_USER_ID, days)
    except CalendarError as exc:
        return {"events": [], "count": 0, "error": str(exc)}
    return {"events": events, "count": len(events)}


if __name__ == "__main__":
    # Démarrage stdio — invoqué par MultiServerMCPClient.
    sys.exit(mcp.run(transport="stdio"))
