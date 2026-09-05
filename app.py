"""
Streamlit app: UK Motorway Asset Density & Maintenance Priority Mapper.

Wraps the existing GIS pipeline (real M1/M6 junctions, buffered priority
zones, simulated assets, spatial join) in an interactive, shareable web app.

Run locally with:
    streamlit run app.py
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# Modules in src/ import each other as top-level modules (e.g.
# "from build_zones import ..."), so src/ must be on sys.path before
# importing any of them here.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from build_map import build_full_map          # noqa: E402
from build_zones import build_priority_zones, load_junctions  # noqa: E402
from spatial_analysis import flag_priority_assets, load_assets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ASSETS_PATH = Path("data/assets.csv")
DEFAULT_RADIUS_METRES = 500
MAP_WIDTH_PX = 1200
MAP_HEIGHT_PX = 600

st.set_page_config(
    page_title="UK Motorway Asset Priority Mapper",
    page_icon="🛣️",
    layout="wide",
)


@st.cache_data
def get_junctions() -> pd.DataFrame:
    """Load and cache real M1/M6 junctions (sourced from OpenStreetMap)."""
    return load_junctions()


@st.cache_data
def get_raw_assets() -> pd.DataFrame:
    """Load and cache the simulated asset dataset."""
    return load_assets(ASSETS_PATH)


@st.cache_data
def compute_priority_zones(_junctions: pd.DataFrame, radius_metres: int) -> pd.DataFrame:
    """
    Build priority zone polygons for the given radius.

    Cached on radius so moving the slider back to a previous value is
    instant rather than recomputing the buffer and reprojection.
    """
    return build_priority_zones(_junctions, radius_metres=radius_metres)


def main() -> None:
    st.title("🛣️ UK Motorway Asset Density & Maintenance Priority Mapper")
    st.markdown(
        "Interactive GIS demo covering the **M1/M6 corridor near Birmingham "
        "and Nottingham**. Real junction locations, buffered maintenance "
        "priority zones, and a spatial join against nearby assets."
    )

    with st.sidebar:
        st.header("Settings")
        radius = st.slider(
            "Priority zone radius (metres)",
            min_value=100,
            max_value=1000,
            value=DEFAULT_RADIUS_METRES,
            step=50,
            help="Buffer distance around each junction. Larger radius flags more assets as priority.",
        )
        st.divider()
        st.subheader("About this data")
        st.markdown(
            "- **Junctions**: real M1/M6 locations, fetched live from "
            "OpenStreetMap via the Overpass API.\n"
            "- **Assets**: gantries, safety barriers, and signage are "
            "**entirely simulated** for this demo — not real National "
            "Highways asset data.\n"
            "- **Priority zones**: calculated by reprojecting to British "
            "National Grid (EPSG:27700), buffering in metres, then "
            "reprojecting back to WGS84 for display."
        )

    try:
        junctions = get_junctions()
    except Exception:
        st.error(
            "Couldn't load junction data. Run `python src/fetch_junctions.py` "
            "at least once to populate data/junctions.csv."
        )
        logger.exception("Failed to load junctions")
        return

    try:
        raw_assets = get_raw_assets()
    except Exception:
        st.error(
            "Couldn't load asset data. Run `python src/generate_assets.py` "
            "at least once to populate data/assets.csv."
        )
        logger.exception("Failed to load assets")
        return

    zones = compute_priority_zones(junctions, radius)
    result = flag_priority_assets(raw_assets, zones)

    n_priority = int(result["in_priority_zone"].sum())
    n_total = len(result)

    col1, col2, col3 = st.columns(3)
    col1.metric("Junctions mapped", len(junctions))
    col2.metric("Simulated assets", n_total)
    col3.metric(
        "Flagged as priority",
        n_priority,
        f"{100 * n_priority / n_total:.0f}% of assets" if n_total else None,
    )

    fmap = build_full_map(junctions, zones, result)
    st_folium(fmap, width=MAP_WIDTH_PX, height=MAP_HEIGHT_PX, returned_objects=[])

    with st.expander("View underlying asset data"):
        st.dataframe(
            result[
                ["asset_id", "asset_type", "motorway", "near_junction", "in_priority_zone"]
            ].sort_values(["motorway", "near_junction"]),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()