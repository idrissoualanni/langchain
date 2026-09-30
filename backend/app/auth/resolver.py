# Mission Identité — CurrentUserResolver (§4/§5 du brief)
#
# LE point unique où l'identité est établie :
#   Bearer token → vérification Neon Auth (JWKS réel, mode neon)
#   → sub (identifiant externe) → users.external_user_id → user_id interne
#   → rôle → CurrentUser
#
# AUCUN endpoint ne doit plus accepter un user_id du client comme
# source d'identité. Les routes dérivent TOUT de get_current_user().
#
# Modes :
#   AUTH_MODE=neon → JWT réel EdDSA (signature via PyJWKClient officiel,
#     exp, sub ; JAMAIS verify_signature=False ; JAMAIS de sub trusté
#     depuis le body ; JAMAIS de secret en dur)
#   AUTH_MODE=dev  → "Bearer dev:<name>" résolu en interne pour le
#     développement local sans clés externes. Mêmes règles d'ownership
#     — pas de contournement possible de l'isolation.
#
# ⚠️ FAIL-CLOSED : un AUTH_MODE inconnu ÉCHOIT en 503. Il ne doit
# JAMAIS exister de chemin par lequel _resolve_from_token() retourne
# None sans lever — une dépendance FastAPI qui reçoit None casse
# l'isolation silencieusement.
import datetime as dt
import time
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient

from app.config import (
    ADMIN_EXTERNAL_IDS,
    AUTH_MODE,
    JWT_LEEWAY,
    NEON_AUTH_JWKS_URL,
    NEON_AUTH_BASE_URL,
    log_safe,
)
from app.infrastructure.database import users as users_db
# get_conn est importé ICI, et non un nouveau helper dans
# infrastructure/database/users.py, parce que le correctif ES-7 doit
# rester confiné à ce fichier. Il n'apporte rien de neuf : c'est
# exactement la connexion thread-local qu'users_db utilise déjà.
from app.infrastructure.database.connections import get_conn
from app.logging.events import log_event


@dataclass
class CurrentUser:
    """Utilisateur courant RÉSOLU (jamais déclaré par le client)."""

    external_user_id: str  # claim `sub` du fournisseur d'identité (Neon)
    user_id: str          # internal UUID — clé de TOUT le stockage
    name: str
    role: str             # "user" | "admin"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ------------------------------------------------------------------
# Vérification JWT Neon Managed Better Auth ( mode neon — réel )
# ------------------------------------------------------------------
# Neon Auth ( Better Auth ) signe ses JWT avec les clés publiques du
# well-known endpoint du projet Neon, via PyJWKClient :
#   sub  → identifiant utilisateur Neon ( stocké dans la colonne
#          users.external_user_id )
#   email/name → nom d'affichage pour le provisioning interne

_neon_jwk_client: PyJWKClient | None = None


def _get_neon_jwk_client() -> PyJWKClient:
    """Client JWKS officiel Neon Auth ( cache des clés publiques )."""
    global _neon_jwk_client
    if _neon_jwk_client is None:
        if not NEON_AUTH_JWKS_URL:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Auth Neon non configurée : définir "
                    "NEON_AUTH_JWKS_URL dans .env ( well-known "
                    "endpoint du projet Neon Auth )",
                ),
            )
        _neon_jwk_client = PyJWKClient(
            NEON_AUTH_JWKS_URL, cache_keys=True
        )
    return _neon_jwk_client


def verify_neon_token(token: str) -> dict:
    """Vérifie un JWT Neon Auth : signature, exp, sub.

    Pas d'issuer ni d'audience codés en dur ( Neon/Better Auth ne
    fournit pas de vérification d'issuer côté backend — la signature
    JWKS + l'exp suffisent ; la clé publique ne provient QUE du
    well-known Neon ).

    ATTENTION : Neon Auth ( Better Auth ) signe en EdDSA / Ed25519
    ( clé OKP ), PAS en RS256. PyJWT supporte EdDSA dès que
    `cryptography` est installé ( requirements.txt ).
    Lève jwt.PyJWTError en cas d'échec ( transformé en 401 ).
    """
    client = _get_neon_jwk_client()
    signing_key = client.get_signing_key_from_jwt(token)

    options: dict = {"require": ["exp", "iat", "sub"]}
    decode_kwargs: dict = {
        "key": signing_key.key,
        # Ed25519 ( OKP ) — signature EdDSA.
        "algorithms": ["EdDSA"],
        "options": options,
        # Tolérance d'horloge ( secondes ) — absorbe la dérive locale
        # des postes ; n'affaiblit PAS la vérification.
        "leeway": JWT_LEEWAY,
    }
    # Better Auth pose un claim aud ( = URL du service Neon Auth ).
    # PyJWT rejette par défaut tout token portant un aud non vérifié
    # ( InvalidAudienceError ) → on déclare l'audience attendue dès que
    # la base URL est configurée, sinon on déspose juste la vérif aud.
    if NEON_AUTH_BASE_URL:
        decode_kwargs["audience"] = NEON_AUTH_BASE_URL
    else:
        options["verify_aud"] = False
    return jwt.decode(token, **decode_kwargs)


