# Tests unitaires V5.2 — tools pédagogiques interactifs.
#
# Exécution : python tests/test_v52_unit.py (depuis backend/)
#
# Couvre les tests critiques du brief :
#   §43 exercice sans réponse       → activité reste waiting_for_answer
#   §44 compréhension               → evaluate_answer → assess_understanding
#   §45 blocage                     → give_hint(level=0)
#   §46 hint progressif              → 0 → 1 → 2, jamais de saut
#   §47 quiz                        → 1 question à la fois
#   §48 code                        → exécutions multiples
#   §49 restart                     → persistance checkpointer
#   §50 cross-thread                → pas de transfert d'activité
#   §51 cross-user                  → isolation par user
#   §52 non-modification agent 1    → tools learning intacts
import sys
import uuid

sys.path.insert(0, ".")

from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from app.services.agent.middleware import build_middleware_stack
from app.tools.pedagogical import pedagogical_tools
from app.graph.main.state import CustomAgentState
from app.tools.coding import (
    code_tools,
    run_python_isolated,
    static_security_scan,
)

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


ALL_TOOLS = pedagogical_tools + code_tools


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


# ==================================================================
# §43 — EXERCICE SANS RÉPONSE : l'activité reste en attente
# ==================================================================


def test_exercise_stays_waiting():
    print("\n--- §43 exercice sans réponse ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T43",
        "u1",
        "Donne-moi un exercice sur les fonctions Python.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(
                content="Voici ton exercice : explique ce que fait "
                "return. À toi."
            ),
        ],
    )
    act = get_activity(agent, "T43")
    check(
        "43a: activité créée avec status=waiting_for_answer",
        act.get("status") == "waiting_for_answer",
        act,
    )
    check(
        "43b: awaiting_answer=True",
        act.get("awaiting_answer") is True,
    )
    check(
        "43c: activity_type=exercise",
        act.get("activity_type") == "exercise",
    )
    check(
        "43d: expected_response_type renseigné",
        bool(act.get("expected_response_type")),
    )
    check(
        "43e: source knowledge réelle",
        "functions" in (act.get("source") or ""),
        act.get("source"),
    )

    # L'étudiant envoie "Bonjour" — pas une réponse
    invoke(
        agent,
        model,
        "T43",
        "u1",
        "Bonjour.",
        scripted=[
            AIMessage(
                content="Je t'attends toujours sur l'exercice. "
                "Tu peux écrire ta réponse quand tu es prêt."
            ),
        ],
    )
    act = get_activity(agent, "T43")
    check(
        "43f: après 'Bonjour', statut TOUJOURS waiting_for_answer",
        act.get("status") == "waiting_for_answer",
        act,
    )
    check(
        "43g: pas d'évaluation fabriquée (attempts=0)",
        act.get("attempts", 0) == 0,
        act,
    )


# ==================================================================
# §44 — RÉPONSE → ÉVALUATION → VÉRIFICATION COMPRÉHENSION
# ==================================================================


def test_answer_then_understanding():
    print("\n--- §44 compréhension vérifiée ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T44",
        "u1",
        "Donne-moi un exercice sur return.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée. À toi."),
        ],
    )

    answer = (
        "return renvoie une valeur au code appelant et termine "
        "immédiatement l'exécution de la fonction. Sans return "
        "explicite, une fonction python renvoie None. On peut "
        "renvoyer plusieurs valeurs avec un tuple."
    )
    # FIX 44b (mission intégration §8) : le VRAI workflow est
    # MULTI-TOUR. Tour 2 : evaluate_answer → l'activité passe en
    # checking_understanding, le LLM demande une explication, puis
    # ATTEND. Tour 3 (nouvelle réponse utilisateur) :
    # assess_understanding. L'ancien test compressait les deux
    # tools dans le même tour → l'activité finissait completed
    # avant la vérification du status intermédiaire.
    invoke(
        agent,
        model,
        "T44",
        "u1",
        answer,
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "answer": answer,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(
                content="Très bonne réponse ! Maintenant, "
                "explique-moi pourquoi return plutôt que print "
                "ici."
            ),
        ],
    )
    act = get_activity(agent, "T44")
    check(
        "44a: attempts incrémenté",
        act.get("attempts") == 1,
        act,
    )
    check(
        "44b: status → checking_understanding (score élevé, multi-tour)",
        act.get("status") == "checking_understanding",
        act.get("status"),
    )
    check(
        "44c: last_evaluation structurée avec score",
        isinstance(act.get("last_evaluation"), dict)
        and "score" in act["last_evaluation"],
        act.get("last_evaluation"),
    )
    # Tour 3 : l'étudiant explique PUIS assess_understanding
    explanation = (
        "return sort de la fonction avec la valeur alors que "
        "print affiche seulement sans transmettre : le résultat "
        "ne serait pas récupérable par le code appelant."
    )
    invoke(
        agent,
        model,
        "T44",
        "u1",
        explanation,
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "assess_understanding",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "response": explanation,
                        },
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(
                content="Excellente explication — tu as vraiment "
                "compris la différence. Activité terminée !"
            ),
        ],
    )
    # FIX 44b (suite) : relire l'activité APRÈS le tour 3 —
    # assess_understanding produit l'observation de compréhension
    # (et l'activité légitimement terminée si understood). Au
    # tour 2, understanding n'existe pas encore : c'est
    # assess_understanding (tour 3) qui la produit.
    act = get_activity(agent, "T44")
    check(
        "44d: understanding APRES assess_understanding (tour 3)",
        isinstance(act.get("understanding"), dict)
        and act["understanding"].get("status") in (
            "understood",
            "partial",
            "unclear",
            "not_understood",
        ),
        act.get("understanding"),
    )


