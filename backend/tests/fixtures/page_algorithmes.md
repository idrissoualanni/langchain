---
subject: python
topic: algorithmes
title: Introduction aux algorithmes
author: Pr. Turing
source: fixtures/page_algorithmes.md
status: draft
---

# Introduction aux algorithmes

## Définition

Un algorithme est une suite finie et non ambiguë d'opérations permettant
de résoudre un problème. Il se décrit indépendamment du langage.

## Complexité

La complexité décrit la croissance du coût (temps, mémoire) en fonction
de la taille de l'entrée. On l'exprime souvent avec la notation grand O.

```python
def somme(liste):
    total = 0
    for x in liste:
        total += x
    return total
```

## Recherche dichotomique

La recherche dichotomique divise par deux l'espace de recherche à chaque
étape ; elle exige une liste triée et coûte O(log n).
