# VideoSubgraph — SERVICE INGESTION vidéo.
#
# Équivaut, EN DOSSIER, au service `video_ingest.py` décrit par le plan
# (§ mission : localisation/upload + transcription + événements SSE).
# Ce fichier n'existe PAS (encore) dans `backend/app/video/` à l'audit
# (RAPPORT-AUDIT-MASTER-PLAN : « fichier amorcé absent ») ; l'interface
# ci-dessous le remplace localement, sans réseau par défaut.
#
# Pipeline du service :
#   locate_source(source_url)      → classification déterministe
#                                    (local / file:// / remote http(s)) ;
#   localize + transcription       → transcript (str) ;
#   persistance du transcript      → transcript_path (fichier UTF-8).
#
# Injection de dépendances (download/transcription réels) via
# `use_services()` : le subgraph reste AUTONOME et déterministe — la
# transcription par défaut est un texte pédagogique hors-ligne (aucun
# appel réseau, aucun secret). Les erreurs transitoires
# (VideoTransientError) déclenchent le retry borné du subgraph ; les
# erreurs définitives (VideoFatalError) terminent immédiatement.
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

Transcriber = Callable[..., str]
Downloader = Callable[[dict, Path, str], str]


class VideoIngestError(Exception):
    """Erreur générique du service d'ingestion vidéo."""


class VideoTransientError(VideoIngestError):
    """Erreur TRANSITOIRE (réseau/provider) → retry borné du subgraph."""


class VideoFatalError(VideoIngestError):
    """Erreur DÉFINITIVE → jamais de retry (pas de boucle infinie)."""


# ---------------------------------------------------------------------
# Transcript par défaut (hors-ligne, déterministe, pédagogique FR).
# Un transcribeur réel (API/whisper) peut remplacer ce défaut via
# use_services(transcriber=...). Aucun secret dedans, jamais loggé.
# ---------------------------------------------------------------------
DEFAULT_TRANSCRIPT = (
    "Bienvenue dans ce cours sur les fonctions en Python.\n"
    "Une fonction est un bloc de code qui exécute une tâche précise.\n"
    "On définit une fonction avec le mot-clé def, suivi du nom explicite.\n"
    "Le nom reste en minuscules pour rester lisible dans le projet.\n"
    "Une fonction peut recevoir des arguments pour personnaliser son travail.\n"
    "Les arguments sont des valeurs transmises lors de l'appel de la fonction.\n"
    "On peut fournir des valeurs par défaut pour les arguments optionnels.\n"
    "Le retour se fait avec le mot-clé return, à la toute fin du corps.\n"
    "Le return permet de récupérer le résultat dans le code appelant.\n"
    "La portée d'une variable locale reste limitée à l'intérieur de la fonction.\n"
    "Les tests de la fonction valident les cas simples puis les cas limites.\n"
    "On vérifie aussi les erreurs possibles comme les types inattendus.\n"
    "Enfin, la documentation de la fonction aide vos collègues à relire.\n"
    "Merci et bonne pratique régulière pour progresser rapidement.\n"
)


def _default_transcriber(
    local_path: str = "",
    audio_path: str = "",
    filename: str = "",
    duration: float = 0.0,
) -> str:
    """Transcription DÉTERMINISTE hors-ligne (aucun réseau / flux réel).

    Réutilise le transcript pédagogique par défaut (aucun secret,
    contenu fixe et prévisible pour la segmentation).
    """
    return DEFAULT_TRANSCRIPT


def _default_downloader(
    origin: dict, dest_dir: Path, dest_name: str
) -> str:
    """Téléchargement par défaut : SOURCE LOCALE uniquement.

    - origine `local` (chemin ou file://) : copie du fichier vers
      dest_dir — jamais de réseau ;
    - origine `remote` (http/https) : aucune demande réseau par défaut
      → VideoTransientError (retry borné ; un downloader réel à
      injecter via use_services(downloader=...)).
    """
    dest = Path(dest_dir) / dest_name
    if origin.get("origin") == "local":
        source = Path(origin.get("source_url") or "")
        if not source.exists():
            raise VideoTransientError(
                f"source locale introuvable: {source.name}"
            )
        shutil.copyfile(str(source), str(dest))
        return str(dest)
    raise VideoTransientError(
        "téléchargement distant non configuré (mode hors-ligne)"
    )


