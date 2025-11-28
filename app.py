import os
import math
import json
import base64
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium
import folium

# utils.py must provide at least these:
from utils import (
    nominatim_geocode,
    google_streetview_embed_url,
)

# ======================================
# Config & secrets
# ======================================

st.set_page_config(
    page_title="Outil de visualisation urbaine",
    page_icon="🧭",
    layout="wide",
)

load_dotenv()

MAPILLARY_TOKEN = os.getenv("MAPILLARY_TOKEN", "")
GOOGLE_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ======================================
# Mapillary helpers (from your old app)
# ======================================

MAP_FIELDS = "id,computed_geometry,thumb_1024_url,thumb_2048_url,captured_at,is_pano"


def _deg_for_meters(lat_deg: float, meters: float):
    """Approximate lat/lon offsets in degrees for given meters."""
    dlat = meters / 111_320.0
    dlon = dlat * math.cos(math.radians(lat_deg))
    return dlat, dlon


def _haversine_m(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lon points."""
    from math import radians, sin, cos, asin, sqrt

    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * R * asin(sqrt(a))


def mapillary_find_best(
    lat: float,
    lon: float,
    token: str,
    radii_m=None,
    require_pano: bool = False,
):
    """
    Cherche la meilleure image Mapillary près d'un point.
    - require_pano=True : essaie d'abord de trouver un panorama.
    - radii_m : liste de rayons (en mètres) à tester en bbox.
    Retourne (thumb_url, meta_dict) ou (None, None).
    """
    if not token or not token.startswith("MLY|"):
        return None, None

    if radii_m is None:
        radii_m = (150, 300, 600, 1200, 3000, 6000, 10000)

    base = "https://graph.mapillary.com/images"

    def rank_items(items):
        ranked = []
        for it in items:
            geom = (it.get("computed_geometry") or {}).get("coordinates")
            if isinstance(geom, (list, tuple)) and len(geom) == 2:
                dist = _haversine_m(lat, lon, geom[1], geom[0])
            else:
                dist = float("inf")
            ranked.append((bool(it.get("is_pano")), dist, it))
        # pano d'abord, puis distance croissante
        ranked.sort(key=lambda x: (-int(x[0]), x[1]))
        return ranked

    # 1) Essai simple avec 'closeto'
    try:
        r = requests.get(
            base,
            params={
                "access_token": token,
                "fields": MAP_FIELDS,
                "limit": 20,
                "closeto": f"{lat},{lon}",
            },
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("data", [])
        if items:
            ranked = rank_items(items)
            if require_pano:
                panos = [t for t in ranked if t[0]]
                if panos:
                    it = panos[0][2]
                    return (
                        it.get("thumb_1024_url") or it.get("thumb_2048_url"),
                        it,
                    )
            it = ranked[0][2]
            return it.get("thumb_1024_url") or it.get("thumb_2048_url"), it
    except Exception:
        pass

    # 2) Fallback avec bbox et différents rayons
    for radius in radii_m:
        dlat, dlon = _deg_for_meters(lat, radius)
        bbox = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"
        try:
            r = requests.get(
                base,
                params={
                    "access_token": token,
                    "fields": MAP_FIELDS,
                    "limit": 50,
                    "bbox": bbox,
                },
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("data", [])
            if not items:
                continue
            ranked = rank_items(items)
            if require_pano:
                panos = [t for t in ranked if t[0]]
                if panos:
                    it = panos[0][2]
                    return (
                        it.get("thumb_1024_url") or it.get("thumb_2048_url"),
                        it,
                    )
            it = ranked[0][2]
            return it.get("thumb_1024_url") or it.get("thumb_2048_url"), it
        except Exception:
            continue

    return None, None


def _fmt_date(value) -> str:
    """Handle Mapillary date strings or timestamps safely."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            if value > 1e12:  # ms
                value /= 1000.0
            return datetime.utcfromtimestamp(value).date().isoformat()
        except Exception:
            return ""
    if isinstance(value, str):
        try:
            return (
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                .date()
                .isoformat()
            )
        except Exception:
            return value[:10]
    return str(value)


def pannellum_html_from_image_bytes(img_bytes: bytes, height_px: int = 480) -> str:
    data_uri = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode(
        "ascii"
    )
    cfg = {
        "type": "equirectangular",
        "panorama": data_uri,
        "autoLoad": True,
        "autoRotate": -2,
        "showZoomCtrl": True,
        "hfov": 90,
    }
    return f"""
    <div id="pano" style="width:100%; height:{int(height_px)}px; border-radius:10px; overflow:hidden;"></div>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum/build/pannellum.css">
    <script src="https://cdn.jsdelivr.net/npm/pannellum/build/pannellum.js"></script>
    <script>
      (function(){{
        var cfg = {json.dumps(cfg)};
        function init(){{ window.pannellum && pannellum.viewer("pano", cfg); }}
        if (document.readyState === "complete") init(); else window.addEventListener("load", init);
      }})();
    </script>
    """


# ======================================
# Geocoding + WFS helpers (cadastre & PLU)
# ======================================

@st.cache_data(ttl=3600)
def cached_geocode(addr: str):
    """
    Wrapper autour de nominatim_geocode fourni par utils.py.
    On suppose qu'il retourne (lat, lon, label).
    """
    return nominatim_geocode(addr)


@st.cache_data(ttl=1800)
def get_cadastre_parcel_from_wfs(lat, lon, bbox_deg=0.001, max_features=10):
    """
    Query IGN WFS (Parcellaire Express) around a point and return
    the *closest* parcel as a small dict:

    {
        "coords": [[lat, lon], ...],   # polygon for Folium
        "area_m2": float | None,      # surface if available in attributes
        "properties": dict            # raw WFS properties (debug)
    }

    Returns None if nothing found.
    """
    wfs_url = "https://data.geopf.fr/wfs/ows"

    min_lon = lon - bbox_deg
    min_lat = lat - bbox_deg
    max_lon = lon + bbox_deg
    max_lat = lat + bbox_deg

    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat},EPSG:4326",
        "OUTPUTFORMAT": "application/json",
        "COUNT": str(max_features),
    }

    try:
        r = requests.get(wfs_url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("IGN WFS error:", e)
        return None

    features = data.get("features", [])
    if not features:
        return None

    best_coords = None
    best_d2 = None
    best_props = None

    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue

        gtype = geom.get("type")
        coords = geom.get("coordinates")

        ring = None
        if gtype == "Polygon":
            if coords and coords[0]:
                ring = coords[0]
        elif gtype == "MultiPolygon":
            try:
                ring = coords[0][0]
            except Exception:
                ring = None

        if not ring:
            continue

        sum_lon = sum(pt[0] for pt in ring)
        sum_lat = sum(pt[1] for pt in ring)
        n = len(ring)
        if n == 0:
            continue

        centroid_lon = sum_lon / n
        centroid_lat = sum_lat / n

        dx = centroid_lon - lon
        dy = centroid_lat - lat
        d2 = dx * dx + dy * dy

        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best_coords = [[pt[1], pt[0]] for pt in ring]
            best_props = feat.get("properties", {})

    if not best_coords:
        return None

    # Try to extract surface/area from attributes
    area_m2 = None
    if best_props:
        for key in best_props.keys():
            lk = key.lower()
            if "contenance" in lk or "surface" in lk:
                val = best_props.get(key)
                try:
                    area_m2 = float(str(val).replace(",", "."))
                except Exception:
                    pass
                if area_m2 is not None:
                    break

    return {
        "coords": best_coords,
        "area_m2": area_m2,
        "properties": best_props or {},
    }


@st.cache_data(ttl=600)
def get_plu_zone_from_wfs(lat, lon, bbox_deg=0.002, max_features=10):
    """
    Simple PLU zoning lookup using GPU WFS (zone_urba layer).
    Returns a dict with zone code, zone label, and raw properties.
    """
    wfs_url = "https://data.geopf.fr/wfs/ows"

    min_lon = lon - bbox_deg
    min_lat = lat - bbox_deg
    max_lon = lon + bbox_deg
    max_lat = lat + bbox_deg

    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "wfs_du:zone_urba",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat},EPSG:4326",
        "OUTPUTFORMAT": "application/json",
        "COUNT": str(max_features),
    }

    try:
        r = requests.get(wfs_url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("IGN WFS PLU error:", e)
        return None

    features = data.get("features", [])
    if not features:
        return None

    feat = features[0]
    props = feat.get("properties", {})

    zone_code = (
        props.get("libelle")
        or props.get("LIBELLE")
        or props.get("ZONE")
        or props.get("zone")
        or props.get("CODE_ZONE")
        or props.get("code_zone")
        or props.get("CODEZONE")
        or props.get("codezone")
        or props.get("typezone")
    )

    zone_label = (
        props.get("libelong")
        or props.get("LIBELLE_LONG")
        or props.get("LIBELLELONG")
        or props.get("LIBELLE")
        or props.get("libelle")
        or props.get("LIB_ZONE")
        or props.get("LIBELLE_ZONE")
        or props.get("NOM_ZONE")
        or props.get("nom_zone")
    )

    if not zone_code:
        for k, v in props.items():
            if "zone" in k.lower() and isinstance(v, str) and len(v) <= 10:
                zone_code = v
                break

    return {
        "zone_code": zone_code,
        "zone_label": zone_label,
        "raw_properties": props,
    }


def build_plu_pdf_url_from_properties(props: dict) -> str | None:
    """
    Construit l'URL du règlement PLU (PDF) à partir des propriétés GPU de la zone_urba.
    On utilise :
      - gpu_doc_id : identifiant du document dans le GPU
      - nomfic     : nom du fichier PDF du règlement
    """
    if not props:
        return None

    doc_id = props.get("gpu_doc_id") or props.get("id")
    filename = props.get("nomfic")

    if not doc_id or not filename:
        return None

    # Pattern conforme à l'API GPU :
    # /api/document/{id}/download-file/{fileName}
    return f"https://www.geoportail-urbanisme.gouv.fr/api/document/{doc_id}/download-file/{filename}"


# ======================================
# Session state
# ======================================

if "geo_result" not in st.session_state:
    st.session_state.geo_result = None

# ======================================
# UI – Header & sidebar
# ======================================

st.title("🧭 Outil intelligent de visualisation urbaine")
st.markdown(
    "Adresse ➜ **carte**, **parcelle cadastrale**, **Street View** (Google / Mapillary), "
    "**zonage PLU** et lien vers le **règlement**."
)
st.markdown("---")

with st.sidebar:
    st.markdown("## Paramètres")

    provider = st.selectbox(
        "Source d'images de rue",
        ["Auto", "Mapillary", "Google"],
        help="Auto : essaie Mapillary d'abord, puis Google si nécessaire.",
    )

    radius = st.slider(
        "Rayon de recherche Mapillary (mètres)",
        50,
        1000,
        150,
        step=50,
        help="Contrôle la proximité des images Mapillary recherchées.",
    )

    pano_first = st.checkbox(
        "Préférer les panoramas Mapillary", value=True
    )

    st.markdown("---")
    st.markdown("### Clés API")
    st.caption(
        "Les clés sont configurées côté serveur (non visibles pour l'utilisateur)."
    )

# ======================================
# UI – Adresse + géocodage
# ======================================

st.markdown("### Adresse")

address = st.text_input(
    "Entrez une adresse :",
    value="",
    placeholder="Ex : Tour Eiffel, Paris",
)

col_search, _ = st.columns([1, 3])
with col_search:
    search = st.button("Geocoder & afficher")

if search:
    if not address.strip():
        st.warning("Veuillez saisir une adresse.")
        st.stop()

    geo = cached_geocode(address.strip())
    # cached_geocode doit renvoyer (lat, lon, label) ou None
    if not geo or not geo[0]:
        st.error("Adresse introuvable. Essayez une autre requête.")
        st.session_state.geo_result = None
    else:
        lat, lon, label = geo
        st.session_state.geo_result = {
            "lat": lat,
            "lon": lon,
            "label": label,
        }

geo = st.session_state.geo_result

if not geo:
    st.info("Saisissez une adresse puis cliquez sur **Geocoder & afficher**.")
    st.stop()

lat = geo["lat"]
lon = geo["lon"]
label = geo["label"]

st.success(
    f"Géocodage réussi → **{label}**  \n"
    f"Coordonnées : `{lat:.6f}, {lon:.6f}`"
)

# ======================================
# PLU info & parcelle
# ======================================

plu_info = get_plu_zone_from_wfs(lat, lon)
props = plu_info.get("raw_properties", {}) if plu_info else {}
pdf_url = build_plu_pdf_url_from_properties(props) if plu_info else None

# Parcelle cadastrale (coords + surface)
parcel = get_cadastre_parcel_from_wfs(lat, lon)

# ======================================
# Fiche synthèse
# ======================================

st.markdown("### Fiche synthèse")

col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 1])

