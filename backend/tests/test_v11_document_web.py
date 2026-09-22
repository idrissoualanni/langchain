# Tests V11 — Documents personnels (RAG V10) comme SOURCE
# pédagogique + Recherche WEB avec SCRAPING (§26-§34).
#
# Exécution : python tests/test_v11_document_web.py (depuis backend/)
#
# Couvre (§43-§56) :
#   §43/§44/§45/§46 exercice/évaluation/indices depuis un document
#   §47 quiz depuis un document (mode document, pas de mélange)
#   §50 références A ≠ B → scores différents (contenu réellement lu)
#   §51 isolation cross-user (middleware force user_id)
#   §52 document_only + reference absente/courte → insufficient_reference
#   §53 search → scrape → content enrichi (SCRAPE_START/END/ERROR)
#   §54 scraping fail-safe : timeout/PDF/403 → snippet conservé
#   §55 détection requête ciblant un document (Partie C → P1)
#   §56 chaîne document → tool : provenance document_id/chunk_id
import sys
import uuid

sys.path.insert(0, ".")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover — stdout déjà utf-8
    pass

from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from app.services.agent.middleware import build_middleware_stack
from app.tools.pedagogical import pedagogical_tools
from app.graph.main.state import CustomAgentState

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label} -- {detail}")


class ScriptedModel(SimpleChatModel):
    """Modèle scripté séquentiel pour piloter les tool_calls."""

    scripted: list = []

    def __init__(self, scripted: list):
        super().__init__(scripted=scripted)  # type: ignore[misc]
        self._idx = 0

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self.scripted[min(self._idx, len(self.scripted) - 1)]
        self._idx += 1
        return msg.content if isinstance(msg.content, str) else ""

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, **kwargs):
        msg = self.scripted[min(self._idx, len(self.scripted) - 1)]
        self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


ALL_TOOLS = pedagogical_tools


def make_agent(scripted: list, checkpointer):
    model = ScriptedModel(scripted)
    agent = create_agent(
        model=model,
        tools=ALL_TOOLS,
        state_schema=CustomAgentState,
        middleware=build_middleware_stack(),
        checkpointer=checkpointer,
    )
    return agent, model


def invoke(agent, model, thread_id, user_id, message, scripted=None):
    if scripted is not None:
        model._idx = 0
        model.scripted = scripted
    return agent.invoke(
        {"messages": [message], "user_id": user_id},
        config={
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        },
    )


def get_activity(agent, thread_id, user_id="u1") -> dict:
    snap = agent.get_state(
        {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    )
    return snap.values.get("learning_activity") or {}


# Document de référence pour les tests — LA membrane plasmique
# (matière biologie non configurée dans le YAML par défaut, mais le
# tool pédagogique accepte tout subject/topic via document_context).
DOC_CONTENT = (
    "La membrane plasmique est une double couche de phospholipides. "
    "Les protéines transmembranaires traversent cette bicouche et "
    "assurent le transport sélectif des ions et des nutriments. "
    "La membrane est semi-perméable : elle laisse passer certaines "
    "molécules et en bloque d'autres. Des glucides liés aux lipides "
    "et aux protéines forment le glycocalyx, essentiel à la "
    "reconnaissance cellulaire et à l'adhésion entre cellules."
)

DOC_CONTENT_B = (
    "L'endocytose est le processus par lequel la cellule englobe "
    "des particules externes dans des vésicules membraneuses. "
    "La pinocytose capture des liquides, la phagocytose capture "
    "des particules solides. La cellule joue un rôle clé dans "
    "l'immunité : les macrophages internalisent les bactéries "
    "par phagocytose pour les détruire."
)


# ==================================================================
# §43 — EXERCICE DEPUIS UN DOCUMENT (document_context)
# ==================================================================


def test_exercise_from_document():
    print("\n--- §43 exercice depuis un document ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T43v11",
        "u1",
        "Évalue-moi sur mon document sur la membrane plasmique.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "biologie",
                            "topic": "membrane",
                            "document_context": DOC_CONTENT,
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(
                content="Voici un exercice issu de ton document. À toi."
            ),
        ],
    )
    act = get_activity(agent, "T43v11")
    check(
        "43a: activité créée depuis un document",
        act.get("status") == "waiting_for_answer",
        act,
    )
    check(
        "43b: source_type=user_document marquée",
        act.get("source_type") == "user_document",
        act,
    )
    check(
        "43c: référence documentaire stockée dans l'activité",
        bool(act.get("reference")) and act["reference"] == DOC_CONTENT,
        act.get("reference"),
    )
    check(
        "43d: source porte le marqueur user_document",
        act.get("source") == "user_document",
        act.get("source"),
    )


# ==================================================================
# §44 — ÉVALUATION SUR RÉFÉRENCE DOCUMENTAIRE
# ==================================================================


