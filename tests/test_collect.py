"""Tests de la brique collect, sans réseau et sans toucher aux vrais fichiers de data/.

Lancer depuis le dossier radar :  python3 -m unittest discover -s tests -v
"""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stdout
from datetime import date, timedelta
from email.message import Message
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

VRAIS_FICHIERS = [Path(radar.FICHIER_ITEMS), Path(radar.FICHIER_PAGES), Path(radar.FICHIER_CONFIG)]
empreintes_avant = {}


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


def article_hn(ident, titre, url="https://exemple.org/article", cree="2026-10-28T09:28:30Z", texte=None):
    """Un résultat de l'API Algolia de Hacker News."""
    return {"objectID": ident, "title": titre, "url": url, "created_at": cree, "story_text": texte}


def faille_osv(ident, resume, publie="2024-09-10T19:41:04Z", details="", alias=()):
    """Une faille telle que la renvoie l'API OSV."""
    return {"id": ident, "summary": resume, "details": details, "published": publie, "aliases": list(alias)}


def entetes(valeurs=None):
    message = Message()
    for cle, valeur in (valeurs or {}).items():
        message[cle] = valeur
    return message


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


def source_hn(**modifs):
    source = {"type": "hackernews", "requete": "claude code", "nom": "Hacker News",
              "limite": 20, "type_veille": "technologique"}
    source.update(modifs)
    return source


def source_failles(**modifs):
    source = {"type": "failles", "paquet": "express", "ecosysteme": "npm", "version": "4.17.1",
              "nom": "Base OSV (failles connues)", "limite": 10, "type_veille": "securite"}
    source.update(modifs)
    return source


def source_page(**modifs):
    source = {"type": "page", "url": "https://www.anthropic.com/legal/aup",
              "nom": "Anthropic · Usage Policy", "type_veille": "reglementaire"}
    source.update(modifs)
    return source


