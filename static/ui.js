import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a1a);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 40, 60);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(50, 100, 50);
scene.add(dirLight);
scene.add(new THREE.GridHelper(80, 80, 0x444444, 0x222222));

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const interactableObjects = [];

const materials = {
    solid_hard_geometry: new THREE.MeshStandardMaterial({ color: 0x3b82f6, roughness: 0.4 }),
    illustrative_dashed: new THREE.LineDashedMaterial({ color: 0x10b981, dashSize: 1, gapSize: 1, linewidth: 2 }),
    approximate_line: new THREE.LineDashedMaterial({ color: 0xf59e0b, dashSize: 1, gapSize: 1, linewidth: 2 }),
    approximate_radius: new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.18, depthWrite: false }),
    point_marker_public: new THREE.MeshStandardMaterial({ color: 0x60a5fa }),
    point_marker_finding: new THREE.MeshStandardMaterial({ color: 0xef4444 }),
    point_marker_orange: new THREE.MeshStandardMaterial({ color: 0xf97316 }),
    point_marker_yellow: new THREE.MeshStandardMaterial({ color: 0xfacc15 }),
    building_context: new THREE.MeshStandardMaterial({ color: 0x333333, transparent: true, opacity: 0.8 }),
};

function createBuilding(buildingData) {
    if (!buildingData.footprint_polygon || buildingData.footprint_polygon.length === 0) return;
    
    const shape = new THREE.Shape();
    const pts = buildingData.footprint_polygon;
    
    shape.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) {
        shape.lineTo(pts[i][0], pts[i][1]);
    }
    
    const geometry = buildingData.height_meters
        ? new THREE.ExtrudeGeometry(shape, { depth: buildingData.height_meters, bevelEnabled: false })
        : new THREE.ShapeGeometry(shape);
    
    const mesh = new THREE.Mesh(geometry, materials.building_context);
    mesh.rotation.x = Math.PI / 2;
    mesh.position.y = buildingData.height_meters || 0.05;
    
    mesh.userData = { 
        type: "Building Context", 
        provenance: buildingData.provenance 
    };
    scene.add(mesh);
    interactableObjects.push(mesh);
}

function createPipeLine(feature, isPublic) {
    if (!feature.coordinates || feature.coordinates.length < 2) return;
    const points = feature.coordinates.map(pt => new THREE.Vector3(pt[0], feature.attributes.depth ? -parseFloat(feature.attributes.depth) * 0.3048 : 0.35, pt[1]));
    
    if (feature.provenance.visual_allowance === 'solid_hard_geometry') {
        // Preserve mapped vertices; do not interpolate public geometry.
        const path = new THREE.CurvePath();
        for (let index = 0; index < points.length - 1; index++) {
            path.add(new THREE.LineCurve3(points[index], points[index + 1]));
        }
        const geometry = new THREE.TubeGeometry(path, Math.max(1, points.length * 3), 0.4, 8, false);
        const mesh = new THREE.Mesh(geometry, materials.solid_hard_geometry);
        mesh.renderOrder = 2;
        mesh.userData = { type: feature.feature_type, attributes: feature.attributes, provenance: feature.provenance };
        scene.add(mesh);
        interactableObjects.push(mesh);
    } 
    else if (feature.provenance.visual_allowance === 'illustrative_dashed' ||
             feature.provenance.visual_allowance === 'approximate_radius') {
        const geoLine = new THREE.BufferGeometry().setFromPoints(points);
        const lineMaterial = feature.provenance.visual_allowance === 'approximate_radius'
            ? materials.approximate_line
            : materials.illustrative_dashed;
        const line = new THREE.Line(geoLine, lineMaterial);
        line.renderOrder = 3;
        line.computeLineDistances();
        
        const curve = new THREE.CatmullRomCurve3(points, false, 'chordal');
        const tubeGeo = new THREE.TubeGeometry(curve, 20, 1.2, 8, false);
        const tubeMesh = new THREE.Mesh(tubeGeo, materials.approximate_radius);
        tubeMesh.renderOrder = 2;
        
        const group = new THREE.Group();
        group.add(line);
        group.add(tubeMesh);
        group.userData = { type: feature.feature_type, attributes: feature.attributes, provenance: feature.provenance };
        
        scene.add(group);
        interactableObjects.push(tubeMesh);
    }
}

