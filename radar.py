#!/usr/bin/env python3
"""RADAR : notre outil de veille en ligne de commande.

Usage (depuis le dossier radar) :
    ./radar collect        Mac / Linux
    .\\radar collect        Windows (PowerShell)
    python3 radar.py collect   partout

« collect » lit radar.config.yaml et remplit data/items.json.

Les sources et les mots-clés viennent UNIQUEMENT de radar.config.yaml.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

DOSSIER = Path(__file__).resolve().parent
FICHIER_CONFIG = DOSSIER / "radar.config.yaml"
FICHIER_ITEMS = DOSSIER / "data" / "items.json"

# La fiche d'une info (partie 3 du kit) : tous ces champs sont obligatoires.
CHAMPS_FICHE = ("titre", "url", "publie_le", "collecte_le", "source",
                "type_veille", "etiquettes", "fiabilite", "statut")
CHAMPS_TEXTE = ("titre", "url", "publie_le", "collecte_le", "source")  # chaînes non vides
CHAMPS_DATE = ("publie_le", "collecte_le")                              # AAAA-MM-JJ
# Les 4 types de veille du kit (prompt 3) ; null tant que la source ne le précise pas.
TYPES_VEILLE = ("technologique", "concurrentielle", "reglementaire", "securite")


class ErreurSource(Exception):
    """Une source n'a pas pu être lue (on passe à la suivante)."""


# --- Outils communs ---------------------------------------------------------

