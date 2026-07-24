import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import * as TWEEN from "https://unpkg.com/@tweenjs/tween.js@23.1.3/dist/tween.esm.js";

const VIEW_STATE = {
  CITY: "CITY",
  BUILDING: "BUILDING",
  LEVEL: "LEVEL",
  ROOM: "ROOM",
};

const MODEL_PATHS = {
  city: "./models/CityView.glb",
  building: "./models/HouseView.glb",
  level: "./models/LevelView.glb",
  room: "./models/RoomView.glb",
};

const appState = {
  currentView: VIEW_STATE.CITY,
  data: null,
  selectedLevel: null,
  selectedRoom: null,
  hoveredMesh: null,
  models: {
    city: null,
    building: null,
    level: null,
    room: null,
  },
  originalMaterials: new Map(),
  syntheticRoomsGroup: null,
};

const container = document.getElementById("viewerContainer");
const canvas = document.getElementById("threeCanvas");

const breadcrumbsEl = document.getElementById("breadcrumbs");
const metadataPanel = document.getElementById("metadataPanel");
const levelStatsPanel = document.getElementById("levelStatsPanel");
const schedulePanel = document.getElementById("schedulePanel");
const sharedParamsPanel = document.getElementById("sharedParamsPanel");

const levelSelect = document.getElementById("levelSelect");
const roomSelect = document.getElementById("roomSelect");
const stateBadge = document.getElementById("stateBadge");
const resetBtn = document.getElementById("resetBtn");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x09111b);
scene.fog = new THREE.Fog(0x09111b, 200, 2000);

const camera = new THREE.PerspectiveCamera(
  50,
  container.clientWidth / container.clientHeight,
  0.1,
  10000,
);
camera.position.set(30, 20, 30);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 5, 0);
controls.update();

const loader = new GLTFLoader();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

/* -----------------------------------------
   DEBUG STATUS
----------------------------------------- */
const debugStatus = document.createElement("div");
debugStatus.style.position = "absolute";
debugStatus.style.bottom = "16px";
debugStatus.style.left = "16px";
debugStatus.style.padding = "10px 12px";
debugStatus.style.background = "rgba(0,0,0,0.65)";
debugStatus.style.color = "#fff";
debugStatus.style.fontSize = "12px";
debugStatus.style.borderRadius = "8px";
debugStatus.style.zIndex = "20";
debugStatus.style.pointerEvents = "none";
debugStatus.textContent = "Initializing viewer...";
container.appendChild(debugStatus);

function setDebug(message) {
  debugStatus.textContent = message;
  console.log("[BIM VIEWER]", message);
}

/* -----------------------------------------
   SCENE
----------------------------------------- */

