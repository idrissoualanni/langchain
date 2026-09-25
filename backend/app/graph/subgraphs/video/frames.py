# VideoSubgraph — EXTRACTION DE FRAMES pour l'analyse visuelle (LLM).
#
# L'agent ReAct ( agent.py ) analyse ces images pour décrire CE QUE LA
# VIDEO MONTRE ( slides, diagrammes, écran de code, gestes… ) — le
# transcript ( faster-whisper ) ne capte QUE ce qui est DIT. Les deux
# sont complémentaires : audio = parole, frames = image.
#
# Stratégies d'échantillonnage :
#   uniform → frames équiréparties sur la timeline ( par index ) ;
#   scene   → détection de coupures ( comparaison d'histogrammes HSV )
#             pour capter les CHANGEMENTS DE PLAN ( nouveau slide,
#             changement de scène… ), repli uniforme si peu de coupures.
#
# Déterministe, hors-ligne : aucun réseau, aucun LLM ( l'analyse LLM se
# fait dans agent.py, sur les frames produites ici ).
#
# Anti-régression ( même philosophie que transcribe.py ) : une vidéo
# illisible ou sans flux vidéo lève VideoFatalError — JAMAIS de frames
# factices présentées comme extraites de la vidéo.
from __future__ import annotations

import base64
from dataclasses import dataclass

from app.config import VIDEO_FRAME_STRATEGY
from app.logging.events import log_event

# Seuil de corrélation d'histogramme en-dessous duquel deux frames sont
# considérées comme des plans différents ( scene ). Empirique : 0.7
# sépare bien slides successifs sans exploser sur du bruit de compression.
_SCENE_CORRELATION_THRESHOLD = 0.7


class FrameExtractionError(Exception):
    """Erreur contrôlée d'extraction de frames."""


# Largeur max (px) d'une frame envoyee au LLM vision. Une frame 320x240
# PNG depasse deja ~35k tokens : 3 frames explosent le contexte de
# gpt-oss:20b ( 131k ). Redimensionner a 160px de large divise le cout
# par ~4 tout en conservant les elements exploitables ( slides, code ).
_FRAME_MAX_WIDTH = 160


@dataclass(frozen=True)
class Frame:
    """Une frame extraite, prête à l'envoi au LLM vision."""

    index: int
    timestamp: float
    # PNG encodé en base64 — format attendu par les messages multimodaux
    # LangChain ( {"type": "image_url", "image_url": {"url": data_url}} ).
    b64_png: str
    width: int
    height: int

    @property
    def data_url(self) -> str:
        """Data-URL prêt pour un HumanMessage multimodal LangChain."""
        return f"data:image/png;base64,{self.b64_png}"


def _probe_video(path: str):
    """Ouvre la vidéo — lève FrameExtractionError si illisible."""
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FrameExtractionError(
            f"ouverture impossible (illisible ou absente): {path}"
        )
    return cap


