// 브라우저 속 Blender — 장면은 Blender(서버)가 계산하고, 여기서는 Blender 키맵으로 그리고 살핀다.
import * as THREE from "three";

const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.headers.get("Content-Type").includes("json") ? r.json() : r.arrayBuffer();
};
const busy = (on) => ($("#busy").hidden = !on);
const status = (t) => ($("#status").textContent = t);

// ---------- three.js — Z 위 (Blender 와 같음), 단위 mm ----------
const canvas = $("#c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
const scene3 = new THREE.Scene();
scene3.background = new THREE.Color(0x3a3a3a);
const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 20000);
camera.up.set(0, 0, 1);
scene3.add(new THREE.HemisphereLight(0xffffff, 0x666666, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(600, -900, 1200);
scene3.add(sun);
const grid = new THREE.GridHelper(1200, 24, 0x555555, 0x444444);
grid.rotation.x = Math.PI / 2;
scene3.add(grid);
const root = new THREE.Group();
scene3.add(root);

// 궤도 시점 (Blender 의 턴테이블 궤도): 목표 · 방위 · 고도 · 거리
const view = { target: new THREE.Vector3(0, 0, 100), yaw: -0.5, pitch: 0.45, dist: 900 };
function placeCamera() {
  const c = Math.cos(view.pitch);
  camera.position.set(view.target.x + view.dist * c * Math.sin(view.yaw), view.target.y - view.dist * c * Math.cos(view.yaw),
    view.target.z + view.dist * Math.sin(view.pitch));
  camera.lookAt(view.target);
}
function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / Math.max(1, r.height);
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);

// ---------- 상태 ----------
let INFO = null, SCENE = null, ITEMS = new Map(), SELECTED = null, HW = false, HIDDEN = new Set();
const mats = new Map();
function material(c) {
  const k = c.map((v) => v.toFixed(3)).join();
  if (!mats.has(k)) {
    const a = c[3];
    mats.set(k, new THREE.MeshStandardMaterial({ color: new THREE.Color(c[0], c[1], c[2]), roughness: 0.6, metalness: 0.05,
      transparent: a < 0.99, opacity: a, depthWrite: a >= 0.99, side: a < 0.99 ? THREE.DoubleSide : THREE.FrontSide }));
  }
  return mats.get(k);
}

async function loadScene(name, keepView = false) {
  busy(true);
  status(`${name} — Blender 에서 메시 받는 중…`);
  const buf = await api(`/api/geom?scene=${encodeURIComponent(name)}`);
  const n = new DataView(buf).getUint32(0, true);
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  const base = 4 + n + ((4 - ((4 + n) % 4)) % 4);
  root.clear();
  ITEMS.clear();
  const geos = head.meshes.map((m) => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(buf, base + m.off, m.n * 3);
    const nor = new Float32Array(buf, base + m.off + m.n * 12, m.n * 3);
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    if (nor.some((v) => v !== 0)) g.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
    else g.computeVertexNormals();
    g.computeBoundingSphere();
    return g;
  });
  for (const it of head.items) {
    const mesh = new THREE.Mesh(geos[it.mesh], material(it.color));
    mesh.matrixAutoUpdate = false;
    mesh.matrix.fromArray(it.m);
    mesh.userData = it;
    mesh.renderOrder = it.color[3] < 0.99 ? 1 : 0;
    root.add(mesh);
    ITEMS.set(it.key, mesh);
  }
  SCENE = name;
  document.querySelectorAll("#scenes button").forEach((b) => b.classList.toggle("on", b.dataset.s === name));
  buildTree(head.items);
  showDims();
  showProcess();
  applyHidden();
  if (!keepView) frameAll(true);
  updateHUD();
  busy(false);
  status(`${name} — 메시 ${head.meshes.length} · 개체 ${head.items.length} (Blender ${INFO.blender})`);
}

async function refreshFrame() {
  const f = await api(`/api/frame?scene=${encodeURIComponent(SCENE)}`);
  for (const [k, m] of Object.entries(f.m)) {
    const o = ITEMS.get(k);
    if (o) o.matrix.fromArray(m);
  }
}