function setupScene() {
  const hemi = new THREE.HemisphereLight(0xd8ecff, 0x1c2635, 1.2);
  scene.add(hemi);

  const dir = new THREE.DirectionalLight(0xffffff, 1.4);
  dir.position.set(100, 120, 80);
  dir.castShadow = true;
  dir.shadow.mapSize.set(2048, 2048);
  scene.add(dir);

  const ambient = new THREE.AmbientLight(0xffffff, 0.45);
  scene.add(ambient);

  const grid = new THREE.GridHelper(1000, 100, 0x31506f, 0x1a2637);
  scene.add(grid);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(2000, 2000),
    new THREE.MeshStandardMaterial({ color: 0x0d1522, roughness: 0.95 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const axes = new THREE.AxesHelper(20);
  scene.add(axes);
}

/* -----------------------------------------
   HELPERS
----------------------------------------- */

function safe(v, fallback = "—") {
  return v === undefined || v === null || v === "" ? fallback : String(v);
}

function totalAssetsInBuilding() {
  const levels = appState.data?.building?.levels || [];
  return levels.reduce((sum, lvl) => {
    return (
      sum +
      (lvl.rooms || []).reduce(
        (rSum, room) => rSum + (room.assets?.length || 0),
        0,
      )
    );
  }, 0);
}

function totalRoomsInBuilding() {
  const levels = appState.data?.building?.levels || [];
  return levels.reduce((sum, lvl) => sum + (lvl.rooms?.length || 0), 0);
}

function getLevelById(levelId) {
  return appState.data?.building?.levels?.find((l) => l.id === levelId) || null;
}

function getRoomById(level, roomId) {
  return level?.rooms?.find((r) => r.id === roomId) || null;
}

function clearSceneModels() {
  ["city", "building", "level", "room"].forEach((key) => {
    if (appState.models[key]) scene.remove(appState.models[key]);
  });

  if (appState.syntheticRoomsGroup) {
    scene.remove(appState.syntheticRoomsGroup);
    appState.syntheticRoomsGroup = null;
  }
}

function computeBounds(object) {
  const box = new THREE.Box3().setFromObject(object);
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  return { box, center, size };
}

function centerModelAtOrigin(model) {
  const { center } = computeBounds(model);
  model.position.sub(center);
}

function fitCameraToObject(object, offset = 1.4) {
  const { box, center, size } = computeBounds(object);

  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
  cameraZ *= offset;

  const minZ = box.min.z;
  const cameraToFarEdge = minZ < 0 ? -minZ + cameraZ : cameraZ - minZ;

  camera.position.set(
    center.x + cameraZ * 0.8,
    center.y + cameraZ * 0.45,
    center.z + cameraZ,
  );
  controls.target.copy(center);

  camera.near = Math.max(0.1, maxDim / 1000);
  camera.far = Math.max(5000, cameraToFarEdge * 4);
  camera.updateProjectionMatrix();
  controls.update();
}

function tweenCamera(position, target, duration = 1200) {
  const pos = {
    x: camera.position.x,
    y: camera.position.y,
    z: camera.position.z,
  };
  const tar = {
    x: controls.target.x,
    y: controls.target.y,
    z: controls.target.z,
  };

  new TWEEN.Tween(pos)
    .to({ x: position.x, y: position.y, z: position.z }, duration)
    .easing(TWEEN.Easing.Cubic.InOut)
    .onUpdate(() => camera.position.set(pos.x, pos.y, pos.z))
    .start();

  new TWEEN.Tween(tar)
    .to({ x: target.x, y: target.y, z: target.z }, duration)
    .easing(TWEEN.Easing.Cubic.InOut)
    .onUpdate(() => {
      controls.target.set(tar.x, tar.y, tar.z);
      controls.update();
    })
    .start();
}

function preserveMaterial(mesh) {
  if (!appState.originalMaterials.has(mesh.uuid)) {
    appState.originalMaterials.set(mesh.uuid, mesh.material);
  }
}

function restoreMaterial(mesh) {
  if (appState.originalMaterials.has(mesh.uuid)) {
    mesh.material = appState.originalMaterials.get(mesh.uuid);
  }
}

function makeHighlight(color = 0x59b7ff, opacity = 0.45) {
  return new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.2,
    transparent: true,
    opacity,
    roughness: 0.4,
  });
}

function clearHover() {
  if (appState.hoveredMesh) {
    restoreMaterial(appState.hoveredMesh);
    appState.hoveredMesh = null;
  }
}

function setHover(mesh, color) {
  if (appState.hoveredMesh && appState.hoveredMesh !== mesh) {
    restoreMaterial(appState.hoveredMesh);
  }
  preserveMaterial(mesh);
  mesh.material = makeHighlight(color);
  appState.hoveredMesh = mesh;
}

function updateBadge() {
  const map = {
    CITY: "City View",
    BUILDING: "Building View",
    LEVEL: "Level View",
    ROOM: "Room View",
  };
  stateBadge.textContent = map[appState.currentView] || "View";
}

