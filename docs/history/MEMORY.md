# MEMORY — Tuteur Python (Ollama + Tavily)

- [refactor app.py] → erreurs: main() dupliqué x2, imports inutiles → fix: réorganisation en sections, main() unique sous garde __main__
- [fix tool-calling app.py] → erreurs: KeyError 'id' (tool_call["id"] inexistant dans ollama 0.6.2) → fix: message tool avec "tool_name" au lieu de "tool_call_id"
- [ajout tool recherche_web Tavily à app.py] → erreurs: none → fix: TavilyClient.search() avec include_answer="advanced", déclaré dans outils_ollama
- [suppression tool diagnostic_competence de app.py] → erreurs: none → fix: retiré fonction, mapping, déclaration, system prompt
- [création requirements.txt] → erreurs: fichier orthographié requirement.txt (vide) → fix: recréé avec ollama, python-dotenv, tavily-python
- [fix ap.py state] → erreurs: state["messages"] écrasé à chaque tour (0 mémoire), user_id/interaction_count réinitialisés par defaults Pydantic → fix: accumulation des messages, champs repassés explicitement à chaque invoke
- [ajout recherche native ollama à ap.py] → erreurs: prompt annonçait un outil inexistant → fix: @tool wrappant ollama.web_search() (signature vérifiée 0.6.2), try/except sur invoke