with col_a:
    st.markdown("**Adresse recherchée :**")
    st.markdown(label)

with col_b:
    st.markdown("**Zone PLU :**")
    if plu_info and plu_info.get("zone_code"):
        st.markdown(f"`{plu_info['zone_code']}`")
    else:
        st.markdown("_Inconnue_")

with col_c:
    st.markdown("**Règlement :**")
    if pdf_url:
        st.markdown(f"[📄 Voir le règlement (PDF)]({pdf_url})")
    else:
        st.markdown("_Non disponible_")

with col_d:
    st.markdown("**Surface parcelle :**")
    if parcel and parcel.get("area_m2"):
        st.markdown(f"≈ {parcel['area_m2']:.0f} m²")
    else:
        st.markdown("_Non disponible_")

st.markdown("---")

# ======================================
# Tabs
# ======================================

tab_carte, tab_plu, tab_street, tab_brut = st.tabs(
    [" Carte & parcelle  ", " PLU / Zonage  ", " Vue panoramique  ", " Données brutes"]
)

# ---------------------- Carte & parcelle ---------------------- #
with tab_carte:
    st.subheader("Carte & parcelle cadastrale")

    m = folium.Map(location=[lat, lon], zoom_start=18, control_scale=True)
    folium.Marker([lat, lon], tooltip=label, popup=label).add_to(m)

    if parcel and parcel.get("coords"):
        folium.Polygon(
            locations=parcel["coords"],
            color="red",
            weight=2,
            fill=True,
            fill_opacity=0.2,
            tooltip="Parcelle (IGN Parcellaire Express)",
        ).add_to(m)
    else:
        offset = 0.0003
        fake_polygon_coords = [
            [lat - offset, lon - offset],
            [lat - offset, lon + offset],
            [lat + offset, lon + offset],
            [lat + offset, lon - offset],
        ]
        folium.Polygon(
            locations=fake_polygon_coords,
            color="orange",
            weight=2,
            fill=True,
            fill_opacity=0.1,
            tooltip="Parcelle (démo, aucun cadastre trouvé)",
        ).add_to(m)

    st_folium(m, height=450, use_container_width=True)

