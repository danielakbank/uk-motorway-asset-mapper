"""
Build the final interactive map: M1/M6 junctions, their maintenance priority
zones, and simulated assets colour-coded by whether they fall within a zone.

Exposes build_full_map() so this logic can be reused both by the CLI
(__main__ below) and by the Streamlit app (app.py), which needs the live
folium.Map object rather than a saved file.
"""

import logging
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from build_zones import build_priority_zones, load_junctions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ASSETS_WITH_PRIORITY_PATH = Path("data/assets_with_priority.csv")
OUTPUT_MAP_PATH = Path("output/priority_map.html")

# Colour palette based on UK motorway/roadworks signage
ZONE_COLOR = "#00539F"       # motorway blue
PRIORITY_COLOR = "#2E8B57"   # muted green
OUTSIDE_COLOR = "#C0392B"    # muted red

LEGEND_HTML = f"""
<div style="
    position: fixed;
    bottom: 30px; left: 30px; z-index: 9999;
    background-color: #1e1e1e; color: #f0f0f0; padding: 12px 16px;
    border: 1px solid #444; border-radius: 6px;
    font-size: 13px; line-height: 1.6;
    color-scheme: dark;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
">
    <b style="color:#ffffff;">Legend</b><br>
    <span style="color:{ZONE_COLOR};">&#9679;</span> Motorway junction<br>
    <span style="color:{PRIORITY_COLOR};">&#9679;</span> Asset — priority zone<br>
    <span style="color:{OUTSIDE_COLOR};">&#9679;</span> Asset — outside zone<br>
    <span style="color:{ZONE_COLOR}; opacity:0.6;">&#9632;</span> 500m priority zone
</div>
"""


def add_junction_markers(fmap: folium.Map, junctions: gpd.GeoDataFrame) -> None:
    """Add a marker for each motorway junction."""
    for _, row in junctions.iterrows():
        popup_text = f"{row['motorway']} J{row['junction_id']} — {row['name']}"
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=popup_text,
            tooltip=popup_text,
            icon=folium.Icon(color="blue", icon="road", prefix="fa"),
        ).add_to(fmap)


def add_priority_zones(fmap: folium.Map, zones: gpd.GeoDataFrame) -> None:
    """Add each priority zone as a translucent circle polygon."""
    for _, row in zones.iterrows():
        folium.GeoJson(
            row.geometry,
            style_function=lambda _: {
                "fillColor": ZONE_COLOR,
                "color": ZONE_COLOR,
                "weight": 1,
                "fillOpacity": 0.15,
            },
            tooltip=f"Priority zone: {row['motorway']} J{row['junction_id']}",
        ).add_to(fmap)


def add_asset_markers(fmap: folium.Map, assets: pd.DataFrame) -> None:
    """Add a small coloured circle marker for each asset, green if in a priority zone."""
    for _, row in assets.iterrows():
        in_zone = row["in_priority_zone"]
        color = PRIORITY_COLOR if in_zone else OUTSIDE_COLOR
        status = "Priority zone" if in_zone else "Outside zone"

        popup_text = (
            f"{row['asset_type']} ({row['asset_id']})<br>"
            f"Near {row['motorway']} J{row['near_junction']}<br>"
            f"Status: {status}"
        )

        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=popup_text,
            tooltip=f"{row['asset_type']} — {status}",
        ).add_to(fmap)


def build_full_map(
    junctions: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    assets: pd.DataFrame,
) -> folium.Map:
    """
    Build the complete Folium map: zones, junctions, assets, and legend.

    This is the single source of truth for map construction, used by both
    the command-line entry point below and the Streamlit app, so the two
    never drift apart.
    """
    center_lat = junctions["latitude"].mean()
    center_lon = junctions["longitude"].mean()
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=9)

    add_priority_zones(fmap, zones)
    add_junction_markers(fmap, junctions)
    add_asset_markers(fmap, assets)

    fmap.get_root().html.add_child(folium.Element(LEGEND_HTML))
    return fmap


def main() -> None:
    junctions = load_junctions()
    logger.info("Loaded %d junctions", len(junctions))

    zones = build_priority_zones(junctions)
    logger.info("Built %d priority zones", len(zones))

    assets = pd.read_csv(ASSETS_WITH_PRIORITY_PATH)
    logger.info("Loaded %d assets", len(assets))

    fmap = build_full_map(junctions, zones, assets)

    OUTPUT_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(OUTPUT_MAP_PATH)
    logger.info("Saved final map to %s", OUTPUT_MAP_PATH)


if __name__ == "__main__":
    main()