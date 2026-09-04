"""
Build "maintenance priority zone" buffers around each motorway junction.

Junctions are supplied in WGS84 (degrees). To buffer them by a real distance
in metres, we reproject to British National Grid (EPSG:27700, a metres-based
UK-specific CRS), draw the buffer there, then reproject back to WGS84 for
mapping with Folium.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

JUNCTIONS_PATH = Path("data/junctions.csv")

WGS84 = "EPSG:4326"           # degrees, what Folium/OSM/GPS use
BRITISH_NATIONAL_GRID = "EPSG:27700"  # metres, UK-specific flat grid

PRIORITY_ZONE_RADIUS_METRES = 500


def load_junctions(path: Path = JUNCTIONS_PATH) -> gpd.GeoDataFrame:
    """Load junctions from CSV and convert to a GeoDataFrame in WGS84."""
    df = pd.read_csv(path)
    df = df[~df["junction_id"].str.startswith("osm_")]

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=WGS84,
    )
    return gdf


def build_priority_zones(
    junctions: gpd.GeoDataFrame,
    radius_metres: float = PRIORITY_ZONE_RADIUS_METRES,
) -> gpd.GeoDataFrame:
    """
    Build a circular priority zone polygon around each junction.

    Reprojects to British National Grid (metres) to buffer accurately,
    then reprojects the resulting polygons back to WGS84 for mapping.
    """
    logger.info("Reprojecting junctions from %s to %s", WGS84, BRITISH_NATIONAL_GRID)
    junctions_bng = junctions.to_crs(BRITISH_NATIONAL_GRID)

    logger.info("Buffering each junction by %sm", radius_metres)
    zones_bng = junctions_bng.copy()
    zones_bng["geometry"] = junctions_bng.geometry.buffer(radius_metres)

    logger.info("Reprojecting zones back to %s", WGS84)
    zones = zones_bng.to_crs(WGS84)

    return zones


if __name__ == "__main__":
    junctions = load_junctions()
    logger.info("Loaded %d junctions", len(junctions))

    zones = build_priority_zones(junctions)
    logger.info("Built %d priority zones", len(zones))

    print(zones[["motorway", "junction_id", "geometry"]].head())