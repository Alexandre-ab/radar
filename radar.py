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
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

import yaml

DOSSIER = Path(__file__).resolve().parent
FICHIER_CONFIG = DOSSIER / "radar.config.yaml"
FICHIER_ITEMS = DOSSIER / "data" / "items.json"
FICHIER_PAGES = DOSSIER / "data" / "pages.json"  # empreintes des pages suivies (type: page)

# Adresses des API publiques utilisées par les collecteurs (le « comment » ;
# le « quoi » — requêtes, paquets, pages — vient de radar.config.yaml).
API_HACKERNEWS = "https://hn.algolia.com/api/v1/search_by_date"
PAGE_HACKERNEWS = "https://news.ycombinator.com/item?id={id}"
API_OSV = "https://api.osv.dev/v1/query"
PAGE_OSV = "https://osv.dev/vulnerability/{id}"
AGENT_HTTP = "radar-veille/1.0 (outil de veille, formation)"
DELAI_HTTP = 20  # secondes

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
    try:
        with open(FICHIER_CONFIG, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        sys.exit(f"❌ {FICHIER_CONFIG.name} est mal formé (YAML) :\n{e}")
    if config is None:
        config = {}
    if not isinstance(config, dict):
        sys.exit(f"❌ {FICHIER_CONFIG.name} doit contenir des rubriques « clé: valeur » (axes, mots_cles, sources…).")
    sources = config.get("sources") or []
    if not isinstance(sources, list) or not all(isinstance(s, dict) for s in sources):
        sys.exit(f"❌ Dans {FICHIER_CONFIG.name}, « sources » doit être une liste de sources {{ type: …, nom: … }}.")
    return config


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


def http(url, donnees=None):
    """GET (ou POST JSON si donnees est fourni) avec la bibliothèque standard.

    Renvoie (texte, entetes). Toute panne réseau ou HTTP devient une ErreurSource.
    """
    entetes = {"User-Agent": AGENT_HTTP}
    corps = None
    if donnees is not None:
        corps = json.dumps(donnees).encode("utf-8")
        entetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(url, data=corps, headers=entetes)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_HTTP) as reponse:
            brut = reponse.read()
            jeu = reponse.headers.get_content_charset() or "utf-8"
            return brut.decode(jeu, errors="replace"), reponse.headers
    except urllib.error.HTTPError as e:
        raise ErreurSource(f"le serveur a répondu HTTP {e.code} pour {url}")
    except (urllib.error.URLError, OSError) as e:
        raise ErreurSource(f"impossible de joindre {url} ({e})")


def http_json(url, donnees=None):
    texte, _ = http(url, donnees)
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        raise ErreurSource(f"{url} a renvoyé une réponse qui n'est pas du JSON")


def liste_d_objets(valeur, quoi):
    """Vérifie qu'une réponse d'API est bien une liste de dictionnaires."""
    if not isinstance(valeur, list) or not all(isinstance(element, dict) for element in valeur):
        raise ErreurSource(f"réponse inattendue de {quoi} (une liste d'objets était attendue)")
    return valeur


class _TexteVisible(HTMLParser):
    """Garde le texte lisible d'une page HTML (sans scripts ni styles) et son <title>."""
    INVISIBLES = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__()
        self.morceaux, self.titre, self._cache, self._dans_titre = [], "", 0, False

    def handle_starttag(self, balise, attributs):
        if balise in self.INVISIBLES:
            self._cache += 1
        elif balise == "title":
            self._dans_titre = True

    def handle_endtag(self, balise):
        if balise in self.INVISIBLES and self._cache:
            self._cache -= 1
        elif balise == "title":
            self._dans_titre = False

    def handle_data(self, donnees):
        if self._dans_titre:
            self.titre += donnees
        elif not self._cache:
            self.morceaux.append(donnees)


def texte_visible(html):
    """Renvoie (titre, texte) d'une page, espaces normalisés."""
    lecteur = _TexteVisible()
    lecteur.feed(html)
    return " ".join(lecteur.titre.split()), " ".join(" ".join(lecteur.morceaux).split())


