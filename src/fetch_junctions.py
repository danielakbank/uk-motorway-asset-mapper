"""
Fetch UK motorway junction locations from OpenStreetMap via the Overpass API.

Queries motorway_junction nodes that sit on M1 or M6 ways within a bounding
box covering the corridor near Birmingham and Nottingham, and saves the
results to data/junctions.csv.

Data source: OpenStreetMap contributors, via the Overpass API.

Note: Overpass public instances require a descriptive User-Agent header,
and may reject or rate-limit requests without one. This script also falls
back to secondary public instances if the primary one is unavailable.

GIS concept: a motorway_junction node doesn't carry its own motorway name.
That lives on the parent "way" (the road itself). To filter to just M1/M6,
we query each motorway separately: find the M1 (or M6) ways in the bbox,
then recurse down to the junction nodes that sit on those specific ways.
"""

import logging
import time
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Bounding box covering the Birmingham-Nottingham M1/M6 corridor
# Format: (south, west, north, east)
BBOX = (52.35, -2.10, 53.05, -1.05)

# Motorways we care about for this project
MOTORWAYS = ["M1", "M6"]

# Try the main instance first, then known mirrors if that fails.
# private.coffee (formerly kumi.systems) has no stated rate limit.
# atownsend.org.uk is a UK/Ireland-only instance, IPv6-only, kept as a last resort
# in case that isn't reachable on this network.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.atownsend.org.uk/api/interpreter",
]

REQUEST_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 30  # per Overpass usage policy, on 406/429 responses

# Overpass instances require a descriptive User-Agent identifying the client.
# Requests without one are increasingly rejected with a 406 error.
HEADERS = {
    "User-Agent": "uk-motorway-asset-mapper/1.0 (portfolio project; contact: akinbankoled@gmail.com)"
}

OUTPUT_PATH = Path("data/junctions.csv")


def build_query(motorway: str, bbox: tuple[float, float, float, float]) -> str:
    """
    Build an Overpass QL query for motorway_junction nodes on a specific
    motorway (e.g. "M1") within a bounding box.

    Finds the motorway's ways first, then recurses down to the junction
    nodes that sit on those ways.
    """
    south, west, north, east = bbox
    return f"""
    [out:json][timeout:25];
    way["highway"="motorway"]["ref"="{motorway}"]({south},{west},{north},{east})->.roads;
    node(w.roads)["highway"="motorway_junction"];
    out body;
    """


def _query_endpoint(endpoint: str, query: str) -> dict:
    """Send a query to a single Overpass endpoint and return the parsed JSON."""
    response = requests.post(
        endpoint,
        data={"data": query},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _query_with_fallback(query: str) -> dict:
    """Send a query, trying each endpoint in order until one succeeds."""
    last_error: requests.RequestException | None = None

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            logger.info("Querying %s", endpoint)
            return _query_endpoint(endpoint, query)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            logger.warning("Endpoint %s failed with status %s: %s", endpoint, status, exc)
            last_error = exc
            if status in (406, 429):
                logger.info(
                    "Rate-limited or rejected by %s, waiting %ds before trying next endpoint",
                    endpoint, RETRY_DELAY_SECONDS,
                )
                time.sleep(RETRY_DELAY_SECONDS)
        except requests.RequestException as exc:
            logger.warning("Endpoint %s failed: %s", endpoint, exc)
            last_error = exc

    raise last_error


def fetch_junctions_for_motorway(
    motorway: str, bbox: tuple[float, float, float, float] = BBOX
) -> pd.DataFrame:
    """Fetch motorway_junction nodes for a single motorway within a bounding box."""
    query = build_query(motorway, bbox)
    logger.info("Fetching %s junctions in bbox %s", motorway, bbox)

    data = _query_with_fallback(query)
    elements = data.get("elements", [])
    logger.info("%s: Overpass returned %d raw elements", motorway, len(elements))

    rows = []
    for element in elements:
        tags = element.get("tags", {})
        rows.append({
            "junction_id": tags.get("ref", f"osm_{element['id']}"),
            "motorway": motorway,
            "name": tags.get("name", tags.get("ref", "Unnamed junction")),
            "latitude": element["lat"],
            "longitude": element["lon"],
        })

    df = pd.DataFrame(rows)
    logger.info("%s: parsed %d junctions", motorway, len(df))
    return df


def fetch_all_junctions(
    motorways: list[str] = MOTORWAYS, bbox: tuple[float, float, float, float] = BBOX
) -> pd.DataFrame:
    """Fetch and combine motorway_junction nodes for all given motorways."""
    frames = []
    for motorway in motorways:
        try:
            frames.append(fetch_junctions_for_motorway(motorway, bbox))
        except requests.RequestException:
            logger.exception("Failed to fetch junctions for %s", motorway)

    if not frames:
        return pd.DataFrame(columns=["junction_id", "motorway", "name", "latitude", "longitude"])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["motorway", "junction_id", "latitude", "longitude"])
    return combined


def save_junctions(df: pd.DataFrame, output_path: Path = OUTPUT_PATH) -> None:
    """Save the junctions DataFrame to CSV, creating the parent folder if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Saved %d junctions to %s", len(df), output_path)

def deduplicate_junctions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse multiple OSM nodes for the same physical junction into one point.

    A single junction (e.g. M1 J21) is often mapped as several separate
    nodes in OSM, one per slip road or carriageway direction. We group by
    motorway and junction number, and take the mean coordinates as a single
    representative point for that junction.
    """
    before = len(df)
    deduped = (
        df.groupby(["motorway", "junction_id"], as_index=False)
        .agg(
            name=("name", "first"),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
        )
    )
    logger.info("Deduplicated %d raw nodes into %d unique junctions", before, len(deduped))
    return deduped


def main() -> None:
    df = fetch_all_junctions()

    if df.empty:
        logger.warning("No junctions fetched for any motorway")
        if OUTPUT_PATH.exists():
            logger.warning("Keeping existing cached file at %s", OUTPUT_PATH)
        else:
            logger.error("No cached junctions file exists. Cannot continue.")
        return

    df = deduplicate_junctions(df)
    save_junctions(df)


if __name__ == "__main__":
    main()