import json
import subprocess
from typing import Tuple, List, Dict, Any
from models.provenance import ProvenanceRecord, EvidenceState, SourceType, VisualAllowance

class OvertureClient:
    def __init__(self, offset_degrees: float = 0.0004):
        self.offset = offset_degrees

    def fetch_site_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Fetches the selected building footprint and height from Overture Maps.
        """
        bbox = (lon - self.offset, lat - self.offset, lon + self.offset, lat + self.offset)
        bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        
        building_footprint = None
        building_height = None
        
        try:
            print(f"[GIS] Fetching Overture Maps buildings for bbox: {bbox_str}", flush=True)
            result = subprocess.run(
                ["overturemaps", "download", "--bbox", bbox_str, "-f", "geojson", "--type", "building"],
                capture_output=True, 
                text=True, 
                check=True
            )
            
            geojson_data = json.loads(result.stdout)
            
            if geojson_data.get("features"):
                min_dist = float('inf')
                
                for feature in geojson_data["features"]:
                    geometry = feature.get("geometry", {})
                    properties = feature.get("properties", {})
                    
                    if geometry.get("type") == "Polygon":
                        raw_coords = geometry["coordinates"][0]
                        
                        avg_lon = sum(c[0] for c in raw_coords) / len(raw_coords)
                        avg_lat = sum(c[1] for c in raw_coords) / len(raw_coords)
                        dist = (avg_lon - lon)**2 + (avg_lat - lat)**2
                        
                        if dist < min_dist:
                            min_dist = dist
                            building_footprint = [(p_lat, p_lon) for p_lon, p_lat in raw_coords]
                            building_height = properties.get("height")
                            
                if building_footprint:
                    print(f"[GIS] ✅ Successfully extracted building footprint from Overture.", flush=True)

        except FileNotFoundError:
            print("[WARN] 'overturemaps' CLI tool not found. Ensure it is installed.", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Overture Maps extraction failed: {e.stderr}", flush=True)
        except Exception as e:
            print(f"[WARN] Overture Maps building extraction bypassed: {e}", flush=True)

        if building_footprint:
            provenance = ProvenanceRecord(
                evidence_state=EvidenceState.APPROXIMATE,
                source_type=SourceType.PUBLIC_GIS,
                source_id="overture_maps_global_buildings",
                confidence_limitations="Building footprints and heights are derived from global ML/satellite datasets. Sufficient for context, but not survey-grade.",
                visual_allowance=VisualAllowance.APPROXIMATE_RADIUS,
                supporting_media=[]
            )
        else:
            print("[WARN] Generating fallback building context footprint.", flush=True)
            building_footprint = None
            building_height = None
            
            provenance = ProvenanceRecord(
                evidence_state=EvidenceState.UNKNOWN,
                source_type=SourceType.ASSUMPTION,
                source_id="system_fallback_generator",
                confidence_limitations="No GIS building footprint found. This is a generic contextual placeholder.",
                visual_allowance=VisualAllowance.ILLUSTRATIVE_DASHED,
                supporting_media=[]
            )

        return {
            "geographic_polygon": building_footprint,
            "height_meters": building_height,
            "provenance": provenance,
        }

if __name__ == "__main__":
    test_lat = 38.8028
    test_lon = -90.3159
    
    client = OvertureClient()
    data = client.fetch_site_data(test_lat, test_lon)
    
    print("\n--- Extracted Evidence ---")
    print(f"Points: {len(data['geographic_polygon'])}")
    print(f"Height: {data['height_meters']}m")
    print(f"Evidence State: {data['provenance'].evidence_state.value}")
    print(f"Visual Allowance: {data['provenance'].visual_allowance.value}")