// ---------- 시점 ----------
function bounds(objs) {
  const b = new THREE.Box3();
  objs.forEach((o) => { if (o.visible) { o.geometry.boundingBox || o.geometry.computeBoundingBox(); b.union(o.geometry.boundingBox.clone().applyMatrix4(o.matrix)); } });
  return b;
}
function frameBox(b) {
  if (b.isEmpty()) return;
  const s = b.getSize(new THREE.Vector3()).length();
  view.target.copy(b.getCenter(new THREE.Vector3()));
  view.dist = Math.max(30, s * 1.15);
}
function frameAll(padFirst) {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  if (padFirst && sc && sc.pad) { // SC 장면은 처음에 3D 프린팅 패드와 그 위 존재를 비춤
    view.target.set(sc.pad[0], sc.pad[1], sc.pad[2] + 30);
    view.dist = 420; view.yaw = -0.55; view.pitch = 0.42;
    return;
  }
  frameBox(bounds([...ITEMS.values()]));
}
const NUM = { front: [0, 0], back: [Math.PI, 0], right: [Math.PI / 2, 0], left: [-Math.PI / 2, 0], top: [0, Math.PI / 2 - 1e-3], bottom: [0, -Math.PI / 2 + 1e-3] };

// HW 뷰포트: 사람이 수조 앞 유리 앞에 서 있음 (눈이 수조 속으로 못 들어감) — 기계가 존재를 돌림
const viewer = { yaw: 0, pitch: 0.12 };
function hwCamera() {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  const p = sc && sc.pad ? sc.pad : [0, 0, 100];
  view.target.set(0, 0, p[2] + 30);
  view.yaw = viewer.yaw; view.pitch = viewer.pitch; view.dist = 820;
}

// ---------- 입력 (Blender 키맵) ----------
let drag = null;
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener("pointerdown", (e) => {
  canvas.focus();
  const orbitBtn = e.button === 1 || (e.button === 0 && $("#lmb")?.checked !== false) || (e.button === 0 && e.altKey);
  drag = { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, btn: e.button, orbit: orbitBtn, shift: e.shiftKey, ctrl: e.ctrlKey, moved: false };
  canvas.setPointerCapture(e.pointerId);
});
let hwPending = null;
function hwSend(action, args) { // 너무 자주 보내지 않게 (기계는 천천히 움직임)
  if (hwPending) { hwPending.args = mergeDelta(hwPending.args, args); return; }
  hwPending = { action, args };
  setTimeout(async () => {
    const p = hwPending; hwPending = null;
    const r = await api("/api/hw", { scene: SCENE, action: p.action, ...p.args });
    $("#hwlog").textContent = r.log.join("\n");
    $("#hwlog").scrollTop = 1e9;
    syncDims(r.dims);
    if (r.geometry) await loadScene(SCENE, true); else await refreshFrame();
    updateHUD();
  }, 120);
}
const mergeDelta = (a, b) => ("delta" in a && "delta" in b ? { ...a, delta: a.delta + b.delta } : b);
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY;
  if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 3) drag.moved = true;
  if (!drag.moved || (!drag.orbit && drag.btn !== 2)) return;
  if (HW) {
    if (drag.shift) hwSend("bed", { delta: dy * 0.35 });
    else { hwSend("turn", { delta: dx * 0.4 }); viewer.pitch = Math.max(-0.3, Math.min(1.2, viewer.pitch + dy * 0.004)); hwCamera(); }
    return;
  }
  if (drag.shift) { // 옮겨 보기
    const k = view.dist / 900;
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0), up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
    view.target.addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
  } else if (drag.ctrl) view.dist *= Math.exp(dy * 0.01);
  else { view.yaw -= dx * 0.008; view.pitch = Math.max(-1.55, Math.min(1.55, view.pitch + dy * 0.008)); }
});
canvas.addEventListener("pointerup", (e) => {
  if (drag && !drag.moved && drag.btn === 0) pick(e);
  drag = null;
});
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  if (HW) { hwSend("zoom", { delta: -Math.sign(e.deltaY) * 2 }); return; }
  view.dist *= Math.exp(Math.sign(e.deltaY) * 0.12);
}, { passive: false });
canvas.tabIndex = 0;
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const k = e.code.replace("Numpad", "").replace("Digit", "");
  const big = Math.PI / 12;
  if (HW) {
    if (k === "1") hwSend("view", { view: "front" });
    else if (k === "3") hwSend("view", { view: "side" });
    else if (k === "7") hwSend("view", { view: "top" });
    else if (k === "4" || k === "6") hwSend("turn", { delta: k === "4" ? -15 : 15 });
    else if ((k === "8" || k === "2") && e.ctrlKey) hwSend("bed", { delta: k === "8" ? -5 : 5 });
    else if (k === "8" || k === "2") { viewer.pitch = Math.max(-0.3, Math.min(1.2, viewer.pitch + (k === "8" ? 0.2 : -0.2))); hwCamera(); status("위아래로 보기 — 기계는 그대로, 사람이 수조 위 · 옆에서 봄"); }
    else if (e.code === "Home") hwSend("home", {});
    else return;
    e.preventDefault();
    return;
  }
  if (k === "1") Object.assign(view, { yaw: NUM[e.ctrlKey ? "back" : "front"][0], pitch: 0 });
  else if (k === "3") Object.assign(view, { yaw: NUM[e.ctrlKey ? "left" : "right"][0], pitch: 0 });
  else if (k === "7") view.pitch = e.ctrlKey ? NUM.bottom[1] : NUM.top[1];
  else if (k === "4") view.yaw -= big; else if (k === "6") view.yaw += big;
  else if (k === "8") view.pitch = Math.min(1.55, view.pitch + big); else if (k === "2") view.pitch = Math.max(-1.55, view.pitch - big);
  else if (e.code === "Home") frameAll(false);
  else if (e.code === "NumpadDecimal" || e.code === "Period" || e.code === "KeyF") { if (SELECTED) frameBox(bounds([SELECTED])); }
  else if (e.code === "KeyH" && SELECTED) { HIDDEN.add(SELECTED.userData.name); applyHidden(); }
  else if (e.code === "KeyH" && e.altKey) { HIDDEN.clear(); applyHidden(); }
  else return;
  e.preventDefault();
});

