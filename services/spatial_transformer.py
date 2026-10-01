import math
import hashlib
from typing import Tuple, List, Dict, Any

from models.provenance import (
    ProvenanceRecord,
    EvidenceState,
    SourceType,
    VisualAllowance,
    SupportingMedia,
    EvidenceReference,
    SpatialFeature
)
from models.site_model import (
    FreshprintSiteModel,
    BuildingContext,
    PublicInfrastructure,
    PrivateSewerSystem,
    InspectionFinding
)

def compute_meters_per_degree(lat: float) -> Tuple[float, float]:
    """Calculates the conversion factor from degrees to meters at a specific latitude."""
    lat_rad = math.radians(lat)
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    m_per_deg_lon = 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    return m_per_deg_lat, m_per_deg_lon

def geo_to_local(
    lat: float, 
    lon: float, 
    center_lat: float, 
    center_lon: float, 
    m_lat: float, 
    m_lon: float
) -> Tuple[float, float]:
    """Translates geographic coordinates into a local WebGL 2D Cartesian space (X, Z)."""
    x_m = (lon - center_lon) * m_lon
    z_m = -(lat - center_lat) * m_lat
    return x_m, z_m

def get_centroid(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Calculates the center point of a local X/Z polygon."""
    if not polygon:
        return 0.0, 0.0
    x_sum = sum(pt[0] for pt in polygon)
    z_sum = sum(pt[1] for pt in polygon)
    return x_sum / len(polygon), z_sum / len(polygon)

def closest_point_on_segment(
    pt: Tuple[float, float], 
    v: Tuple[float, float], 
    w: Tuple[float, float]
) -> Tuple[float, float]:
    """Finds the closest point on a line segment (v, w) to a point (pt)."""
    l2 = (w[0] - v[0])**2 + (w[1] - v[1])**2
    if l2 == 0:
        return v
    t = max(0, min(1, ((pt[0] - v[0]) * (w[0] - v[0]) + (pt[1] - v[1]) * (w[1] - v[1])) / l2))
    return (v[0] + t * (w[0] - v[0]), v[1] + t * (w[1] - v[1]))


def nearest_point_on_polygon(
    point: Tuple[float, float],
    polygon: List[Tuple[float, float]],
) -> Tuple[float, float]:
    """Return the footprint edge point nearest to a local point."""
    if len(polygon) < 2:
        return point

    nearest = polygon[0]
    min_dist = float("inf")
    for index, vertex in enumerate(polygon):
        next_vertex = polygon[(index + 1) % len(polygon)]
        candidate = closest_point_on_segment(point, vertex, next_vertex)
        dist = (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2
        if dist < min_dist:
            min_dist = dist
            nearest = candidate
    return nearest

def build_freshprint_model(
    address: str,
    bbox: Tuple[float, float, float, float],
    overture_data: Dict[str, Any],
    msd_infrastructure: PublicInfrastructure,
    private_report_json: Dict[str, Any],
    anchor_coordinates: Tuple[float, float]
) -> FreshprintSiteModel:
    """
    Ingests all raw sources (Overture, MSD GIS, Superior Sewer JSON), 
    projects them into a unified local coordinate system, and generates
    the spatial connections bounded by strict evidence rules.
    """
    
    house_geo = overture_data.get("geographic_polygon") or []
    center_lat, center_lon = anchor_coordinates
    if house_geo:
        center_lat = sum(pt[0] for pt in house_geo) / len(house_geo)
        center_lon = sum(pt[1] for pt in house_geo) / len(house_geo)
    m_lat, m_lon = compute_meters_per_degree(center_lat)

    local_footprint = []
    for lat, lon in house_geo:
        local_footprint.append(geo_to_local(lat, lon, center_lat, center_lon, m_lat, m_lon))
        
    building_context = BuildingContext(
        building_type="single_family",
        footprint_polygon=local_footprint,
        height_meters=overture_data["height_meters"],
        provenance=overture_data["provenance"]
    )
    
    house_centroid = get_centroid(local_footprint)

    # Select the nearest main for the private connectivity claim.
    selected_main = None
    selected_main_point = None
    selected_main_distance = float("inf")
    for main in msd_infrastructure.mains:
        raw_coords = main.coordinates
        if raw_coords and isinstance(raw_coords[0][0], list):
            raw_coords = raw_coords[0]
        local_coords = [
            list(geo_to_local(lat, lon, center_lat, center_lon, m_lat, m_lon))
            for lon, lat in raw_coords
        ]
        main.coordinates = local_coords
        for index in range(len(local_coords) - 1):
            candidate = closest_point_on_segment(
                house_centroid, local_coords[index], local_coords[index + 1]
            )
            distance = (candidate[0] - house_centroid[0]) ** 2 + (candidate[1] - house_centroid[1]) ** 2
            if distance < selected_main_distance:
                selected_main = main
                selected_main_point = candidate
                selected_main_distance = distance

    for manhole in msd_infrastructure.manholes:
        if manhole.coordinates and len(manhole.coordinates) >= 2:
            lon, lat = manhole.coordinates
            manhole.coordinates = list(
                geo_to_local(lat, lon, center_lat, center_lon, m_lat, m_lon)
            )

    if selected_main and selected_main_point:
        selected_main.attributes["selected_for_property"] = True

    house_edge = nearest_point_on_polygon(house_centroid, local_footprint)
    if selected_main_point:
        connection_point = selected_main_point
    else:
        edge_vector = (
            house_edge[0] - house_centroid[0],
            house_edge[1] - house_centroid[1],
        )
        edge_length = math.hypot(*edge_vector)
        if edge_length:
            unit_vector = (edge_vector[0] / edge_length, edge_vector[1] / edge_length)
            connection_point = (
                house_edge[0] + unit_vector[0] * 12.0,
                house_edge[1] + unit_vector[1] * 12.0,
            )
        else:
            connection_point = house_centroid

    # Use the footprint center as the roof-vent proxy until coordinates exist.
    procedural_lateral_coords = [house_centroid, connection_point]
    has_house_connection = connection_point != house_centroid

    system_data = private_report_json.get("inspected_systems", [])[0]
    report_metadata = private_report_json.get("document_metadata", {})
    report_source_id = report_metadata.get("source_id", "private_inspection_report")
    media_list = []
    for media in system_data.get("supporting_evidence", []):
        media_list.append(SupportingMedia(
            media_type=media.get("evidence_type", "video"),
            url=media.get("url"),
            segment_description=media.get("segment")
        ))
        
    schematic_lateral = SpatialFeature(
        feature_id="private_lateral_01",
        feature_type="private_sewer_lateral",
        geometry_type="LineString",
        coordinates=procedural_lateral_coords,
        attributes={
            "materials_observed": system_data.get("materials_observed"),
            "connectivity_route": system_data.get("connectivity_route"),
            "route_basis": "inspection videos and locator markings",
            "selected_public_main_distance_meters": round(math.sqrt(selected_main_distance), 2)
            if selected_main_point else None,
        },
        provenance=ProvenanceRecord(
            evidence_state=EvidenceState.APPROXIMATE,
            source_type=SourceType.PROFESSIONAL_INSPECTION,
            source_id=report_source_id,
            confidence_limitations=system_data.get("spatial_provenance", {}).get("confidence_limitations", "Assumed route based on connection points."),
            visual_allowance=VisualAllowance.APPROXIMATE_RADIUS,
            supporting_media=media_list,
            evidence_references=[
                EvidenceReference(
                    source_id=report_source_id,
                    reference_type="report",
                    locator="pages 4-8",
                    description="Roof access, materials, locator limitation, route observations, and inspection videos.",
                ),
                EvidenceReference(
                    source_id=selected_main.provenance.source_id if selected_main else "msd_arcgis_layer_3",
                    reference_type="gis_record",
                    locator=selected_main.feature_id if selected_main else None,
                    description="Nearest selected public sanitary main, retained as mapped context.",
                ),
            ],
        )
    )

    findings = []
    for raw_finding in system_data.get("findings", []):
        finding_coords = None
        finding_references = [
            EvidenceReference(
                source_id=report_source_id,
                reference_type="report",
                locator="page 6" if raw_finding["finding_type"] == "break_or_crack" else "page 7",
                description=raw_finding.get("description"),
            )
        ]
        
        finding_feature = SpatialFeature(
            feature_id=f"finding_{raw_finding['finding_type']}",
            feature_type="inspection_finding",
            geometry_type="Point" if finding_coords else "Unknown",
            coordinates=finding_coords,
            attributes={
                "depth": raw_finding.get("estimated_depth_ft"),
                "description": raw_finding.get("description"),
                "action_required": raw_finding.get("action_required"),
                "location_basis": "No survey-grade XY coordinate reported.",
            },
            provenance=ProvenanceRecord(
                evidence_state=EvidenceState.APPROXIMATE,
                source_type=SourceType.PROFESSIONAL_INSPECTION,
                source_id="superior_sewer_06012026",
                confidence_limitations="The report documents the condition, but does not establish survey-grade XY coordinates.",
                visual_allowance=VisualAllowance.POINT_MARKER,
                supporting_media=media_list,
                evidence_references=finding_references,
            )
        )
        
        findings.append(InspectionFinding(
            finding_type=raw_finding["finding_type"],
            description=raw_finding["description"],
            estimated_depth_ft=raw_finding.get("estimated_depth_ft"),
            action_required=raw_finding.get("action_required"),
            evidence_state=raw_finding.get("spatial_provenance", {}).get("evidence_state", "documented"),
            spatial_location=finding_feature if finding_coords else None,
            provenance=finding_feature.provenance
        ))

    private_system = PrivateSewerSystem(
        access_points=[], 
        lateral_lines=[schematic_lateral] if has_house_connection else [],
        findings=findings
    )

    site_id = hashlib.md5(address.strip().lower().encode('utf-8')).hexdigest()[:8]

    return FreshprintSiteModel(
        site_id=site_id,
        address=address,
        building=building_context,
        public_infrastructure=msd_infrastructure,
        private_infrastructure=private_system
    )