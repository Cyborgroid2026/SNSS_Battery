// 조각가 · 존재 탭 — 양자 인공세포 존재 3D 보기 (깨어남 시간 · 쌓기 높이), 레시피 · 작업 · 파일.
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const D = (window.DATA || {}).sculptor;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

if (D) {
  const P = D.prediction;
  const tfmt = (s) => (s == null || !isFinite(s) ? "깨지 않음" : s < 120 ? `${s.toFixed(0)} s` : `${(s / 60).toFixed(1)} 분`);
  $("#scCards").innerHTML = [
    ["몸", `높이 ${P.height_mm.toFixed(0)} mm · ${P.body_ml.toFixed(1)} mL`],
    ["양자 인공세포", `${P.n_cells}개 (p ${P.n_pos} · n ${P.n_neg}, 약 ${D.cell_mm} mm)`],
    ["간극연접 · p–n 막", `${P.n_junction_pairs}쌍 · ${P.n_membrane_pairs}쌍`],
    ["양자층 페르미 준위", `p ${P.ef_pos_mev.toFixed(0)} · n +${P.ef_neg_mev.toFixed(0)} meV`],
    ["에너지 (0.8 V)", `${(P.energy_j * 1000).toFixed(0)} mJ · ${P.capacitance_f.toFixed(2)} F`],
    ["깨어남", `절반 ${tfmt(P.wake_median_s)} · 머리 ${tfmt(P.wake_head_s)}`],
    ["빚는 시간", `작업 ${D.job.work_h.toFixed(1)} h + 숙성 ${D.job.wait_h.toFixed(1)} h`],
    ["배지 (멸균생리식염수)", `${(D.job.saline_ml / 1000).toFixed(2)} L 가득 · 다 자란 뒤 ${D.job.nacl_after.toFixed(1)} mM`],
    ["설계 점검", D.check.length ? D.check.join(" · ") : "통과 (상온 · 펜 끝에서 굳음)"],
  ].map(([k, v]) => `<div class="card"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

  $("#scRecipes").innerHTML = "<tr><th>재료</th><th>GO : SNSS : PVA</th><th>GO 통</th><th>빛</th><th>섞인 뒤 GO</th><th>NaCl (CCC)</th><th>PVA</th><th>굳음</th><th>항복응력</th></tr>" +
    D.recipes.map((r) => `<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${r.color};margin-right:6px"></span>${esc(r.name)}</td>` +
      `<td class="n">${r.go.toFixed(2)} : ${r.snss.toFixed(2)} : ${r.pva.toFixed(2)}</td><td>${esc({ p: "p형 (NBD)", n: "n형 (PEI)", plain: "막용" }[r.variant] || r.variant)}</td>` +
      `<td>${r.light ? "405 nm 켬 → rGO" : "끔 → GO"}</td><td class="n">${r.go_mg.toFixed(1)} mg/mL</td><td class="n">${r.nacl.toFixed(0)} mM (${r.ccc.toFixed(0)})</td>` +
      `<td class="n">${r.pva_wt.toFixed(1)} %</td><td>${r.ok ? '<span class="badge ok">✔</span>' : '<span class="badge bad">✘</span>'}</td><td class="n">${r.yield.toFixed(0)} Pa</td></tr>`).join("");

  $("#scPorts").innerHTML = "<tr><th>분야</th><th>단자</th><th>연결</th><th>방향</th><th>신호</th><th>쓰임</th></tr>" +
    (D.ports || []).map((p) => `<tr><td>${esc(p.domain)}</td><td>${esc(p.key)}</td><td>${esc(p.connector)}</td><td>${esc(p.direction)}</td><td>${esc(p.signal)}</td><td>${esc(p.use)}</td></tr>`).join("");
  $("#scPartsImg").innerHTML = D.parts_png ? `<img class="fig" src="${esc(D.parts_png)}" alt="출력 부품판 (Blender)">` : "";
  const g = (D.parts || []).length;
  $("#scParts").innerHTML = `<tr><th>출력 부품 (${g}종 — 베드 ${D.parent_bed[0]}×${D.parent_bed[1]} FDM)</th><th>수량</th><th>재료</th><th>크기 mm</th><th>쓰임</th></tr>` +
    (D.parts || []).map((p) => `<tr><td>${esc(p.name)}</td><td class="n">${p.qty}</td><td>${esc(p.material)}</td><td class="n">${p.size.join(" × ")}${p.fits ? "" : " ⚠"}</td><td>${esc(p.role)}</td></tr>`).join("");
  $("#scBuy").innerHTML = "<tr><th>구분</th><th>품목</th><th>수량</th><th>사양</th><th>구입처</th></tr>" +
    (D.buy || []).map((b) => `<tr><td>${esc(b.group)}</td><td>${esc(b.part)}</td><td>${esc(b.qty)}</td><td>${esc(b.spec)}</td><td>${esc(b.where)}</td></tr>`).join("");

  const rend = D.renders || [];
  const imgs = rend.filter((f) => f.endsWith(".png")).map((f) => `<img class="fig" src="${esc(f)}" alt="Blender 렌더" style="max-width:49%">`).join(" ");
  const vid = rend.find((f) => f.endsWith(".mp4"));
  $("#scRenders").innerHTML = rend.length ? `<h2>Blender 렌더 (./tools.sh blender)</h2>${imgs}${vid ? `<video class="fig" src="${esc(vid)}" controls loop muted style="max-width:60%"></video>` : ""}` :
    '<p class="sub">Blender 렌더가 아직 없습니다 — <code>./tools.sh blender</code> 를 실행한 뒤 웹을 다시 만드세요.</p>';

  $("#scJob").innerHTML = "<tr><th>단계</th></tr>" + D.job.ops.map((o) => `<tr><td>${esc(o)}</td></tr>`).join("") +
    `<tr><td>재료 바꿈 ${D.job.switches}회 (혼합기 밀어내기 포함)</td></tr>` +
    D.files.map((f) => `<tr><td><a href="${esc(f)}" download>${esc(f.split("/").pop())} 받기</a></td></tr>`).join("") +
    (D.extra_files || []).map((f) => `<tr><td><a href="${esc(f)}" download>${esc(f.split("/").pop())} 받기</a></td></tr>`).join("");
  $("#scText").textContent = [D.prediction_text, "", D.qcap_text, "", D.machine].join("\n");

  // ---------- 3D ----------
  const view = $("#scView");
  const msg = $("#scMsg");
  let V;
  try {
    V = window.SNSS_BEING || (await (await fetch("sculpt/being_view.json")).json());
  } catch (e) {
    msg.textContent = "3D 를 불러오지 못했습니다: " + e;
  }
  if (V) {
    msg.remove();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.localClippingEnabled = true;
    view.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(30, 1, 1, 5000);
    cam.up.set(0, 0, 1);
    const controls = new OrbitControls(cam, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x404858, 1.5));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(120, -200, 260);
    scene.add(key);
    const H = V.bounds[0];
    const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), H + 1);
    const bright = { pos: new THREE.Color(0xff3b55), neg: new THREE.Color(0x3d8bff) };
    const dim = { pos: new THREE.Color(0x4a1c24), neg: new THREE.Color(0x1a2a46) };
    const meshes = {};
    let maxWake = 1;
    for (const role of ["pos", "neg", "mem"]) {
      const m = V[role];
      if (!m) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(m.v, 3));
      g.setIndex(m.f);
      g.computeVertexNormals();
      let mat;
      if (role === "mem") {
        mat = new THREE.MeshStandardMaterial({ color: 0xb9c3ce, transparent: true, opacity: 0.18, depthWrite: false,
                                               roughness: 0.4, clippingPlanes: [clip], side: THREE.DoubleSide });
      } else {
        g.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(m.v.length), 3));
        mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, clippingPlanes: [clip],
                                               emissive: 0x000000 });
        for (const w of m.w || []) if (w > maxWake) maxWake = w;
      }
      const mesh = new THREE.Mesh(g, mat);
      mesh.renderOrder = role === "mem" ? 2 : 1;
      scene.add(mesh);
      meshes[role] = { mesh, w: m.w };
    }
    const tEl = $("#scTime"), hEl = $("#scHeight");
    function paint() {
      const t = (tEl.value / 1000) * maxWake * 1.05;
      $("#scTimeV").textContent = `${tfmt(t)} — 빛나는 세포 = 깨어남 (63 % 충전)`;
      for (const role of ["pos", "neg"]) {
        const M = meshes[role];
        if (!M) continue;
        const col = M.mesh.geometry.getAttribute("color");
        const a = col.array;
        for (let i = 0; i < M.w.length; i++) {
          const w = M.w[i];
          const c = w >= 0 && w <= t ? bright[role] : dim[role];
          a[3 * i] = c.r; a[3 * i + 1] = c.g; a[3 * i + 2] = c.b;
        }
        col.needsUpdate = true;
      }
      const h = (hEl.value / 1000) * (H + 1);
      clip.constant = h;
      $("#scHeightV").textContent = `높이 ${h.toFixed(1)} / ${H.toFixed(1)} mm`;
    }
    tEl.oninput = paint;
    hEl.oninput = paint;
    const anim = (el, ms) => {
      const t0 = performance.now();
      const step = (now) => {
        el.value = Math.min(1000, ((now - t0) / ms) * 1000);
        paint();
        if (el.value < 1000) requestAnimationFrame(step);
      };
      el.value = 0;
      requestAnimationFrame(step);
    };
    $("#scWake").onclick = () => anim(tEl, 6000);
    $("#scBuild").onclick = () => anim(hEl, 6000);
    for (const [id, role] of [["#scSkin", "mem"], ["#scPos", "pos"], ["#scNeg", "neg"]]) {
      $(id).onchange = (e) => { if (meshes[role]) meshes[role].mesh.visible = e.target.checked; };
    }
    // 시점
    const box = new THREE.Box3();
    Object.values(meshes).forEach((m) => box.expandByObject(m.mesh));
    const c = box.getCenter(new THREE.Vector3());
    controls.target.copy(c);
    cam.position.set(c.x + H * 1.6, c.y - H * 2.4, c.z + H * 0.6);
    function resize() {
      const w = view.clientWidth, h = view.clientHeight || 460;
      renderer.setSize(w, h);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    }
    new ResizeObserver(resize).observe(view);
    resize();
    paint();
    (function loop() {
      controls.update();
      renderer.render(scene, cam);
      requestAnimationFrame(loop);
    })();
  }
}
