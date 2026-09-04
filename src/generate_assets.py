"""
Generate simulated roadside assets near M1/M6 junctions.

IMPORTANT: This data is entirely simulated for portfolio/demo purposes.
These are NOT real National Highways asset locations. Coordinates are
randomly scattered near real junction locations to create a plausible
but fictional dataset for demonstrating spatial analysis techniques.
"""

import logging
import random
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

JUNCTIONS_PATH = Path("data/junctions.csv")
OUTPUT_PATH = Path("data/assets.csv")

WGS84 = "EPSG:4326"
BRITISH_NATIONAL_GRID = "EPSG:27700"

ASSET_TYPES = ["Gantry", "Safety Barrier", "Signage"]
ASSETS_PER_JUNCTION = 4
MAX_DISTANCE_METRES = 800  # deliberately wider than the 500m priority zone,
                            # so some simulated assets fall outside it

RANDOM_SEED = 42  # fixed seed so results are reproducible for anyone re-running this


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


def generate_assets_for_junction(
    junction_id: str,
    motorway: str,
    easting: float,
    northing: float,
    rng: random.Random,
) -> list[dict]:
    """
    Generate simulated asset points scattered around one junction.

    Works in British National Grid (metres) so distance/direction math
    is straightforward: pick a random angle and a random distance, then
    move that far from the junction in that direction.
    """
    assets = []
    for i in range(ASSETS_PER_JUNCTION):
        angle_degrees = rng.uniform(0, 360)
        distance_metres = rng.uniform(50, MAX_DISTANCE_METRES)

        import math
        angle_radians = math.radians(angle_degrees)
        dx = distance_metres * math.cos(angle_radians)
        dy = distance_metres * math.sin(angle_radians)

        assets.append({
            "asset_id": f"{motorway}_{junction_id}_asset{i+1}",
            "asset_type": rng.choice(ASSET_TYPES),
            "near_junction": junction_id,
            "motorway": motorway,
            "easting": easting + dx,
            "northing": northing + dy,
        })
    return assets


def generate_all_assets(junctions: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Generate simulated assets near every junction and return as a GeoDataFrame."""
    rng = random.Random(RANDOM_SEED)

    junctions_bng = junctions.to_crs(BRITISH_NATIONAL_GRID)

    all_assets = []
    for _, row in junctions_bng.iterrows():
        assets = generate_assets_for_junction(
            junction_id=row["junction_id"],
            motorway=row["motorway"],
            easting=row.geometry.x,
            northing=row.geometry.y,
            rng=rng,
        )
        all_assets.extend(assets)

    df = pd.DataFrame(all_assets)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["easting"], df["northing"]),
        crs=BRITISH_NATIONAL_GRID,
    )
    gdf = gdf.to_crs(WGS84)
    gdf["latitude"] = gdf.geometry.y
    gdf["longitude"] = gdf.geometry.x

    return gdf


def save_assets(gdf: gpd.GeoDataFrame, output_path: Path = OUTPUT_PATH) -> None:
    """Save assets to CSV (dropping the geometry column, keeping lat/lon)."""
    df = gdf.drop(columns=["geometry", "easting", "northing"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Saved %d simulated assets to %s", len(df), output_path)


def main() -> None:
    junctions = load_junctions()
    logger.info("Loaded %d junctions to scatter assets around", len(junctions))

    assets = generate_all_assets(junctions)
    logger.info("Generated %d simulated assets", len(assets))

    save_assets(assets)


if __name__ == "__main__":
    main()