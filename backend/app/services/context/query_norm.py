# Query Normalization V6.5 (§8) — normalisation contrôlée des
# requêtes de recherche.
#
# Étapes (toutes GÉNÉRIQUES — aucun if subject, aucune liste de
# matières) :
#   1. fold accents (NFD) — « fonctions » ≡ « fonctioncs » ;
#   2. lowercase ;
#   3. ponctuation → espaces (tirets inclus) ;
#   4. whitespace collapsé ;
#   5. variantes morphologiques CONTRÔLÉES :
#      - pluriel FR → singulier (s / x finaux) ;
#      - pluriel EN → singulier (es / s) ;
#      - « fonction » ≡ « fonctions » ≡ « function » ≡ « functions »
#        via le pluriel FR/EN + le stem commun.
#
# Le pluriel anglais « functions » partage le stem « function »
# avec le singulier FR « fonction » ? NON — « fonction » (FR) et
# « function » (EN) diffèrent d'une lettre (c/t finale) : la
# variation FR↔EN est gérée par le ROUTER via les aliases/topics
# du SubjectConfig (source déclarative YAML, §9), PAS par ce
# module. Ce module normalise la FORME, pas la langue.
import re
import unicodedata

# Variantes orthographiques contrôlées (suffixes flexionnels
# uniquement — pas de dictionnaire de synonymes global, §9).
_PLURAL_ES_RE = re.compile(r"([a-z]{3,})es\b")
_PLURAL_S_RE = re.compile(r"([a-z]{3,})s\b")
_PLURAL_X_RE = re.compile(r"([a-z]{3,})x\b")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _strip_accents(text: str) -> str:
    """Fold accents (NFD) — indépendant de la casse source."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_query(text: str) -> str:
    """Normalisation complète §8 : accents, casse, ponctuation,
    whitespace. Retourne le texte normalisé (mots séparés)."""
    if not text:
        return ""
    t = _strip_accents(text.lower())
    t = _PUNCT_RE.sub(" ", t)  # ponctuation → espace
    t = _WS_RE.sub(" ", t).strip()
    return t


def _singularize(token: str) -> str:
    """Singulier contrôlé d'un token SANS stop-words courts.

    Règles morphologiques uniquement (suffixe flexionnel) :
      -…es  → -e/-∅ (boxes→box, tables→table)
      -…s   → ∅ (fonctions→fonction)
      -…x   → ∅ (cours→cour invalide ? NON : « cours » est
      déjà singulier → règle x DÉSACTIVÉE, cf. plus bas)
    """
    if len(token) < 4:
        return token
    m = _PLURAL_ES_RE.match(token)
    if m and not token.endswith("ss"):
        stem = m.group(1)
        # tables → table ; boxes → box (le e final réapparaît au
        # singulier FR dans ~tous les cas : table(s), boite(s))
        return stem + "e" if stem.endswith("t") is False else stem
    m = _PLURAL_S_RE.match(token)
    if m and not token.endswith("ss") and not token.endswith("us"):
        return m.group(1)
    return token


def normalize_tokens(text: str) -> list[str]:
    """Tokens normalisés + SINGULARISÉS d'une requête.

    « les fonctions et les boucles » → [fonction, boucle] —
    les pluriels FR/EN se rapprochent des topics Registry qui
    sont majoritairement au singulier (fonction? NON — le
    Registry V4 a « fonctions » AU PLURIEL ; mais « boucles »
    aussi → ce module rapproche « boucle » (singulier user) de
    « boucles » (topic Registry) en singularisant l'entrée
    user PUIS en laissant le router comparer via les variantes.
    """
    norm = normalize_query(text)
    if not norm:
        return []
    return [
        _singularize(tok) for tok in norm.split() if tok
    ]


def variant_forms(token: str) -> set[str]:
    """Formes variantes d'un token (stem + pluriels FR/EN).

    Utilisé par le router pour rapprocher une entrée user
    « fonction » du topic Registry « fonctions » sans liste
    globale de synonymes : les variantes sont MORPHOLOGIQUES,
    dérivées du token, pas déclarées à la main.
    """
    if not token:
        return set()
    stem = _singularize(token)
    return {
        token,
        stem,
        stem + "s",       # pluriel FR/EN régulier
        stem + "es",      # pluriel EN (boxes)
        stem + "x",       # pluriel FR irrégulier
    }


def expand_query_terms(text: str) -> set[str]:
    """Tous les tokens + toutes leurs variantes d'une requête.

    « je comprends pas les closures » → {closure, closures,
    closurees(?)...} — non : « closures » → stem « closure » →
    {closures, closure, closureses×} etc. Le router teste
    l'appartenance topic ∈ variantes(query) OU variantes(topic)
    ∩ tokens(query) — cf. router.py V6.5.
    """
    out: set[str] = set()
    for tok in normalize_tokens(text):
        out |= variant_forms(tok)
    return out
