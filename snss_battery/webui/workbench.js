// CAD 작업대 — 시료(결정 블록의 층 · 벽, 식염수병 틀, 흑연 프로브)를 CAD 프로그램처럼 다룬다.
// 모델 트리 · 속성 · 시점 · 투영 · 표시 방식 · 단면 · 분해도 · 치수 · STL/PNG 내보내기.
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const DATA = window.DATA;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const view = $("#wbView");
const SAMPLES = DATA.samples || [];

let M;
try {
  M = window.SNSS_MODEL || await (await fetch("model.json")).json();  // 정적 사이트는 data/model.js 로 내장
} catch (e) {
  $("#wbMsg").textContent = "model.json 을 불러오지 못했습니다: " + e;
  throw e;
}

const COL = { a: 0x9cc9e4, b: 0x2c6fb0, cem: 0xe8833a, aem: 0x3a9a5b, bottle: 0xdfe9f3, cap: 0x3b7dd8, probe: 0x2e3135,
              sel: 0xffc83d };
const hex = (c) => "#" + c.toString(16).padStart(6, "0");
const KIND = {
  a: { name: "A 묽은 도메인층", short: "A", el: "C · H · O · Na · Cl",
       mat: (s) => `${s.recipe ? "PVA 크라이오겔" : "GO 액정 겔"} + NaCl ${s.c_a.toFixed(1)} mM` },
  cem: { name: "CEM 양이온 선택 벽", short: "CEM", el: "C · H · O", mat: (s) => `${s.cem} — GO, 음전하 (Na⁺ 통과)` },
  b: { name: "B 진한 도메인층", short: "B", el: "C · H · O · Na · Cl",
       mat: (s) => `${s.recipe ? "PVA 크라이오겔" : "GO 액정 겔"} + NaCl ${s.c_b.toFixed(0)} mM` },
  aem: { name: "AEM 음이온 선택 벽", short: "AEM", el: "C · H · O · N · Cl", mat: (s) => `${s.aem} — GO + PDDA, 양전하 (Cl⁻ 통과)` },
};
const ORDER = ["a", "cem", "b", "aem"];
const WALL_VIS = 0.12; // 벽(5–8 µm)을 화면에 보이게 하는 최소 표시 두께 [mm]

// ---------- 렌더러 · 카메라 ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.localClippingEnabled = true;
renderer.autoClear = false;
view.prepend(renderer.domElement);
renderer.domElement.tabIndex = 0;

const scene = new THREE.Scene();
const persp = new THREE.PerspectiveCamera(32, 1, 0.5, 8000);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -8000, 8000);
persp.up.set(0, 0, 1); ortho.up.set(0, 0, 1);
let camera = persp;
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.12;

scene.add(new THREE.HemisphereLight(0xffffff, 0x51606f, 1.6));
const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(-160, -220, 320);
scene.add(key);
const rim = new THREE.DirectionalLight(0x9fc7ff, 0.6);
rim.position.set(200, 160, 120);
scene.add(rim);

const grid = new THREE.GridHelper(400, 40, 0x7d8b9b, 0x3b4654);
grid.rotation.x = Math.PI / 2;
grid.material.transparent = true;
grid.material.opacity = 0.55;
grid.material.depthWrite = false;
scene.add(grid);

const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0); // y ≤ c 만 남김
const allMats = [];
function mat(color, opts = {}) {
  const m = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0, side: THREE.DoubleSide, ...opts });
  allMats.push(m);
  return m;
}
const lineMats = [];
function lineMat(color, opts = {}) {
  const m = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9, ...opts });
  lineMats.push(m);
  return m;
}

// ---------- 식염수병 (model.json 의 B-rep 삼각형) ----------
const bottleGroup = new THREE.Group();
scene.add(bottleGroup);
const bottleMat = mat(COL.bottle, { transparent: true, opacity: 0.22, depthWrite: false, roughness: 0.15 });
const capMat = mat(COL.cap, { roughness: 0.4 });
const bottleParts = {};
const edgeGroup = new THREE.Group();
for (const s of M.bottle) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(s.positions, 3));
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, s.kind === "cap" ? capMat : bottleMat);
  mesh.renderOrder = 3;
  const grp = new THREE.Group();
  grp.add(mesh);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(g, 28), lineMat(0xa9bccf, { opacity: 0.45 }));
  edges.userData.edge = true;
  grp.add(edges);
  grp.userData = { part: s.name, kind: s.kind };
  mesh.userData.node = "bottle:" + s.name;
  bottleParts[s.name] = grp;
  bottleGroup.add(grp);
}

// ---------- 결정 블록 (층 · 벽 = InstancedMesh) ----------
const unit = new THREE.CylinderGeometry(1, 1, 1, 96, 1, false);
unit.rotateX(Math.PI / 2);
const gel = new THREE.Group();
scene.add(gel);
const gelMats = {};
for (const k of ORDER) gelMats[k] = mat(0xffffff, { roughness: k === "a" || k === "b" ? 0.6 : 0.35 });
let inst = {}, rec = {}, outline = null;
const dummy = new THREE.Object3D();
const tmpColor = new THREE.Color();

// ---------- 흑연 프로브 (측정 도구) ----------
const probes = new THREE.Group();
scene.add(probes);
const graphite = mat(COL.probe, { roughness: 0.35 });
function probe(sign) {
  const grp = new THREE.Group();
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 42, 24).rotateX(Math.PI / 2), graphite);
  rod.position.z = sign * 21;
  const clipM = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.2, 8, 24).rotateX(Math.PI / 2), mat(sign > 0 ? 0xc0392b : 0x1b1b1b));
  clipM.position.z = sign * 40;
  grp.add(rod, clipM);
  rod.userData.node = clipM.userData.node = "probe";
  grp.userData.sign = sign;
  probes.add(grp);
  return grp;
}
const probeTop = probe(1), probeBot = probe(-1);

// ---------- 치수 ----------
const dimGroup = new THREE.Group();
scene.add(dimGroup);
const dimMat = lineMat(0xffd479, { depthTest: false, opacity: 1 });
const dimLabels = [];
function dimLine(a, b, text, tick) {
  const pts = [a, b];
  const ta = tick.clone().multiplyScalar(3);
  pts.push(a.clone().add(ta), a.clone().sub(ta), b.clone().add(ta), b.clone().sub(ta));
  const g = new THREE.BufferGeometry().setFromPoints([a, b, pts[2], pts[3], pts[4], pts[5]]);
  const l = new THREE.LineSegments(g, dimMat);
  l.renderOrder = 10;
  dimGroup.add(l);
  const el = document.createElement("div");
  el.className = "ovl wb-dim";
  el.textContent = text;
  view.appendChild(el);
  dimLabels.push({ el, p: a.clone().add(b).multiplyScalar(0.5) });
}
function clearDims() {
  dimGroup.children.slice().forEach((c) => { c.geometry.dispose(); dimGroup.remove(c); });
  dimLabels.splice(0).forEach((d) => d.el.remove());
}

// ---------- 상태 ----------
const st = { s: SAMPLES[0], explode: 0, proc: 0, section: false, secC: 0, mode: "shade", dims: true,
             showBottle: true, showProbe: true, vis: { a: true, cem: true, b: true, aem: true }, sel: null, blockH: 0 };

const layered = (s) => (s.tissue ? 0 : s.pairs); // 층 원판으로 그리는 쌍 수 (조직 시료는 0)
function buildGel(s) {
  for (const k of ORDER) if (inst[k]) { gel.remove(inst[k]); inst[k].dispose(); }
  inst = {}; rec = {};
  const np = layered(s);
  for (const k of ORDER) {
    const m = new THREE.InstancedMesh(unit, gelMats[k], Math.max(1, np));
    m.count = np;
    m.userData.kind = k;
    m.frustumCulled = false;
    for (let i = 0; i < Math.max(1, np); i++) m.setColorAt(i, tmpColor.setHex(COL[k]));
    inst[k] = m;
    rec[k] = [];
    gel.add(m);
  }
  let z = 0;
  for (let i = 0; i < np; i++) {
    for (const k of ORDER) {
      const th = k === "a" || k === "b" ? s.layer_mm : k === "cem" ? s.cem_mm : s.aem_mm;
      rec[k].push({ z0: z, z1: z + th, th });
      z += th;
    }
  }
  st.realH = s.tissue ? s.block_h : z;
  buildTissue(s);
  layout();
}