# ------------------------------------------------------------------
# Provisioning : identité externe → user interne (§6/§7)
# ------------------------------------------------------------------
# ES-7 — PROVISIONNEMENT ATOMIQUE ( la « course au premier login »).
#
# CE QUI CASSAIT : un SELECT suivi d'un INSERT, deux instructions
# sans transaction ni verrou. Le même `sub` arrive LÉGITIMEMENT en
# double très souvent côté front ( deux onglets, un refresh de token
# rejoué après un 401, un flux SSE qui ouvre sa connexion pendant que
# la page se charge ) : les deux requêtes lisent « absent », les deux
# INSERT, et la seconde viole l'index unique idx_users_external_id
# → 500 sur une connexion parfaitement légitime.
#
# CE QUI REMPLACE : l'arbitrage revient à la CONTRAINTE UNIQUE, pas au
# code applicatif. L'INSERT porte `ON CONFLICT ... DO NOTHING` : un
# seul INSERT gagne, l'autre devient un no-op SILENCIEUX, et les DEUX
# appels relisent la même ligne ( re-SELECT ). Jamais deux lignes,
# jamais de 500, et pas un verrou de plus sur la base.
#
# Pourquoi PAS « SELECT ... FOR UPDATE » : un verrou de ligne ne peut
# pas s'accrocher à une ligne qui N'EXISTE PAS encore. Le second
# lecteur voit « absent » exactement comme le premier, et les deux
# finissent par insérer — le verrou n'apporte donc RIEN ici, il
# faudrait un verrou consultatif ( advisory lock ) par sub, c'est-à-dire
# de l'état en base à inventer. Et ouvrir un BEGIN autour du handler
# immobiliserait la connexion thread-local partagée par tout le reste
# de la requête ( cf. connections.get_conn ).
#
# Le re-SELECT est indispensable et n'est PAS décoratif : en
# PostgreSQL, `ON CONFLICT DO NOTHING` ATTEND ( attend le verrou
# predictif ) que la transaction concurrente se termine. Quand
# l'instruction rend la main, le gagnant a nécessairement COMMITé —
# le re-SELECT, pris dans un nouveau snapshot READ COMMITTED, voit
# donc sa ligne. C'est ce qui rend le second appel total : il récupère
# la ligne créée par le premier au lieu d'échouer.

# `ON CONFLICT` doit REPRENDRE le prédicat de l'index.
# idx_users_external_id est un index unique PARTIEL ( WHERE
# external_user_id IS NOT NULL, cf. connections.UNIQUE_INDEX, rejoué
# à chaque démarrage par connections.init_db() ) : ni PostgreSQL ni
# SQLite n'infèrent un index partiel si la clause ON CONFLICT n'en
# redit pas la condition — PostgreSQL exige alors le `index_predicate`
# explicite. La forme « naturelle »
#   ON CONFLICT (external_user_id) DO NOTHING
# est donc REJETÉE par le moteur, et le libellé diffère selon le
# moteur : PostgreSQL 17 ( Neon ) lève
#   there is no unique or exclusion constraint matching the
#   ON CONFLICT specification
# alors que SQLite lève
#   ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE
#   constraint
# Dans les DEUX cas c'est un 500 sur le PREMIER login de chaque
# utilisateur — autrement dit, exactement le défaut qu'on veut
# supprimer, déplacé d'une violation d'index à une erreur
# d'inférence. Ne pas « simplifier » cette ligne en retirant le
# WHERE : c'est la seule forme acceptée par l'index réellement
# déployé (vérifié sur la base Neon de production).
#
# Le conflit ignoré est donc STRICTEMENT external_user_id : une
# collision de clé primaire sur user_id reste une IntegrityError
# explicite, jamais un échec maquillé en succès. C'est le comportement
# voulu — le UUID est généré ici, à chaque appel, et masquer un
# conflit qui n'a rien à voir avec l'identité rendrait l'anomalie
# invisible.
#
# Le SQL est ici, et non dans users_db.create_user(), pour rester dans
# le périmètre demandé par ES-7 ( resolver.py seul ). users_db garde
# create_user() pour les créations SANS external_user_id ( route
# /api/users en mode dev ), où il n'y a aucune concurrence à arbitrer.
_PROVISION_SQL = (
    "INSERT INTO users "
    "(user_id, name, created_at, external_user_id, role) "
    "VALUES (:user_id, :name, :created_at, :external_user_id, :role) "
    "ON CONFLICT (external_user_id) "
    "WHERE external_user_id IS NOT NULL DO NOTHING"
)


