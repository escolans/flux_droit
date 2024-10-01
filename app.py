# Importation des modules nécessaires pour l'application
from flask import Flask, render_template, request, flash, abort  # Flask pour gérer les routes web, flash pour afficher des messages d'erreur, abort pour gérer les erreurs HTTP
import feedparser  # Module pour analyser et récupérer les flux RSS
import json  # Module pour manipuler des fichiers JSON
from bs4 import BeautifulSoup  # BeautifulSoup pour extraire et nettoyer le HTML des descriptions
from dateutil import parser as date_parser  # Pour analyser et formater les dates des articles RSS
from cachetools import TTLCache  # Pour gérer un cache avec une durée de vie limitée (TTL)
import os  # Pour accéder aux variables d'environnement, utile pour les configurations de port
import requests  # Pour effectuer des requêtes HTTP (comme récupérer des flux RSS externes)
import logging  # Pour ajouter des logs

# Initialisation de l'application Flask avec le dossier des templates
app = Flask(__name__, template_folder='.')

# Utilisation d'une clé secrète plus sécurisée, chargée depuis une variable d'environnement (meilleure pratique pour la sécurité)
app.secret_key = os.environ.get('SECRET_KEY', 'defaultsecretkey')

# Création d'un cache en mémoire avec un TTL de 10 minutes et une taille maximale de 100 éléments
cache = TTLCache(maxsize=100, ttl=600)

# Configuration de la journalisation (log) pour capturer les erreurs et événements importants
logging.basicConfig(level=logging.INFO)

# Fonction pour charger les sources RSS à partir d'un fichier JSON appelé "sources.json"
def load_sources():
    try:
        # Ouvre le fichier JSON contenant les sources RSS avec l'encodage UTF-8
        with open('sources.json', 'r', encoding='utf-8') as file:
            # Charge les données JSON dans une variable Python
            data = json.load(file)
        # Vérifie si le fichier JSON contient bien une clé 'sources'
        if 'sources' not in data:
            logging.error("'sources' manquant dans le fichier JSON.")
            raise KeyError("'sources' manquant dans le fichier JSON.")
        # Retourne uniquement la partie "sources" du fichier JSON
        return data['sources']
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Gère les erreurs liées à la lecture du fichier JSON (fichier manquant ou mal formé)
        logging.error(f"Erreur lors du chargement des sources RSS : {e}")
        abort(500, description="Erreur de configuration des flux RSS. Contactez l'administrateur.")

# Chargement des sources RSS au démarrage de l'application dans une variable globale
RSS_FEEDS = load_sources()

# Fonction pour récupérer un flux RSS depuis une URL et le mettre en cache
def fetch_feed(url):
    if not url:
        logging.error("URL vide ou invalide pour récupérer le flux RSS.")
        return None  # Retourne None en cas d'URL invalide

    # Vérifie si l'URL est déjà présente dans le cache
    if url in cache:
        logging.info(f"Chargement du cache pour {url}")  # Log pour indiquer que le cache est utilisé
        return cache[url]  # Retourne le flux directement depuis le cache
    
    logging.info(f"Récupération du flux RSS depuis {url}")  # Log pour indiquer la récupération des données via HTTP
    try:
        # Effectue une requête HTTP GET avec un timeout de 10 secondes
        response = requests.get(url, timeout=10)
        # Vérifie si la requête a échoué en fonction du code de statut HTTP
        response.raise_for_status()  # Lève une exception si le code HTTP n'est pas 200
        # Analyse le contenu du flux RSS récupéré
        feed = feedparser.parse(response.content)
    except requests.exceptions.Timeout:
        # Gère l'exception en cas de timeout (le serveur a pris trop de temps à répondre)
        logging.error(f"Le flux RSS de {url} a pris trop de temps à répondre.")
        flash(f"Le flux de {url} est indisponible pour l'instant. Essayez plus tard.")
        return None
    except requests.exceptions.HTTPError as e:
        # Gère les erreurs HTTP (comme les erreurs 404 ou 500)
        logging.error(f"Erreur HTTP lors de la récupération du flux RSS de {url}: {e}")
        flash(f"Erreur HTTP lors de la récupération du flux de {url}.")
        return None
    except requests.exceptions.RequestException as e:
        # Gère toute autre erreur liée à la requête HTTP
        logging.error(f"Erreur lors de la récupération du flux RSS de {url}: {e}")
        flash(f"Impossible de récupérer le flux de {url}.")
        return None

    # Vérifie que le flux contient bien des articles
    if not feed or not feed.entries:
        logging.warning(f"Aucun article trouvé pour le flux {url}")
        flash(f"Le flux de {url} ne contient actuellement aucun article.")
        return None
    else:
        # Affiche le nombre d'articles trouvés dans le flux
        logging.info(f"{len(feed.entries)} articles trouvés pour {url}")
    
    # Met en cache le flux récupéré pour des requêtes futures
    cache[url] = feed
    return feed  # Retourne le flux RSS analysé

# Fonction pour extraire l'URL de l'image d'un article, s'il y en a une
def extract_image(entry):
    try:
        # Vérifie si l'article contient une vignette ("media_thumbnail")
        if 'media_thumbnail' in entry:
            return entry.media_thumbnail[0]['url']  # Retourne l'URL de la première vignette trouvée
        # Sinon, vérifie s'il contient une image dans "media_content"
        elif 'media_content' in entry:
            return entry.media_content[0]['url']  # Retourne l'URL de la première image trouvée
        # Sinon, recherche un lien d'image dans "links"
        elif 'links' in entry:
            # Parcourt les liens de l'article pour trouver une image
            for link in entry.links:
                if 'image' in link.type:  # Vérifie si le lien est de type image
                    return link.href  # Retourne l'URL de l'image
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction de l'image : {e}")
    return None  # Retourne None si aucune image n'est trouvée