function layout() {
  const s = st.s, e = st.explode, t = s.layer_mm;
  const gap = e * t * 0.8;
  let g = 0, top = s.tissue ? s.block_h : 0;
  for (let i = 0; i < layered(s); i++) {
    for (const k of ORDER) {
      const r = rec[k][i];
      const wall = k === "cem" || k === "aem";
      const th = wall ? Math.max(r.th, WALL_VIS + e * t * 0.25) : r.th;
      const zc = (r.z0 + r.z1) / 2 + g * gap;
      // 쌍이 촘촘하면(화면에서 무늬가 뭉침) 분해할 때만 벽 테두리를 내밂
      const rad = wall && (s.pairs <= 60 || e > 0) ? s.gel_r * 1.006 : s.gel_r;
      dummy.position.set(0, 0, zc);
      dummy.scale.set(rad, rad, th);
      dummy.updateMatrix();
      inst[k].setMatrixAt(i, dummy.matrix);
      r.zc = zc; r.vis = th;
      top = Math.max(top, zc + th / 2);
      g++;
    }
  }
  for (const k of ORDER) { inst[k].instanceMatrix.needsUpdate = true; if (layered(s)) inst[k].computeBoundingSphere(); }
  st.blockH = top;
  tissueExplode(e);
  if (outline) { gel.remove(outline); outline.geometry.dispose(); }
  const og = new THREE.CylinderGeometry(s.gel_r * 1.01, s.gel_r * 1.01, top, 96).rotateX(Math.PI / 2).translate(0, 0, top / 2);
  outline = new THREE.LineSegments(new THREE.EdgesGeometry(og, 30), lineMat(0xffffff, { opacity: 0.7 }));
  og.dispose();
  outline.userData.edge = true;
  gel.add(outline);
  applyMode();
  buildDims();
}

function buildDims() {
  clearDims();
  if (!st.dims) return;
  const s = st.s, r = s.gel_r, H = st.blockH, z0 = gel.position.z;
  dimLine(new THREE.Vector3(-r, 0, z0 + H + 8), new THREE.Vector3(r, 0, z0 + H + 8), `Ø ${(2 * r).toFixed(1)}`, new THREE.Vector3(0, 0, 1));
  dimLine(new THREE.Vector3(r + 12, 0, z0), new THREE.Vector3(r + 12, 0, z0 + H),
          st.explode > 0 ? `H ${H.toFixed(1)} (분해)` : `H ${H.toFixed(1)}`, new THREE.Vector3(1, 0, 0));
  const t = s.layer_mm, pitch = 2 * t + s.cem_mm + s.aem_mm;
  if (st.explode === 0 && !s.tissue && s.pairs <= 40) {
    dimLine(new THREE.Vector3(-r - 12, 0, z0), new THREE.Vector3(-r - 12, 0, z0 + pitch), `쌍 ${pitch.toFixed(3)}`, new THREE.Vector3(1, 0, 0));
  }
}

function applyMode() {
  const wire = st.mode === "wire";
  for (const m of allMats) if (m !== bottleMat) m.wireframe = wire;
  bottleMat.wireframe = wire;
  scene.traverse((o) => { if (o.userData.edge) o.visible = st.mode !== "shade"; });
  for (const k of ORDER) inst[k].visible = st.vis[k] && !st.s.tissue;
  applyTissueVis();
}

function applySection() {
  clip.constant = st.secC;
  for (const m of allMats) { m.clippingPlanes = st.section ? [clip] : []; m.needsUpdate = true; }
  for (const m of lineMats) { if (m !== dimMat) { m.clippingPlanes = st.section ? [clip] : []; m.needsUpdate = true; } }
}

const STAGES = {
  concept: ["① 결정화된 병", "② 병 절단 · 제거", "③ 흑연 프로브로 측정"],
  recipe: ["① 틀(어깨 아래를 자른 병) 속 결정", "② 틀 벗기기", "③ 흑연 프로브로 측정"],
};
function applyProcess() {
  const s = st.s, t = st.proc, t1 = Math.min(t, 1), t2 = Math.max(t - 1, 0);
  const ease = (v) => v * v * (3 - 2 * v);
  for (const [name, grp] of Object.entries(bottleParts)) {
    const upper = name === "병 위" || name === "뚜껑";
    if (upper) grp.position.z = 110 * t1;
    else grp.position.x = (name.includes("왼쪽") ? -1 : 1) * 95 * ease(t1);
    grp.visible = st.showBottle && t1 < 0.999 && !(upper && s.recipe);
  }
  const lift = 46 * ease(t2);
  gel.position.z = s.gel_z + lift;
  const a = 34 * (1 - ease(t2));
  probeTop.position.z = gel.position.z + st.blockH + a + 0.3;
  probeBot.position.z = gel.position.z - a - 0.3;
  probes.visible = st.showProbe && t2 > 0;
  const lab = (s.recipe ? STAGES.recipe : STAGES.concept)[t2 > 0 ? 2 : t1 > 0 ? 1 : 0];
  $("#wbStage").textContent = lab;
  const meter = $("#wbMeter");
  if (t2 > 0.6) {
    const v = s.ocv * Math.min(1, (t2 - 0.6) / 0.4);
    meter.style.display = "block";
    meter.innerHTML = s.tissue
      ? `<small>멀티미터 · DC mV</small><b>${(v * 1000).toFixed(1)} mV</b><small>대칭 → 사실상 0 · 에너지 ${s.energy_j.toFixed(0)} J 는 세포 안에</small>`
      : `<small>멀티미터 · DC V</small><b>${v.toFixed(2)} V</b><small>${esc(s.name)} 모델 예측</small>`;
  } else meter.style.display = "none";
  buildDims();
}

// ---------- 모델 트리 ----------
function treeNodes() {
  const s = st.s;
  if (s.tissue) return tissueTree();
  const bottleKids = Object.keys(bottleParts).filter((n) => !(s.recipe && (n === "병 위" || n === "뚜껑")))
    .map((n) => ({ id: "bottle:" + n, label: n, color: n === "뚜껑" ? COL.cap : COL.bottle }));
  return [
    { id: "sample", label: s.name, icon: "▣", open: true, kids: [
      { id: "bottle", label: s.recipe ? "식염수병 틀 (PE)" : "식염수병 (PE)", color: COL.bottle, eye: "bottle", open: openState.bottle, kids: bottleKids },
      { id: "block", label: "결정 블록", color: COL.b, open: true, cnt: `${4 * s.pairs} 고체`,
        kids: ORDER.map((k) => ({ id: "kind:" + k, label: KIND[k].name, color: COL[k], eye: k, cnt: `×${s.pairs}` })) },
      { id: "probe", label: "흑연 프로브 (측정 도구)", color: COL.probe, eye: "probe", cnt: "×2" },
    ] },
  ];
}
const openState = { bottle: false };
function renderTree() {
  const vis = (e) => (e === "bottle" ? st.showBottle : e === "probe" ? st.showProbe : e in tv ? tv[e] : st.vis[e]);
  const li = (n) => `<li><div class="node${st.sel && st.sel.id === n.id ? " sel" : ""}" data-id="${esc(n.id)}">
      <span class="tw">${n.kids ? (n.open ? "▾" : "▸") : ""}</span>
      ${n.eye ? `<button class="eye${vis(n.eye) ? "" : " off"}" data-eye="${n.eye}" title="보이기/숨기기">${vis(n.eye) ? "◉" : "○"}</button>` : ""}
      ${n.color !== undefined ? `<i class="sw" style="background:${hex(n.color)}"></i>` : `<span>${n.icon || ""}</span>`}
      <span>${esc(n.label)}</span>${n.cnt ? `<span class="cnt">${esc(n.cnt)}</span>` : ""}</div>
      ${n.kids && n.open ? `<ul>${n.kids.map(li).join("")}</ul>` : ""}</li>`;
  $("#wbTree").innerHTML = treeNodes().map(li).join("");
}
$("#wbTree").addEventListener("click", (ev) => {
  const eye = ev.target.closest("[data-eye]");
  if (eye) {
    const e = eye.dataset.eye;
    if (e === "bottle") st.showBottle = !st.showBottle;
    else if (e === "probe") st.showProbe = !st.showProbe;
    else if (e in tv) tv[e] = !tv[e];
    else st.vis[e] = !st.vis[e];
    applyMode(); applyProcess(); renderTree();
    return;
  }
  const node = ev.target.closest(".node");
  if (!node) return;
  const id = node.dataset.id;
  if (id === "bottle" && ev.target.classList.contains("tw")) { openState.bottle = !openState.bottle; renderTree(); return; }
  select({ id });
});

