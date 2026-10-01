import requests
from typing import Tuple, List, Dict, Any, Optional
from models.provenance import (
    ProvenanceRecord, 
    EvidenceState, 
    SourceType, 
    VisualAllowance, 
    SpatialFeature,
    SupportingMedia
)
from models.site_model import PublicInfrastructure

class MSDGISClient:
    """
    Client for querying the Metropolitan Sewer District (MSD) public ArcGIS FeatureServer.
    Ingests publicly mapped sanitary infrastructure (mains and network points) and 
    binds each feature to a strict ProvenanceRecord.
    """
    
    BASE_URL = "https://services2.arcgis.com/w657bnjzrjguNyOy/ArcGIS/rest/services/MSD_Infrastructure_Complete/FeatureServer"
    SAN_POINTS_LAYER = 1
    SAN_LINES_LAYER = 3

    def __init__(self, timeout_sec: int = 15):
        self.timeout = timeout_sec

    def query_layer_geojson(
        self, 
        layer_id: int, 
        bbox: Tuple[float, float, float, float]
    ) -> Dict[str, Any]:
        """
        Queries an ArcGIS FeatureServer layer using a spatial envelope bounding box.
        bbox format: (min_lon, min_lat, max_lon, max_lat) in EPSG:4326 (WGS84).
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        envelope_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        
        url = f"{self.BASE_URL}/{layer_id}/query"
        params = {
            "f": "geojson",
            "where": "1=1",
            "geometry": envelope_str,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true"
        }
        
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_public_infrastructure(
        self, 
        bbox: Tuple[float, float, float, float]
    ) -> PublicInfrastructure:
        """
        Retrieves public lines and manholes within the target bounding box and converts
        them into SpatialFeatures with immutable provenance records.
        """
        print(f"[MSD GIS] Ingesting public infrastructure for bbox: {bbox}", flush=True)

        mains: List[SpatialFeature] = []
        manholes: List[SpatialFeature] = []

        try:
            lines_geojson = self.query_layer_geojson(self.SAN_LINES_LAYER, bbox)
            features = lines_geojson.get("features", [])
            print(f"[MSD GIS] Found {len(features)} public sanitary line segments.", flush=True)

            for feat in features:
                geom = feat.get("geometry") or {}
                if not geom.get("coordinates"):
                    continue
                props = feat.get("properties") or {}
                obj_id = str(feat.get("id") or props.get("OBJECTID") or props.get("FACILITYID") or "unknown_line")

                line_provenance = ProvenanceRecord(
                    evidence_state=EvidenceState.DOCUMENTED_MAPPED,
                    source_type=SourceType.PUBLIC_GIS,
                    source_id=f"msd_arcgis_layer_3_line_{obj_id}",
                    confidence_limitations="Source-backed public municipal GIS data. Line represents public right-of-way main, not private lateral.",
                    visual_allowance=VisualAllowance.SOLID_HARD_GEOMETRY,
                    supporting_media=[
                        SupportingMedia(
                            media_type="document",
                            url="https://services2.arcgis.com/w657bnjzrjguNyOy/ArcGIS/rest/services/MSD_Infrastructure_Complete/FeatureServer/3",
                            segment_description="MSD Infrastructure Complete - Sanitary Network Lines"
                        )
                    ]
                )

                mains.append(SpatialFeature(
                    feature_id=f"msd_main_{obj_id}",
                    feature_type="public_sanitary_main",
                    geometry_type=geom.get("type", "LineString"),
                    coordinates=geom.get("coordinates", []),
                    attributes={
                        "material": props.get("MATERIAL", "UNKNOWN"),
                        "diameter_inches": props.get("DIAMETER"),
                        "facility_id": props.get("FACILITYID"),
                        "install_date": props.get("INSTALLDATE"),
                        "raw_properties": props
                    },
                    provenance=line_provenance
                ))

        except Exception as e:
            print(f"[WARN] Failed to retrieve MSD line geometry: {e}", flush=True)

        try:
            points_geojson = self.query_layer_geojson(self.SAN_POINTS_LAYER, bbox)
            features = points_geojson.get("features", [])
            print(f"[MSD GIS] Found {len(features)} public network point structures.", flush=True)

            for feat in features:
                geom = feat.get("geometry", {})
                props = feat.get("properties", {})
                obj_id = str(feat.get("id") or props.get("OBJECTID") or props.get("FACILITYID") or "unknown_point")

                point_provenance = ProvenanceRecord(
                    evidence_state=EvidenceState.DOCUMENTED_MAPPED,
                    source_type=SourceType.PUBLIC_GIS,
                    source_id=f"msd_arcgis_layer_1_point_{obj_id}",
                    confidence_limitations="Source-backed municipal point structure (manhole / junction).",
                    visual_allowance=VisualAllowance.POINT_MARKER,
                    supporting_media=[
                        SupportingMedia(
                            media_type="document",
                            url="https://services2.arcgis.com/w657bnjzrjguNyOy/ArcGIS/rest/services/MSD_Infrastructure_Complete/FeatureServer/1",
                            segment_description="MSD Infrastructure Complete - Sanitary Network Points"
                        )
                    ]
                )

                manholes.append(SpatialFeature(
                    feature_id=f"msd_point_{obj_id}",
                    feature_type="public_manhole_or_junction",
                    geometry_type=geom.get("type", "Point"),
                    coordinates=geom.get("coordinates", []),
                    attributes={
                        "structure_type": props.get("SUBTYPE", "MANHOLE"),
                        "rim_elevation": props.get("RIMELEV"),
                        "invert_elevation": props.get("INVERTELEV"),
                        "facility_id": props.get("FACILITYID"),
                        "raw_properties": props
                    },
                    provenance=point_provenance
                ))

        except Exception as e:
            print(f"[WARN] Failed to retrieve MSD point geometry: {e}", flush=True)

        return PublicInfrastructure(mains=mains, manholes=manholes)


if __name__ == "__main__":
    florissant_bbox = (-90.3168, 38.8021, -90.3150, 38.8035)
    
    client = MSDGISClient()
    infrastructure = client.fetch_public_infrastructure(florissant_bbox)
    
    print("\n--- Ingested Public Infrastructure ---")
    print(f"Mains count: {len(infrastructure.mains)}")
    print(f"Manholes count: {len(infrastructure.manholes)}")
    if infrastructure.mains:
        first_main = infrastructure.mains[0]
        print(f"Sample Main ID: {first_main.feature_id}")
        print(f"Evidence State: {first_main.provenance.evidence_state.value}")
        print(f"Visual Allowance: {first_main.provenance.visual_allowance.value}")