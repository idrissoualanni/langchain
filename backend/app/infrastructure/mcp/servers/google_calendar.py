# Backend Google Calendar — couche de persistance de l'agenda ( §40 ).
#
# Remplace le store JSON mock ( calendar_server._load/_save ) par l'API
# Google Calendar reelle. Le CONTRAT DES TOOLS est strictement preserve :
# check_availability / create_event / list_events gardent la meme signature
# et les memes structures de retour — le serveur MCP appelle ce backend de
# maniere transparente.
#
# Authentification : OAuth2 utilisateur ( InstalledAppFlow ).
#   GOOGLE_CALENDAR_CREDENTIALS  chemin du client_secret.json ( GCP )
#   GOOGLE_CALENDAR_TOKEN        cache du token OAuth ( cree au 1er consent )
#
# Cycle de vie :
#   1er appel  -> flow.run_local_server() ouvre le navigateur, l'utilisateur
#                consent, le token est PERSISTE sur disque.
#   suivants   -> Credentials.from_authorized_user_file() ; si expired ->
#                refresh automatique + re-persiste ( pas de re-consent ).
#   absence/HS -> CalendarBackendError remontee en resultat d'erreur ( le
#                graphe ne plante JAMAIS — §15 fail-safe ).
#
# Rotation backend ( deterministe ) :
#   GOOGLE_CALENDAR_CREDENTIALS defini + token valide -> API Google.
#   Sinon -> fallback sur le store JSON ( data/mcp/calendar.json ) pour que
#   le dev local et les demos marchent sans GCP.
#
# Securite ( §41 ) : le secret OAuth reste cote serveur ; le LLM ne manipule
# JAMAIS les credentials — les tools ne recevant que { title, start, end }.
# client_secret.json et token.json DOIVENT etre hors git ( .gitignore ).
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Racine backend ( app/infrastructure/mcp/servers/google_calendar.py ->
# parents[4] = backend/ qui contient data/mcp/ ).
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_GOOGLE_DIR = _BACKEND_ROOT / "data" / "mcp" / "google"

# Scopes : calendar.events couvre list/create/patch/delete des evenements
# ( tools create_event / list_events ). calendar.calendar.readonly est
# requis par l'endpoint freeBusy ( tool check_availability ) — il refuse
# avec "insufficient authentication scopes" sous calendar.events seul.
# Les deux sont NON sensibles ( validation GCP automatique ).
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendar.readonly",
]

_GOOGLE_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_CREDENTIALS = _GOOGLE_DIR / "client_secret.json"
_DEFAULT_TOKEN = _GOOGLE_DIR / "token.json"


class CalendarBackendError(RuntimeError):
    """Echec du backend agenda ( OAuth manquant, token HS, API KO ).

    Remontee comme RESULTAT d'erreur — jamais comme exception dans le
    graphe ( §15 ). Le message est destine a l'utilisateur final.
    """


def _credentials_path() -> Path:
    return Path(
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS", str(_DEFAULT_CREDENTIALS))
    )


def _token_path() -> Path:
    return Path(os.getenv("GOOGLE_CALENDAR_TOKEN", str(_DEFAULT_TOKEN)))


# --- Clients caches ( le service OAuth est lent a construire ) -----------
# Valeur sentinelle pour distinguer "non encore resolu" de "resolu a None".
_UNRESOLVED = object()
_service: Any = _UNRESOLVED
_last_backend: str | None = None


def _reset_cache() -> None:
    """Invalide le cache ( tests / changement d'env a chaud )."""
    global _service, _last_backend
    _service = _UNRESOLVED
    _last_backend = None


def _active_backend() -> str:
    """Nom du backend actif : "google" ou "mock" ( deterministe ).

    Google n'est retenu QUE si le client_secret est present — sinon on
    degrade sur le store JSON sans erreur ( dev local sans GCP ).
    """
    return "google" if _credentials_path().exists() else "mock"


