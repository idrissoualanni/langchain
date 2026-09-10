# Réseaux — Modèle OSI

## couches
Le modèle OSI (Open Systems Interconnection) organise la communication réseau en 7 couches : physique, liaison de données, réseau, transport, session, présentation, application. Chaque couche rend un service à la couche supérieure et s'appuie sur la couche inférieure. Cette séparation en couches permet de raisonner et de diagnostiquer les réseaux de manière structurée : chaque problème se localise à une couche précise.

## encapsulation
L'encapsulation est le mécanisme par lequel chaque couche enveloppe les données de la couche supérieure avec son propre en-tête. La couche application produit des données, la transport ajoute un en-tête TCP (segment), la réseau ajoute une en-tête IP (paquet), la liaison ajoute une en-tête Ethernet (trame). À la réception, le processus inverse (désencapsulation) retire chaque en-tête couche par couche. Les unités de données de protocole (PDU) portent des noms différents selon la couche : segment, paquet, trame, bits.

## osi-vs-tcpip
Le modèle OSI est un modèle de référence théorique en 7 couches ; le modèle TCP/IP est le modèle réel d'Internet en 4 couches (accès réseau, Internet, transport, application). TCP/IP regroupe en pratique les couches hautes d'OSI en une seule couche application. OSI sert à enseigner et à raisonner ; TCP/IP décrit ce qui est déployé. Les deux modèles coexistent : on diagnostique en OSI, on implémente en TCP/IP.