const ray = new THREE.Raycaster();
function pick(e) {
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  const hits = ray.intersectObjects([...ITEMS.values()].filter((o) => o.visible && o.material.opacity > 0.3), false);
  const h = hits[0];
  if (HW && h) { hwSend("look", { x: h.point.x, y: h.point.y, r: 6 }); }
  select(h ? h.object : null);
}
function select(o) {
  if (SELECTED) SELECTED.material = SELECTED.userData._mat || SELECTED.material;
  SELECTED = o;
  document.querySelectorAll(".row.sel").forEach((r) => r.classList.remove("sel"));
  if (!o) { $("#sel").innerHTML = '<p class="dim">없음</p>'; return; }
  o.userData._mat = o.material;
  o.material = o.material.clone();
  o.material.emissive = new THREE.Color(0x3355aa);
  const row = document.querySelector(`.row[data-name="${CSS.escape(o.userData.name)}"]`);
  if (row) { row.classList.add("sel"); row.scrollIntoView({ block: "nearest" }); }
  showSelection(o.userData);
}

// ---------- 아웃라이너 ----------
function buildTree(items) {
  const tree = { kids: new Map(), objs: new Map() };
  for (const it of items) {
    let n = tree;
    for (const c of it.path) { if (!n.kids.has(c)) n.kids.set(c, { kids: new Map(), objs: new Map() }); n = n.kids.get(c); }
    n.objs.set(it.name, (n.objs.get(it.name) || 0) + 1);
  }
  const el = $("#tree");
  el.innerHTML = "";
  const draw = (n, parent, depth, prefix) => {
    for (const [name, k] of n.kids) {
      if (depth === 0 && name === SCENE) { draw(k, parent, depth, prefix); continue; }
      const d = document.createElement("div");
      d.className = "node coll";
      const path = [...prefix, name];
      d.innerHTML = `<div class="row" data-coll="${encodeURIComponent(path.join("/"))}"><span class="tw">▾</span><span class="eye">👁</span><span>${name}</span></div>`;
      const body = document.createElement("div");
      d.appendChild(body);
      d.querySelector(".tw").onclick = (ev) => { ev.stopPropagation(); body.hidden = !body.hidden; ev.target.textContent = body.hidden ? "▸" : "▾"; };
      d.querySelector(".eye").onclick = (ev) => { ev.stopPropagation(); toggleColl(path, ev.target); };
      parent.appendChild(d);
      draw(k, body, depth + 1, path);
      if (depth >= 1 && k.objs.size > 6) { body.hidden = true; d.querySelector(".tw").textContent = "▸"; }
    }
    for (const [name, count] of n.objs) {
      const d = document.createElement("div");
      d.className = "node obj";
      d.innerHTML = `<div class="row" data-name="${name.replace(/"/g, "&quot;")}"><span class="tw"></span><span class="eye">👁</span><span>${name}${count > 1 ? ` <span class="dim">×${count}</span>` : ""}</span></div>`;
      d.querySelector(".row").onclick = () => select([...ITEMS.values()].find((o) => o.userData.name === name));
      d.querySelector(".eye").onclick = (ev) => { ev.stopPropagation(); HIDDEN.has(name) ? HIDDEN.delete(name) : HIDDEN.add(name); applyHidden(); };
      parent.appendChild(d);
    }
  };
  draw(tree, el, 0, []);
}
const HIDDEN_COLL = new Set();
function toggleColl(path, eye) {
  const k = path.join("/");
  HIDDEN_COLL.has(k) ? HIDDEN_COLL.delete(k) : HIDDEN_COLL.add(k);
  applyHidden();
}
function applyHidden() {
  for (const o of ITEMS.values()) {
    const p = o.userData.path;
    let hid = HIDDEN.has(o.userData.name);
    for (let i = 1; i <= p.length && !hid; i++) if (HIDDEN_COLL.has(p.slice(0, i).join("/"))) hid = true;
    o.visible = !hid;
  }
  document.querySelectorAll(".row[data-name]").forEach((r) => (r.querySelector(".eye").style.opacity = HIDDEN.has(r.dataset.name) ? 0.25 : 1));
  document.querySelectorAll(".row[data-coll]").forEach((r) => (r.querySelector(".eye").style.opacity = HIDDEN_COLL.has(decodeURIComponent(r.dataset.coll)) ? 0.25 : 1));
}