class DossierTemporaire(unittest.TestCase):
    """Redirige config, items.json et pages.json vers un dossier temporaire,
    et interdit tout appel réseau réel (subprocess et urllib)."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.items = self.dossier / "data" / "items.json"
        self.pages = self.dossier / "data" / "pages.json"
        self.config = self.dossier / "radar.config.yaml"
        for nom, valeur in [("DOSSIER", self.dossier),
                            ("FICHIER_CONFIG", self.config),
                            ("FICHIER_ITEMS", self.items),
                            ("FICHIER_PAGES", self.pages)]:
            self.patcher(radar, nom, valeur)
        self.patcher(radar.subprocess, "run", side_effect=AssertionError("appel à gh interdit"))
        self.patcher(radar.urllib.request, "urlopen", side_effect=AssertionError("appel réseau interdit"))

    def patcher(self, cible, nom, valeur=mock.DEFAULT, **options):
        patch = mock.patch.object(cible, nom, valeur, **options)
        objet = patch.start()
        self.addCleanup(patch.stop)
        return objet


# --- La fiche ----------------------------------------------------------------

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

    def test_date_de_collecte_future(self):
        apres_demain = (date.today() + timedelta(days=2)).isoformat()
        self.assertFalse(radar.fiche_valide(fiche_ok(collecte_le=apres_demain)))
        self.assertTrue(radar.fiche_valide(fiche_ok(collecte_le=date.today().isoformat())))

    def test_url_sans_http_ni_https(self):
        for valeur in ["github.com/anthropics/claude-code", "ftp://exemple.org/a",
                       "https://", "http:/exemple.org", "https://exemple .org", "javascript:alert(1)"]:
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche_ok(url=valeur)))
        self.assertTrue(radar.fiche_valide(fiche_ok(url="http://exemple.org/a")))


# --- La configuration --------------------------------------------------------

class TestChargerConfig(DossierTemporaire):

    def charger(self, texte):
        self.config.write_text(texte, encoding="utf-8")
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            return radar.charger_config()

    def test_yaml_mal_forme(self):
        with self.assertRaises(SystemExit) as erreur:
            self.charger("mots_cles: [\"claude code\"\nsources: - { type: releases")
        self.assertIn("mal formé", str(erreur.exception.code))

    def test_config_qui_nest_pas_un_dictionnaire(self):
        with self.assertRaises(SystemExit) as erreur:
            self.charger("- une\n- liste\n")
        self.assertIn("clé: valeur", str(erreur.exception.code))

    def test_sources_qui_ne_sont_pas_une_liste_d_objets(self):
        for texte in ("sources: releases\n", "sources: [releases, page]\n"):
            with self.subTest(texte=texte):
                with self.assertRaises(SystemExit) as erreur:
                    self.charger(texte)
                self.assertIn("sources", str(erreur.exception.code))

    def test_config_valide_et_fichier_vide(self):
        self.assertEqual(self.charger("mots_cles: [codex]\nsources: []\n")["mots_cles"], ["codex"])
        self.assertEqual(self.charger(""), {})


# --- Validation d'une source, avant tout appel réseau ------------------------

class TestValiderSource(unittest.TestCase):

    def test_limite_par_defaut_et_valide(self):
        source = source_releases()
        del source["limite"]
        self.assertEqual(radar.valider_source(source, "depot"), 10)
        self.assertEqual(radar.valider_source(source_releases(limite=100), "depot"), 100)

    def test_limite_invalide(self):
        for valeur in (0, -1, 101, "10", True, 2.5, None):
            with self.subTest(valeur=valeur):
                with self.assertRaises(radar.ErreurSource) as erreur:
                    radar.valider_source(source_releases(limite=valeur), "depot")
                self.assertIn("limite", str(erreur.exception))

    def test_type_veille_invalide(self):
        with self.assertRaises(radar.ErreurSource) as erreur:
            radar.valider_source(source_releases(type_veille="tech"), "depot")
        self.assertIn("type_veille « tech » inconnu", str(erreur.exception))

    def test_type_veille_absent_autorise(self):
        source = source_releases()
        del source["type_veille"]
        self.assertEqual(radar.valider_source(source, "depot"), 10)

    def test_champ_requis_manquant_pour_chaque_type(self):
        cas = [(source_releases, "depot", radar.collecter_releases, "gh_api"),
               (source_hn, "requete", radar.collecter_hackernews, "http_json"),
               (source_failles, "paquet", radar.collecter_failles, "http_json"),
               (source_failles, "ecosysteme", radar.collecter_failles, "http_json"),
               (source_page, "url", radar.collecter_page, "http")]
        for fabrique, champ, collecteur, appel_reseau in cas:
            with self.subTest(champ=champ, collecteur=collecteur.__name__):
                source = fabrique()
                del source[champ]
                with mock.patch.object(radar, appel_reseau) as faux_reseau:
                    with self.assertRaises(radar.ErreurSource) as erreur:
                        collecteur(source)
                    faux_reseau.assert_not_called()
                self.assertIn(f"champ « {champ} » manquant", str(erreur.exception))

    def test_source_invalide_aucun_appel_reseau(self):
        cas = [(source_releases, radar.collecter_releases, "gh_api"),
               (source_hn, radar.collecter_hackernews, "http_json"),
               (source_failles, radar.collecter_failles, "http_json"),
               (source_page, radar.collecter_page, "http")]
        for fabrique, collecteur, appel_reseau in cas:
            for modif in ({"type_veille": "tech"}, {"limite": 0}, {"nom": ""}):
                with self.subTest(collecteur=collecteur.__name__, modif=modif):
                    with mock.patch.object(radar, appel_reseau) as faux_reseau:
                        with self.assertRaises(radar.ErreurSource):
                            collecteur(fabrique(**modif))
                        faux_reseau.assert_not_called()


# --- Les appels réseau -------------------------------------------------------

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


class FausseReponseHttp:
    """Remplace la réponse de urllib.request.urlopen."""

    def __init__(self, corps, valeurs_entetes=None):
        self.corps = corps
        self.headers = entetes(valeurs_entetes or {"Content-Type": "text/html; charset=utf-8"})

    def read(self):
        return self.corps

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestHttp(unittest.TestCase):
    """http() et http_json() : urlopen est simulé, aucun appel réseau réel."""

    def test_get_avec_agent_et_delai(self):
        with mock.patch.object(radar.urllib.request, "urlopen",
                               return_value=FausseReponseHttp("Café".encode("utf-8"))) as faux:
            texte, _ = radar.http("https://exemple.org/page")
        requete = faux.call_args.args[0]
        self.assertEqual(texte, "Café")
        self.assertEqual(requete.get_method(), "GET")
        self.assertEqual(requete.full_url, "https://exemple.org/page")
        self.assertEqual(requete.get_header("User-agent"), radar.AGENT_HTTP)
        self.assertEqual(faux.call_args.kwargs["timeout"], radar.DELAI_HTTP)

    def test_post_json(self):
        reponse = FausseReponseHttp(b'{"vulns": []}', {"Content-Type": "application/json"})
        with mock.patch.object(radar.urllib.request, "urlopen", return_value=reponse) as faux:
            resultat = radar.http_json("https://api.exemple.org/q", {"package": {"name": "express"}})
        requete = faux.call_args.args[0]
        self.assertEqual(resultat, {"vulns": []})
        self.assertEqual(requete.get_method(), "POST")
        self.assertEqual(json.loads(requete.data), {"package": {"name": "express"}})
        self.assertEqual(requete.get_header("Content-type"), "application/json")

    def test_jeu_de_caracteres_annonce(self):
        reponse = FausseReponseHttp("Sécurité".encode("latin-1"), {"Content-Type": "text/html; charset=iso-8859-1"})
        with mock.patch.object(radar.urllib.request, "urlopen", return_value=reponse):
            texte, _ = radar.http("https://exemple.org")
        self.assertEqual(texte, "Sécurité")

    def test_erreur_http(self):
        erreur = urllib.error.HTTPError("https://exemple.org", 403, "Forbidden", entetes(), None)
        with mock.patch.object(radar.urllib.request, "urlopen", side_effect=erreur):
            with self.assertRaises(radar.ErreurSource) as e:
                radar.http("https://exemple.org")
        self.assertIn("HTTP 403", str(e.exception))

    def test_reseau_injoignable(self):
        for panne in (urllib.error.URLError("nodename nor servname provided"), TimeoutError("timed out")):
            with self.subTest(panne=panne):
                with mock.patch.object(radar.urllib.request, "urlopen", side_effect=panne):
                    with self.assertRaises(radar.ErreurSource) as e:
                        radar.http("https://exemple.org")
                self.assertIn("impossible de joindre", str(e.exception))

    def test_http_json_reponse_non_json(self):
        with mock.patch.object(radar.urllib.request, "urlopen", return_value=FausseReponseHttp(b"<html>")):
            with self.assertRaises(radar.ErreurSource) as e:
                radar.http_json("https://exemple.org")
        self.assertIn("pas du JSON", str(e.exception))


# --- Les collecteurs ---------------------------------------------------------

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

    def test_reponse_github_mal_structuree(self):
        for reponse in ({"message": "Not Found"}, [release("v1"), "pas un objet"], None, "texte"):
            with self.subTest(reponse=reponse):
                with mock.patch.object(radar, "gh_api", return_value=reponse):
                    with self.assertRaises(radar.ErreurSource) as e:
                        radar.collecter_releases(source_releases())
                self.assertIn("réponse inattendue de GitHub", str(e.exception))


class TestCollecterHackernews(unittest.TestCase):

    def test_fiches_et_parametres_de_recherche(self):
        reponse = {"hits": [
            article_hn("1", "DeltaDB now has a Claude Code plugin", url="https://delta.dev/blog"),
            article_hn("2", "Ask HN: Claude Code ou Codex ?", url=None, texte="Votre avis ?"),
        ]}
        with mock.patch.object(radar, "http_json", return_value=reponse) as faux:
            fiches = radar.collecter_hackernews(source_hn(limite=7))
        adresse = urllib.parse.urlsplit(faux.call_args.args[0])
        self.assertEqual(f"{adresse.scheme}://{adresse.netloc}{adresse.path}", radar.API_HACKERNEWS)
        self.assertEqual(urllib.parse.parse_qs(adresse.query),
                         {"query": ["claude code"], "tags": ["story"], "hitsPerPage": ["7"]})
        (lien, _), (ask, texte_ask) = fiches
        self.assertEqual(lien["url"], "https://delta.dev/blog")
        self.assertEqual(lien["publie_le"], "2026-10-28")
        self.assertEqual(lien["source"], "Hacker News")
        self.assertEqual(lien["type_veille"], "technologique")
        self.assertEqual(ask["url"], "https://news.ycombinator.com/item?id=2")  # pas de lien externe
        self.assertEqual(texte_ask, "Votre avis ?")
        self.assertTrue(all(radar.fiche_valide(f) for f, _ in fiches))

    def test_article_sans_url_ni_identifiant_rejete(self):
        with mock.patch.object(radar, "http_json", return_value={"hits": [article_hn(None, "Sans lien", url=None)]}):
            [(fiche, _)] = radar.collecter_hackernews(source_hn())
        self.assertFalse(radar.fiche_valide(fiche))

    def test_reponse_mal_structuree(self):
        for reponse in ([], {"hits": "rien"}, {"hits": [article_hn("1", "ok"), 42]}, {}):
            with self.subTest(reponse=reponse):
                with mock.patch.object(radar, "http_json", return_value=reponse):
                    with self.assertRaises(radar.ErreurSource):
                        radar.collecter_hackernews(source_hn())


class TestCollecterFailles(unittest.TestCase):

    def test_requete_osv_et_fiches(self):
        reponse = {"vulns": [
            faille_osv("GHSA-rv95-896h-c2vc", "Express.js Open Redirect", publie="2024-03-25T19:40:26Z"),
            faille_osv("GHSA-qw6h-vgh9-j6wx", "express vulnerable to XSS", alias=["CVE-2024-43796"]),
        ]}
        with mock.patch.object(radar, "http_json", return_value=reponse) as faux:
            fiches = radar.collecter_failles(source_failles())
        faux.assert_called_once_with(radar.API_OSV, {
            "package": {"name": "express", "ecosystem": "npm"}, "version": "4.17.1"})
        (recente, texte), (ancienne, _) = fiches  # triées de la plus récente à la plus ancienne
        self.assertEqual(recente["titre"], "express · GHSA-qw6h-vgh9-j6wx : express vulnerable to XSS")
        self.assertEqual(recente["url"], "https://osv.dev/vulnerability/GHSA-qw6h-vgh9-j6wx")
        self.assertEqual(recente["publie_le"], "2024-09-10")
        self.assertEqual(recente["type_veille"], "securite")
        self.assertIn("CVE-2024-43796", texte)
        self.assertEqual(ancienne["publie_le"], "2024-03-25")
        self.assertTrue(all(radar.fiche_valide(f) for f, _ in fiches))

    def test_sans_version_et_limite(self):
        source = source_failles(limite=1)
        del source["version"]
        reponse = {"vulns": [faille_osv("A", "a", publie="2020-01-01T00:00:00Z"),
                             faille_osv("B", "b", publie="2025-01-01T00:00:00Z")]}
        with mock.patch.object(radar, "http_json", return_value=reponse) as faux:
            fiches = radar.collecter_failles(source)
        self.assertNotIn("version", faux.call_args.args[1])
        self.assertEqual([f["titre"] for f, _ in fiches], ["express · B : b"])

    def test_aucune_faille_connue(self):
        with mock.patch.object(radar, "http_json", return_value={}):
            self.assertEqual(radar.collecter_failles(source_failles()), [])

    def test_version_non_texte_refusee_avant_le_reseau(self):
        with mock.patch.object(radar, "http_json") as faux:
            with self.assertRaises(radar.ErreurSource) as e:
                radar.collecter_failles(source_failles(version=4.17))  # YAML sans guillemets
            faux.assert_not_called()
        self.assertIn("guillemets", str(e.exception))

    def test_reponse_mal_structuree(self):
        for reponse in ([], {"vulns": "aucune"}, {"vulns": [faille_osv("A", "a"), "B"]}):
            with self.subTest(reponse=reponse):
                with mock.patch.object(radar, "http_json", return_value=reponse):
                    with self.assertRaises(radar.ErreurSource):
                        radar.collecter_failles(source_failles())


PAGE_V1 = """<html><head><title>Usage Policy \\ Anthropic</title><style>p{color:red}</style></head>
<body><script>var secret = "claude code";</script><p>Effective Nov 12, 2026.</p>
<p>Users of Claude Code must follow this policy.</p></body></html>"""
PAGE_V2 = PAGE_V1.replace("must follow", "shall follow")


class TestCollecterPage(DossierTemporaire):

    def lire(self, html, valeurs_entetes=None, **modifs):
        with mock.patch.object(radar, "http", return_value=(html, entetes(valeurs_entetes))) as faux:
            [(fiche, texte)] = radar.collecter_page(source_page(**modifs))
        faux.assert_called_once()
        return fiche, texte

    def test_premiere_lecture(self):
        fiche, texte = self.lire(PAGE_V1, {"Last-Modified": "Tue, 27 Oct 2026 08:00:00 GMT"})
        self.assertNotIn("secret", texte)        # scripts ignorés
        self.assertNotIn("color:red", texte)     # styles ignorés
        self.assertIn("Users of Claude Code must follow this policy.", texte)
        self.assertEqual(fiche["publie_le"], "2026-10-27")   # date du serveur
        self.assertEqual(fiche["titre"], "Usage Policy \\ Anthropic (version du 2026-10-27)")
        self.assertEqual(fiche["source"], "Anthropic · Usage Policy")
        self.assertEqual(fiche["type_veille"], "reglementaire")
        self.assertRegex(fiche["url"], r"^https://www\.anthropic\.com/legal/aup#empreinte-[0-9a-f]{12}$")
        self.assertTrue(radar.fiche_valide(fiche))
        cache = json.loads(self.pages.read_text(encoding="utf-8"))["https://www.anthropic.com/legal/aup"]
        self.assertEqual(cache["empreinte"], hashlib.sha256(texte.encode("utf-8")).hexdigest())
        self.assertEqual(cache["vue_le"], date.today().isoformat())

    def test_meme_version_garde_sa_date_de_premiere_lecture(self):
        premiere, _ = self.lire(PAGE_V1)
        self.assertEqual(premiere["publie_le"], date.today().isoformat())  # pas de Last-Modified
        cache = json.loads(self.pages.read_text(encoding="utf-8"))
        cache["https://www.anthropic.com/legal/aup"]["vue_le"] = "2026-10-01"
        self.pages.write_text(json.dumps(cache), encoding="utf-8")
        seconde, _ = self.lire(PAGE_V1)
        self.assertEqual(seconde["url"], premiere["url"])      # même version → même url (dédupliquée)
        self.assertEqual(seconde["publie_le"], "2026-10-01")   # date réelle de 1re lecture

    def test_nouvelle_version_nouvelle_fiche(self):
        v1, _ = self.lire(PAGE_V1)
        v2, _ = self.lire(PAGE_V2)
        self.assertNotEqual(v1["url"], v2["url"])

    def test_fragment_retire_de_l_url_suivie(self):
        fiche, _ = self.lire(PAGE_V1, url="https://www.anthropic.com/legal/aup#section-2")
        self.assertRegex(fiche["url"], r"^https://www\.anthropic\.com/legal/aup#empreinte-")

    def test_page_vide_ou_en_javascript(self):
        with mock.patch.object(radar, "http", return_value=("<html><script>app()</script></html>", entetes())):
            with self.assertRaises(radar.ErreurSource):
                radar.collecter_page(source_page())

    def test_url_invalide_refusee_avant_le_reseau(self):
        for url in ("<url des CGU d'un éditeur d'IA>", "www.anthropic.com/legal/aup"):
            with self.subTest(url=url):
                with mock.patch.object(radar, "http") as faux:
                    with self.assertRaises(radar.ErreurSource):
                        radar.collecter_page(source_page(url=url))
                    faux.assert_not_called()

    def test_cache_abime_reconstruit(self):
        self.pages.parent.mkdir(parents=True, exist_ok=True)
        self.pages.write_text("{ pas du json", encoding="utf-8")
        fiche, _ = self.lire(PAGE_V1)
        self.assertTrue(radar.fiche_valide(fiche))
        self.assertIn("https://www.anthropic.com/legal/aup", json.loads(self.pages.read_text(encoding="utf-8")))


# --- La commande collect de bout en bout -------------------------------------

class TestCommandeCollect(DossierTemporaire):
    """radar collect de bout en bout, dans un dossier temporaire, réseau simulé."""

    def ecrire_config(self, sources, mots_cles=("claude code",), ignorer=("crypto",)):
        config = {"mots_cles": list(mots_cles), "ignorer": list(ignorer), "sources": sources}
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    def collecter(self, releases=(), hackernews=None, osv=None, page=None):
        def faux_http_json(url, donnees=None):
            return osv if url == radar.API_OSV else hackernews
        self.faux_gh = self.patcher(radar, "gh_api", return_value=list(releases))
        self.patcher(radar, "http_json", side_effect=faux_http_json)
        self.patcher(radar, "http", return_value=(page, entetes()))
        sortie = io.StringIO()
        with redirect_stdout(sortie):
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
        # Changé à la passe 1 : la faute est signalée AVANT l'appel réseau (avant : « 2 rejetées »).
        self.ecrire_config([source_releases(type_veille="tech")])
        items, sortie = self.collecter([release("v1"), release("v2")])
        self.assertEqual(items, [])
        self.assertIn("type_veille « tech » inconnu", sortie)
        self.faux_gh.assert_not_called()

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
        # Changé à la passe 1 : hackernews est géré, on teste un type inconnu.
        self.ecrire_config([source_releases(), {"type": "inconnu", "nom": "X", "requete": "claude code"}])
        _, sortie = self.collecter([release("v1")])
        self.assertIn("inconnu · claude code : NON COLLECTÉE", sortie)
        self.assertEqual(set(radar.COLLECTEURS), {"releases", "hackernews", "failles", "page"})

    def test_les_cinq_sources_du_plan(self):
        self.ecrire_config(
            [source_releases(), source_releases(depot="openai/codex", produit="Codex CLI"),
             source_hn(), source_failles(), source_page()],
            mots_cles=("claude code", "codex", "express"),
        )
        arguments = dict(
            releases=[release("v1"), release("v2", depot="openai/codex")],
            hackernews={"hits": [article_hn("9", "Claude Code plugin"), article_hn("8", "Show HN: voyages")]},
            osv={"vulns": [faille_osv("GHSA-1", "express vulnerable to XSS")]},
            page=PAGE_V1,
        )
        items, sortie = self.collecter(**arguments)
        self.assertNotIn("NON COLLECTÉE", sortie)
        self.assertNotIn("❌", sortie)
        par_source = {}
        for item in items:
            par_source.setdefault(item["source"], []).append(item)
        self.assertEqual(set(par_source), {"Dépôt GitHub officiel", "Hacker News",
                                           "Base OSV (failles connues)", "Anthropic · Usage Policy"})
        self.assertEqual([i["titre"] for i in par_source["Hacker News"]], ["Claude Code plugin"])  # filtre
        self.assertEqual(par_source["Base OSV (failles connues)"][0]["type_veille"], "securite")
        self.assertEqual(par_source["Anthropic · Usage Policy"][0]["type_veille"], "reglementaire")
        self.assertTrue(all(radar.fiche_valide(i) for i in items))

        # Deuxième collecte identique : rien de nouveau (même version de page, mêmes urls).
        _, sortie = self.collecter(**arguments)
        self.assertIn("\n0 nouvelles infos", sortie)


if __name__ == "__main__":
    unittest.main()
