from flask import Flask, render_template, request, flash
import feedparser
import json
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from cachetools import TTLCache

# Initialisation de l'application Flask
app = Flask(__name__, template_folder='.')
app.secret_key = 'supersecretkey'  # Nécessaire pour utiliser flash messages

# Création du cache pour les flux RSS avec une durée de vie de 10 minutes
cache = TTLCache(maxsize=100, ttl=600)

# Fonction pour charger les sources depuis le fichier JSON
def load_sources():
    with open('sources.json', 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data['sources']

# Chargement des sources depuis le fichier JSON
RSS_FEEDS = load_sources()

def fetch_feed(url):
    if url in cache:
        print(f"Chargement du cache pour {url}")
        return cache[url]
    print(f"Récupération du flux RSS depuis {url}")
    feed = feedparser.parse(url)
    if not feed.entries:
        print(f"Aucun article trouvé pour le flux {url}")
        flash(f"Le flux de {url} ne contient actuellement aucun article.")
    else:
        print(f"{len(feed.entries)} articles trouvés pour {url}")
    cache[url] = feed
    return feed

def extract_image(entry):
    if 'media_thumbnail' in entry:
        return entry.media_thumbnail[0]['url']
    elif 'media_content' in entry:
        return entry.media_content[0]['url']
    elif 'links' in entry:
        for link in entry.links:
            if 'image' in link.type:
                return link.href
    return None

def extract_description(entry):
    if 'summary' in entry:
        return BeautifulSoup(entry.summary, 'html.parser').text[:150] + '...'
    return "Pas de description disponible."

def parse_date(entry):
    try:
        if 'published' in entry:
            return date_parser.parse(entry.published).strftime('%d %B %Y %H:%M')
        elif 'pubDate' in entry:
            return date_parser.parse(entry.pubDate).strftime('%d %B %Y %H:%M')
    except (AttributeError, ValueError):
        return 'Date inconnue'

def is_valid_article(entry):
    title = entry.get('title', '')
    if not title or title.lower().endswith(('.jpg', '.png', '.gif')):
        print(f"Article ignoré: {title}")
        return False
    return True

@app.route('/')
def index():
    selected_category = request.args.get('category', 'Tous')
    articles = []

    for source in RSS_FEEDS:
        if selected_category != 'Tous' and source['category'] != selected_category:
            continue

        feed = fetch_feed(source['url'])
        for entry in feed.entries:
            if not is_valid_article(entry):
                continue

            article = {
                'title': entry.title,
                'link': entry.link,
                'published': parse_date(entry),
                'source': source['name'],
                'category': source['category'],
                'image': extract_image(entry),
                'description': extract_description(entry)
            }
            articles.append(article)

    if not articles:
        flash(f"Aucun article disponible pour la catégorie '{selected_category}'. Vérifiez si les flux sont actifs ou nécessitent un accès particulier.")

    # Tri des articles par date de publication, en gérant les dates manquantes
    articles.sort(key=lambda x: x['published'] if x['published'] and x['published'] != 'Date inconnue' else '', reverse=True)

    categories = ['Tous'] + sorted({source['category'] for source in RSS_FEEDS})

    return render_template('index.html', articles=articles, categories=categories, selected_category=selected_category)

if __name__ == '__main__':
    app.run(debug=True)