function buildBreadcrumbs() {
  breadcrumbsEl.innerHTML = "";

  const crumbs = [
    {
      label: "City View",
      action: () => goToCityView(),
      active: appState.currentView === VIEW_STATE.CITY,
    },
    {
      label: appState.data?.building?.name || "Toronto Tower",
      action: () => goToBuildingView(),
      active: appState.currentView === VIEW_STATE.BUILDING,
    },
  ];

  if (appState.selectedLevel) {
    crumbs.push({
      label: appState.selectedLevel.name,
      action: () => goToLevelView(appState.selectedLevel.id),
      active: appState.currentView === VIEW_STATE.LEVEL,
    });
  }

  if (appState.selectedRoom) {
    crumbs.push({
      label: `${appState.selectedRoom.number} - ${appState.selectedRoom.name}`,
      action: () =>
        goToRoomView(appState.selectedLevel.id, appState.selectedRoom.id),
      active: appState.currentView === VIEW_STATE.ROOM,
    });
  }

  crumbs.forEach((crumb, i) => {
    const btn = document.createElement("button");
    btn.className = `crumb ${crumb.active ? "active" : ""}`;
    btn.textContent = crumb.label;
    btn.addEventListener("click", crumb.action);
    breadcrumbsEl.appendChild(btn);

    if (i < crumbs.length - 1) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = ">";
      breadcrumbsEl.appendChild(sep);
    }
  });
}

/* -----------------------------------------
   UI
----------------------------------------- */

function renderMetadata() {
  const b = appState.data?.building;
  if (!b) {
    metadataPanel.innerHTML = `<div class="empty">No metadata loaded.</div>`;
    return;
  }

  metadataPanel.innerHTML = `
    <div class="meta-grid">
      <div class="meta-item"><div class="meta-label">Building ID</div><div class="meta-value">${safe(b.id)}</div></div>
      <div class="meta-item"><div class="meta-label">Building Name</div><div class="meta-value">${safe(b.name)}</div></div>
      <div class="meta-item"><div class="meta-label">Floor Count</div><div class="meta-value">${safe(b.floors)}</div></div>
      <div class="meta-item"><div class="meta-label">Level Count</div><div class="meta-value">${safe(b.levels?.length || 0)}</div></div>
      <div class="meta-item"><div class="meta-label">Room Count</div><div class="meta-value">${safe(totalRoomsInBuilding())}</div></div>
      <div class="meta-item"><div class="meta-label">Asset Count</div><div class="meta-value">${safe(totalAssetsInBuilding())}</div></div>
    </div>
  `;
}

function renderEmptyStats() {
  levelStatsPanel.innerHTML = `<div class="empty">Select a level to see floor KPIs.</div>`;
}

function renderLevelStats(level) {
  const rooms = level.rooms || [];
  const roomCount = rooms.length;
  const area = rooms.reduce((sum, room) => sum + (room.area_sqm || 0), 0);
  const assetCount = rooms.reduce(
    (sum, room) => sum + (room.assets?.length || 0),
    0,
  );

  levelStatsPanel.innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-title">Level Name</div><div class="kpi-value">${safe(level.name)}</div></div>
      <div class="kpi-card"><div class="kpi-title">Level ID</div><div class="kpi-value">${safe(level.id)}</div></div>
      <div class="kpi-card"><div class="kpi-title">Room Count</div><div class="kpi-value">${roomCount}</div></div>
      <div class="kpi-card"><div class="kpi-title">Area</div><div class="kpi-value">${area.toFixed(2)} m²</div></div>
      <div class="kpi-card"><div class="kpi-title">Assets</div><div class="kpi-value">${assetCount}</div></div>
      <div class="kpi-card"><div class="kpi-title">Occupancy</div><div class="kpi-value">${roomCount * 2}</div></div>
    </div>
  `;
}

function renderEmptySchedule() {
  schedulePanel.innerHTML = `<div class="empty">Select a level or room to view schedules.</div>`;
}

function renderSchedule(level, selectedRoomId = null) {
  const rows = [];

  (level.rooms || []).forEach((room) => {
    if (selectedRoomId && room.id !== selectedRoomId) return;

    if ((room.assets || []).length === 0) {
      rows.push({
        roomNumber: room.number,
        roomName: room.name,
        assetFamily: "No Assets",
        assetType: "—",
        qty: 0,
      });
    } else {
      room.assets.forEach((asset) => {
        rows.push({
          roomNumber: room.number,
          roomName: room.name,
          assetFamily: asset.family || "—",
          assetType: asset.type || "—",
          qty: 1,
        });
      });
    }
  });

  schedulePanel.innerHTML = rows.length
    ? `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Room #</th>
            <th>Room Name</th>
            <th>Family</th>
            <th>Type</th>
            <th>Qty</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr>
              <td>${safe(row.roomNumber)}</td>
              <td>${safe(row.roomName)}</td>
              <td>${safe(row.assetFamily)}</td>
              <td>${safe(row.assetType)}</td>
              <td>${safe(row.qty)}</td>
            </tr>
          `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `
    : `<div class="empty">No schedule data found.</div>`;
}

