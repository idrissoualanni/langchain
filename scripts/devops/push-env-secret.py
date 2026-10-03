#!/usr/bin/env python3
r"""
But
    Poser une variable d'environnement SECRE sur un service Render, sans que la
    valeur n'apparaisse jamais dans un terminal, un journal, une sortie d'agent
    ou le depot.

Quand l'utiliser
    Quand une cle doit etre deposee sur une plateforme (Render, Vercel) et que la
    valeur ne peut pas transiter par une conversation ou un fichier versionne.
    Exemple : la cle Deepgram, absente des 87 variables de production.

Niveau de permission
    Niveau 2 - ecriture sur la configuration d'un service.
    Sur la PRODUCTION : exiger une confirmation explicite de l'utilisateur.

Environnements
    prod    = srv-daq69ctg1s2s73f9okog
    staging = srv-db0ip2ugekts739sr36g

Effets de bord
    - cree ou remplace la variable chez Render ;
    - n'ecrit RIEN sur le disque, ne lit aucun .env du depot ;
    - ne redeploie pas : la variable ne prend effet qu'au prochain redemarrage.

Securite
    - la valeur vient d'un fichier temporaire choisi par l'appelant, hors depot ;
    - la valeur n'est jamais affichee, ni tronquee, ni comparee en clair ;
    - la verification porte sur la LONGUEUR et une empreinte SHA-256, jamais
      sur le contenu ;
    - aucun secret n'est ecrit dans ce fichier.

Mode simulation
    Le script est sec par defaut : sans --apply il affiche ce qu'il ferait et
    sort. --apply est obligatoire pour ecrire.

Usage
    # 1. ecrire la cle dans un fichier temporaire hors depot
    #    (PowerShell, qui ne laisse pas la valeur dans l'historique du chat)
    Set-Content -NoNewline -Path "$env:TEMP\deepgram.key" -Value "<la cle>"

    # 2. simulation
    python scripts/devops/push-env-secret.py --env staging \\
        --name DEEPGRAM_API_KEY --from-file "$env:TEMP/deepgram.key"

    # 3. application
    python scripts/devops/push-env-secret.py --env staging \\
        --name DEEPGRAM_API_KEY --from-file "$env:TEMP/deepgram.key" --apply

    # 4. nettoyer la trace locale
    Remove-Item "$env:TEMP\deepgram.key"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

SERVICES = {
    "prod": "srv-daq69ctg1s2s73f9okog",
    "staging": "srv-db0ip2ugekts739sr36g",
}

API = "https://api.render.com/v1"


def cle_api() -> str:
    """Jeton Render. Jamais affiche, jamais journalise."""
    cfg = pathlib.Path.home() / ".render" / "cli.yaml"
    if not cfg.exists():
        sys.exit("~/.render/cli.yaml introuvable :Render CLI non authentifie")
    import yaml  # dependance du CLI Render

    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    jeton = (data.get("api") or {}).get("key")
    if not jeton:
        sys.exit("jeton absent de ~/.render/cli.yaml")
    return jeton


def lire_valeur(chemin: str) -> str:
    p = pathlib.Path(chemin).expanduser()
    if not p.exists():
        sys.exit(f"fichier source introuvable : {p}")
    valeur = p.read_text(encoding="utf-8").strip()
    if not valeur:
        sys.exit("fichier source vide")
    # Garde-fou : refuser une valeur multiligne, signe d'un fichier de config.
    if "\n" in valeur or len(valeur) > 4096:
        sys.exit("valeur refusee : multiligne ou trop longue")
    return valeur


def poser(service: str, nom: str, valeur: str) -> None:
    h = {
        "Authorization": f"Bearer {cle_api()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(
        f"{API}/services/{service}/env-vars/{nom}",
        data=json.dumps({"value": valeur}).encode(),
        headers=h,
        method="PUT",
    )
    try:
        urllib.request.urlopen(req, timeout=40).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"Render a refuse l'ecriture : HTTP {e.code}")


def relire(service: str, nom: str) -> str | None:
    h = {"Authorization": f"Bearer {cle_api()}", "Accept": "application/json"}
    req = urllib.request.Request(f"{API}/services/{service}/env-vars/{nom}", headers=h)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    except urllib.error.HTTPError:
        return None
    return (d.get("envVar", d)).get("value")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True, choices=sorted(SERVICES))
    p.add_argument("--name", required=True, help="nom de la variable")
    p.add_argument("--from-file", required=True, help="fichier contenant la valeur")
    p.add_argument("--apply", action="store_true", help="ecrire. Sans ce flag : simulation.")
    a = p.parse_args()

    service = SERVICES[a.env]
    valeur = lire_valeur(a.from_file)
    empreinte = hashlib.sha256(valeur.encode()).hexdigest()[:12]

    print(f"environnement : {a.env}  ({service})")
    print(f"variable      : {a.name}")
    print(f"longueur      : {len(valeur)}")
    print(f"sha256[:12]   : {empreinte}   (permet de verifier sans reveler)")

    if not a.apply:
        print("\nSIMULATION - aucune ecriture. Relancer avec --apply.")
        return 0

    if a.env == "prod":
        print("\nATTENTION : ecriture sur la PRODUCTION.")
        if os.environ.get("DEV_CONFIRM_PROD") != "oui":
            print("Refusee. Relancer avec DEV_CONFIRM_PROD=oui pour confirmer.")
            return 2

    poser(service, a.name, valeur)

    # Verification : jamais le contenu, seulement la concordance de l'empreinte.
    relu = relire(service, a.name)
    if relu is None:
        print("ERREUR : variable introuvable apres ecriture")
        return 1
    if hashlib.sha256(relu.encode()).hexdigest()[:12] != empreinte:
        print("ERREUR : la valeur relue ne correspond pas a celle ecrite")
        return 1

    print(f"\nOK : {a.name} posee sur {a.env} et relue a l'identique.")
    print("Elle ne sera effective qu'au prochain redemarrage du service.")
    print(f"Pensez a supprimer {a.from_file}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())