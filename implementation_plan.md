# Implementation Plan

## [Overview]

Faire converger la base de connaissance vers la logique cible en conservant **Neon comme
source de vérité unique** (décision NEON-ONLY), et non un dossier Markdown. Le périmètre
ferme six écarts identifiés par l'audit : (1) pipeline **PDF/Word → Markdown** ; (2)
**chunking par titres** avec secours **800 caractères / chevauchement 100** ; (3) recherche
**hybride** ajoutant `tsvector` + index **GIN** à côté de HNSW ; (4) **ingestion incrémentale
par hash + réconciliation** (suppression des sources disparues) ; (5) **statut de validation
admin par sujet** avec gating fail-closed + métadonnée **`auteur`** ; (6) **visualisation 3D**
Three.js (`Points`/`Mesh`/`Line`) des chunks vectorisés, projection 3D par **PCA** côté backend.
Toutes les migrations sont **additives et idempotentes** (le Neon de staging est partagé avec
la prod). Le format d'import **frontmatter/YAML** est formalisé et validé par Pydantic.

## [Types]

- `backend/app/schemas/subject.py` : `SubjectConfig` (dataclass) + `status: str = "draft"` +
  `author: str = ""` ; type `SubjectStatus = Literal["draft","review","validated","archived"]` ;
  nouveau `SubjectDefinitionIn(BaseModel)` (validation Pydantic des définitions) ;
  `SubjectOut` + `status`/`author`.
- `backend/app/schemas/knowledge.py` (nouveau) : `ChunkFrontmatter`, `SectionUpsertRequest(+author)`,
  `SubjectStatusUpdate`, `ChunkVector3D`, `ChunkVizResponse`, `ChunkEdge`, `ReconcileResponse`.

## [Files]

- `backend/app/infrastructure/database/schema.py` — `subject_definitions` +`status`,`author` ;
  `knowledge_sections` +`author` + `content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('french',…)) STORED`
  + index `gin(content_tsv)`. Alter idempotents.
- `backend/app/services/knowledge/store.py` — `upsert_section(+author)`, `search_hybrid`,
  `load_subject_definitions(only_validated=True)`, `load_subject_meta`,
  `upsert_subject_definition(...,status,author)`, `reconcile_subject_sources`, `list_chunk_vectors`,
  `set_subject_status`.
- `backend/app/services/knowledge/convert.py` (nouveau) — PDF/Word→Markdown.
- `backend/app/services/knowledge/frontmatter.py` (nouveau) — frontmatter YAML + découpe `##`.
- `backend/app/services/knowledge/viz.py` (nouveau) — PCA (numpy SVD) → 3D + kNN edges.
- `backend/app/services/knowledge/ingest.py` (nouveau) — orchestrateur convert→chunk→embed→upsert→reconcile.
- `backend/app/services/documents/chunker.py` — + `chunk_markdown(text, *, max_chars=800, overlap_chars=100)`.
- `backend/app/subjects/registry.py` — gating `only_validated=True`.
- `backend/app/services/context/knowledge_retriever.py` — `search_hybrid` + garde-fou validation.
- `backend/app/tools/knowledge/knowledge.py` (nouveau) — tool `search_knowledge` + `__init__.py`.
- `backend/app/tools/__init__.py` — ajouter `knowledge_tools`.
- `backend/app/services/agent/tool_descriptions.py` — entrée `search_knowledge`.
- `backend/app/api/admin/subjects.py` — statut/auteur + `PATCH /{id}/status`.
- `backend/app/api/admin/knowledge.py` — upload (docx/pdf), `GET …/chunks/viz`, `POST …/corpus/reconcile`.
- Frontend : `ChunkEmbeddingViz3D.tsx`, `SubjectValidationPanel.tsx`, `useChunkViz.ts`,
  `SubjectDefinitionsPanel.tsx`, `KnowledgePage.tsx`.
- `AGENTS.md`, `backend/requirements.txt`, `frontend/package.json`.

## [Functions]

