#!/usr/bin/env python3
"""RADAR : notre outil de veille en ligne de commande.

Usage (depuis le dossier radar) :
    ./radar collect        Mac / Linux
    .\\radar collect        Windows (PowerShell)
    python3 radar.py collect   partout

« collect » lit radar.config.yaml et remplit data/items.json.
« score »   calcule le champ « fiabilite » de chaque info (rubrique regles_score)
            et affiche le top 10 (« score --top 20 » pour en voir plus) ;
            il pose aussi les étiquettes et le statut (retenue / ecartee).
« search »  retrouve les infos par un mot du titre ou des étiquettes
            (« search <mot> --retenues » : seulement les retenues).
« decide »  compare les 2 options de la rubrique decision (chiffres bruts via gh api)
            et écrit decision.md.

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
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

import yaml

DOSSIER = Path(__file__).resolve().parent
FICHIER_CONFIG = DOSSIER / "radar.config.yaml"
FICHIER_ITEMS = DOSSIER / "data" / "items.json"
FICHIER_PAGES = DOSSIER / "data" / "pages.json"  # empreintes des pages suivies (type: page)
FICHIER_DECISION = DOSSIER / "decision.md"      # écrit par « radar decide »

# Adresses des API publiques utilisées par les collecteurs (le « comment » ;
# le « quoi » — requêtes, paquets, pages — vient de radar.config.yaml).
API_HACKERNEWS = "https://hn.algolia.com/api/v1/search_by_date"
PAGE_HACKERNEWS = "https://news.ycombinator.com/item?id={id}"
API_OSV = "https://api.osv.dev/v1/query"
PAGE_OSV = "https://osv.dev/vulnerability/{id}"
PAGE_GITHUB = "https://github.com/{depot}"
AGENT_HTTP = "radar-veille/1.0 (outil de veille, formation)"
DELAI_HTTP = 20  # secondes

# La fiche d'une info (partie 3 du kit) : tous ces champs sont obligatoires.
CHAMPS_FICHE = ("titre", "url", "publie_le", "collecte_le", "source",
                "type_veille", "etiquettes", "fiabilite", "statut")
CHAMPS_TEXTE = ("titre", "url", "publie_le", "collecte_le", "source")  # chaînes non vides
CHAMPS_DATE = ("publie_le", "collecte_le")                              # AAAA-MM-JJ
# Les 4 types de veille du kit (prompt 3) ; null tant que la source ne le précise pas.
TYPES_VEILLE = ("technologique", "concurrentielle", "reglementaire", "securite")
# Les 4 catégories de source du kit (prompt 2). Leurs points sont dans regles_score.
CATEGORIES = ("officielle", "institution", "communaute", "social")
# Le schéma de regles_score : les règles du kit, obligatoires, et les conditions comprises
# par les règles à cas (si:). Les points, délais et mots viennent tous de la config.
REGLES_OBLIGATOIRES = ("categorie", "fraicheur", "auteur_identifie",
                       "source_ou_methode_citee", "recoupee", "biais_interet")
CONDITIONS = ("sources", "categories", "types_veille", "domaines",
              "url_contient", "titre_contient", "titre_sans")
# Les 2 statuts du kit (prompt 3), posés par « radar score » selon le seuil de la config.
STATUTS = ("retenue", "ecartee")
# Le schéma de la rubrique decision (prompt 4 et partie 5 du kit) : 2 options, les 7 critères,
# l'échelle des poids et des notes, les rubriques d'impact. Les valeurs viennent de la config.
NOMBRE_OPTIONS = 2
CRITERES_KIT = ("maturite", "dynamisme", "licence", "maintenance", "cout_total", "apprentissage", "reversibilite")
POIDS_POSSIBLES = (1, 3)
NOTES_POSSIBLES = (1, 5)
CHAMPS_IMPACT = (("perimetre", "Périmètre"), ("budget", "Budget"), ("delais", "Délais"),
                 ("anticipation", "Anticipation"))
PAR_PAGE_GH, PAGES_GH_MAX = 100, 50  # listes gh api : 100 par page, au plus 50 pages


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
    if not resultat.stdout.strip():
        return None  # réponse vide (HTTP 204), ex. la liste des contributeurs d'un dépôt vide
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
    # fiabilite : null tant que « radar score » n'est pas passé, sinon un nombre entier.
    if fiche["fiabilite"] is not None and not est_entier(fiche["fiabilite"]):
        return False
    # etiquettes : null avant « radar collect / score », sinon une liste de textes (vide possible).
    etiquettes = fiche["etiquettes"]
    if etiquettes is not None and (not isinstance(etiquettes, list)
                                   or not all(isinstance(e, str) and e.strip() for e in etiquettes)):
        return False
    # statut : null avant « radar score », sinon retenue ou ecartee.
    if fiche["statut"] is not None and fiche["statut"] not in STATUTS:
        return False
    return True


def est_entier(valeur):
    """Vrai pour 3 ou -2, faux pour True, 2.5 ou « 3 » (en Python, True est aussi un int)."""
    return isinstance(valeur, int) and not isinstance(valeur, bool)


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
    if type_veille not in TYPES_VEILLE:
        raise ErreurSource(f"type_veille « {type_veille} » manquant ou inconnu (attendu : {', '.join(TYPES_VEILLE)})")
    if source.get("categorie") not in CATEGORIES:
        raise ErreurSource(f"categorie « {source.get('categorie')} » manquante ou inconnue "
                           f"(attendu : {', '.join(CATEGORIES)})")
    limite = source.get("limite", 10)
    if not est_entier(limite) or not 1 <= limite <= 100:
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
    """Les derniers articles d'une recherche (type: hackernews, via l'API Algolia)."""
    limite = valider_source(source, "requete")
    parametres = urllib.parse.urlencode({"query": source["requete"], "tags": "story", "hitsPerPage": limite})
    reponse = http_json(f"{API_HACKERNEWS}?{parametres}")
    if not isinstance(reponse, dict):
        raise ErreurSource("réponse inattendue de l'API Algolia")

    fiches = []
    for article in liste_d_objets(reponse.get("hits"), "l'API Algolia"):
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


# --- Score de fiabilité (brique 3) ------------------------------------------
# Toutes les règles, points et listes de mots viennent de « regles_score » dans la config.

def est_texte(valeur):
    return isinstance(valeur, str) and bool(valeur.strip())


def liste_de_textes(valeur):
    return isinstance(valeur, list) and bool(valeur) and all(est_texte(v) for v in valeur)


def cas_de(regle):
    """« si » accepte un seul cas (dictionnaire) ou une liste de cas."""
    cas = regle.get("si")
    return [cas] if isinstance(cas, dict) else cas


def erreurs_regle(nom, regle):
    """Liste les erreurs d'écriture d'une règle de regles_score (vide si tout va bien)."""
    if not isinstance(regle, dict):
        return ["doit être une rubrique « clé: valeur »"]
    if nom == "categorie":
        return ([f"points de « {c} » manquants ou non entiers" for c in CATEGORIES if not est_entier(regle.get(c))]
                + [f"catégorie « {c} » inconnue" for c in regle if c not in CATEGORIES])

    erreurs = []
    if not est_entier(regle.get("points")):
        erreurs.append("« points » doit être un nombre entier")
    if "libelle" in regle and not est_texte(regle["libelle"]):
        erreurs.append("« libelle » doit être un texte")
    if nom == "fraicheur":
        if not est_entier(regle.get("jours")) or regle["jours"] < 1:
            erreurs.append("« jours » doit être un nombre entier positif")
    elif nom == "recoupee":
        if not liste_de_textes(regle.get("sujets")):
            erreurs.append("« sujets » doit être une liste de textes")
    else:
        erreurs += erreurs_cas(regle)
    return erreurs


def erreurs_cas(regle):
    """Vérifie le « si » d'une règle ou d'une étiquette : au moins un cas, conditions connues."""
    cas = cas_de(regle)
    if not isinstance(cas, list) or not cas:
        return ["« si » doit contenir au moins un cas"]
    erreurs = []
    for numero, un_cas in enumerate(cas, 1):
        if not isinstance(un_cas, dict) or not un_cas:
            erreurs.append(f"cas n°{numero} vide ou mal écrit")
            continue
        for condition, valeurs in un_cas.items():
            if condition not in CONDITIONS:
                erreurs.append(f"cas n°{numero} : condition « {condition} » inconnue "
                               f"(possibles : {', '.join(CONDITIONS)})")
            elif not liste_de_textes(valeurs):
                erreurs.append(f"cas n°{numero} : « {condition} » doit être une liste de textes")
            elif condition == "categories" and any(v not in CATEGORIES for v in valeurs):
                erreurs.append(f"cas n°{numero} : « categories » n'accepte que {', '.join(CATEGORIES)}")
            elif condition == "types_veille" and any(v not in TYPES_VEILLE for v in valeurs):
                erreurs.append(f"cas n°{numero} : « types_veille » n'accepte que {', '.join(TYPES_VEILLE)}")
    return erreurs


def lire_regles(config):
    """Valide regles_score et la categorie des sources ; renvoie (regles, categorie_par_source).

    Toutes les erreurs sont listées d'un coup, puis la commande s'arrête.
    """
    erreurs, categorie_par_source = [], {}
    for source in config.get("sources") or []:
        nom, categorie = source.get("nom"), source.get("categorie")
        if not est_texte(nom):
            erreurs.append(f"une source {source.get('type')} n'a pas de « nom »")
        elif categorie not in CATEGORIES:
            erreurs.append(f"source « {nom} » : categorie « {categorie} » manquante ou inconnue "
                           f"(attendu : {', '.join(CATEGORIES)})")
        elif categorie_par_source.get(nom, categorie) != categorie:
            erreurs.append(f"deux sources s'appellent « {nom} » mais n'ont pas la même categorie "
                           f"({categorie_par_source[nom]} et {categorie})")
        else:
            categorie_par_source[nom] = categorie

    regles = config.get("regles_score")
    if not isinstance(regles, dict):
        erreurs.append("la rubrique « regles_score » est absente")
        regles = {}
    erreurs += [f"la règle « {nom} » est absente de regles_score" for nom in REGLES_OBLIGATOIRES if nom not in regles]
    for nom, regle in regles.items():
        erreurs += [f"regles_score › {nom} : {erreur}" for erreur in erreurs_regle(nom, regle)]
    if erreurs:
        sys.exit(f"❌ {FICHIER_CONFIG.name} : le score ne peut pas être calculé.\n"
                 + "\n".join(f"   - {erreur}" for erreur in erreurs))
    return regles, categorie_par_source


def premier_present(texte, valeurs):
    texte = texte.lower()
    return next((v for v in valeurs if v.lower() in texte), None)


def condition_vraie(condition, valeurs, fiche, categorie):
    """L'explication lisible si la condition est vraie pour cette fiche, sinon None."""
    if condition == "sources":
        return f"source « {fiche['source']} »" if fiche["source"] in valeurs else None
    if condition == "categories":
        return f"source {categorie}" if categorie in valeurs else None
    if condition == "types_veille":
        return f"veille {fiche['type_veille']}" if fiche["type_veille"] in valeurs else None
    if condition == "domaines":
        hote = (urllib.parse.urlsplit(fiche["url"]).hostname or "").lower()
        trouve = next((d for d in valeurs if hote == d.lower() or hote.endswith("." + d.lower())), None)
        return f"site {trouve}" if trouve else None
    if condition == "url_contient":
        trouve = premier_present(fiche["url"], valeurs)
        return f"« {trouve} » dans l'url" if trouve else None
    if condition == "titre_contient":
        trouve = premier_present(fiche["titre"], valeurs)
        return f"« {trouve} » dans le titre" if trouve else None
    if condition == "titre_sans":
        if premier_present(fiche["titre"], valeurs) is not None:
            return None
        return "titre sans " + ", ".join(f"« {v} »" for v in valeurs)
    return None