// ---------- 속성 ----------
function showDims() {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  const el = $("#dims");
  el.innerHTML = sc.dims.length ? "" : '<p class="dim">이 장면은 기본형을 직접 (메타볼 · 아웃라이너)</p>';
  for (const d of sc.dims) {
    const step = d.max - d.min > 50 ? 0.5 : 0.01;
    const row = document.createElement("div");
    row.className = "dimrow";
    row.innerHTML = `<label><b>${d.key}</b><input type="number" step="${step}" value="${d.value}"></label>
      <input type="range" min="${d.min}" max="${d.max}" step="${step}" value="${d.value}"><div class="desc">${d.desc}</div>`;
    const [num, rng] = row.querySelectorAll("input");
    let t = null;
    const send = (v) => {
      num.value = v; rng.value = v; d.value = +v;
      clearTimeout(t);
      t = setTimeout(async () => {
        const r = await api("/api/set", { scene: SCENE, key: d.key, value: +v });
        if (r.geometry) await loadScene(SCENE, true); else await refreshFrame();
        updateHUD();
      }, 90);
    };
    rng.oninput = () => send(rng.value);
    num.onchange = () => send(num.value);
    row.dataset.key = d.key;
    el.appendChild(row);
  }
}
function syncDims(dims) {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  for (const d of sc.dims) if (d.key in dims) {
    d.value = dims[d.key];
    const row = document.querySelector(`.dimrow[data-key="${d.key}"]`);
    if (row) row.querySelectorAll("input").forEach((i) => (i.value = (+dims[d.key]).toFixed(2)));
  }
}
async function showSelection(it) {
  const el = $("#sel");
  el.innerHTML = `<p><b>${it.name}</b>${it.part ? `<br><span class="dim">부품: ${it.part}</span>` : ""}<br><span class="dim">${it.path.join(" › ")}</span></p>`;
  if (SCENE !== "존재 모양") return;
  const m = await api(`/api/meta?object=${encodeURIComponent(it.name)}`).catch(() => null);
  if (!m || !m.elements.length) return;
  el.insertAdjacentHTML("beforeend", `<p class="dim">메타볼 요소 ${m.elements.length}개 — 값을 바꾸면 Blender 가 다시 녹이고 조립 속 존재도 새로 구움</p>`);
  for (const e of m.elements) {
    const d = document.createElement("div");
    d.className = "el";
    d.innerHTML = `<b>${e.i + 1}. ${{ BALL: "구", CAPSULE: "캡슐", ELLIPSOID: "타원체" }[e.type] || e.type}</b> <button data-x>빼기</button>
      <div class="grid"><input title="x" value="${e.co[0].toFixed(1)}"><input title="y" value="${e.co[1].toFixed(1)}"><input title="z" value="${e.co[2].toFixed(1)}"><input title="반지름 (표면)" value="${e.r.toFixed(2)}"></div>`;
    const ins = d.querySelectorAll("input");
    ins.forEach((i) => (i.onchange = async () => {
      busy(true);
      await api("/api/meta", { object: m.name, i: e.i, co: [+ins[0].value, +ins[1].value, +ins[2].value], r: +ins[3].value });
      await loadScene(SCENE, true); busy(false);
    }));
    d.querySelector("[data-x]").onclick = async () => { await api("/api/meta", { object: m.name, i: e.i, remove: true }); await loadScene(SCENE, true); showSelection(it); };
    el.appendChild(d);
  }
  const add = document.createElement("p");
  add.innerHTML = '더하기: <button data-t="BALL">+ 구</button> <button data-t="CAPSULE">+ 캡슐</button> <button data-t="ELLIPSOID">+ 타원체</button>';
  add.querySelectorAll("button").forEach((b) => (b.onclick = async () => { await api("/api/meta", { object: m.name, add: b.dataset.t }); await loadScene(SCENE, true); showSelection(it); }));
  el.appendChild(add);
}
async function showProcess() {
  const box = $("#procBox");
  box.hidden = SCENE !== "SC-3 영점 막대";
  if (box.hidden) return;
  const p = await api("/api/process").catch((e) => ({ error: e.message }));
  const el = $("#proc");
  if (p.error) { el.innerHTML = `<p class="dim">${p.error}</p>`; return; }
  el.innerHTML = `<p class="dim">${p.sd} · ${p.name} · ${(p.total_s / 3600).toFixed(1)} h · 구움 ${p.burned} · 고친 것 ${p.edits.length}건 (→ <code>candy reburn</code>)</p>`;
  for (const s of p.steps) {
    const row = document.createElement("div");
    row.className = "dimrow";
    row.innerHTML = `<label><span>단계 ${s.i} · r ${s.r_mm[0]}–${s.r_mm[1]} mm · ${(s.seconds / 60).toFixed(0)} 분${s.repeat > 1 ? " ×" + s.repeat : ""}${s.skip ? " (건너뜀)" : ""}</span>
      <span><button data-go>보기</button> <button data-r>R 반복</button> <button data-s>S 건너뛰기</button></span></label>`;
    row.querySelector("[data-go]").onclick = async () => { await api("/api/set", { scene: SCENE, key: "Grow", value: s.r_mm[1] }); syncDims({ Grow: s.r_mm[1] }); await loadScene(SCENE, true); };
    row.querySelector("[data-r]").onclick = async () => { await api("/api/process", { op: "repeat", step: s.i }); showProcess(); status(`단계 ${s.i} 반복 — SD edits.json 에 적음`); };
    row.querySelector("[data-s]").onclick = async () => { await api("/api/process", { op: "skip", step: s.i }); showProcess(); status(`단계 ${s.i} 건너뛰기 — SD edits.json 에 적음`); };
    el.appendChild(row);
  }
}
function updateHUD() {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  const dv = Object.fromEntries(sc.dims.map((d) => [d.key, d.value]));
  $("#hud").textContent = HW
    ? `HW 뷰포트 — ${SCENE} · 수조 앞에 선 사람의 눈\n끌기 = 회전 받침 ${(+dv.TurnTable || 0).toFixed(0)}° · Shift+끌기 = 받침 ${(+dv.BedDrop || 0).toFixed(1)} mm` +
      (sc.hw === "sc2" ? ` · 휠 = 보기 빛 R ${(+dv.ViewR || 0).toFixed(0)} mm · 누르기 = 그곳 비춤` : " · 누르기 = 고르기 (SC-1 은 보기 빛 없음)") +
      "\n숫자판 1 · 3 · 7 앞 · 옆 · 위 · Home 처음으로"
    : `${SCENE}\n가운데(또는 왼쪽) 끌기 돌려 보기 · Shift 옮겨 보기 · 휠 확대 · 숫자판 1 3 7 · Home · F 고른 것`;
}

