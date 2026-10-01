from typing import List, Tuple, Optional
from pydantic import BaseModel, Field
from models.provenance import ProvenanceRecord, SpatialFeature

class BuildingContext(BaseModel):
    """
    Represents the property structure serving as the spatial anchor for the underground utilities.
    """
    building_type: str = Field(default="single_family")
    footprint_polygon: List[Tuple[float, float]] = Field(
        ..., 
        description="List of [x, z] coordinates representing the building footprint in local meters."
    )
    height_meters: Optional[float] = Field(
        None, 
        description="Extruded height of the building for the 3D block representation."
    )
    provenance: ProvenanceRecord = Field(
        ..., 
        description="Tracks the source of this geometry (e.g., Overture Maps extraction)."
    )

class InspectionFinding(BaseModel):
    """
    Represents a specific defect, observation, or missing component from a professional inspection.
    """
    finding_type: str = Field(..., description="e.g., 'break_or_crack', 'root_intrusion', 'missing_yard_vent'")
    description: str = Field(..., description="Details from the inspection report.")
    estimated_depth_ft: Optional[str] = Field(None, description="Reported depth below grade, if provided.")
    evidence_state: str = Field(default="documented", description="State of the reported condition itself.")
    action_required: Optional[str] = Field(None, description="e.g., 'repair_recommended'")
    spatial_location: Optional[SpatialFeature] = Field(
        None, 
        description="A Point feature representing the location in the 3D scene, if mathematically deducible."
    )
    provenance: ProvenanceRecord = Field(
        ...,
        description="Tracks the evidence state of this finding, ensuring assumed locations aren't rendered as exact coordinates."
    )

class PublicInfrastructure(BaseModel):
    mains: List[SpatialFeature] = Field(default_factory=list)
    manholes: List[SpatialFeature] = Field(default_factory=list)

class PrivateSewerSystem(BaseModel):
    """
    The collection of private plumbing assets and inspection findings for a specific property.
    """
    access_points: List[SpatialFeature] = Field(
        default_factory=list,
        description="Points where the system was accessed or located (e.g., roof vents, yard vents, cleanouts)."
    )
    lateral_lines: List[SpatialFeature] = Field(
        default_factory=list, 
        description="The pipe paths connecting the house to the public main. Usually schematic or approximate."
    )
    findings: List[InspectionFinding] = Field(
        default_factory=list,
        description="Defects and observations extracted from the inspector's report."
    )

class FreshprintSiteModel(BaseModel):
    """
    The final, normalized payload handed off to the Three.js rendering layer.
    The renderer iterates through these collections, relying entirely on the embedded 
    'visual_allowance' rules in the ProvenanceRecords to determine how to draw them.
    """
    site_id: str = Field(..., description="Unique hash generated from the property address.")
    address: str = Field(..., description="Formatted property address.")
    building: BuildingContext
    public_infrastructure: PublicInfrastructure
    private_infrastructure: PrivateSewerSystem
    coordinate_reference_system: str = Field(
        default="local_webgl_meters", 
        description="Indicates that all geographic data has been projected into local origin-based meters."
    )