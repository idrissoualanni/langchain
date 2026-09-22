# Tests V10 — INTÉGRATION Context Builder + Documents utilisateur (RAG).
#
# Établit que :
#   A. Build sans documents → BuiltContext.user_documents = status
#      unavailable, section ABSENTE du prompt (pas d'erreur, §15).
#   B. Build avec documents indexés + question pertinente → status
#      found, texte injecté dans le prompt, stats remontées.
#   C. Build avec documents mais question sans rapport → status
#      insufficient/unavailable, pas de section (aucun invent biaisé).
#   D. Isolation user_id : les docs de l'utilisateur A ne fuient
#      JAMAIS dans le contexte de B.
import sys
import tempfile
import warnings
from pathlib import Path
from unittest import mock

sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


from app.context.builder import build_context  # noqa: E402
from app.context.prompt_builder import build_system_prompt  # noqa: E402
from app.schemas.context import BuiltContext  # noqa: E402
from app.context.semantic.provider import (  # noqa: E402
    LocalHashEmbeddingProvider,
    set_embedding_provider,
)
from app.rag.chunker import chunk_text  # noqa: E402
from app.rag.retriever import DocumentRetriever  # noqa: E402
from app.rag.vector_store import (  # noqa: E402
    RagStore,
    reset_rag_store,
)

# Déterministe et instantané (pas d'Ollama dans les tests).
set_embedding_provider(LocalHashEmbeddingProvider())

TMP = tempfile.mkdtemp(prefix="v10_ctx_")
STORE_PATH = Path(TMP) / "user_documents.db"


def fresh_store():
    reset_rag_store()
    return RagStore(path=STORE_PATH)


def build(user_id, query):
    with mock.patch(
        "app.rag.retriever.DocumentRetriever",
        lambda: DocumentRetriever(store=fresh_store()),
    ):
        b = build_context(
            user_id=user_id,
            thread_id="t-v10-ctx",
            query=query,
        )
    return b


CORE = "Tu es un tuteur pédagogique. Réponds en français."
NOTE_DOC = (
    "## DOCUMENTS PERSONNELS DE L'ÉTUDIANT"
    "|".join(""),
)


def prompt_for(b: BuiltContext) -> str:
    return build_system_prompt(CORE, b, user_id=b.user.text or "u")


print("--- A. Pas de documents → section absente, pas d'erreur ---")
b = build("u-nodoc", "qu'est-ce qu'une boucle for en python ?")
check(
    "A1. user_documents présent dans BuiltContext (extra=forbid OK)",
    isinstance(b.user_documents, type(BuiltContext().user_documents)),
)
check(
    "A2. status=unavailable si rien d'indexé (pas de fake success)",
    b.user_documents.status == "unavailable",
    str(b.user_documents.status),
)
check(
    "A3. text vide (aucun invent biaisé)", b.user_documents.text == ""
)
p = prompt_for(b)
check(
    "A4. prompt SANS section documents (fail-safe simple)",
    "DOCUMENTS PERSONNELS" not in p,
)


print("--- B. Documents pertinents → section injectée ---")
store = fresh_store()
doc_text = (
    "## OpenCV Python\n"
    "cv2.imread charge une image depuis un fichier. "
    "cv2.cvtColor convertit l'espace de couleurs. "
    "cv2.threshold applique un seuillage binaire."
)
record = store.add_document(
    user_id="u-doc",
    filename="opencv-notes.md",
    content_type="text/plain",
    text=doc_text,
    chunks=chunk_text(doc_text),
)
_ = record  # doc_id inutilisé directement

with mock.patch(
    "app.rag.retriever.DocumentRetriever",
    lambda: DocumentRetriever(store=store),
):
    b = build_context(
        user_id="u-doc",
        thread_id="t-v10-ctx",
        query="comment charger une image avec opencv ?",
    )
check(
    "B1. status=found avec docs pertinents",
    b.user_documents.status == "found",
    str(b.user_documents.status),
)
check(
    "B2. count > 0", b.user_documents.count > 0,
    str(b.user_documents.count),
)
check(
    "B3. texte non vide", bool(b.user_documents.text)
)
check(
    "B4a. stats.user_documents_count remonté",
    b.stats.user_documents_count == b.user_documents.count,
    str(b.stats.user_documents_count),
)
check(
    "B4b. prompt contient la section documents",
    "DOCUMENTS PERSONNELS" in prompt_for(b),
)
check(
    "B4c. le nom du fichier source apparaît",
    "opencv-notes.md" in prompt_for(b),
)
check(
    "B4d. le chunk pertinent apparaît",
    "cv2.imread" in prompt_for(b),
)


print("--- C. Docs existants mais question hors sujet → rien ---")
with mock.patch(
    "app.rag.retriever.DocumentRetriever",
    lambda: DocumentRetriever(store=store),
):
    b = build_context(
        user_id="u-doc",
        thread_id="t-v10-ctx",
        query="quel sport préfères-tu pour le week-end ?",
    )
check(
    "C1. pas de section documents hors sujet (aucun bias)",
    b.user_documents.count == 0
    and b.user_documents.text == "",
    f"status={b.user_documents.status} count={b.user_documents.count}",
)
check(
    "C2. prompt sans section hors sujet",
    "DOCUMENTS PERSONNELS" not in prompt_for(b),
)


print("--- D. Isolation user_id stricte (pas de fuite cross-user) ---")
with mock.patch(
    "app.rag.retriever.DocumentRetriever",
    lambda: DocumentRetriever(store=store),
):
    b = build_context(
        user_id="u-INTRUS",
        thread_id="t-v10-ctx",
        query="comment charger une image avec opencv ?",
    )
check(
    "D1. docs de u-doc invisibles pour u-INTRUS",
    b.user_documents.status == "unavailable"
    and b.user_documents.count == 0,
    f"status={b.user_documents.status} count={b.user_documents.count}",
)


print("--- E. Défensif : RagStore en échec → contexte intact (§15) ---")

def boom_search(**kwargs):
    raise RuntimeError("base corrompue")


with mock.patch(
    "app.rag.retriever.DocumentRetriever",
    lambda: mock.Mock(
        search_documents=mock.Mock(side_effect=boom_search),
    ),
):
    b = build_context(
        user_id="u-doc",
        thread_id="t-v10-ctx",
        query="comment charger une image ?",
    )
check(
    "E1. exception RagStore n'abat pas le build (fail-safe)",
    b.user_documents.count == 0
    and b.user_documents.text == "",
    f"status={b.user_documents.status}",
)
check(
    "E2. le build retourne quand même un contexte",
    isinstance(b, BuiltContext),
)


reset_rag_store()
set_embedding_provider(LocalHashEmbeddingProvider())

failed = [r for r in results if not r[1]]
print(f"\n{'='*60}\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:")
    for label, _ in failed:
        print(f"  - {label}")
    sys.exit(1)
print("ALL PASSED")