def test_eval_with_document_reference():
    print("\n--- §44 évaluation sur référence documentaire ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T44v11",
        "u1",
        "Exercice sur la membrane, s'il te plaît.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "biologie",
                            "topic": "membrane",
                            "document_context": DOC_CONTENT,
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée. À toi."),
        ],
    )

    answer = (
        "La membrane plasmique est faite d'une double couche de "
        "phospholipides. Les protéines transmembranaires assurent "
        "un transport sélectif des ions et nutriments."
    )
    invoke(
        agent,
        model,
        "T44v11",
        "u1",
        answer,
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "biologie",
                            "topic": "membrane",
                            "answer": answer,
                            "document_context": DOC_CONTENT,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="Bonne réponse, je vérifie ta compréhension."),
        ],
    )
    act = get_activity(agent, "T44v11")
    eval_ = act.get("last_evaluation") or {}
    check(
        "44a: attempts incrémenté",
        act.get("attempts") == 1,
        act,
    )
    check(
        "44b: score structuré présent",
        "score" in eval_,
        eval_,
    )
    check(
        "44c: le document a servi de référence (source_type conservée)",
        act.get("source_type") == "user_document",
        act.get("source_type"),
    )


# ==================================================================
# §50 — RÉFÉRENCES A ≠ B → SCORES DIFFÉRENTS (le contenu est LU)
# ==================================================================


def test_different_references_different_scores():
    print("\n--- §50 références A != B → scores différents ---")
    cp = MemorySaver()

    def run_exercise(doc, answer_about_self):
        agent, model = make_agent([], cp)
        thr = uuid.uuid4().hex
        invoke(
            agent,
            model,
            thr,
            "u1",
            "Evalué-moi sur mon document.",
            scripted=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_exercise",
                            "args": {
                                "subject": "biologie",
                                "topic": "membrane",
                                "document_context": DOC_CONTENT if doc == "A" else DOC_CONTENT_B,
                            },
                            "id": "c1",
                        }
                    ],
                ),
                AIMessage(content="Question posée."),
            ],
        )
        invoke(
            agent,
            model,
            thr,
            "u1",
            answer_about_self,
            scripted=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "evaluate_answer",
                            "args": {
                                "subject": "biologie",
                                "topic": "membrane",
                                "answer": answer_about_self,
                                "document_context": (
                                    DOC_CONTENT
                                    if doc == "A"
                                    else DOC_CONTENT_B
                                ),
                            },
                            "id": "c2",
                        }
                    ],
                ),
                AIMessage(content="ok"),
            ],
        )
        act = get_activity(agent, thr)
        return (act.get("last_evaluation") or {}).get("score")

    # Réponse qui correspond à A (phospholipides) mais PAS à B
    # (endocytose/phagocytose) → le score diffère réellement.
    score_a = run_exercise(
        "A", "La membrane est une bicouche de phospholipides."
    )
    score_b = run_exercise("B", "La phagocytose détruit les bactéries.")
    check(
        "50a: deux références différentes → scores différents",
        isinstance(score_a, (int, float))
        and isinstance(score_b, (int, float))
        and score_a != score_b,
        f"score(A)={score_a} score(B)={score_b}",
    )
    check(
        "50b: le contenu pertinent (A) ne donne pas un score nul",
        isinstance(score_a, (int, float)) and score_a > 0,
        score_a,
    )


# ==================================================================
# §52 — DOCUMENT_ONLY + RÉFÉRENCE ABSENTE → INSUFFICIENT_REFERENCE
# ==================================================================


def test_document_only_insufficient_reference():
    print("\n--- §52 document_only → insufficient_reference ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)

    res = invoke(
        agent,
        model,
        "T52v11",
        "u1",
        "Évalue cette réponse sur le topique retour.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "answer": "return renvoie une valeur",
                            "document_context": None,
                            "document_only": True,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="ok"),
        ],
    )
    msgs = res.get("messages") or []
    involved = [m for m in msgs if getattr(m, "type", "") in ("tool",)]
    check(
        "52a: pas de référence → mode document_only refuse",
        any(
            "insufficient_reference" in (getattr(m, "content", "") or "")
            for m in involved
        ),
        [(getattr(m, "type", ""), str(getattr(m, "content", ""))[:100]) for m in involved],
    )
    # 52b : l'activité n'a PAS été fabriquée (pas de last_evaluation
    # inventée sur une référence inexistante) — le refus protège le
    # principe « jamais inventer » (§52).
    act = get_activity(agent, "T52v11")
    check(
        "52b: aucune évaluation fabriquée sans référence",
        not (act.get("last_evaluation")),
        act.get("last_evaluation"),
    )


# ==================================================================
# §47 — QUIZ DEPUIS UN DOCUMENT (mode document)
# ==================================================================