def _decode_to_png(frame_mat) -> tuple[str, int, int]:
    """Encode une frame OpenCV (BGR) en PNG base64 + dimensions.

    Redimensionne a _FRAME_MAX_WIDTH de large : une frame pleine
    resolution depasse le contexte du LLM vision ( voir commentaire de
    _FRAME_MAX_WIDTH ).
    """
    import cv2

    h, w = frame_mat.shape[:2]
    if w > _FRAME_MAX_WIDTH:
        scale = _FRAME_MAX_WIDTH / w
        frame_mat = cv2.resize(
            frame_mat,
            (_FRAME_MAX_WIDTH, max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buffer = cv2.imencode(".png", frame_mat)
    if not ok:
        raise FrameExtractionError("encodage PNG échoué (frame corrompue ?)")
    b64 = base64.b64encode(buffer.tobytes()).decode("ascii")
    h, w = frame_mat.shape[:2]
    return b64, w, h


def _frame_at(cap, index: int) -> Frame:
    """Positionne le curseur video sur un index et renvoie la Frame."""
    import cv2

    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, mat = cap.read()
    if not ok or mat is None:
        raise FrameExtractionError(f"lecture frame {index} échouée")
    b64, w, h = _decode_to_png(mat)
    return Frame(index=index, timestamp=0.0, b64_png=b64, width=w, height=h)


def _uniform_indexes(total_frames: int, count: int) -> list[int]:
    """Indexes équirépartis sur la timeline (toujours dans [0, total-1])."""
    if total_frames <= 0 or count <= 0:
        return []
    # count >= total → toutes les frames
    if count >= total_frames:
        return list(range(total_frames))
    # On évite les extrêmes (frame 0 noire, dernière tronquée) : on
    # échantillonne au milieu de chaque intervalle.
    step = total_frames / (count + 1)
    return [int(round(step * (i + 1))) for i in range(count)]


def _scene_indexes(path: str, cap, total_frames: int, count: int) -> list[int]:
    """Détection de coupures (histogrammes HSV correlés).

    On balaie la vidéo en se positionnant par pas bornés (lire toutes les
    frames d'une longue vidéo coûterait trop) ; on compare l'histogramme
    HSV de chaque échantillon au précédent et on garde les transitions.
    """
    import cv2

    if total_frames <= 0 or count <= 0:
        return []

    # Échantillon de balayage : au plus ~2 frames par frame voulue, pour
    # rester raisonnable sur une vidéo longue.
    scan_every = max(1, total_frames // (count * 4))
    boundaries: list[int] = [0]

    prev_hist = None
    idx = 0
    while idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, mat = cap.read()
        if not ok or mat is None:
            idx += scan_every
            continue
        hsv = cv2.cvtColor(mat, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev_hist is not None:
            correlation = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if correlation < _SCENE_CORRELATION_THRESHOLD:
                boundaries.append(idx)
        prev_hist = hist
        idx += scan_every

    # Complète par répartition uniforme si trop peu de coupures trouvées.
    if len(boundaries) < 2:
        log_event(
            "VIDEO_FRAMES_SCENE_FALLBACK",
            level="WARNING",
            message=(
                f"Peu de coupures détectées ({len(boundaries)}) — "
                "repli sur échantillonnage uniforme"
            ),
            extra={"operation": "video_frames"},
        )
        return _uniform_indexes(total_frames, count)

    # Plafonne au nombre demandé (premières coupures = ouverture).
    return boundaries[:count]


def extract_frames(
    local_path: str,
    *,
    count: int,
    strategy: str = "",
) -> list[Frame]:
    """Extrait `count` frames de la vidéo selon la stratégie.

    Retourne des Frame (PNG base64 + timestamp). Lève FrameExtractionError
    si la vidéo est illisible ou sans flux vidéo — l'appelant décide du
    statut (jamais de frames factices).

    count <= 0 ou stratégie inconnue → [] (rien à analyser, pas un échec).
    """
    if count <= 0:
        return []

    strat = (strategy or VIDEO_FRAME_STRATEGY or "uniform").strip().lower()
    cap = _probe_video(local_path)
    try:
        total = int(cap.get(7)) or 0  # CAP_PROP_FRAME_COUNT
        if total <= 0:
            raise FrameExtractionError(
                "flux vidéo vide ou durée indéterminée (0 frames)"
            )

        if strat == "scene":
            indexes = _scene_indexes(local_path, cap, total, count)
        else:
            indexes = _uniform_indexes(total, count)

        fps = cap.get(5) or 0.0  # CAP_PROP_FPS
        frames: list[Frame] = []
        for i in indexes:
            frame = _frame_at(cap, i)
            # Timestamp dérivé de l'index et du fps (repli 0 si inconnu).
            ts = round(i / fps, 2) if fps > 0 else 0.0
            frames.append(
                Frame(
                    index=i,
                    timestamp=ts,
                    b64_png=frame.b64_png,
                    width=frame.width,
                    height=frame.height,
                )
            )

        log_event(
            "VIDEO_FRAMES_OK",
            message=(
                f"Frames extraites | strategy={strat} | "
                f"frames={len(frames)} | total={total}"
            ),
            extra={
                "operation": "video_frames",
                "strategy": strat,
                "extracted": len(frames),
                "total_frames": total,
            },
        )
        return frames
    finally:
        cap.release()


__all__ = [
    "Frame",
    "FrameExtractionError",
    "extract_frames",
]