def explication_regle(regle, fiche, categorie):
    """Le premier cas vrai de la règle (ses conditions reliées par « et »), sinon None."""
    for un_cas in cas_de(regle):
        explications = [condition_vraie(c, v, fiche, categorie) for c, v in un_cas.items()]
        if all(explications):
            return " et ".join(explications)
    return None


def calculer_recoupements(items, sujets):
    """url → noms des AUTRES sources dont un titre partage au moins un sujet avec cette info."""
    sujets_par_url, sources_par_sujet = {}, {}
    for item in items:
        trouves = {s.lower() for s in sujets if s.lower() in item["titre"].lower()}
        sujets_par_url[item["url"]] = trouves
        for sujet in trouves:
            sources_par_sujet.setdefault(sujet, set()).add(item["source"])
    return {item["url"]: set().union(*(sources_par_sujet[s] for s in sujets_par_url[item["url"]]))
            - {item["source"]} for item in items}


def libelle_de(nom, regle):
    return regle.get("libelle") or nom.replace("_", " ")


def scorer(fiche, regles, categorie_par_source, recoupements, ref):
    """Renvoie (total, raisons) ; raisons = [(points, phrase), …] dans l'ordre de la config."""
    categorie = categorie_par_source.get(fiche["source"])
    raisons = []
    for nom, regle in regles.items():
        if nom == "categorie":
            if categorie is None:
                raisons.append((0, "catégorie inconnue : source absente du plan de veille"))
            else:
                raisons.append((regle[categorie], f"source {categorie}"))
        elif nom == "fraicheur":
            age = (ref - date.fromisoformat(fiche["publie_le"])).days
            if age < regle["jours"]:
                quand = ("aujourd'hui" if age == 0 else
                         f"il y a {age} jour" + ("s" if age > 1 else ""))
                raisons.append((regle["points"],
                                f"{libelle_de(nom, regle)} : publiée {quand} (moins de {regle['jours']} jours)"))
        elif nom == "recoupee":
            autres = recoupements.get(fiche["url"])
            if autres:
                raisons.append((regle["points"], f"{libelle_de(nom, regle)} par {', '.join(sorted(autres))}"))
        else:
            explication = explication_regle(regle, fiche, categorie)
            if explication:
                raisons.append((regle["points"], f"{libelle_de(nom, regle)} ({explication})"))
    return sum(points for points, _ in raisons), raisons


