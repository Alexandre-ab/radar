"""Tests de la brique 6 (radar report → rapport.md), sans réseau et sans toucher
aux vrais fichiers du projet.

Lancer depuis le dossier radar :  python3 -m unittest discover -s tests -v
"""
import argparse
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

VRAIS_FICHIERS = [Path(radar.FICHIER_ITEMS), Path(radar.FICHIER_PAGES), Path(radar.FICHIER_CONFIG),
                  Path(radar.FICHIER_DECISION), Path(radar.FICHIER_RAPPORT)]
empreintes_avant = {}

REF = date(2026, 10, 28)


def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest() if chemin.exists() else None


def setUpModule():
    for chemin in VRAIS_FICHIERS:
        empreintes_avant[chemin] = empreinte(chemin)


def tearDownModule():
    # Garde-fou : les tests ne doivent jamais réécrire les vrais fichiers du projet.
    for chemin in VRAIS_FICHIERS:
        if empreinte(chemin) != empreintes_avant[chemin]:
            raise AssertionError(f"{chemin} a été modifié par les tests !")


def fiche(titre, url, publie_le, source, fiabilite, statut, etiquettes=()):
    return {"titre": titre, "url": url, "publie_le": publie_le, "collecte_le": "2026-10-28", "source": source,
            "type_veille": "technologique", "etiquettes": list(etiquettes), "fiabilite": fiabilite, "statut": statut}


ITEMS = [
    fiche("Outil v1.1", "https://github.com/ex/outil/releases/v1.1", "2026-10-20", "Dépôt officiel", 6, "retenue", ["cli"]),
    fiche("Outil v1.2", "https://github.com/ex/outil/releases/v1.2", "2026-10-27", "Dépôt officiel", 6, "retenue", ["cli"]),
    fiche("Base v3.0", "https://github.com/ex/base/releases/v3.0", "2026-08-05", "Dépôt officiel", 6, "retenue", ["data"]),
    fiche("Base v2.9", "https://github.com/ex/base/releases/v2.9", "2026-05-12", "Dépôt officiel", 6, "retenue", ["data"]),
    fiche("Show HN: un | outil", "https://exemple.org/show", "2026-10-26", "Forum", 2, "ecartee", ["cli"]),
    fiche("Un autre outil", "https://exemple.org/autre", "2026-10-25", "Forum", 4, "retenue", ["cli"]),
    fiche("Politique d'usage", "https://exemple.org/cgu#empreinte-abc", "2026-10-28", "Éditeur", 5, "retenue"),
]


def note(valeur, source="https://exemple.org/source-note"):
    return {"note": valeur, "chiffre": "un chiffre vérifié", "source": source, "date": "2026-10-27"}


def critere(poids, a, b):
    return {"poids": poids, "notes": {"garder": note(a), "changer": note(b, "https://exemple.org/autre-note")}}


DECISION = {
    "question": "Garder A ou passer à B ?",
    "contexte": "Le contexte du client.",
    "besoins": ["rester local", "0 € en plus"],
    "commits_sur_jours": 90,
    "filtre": {"si": [{"titre_contient": ["base"]}]},
    "options": {
        "garder": {"nom": "Garder A", "depot": "ex/a",
                   "impact": {"perimetre": "Rien ne change.", "budget": "0 €", "delais": "0 sprint",
                              "anticipation": "Surveiller la taille."}},
        "changer": {"nom": "Passer à B", "depot": "ex/b"},
    },
    "criteres": {nom: critere(2, 4, 3) for nom in radar.CRITERES_KIT},
}

