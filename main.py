import os
import json
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models.provenance import ProvenanceRecord, EvidenceState, SourceType, VisualAllowance
from models.site_model import PublicInfrastructure
from services.geocoder import get_site_context
from services.msd_gis_client import MSDGISClient
from services.spatial_transformer import build_freshprint_model

app = FastAPI(title="Freshprint Evidence Engine")

app.mount("/static", StaticFiles(directory="static"), name="static")

def load_private_inspection(file_path: str = "data/superior_sewer_report.json") -> dict:
    if not os.path.exists(file_path):
        print(f"[WARN] {file_path} not found. Using fallback inspection data.")
        return {
            "inspected_systems": [{
                "system_type": "sewer_lateral",
                "materials_observed": ["cast_iron", "clay", "pvc"],
                "connectivity_route": ["msd_public_main", "cast_transition", "roof_vent"],
                "spatial_provenance": {
                    "evidence_state": "approximate",
                    "confidence_limitations": "Locator interference reported. Route is assumed."
                },
                "findings": [{
                    "finding_type": "break_or_crack",
                    "description": "Break / crack in line.",
                    "estimated_depth_ft": "3-4",
                    "action_required": "repair_recommended"
                }],
                "supporting_evidence": []
            }]
        }
        
    with open(file_path, "r") as f:
        return json.load(f)

@app.get("/api/generate-site")
async def generate_evidence_payload(
    address: str = Query(
        default="505 Ridge Dr, Florissant, MO 63033",
        description="Target property address to process"
    )
):
    try:
        print(f"\n[Pipeline] 🚀 Generating spatial evidence for: {address}")

        site_context = get_site_context(address)
        lat, lon = site_context["coordinates"]
        parcel_data = site_context["parcel_data"]
        bbox = parcel_data["bounding_box"]

        is_fallback = parcel_data["footprint_is_fallback"]
        
        overture_data = {
            "geographic_polygon": parcel_data["building_footprint"],
            "height_meters": parcel_data.get("building_height"),
            "provenance": ProvenanceRecord(
                evidence_state=EvidenceState.UNKNOWN if is_fallback else EvidenceState.APPROXIMATE,
                source_type=SourceType.ASSUMPTION if is_fallback else SourceType.PUBLIC_GIS,
                source_id="system_fallback_generator" if is_fallback else "overture_maps_global_buildings",
                confidence_limitations=("Generic contextual placeholder — no GIS footprint found."
                                        if is_fallback else
                                        "Building footprints derived from global spatial datasets."),
                visual_allowance=(VisualAllowance.ILLUSTRATIVE_DASHED if is_fallback
                                else VisualAllowance.APPROXIMATE_RADIUS),
                supporting_media=[],
            ),
        }

        msd_client = MSDGISClient()
        msd_infrastructure = msd_client.fetch_public_infrastructure(bbox)

        private_report_json = load_private_inspection()

        print("[Pipeline] 📐 Transforming data into local WebGL space...")
        site_model = build_freshprint_model(
            address=site_context["address"],
            bbox=bbox,
            anchor_coordinates=(lat, lon),
            overture_data=overture_data,
            msd_infrastructure=msd_infrastructure,
            private_report_json=private_report_json
        )

        print("[Pipeline] 🎉 Generation complete.")
        return site_model

    except Exception as e:
        print(f"[ERROR] Pipeline failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pipeline Error: {str(e)}")

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")