function renderEmptySharedParams() {
  sharedParamsPanel.innerHTML = `<div class="empty">Select a room to inspect asset shared parameters.</div>`;
}

function renderSharedParams(room) {
  const assets = room.assets || [];
  if (!assets.length) {
    sharedParamsPanel.innerHTML = `<div class="empty">This room has no assets.</div>`;
    return;
  }

  sharedParamsPanel.innerHTML = assets
    .map((asset) => {
      const shared = asset.shared_parameters || {};
      const rows = Object.keys(shared).length
        ? Object.entries(shared)
            .map(
              ([k, v]) => `
        <div class="detail-row">
          <span class="key">${k}</span>
          <span class="val">${safe(v)}</span>
        </div>
      `,
            )
            .join("")
        : `
        <div class="detail-row">
          <span class="key">Shared Parameters</span>
          <span class="val">None</span>
        </div>
      `;

      return `
      <div class="asset-card">
        <h4>${safe(asset.family)}</h4>
        <div class="detail-row"><span class="key">Asset ID</span><span class="val">${safe(asset.id)}</span></div>
        <div class="detail-row"><span class="key">Type</span><span class="val">${safe(asset.type)}</span></div>
        ${rows}
      </div>
    `;
    })
    .join("");
}

/* -----------------------------------------
   DATA
----------------------------------------- */

async function loadData() {
  setDebug("Loading building_data.json...");
  const response = await fetch("./building_data.json");
  if (!response.ok) throw new Error("Failed to load building_data.json");
  appState.data = await response.json();
  populateLevelSelect();
  setDebug("building_data.json loaded");
}

function populateLevelSelect() {
  levelSelect.innerHTML = `<option value="">Select Level</option>`;
  const levels = appState.data?.building?.levels || [];
  levels.forEach((level) => {
    const option = document.createElement("option");
    option.value = level.id;
    option.textContent = level.name;
    levelSelect.appendChild(option);
  });
}

function populateRoomSelect(level) {
  roomSelect.innerHTML = `<option value="">Select Room</option>`;
  (level?.rooms || []).forEach((room) => {
    const option = document.createElement("option");
    option.value = room.id;
    option.textContent = `${room.number} - ${room.name}`;
    roomSelect.appendChild(option);
  });
}

/* -----------------------------------------
   MODEL LOADING
----------------------------------------- */

function loadModel(path) {
  return new Promise((resolve, reject) => {
    loader.load(
      path,
      (gltf) => resolve(gltf.scene),
      (xhr) => {
        if (xhr.total) {
          const pct = ((xhr.loaded / xhr.total) * 100).toFixed(0);
          setDebug(`Loading model: ${path} (${pct}%)`);
        } else {
          setDebug(`Loading model: ${path}`);
        }
      },
      (err) => reject(err),
    );
  });
}

function prepareModel(model) {
  model.traverse((child) => {
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;

      if (child.material) {
        child.material.side = THREE.DoubleSide;
      }
    }
  });
  return model;
}

async function showModel(key, path) {
  clearSceneModels();

  if (!appState.models[key]) {
    setDebug(`Loading ${key} model...`);
    const loaded = await loadModel(path);
    appState.models[key] = prepareModel(loaded);

    const info = computeBounds(appState.models[key]);
    console.log(`${key} bounds:`, info);
  }

  scene.add(appState.models[key]);

  // IMPORTANT: center large or offset models
  centerModelAtOrigin(appState.models[key]);
  fitCameraToObject(appState.models[key], 1.6);

  setDebug(`${key} model visible`);
  return appState.models[key];
}

/* -----------------------------------------
   FALLBACK ROOMS
----------------------------------------- */

