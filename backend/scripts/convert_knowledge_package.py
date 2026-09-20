# Mission Intégration Knowledge Base — convertisseur YAML (étape 2/6).
#
# Le package fournit des YAML au format "topics[] riches" :
#   topics:
#     - id: algebre
#       name: Algèbre
#       description: ...
#       aliases: [...]
#       semantic_terms: [...]   (LISTE au niveau topic)
#
# Le projet attend (SubjectConfig) :
#   topics: [algebre, ...]              # list[str]
#   semantic_terms:                       # dict {topic: [termes]}
#     algebre: [...]
#   aliases: [...]                        # matière
#   knowledge.sources: [subject/topic, ...]
#
# Ce script convertit staging → format projet, FUSIONNE les 4
# collisions avec l'existant (mathematics, biology, computer_networks
# ; informatique devient une matière distincte de python), et place
# les knowledge .md selon la convention knowledge/{source}.md.
#
# Stratégie de fusion (jamais de doublon de matière au registry) :
#   - mathematiques (zip)  → enrichit mathematics (existant)
#   - biologie (zip)       → enrichit biology (existant)
#   - reseaux_cybersecurite(zip) → enrichit computer_networks (existant)
#   - informatique (zip)   → NOUVELLE matière (algorithmique/
#     structures_donnees/programmation ≠ python/langage) MAIS sans
#     casser le routing python (topics distincts, aliases sans
#     "python").
#
# Usage : python scripts/convert_knowledge_package.py [--dry-run]
import shutil
import sys
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
STAGING = BACKEND / "app" / "knowledge_new"
DEFS = BACKEND / "app" / "subjects" / "definitions"
KNOW = BACKEND / "app" / "knowledge"

# Fusion : yaml zip (id) → yaml projet cible (id) à enrichir
MERGE_TARGETS = {
    "mathematiques": "mathematics",
    "biologie": "biology",
    "reseaux_cybersecurite": "computer_networks",
}

DRY = "--dry-run" in sys.argv


def norm(text: str) -> str:
    return " ".join((text or "").split())


def convert_topics_rich_to_flat(data: dict) -> dict:
    """Convertit topics[] riches → topics list[str] + semantic_terms dict."""
    topics_out: list[str] = []
    semantic: dict[str, list[str]] = {}
    topic_aliases_flat: list[str] = []
    for t in data.get("topics", []):
        if isinstance(t, str):
            # déjà format projet (topics: [str])
            topics_out.append(t)
            continue
        tid = t.get("id")
        if not tid:
            continue
        tid = str(tid)
        topics_out.append(tid)
        terms = list(t.get("semantic_terms", []) or [])
        # la description du topic enrichit la voie sémantique
        desc = norm(t.get("description", ""))
        if desc:
            terms.insert(0, desc)
        if terms:
            semantic[tid] = terms
        for a in t.get("aliases", []) or []:
            a = norm(str(a))
            if a and a not in topic_aliases_flat:
                topic_aliases_flat.append(a)
    data["topics"] = topics_out
    if semantic:
        # fusion avec semantic_terms existants (éventuels)
        base = dict(data.get("semantic_terms", {}) or {})
        for k, v in semantic.items():
            if k in base:
                merged = list(base[k]) + [t for t in v if t not in base[k]]
                base[k] = merged
            else:
                base[k] = v
        data["semantic_terms"] = base
    # topic aliases (zip) : utiles au lexical matière → on les
    # ajoute aux aliases de la matière (voie déclarative existante)
    if topic_aliases_flat:
        base_aliases = list(data.get("aliases", []) or [])
        for a in topic_aliases_flat:
            if a not in base_aliases:
                base_aliases.append(a)
        data["aliases"] = base_aliases
    return data


def knowledge_sources_for(subject_id: str, topics: list[str]) -> list[str]:
    """Sources knowledge au format projet : {subject}/{topic}.

    Les .md du package sont knowledge/{subject}/{topic}.md — la
    convention projet est knowledge/{source}.md avec
    source=subject/topic (ex: informatique/python/basics).
    """
    srcs = []
    for t in topics:
        p = STAGING / "backend" / "app" / "knowledge" / subject_id / f"{t}.md"
        if p.exists():
            srcs.append(f"{subject_id}/{t}")
    return srcs


