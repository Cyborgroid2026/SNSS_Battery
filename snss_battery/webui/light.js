// 빛 조각가 · 콘솔 탭 — 배지가 모니터. 층별 프로젝터 화면 (405 · 530 nm) · 수조 3D (받침이 내려가며 자람) · 방수 키보드/마우스 조작 · 어림.
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const D = (window.DATA || {}).light;
const L = window.SNSS_LIGHT;
const B = window.SNSS_LIGHT_BEING;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ROLE = ["잉크 (빈 칸)", "p 세포질 (+)", "n 세포질 (−)", "막 · 피부"];

async function inflate(b64) {
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const ds = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(ds).arrayBuffer());
}

if (D && L) {
  // ---------- 카드 · 글 ----------
  const pct = (x) => `${(100 * x).toFixed(x < 0.01 ? 2 : 0)} %`;
  $("#lcCards").innerHTML = [
    ["존재", `높이 ${D.height_mm.toFixed(0)} mm · 세포 ${D.n_cells}개`],
    ["층", `${D.layers}개 × ${D.layer_mm} mm (빛 침투 ${D.dp_mm.toFixed(3)} mm)`],
    ["빚는 시간", `빛 + 내림 ${D.expose_h.toFixed(0)} h + 숙성 ${D.cure_h} h`],
    ["세포질 rGO · 막 샘", `${pct(D.cyto_reduced)} · ${pct(D.mem_leaky)}`],
    ["초록 p 도핑", `p 세포 ${pct(D.p_graft)} · n 세포 ${pct(D.n_graft)}`],
    ["에너지 (0.8 V)", `${(D.energy_j * 1000).toFixed(0)} mJ (도핑 없으면 ${(D.undoped_energy_j * 1000).toFixed(0)})`],
    ["주사기 주입 (n 세포)", `${D.inject.cells}개 · ${D.inject.phases}번 · +${D.inject.hours.toFixed(1)} h → ${(D.inject.energy_j * 1000).toFixed(0)} mJ`],
    ["사후 전기 도핑 (n 세포)", `PEI 통 ${D.edope_hours} h → ${(D.edope_energy_j * 1000).toFixed(0)} mJ · 속까지 약 ${D.edope_t90_h.toFixed(0)} h`],
    ["잉크층", `${D.ink_density.toFixed(1)} < 배지 ${D.bath_density.toFixed(1)} kg/m³ · CCC ${D.ccc_mm.toFixed(0)} mM`],
    ["상온", `잉크 표면 +${D.surface_k.toFixed(2)} K · 배지 +${D.bath_k.toFixed(2)} K`],
    ["빛 상수", D.calibrated ? "시험편 보정값 (light_cal.json)" : "가정값 — ./tools.sh light-cal 로 시험편부터"],
    ["설계 점검", D.check.length ? D.check.join(" · ") : "통과"],
  ].map(([k, v]) => `<div class="card"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
  $("#lcTools").innerHTML = `<tr><th>도구</th><th>이름</th><th>끝 (물속, 금속 없음)</th><th>쓰임</th></tr>` +
    D.tools.map((t) => `<tr><td>${esc(t.key)}</td><td>${esc(t.name)}</td><td>${esc(t.tip)}</td><td>${esc(t.use)}</td></tr>`).join("") +
    `<tr><td colspan="4" class="sub">도구 면 ${D.inject.tip_z} mm (멸균생리식염수 속) · 도구 작업은 작업물 ${D.inject.max_h.toFixed(0)} mm 까지</td></tr>`;
  $("#lcText").textContent = [D.machine, "", D.layout, "", D.job_text].join("\n");
  $("#lcRenders").innerHTML = D.renders.length
    ? `<h2>Blender 렌더 (./tools.sh light-blender)</h2>` + D.renders.map((f) => `<img class="fig" src="${esc(f)}" alt="Blender 렌더" style="max-width:49%">`).join(" ")
    : '<p class="sub">Blender 렌더가 아직 없습니다 — <code>./tools.sh light-blender</code> 를 실행한 뒤 웹을 다시 만드세요.</p>';

  const { nx, ny, nz, pitch, offset } = L;
  const [px, pz] = pitch;
  const vox = await inflate(L.gz);
  const cum = [];
  L.layer_s.reduce((a, t, i) => (cum[i] = a + t), 0);
  const firstK = L.layer_s.findIndex((t) => t > 0);
  const lastK = nz - 1 - [...L.layer_s].reverse().findIndex((t) => t > 0);
  let k = Math.round(firstK + 0.62 * (lastK - firstK));
  let ch = "both";
  let pinned = null;

  // ---------- 프로젝터 화면 ----------
  const off = document.createElement("canvas");
  off.width = nx;
  off.height = ny;
  const octx = off.getContext("2d");
  const img = octx.createImageData(nx, ny);
  const cv = $("#lcFrame");
  const ctx = cv.getContext("2d");
  const at = (x, y, c) => vox[((k * ny + y) * nx + x) * 3 + c];
  const fit = () => {
    const s = Math.min(cv.width / nx, cv.height / ny);
    return { s, x0: (cv.width - nx * s) / 2, y0: (cv.height - ny * s) / 2 };
  };

  function paintFrame() {
    const d = img.data;
    for (let y = 0; y < ny; y++) {
      const row = (ny - 1 - y) * nx; // 아래가 y 작은 쪽 (Python 그림과 같음)
      for (let x = 0; x < nx; x++) {
        const e = ch === "g" ? 0 : at(x, y, 1);
        const g = ch === "v" ? 0 : at(x, y, 2);
        const o = (row + x) * 4;
        d[o] = Math.round(0.62 * e); d[o + 1] = g; d[o + 2] = e; d[o + 3] = 255;
      }
    }
    octx.putImageData(img, 0, 0);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.imageSmoothingEnabled = false;
    const { s, x0, y0 } = fit();
    ctx.drawImage(off, x0, y0, nx * s, ny * s);
    // 10 mm 눈금
    ctx.strokeStyle = "#fff"; ctx.fillStyle = "#fff"; ctx.lineWidth = 2; ctx.font = "12px sans-serif";
    const bar = (10 / px) * s;
    ctx.beginPath(); ctx.moveTo(14, cv.height - 14); ctx.lineTo(14 + bar, cv.height - 14); ctx.stroke();
    ctx.fillText("10 mm", 14, cv.height - 20);
    if (pinned) {
      ctx.strokeStyle = "#ffd84d";
      ctx.strokeRect(x0 + pinned[0] * s - 1, y0 + (ny - 1 - pinned[1]) * s - 1, s + 2, s + 2);
    }
    if (tex) tex.needsUpdate = true;
  }

  function cellInfo(x, y) {
    const m = at(x, y, 0);
    const e = (at(x, y, 1) / 255) * L.e_max;
    const g = (at(x, y, 2) / 255) * L.g_max;
    return `x ${((offset[0] + x + 0.5) * px).toFixed(1)} · y ${((offset[1] + y + 0.5) * px).toFixed(1)} mm — ${ROLE[m]} · ` +
      `405 nm ${e.toFixed(0)} mJ/cm² · 530 nm ${g.toFixed(0)} mJ/cm²` + (pinned ? " (고정 — 다시 누르면 풂)" : "");
  }
  function pick(ev) {
    const r = cv.getBoundingClientRect();
    const { s, x0, y0 } = fit();
    const cx = ((ev.clientX - r.left) / r.width) * cv.width;
    const cy = ((ev.clientY - r.top) / r.height) * cv.height;
    const x = Math.floor((cx - x0) / s);
    const y = ny - 1 - Math.floor((cy - y0) / s);
    return x >= 0 && x < nx && y >= 0 && y < ny ? [x, y] : null;
  }
  cv.addEventListener("mousemove", (ev) => {
    if (pinned) return;
    const p = pick(ev);
    $("#lcHover").textContent = p ? cellInfo(...p) : "칸에 마우스를 올리면 노출량 · 재료";
  });
  cv.addEventListener("click", (ev) => {
    const p = pick(ev);
    pinned = pinned || !p ? null : p;
    if (p) $("#lcHover").textContent = cellInfo(...p);
    paintFrame();
  });
  cv.addEventListener("wheel", (ev) => { ev.preventDefault(); setLayer(k + (ev.deltaY > 0 ? -1 : 1)); }, { passive: false });

  // ---------- 수조 3D ----------
  const view = $("#lcTank");
  let tex = null;
  let renderer, scene, cam, controls, being, plane;
  const FILL = D.fill_mm;
  function initTank() {
    $("#lcMsg").remove();
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.localClippingEnabled = true;
    view.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    cam = new THREE.PerspectiveCamera(32, 1, 1, 8000);
    cam.up.set(0, 0, 1);
    controls = new OrbitControls(cam, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x404858, 1.4));
    const key = new THREE.DirectionalLight(0xffffff, 1.3);
    key.position.set(300, -500, 900);
    scene.add(key);
    const T = D.tank_mm;
    const edges = (w, d, h, z, color, op = 0.6) => {
      const ls = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, d, h)),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: op }));
      ls.position.z = z;
      scene.add(ls);
    };
    edges(T, T, T, T / 2 - 4, 0xbfd8ff); // 유리 수조
    const water = new THREE.Mesh(new THREE.BoxGeometry(T - 2, T - 2, FILL + 4),
      new THREE.MeshPhongMaterial({ color: 0x9fd0f2, transparent: true, opacity: 0.1, depthWrite: false }));
    water.position.z = (FILL - 4) / 2;
    scene.add(water);
    const W = D.well_mm, H = D.ink_depth_mm;
    const ink = new THREE.Mesh(new THREE.BoxGeometry(W, W, H),
      new THREE.MeshPhongMaterial({ color: 0x2b1d14, transparent: true, opacity: 0.35, depthWrite: false }));
    ink.position.z = FILL - H / 2;
    scene.add(ink);
    edges(W + 6, W + 6, H + 15, FILL - (H + 10) / 2 + 2.5, 0xf08a3c, 0.9); // 잉크 우물 테
    // 프로젝터 · 빛길
    const pjm = new THREE.Mesh(new THREE.BoxGeometry(120, 90, 60), new THREE.MeshPhongMaterial({ color: 0xd9a441 }));
    pjm.position.z = D.gz + 30;
    scene.add(pjm);
    const cone = new THREE.Mesh(new THREE.ConeGeometry(55 * Math.SQRT2, D.gz - FILL, 4, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x8a4dff, transparent: true, opacity: 0.07, side: THREE.DoubleSide, depthWrite: false }));
    cone.rotation.x = -Math.PI / 2;
    cone.rotation.y = Math.PI / 4;
    cone.position.z = (D.gz + FILL) / 2;
    scene.add(cone);
    // 수면 = 모니터: 프로젝터 화면을 그대로 비춤
    tex = new THREE.CanvasTexture(off);
    tex.magFilter = tex.minFilter = THREE.NearestFilter;
    tex.colorSpace = THREE.SRGBColorSpace;
    plane = new THREE.Mesh(new THREE.PlaneGeometry(nx * px, ny * px),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    plane.position.set((offset[0] + nx / 2) * px, (offset[1] + ny / 2) * px, FILL + 0.3);
    scene.add(plane);
    // 존재 + 받침 (함께 내려감), 수면 위는 아직 빚지 않음 → 잘라 냄
    const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), FILL);
    being = new THREE.Group();
    const colors = { pos: 0xe0344b, neg: 0x3d7bd6, mem: 0xb9c3ce };
    for (const role of ["pos", "neg", "mem"]) {
      const r = B && B[role];
      if (!r) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(r.v, 3));
      g.setIndex(r.f);
      g.computeVertexNormals();
      being.add(new THREE.Mesh(g, new THREE.MeshPhongMaterial({
        color: colors[role], clippingPlanes: [clip], side: THREE.DoubleSide,
        transparent: role === "mem", opacity: role === "mem" ? 0.25 : 1, depthWrite: role !== "mem" })));
    }
    const bed = new THREE.Mesh(new THREE.BoxGeometry(120, 120, 6), new THREE.MeshPhongMaterial({ color: 0xdde3ea }));
    bed.position.z = -3;
    const riser = new THREE.Mesh(new THREE.BoxGeometry(40, 40, 40), new THREE.MeshPhongMaterial({ color: 0xf08a3c }));
    riser.position.z = -26;
    being.add(bed, riser);
    scene.add(being);
    resetCam();
    new ResizeObserver(resize).observe(view);
    resize();
    (function loop() { controls.update(); renderer.render(scene, cam); requestAnimationFrame(loop); })();
  }
  function resetCam() {
    cam.position.set(420, -640, FILL + 330);
    controls.target.set(0, 0, FILL - 60);
    controls.update();
  }
  function resize() {
    const w = view.clientWidth, h = view.clientHeight;
    renderer.setSize(w, h, false);
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
  }

  // ---------- 층 ----------
  const slider = $("#lcLayer");
  slider.min = firstK;
  slider.max = lastK;
  function setLayer(v) {
    k = Math.max(firstK, Math.min(lastK, v));
    slider.value = k;
    const t = cum[k] / 3600;
    const swaps = Math.floor(t / D.ink_life_h);
    $("#lcLayerV").textContent = `층 ${k} · z ${((k + 1) * pz).toFixed(1)} mm`;
    $("#lcTimeV").textContent = `${t.toFixed(1)} h 지남 / ${(cum[lastK] / 3600).toFixed(1)} h · 이 층 ${(L.layer_s[k] / 60).toFixed(1)} 분` +
      (swaps ? ` · 잉크 ${swaps}번 갈았음` : "");
    if (being) being.position.z = FILL - (k + 1) * pz;
    if (pinned) $("#lcHover").textContent = cellInfo(...pinned);
    paintFrame();
  }
  slider.oninput = () => setLayer(+slider.value);
  let timer = null;
  function play() {
    if (timer) { clearInterval(timer); timer = null; $("#lcPlay").textContent = "▶ 빚기 재생 (Space)"; return; }
    if (k >= lastK) setLayer(firstK);
    $("#lcPlay").textContent = "■ 멈춤 (Space)";
    timer = setInterval(() => { if (k >= lastK) play(); else setLayer(k + 1); }, 70);
  }
  $("#lcPlay").onclick = play;
  document.querySelectorAll('input[name="lcCh"]').forEach((r) => (r.onchange = () => { ch = r.value; paintFrame(); }));
  const setCh = (v) => { ch = v; document.querySelector(`input[name="lcCh"][value="${v}"]`).checked = true; paintFrame(); };

  // 방수 키보드: 콘솔 탭이 보일 때만
  document.addEventListener("keydown", (ev) => {
    if (!$('section[data-id="console"]').classList.contains("on")) return;
    if (ev.target.tagName === "INPUT" && ev.target.type !== "radio") return;
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: 10, ArrowDown: -10 }[ev.key];
    if (step) setLayer(k + step);
    else if (ev.key === "Home") setLayer(firstK);
    else if (ev.key === "End") setLayer(lastK);
    else if (ev.key === " ") play();
    else if (ev.key === "1" || ev.key === "2" || ev.key === "3") setCh({ 1: "both", 2: "v", 3: "g" }[ev.key]);
    else if (ev.key === "r" || ev.key === "R") { if (cam) resetCam(); }
    else return;
    ev.preventDefault();
  });

  // ---------- 어림 (lightsculpt.py 와 같은 식) ----------
  const K = D.k;
  const w = { go: $("#wGo"), I: $("#wI"), Ig: $("#wIg"), pva: $("#wPva") };
  w.go.value = K.go_mg_ml; w.I.value = K.irr; w.Ig.value = K.irr_g; w.pva.value = K.pva_wt;
  function whatIf() {
    const go = +w.go.value, I = +w.I.value, Ig = +w.Ig.value, pva = +w.pva.value;
    $("#wGoV").textContent = `${go} mg/mL`; $("#wIV").textContent = `${I} mW/cm²`; $("#wIgV").textContent = `${Ig} mW/cm²`; $("#wPvaV").textContent = `${pva} %`;
    const dp = 10 / (Math.LN10 * (K.eps_go * go + K.a_sbq * pva));
    const leak = (x) => Math.exp(-x) + (K.ec * Math.exp((1 + K.overcure) * x) * (1 - Math.exp(-x))) / x / K.e_red;
    let x = 0.5;
    for (let t = 0.5; t <= 4; t += 0.01) if (leak(t) < leak(x)) x = t;
    const h = x * dp;
    const dpg = 10 / (Math.LN10 * (K.eps_go_530 * go + K.eps_eosin * K.eosin_um * 1e-6));
    const H = D.height_mm;
    const layers = Math.ceil(H / h);
    const tV = (K.e_red * H) / (dp * I) / 3600;
    const tG = (K.e_graft_target * H) / (dpg * Ig) / 3600;
    const tR = (layers * K.recoat_s) / 3600;
    const dT = (Math.max(I, Ig) * 10 * (1 - K.reflect)) / (0.6 / (D.ink_depth_mm / 1000) + 10);
    const rhoW = K.rho_water;
    const rho = rhoW + go * (1 - rhoW / 1800) + 10 * pva * (1 - rhoW / 1270) + 0.0405 * K.nacl_mm;
    const ccc = 44 * (1 + 0.15 * pva);
    const ok = (b) => (b ? '<span class="badge ok">✔</span>' : '<span class="badge bad">✘</span>');
    $("#lcWhatIf").innerHTML = "<tr><th>항목</th><th>어림</th><th>판정</th></tr>" + [
      ["빛 침투 Dp (405 / 530 nm)", `${dp.toFixed(3)} / ${dpg.toFixed(3)} mm`, true],
      ["층 두께 (막 새는 빛 최소)", `${h.toFixed(3)} mm = ${x.toFixed(2)} Dp · ${layers}층`, true],
      ["막 아래로 새는 빛", `${leak(x).toFixed(2)} · E_red (θ ${K.theta})`, leak(x) <= K.theta],
      ["시간: 405 + 530 + 내림", `${tV.toFixed(1)} + ${tG.toFixed(1)} + ${tR.toFixed(1)} = ${(tV + tG + tR).toFixed(1)} h`, true],
      ["잉크 표면 온도 (상온)", `+${dT.toFixed(2)} K`, dT <= 1],
      ["잉크가 뜸", `${rho.toFixed(1)} vs 배지 ${D.bath_density.toFixed(1)} kg/m³`, rho <= D.bath_density - 0.5],
      ["잉크 속 GO 가 떠 있음", `염 ${(K.nacl_mm + K.nbd_mm).toFixed(0)} mM < CCC ${ccc.toFixed(0)} mM`, K.nacl_mm + K.nbd_mm < ccc],
      ["에너지 (GO 에 비례, 어림)", `${((D.energy_j * go) / K.go_mg_ml * 1000).toFixed(0)} mJ`, true],
    ].map(([a, b, c]) => `<tr><td>${esc(a)}</td><td class="n">${esc(b)}</td><td>${ok(c)}</td></tr>`).join("");
  }
  Object.values(w).forEach((el) => (el.oninput = whatIf));
  whatIf();

  // ---------- 시험편 측정 → 보정 (서버 /api/lightcal) ----------
  const CAL_HEAD = { A: ["A 굳힘", "노출 mJ/cm²", "두께 mm"], B: ["B 광환원", "노출 mJ/cm²", "저항 Ω"],
                     C: ["C 초록 접목", "노출 mJ/cm²", "ΔV mV"], D: ["D 전기 도핑", "전위 V", "ΔV mV"] };
  let calRows = [];
  let calDemo = false;
  function drawCal() {
    $("#lcCal").innerHTML = Object.entries(CAL_HEAD).map(([t, [h, xh, vh]]) =>
      `<table><tr><th colspan="3">${h}</th></tr><tr><th>칸</th><th>${xh}</th><th>${vh}</th></tr>` +
      calRows.filter((r) => r.test === t).map((r) =>
        `<tr><td class="n">${r.i}</td><td class="n">${r.x}</td><td><input data-t="${t}" data-i="${r.i}" value="${esc(r.value)}" inputmode="decimal"></td></tr>`).join("") +
      "</table>").join("");
    $("#lcCal").querySelectorAll("input").forEach((el) => (el.oninput = () => {
      const r = calRows.find((x) => x.test === el.dataset.t && x.i === +el.dataset.i);
      if (r) r.value = el.value.trim();
      calDemo = false; // 손으로 고치면 진짜 측정
    }));
  }
  fetch("api/lightcal", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((st) => {
    calRows = st.rows;
    drawCal();
    $("#lcCalText").textContent = st.text || "아직 보정값이 없습니다 (가정값으로 계산 중).";
  }).catch(() => {
    $("#lcCalText").textContent = "측정 저장은 서버에서만 됩니다 — ./tools.sh web 으로 열거나, measurements.csv 를 채워 python -m snss_battery light-cal fit …";
    $("#lcCalFit").disabled = $("#lcCalDemo").disabled = true;
  });
  $("#lcCalFit").onclick = async () => {
    $("#lcCalText").textContent = "맞추는 중…";
    const r = await fetch("api/lightcal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows: calRows, demo: calDemo }) });
    const j = await r.json();
    $("#lcCalText").textContent = j.error ? "오류: " + j.error : j.text;
  };
  $("#lcCalDemo").onclick = () => {  // lightcal.synthetic_measurements 와 같은 참값 (잡음 없음)
    const HB = 1.054571817e-34, VF = 1e6, Q = 1.602176634e-19;
    const dp = 10 / (Math.LN10 * (12 * K.go_mg_ml + K.a_sbq * K.pva_wt));
    const ef = (n) => (HB * VF * Math.sqrt(Math.PI * n * 1e16)) / Q * 1000;
    for (const r of calRows) {
      const x = r.x;
      r.value = String(+({
        A: Math.max(0, dp * Math.log(x / 28)),
        B: 10 ** -(-6 + 6 * (1 - Math.exp(-x / (1400 / Math.LN10)))),
        C: ef(4.0) * (1 - Math.exp(-x / 380)),
        D: ef(5.0) / (1 + Math.exp((x + 0.2) / 0.08)),
      }[r.test]).toPrecision(4));
    }
    drawCal();
    calDemo = true;
    $("#lcCalText").textContent = "연습값 (참값 ε_GO 12 · Ec 28 · E_red 1400 · E_g 380 · 정공 4.0 · E½ −0.2 V) — 맞추기를 누르면 되찾는지 봄";
  };

  setLayer(k);
  const start = () => { if (!renderer) initTank(); else resize(); };
  if (typeof tabHooks !== "undefined") tabHooks.console = start; // eslint-disable-line no-undef
  if ($('section[data-id="console"]').classList.contains("on")) start();
} else if ($("#lcCards")) {
  $("#lcCards").innerHTML = '<div class="card"><div class="v">빛 조각가 자료가 없습니다 — 웹을 다시 만드세요.</div></div>';
}