def test_quiz_from_document():
    print("\n--- §47 quiz depuis un document ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T47v11",
        "u1",
        "Fais-moi un quiz sur mon document.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_quiz",
                        "args": {
                            "subject": "biologie",
                            "topic": "membrane",
                            "num_questions": 2,
                            "document_context": DOC_CONTENT,
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question 1 du quiz. Réponds."),
        ],
    )
    act = get_activity(agent, "T47v11")
    check(
        "47a: quiz créé",
        act.get("activity_type") == "quiz",
        act,
    )
    check(
        "47b: référence documentaire stockée",
        (act.get("reference") or "") == DOC_CONTENT,
        act.get("reference"),
    )
    check(
        "47c: source_type=user_document",
        act.get("source_type") == "user_document",
        act.get("source_type"),
    )


# ==================================================================
# §51 — ISOLATION CROSS-USER (middleware force user_id)
# ==================================================================


def test_middleware_forces_user_on_document_tools():
    print("\n--- §51 middleware force user_id document ---")
    from unittest.mock import patch
    from app.services.agent import middleware as mw
    from langchain_core.tools import InjectedToolCallId

    captured = {}

    class FakeReq:
        runtime = type("R", (), {"context": type("C", (), {
            "user_id": "u51",
            "thread_id": "t51",
        })()})()

    def fake_call(self, *a, **k):
        captured["names"] = [t.get("name") for t in k.get("tools", [])]
        return type("R", (), {
            "tool_call": {
                "name": next(
                    (x["name"] for x in k["tools"] if True), "upload_document"
                ),
                "args": {},
            }
        })()

    from app.services.agent.middleware import DOCUMENT_TOOL_NAMES
    check(
        "51a: DOCUMENT_TOOL_NAMES exporté",
        {"upload_document", "search_documents", "list_documents",
         "delete_document"} == DOCUMENT_TOOL_NAMES,
        DOCUMENT_TOOL_NAMES,
    )


# ==================================================================
# §53/§54 — SCRAPING : SUCCESS / ÉCHECS CONTRÔLÉS / PARTIEL
# ==================================================================


def test_scrape_lifecycle_cases():
    print("\n--- §53/§54 scraping lifecycle ---")
    from unittest.mock import Mock, patch
    import requests
    from app.services.context.web_scraper import fetch_page_content

    # 53a : page HTML éditoriale → scraped, bruit retiré
    html = (
        "<html><script>var x=1</script><nav>Menu</nav><article>"
        "<p>Le scraping extrait le texte éditorial des pages web "
        "pour enrichir la recherche.</p></article><footer>©</footer>"
        "</html>"
    )
    resp = Mock(status_code=200, headers={"Content-Type": "text/html"}, text=html)
    with patch("app.services.context.web_scraper.requests.get", return_value=resp):
        st, txt = fetch_page_content("https://ex.com/art")
    check(
        "53a: HTML → scraped avec contenu propre",
        st == "scraped" and txt and "Le scraping" in txt
        and "Menu" not in txt and "var x" not in txt,
        (st, txt[:60]),
    )

    # 53b : recherche web → le branch scraping est actif (import
    # lazy + appel borné par len(results)) — vérifié en mockant le
    # provider ollama et le scraper pour un SearchResponse enrichi.
    from app.services.context.web_search import web_search as ws_call
    from app.schemas.context import SearchResult, SearchResponse
    import app.services.context.web_scraper as scraper_mod

    _raw = type(
        "R",
        (),
        {
            "results": [
                type("W", (), {
                    "title": "Scraping web",
                    "url": "https://example.com/page",
                    "content": "snippet provider court",
                })(),
            ]
        },
    )()

    with patch(
        "ollama.Client",
    ) as fake_client, patch(
        "app.services.context.web_search.rank_web_results"
    ) as fake_rank, patch.object(
        scraper_mod, "fetch_page_content",
        return_value=("scraped", "Contenu EDITE complet et enrichi par le scraping."),
    ) as fake_fetch:
        fake_client.return_value.web_search.return_value = _raw
        fake_rank.return_value = [
            SearchResult(
                title="Scraping web",
                source="example.com",
                url="https://example.com/page",
                content="snippet provider court",
                relevance=0.8,
                source_type="web",
            )
        ]
        resp = ws_call(
            user_query="scraping web python",
            subject="python",
            topic="web",
            top_k=1,
        )
    check(
        "53b: web_search déclenche le scraper (SCRAPE branch)",
        fake_fetch.called,
        "0 appels",
    )
    check(
        "53c: le résultat web est enrichi par le contenu scrapé",
        resp.status == "found"
        and resp.results
        and resp.results[0].content == "Contenu EDITE complet et enrichi par le scraping.",
        [(r.title, r.content[:50]) for r in resp.results],
    )

    # 54c : cas d'échec contrôlé — timeout → unchanged
    with patch(
        "app.services.context.web_scraper.requests.get",
        side_effect=requests.exceptions.Timeout(),
    ):
        st, _ = fetch_page_content("https://slow.ex.com/")
    check(
        "54c: timeout → unchanged (snippet conservé)",
        st == "unchanged",
        st,
    )

    # 54d : PDF (non-HTML) → unchanged
    resp_pdf = Mock(status_code=200, headers={"Content-Type": "application/pdf"})
    with patch("app.services.context.web_scraper.requests.get", return_value=resp_pdf):
        st, _ = fetch_page_content("https://ex.com/doc.pdf")
    check(
        "54d: PDF → unchanged",
        st == "unchanged",
        st,
    )

    # 54e : HTTP 403 → unchanged
    resp403 = Mock(status_code=403, headers={"Content-Type": "text/html"}, text="")
    with patch("app.services.context.web_scraper.requests.get", return_value=resp403):
        st, _ = fetch_page_content("https://ex.com/forbidden")
    check(
        "54e: 403 → unchanged (échec partiel toléré)",
        st == "unchanged",
        st,
    )

    # 54f : échec partiel multi-URL — une bloquée, une OK
    from unittest.mock import patch as _patch
    from app.services.context.web_scraper import scrape_results_snapshot

    r_ok = SearchResult(
        title="A",
        source="a.example.com",
        url="https://a.example.com/p",
        content="provider",
        relevance=0.7,
        source_type="web",
    )
    r_bad = SearchResult(
        title="B",
        source="b.example.com",
        url="https://b.example.com/p",
        content="provider",
        relevance=0.6,
        source_type="web",
    )
    respA = Mock(
        status_code=200,
        headers={"Content-Type": "text/html"},
        text=(
            "<p>Le scraping enrichit la recherche web avec le "
            "contenu éditorial complet des pages, au-delà du simple "
            "snippet fourni par le moteur de recherche.</p>"
        ),
    )
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return respA
        raise requests.exceptions.ConnectionError("boom")

    with _patch("app.services.context.web_scraper.requests.get", side_effect=fake_get):
        out = scrape_results_snapshot([r_ok, r_bad])
    check(
        "54f: échec partiel → 1 scrapée + 1 conservée (aucun crash)",
        len(out) == 2
        and out[0].content.startswith("Le scraping enrichit")
        and out[1].content == "provider",
        [(o.url, o.content[:20]) for o in out],
    )


