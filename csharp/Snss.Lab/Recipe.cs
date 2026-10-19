using System.Text.Json;

namespace Snss;

/// <summary>레시피 재료량 + 결정 예측 (spec §10, Python snss_battery/recipe.py 와 독립 구현)</summary>
public sealed record Recipe(double Pairs, double Layer, double Dilution, double InnerD, double Go, double Wall,
                            double AemGo, double Pdda, double Spare)
{
    const double NaclMw = 58.44, SalineM = 0.1545, GoDisp = 4.0;

    public static Recipe From(JsonElement j)
    {
        double N(string k) => j.GetProperty(k).GetDouble();
        return new Recipe(N("pairs"), N("layer_mm"), N("dilution"), N("bottle_inner_mm"), N("go_layer_mg_ml"),
                          N("wall_ml"), N("aem_go_mg_ml"), N("aem_pdda_wt"), N("spare"));
    }

    /// <summary>(키, 값, 정수 여부) — Python 과 같은 순서·이름</summary>
    public List<(string Key, double Value, bool Int)> Values()
    {
        double ca = SalineM / Dilution, cb = 2.0 * SalineM - ca;
        double area = Math.PI * Math.Pow(InnerD / 20.0, 2);
        double layerMl = area * Layer / 10.0;
        double mix = layerMl * Pairs * Spare;
        double height = Pairs * (2.0 * Layer + 0.013);
        double half = mix / 2.0, stock = 2.0 * half;
        double pva = stock * 0.10;
        double goStock = stock * (2.0 * Go) / GoDisp;
        double salineA = half * (2.0 * ca) / SalineM;
        double nacl = (2.0 * cb - SalineM) * half / 1000.0 * NaclMw;
        double walls = Pairs * Wall * Spare;
        double cemGo = walls * 0.9, aemGo = walls * AemGo / GoDisp, pdda = walls * Pdda / 20.0;

        var s = new Case(area * height / 10.0, InnerD + 1.6, 0.9, 25.0, Go, Layer, cb / ca, 0.0, 0.0).Build().Stack;
        double i = Sim.Operating(s.Ocv, s.RInt, new Led());
        return
        [
            ("c_dilute_m", ca, false), ("c_conc_m", cb, false), ("ratio", cb / ca, false), ("area_cm2", area, false),
            ("layer_ml", layerMl, false), ("mix_ml", mix, false), ("height_mm", height, false),
            ("steps", 4.0 * Pairs, true), ("half_ml", half, false), ("stock_ml", stock, false), ("pva_g", pva, false),
            ("go_stock_ml", goStock, false), ("water_stock_ml", stock - pva - goStock, false),
            ("saline_a_ml", salineA, false), ("water_a_ml", half - salineA, false), ("extra_nacl_g", nacl, false),
            ("wall_ml", walls, false), ("cem_go_ml", cemGo, false), ("cem_pva_ml", walls - cemGo, false),
            ("aem_go_ml", aemGo, false), ("pdda_ml", pdda, false), ("aem_water_ml", walls - aemGo - pdda, false),
            ("buy_saline_ml", salineA + half, false), ("buy_go_ml", goStock + cemGo + aemGo, false),
            ("buy_pva_g", pva + (walls - cemGo) * 0.10, false), ("n_pairs", s.NPairs, true),
            ("ocv_v", s.Ocv, false), ("r_int_ohm", s.RInt, false), ("led_ma", i * 1000.0, false),
        ];
    }
}