def merge_yaml(existing_path: Path, new_data: dict) -> dict:
    """Fusionne new_data dans le YAML projet existant.

    Règles : topics/sources/aliases/semantic_terms UNION (sans
    doublon) ; les champs pédagogiques de l'existant (style,
    guidelines, capabilities, tools, model) SONT CONSERVÉS —
    le package n'apporte pas de meilleure valeur sur ces axes.
    """
    existing = yaml.safe_load(
        existing_path.read_text(encoding="utf-8")
    ) or {}
    # topics : union
    topics = list(existing.get("topics", []) or [])
    for t in new_data.get("topics", []):
        if t not in topics:
            topics.append(t)
    existing["topics"] = topics
    # knowledge.sources : union
    know = dict(existing.get("knowledge", {}) or {})
    srcs = list(know.get("sources", []) or [])
    for s in new_data.get("knowledge", {}).get("sources", []):
        if s not in srcs:
            srcs.append(s)
    know["sources"] = srcs
    existing["knowledge"] = know
    # aliases : union (existant d'abord)
    aliases = list(existing.get("aliases", []) or [])
    for a in new_data.get("aliases", []):
        if a not in aliases:
            aliases.append(a)
    existing["aliases"] = aliases
    # semantic_terms : union par topic
    sem = dict(existing.get("semantic_terms", {}) or {})
    for t, terms in (new_data.get("semantic_terms", {}) or {}).items():
        cur = list(sem.get(t, []) or [])
        for term in terms:
            if term not in cur:
                cur.append(term)
        sem[t] = cur
    existing["semantic_terms"] = sem
    return existing


def main() -> int:
    if not STAGING.exists():
        print("STAGING absent — zip non extrait")
        return 1
    staging_defs = (
        STAGING / "backend" / "app" / "subjects" / "definitions"
    )
    staging_know = STAGING / "backend" / "app" / "knowledge"

    created, merged, md_copied = [], [], 0
    for path in sorted(staging_defs.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sid = data.get("id")
        if not sid:
            print(f"[SKIP] {path.name} : pas d'id")
            continue
        data = convert_topics_rich_to_flat(data)
        srcs = knowledge_sources_for(sid, data.get("topics", []))
        if srcs:
            data["knowledge"] = {"sources": srcs}

        target_id = MERGE_TARGETS.get(sid, sid)
        target_path = DEFS / f"{target_id}.yaml"
        if target_id != sid and target_path.exists():
            out = merge_yaml(target_path, data)
            if not DRY:
                target_path.write_text(
                    yaml.safe_dump(
                        out, allow_unicode=True, sort_keys=False,
                        default_flow_style=False,
                    ),
                    encoding="utf-8",
                )
            merged.append(f"{sid} → {target_id} (+{len(data.get('topics', []))} topics)")
        else:
            if target_path.exists():
                # collision non prévue : signaler, ne pas écraser
                print(f"[WARN] collision non gérée : {path.name} vs {target_path.name}")
                continue
            if not DRY:
                target_path.write_text(
                    yaml.safe_dump(
                        data, allow_unicode=True, sort_keys=False,
                        default_flow_style=False,
                    ),
                    encoding="utf-8",
                )
            created.append(f"{target_id} ({len(data.get('topics', []))} topics)")

        # knowledge .md : copier les .md du sujet
        src_dir = staging_know / sid
        if src_dir.exists():
            for md in src_dir.glob("*.md"):
                # source = {target_id}/{topic} ; le fichier vit sous
                # knowledge/{target_id}/{topic}.md
                dest_dir = KNOW / target_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / md.name
                if not dest.exists():
                    if not DRY:
                        shutil.copy2(md, dest)
                    md_copied += 1

    # actualites : structure README par rubrique → knowledge/actualites/*
    act = staging_know / "actualites"
    if act.exists():
        for sub in act.iterdir():
            if sub.is_dir():
                dest_dir = KNOW / "actualites" / sub.name
                dest_dir.mkdir(parents=True, exist_ok=True)
                for md in sub.glob("*.md"):
                    dest = dest_dir / md.name
                    if not dest.exists():
                        if not DRY:
                            shutil.copy2(md, dest)
                        md_copied += 1

    print(f"CREATED: {created}")
    print(f"MERGED: {merged}")
    print(f"MD COPIED: {md_copied}")
    print(f"DRY RUN: {DRY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
