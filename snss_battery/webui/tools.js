// 표준 도구 탭 — FEniCSx(ParaView 프레임) · PyBaMM · PHREEQC · eLabFTW 결과를 브라우저에서 봄 (VS Code 통합 브라우저 포함).
// 데이터: web.py _standard_tools() → DATA.tools (spec/*.json, results/frames).
(function tools() {
  const T = (window.DATA || {}).tools;
  const body = document.getElementById("toolsBody");
  if (!T || !body) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const f = (v, d = 1) => (v == null || Number.isNaN(v) ? "-" : Number(v).toFixed(d));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  const COL = ["#3b7dd8", "#e07a1f", "#2f8a4f", "#b3261e", "#7a4fc9"];

  // ---------- 작은 선 그래프 (캔버스) ----------
  // series: [{x:[], y:[], name, color, dash}], o: {xlabel, ylabel, logx, cursor, points:[{x,y,name}]}
  function chart(cv, series, o = {}) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth || 520, H = cv.clientHeight || 260;
    cv.width = W * dpr; cv.height = H * dpr;
    const c = cv.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const L = 58, R = 12, Tp = 24, B = 40, ink = css("--ink"), muted = css("--muted"), line = css("--line");
    const tx = (v) => (o.logx ? Math.log10(v) : v);
    const xs = series.flatMap((s) => s.x.map(tx)), ys = series.flatMap((s) => s.y).filter((v) => v != null && isFinite(v));
    (o.points || []).forEach((p) => { xs.push(tx(p.x)); ys.push(p.y); });
    let [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    if (o.ymin != null) y0 = o.ymin;
    const pad = (y1 - y0) * 0.08 || 1; y0 -= o.ymin != null ? 0 : pad; y1 += pad;
    const X = (v) => L + ((tx(v) - x0) / (x1 - x0 || 1)) * (W - L - R), Y = (v) => H - B - ((v - y0) / (y1 - y0 || 1)) * (H - Tp - B);
    c.font = "11px sans-serif"; c.strokeStyle = line; c.fillStyle = muted; c.lineWidth = 1;
    for (let k = 0; k <= 4; k++) { // 눈금
      const yv = y0 + ((y1 - y0) * k) / 4, yy = Y(yv);
      c.beginPath(); c.moveTo(L, yy); c.lineTo(W - R, yy); c.stroke();
      c.textAlign = "right"; c.fillText(Math.abs(yv) >= 100 ? yv.toFixed(0) : yv.toFixed(Math.abs(y1 - y0) < 2 ? 2 : 1), L - 6, yy + 4);
    }
    c.textAlign = "center";
    if (o.logx) for (let e = Math.ceil(x0); e <= x1; e++) c.fillText(`${10 ** e >= 1 ? 10 ** e : (10 ** e).toPrecision(1)}`, X(10 ** e), H - B + 16);
    else for (let k = 0; k <= 5; k++) { const xv = x0 + ((x1 - x0) * k) / 5; c.fillText(xv.toFixed(x1 - x0 < 5 ? 1 : 0), X(xv), H - B + 16); }
    c.fillStyle = ink; c.fillText(o.xlabel || "", (L + W - R) / 2, H - 6);
    c.save(); c.translate(14, (Tp + H - B) / 2); c.rotate(-Math.PI / 2); c.fillText(o.ylabel || "", 0, 0); c.restore();
    series.forEach((s, k) => {
      c.strokeStyle = s.color || COL[k % COL.length]; c.lineWidth = 2; c.setLineDash(s.dash ? [6, 4] : []);
      c.beginPath(); s.x.forEach((xv, i) => { const p = [X(xv), Y(s.y[i])]; i ? c.lineTo(...p) : c.moveTo(...p); }); c.stroke();
    });
    c.setLineDash([]);
    (o.points || []).forEach((p) => { c.fillStyle = "#b3261e"; c.beginPath(); c.arc(X(p.x), Y(p.y), 4, 0, 6.29); c.fill(); });
    if (o.cursor != null) { c.strokeStyle = ink; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(X(o.cursor), Tp); c.lineTo(X(o.cursor), H - B); c.stroke(); c.setLineDash([]); }
    // 범례
    let lx = L + 6;
    [...series.filter((s) => s.name), ...(o.points || []).length ? [{ name: o.pointsName || "문헌값", color: "#b3261e" }] : []].forEach((s, k) => {
      c.fillStyle = s.color || COL[k % COL.length]; c.fillRect(lx, 8, 14, 3);
      c.fillStyle = ink; c.textAlign = "left"; c.fillText(s.name, lx + 18, 13); lx += c.measureText(s.name).width + 34;
    });
  }
  const canvas = (id, h = 260) => `<canvas id="${id}" style="width:100%;height:${h}px;display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px"></canvas>`;
  const player = (id, max) => `<div class="row"><button class="ghost" id="${id}Play" type="button">▶ 재생</button>
    <input id="${id}Range" type="range" min="0" max="${max}" value="0" style="flex:1"><b id="${id}Label"></b></div>`;
  function animate(id, n, draw) { // 재생 단추 + 슬라이더. 돌려주는 함수 = 지금 위치로 다시 그리기
    const range = document.getElementById(id + "Range"), btn = document.getElementById(id + "Play");
    let timer = null;
    const set = (k) => { range.value = k; draw(+k); };
    range.oninput = () => set(range.value);
    btn.onclick = () => {
      if (timer) { clearInterval(timer); timer = null; btn.textContent = "▶ 재생"; return; }
      if (+range.value >= n - 1) set(0);
      btn.textContent = "❚❚ 정지";
      timer = setInterval(() => { const k = +range.value + 1; if (k >= n) { clearInterval(timer); timer = null; btn.textContent = "▶ 재생"; } else set(k); }, 180);
    };
    set(0);
    return () => draw(+range.value);
  }
  const parts = [];

  // ---------- 1. 동결 · 해동 — FEniCSx + ParaView ----------
  if (T.fem) {
    const cases = T.fem.cases;
    const rows = cases.map((c) => `<tr><td>${esc(c.name)}</td><td class="n">${c.t_all_h ? f(c.t_all_h) + " h" : "-"}</td>
      <td class="n">${c.bottom_up_fraction != null ? f(100 * c.bottom_up_fraction, 0) + " %" : "-"}</td>
      <td class="n">${c.side_lead_mid != null ? (c.side_lead_mid >= 0 ? "+" : "") + f(100 * c.side_lead_mid, 0) + " %" : "-"}</td></tr>`).join("");
    parts.push(`<h2>① 방향성 동결 · 해동 — FEniCSx 계산 · ParaView 그림</h2>
      <p class="sub">병 · 겔 · 단열재를 축대칭 열전달 + 상변화로 풀었습니다 (${esc(T.fem.tool)}, 어는점 ${f(T.fem.melt_c, 2)} °C 는 PHREEQC).
        ${T.frames ? "파랑 = 얼음, 흰색 = 아직 물, 회색 = 병 · 단열재, 빨간 선 = 얼음 전선. 왼쪽 새 레시피 · 오른쪽 저가 방법." : "애니메이션은 <code>./tools.sh fem-movie</code> 뒤 다시 빌드하면 나옵니다. 아래는 얼린 시각 지도입니다."}</p>
      ${T.frames ? `<img id="femImg" style="width:100%;max-width:1100px;border-radius:10px;border:1px solid var(--line)" alt="ParaView 동결 애니메이션">${player("fem", T.frames.times_h.length - 1)}`
                 : `<div class="cards" id="femMaps"></div>`}
      <table><tr><th>조건</th><th>전부 얼거나 녹는 시간</th><th>아래→위로 언 비율</th><th>벽이 가운데보다 먼저 언 정도</th></tr>${rows}</table>`);
  }
  // ---------- 2. 배터리 — PyBaMM ----------
  if (T.pybamm) {
    const v = T.pybamm.validation, rows = v.reference.map((a, k) => {
      const b = v.pybamm_lumped[k], c = v.pybamm_full[k];
      return `<tr><td>${a.cycle === 0 ? "첫 방전 (태어난 상태)" : a.cycle + "사이클"}</td><td class="n">${f(a.discharge_mah, 4)}</td>
        <td class="n">${f(b.discharge_mah, 4)}</td><td class="n">${f(c.discharge_mah, 4)}</td></tr>`;
    }).join("");
    const pv = T.pybamm.view;
    parts.push(`<h2>② 배터리 충방전 — PyBaMM</h2>
      <p class="sub">인공세포 스택 (${v.n_pairs}쌍, ${v.current_ma} mA, ${f(v.v_min, 2)}–${f(v.v_max, 2)} V). 같은 가정으로 풀면 기존 모델과 맞고,
        세포 두께 방향 확산 + PHREEQC 활동도를 넣으면 개방전압 ${f(v.ocv0.reference, 2)} → ${f(v.ocv0.full, 2)} V.</p>
      <table><tr><th>방전 용량 mAh</th><th>기존 모델</th><th>PyBaMM 같은 가정</th><th>PyBaMM 확산 + 활동도</th></tr>${rows}</table>
      ${pv ? `<div class="cards" style="grid-template-columns:1fr 1fr">
        <div>${canvas("pbV")}<p class="sub">전압 · 개방전압 (${esc(pv.tool)})</p></div>
        <div>${canvas("pbC")}<p class="sub">세포 안 농도: 막(왼쪽 0 µm) → 세포 가운데 (묽은 세포 A)</p></div></div>
        ${player("pb", pv.profile_t_h.length - 1)}` : ""}`);
  }
  // ---------- 3. 용액 화학 — PHREEQC ----------
  if (T.phreeqc) {
    const r = T.phreeqc.report;
    parts.push(`<h2>③ 용액 화학 — PHREEQC (USGS) · pitzer.dat</h2>
      <div class="cards">
        <div class="card"><div class="k">생리식염수 어는점</div><div class="v">${f(r.saline_freezing_c, 2)} °C</div></div>
        <div class="card"><div class="k">공정점 소금물 (문헌 5.2)</div><div class="v">${f(r.eutectic_m, 2)} mol/kg</div></div>
        <div class="card"><div class="k">막 하나의 확산 전위</div><div class="v">${f(r.wall_mv_ideal)} → ${f(r.wall_mv_activity)} mV (활동도)</div></div>
        <div class="card"><div class="k">막 사이 소금물 ${f(r.c_brine_m, 2)} mol/kg</div><div class="v">γ± ${f(r.gamma_brine, 3)} · 어는점 ${f(r.brine_freezing_c)} °C</div></div>
      </div>
      <div class="cards" style="grid-template-columns:1fr 1fr"><div>${canvas("phG")}</div><div>${canvas("phT")}</div></div>`);
  }
  // ---------- 4. 공정 기록 — eLabFTW ----------
  parts.push(`<h2>④ 공정 · 시료 · 측정 기록 — eLabFTW</h2>
    <p class="sub">공정 19단계가 실험 템플릿으로 들어가 있습니다. 서버 켜기: <code>./tools.sh elab-up</code> → 아래 주소를 통합 브라우저에서 엽니다.
      로그인 ID <code>admin@snss.local</code>, 비밀번호는 <code>elab/.env</code> 의 ELAB_ADMIN_PASSWORD.</p>
    <div class="row"><a class="ghost" style="text-decoration:none;padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--ink)"
      href="${esc(T.elab_url)}" target="_blank" rel="noopener">${esc(T.elab_url)} 열기</a></div>`);
  body.innerHTML = parts.join("");

  // ---------- 그리기 ----------
  let redrawPb = null;
  function drawAll() {
    if (T.fem && T.frames) {
      const img = document.getElementById("femImg"), fr = T.frames;
      if (!img.dataset.bound) {
        img.dataset.bound = 1;
        fr.times_h.forEach((_, k) => { const im = new Image(); im.src = `frames/${fr.pattern.replace("{:03d}", String(k).padStart(3, "0"))}`; }); // 미리 받기
        animate("fem", fr.times_h.length, (k) => {
          img.src = `frames/${fr.pattern.replace("{:03d}", String(k).padStart(3, "0"))}`;
          document.getElementById("femLabel").textContent = `경과 ${f(fr.times_h[k])} h`;
        });
      }
    } else if (T.fem) { // 프레임이 없으면: 얼린 시각 지도 (새 레시피 · 저가)
      const box = document.getElementById("femMaps");
      if (box && !box.dataset.bound) {
        box.dataset.bound = 1;
        T.fem.cases.filter((c) => c.grid && c.side_lead_mid != null).forEach((c) => {
          const d = document.createElement("div"); d.className = "card";
          d.innerHTML = `<div class="k">${esc(c.name)}</div><canvas style="width:100%;height:220px"></canvas><div class="k">색 = 그 자리가 언 시각 (밝을수록 늦게)</div>`;
          box.appendChild(d);
          const cv = d.querySelector("canvas"), g = c.grid.t_h, nz = g.length, nr = g[0].length, max = c.t_all_h || 1;
          const dpr = window.devicePixelRatio || 1; cv.width = cv.clientWidth * dpr; cv.height = 220 * dpr;
          const cc = cv.getContext("2d"), w = cv.width / (2 * nr), h = cv.height / nz;
          g.forEach((row, j) => row.forEach((v, i) => {
            const u = v == null ? 1 : v / max;
            cc.fillStyle = `rgb(${Math.round(30 + 200 * u)},${Math.round(80 + 150 * u)},${Math.round(200 + 40 * u)})`;
            const y = cv.height - (j + 1) * h; cc.fillRect(cv.width / 2 + i * w, y, w + 1, h + 1); cc.fillRect(cv.width / 2 - (i + 1) * w, y, w + 1, h + 1);
          }));
        });
      }
    }
    if (T.pybamm && T.pybamm.view) {
      const pv = T.pybamm.view, cvs = [document.getElementById("pbV"), document.getElementById("pbC")];
      if (redrawPb) redrawPb();
      else {
        const allA = pv.cA.flat(), lo = Math.min(...allA), hi = Math.max(...allA);
        redrawPb = animate("pb", pv.profile_t_h.length, (k) => {
          const th = pv.profile_t_h[k];
          chart(cvs[0], [{ x: pv.t_h, y: pv.V, name: "단자 전압" }, { x: pv.t_h, y: pv.OCV, name: "개방전압", dash: true }],
                { xlabel: "시간 h", ylabel: "V", cursor: th });
          chart(cvs[1], [{ x: pv.x_um, y: pv.cA[k], name: `묽은 세포 A · ${f(th, 2)} h` },
                         { x: [pv.x_um[0], pv.x_um[pv.x_um.length - 1]], y: [lo, hi], name: "", color: "transparent" }],
                { xlabel: "막에서 거리 µm", ylabel: "mol/m³" });
          const ph = pv.phase_end_h.findIndex((e) => th <= e + 1e-6), name = { discharge: "방전", charge: "충전" }[pv.phases[ph]] || "";
          document.getElementById("pbLabel").textContent = `${f(th, 2)} h · ${name}`;
        });
      }
    }
    if (T.phreeqc) {
      const p = T.phreeqc, cvs = [document.getElementById("phG"), document.getElementById("phT")];
      chart(cvs[0], [{ x: p.m, y: p.gamma25, name: "γ± 25 °C" }, { x: p.m, y: p.gamma0, name: "γ± 0 °C", dash: true }],
            { xlabel: "NaCl mol/kg (로그)", ylabel: "평균 활동도계수 γ±", logx: true,
              points: [{ x: 0.1, y: 0.778 }, { x: 1, y: 0.657 }, { x: 3, y: 0.714 }], pointsName: "Robinson & Stokes" });
      chart(cvs[1], [{ x: p.m, y: p.tf, name: "얼음과 평형인 온도" }], { xlabel: "NaCl mol/kg", ylabel: "°C" });
    }
  }
  // 탭이 보일 때 · 크기가 바뀔 때 그림 (숨은 캔버스는 크기가 0)
  const sec = body.closest("section");
  new ResizeObserver(() => { if (sec.offsetParent) drawAll(); }).observe(sec);
})();