def _now_iso() -> str:
    """Horodatage ISO UTC — MÊME format que users_db._now_iso().

    Dupliqué volontairement plutôt qu'importé ( c'est un privé ) :
    le provisioning écrit dans la même table, il ne doit pas créer
    une seconde convention d'horodatage à côté de create_user().
    """
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def resolve_internal_user(
    external_user_id: str, display_name: str
) -> CurrentUser:
    """Mappe l'identifiant externe → user interne, avec provisioning.

    - login 1 : aucun user avec cet external_user_id →
      provisionnement (nouvel UUID interne, ENREGISTRÉ avec son
      external_user_id)
    - logins suivants : RETROUVE LE MÊME user interne ( jamais de
      nouvel UUID à chaque connexion )
    - les users existants sans external_user_id ne sont JAMAIS
      rattachés arbitrairement (§7) — ils restent intacts.

    CHEMIN « deja connu » ( 99,9% des requêtes ) : un seul SELECT,
    aucune écriture. La lecture préalable n'est PAS un simple
    optimisme — c'est ce qui évite d'écrire en base à chaque requête
    authentifiée. La course ne peut plus faire de dégât : si le
    SELECT ment ( absence devenue un INSERT entre-temps ), le
    provisionnement atomique ci-dessous absorbe le doublon.
    """
    existing = users_db.get_user_by_external_id(external_user_id)
    if existing is not None:
        return _current_user_from_row(
            existing, external_user_id, display_name
        )
    return _provision_user(external_user_id, display_name)


def _provision_user(
    external_user_id: str, display_name: str
) -> CurrentUser:
    """INSERT atomique + re-SELECT — insère OU récupère, jamais 500.

    Boucle de 2 tentatives, pas de plus : le seul cas où le
    re-SELECT renvoie None alors que l'INSERT vient de passer est la
    suppression de la ligne dans la fenêtre entre le COMMIT et la
    relecture ( quelque chose d'infime et d'extérieur : un DELETE
    d'admin ). Une tentative de plus suffit à refermer cette fenêtre ;
    au-delà, on ne boucle pas sur une anomalie de données, on échoue
   Bruyamment.
    """
    name = display_name or "Utilisateur"
    role = "admin" if external_user_id in ADMIN_EXTERNAL_IDS else "user"

    for attempt in (1, 2):
        # UUID interne candidat. Il sert à la fois de clé primaire et
        # de TÉMOIN : si la ligne relue porte ce UUID, c'est nous qui
        # avons gagné l'INSERT ; sinon c'est le concurrent et notre
        # UUID est simplement jeté ( aucun orphelin possible ).
        candidate_id = str(uuid.uuid4())
        conn = get_conn()
        conn.execute(
            _PROVISION_SQL,
            {
                "user_id": candidate_id,
                "name": name,
                "created_at": _now_iso(),
                "external_user_id": external_user_id,
                "role": role,
            },
        )
        # COMMIT avant la relecture : le re-SELECT part alors d'un
        # NOUVEAU snapshot et voit la ligne du gagnant, même si elle a
        # été écrite par une autre transaction ( cf. le commentaire
        # ES-7 ci-dessus ). Sans ce commit, la transaction ouverte
        # par le SELECT de contrôle resterait « idle in transaction »
        # — Neon coupe ce genre de session ( cf. connections ).
        conn.commit()

        row = users_db.get_user_by_external_id(external_user_id)
        if row is None:
            continue  # ligne supprimée entre-temps → on réessaie

        if row["user_id"] == candidate_id:
            log_event(
                "AUTH_PROVISION",
                message=(
                    "User provisioned from external id"
                    f" | name={display_name}"
                ),
                user_id=candidate_id,
            )
        else:
            # Course perdue et arbitrée : c'est le CAS NOMINAL, pas
            # une erreur. On le trace pour rendre la course visible
            # dans le monitoring ( elle est invisible autrement ),
            # et on rend la ligne du gagnant — donc les DEUX
            # requêtes répondent 2xx avec le MÊME user_id.
            log_event(
                "AUTH_PROVISION_RACE",
                level="WARN",
                message=(
                    "Provisioning concurrent detecte : ligne "
                    f"existante reutilisee | loser_uuid={candidate_id}"
                ),
                user_id=row["user_id"],
            )
        return _current_user_from_row(
            row, external_user_id, display_name
        )

    # Anomalie de données, pas de concurrence : la ligne qu'on vient
    # d'écrire ( ou de voir écrire ) a disparu. On refuse de
    # fabriquer un CurrentUser avec un user_id qui n'existe pas en
    # base — ce serait casser l'isolation en silence, exactement le
    # défaut que le mode FAIL-CLOSED de ce fichier refuse partout
    # ailleurs. 503 explicite + trace.
    log_event(
        "AUTH_PROVISION_ANOMALY",
        level="ERROR",
        message=(
            "Provisioning impossible : aucune ligne pour cet "
            f"external id apres insertion | sub={log_safe(external_user_id)}"
        ),
    )
    raise HTTPException(
        status_code=503,
        detail=(
            "Provisionnement du compte impossible, réessaie dans un "
            "instant."
        ),
    )