def charger_pages():
    if not FICHIER_PAGES.exists():
        return {}
    try:
        with open(FICHIER_PAGES, encoding="utf-8") as f:
            pages = json.load(f)
    except json.JSONDecodeError:
        return {}  # un cache abîmé se reconstruit à la prochaine lecture
    return pages if isinstance(pages, dict) else {}


def enregistrer_pages(pages):
    FICHIER_PAGES.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER_PAGES, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
        f.write("\n")


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


def aujourdhui():
    """Les API donnent des dates UTC : on prend le plus tardif entre « aujourd'hui »
    local et UTC, pour ne rien rejeter à tort selon le fuseau horaire."""
    return max(date.today(), datetime.now(timezone.utc).date())


def jour(horodatage):
    """« 2026-10-27T20:24:20Z » → « 2026-10-27 » (None si absent)."""
    return horodatage[:10] if isinstance(horodatage, str) and horodatage else None


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
    # Ni publiée ni collectée dans le futur.
    if any(date.fromisoformat(fiche[champ]) > aujourdhui() for champ in CHAMPS_DATE):
        return False
    if fiche["type_veille"] is not None and fiche["type_veille"] not in TYPES_VEILLE:
        return False
    # etiquettes, fiabilite et statut restent libres (null autorisé) : remplis aux briques 3 et 4.
    return True


def contient_un_mot(texte, mots):
    texte = (texte or "").lower()
    return any(mot.lower() in texte for mot in mots)


# --- Collecteurs : un par « type » de source dans la config -----------------

def valider_source(source, *champs):
    """Contrôle une source de la config AVANT tout appel réseau ; renvoie sa limite.

    « nom » et les champs demandés doivent être des textes non vides : le nom affiché
    dans le champ « source » vient de la config, jamais du code.
    """
    for champ in ("nom",) + champs:
        valeur = source.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            raise ErreurSource(f"champ « {champ} » manquant dans la config : aucune fiche créée pour cette source")
    type_veille = source.get("type_veille")
    if type_veille is not None and type_veille not in TYPES_VEILLE:
        raise ErreurSource(f"type_veille « {type_veille} » inconnu (attendu : {', '.join(TYPES_VEILLE)})")
    limite = source.get("limite", 10)
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 100:
        raise ErreurSource(f"limite « {limite} » invalide (un nombre entier entre 1 et 100)")
    return limite


def date_last_modified(valeur):
    """En-tête HTTP « Last-Modified » → AAAA-MM-JJ (None si absent ou illisible)."""
    try:
        return parsedate_to_datetime(valeur).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


# --- Collecteurs : un par « type » de source dans la config -----------------
# Chacun renvoie des paires (fiche, texte) : le texte sert seulement au filtrage
# par mots-clés, il n'est pas enregistré.

def collecter_releases(source):
    """Les versions publiées d'un dépôt GitHub (type: releases), via gh api."""
    limite = valider_source(source, "depot")
    depot = source["depot"]
    produit = source.get("produit", depot)

    releases = liste_d_objets(gh_api(f"repos/{depot}/releases?per_page={limite}"), "GitHub")
    fiches = []
    for release in releases:
        fiche = nouvelle_fiche(
            titre=f"{produit} {release.get('tag_name')}",
            url=release.get("html_url"),
            publie_le=jour(release.get("published_at")),  # vide pour un brouillon
            source=source["nom"],
            type_veille=source.get("type_veille"),
        )
        fiches.append((fiche, release.get("body") or ""))
    return fiches


def collecter_hackernews(source):
    """Les derniers articles Hacker News d'une recherche (type: hackernews, API Algolia)."""
    limite = valider_source(source, "requete")
    parametres = urllib.parse.urlencode({"query": source["requete"], "tags": "story", "hitsPerPage": limite})
    reponse = http_json(f"{API_HACKERNEWS}?{parametres}")
    if not isinstance(reponse, dict):
        raise ErreurSource("réponse inattendue de Hacker News")

    fiches = []
    for article in liste_d_objets(reponse.get("hits"), "Hacker News"):
        url = article.get("url")
        if not url and article.get("objectID"):
            url = PAGE_HACKERNEWS.format(id=article["objectID"])  # « Ask HN » : pas de lien externe
        fiche = nouvelle_fiche(
            titre=article.get("title"),
            url=url,
            publie_le=jour(article.get("created_at")),
            source=source["nom"],
            type_veille=source.get("type_veille"),
        )
        fiches.append((fiche, article.get("story_text") or ""))
    return fiches