RAPPORT = {
    "option_recommandee": "garder",
    "etiquette_data": "data",
    "tendances": [
        {"titre": "Les outils publient vite", "type_veille": "technologique",
         "infos": ["https://github.com/ex/outil/releases/v1.2", "https://github.com/ex/outil/releases/v1.1"],
         "constat": "2 versions en 7 jours.", "impact": "Tester chaque version.", "anticipation": "Figer les versions.",
         "budget": "0 €.", "technique": "1 développeur suffit.", "statut": "retenue", "pourquoi": "Source officielle."},
        {"titre": "La base mûrit",
         "infos": ["https://github.com/ex/base/releases/v3.0", "https://github.com/ex/base/releases/v2.9"],
         "constat": "2 versions en 3 mois.", "impact": "Option crédible.", "anticipation": "Préparer l'import.",
         "budget": "Licence libre.", "technique": "Module natif.", "statut": "retenue", "pourquoi": "Officiel."},
        {"titre": "Des concurrents apparaissent", "type_veille": "concurrentielle",
         "infos": ["https://exemple.org/show", "https://exemple.org/autre"],
         "constat": "2 projets.", "impact": "Concurrence.", "anticipation": "Observer.",
         "budget": "Rien à payer.", "technique": "Aucun effet.", "statut": "ecartee", "pourquoi": "Signal faible."},
    ],
    "a_surveiller": ["Le rythme des versions.",
                     {"texte": "La politique d'usage.", "url": "https://exemple.org/cgu#empreinte-abc"}],
    "recommandation": "Nous recommandons de garder A pour les 2 prochains sprints (v1.2 incluse).",
    "risques": ["La recherche ralentit.", "Un seul développeur."],
    "plan_b": "Passer à B au-delà du seuil.",
    "prochaine_etape": {"action": "Mesurer la recherche.", "date": "2026-11-04"},
}


def config_ok(rapport=None, decision=None):
    return {
        "sources": [{"type": "releases", "depot": "ex/outil", "nom": "Dépôt officiel", "categorie": "officielle",
                     "type_veille": "technologique"},
                    {"type": "hackernews", "requete": "outil", "nom": "Forum", "categorie": "communaute",
                     "type_veille": "technologique"},
                    {"type": "page", "url": "https://exemple.org/cgu", "nom": "Éditeur", "categorie": "officielle",
                     "type_veille": "reglementaire"},
                    {"type": "releases", "depot": "ex/base", "nom": "Dépôt officiel", "categorie": "officielle",
                     "type_veille": "technologique"}],
        "seuil": 4,
        "etiquettes": {"cli": {"si": [{"titre_contient": ["outil"]}]}, "data": {"si": [{"titre_contient": ["base"]}]}},
        "decision": decision if decision is not None else copy.deepcopy(DECISION),
        "rapport": rapport if rapport is not None else copy.deepcopy(RAPPORT),
    }


def rapport_ok(**modifs):
    rapport = copy.deepcopy(RAPPORT)
    rapport.update(modifs)
    return rapport


# --- Validation de la rubrique rapport --------------------------------------