def _current_user_from_row(
    row: dict, external_user_id: str, display_name: str
) -> CurrentUser:
    """LIGNE de base → CurrentUser, rôle LU en base (autorité unique).

    Chemin UNIQUE de lecture du rôle, utilisé par le cas « déjà connu »
    ET par la fin du provisionnement. La ligne relue peut venir d'un
    autre process (déploiement en cours) : on la lit telle quelle,
    sans la réécrire.

    ADR-023 : `users.role` (base) est l'AUTORITÉ UNIQUE au runtime.
    `ADMIN_EXTERNAL_IDS` (environnement) n'est qu'un bootstrap initial,
    appliqué une seule fois à la création de la ligne dans
    `_provision_user`. Ici on ne converte JAMAIS la base à la volée :
    une divergence entre l'environnement et la base est un signal de
    configuration à faire REMONTER, pas une erreur à auto-réparer.
    L'ancien comportement écrivait la base à chaque requête
    (set_user_role) : silencieux, il masquait précisément les
    divergences de configuration que l'ADR-023 veut rendre visibles.
    """
    # Le rôle effectif est celui de la base, point final. Rien d'autre
    # ne peut l'emporter au runtime : ni variable d'environnement, ni
    # claim du jeton (le JWT ne transporte pas le rôle applicatif).
    stored_role = _role_of(row)

    # Bootstrap résiduel : si l'environnement annonce admin mais que la
    # base dit user, on ne réécrit pas — on signale. La promotion reste
    # une action humaine explicite (UPDATE SQL ou future page admin).
    if external_user_id in ADMIN_EXTERNAL_IDS and stored_role != "admin":
        log_event(
            "AUTH_ROLE_DIFF",
            level="WARN",
            message=(
                "ADMIN_EXTERNAL_IDS declare admin mais le role en base "
                "est different : la base fait foi (ADR-023), promotion "
                f"manuelle requise | external_user_id={log_safe(external_user_id)}"
            ),
            user_id=row["user_id"],
        )
    return CurrentUser(
        external_user_id=external_user_id,
        user_id=row["user_id"],
        name=row.get("name") or display_name or "Utilisateur",
        role=stored_role,
    )


def _role_of(user_row: dict) -> str:
    """Rôle stocké en base (colonne role, défaut 'user')."""
    return user_row.get("role") or "user"


# ------------------------------------------------------------------
# Dépendances FastAPI (§4/§9)
# ------------------------------------------------------------------

def _extract_bearer(request: Request) -> str:
    """Extrait le Bearer token — 401 sinon."""
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (Bearer token)",
        )
    token = header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token manquant")
    return token


