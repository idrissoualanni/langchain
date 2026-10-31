"""Reproduction : le tool update_user_profile levait NameError à chaque appel.

`write_profile` n'était pas importé dans app/tools/memory/memory.py — le
modèle ne pouvait jamais enregistrer le nom ou la description de
l'apprenant. Détecté par ruff (F821), désormais bloquant en CI.
"""
import langgraph.config

import app.tools.memory.memory as memory_tools


def test_update_user_profile_enregistre_le_profil(monkeypatch):
    calls = []
    monkeypatch.setattr(
        langgraph.config, "get_config", lambda: {"configurable": {"user_id": "u1"}}
    )
    monkeypatch.setattr(
        memory_tools,
        "write_profile",
        lambda user_id, fields: calls.append((user_id, fields)) or fields,
    )

    result = memory_tools.update_user_profile.func(name="Ada")

    assert result == {"name": "Ada"}
    assert calls == [("u1", {"name": "Ada"})]