def _build_service() -> Any:
    """Construit le client Google Calendar ( OAuth2 + cache disque ).

    Leve CalendarBackendError si l'OAuth ne peut aboutir ( credentials
    introuvables, refus, reseau KO ) — le caller decide du fallback.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds_path = _credentials_path()
    token_path = _token_path()

    if not creds_path.exists():
        raise CalendarBackendError(
            "Google Calendar non configuré : placez client_secret.json "
            f"dans {creds_path.parent} ( ou définissez "
            "GOOGLE_CALENDAR_CREDENTIALS )"
        )

    # Token cache : on le charge avant tout, y compris expire ( refresh ).
    creds: Credentials | None = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(token_path), SCOPES
            )
        except Exception as exc:  # noqa: BLE001 — token corrompu
            creds = None
            os.environ.setdefault("GOOGLE_CALENDAR_TOKEN_WARNED", "1")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 1er consent ( ou token irrecuperable ) : navigateur local.
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Persiste pour les appels suivants ( pas de re-consent ).
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds, static_discovery=False)


def _service_or_none() -> Any:
    """Client Google resolu une fois, en cache ; None si backend = mock.

    Leve CalendarBackendError si le backend est google mais que l'OAuth
    echoue ( credentials absents au moment de l'appel, token HS... ).
    """
    global _service, _last_backend
    backend = _active_backend()
    if _last_backend != backend:
        _service = _UNRESOLVED
        _last_backend = backend
    if _service is _UNRESOLVED:
        _service = None if backend == "mock" else _build_service()
    return _service


# --- Normalisation ISO8601 ( tolerant : date seule ou datetime ) --------
def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _rfc3339(dt: datetime) -> str:
    """Format exige par l'API Google Calendar ( RFC3339 UTC )."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


# --- Store JSON de secours ( mock, sans GCP ) ---------------------------
def _mock_load() -> list[dict]:
    from app.infrastructure.mcp.servers.calendar_server import _load

    return _load()


def _mock_save(events: list[dict]) -> None:
    from app.infrastructure.mcp.servers.calendar_server import _save

    _save(events)


def _mock_id(events: list[dict]) -> str:
    return f"evt-{len(events) + 1:04d}"


# --- API publique : CONTRAT IDENTIQUE au mock ---------------------------
def check_availability(start: str, end: str) -> dict:
    """{ available: bool, conflicts: [...] } — cf. tool MCP du meme nom.

    Utilise freebusy() : semantique exacte de disponibilite, sans exposer
    les details des evenements prives ( titre cache ).
    """
    s, e = _parse_dt(start), _parse_dt(end)
    if s is None or e is None or e <= s:
        return {
            "available": False,
            "conflicts": [],
            "error": "Créneau invalide (dates ISO start<end attendues)",
        }

    if _active_backend() == "mock":
        conflicts = [
            {
                "id": ev.get("id"),
                "title": ev.get("title"),
                "start": ev.get("start"),
                "end": ev.get("end"),
            }
            for ev in _mock_load()
            if _overlap(
                s, e, _parse_dt(ev.get("start", "")), _parse_dt(ev.get("end", ""))
            )
        ]
        return {"available": not conflicts, "conflicts": conflicts}

    service = _service_or_none()
    body = {
        "timeMin": _rfc3339(s),
        "timeMax": _rfc3339(e),
        "items": [{"id": "primary"}],
    }
    try:
        resp = (
            service.freebusy()
            .query(body=body)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — API KO
        raise CalendarBackendError(
            f"Échec de la requête de disponibilité Google : {exc}"
        ) from exc

    busy = (resp.get("calendars", {}).get("primary", {}) or {}).get("busy", [])
    conflicts = [
        {
            "id": "busy",
            "title": "Occupé",
            "start": slot.get("start"),
            "end": slot.get("end"),
        }
        for slot in busy
        if _overlap(
            s,
            e,
            _parse_dt(slot.get("start", "")),
            _parse_dt(slot.get("end", "")),
        )
    ]
    return {"available": not conflicts, "conflicts": conflicts}


def create_event(title: str, start: str, end: str) -> dict:
    """Cree l'evenement -> { created: bool, ...event }.

    Sur conflit : created=False + conflicts ( rien n'est ecrit ).
    """
    s, e = _parse_dt(start), _parse_dt(end)
    if not title.strip() or s is None or e is None or e <= s:
        return {
            "created": False,
            "error": "Paramètres invalides (title, start<end ISO requis)",
        }

    # Conflit verifie AVANT l'ecriture ( cohérence avec le mock ).
    avail = check_availability(start, end)
    if not avail.get("available"):
        return {
            "created": False,
            "error": "Créneau déjà occupé",
            "conflicts": avail.get("conflicts", []),
        }

    if _active_backend() == "mock":
        events = _mock_load()
        new_id = _mock_id(events)
        event = {
            "id": new_id,
            "title": title.strip(),
            "start": s.isoformat(),
            "end": e.isoformat(),
            "created": datetime.now().isoformat(),
        }
        events.append(event)
        _mock_save(events)
        return {"created": True, **event}

    service = _service_or_none()
    body = {
        "summary": title.strip(),
        "start": {"dateTime": _rfc3339(s)},
        "end": {"dateTime": _rfc3339(e)},
    }
    try:
        created = (
            service.events().insert(calendarId="primary", body=body).execute()
        )
    except Exception as exc:  # noqa: BLE001 — API KO
        raise CalendarBackendError(
            f"Échec de la création de l'événement Google : {exc}"
        ) from exc

    return {
        "created": True,
        "id": created.get("id"),
        "title": created.get("summary", title.strip()),
        "start": (created.get("start", {}) or {}).get("dateTime"),
        "end": (created.get("end", {}) or {}).get("dateTime"),
        "created": created.get("created"),
    }


def list_events(days: int = 7) -> dict:
    """{ events: [...], count: int } — evenements a venir, tries.

    Fallback mock si l'API Google n'est pas configuree.
    """
    horizon = max(1, min(int(days), 90))

    if _active_backend() == "mock":
        now = datetime.now()
        upcoming = []
        for ev in _mock_load():
            s = _parse_dt(ev.get("start", ""))
            if s is None:
                continue
            if now <= s <= now + timedelta(days=horizon):
                upcoming.append(ev)
        upcoming.sort(key=lambda ev: ev.get("start", ""))
        return {"events": upcoming, "count": len(upcoming)}

    service = _service_or_none()
    now = datetime.now(timezone.utc)
    try:
        resp = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=_rfc3339(now),
                timeMax=_rfc3339(now + timedelta(days=horizon)),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — API KO
        raise CalendarBackendError(
            f"Échec de la liste des événements Google : {exc}"
        ) from exc

    items = resp.get("items", [])
    events = [
        {
            "id": it.get("id"),
            "title": it.get("summary", ""),
            "start": (it.get("start", {}) or {}).get("dateTime")
            or (it.get("start", {}) or {}).get("date"),
            "end": (it.get("end", {}) or {}).get("dateTime")
            or (it.get("end", {}) or {}).get("date"),
            "created": it.get("created"),
        }
        for it in items
    ]
    return {"events": events, "count": len(events)}


if __name__ == "__main__":
    # Smoke test standalone : python -m
    # app.infrastructure.mcp.servers.google_calendar
    # Ouvre le navigateur au 1er lancement ( consent OAuth ), puis liste.
    backend = _active_backend()
    print(f"[agenda] backend actif : {backend}")
    if backend == "google":
        print("[agenda] credentials :", _credentials_path())
    try:
        res = list_events(days=7)
        print(
            f"[agenda] list_events OK | count={res.get('count')} | "
            f"backend={backend}"
        )
        for ev in res.get("events", [])[:5]:
            print(f"           - {ev.get('start')} | {ev.get('title')}")
    except CalendarBackendError as exc:
        print(f"[agenda] ERREUR backend : {exc}")
