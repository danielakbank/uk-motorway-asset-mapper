"""
Load M1/M6 junctions and plot them on an interactive Folium map.

This is the first visualisation step: prove the pipeline works end to end
before adding buffers, simulated assets, or spatial analysis.
"""

import logging
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

JUNCTIONS_PATH = Path("data/junctions.csv")
OUTPUT_MAP_PATH = Path("output/priority_map.html")

# OSM/GPS coordinates are always in WGS84
WGS84 = "EPSG:4326"


def load_junctions(path: Path = JUNCTIONS_PATH) -> gpd.GeoDataFrame:
    """
    Load junctions from CSV and convert to a GeoDataFrame.

    Drops junctions with no real OSM ref (auto-generated osm_<id> ids),
    since these are typically unlabelled slip-road nodes rather than
    named junctions a driver would recognise.
    """
    df = pd.read_csv(path)

    before = len(df)
    df = df[~df["junction_id"].str.startswith("osm_")]
    logger.info("Dropped %d unlabelled junction nodes, %d remain", before - len(df), len(df))

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=WGS84,
    )
    return gdf


def build_junctions_map(gdf: gpd.GeoDataFrame) -> folium.Map:
    """Build a Folium map with a marker for each junction."""
    center_lat = gdf["latitude"].mean()
    center_lon = gdf["longitude"].mean()

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=9)

    for _, row in gdf.iterrows():
        popup_text = f"{row['motorway']} J{row['junction_id']} — {row['name']}"
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=popup_text,
            tooltip=popup_text,
            icon=folium.Icon(color="blue", icon="road", prefix="fa"),
        ).add_to(fmap)

    return fmap


def main() -> None:
    gdf = load_junctions()
    logger.info("Loaded %d junctions into GeoDataFrame", len(gdf))

    fmap = build_junctions_map(gdf)

    OUTPUT_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(OUTPUT_MAP_PATH)
    logger.info("Saved map to %s", OUTPUT_MAP_PATH)


if __name__ == "__main__":
    main()