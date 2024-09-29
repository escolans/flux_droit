from flask import Flask, render_template, request, flash  # Importation des modules nécessaires de Flask
import feedparser  # Module pour analyser les flux RSS
import json  # Module pour manipuler des fichiers JSON
from bs4 import BeautifulSoup  # Pour extraire et nettoyer le texte HTML des descriptions
from dateutil import parser as date_parser  # Pour analyser et formater les dates des flux RSS
from cachetools import TTLCache  # Pour gérer le cache avec une durée de vie
import os  # Pour accéder aux variables d'environnement

# Initialisation de l'application Flask avec le dossier des templates défini
app = Flask(__name__, template_folder='.')
app.secret_key = 'supersecretkey'  # Clé secrète nécessaire pour les messages flash

# Création d'un cache avec une taille maximale de 100 entrées et une durée de vie de 10 minutes
cache = TTLCache(maxsize=100, ttl=600)

# Fonction pour charger les sources RSS depuis un fichier JSON
def load_sources():
    with open('sources.json', 'r', encoding='utf-8') as file:  # Ouvre le fichier sources.json
        data = json.load(file)  # Charge les données JSON
    return data['sources']  # Retourne la liste des sources

# Chargement des sources depuis le fichier JSON au démarrage de l'application
RSS_FEEDS = load_sources()

# Fonction pour récupérer un flux RSS en le mettant en cache pour éviter des requêtes répétées
def fetch_feed(url):
    if url in cache:  # Vérifie si le flux est déjà en cache
        print(f"Chargement du cache pour {url}")
        return cache[url]  # Retourne le flux depuis le cache
    print(f"Récupération du flux RSS depuis {url}")
    feed = feedparser.parse(url)  # Analyse le flux RSS à partir de l'URL fournie
    if not feed.entries:  # Vérifie s'il y a des articles dans le flux
        print(f"Aucun article trouvé pour le flux {url}")
        flash(f"Le flux de {url} ne contient actuellement aucun article.")  # Alerte si aucun article
    else:
        print(f"{len(feed.entries)} articles trouvés pour {url}")
    cache[url] = feed  # Ajoute le flux au cache
    return feed  # Retourne le flux récupéré

# Fonction pour extraire l'URL d'une image d'un article si disponible
def extract_image(entry):
    # Recherche dans les différentes balises possibles pour une image
    if 'media_thumbnail' in entry:
        return entry.media_thumbnail[0]['url']
    elif 'media_content' in entry:
        return entry.media_content[0]['url']
    elif 'links' in entry:
        for link in entry.links:
            if 'image' in link.type:
                return link.href
    return None  # Retourne None si aucune image n'est trouvée

# Fonction pour extraire et nettoyer la description de l'article
def extract_description(entry):
    if 'summary' in entry:  # Vérifie si l'article a un résumé
        return BeautifulSoup(entry.summary, 'html.parser').text[:150] + '...'  # Limite à 150 caractères
    return "Pas de description disponible."

# Fonction pour analyser et formater la date de publication d'un article
def parse_date(entry):
    try:
        if 'published' in entry:  # Vérifie s'il y a une date de publication
            return date_parser.parse(entry.published).strftime('%d %B %Y %H:%M')
        elif 'pubDate' in entry:  # Vérifie une autre balise de date
            return date_parser.parse(entry.pubDate).strftime('%d %B %Y %H:%M')
    except (AttributeError, ValueError):  # Gère les erreurs possibles
        return 'Date inconnue'

# Fonction pour vérifier si un article est valide (par exemple, exclure les images)
def is_valid_article(entry):
    title = entry.get('title', '')  # Récupère le titre de l'article
    # Ignore les articles sans titre ou ayant des titres correspondant à des images
    if not title or title.lower().endswith(('.jpg', '.png', '.gif')):
        print(f"Article ignoré: {title}")
        return False
    return True

# Route principale de l'application qui gère l'affichage des articles
@app.route('/')
def index():
    selected_category = request.args.get('category', 'Tous')  # Récupère la catégorie sélectionnée
    articles = []  # Initialise la liste des articles à afficher

    # Parcours chaque source RSS
    for source in RSS_FEEDS:
        # Filtre par catégorie si une catégorie spécifique est sélectionnée
        if selected_category != 'Tous' and source['category'] != selected_category:
            continue

        feed = fetch_feed(source['url'])  # Récupère et analyse le flux RSS
        # Parcours chaque article du flux
        for entry in feed.entries:
            if not is_valid_article(entry):  # Vérifie si l'article est valide
                continue

            # Crée un dictionnaire avec les informations de l'article
            article = {
                'title': entry.title,
                'link': entry.link,
                'published': parse_date(entry),
                'source': source['name'],
                'category': source['category'],
                'image': extract_image(entry),
                'description': extract_description(entry)
            }
            articles.append(article)  # Ajoute l'article à la liste

    # Affiche un message si aucun article n'est trouvé
    if not articles:
        flash(f"Aucun article disponible pour la catégorie '{selected_category}'. Vérifiez si les flux sont actifs ou nécessitent un accès particulier.")

    # Tri les articles par date de publication, en traitant les dates manquantes
    articles.sort(key=lambda x: x['published'] if x['published'] and x['published'] != 'Date inconnue' else '', reverse=True)

    # Récupère les catégories uniques des sources pour le menu
    categories = ['Tous'] + sorted({source['category'] for source in RSS_FEEDS})

    # Génère la page HTML avec les articles et les catégories disponibles
    return render_template('index.html', articles=articles, categories=categories, selected_category=selected_category)

# Point d'entrée principal pour lancer l'application Flask
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))  # Utilise le port défini par Render ou 5001 par défaut
    app.run(host='0.0.0.0', port=port)  # Démarre l'application sur tous les hôtes disponibles
