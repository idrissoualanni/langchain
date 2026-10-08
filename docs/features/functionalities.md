# 🚀 Liste des Fonctionnalités Backend

Ce document recense l'intégralité des fonctionnalités implémentées dans le backend, classées par module.

## 🧠 Orchestration & Agent (LangGraph)
- **Routage Dynamique** : Dispatch intelligent des requêtes entre le retrieval, le fallback et les sous-graphes.
- **Sous-Graphes Spécialisés** :
    - `Coding` : Génération et exécution de code.
    - `Research` : Recherche web multi-étapes (Tavily).
    - `Problem` : Résolution d'exercices pédagogiques.
    - `Document` : RAG sur documents importés.
    - `Video` : Analyse et indexation de contenu vidéo.
- **Pilotage Pédagogique** : Injection de stratégies d'apprentissage dynamiques.

## 🔍 Contexte & Retrieval (RAG)
- **Retrieval Hybride** : Fusion de la recherche sémantique (pgvector/HNSW) et lexicale.
- **Pipeline RAG** : Ingestion, vectorisation et stockage de documents.
- **Gestion du Budget** : Optimisation des tokens LLM pour maintenir un contexte pertinent.

## 🎓 Moteur d'Apprentissage (Learning Engine)
- **Profil Apprenant** : Suivi persistant de la maîtrise des concepts et des lacunes.
- **Stratégie Adaptative** : Ajustement automatique du niveau d'aide (Scaffolding vs Challenge).

## 💾 Mémoire Cognitive
- **Mémoire Long Terme** : Stockage des faits utilisateur et connaissances conceptuelles.
- **Consolidation de Session** : Synthèse des interactions pour assurer la continuité.

## 🛠️ Infrastructure & Outils
- **Intégration MCP** : Support du Model Context Protocol (Calendrier, Système de fichiers).
- **Sandbox de Code** : Environnement d'exécution sécurisé pour le code généré.
- **Voix Temps Réel** : Intégration LiveKit (WebRTC) pour l'audio et la vidéo.
- **Système de Cache** : Couche Redis avec repli automatique sur `TTLCache` local.

## 🌐 API & Administration
- **Gestion des Threads** : Cycle de vie complet des conversations.
- **Administration** : Gestion du registre des matières et des bases de connaissances.
- **Observabilité** : Tracing et monitoring via LangSmith et LangFuse.