// ---------- 인공세포 조직 (3D 보로노이 세포 · 프랙탈 동결 전선 · 층·극성 없음, model_tissue.json) ----------
// 병 속 결정 → 상세도 A (×30, 실제 계산 창의 세포) → 인공세포 1개 (×200). 같은 테셀레이션을 크기만 바꿔 이어서 본다.
// 보로노이 원소가 그대로 구조: 세포(3D) = 묽은 내강, 면(2D) = GO/PVA 막 + 막 사이 진한 소금물, 모서리(1D) = 소금물 통로.
let T = null;
try { T = window.SNSS_TISSUE || await (await fetch("model_tissue.json")).json(); } catch (e) { T = null; }
const TS = { detail: 30, cell: 200 };
const TD = { x: 0, z: 18 };
const TC = { x: 0, z: 0 };
const TCOL = { lumen: 0xbfe3f5, wall: 0xc98a3a, vein: 0x2456b8, boundary: 0x8899aa };
const tv = { crystal: true, detail: true, one: true, lumen: true, wall: true, vein: true };
const tissue = new THREE.Group();
scene.add(tissue);
const tags = [];
const tMat = {
  lumen: mat(0xffffff, { vertexColors: true, roughness: 0.4 }),
  wall: mat(TCOL.wall, { roughness: 0.35, transparent: true, opacity: 0.9 }),
  oneFace: mat(TCOL.wall, { transparent: true, opacity: 0.32, depthWrite: false, roughness: 0.15 }),
  na: mat(0xf2c230, { roughness: 0.3 }), cl: mat(0x9b6bd6, { roughness: 0.3 }),
  dock: mat(0xf4f8ff, { roughness: 0.2 }),
  crystal: mat(0xffffff, { roughness: 0.32 }),
};
const veinMat = lineMat(TCOL.vein, { opacity: 0.9 });
const selMat = new THREE.MeshBasicMaterial({ color: COL.sel, side: THREE.DoubleSide, depthTest: false, transparent: true, opacity: 0.85 });
const selMesh = new THREE.Mesh(new THREE.BufferGeometry(), selMat);
selMesh.renderOrder = 20;
selMesh.visible = false;
scene.add(selMesh);
const tParts = {};
let tBase = {};
let oneIdx = -1, crystalMesh = null;
const eFmt = (j) => (j >= 1e-6 ? `${(j * 1e6).toFixed(2)} µJ` : `${(j * 1e9).toFixed(1)} nJ`);

function addTag(text, p, cls = "wb-dim") {
  const el = document.createElement("div");
  el.className = "ovl " + cls;
  el.innerHTML = text;
  view.appendChild(el);
  tags.push({ el, p });
}
function clearTissue() {
  tissue.children.slice().forEach((c) => { tissue.remove(c); c.traverse?.((o) => o.geometry?.dispose()); });
  if (crystalMesh) { gel.remove(crystalMesh); crystalMesh.geometry.dispose(); crystalMesh = null; }
  tags.splice(0).forEach((t) => t.el.remove());
  for (const k of Object.keys(tParts)) delete tParts[k];
  tBase = {};
  selMesh.visible = false;
}
const P = (f) => { const a = T.faces[f].p, o = []; for (let i = 0; i < a.length; i += 3) o.push([a[i], a[i + 1], a[i + 2]]); return o; };
const cellCenter = (i) => {
  const c = [0, 0, 0]; let n = 0;
  for (const f of T.cells[i].f) for (const v of P(f)) { c[0] += v[0]; c[1] += v[1]; c[2] += v[2]; n++; }
  return c.map((x) => x / n);
};
function fan(poly, out, shrinkTo, k, own, ownArr) {
  const q = shrinkTo ? poly.map((v) => v.map((x, j) => shrinkTo[j] + (x - shrinkTo[j]) * k)) : poly;
  for (let i = 1; i < q.length - 1; i++) { out.push(...q[0], ...q[i], ...q[i + 1]); ownArr.push(own); }
}
function meshOf(arr, material, owners, pick, colors) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(arr, 3));
  if (colors) g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, material);
  m.userData.owners = owners;
  m.userData.pick = (fi) => pick(owners[fi]);
  return m;
}

// 결정 표면 무늬: 2D 보로노이·프랙탈 탭과 같은 결정핵 규칙(FR), 크기만 ×12 확대 — 모든 세포 같은 종류, 벽은 하나의 막
function crystalTexture(s) {
  const cv = document.createElement("canvas"), GW = 1024, GH = 600;
  cv.width = GW; cv.height = GH;
  const cx = cv.getContext("2d"), img = cx.createImageData(GW, GH), d = img.data;
  const F = DATA.fractal.params, X = 12;
  const W = 2 * Math.PI * s.gel_r, H = s.block_h, sp = (s.spacing_um / 1000) * X;
  const r = FR.rng(11);
  const pts = FR.seeds({ W, H, spacing: sp, Ds: F.seed_dimension }, r), shade = pts.map(() => 0.86 + r() * 0.26);
  const own = FR.raster(pts, W, H, GW, GH);
  for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
    const g = j * GW + i, o = own[g], p = ((GH - 1 - j) * GW + i) * 4;
    let c = [191, 227, 245].map((v) => v * shade[o]);
    const nb = [i < GW - 1 ? own[g + 1] : o, j < GH - 1 ? own[g + GW] : o].find((q) => q !== o);
    if (nb !== undefined) c = [201, 138, 58];
    d[p] = c[0]; d[p + 1] = c[1]; d[p + 2] = c[2]; d[p + 3] = 255;
  }
  cx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function buildTissue(s) {
  clearTissue();
  if (!s.tissue || !T) return;
  if (typeof FR !== "undefined") { tMat.crystal.map?.dispose(); tMat.crystal.map = crystalTexture(s); tMat.crystal.needsUpdate = true; }
  const cg = new THREE.CylinderGeometry(s.gel_r, s.gel_r, s.block_h, 160, 1).rotateX(Math.PI / 2).translate(0, 0, s.block_h / 2);
  crystalMesh = new THREE.Mesh(cg, tMat.crystal);
  crystalMesh.userData.node = "crystal";
  gel.add(crystalMesh);
  // ② 상세도 A
  const det = new THREE.Group();
  TD.x = M.radius + 34 + (T.W * TS.detail) / 2;
  det.position.set(TD.x, -(T.W * TS.detail) / 2, TD.z);
  det.scale.setScalar(TS.detail);
  tissue.add(det);
  const cen = T.cells.map((_, i) => cellCenter(i));
  const ts = T.cells.map((c) => c.t), t0 = Math.min(...ts), t1 = Math.max(...ts) || 1;
  const arr = [], own = [], col = [], tmp = new THREE.Color();
  T.cells.forEach((c, i) => {
    // 색: 얼음이 지나간 시각(프랙탈 동결 전선)에 따라 아주 조금씩 — 층이 아니라 연속
    const u = (c.t - t0) / (t1 - t0 || 1), sh = 0.9 + 0.12 * Math.sin(i * 12.9898);
    tmp.setHex(TCOL.lumen).multiplyScalar(sh).lerp(new THREE.Color(0x8fc3e6), 0.45 * u);
    const before = arr.length;
    for (const f of c.f) fan(P(f), arr, cen[i], 0.86, i, own);
    for (let q = before; q < arr.length; q += 3) col.push(tmp.r, tmp.g, tmp.b);
  });
  tParts.lumen = meshOf(arr, tMat.lumen, own, (i) => "tcell:" + i, col);
  det.add(tParts.lumen);
  const wa = [], wo = [], segs = [], seen = new Set();
  T.faces.forEach((f, j) => {
    if (f.b < 0) return;
    const q = P(j);
    fan(q, wa, null, 1, j, wo);
    for (let k = 0; k < q.length; k++) { // 소금물 통로 = 막 둘레의 보로노이 모서리
      const a = q[k], b = q[(k + 1) % q.length], key = [a, b].map((v) => v.map((x) => x.toFixed(4)).join(",")).sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      segs.push(new THREE.Vector3(...a), new THREE.Vector3(...b));
    }
  });
  tParts.wall = meshOf(wa, tMat.wall, wo, (j) => "tface:" + j);
  det.add(tParts.wall);
  tParts.vein = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segs), veinMat);
  det.add(tParts.vein);
  det.add(new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(T.W, T.W, T.H).translate(T.W / 2, T.W / 2, T.H / 2)),
                                 lineMat(0xffd479, { opacity: 0.8 })));
  tParts.detail = det;
  tBase = { cen, wc: [T.W / 2, T.W / 2, T.H / 2], lumen: Float32Array.from(tParts.lumen.geometry.attributes.position.array),
            wall: Float32Array.from(tParts.wall.geometry.attributes.position.array) };
  const zMid = s.gel_z + s.block_h * 0.5;
  const mk = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.6, 3.2), new THREE.MeshBasicMaterial({ color: 0xffd479, wireframe: true }));
  mk.position.set(s.gel_r + 0.8, 0, zMid);
  tissue.add(mk);
  tissue.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(s.gel_r + 1.6, 0, zMid), new THREE.Vector3(TD.x - (T.W * TS.detail) / 2, 0, TD.z + T.H * TS.detail * 0.6)]),
    lineMat(0xffd479, { opacity: 0.7 })));
  addTag(`상세도 A ×${TS.detail} · 인공세포 조직 (결정 가운데)<br><small>${T.W} × ${T.W} × ${T.H} mm · 세포 ${T.cells.length}개 · 통로 ${T.n_veins}개 · 층·극성 없음</small>`,
         new THREE.Vector3(TD.x, 0, TD.z + T.H * TS.detail + 8));
  // ③ 인공세포 1개 (경계에 닿지 않은 가운데 세포)
  let best = -1, bd = 1e9;
  T.cells.forEach((c, i) => {
    if (c.f.some((f) => T.faces[f].b < 0)) return;
    const q = cen[i], dd = Math.hypot(q[0] - T.W / 2, q[1] - T.W / 2, q[2] - T.H / 2);
    if (dd < bd) { bd = dd; best = i; }
  });
  oneIdx = best;
  if (best >= 0) buildOne(best, cen[best]);
}