# ==================================================================
# §45/§46 — BLOCAGE → HINT PROGRESSIF
# ==================================================================


def test_hint_progressive():
    print("\n--- §45/§46 hint progressif ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T46",
        "u1",
        "Un exercice sur return.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )

    # L'étudiant bloque → level 0
    invoke(
        agent,
        model,
        "T46",
        "u1",
        "Je suis bloqué.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "give_hint",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "level": 0,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="Voici un indice..."),
        ],
    )
    act = get_activity(agent, "T46")
    check(
        "45a: hint_level=0 après premier blocage",
        act.get("hint_level") == 0,
        act.get("hint_level"),
    )
    check(
        "45b: status → waiting_for_retry",
        act.get("status") == "waiting_for_retry",
        act.get("status"),
    )

    # L'étudiant tente quelque chose, rebloque → level 1
    invoke(
        agent,
        model,
        "T46",
        "u1",
        "Je ne sais toujours pas.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "give_hint",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "level": 1,
                        },
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(content="Indice 2..."),
        ],
    )
    act = get_activity(agent, "T46")
    check(
        "46a: hint_level progresse à 1",
        act.get("hint_level") == 1,
        act.get("hint_level"),
    )

    # L'étudiant demande level=2 après avoir vu le 1 → 2
    invoke(
        agent,
        model,
        "T46",
        "u1",
        "Toujours bloqué.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "give_hint",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "level": 2,
                        },
                        "id": "c4",
                    }
                ],
            ),
            AIMessage(content="Indice 3..."),
        ],
    )
    act = get_activity(agent, "T46")
    check(
        "46b: hint_level max=2 (progression atteint 2)",
        act.get("hint_level") == 2,
        act.get("hint_level"),
    )

    # Saut direct impossible : nouveau thread, demande level=2 d'emblée
    invoke(
        agent,
        model,
        "T46b",
        "u1",
        "Exercice sur return.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c5",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )
    invoke(
        agent,
        model,
        "T46b",
        "u1",
        "Bloqué, donne-moi la solution directe.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "give_hint",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "level": 2,
                        },
                        "id": "c6",
                    }
                ],
            ),
            AIMessage(content="Indice borné..."),
        ],
    )
    act = get_activity(agent, "T46b")
    check(
        "46c: saut direct 0→2 INTERDIT (borné à 1)",
        act.get("hint_level") == 1,
        act.get("hint_level"),
    )


# ==================================================================
# §47 — QUIZ CONVERSATIONNEL
# ==================================================================


