# Serveur MCP "filesystem" — tools de fichiers (création/lecture/
# écriture/listing) pour les workflows document/coding (§40).
#
# Lancé en stdio par le registry (app/mcp/registry.py). Tools exposés :
#   - create_file(path, content)  : crée un fichier (échec si existe)
#   - write_file(path, content)   : crée ou écrase un fichier (versionné)
#   - read_file(path)             : lit un fichier texte
#   - list_files(dir)             : liste les fichiers d'un répertoire
#
# STOCKAGE 100% EN BASE ( migration Neon ) : le contenu vit dans la table
# mcp_files, l'historique des écrasements dans mcp_file_versions. ZÉRO
# fichier sur disque — éphémère sur Render, perdu à chaque redéploiement.
#
# SÉCURITÉ (§41) — sandbox stricte, INTÉGRALEMENT CONSERVÉE :
#   1. Chemin validé ( traversal, absolu, ~, nul ) avant d'atteindre la
#      base. La sandbox vit dans le path, pas dans le stockage.
#   2. Pas d'exécution, pas de shell.
#   3. Taille bornée : écriture <= MCP_FS_MAX_BYTES, lecture tronquée
#      au-delà (un fichier énorme ne doit pas saturer le contexte).
#   4. Extensions textuelles seules (refus explicite des binaires /
#      exécutables — la lecture d'un .exe n'a aucun sens pédagogique).
#   5. Isolation par utilisateur ( MCP_FS_USER_ID propagé en env du
#      subprocess stdio — JAMAIS None : pas d'espace partagé ).
from __future__ import annotations

import os
from pathlib import PurePosixPath

from mcp.server.fastmcp import FastMCP

from app.services.storage.mcp_files import (
    McpFsError,
    create_file as db_create_file,
    delete_file as db_delete_file,
    file_exists as db_file_exists,
    list_files as db_list_files,
    read_file as db_read_file,
    write_file as db_write_file,
)

mcp = FastMCP("filesystem")

_MAX_BYTES = int(os.getenv("MCP_FS_MAX_BYTES", str(200_000)))  # 200 Ko
_READ_CAP = int(os.getenv("MCP_FS_READ_CAP", str(50_000)))  # 50 Ko envoyés au modèle

# user_id : propagé par toolset.py via l'env du subprocess. Un serveur qui
# isole ses données par utilisateur ne doit JAMAIS tomber sur un espace
# partagé — on refuse de démarrer sans identité explicite.
_USER_ID = os.getenv("MCP_FS_USER_ID", "").strip()
if not _USER_ID:
    # En local ( tests directs hors registry ), on accepte un override
    # explicite ; sinon on ÉCHOUE FORT plutôt que d'écrire sans propriétaire.
    _USER_ID = os.getenv("MCP_FS_USER_ID_TEST", "").strip()
if not _USER_ID and __name__ == "__main__":
    raise SystemExit(
        "MCP_FS_USER_ID requis : un serveur filesystem isolé par "
        "utilisateur ne peut pas démarrer sans propriétaire."
    )

# Extensions autorisées (texte/code uniquement — §41 : pas de binaire).
_ALLOWED_EXT = {
    ".txt", ".md", ".markdown", ".rst",
    ".json", ".yaml", ".yml", ".csv", ".tsv", ".ini", ".toml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb",
    ".php", ".sh", ".bash", ".sql", ".xml", ".svg", ".env",
}

_MAX_NAME = 120
_LIST_CAP = 200  # borne : pas de flooding du contexte


def _validate(path: str) -> str:
    """Valide `path` ( sécurités §41 ) et renvoie le chemin relatif pur.

    Refuse : chemins vides, absolus, ~, traversal (..), caractère nul,
    extension non textuelle, nom trop long. Ne touche plus au disque —
    la résolution filesystem disparaît avec la base.
    """
    if not path or not isinstance(path, str):
        raise ValueError("chemin requis")
    if "\x00" in path:
        raise ValueError("caractère nul interdit")
    if PurePosixPath(path).is_absolute() or path.startswith("~"):
        raise ValueError("chemin absolu ou ~ interdit — relatif à la racine uniquement")

    # Pas de traversal : on normalise avant résolution.
    normalized = PurePosixPath(path)
    if any(part == ".." for part in normalized.parts):
        raise ValueError("traversal (..) interdit")
    rel = normalized.as_posix().strip("/")
    if not rel:
        raise ValueError("chemin vide")

    name = normalized.name
    if not name or len(name) > _MAX_NAME:
        raise ValueError(f"nom de fichier invalide (<= {_MAX_NAME} caractères)")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        raise ValueError(
            f"extension '{suffix or '(aucune)'}' interdite — "
            f"texte/code uniquement"
        )
    return rel


