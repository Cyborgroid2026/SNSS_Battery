"""Tkinter GUI: python -m snss_battery gui"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from .assembly import GrapheneLCDispersion, assess  # noqa: E402
from .bottle import BottleGelBattery, BottleSpec, GelFormation  # noqa: E402
from .cad import BottleDesign, BottleDesignParams  # noqa: E402
from .drawing import assembly_sheet, export_all  # noqa: E402
from .electrolyte import SalineSolution  # noqa: E402
from .materials import Selectivity, format_audit, membranes_by_selectivity  # noqa: E402
from .plots import (  # noqa: E402
    plot_assembly, plot_battery_3d, plot_box_counting, plot_cycles, plot_fractal_sweeps, plot_structure,
    plot_voronoi_section, stack_at_soc,
)
from .simulation import CyclingResult, cycle_cc, max_power_point, suggest_limits  # noqa: E402

# (키, 라벨, 기본값, 정수 여부)
_SALINE = [
    ("nacl", "NaCl 농도 [wt%]", 0.9, False),
    ("temp", "온도 [°C]", 25.0, False),
    ("volume", "식염수병 용량 [mL]", 500.0, False),
    ("diameter", "병 바깥지름 [mm]", 72.0, False),
]
_GO = [
    ("go", "GO 농도 [mg/mL]", 5.0, False),
    ("flake", "판 크기 [µm]", 10.0, False),
    ("flake_t", "판 두께 [nm]", 1.0, False),
    ("ccc", "임계응집농도 CCC [mM]", 44.0, False),
]
_GEL = [
    ("layer", "도메인 층 두께 [mm]", 0.5, False),
    ("ratio", "결정화 농도비 (진한/묽은)", 20.0, False),
    ("shrink", "겔화 수축률 (0~0.5)", 0.0, False),
    ("surface", "결정 표면 그래핀 [mg/cm²] (0=자동)", 0.0, False),
    ("age", "결정화 후 보관 [일]", 0.0, False),
]
_CYCLE = [
    ("current", "방전·충전 전류 [mA]", 0.1, False),
    ("vmax", "충전 상한 [V]", 12.292, False),
    ("vmin", "방전 하한 [V]", 8.923, False),
    ("cycles", "충전 후 재사용 횟수", 2, True),
    ("dt", "시간 스텝 [s]", 10.0, False),
]
_FRACTAL = [
    ("fd", "층 경계 프랙탈 차원 D", 1.25, False),
    ("rough", "층 경계 거칠기 (×층 두께)", 0.35, False),
    ("corr", "층 경계 상관도 (0~1)", 0.85, False),
    ("sd", "결정핵 분포 프랙탈 차원", 2.0, False),
    ("grains", "층 두께당 결정핵 수", 3.0, False),
]
_DESIGN = [
    ("cut", "절단 여유 (겔 위) [mm]", 5.0, False),
]
_ALL = (_SALINE, _GO, _GEL, _FRACTAL, _CYCLE, _DESIGN)


class ScrollFrame(ttk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0, width=340)
        bar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        for seq, delta in (("<Button-4>", -1), ("<Button-5>", 1)):
            canvas.bind(seq, lambda _e, d=delta: canvas.yview_scroll(d, "units"))
            self.inner.bind(seq, lambda _e, d=delta: canvas.yview_scroll(d, "units"))


class App(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=8)
        self.root = root
        self.result: CyclingResult | None = None
        self.battery: BottleGelBattery | None = None
        self.design: BottleDesign | None = None
        self.vars: dict[str, tk.StringVar] = {}
        root.title("SNSS 생리식염수 결정 배터리 시뮬레이터")
        root.geometry("1280x840")
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_controls()
        self._build_output()
        self.refresh()

    # ---------- 레이아웃 ----------
    def _section(self, parent, title: str, fields) -> ttk.LabelFrame:
        box = ttk.LabelFrame(parent, text=title, padding=6)
        box.pack(fill="x", pady=(0, 6))
        box.columnconfigure(0, weight=1)
        for r, (key, label, default, _) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=r, column=0, sticky="w")
            v = tk.StringVar(value=str(default))
            e = ttk.Entry(box, textvariable=v, width=9)
            e.grid(row=r, column=1, sticky="e", pady=1)
            e.bind("<Return>", lambda _e: self.refresh())
            self.vars[key] = v
        return box

    def _combo(self, box, label: str, values: list[str], default: str) -> tk.StringVar:
        r = box.grid_size()[1]
        ttk.Label(box, text=label).grid(row=r, column=0, sticky="w")
        v = tk.StringVar(value=default)
        cb = ttk.Combobox(box, textvariable=v, values=values, state="readonly", width=12)
        cb.grid(row=r, column=1, sticky="e", pady=1)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        return v

    def _button(self, box, text, cmd, pad=(6, 0)) -> ttk.Button:
        r = box.grid_size()[1]
        b = ttk.Button(box, text=text, command=cmd)
        b.grid(row=r, column=0, columnspan=2, sticky="ew", pady=pad)
        return b

    def _build_controls(self) -> None:
        sf = ScrollFrame(self)
        sf.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        side = sf.inner

        self._section(side, "① 약국 생리식염수병", _SALINE)
        self._section(side, "② 그래핀 폴리머 액정 붓기", _GO)
        box = self._section(side, "③ 병 안 결정화 (반응 화학물과 함께)", _GEL)
        self.cem = self._combo(box, "도메인 벽 (양이온 선택)",
                               [m.key for m in membranes_by_selectivity(Selectivity.CATION)], "go_lc")
        self.aem = self._combo(box, "도메인 벽 (음이온 선택)",
                               [m.key for m in membranes_by_selectivity(Selectivity.ANION)], "go_pdda")
        self.reactants = tk.StringVar()
        r = box.grid_size()[1]
        ttk.Label(box, text="반응 화학물질 (메모)").grid(row=r, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.reactants, width=14).grid(row=r, column=1, sticky="e", pady=1)
        self._button(box, "적용 (Enter)", self.refresh)

        box = self._section(side, "④ 보로노이·프랙탈 구조", _FRACTAL)
        self.frac_btn = self._button(box, "▶ 프랙탈 분석 (단면·스윕)", self.run_fractal)

        box = self._section(side, "⑤ 프로브 연결 → 방전 → 재충전", _CYCLE)
        self._button(box, "권장 전압 자동 설정", self.auto_limits)
        self.run_btn = self._button(box, "▶ 프로브 연결 시뮬레이션", self.run_cycle, (2, 0))
        self.csv_btn = self._button(box, "CSV 저장", self.save_csv, (2, 0))
        self.csv_btn.config(state="disabled")
        self.progress = ttk.Progressbar(box, mode="indeterminate")
        self.progress.grid(row=box.grid_size()[1], column=0, columnspan=2, sticky="ew", pady=(6, 0))

        box = self._section(side, "⑥ 실물 도면 (병 절단·측정)", _DESIGN)
        self._button(box, "도면·3D 파일 내보내기 (DXF·PDF·STL…)", self.export_cad)
        ttk.Button(side, text="기본값으로 초기화", command=self.reset_defaults).pack(fill="x")

    def _build_output(self) -> None:
        out = ttk.Frame(self)
        out.grid(row=0, column=1, sticky="nsew")
        out.columnconfigure(0, weight=1)
        out.rowconfigure(1, weight=1)

        self.summary = tk.Text(out, height=13, font=("monospace", 9), wrap="none")
        self.summary.grid(row=0, column=0, sticky="ew")

        nb = ttk.Notebook(out)
        nb.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.nb = nb
        self.asm_fig, self.asm_canvas, _ = self._plot_tab(nb, "결정화 (막 형성)")
        self.str_fig, self.str_canvas, frame = self._plot_tab(nb, "세포형 도메인 구조")
        bar = ttk.Frame(frame)
        bar.pack(fill="x", before=self.str_canvas.get_tk_widget())
        ttk.Label(bar, text="충전 상태 (SOC)").pack(side="left", padx=4)
        self.soc_var = tk.DoubleVar(value=90.0)
        ttk.Scale(bar, from_=0, to=100, variable=self.soc_var,
                  command=lambda _v: self._plot_structure()).pack(side="left", fill="x", expand=True, padx=4)
        self.soc_label = ttk.Label(bar, width=22)
        self.soc_label.pack(side="left")
        self.vor_fig, self.vor_canvas, _ = self._plot_tab(nb, "보로노이 단면")
        self.frs_fig, self.frs_canvas, _ = self._plot_tab(nb, "프랙탈 분석")
        self.cyc_fig, self.cyc_canvas, _ = self._plot_tab(nb, "프로브 연결 · 충방전")
        self.dwg_fig, self.dwg_canvas, _ = self._plot_tab(nb, "실물 도면")
        self.m3d_fig, self.m3d_canvas, _ = self._plot_tab(nb, "3D 모델")

        self.status = tk.StringVar(value="준비")
        ttk.Label(out, textvariable=self.status, foreground="gray").grid(row=2, column=0, sticky="w")

    def _plot_tab(self, nb: ttk.Notebook, title: str):
        frame = ttk.Frame(nb)
        nb.add(frame, text=title)
        fig = Figure(figsize=(8, 5), dpi=100, layout="constrained")
        canvas = FigureCanvasTkAgg(fig, master=frame)
        NavigationToolbar2Tk(canvas, frame).update()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return fig, canvas, frame

    # ---------- 입력 ----------
    def _num(self, key: str, as_int: bool = False) -> float:
        raw = self.vars[key].get().strip()
        try:
            return int(raw) if as_int else float(raw)
        except ValueError:
            raise ValueError(f"'{raw}'은(는) 올바른 숫자가 아닙니다.") from None

    def _values(self, fields) -> dict[str, float]:
        return {k: self._num(k, as_int) for k, _, _, as_int in fields}

    def build_dispersion(self) -> GrapheneLCDispersion:
        g = self._values(_GO)
        return GrapheneLCDispersion(g["go"], g["flake"], g["flake_t"], g["ccc"])

    def build_battery(self) -> BottleGelBattery:
        s, g, gel, fr = self._values(_SALINE), self._values(_GO), self._values(_GEL), self._values(_FRACTAL)
        bat = BottleGelBattery(
            BottleSpec(fill_volume_ml=s["volume"], outer_diameter_mm=s["diameter"]),
            GelFormation(go_mg_per_ml=g["go"], layer_thickness_mm=gel["layer"],
                         concentration_ratio=gel["ratio"], shrinkage=gel["shrink"],
                         cation_membrane=self.cem.get(), anion_membrane=self.aem.get(),
                         surface_go_mg_cm2=gel["surface"], reactants=self.reactants.get(),
                         interface_dimension=fr["fd"], interface_roughness=fr["rough"],
                         interface_correlation=fr["corr"], seed_dimension=fr["sd"], grains_per_layer=fr["grains"]),
            SalineSolution(s["nacl"], s["temp"]),
        )
        bat.age(gel["age"])
        return bat

    def build_design(self, bat: BottleGelBattery) -> BottleDesign:
        v = self._values(_DESIGN)
        return BottleDesign(bat, BottleDesignParams(cut_margin_mm=v["cut"]))

    def reset_defaults(self) -> None:
        for fields in _ALL:
            for key, _, default, _ in fields:
                self.vars[key].set(str(default))
        self.cem.set("go_lc")
        self.aem.set("go_pdda")
        self.reactants.set("")
        self.refresh()

    def auto_limits(self) -> None:
        try:
            bat = self.build_battery()
            v_max, v_min = suggest_limits(bat.stack, self._num("current") / 1000)
        except (ValueError, KeyError) as e:
            messagebox.showerror("입력 오류", str(e))
            return
        self.vars["vmax"].set(str(v_max))
        self.vars["vmin"].set(str(v_min))
        self.status.set(f"권장 전압: 충전 상한 {v_max} V, 방전 하한 {v_min} V")

    # ---------- 갱신 ----------
    def refresh(self) -> None:
        try:
            disp = self.build_dispersion()
            bat = self.build_battery()
            design = self.build_design(bat)
        except (ValueError, KeyError) as e:
            self._set_summary(f"오류: {e}")
            self.status.set("입력 오류")
            return
        self.battery, self.design = bat, design
        s = bat.stack
        rep = assess(disp, s.saline.molarity)
        _, p = max_power_point(s)
        self._set_summary("\n".join([
            s.saline.describe(),
            "[결정화] " + rep.describe().replace("\n", "\n         "),
            bat.describe(),
            design.summary(),
            f"[프로브 연결 즉시] 개방전압 {s.open_circuit_voltage():.2f} V, 내부저항 {s.internal_resistance():.1f} Ω, "
            f"순간 최대 {p * 1000:.1f} mW, 용량 {s.capacity_mah:.2f} mAh",
            format_audit(design.audit()),
        ]))
        self.soc_var.set(round(s.state_of_charge * 100))
        plot_assembly(self.asm_fig, disp, s.saline.molarity * 1000)
        self.asm_canvas.draw_idle()
        self._plot_structure()
        fig = self.dwg_fig
        fig.clear()
        fig.set_layout_engine("none")
        assembly_sheet(design).render(fig.add_axes([0, 0, 1, 1]))
        self.dwg_canvas.draw_idle()
        plot_battery_3d(self.m3d_fig, design)
        self.m3d_canvas.draw_idle()
        self.status.set("파라미터 적용됨" + ("" if rep.forms_membrane
                                          else " — ⚠ 현재 배합에서는 정렬된 막(결정화)이 생기지 않음"))

    def _set_summary(self, text: str) -> None:
        self.summary.config(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.config(state="disabled")

    def _plot_structure(self) -> None:
        if self.battery is None:
            return
        born = self.battery.stack.state_of_charge * 100
        self.soc_label.config(text=f"{self.soc_var.get():.0f}% (결정화 직후 {born:.0f}%)")
        plot_structure(self.str_fig, stack_at_soc(self.battery.stack, self.soc_var.get() / 100))
        self.str_canvas.draw_idle()

    # ---------- 전극 연결 · 충방전 ----------
    def run_cycle(self) -> None:
        try:
            stack = self.build_battery().stack
            c = self._values(_CYCLE)
            i = c["current"] / 1000
            if c["cycles"] < 0:
                raise ValueError("재사용 횟수는 0 이상이어야 합니다.")
            if i <= 0 or c["dt"] <= 0:
                raise ValueError("전류와 시간 스텝은 양수여야 합니다.")
        except (ValueError, KeyError) as e:
            messagebox.showerror("입력 오류", str(e))
            return
        est_steps = (2 * c["cycles"] + 1) * stack.capacity_c / i / c["dt"]
        record_every = max(1, int(est_steps / 6000))
        self.run_btn.config(state="disabled")
        self.progress.start(10)
        self.status.set("시뮬레이션 실행 중…")

        # Tk는 메인 스레드에서만 호출 가능 → 워커는 큐에 결과만 넣고 메인 스레드가 폴링
        results: queue.Queue = queue.Queue()

        def work():
            try:
                res = cycle_cc(stack, i, c["vmax"], c["vmin"], c["cycles"], c["dt"],
                               record_every=record_every, born_charged=True)
                results.put((res, None))
            except Exception as e:  # noqa: BLE001
                results.put((None, e))

        def poll():
            try:
                res, err = results.get_nowait()
            except queue.Empty:
                self.root.after(50, poll)
                return
            self._on_done(res, c, err)

        threading.Thread(target=work, daemon=True).start()
        poll()

    def _on_done(self, res: CyclingResult | None, c: dict, err: Exception | None) -> None:
        self.progress.stop()
        self.run_btn.config(state="normal")
        if err is not None:
            messagebox.showerror("시뮬레이션 오류", str(err))
            self.status.set("오류")
            return
        self.result = res
        self.csv_btn.config(state="normal" if res.points else "disabled")
        self.summary.config(state="normal")
        self.summary.insert("end", "\n\n[프로브 연결 → 방전 → 재충전 결과]\n" + res.summary())
        self.summary.see("end")
        self.summary.config(state="disabled")
        born = next((x for x in res.cycles if x.born), None)
        msg = "완료"
        if born:
            msg += f": 결정화 상태에서 바로 {born.discharge_mah:.3f} mAh 방전"
        if res.cycles and not res.cycles[-1].born:
            last = res.cycles[-1]
            msg += f", 재충전 후 {last.discharge_mah:.3f} mAh (쿨롱효율 {last.coulombic_efficiency * 100:.1f}%)"
        if res.warnings:
            msg += f" | 경고 {len(res.warnings)}건"
        self.status.set(msg)
        plot_cycles(self.cyc_fig, res, c["vmax"], c["vmin"])
        self.cyc_canvas.draw_idle()
        self.nb.select(4)

    # ---------- 보로노이 · 프랙탈 ----------
    def run_fractal(self) -> None:
        try:
            bat = self.build_battery()
            bat.fractal_params()  # 값 검사
        except (ValueError, KeyError) as e:
            messagebox.showerror("입력 오류", str(e))
            return
        self.frac_btn.config(state="disabled")
        self.progress.start(10)
        self.status.set("보로노이·프랙탈 네트워크 계산 중… (수 초)")
        results: queue.Queue = queue.Queue()

        def work():
            try:
                from .tessellation import analyze_battery, sweep_interface_dimension, sweep_roughness

                s = bat.stack
                res = analyze_battery(bat)
                base = bat.fractal_params(window_layers=24)
                args = (s, bat.formation.layer_thickness_mm, 2 * s.n_pairs, bat.gel_area_cm2 * 100, base)
                results.put(((res, sweep_interface_dimension(*args), sweep_roughness(*args)), None))
            except Exception as e:  # noqa: BLE001
                results.put((None, e))

        def poll():
            try:
                out, err = results.get_nowait()
            except queue.Empty:
                self.root.after(80, poll)
                return
            self.progress.stop()
            self.frac_btn.config(state="normal")
            if err is not None:
                messagebox.showerror("프랙탈 분석 오류", str(err))
                self.status.set("오류")
                return
            res, by_d, by_r = out
            plot_voronoi_section(self.vor_fig, res)
            self.vor_canvas.draw_idle()
            fig = self.frs_fig
            fig.clear()
            sub = fig.subfigures(2, 1, height_ratios=[1, 1.1])
            plot_box_counting(sub[0], res)
            plot_fractal_sweeps(sub[1], by_d, by_r)
            self.frs_canvas.draw_idle()
            self.summary.config(state="normal")
            self.summary.insert("end", "\n\n[보로노이·프랙탈]\n" + res.describe())
            self.summary.see("end")
            self.summary.config(state="disabled")
            self.status.set(f"프랙탈 분석 완료: 개방전압 {res.ocv_v:.2f} V (평평한 층 대비 {res.efficiency * 100:.0f} %), "
                            f"내부 누설 {res.leak_current_ma:.3f} mA, 실측 D {res.fractal_dim_interfaces:.2f}")
            self.nb.select(2)

        threading.Thread(target=work, daemon=True).start()
        poll()

    # ---------- 내보내기 ----------
    def export_cad(self) -> None:
        if self.design is None:
            messagebox.showerror("설계 없음", "먼저 파라미터를 적용하세요.")
            return
        folder = filedialog.askdirectory(title="도면·3D 파일을 저장할 폴더 선택", mustexist=False)
        if not folder:
            return
        try:
            files = export_all(self.design, folder)
        except OSError as e:
            messagebox.showerror("저장 실패", str(e))
            return
        self.status.set(f"파일 {len(files)}개 저장: {folder}")
        messagebox.showinfo("내보내기 완료", f"{folder}\n\n" + "\n".join(str(f.relative_to(folder)) for f in files))

    def save_csv(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.result.to_csv(path)
            self.status.set(f"CSV 저장: {path}")


def _setup_korean_font() -> None:
    from .drawing import setup_fonts

    setup_fonts()


def main() -> None:
    _setup_korean_font()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