function buildOne(i, c) {
  const grp = new THREE.Group(), cell = T.cells[i];
  TC.x = -(M.radius + 84);
  TC.z = 118;
  grp.position.set(TC.x, 0, TC.z);
  grp.scale.setScalar(TS.cell);
  tissue.add(grp);
  tParts.one = grp;
  const pos = [], lines = [], planes = [];
  const rel = (v) => [v[0] - c[0], v[1] - c[1], v[2] - c[2]];
  for (const f of cell.f) {
    const poly = P(f).map(rel);
    for (let k = 1; k < poly.length - 1; k++) pos.push(...poly[0], ...poly[k], ...poly[k + 1]);
    for (let k = 0; k < poly.length; k++) lines.push(new THREE.Vector3(...poly[k]), new THREE.Vector3(...poly[(k + 1) % poly.length]));
    const fc = poly.reduce((a, v) => a.map((x, j) => x + v[j] / poly.length), [0, 0, 0]);
    const nrm = new THREE.Vector3(...poly[1]).sub(new THREE.Vector3(...poly[0])).cross(new THREE.Vector3(...poly[2]).sub(new THREE.Vector3(...poly[0]))).normalize();
    if (nrm.dot(new THREE.Vector3(...fc)) < 0) nrm.negate();
    planes.push({ n: nrm, c: new THREE.Vector3(...fc), poly, area: T.faces[f].A });
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, tMat.oneFace);
  m.userData.pick = () => "one";
  grp.add(m);
  grp.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(lines), lineMat(0xffe2b0, { opacity: 0.9 })));
  const rnd = typeof FR !== "undefined" ? FR.rng(5) : Math.random;
  const sph = new THREE.SphereGeometry(T.spacing * 0.03, 10, 8);
  const ions = (pts, mt) => {
    const im = new THREE.InstancedMesh(sph, mt, Math.max(1, pts.length));
    pts.forEach((p, k) => { dummy.position.copy(p); dummy.scale.setScalar(1); dummy.updateMatrix(); im.setMatrixAt(k, dummy.matrix); });
    im.count = pts.length;
    im.userData.pick = () => "one";
    grp.add(im);
  };
  // 내강 (묽음 — 이온 몇 개)
  const inside = (p) => planes.every((q) => q.n.dot(p.clone().sub(q.c)) < -0.004);
  const ext = T.spacing * 0.7, inner = [[], []];
  for (let k = 0, tries = 0; k < 4 && tries < 4000; tries++) {
    const p = new THREE.Vector3((rnd() - 0.5) * 2 * ext, (rnd() - 0.5) * 2 * ext, (rnd() - 0.5) * 2 * ext);
    if (inside(p)) inner[k++ % 2].push(p);
  }
  // 막 바깥 소금물 (진함 — 막 면을 따라 빽빽)
  const outer = [[], []];
  const nOut = Math.round(140 * Math.min(1, T.c_brine / 1.5));
  const total = planes.reduce((a, q) => a + q.area, 0);
  planes.forEach((q) => {
    const k = Math.round((nOut * q.area) / total);
    for (let j = 0; j < k; j++) {
      const ti = 1 + Math.floor(rnd() * (q.poly.length - 2)), a = q.poly[0], b = q.poly[ti], cc = q.poly[ti + 1];
      let u = rnd(), w = rnd();
      if (u + w > 1) { u = 1 - u; w = 1 - w; }
      const p = new THREE.Vector3(...a).multiplyScalar(1 - u - w).add(new THREE.Vector3(...b).multiplyScalar(u)).add(new THREE.Vector3(...cc).multiplyScalar(w));
      outer[j % 2].push(p.add(q.n.clone().multiplyScalar(T.spacing * 0.03)));
    }
  });
  ions([...inner[0], ...outer[0]], tMat.na);
  ions([...inner[1], ...outer[1]], tMat.cl);
  // 빈 결합 자리: 막마다 고리 하나 (채널·효소·회로를 붙일 자리)
  const ring = new THREE.TorusGeometry(T.spacing * 0.06, T.spacing * 0.01, 8, 24);
  let nd = 0;
  for (const q of planes) {
    if (q.area < T.spacing * T.spacing * 0.08) continue;
    const r = new THREE.Mesh(ring, tMat.dock);
    r.position.copy(q.c).add(q.n.clone().multiplyScalar(-T.spacing * 0.02));
    r.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), q.n);
    r.userData.pick = () => "dock";
    grp.add(r);
    nd++;
  }
  cell.docks = nd;
  addTag(`인공세포 1개 ×${TS.cell} · 빈 세포<br><small>내강 ${cell.c.toFixed(1)} mM · 막 사이 소금물 ${T.c_brine.toFixed(2)} M · 저장 ΔG ${eFmt(cell.e)}<br>` +
         `막 확산 전위 ${T.wall_mv.toFixed(0)} mV (사방 같음 → 상쇄) · 극성 없음 · 생물학 0 · 공학 0 · 빈 결합 자리 ${nd}</small>`,
         new THREE.Vector3(TC.x, 0, TC.z + T.spacing * TS.cell * 0.85 + 10));
  addTag(`<span style="color:#c98a3a">■</span> GO/PVA 막 · <span style="color:#f2c230">●</span> Na⁺ <span style="color:#9b6bd6">●</span> Cl⁻ (안: 묽음 · 막 바깥: 진함) · ◯ 빈 자리`,
         new THREE.Vector3(TC.x, 0, TC.z - T.spacing * TS.cell * 0.75 - 4));
}