def _guard_size(content: str) -> None:
    if not isinstance(content, str):
        raise ValueError("contenu textuel requis")
    if len(content.encode("utf-8")) > _MAX_BYTES:
        raise ValueError(f"contenu > {_MAX_BYTES} octets — écriture refusée")


@mcp.tool()
def create_file(path: str, content: str) -> str:
    """Crée un nouveau fichier avec ce contenu.

    Refuse si le fichier existe déjà (évite l'écrasement implicite —
    l'agent doit utiliser write_file pour remplacer).
    Retourne le chemin relatif + la taille créée.
    """
    rel = _validate(path)
    _guard_size(content)
    try:
        size, _file_id = db_create_file(_USER_ID, rel, content)
    except McpFsError as exc:
        raise ValueError(str(exc)) from exc
    return f"Créé : {rel} ({size} octets)"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Crée ou écrase un fichier avec ce contenu.

    Convention pédagogique : l'écrasement est explicite dans le nom de
    l'outil. L'ANCIEN contenu est VERSIONNÉ ( mcp_file_versions ) —
    jamais de perte de données silencieuse.
    """
    rel = _validate(path)
    _guard_size(content)
    try:
        size, _file_id, existed = db_write_file(_USER_ID, rel, content)
    except McpFsError as exc:
        raise ValueError(str(exc)) from exc
    verb = "Remplacé ( ancienne version conservée )" if existed else "Créé"
    return f"{verb} : {rel} ({size} octets)"


@mcp.tool()
def read_file(path: str) -> str:
    """Lit un fichier texte (tronqué à la capacité contexte).

    Refuse les fichiers absents — un retour structuré reste préférable
    à une erreur silencieuse.
    """
    rel = _validate(path)
    try:
        raw = db_read_file(_USER_ID, rel)
    except McpFsError as exc:
        raise FileNotFoundError(str(exc)) from exc
    if len(raw) > _READ_CAP:
        raw = raw[:_READ_CAP] + f"\n…[tronqué — {len(raw) - _READ_CAP} caractères restants]"
    return raw


@mcp.tool()
def list_files(dir: str = ".") -> str:
    """Liste les fichiers (récursif, borné) sous ce répertoire.

    Retourne un listing texte : un chemin par ligne, dossiers suffixés '/'.
    Les répertoires n'existent pas en base : ils sont IMPLICITES dans les
    chemins ( "devoir/main.py" ⇒ dossier "devoir" ).
    """
    prefix = dir or "."
    if prefix != ".":
        # Mêmes sécurités que _validate, sans la contrainte d'extension
        # ( on liste un répertoire, pas un fichier ).
        if "\x00" in prefix:
            raise ValueError("caractère nul interdit")
        if PurePosixPath(prefix).is_absolute() or prefix.startswith("~"):
            raise ValueError("chemin absolu ou ~ interdit")
        if any(part == ".." for part in PurePosixPath(prefix).parts):
            raise ValueError("traversal (..) interdit")

    try:
        paths = db_list_files(_USER_ID, prefix, limit=_LIST_CAP)
    except McpFsError as exc:
        raise FileNotFoundError(str(exc)) from exc

    if not paths:
        return "(vide)"

    # Reconstruit l'arbre : un dossier est tout préfixe de chemin présent.
    dirs: set[str] = set()
    entries: list[str] = []
    for p in paths:
        parts = PurePosixPath(p).parts
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        entries.append(p)
        # on affiche aussi les dossiers connus sous ce préfixe
    # trie : dossiers d'abord ( suffixe '/' ), puis fichiers
    lines = sorted(f"{d}/" for d in dirs) + sorted(entries)
    if len(paths) >= _LIST_CAP:
        lines.append(f"…[liste tronquée à {_LIST_CAP} entrées]")
    if not lines:
        return "(vide)"
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