# Fonction pour extraire et nettoyer la description d'un article RSS
def extract_description(entry):
    try:
        # Vérifie si l'article contient un résumé (summary) et qu'il n'est pas vide
        if 'summary' in entry and entry.summary:
            # Utilise BeautifulSoup pour nettoyer le HTML de la description et limite à 150 caractères
            return BeautifulSoup(entry.summary, 'html.parser').text[:150] + '...'
    except Exception as e:
        # Gère les erreurs de parsing du HTML et retourne une description par défaut en cas d'erreur
        logging.error(f"Erreur lors du parsing de la description : {e}")
    # Si aucune description n'est disponible, retourne un message par défaut
    return "Pas de description disponible."

# Fonction pour analyser et formater la date de publication d'un article
def parse_date(entry):
    try:
        # Vérifie si l'article contient une date de publication dans le champ "published"
        if 'published' in entry:
            return date_parser.parse(entry.published).strftime('%d %B %Y %H:%M')  # Formate la date
        # Sinon, utilise le champ "pubDate" comme alternative
        elif 'pubDate' in entry:
            return date_parser.parse(entry.pubDate).strftime('%d %B %Y %H:%M')  # Formate la date
    except (AttributeError, ValueError) as e:
        # Gère les erreurs liées à l'absence ou à l'invalidité des dates et retourne une valeur par défaut
        logging.error(f"Erreur lors de l'analyse de la date : {e}")
        return 'Date inconnue'

# Fonction pour vérifier si un article est valide (exclut les images et les articles sans titre)
def is_valid_article(entry):
    # Récupère le titre de l'article, ou une chaîne vide si absent
    title = entry.get('title', '')
    # Ignore les articles qui n'ont pas de titre ou dont le titre correspond à une image (.jpg, .png, .gif)
    if not title or title.lower().endswith(('.jpg', '.png', '.gif')):
        logging.info(f"Article ignoré: {title}")  # Log pour les articles ignorés
        return False  # Retourne False pour indiquer que l'article est invalide
    return True  # Retourne True si l'article est valide

# Route principale qui gère l'affichage des articles dans la page HTML
@app.route('/')
def index():
    # Récupère la catégorie sélectionnée par l'utilisateur via un paramètre d'URL, ou affiche "Tous" par défaut
    selected_category = request.args.get('category', 'Tous')

    # Vérifie la validité de la catégorie (pour éviter toute injection malveillante ou valeur incorrecte)
    if selected_category not in ['Tous'] + [source['category'] for source in RSS_FEEDS]:
        logging.warning(f"Catégorie invalide sélectionnée : {selected_category}")
        abort(400, description="Catégorie invalide.")

    # Initialise une liste vide pour stocker les articles à afficher
    articles = []

    # Parcourt toutes les sources RSS définies dans le fichier JSON
    for source in RSS_FEEDS:
        # Si une catégorie est sélectionnée, ne prend en compte que les articles de cette catégorie
        if selected_category != 'Tous' and source['category'] != selected_category:
            continue

        # Récupère le flux RSS de la source, avec mise en cache
        feed = fetch_feed(source['url'])
        if not feed:  # Si le flux est None (échec), passe à la source suivante
            continue

        # Parcourt chaque article du flux RSS récupéré
        for entry in feed.entries:
            if not is_valid_article(entry):  # Vérifie si l'article est valide
                continue

            # Crée un dictionnaire contenant les informations de l'article
            article = {
                'title': entry.title,  # Titre de l'article
                'link': entry.link,  # Lien vers l'article complet
                'published': parse_date(entry),  # Date de publication formatée
                'source': source['name'],  # Nom de la source (site)
                'category': source['category'],  # Catégorie de l'article
                'image': extract_image(entry),  # URL de l'image (si disponible)
                'description': extract_description(entry)  # Description de l'article
            }
            # Ajoute l'article à la liste des articles à afficher
            articles.append(article)

    # Si aucun article n'est trouvé, affiche un message d'erreur à l'utilisateur
    if not articles:
        logging.warning(f"Aucun article trouvé pour la catégorie '{selected_category}'")
        flash(f"Aucun article disponible pour la catégorie '{selected_category}'.")

    # Trie les articles par date de publication, du plus récent au plus ancien
    articles.sort(key=lambda x: x['published'] if x['published'] and x['published'] != 'Date inconnue' else '', reverse=True)

    # Génère une liste de catégories disponibles pour le menu de filtrage
    categories = ['Tous'] + sorted({source['category'] for source in RSS_FEEDS})

    # Retourne le rendu de la page HTML avec les articles et catégories disponibles
    return render_template('index.html', articles=articles, categories=categories, selected_category=selected_category)

# Point d'entrée principal pour démarrer l'application Flask
if __name__ == '__main__':
    # Récupère le port depuis les variables d'environnement, ou utilise 5000 par défaut si non défini
    try:
        port = int(os.environ.get('PORT', 5000))
    except ValueError as e:
        logging.error(f"Erreur lors de la récupération du port : {e}")
        port = 5000  # Valeur par défaut si l'environnement ne définit pas correctement le port
    # Démarre l'application Flask sur l'adresse 0.0.0.0 et le port défini
    app.run(host='0.0.0.0', port=port)
