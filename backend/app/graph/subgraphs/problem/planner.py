# Problem Subgraph — PLAN INTERNE + GUIDE pas à pas (§21).
#
# build_plan : traduit un ParsedStatement en LISTE D'ÉTAPES attendues
# (SolutionStep) ordonnées — le plan interne de résolution.
# build_guide : pour un plan donné, produit le guide pas à pas (hint
# par étape) NULLE solution n'est donnée : le guide oriente, ne résout
# pas (donner la réponse serait une fuite, §15/§21).
#
# DÉTERMINISTE : les étapes dérivent de la classe d'énoncé détectée
# par le parsing. Aucun LLM.
from __future__ import annotations

from app.schemas.problem import (
    ParsedStatement,
    SolutionStep,
)

# Étapes DÉTERMINISTES par classe d'énoncé (§21 plan interne).
# Chaque étape : {kind, label, hint}. expected reste vide (la réponse
# exacte serait une fuite — l'évaluation de l'étudiant est faite par
# le moteur §20 au moment de la soumission).
_STEP_TEMPLATES: dict[str, list[dict]] = {
    "derivee": [
        {
            "kind": "formuler",
            "label": "Écrire la fonction à dériver",
            "hint": "Identifie la fonction et réécris-la sous une forme dérivable.",
        },
        {
            "kind": "appliquer_derivee",
            "label": "Appliquer la règle de dérivation",
            "hint": "Utilise les règles usuelles (puissance, produit, chaîne).",
        },
        {
            "kind": "simplifier",
            "label": "Simplifier l'expression obtenue",
            "hint": "Factorise et réduis les termes semblables.",
        },
        {
            "kind": "conclure",
            "label": "Écrire la dérivée finale",
            "hint": "Donne f'(x) sous forme simplifiée.",
        },
    ],
    "integrale": [
        {
            "kind": "formuler",
            "label": "Écrire l'intégrale à calculer",
            "hint": "Reconnais la fonction et les bornes éventuelles.",
        },
        {
            "kind": "primitive",
            "label": "Déterminer une primitive",
            "hint": "Applique les primitives usuelles ou une intégration par parties.",
        },
        {
            "kind": "evalu",
            "label": "Évaluer aux bornes",
            "hint": "Calcule F(b) - F(a) si bornes données.",
        },
        {
            "kind": "conclure",
            "label": "S'écrire le résultat final",
            "hint": "Conclus avec le résultat numérique ou l'expression.",
        },
    ],
    "equation": [
        {
            "kind": "formuler",
            "label": "Écrire l'équation",
            "hint": "Mets tous les termes d'un même côté si besoin.",
        },
        {
            "kind": "resoudre",
            "label": "Isolet l'inconnue",
            "hint": "Utilise les opérations inverses de part et d'autre de l'égalité.",
        },
        {
            "kind": "verifier",
            "label": "Vérifier la solution",
            "hint": "Remplace la solution dans l'équation de départ.",
        },
        {
            "kind": "conclure",
            "label": "Écrire l'ensemble des solutions",
            "hint": "Écris S = {...} en conclusion.",
        },
    ],
    "inequation": [
        {
            "kind": "formuler",
            "label": "Écrire l'inéquation",
            "hint": "Réunis les termes et identifie l'inconnue.",
        },
        {
            "kind": "etude_signe",
            "label": "Étudier le signe",
            "hint": "Résous en étudiant le signe de l'expression.",
        },
        {
            "kind": "tableau",
            "label": "Récapitule dans un tableau de signes",
            "hint": "Tableau de signes des facteurs puis de l'expression.",
        },
        {
            "kind": "conclure",
            "label": "Écrire l'intervalle solution",
            "hint": "Donne l'intervalle des x vérifiant l'inégalité.",
        },
    ],
    "factorisation": [
        {
            "kind": "formuler",
            "label": "Écrire l'expression",
            "hint": "Repère un facteur commun ou une identité remarquable.",
        },
        {
            "kind": "factoriser",
            "label": "Mettre en facteur",
            "hint": "Factorise par le facteur commun ou l'identité.",
        },
        {
            "kind": "verifier",
            "label": "Développer pour vérifier",
            "hint": "Développe le résultat pour retrouver l'expression initiale.",
        },
        {
            "kind": "conclure",
            "label": "Écrire la forme factorisée",
            "hint": "Donne l'expression factorisée finale.",
        },
    ],
    "trigonometrie": [
        {
            "kind": "formuler",
            "label": "Repérer l'angle ou le triangle",
            "hint": "Identifie l'angle considéré et les données.",
        },
        {
            "kind": "appliquer_formule",
            "label": "Appliquer la formule trigonométrique",
            "hint": "Utilise cos/sin/tan ou les formules d'addition.",
        },
        {
            "kind": "calculer",
            "label": "Calculer la grandeur demandée",
            "hint": "Résous la relation obtenue (longueur, angle...).",
        },
        {
            "kind": "conclure",
            "label": "Conclure avec l'unité",
            "hint": "Donne le résultat avec son unité (m, degre...).",
        },
    ],
    "geometrie": [
        {
            "kind": "formuler",
            "label": "Récapituler les données de la figure",
            "hint": "Liste longueurs, angles et propriétés connues.",
        },
        {
            "kind": "appliquer_propriete",
            "label": "Appliquer la propriété géométrique",
            "hint": "Utilise le théorème adapté (de Pythagore, de Thalès...).",
        },
        {
            "kind": "calculer",
            "label": "Calculer la grandeur demandée",
            "hint": "Applique la formule (aire, volume, longueur).",
        },
        {
            "kind": "conclure",
            "label": "Conclure avec l'unité",
            "hint": "Donne le résultat avec son unité.",
        },
    ],
    "suite": [
        {
            "kind": "identifier",
            "label": "Identifier le type de suite",
            "hint": "Arithmétique, géométrique, ou définie par récurrence ?",
        },
        {
            "kind": "exprimer",
            "label": "Écrire la raison ou la relation de récurrence",
            "hint": "Exprime u(n+1) - u(n) ou u(n+1)/u(n) selon le type.",
        },
        {
            "kind": "calculer",
            "label": "Calculer le terme général",
            "hint": "Déduis u(n) en fonction de n.",
        },
        {
            "kind": "conclure",
            "label": "Conclure (variation, limite, somme)",
            "hint": "Conclus selon la question posée.",
        },
    ],
    "probabilite": [
        {
            "kind": "modele",
            "label": "Modéliser l'expérience",
            "hint": "Décris l'univers des possibles (cardinal, équiprobabilité).",
        },
        {
            "kind": "definir_evenement",
            "label": "Définir l'événement",
            "hint": "Exprimer l'événement demandé en termes d'issues.",
        },
        {
            "kind": "calculer",
            "label": "Calculer la probabilité",
            "hint": "Applique la formule nombre_cas_favorables / nombre_cas_possibles.",
        },
        {
            "kind": "conclure",
            "label": "Conclure en probabilité",
            "hint": "Donne le résultat comme nombre en [0,1] ou pourcentage.",
        },
    ],
    "logique": [
        {
            "kind": "formuler",
            "label": "Énoncer l'assertion",
            "hint": "Écris clairement la proposition à démontrer.",
        },
        {
            "kind": "hypotheses",
            "label": "Rappeler les hypothèses",
            "hint": "Liste ce qui est supposé vrai.",
        },
        {
            "kind": "raisonner",
            "label": "Dérouler le raisonnement",
            "hint": "Applique implication / contraposition / cas par cas.",
        },
        {
            "kind": "conclure",
            "label": "Conclure",
            "hint": "Conclus la démonstration explicitement.",
        },
    ],
    "autre": [
        {
            "kind": "formuler",
            "label": "Lire et reformuler l'énoncé",
            "hint": "Reformule la question en tes propres mots.",
        },
        {
            "kind": "planifier",
            "label": "Choisir une méthode",
            "hint": "Pense aux outils adaptés au thème.",
        },
        {
            "kind": "resoudre",
            "label": "Résoudre étape par étape",
            "hint": "Avance pas à pas en justifiant.",
        },
        {
            "kind": "verifier",
            "label": "Vérifier et conclure",
            "hint": "Relis, vérifie les calculs, conclus proprement.",
        },
    ],
}


