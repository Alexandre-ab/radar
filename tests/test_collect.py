"""Tests de la brique collect, sans réseau et sans toucher à data/items.json.

Lancer depuis le dossier radar :  python3 -m unittest discover -s tests -v
"""
import hashlib
import io
import json
import subprocess
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

VRAI_ITEMS = Path(radar.FICHIER_ITEMS)
empreinte_avant = None


def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest() if chemin.exists() else None


def setUpModule():
    global empreinte_avant
    empreinte_avant = empreinte(VRAI_ITEMS)


def tearDownModule():
    # Garde-fou : les tests ne doivent jamais réécrire le vrai data/items.json.
    if empreinte(VRAI_ITEMS) != empreinte_avant:
        raise AssertionError("data/items.json a été modifié par les tests !")


def fiche_ok(**modifs):
    fiche = {
        "titre": "Claude Code v2.1.312",
        "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.312",
        "publie_le": "2026-10-27",
        "collecte_le": "2026-10-28",
        "source": "Dépôt GitHub officiel",
        "type_veille": "technologique",
        "etiquettes": None,
        "fiabilite": None,
        "statut": None,
    }
    fiche.update(modifs)
    return fiche


def release(tag, corps="", publie="2026-10-27T20:24:20Z", depot="anthropics/claude-code"):
    """Une release telle que la renvoie l'API GitHub (champs utiles seulement)."""
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/{depot}/releases/tag/{tag}",
        "published_at": publie,
        "body": corps,
    }


def source_releases(**modifs):
    source = {
        "type": "releases",
        "depot": "anthropics/claude-code",
        "nom": "Dépôt GitHub officiel",
        "produit": "Claude Code",
        "limite": 10,
        "type_veille": "technologique",
    }
    source.update(modifs)
    return source


class TestFicheValide(unittest.TestCase):

    def test_fiche_valide(self):
        self.assertTrue(radar.fiche_valide(fiche_ok()))

    def test_fiche_sans_url(self):
        self.assertFalse(radar.fiche_valide(fiche_ok(url="")))
        self.assertFalse(radar.fiche_valide(fiche_ok(url=None)))
        self.assertFalse(radar.fiche_valide(fiche_ok(url="   ")))

    def test_fiche_sans_date(self):
        self.assertFalse(radar.fiche_valide(fiche_ok(publie_le=None)))
        self.assertFalse(radar.fiche_valide(fiche_ok(publie_le="")))
        self.assertFalse(radar.fiche_valide(fiche_ok(collecte_le=None)))

    def test_date_invalide(self):
        for valeur in ["hier", "2026-02-30", "28/10/2026", "20261028",
                       "2026-10-27T20:24:20Z", 20261027]:
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche_ok(publie_le=valeur)))
                self.assertFalse(radar.fiche_valide(fiche_ok(collecte_le=valeur)))

    def test_champ_obligatoire_manquant(self):
        for champ in radar.CHAMPS_FICHE:
            with self.subTest(champ=champ):
                fiche = fiche_ok()
                del fiche[champ]
                self.assertFalse(radar.fiche_valide(fiche))

    def test_champ_texte_vide_ou_mauvais_type(self):
        for champ in ("titre", "source"):
            with self.subTest(champ=champ):
                self.assertFalse(radar.fiche_valide(fiche_ok(**{champ: ""})))
                self.assertFalse(radar.fiche_valide(fiche_ok(**{champ: 42})))

    def test_fiche_qui_nest_pas_un_objet(self):
        for valeur in ["pas une fiche", None, 3, ["titre"]]:
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(valeur))

    def test_null_autorise_pour_les_briques_suivantes(self):
        self.assertTrue(radar.fiche_valide(fiche_ok(type_veille=None)))
        self.assertTrue(radar.fiche_valide(fiche_ok(etiquettes=None, fiabilite=None, statut=None)))
        self.assertFalse(radar.fiche_valide(fiche_ok(type_veille="")))

    def test_type_veille_valide_pour_les_quatre_categories(self):
        for valeur in ("technologique", "concurrentielle", "reglementaire", "securite"):
            with self.subTest(valeur=valeur):
                self.assertTrue(radar.fiche_valide(fiche_ok(type_veille=valeur)))

    def test_type_veille_invalide(self):
        for valeur in ["tech", "Technologique", "sécurité", " securite", 3, ["securite"]]:
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche_ok(type_veille=valeur)))

    def test_date_de_publication_future(self):
        apres_demain = (date.today() + timedelta(days=2)).isoformat()
        self.assertFalse(radar.fiche_valide(fiche_ok(publie_le=apres_demain)))
        self.assertTrue(radar.fiche_valide(fiche_ok(publie_le=date.today().isoformat())))

    def test_url_sans_http_ni_https(self):
        for valeur in ["github.com/anthropics/claude-code", "ftp://exemple.org/a",
                       "https://", "http:/exemple.org", "https://exemple .org", "javascript:alert(1)"]:
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche_ok(url=valeur)))
        self.assertTrue(radar.fiche_valide(fiche_ok(url="http://exemple.org/a")))


