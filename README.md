🧭 Outil Intelligent de Visualisation Urbaine

Application Streamlit pour explorer une adresse, sa parcelle cadastrale, son zonage PLU et l’imagerie Street View (Mapillary + Google).

<img src="SCREENSHOT_HERE" width="700"/>
🚀 Aperçu

Cet outil propose une visualisation complète et interactive pour analyser une adresse en France :

Géocodage (Nominatim → coordonnées GPS)

Parcelle cadastrale (IGN Parcellaire Express)

Zonage PLU + lien direct vers le règlement PDF (Géoportail de l’Urbanisme)

Vue panoramique (Mapillary ou Google Street View selon disponibilité)

Fiche synthèse automatique

Affichage complet dans une interface Streamlit moderne et simple

Idéal pour :
urbanistes, architectes, diagnostiqueurs, bureaux d’études, agents immobiliers, collectivités.

✨ Fonctionnalités
🗺️ 1. Géocodage précis (Nominatim)

Conversion d’une adresse en coordonnées GPS

Affichage du libellé complet

📐 2. Parcelle cadastrale (IGN)

Récupération automatique via WFS

Affichage de la géométrie exacte sur Folium

Calcul de la surface (si disponible dans les attributs IGN)

<img src="SCREENSHOT_PARCEL" width="600"/>
🏙️ 3. PLU / Zonage (GPU)

Récupération du zonage via WFS du Géoportail de l’Urbanisme

Code et libellé de zone

Lien direct vers le règlement PDF officiel du PLU

Extraction légère d’informations (optionnel)

<img src="SCREENSHOT_PLU" width="600"/>
🚶 4. Vue panoramique (Mapillary + Google)

Recherche avancée d’images Mapillary (avec fallback multi-rayon)

Affichage :

image statique haute résolution

panorama immersif avec Pannellum

lien direct vers Mapillary

Fallback automatique vers Google Street View si nécessaire

<img src="SCREENSHOT_PANO" width="600"/>
📄 5. Fiche synthèse complète

Adresse recherchée

Coordonnées

Zonage PLU

Surface parcelle

Lien vers règlement

Aperçu Street View

🧱 Architecture technique

Backend :

Python 3.10+

Streamlit

Requests

PyPDF2

Pannellum (via HTML/JS embed)

Folium (cartographie)

APIs utilisées :

Service	Fonction
Nominatim (OpenStreetMap)	Géocodage
IGN Parcellaire Express WFS	Délimitation parcellaire
Géoportail de l’Urbanisme (GPU) WFS	Zonage PLU
Mapillary Graph API	Imagery + panoramas
Google Maps API (facultatif)	StreetView fallback# Outil-intelligent-de-visualisation-urbaine