# ---------------------------------------------------------------------
# Configuration de services injectables (stateful module-level, comme
# get_rag_store / résolution de provider dans le reste du projet).
# ---------------------------------------------------------------------
_active: dict = {"downloader": None, "transcriber": None}


def use_services(
    downloader: Downloader | None = None,
    transcriber: Transcriber | None = None,
) -> None:
    """Injecte downloader/transcriber réels (sinon défauts sûrs)."""
    if downloader is not None:
        _active["downloader"] = downloader
    if transcriber is not None:
        _active["transcriber"] = transcriber


def reset_services() -> None:
    """Rétablit les services par défaut (sûrs hors-ligne)."""
    _active["downloader"] = None
    _active["transcriber"] = None


def _downloader() -> Downloader:
    return _active["downloader"] or _default_downloader


def _transcriber() -> Transcriber:
    transcriber = _active.get("transcriber")
    if transcriber is not None:
        return transcriber  # injection explicite (tests)
    # Résolution automatique : whisper réel si disponible, sinon bouchon
    # pédagogique (repli hors-ligne, déterministe).
    from app.graph.subgraphs.video.transcribe import resolve_transcriber

    resolved = resolve_transcriber()
    return resolved if resolved is not None else _default_transcriber


# ---------------------------------------------------------------------
# Étapes pures du service
# ---------------------------------------------------------------------
def locate_source(source_url: str, filename: str = "") -> dict:
    """Classifie la source : local / file:// / remote http(s) (§28).

    Ne télécharge NI ne lit le fichier : classification pure et
    déterministe (testable sans réseau).
    """
    url = (source_url or "").strip()
    if not url:
        raise VideoFatalError("source_url vide")
    if url.startswith(("http://", "https://")):
        name = filename or url.rstrip("/").rsplit("/", 1)[-1] or "remote.mp4"
        return {
            "origin": "remote",
            "source_url": url,
            "filename": name,
        }
    if url.startswith("file://"):
        path = Path(url[len("file://"):])
        return {
            "origin": "local",
            "source_url": str(path),
            "filename": filename or path.name or "video.mp4",
        }
    path = Path(url)
    if not path.exists():
        raise VideoTransientError(f"source locale introuvable: {path.name}")
    return {
        "origin": "local",
        "source_url": str(path),
        "filename": filename or path.name,
    }


def _derive_audio_path(local_path: str) -> str:
    """Chemin audio dérivé du média local (placeholder déterministe).

    V1 : le média est transcrit sans extraction audio réelle ; le
    chemin est matérialisé (fichier vide) pour rester cohérent avec le
    contrat (audio_path). Un extracteur réel peut l'enrichir.
    """
    audio = Path(local_path).with_suffix(".audio.wav")
    try:
        if not audio.exists():
            audio.touch(exist_ok=True)
    except OSError:
        pass
    return str(audio)


def ingest_video(
    *,
    source_url: str,
    filename: str,
    dest_dir: str,
    duration: float = 0.0,
) -> dict:
    """Orchestre l'ingestion : localiser → matérialiser → transcrire →
    persister le transcript.

    Retourne :
      {local_path, audio_path, transcript_path, transcript, duration,
       origin, format}

    Lève VideoTransientError (retry) ou VideoFatalError (stop) ; les
    secrets/URLs ne sont jamais loggés ici (seul le nom de fichier).
    """
    origin = locate_source(source_url, filename)
    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)

    ext = Path(origin["filename"]).suffix or ".mp4"
    local_path = _downloader()(origin, dest_root, f"source{ext}")

    audio_path = _derive_audio_path(local_path)
    transcript = _transcriber()(
        local_path=local_path,
        audio_path=audio_path,
        filename=origin["filename"],
        duration=float(duration or 0.0),
    )
    if transcript is None or not str(transcript).strip():
        raise VideoFatalError("transcription vide (transcriber défaillant)")

    transcript_path = Path(local_path).with_suffix(".transcript.txt")
    transcript_path.write_text(str(transcript), encoding="utf-8")

    return {
        "local_path": local_path,
        "audio_path": audio_path,
        "transcript_path": str(transcript_path),
        "transcript": str(transcript),
        "duration": float(duration or 0.0),
        "origin": origin["origin"],
        "format": ext.lstrip(".").lower() or "mp4",
    }


__all__ = [
    "DEFAULT_TRANSCRIPT",
    "VideoFatalError",
    "VideoIngestError",
    "VideoTransientError",
    "ingest_video",
    "locate_source",
    "reset_services",
    "use_services",
]