def build_plan(parsed: ParsedStatement) -> list[SolutionStep]:
    """Construit le plan interne d'étapes (§21) pour l'énoncé parsé.

    DÉTERMINISTE : les étapes viennent du gabarit de la classe.
    Chaque étape reçoit un step_id stable (step-<n>).
    """
    template = _STEP_TEMPLATES.get(parsed.statement_class, _STEP_TEMPLATES["autre"])
    steps: list[SolutionStep] = []
    for idx, spec in enumerate(template, start=1):
        steps.append(
            SolutionStep(
                step_id=f"step-{idx}",
                label=spec["label"],
                kind=spec["kind"],
                hint=spec["hint"],
                expected="",
                error_kind="aucune",
            )
        )
    return steps


def build_guide(plan: list[SolutionStep], current_index: int) -> str:
    """Guide pas à pas pour l'ÉTAPE COURANTE du plan (§21 guide).

    Ne divulgue jamais de réponse (hint ≠ solution). Mémo de
    progression : "Étape 2/4 — <label>".
    """
    if not plan:
        return ""
    idx = max(0, min(current_index, len(plan) - 1))
    step = plan[idx]
    return f"Étape {idx + 1}/{len(plan)} — {step.label}\n{step.hint}"


__all__ = ["build_plan", "build_guide"]