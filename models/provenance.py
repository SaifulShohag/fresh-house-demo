from enum import Enum
from typing import Optional, List, Dict, Any, Union, Tuple
from pydantic import BaseModel, ConfigDict, Field

class EvidenceState(str, Enum):
    """
    The core ontological state of the data, as requested by Fresh House.
    Dictates how the system interprets the existence of the feature.
    """
    DOCUMENTED_MAPPED = "documented_mapped"
    APPROXIMATE = "approximate"
    RECONSTRUCTED_SCHEMATIC = "reconstructed_schematic"
    UNKNOWN = "unknown"

class SourceType(str, Enum):
    """Categorizes the origin of the data to track liability and authority."""
    PUBLIC_GIS = "public_gis"
    PROFESSIONAL_INSPECTION = "professional_inspection"
    MUNICIPAL_RECORD = "municipal_record"
    AI_EXTRACTION = "ai_extraction"
    PROCEDURAL_GENERATION = "procedural_generation"
    ASSUMPTION = "assumption"

class VisualAllowance(str, Enum):
    """
    Directives for the Three.js renderer. This ensures the frontend does not 
    accidentally render an assumption as a hard fact.
    """
    SOLID_HARD_GEOMETRY = "solid_hard_geometry"
    APPROXIMATE_RADIUS = "approximate_radius"
    ILLUSTRATIVE_DASHED = "illustrative_dashed"
    POINT_MARKER = "point_marker"
    HIDDEN = "hidden"

class SupportingMedia(BaseModel):
    """Links spatial geometry directly to the real-world evidence."""
    media_type: str = Field(..., description="e.g., 'video', 'photograph', 'document'")
    url: str = Field(..., description="Direct link to the media (e.g., Dropbox video url)")
    segment_description: Optional[str] = Field(None, description="What this media proves (e.g., 'MSD to cast transition')")
    timestamp_start: Optional[str] = Field(None, description="Start time if a video")
    timestamp_end: Optional[str] = Field(None, description="End time if a video")


class EvidenceReference(BaseModel):
    """A stable pointer to the source claim supporting a feature."""
    source_id: str
    reference_type: str = Field(..., description="report, video, gis_record, or photograph")
    locator: Optional[str] = Field(None, description="Page, section, segment, or record identifier")
    description: Optional[str] = None

class ProvenanceRecord(BaseModel):
    """
    The central ledger for any piece of data in the Freshprint system.
    Every geometry, finding, or attribute must be wrapped in this record.
    """
    evidence_state: EvidenceState = Field(
        ..., 
        description="The strict classification of how this data is known."
    )
    source_type: SourceType
    source_id: str = Field(
        ..., 
        description="A unique identifier for the source document (e.g., 'superior_sewer_06012026', 'msd_layer_3')."
    )
    confidence_limitations: Optional[str] = Field(
        None, 
        description="Explicitly documents any limitations (e.g., 'Locator interference reported; not positive on markings')."
    )
    visual_allowance: VisualAllowance = Field(
        ..., 
        description="Strict instruction to the renderer on how to display this data safely."
    )
    supporting_media: List[SupportingMedia] = Field(
        default_factory=list,
        description="Original videos, photos, or documents backing this specific claim."
    )
    evidence_references: List[EvidenceReference] = Field(
        default_factory=list,
        description="Source-level references that support the claim represented by this feature."
    )

class SpatialFeature(BaseModel):
    """
    A generic container that binds physical geometry and attributes 
    to a strict ProvenanceRecord.
    """
    model_config = ConfigDict(validate_assignment=True)
    feature_id: str = Field(..., description="Unique ID for this specific feature/pipe/finding")
    feature_type: str = Field(..., description="e.g., 'public_sewer_main', 'private_lateral', 'pipe_break'")
    geometry_type: str = Field(..., description="GeoJSON types: 'LineString', 'Point', 'Polygon', 'Unknown'")
    coordinates: Union[List[List[float]], List[float], None] = None
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source attributes associated with this spatial feature."
    )
    provenance: ProvenanceRecord = Field(
        ...,
        description="Evidence and rendering rules for this spatial feature."
    )