class TestLireRapport(unittest.TestCase):

    def lire(self, rapport=None, config=None):
        config = config or config_ok(rapport)
        return radar.lire_rapport(config, radar.lire_decision(config), ITEMS)

    def erreur(self, rapport=None, config=None):
        with mock.patch.object(radar, "aujourdhui", return_value=REF):
            with self.assertRaises(SystemExit) as e:
                self.lire(rapport, config)
        return str(e.exception.code)

    def test_vraie_config_du_projet_valide(self):
        # Lecture seule du vrai radar.config.yaml et du vrai data/items.json.
        config = radar.charger_config()
        rapport = radar.lire_rapport(config, radar.lire_decision(config), radar.charger_items())
        self.assertEqual(len(rapport["tendances"]), radar.NOMBRE_TENDANCES)

    def test_config_de_test_valide(self):
        with mock.patch.object(radar, "aujourdhui", return_value=REF):
            self.assertEqual(self.lire()["option_recommandee"], "garder")

    def test_rubrique_absente(self):
        config = config_ok()
        del config["rapport"]
        self.assertIn("la rubrique « rapport » est absente", self.erreur(config=config))

    def test_url_de_tendance_absente_de_items_json(self):
        rapport = rapport_ok()
        rapport["tendances"][0]["infos"].append("https://exemple.org/inventee")
        self.assertIn("url absente de data/items.json (source inventée ?) : https://exemple.org/inventee",
                      self.erreur(rapport))

    def test_une_seule_info_ne_fait_pas_une_tendance(self):
        rapport = rapport_ok()
        rapport["tendances"][0]["infos"] = rapport["tendances"][0]["infos"][:1]
        self.assertIn("« infos » doit citer au moins 2 urls", self.erreur(rapport))

    def test_url_en_double(self):
        rapport = rapport_ok()
        rapport["tendances"][0]["infos"] = ["https://github.com/ex/outil/releases/v1.2"] * 2
        self.assertIn("une même url est citée deux fois", self.erreur(rapport))

    def test_exactement_trois_tendances(self):
        for tendances in (RAPPORT["tendances"][:2], RAPPORT["tendances"] + RAPPORT["tendances"][:1], None):
            with self.subTest(n=len(tendances or [])):
                self.assertIn("exactement 3 tendances", self.erreur(rapport_ok(tendances=copy.deepcopy(tendances))))

    def test_champs_de_tendance(self):
        for cle in ("titre", "constat", "impact", "anticipation", "budget", "technique", "pourquoi"):
            with self.subTest(cle=cle):
                rapport = rapport_ok()
                rapport["tendances"][1][cle] = ""
                self.assertIn(f"tendances › n°2 : « {cle} »", self.erreur(rapport))
        for modif, attendu in [({"statut": "à voir"}, "« statut » doit être retenue ou ecartee"),
                               ({"type_veille": "tech"}, "type_veille « tech » inconnu")]:
            with self.subTest(modif=modif):
                rapport = rapport_ok()
                rapport["tendances"][2].update(modif)
                self.assertIn(attendu, self.erreur(rapport))

    def test_au_moins_une_tendance_sur_la_data(self):
        rapport = rapport_ok()
        rapport["tendances"][1]["infos"] = ["https://github.com/ex/base/releases/v3.0",
                                            "https://github.com/ex/outil/releases/v1.1"]  # une sans « data »
        self.assertIn("aucune tendance sur la data", self.erreur(rapport))
        self.assertIn("« etiquette_data » doit être l'une des étiquettes", self.erreur(rapport_ok(etiquette_data="donnees")))

    def test_option_recommandee_et_son_impact(self):
        self.assertIn("« option_recommandee » doit être l'une des options", self.erreur(rapport_ok(option_recommandee="c")))
        # « changer » n'a pas d'impact : impossible de remplir la page 2, point 4
        message = self.erreur(rapport_ok(option_recommandee="changer"))
        for cle in ("perimetre", "budget", "delais"):
            self.assertIn(f"l'option recommandée n'a pas d'impact « {cle} »", message)

    def test_recommandation_en_une_seule_phrase(self):
        for texte in ("Nous gardons A. Puis nous verrons.", "Garder A !  Et vite.", "Garder A\npour 2 sprints.", ""):
            with self.subTest(texte=texte):
                self.assertIn("« recommandation » doit tenir en UNE phrase", self.erreur(rapport_ok(recommandation=texte)))

    def test_a_surveiller(self):
        self.assertIn("« a_surveiller » doit lister", self.erreur(rapport_ok(a_surveiller=[])))
        self.assertIn("a_surveiller › n°1 : url absente de data/items.json",
                      self.erreur(rapport_ok(a_surveiller=[{"texte": "x", "url": "https://exemple.org/inventee"}])))
        self.assertIn("a_surveiller › n°1 : doit être un texte", self.erreur(rapport_ok(a_surveiller=[3])))

    def test_risques_plan_b_et_prochaine_etape(self):
        for modif, attendu in [({"risques": []}, "« risques » doit lister"),
                               ({"plan_b": ""}, "« plan_b » doit être un texte"),
                               ({"prochaine_etape": {"date": "2026-11-04"}}, "doit contenir « action » et « date »"),
                               ({"prochaine_etape": {"action": "x", "date": "2026-10-27"}}, "à partir d'aujourd'hui"),
                               ({"prochaine_etape": {"action": "x", "date": date(2026, 11, 4)}}, "entre guillemets")]:
            with self.subTest(modif=modif):
                self.assertIn(attendu, self.erreur(rapport_ok(**modif)))

    def test_toutes_les_erreurs_listees_ensemble(self):
        message = self.erreur(rapport_ok(plan_b="", risques=[]))
        self.assertIn("« plan_b »", message)
        self.assertIn("« risques »", message)