// ---------- 단추 ----------
async function init() {
  INFO = await api("/api/info");
  const nav = $("#scenes");
  for (const s of INFO.scenes) {
    const b = document.createElement("button");
    b.textContent = s.name; b.dataset.s = s.name;
    b.onclick = () => { setHW(false); loadScene(s.name); };
    nav.appendChild(b);
  }
  $("#keymap").innerHTML = "<table>" + INFO.keymap.map((r) => `<tr><td>${r[0]}</td><td>${r[1]}<br><span class="dim">${r[2]}</span></td></tr>`).join("") + "</table>" +
    '<p><label><input type="checkbox" id="lmb" checked> 왼쪽 끌기도 돌려 보기 (가운데 버튼 없는 마우스 · 터치패드)</label></p>';
  resize();
  await loadScene(INFO.scenes[0].name);
  loop();
}
function setHW(on) {
  const sc = INFO.scenes.find((s) => s.name === SCENE);
  HW = on && !!(sc && sc.hw);
  $("#hw").checked = HW;
  document.body.classList.toggle("hwon", HW);
  $("#hwH").hidden = $("#hwlog").hidden = !HW;
  if (HW) hwCamera(); else if (on) status("HW 뷰포트는 SC-1 조각가 · SC-2 빛 조각가 장면에서");
  if (INFO) updateHUD();
}
$("#hw").onchange = (e) => setHW(e.target.checked);
$("#bCheck").onclick = async () => {
  busy(true);
  const r = await api(`/api/check?scene=${encodeURIComponent(SCENE)}`).catch((e) => ({ error: e.message }));
  busy(false);
  if (r.error) return status(r.error);
  const bad = r.clearance.filter((x) => x.gap < 2);
  $("#joblog").innerHTML = `<span class="${bad.length ? "bad" : "ok"}">공간 점검 ${bad.length ? "문제 " + bad.length : "통과"}</span> · ` +
    `<span class="${r.motion.length ? "bad" : "ok"}">움직임 점검 ${r.motion.length ? "부딪힘 " + r.motion.length : "통과"}</span>\n` +
    r.clearance.filter((x) => x.gap < 10).map((x) => `  ${x.zone} ↔ ${x.part}: ${x.gap.toFixed(1)} mm`).join("\n");
};
async function sendTo(machine) {
  const obj = SELECTED && SCENE === "존재 모양" ? SELECTED.userData.name : null;
  const r = await api("/api/send", { machine, object: obj }).catch((e) => ({ error: e.message }));
  if (r.error) return status(r.error);
  status(`${r.started} — ${r.stl}`);
  const poll = setInterval(async () => {
    const l = await api("/api/log");
    $("#joblog").textContent = `── ${l.title}${l.running ? " (도는 중)" : l.code === 0 ? " 끝 — '빚은 세포' 장면에 불러옴" : " 실패"}\n` + l.lines.slice(-30).join("\n");
    $("#log").scrollTop = 1e9;
    if (!l.running) { clearInterval(poll); if (l.code === 0 && SCENE === "빚은 세포") loadScene(SCENE, true); }
  }, 1000);
}
$("#bSC1").onclick = () => sendTo("sc1");
$("#bSC2").onclick = () => sendTo("sc2");
$("#bRender").onclick = async () => {
  busy(true); status("Blender 가 EEVEE 로 렌더하는 중 (지금 시점 그대로)…");
  const r = canvas.getBoundingClientRect();
  const png = await api("/api/render", { scene: SCENE, eye: camera.position.toArray(), target: view.target.toArray(), fov: camera.fov, w: Math.round(r.width), h: Math.round(r.height) });
  const img = $("#shot img");
  img.src = URL.createObjectURL(new Blob([png], { type: "image/png" }));
  $("#shot").hidden = false; busy(false); status("Blender 렌더 끝");
};
$("#shot").onclick = () => ($("#shot").hidden = true);
$("#bSave").onclick = async () => { const r = await api("/api/save", {}); status(`저장: ${r.saved}`); };

function loop() {
  requestAnimationFrame(loop);
  placeCamera();
  renderer.render(scene3, camera);
}
init().catch((e) => status("연결 실패: " + e.message));