def test_quiz_one_question_at_a_time():
    print("\n--- §47 quiz conversationnel ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "T47",
        "u1",
        "Fais-moi un quiz sur les fonctions.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_quiz",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "num_questions": 3,
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question 1/3 posée. À toi."),
        ],
    )
    act = get_activity(agent, "T47")
    check(
        "47a: quiz actif type=quiz",
        act.get("activity_type") == "quiz",
        act.get("activity_type"),
    )
    check(
        "47b: total_questions=3, current_index=0",
        act.get("total_questions") == 3
        and act.get("current_index") == 0,
        (act.get("total_questions"), act.get("current_index")),
    )
    questions_in_state = act.get("questions") or []
    check(
        "47c: questions stockées dans le state (pas dans le chat)",
        len(questions_in_state) == 3,
        len(questions_in_state),
    )
    # La question 1 est la seule posée : les suivantes ne sont PAS
    # dans les messages visibles de l'étudiant
    snap = agent.get_state(
        {"configurable": {"thread_id": "T47", "user_id": "u1"}}
    )
    chat_msgs = [
        m.content for m in snap.values["messages"]
        if m.type in ("human", "ai") and m.content
    ]
    q2_text = questions_in_state[1]["question"] if len(
        questions_in_state
    ) > 1 else ""
    check(
        "47d: la question 2 n'est PAS encore visible dans le chat",
        not any(q2_text[:40] in c for c in chat_msgs),
        "Q2 visible prématurément",
    )

    # Réponse 1 → evaluate → next question
    answer1 = (
        "return renvoie une valeur au code appelant et termine "
        "immédiatement l'exécution de la fonction python."
    )
    invoke(
        agent,
        model,
        "T47",
        "u1",
        answer1,
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "answer": answer1,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_quiz_next",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "next_question": True,
                        },
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(content="Question 2/3 posée."),
        ],
    )
    act = get_activity(agent, "T47")
    check(
        "47e: après réponse 1, current_index=1",
        act.get("current_index") == 1,
        act.get("current_index"),
    )
    check(
        "47f: le quiz attend une nouvelle réponse",
        act.get("awaiting_answer") is True
        and act.get("status") == "waiting_for_answer",
        (act.get("status"), act.get("awaiting_answer")),
    )

    # Suite : question 2 puis 3 puis terminé
    invoke(
        agent,
        model,
        "T47",
        "u1",
        "une réponse moyenne sur les parametres",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "python",
                            "topic": "parametres",
                            "answer": "parametre variable def",
                        },
                        "id": "c4",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_quiz_next",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "next_question": True,
                        },
                        "id": "c5",
                    }
                ],
            ),
            AIMessage(content="Question 3/3 posée."),
        ],
    )
    invoke(
        agent,
        model,
        "T47",
        "u1",
        "la portee c est la visibilite des variables locale globale",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "evaluate_answer",
                        "args": {
                            "subject": "python",
                            "topic": "portee",
                            "answer": "portee visibilite variables "
                            "locale globale legb",
                        },
                        "id": "c6",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_quiz_next",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                            "next_question": True,
                        },
                        "id": "c7",
                    }
                ],
            ),
            AIMessage(content="Quiz terminé !"),
        ],
    )
    act = get_activity(agent, "T47")
    check(
        "47g: quiz TERMINÉ après 3 questions",
        act.get("status") == "completed",
        act.get("status"),
    )


# ==================================================================
# §48 — CODE : exécutions multiples (sandbox)
# ==================================================================