class TestOutils(unittest.TestCase):

    def test_une_seule_phrase(self):
        for texte in ("Une phrase.", "Une phrase avec v13.0.3 et 2,5 €.", "Une phrase sans point"):
            with self.subTest(texte=texte):
                self.assertTrue(radar.une_seule_phrase(texte))
        for texte in ("Une. Deux.", "Une ? Deux", "Une… Deux", "Une\nDeux"):
            with self.subTest(texte=texte):
                self.assertFalse(radar.une_seule_phrase(texte))

    def test_urls_citees(self):
        # Corrigé après la revue Codex : les urls en texte brut comptent aussi (avant : ignorées).
        texte = "voir [a](https://a.org/x) et [b](http://b.org/y?z=1#f), et https://c.org seul"
        self.assertEqual(radar.urls_citees(texte), ["https://a.org/x", "http://b.org/y?z=1#f", "https://c.org"])

    def test_urls_brutes_et_ponctuation_finale(self):
        for texte, attendu in [("(voir https://x.org/a).", ["https://x.org/a"]),
                               ("fin de phrase https://x.org/a.", ["https://x.org/a"]),
                               ("liste : https://x.org/a, https://y.org/b ; https://z.org/c!", 
                                ["https://x.org/a", "https://y.org/b", "https://z.org/c"]),
                               ("« https://x.org/b »", ["https://x.org/b"]),
                               ("https://fr.wikipedia.org/wiki/SQLite_(logiciel), suite",
                                ["https://fr.wikipedia.org/wiki/SQLite_(logiciel)"]),
                               ("http://x.org/y?q=1&r=2#f", ["http://x.org/y?q=1&r=2#f"]),
                               ("[https://a.org](https://a.org)", ["https://a.org", "https://a.org"]),
                               ("http:// tout seul, ou httpx://a.org", []),
                               ("aucune url ici.", [])]:
            with self.subTest(texte=texte):
                self.assertEqual(radar.urls_citees(texte), attendu)

    def test_urls_autorisees(self):
        autorisees = radar.urls_autorisees(DECISION, ITEMS)
        self.assertTrue({i["url"] for i in ITEMS} <= autorisees)
        self.assertTrue({"https://github.com/ex/a", "https://github.com/ex/b", "https://exemple.org/source-note",
                         "https://exemple.org/autre-note"} <= autorisees)
        self.assertNotIn("https://exemple.org/inventee", autorisees)


# --- La commande report de bout en bout ---------------------------------------

