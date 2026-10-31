"""Configuration pytest — rend `app` importable depuis la racine backend.

Les suites existantes s'exécutent depuis `backend/` ( sys.path.insert ).
Ce conftest permet de lancer `pytest` depuis n'importe où en ajoutant le
dossier backend au sys.path.

Il retire aussi de la collecte les fichiers `test_*.py` qui ne sont PAS des
modules pytest mais des SCRIPTS autonomes. Ces scripts s'exécutent dès
l'import (prints, appels `check(...)`, requêtes HTTP, et `sys.exit(...)` en
fin de module) et provoquent :

  - un ``INTERNALERROR`` pytest ( ``SystemExit`` ) quand le script atteint
    son ``sys.exit(...)`` pendant la collecte (ex. ``test_phase1_graph_contracts``) ;
  - des erreurs de collecte ``URLError`` quand le script tape un serveur
    absent (ex. ``test_auth_security``).

PIÈGE DE DÉTECTION (à conserver en tête) : un script garde son
``sys.exit(1)`` derrière ``if FAIL: ...`` au niveau module. Ce n'est donc PAS
une simple expression ``ast.Expr`` de premier niveau, et chercher
``node.func.id == "sys.exit"`` ne trouve jamais rien — ``sys.exit`` se parse
en ``ast.Attribute``. La règle retenue ici est plus large et plus sûre : est
exclu tout fichier ``test_*.py`` ne définissant AUCUN élément de test pytest
( fonction ``test_*`` ou classe ``Test*`` ). Un tel fichier ne peut rien
apporter à la collecte, mais son import peut avoir des effets de bord : il
n'a rien à y faire.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# Observabilité coupée AVANT tout import `app.*` : `load_dotenv` n'écrase
# pas une variable déjà posée, donc le `.env` local ne peut plus réactiver
# l'export. Sans ça, chaque `pytest` envoyait les traces de test (prompts,
# faits utilisateurs fictifs) à api.smith.langchain.com avec la vraie clé.
for _var in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_ENABLED", "LANGFUSE_ENABLED"):
    os.environ[_var] = "false"

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_TESTS_DIR = Path(__file__).resolve().parent


def _database_reachable() -> bool:
    """La base de DATABASE_URL accepte-t-elle une connexion TCP ?

    Simple ouverture de socket (2 s) : suffisant pour distinguer « Neon
    configuré » de la valeur factice de la CI (localhost:5432 sans
    serveur), sans ouvrir de session SQL.
    """
    from app.config import DATABASE_URL

    parts = urlsplit(DATABASE_URL or "")
    if not parts.hostname:
        return False
    try:
        with socket.create_connection((parts.hostname, parts.port or 5432), timeout=2):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    """`@pytest.mark.integration` : sauté si la base n'est pas joignable."""
    if not any(item.get_closest_marker("integration") for item in items):
        return
    if _database_reachable():
        return
    skip = pytest.mark.skip(reason="base de données injoignable (test d'intégration)")
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _deterministic_embeddings():
    """Provider d'embedding local et déterministe pour chaque test.

    Le provider réel (Ollama Cloud / Cloudflare) dépend du réseau et d'une
    clé : un test qui l'appelait échouait dès que le service était
    indisponible (« embedding provider indisponible »). Les tests qui
    veulent un provider précis l'installent eux-mêmes via
    `set_embedding_provider` — celui-ci est restauré au teardown.
    """
    from app.services.context.semantic.provider import (
        LocalHashEmbeddingProvider,
        set_embedding_provider,
    )

    set_embedding_provider(LocalHashEmbeddingProvider())
    yield
    set_embedding_provider(None)


def _has_pytest_tests(tree: ast.Module) -> bool:
    """True si le module définit un élément collectable par pytest."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                return True
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("Test"):
                return True
    return False


def _module_level_exit_lines(tree: ast.Module) -> list[int]:
    """Lignes des appels ``*.exit()`` exécutés au chargement du module.

    On parcourt le corps de module et on descend dans les structures de
    contrôle de niveau module ( ``if``/``for``/``while``/``with``/``try`` ),
    en IGNORANT le corps des fonctions/classes et le garde
    ``if __name__ == "__main__":`` (non exécuté à l'import).
    """

    def is_main_guard(node: ast.If) -> bool:
        test = node.test
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        )

    lines: list[int] = []

    def walk(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.If) and is_main_guard(stmt):
                continue
            for sub in ast.walk(stmt):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "exit"
                ):
                    lines.append(sub.lineno)
            # descendre dans les blocs de contrôle de module
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(stmt, field, None)
                if nested:
                    walk(nested)
            for handler in getattr(stmt, "handlers", []) or []:
                walk(handler.body)

    walk(tree.body)
    return lines


def _find_script_modules() -> list[str]:
    """Scripts `test_*.py` (aucun test) à retirer de la collecte.

    Retourne des chemins RELATIFS au dossier de ce conftest.
    """
    ignored: list[str] = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8"), filename=str(path)
            )
        except (OSError, SyntaxError):
            # Ne pas masquer un problème de syntaxe : pytest le rapportera.
            continue
        if not _has_pytest_tests(tree):
            ignored.append(path.name)
    return ignored


#: Fichiers exclus de la collecte car ce ne sont pas des modules de test.
#: La liste est calculée par AST ( cf. docstring ) : tout script `test_*.py`
#: sans fonction/classe de test y figure automatiquement.
collect_ignore = _find_script_modules()
