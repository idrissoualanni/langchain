"""Une table ne peut avoir qu'un seul proprietaire de DDL.

POURQUOI CE TEST EXISTE

`video_segments` et `videos` etaient definies dans DEUX modules :

  - app/infrastructure/database/connections.py  (version perimee)
  - app/infrastructure/database/schema.py       (version qui fait foi)

Or `connections.init_db()` s'execute AVANT `schema.init_schema()`. Les
deux DDL utilisent `CREATE TABLE IF NOT EXISTS`, donc sur une base
neuve le premier arrive creat sa version et le second ne faisait plus
rien. Le demarrage de l'application echouait alors sur la creation de
l'index HNSW `embedding`, colonne absente de la version perimee.

Le cas est reste invisible en production : la table existait deja dans
la bonne forme, les deux `IF NOT EXISTS` etaient donc inoperants et le
conflit ne pouvait plus se reproduire. Il aurait suffi d'un deploiement
sur une base neuve - nouvelle region, restauration, nouvel
environnement - pour faire tomber l'application.

Ce test echoue des qu'une table est reintroduite dans deux modules.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CONNECTIONS = BACKEND / "app" / "infrastructure" / "database" / "connections.py"
SCHEMA = BACKEND / "app" / "infrastructure" / "database" / "schema.py"
PERSIST = BACKEND / "app" / "graph" / "subgraphs" / "video" / "persist.py"

_CREATE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\n\s*\)",
    re.S | re.I,
)


def _defined(path: Path) -> dict:
    """Tables CREATE TABLE IF NOT EXISTS du fichier, avec leurs colonnes."""
    text = path.read_text(encoding="utf-8")
    out: dict = {}
    for name, body in _CREATE.findall(text):
        cols = []
        for raw in body.split(",\n"):
            line = raw.strip()
            if not line or line.startswith(("--", "#")):
                continue
            cols.append(line.split()[0].strip('"'))
        out[name] = cols
    return out


def _inserted_columns(path: Path, table: str) -> list:
    """Colonnes listees dans les INSERT INTO <table> du fichier."""
    text = path.read_text(encoding="utf-8")
    out: list = []
    pattern = re.compile(
        r"INSERT\s+INTO\s+" + table + r"\s*\((.*?)\)\s*VALUES", re.S | re.I
    )
    for body in pattern.findall(text):
        cleaned = body.replace("\n", " ")
        out.extend(c.strip().strip('"') for c in cleaned.split(","))
    return out


@pytest.fixture(scope="module")
def connections() -> dict:
    return _defined(CONNECTIONS)


@pytest.fixture(scope="module")
def schema() -> dict:
    return _defined(SCHEMA)


def test_les_deux_modules_se_lisent_correctement(connections, schema):
    """Garde-fou : un parseur muet qui ne trouve rien ne prouve rien."""
    assert "users" in connections, "connections.py ne definit plus users ?"
    assert "threads" in connections, "connections.py ne definit plus threads ?"
    assert len(schema) >= 10, f"schema.py ne definit plus que {len(schema)} tables"


def test_aucune_table_definit_par_deux_modules(connections, schema):
    """L'invariant central - celui qui a ete viole.

    Deux proprietaires pour une meme table, c'est une definition qui
    gagne selon l'ordre d'execution. Sur une base neuve, le perdant est
    silencieusement ignore (IF NOT EXISTS) et l'application ecrit ensuite
    contre des colonnes qui n'existent pas.
    """
    doublons = sorted(set(connections) & set(schema))
    assert not doublons, (
        "Tables definies dans connections.py ET schema.py : "
        f"{doublons}. Chaque table doit avoir UN seul proprietaire de DDL."
    )


@pytest.mark.parametrize("table", ["videos", "video_segments"])
def test_les_tables_video_appartiennent_a_schema_py(connections, schema, table):
    """Regression ciblee : ces deux tables sont celles de schema.py."""
    assert table in schema, f"{table} absente de schema.py"
    assert table not in connections, (
        f"{table} a ete reintroduite dans connections.py : sur une base "
        "neuve ce DDL precede schema.py et la table prendrait la mauvaise "
        "forme."
    )


@pytest.mark.parametrize("table", ["videos", "video_segments"])
def test_les_colonnes_ecrites_existent_dans_le_ddl(schema, table):
    """Le code ecrit des colonnes que le DDL doit connaitre.

    C'est le garde-fou qui aurait attrape le bug par l'autre bout :
    persist.py insere media_object_id, que seule la version de schema.py
    declare. Si le DDL gagnant etait l'autre, l'ecriture aurait echoue
    avec column does not exist.
    """
    assert table in schema, f"{table} absente de schema.py"
    ecrites = _inserted_columns(PERSIST, table)
    assert ecrites, f"aucun INSERT INTO {table} trouve dans persist.py"
    manquantes = sorted(set(ecrites) - set(schema[table]))
    assert not manquantes, (
        f"{table} : le code insere des colonnes absentes du DDL de "
        f"schema.py : {manquantes}"
    )
