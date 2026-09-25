"""
Tests DÉTERMINISTES du VideoSubgraph (§28).

Conformité mission :
  - pipeline hors chemin conversationnel : validate_upload → ingest →
    segment → enrich → index/persist → finalize ;
  - retries bornés sur erreurs TRANSITOIRES uniquement (jamais de
    boucle infinite, jamais de ré-ingestion au retrieval) ;
  - sortie structurée VideoResult (§8), état interne jamais exposé ;
  - aucun réseau / flux réel : transcription et ingestion STUBBÉES.

Lancement (depuis backend/) :
    ..\\.venv\\Scripts\\python.exe -m pytest -q tests/test_video_subgraph.py -x
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import pytest
from pydantic import ValidationError

from app.schemas.workflow import VideoResult
from app.graph.subgraphs.video.ingest import (
    VideoFatalError,
    VideoTransientError,
    ingest_video,
    locate_source,
    reset_services,
    use_services,
)
from app.graph.subgraphs.video.nodes import (
    MAX_ATTEMPTS_DEFAULT,
    compile_video_subgraph,
    run_video_subgraph,
    validate_upload_node,
)
from app.graph.subgraphs.video.persist import VideoKnowledgeStore
from app.graph.subgraphs.video.retrieval import get_video, search_video_segments
from app.schemas.video import (
    PedagogicalSegment,
    VideoUploadPayload,
)
from app.graph.subgraphs.video.segment import (
    SegmentationError,
    extract_topics,
    segment_parts,
    segment_transcript,
    split_sentences,
)
from app.graph.subgraphs.video.state import VideoState

LESSON = (
    "Salut, cette vidéo présente la définition des fonctions en Python.\n"
    "Une fonction regroupe des instructions sous un nom explicite.\n"
    "Le mot-clé def introduit le corps de la fonction.\n"
    "Les arguments permettent de passer des données à la fonction.\n"
    "Les arguments peuvent recevoir une valeur par défaut.\n"
    "Le mot-clé return renvoie le résultat de la fonction.\n"
    "Le return termine immédiatement l'exécution de la fonction.\n"
    "La portée locale protège les variables définies à l'intérieur.\n"
    "Les tests unitaires vérifient le comportement attendu.\n"
    "Les erreurs de type sont explorées par les tests.\n"
    "Documenter chaque fonction aide la relecture du code.\n"
    "Merci d'avoir regardé cette vidéo sur les fonctions Python.\n"
)

MISSION_STATE_KEYS = (
    "video_id", "user_id", "filename", "source_url", "local_path",
    "duration", "audio_path", "transcript_path", "segments", "metadata",
    "status", "progress", "errors", "iteration", "max_attempts", "result",
)


class CountingTranscriber:
    """Stub de transcription : comptabilise les appels / injecte des erreurs."""

    def __init__(self, transcript: str = LESSON, errors=()):
        self.transcript = transcript
        self.errors = list(errors)
        self.calls = 0

    def __call__(self, local_path="", audio_path="", filename="", duration=0.0):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.transcript


@pytest.fixture(autouse=True)
def _reset_services():
    reset_services()
    yield
    reset_services()


@pytest.fixture()
def media_file(tmp_path):
    media = tmp_path / "lesson.mp4"
    media.write_bytes(b"fake-media-bytes")
    return media


def _payload(tmp_path, media, **over):
    payload = {
        "filename": "lesson.mp4",
        "source_url": str(media),
        "duration": 120.0,
        "options": {
            "working_dir": str(tmp_path / "wd"),
            "store_dir": str(tmp_path / "store"),
        },
    }
    payload.update(over)
    return payload


# ============================================================
# A. ÉTAT + CONTRATS
# ============================================================


class TestStateAndContracts:
    def test_state_has_mission_fields(self):
        missing = set(MISSION_STATE_KEYS) - set(VideoState.__annotations__)
        assert not missing, f"champs mission manquants: {missing}"

    def test_payload_strict_extra_forbid(self):
        with pytest.raises(ValidationError):
            VideoUploadPayload(
                filename="a.mp4", source_url="/x/a.mp4", inconnu=1
            )

    def test_video_result_contract(self):
        r = VideoResult(workflow="video", segments=[{"title": "Intro"}])
        assert r.status == "ok"
        assert r.segments[0]["title"] == "Intro"
        with pytest.raises(ValidationError):
            VideoResult(workflow="video", champ_inconnu=1)

    def test_pedagogical_segment_validation(self):
        with pytest.raises(ValidationError):
            PedagogicalSegment(title="x", start=10.0, end=2.0)


# ============================================================
# B. SERVICES PURS (ingestion / segmentation)
# ============================================================


class TestIngestServices:
    def test_locate_source_local(self, tmp_path):
        p = tmp_path / "f.mp4"
        p.write_bytes(b"x")
        loc = locate_source(str(p))
        assert loc["origin"] == "local"
        assert loc["filename"] == "f.mp4"

    def test_locate_source_file_uri(self):
        loc = locate_source("file:///data/lesson.mp4")
        assert loc["origin"] == "local"

    def test_locate_source_remote(self):
        loc = locate_source("https://cdn.example/lesson.mp4")
        assert loc["origin"] == "remote"

    def test_locate_source_missing_local_is_transient(self):
        with pytest.raises(VideoTransientError):
            locate_source("C:/abs/pas/là/mp4") if os.name == "nt" else locate_source("/abs/pas/là.mp4")

    def test_ingest_local_file_with_stub(self, tmp_path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"DATA")
        stub = CountingTranscriber("un transcript de test")
        use_services(transcriber=stub)
        out = ingest_video(
            source_url=str(src),
            filename="v.mp4",
            dest_dir=str(tmp_path / "media"),
            duration=60.0,
        )
        assert stub.calls == 1
        assert out["origin"] == "local"
        assert out["duration"] == 60.0
        assert Path(out["local_path"]).exists()
        assert Path(out["audio_path"]).exists()
        transcript_file = Path(out["transcript_path"])
        assert transcript_file.read_text(encoding="utf-8") == "un transcript de test"

    def test_ingest_remote_without_downloader_fails_transient(self, tmp_path):
        with pytest.raises(VideoTransientError):
            ingest_video(
                source_url="https://example.com/lesson.mp4",
                filename="lesson.mp4",
                dest_dir=str(tmp_path / "media"),
            )


class TestSegmentation:
    def test_split_sentences(self):
        parts = split_sentences("Premier. Deuxième!\nTroisième.\n")
        assert "Premier." in parts
        assert len(parts) >= 2

    def test_extract_topics_deterministic(self):
        a = extract_topics(LESSON, top_n=3)
        b = extract_topics(LESSON, top_n=3)
        assert a == b
        assert a, "topics non vides"

    def test_segment_transcript_well_formed(self, tmp_path):
        segments = segment_transcript(LESSON, duration=120.0)
        assert len(segments) >= 2
        prev_end = 0.0
        for i, seg in enumerate(segments):
            PedagogicalSegment(**seg)  # validé
            assert seg["start"] >= 0.0
            assert seg["end"] >= seg["start"]
            assert seg["start"] >= prev_end - 1e-9
            assert seg["end"] <= 120.0 + 1e-9
            assert seg["title"] or seg["summary"]
            assert seg["start"] == pytest.approx(prev_end, abs=1e-6)
            prev_end = seg["end"]
        assert segments[-1]["end"] <= 120.0

    def test_segment_transcript_rejects_empty(self):
        with pytest.raises(SegmentationError):
            segment_transcript("   ")


# ============================================================
# C. PIPELINE COMPLET (graphe LangGraph, hors-ligne)
# ============================================================


class TestPipeline:
    def test_full_pipeline_success(self, tmp_path, media_file):
        value = 0.0
        stub = CountingTranscriber(LESSON)
        use_services(transcriber=stub)
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "thread_id": "t1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "duration": 120.0,
                "max_attempts": MAX_ATTEMPTS_DEFAULT,
                "metadata": {"options": {"working_dir": str(tmp_path / "wd"),
                                         "store_dir": str(tmp_path / "store")}},
            }
        )
        assert out["status"] == "done"
        assert out["progress"] == 1.0
        assert out["result"]["workflow"] == "video"
        assert out["result"]["status"] == "ok"
        assert out["result"]["video_id"].startswith("vid-")
        assert out["result"]["transcript"].strip()
        assert len(out["result"]["segments"]) >= 1
        assert out["result"]["knowledge_keys"] == [
            f"video://u1/{out['result']['video_id']}"
        ]
        assert stub.calls == 1
        # la vidéo est devenue une source de connaissance persistée
        store = VideoKnowledgeStore(tmp_path / "store")
        assert store.get_video("u1", out["result"]["video_id"]) is not None

    def test_run_facade_returns_videoresult(self, tmp_path, media_file):
        stub = CountingTranscriber(LESSON)
        use_services(transcriber=stub)
        r = run_video_subgraph(
            _payload(tmp_path, media_file), user_id="u1", thread_id="t1"
        )
        assert isinstance(r, VideoResult)
        assert r.status == "ok"
        assert r.segments
        assert r.video_id

    def test_validate_rejects_missing_source_url_no_retry(self, tmp_path):
        stub = CountingTranscriber(LESSON)
        use_services(transcriber=stub)
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": "",
                "metadata": {"options": {"working_dir": str(tmp_path / "wd")}},
            }
        )
        assert out["status"] == "done"
        assert out["result"]["status"] == "error"
        assert stub.calls == 0  # jamais d'ingestion → jamais de boucle

    def test_validate_node_progress(self, tmp_path, media_file):
        out = validate_upload_node(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
            }
        )
        assert out["status"] == "validated"
        assert out["progress"] == 0.1


# ============================================================
# D. RETRIES BORNÉS (erreurs transitoires / définitives)
# ============================================================


class TestBoundedRetries:
    def test_transient_then_success(self, tmp_path, media_file):
        errors = [VideoTransientError("provider KO 1"), VideoTransientError("provider KO 2")]
        stub = CountingTranscriber(LESSON, errors=errors)
        use_services(transcriber=stub)
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "duration": 120.0,
                "max_attempts": 3,
                "metadata": {"options": {"working_dir": str(tmp_path / "wd"),
                                         "store_dir": str(tmp_path / "store")}},
            }
        )
        assert out["result"]["status"] == "ok"
        assert stub.calls == 3  # 2 échecs transitoires + 1 succès
        assert out["max_attempts"] == 3

    def test_transient_exhausted_is_bounded(self, tmp_path, media_file):
        stub = CountingTranscriber(
            LESSON, errors=[VideoTransientError("toujours KO")] * 5
        )
        use_services(transcriber=stub)
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "max_attempts": 2,
                "metadata": {"options": {"working_dir": str(tmp_path / "wd")}},
            }
        )
        assert out["status"] == "done"
        assert out["result"]["status"] == "error"
        assert stub.calls == 2  # BORNÉ : max_attempts, pas de boucle infinie
        assert out["iteration"] == 2

    def test_fatal_error_never_retried(self, tmp_path, media_file):
        stub = CountingTranscriber(
            LESSON, errors=[VideoFatalError("source corrompue")] * 3
        )
        use_services(transcriber=stub)
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "max_attempts": 3,
                "metadata": {"options": {"working_dir": str(tmp_path / "wd")}},
            }
        )
        assert stub.calls == 1  # définitif → pas de retry
        assert out["iteration"] == 0
        assert out["result"]["status"] == "error"

    def test_remote_url_safe_offline_bounded(self, tmp_path):
        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": "https://example.com/lesson.mp4",
                "max_attempts": 2,
                "metadata": {"options": {"working_dir": str(tmp_path / "wd")}},
            }
        )
        # Aucun downloader réel : échec transitoire borné (2 tentatives).
        assert out["result"]["status"] == "error"
        assert out["iteration"] == 2


# ============================================================
# E. ÉCHEC D'INDEX → partial (jamais de message d'erreur brute)
# ============================================================


class TestIndexFailure:
    def test_index_failure_produces_partial(self, tmp_path, media_file, monkeypatch):
        # Forcer le mode JSON local : store_dir occupe par un FICHIER
        # fait echouer l'ecriture du store ( mkdir impossible ), ce qui
        # declenche le chemin index_failed -> status "partial".
        # En mode PostgreSQL ( Neon ), le store_dir fichier n'empeche
        # plus l'indexation en base — on force donc le mode JSON local.
        occupied = tmp_path / "occupied"
        occupied.write_text("bloque le dossier")
        use_services(transcriber=CountingTranscriber(LESSON))

        import app.graph.subgraphs.video.persist as persist_mod

        monkeypatch.setattr(persist_mod, "USE_POSTGRES", False)
        monkeypatch.setattr(persist_mod, "DATABASE_URL", "")

        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "metadata": {"options": {"working_dir": str(tmp_path / "wd"),
                                         "store_dir": str(occupied)}},
            }
        )
        assert out["status"] == "done"
        assert out["result"]["status"] == "partial"
        assert out["result"]["segments"]  # la segmentation survit
        assert any("index" in e for e in out["errors"])
        assert out["result"]["knowledge_keys"] == []

    def test_index_failure_produces_partial_in_postgres(
        self, tmp_path, media_file, monkeypatch
    ):
        # En mode PostgreSQL ( Neon ), l'echec d'indexation vient de la
        # base — on l'injecte via monkeypatch ( aucun ecriture reelle ).
        use_services(transcriber=CountingTranscriber(LESSON))

        import app.graph.subgraphs.video.persist as persist_mod

        def _boom(self, **kwargs):
            raise RuntimeError("neon injoignable (simule)")

        monkeypatch.setattr(
            persist_mod.VideoKnowledgeStore, "_persist_video_pg", _boom
        )
        monkeypatch.setattr(persist_mod, "USE_POSTGRES", True)
        monkeypatch.setattr(persist_mod, "DATABASE_URL", "postgresql://fake")

        graph = compile_video_subgraph()
        out = graph.invoke(
            {
                "user_id": "u1",
                "filename": "lesson.mp4",
                "source_url": str(media_file),
                "metadata": {"options": {"working_dir": str(tmp_path / "wd")}},
            }
        )
        assert out["status"] == "done"
        assert out["result"]["status"] == "partial"
        assert out["result"]["segments"]
        assert any("index" in e for e in out["errors"])


# ============================================================
# F. RETRIEVAL SANS RÉ-INGESTION
# ============================================================


class TestRetrievalNoReingestion:
    def test_retrieval_does_not_retranscribe(self, tmp_path, media_file):
        stub = CountingTranscriber(LESSON)
        use_services(transcriber=stub)
        r = run_video_subgraph(
            _payload(tmp_path, media_file), user_id="u1", thread_id="t1"
        )
        calls_after_ingestion = stub.calls
        assert calls_after_ingestion == 1

        store = VideoKnowledgeStore(tmp_path / "store")
        video = get_video("u1", r.video_id, store)
        assert video is not None
        assert len(video["segments"]) >= 1

        resp = search_video_segments(
            "u1", "arguments", video_id=r.video_id, store=store
        )
        assert resp["status"] == "found"
        assert stub.calls == calls_after_ingestion  # AUCUNE ré-ingestion

    def test_search_relevance_and_insufficient(self, tmp_path):
        store = VideoKnowledgeStore(tmp_path / "store")
        parts = segment_parts(LESSON, duration=120.0)
        store.persist_video(
            video_id="v1",
            user_id="u1",
            filename="cours.mp4",
            source_url="file://local/cours.mp4",
            duration=120.0,
            transcript=LESSON,
            segments=[p["segment"] for p in parts],
            segment_texts=[p["text"] for p in parts],
        )
        resp = search_video_segments("u1", "arguments", store=store)
        assert resp["status"] == "found"
        assert resp["results"]
        assert resp["results"][0]["relevance"] > 0

        # Matche via le texte STOCKÉ (pas de ré-ingestion).
        resp2 = search_video_segments("u1", "tests unitaires", store=store)
        assert resp2["status"] == "found"
        assert any("test" in r["segment"]["summary"] or r["relevance"] >= 1.0
                   for r in resp2["results"])

        resp3 = search_video_segments("u1", "trucbidulexyz", store=store)
        assert resp3["status"] == "insufficient"

    def test_search_fallback_without_segment_texts(self, tmp_path):
        # Sans texte stocké, le scoring se rabat sur title/summary/topics.
        store = VideoKnowledgeStore(tmp_path / "store2")
        store.persist_video(
            video_id="v2", user_id="u1", filename="a.mp4",
            source_url="x", transcript=LESSON,
            segments=segment_transcript(LESSON, duration=120.0),
        )
        assert search_video_segments("u1", "arguments", store=store)["status"] == "found"

    def test_store_isolation_by_user(self, tmp_path):
        store = VideoKnowledgeStore(tmp_path / "store")
        store.persist_video(
            video_id="v1", user_id="u1", filename="a.mp4",
            source_url="x", transcript=LESSON,
            segments=segment_transcript(LESSON),
        )
        assert store.get_video("u2", "v1") is None
        assert get_video("u1", "v1", store) is not None


# ============================================================
# G. STRUCTURE DU GRAPHE
# ============================================================


class TestGraphStructure:
    def test_compile_contains_pipeline_nodes(self):
        g = compile_video_subgraph().get_graph()
        names = {n if isinstance(n, str) else str(n) for n in g.nodes}
        assert {"validate_upload", "ingest", "segment", "enrich", "index", "finalize"} <= names

    def test_max_attempts_default_bounded(self):
        assert MAX_ATTEMPTS_DEFAULT == 3

# ============================================================
# H. TRANSCRIPTION RÉELLE (faster-whisper)
# ============================================================

from app.config import VIDEO_TRANSCRIPTION_MODE
from app.graph.subgraphs.video.transcribe import (
    resolve_transcriber,
    whisper_transcriber,
    _whisper_available,
)


class TestTranscriptionMode:
    """Résolution du transcriber selon la config et la disponibilité."""

    def test_offline_mode_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.graph.subgraphs.video.transcribe.VIDEO_TRANSCRIPTION_MODE",
            "offline",
        )
        assert resolve_transcriber() is None

    def test_whisper_forced_but_absent_raises(self, monkeypatch):
        monkeypatch.setattr(
            "app.graph.subgraphs.video.transcribe.VIDEO_TRANSCRIPTION_MODE",
            "whisper",
        )
        monkeypatch.setattr(
            "app.graph.subgraphs.video.transcribe._whisper_available",
            lambda: False,
        )
        with pytest.raises(VideoFatalError):
            resolve_transcriber()

    def test_auto_falls_back_without_lib(self, monkeypatch):
        monkeypatch.setattr(
            "app.graph.subgraphs.video.transcribe.VIDEO_TRANSCRIPTION_MODE",
            "auto",
        )
        monkeypatch.setattr(
            "app.graph.subgraphs.video.transcribe._whisper_available",
            lambda: False,
        )
        # Aucune injection explicite → repli sur le bouchon.
        reset_services()
        assert resolve_transcriber() is None


@pytest.mark.skipif(
    not _whisper_available(), reason="faster-whisper non installé"
)
class TestWhisperTranscriber:
    """Transcription réelle — nécessite faster-whisper (CPU)."""

    def test_audio_sans_parole_echec_controle(self, tmp_path):
        # Vidéo silencieuse (ffmpeg testsrc) → pas d'audio exploitable.
        import subprocess

        video = tmp_path / "silence.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-c:v", "libx264", str(video),
                ],
                check=True, timeout=60, capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("ffmpeg indisponible")

        with pytest.raises(VideoFatalError):
            whisper_transcriber(local_path=str(video), filename="silence.mp4")
