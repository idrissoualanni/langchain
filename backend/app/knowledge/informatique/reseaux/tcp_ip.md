# Réseaux — TCP/IP

## ip
Le protocole IP (Internet Protocol) achemine les paquets de l'émetteur au destinataire par adressage. IPv4 utilise des adresses 32 bits (ex: 192.168.1.1), IPv6 des adresses 128 bits. IP est un protocole sans connexion et sans garantie de livraison (best effort) : les paquets peuvent être perdus, dupliqués ou arriver dans le désordre. C'est TCP, au-dessus, qui rétablit la fiabilité. Le routage IP choisit le prochain saut vers la destination à chaque paquet indépendamment.

## tcp
TCP (Transmission Control Protocol) fournit un transport fiable, ordonné et orienté connexion, par-dessus IP. Il numérorote les octets, accuse réception (ACK), retarme les pertes et contrôle le flux et la congestion. L'établissement d'une connexion suit le three-way handshake : SYN, SYN-ACK, ACK. La connexion se termine par une séquence FIN. TCP garantit que les données arrivent complètes, dans l'ordre, sans duplication.

## udp
UDP (User Datagram Protocol) est le transport minimal : pas de connexion, pas d'accusé de réception, pas de garantie d'ordre. Il ajoute à IP uniquement un en-tête léger avec ports et checksum. Ce coût réduit le rend adapté aux applications temps réel (streaming audio/vidéo, jeux, DNS) où la latence prime sur la fiabilité. Une perte occasionnelle est préférable à une retransmission qui retarderait tout le flux.

## ports
Un port identifie une application ou un service sur une machine (0 à 65535). Un socket = couple (adresse IP, port). Les ports 0-1023 sont dits réservés (HTTP 80, HTTPS 443, SSH 22, DNS 53), les 1024-49151 enregistrés, les 49152-65535 éphémères (clients). Une connexion TCP est identifiée de façon unique par le quadruplet (IP source, port source, IP destination, port destination) — ce qui permet plusieurs connexions simultanées vers le même serveur.

## dns
Le DNS (Domain Name System) traduit les noms de domaine en adresses IP. La résolution interroge les serveurs DNS en cascade : resolver local, serveurs racine, TLD, serveurs autoritaires. Les réponses sont mises en cache avec une durée de vie (TTL) pour limiter le trafic. DNS utilise principalement UDP sur le port 53, bascule sur TCP pour les grandes réponses.
