"""
Spatial join: determine which simulated assets fall within a junction's
maintenance priority zone.

Loads real junctions (buffered into priority zones) and simulated assets,
then uses a spatial join to flag each asset as "priority" (inside a zone)
or not. This is the core analytical step of the project.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from build_zones import build_priority_zones, load_junctions, WGS84, BRITISH_NATIONAL_GRID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ASSETS_PATH = Path("data/assets.csv")
OUTPUT_PATH = Path("data/assets_with_priority.csv")


def load_assets(path: Path = ASSETS_PATH) -> gpd.GeoDataFrame:
    """Load simulated assets from CSV and convert to a GeoDataFrame in WGS84."""
    df = pd.read_csv(path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=WGS84,
    )
    return gdf


def flag_priority_assets(
    assets: gpd.GeoDataFrame, zones: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """
    Spatial join: flag each asset as inside or outside any priority zone.

    Both inputs are reprojected to British National Grid for the join,
    since that's the metres-based CRS the zones were actually built in.
    """
    assets_bng = assets.to_crs(BRITISH_NATIONAL_GRID)
    zones_bng = zones.to_crs(BRITISH_NATIONAL_GRID)

    # Keep only the zone's identifying columns to avoid column name clashes
    zones_for_join = zones_bng[["motorway", "junction_id", "geometry"]].rename(
        columns={"motorway": "zone_motorway", "junction_id": "zone_junction_id"}
    )

    joined = gpd.sjoin(
        assets_bng,
        zones_for_join,
        how="left",
        predicate="within",
    )

    # An asset with a non-null zone_junction_id landed inside some zone
    joined["in_priority_zone"] = joined["zone_junction_id"].notna()

    # An asset could technically fall inside more than one overlapping zone;
    # keep just the first match so each asset appears once in the output
    joined = joined[~joined.index.duplicated(keep="first")]

    return joined


def main() -> None:
    junctions = load_junctions()
    zones = build_priority_zones(junctions)
    logger.info("Built %d priority zones", len(zones))

    assets = load_assets()
    logger.info("Loaded %d simulated assets", len(assets))

    result = flag_priority_assets(assets, zones)

    n_priority = result["in_priority_zone"].sum()
    logger.info(
        "%d of %d assets (%.1f%%) fall within a maintenance priority zone",
        n_priority, len(result), 100 * n_priority / len(result),
    )

    output_df = result.drop(columns=["geometry", "index_right"])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Saved result to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()