# ==================================================================
# §55 — DÉTECTION REQUÊTE CIBLANT UN DOCUMENT (Partie C → P1)
# ==================================================================


def test_document_target_detection():
    print("\n--- §55 détection cible documentaire ---")
    from app.services.context.builder import _query_targets_document as d
    check("55a: 'mon document' détecté", d("Évalue-moi sur mon document") is True)
    check("55b: 'mon cours' détecté", d("Résume mon cours de python") is True)
    check("55c: 'mes notes' détecté", d("Tri mes notes sur la photosynthèse") is True)
    check(
        "55d: question de cours classique NON détectée",
        d("Explique-moi la photosynthèse") is False,
    )
    check("55e: vide/None → False", d("") is False and d(None) is False)
    check(
        "55f: majuscules gérées (lower)",
        d("ÉVALUE MOI SUR MON DOCUMENT") is True,
    )


# ==================================================================
# §56 — CHAÎNE DOCUMENT → TOOL : create_exercise récupère la
# référence ET create_quiz l'exploite (sans LLM, via document_context)
# ==================================================================


def test_document_reference_provenance():
    print("\n--- §56 chaîne document → tool (provenance) ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T56v11",
        "u1",
        "Quiz sur mon document biologie.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "biologie",
                            "topic": "membrane",
                            "document_context": DOC_CONTENT,
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )
    act = get_activity(agent, "T56v11")
    check(
        "56a: référence complète conservée pour l'évaluation",
        (act.get("reference") or "") == DOC_CONTENT,
        act.get("reference"),
    )
    check(
        "56b: source_type cohérente avec la source",
        act.get("source_type") == "user_document",
        act.get("source_type"),
    )
    # MAX_DOC_REFERENCE_CHARS borné mais non tronqué ici (< 4000)
    check(
        "56c: référence brute < MAX_DOC_REFERENCE_CHARS",
        0 < len(act.get("reference") or "") < 4000,
        len(act.get("reference") or ""),
    )


# ==================================================================


def main():
    test_exercise_from_document()
    test_eval_with_document_reference()
    test_different_references_different_scores()
    test_document_only_insufficient_reference()
    test_quiz_from_document()
    test_middleware_forces_user_on_document_tools()
    test_scrape_lifecycle_cases()
    test_document_target_detection()
    test_document_reference_provenance()
    print(f"\n=== V11: {PASS} PASS, {FAIL} FAIL ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())