def collecter_failles(source):
    """Les failles connues d'un paquet dans la base OSV (type: failles)."""
    limite = valider_source(source, "paquet", "ecosysteme")
    requete = {"package": {"name": source["paquet"], "ecosystem": source["ecosysteme"]}}
    version = source.get("version")
    if version is not None:
        if not isinstance(version, str) or not version.strip():
            raise ErreurSource('champ « version » invalide : écrivez-le entre guillemets, ex. "1.2.3"')
        requete["version"] = version  # sans version : toutes les failles connues du paquet
    reponse = http_json(API_OSV, requete)
    if not isinstance(reponse, dict):
        raise ErreurSource("réponse inattendue de la base OSV")

    failles = liste_d_objets(reponse.get("vulns", []), "la base OSV")  # {} = aucune faille connue
    failles = sorted(failles, key=lambda f: str(f.get("published") or ""), reverse=True)[:limite]
    fiches = []
    for faille in failles:
        ident = faille.get("id")
        url = PAGE_OSV.format(id=urllib.parse.quote(ident)) if isinstance(ident, str) and ident else None
        alias = [a for a in faille.get("aliases") or [] if isinstance(a, str)]
        fiche = nouvelle_fiche(
            titre=f"{source['paquet']} · {ident} : {faille.get('summary') or 'faille sans résumé'}",
            url=url,
            publie_le=jour(faille.get("published")),
            source=source["nom"],
            type_veille=source.get("type_veille"),
        )
        fiches.append((fiche, " ".join([faille.get("details") or ""] + alias)))
    return fiches


def collecter_page(source):
    """Une page suivie, par exemple des CGU (type: page) : une fiche par version de son texte.

    L'empreinte SHA-256 du texte visible est gardée dans data/pages.json, et l'url de la
    fiche la porte (#empreinte-…) : une nouvelle version donne une nouvelle fiche, la même
    version n'est jamais ajoutée deux fois.
    publie_le = en-tête « Last-Modified » du serveur s'il existe, sinon le jour où cette
    version a été vue pour la première fois : jamais une date inventée.
    """
    valider_source(source, "url")
    url = urllib.parse.urldefrag(source["url"]).url
    if not re.fullmatch(r"https?://\S+", url):
        raise ErreurSource(f"url « {url} » invalide (http:// ou https:// attendu)")
    html, entetes = http(url)
    titre_page, texte = texte_visible(html)
    if not texte:
        raise ErreurSource("page vide, ou lisible seulement avec un navigateur (JavaScript)")
    empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()

    pages = charger_pages()
    connue = pages.get(url) if isinstance(pages.get(url), dict) else {}
    if connue.get("empreinte") == empreinte and est_date_iso(connue.get("vue_le")):
        vue_le = connue["vue_le"]           # même version : on garde sa date de 1re lecture
    else:
        vue_le = date.today().isoformat()   # nouvelle version (ou 1re lecture)
    publie_le = date_last_modified(entetes.get("Last-Modified")) or vue_le
    pages[url] = {
        "empreinte": empreinte,
        "vue_le": vue_le,
        "verifiee_le": date.today().isoformat(),
        "last_modified": entetes.get("Last-Modified"),
    }
    enregistrer_pages(pages)

    fiche = nouvelle_fiche(
        titre=f"{titre_page or source['nom']} (version du {publie_le})",
        url=f"{url}#empreinte-{empreinte[:12]}",
        publie_le=publie_le,
        source=source["nom"],
        type_veille=source.get("type_veille"),
    )
    return [(fiche, texte)]


# Pour ajouter une source : écrire collecter_xxx(source) et l'inscrire ici.
COLLECTEURS = {
    "releases": collecter_releases,
    "hackernews": collecter_hackernews,
    "failles": collecter_failles,
    "page": collecter_page,
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