- `convert.pdf_to_markdown / docx_to_markdown / to_markdown`
- `frontmatter.parse_frontmatter / split_sections_markdown`
- `chunker.chunk_markdown(text, *, max_chars=800, overlap_chars=100)`
- `store.search_hybrid`, `store.reconcile_subject_sources`, `store.list_chunk_vectors`,
  `store.load_subject_meta`, `store.set_subject_status`
- `viz.project_embeddings_3d`, `viz.knn_edges`, `viz.get_chunk_viz`
- tool `search_knowledge(subject, query, top_k=3)`

## [Classes]

- `SubjectDefinitionIn`, `ChunkFrontmatter`, `ChunkVector3D`, `ChunkVizResponse`, `ChunkEdge`,
  `ReconcileResponse`, `SubjectStatusUpdate` (Pydantic).
- `KnowledgeIngestor` (`services/knowledge/ingest.py`).

## [Dependencies]

- Backend : `mammoth` (Word→MD). `pymupdf`, `numpy` déjà présents.
- Frontend : `three`, `@react-three/fiber`, `@react-three/drei`.

## [Testing]

- 3 pages fixtures (`page_algorithmes.md`, `cours.pdf`, `lecon.docx`).
- Offline : `test_knowledge_convert.py`, `test_knowledge_chunker.py`, `test_knowledge_frontmatter.py`.
- DB (si `DATABASE_URL`) : `test_knowledge_ingestion.py`, `test_subject_validation_gating.py`,
  `test_knowledge_reconcile.py`, `test_knowledge_tool.py`.

## [Implementation Order]

1. schema.py → 2. schemas → 3. store.py → 4. registry.py → 5. knowledge_retriever + tool
`search_knowledge` → 6. convert/frontmatter/chunker/viz/ingest → 7. API admin →
8. requirements/package.json → 9. frontend → 10. tests + docstrings → 11. AGENTS.md → 12. vérif.

---

## Extensions (session 2) — reranking + propositions

### Reranking du tool `search_knowledge`

- Nouveau `backend/app/services/knowledge/rerank.py` : deuxieme etage de tri
  APRES la recherche hybride. Signaux : couverture des mots de la requete dans le
  passage, dans le titre, et presence litterale de la requete.
- Interface `Reranker` (Protocol) + `get_reranker` / `set_reranker` : un reranker
  LLM / cross-encoder se branche sans modifier le retriever ni le tool.
- `knowledge_retriever.search_knowledge` genere un **pool** de candidates
  (`limit * 4`) puis reranke vers le `top_k` demande.
- Contrainte d import : `normalize_query` est charge **paresseusement** (le
  package `app.services.context` cree un cycle via builder -> knowledge_retriever).
- Tests offline : `backend/tests/test_knowledge_rerank.py` (reclassement lexical,
  pliage des accents, signaux exposes, reranker branche).

### Tool `propose_knowledge` + approbation admin

- Nouveau tool `propose_knowledge(subject, title, content, reason)` : ecrit une
  proposition dans `knowledge_proposals` ( `status='pending'` ). Elle n entre
  **JAMAIS** dans le corpus sans decision admin.
- Refus si la matiere est inconnue ou si le contenu est vide ; fail-safe ( erreur
  capturee, jamais propagee ).
- `store.decide_proposal` : l approbation vectorise puis insere dans
  `knowledge_sections` ; si l embedding echoue la proposition **reste pending**
  ( HTTP 503 ). Une proposition deja decidee renvoie 409.
- API admin : `GET /api/admin/knowledge/proposals`,
  `POST /api/admin/knowledge/proposals/{id}/decide`,
  `DELETE /api/admin/knowledge/proposals/{id}`.
- Frontend : `KnowledgeProposalsPanel.tsx` (filtre par statut, Approuver / Rejeter)
  integre dans `KnowledgePage.tsx`.
- Tests offline : `backend/tests/test_knowledge_proposal.py`.

### Documentation

- `AGENTS.md` : sections **8.6 Reranking** et **8.7 Propositions de connaissance**.