def en_points(n):
    return f"{n} point" + ("s" if abs(n) > 1 else "")


# --- Archive : étiquettes et statut (brique 4) ------------------------------
# Les étiquettes possibles, leurs conditions et le seuil viennent tous de la config.

def erreurs_etiquettes(config):
    """Renvoie (etiquettes, erreurs) ; etiquettes = {nom: {si: …}} dans l'ordre de la config."""
    etiquettes = config.get("etiquettes")
    if not isinstance(etiquettes, dict) or not etiquettes:
        return {}, ["la rubrique « etiquettes » est absente ou vide"]
    erreurs = []
    for nom, etiquette in etiquettes.items():
        if not est_texte(nom):
            erreurs.append(f"etiquettes : le nom « {nom} » doit être un texte")
        elif not isinstance(etiquette, dict):
            erreurs.append(f"etiquettes › {nom} : doit contenir « si: » et ses cas")
        else:
            erreurs += [f"etiquettes › {nom} : {erreur}" for erreur in erreurs_cas(etiquette)]
    return etiquettes, erreurs


def arreter(quoi, erreurs):
    sys.exit(f"❌ {FICHIER_CONFIG.name} : {quoi}\n" + "\n".join(f"   - {erreur}" for erreur in erreurs))


def lire_etiquettes(config):
    etiquettes, erreurs = erreurs_etiquettes(config)
    if erreurs:
        arreter("les étiquettes ne peuvent pas être posées.", erreurs)
    return etiquettes


