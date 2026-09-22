# Subgraphs spécialisés du Main Graph.
#
# Chaque sous-graphe expose un contrat §8 (workflow_result) et une
# fabrique standardisée : compile_<name>_subgraph() (§5). Aucun LLM
# dans les sous-graphes déterministes (problem, document) ; les
# sous-graphes agentiques seront wrapperés par le node correspondant.