def charger_config():
    if not FICHIER_CONFIG.exists():
        sys.exit(f"❌ Plan de veille introuvable : {FICHIER_CONFIG}")
    with open(FICHIER_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def charger_items():
    """Relit data/items.json en appliquant les mêmes règles qu'aux nouvelles infos."""
    if not FICHIER_ITEMS.exists():
        return []
    try:
        with open(FICHIER_ITEMS, encoding="utf-8") as f:
            contenu = json.load(f)
    except json.JSONDecodeError as e:
        # On s'arrête plutôt que d'écraser un fichier qu'on n'a pas su lire.
        sys.exit(f"❌ {FICHIER_ITEMS} est illisible ({e}). Corrigez-le ou supprimez-le.")
    if not isinstance(contenu, list):
        sys.exit(f"❌ {FICHIER_ITEMS} doit contenir une liste de fiches.")

    items, urls, invalides, doublons = [], set(), 0, 0
    for fiche in contenu:
        if not fiche_valide(fiche):
            invalides += 1
        elif fiche["url"] in urls:
            doublons += 1
        else:
            items.append(fiche)
            urls.add(fiche["url"])
    if invalides:
        print(f"🧹 {invalides} fiche(s) retirée(s) de items.json : non conforme(s) à la fiche (partie 3 du kit)")
    if doublons:
        print(f"🧹 {doublons} doublon(s) retiré(s) de items.json (même url)")
    return items


def enregistrer_items(items):
    FICHIER_ITEMS.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER_ITEMS, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")


def gh_api(chemin):
    """Appelle l'API GitHub via « gh api » (connecté à votre compte : 5 000 requêtes/h)."""
    try:
        resultat = subprocess.run(
            ["gh", "api", chemin], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        raise ErreurSource("la commande « gh » n'est pas installée (https://cli.github.com)")
    except subprocess.CalledProcessError as e:
        raise ErreurSource(f"gh api a échoué : {e.stderr.strip()} (vérifiez « gh auth status »)")
    try:
        return json.loads(resultat.stdout)
    except json.JSONDecodeError:
        raise ErreurSource("gh api a renvoyé une réponse qui n'est pas du JSON")


def nouvelle_fiche(titre, url, publie_le, source, type_veille):
    """Une info au format de la fiche (partie 3 du kit)."""
    return {
        "titre": titre,
        "url": url,
        "publie_le": publie_le,
        "collecte_le": date.today().isoformat(),
        "source": source,
        "type_veille": type_veille,  # repris de la source dans la config
        "etiquettes": None,   # brique 4
        "fiabilite": None,    # brique 3
        "statut": None,       # brique 4
    }


def est_date_iso(valeur):
    """Vrai si valeur est une vraie date écrite AAAA-MM-JJ (« 2026-02-30 » est refusée)."""
    if not isinstance(valeur, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur):
        return False
    try:
        date.fromisoformat(valeur)
    except ValueError:
        return False
    return True


def fiche_valide(fiche):
    """Vérifie une fiche selon la partie 3 du kit.

    Règle d'or : jamais d'info sans url ni date de publication.
    """
    if not isinstance(fiche, dict):
        return False
    if any(champ not in fiche for champ in CHAMPS_FICHE):
        return False
    if any(not isinstance(fiche[champ], str) or not fiche[champ].strip() for champ in CHAMPS_TEXTE):
        return False
    if not re.fullmatch(r"https?://\S+", fiche["url"]):
        return False
    if not all(est_date_iso(fiche[champ]) for champ in CHAMPS_DATE):
        return False
    # Pas d'info publiée dans le futur. GitHub donne des dates UTC : on prend le plus
    # tardif entre « aujourd'hui » local et UTC, pour ne rien rejeter à tort selon le fuseau.
    aujourdhui = max(date.today(), datetime.now(timezone.utc).date())
    if date.fromisoformat(fiche["publie_le"]) > aujourdhui:
        return False
    if fiche["type_veille"] is not None and fiche["type_veille"] not in TYPES_VEILLE:
        return False
    # etiquettes, fiabilite et statut restent libres (null autorisé) : remplis aux briques 3 et 4.
    return True


def contient_un_mot(texte, mots):
    texte = (texte or "").lower()
    return any(mot.lower() in texte for mot in mots)


# --- Collecteurs : un par « type » de source dans la config -----------------

def collecter_releases(source):
    """Les versions publiées d'un dépôt GitHub (type: releases).

    Renvoie des paires (fiche, texte) : le texte (notes de version) sert
    seulement au filtrage par mots-clés, il n'est pas enregistré.
    """
    depot = source.get("depot")
    if not depot:
        raise ErreurSource("champ « depot » manquant dans la config")
    # Le nom affiché dans le champ « source » vient de la config, jamais du code.
    nom_source = source.get("nom")
    if not isinstance(nom_source, str) or not nom_source.strip():
        raise ErreurSource("champ « nom » manquant dans la config : aucune fiche créée pour cette source")
    limite = source.get("limite", 10)
    produit = source.get("produit", depot)

    fiches = []
    for release in gh_api(f"repos/{depot}/releases?per_page={limite}"):
        publie_le = release.get("published_at")  # vide pour un brouillon
        fiche = nouvelle_fiche(
            titre=f"{produit} {release.get('tag_name')}",
            url=release.get("html_url"),
            publie_le=publie_le[:10] if publie_le else None,
            source=nom_source,
            type_veille=source.get("type_veille"),
        )
        fiches.append((fiche, release.get("body") or ""))
    return fiches


# Pour ajouter une source : écrire collecter_xxx(source) et l'inscrire ici.
COLLECTEURS = {
    "releases": collecter_releases,
}


# --- Commandes --------------------------------------------------------------

def commande_collect(args):
    config = charger_config()
    mots_cles = config.get("mots_cles") or []
    ignorer = config.get("ignorer") or []
    if not mots_cles:
        sys.exit("❌ La liste « mots_cles » de radar.config.yaml est vide : rien ne déclencherait de capture.")
    items = charger_items()
    urls_connues = {item["url"] for item in items}
    total_nouvelles = 0
    non_collectees = []

    for source in config.get("sources") or []:
        type_source = source.get("type")
        libelle = source.get("depot") or source.get("requete") or source.get("paquet") or source.get("url")
        collecteur = COLLECTEURS.get(type_source)
        if collecteur is None:
            print(f"⚠️  {type_source} · {libelle} : NON COLLECTÉE (collecteur « {type_source} » pas encore écrit)")
            non_collectees.append(f"{type_source} · {libelle}")
            continue

        try:
            fiches = collecteur(source)
        except ErreurSource as e:
            print(f"❌ {type_source} · {libelle} : {e}")
            non_collectees.append(f"{type_source} · {libelle}")
            continue

        nouvelles = rejetees = hors_sujet = ignorees = 0
        for fiche, texte in fiches:
            contenu = f"{fiche['titre']} {texte}"
            if not fiche_valide(fiche):
                rejetees += 1
            elif not contient_un_mot(contenu, mots_cles):
                hors_sujet += 1
            elif contient_un_mot(contenu, ignorer):
                ignorees += 1
            elif fiche["url"] not in urls_connues:
                items.append(fiche)
                urls_connues.add(fiche["url"])
                nouvelles += 1

        detail = f"{len(fiches)} lues, {nouvelles} nouvelles"
        if rejetees:
            detail += f", {rejetees} rejetées (fiche non conforme : url, dates, type_veille ou champs manquants)"
        if hors_sujet:
            detail += f", {hors_sujet} sans aucun mot-clé"
        if ignorees:
            detail += f", {ignorees} ignorées (liste « ignorer »)"
        print(f"✅ {type_source} · {libelle} : {detail}")
        total_nouvelles += nouvelles

    items.sort(key=lambda item: item["publie_le"], reverse=True)
    enregistrer_items(items)
    print(f"\n{total_nouvelles} nouvelles infos · {len(items)} au total dans {FICHIER_ITEMS.relative_to(DOSSIER)}")
    if non_collectees:
        print(f"⚠️  {len(non_collectees)} source(s) du plan non collectée(s) : {', '.join(non_collectees)}")


def main():
    parser = argparse.ArgumentParser(prog="radar", description="RADAR : notre outil de veille.")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("collect", help="collecte les infos des sources de radar.config.yaml")

    args = parser.parse_args()
    if args.commande == "collect":
        commande_collect(args)


if __name__ == "__main__":
    main()
