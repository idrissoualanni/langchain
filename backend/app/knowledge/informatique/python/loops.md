# Python — Boucles

## for
La boucle `for` parcourt les éléments d'un itérable (liste, chaîne, range, dict). Syntaxe : `for element in iterable:`. La variable de boucle prend successivement chaque valeur. La fonction `enumerate(liste)` fournit à la fois l'index et la valeur. Pour un dictionnaire, `items()` donne les paires clé-valeur. Une boucle `for` peut parcourir n'importe quel objet itérable — c'est l'itération universelle de Python.

## while
La boucle `while` répète un bloc tant qu'une condition reste vraie. Elle convient quand le nombre d'itérations n'est pas connu à l'avance. La condition est réévaluée avant chaque itération. Si la condition est fausse dès le départ, le corps n'est jamais exécuté. Attention aux boucles infinies : s'assurer que quelque chose dans le corps fait évoluer la condition vers False.

## range
`range(stop)`, `range(start, stop)` et `range(start, stop, step)` génèrent des séquences d'entiers. range(5) produit 0, 1, 2, 3, 4 — la borne stop est exclue. Le pas peut être négatif pour compter à rebours : range(10, 0, -1). range est un générateur paresseux : il ne construit pas la liste en mémoire, ce qui le rend efficace même pour de grandes bornes. Pour itérer n fois, l'idiome canonique est `for i in range(n)`.

## break-continue
`break` interrompt immédiatement la boucle courante ; l'exécution continue après le bloc. `continue` passe directement à l'itération suivante sans exécuter le reste du corps. break ne sort que du niveau de boucle le plus interne. L'usage excessif de break rend le flux difficile à suivre — mais le pattern "chercher puis sortir dès trouvé" est un usage légitime et classique.

## comprehensions
Une liste en compréhension construit une liste en une expression : `[x * 2 for x in liste if x > 0]`. La syntaxe est `[expression for variable in iterable if condition]`. Les compréhensions sont plus concises et souvent plus rapides qu'une boucle for avec append. On peut aussi construire des dicts (`{k: v for ...}`) et des sets. Pour la lisibilité, préférer une boucle classique si la compréhension dépasse une ligne de logique.