function tissueExplode(e) {
  if (!st.s.tissue || !T || !tBase.cen) return;
  const k0 = e * 0.9;
  const off = (i) => tBase.cen[i].map((x, j) => (x - tBase.wc[j]) * k0);
  for (const k of ["lumen", "wall"]) {
    const m = tParts[k], a = m.geometry.attributes.position, base = tBase[k], ow = m.userData.owners;
    for (let t = 0; t < ow.length; t++) {
      let o;
      if (k === "lumen") o = off(ow[t]);
      else { const f = T.faces[ow[t]], oa = off(f.a), ob = f.b >= 0 ? off(f.b) : oa; o = oa.map((x, j) => (x + ob[j]) / 2); }
      for (let v = 0; v < 3; v++) for (let j = 0; j < 3; j++) a.array[(3 * t + v) * 3 + j] = base[(3 * t + v) * 3 + j] + o[j];
    }
    a.needsUpdate = true;
    m.geometry.computeBoundingSphere();
  }
  if (tParts.vein) tParts.vein.visible = tv.vein && tv.detail && e === 0;
}
function applyTissueVis() {
  if (crystalMesh) crystalMesh.visible = tv.crystal;
  if (tParts.detail) tParts.detail.visible = tv.detail;
  if (tParts.one) tParts.one.visible = tv.one;
  for (const k of ["lumen", "wall", "vein"]) if (tParts[k]) tParts[k].visible = tv[k] && (k !== "vein" || st.explode === 0);
  tags.forEach((t, i) => { t.hidden = i === 0 ? !tv.detail : !tv.one; });
}
function tissuePickables() {
  if (!st.s.tissue) return [];
  const out = ["lumen", "wall"].map((k) => tParts[k]).filter(Boolean);
  if (tParts.one) tParts.one.traverse((o) => { if (o.isMesh) out.push(o); });
  if (crystalMesh) out.push(crystalMesh);
  return out;
}
function tissueHighlight(id) {
  if (!T) return;
  const pos = [];
  const addFace = (f, shift) => { const q = P(f); for (let i = 1; i < q.length - 1; i++) for (const v of [q[0], q[i], q[i + 1]]) pos.push(v[0] + shift[0], v[1] + shift[1], v[2] + shift[2]); };
  if (id.startsWith("tcell:")) {
    const i = +id.slice(6), o = tBase.cen[i].map((x, j) => (x - tBase.wc[j]) * st.explode * 0.9);
    for (const f of T.cells[i].f) addFace(f, o);
  } else if (id.startsWith("tface:")) addFace(+id.slice(6), [0, 0, 0]);
  else if (id === "crystal" && crystalMesh) crystalMesh.material.emissive.setHex(0x3a2a00);
  else if (id === "tk:lumen") tMat.lumen.emissive.setHex(0x3a3000);
  else if (id === "tk:wall") tMat.wall.emissive.setHex(0x6b4a00);
  if (!pos.length) return;
  selMesh.geometry.dispose();
  selMesh.geometry = new THREE.BufferGeometry();
  selMesh.geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  selMesh.position.copy(tParts.detail.position); selMesh.scale.copy(tParts.detail.scale);
  selMesh.visible = true;
}
function tissueLabel(id) {
  if (!T) return null;
  if (id.startsWith("tcell:")) return `인공세포 #${+id.slice(6)} · 내강 ${T.cells[+id.slice(6)].c.toFixed(1)} mM`;
  if (id.startsWith("tface:")) return "GO/PVA 막 + 막 사이 소금물";
  return { one: "인공세포 1개 (×200)", dock: "빈 결합 자리 (미도입)", crystal: "결정 (병 속 통째)" }[id] || null;
}
function cellRows(i, head) {
  const c = T.cells[i], s = st.s;
  const deq = 2 * Math.cbrt((3 * c.v) / (4 * Math.PI)) * 1000;
  const area = c.f.reduce((a, f) => a + (T.faces[f].b >= 0 ? T.faces[f].A : 0), 0);
  return [["이름", `<b>${head || "인공세포 #" + i}</b>`], ["종류", "인공세포 (모든 세포 같음 · 극성 없음)"],
    ["내강", `묽은 식염수 ${c.c.toFixed(2)} mM — 얼음이 녹은 자리, 비어 있음`],
    ["막 사이 소금물", `${T.c_brine.toFixed(2)} M · ${(c.fv * 1000).toFixed(3)} nL (막 ${T.film_um} µm)`],
    ["부피", `${(c.v * 1000).toFixed(2)} nL (등가 지름 ${deq.toFixed(0)} µm)`], ["저장 에너지 ΔG", eFmt(c.e)],
    ["막", `${c.f.length}장 · ${(area * 1e6).toFixed(0)} µm² (모두 같은 GO/PVA 막)`],
    ["막 확산 전위", `${T.wall_mv.toFixed(1)} mV — 사방 같아 세포 밖으로는 0`], ["언 시각", `동결 시작 후 ${c.t.toFixed(2)} h (프랙탈 전선)`],
    ["생물학 요소", '<span class="pill off">0 (미도입)</span>'], ["공학 요소", '<span class="pill off">0 (미도입)</span>'],
    ["빈 결합 자리", `${c.docks ?? "막마다"} — GO 가장자리 –COOH`], ["금속", '<span class="pill">없음</span>']];
}
function tissueProps(id) {
  const s = st.s;
  if (!s.tissue || !T) return null;
  const F = s.freezing;
  if (id.startsWith("tcell:")) return cellRows(+id.slice(6));
  if (id === "one") return cellRows(oneIdx, `인공세포 1개 ×${TS.cell} (#${oneIdx})`);
  if (id === "dock") return [["이름", "<b>빈 결합 자리</b>"], ["위치", "막 (GO 판 가장자리 –COOH)"], ["쓰임 (나중에)", "이온 채널 · 효소 · 전극 연결 — 담긴 에너지를 꺼내는 자리"],
    ["지금", '<span class="pill off">비어 있음 — 생물학·공학 투자 전</span>'], ["순서", "결정화(동결)가 끝난 뒤 넣음 — 동결이 생체 요소를 망가뜨리지 않게"]];
  if (id.startsWith("tface:")) {
    const f = T.faces[+id.slice(6)];
    return [["이름", "<b>GO/PVA 막 + 막 사이 소금물</b>"], ["두 세포", `#${f.a} | #${f.b}`], ["넓이", `${(f.A * 1e6).toFixed(0)} µm²`],
      ["재질", "GO + PVA (얼음 결정 경계로 밀려남)"], ["사이 소금물", `${T.c_brine.toFixed(2)} M · 두께 ${T.film_um} µm`],
      ["확산 전위", `${T.wall_mv.toFixed(1)} mV (양쪽 세포에 같게 → 상쇄)`], ["둘레", "모서리 = 소금물 통로 (다른 막과 이어짐)"]];
  }
  if (id === "detail" || id.startsWith("tk:")) {
    return [["이름", `<b>상세도 A — 인공세포 조직</b>`], ["계산 창", `${T.W} × ${T.W} × ${T.H} mm (×${TS.detail} 표시, 결정 가운데)`],
      ["보로노이 원소", `세포 ${T.cells.length} · 막 ${T.faces.filter((f) => f.b >= 0).length} · 통로 ${T.n_veins}`],
      ["세포 크기", `${s.spacing_um.toFixed(0)} µm (2D 와 같은 결정핵 규칙)`], ["동결 전선", `프랙탈 D ≈ ${s.d_front.toFixed(2)} (설정 ${s.d_set}) · 굴곡 ${s.front_um.toFixed(0)} µm`],
      ["농도", `내강 ${s.c_lumen_mM.toFixed(1)} mM · 소금물 ${s.c_brine_m.toFixed(2)} M`], ["층 · 극성", "없음"]];
  }
  if (id === "crystal" || id === "sample" || id === "block") {
    return [["이름", `<b>${id === "sample" ? esc(s.name) : "결정 (병 속 통째)"}</b>`], ["종류", "식염수에서 바로 자란 얼음 결정 → 인공세포 조직"],
      ["지름 × 높이", `Ø${(2 * s.gel_r).toFixed(1)} × ${s.block_h.toFixed(1)} mm`], ["인공세포", `약 ${(s.n_cells / 1e6).toFixed(0)}백만 개 (모두 비어 있음)`],
      ["방향성 동결", `약 ${F.hours.toFixed(0)} h · 전선 ${F.v_mid_um_s.toFixed(1)}→${F.v_top_um_s.toFixed(1)} µm/s`],
      ["내강 농도 (아래→위)", `${s.c_bottom_mM.toFixed(0)} → ${s.c_top_mM.toFixed(1)} mM (빨리 언 아래쪽에 소금이 더 갇힘)`],
      ["저장 화학 에너지", `${s.energy_j.toFixed(0)} J — 잠겨 있음`], ["표면 무늬", "같은 규칙 · 크기 ×12 확대 표시"],
      ["층 · 극성", "없음"], ["금속", '<span class="pill">없음 (Na⁺ 만)</span>'], ["설명", esc(s.note)]];
  }
  return null;
}
function tissueTree() {
  const s = st.s, nw = T ? T.faces.filter((f) => f.b >= 0).length : 0;
  return [{ id: "sample", label: s.name, icon: "▣", open: true, kids: [
    { id: "bottle", label: "식염수병 (PE) — 반응 용기", color: COL.bottle, eye: "bottle", open: openState.bottle,
      kids: Object.keys(bottleParts).map((n) => ({ id: "bottle:" + n, label: n, color: n === "뚜껑" ? COL.cap : COL.bottle })) },
    { id: "crystal", label: "결정 (병 속 통째)", color: TCOL.lumen, eye: "crystal", cnt: `${(s.n_cells / 1e6).toFixed(0)}M 세포` },
    { id: "detail", label: `상세도 A ×${TS.detail} · 조직`, color: 0xffd479, eye: "detail", open: true, cnt: `${T ? T.cells.length : 0}`,
      kids: [
        { id: "tk:lumen", label: "인공세포 (묽은 내강)", color: TCOL.lumen, eye: "lumen", cnt: `×${T ? T.cells.length : 0}` },
        { id: "tk:wall", label: "막 + 막 사이 소금물", color: TCOL.wall, eye: "wall", cnt: `×${nw}` },
        { id: "tk:vein", label: "소금물 통로 (모서리)", color: TCOL.vein, eye: "vein", cnt: `×${T ? T.n_veins : 0}` },
      ] },
    { id: "one", label: `인공세포 1개 ×${TS.cell}`, color: 0xffffff, eye: "one", cnt: "빈 세포" },
    { id: "probe", label: "흑연 프로브 (측정 도구)", color: COL.probe, eye: "probe", cnt: "×2" },
  ] }];
}
function tissueSTL() {
  const tris = [];
  T.cells.forEach((c) => { for (const f of c.f) { const q = P(f); for (let i = 1; i < q.length - 1; i++) tris.push([q[0], q[i], q[i + 1]]); } });
  const buf = new ArrayBuffer(84 + tris.length * 50), dv = new DataView(buf);
  const head = "SNSS artificial-cell tissue window, mm (3D Voronoi, no layers)";
  for (let i = 0; i < head.length; i++) dv.setUint8(i, head.charCodeAt(i));
  dv.setUint32(80, tris.length, true);
  let o = 84;
  for (const t of tris) {
    o += 12;
    for (const v of t) { dv.setFloat32(o, v[0], true); dv.setFloat32(o + 4, v[1], true); dv.setFloat32(o + 8, v[2], true); o += 12; }
    o += 2;
  }
  download(new Blob([buf], { type: "model/stl" }), "snss_tissue_cells.stl");
}