def test_code_practice_loop():
    print("\n--- §48 pratique du code (multi-tentatives) ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)

    # Tentative 1 : code fautif (print au lieu de return)
    code1 = (
        "def somme(a, b):\n"
        "    print(a + b)\n"
        "\n"
        "somme(2, 3)\n"
    )
    invoke(
        agent,
        model,
        "T48",
        "u1",
        "Voici mon code :\n```\n" + code1 + "\n```",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute_code",
                        "args": {
                            "language": "python",
                            "code": code1,
                            "subject": "python",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Ton code produit la somme..."),
        ],
    )
    snap = agent.get_state(
        {"configurable": {"thread_id": "T48", "user_id": "u1"}}
    )
    vals = snap.values
    check(
        "48a: code_runs=1 après première exécution",
        vals.get("code_runs") == 1,
        vals.get("code_runs"),
    )
    check(
        "48b: activity_log a des événements CODE_*",
        any(
            str(e.get("event", "")).startswith("CODE_")
            for e in vals.get("activity_log", [])
        ),
    )

    # Tentative 2 : code corrigé
    code2 = (
        "def somme(a, b):\n"
        "    return a + b\n"
        "\n"
        "print(somme(2, 3))\n"
    )
    invoke(
        agent,
        model,
        "T48",
        "u1",
        "J'ai corrigé :\n```\n" + code2 + "\n```",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute_code",
                        "args": {
                            "language": "python",
                            "code": code2,
                            "subject": "python",
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="Parfait, cette fois..."),
        ],
    )
    snap = agent.get_state(
        {"configurable": {"thread_id": "T48", "user_id": "u1"}}
    )
    check(
        "48c: code_runs=2 — multi-tentatives OK",
        snap.values.get("code_runs") == 2,
        snap.values.get("code_runs"),
    )

    # run_tests : tests réels (2 passent, 1 rate volontairement)
    code3 = "def somme(a, b):\n    return a + b\n"
    invoke(
        agent,
        model,
        "T48",
        "u1",
        "Teste mon code.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_tests",
                        "args": {
                            "language": "python",
                            "code": code3,
                            "subject": "python",
                            "tests": [
                                {
                                    "name": "2 + 3",
                                    "call": "somme(2, 3)",
                                    "expected": 5,
                                },
                                {
                                    "name": "-2 + 5",
                                    "call": "somme(-2, 5)",
                                    "expected": 3,
                                },
                                {
                                    "name": "0 + 0",
                                    "call": "somme(0, 0)",
                                    "expected": 1,
                                },
                            ],
                        },
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(content="2 tests passent, 1 échoue..."),
        ],
    )
    snap = agent.get_state(
        {"configurable": {"thread_id": "T48", "user_id": "u1"}}
    )
    tool_msgs = [
        m.content for m in snap.values["messages"]
        if m.type == "tool"
    ]
    check(
        "48d: run_tests rapporte 2/3 réussis",
        any("2/3" in c for c in tool_msgs),
        [c[:80] for c in tool_msgs if "TESTS" in c],
    )

    # analyze_code sur le code fautif
    invoke(
        agent,
        model,
        "T48",
        "u1",
        "Analyse mon premier code.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "analyze_code",
                        "args": {
                            "language": "python",
                            "code": code1,
                            "subject": "python",
                        },
                        "id": "c4",
                    }
                ],
            ),
            AIMessage(content="Observations d'analyse..."),
        ],
    )
    snap = agent.get_state(
        {"configurable": {"thread_id": "T48", "user_id": "u1"}}
    )
    tool_msgs = [
        m.content for m in snap.values["messages"] if m.type == "tool"
    ]
    check(
        "48e: analyze_code détecte l'observation print/return",
        any("print" in c.lower() and "ANALYSE" in c for c in tool_msgs),
    )


# ==================================================================
# §49 — RESTART : persistance de l'activité (nouvelle instance)
# ==================================================================