def lire_archivage(config):
    """Valide seuil, etiquettes et le type_veille des sources.

    Renvoie (seuil, etiquettes, type_veille_par_source) ; deux sources de même nom
    doivent avoir le même type_veille, puisque la fiche ne garde que le nom.
    """
    etiquettes, erreurs = erreurs_etiquettes(config)
    seuil = config.get("seuil")
    if not est_entier(seuil):
        erreurs.append("« seuil » doit être un nombre entier (ex. seuil: 4)")
    type_veille_par_source = {}
    for source in config.get("sources") or []:
        nom, type_veille = source.get("nom"), source.get("type_veille")
        if not est_texte(nom):
            continue  # déjà signalé par lire_regles
        if type_veille not in TYPES_VEILLE:
            erreurs.append(f"source « {nom} » : type_veille « {type_veille} » manquant ou inconnu "
                           f"(attendu : {', '.join(TYPES_VEILLE)})")
        elif type_veille_par_source.get(nom, type_veille) != type_veille:
            erreurs.append(f"deux sources s'appellent « {nom} » mais n'ont pas le même type_veille "
                           f"({type_veille_par_source[nom]} et {type_veille})")
        else:
            type_veille_par_source[nom] = type_veille
    if erreurs:
        arreter("l'archivage (étiquettes, statut) est impossible.", erreurs)
    return seuil, etiquettes, type_veille_par_source


def attribuer_etiquettes(fiche, etiquettes, categorie):
    """Les étiquettes de la config dont un cas est vrai pour cette fiche (ordre de la config)."""
    return [nom for nom, etiquette in etiquettes.items() if explication_regle(etiquette, fiche, categorie)]


def decrire_archivage(item):
    """« <statut> · étiquettes : <étiquette>, <étiquette> », lisible même avant « radar score »."""
    statut = item["statut"] or "statut à calculer (radar score)"
    if item["etiquettes"] is None:
        etiquettes = "étiquettes à calculer"
    elif item["etiquettes"]:
        etiquettes = "étiquettes : " + ", ".join(item["etiquettes"])
    else:
        etiquettes = "aucune étiquette"
    return f"{statut} · {etiquettes}"


# --- Décision (brique 5) -----------------------------------------------------
# Options, dépôts, critères, poids, notes, chiffres et impact viennent tous de la
# rubrique « decision » de la config ; seuls les chiffres bruts sont relevés en direct.

def dans_echelle(valeur, echelle):
    return est_entier(valeur) and echelle[0] <= valeur <= echelle[1]