// ---------- 선택 · 속성 ----------
const fmt = (v, d = 2) => (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(d));
const volMl = (r, h) => Math.PI * r * r * h / 1000;
function clearHighlight() {
  for (const k of ORDER) {
    for (let i = 0; i < rec[k].length; i++) inst[k].setColorAt(i, tmpColor.setHex(COL[k]));
    inst[k].instanceColor.needsUpdate = true;
  }
  for (const m of allMats) if (m.emissive) m.emissive.setHex(0x000000);
  selMesh.visible = false;
}
function highlight(sel) {
  clearHighlight();
  if (!sel) return;
  const glow = 0x6b4a00;
  if (sel.id.startsWith("inst:")) {
    const [, k, i] = sel.id.split(":");
    inst[k].setColorAt(+i, tmpColor.setHex(COL.sel));
    inst[k].instanceColor.needsUpdate = true;
  } else if (sel.id.startsWith("kind:")) gelMats[sel.id.slice(5)].emissive.setHex(glow);
  else if (sel.id === "block") for (const k of ORDER) gelMats[k].emissive.setHex(glow);
  else if (sel.id.startsWith("bottle")) { bottleMat.emissive.setHex(0x334455); if (sel.id.includes("뚜껑")) capMat.emissive.setHex(glow); }
  else if (sel.id === "probe") graphite.emissive.setHex(0x444444);
  else tissueHighlight(sel.id);
}
function propsOf(id) {
  const s = st.s, r = s.gel_r, t = s.layer_mm;
  const tp = tissueProps(id);
  if (tp) return tp;
  const head = (name, kind) => [["이름", `<b>${esc(name)}</b>`], ["종류", esc(kind)]];
  if (id.startsWith("inst:")) {
    const [, k, i] = id.split(":"), q = rec[k][+i], wall = k === "cem" || k === "aem";
    return [...head(`${KIND[k].short}${+i + 1} ${KIND[k].name.split(" ").slice(1).join(" ")}`, wall ? "도메인 벽 (막)" : "도메인층"),
      ["재질", esc(KIND[k].mat(s))], ["원소", KIND[k].el], ["금속", '<span class="pill">없음</span>'],
      ["지름", `${fmt(2 * r, 1)} mm`], ["두께", wall ? `${(q.th * 1000).toFixed(0)} µm (화면 ${q.vis.toFixed(2)} mm로 과장)` : `${fmt(q.th, 3)} mm`],
      ["z 범위", `${fmt(q.z0, 3)} – ${fmt(q.z1, 3)} mm`], ["부피", `${fmt(volMl(r, q.th), wall ? 4 : 2)} mL`],
      ["순서", `${+i + 1} / ${s.pairs} 번째 쌍`]];
  }
  if (id.startsWith("kind:")) {
    const k = id.slice(5), wall = k === "cem" || k === "aem", th = rec[k][0].th;
    return [...head(KIND[k].name, `${s.pairs}개 (패턴)`), ["재질", esc(KIND[k].mat(s))], ["원소", KIND[k].el],
      ["금속", '<span class="pill">없음</span>'], ["한 장 두께", wall ? `${(th * 1000).toFixed(0)} µm` : `${fmt(th, 3)} mm`],
      ["합계 부피", `${fmt(volMl(r, th) * s.pairs, 2)} mL`], ["역할", wall ? (k === "cem" ? "양이온만 통과 → 쌍마다 기전력" : "음이온만 통과 → 쌍마다 기전력") : k === "a" ? "묽은 쪽 (이온을 받음)" : "진한 쪽 (이온을 내놓음)"]];
  }
  if (id === "block" || id === "sample") {
    return [...head(id === "sample" ? s.name : "결정 블록", id === "sample" ? "시료 (조립품)" : "결정 = 전지 전체"),
      ["지름 × 높이", `Ø${fmt(2 * r, 1)} × ${fmt(st.realH, 1)} mm`], ["부피", `${fmt(volMl(r, st.realH), 1)} mL`],
      ["질량 (근사)", `${fmt(s.mass_g, 0)} g`], ["층 · 벽", `${2 * s.pairs}층 · ${2 * s.pairs}장`], ["쌍 간격", `${fmt(2 * t + s.cem_mm + s.aem_mm, 3)} mm`],
      ["GO 양", `${fmt(s.go_g, 2)} g`], ["금속", '<span class="pill">없음 (Na⁺ 만)</span>'], ["설명", esc(s.note)]];
  }
  if (id.startsWith("bottle")) {
    const part = id.includes(":") ? id.split(":")[1] : "식염수병";
    return [...head(part, s.recipe ? "틀 (결정화 후 벗김)" : "반응 용기 (결정화 후 절단)"), ["재질", part === "뚜껑" ? "PP" : "PE (폴리에틸렌)"],
      ["원소", "C · H"], ["전지에 남음", '<span class="pill off">아니오</span>'], ["바깥지름", `${fmt(2 * M.radius, 1)} mm`],
      ["전체 높이", `${fmt(M.height, 1)} mm`], ["채움", `${fmt(s.fill_ml, 0)} mL`], ["절단선", `${fmt(s.cut_z, 1)} mm (바닥에서)`]];
  }
  if (id === "probe") {
    return [...head("흑연 막대 프로브 ×2", "측정 도구 (전지 부품 아님)"), ["재질", "흑연 (샤프심 · 연필심)"], ["원소", "C"],
      ["지름 × 길이", "Ø3.2 × 42 mm"], ["접점", "(+) 윗면 중앙 · (−) 아랫면 중앙"], ["주의", "금속 프로브를 결정에 직접 대지 말 것"]];
  }
  return [];
}
function select(sel) {
  st.sel = sel;
  highlight(sel);
  const rows = sel ? propsOf(sel.id) : propsOf("sample");
  $("#wbProps").innerHTML = rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join("");
  renderTree();
  status();
}
function renderPred() {
  const s = st.s;
  const ledCls = s.led_level === 2 ? "" : s.led_level === 1 ? "" : " off";
  const tx = s.tissue ? [
    ["인공세포 수", `약 ${(s.n_cells / 1e6).toFixed(0)}백만 개`], ["저장 화학 에너지", `<span class="big">${s.energy_j.toFixed(0)} J</span>`],
    ["세포 하나", `${(s.e_cell_j * 1e6).toFixed(1)} µJ · 내강 ${s.c_lumen_mM.toFixed(1)} mM / 소금물 ${s.c_brine_m.toFixed(2)} M`],
    ["막 확산 전위", `${s.wall_mv.toFixed(0)} mV (사방 같아 상쇄)`],
    ["프랙탈 동결 전선", `D ≈ ${s.d_front.toFixed(2)} (설정 ${s.d_set})`],
    ["방향성 동결", `약 ${s.freezing.hours.toFixed(0)} h (${s.plate_c} °C 판)`],
    ["에너지 꺼내기", '<span class="pill off">공학 요소 넣은 뒤</span>']] : [];
  $("#wbPred").innerHTML = (s.tissue ? [
    ["윗면–아랫면 전압", `${(s.ocv * 1000).toFixed(1)} mV — 사실상 0 (대칭)`],
    ["내부저항", `${s.r_ohm.toFixed(0)} Ω`],
    ["LED + 470 Ω", '<span class="pill off">꺼짐 — 이번 단계 목표 아님</span>'],
  ] : [
    ["개방전압", `<span class="big">${s.ocv.toFixed(2)} V</span>`],
    ["내부저항", `${s.r_ohm.toFixed(0)} Ω`],
    ["LED + 470 Ω", `${s.led_ma.toFixed(2)} mA <span class="pill${ledCls}">${esc(s.led)}</span>`],
    ["농도 A / B", `${s.c_a.toFixed(1)} / ${s.c_b.toFixed(0)} mM`],
    ["보관 수명 (1/e)", `약 ${s.shelf_days.toFixed(0)}일`],
  ]).concat([
    ...(s.recipe ? [["붓기 · 얼리기", `${s.steps}회`], ["층 하나", `${s.layer_ml.toFixed(1)} mL`]] : []), ...tx,
  ]).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join("");
}