def test_restart_persistence():
    print("\n--- §49 restart : persistance checkpointer ---")
    import sqlite3

    # DB de checkpoint SOUS le workspace (backend/database) — la
    # sandbox de test interdit le TMP système.
    from app.config import DATABASE_DIR

    db_path = DATABASE_DIR / "test_v52_restart.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    from langgraph.checkpoint.sqlite import SqliteSaver

    cp = SqliteSaver(conn)

    agent1, model1 = make_agent([], cp)
    invoke(
        agent1,
        model1,
        "T49",
        "u1",
        "Exercice sur return.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )
    act_before = get_activity(agent1, "T49")
    check(
        "49a: activité créée avant restart",
        act_before.get("status") == "waiting_for_answer",
    )

    # "Redémarrage" : NOUVELLE instance d'agent, MÊME checkpointer
    agent2, model2 = make_agent([], cp)
    act_after = get_activity(agent2, "T49")
    check(
        "49b: activité RÉCUPÉRÉE après restart (même checkpointer)",
        act_after.get("status") == "waiting_for_answer"
        and act_after.get("activity_id") == act_before.get(
            "activity_id"
        ),
        act_after,
    )

    conn.close()
    if db_path.exists():
        db_path.unlink()


# ==================================================================
# §50 — CROSS-THREAD : pas de transfert d'activité
# ==================================================================


def test_cross_thread():
    print("\n--- §50 cross-thread ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)
    invoke(
        agent,
        model,
        "TA",
        "u1",
        "Exercice sur return.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            "topic": "return",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )

    act_a = get_activity(agent, "TA")
    act_b = get_activity(agent, "TB")
    check(
        "50a: thread B ne voit PAS l'activité du thread A",
        not act_b,
        act_b,
    )
    invoke(
        agent,
        model,
        "TB",
        "u1",
        "Un exercice sur la boucle while.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "python",
                            # FIX 50c (mission intégration §9) : "loops"
                            # n'est pas une section knowledge réelle
                            # (sections de loops.md : for, while, range,
                            # break-continue, comprehensions). On
                            # utilise "while" qui existe réellement.
                            "topic": "while",
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="Question posée."),
        ],
    )
    act_a2 = get_activity(agent, "TA")
    act_b2 = get_activity(agent, "TB")
    check(
        "50b: thread A garde SON activité (return) intacte",
        act_a2.get("topic") == "return"
        and act_a2.get("status") == "waiting_for_answer",
        act_a2,
    )
    check(
        "50c: thread B a SA propre activité (while)",
        act_b2.get("topic") == "while",
        act_b2,
    )
    check(
        "50d: les deux activités ont des ids différents",
        act_a2.get("activity_id") != act_b2.get("activity_id"),
    )


# ==================================================================
# §51 — CROSS-USER : isolation API
# ==================================================================


def test_cross_user():
    print("\n--- §51 cross-user (API) ---")
    from fastapi.testclient import TestClient
    from app.main import app
    import uuid as _uuid

    client = TestClient(app)

    # Setup : 2 users, 1 thread chacun
    # Mission Identité : les users sont provisionnés en mode dev
    # ( dev_token = session simulée ) — chaque requête porte le
    # token de SON user.
    _u1 = client.post(
        "/api/users", json={"name": "V52-A-" + _uuid.uuid4().hex[:6]}
    ).json()
    _u2 = client.post(
        "/api/users", json={"name": "V52-B-" + _uuid.uuid4().hex[:6]}
    ).json()
    u1 = _u1["user_id"]
    u2 = _u2["user_id"]
    tok1 = {"Authorization": f"Bearer {_u1.get('dev_token', 'dev:' + u1)}"}
    tok2 = {"Authorization": f"Bearer {_u2.get('dev_token', 'dev:' + u2)}"}
    t1 = client.post(
        f"/api/users/{u1}/threads", json={"name": "act-a"},
        headers=tok1,
    ).json()["thread_id"]
    t2 = client.post(
        f"/api/users/{u2}/threads", json={"name": "act-b"},
        headers=tok2,
    ).json()["thread_id"]

    # u2 tente de lire l'activité du thread de u1 → 403
    resp = client.get(
        f"/api/threads/{t1}/activity", params={"user_id": u2},
        headers=tok2,
    )
    check(
        "51a: user B NE PEUT PAS lire l'activité du thread de user A (403)",
        resp.status_code == 403,
        resp.status_code,
    )

    # u1 lit sa propre activité → 200
    resp = client.get(
        f"/api/threads/{t1}/activity", params={"user_id": u1},
        headers=tok1,
    )
    check(
        "51b: user A lit sa propre activité (200)",
        resp.status_code == 200,
        resp.status_code,
    )

    # run-code cross-user → 403
    resp = client.post(
        f"/api/threads/{t1}/run-code",
        json={"user_id": u2, "code": "print(1)"},
        headers=tok2,
    )
    check(
        "51c: user B NE PEUT PAS exécuter du code dans le thread de A (403)",
        resp.status_code == 403,
        resp.status_code,
    )

    # run-code légitime → 200 avec résultat réel
    resp = client.post(
        f"/api/threads/{t1}/run-code",
        json={"user_id": u1, "code": "print(2 + 3)"},
        headers=tok1,
    )
    body = resp.json()
    check(
        "51d: run-code légitime exécute réellement (stdout=5)",
        resp.status_code == 200
        and body.get("stdout", "").strip() == "5"
        and body.get("exit_code") == 0,
        body,
    )

    # code dangereux rejeté par la sécurité
    resp = client.post(
        f"/api/threads/{t1}/run-code",
        json={
            "user_id": u1,
            "code": "import requests\nrequests.get('http://x')",
        },
        headers=tok1,
    )
    check(
        "51e: code réseau REJETÉ par la sécurité (400)",
        resp.status_code == 400,
        resp.status_code,
    )


# ==================================================================
# SANDBOX — sécurité de l'exécution
# ==================================================================


def test_sandbox_security():
    print("\n--- sandbox sécurité ---")

    # Exécution normale réelle
    r = run_python_isolated("print(40 + 2)")
    check(
        "s1: exécution réelle stdout=42 exit=0",
        r["status"] == "success"
        and r["stdout"].strip() == "42"
        and r["exit_code"] == 0,
        r,
    )

    # Erreur réelle
    r = run_python_isolated("undefined_variable")
    check(
        "s2: NameError remonté dans stderr",
        r["status"] == "error"
        and "NameError" in r["stderr"],
        r["stderr"][:100],
    )

    # Timeout
    r = run_python_isolated("while True:\n    pass\n", timeout_s=3)
    check(
        "s3: boucle infinie tuée par timeout",
        r["status"] == "timeout",
        r,
    )

    # Scan statique : réseau bloqué
    v = static_security_scan(
        "import requests\nrequests.get('http://evil.com')"
    )
    check(
        "s4: scan bloque import requests",
        len(v) >= 1,
        v,
    )
    v = static_security_scan("import socket")
    check("s5: scan bloque import socket", len(v) >= 1)

    # Scan statique : fichiers bloqués
    v = static_security_scan(
        "with open('.env') as f:\n    print(f.read())"
    )
    check("s6: scan bloque open()", len(v) >= 1)

    # Scan statique : eval/exec bloqués
    v = static_security_scan("eval('1+1')")
    check("s7: scan bloque eval", len(v) >= 1)

    # Scan statique : code propre accepté
    v = static_security_scan(
        "def somme(a, b):\n    return a + b\nprint(somme(2, 3))\n"
    )
    check("s8: code propre passe le scan", len(v) == 0, v)

    # Environnement purgé : pas de secrets visibles (os bloqué par
    # le scan des tools, mais l'appel direct doit aussi être sûr)
    r = run_python_isolated(
        "import os\nprint(os.environ.get('OLLAMA_API_KEY', 'ABSENT'))"
    )
    check(
        "s9: secrets du serveur ABSENTS de l'env sandbox",
        "ABSENT" in r["stdout"],
        r["stdout"][:100],
    )

    # Garde disponibilité : biology n'autorise PAS execute_code
    from app.tools.coding import _code_tools_enabled

    check(
        "s10: python autorise execute_code (config)",
        _code_tools_enabled("python"),
    )
    check(
        "s11: biology N'AUTORISE PAS execute_code (config)",
        not _code_tools_enabled("biology"),
    )
    check(
        "s12: subject inconnu → non autorisé",
        not _code_tools_enabled("nonexistent-subject"),
    )


# ==================================================================
# §52 — NON-MODIFICATION de l'agent 1 (Learning Profile)
# ==================================================================


def test_agent1_intact():
    print("\n--- §52 tools Learning Profile de l'agent 1 intacts ---")
    from app.tools import all_tools

    names = {t.name for t in all_tools}
    for expected in (
        "get_learning_profile",
        "get_learning_topic",
        "record_learning_observation",
        "update_learning_goal",
    ):
        check(
            f"52: tool agent 1 '{expected}' toujours enregistré",
            expected in names,
        )
    check(
        "52: core prompt règle 15 (record_learning_observation) préservée",
        "record_learning_observation" in __import__(
            "app.services.agent.prompts", fromlist=["CORE_PROMPT"]
        ).CORE_PROMPT,
    )


# ==================================================================
# TYPE INDEPENDENCE (§38) — tools génériques toutes matières
# ==================================================================


def test_subject_independence():
    print("\n--- §38 indépendance matières ---")
    cp = MemorySaver()
    agent, model = make_agent([], cp)

    # Biologie : exercice fonctionnel aussi
    invoke(
        agent,
        model,
        "T38",
        "u1",
        "Donne-moi un exercice de biologie sur la membrane.",
        scripted=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_exercise",
                        "args": {
                            "subject": "biology",
                            "topic": "membrane",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Question de bio posée."),
        ],
    )
    act = get_activity(agent, "T38")
    check(
        "38a: exercice biology OK (tools génériques)",
        act.get("subject") == "biology"
        and act.get("status") == "waiting_for_answer",
        act,
    )
    check(
        "38b: biology → expected_response_type ≠ code",
        act.get("expected_response_type") != "code",
        act.get("expected_response_type"),
    )


if __name__ == "__main__":
    test_exercise_stays_waiting()
    test_answer_then_understanding()
    test_hint_progressive()
    test_quiz_one_question_at_a_time()
    test_code_practice_loop()
    test_restart_persistence()
    test_cross_thread()
    test_cross_user()
    test_sandbox_security()
    test_agent1_intact()
    test_subject_independence()

    print(f"\n{'=' * 50}")
    print(f"RÉSULTATS : {PASS} PASS / {FAIL} FAIL")
    if FAIL:
        sys.exit(1)
    print("TOUS LES TESTS V5.2 PASSENT")
