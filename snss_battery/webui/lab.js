// 실험대 — RECIPE.md 의 제조 절차를 가상 화학 실험실에서 단계별로 보여 준다.
// 시약 선반 · 핫플레이트 · 전자저울 · 비커 4개 · 냉동실(금속판 + 병 틀) · 측정대(흑연 막대 · 멀티미터 · LED).
(function lab() {
  const DATA = window.DATA;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const cv = $("#labC");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const BOT = DATA.bottle;
  const W = 1200, H = 560, K = 1.3; // 장면 크기, 병·결정 축척 [px/mm]
  const FONT = '"NanumGothic", "Noto Sans KR", sans-serif';

  // ---------- 시료 ----------
  const byKey = Object.fromEntries((DATA.samples || []).map((s) => [s.key, s]));
  const concept = byKey.concept || {};
  const r0 = { key: "r0", name: "레시피 0 — 한 번에 붓기 (반증 실험)", r0: true, pairs: 0, layer_mm: 0, ocv: 0, led_ma: 0, led: "꺼짐", led_level: 0,
               fill_ml: BOT.volume, note: "원래 구상 그대로 섞어 통째로 얼림 — 층이 저절로 번갈아 생긴다는 근거가 없어 약 0 V 예상" };
  const tis = byKey.tissue;
  if (tis) { // 레시피 3 양 (web.py amounts) → 쓰기 쉬운 이름
    const g = Object.fromEntries(tis.amounts.map(([k, items]) => [k, Object.fromEntries(items.map(([n, v]) => [n, v]))]));
    const v = Object.values(g);
    tis.tq = { take: v[0]["덜어 낸 생리식염수"], pva: v[0]["PVA 가루"], pvaWt: v[0]["농도"], go: v[1]["GO 분산액 4 mg/mL"],
               extra: v[2]["더 빼낼 식염수 (넘침 방지)"] };
  }
  const SAMPLES = [tis].filter(Boolean); // 층 쌓기 시료는 뺐음
  let S = SAMPLES[0];

  // ---------- 절차 ----------
  const f1 = (v) => (v ?? 0).toFixed(1), f2 = (v) => (v ?? 0).toFixed(2);
  const nb = (rows) => `<table>${rows.map(([a, b]) => `<tr><td>${a}</td><td><b>${b}</b></td></tr>`).join("")}</table>`;
  function steps(s) {
    const q = s.q || {};
    if (s.tissue) {
      // 공정은 snss_battery/process.py (RECIPE.md 3절과 같음) — 단계마다 수작업 / 기계작업
      const F = s.freezing;
      const extra = {
        dfreeze: [["얼음 전선 속도", `${F.v_mid_um_s.toFixed(1)} → ${F.v_top_um_s.toFixed(1)} µm/s`], ["세포 폭 (추정)", `${F.cell_mid_um.toFixed(0)}–${F.cell_top_um.toFixed(0)} µm`],
                  ["소금", `얼음에 ${(100 * s.k_eff).toFixed(1)} % 만 → 나머지는 막 사이로`]],
        thaw: [["해동 뒤", "얼음 → 묽은 내강 (비어 있는 세포)"], ["막 사이", `진한 소금물 ${s.c_brine_m.toFixed(2)} M`]],
        ft: [["위험", "부피 팽창 9 % 로 막 손상 가능 — S4 확인"]],
        demold: [["절단선 A", `바닥에서 ${f1(s.cut_z)} mm`]],
        meas: [["모델 예측", `${(1000 * s.ocv).toFixed(1)} mV (사실상 0)`], ["이유", "층·극성 없음 → 막전위 상쇄"], ["판정", "E2: |V| < 50 mV"]],
        cond: [["내강", `${s.c_lumen_mM.toFixed(1)} mM`], ["막 사이", `${s.c_brine_m.toFixed(2)} M`], ["저장 에너지", `${s.energy_j.toFixed(0)} J (잠겨 있음)`], ["판정", "E1: 벽/칸 Cl 신호 10배 이상"]],
      };
      return s.process.map((p) => ({
        id: p.id, t: p.title, d: p.action, h: p.hours, mode: p.mode, modeKo: p.mode_ko, hands: p.hands_min,
        sec: Math.round(3 + 2.2 * Math.log2(1 + p.hours)) + (p.id === "dfreeze" ? 4 : 0),
        n: () => nb([["구분", `<span class="mode ${p.mode}">${esc(p.mode_ko)}</span>`], ["손 작업", `${p.hands_min.toFixed(0)} 분`],
                     ["걸리는 시간", p.hours >= 1 ? `${p.hours.toFixed(1)} h` : `${Math.round(p.hours * 60)} 분`], ["장비", esc(p.equipment.join(" · "))],
                     ["할 일", esc(p.action)], ["넘어가는 조건", esc(p.check)], ...(extra[p.id] || [])]),
      }));
    }
    if (s.r0) {
      const pva = s.fill_ml * 0.05, go = s.fill_ml * 0.5 / 4;
      return [
        { id: "weigh", t: "계량", d: "PVA 가루를 전자저울로 잰다", h: 0.2, sec: 3, n: () => nb([["PVA 가루 (5 wt%)", `${f1(pva)} g`]]) },
        { id: "stock", t: "PVA 녹이기", d: "증류수 90 °C 중탕, 투명해질 때까지", h: 1.5, sec: 5, n: () => nb([["온도", "90 °C"], ["시간", "1–2 h"]]) },
        { id: "mix", t: "한 통에 섞기", d: "생리식염수 + PVA + GO 분산액", h: 0.3, sec: 4, n: () => nb([["생리식염수", `${f1(s.fill_ml * 0.85)} mL`], ["GO 분산액 4 mg/mL", `${f1(go)} mL`], ["PVA 용액", "나머지"]]) },
        { id: "pour1", t: "병에 통째로 붓기", d: "식염수병 그대로, 냉동실 금속판 위", h: 0.2, sec: 4, n: () => nb([["붓는 양", `${f1(s.fill_ml)} mL`], ["층", "없음 (섞임)"]]) },
        { id: "ft", t: "동결-해동 3회", d: "동결 12 h (−20 °C) / 해동 2 h (4 °C)", h: 42, sec: 8, n: () => nb([["동결", "12 h · −20 °C"], ["해동", "2 h · 4 °C"], ["반복", "3회"]]) },
        { id: "demold", t: "병 절단 · 꺼내기", d: "절단 가이드 띠로 자르고 결정을 꺼냄", h: 0.3, sec: 4, n: () => nb([["절단선 A", `바닥에서 ${f1(concept.cut_z)} mm`], ["측정", "10분 안에"]]) },
        { id: "meas", t: "흑연 막대로 측정", d: "윗면 (+) · 아랫면 (−), 10 MΩ 멀티미터", h: 0.1, sec: 5, n: () => nb([["예상", "약 0 V (농도차 없음)"], ["자발 정렬 가정 시", `${f2(concept.ocv)} V`], ["판정", "H1 반증 실험"]]) },
        { id: "led", t: "LED 연결", d: "빨강 LED + 470 Ω 직렬", h: 0.1, sec: 4, n: () => nb([["예상", "꺼짐"]]) },
      ];
    }
    return [
      { id: "weigh", t: "계량", d: "PVA 가루 · 소금을 전자저울로 잰다", h: 0.2, sec: 3, n: () => nb([["PVA 가루", `${f2(q.buy_pva_g)} g`], ["추가 소금 NaCl", `${f2(q.extra_nacl_g)} g`]]) },
      { id: "stock", t: "PVA 원액 만들기", d: "증류수 90 °C 중탕 → 식힌 뒤 GO 분산액", h: 1.5, sec: 6,
        n: () => nb([["증류수", `${f1(q.water_stock_ml)} mL`], ["PVA 가루", `${f2(q.pva_g)} g`], ["GO 분산액 4 mg/mL", `${f1(q.go_stock_ml)} mL`], ["→ 원액", `${f1(q.stock_ml)} mL (10 wt%)`]]) },
      { id: "prep", t: "4가지 액 조제", d: "A액 · B액 · CEM 벽액 · AEM 벽액", h: 0.5, sec: 6,
        n: () => nb([["A액", `원액 ${f1(q.half_ml)} + 식염수 ${f1(q.saline_a_ml)} + 물 ${f1(q.water_a_ml)} mL`], ["B액", `원액 ${f1(q.half_ml)} + 식염수 ${f1(q.half_ml)} mL + NaCl ${f2(q.extra_nacl_g)} g`],
                     ["CEM 벽액", `GO ${f2(q.cem_go_ml)} + 원액 ${f2(q.cem_pva_ml)} mL`], ["AEM 벽액", `GO ${f2(q.aem_go_ml)} + PDDA ${f2(q.pdda_ml)} + 물 ${f2(q.aem_water_ml)} mL`]]) },
      { id: "mold", t: "틀 준비", d: "병 어깨 아래를 잘라 틀, 붓기 가이드 띠, 차가운 금속판", h: 0.3, sec: 4,
        n: () => nb([["틀", "약국 식염수병 (PE)"], ["붓기 가이드", `<a href="cad/pour_guide_${esc(s.key)}.pdf" target="_blank">PDF</a> 1:1 인쇄`], ["금속판", "도구 (결정에 안 들어감)"]]) },
      { id: "layers", t: `층 쌓기 × ${s.pairs}쌍`, d: "A → CEM 벽 → B → AEM 벽, 붓고 얼리기 반복", h: s.steps * 0.5, sec: 16,
        n: () => nb([["층 하나 (A·B)", `${f1(s.layer_ml)} mL · ${s.layer_mm} mm`], ["벽 한 장", `${f2(s.wall_one_ml)} mL 붓으로 얇게`], ["붓기 · 얼리기", `${s.steps}회 (한 번 약 30분)`], ["목표 높이", `${f1(s.height_mm)} mm`]]) },
      { id: "ft", t: "동결-해동 3회 (결정화)", d: "동결 12 h (−20 °C) / 냉장 해동 2 h", h: 42, sec: 8,
        n: () => nb([["동결", "12 h · −20 °C"], ["해동", "2 h · 4 °C"], ["반복", "3회 — 겔이 불투명·탄탄해짐"]]) },
      { id: "demold", t: "틀 벗기기 · 다듬기", d: "병 껍질을 벗기고 윗면·아랫면 정리", h: 0.3, sec: 4, n: () => nb([["다듬기", "윗면·아랫면 1 mm"], ["측정", "10분 안에 (마르기 전)"]]) },
      { id: "meas", t: "흑연 막대로 측정", d: "윗면 (+) · 아랫면 (−), 10 MΩ 멀티미터", h: 0.1, sec: 5,
        n: () => nb([["모델 예측", `${f2(s.ocv)} V`], ["내부저항", `${(s.r_ohm || 0).toFixed(0)} Ω`], ["대조군", "A·B·C 함께 측정"], ["판정", "H1 ≥ 0.3 V · 대조군의 10배"]]) },
      { id: "led", t: "LED 연결", d: "빨강 LED + 470 Ω 직렬", h: 0.1, sec: 5, n: () => nb([["예측 전류", `${f2(s.led_ma)} mA`], ["상태", esc(s.led)], ["판정", "H5"]]) },
    ];
  }
  let STEPS = steps(S), T0 = [], TOTAL = 0, HOURS = [];
  function index() {
    T0 = []; HOURS = []; TOTAL = 0;
    let h = 0;
    for (const st of STEPS) { T0.push(TOTAL); HOURS.push(h); TOTAL += st.sec; h += st.h; }
    HOURS.push(h);
  }
  index();

  // ---------- 그리기 도구 ----------
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = (v) => v * v * (3 - 2 * v);
  const lerp = (a, b, u) => a + (b - a) * u;
  function rr(x, y, w, h, r, fill, stroke, lw = 1) {
    ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2)));
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
  }
  function text(s, x, y, size = 12, color = "#33404d", align = "center", weight = "") {
    ctx.font = `${weight} ${size}px ${FONT}`; ctx.fillStyle = color; ctx.textAlign = align; ctx.fillText(s, x, y);
  }
  function lcd(x, y, w, h, s, color = "#9cf0c5", size = 18) {
    rr(x, y, w, h, 4, "#10181a", "#000");
    ctx.font = `600 ${size}px ui-monospace, "NanumGothicCoding", monospace`; ctx.fillStyle = color; ctx.textAlign = "right";
    ctx.fillText(s, x + w - 6, y + h / 2 + size * 0.36);
  }
  function beaker(x, y, w, h, level, color, label, sub) {
    // 유리 비커: level 0~1
    const lv = clamp(level) * (h - 10);
    if (lv > 0) {
      const g = ctx.createLinearGradient(x, 0, x + w, 0);
      g.addColorStop(0, color); g.addColorStop(0.5, shade(color, 1.18)); g.addColorStop(1, color);
      ctx.fillStyle = g; ctx.fillRect(x + 3, y + h - 3 - lv, w - 6, lv);
      ctx.fillStyle = "#ffffff55"; ctx.fillRect(x + 3, y + h - 3 - lv, w - 6, 2);
    }
    ctx.strokeStyle = "#7f93a6"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x - 4, y); ctx.lineTo(x, y + 4); ctx.lineTo(x, y + h - 4); ctx.quadraticCurveTo(x, y + h, x + 4, y + h);
    ctx.lineTo(x + w - 4, y + h); ctx.quadraticCurveTo(x + w, y + h, x + w, y + h - 4); ctx.lineTo(x + w, y); ctx.stroke();
    ctx.strokeStyle = "#7f93a680"; ctx.lineWidth = 1;
    for (let k = 1; k <= 3; k++) { const yy = y + h - (h - 10) * k / 4; ctx.beginPath(); ctx.moveTo(x + 4, yy); ctx.lineTo(x + 12, yy); ctx.stroke(); }
    ctx.fillStyle = "#ffffff40"; ctx.fillRect(x + w - 10, y + 8, 3, h - 18);
    if (label) text(label, x + w / 2, y + h + 18, 12, "#eef3f8", "center", "600");
    if (sub) text(sub, x + w / 2, y + h + 32, 10, "#aebccb");
  }
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(clamp(v * f, 0, 255)));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  function reagent(x, y, w, h, body, cap, label, kind) {
    if (kind === "jar") { rr(x, y + 10, w, h - 10, 6, body, "#0002"); rr(x - 2, y, w + 4, 14, 3, cap); }
    else {
      rr(x, y + h * 0.3, w, h * 0.7, 6, body, "#0002");
      ctx.fillStyle = body; ctx.beginPath(); ctx.moveTo(x + 4, y + h * 0.3 + 2); ctx.lineTo(x + w * 0.32, y + 12); ctx.lineTo(x + w * 0.68, y + 12); ctx.lineTo(x + w - 4, y + h * 0.3 + 2); ctx.fill();
      rr(x + w * 0.3, y, w * 0.4, 14, 3, cap);
    }
    rr(x + 5, y + h * 0.48, w - 10, h * 0.3, 3, "#fffffff0");
    ctx.save(); ctx.beginPath(); ctx.rect(x + 5, y + h * 0.48, w - 10, h * 0.3); ctx.clip();
    text(label, x + w / 2, y + h * 0.48 + h * 0.18, 10, "#263241", "center", "600"); ctx.restore();
  }

  // ---------- 상태 계산 ----------
  let t = 0, playing = false, last = 0;
  function where(tt) {
    let i = 0;
    while (i < STEPS.length - 1 && tt >= T0[i + 1]) i++;
    return { i, u: clamp((tt - T0[i]) / STEPS[i].sec) };
  }
  const prog = (id) => {
    const k = STEPS.findIndex((x) => x.id === id);
    if (k < 0) return -1;
    const { i, u } = where(t);
    return i > k ? 1 : i < k ? 0 : u;
  };
  function hoursNow() { const { i, u } = where(t); return HOURS[i] + u * STEPS[i].h; }

  // 통째 결정: 병이 있는 곳 (bench 실험대 · plate 냉각판 · bath 항온수조) 과 얼음 상태
  function tisState() {
    const fz = S.freezing.hours, th = (STEPS.find((x) => x.id === "thaw") || { h: 2 }).h, share = fz / (fz + th);
    const ft = prog("ft"), N = S.freeze_thaw - 1;
    if (prog("demold") > 0 || ft >= 1) return { at: "bench", ice: 0, gel: true, bath: false };
    if (ft > 0) {
      const c = (ft * N) % 1, n = Math.min(N, Math.floor(ft * N) + 1);
      return c < share ? { at: "plate", ice: Math.sqrt(c / share), gel: true, cycle: n, phase: "동결" }
                       : { at: "bench", ice: 1 - (c - share) / (1 - share), gel: true, bath: true, cycle: n, phase: "해동" };
    }
    const tw = prog("thaw");
    if (tw > 0) return { at: "bench", ice: 1 - tw, gel: true, bath: true };
    const df = prog("dfreeze");
    if (df > 0) return { at: "plate", ice: Math.sqrt(df), gel: false };
    const su = prog("setup");
    return { at: su > 0.4 ? "plate" : "bench", move: clamp((su - 0.15) / 0.3), ice: 0, gel: false };
  }
  function freezerTemp() {
    if (S.tissue) { // 저온실 안 냉각판: 냉각기를 켠 뒤 약 45분에 판 온도 도달
      const k = STEPS.findIndex((x) => x.id === "chill");
      if (prog("chill") <= 0) return 4;
      return lerp(4, S.plate_c, clamp((hoursNow() - HOURS[k]) / 0.75));
    }
    const L = prog("layers"), F = prog("ft"), P1 = prog("pour1"), M = prog("mold");
    if (F > 0 && F < 1) { const n = S.tissue ? S.freeze_thaw - 1 : 3, c = (F * n) % 1; return c < 2 / 14 ? 4 : -20; }
    if (L > 0 || P1 > 0 || M > 0.5) return -20;
    return -20;
  }
  function hotTemp() {
    if (S.tissue) {
      const P = prog("stock"), C = prog("cool");
      if (C > 0) return C >= 1 ? 22 : lerp(90, 38, C);
      if (P <= 0) return 22;
      return P < 0.2 ? lerp(22, 90, P / 0.2) : 90;
    }
    const P = prog("stock");
    if (P <= 0) return 22;
    if (P < 0.25) return lerp(22, 90, P / 0.25);
    if (P < 0.7) return 90;
    if (P < 1) return lerp(90, 38, (P - 0.7) / 0.3);
    return 22;
  }

  // ---------- 장면 ----------
  const COL = { A: "#bfe0f2", B: "#4f8fc9", CEM: "#4a3426", AEM: "#6e5c2c", stock: "#e9e4d4", stockGO: "#8b7b68", mix: "#7d7466" };
  function background() {
    const g = ctx.createLinearGradient(0, 0, 0, 430);
    g.addColorStop(0, "#f3f6f9"); g.addColorStop(1, "#dfe6ec");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, 430);
    ctx.strokeStyle = "#cfd8e033"; ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 430); ctx.stroke(); }
    for (let y = 0; y < 430; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    // 선반
    rr(30, 128, 580, 10, 2, "#9a7b5a"); ctx.fillStyle = "#7d6146"; ctx.fillRect(60, 138, 6, 20); ctx.fillRect(570, 138, 6, 20);
    // 실험대
    const b = ctx.createLinearGradient(0, 430, 0, 470);
    b.addColorStop(0, "#3a4350"); b.addColorStop(1, "#2a313b");
    ctx.fillStyle = b; ctx.fillRect(0, 430, W, 40);
    ctx.fillStyle = "#525d6b"; ctx.fillRect(0, 430, W, 3);
    ctx.fillStyle = "#c9d0d8"; ctx.fillRect(0, 470, W, H - 470);
    ctx.strokeStyle = "#aab4bf"; ctx.lineWidth = 2;
    for (let x = 20; x < W; x += 236) rr(x, 484, 220, 90, 6, "#d5dbe2", "#aab4bf", 1.5);
    for (let x = 20; x < W; x += 236) rr(x + 95, 496, 30, 6, 3, "#8994a1");
  }
  function shelf() {
    const q = S.q || {};
    reagent(50, 40, 58, 86, "#eef5fb", "#3b7dd8", "식염수", "bottle");
    reagent(124, 50, 50, 76, "#3c2a1f", "#222", "GO", "bottle");
    reagent(190, 66, 56, 60, "#f7f5ee", "#c94f3d", "PVA", "jar");
    if (!S.tissue) reagent(262, 70, 52, 56, "#f4f4f4", "#3d7a4c", "NaCl", "jar");
    if (!S.r0 && !S.tissue) reagent(330, 56, 50, 70, "#efe6c8", "#6b4ba0", "PDDA", "bottle");
    reagent(396, 46, 52, 80, "#e8f1f8", "#888", "증류수", "bottle");
    text("시약 선반", 470, 88, 12, "#4a5866", "left", "700");
    text("약국 생리식염수 · GO 4 mg/mL", 470, 104, 10.5, "#6f7b88", "left");
    text(S.r0 ? "금속·생물 재료 없음" : (S.tissue ? "PVA · GO · 식염수만 · 금속 없음" : `PDDA 20 % ${f2(q.pdda_ml)} mL · 금속 없음`), 470, 119, 10.5, "#6f7b88", "left");
  }
  function hotplate() {
    const T = hotTemp(), on = T > 30;
    rr(40, 392, 150, 38, 6, "#e4e8ec", "#9aa6b2");
    rr(52, 386, 126, 10, 3, on ? `rgb(${Math.round(lerp(150, 230, (T - 30) / 60))},90,60)` : "#8a96a3");
    lcd(60, 402, 62, 20, `${T.toFixed(0)}°C`, on ? "#ffb26b" : "#9cf0c5", 13);
    ctx.fillStyle = "#566270"; ctx.beginPath(); ctx.arc(160, 412, 8, 0, 6.29); ctx.fill();
    // 원액 비커
    const P = prog("stock"), D = prog("prep");
    const level = S.tissue ? clamp(prog("take") * 2) * (1 - clamp(prog("mix") * 2.5)) * (1 - 0.04 * prog("pretest"))
      : S.r0 ? clamp(P * 1.2) * (1 - prog("mix")) : clamp(P * 1.2) * (1 - 0.92 * D);
    const goMix = clamp((P - 0.75) / 0.25);
    const c = goMix > 0 ? COL.stockGO : COL.stock;
    beaker(70, 290, 92, 96, level * 0.85, c, "", "");
    text("PVA 원액", 116, 270, 12, "#263241", "center", "700");
    text(S.tissue ? `덜어 낸 식염수 + PVA ${f1(S.tq.pvaWt)} %` : S.r0 ? "5 wt%" : "10 wt% + GO 1 mg/mL", 116, 284, 10, "#5d6673");
    if (on && P < 1) for (let k = 0; k < 6; k++) { // 김
      const ph = (performance.now() / 900 + k / 6) % 1;
      ctx.strokeStyle = `rgba(255,255,255,${0.6 * (1 - ph)})`; ctx.lineWidth = 3;
      ctx.beginPath(); const x0 = 90 + k * 11; ctx.moveTo(x0, 285 - ph * 40); ctx.quadraticCurveTo(x0 + 6, 275 - ph * 40, x0, 265 - ph * 40); ctx.stroke();
    }
    // 온도계
    ctx.strokeStyle = "#555"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(150, 250); ctx.lineTo(140, 360); ctx.stroke();
    ctx.fillStyle = "#c0392b"; ctx.beginPath(); ctx.arc(140, 362, 4, 0, 6.29); ctx.fill();
    text("핫플레이트 · 중탕", 115, 462, 11, "#e6ebf0");
  }
  function balance() {
    const P = prog("weigh"), q = S.q || {};
    const target = S.tissue ? S.tq.pva : S.r0 ? S.fill_ml * 0.05 : q.buy_pva_g || 0;
    rr(214, 404, 112, 26, 5, "#dfe4ea", "#9aa6b2");
    rr(222, 392, 96, 10, 3, "#b9c3cd");
    lcd(230, 410, 60, 16, `${(target * ease(clamp(P * 1.3))).toFixed(2)}g`, "#9cf0c5", 11);
    if (P > 0 && P < 1) { rr(246, 368, 48, 24, 4, "#f7f5ee", "#bbb"); ctx.fillStyle = "#fffaf0"; ctx.beginPath(); ctx.ellipse(270, 372, 18, 5, 0, 0, 6.29); ctx.fill(); }
    text("전자저울", 270, 462, 11, "#e6ebf0");
  }
  function beakers() {
    const D = prog("prep"), L = prog("layers");
    const x0 = 352, gap = 66;
    if (S.tissue) { // GO 분산액 · 예비 시험 바이알 · 1 L 섞는 비커
      const pt = prog("pretest"), m = prog("mix"), dg = prog("degas"), rf = prog("refill");
      beaker(x0, 360, 40, 66, 0.8 * (1 - 0.04 * clamp(pt * 3)) * (1 - clamp((m - 0.4) / 0.5)), COL.CEM, "GO", "4 mg/mL");
      if (pt > 0) {
        rr(x0 + 52, 384, 18, 42, 3, pt < 1 ? "#6e5c2c" : "#6e5c2cb0", "#7f93a6", 1.5);
        text("예비", x0 + 61, 444, 10, "#eef3f8", "center", "600");
        if (pt > 0.3 && pt < 1) text("30분 정치 · 응집?", x0 + 61, 376, 9.5, "#33404d");
      }
      const lv = m <= 0 ? 0 : (rf > 0 ? 1 - rf : 1) * lerp(0.55, 0.85, clamp((m - 0.1) / 0.8));
      beaker(x0 + 84, 330, 76, 96, lv, m < 0.15 ? "#dfeaf2" : COL.mix, "1 L 비커", dg > 0 && dg < 1 ? "진공 · 기포 빼기" : "섞기");
      if (dg > 0 && dg < 1) for (let k = 0; k < 8; k++) { // 기포
        const ph = (performance.now() / 700 + k / 8) % 1;
        ctx.fillStyle = `rgba(255,255,255,${0.7 * (1 - ph)})`; ctx.beginPath(); ctx.arc(x0 + 96 + k * 7, 420 - ph * 70 * lv, 2, 0, 6.29); ctx.fill();
      }
      if (m > 0 && m < 1) { ctx.strokeStyle = "#566270"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(x0 + 122, 418, 10 * Math.abs(Math.cos(performance.now() / 120)), 2.5, 0, 0, 6.29); ctx.stroke(); }
      return;
    }
    if (S.r0) {
      const m = prog("mix"), p1 = prog("pour1");
      beaker(x0 + 30, 330, 110, 96, clamp(m * 1.1) * (1 - p1) * 0.85, COL.mix, "혼합액", "식염수 + PVA + GO 한 통");

      return;
    }
    const used = (k) => (L <= 0 ? 0 : L >= 1 ? 1 : L); // 층 쌓기 동안 줄어듦
    const items = [["A액", COL.A, "묽은 층"], ["B액", COL.B, "진한 층"], ["CEM", COL.CEM, "GO 벽액"], ["AEM", COL.AEM, "GO+PDDA"]];
    items.forEach(([n, c, sub], k) => {
      const fill = clamp((D - k * 0.2) / 0.35);
      const small = k >= 2;
      const lv = fill * (1 - 0.88 * used(k)) * (small ? 0.55 : 0.85);
      beaker(x0 + k * gap, small ? 372 : 334, small ? 44 : 52, small ? 54 : 92, lv, c, n, sub);
    });
  }
  // 냉동실 · 틀 · 결정
  const FZ = { x: 640, y: 112, w: 250, h: 340 };
  function freezer() {
    const T = freezerTemp(), active = prog("mold") > 0.3 || (S.r0 && prog("pour1") > 0) || (S.tissue && prog("chill") > 0);
    rr(FZ.x, FZ.y, FZ.w, FZ.h, 10, "#f2f5f8", "#9fb0c2", 2);
    rr(FZ.x + 12, FZ.y + 34, FZ.w - 24, FZ.h - 50, 6, "#2d3d4f");
    const g = ctx.createLinearGradient(0, FZ.y + 34, 0, FZ.y + FZ.h - 16);
    g.addColorStop(0, "#3c5068"); g.addColorStop(1, "#22303f");
    rr(FZ.x + 14, FZ.y + 36, FZ.w - 28, FZ.h - 54, 5, g);
    lcd(FZ.x + FZ.w - 92, FZ.y + 7, 80, 22, `${T > 0 ? "+" : ""}${T.toFixed(0)}°C`, T < 0 ? "#8fd0ff" : "#ffc36b", 15);
    text(S.tissue ? "저온실 +4 °C · 냉각판" : "냉동실", FZ.x + 16, FZ.y + 24, 13, "#33404d", "left", "700");
    // 서리
    if (active && T < 0) {
      ctx.fillStyle = "#e9f6ff"; ctx.globalAlpha = 0.55;
      for (let k = 0; k < 40; k++) { const x = FZ.x + 16 + ((k * 53) % (FZ.w - 32)), y = FZ.y + 38 + ((k * 31) % 14); ctx.beginPath(); ctx.arc(x, y, 1.6 + (k % 3), 0, 6.29); ctx.fill(); }
      ctx.globalAlpha = 1;
    }
    // 열린 문
    ctx.fillStyle = "#e3e8ee"; ctx.beginPath(); ctx.moveTo(FZ.x + FZ.w, FZ.y + 6); ctx.lineTo(FZ.x + FZ.w + 34, FZ.y + 24);
    ctx.lineTo(FZ.x + FZ.w + 34, FZ.y + FZ.h - 10); ctx.lineTo(FZ.x + FZ.w, FZ.y + FZ.h - 2); ctx.fill();
    ctx.strokeStyle = "#9fb0c2"; ctx.lineWidth = 1.5; ctx.stroke();
    // 금속판 (도구)
    const plate = FZ.y + FZ.h - 30;
    const pg = ctx.createLinearGradient(0, plate, 0, plate + 12);
    pg.addColorStop(0, "#c7ced6"); pg.addColorStop(1, "#7e8994");
    ctx.fillStyle = pg; ctx.fillRect(FZ.x + 30, plate, FZ.w - 60, 12);
    text(S.tissue ? "냉각판 · 순환식 냉각기" : "차가운 금속판 (도구)", FZ.x + FZ.w / 2, plate + 26, 10, "#c9d6e3");
    return plate;
  }
  // 결정 블록을 그림: (cx, base) 아래 중심, 단면 층 표시
  function crystal(cx, base, h, opts = {}) {
    const r = (BOT.d / 2 - BOT.wall) * K, s = S;
    ctx.save();
    ctx.beginPath(); ctx.rect(cx - r, base - h, 2 * r, h); ctx.clip();
    if (s.r0) {
      ctx.fillStyle = COL.mix; ctx.fillRect(cx - r, base - h, 2 * r, h);
    } else {
      const t = s.layer_mm * K, pitch = (2 * s.layer_mm + s.cem_mm + s.aem_mm) * K;
      const n = opts.layers ?? 4 * s.pairs; // 쌓인 층 (A, CEM, B, AEM 순서)
      const off = [0, t, t + s.cem_mm * K, 2 * t + s.cem_mm * K];
      for (let k = 0; k < n; k++) {
        const kind = k % 4, y0 = base - Math.floor(k / 4) * pitch - off[kind];
        if (kind === 0 || kind === 2) { ctx.fillStyle = kind === 0 ? COL.A : COL.B; ctx.fillRect(cx - r, y0 - t, 2 * r, t); }
        else { ctx.fillStyle = kind === 1 ? COL.CEM : COL.AEM; ctx.fillRect(cx - r, y0 - 0.7, 2 * r, 1.4); }
      }
    }
    // 원통 음영
    const g = ctx.createLinearGradient(cx - r, 0, cx + r, 0);
    g.addColorStop(0, "#0000003a"); g.addColorStop(0.35, "#ffffff22"); g.addColorStop(0.7, "#00000008"); g.addColorStop(1, "#00000045");
    ctx.fillStyle = g; ctx.fillRect(cx - r, base - h, 2 * r, h);
    if (opts.opaque) { ctx.fillStyle = `rgba(245,247,250,${0.42 * opts.opaque})`; ctx.fillRect(cx - r, base - h, 2 * r, h); }
    if (opts.liquid) { ctx.fillStyle = "#ffffff30"; ctx.fillRect(cx - r, base - h, 2 * r, 3); }
    ctx.restore();
    ctx.strokeStyle = "#00000055"; ctx.lineWidth = 1; ctx.strokeRect(cx - r, base - h, 2 * r, h);
  }
  function mold(cx, base, full) {
    // 식염수병 (투명 PE) — 레시피: 어깨 아래를 자른 틀, 레시피 0: 병 전체
    const ro = (BOT.d / 2) * K, hb = BOT.body * K;
    ctx.save();
    ctx.strokeStyle = "#cfe3f2"; ctx.lineWidth = 2; ctx.fillStyle = "#cfe3f21c";
    ctx.beginPath(); ctx.moveTo(cx - ro, base - hb); ctx.lineTo(cx - ro, base - 4); ctx.quadraticCurveTo(cx - ro, base, cx - ro + 4, base);
    ctx.lineTo(cx + ro - 4, base); ctx.quadraticCurveTo(cx + ro, base, cx + ro, base - 4); ctx.lineTo(cx + ro, base - hb);
    if (full) {
      const rn = (BOT.neck_d / 2) * K, zs = base - hb, zn = zs - BOT.shoulder * K, zt = zn - BOT.neck_h * K;
      ctx.bezierCurveTo(cx + ro, zs - BOT.shoulder * K * 0.7, cx + rn + 8, zn + 4, cx + rn, zn); ctx.lineTo(cx + rn, zt);
      ctx.moveTo(cx - ro, base - hb); ctx.bezierCurveTo(cx - ro, zs - BOT.shoulder * K * 0.7, cx - rn - 8, zn + 4, cx - rn, zn); ctx.lineTo(cx - rn, zt);
    }
    ctx.fill(); ctx.stroke();
    // 붓기 가이드 띠 (레시피)
    if (!full) {
      ctx.strokeStyle = "#e07a1f"; ctx.lineWidth = 1;
      const tick = (2 * S.layer_mm + S.cem_mm + S.aem_mm) * K;
      for (let k = 0; k <= S.pairs; k += Math.max(1, Math.round(S.pairs / 12))) {
        const y = base - k * tick; ctx.beginPath(); ctx.moveTo(cx + ro + 2, y); ctx.lineTo(cx + ro + (k % 5 === 0 ? 12 : 7), y); ctx.stroke();
      }
      text("가이드 띠", cx + ro + 16, base - 4, 9.5, "#ffc36b", "left");
    }
    ctx.restore();
  }
  function pourer(x, y, color, ang, streamTo) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    rr(-18, -26, 36, 40, 4, "#ffffff30", "#9fb0c2", 1.5);
    ctx.fillStyle = color; ctx.fillRect(-15, -4, 30, 16);
    ctx.restore();
    if (streamTo) {
      ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.globalAlpha = 0.9;
      ctx.beginPath(); ctx.moveTo(x + 18, y - 6); ctx.quadraticCurveTo(x + 22, (y + streamTo) / 2, x + 20, streamTo); ctx.stroke(); ctx.globalAlpha = 1;
    }
  }
  // 측정대
  const ST = { x: 935, y: 430 };
  function stand(blockH, have) {
    rr(ST.x - 6, 412, 120, 18, 4, "#e9eef3", "#a8b4c0");
    rr(ST.x + 20, 398, 8, 14, 2, "#b9c6d3"); rr(ST.x + 80, 398, 8, 14, 2, "#b9c6d3");
    text("측정대", ST.x + 54, 462, 11, "#e6ebf0");
  }
  function meter(x, y, reading, mode, on) {
    rr(x, y, 120, 168, 12, "#f2c230", "#a5831c", 2);
    rr(x + 8, y + 8, 104, 152, 8, "#2b2f33");
    lcd(x + 16, y + 18, 88, 34, reading, on ? "#9cf0c5" : "#4b6b60", 19);
    text(mode, x + 60, y + 66, 10, "#c9d1d9");
    ctx.fillStyle = "#43494f"; ctx.beginPath(); ctx.arc(x + 60, y + 102, 22, 0, 6.29); ctx.fill();
    ctx.strokeStyle = "#f2c230"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(x + 60, y + 102);
    const a = mode.includes("mA") ? -0.4 : -1.9; ctx.lineTo(x + 60 + 18 * Math.cos(a), y + 102 + 18 * Math.sin(a)); ctx.stroke();
    for (const [jx, c] of [[x + 34, "#c0392b"], [x + 86, "#111"]]) { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(jx, y + 142, 6, 0, 6.29); ctx.fill(); }
    text("10 MΩ 멀티미터", x + 60, y + 186, 10.5, "#33404d");
  }
  function ledBoard(x, y, level, glow) {
    rr(x, y, 96, 36, 4, "#f4f1e6", "#c9c2a8");
    for (let i = 0; i < 9; i++) for (let j = 0; j < 3; j++) { ctx.fillStyle = "#cfc7ad"; ctx.fillRect(x + 6 + i * 10, y + 6 + j * 10, 3, 3); }
    // 저항 470 Ω
    rr(x + 14, y + 13, 30, 10, 4, "#d8c39b"); ["#e6c229", "#8b4513", "#c0392b"].forEach((c, k) => { ctx.fillStyle = c; ctx.fillRect(x + 20 + k * 7, y + 13, 3, 10); });
    text("470 Ω", x + 29, y + 50, 9.5, "#5d6673");
    // LED
    const lx = x + 70, ly = y + 12;
    if (glow > 0) {
      const R = 16 + 34 * glow;
      const g = ctx.createRadialGradient(lx, ly, 2, lx, ly, R);
      g.addColorStop(0, `rgba(255,70,60,${0.85 * glow})`); g.addColorStop(1, "rgba(255,70,60,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(lx, ly, R, 0, 6.29); ctx.fill();
    }
    ctx.fillStyle = glow > 0 ? `rgb(255,${Math.round(90 + 120 * glow)},${Math.round(80 + 100 * glow)})` : "#9c2b25";
    ctx.beginPath(); ctx.arc(lx, ly, 7, Math.PI, 0); ctx.lineTo(lx + 7, ly + 9); ctx.lineTo(lx - 7, ly + 9); ctx.fill();
    text("LED", lx, y + 50, 9.5, "#5d6673");
  }
  function wire(x0, y0, x1, y1, color, sag = 40) {
    ctx.strokeStyle = color; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.bezierCurveTo(x0, y0 + sag, x1, y1 + sag, x1, y1); ctx.stroke();
  }

  // 통째 결정: 2D 보로노이·프랙탈 탭과 같은 결정핵 규칙(FR) — 세포 크기 ×20 확대, 층·극성 없음
  const tisTex = {};
  function tissueTexture() {
    if (tisTex.cv || typeof FR === "undefined") return tisTex.cv;
    const F = DATA.fractal.params, X = 20, Wm = 2 * (BOT.d / 2 - BOT.wall), Hm = BOT.fill;
    const sp = (S.spacing_um / 1000) * X;
    const GW = 300, GH = Math.round(GW * Hm / Wm), r = FR.rng(21);
    const pts = FR.seeds({ W: Wm, H: Hm, spacing: sp, Ds: F.seed_dimension }, r);
    const sh = pts.map(() => 0.86 + r() * 0.26);
    const own = FR.raster(pts, Wm, Hm, GW, GH), cv2 = document.createElement("canvas");
    cv2.width = GW; cv2.height = GH;
    const c2 = cv2.getContext("2d"), img = c2.createImageData(GW, GH), d = img.data;
    for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
      const g = j * GW + i, o = own[g], p = ((GH - 1 - j) * GW + i) * 4;
      let c = [191, 227, 245].map((v) => v * sh[o]);
      const nbr = [i < GW - 1 ? own[g + 1] : o, j < GH - 1 ? own[g + GW] : o].find((q) => q !== o);
      if (nbr !== undefined) c = [201, 138, 58]; // 막 + 막 사이 진한 소금물
      d[p] = c[0]; d[p + 1] = c[1]; d[p + 2] = c[2]; d[p + 3] = 255;
    }
    c2.putImageData(img, 0, 0);
    // 얼어 있을 때: 얼음 결정 결 (희고 반짝임)
    const ice = document.createElement("canvas"); ice.width = GW; ice.height = GH;
    const ci = ice.getContext("2d"); ci.drawImage(cv2, 0, 0);
    ci.fillStyle = "rgba(235,246,255,0.28)"; ci.fillRect(0, 0, GW, GH);
    tisTex.cv = cv2; tisTex.ice = ice;
    return cv2;
  }
  // o: level 액면 (0–1) · color 액체 색 · ice 얼음 (동결: 아래부터 높이 비율, 해동: 남은 부피 비율) · core 해동 중 · gel 세포 구조 있음
  function tissueCrystal(cx, base, h, o) {
    const r = (BOT.d / 2 - BOT.wall) * K, cv0 = tissueTexture(), hl = h * o.level;
    if (hl <= 0) return;
    const shadeIt = () => {
      const g = ctx.createLinearGradient(cx - r, 0, cx + r, 0);
      g.addColorStop(0, "#00000040"); g.addColorStop(0.35, "#ffffff26"); g.addColorStop(1, "#00000048");
      ctx.fillStyle = g; ctx.fillRect(cx - r, base - hl, 2 * r, hl);
    };
    if (!o.gel || !cv0) { ctx.fillStyle = o.color + "cc"; ctx.fillRect(cx - r, base - hl, 2 * r, hl); }
    else { ctx.drawImage(tisTex.cv, cx - r, base - h, 2 * r, h); ctx.fillStyle = "rgba(245,247,250,0.18)"; ctx.fillRect(cx - r, base - h, 2 * r, h); }
    if (o.ice > 0 && cv0) {
      ctx.save(); ctx.beginPath();
      if (o.core) { const rc = r * Math.sqrt(o.ice); ctx.rect(cx - rc, base - hl, 2 * rc, hl); } // 수조: 바깥부터 녹음
      else { // 냉각판: 아래부터 얾 (프랙탈 전선을 흉내 낸 물결)
        const fz = base - hl * o.ice;
        ctx.moveTo(cx - r, base);
        for (let k = 0; k <= 24; k++) ctx.lineTo(cx - r + (2 * r * k) / 24, fz + (o.ice < 1 ? 2.5 * Math.sin(k * 1.7 + o.ice * 40) : 0));
        ctx.lineTo(cx + r, base); ctx.closePath();
      }
      ctx.clip(); ctx.drawImage(tisTex.ice, cx - r, base - h, 2 * r, h); ctx.restore();
      if (!o.core && o.ice < 1) { ctx.strokeStyle = "#dff3ff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx - r, base - hl * o.ice); ctx.lineTo(cx + r, base - hl * o.ice); ctx.stroke(); }
    }
    shadeIt();
  }
  function waterBath(cx, base) {
    const ro = (BOT.d / 2) * K + 16, hw = (BOT.body - 5) * K;
    rr(cx - ro, base - hw - 12, 2 * ro, hw + 12, 6, null, "#7f93a6", 2);
    ctx.fillStyle = "#6fb3e655"; ctx.fillRect(cx - ro + 2, base - hw, 2 * ro - 4, hw);
    text("항온수조 25 °C", cx, 462, 11, "#ffc36b", "center", "700");
  }
  function insulation(cx, base) {
    const ro = (BOT.d / 2) * K, hb = (BOT.body + 10) * K;
    ctx.fillStyle = "#f3e7a8b0";
    ctx.fillRect(cx - ro - 14, base - hb, 12, hb); ctx.fillRect(cx + ro + 2, base - hb, 12, hb);
    text("단열재", cx + ro + 8, base - hb - 6, 9.5, "#ffe9a8");
  }

  function render() {
    const dpr = window.devicePixelRatio || 1, rect = cv.getBoundingClientRect();
    if (rect.width < 50) return;
    const sc = rect.width / W;
    cv.width = Math.round(rect.width * dpr); cv.height = Math.round(rect.width * (H / W) * dpr);
    ctx.setTransform(sc * dpr, 0, 0, sc * dpr, 0, 0);
    background(); shelf(); hotplate(); balance(); beakers();
    const plate = freezer();
    const cx = FZ.x + FZ.w / 2, base = plate;
    const s = S, { i, u } = where(t), step = STEPS[i];
    const blockH = s.r0 || s.tissue ? BOT.fill * K : s.height_mm * K;
    const ft = prog("ft"), dm = prog("demold"), me = prog("meas"), ld = prog("led");
    // 결정 위치: 냉동실 → 측정대
    const move = ease(clamp((dm - 0.35) / 0.65));
    let bx = lerp(cx, ST.x + 54, move), bb = lerp(base, 398, move);
    // 내용물
    let layersDone = 0, frontMm = 0;
    if (s.tissue) { // 병: 실험대 → 냉각판 ⇄ 항온수조 → 측정대
      const st = tisState(), full = BOT.fill * K, BX = 575, BENCH = 430;
      let px = st.at === "plate" ? cx : BX, pb = st.at === "plate" ? base : BENCH;
      if (st.move > 0 && st.move < 1) { px = lerp(BX, cx, ease(st.move)); pb = lerp(BENCH, base, ease(st.move)); }
      bx = lerp(px, ST.x + 54, move); bb = lerp(pb, 398, move);
      const tk = prog("take"), mx = prog("mix"), rf = prog("refill");
      const level = rf > 0 ? lerp(0.0, 1, clamp(rf * 1.2)) : mx > 0 ? 0.675 * (1 - clamp(mx * 3)) : 1 - 0.325 * clamp(tk * 1.5);
      const color = rf > 0 || st.gel || st.ice > 0 ? COL.mix : "#cfe6f5";
      tissueCrystal(bx, bb, full, { level: dm > 0 ? 1 : level, color, ice: st.ice, core: !!st.bath, gel: st.gel || dm > 0 });
      frontMm = st.bath ? 0 : BOT.fill * st.ice;
      if (dm < 0.35) {
        if (st.at === "plate" && !(st.move < 1)) insulation(px, pb);
        mold(px, pb, true);
        if (st.bath) waterBath(px, pb);
      } else if (dm < 1) { ctx.globalAlpha = 1 - clamp((dm - 0.35) / 0.3); mold(px + 90 * dm, pb, true); ctx.globalAlpha = 1; }
      const cold = st.at === "plate", ly = cold ? FZ.y + 58 : pb - 262;
      const lab = (msg, sub) => { text(msg, px, ly, 12, cold ? "#bfe6ff" : "#263241", "center", "700"); if (sub) text(sub, px, ly + 14, 9.5, cold ? "#c9d6e3" : "#5d6673"); };
      if (tk > 0 && tk < 1) lab("메스실린더로 덜어 냄", "100 mL + 62.5 mL");
      if (mx > 0 && mx < 0.35) { lab("남은 식염수 → 1 L 비커"); pourer(BX - 60, 250, "#cfe6f5", -0.9, 330); }
      if (rf > 0 && rf < 1) { lab("깔때기로 병에 다시 담기", "벽을 타고 천천히"); pourer(BX - 70, 230, COL.mix, 0.9, BENCH - full * level); }
      if (prog("setup") > 0 && prog("setup") < 1) lab("접촉액 · 단열 · 열전대", "수작업");
      if (st.at === "plate" && st.ice > 0 && st.ice < 1) lab(`얼음 전선 ${frontMm.toFixed(0)} mm ↑ 세포 생성`, st.cycle ? `재동결 ${st.cycle} / ${s.freeze_thaw - 1}` : "세포 무늬 ×20 확대 (같은 보로노이 규칙)");
      if (st.bath && st.ice > 0) lab(`해동 — 얼음 심 ${(100 * st.ice).toFixed(0)} %`, st.cycle ? `회차 ${st.cycle} / ${s.freeze_thaw - 1}` : "바깥부터 녹음");
    } else if (s.r0) {
      const p1 = prog("pour1");
      const fillH = blockH * ease(clamp(p1 * 1.2));
      if (p1 > 0 || ft > 0) crystal(bx, bb, Math.max(1, fillH), { opaque: ft, liquid: ft <= 0 });
      if (dm < 0.35) mold(cx, base, true);
      else if (dm < 1) { ctx.globalAlpha = 1 - clamp((dm - 0.35) / 0.3); mold(cx + 90 * dm, base, true); ctx.globalAlpha = 1; }
      if (p1 > 0 && p1 < 0.85) pourer(cx - 70, FZ.y + 70, COL.mix, 0.9, base - fillH);
    } else {
      const L = prog("layers");
      layersDone = L >= 1 ? 4 * s.pairs : Math.floor(L * 4 * s.pairs);
      const pitch = (2 * s.layer_mm + s.cem_mm + s.aem_mm) * K;
      const curH = Math.min(blockH, Math.ceil(layersDone / 4 + 0.5) * pitch);
      if (layersDone > 0) crystal(bx, bb, L >= 1 ? blockH : curH, { layers: layersDone, opaque: ft });
      const moldOn = prog("mold") > 0.4 && dm < 0.35;
      if (moldOn) mold(cx, base, false);
      else if (dm >= 0.35 && dm < 0.7) { ctx.globalAlpha = 1 - (dm - 0.35) / 0.35; mold(cx, base - 30 * (dm - 0.35) / 0.35, false); ctx.globalAlpha = 1; }
      if (L > 0 && L < 1) {
        const kind = layersDone % 4, cols = [COL.A, COL.CEM, COL.B, COL.AEM];
        const sub = (L * 4 * s.pairs) % 1;
        if (sub < 0.55) pourer(cx - 66, FZ.y + 66, cols[kind], 0.85, base - curH);
        text(["A액 붓기", "CEM 벽 바르기", "B액 붓기", "AEM 벽 바르기"][kind] + (sub >= 0.55 ? " → 얼리기" : ""), cx, FZ.y + 58, 12, "#e8f1fb", "center", "600");
      }
      if (prog("mold") > 0 && prog("mold") < 1) { // 병 윗부분 잘라 냄
        const m = prog("mold");
        ctx.globalAlpha = 1 - m; text("✂ 어깨 아래 절단", cx, base - BOT.body * K - 10, 12, "#ffd479", "center", "700"); ctx.globalAlpha = 1;
      }
    }
    if (!s.tissue && ft > 0 && ft < 1) {
      const N = s.tissue ? s.freeze_thaw - 1 : 3, c = (ft * N) % 1, n = Math.min(N, Math.floor(ft * N) + 1);
      text(`동결-해동 ${n} / ${N} · ${c < 2 / 14 ? "해동 +4 °C" : "동결 −20 °C"}`, cx, FZ.y + 58, 12.5, "#bfe6ff", "center", "700");
    }
    // 측정대 · 계기
    stand(blockH, move > 0.99);
    const showM = me > 0 || ld > 0 || prog("cond") > 0;
    const blockTop = bb - blockH;
    let reading = "--.--", mode = "DC V", on = false, glow = 0;
    if (showM) {
      const pr = ease(clamp(me / 0.4));
      // 흑연 막대 + 집게
      const topY = blockTop - 4 - 30 * (1 - pr), botX = ST.x + 54;
      ctx.fillStyle = "#2e3135"; ctx.fillRect(botX - 3, topY - 46, 6, 46); rr(botX - 6, topY - 58, 12, 14, 3, "#c0392b");
      ctx.fillRect(ST.x - 30 + 30 * pr, 404, 50, 5); rr(ST.x - 44 + 30 * pr, 400, 14, 13, 3, "#111");
      const MX = 1062, MY = 214;
      if (me > 0.5) {
        const v = s.r0 ? 0.002 * Math.sin(performance.now() / 300) : s.ocv * ease(clamp((me - 0.5) / 0.4));
        reading = s.tissue ? `${(v * 1000).toFixed(1)}mV` : `${v.toFixed(2)} V`; on = true;
      }
      let cd = prog("cond");
      if (s.tissue) cd = 0; // 통째 결정: 단면은 SEM-EDS (아래 상자)
      if (cd > 0) { // 국소 전도도: 탐침이 막(진한 소금물)과 내강(묽음)을 번갈아 지남
        mode = "전도도 mS/cm (탐침)";
        const wall = Math.sin(cd * 60) > 0.55;
        reading = wall ? `${(s.c_brine_m < 2 ? 85 * s.c_brine_m : 150).toFixed(0)}` : `${(0.12 * s.c_lumen_mM).toFixed(2)}`;
        on = true;
      }
      if (ld > 0) {
        mode = "DC mA (LED 직렬)";
        const k = ease(clamp(ld / 0.5));
        reading = `${((s.led_ma || 0) * k).toFixed(2)}mA`; on = true;
        glow = s.led_level === 2 ? k : s.led_level === 1 ? 0.35 * k : 0;
      }
      wire(botX, topY - 58, MX + 34, MY + 142, "#c0392b", -60);
      wire(ST.x - 37 + 30 * pr, 413, MX + 86, MY + 142, "#111", 30);
      meter(MX, MY, reading, mode, on);
      if (ld > 0) ledBoard(1074, 154, s.led_level, glow);
    }
    if (s.tissue) { // 단면 채취 → 동결건조 → SEM-EDS (공용 장비)
      const sc = prog("section"), ly = prog("lyo"), cd = prog("cond");
      const box = (lines) => { rr(ST.x - 20, 96, 250, 20 + 16 * lines.length, 8, "#17202bd9");
        lines.forEach((l, k) => text(l, ST.x - 8, 114 + 16 * k, k ? 11 : 12, k ? "#c9d6e3" : "#ffffff", "left", k ? "" : "700")); };
      if (cd > 0) {
        const wall = Math.sin(cd * 40) > 0.3;
        box(["SEM-EDS · Cl 지도", `벽 근처 ${s.c_brine_m.toFixed(2)} M  /  칸 안 ${s.c_lumen_mM.toFixed(1)} mM`, wall ? "▶ 지금 벽 위를 훑는 중" : "▶ 지금 칸 안을 훑는 중", "E1: 벽/칸 10배 이상이면 충족"]);
      } else if (ly > 0) box(["동결건조기", `조각 3개 · ${(24 * ly).toFixed(0)} / 24 h`, "얼린 채로 물만 뺌 → 소금 위치 보존"]);
      else if (sc > 0) box(["단면 채취 · 급속 고정", "세로 절단 → 사진 (자 함께)", "위 · 가운데 · 아래 2 mm 조각", "액체질소 10초 → 소금 분포 고정"]);
    }
    // 단계 제목 (+ 수작업 / 기계작업)
    const fit = (str, w, size) => { ctx.font = `${size}px ${FONT}`; let x = str; while (x.length > 4 && ctx.measureText(x).width > w) x = x.slice(0, -2); return x === str ? x : x + "…"; };
    ctx.fillStyle = "#17202bd9"; ctx.beginPath(); ctx.roundRect(16, 168, 360, 54, 8); ctx.fill();
    if (step.mode) {
      const hand = step.mode === "hand";
      rr(290, 176, 76, 20, 10, hand ? "#e07a1f" : "#3b7dd8");
      text(`${hand ? "✋" : "⚙"} ${step.modeKo}`, 328, 190, 11, "#ffffff", "center", "700");
    }
    text(fit(`${i + 1}. ${step.t}`, step.mode ? 262 : 330, 15), 30, 191, 15, "#ffffff", "left", "700");
    text(fit(step.d, 336, 11.5), 30, 211, 11.5, "#c9d6e3", "left");
    // 계기 패널 (HTML)
    const T = freezerTemp(), Th = hotTemp();
    const temp = step.id === "stock" || step.id === "weigh" ? `${Th.toFixed(0)} °C` : `${T > 0 ? "+" : ""}${T.toFixed(0)} °C`;
    if (s.tissue) { // 지금 쓰는 장비의 온도 · 수작업 누계
      const hot = ["weigh", "take", "disperse", "stock", "cool"].includes(step.id), st = tisState();
      const handsDone = STEPS.slice(0, i).reduce((a, x) => a + x.hands, 0) + u * step.hands;
      $("#labLcd").innerHTML = [
        ["경과 시간", `${hoursNow().toFixed(1)} h`, ""],
        ["지금", step.modeKo, step.mode === "hand" ? "warn" : ""],
        st.bath ? ["항온수조", "25 °C", "warn"] : hot ? ["핫플레이트", `${Th.toFixed(0)} °C`, Th > 30 ? "warn" : ""]
          : ["냉각판", `${T > 0 ? "+" : ""}${T.toFixed(0)} °C`, T < 0 ? "cold" : ""],
        ["얼음 전선 (세포 형성)", `${frontMm.toFixed(0)} / ${BOT.fill.toFixed(0)} mm`, frontMm > 0 ? "cold" : ""],
        ["손 작업 누계", `${(handsDone / 60).toFixed(1)} h`, ""],
        ["멀티미터", reading, on ? "" : "cold"],
      ].map(([k, v, c]) => `<div><small>${k}</small><b class="${c}">${esc(v)}</b></div>`).join("");
    } else $("#labLcd").innerHTML = [
      ["경과 시간", `${hoursNow().toFixed(1)} h`, ""],
      [step.id === "stock" || step.id === "weigh" ? "핫플레이트" : "냉동실", temp, T < 0 && !(step.id === "stock" || step.id === "weigh") ? "cold" : Th > 30 ? "warn" : ""],
      s.tissue ? ["얼음 전선 (세포 형성)", `${frontMm.toFixed(0)} / ${BOT.fill.toFixed(0)} mm`, frontMm > 0 ? "cold" : ""]
        : ["쌓인 층 · 벽", s.r0 ? "층 없음" : `${Math.ceil(layersDone / 2)} / ${2 * s.pairs}`, ""],
      ["멀티미터", reading, on ? "" : "cold"],
    ].map(([k, v, c]) => `<div><small>${k}</small><b class="${c}">${esc(v)}</b></div>`).join("");
    [...$("#labSteps").children].forEach((li, k) => { li.classList.toggle("on", k === i); li.classList.toggle("done", k < i || (k === i && u >= 1)); });
    if (render.lastStep !== i || render.lastS !== S.key) { $("#labNote").innerHTML = `<div><b>${esc(step.t)}</b></div>` + step.n(); render.lastStep = i; render.lastS = S.key; }
    $("#labBar").style.width = `${(100 * t) / TOTAL}%`;
    $("#labClock").textContent = `${hoursNow().toFixed(1)} / ${HOURS[HOURS.length - 1].toFixed(0)} h`;
  }

  // ---------- 조작 ----------
  function setSample(key) {
    S = SAMPLES.find((x) => x.key === key) || SAMPLES[0];
    STEPS = steps(S); index();
    delete tisTex.cv;
    const dur = (h) => (h >= 1 ? h.toFixed(h < 10 ? 1 : 0) + " h" : Math.round(h * 60) + " 분");
    $("#labSteps").innerHTML = STEPS.map((st, k) => `<li data-k="${k}">${st.mode ? `<span class="mode ${st.mode}">${esc(st.modeKo)}</span> ` : ""}${esc(st.t)}`
      + `<br><small>${st.mode ? `손 ${st.hands.toFixed(0)} 분 · 걸림 ${dur(st.h)}` : `${esc(st.d)} · ${dur(st.h)}`}</small></li>`).join("");
    $("#labSampleNote").textContent = S.note || "";
    render.lastStep = -1;
    t = 0; render();
    try { localStorage.setItem("snss-lab-sample", key); } catch (e) {}
  }
  $("#labSteps").addEventListener("click", (ev) => { const li = ev.target.closest("li"); if (li) { t = T0[+li.dataset.k] + 0.001; render(); } });
  const sel = $("#labSample");
  sel.innerHTML = SAMPLES.map((s) => `<option value="${esc(s.key)}">${esc(s.name)}${s.r0 ? "" : s.tissue ? ` — 인공세포 · ${s.ocv.toFixed(2)} V` : ` — ${s.pairs}쌍 · ${s.ocv.toFixed(2)} V`}</option>`).join("");
  sel.onchange = () => setSample(sel.value);
  const play = $("#labPlay");
  function loop(now) {
    if (!playing) return;
    t += ((now - last) / 1000) * +$("#labSpeed").value; last = now;
    if (t >= TOTAL) { t = TOTAL; playing = false; play.textContent = "▶ 다시"; }
    if (cv.offsetParent) render();
    if (playing) requestAnimationFrame(loop);
  }
  play.onclick = () => {
    playing = !playing;
    if (playing && t >= TOTAL) t = 0;
    play.textContent = playing ? "❚❚ 정지" : "▶ 재생";
    last = performance.now(); requestAnimationFrame(loop);
  };
  $("#labPrev").onclick = () => { const { i, u } = where(t); t = T0[Math.max(0, u > 0.05 ? i : i - 1)]; render(); };
  $("#labNext").onclick = () => { const { i } = where(t); t = i + 1 < STEPS.length ? T0[i + 1] + 0.001 : TOTAL; render(); };
  $("#labProg").onclick = (ev) => { const r = ev.currentTarget.getBoundingClientRect(); t = clamp((ev.clientX - r.left) / r.width) * TOTAL; render(); };
  new ResizeObserver(() => render()).observe(cv);
  // 김·멀티미터 흔들림이 멈춘 상태에서도 살짝 움직이게
  setInterval(() => { if (!playing && cv.offsetParent) render(); }, 250);

  let saved = null;
  try { saved = localStorage.getItem("snss-lab-sample"); } catch (e) {}
  const q = new URLSearchParams(location.search);
  sel.value = q.get("lab") || (SAMPLES.some((s) => s.key === saved) ? saved : SAMPLES[0].key);
  setSample(sel.value);
  if (q.has("labt")) { t = clamp(+q.get("labt")) * TOTAL; render(); }
  window.__lab = { setSample, seek: (u) => { t = clamp(u) * TOTAL; render(); } };
})();
