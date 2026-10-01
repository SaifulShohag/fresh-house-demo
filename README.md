# Freshprint Evidence Engine

Freshprint Evidence Engine is a prototype spatial evidence viewer for residential sewer infrastructure. It combines property context, public sanitary GIS, and professional inspection evidence into a local coordinate model that can be rendered in a Three.js viewer.

## Live Demo

- Viewer: https://fresh-house-demo.onrender.com/
- API: https://fresh-house-demo.onrender.com/api/generate-site

The deployed prototype currently uses the address `505 Ridge Dr, Florissant, MO 63033` and the inspection data in `data/superior_sewer_report.json`.

## Capabilities

- Geocodes an address through OpenStreetMap Nominatim.
- Retrieves a building footprint and height through the Overture Maps CLI.
- Queries MSD sanitary network lines and points through ArcGIS FeatureServer.
- Loads professional sewer inspection evidence from a normalized JSON report.
- Projects source geometries into a local WebGL coordinate system.
- Renders public infrastructure and approximate private sewer evidence in Three.js.
- Preserves evidence state, source identifiers, limitations, report references, and supporting media.
- Provides clickable geometry and evidence details in the viewer.

## Evidence Model

Every spatial feature carries provenance information describing what Freshprint is allowed to represent visually.

| Evidence state | Meaning |
| --- | --- |
| `documented_mapped` | Directly established by a mapped source such as MSD GIS. |
| `approximate` | Supported by evidence but not survey-grade. |
| `reconstructed_schematic` | Procedurally created to explain evidence without claiming measurement. |
| `unknown` | Not established by the available sources. |

The public MSD sanitary network is mapped context. The private sewer lateral is an approximate connection supported by the inspection report, locator markings, route description, and inspection videos. The report does not provide survey-grade XY coordinates for the private lateral or findings, so those locations are not presented as exact points.

## Architecture

```text
Address
  -> Geocoding and property context
  -> Overture building footprint
  -> MSD sanitary GIS lines and points
  -> Private inspection report JSON
  -> Evidence and spatial normalization
  -> Local WebGL coordinate model
  -> FastAPI payload
  -> Three.js viewer
```

### Main Components

- `main.py`: FastAPI application and site-generation endpoint.
- `services/geocoder.py`: Address lookup and Overture building extraction.
- `services/msd_gis_client.py`: MSD ArcGIS sanitary infrastructure client.
- `services/spatial_transformer.py`: Coordinate normalization and evidence-backed model construction.
- `models/provenance.py`: Evidence state, provenance, source references, and media models.
- `models/site_model.py`: Normalized property, infrastructure, and finding models.
- `data/superior_sewer_report.json`: Current private inspection source.
- `static/index.html`: Viewer shell and controls.
- `static/ui.js`: Three.js scene, geometry rendering, and evidence interaction.

## Local Development

### Requirements

- Python 3.10 or newer
- Overture Maps CLI available on the system path
- Network access to Nominatim, Overture Maps, and MSD ArcGIS services

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` file only when required by future integrations. Never commit credentials or place them in this README.

### Run

```powershell
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/ in a browser.

### API Request

```text
GET /api/generate-site?address=505%20Ridge%20Dr%2C%20Florissant%2C%20MO%2063033
```

The response contains the normalized building, public infrastructure, private infrastructure, findings, provenance, supporting media, and the local coordinate reference system.

## Deployment on Render

Deployment is defined in `render.yaml`.

The service uses:

```text
Build: pip install -r requirements.txt
Start: uvicorn main:app --host 0.0.0.0 --port $PORT
Health check: /
```

To deploy:

1. Create a new Render Blueprint or Web Service from the repository.
2. Use the included `render.yaml`, or configure the build and start commands above.
3. Add runtime secrets through the Render dashboard instead of committing them.
4. Confirm the health check and `/api/generate-site` endpoint after deployment.

## Prototype Limitations

- The private report source is currently a fixed JSON file rather than a property-upload workflow.
- The private lateral geometry is approximate and uses the building center as a roof-access proxy when no roof-vent coordinates are available.
- Inspection findings retain their report evidence but do not receive fabricated XY coordinates.
- Overture footprints are mapped context and are not survey-grade.
- MSD data is source-backed public context; it does not establish the private lateral route.
- The Overture CLI and external GIS services must be available to the deployment environment.
- The current viewer is a prototype and is not a substitute for a utility locate, survey, excavation plan, or engineering determination.

## Security

- Keep `.env` out of version control.
- Store production credentials in Render environment variables.
- Rotate any credentials that have been exposed or shared outside the deployment environment.
- Do not place API keys, tokens, inspection credentials, or private media URLs in source control.

## License

No license has been specified for this prototype.