def erreurs_options(options):
    if not isinstance(options, dict) or len(options) != NOMBRE_OPTIONS:
        return [f"« options » doit contenir exactement {NOMBRE_OPTIONS} options"]
    erreurs, champs_impact = [], [cle for cle, _ in CHAMPS_IMPACT]
    for ident, option in options.items():
        prefixe = f"options › {ident}"
        if not isinstance(option, dict):
            erreurs.append(f"{prefixe} : doit contenir « nom » et « depot »")
            continue
        if not est_texte(option.get("nom")):
            erreurs.append(f"{prefixe} : « nom » doit être un texte")
        if not isinstance(option.get("depot"), str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", option["depot"]):
            erreurs.append(f"{prefixe} : « depot » doit s'écrire propriétaire/nom (dépôt GitHub)")
        impact = option.get("impact")
        if impact is not None and not isinstance(impact, dict):
            erreurs.append(f"{prefixe} › impact : doit contenir {', '.join(champs_impact)}")
        for cle, texte in (impact.items() if isinstance(impact, dict) else []):
            if cle not in champs_impact:
                erreurs.append(f"{prefixe} › impact : « {cle} » inconnu (possibles : {', '.join(champs_impact)})")
            elif not est_texte(texte):
                erreurs.append(f"{prefixe} › impact › {cle} : doit être un texte")
    return erreurs


def erreurs_note(prefixe, note):
    if not isinstance(note, dict):
        return [f"{prefixe} : doit contenir note, chiffre, source et date"]
    erreurs = []
    if not dans_echelle(note.get("note"), NOTES_POSSIBLES):
        erreurs.append(f"{prefixe} : « note » doit être un entier de {NOTES_POSSIBLES[0]} à {NOTES_POSSIBLES[1]}")
    if not est_texte(note.get("chiffre")):
        erreurs.append(f"{prefixe} : « chiffre » doit donner le chiffre réel qui justifie la note")
    if not isinstance(note.get("source"), str) or not re.fullmatch(r"https?://\S+", note["source"]):
        erreurs.append(f"{prefixe} : « source » doit être une url http(s)")
    if not est_date_iso(note.get("date")) or date.fromisoformat(note["date"]) > aujourdhui():
        erreurs.append(f'{prefixe} : « date » = jour de consultation de la source, '
                       f'AAAA-MM-JJ entre guillemets (ex. "2026-10-28"), pas dans le futur')
    return erreurs


def erreurs_criteres(criteres, options):
    if not isinstance(criteres, dict):
        return ["« criteres » doit contenir les critères de la matrice"]
    erreurs = [f"le critère « {nom} » du kit est absent de « criteres »" for nom in CRITERES_KIT if nom not in criteres]
    # La matrice du kit a exactement ces 7 critères : un critère en plus fausserait les totaux.
    erreurs += [f"critère « {nom} » inconnu (possibles : {', '.join(CRITERES_KIT)})"
                for nom in criteres if nom not in CRITERES_KIT]
    for nom, critere in criteres.items():
        if nom not in CRITERES_KIT:
            continue
        prefixe = f"criteres › {nom}"
        if not isinstance(critere, dict):
            erreurs.append(f"{prefixe} : doit contenir poids et notes")
            continue
        if "libelle" in critere and not est_texte(critere["libelle"]):
            erreurs.append(f"{prefixe} : « libelle » doit être un texte")
        if not dans_echelle(critere.get("poids"), POIDS_POSSIBLES):
            erreurs.append(f"{prefixe} : « poids » doit être un entier de {POIDS_POSSIBLES[0]} à {POIDS_POSSIBLES[1]}")
        if "note_eliminatoire" in critere and not dans_echelle(critere["note_eliminatoire"], NOTES_POSSIBLES):
            erreurs.append(f"{prefixe} : « note_eliminatoire » doit être une note de "
                           f"{NOTES_POSSIBLES[0]} à {NOTES_POSSIBLES[1]}")
        notes = critere.get("notes")
        if not isinstance(notes, dict):
            erreurs.append(f"{prefixe} : « notes » doit donner une note par option")
            continue
        erreurs += [f"{prefixe} : pas de note pour l'option « {ident} »" for ident in options if ident not in notes]
        erreurs += [f"{prefixe} : option « {ident} » inconnue" for ident in notes if ident not in options]
        for ident, note in notes.items():
            if ident in options:
                erreurs += erreurs_note(f"{prefixe} › {ident}", note)
    return erreurs


def lire_decision(config):
    """Valide la rubrique decision ; toutes les erreurs sont listées d'un coup."""
    decision = config.get("decision")
    quoi = "la décision ne peut pas être préparée."
    if not isinstance(decision, dict):
        arreter(quoi, ["la rubrique « decision » est absente"])
    erreurs = []
    if not est_texte(decision.get("question")):
        erreurs.append("« question » doit être un texte")
    if "contexte" in decision and not est_texte(decision["contexte"]):
        erreurs.append("« contexte » doit être un texte")
    if not liste_de_textes(decision.get("besoins")):
        erreurs.append("« besoins » doit être la liste des besoins du client")
    if not est_entier(decision.get("commits_sur_jours")) or decision["commits_sur_jours"] < 1:
        erreurs.append("« commits_sur_jours » doit être un nombre entier positif de jours")
    if "infos_max" in decision and (not est_entier(decision["infos_max"]) or decision["infos_max"] < 1):
        erreurs.append("« infos_max » doit être un nombre entier positif")
    filtre = decision.get("filtre")
    if not isinstance(filtre, dict):
        erreurs.append("« filtre » doit contenir « si: » et ses cas")
    else:
        erreurs += [f"filtre : {erreur}" for erreur in erreurs_cas(filtre)]
    erreurs += erreurs_options(decision.get("options"))
    options = decision.get("options") if isinstance(decision.get("options"), dict) else {}
    erreurs += erreurs_criteres(decision.get("criteres"), options)
    if erreurs:
        arreter(quoi, erreurs)
    return decision


def infos_de_la_question(items, decision, categorie_par_source):
    """Les infos que le filtre de la décision retient, par fiabilité puis date décroissantes."""
    trouvees = [item for item in items
                if explication_regle(decision["filtre"], item, categorie_par_source.get(item["source"]))]
    trouvees.sort(key=lambda item: (item["fiabilite"] if item["fiabilite"] is not None else float("-inf"),
                                    item["publie_le"]), reverse=True)
    return trouvees


def lister_pages(chemin):
    """Tous les éléments d'une liste gh api, page par page."""
    elements, separateur = [], "&" if "?" in chemin else "?"
    for page in range(1, PAGES_GH_MAX + 1):
        lot = gh_api(f"{chemin}{separateur}per_page={PAR_PAGE_GH}&page={page}")
        if lot is None:
            break  # réponse vide : aucun élément
        elements += liste_d_objets(lot, "GitHub")
        if len(lot) < PAR_PAGE_GH:
            break
    return elements


def chiffres_depot(depot, jours):
    """Les chiffres bruts d'un dépôt GitHub, relevés en direct via gh api."""
    infos = gh_api(f"repos/{depot}")
    if not isinstance(infos, dict):
        raise ErreurSource("réponse inattendue de GitHub")
    releases = [r for r in lister_pages(f"repos/{depot}/releases") if not r.get("draft")]
    publiees = sorted((r for r in releases if jour(r.get("published_at"))),
                      key=lambda r: r["published_at"], reverse=True)
    depuis = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    licence = infos.get("license")
    return {
        "url": infos.get("html_url") or PAGE_GITHUB.format(depot=depot),
        "prive": bool(infos.get("private")),
        "cree_le": jour(infos.get("created_at")),
        "releases": len(releases),
        "derniere_version": (publiees[0].get("tag_name"), jour(publiees[0]["published_at"])) if publiees else None,
        "contributeurs": len(lister_pages(f"repos/{depot}/contributors?anon=1")),
        "commits_recents": len(lister_pages(f"repos/{depot}/commits?since={depuis}")),
        "licence": licence.get("spdx_id") if isinstance(licence, dict) else None,  # null : aucune licence
        "etoiles": infos.get("stargazers_count"),
        "issues_ouvertes": infos.get("open_issues_count"),
        "dernier_push": jour(infos.get("pushed_at")),
        "archive": bool(infos.get("archived")),
    }


def evaluer_options(decision):
    """Total pondéré de chaque option, sur le maximum possible, et critères éliminatoires."""
    criteres = decision["criteres"]
    maximum = sum(critere["poids"] * NOTES_POSSIBLES[1] for critere in criteres.values())
    resultats = {}
    for ident in decision["options"]:
        total = sum(critere["poids"] * critere["notes"][ident]["note"] for critere in criteres.values())
        eliminee_par = [nom for nom, critere in criteres.items()
                        if "note_eliminatoire" in critere
                        and critere["notes"][ident]["note"] <= critere["note_eliminatoire"]]
        resultats[ident] = {"total": total, "maximum": maximum,
                            "pourcentage": round(100 * total / maximum), "eliminee_par": eliminee_par}
    return resultats


def meilleure_option(resultats):
    """L'option non éliminée au meilleur total, ou None (égalité, ou toutes éliminées)."""
    en_lice = {ident: r for ident, r in resultats.items() if not r["eliminee_par"]}
    if not en_lice:
        return None
    meilleur = max(r["total"] for r in en_lice.values())
    gagnantes = [ident for ident, r in en_lice.items() if r["total"] == meilleur]
    return gagnantes[0] if len(gagnantes) == 1 else None


def cellule(texte):
    """Un texte sûr dans une case de tableau du fichier .md."""
    return " ".join(str(texte).split()).replace("|", "\\|")


def lien(texte, url):
    return f"[{cellule(texte).replace('[', '(').replace(']', ')')}]({url})"


def libelle_critere(nom, critere):
    return critere.get("libelle") or nom.replace("_", " ")


def total_lisible(resultat):
    return f"{resultat['total']} / {resultat['maximum']} ({resultat['pourcentage']} %)"


def conclusion(decision, resultats, gagnant):
    options = decision["options"]
    lignes = [f"⛔ « {options[ident]['nom']} » est éliminée : note éliminatoire en "
              + ", ".join(libelle_critere(c, decision["criteres"][c]) for c in r["eliminee_par"])
              for ident, r in resultats.items() if r["eliminee_par"]]
    if gagnant:
        autres = [r["total"] for ident, r in resultats.items() if ident != gagnant]
        ecart = resultats[gagnant]["total"] - max(autres) if autres else 0
        lignes.append(f"Option la mieux notée : « {options[gagnant]['nom']} », "
                      f"{total_lisible(resultats[gagnant])}, {ecart:+d} points d'écart.")
    elif any(not r["eliminee_par"] for r in resultats.values()):
        lignes.append("Égalité : la matrice ne départage pas les options.")
    else:
        lignes.append("Aucune option ne passe les critères éliminatoires.")
    return lignes


def lignes_chiffres(decision, chiffres):
    """Le tableau des chiffres bruts relevés par gh api, une colonne par option."""
    options = decision["options"]
    jours = decision["commits_sur_jours"]

    def valeur(ident, cle):
        c = chiffres[ident]
        if "erreur" in c:
            return "indisponible" if cle != "depot" else f"❌ {cellule(c['erreur'])}"
        if cle == "depot":
            return lien(options[ident]["depot"], c["url"]) + (" (dépôt privé)" if c["prive"] else "")
        if cle == "derniere_version":
            return f"{c[cle][0]} ({c[cle][1]})" if c[cle] else "aucune"
        if cle == "licence":
            return c[cle] or "aucune licence déclarée (license: null)"
        if cle == "archive":
            return "oui" if c[cle] else "non"
        nombre = c[cle]
        if cle in ("releases", "contributeurs", "commits_recents") and nombre >= PAR_PAGE_GH * PAGES_GH_MAX:
            return f"au moins {nombre}"
        return "inconnu" if nombre is None else str(nombre)

    rangees = [("depot", "Dépôt"), ("cree_le", "Créé le"), ("releases", "Versions publiées (releases)"),
               ("derniere_version", "Dernière version"), ("contributeurs", "Contributeurs"),
               ("commits_recents", f"Commits sur {jours} jours"), ("licence", "Licence"),
               ("etoiles", "Étoiles"), ("issues_ouvertes", "Issues ouvertes"),
               ("dernier_push", "Dernier push"), ("archive", "Archivé")]
    lignes = ["| Chiffre | " + " | ".join(cellule(o["nom"]) for o in options.values()) + " |",
              "|---|" + "---|" * len(options)]
    for cle, titre in rangees:
        lignes.append(f"| {titre} | " + " | ".join(valeur(ident, cle) for ident in options) + " |")
    return lignes


def rediger_decision(decision, infos, chiffres, resultats, gagnant, ref):
    """Le contenu de decision.md."""
    options, criteres = decision["options"], decision["criteres"]
    nb_max = decision.get("infos_max", len(infos))
    md = [f"# Décision · {decision['question']}", "",
         f"_Écrit par « radar decide » le {ref} à partir de {FICHIER_CONFIG.name} (rubrique « decision ») "
         f"et de {FICHIER_ITEMS.relative_to(DOSSIER)} ; chiffres bruts relevés en direct avec gh api. "
         f"Ce fichier est réécrit à chaque lancement : modifiez la config, pas ce fichier._", "",
         "## 1. La question et le contexte", "", decision["question"], ""]
    if decision.get("contexte"):
        md += [decision["contexte"], ""]
    md += ["Besoins du client (ils fixent nos poids) :", ""] + [f"- {besoin}" for besoin in decision["besoins"]] + [""]

    md += ["## 2. Les options comparées", "", "| | Option | Dépôt GitHub |", "|---|---|---|"]
    for numero, (ident, option) in enumerate(options.items(), 1):
        md.append(f"| {numero} | {cellule(option['nom'])} | "
                 f"{lien(option['depot'], PAGE_GITHUB.format(depot=option['depot']))} |")
    md.append("")

    retenues = sum(item["statut"] == "retenue" for item in infos)
    md += ["## 3. Ce que dit la veille", "",
          f"{len(infos)} info(s) de {FICHIER_ITEMS.name} touchent la question ({retenues} retenue(s))"
          + (f", les {nb_max} plus fiables :" if len(infos) > nb_max else " :"), ""]
    if infos:
        md += ["| Fiabilité | Statut | Publiée le | Info | Source |", "|---|---|---|---|---|"]
        for item in infos[:nb_max]:
            fiabilite = item["fiabilite"] if item["fiabilite"] is not None else "non notée"
            md.append(f"| {fiabilite} | {item['statut'] or 'à calculer'} | {item['publie_le']} | "
                     f"{lien(item['titre'], item['url'])} | {cellule(item['source'])} |")
    else:
        md.append("_Aucune info collectée ne touche la question : lancez « radar collect » puis « radar score »._")
    md.append("")

    md += [f"## 4. Chiffres bruts (gh api, relevés le {ref})", ""] + lignes_chiffres(decision, chiffres) + [""]

    md += [f"## 5. Matrice de décision (poids {POIDS_POSSIBLES[0]} à {POIDS_POSSIBLES[1]}, "
          f"notes {NOTES_POSSIBLES[0]} à {NOTES_POSSIBLES[1]})", "",
          "| Critère | Poids | " + " | ".join(cellule(o["nom"]) for o in options.values()) + " |",
          "|---|---|" + "---|" * len(options)]
    for nom, critere in criteres.items():
        notes = [f"{critere['notes'][ident]['note']} / {NOTES_POSSIBLES[1]} → "
                 f"{critere['poids'] * critere['notes'][ident]['note']}" for ident in options]
        eliminatoire = f" (éliminatoire si ≤ {critere['note_eliminatoire']})" if "note_eliminatoire" in critere else ""
        md.append(f"| {cellule(libelle_critere(nom, critere))}{eliminatoire} | {critere['poids']} | "
                 + " | ".join(notes) + " |")
    md.append(f"| **Total pondéré** | **{sum(c['poids'] for c in criteres.values())}** | "
             + " | ".join(f"**{total_lisible(resultats[ident])}**" for ident in options) + " |")
    md += [""] + [f"**{ligne}**" for ligne in conclusion(decision, resultats, gagnant)] + [""]

    md += ["### Justification de chaque note", ""]
    for nom, critere in criteres.items():
        md.append(f"**{libelle_critere(nom, critere)}** (poids {critere['poids']})")
        md.append("")
        for ident, option in options.items():
            note = critere["notes"][ident]
            md.append(f"- {option['nom']} : {note['note']} / {NOTES_POSSIBLES[1]}. {note['chiffre']} "
                     f"([source]({note['source']}), consultée le {note['date']})")
        md.append("")

    md += ["## 6. Impact", ""]
    for ident, option in options.items():
        impact = option.get("impact") or {}
        md += [f"### {option['nom']}", ""]
        md += [f"- **{titre}** : {impact.get(cle) or '_à remplir_'}" for cle, titre in CHAMPS_IMPACT]
        md.append("")
    return "\n".join(md)


# --- Commandes --------------------------------------------------------------

def commande_collect(args):
    config = charger_config()
    mots_cles = config.get("mots_cles") or []
    ignorer = config.get("ignorer") or []
    if not mots_cles:
        sys.exit("❌ La liste « mots_cles » de radar.config.yaml est vide : rien ne déclencherait de capture.")
    etiquettes = lire_etiquettes(config)
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
                fiche["etiquettes"] = attribuer_etiquettes(fiche, etiquettes, source.get("categorie"))
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


def commande_score(args):
    config = charger_config()
    regles, categorie_par_source = lire_regles(config)
    seuil, etiquettes, type_veille_par_source = lire_archivage(config)
    items = charger_items()
    if not items:
        print("Aucune info à noter : lancez d'abord « radar collect ».")
        return

    ref = aujourdhui()
    recoupements = calculer_recoupements(items, regles["recoupee"]["sujets"])
    resultats = []
    for item in items:
        # type_veille et étiquettes sont recalculés d'après la config actuelle (brique 4).
        item["type_veille"] = type_veille_par_source.get(item["source"], item["type_veille"])
        item["fiabilite"], raisons = scorer(item, regles, categorie_par_source, recoupements, ref)
        item["etiquettes"] = attribuer_etiquettes(item, etiquettes, categorie_par_source.get(item["source"]))
        item["statut"] = "retenue" if item["fiabilite"] >= seuil else "ecartee"
        resultats.append((item, raisons))
    enregistrer_items(items)

    # Score décroissant, puis date de publication décroissante.
    classement = sorted(resultats, key=lambda r: (r[0]["fiabilite"], r[0]["publie_le"]), reverse=True)
    top = classement[:args.top]
    print(f"🏆 Top {len(top)} sur {len(items)} infos, par fiabilité "
          f"(règles : « regles_score » de {FICHIER_CONFIG.name})\n")
    for rang, (item, raisons) in enumerate(top, 1):
        print(f"{rang:2}. {en_points(item['fiabilite'])} · {item['titre']}")
        print(f"    {item['source']} · publiée le {item['publie_le']}")
        print(f"    {decrire_archivage(item)}")
        for points, phrase in raisons:
            print(f"      {points:+d}  {phrase}")
        print()

    scores = [item["fiabilite"] for item in items]
    retenues = sum(item["statut"] == "retenue" for item in items)
    print(f"✅ fiabilite enregistrée pour {len(items)} infos dans {FICHIER_ITEMS.relative_to(DOSSIER)} "
          f"(de {min(scores)} à {max(scores)})")
    print(f"✅ étiquettes et statut posés : {retenues} retenues, {len(items) - retenues} écartées "
          f"(seuil : {seuil})")
    incompletes = [item["titre"] for item in items if any(item[champ] is None for champ in CHAMPS_FICHE)]
    if incompletes:
        print(f"⚠️  {len(incompletes)} info(s) gardent un champ vide (null), ex. : {incompletes[0]}")
    inconnues = sorted({item["source"] for item in items} - set(categorie_par_source))
    if inconnues:
        print(f"⚠️  Sources absentes du plan (catégorie inconnue, 0 point) : {', '.join(inconnues)}")


def commande_search(args):
    """Retrouve les infos dont le titre ou une étiquette contient le mot (sans écrire)."""
    mot = " ".join(args.mot).strip()
    if not mot:
        sys.exit("❌ Donnez un mot à chercher, ex. : radar search <mot>")
    items = charger_items()
    cherche = mot.lower()
    trouvees = [item for item in items
                if cherche in item["titre"].lower()
                or any(cherche in etiquette.lower() for etiquette in item["etiquettes"] or [])]
    masquees = 0
    if args.retenues:
        masquees = sum(item["statut"] != "retenue" for item in trouvees)
        trouvees = [item for item in trouvees if item["statut"] == "retenue"]
    # Score décroissant (non noté = en dernier), puis date de publication décroissante.
    trouvees.sort(key=lambda item: (item["fiabilite"] if item["fiabilite"] is not None else float("-inf"),
                                    item["publie_le"]), reverse=True)

    filtre = ", retenues seulement" if args.retenues else ""
    if not trouvees:
        print(f"Aucune info ne contient « {mot} » dans son titre ou ses étiquettes{filtre}.")
    else:
        print(f"🔎 {len(trouvees)} info(s) contiennent « {mot} » (titre ou étiquettes{filtre})\n")
    for rang, item in enumerate(trouvees, 1):
        score = en_points(item["fiabilite"]) if item["fiabilite"] is not None else "pas encore notée"
        print(f"{rang:2}. {item['titre']}")
        print(f"    {score} · {decrire_archivage(item)}")
        print(f"    {item['source']} · publiée le {item['publie_le']}")
        print(f"    {item['url']}")
        print()
    if masquees:
        print(f"({masquees} info(s) écartée(s) ou non notée(s) masquée(s) par --retenues)")


def commande_decide(args):
    config = charger_config()
    decision = lire_decision(config)
    categorie_par_source = {source.get("nom"): source.get("categorie") for source in config.get("sources") or []}
    infos = infos_de_la_question(charger_items(), decision, categorie_par_source)
    ref = aujourdhui()

    chiffres = {}
    for ident, option in decision["options"].items():
        print(f"📡 gh api : chiffres bruts de {option['depot']}…")
        try:
            chiffres[ident] = chiffres_depot(option["depot"], decision["commits_sur_jours"])
        except ErreurSource as e:
            print(f"❌ {option['depot']} : {e}")
            chiffres[ident] = {"erreur": str(e)}
    resultats = evaluer_options(decision)
    gagnant = meilleure_option(resultats)
    FICHIER_DECISION.write_text(rediger_decision(decision, infos, chiffres, resultats, gagnant, ref), encoding="utf-8")

    print(f"\n⚖️  {decision['question']}")
    for ident, option in decision["options"].items():
        c = chiffres[ident]
        resume = ("chiffres indisponibles" if "erreur" in c else
                  f"créé le {c['cree_le']}, {c['releases']} release(s), {c['contributeurs']} contributeur(s), "
                  f"{c['commits_recents']} commit(s) sur {decision['commits_sur_jours']} j, "
                  f"licence {c['licence'] or 'non déclarée'}")
        print(f"   {option['nom']} : {total_lisible(resultats[ident])}")
        print(f"      {option['depot']} · {resume}")
    for ligne in conclusion(decision, resultats, gagnant):
        print(f"   → {ligne}")
    retenues = sum(item["statut"] == "retenue" for item in infos)
    print(f"   🔎 {len(infos)} info(s) de veille touchent la question ({retenues} retenue(s))")
    print(f"✅ {FICHIER_DECISION.name} écrit")


def entier_positif(texte):
    try:
        valeur = int(texte)
    except ValueError:
        valeur = 0
    if valeur < 1:
        raise argparse.ArgumentTypeError(f"« {texte} » : un nombre entier positif est attendu")
    return valeur


def main():
    parser = argparse.ArgumentParser(prog="radar", description="RADAR : notre outil de veille.")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("collect", help="collecte les infos des sources de radar.config.yaml")
    score = commandes.add_parser("score", help="calcule la fiabilité de chaque info (regles_score)")
    score.add_argument("--top", type=entier_positif, default=10, help="nombre d'infos affichées (10 par défaut)")
    search = commandes.add_parser("search", help="retrouve les infos dont le titre ou les étiquettes contiennent un mot")
    search.add_argument("mot", nargs="+", help="le ou les mots à chercher dans les titres et les étiquettes")
    search.add_argument("--retenues", action="store_true", help="seulement les infos retenues")
    commandes.add_parser("decide", help="compare les 2 options de la rubrique decision et écrit decision.md")

    args = parser.parse_args()
    if args.commande == "collect":
        commande_collect(args)
    elif args.commande == "score":
        commande_score(args)
    elif args.commande == "search":
        commande_search(args)
    elif args.commande == "decide":
        commande_decide(args)


if __name__ == "__main__":
    main()
