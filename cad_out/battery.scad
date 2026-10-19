// SNSS 생리식염수병 결정 배터리 — 자동 생성 (snss_battery.cad). 단위 mm
$fn = 96;
bottle_d    = 72.0;
wall        = 0.8;
crystal_d   = 70.400;
crystal_h   = 127.638;  // 다듬은 결정 블록 (세포형 도메인 252층)
cut_z       = 134.250;         // 절단선 A (병 바닥에서)
show_bottle = true;

// 꺼낸 결정 블록 (아래면 = -, 윗면 = +)
color("steelblue", 0.9) cylinder(d = crystal_d, h = crystal_h);
// 절단선 A 아래 병 컵 (참고용)
if (show_bottle) translate([0, 0, -wall]) color("white", 0.25) difference() {
    cylinder(d = bottle_d, h = cut_z);
    translate([0, 0, wall]) cylinder(d = bottle_d - 2 * wall, h = cut_z);
}