// ---------- 고르기 (레이캐스트) ----------
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const shown = (o) => { while (o) { if (!o.visible) return false; o = o.parent; } return true; };
function pick(ev) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const targets = [...tissuePickables(), ...ORDER.map((k) => inst[k]), ...bottleGroup.children.map((g) => g.children[0]), ...probes.children.flatMap((g) => g.children)];
  for (const h of ray.intersectObjects(targets, false)) {
    if (!shown(h.object)) continue;
    if (st.section && h.point.y > st.secC) continue;
    if (h.object.isInstancedMesh) return { id: `inst:${h.object.userData.kind}:${h.instanceId}`, p: h.point };
    if (h.object.userData.pick) return { id: h.object.userData.pick(h.faceIndex), p: h.point };
    if (h.object.material === bottleMat && h.object.parent.userData.kind !== "cap" && ev.type === "pointermove") continue;
    return { id: h.object.userData.node || "bottle", p: h.point };
  }
  return null;
}
function label(id) {
  const tl = tissueLabel(id);
  if (tl) return tl;
  if (id.startsWith("inst:")) { const [, k, i] = id.split(":"); return `${KIND[k].short}${+i + 1} · ${KIND[k].name}`; }
  if (id.startsWith("bottle:")) return id.slice(7);
  return id === "probe" ? "흑연 프로브" : id;
}
let hoverP = null, hoverPending = false, downAt = null;
renderer.domElement.addEventListener("pointerdown", (ev) => { downAt = [ev.clientX, ev.clientY]; });
renderer.domElement.addEventListener("pointerup", (ev) => {
  if (!downAt || Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 4 || ev.button !== 0) return;
  const h = pick(ev);
  select(h ? { id: h.id } : null);
});
renderer.domElement.addEventListener("pointermove", (ev) => {
  if (hoverPending) return;
  hoverPending = true;
  requestAnimationFrame(() => {
    hoverPending = false;
    const h = pick(ev), tip = $("#wbTip"), r = view.getBoundingClientRect();
    if (h) {
      tip.style.display = "block";
      tip.style.left = ev.clientX - r.left + "px"; tip.style.top = ev.clientY - r.top + "px";
      tip.textContent = label(h.id);
      hoverP = h.p;
    } else { tip.style.display = "none"; hoverP = null; }
    status();
  });
});
renderer.domElement.addEventListener("pointerleave", () => { $("#wbTip").style.display = "none"; });

// ---------- 시점 · 투영 ----------
function bounds() {
  // 보이는 것의 위·아래 끝 (병 · 결정 · 프로브)
  const bottle = st.showBottle && st.proc < 1;
  const z0 = probes.visible ? probeBot.position.z - 44 : 0;
  let z1 = Math.max(bottle ? M.height : 0, gel.position.z + st.blockH + (probes.visible ? 44 : 0));
  if (st.s.tissue && T) z1 = Math.max(z1, TD.z + T.H * TS.detail + 14);
  return [z0, z1, st.s.tissue ? M.radius + 150 : bottle ? M.radius + 20 : st.s.gel_r + 20];
}
function center() { const [z0, z1] = bounds(); return new THREE.Vector3(0, 0, (z0 + z1) / 2); }
function fitDist() {
  const [z0, z1, r] = bounds(), w = view.clientWidth || 1, h = view.clientHeight || 1;
  const R = Math.max((z1 - z0) / 2, (r * h) / w) * 1.12 + 6;
  return R / Math.tan((persp.fov * Math.PI) / 360);
}
const DIRS = { iso: [0.55, -0.95, 0.6], front: [0, -1, 0.0001], top: [0.0001, -0.0001, 1], right: [1, 0, 0.0001] };
let tween = null;
function setView(name, instant) {
  const d = new THREE.Vector3(...DIRS[name]).normalize(), c = center(), dist = fitDist();
  const to = c.clone().add(d.multiplyScalar(dist));
  if (camera.isOrthographicCamera) { camera.zoom = 1; camera.updateProjectionMatrix(); }
  if (instant) { camera.position.copy(to); controls.target.copy(c); controls.update(); return; }
  tween = { t0: performance.now(), p0: camera.position.clone(), p1: to, c0: controls.target.clone(), c1: c };
  document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("on", b.dataset.view === name));
}
function setProjection(kind) {
  const from = camera, to = kind === "ortho" ? ortho : persp;
  if (from === to) return;
  to.position.copy(from.position); to.quaternion.copy(from.quaternion);
  camera = to; controls.object = to;
  resize(); controls.update();
  document.querySelectorAll("[data-proj]").forEach((b) => b.classList.toggle("on", b.dataset.proj === kind));
}

// ---------- 축 표시 (왼쪽 아래) ----------
const gScene = new THREE.Scene();
const gCam = new THREE.OrthographicCamera(-1.6, 1.6, 1.6, -1.6, 0.1, 10);
gCam.up.set(0, 0, 1);
const AX = [[1, 0, 0, 0xe5534b, "X"], [0, 1, 0, 0x57ab5a, "Y"], [0, 0, 1, 0x539bf5, "Z"]];
const gLabels = AX.map(([x, y, z, c, n]) => {
  gScene.add(new THREE.ArrowHelper(new THREE.Vector3(x, y, z), new THREE.Vector3(), 1, c, 0.32, 0.18));
  const el = document.createElement("div");
  el.className = "ovl wb-axis"; el.style.color = hex(c); el.textContent = n;
  view.appendChild(el);
  return { el, v: new THREE.Vector3(x, y, z).multiplyScalar(1.3) };
});
const GIZ = 96;

