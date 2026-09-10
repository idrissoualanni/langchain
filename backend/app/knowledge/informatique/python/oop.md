# Python — Programmation orientée objet

## classes
Une classe est un modèle qui décrit des objets : leurs données (attributs) et leurs comportements (méthodes). On la définit avec `class Nom:`. La méthode spéciale `__init__` est le constructeur, appelé à la création de l'objet. Par convention, les noms de classes utilisent le CapWords (PascalCase). Un attribut d'instance se crée via `self.attribut = valeur` dans `__init__`.

## objets
Un objet est une instance concrète d'une classe : `mon_compte = Compte("Alpha")`. Chaque instance possède ses propres attributs, indépendants des autres instances. La fonction `isinstance(obj, Classe)` teste l'appartenance à une classe. Plusieurs instances d'une même classe coexistent sans interférer. La méthode `__str__` définit la représentation lisible affichée par print.

## methodes
Une méthode est une fonction définie dans une classe ; son premier paramètre est `self`, la référence à l'instance courante. On l'appelle sur l'objet : `mon_compte.deposer(100)`. Un attribut de classe (partagé par toutes les instances) se déclare directement dans le corps de la classe, contrairement à l'attribut d'instance défini via self. Les méthodes modifient l'état de l'objet ou exploitent ses attributs.

## heritage
L'héritage permet à une classe fille de réutiliser et spécialiser une classe mère : `class Eleve(Personne):`. La fille hérite des attributs et méthodes de la mère. `super()` permet d'appeler le constructeur de la mère depuis la fille. La redéfinition (override) remplace une méthode héritée par une version spécialisée. Python supporte l'héritage multiple — à utiliser avec prudence.

## encapsulation
L'encapsulation protège l'état interne d'un objet : les attributs préfixés par `_` signalent un usage interne (convention), ceux préfixés par `__` déclenchent le name mangling. Python privilégie la convention à l'interdiction : rien n'empêche techniquement d'accéder à un attribut privé, mais un code bien conçu respecte ces conventions. Les @property permettent d'exposer des attributs calculés avec une syntaxe d'accès simple.