function createSyntheticRoomMeshes(level) {
  if (appState.syntheticRoomsGroup) {
    scene.remove(appState.syntheticRoomsGroup);
    appState.syntheticRoomsGroup = null;
  }

  const group = new THREE.Group();
  const rooms = level.rooms || [];
  const cols = Math.ceil(Math.sqrt(rooms.length || 1));
  const spacing = 10;

  rooms.forEach((room, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;

    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(6, 3, 6),
      new THREE.MeshStandardMaterial({
        color: new THREE.Color().setHSL((i * 0.14) % 1, 0.55, 0.48),
        transparent: true,
        opacity: 0.65,
      }),
    );

    mesh.position.set(col * spacing, 1.5, row * spacing);
    mesh.userData.type = "room";
    mesh.userData.levelId = level.id;
    mesh.userData.roomId = room.id;
    group.add(mesh);
  });

  group.position.x = -((cols - 1) * spacing) / 2;
  group.position.z = -(Math.ceil(rooms.length / cols) * spacing) / 2;

  appState.syntheticRoomsGroup = group;
  scene.add(group);
}

/* -----------------------------------------
   VIEWS
----------------------------------------- */

async function goToCityView() {
  appState.currentView = VIEW_STATE.CITY;
  appState.selectedLevel = null;
  appState.selectedRoom = null;
  levelSelect.value = "";
  roomSelect.innerHTML = `<option value="">Select Room</option>`;

  await showModel("city", MODEL_PATHS.city);

  renderMetadata();
  renderEmptyStats();
  renderEmptySchedule();
  renderEmptySharedParams();
  buildBreadcrumbs();
  updateBadge();
}

async function goToBuildingView() {
  appState.currentView = VIEW_STATE.BUILDING;
  appState.selectedRoom = null;
  roomSelect.innerHTML = `<option value="">Select Room</option>`;

  await showModel("building", MODEL_PATHS.building);

  renderMetadata();
  renderEmptyStats();
  renderEmptySchedule();
  renderEmptySharedParams();
  buildBreadcrumbs();
  updateBadge();
}

async function goToLevelView(levelId) {
  const level = getLevelById(levelId);
  if (!level) return;

  appState.currentView = VIEW_STATE.LEVEL;
  appState.selectedLevel = level;
  appState.selectedRoom = null;

  levelSelect.value = level.id;
  populateRoomSelect(level);

  await showModel("level", MODEL_PATHS.level);
  createSyntheticRoomMeshes(level);

  if (appState.syntheticRoomsGroup) {
    fitCameraToObject(appState.syntheticRoomsGroup, 2.2);
  }

  renderMetadata();
  renderLevelStats(level);
  renderSchedule(level);
  renderEmptySharedParams();
  buildBreadcrumbs();
  updateBadge();
}

async function goToRoomView(levelId, roomId) {
  const level = getLevelById(levelId);
  if (!level) return;

  const room = getRoomById(level, roomId);
  if (!room) return;

  appState.currentView = VIEW_STATE.ROOM;
  appState.selectedLevel = level;
  appState.selectedRoom = room;

  levelSelect.value = level.id;
  populateRoomSelect(level);
  roomSelect.value = room.id;

  await showModel("room", MODEL_PATHS.room);

  const eye = room.camera?.eye || [0, 0, 0];
  const target = room.camera?.target || [0, 0, 0];
  const zeroCamera = eye.every((v) => v === 0) && target.every((v) => v === 0);

  if (zeroCamera) {
    setDebug("Room camera in JSON is [0,0,0], using fallback camera");
    fitCameraToObject(appState.models.room, 1.8);
  } else {
    tweenCamera(
      new THREE.Vector3(eye[0], eye[1], eye[2]),
      new THREE.Vector3(target[0], target[1], target[2]),
      1200,
    );
  }

  renderMetadata();
  renderLevelStats(level);
  renderSchedule(level, room.id);
  renderSharedParams(room);
  buildBreadcrumbs();
  updateBadge();
}

/* -----------------------------------------
   INTERACTION
----------------------------------------- */

function getPointer(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
}

