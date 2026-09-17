# Mission Intégration — étape 5 : cohérence contenu des .md (§5).
# Ne jamais se fier au nom de fichier : vérifier H1, métadonnées
# Sujet/Topic dans le corps vs YAML déclaratif.
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, ".")
from app.subjects.registry import (  # noqa: E402
    invalidate,
    load_registry,
)

invalidate()
reg = load_registry()
KNOW = Path("app/knowledge")

# fusions légitimes (matière renommée zip → projet)
RENAMED = {
    "biology": "biologie",
    "mathematics": "mathematiques",
    "computer_networks": "reseaux_cybersecurite",
}

issues = []
checked = 0
for sid, cfg in sorted(reg.items()):
    for src in cfg.knowledge.get("sources", []):
        p = KNOW / f"{src}.md"
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        checked += 1
        h1 = re.search(r"^# (.+)$", text, re.M)
        if not h1:
            issues.append(f"{src}: pas de H1")
            continue
        m_subj = re.search(r"\*\*Sujet :\*\*\s*(\S+)", text)
        m_top = re.search(r"\*\*Topic :\*\*\s*(\S+)", text)
        if m_subj and m_subj.group(1) != sid:
            if RENAMED.get(sid) != m_subj.group(1):
                issues.append(
                    f'{src}: Sujet md="{m_subj.group(1)}" '
                    f'!= yaml "{sid}"'
                )
        if m_top:
            topic = m_top.group(1)
            if topic not in cfg.topics:
                issues.append(
                    f'{src}: Topic md="{topic}" pas dans topics yaml'
                )

print(f"FILES CHECKES: {checked}")
print(f"INCOHERENCES: {len(issues)}")
for i in issues:
    print(" -", i)
