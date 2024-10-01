# Importation des modules nécessaires pour l'application
from flask import Flask, render_template, request, flash  # Flask pour gérer l'application web, flash pour les messages d'erreur
import feedparser  # Pour analyser les flux RSS
import json  # Pour manipuler et lire les fichiers JSON
from bs4 import BeautifulSoup  # Pour parser et nettoyer le HTML des descriptions
from dateutil import parser as date_parser  # Pour analyser et formater les dates des articles RSS
from cachetools import TTLCache  # Pour mettre en cache les flux RSS afin d'améliorer les performances
import os  # Pour accéder aux variables d'environnement
import requests  # Pour effectuer des requêtes HTTP pour récupérer les flux RSS


# Initialisation de l'application Flask, avec le template_folder spécifié à la racine
app = Flask(__name__, template_folder='.')

# Clé secrète pour la gestion des messages "flash", nécessaire pour afficher les messages dans Flask
app.secret_key = 'supersecretkey'

# Création d'un cache en mémoire avec une capacité de 100 entrées et une durée de vie de 10 minutes
cache = TTLCache(maxsize=100, ttl=600)

# Fonction pour charger les sources RSS depuis un fichier JSON (sources.json)
def load_sources():
    # Ouvre le fichier JSON contenant les sources RSS
    with open('sources.json', 'r', encoding='utf-8') as file:
        # Charge les données JSON dans une variable Python
        data = json.load(file)
    # Retourne uniquement la partie "sources" du fichier JSON
    return data['sources']

# Chargement des sources RSS au démarrage de l'application dans une variable globale
RSS_FEEDS = load_sources()

# Fonction pour récupérer un flux RSS depuis une URL, avec mise en cache pour éviter de solliciter le serveur inutilement
def fetch_feed(url):
    # Vérifie si le flux est déjà présent dans le cache
    if url in cache:
        print(f"Chargement du cache pour {url}")  # Log pour indiquer que le cache est utilisé
        return cache[url]  # Retourne le flux du cache
    print(f"Récupération du flux RSS depuis {url}")  # Log pour indiquer qu'on fait une requête vers l'URL
    try:
        # Récupère le contenu du flux RSS avec un timeout de 10 secondes
        response = requests.get(url, timeout=10)
        # Parse le flux RSS depuis le contenu récupéré
        feed = feedparser.parse(response.content)
    except requests.exceptions.Timeout:
        # En cas de timeout, affiche un message d'erreur et renvoie None
        print(f"Le flux RSS de {url} a pris trop de temps à répondre.")
        flash(f"Le flux de {url} est indisponible pour l'instant. Essayez plus tard.")
        return None
    except requests.exceptions.RequestException as e:
        # Gère toute autre erreur liée à la requête
        print(f"Erreur lors de la récupération du flux RSS de {url}: {e}")
        flash(f"Impossible de récupérer le flux de {url}.")
        return None

    # Si le flux n'a pas d'entrées (articles), avertit l'utilisateur
    if not feed.entries:
        print(f"Aucun article trouvé pour le flux {url}")
        flash(f"Le flux de {url} ne contient actuellement aucun article.")
    else:
        # Sinon, affiche le nombre d'articles trouvés
        print(f"{len(feed.entries)} articles trouvés pour {url}")
    
    # Ajoute le flux récupéré au cache pour des requêtes futures
    cache[url] = feed
    return feed  # Retourne le flux RSS analysé

# Fonction pour extraire l'URL de l'image d'un article s'il y en a une
def extract_image(entry):
    # Recherche dans les balises possibles où une image peut être stockée
    if 'media_thumbnail' in entry:
        return entry.media_thumbnail[0]['url']  # Retourne la première image trouvée
    elif 'media_content' in entry:
        return entry.media_content[0]['url']  # Retourne une autre version de l'image si présente
    elif 'links' in entry:
        # Parcourt les liens associés à l'article pour trouver une image
        for link in entry.links:
            if 'image' in link.type:
                return link.href  # Retourne l'URL de l'image si trouvée
    return None  # Retourne None si aucune image n'est trouvée

# Fonction pour extraire et nettoyer la description de l'article (limite à 150 caractères)
def extract_description(entry):
    # Vérifie si l'article contient un résumé ("summary")
    if 'summary' in entry:
        # Utilise BeautifulSoup pour nettoyer le HTML du résumé
        return BeautifulSoup(entry.summary, 'html.parser').text[:150] + '...'  # Limite à 150 caractères
    return "Pas de description disponible."  # Retourne un texte par défaut si aucune description n'est présente

# Fonction pour analyser et formater la date de publication d'un article
def parse_date(entry):
    try:
        # Vérifie si l'article contient une date de publication
        if 'published' in entry:
            return date_parser.parse(entry.published).strftime('%d %B %Y %H:%M')  # Formate la date
        elif 'pubDate' in entry:
            return date_parser.parse(entry.pubDate).strftime('%d %B %Y %H:%M')  # Alternative
    except (AttributeError, ValueError):
        return 'Date inconnue'  # Retourne une date par défaut en cas d'erreur

# Fonction pour vérifier si un article est valide (exclut les images ou contenus sans titre)
def is_valid_article(entry):
    # Récupère le titre de l'article ou une chaîne vide si absent
    title = entry.get('title', '')
    # Ignore les articles qui n'ont pas de titre ou qui sont des images (formats .jpg, .png, .gif)
    if not title or title.lower().endswith(('.jpg', '.png', '.gif')):
        print(f"Article ignoré: {title}")  # Log pour les articles ignorés
        return False  # Considère cet article comme invalide
    return True  # Considère l'article valide si aucun problème détecté

# Route principale qui gère l'affichage des articles dans la page HTML
@app.route('/')
def index():
    # Récupère la catégorie sélectionnée par l'utilisateur ou affiche "Tous" par défaut
    selected_category = request.args.get('category', 'Tous')
    
    # Liste qui contiendra tous les articles à afficher
    articles = []

    # Parcourt toutes les sources RSS définies dans le fichier JSON
    for source in RSS_FEEDS:
        # Si une catégorie est sélectionnée, filtre les sources par catégorie
        if selected_category != 'Tous' and source['category'] != selected_category:
            continue

        # Récupère le flux RSS de la source (avec mise en cache)
        feed = fetch_feed(source['url'])
        if not feed:  # Si le flux est None (échec), passe à la source suivante
            continue

        # Parcourt chaque article du flux RSS récupéré
        for entry in feed.entries:
            if not is_valid_article(entry):  # Vérifie si l'article est valide
                continue

            # Construit un dictionnaire contenant les informations de l'article
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

    # Si aucun article n'est trouvé, affiche un message d'erreur
    if not articles:
        flash(f"Aucun article disponible pour la catégorie '{selected_category}'. Vérifiez si les flux sont actifs ou nécessitent un accès particulier.")

    # Trie les articles par date de publication (du plus récent au plus ancien)
    articles.sort(key=lambda x: x['published'] if x['published'] and x['published'] != 'Date inconnue' else '', reverse=True)

    # Génère une liste de catégories disponibles pour le menu de filtrage
    categories = ['Tous'] + sorted({source['category'] for source in RSS_FEEDS})

    # Retourne le rendu de la page HTML avec les articles et catégories disponibles
    return render_template('index.html', articles=articles, categories=categories, selected_category=selected_category)

# Point d'entrée principal pour démarrer l'application Flask
if __name__ == '__main__':
    # Utilise le port défini par Render ou 5001 par défaut
    port = int(os.environ.get('PORT', 5001))
    # Démarre l'application Flask en mode production
    app.run(host='0.0.0.0', port=port)