function getInteractiveObjects() {
  const objects = [];

  if (appState.currentView === VIEW_STATE.CITY && appState.models.city) {
    appState.models.city.traverse((child) => {
      if (child.isMesh) objects.push(child);
    });
  }

  if (
    appState.currentView === VIEW_STATE.BUILDING &&
    appState.models.building
  ) {
    appState.models.building.traverse((child) => {
      if (child.isMesh) objects.push(child);
    });
  }

  if (
    (appState.currentView === VIEW_STATE.LEVEL ||
      appState.currentView === VIEW_STATE.ROOM) &&
    appState.syntheticRoomsGroup
  ) {
    appState.syntheticRoomsGroup.traverse((child) => {
      if (child.isMesh) objects.push(child);
    });
  }

  return objects;
}

function onPointerMove(event) {
  getPointer(event);
  raycaster.setFromCamera(pointer, camera);

  const objects = getInteractiveObjects();
  const hits = raycaster.intersectObjects(objects, true);

  if (!hits.length) {
    clearHover();
    container.style.cursor = "default";
    return;
  }

  const hit = hits[0].object;

  if (appState.currentView === VIEW_STATE.CITY) {
    setHover(hit, 0x7c6cff);
    container.style.cursor = "pointer";
    return;
  }

  if (appState.currentView === VIEW_STATE.BUILDING) {
    setHover(hit, 0x59b7ff);
    container.style.cursor = "pointer";
    return;
  }

  if (
    (appState.currentView === VIEW_STATE.LEVEL ||
      appState.currentView === VIEW_STATE.ROOM) &&
    hit.userData.type === "room"
  ) {
    setHover(hit, 0x19c37d);
    container.style.cursor = "pointer";
    return;
  }

  clearHover();
  container.style.cursor = "default";
}

async function onClick(event) {
  getPointer(event);
  raycaster.setFromCamera(pointer, camera);

  const objects = getInteractiveObjects();
  const hits = raycaster.intersectObjects(objects, true);
  if (!hits.length) return;

  const hit = hits[0].object;

  if (appState.currentView === VIEW_STATE.CITY) {
    await goToBuildingView();
    return;
  }

  if (appState.currentView === VIEW_STATE.BUILDING) {
    const firstLevel = appState.data?.building?.levels?.[0];
    if (firstLevel) await goToLevelView(firstLevel.id);
    return;
  }

  if (
    (appState.currentView === VIEW_STATE.LEVEL ||
      appState.currentView === VIEW_STATE.ROOM) &&
    hit.userData.type === "room"
  ) {
    await goToRoomView(hit.userData.levelId, hit.userData.roomId);
  }
}

/* -----------------------------------------
   EVENTS
----------------------------------------- */

window.addEventListener("resize", () => {
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
});

renderer.domElement.addEventListener("pointermove", onPointerMove);
renderer.domElement.addEventListener("click", onClick);

levelSelect.addEventListener("change", async (e) => {
  const levelId = e.target.value;
  if (!levelId) return;
  await goToLevelView(levelId);
});

roomSelect.addEventListener("change", async (e) => {
  const roomId = e.target.value;
  if (!roomId || !appState.selectedLevel) return;
  await goToRoomView(appState.selectedLevel.id, roomId);
});

resetBtn.addEventListener("click", async () => {
  if (appState.currentView === VIEW_STATE.ROOM && appState.selectedLevel) {
    await goToLevelView(appState.selectedLevel.id);
  } else if (appState.currentView === VIEW_STATE.LEVEL) {
    await goToBuildingView();
  } else {
    await goToCityView();
  }
});

/* -----------------------------------------
   LOOP
----------------------------------------- */

function animate() {
  requestAnimationFrame(animate);
  TWEEN.update();
  controls.update();
  renderer.render(scene, camera);
}

/* -----------------------------------------
   INIT
----------------------------------------- */

async function init() {
  try {
    setupScene();
    await loadData();
    renderMetadata();
    renderEmptyStats();
    renderEmptySchedule();
    renderEmptySharedParams();
    buildBreadcrumbs();
    updateBadge();
    await goToCityView();
    animate();
  } catch (error) {
    console.error(error);
    setDebug(`Error: ${error.message}`);
    metadataPanel.innerHTML = `<div class="empty">Failed to load viewer files.</div>`;
  }
}

init();