class TestGhApi(unittest.TestCase):
    """gh_api() seule : subprocess.run est simulé, aucun vrai « gh » n'est lancé."""

    def test_appel_exact_et_decodage_json(self):
        reponse = subprocess.CompletedProcess(args=[], returncode=0, stdout='[{"tag_name": "v1"}]', stderr="")
        with mock.patch.object(radar.subprocess, "run", return_value=reponse) as faux_run:
            resultat = radar.gh_api("repos/anthropics/claude-code/releases?per_page=3")
        faux_run.assert_called_once_with(
            ["gh", "api", "repos/anthropics/claude-code/releases?per_page=3"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(resultat, [{"tag_name": "v1"}])

    def test_erreur_de_gh(self):
        erreur = subprocess.CalledProcessError(1, ["gh", "api", "x"], stderr="HTTP 404: Not Found\n")
        with mock.patch.object(radar.subprocess, "run", side_effect=erreur):
            with self.assertRaises(radar.ErreurSource) as e:
                radar.gh_api("x")
        self.assertIn("HTTP 404: Not Found", str(e.exception))

    def test_gh_absent(self):
        with mock.patch.object(radar.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(radar.ErreurSource) as e:
                radar.gh_api("x")
        self.assertIn("pas installée", str(e.exception))

    def test_reponse_qui_nest_pas_du_json(self):
        reponse = subprocess.CompletedProcess(args=[], returncode=0, stdout="<html>", stderr="")
        with mock.patch.object(radar.subprocess, "run", return_value=reponse):
            with self.assertRaises(radar.ErreurSource):
                radar.gh_api("x")


class TestCollecterReleases(unittest.TestCase):

    def test_type_veille_repris_de_la_configuration(self):
        with mock.patch.object(radar, "gh_api", return_value=[release("v1")]):
            [(fiche, _)] = radar.collecter_releases(source_releases(type_veille="securite"))
        self.assertEqual(fiche["type_veille"], "securite")
        self.assertEqual(fiche["source"], "Dépôt GitHub officiel")
        self.assertTrue(radar.fiche_valide(fiche))

    def test_source_sans_nom_rejetee(self):
        for source in (source_releases(nom=None), source_releases(nom="  ")):
            with self.subTest(nom=source["nom"]):
                with mock.patch.object(radar, "gh_api") as faux_gh:
                    with self.assertRaises(radar.ErreurSource) as erreur:
                        radar.collecter_releases(source)
                    faux_gh.assert_not_called()  # on s'arrête avant tout appel réseau
                self.assertIn("nom", str(erreur.exception))
        source = source_releases()
        del source["nom"]
        with mock.patch.object(radar, "gh_api") as faux_gh:
            with self.assertRaises(radar.ErreurSource):
                radar.collecter_releases(source)
            faux_gh.assert_not_called()

    def test_appel_via_gh_api(self):
        with mock.patch.object(radar, "gh_api", return_value=[]) as faux_gh:
            radar.collecter_releases(source_releases(limite=5))
        faux_gh.assert_called_once_with("repos/anthropics/claude-code/releases?per_page=5")


class TestCommandeCollect(unittest.TestCase):
    """radar collect de bout en bout, dans un dossier temporaire, gh_api simulé."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.items = self.dossier / "data" / "items.json"
        self.config = self.dossier / "radar.config.yaml"
        for nom, valeur in [("DOSSIER", self.dossier),
                            ("FICHIER_CONFIG", self.config),
                            ("FICHIER_ITEMS", self.items)]:
            patch = mock.patch.object(radar, nom, valeur)
            patch.start()
            self.addCleanup(patch.stop)
        # Aucun processus (donc aucun vrai « gh ») ne doit être lancé.
        patch = mock.patch.object(radar.subprocess, "run", side_effect=AssertionError("appel réseau interdit"))
        patch.start()
        self.addCleanup(patch.stop)

    def ecrire_config(self, sources, mots_cles=("claude code",), ignorer=("crypto",)):
        config = {"mots_cles": list(mots_cles), "ignorer": list(ignorer), "sources": sources}
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    def collecter(self, releases):
        sortie = io.StringIO()
        with mock.patch.object(radar, "gh_api", return_value=releases), redirect_stdout(sortie):
            radar.commande_collect(None)
        return json.loads(self.items.read_text(encoding="utf-8")), sortie.getvalue()

    def test_filtrage_par_mots_cles(self):
        self.ecrire_config([source_releases(produit="Outil X")])
        items, _ = self.collecter([
            release("v1", corps="Compatibilité avec Claude Code"),
            release("v2", corps="Corrections diverses"),
        ])
        self.assertEqual([i["titre"] for i in items], ["Outil X v1"])

    def test_filtrage_par_ignorer(self):
        self.ecrire_config([source_releases()])
        items, sortie = self.collecter([
            release("v1", corps="Nouveau portefeuille CRYPTO"),
            release("v2", corps="Corrections diverses"),
        ])
        self.assertEqual([i["titre"] for i in items], ["Claude Code v2"])
        self.assertIn("1 ignorées", sortie)

    def test_doublon_url_non_ajoute(self):
        self.ecrire_config([source_releases()])
        self.items.parent.mkdir()
        existante = fiche_ok(url=release("v1")["html_url"], titre="Claude Code v1")
        self.items.write_text(json.dumps([existante]), encoding="utf-8")
        items, _ = self.collecter([release("v1"), release("v1"), release("v2")])
        self.assertEqual(sorted(i["url"] for i in items),
                         sorted({release("v1")["html_url"], release("v2")["html_url"]}))

    def test_nettoyage_des_fiches_deja_presentes(self):
        self.ecrire_config([source_releases()])
        self.items.parent.mkdir()
        bonne = fiche_ok()
        self.items.write_text(json.dumps([
            bonne,
            dict(bonne),                               # doublon
            fiche_ok(url="https://ex.org/a", publie_le="hier"),
            {"titre": "incomplète", "url": "https://ex.org/b"},
            "pas une fiche",
        ]), encoding="utf-8")
        items, sortie = self.collecter([])
        self.assertEqual(items, [bonne])
        self.assertIn("3 fiche(s) retirée(s)", sortie)
        self.assertIn("1 doublon(s) retiré(s)", sortie)

    def test_release_sans_date_rejetee(self):
        self.ecrire_config([source_releases()])
        items, sortie = self.collecter([release("v1", publie=None), release("v2")])
        self.assertEqual([i["titre"] for i in items], ["Claude Code v2"])
        self.assertIn("1 rejetées", sortie)

    def test_collecte_avec_url_invalide(self):
        self.ecrire_config([source_releases()])
        mauvaise = release("v1")
        mauvaise["html_url"] = "github.com/anthropics/claude-code/releases/tag/v1"
        items, sortie = self.collecter([mauvaise, release("v2")])
        self.assertEqual([i["titre"] for i in items], ["Claude Code v2"])
        self.assertIn("1 rejetées", sortie)

    def test_collecte_avec_type_veille_invalide(self):
        self.ecrire_config([source_releases(type_veille="tech")])
        items, sortie = self.collecter([release("v1"), release("v2")])
        self.assertEqual(items, [])
        self.assertIn("2 rejetées", sortie)

    def test_type_veille_dans_items(self):
        self.ecrire_config([source_releases(type_veille="reglementaire")])
        items, _ = self.collecter([release("v1")])
        self.assertEqual(items[0]["type_veille"], "reglementaire")

    def test_source_sans_nom_ne_cree_aucune_fiche(self):
        source = source_releases()
        del source["nom"]
        self.ecrire_config([source])
        items, sortie = self.collecter([release("v1")])
        self.assertEqual(items, [])
        self.assertIn("champ « nom » manquant", sortie)

    def test_source_non_geree_signalee(self):
        self.ecrire_config([source_releases(), {"type": "hackernews", "requete": "claude code"}])
        _, sortie = self.collecter([release("v1")])
        self.assertIn("hackernews · claude code : NON COLLECTÉE", sortie)
        self.assertIn("releases", radar.COLLECTEURS)  # la table des collecteurs reste extensible


if __name__ == "__main__":
    unittest.main()
