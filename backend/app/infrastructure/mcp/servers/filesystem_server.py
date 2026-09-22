# Serveur MCP "filesystem" — tools de fichiers (création/lecture/
# écriture/listing) pour les workflows document/coding (§40).
#
# Lancé en stdio par le registry (app/mcp/registry.py). Tools exposés :
#   - create_file(path, content)  : crée un fichier (échec si existe)
#   - write_file(path, content)   : crée ou écrase un fichier
#   - read_file(path)             : lit un fichier texte
#   - list_files(dir)             : liste les fichiers d'un répertoire
#
# SÉCURITÉ (§41) — sandbox stricte :
#   1. Racine imposée : data/workspace/files (MCP_FS_ROOT override).
#      Tout chemin en dehors est refusé (path traversal, absolu, ~…).
#   2. Pas d'exécution, pas de shell, pas de suivi de liens symboliques
#      hors racine (resolve() contrôlé).
#   3. Taille bornée : écriture <= MCP_FS_MAX_BYTES, lecture tronquée
#      au-delà (un fichier énorme ne doit pas saturer le contexte).
#   4. Extensions textuelles seules (refus explicite des binaires /
#      exécutables — la lecture d'un .exe n'a aucun sens pédagogique).
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("filesystem")

# Racine sandbox : backend/data/workspace/files (parents[4] depuis
# app/infrastructure/mcp/servers/filesystem_server.py). Déterministe quel
# que soit le CWD du subprocess MCP ; MCP_FS_ROOT permet l'override (tests).
# REFACTOR : ce fichier est dans app/infrastructure/mcp/servers/ →
# parents[4] = backend/ (qui contient data/workspace/files).
# Avant le déménagement, parents[4] valait la racine du repo :
# l'ancrage backend/ est la cible correcte.
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_ROOT = Path(os.getenv("MCP_FS_ROOT", str(_BACKEND_ROOT / "data" / "workspace" / "files"))).resolve()

_MAX_BYTES = int(os.getenv("MCP_FS_MAX_BYTES", str(200_000)))  # 200 Ko
_READ_CAP = int(os.getenv("MCP_FS_READ_CAP", str(50_000)))  # 50 Ko envoyés au modèle

# Extensions autorisées (texte/code uniquement — §41 : pas de binaire).
_ALLOWED_EXT = {
    ".txt", ".md", ".markdown", ".rst",
    ".json", ".yaml", ".yml", ".csv", ".tsv", ".ini", ".toml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb",
    ".php", ".sh", ".bash", ".sql", ".xml", ".svg", ".env",
}

_MAX_NAME = 120

# La racine existe toujours (créée à l'import, parents compris) — un
# list_files sur une racine vide renvoie "(vide)" plutôt qu'une erreur.
_ROOT.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> Path:
    """Résout `path` DANS la sandbox, ou lève ValueError (sécurité §41).

    Refuse : chemins vides, absolus, ~, traversal (..), symlink pointant
    hors racine, extension non textuelle, nom trop long.
    """
    if not path or not isinstance(path, str):
        raise ValueError("chemin requis")
    if "\x00" in path:
        raise ValueError("caractère nul interdit")
    if Path(path).is_absolute() or path.startswith("~"):
        raise ValueError("chemin absolu ou ~ interdit — relatif à la racine uniquement")

    # Pas de traversal : on normalise avant résolution. Path("a/b").parts
    # == ('a', 'b') — le séparateur n'apparaît jamais comme composant.
    normalized = Path(path)
    if any(part == ".." for part in normalized.parts):
        raise ValueError("traversal (..) interdit")
    if not normalized.as_posix().strip("/"):
        raise ValueError("chemin vide")

    resolved = (_ROOT / normalized).resolve()
    # Symlink hors racine : resolve() a suivi la cible, on revérifie.
    if _ROOT not in resolved.parents and resolved != _ROOT:
        raise ValueError("cible hors de la racine (symlink interdit)")

    name = resolved.name
    if not name or len(name) > _MAX_NAME:
        raise ValueError(f"nom de fichier invalide (<= {_MAX_NAME} caractères)")
    if resolved.suffix.lower() not in _ALLOWED_EXT:
        raise ValueError(
            f"extension '{resolved.suffix or '(aucune)'}' interdite — "
            f"texte/code uniquement"
        )
    return resolved


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
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"'{path}' existe déjà — write_file pour remplacer")
    _guard_size(content)
    target.write_text(content, encoding="utf-8")
    return f"Créé : {path} ({len(content.encode('utf-8'))} octets)"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Crée ou écrase un fichier avec ce contenu.

    Convention pédagogique : l'écrasement est explicite dans le nom de
    l'outil (jamais de perte de données silencieuse).
    """
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _guard_size(content)
    target.write_text(content, encoding="utf-8")
    return f"Écrit : {path} ({len(content.encode('utf-8'))} octets)"


@mcp.tool()
def read_file(path: str) -> str:
    """Lit un fichier texte (tronqué à la capacité contexte).

    Refuse les fichiers absents ou binaires — un retour structuré reste
    préférable à une erreur silencieuse.
    """
    target = _resolve(path)
    if not target.exists():
        raise FileNotFoundError(f"'{path}' introuvable")
    if target.is_dir():
        raise ValueError(f"'{path}' est un répertoire — list_files pour le contenu")
    raw = target.read_text(encoding="utf-8", errors="strict")
    if len(raw) > _READ_CAP:
        raw = raw[:_READ_CAP] + f"\n…[tronqué — {len(raw) - _READ_CAP} caractères restants]"
    return raw


@mcp.tool()
def list_files(dir: str = ".") -> str:
    """Liste les fichiers (récursif, borné) sous ce répertoire de la racine.

    Retourne un listing texte : un chemin par ligne, dossiers suffixés '/'.
    """
    base = _ROOT / Path(dir) if dir and dir != "." else _ROOT
    if dir and dir != ".":
        normalized = Path(dir)
        if any(part == ".." for part in normalized.parts):
            raise ValueError("traversal (..) interdit")
        base = (_ROOT / normalized).resolve()
        if _ROOT not in base.parents and base != _ROOT:
            raise ValueError("cible hors de la racine")
    if not base.exists():
        raise FileNotFoundError(f"'{dir}' introuvable")

    entries: list[str] = []
    for child in sorted(base.rglob("*")):
        rel = child.relative_to(_ROOT).as_posix()
        entries.append(f"{rel}/" if child.is_dir() else rel)
        if len(entries) >= 200:  # borne : pas de flooding du contexte
            entries.append("…[liste tronquée à 200 entrées]")
            break
    if not entries:
        return "(vide)"
    return "\n".join(entries)


if __name__ == "__main__":
    _ROOT.mkdir(parents=True, exist_ok=True)
    mcp.run()