class TestCommandeReport(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.items = self.dossier / "data" / "items.json"
        self.config = self.dossier / "radar.config.yaml"
        self.rapport = self.dossier / "rapport.md"
        self.decision = self.dossier / "decision.md"
        for nom, valeur in [("DOSSIER", self.dossier), ("FICHIER_CONFIG", self.config), ("FICHIER_ITEMS", self.items),
                            ("FICHIER_PAGES", self.dossier / "data" / "pages.json"),
                            ("FICHIER_DECISION", self.decision), ("FICHIER_RAPPORT", self.rapport)]:
            self.patcher(radar, nom, valeur)
        self.patcher(radar, "aujourdhui", return_value=REF)
        self.patcher(radar.subprocess, "run", side_effect=AssertionError("appel à gh interdit"))
        self.patcher(radar.urllib.request, "urlopen", side_effect=AssertionError("appel réseau interdit"))
        self.ecrire_config(config_ok())
        self.ecrire_items(ITEMS)

    def patcher(self, cible, nom, valeur=mock.DEFAULT, **options):
        patch = mock.patch.object(cible, nom, valeur, **options)
        objet = patch.start()
        self.addCleanup(patch.stop)
        return objet

    def ecrire_config(self, config):
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def ecrire_items(self, items):
        self.items.parent.mkdir(parents=True, exist_ok=True)
        self.items.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    def lancer(self, verifier_liens=False):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            radar.commande_report(argparse.Namespace(verifier_liens=verifier_liens))
        return sortie.getvalue(), self.rapport.read_text(encoding="utf-8")

    def test_les_deux_pages_dans_l_ordre(self):
        _, md = self.lancer()
        titres = ["## Page 1 · Synthèse de veille", "### 1. Nos sources retenues", "### 2. Les 3 tendances",
                  "### 3. Ce qu'il faut continuer à surveiller", '<div style="page-break-after: always;"></div>',
                  "## Page 2 · Note de recommandation", "### 1. La question et le contexte",
                  "### 2. Les options et la matrice", "### 3. La recommandation",
                  "### 4. L'impact", "Option retenue : Garder A.", "### 5. Les risques et le plan B",
                  "### 6. La prochaine étape"]
        positions = [md.index(titre) for titre in titres]
        self.assertEqual(positions, sorted(positions))

    def test_sources_retenues_datees(self):
        _, md = self.lancer()
        self.assertIn("| Dépôt officiel | officielle | technologique | 4 | 2026-05-12 et 2026-10-27 | "
                      "[Outil v1.2](https://github.com/ex/outil/releases/v1.2) |", md)
        self.assertIn("| Forum | communaute | technologique | 1 | 2026-10-25 et 2026-10-25 | "
                      "[Un autre outil](https://exemple.org/autre) |", md)
        self.assertIn("| Éditeur | officielle | reglementaire | 1 |", md)
        self.assertEqual(md.count("| Dépôt officiel |"), 1)   # deux sources de même nom : une ligne
        self.assertIn("6 infos retenues sur 7 collectées (fiabilité au moins égale au seuil de 4", md)

    def test_tendances(self):
        _, md = self.lancer()
        self.assertIn("#### Tendance 1 · Les outils publient vite (technologique)", md)
        self.assertIn("#### Tendance 2 · La base mûrit (tendance « data »)", md)
        self.assertIn("#### Tendance 3 · Des concurrents apparaissent (concurrentielle)", md)
        self.assertIn("**Ce que montrent les infos** : 2 versions en 7 jours.", md)
        # infos triées par date, avec source, fiabilité et statut ; « | » échappé dans le titre
        self.assertIn("- 2026-10-20 · [Outil v1.1](https://github.com/ex/outil/releases/v1.1) · Dépôt officiel · "
                      "fiabilité 6 (retenue)\n- 2026-10-27 · [Outil v1.2]", md)
        self.assertIn("[Show HN: un \\| outil](https://exemple.org/show) · Forum · fiabilité 2 (ecartee)", md)
        for ligne in ("- **Impact attendu** : Tester chaque version.", "- **Ce qu'elle permet d'anticiper** : Figer",
                      "- **Compatibilité budget** : 0 €.", "- **Compatibilité technique** : 1 développeur",
                      "- **Retenue**, pourquoi : Source officielle.", "- **Écartée**, pourquoi : Signal faible."):
            self.assertIn(ligne, md)

    def test_a_surveiller_avec_et_sans_lien(self):
        _, md = self.lancer()
        self.assertIn("- Le rythme des versions.\n- La politique d'usage. "
                      "([Politique d'usage](https://exemple.org/cgu#empreinte-abc))", md)

    def test_page_2(self):
        _, md = self.lancer()
        page2 = md[md.index("## Page 2"):]
        self.assertIn("Garder A ou passer à B ?\n\nLe contexte du client.\n\nBesoins du client : rester local ; 0 € en plus.", page2)
        self.assertIn("| 1 | Garder A | [ex/a](https://github.com/ex/a) |", page2)
        self.assertIn("| **Total pondéré** | **14** | **56 / 70 (80 %)** | **42 / 70 (60 %)** |", page2)
        self.assertIn("> **Nous recommandons de garder A pour les 2 prochains sprints (v1.2 incluse).**", page2)
        self.assertIn("- **Périmètre** : Rien ne change.\n- **Budget** : 0 €\n- **Délais** : 0 sprint", page2)
        self.assertNotIn("Surveiller la taille.", page2)   # anticipation : pas au point 4 du kit
        self.assertIn("- La recherche ralentit.\n- Un seul développeur.\n\n**Plan B** : Passer à B au-delà du seuil.", page2)
        self.assertIn("**Le 2026-11-04** : Mesurer la recherche.", page2)

    def test_toutes_les_urls_viennent_de_items_ou_de_la_decision(self):
        _, md = self.lancer()
        citees = set(radar.urls_citees(md))
        self.assertTrue(citees)
        self.assertEqual(citees - radar.urls_autorisees(DECISION, ITEMS), set())

    def test_resume_terminal(self):
        sortie, _ = self.lancer()
        self.assertIn("   Tendance 3 (ecartee) : Des concurrents apparaissent", sortie)
        self.assertIn("   Recommandation : Nous recommandons de garder A", sortie)
        self.assertIn("   Prochaine étape le 2026-11-04 : Mesurer la recherche.", sortie)
        self.assertIn("✅ rapport.md écrit : 2 pages,", sortie)
        self.assertNotIn("n'est pas la mieux notée", sortie)

    def test_avertissement_si_la_recommandation_n_est_pas_la_mieux_notee(self):
        config = config_ok()
        config["decision"]["options"]["changer"]["impact"] = dict(DECISION["options"]["garder"]["impact"])
        config["rapport"]["option_recommandee"] = "changer"
        self.ecrire_config(config)
        sortie, _ = self.lancer()
        self.assertIn("⚠️  L'option recommandée n'est pas la mieux notée de la matrice", sortie)

    def test_report_n_ecrit_ni_items_ni_decision(self):
        avant = self.items.read_bytes()
        self.lancer()
        self.assertEqual(self.items.read_bytes(), avant)
        self.assertFalse(self.decision.exists())

    def test_score_pas_encore_lance(self):
        items = copy.deepcopy(ITEMS)
        items[0]["statut"] = None
        self.ecrire_items(items)
        with self.assertRaises(SystemExit) as e:
            self.lancer()
        self.assertIn("lancez d'abord « radar score »", str(e.exception.code))
        self.assertFalse(self.rapport.exists())

    def test_rapport_invalide_rien_n_est_ecrit(self):
        rapport = rapport_ok()
        rapport["tendances"][0]["infos"][0] = "https://exemple.org/inventee"
        self.ecrire_config(config_ok(rapport))
        with self.assertRaises(SystemExit) as e:
            self.lancer()
        self.assertIn("source inventée", str(e.exception.code))
        self.assertFalse(self.rapport.exists())

    def test_garde_fou_final_sur_les_urls(self):
        # Même si la rédaction ajoutait un lien étranger, le rapport ne serait pas écrit.
        self.patcher(radar, "rediger_rapport", return_value="voir [ici](https://exemple.org/inventee)")
        with self.assertRaises(SystemExit) as e:
            self.lancer()
        self.assertIn("https://exemple.org/inventee", str(e.exception.code))
        self.assertFalse(self.rapport.exists())

    def test_url_inventee_en_texte_brut_bloque_l_ecriture(self):
        # Régression (revue Codex) : une url sans syntaxe [lien](url) ne doit pas passer.
        inventee = "https://exemple.org/inventee-brute"
        for champ in ("recommandation", "risques", "plan_b", "prochaine_etape", "tendance", "a_surveiller"):
            with self.subTest(champ=champ):
                rapport = rapport_ok()
                if champ == "recommandation":
                    rapport["recommandation"] = f"Nous recommandons de garder A (voir {inventee})."
                elif champ == "risques":
                    rapport["risques"].append(f"Un risque décrit sur {inventee}.")
                elif champ == "plan_b":
                    rapport["plan_b"] = f"Passer à B, comme le montre {inventee}"
                elif champ == "prochaine_etape":
                    rapport["prochaine_etape"]["action"] = f"Lire {inventee}, puis décider."
                elif champ == "tendance":
                    rapport["tendances"][0]["constat"] = f"2 versions en 7 jours ({inventee})."
                else:
                    rapport["a_surveiller"].append(f"Surveiller {inventee} chaque semaine.")
                self.ecrire_config(config_ok(rapport))
                with self.assertRaises(SystemExit) as e:
                    self.lancer()
                self.assertIn("le rapport cite des urls qui ne viennent ni de data/items.json ni de la décision",
                              str(e.exception.code))
                self.assertIn(inventee, str(e.exception.code))
                self.assertFalse(self.rapport.exists())

    def test_url_brute_autorisee_acceptee(self):
        # Une url brute qui vient bien de items.json passe, ponctuation finale retirée.
        rapport = rapport_ok()
        rapport["risques"].append("Voir la version (https://github.com/ex/outil/releases/v1.2).")
        self.ecrire_config(config_ok(rapport))
        _, md = self.lancer()
        self.assertIn("https://github.com/ex/outil/releases/v1.2", radar.urls_citees(md))

    def test_url_brute_verifiee_en_direct(self):
        rapport = rapport_ok()
        rapport["risques"].append("Voir https://github.com/ex/outil/releases/v1.1.")
        self.ecrire_config(config_ok(rapport))
        faux_http = self.patcher(radar, "http", return_value=("<html>ok</html>", {}))
        self.lancer(verifier_liens=True)
        self.assertIn("https://github.com/ex/outil/releases/v1.1", {a.args[0] for a in faux_http.call_args_list})

    def test_verifier_liens_tous_ok(self):
        faux_http = self.patcher(radar, "http", return_value=("<html>ok</html>", {}))
        sortie, md = self.lancer(verifier_liens=True)
        ouvertes = {appel.args[0] for appel in faux_http.call_args_list}
        self.assertIn("https://exemple.org/cgu", ouvertes)                    # #fragment retiré
        self.assertNotIn("https://exemple.org/cgu#empreinte-abc", ouvertes)
        self.assertEqual(len(ouvertes), len({u.split("#")[0] for u in radar.urls_citees(md)}))
        self.assertIn("tous vérifiés en direct", sortie)

    def test_verifier_liens_un_lien_casse(self):
        def faux_http(url):
            if url == "https://exemple.org/show":
                raise radar.ErreurSource("le serveur a répondu HTTP 404 pour https://exemple.org/show")
            return "<html>ok</html>", {}
        self.patcher(radar, "http", side_effect=faux_http)
        with self.assertRaises(SystemExit) as e:
            self.lancer(verifier_liens=True)
        self.assertIn("des liens du rapport ne répondent pas", str(e.exception.code))
        self.assertIn("HTTP 404", str(e.exception.code))
        self.assertFalse(self.rapport.exists())

    def test_ligne_de_commande(self):
        appel = self.patcher(radar, "commande_report")
        with mock.patch.object(sys, "argv", ["radar", "report", "--verifier-liens"]):
            radar.main()
        self.assertTrue(appel.call_args.args[0].verifier_liens)


# --- Le vrai rapport.md -------------------------------------------------------

class TestVraiRapport(unittest.TestCase):

    def test_100_pour_cent_des_urls_du_vrai_rapport_viennent_de_items_ou_de_decision(self):
        chemin = Path(radar.FICHIER_RAPPORT)
        if not chemin.exists():
            self.skipTest("rapport.md pas encore écrit (lancez « ./radar report »)")
        config = radar.charger_config()                       # lecture seule
        autorisees = radar.urls_autorisees(radar.lire_decision(config), radar.charger_items())
        citees = set(radar.urls_citees(chemin.read_text(encoding="utf-8")))
        self.assertTrue(citees)
        self.assertEqual(sorted(citees - autorisees), [])


if __name__ == "__main__":
    unittest.main()
