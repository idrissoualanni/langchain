# Python — Les bases

## variables
Une variable est un nom qui référence une valeur en mémoire. En Python, on crée une variable par simple assignation : `x = 5`. Le nom d'une variable doit commencer par une lettre ou un underscore, et Python est sensible à la casse. Une variable peut être réassignée à tout moment, y compris à une valeur d'un autre type. La fonction `type()` permet de connaître le type d'une variable. Les noms de variables explicites (par exemple `compteur` plutôt que `c`) rendent le code lisible et maintenable.

## types
Python manipule plusieurs types de base : `int` (entiers), `float` (nombres à virgule), `str` (chaînes de caractères), `bool` (True/False), et `NoneType` (la valeur None). La conversion entre types se fait par les fonctions `int()`, `float()`, `str()`, `bool()`. La fonction `isinstance(v, int)` vérifie l'appartenance à un type. Python est à typage dynamique : le type appartient à la valeur, pas à la variable. Le typage fort de Python interdit les opérations entre types incompatibles : `"a" + 1` lève une TypeError, alors que `"a" + str(1)` fonctionne.

## print
La fonction `print()` affiche des valeurs sur la sortie standard. Elle accepte plusieurs arguments séparés par des virgules et les joint par des espaces. Le paramètre `sep` change le séparateur, `end` change ce qui est affiché en fin de ligne (saut de ligne par défaut). Les f-strings (`f"valeur : {x}"`) sont la façon moderne et recommandée d'insérer des expressions dans une chaîne. print renvoie toujours None — c'est un affichage, pas une valeur exploitable.

## indentation
L'indentation est syntaxique en Python : elle définit les blocs de code. Un bloc commence par `:` et toutes ses lignes doivent être indentées au même niveau (4 espaces par convention). Une indentation incorrecte lève une IndentationError. Contrairement aux langages à accolades, l'indentation n'est pas décorative : elle fait partie de la grammaire du langage. Les blocs imbriqués ajoutent un niveau d'indentation supplémentaire à chaque niveau.