// ---------- 내보내기 ----------
function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function exportSTL() {
  if (st.s.tissue) return tissueSTL();
  const s = st.s, seg = 64, r = s.gel_r, layers = [];
  for (const k of ["a", "b"]) for (const q of rec[k]) layers.push(q);
  const nTri = layers.length * seg * 4, buf = new ArrayBuffer(84 + nTri * 50), dv = new DataView(buf);
  const head = `SNSS ${s.key} crystal block, mm, A/B domain layers (walls omitted)`;
  for (let i = 0; i < Math.min(80, head.length); i++) dv.setUint8(i, head.charCodeAt(i) & 127);
  dv.setUint32(80, nTri, true);
  let o = 84;
  const tri = (n, a, b, c) => {
    for (const v of [n, a, b, c]) { dv.setFloat32(o, v[0], true); dv.setFloat32(o + 4, v[1], true); dv.setFloat32(o + 8, v[2], true); o += 12; }
    dv.setUint16(o, 0, true); o += 2;
  };
  const P = (j, z) => [r * Math.cos((2 * Math.PI * j) / seg), r * Math.sin((2 * Math.PI * j) / seg), z];
  for (const q of layers) {
    for (let j = 0; j < seg; j++) {
      const a0 = P(j, q.z0), a1 = P(j + 1, q.z0), b0 = P(j, q.z1), b1 = P(j + 1, q.z1);
      const m = (2 * Math.PI * (j + 0.5)) / seg, n = [Math.cos(m), Math.sin(m), 0];
      tri(n, a0, a1, b1); tri(n, a0, b1, b0);
      tri([0, 0, -1], [0, 0, q.z0], a1, a0); tri([0, 0, 1], [0, 0, q.z1], b0, b1);
    }
  }
  download(new Blob([buf], { type: "model/stl" }), `snss_${s.key}_crystal.stl`);
}
function exportPNG() {
  draw();
  renderer.domElement.toBlob((b) => b && download(b, `snss_${st.s.key}_view.png`));
}

// ---------- 상태 표시줄 ----------
function status() {
  const s = st.s, nSolid = 4 * s.pairs;
  $("#wbStatus").innerHTML = [
    `단위 <b>mm</b>`, `시료 <b>${esc(s.name)}</b>`,
    s.tissue && T ? `인공세포 <b>${T.cells.length}</b>개 (창) · 병 전체 약 <b>${(s.n_cells / 1e6).toFixed(0)}</b>백만 개` : `고체 <b>${nSolid}</b>개 (층 ${2 * s.pairs} · 벽 ${2 * s.pairs})`,
    `투영 <b>${camera.isOrthographicCamera ? "직교" : "원근"}</b>`, `선택 <b>${st.sel ? esc(label(st.sel.id)) : "-"}</b>`,
    hoverP ? `커서 <b>x ${hoverP.x.toFixed(2)} · y ${hoverP.y.toFixed(2)} · z ${hoverP.z.toFixed(2)}</b>` : "커서 -",
    `금속 <b>0</b>`,
  ].map((x) => `<span>${x}</span>`).join("");
}

// ---------- 그리기 ----------
const v3 = new THREE.Vector3();
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  renderer.domElement.style.width = w + "px"; renderer.domElement.style.height = h + "px";
  persp.aspect = w / h; persp.updateProjectionMatrix();
  const dist = camera.position.distanceTo(controls.target) || fitDist();
  const hh = dist * Math.tan((persp.fov * Math.PI) / 360);
  ortho.left = -hh * persp.aspect; ortho.right = hh * persp.aspect; ortho.top = hh; ortho.bottom = -hh;
  ortho.updateProjectionMatrix();
}
function draw() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setViewport(0, 0, w, h); renderer.setScissorTest(false);
  renderer.clear();
  renderer.render(scene, camera);
  for (const d of [...dimLabels, ...tags]) {
    v3.copy(d.p).project(camera);
    const vis = v3.z < 1 && Math.abs(v3.x) < 1.05 && Math.abs(v3.y) < 1.05;
    d.el.style.display = vis && !d.hidden ? "block" : "none";
    d.el.style.left = ((v3.x + 1) / 2) * w + "px"; d.el.style.top = ((1 - v3.y) / 2) * h + "px";
  }
  // 축 표시
  gCam.position.copy(camera.position).sub(controls.target).setLength(4);
  gCam.quaternion.copy(camera.quaternion);
  renderer.setScissorTest(true);
  renderer.setScissor(8, 8, GIZ, GIZ); renderer.setViewport(8, 8, GIZ, GIZ);
  renderer.clearDepth();
  renderer.render(gScene, gCam);
  renderer.setScissorTest(false);
  for (const g of gLabels) {
    v3.copy(g.v).project(gCam);
    g.el.style.left = 8 + ((v3.x + 1) / 2) * GIZ + "px"; g.el.style.top = h - 8 - ((v3.y + 1) / 2) * GIZ + "px";
  }
}
renderer.setAnimationLoop(() => {
  if (!view.offsetParent) return; // 탭이 숨겨짐
  if (tween) {
    const u = Math.min(1, (performance.now() - tween.t0) / 380), e = u * u * (3 - 2 * u);
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.c0, tween.c1, e);
    if (u >= 1) tween = null;
  }
  controls.update();
  draw();
});
new ResizeObserver(resize).observe(view);

// ---------- 도구 막대 · 아래 막대 ----------
function setSample(key) {
  st.s = SAMPLES.find((x) => x.key === key) || SAMPLES[0];
  st.sel = null;
  buildGel(st.s);
  st.secC = 0; $("#wbSecPos").min = -st.s.gel_r; $("#wbSecPos").max = st.s.gel_r; $("#wbSecPos").value = 0;
  applySection(); applyProcess(); renderTree(); renderPred(); select(null);
  $("#wbTitle").innerHTML = st.s.tissue
    ? `<b>${esc(st.s.name)}</b>3D 보로노이 세포 · 프랙탈 동결 전선 · 층·극성 없음 · 저장 에너지 ${st.s.energy_j.toFixed(0)} J`
    : `<b>${esc(st.s.name)}</b>${st.s.pairs}쌍 × 층 ${st.s.layer_mm} mm · 예측 ${st.s.ocv.toFixed(2)} V`;
  setView("iso", true);
  try { localStorage.setItem("snss-wb-sample", key); } catch (e) {}
}
const selEl = $("#wbSample");
selEl.innerHTML = SAMPLES.map((s) => `<option value="${esc(s.key)}">${esc(s.name)}${s.tissue ? ` — 에너지 ${s.energy_j.toFixed(0)} J` : ` — ${s.pairs}쌍 · ${s.ocv.toFixed(2)} V`}</option>`).join("");
selEl.onchange = () => setSample(selEl.value);
document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
document.querySelectorAll("[data-proj]").forEach((b) => (b.onclick = () => setProjection(b.dataset.proj)));
document.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => {
  st.mode = b.dataset.mode; applyMode();
  document.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("on", x === b));
}));
$("#wbFit").onclick = () => setView(Object.keys(DIRS).find((k) => document.querySelector(`[data-view=${k}].on`)) || "iso");
$("#wbSection").onclick = (ev) => { st.section = !st.section; ev.currentTarget.classList.toggle("on", st.section); applySection(); };
$("#wbDims").onclick = (ev) => { st.dims = !st.dims; ev.currentTarget.classList.toggle("on", st.dims); buildDims(); };
$("#wbGrid").onclick = (ev) => { grid.visible = !grid.visible; ev.currentTarget.classList.toggle("on", grid.visible); };
$("#wbSTL").onclick = exportSTL;
$("#wbPNG").onclick = exportPNG;
$("#wbProc").oninput = (ev) => { st.proc = ev.target.value / 100; applyProcess(); };
$("#wbExp").oninput = (ev) => { st.explode = ev.target.value / 100; layout(); applyProcess(); };
$("#wbSecPos").oninput = (ev) => { st.secC = +ev.target.value; applySection(); };

let saved = null;
try { saved = localStorage.getItem("snss-wb-sample"); } catch (e) {}
const q = new URLSearchParams(location.search);
$("#wbMsg").remove();
selEl.value = q.get("sample") || (SAMPLES.some((s) => s.key === saved) ? saved : st.s.key);
if (q.has("stage")) $("#wbProc").value = q.get("stage");
st.proc = $("#wbProc").value / 100;
if (q.has("explode")) { $("#wbExp").value = q.get("explode"); st.explode = q.get("explode") / 100; }
resize();
setSample(selEl.value);
if (q.has("pick")) select({ id: q.get("pick") });
window.__wb = { setSample, setView, select };
