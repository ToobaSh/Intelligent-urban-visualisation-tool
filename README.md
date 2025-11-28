# 🧭 Outil intelligent de visualisation urbaine

Application Streamlit permettant d’explorer une adresse en France :  
parcelle cadastrale, zonage PLU, règlement PDF, images Mapillary et Google Street View.

---

##  Aperçu

Cet outil propose une visualisation complète pour analyser instantanément une adresse :

- Géocodage (adresse → coordonnées GPS)
- Parcelle cadastrale (IGN WFS)
- Zonage PLU + lien direct vers le règlement PDF (Géoportail de l’Urbanisme)
- Vue panoramique (Mapillary + Google Street View)
- Fiche synthèse regroupant toutes les informations
- Interface Streamlit simple et professionnelle

Idéal pour les urbanistes, architectes, diagnostiqueurs, agents immobiliers, collectivités.

---

##  Fonctionnalités

### 1. Géocodage (Nominatim)
- Transformation de l’adresse en coordonnées GPS
- Affichage du libellé complet retourné par OpenStreetMap

### 2. Parcelle cadastrale (IGN Parcellaire Express)
- Requête automatique via l’API WFS d’IGN
- Contour exact de la parcelle affiché sur une carte Folium
- Surface en m² lorsque l’attribut « contenance » est disponible

### 3. Zonage PLU (Géoportail de l’Urbanisme)
- Récupération automatique de la zone via WFS GPU
- Affichage du code de zone et du libellé
- Lien direct vers le règlement PDF officiel du PLU

### 4. Vue panoramique (StreetView)
- Recherche avancée d’images Mapillary (thumbnail + panorama 360°)
- Visionneuse panoramique intégrée (Pannellum)
- Fallback automatique vers Google Street View si aucune image Mapillary n’est disponible

### 5. Fiche synthèse
- Adresse
- Coordonnées GPS
- Zone PLU
- Surface parcelle
- Lien règlement
- Vue panoramique

---

##  Architecture technique

- Python 3+
- Streamlit
- Folium (cartographie)
- Pannellum (panorama 360° via HTML/JS)
- PyPDF2 (lecture du règlement PLU)
- APIs utilisées :
  - Nominatim (OSM)
  - IGN WFS (Parcellaire Express)
  - Géoportail de l’Urbanisme WFS
  - Mapillary Graph API
  - Google Maps API (Street View)

---