# ---------------------- PLU / Zonage ---------------------- #
with tab_plu:
    st.subheader("PLU / Zonage")

    if plu_info:
        st.success("Zonage trouvé sur le Géoportail de l'Urbanisme.")

        if plu_info.get("zone_code"):
            st.write(f"**Code de zone :** `{plu_info['zone_code']}`")

        if plu_info.get("zone_label"):
            st.write(f"**Libellé de zone :** {plu_info['zone_label']}")

        st.markdown("#### 📄 Règlement PLU")
        if pdf_url:
            st.markdown(f"[📥 Télécharger le règlement complet (PDF)]({pdf_url})")
        else:
            st.info(
                "Aucun lien direct vers le règlement PDF n'a été trouvé dans les propriétés GPU."
            )

        with st.expander("Afficher les propriétés brutes (avancé)"):
            st.json(plu_info.get("raw_properties", {}))
    else:
        st.info(
            "Aucune information de zonage PLU trouvée pour cette position sur le GPU "
            "(la commune est peut-être au RNU ou pas encore numérisée)."
        )

# ---------------------- Street View / Panoramique ---------------------- #
with tab_street:
    st.subheader("Vue panoramique (Mapillary / Google)")

    chosen_provider = provider
    selected_thumb = None
    selected_meta = None

    # Liste des rayons pour Mapillary (basés sur le slider)
    radii = (
        radius,
        max(radius * 2, 300),
        600,
        1200,
        3000,
        6000,
        10000,
    )

    # Auto mode: Mapillary d'abord, puis Google
    if provider == "Auto":
        if MAPILLARY_TOKEN:
            thumb, meta = mapillary_find_best(
                lat, lon, MAPILLARY_TOKEN, radii_m=radii, require_pano=pano_first
            )
            # Si on a demandé un pano mais rien trouvé, on retente sans contrainte
            if pano_first and (not thumb or not isinstance(meta, dict)):
                thumb, meta = mapillary_find_best(
                    lat, lon, MAPILLARY_TOKEN, radii_m=radii, require_pano=False
                )

            if thumb and isinstance(meta, dict):
                chosen_provider = "Mapillary"
                selected_thumb = thumb
                selected_meta = meta

        if (not selected_thumb) and GOOGLE_KEY:
            chosen_provider = "Google"

    # ---- Mapillary ---- #
    if chosen_provider == "Mapillary":
        if not MAPILLARY_TOKEN:
            st.warning(
                "Veuillez configurer MAPILLARY_TOKEN pour utiliser les images Mapillary."
            )
        else:
            if not selected_thumb or not selected_meta:
                thumb, meta = mapillary_find_best(
                    lat, lon, MAPILLARY_TOKEN, radii_m=radii, require_pano=pano_first
                )
                if pano_first and (not thumb or not isinstance(meta, dict)):
                    st.info(
                        "Aucune image panoramique proche — recherche d'une photo la plus proche."
                    )
                    thumb, meta = mapillary_find_best(
                        lat,
                        lon,
                        MAPILLARY_TOKEN,
                        radii_m=radii,
                        require_pano=False,
                    )
            else:
                thumb, meta = selected_thumb, selected_meta

            if not thumb or not isinstance(meta, dict):
                st.error("Aucune imagerie Mapillary trouvée à proximité de ce point.")
            else:
                static_url = meta.get("thumb_1024_url") or thumb

                # Static preview
                try:
                    img_resp = requests.get(static_url, timeout=20)
                    img_resp.raise_for_status()
                    st.image(
                        img_resp.content,
                        caption="Aperçu statique Mapillary",
                        use_column_width=True,
                    )
                except Exception as e:
                    st.warning(f"Erreur lors du chargement de l'image statique : {e}")

                is_pano = bool(meta.get("is_pano"))
                date_str = _fmt_date(meta.get("captured_at", ""))

                if is_pano:
                    st.markdown("##### Vue panoramique Mapillary (Pannellum)")
                    pano_url = meta.get("thumb_2048_url") or static_url
                    try:
                        pbytes = requests.get(pano_url, timeout=30)
                        pbytes.raise_for_status()
                        html_block = pannellum_html_from_image_bytes(
                            pbytes.content, height_px=480
                        )
                        st.components.v1.html(
                            html_block, height=520, scrolling=False
                        )
                    except Exception as e:
                        st.warning(
                            f"Erreur lors du chargement du panorama (affichage statique uniquement) : {e}"
                        )
                else:
                    st.info(
                        "Cette image n'est pas panoramique (prise de vue standard)."
                    )

                pid = str(meta.get("id", ""))
                footer = f"ID: `{pid}`"
                if date_str:
                    footer += f" — Date de prise de vue : {date_str}"
                st.caption(footer)

    # ---- Google Street View ---- #
    elif chosen_provider == "Google":
        if not GOOGLE_KEY:
            st.warning(
                "Veuillez configurer GOOGLE_MAPS_API_KEY pour utiliser Google Street View."
            )
        else:
            url = google_streetview_embed_url(lat, lon, GOOGLE_KEY)
            if url:
                st.markdown(f"[Open Street View in a new tab ↗]({url})")
                st.components.v1.iframe(url, height=450, scrolling=False)
            else:
                st.info("Impossible de construire l'URL d'embed Google Street View.")

    # ---- Aucun provider dispo ---- #
    else:
        st.info(
            "Aucun fournisseur d'imagerie de rue disponible ou aucune image trouvée à proximité."
        )

# ---------------------- Données brutes ---------------------- #
with tab_brut:
    st.subheader("Données brutes / debug")

    st.markdown("#### Coordonnées & adresse")
    st.write({"lat": lat, "lon": lon, "label": label})

    st.markdown("#### PLU (propriétés WFS)")
    if plu_info:
        st.json(plu_info.get("raw_properties", {}))
    else:
        st.info("Aucune information PLU disponible pour cette position.")

    st.markdown("#### Parcelle cadastrale (propriétés WFS)")
    if parcel and parcel.get("properties"):
        st.json(parcel["properties"])
    else:
        st.info("Aucune parcelle trouvée ou pas de propriétés disponibles.")
