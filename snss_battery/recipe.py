"""레시피 계산기 — 기존 문헌 기법을 조합한 생리식염수 결정 배터리 제조량 (RECIPE.md 와 짝).

구성 원리
  - 겔 몸체: PVA 동결-해동 크라이오겔 (얼음 결정 + PVA 미세결정이 물리 가교 → '결정화')
  - 묽은 층 A / 진한 층 B: 약국 생리식염수를 희석·보강해 만든 두 액 (평균 = 원래 0.9 %)
  - 양이온 선택 벽 (CEM): 음전하 그래핀 산화물(GO) 액정 박막
  - 음이온 선택 벽 (AEM): GO + 양이온성 고분자 PDDA (전하 반전)
  - 층마다 붓고 얼려 섞이지 않게 쌓은 뒤 동결-해동 3회
수치는 모델(bottle.py)과 같은 기하를 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

NACL_MW = 58.44
SALINE_M = 0.1545  # 0.9 % 생리식염수
GO_DISP_MG_ML = 4.0  # 시판 GO 수분산액 농도 (대면적 단일층, 판 ≥ 10 µm 권장)


@dataclass
class Recipe:
    name: str = "LED판"
    pairs: int = 25
    layer_mm: float = 2.5
    dilution: float = 20.0  # 묽은 층 = 식염수 1/20
    bottle_inner_mm: float = 70.4
    pva_wt: float = 5.0  # 층 안 PVA 최종 농도
    go_layer_mg_ml: float = 0.5  # 층 안 GO (액정 정렬 씨앗)
    wall_ml: float = 0.4  # 벽 한 장에 바르는 양
    cem_go_mg_ml: float = 3.6  # GO 분산액 9 : PVA 원액 1
    aem_go_mg_ml: float = 2.0
    aem_pdda_wt: float = 1.0
    spare: float = 1.2  # 여유 20 %

    # ---------- 농도 ----------
    @property
    def c_dilute_m(self) -> float:
        return SALINE_M / self.dilution

    @property
    def c_conc_m(self) -> float:
        return 2 * SALINE_M - self.c_dilute_m  # 평균이 0.9 % 가 되도록

    @property
    def ratio(self) -> float:
        return self.c_conc_m / self.c_dilute_m

    # ---------- 부피 ----------
    @property
    def area_cm2(self) -> float:
        return math.pi * (self.bottle_inner_mm / 20) ** 2

    @property
    def layer_ml(self) -> float:
        return self.area_cm2 * self.layer_mm / 10

    @property
    def mix_ml(self) -> float:
        """A액·B액 각각 필요한 양 (여유 포함)."""
        return self.layer_ml * self.pairs * self.spare

    @property
    def height_mm(self) -> float:
        return self.pairs * (2 * self.layer_mm + 0.013)

    def quantities(self) -> dict[str, float]:
        """재료량 (평평한 값 목록 — Rust·C# 교차 검증과 같은 키, spec/SPEC.md §10).
        GO 는 시판 분산액(4 mg/mL)으로 넣으므로 그 물도 계산에 포함."""
        half = self.mix_ml / 2  # A·B 액 = (PVA 원액) 절반 + (식염수 쪽) 절반
        # PVA 원액 (10 wt% PVA, GO 1 mg/mL 포함) — A·B 에 절반씩
        stock = 2 * half
        pva_g = stock * 0.10
        go_stock = stock * (2 * self.go_layer_mg_ml) / GO_DISP_MG_ML
        # A: 식염수 쪽 절반의 NaCl = 2·cA
        saline_a = half * (2 * self.c_dilute_m) / SALINE_M
        # B: 식염수 쪽 절반 = 식염수 + 추가 NaCl 로 2·cB
        extra_nacl_g = (2 * self.c_conc_m - SALINE_M) * half / 1000 * NACL_MW
        walls = self.pairs * self.wall_ml * self.spare
        cem_go = walls * 0.9
        aem_go = walls * self.aem_go_mg_ml / GO_DISP_MG_ML
        pdda = walls * self.aem_pdda_wt / 20  # 시판 20 wt% 수용액
        return {
            "half_ml": half, "stock_ml": stock, "pva_g": pva_g, "go_stock_ml": go_stock,
            "water_stock_ml": stock - pva_g - go_stock, "saline_a_ml": saline_a, "water_a_ml": half - saline_a,
            "extra_nacl_g": extra_nacl_g, "wall_ml": walls, "cem_go_ml": cem_go, "cem_pva_ml": walls - cem_go,
            "aem_go_ml": aem_go, "pdda_ml": pdda, "aem_water_ml": walls - aem_go - pdda,
            "buy_saline_ml": saline_a + half, "buy_go_ml": go_stock + cem_go + aem_go,
            "buy_pva_g": pva_g + (walls - cem_go) * 0.10,
        }

    def amounts(self) -> list[tuple[str, list[tuple[str, float, str]]]]:
        """재료량 (그룹별 표)."""
        q = self.quantities()
        return [
            ("PVA 원액 (10 wt% PVA + GO 1 mg/mL)", [("총량", q["stock_ml"], "mL"), ("PVA 가루", q["pva_g"], "g"),
                                                  ("GO 분산액 4 mg/mL", q["go_stock_ml"], "mL"),
                                                  ("증류수", q["water_stock_ml"], "mL")]),
            ("A액 — 묽은 층", [("PVA 원액", q["half_ml"], "mL"), ("약국 생리식염수", q["saline_a_ml"], "mL"),
                             ("증류수", q["water_a_ml"], "mL")]),
            ("B액 — 진한 층", [("PVA 원액", q["half_ml"], "mL"), ("약국 생리식염수", q["half_ml"], "mL"),
                             ("추가 소금 NaCl", q["extra_nacl_g"], "g")]),
            ("CEM 벽액 — 양이온 선택", [("총량", q["wall_ml"], "mL"), ("GO 분산액 4 mg/mL", q["cem_go_ml"], "mL"),
                                     ("PVA 원액", q["cem_pva_ml"], "mL")]),
            ("AEM 벽액 — 음이온 선택 (반죽)", [("총량", q["wall_ml"], "mL"), ("GO 분산액 4 mg/mL", q["aem_go_ml"], "mL"),
                                         ("PDDA 20 wt% 용액", q["pdda_ml"], "mL"), ("증류수", q["aem_water_ml"], "mL")]),
            ("총 구매량 (여유 포함)", [("약국 생리식염수", q["buy_saline_ml"], "mL"), ("GO 분산액 4 mg/mL", q["buy_go_ml"], "mL"),
                                     ("PVA 가루", q["buy_pva_g"], "g"), ("PDDA 20 wt%", q["pdda_ml"], "mL"),
                                     ("NaCl", q["extra_nacl_g"], "g")]),
        ]

    def steps(self) -> int:
        return 4 * self.pairs  # 붓고 얼리는 횟수

    def battery(self):
        from .bottle import BottleGelBattery, BottleSpec, GelFormation

        fill = self.area_cm2 * self.height_mm / 10
        return BottleGelBattery(
            BottleSpec(fill_volume_ml=fill, outer_diameter_mm=self.bottle_inner_mm + 1.6),
            GelFormation(go_mg_per_ml=self.go_layer_mg_ml, layer_thickness_mm=self.layer_mm,
                         concentration_ratio=self.ratio,
                         reactants=f"PVA {self.pva_wt:g} wt% 크라이오겔 · NaCl · GO 벽 · GO/PDDA 벽 ({self.name})"),
        )

    def predict(self) -> dict:
        from .metabolism import LED, operating_current

        b = self.battery()
        s = b.stack
        led = LED()
        i = operating_current(s.open_circuit_voltage(), s.internal_resistance(), led)
        return {"pairs": s.n_pairs, "ocv_v": s.open_circuit_voltage(), "r_ohm": s.internal_resistance(),
                "led_ma": i * 1000, "led": led.label(i), "shelf_days": b.shelf_time_constant_days}

    def describe(self) -> str:
        p = self.predict()
        lines = [f"[{self.name}] {self.pairs}쌍 × 층 {self.layer_mm:g} mm — 결정 높이 약 {self.height_mm:.0f} mm, "
                 f"층 하나 {self.layer_ml:.1f} mL, 붓기·얼리기 {self.steps()}회",
                 f"  묽은 층 {self.c_dilute_m * 1000:.1f} mM / 진한 층 {self.c_conc_m * 1000:.0f} mM (비 {self.ratio:.0f})"]
        for group, items in self.amounts():
            lines.append(f"  [{group}]")
            for item, value, unit in items:
                lines.append(f"    {item:<22} {value:9.2f} {unit}")
        lines.append(f"  모델 예측: 개방전압 {p['ocv_v']:.2f} V, 내부저항 {p['r_ohm']:.0f} Ω, "
                     f"LED+470 Ω {p['led_ma']:.2f} mA → {p['led']}")
        return "\n".join(lines)


    def spec_case(self) -> dict:
        """교차 검증용 입력 (spec/cases.json 의 recipes 항목)."""
        return {k: getattr(self, k) for k in ("name", "pairs", "layer_mm", "dilution", "bottle_inner_mm", "go_layer_mg_ml",
                                              "wall_ml", "aem_go_mg_ml", "aem_pdda_wt", "spare")}


RECIPES = {
    "practice": Recipe(name="연습판", pairs=6),
    "led": Recipe(name="LED판", pairs=25),
}