function createMarker(feature) {
    if (!feature || !feature.coordinates) return;
    const height = feature.attributes.display_height_meters || 0;
    const isFinding = feature.feature_type === 'inspection_finding';
    
    const geometry = new THREE.SphereGeometry(isFinding ? 0.8 : 0.6, 16, 16);
    const markerColor = feature.attributes.marker_color;
    const material = markerColor === '#f97316'
        ? materials.point_marker_orange
        : markerColor === '#facc15'
            ? materials.point_marker_yellow
            : isFinding ? materials.point_marker_finding : materials.point_marker_public;
    
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(feature.coordinates[0], height, feature.coordinates[1]);
    mesh.userData = { type: feature.feature_type, attributes: feature.attributes, provenance: feature.provenance };
    
    scene.add(mesh);
    interactableObjects.push(mesh);
}

function frameHouse(buildingData) {
    const points = buildingData.footprint_polygon || [];
    if (!points.length) return;

    const box = new THREE.Box3();
    points.forEach(point => box.expandByPoint(new THREE.Vector3(point[0], 0, point[1])));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.z, 12);

    controls.target.set(center.x, 0, center.z);
    camera.position.set(center.x + radius * 1.5, radius * 1.35, center.z + radius * 1.5);
    camera.near = 0.1;
    camera.far = Math.max(500, radius * 20);
    camera.updateProjectionMatrix();
}

export async function loadSiteData(address) {
    const objectsToRemove = [...interactableObjects];
    objectsToRemove.forEach(obj => {
        if(obj.parent && obj.parent.type === 'Group') {
            scene.remove(obj.parent);
        } else {
            scene.remove(obj);
        }
    });
    interactableObjects.length = 0;

    try {
        const res = await fetch(`/api/generate-site?address=${encodeURIComponent(address)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);

        if (data.building) {
            createBuilding(data.building);
            frameHouse(data.building);
        }

        const publicMains = data.public_infrastructure?.mains || [];
        const privateInfrastructure = data.private_infrastructure || {};
        const lateralLines = privateInfrastructure.lateral_lines || [];
        const findings = privateInfrastructure.findings || [];

        publicMains.forEach(main => createPipeLine(main, true));
        (data.public_infrastructure?.manholes || []).forEach(manhole => createMarker(manhole));
        lateralLines.forEach(lat => createPipeLine(lat, false));
        findings.forEach(finding => createMarker(finding.spatial_location));

        if (!publicMains.length && !lateralLines.length) {
            throw new Error('Evidence payload contains no renderable sewer geometry.');
        }
        
    } catch (err) {
        console.error("Failed to load evidence model:", err);
    }
}

window.addEventListener('pointerdown', (event) => {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'BUTTON' || event.target.closest('#evidence-panel')) return;

    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(interactableObjects, false);

    if (intersects.length > 0) {
        const objectData = intersects[0].object.userData;
        const data = objectData.provenance ? objectData : intersects[0].object.parent.userData;
        updateSidebar(data);
    } else {
        document.getElementById('evidence-panel').style.display = 'none';
    }
});

function updateSidebar(data) {
    const panel = document.getElementById('evidence-panel');
    const prov = data.provenance;
    
    let mediaHtml = '';
    if (prov.supporting_media && prov.supporting_media.length > 0) {
        mediaHtml = '<h4>Supporting Evidence</h4><ul>' + 
            prov.supporting_media.map(m => `<li><a href="${m.url}" target="_blank">${m.segment_description || m.media_type}</a></li>`).join('') + 
            '</ul>';
    }

    let attrHtml = '';
    if (data.attributes && Object.keys(data.attributes).length > 0) {
        attrHtml = '<h4>Attributes</h4><ul>' + 
            Object.entries(data.attributes).map(([k, v]) => `<li><strong>${k}:</strong> ${JSON.stringify(v)}</li>`).join('') + 
            '</ul>';
    }

    panel.innerHTML = `
        <h3>${data.type ? data.type.replace(/_/g, ' ').toUpperCase() : 'UNKNOWN'}</h3>
        <div class="tag ${prov.evidence_state}">${prov.evidence_state.replace(/_/g, ' ').toUpperCase()}</div>
        <p><strong>Source:</strong> ${prov.source_type} (${prov.source_id})</p>
        <p class="limitations"><strong>Limitations:</strong> ${prov.confidence_limitations}</p>
        ${attrHtml}
        ${mediaHtml}
    `;
    panel.style.display = 'block';
}

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();