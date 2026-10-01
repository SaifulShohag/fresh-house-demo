import requests
import json
import subprocess
import math
import os
from typing import Tuple, List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class GeocodeResult(BaseModel):
    lat: float
    lon: float
    formatted_address: str
    place_id: str


class ParcelData(BaseModel):
    building_footprint: Optional[List[Tuple[float, float]]]
    building_height: Optional[float] = None
    footprint_is_fallback: bool = False
    parcel_bounds: Optional[List[Tuple[float, float]]] = None
    bounding_box: Tuple[float, float, float, float]


# Use a narrow building window and a wider infrastructure window.
BUILDING_OFFSET = 0.0012
INFRA_OFFSET = 0.003


def _meters_per_degree(lat: float) -> Tuple[float, float]:
    lat_rad = math.radians(lat)
    return (
        111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad),
        111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad),
    )


def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    """FIX 4: ray-casting containment test. ring = GeoJSON [[lon, lat], ...]."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_int = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_int:
                inside = not inside
        j = i
    return inside


def _iter_candidate_rings(geojson_data: dict):
    """FIX 2 + 3: yield (ring, properties) for every outer ring,
    handling Polygon AND MultiPolygon, null-safe throughout."""
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        gtype = geom.get("type")

        if gtype == "Polygon":
            rings = [geom.get("coordinates", [[]])[0]]
        elif gtype == "MultiPolygon":
            rings = [part[0] for part in geom.get("coordinates", []) if part]
        else:
            continue

        for ring in rings:
            if len(ring) >= 4:
                yield ring, props


def geocode_address(address: str) -> GeocodeResult:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY is not configured.")

    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": api_key},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "OK" or not data.get("results"):
        message = data.get("error_message") or data.get("status", "Unknown error")
        raise ValueError(f"Google geocoding failed for {address}: {message}")

    result = data["results"][0]
    location = result["geometry"]["location"]
    return GeocodeResult(
        lat=float(location["lat"]),
        lon=float(location["lng"]),
        formatted_address=result["formatted_address"],
        place_id=str(result["place_id"]),
    )


def fetch_osm_parcel_data(lat: float, lon: float) -> ParcelData:
    infra_bbox = (
        lon - INFRA_OFFSET, lat - INFRA_OFFSET,
        lon + INFRA_OFFSET, lat + INFRA_OFFSET,
    )

    building_footprint = None
    building_height = None

    try:
        b = (lon - BUILDING_OFFSET, lat - BUILDING_OFFSET,
             lon + BUILDING_OFFSET, lat + BUILDING_OFFSET)
        bbox_str = f"{b[0]},{b[1]},{b[2]},{b[3]}"

        print(f"[GIS] Fetching Overture buildings for bbox: {bbox_str}", flush=True)
        result = subprocess.run(
            ["overturemaps", "download", "--bbox", bbox_str, "-f", "geojson", "--type", "building"],
            capture_output=True, text=True, check=True, timeout=60,
        )
        geojson_data = json.loads(result.stdout)

        contained_ring, contained_height = None, None
        best_ring, best_height, min_dist = None, None, float("inf")

        for ring, props in _iter_candidate_rings(geojson_data):
            if _point_in_ring(lon, lat, ring):
                contained_ring = ring
                contained_height = props.get("height")
                break

            avg_lon = sum(c[0] for c in ring) / len(ring)
            avg_lat = sum(c[1] for c in ring) / len(ring)
            dist = (avg_lon - lon) ** 2 + (avg_lat - lat) ** 2
            if dist < min_dist:
                min_dist = dist
                best_ring, best_height = ring, props.get("height")

        chosen = contained_ring or best_ring
        height = contained_height if contained_ring else best_height

        if chosen:
            building_footprint = [(p_lat, p_lon) for p_lon, p_lat in chosen]
            building_height = float(height) if height else None
            print(f"[GIS] ✅ Footprint: {len(building_footprint)} pts, "
                  f"height={building_height}m", flush=True)

    except FileNotFoundError:
        print("[WARN] 'overturemaps' CLI not found.", flush=True)
    except subprocess.TimeoutExpired:
        print("[WARN] Overture download timed out.", flush=True)
    except Exception as e:
        print(f"[WARN] Overture building extraction error: {e}", flush=True)

    if building_footprint:
        return ParcelData(
            building_footprint=building_footprint,
            building_height=building_height,
            footprint_is_fallback=False,
            parcel_bounds=None,
            bounding_box=infra_bbox,
        )

    print("[WARN] No Overture footprint found; building geometry will be omitted.", flush=True)
    return ParcelData(
        building_footprint=None,
        building_height=None,
        footprint_is_fallback=True,
        parcel_bounds=None,
        bounding_box=infra_bbox,
    )


def get_site_context(address: str) -> dict:
    location = geocode_address(address)
    parcel = fetch_osm_parcel_data(location.lat, location.lon)
    return {
        "address": location.formatted_address,
        "coordinates": (location.lat, location.lon),
        "place_id": location.place_id,
        "parcel_data": parcel.model_dump(),
    }