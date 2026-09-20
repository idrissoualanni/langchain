# Python — Fonctions

## definition
Une fonction est un bloc de code réutilisable portant un nom. On la définit avec le mot-clé `def` suivi du nom, de parenthèses et de deux points. Le corps de la fonction est indenté. Par exemple : `def saluer():` puis le bloc. Une fonction bien nommée décrit ce qu'elle fait. Une fonction peut être appelée autant de fois que nécessaire, ce qui évite la duplication de code et rend le programme modulaire.

## return
L'instruction `return` renvoie une valeur au code appelant et termine immédiatement l'exécution de la fonction. Sans `return` explicite, une fonction Python renvoie `None`. On peut renvoyer plusieurs valeurs avec un tuple : `return a, b`. Une fonction peut contenir plusieurs `return`, notamment pour des cas de sortie anticipée (early return). Toute instruction placée après un `return` exécuté ne sera jamais atteinte.

## parametres
Un paramètre est une variable déclarée dans la définition de la fonction ; un argument est la valeur effectivement passée lors de l'appel. Python autorise les valeurs par défaut (`def f(x, n=2)`), les paramètres nommés (`f(n=3, x=1)`), et le passage d'un nombre variable d'arguments avec `*args` (tuple) et `**kwargs` (dict). Les arguments nommés doivent suivre les arguments positionnels. Attention au piège des valeurs par défaut mutables : ne jamais utiliser une liste vide `[]` comme défaut, préférer `None`.

## portee
La portée d'une variable définit où elle est accessible. Une variable créée dans une fonction est locale : elle n'existe que pendant l'exécution de la fonction. Python applique la règle LEGB (Local, Enclosing, Global, Built-in) pour résoudre les noms. Le mot-clé `global` permet de modifier une variable globale depuis une fonction — mais c'est une pratique à éviter autant que possible car elle rend le flux de données difficile à suivre. Une fonction doit idéalement communiquer par ses paramètres et sa valeur de retour.

## recursion
Une fonction récursive s'appelle elle-même pour résoudre un problème en le réduisant à des sous-problèmes plus petits. Toute récursion nécessite un cas de base (condition d'arrêt) et un cas récursif. Sans cas de base, la récursion est infinie et lève une RecursionError. L'exemple classique est la factorielle : `fact(n) = n * fact(n-1)` avec `fact(0) = 1`. La récursion est élégante pour les structures arborescentes, mais une boucle est souvent plus efficace en Python.