def _resolve_from_token(token: str) -> CurrentUser:
    """Token vérifié → CurrentUser (selon AUTH_MODE)."""
    if AUTH_MODE == "dev":
        # Mode dev : "dev:<internal_user_id>" OU "dev:<name>".
        # UUID → user interne existant (sessions de test des suites
        # de régression) ; name → provisioning local. L'identité
        # vient TOUJOURS du token, jamais du body.
        if not token.startswith("dev:"):
            raise HTTPException(
                status_code=401,
                detail="Mode dev : token attendu 'dev:<id|name>'",
            )
        ident = token[4:].strip()
        if not ident:
            raise HTTPException(401, detail="Token dev vide")
        # UUID interne existant ?
        row = users_db.get_user(ident)
        if row is not None:
            return CurrentUser(
                external_user_id=row.get("external_user_id")
                or f"dev-{row['user_id'][:8]}",
                user_id=row["user_id"],
                name=row["name"],
                role=_role_of(row),
            )
        # admin flag config : ADMIN_EXTERNAL_IDS "dev-admin"
        if ident in ADMIN_EXTERNAL_IDS:
            return resolve_internal_user(
                f"dev-{ident}", ident
            )
        return resolve_internal_user(
            f"dev-{ident[:24]}", ident
        )

    # Mode neon : vérification RÉELLE des JWT Neon Managed Better Auth
    # ( JWKS → sub → user interne ). Le sub est l'identifiant
    # externe : resolve_internal_user le mappe en user interne
    # ( provisioning au premier login ).
    if AUTH_MODE == "neon":
        try:
            claims = verify_neon_token(token)
        except HTTPException:
            raise
        except Exception as exc:  # jwt.ExpiredSignatureError, etc.
            log_event(
                "AUTH_REJECT",
                message=(
                    f"Token rejected | mode=neon err={log_safe(exc)}"
                ),
            )
            raise HTTPException(
                status_code=401,
                detail="Token invalide ou expiré",
            )
        sub = claims.get("sub") or ""
        if not sub:
            raise HTTPException(
                status_code=401, detail="Token sans sub"
            )
        # Nom d'affichage depuis les claims Neon/Better Auth
        # ( email prioritaire, puis name ).
        display = (
            claims.get("email")
            or claims.get("name")
            or claims.get("username")
            or ""
        )
        return resolve_internal_user(sub, display)

    # ⚠️ FAIL-CLOSED : AUTH_MODE inconnu ou mal orthographié.
    # AVANT ce garde-fou, la fonction tombait hors de tout `if` et
    # retournait None — une dépendance FastAPI recevant None casse
    # l'isolation SILENCIEUSEMENT ( pas de 401, pas de log ).
    # Toute valeur hors {neon, dev} est donc un défaut de config :
    # 503 explicite, jamais None. AUTH_MODE n'est pas secret
    # ( déjà renvoyé par GET /api/health/auth ).
    log_event(
        "AUTH_REJECT",
        message=f"AUTH_MODE inconnu | mode={AUTH_MODE!r}",
    )
    raise HTTPException(
        status_code=503,
        detail=f"Mode d'authentification non supporté : {AUTH_MODE!r}",
    )


def get_current_user(
    request: Request,
) -> CurrentUser:
    """DÉPENDANCE CENTRALE — l'identité vient UNIQUEMENT d'ici."""
    token = _extract_bearer(request)
    return _resolve_from_token(token)


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """401 si non authentifié, 403 si role=user, sinon admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Réservé aux administrateurs",
        )
    return current_user


def optional_current_user(
    request: Request,
) -> CurrentUser | None:
    """User courant si token présent et valide — None sinon.

    Pour les routes publiques qui s'enrichissent si authentifiées
    ( ex : /api/health reste public ).
    """
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    try:
        token = header[7:].strip()
        if not token:
            return None
        return _resolve_from_token(token)
    except HTTPException:
        return None


# ------------------------------------------------------------------
# Health de l'auth ( observabilité )
# ------------------------------------------------------------------

def auth_mode() -> str:
    return AUTH_MODE


_last_jwks_check: dict = {}


def jwks_reachable() -> bool:
    """Test réseau du JWKS ( sans cache ) — observabilité health.

    Neon Auth est le SEUL fournisseur d'identité : son well-known est
    testé dans tous les modes, y compris dev — en dev on observe la
    joignabilité de la cible de PRODUCTION, pas d'unJWKS local.
    """
    global _last_jwks_check
    now = time.time()
    if now - _last_jwks_check.get("ts", 0) < 30:
        return _last_jwks_check.get("ok", False)
    jwks_url = NEON_AUTH_JWKS_URL
    if not jwks_url:
        _last_jwks_check = {"ts": now, "ok": False}
        return False
    try:
        client = PyJWKClient(jwks_url, cache_keys=True)
        client.get_signing_keys()
        _last_jwks_check = {"ts": now, "ok": True}
        return True
    except Exception:
        _last_jwks_check = {"ts": now, "ok": False}
        return False
