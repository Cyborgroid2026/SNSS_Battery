using System.Text;
using System.Text.Json;
using Snss;

// Snss.Lab — SNSS 생리식염수 결정 배터리 독립 구현 (C#)
//   dotnet run -c Release -- crosscheck ../../spec/cases.json     기준 사례 계산 → JSON
//   dotnet run -c Release -- recipe ../../spec/cases.json         레시피 재료량 → JSON
//   dotnet run -c Release -- light ../../spec/light_cases.json    빛 조각가 SC-2 잉크층 · 층 노출 → JSON
//   dotnet run -c Release -- verify ../../experiments/log.jsonl   실험 기록 판정 → JSON
Console.OutputEncoding = Encoding.UTF8;
var cmd = args.Length > 0 ? args[0] : "";
var opts = new JsonWriterOptions { Indented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
using var stdout = Console.OpenStandardOutput();
using var w = new Utf8JsonWriter(stdout, opts);

switch (cmd)
{
    case "crosscheck":
        Crosscheck(args.Length > 1 ? args[1] : "../spec/cases.json");
        break;
    case "quantum":
        QuantumJson();
        break;
    case "recipe":
        Recipes(args.Length > 1 ? args[1] : "../spec/cases.json");
        break;
    case "light":
        LightJson(args.Length > 1 ? args[1] : "../spec/light_cases.json");
        break;
    case "qcad":
        {
            var dir = args.Length > 1 ? args[1] : "cad_out";
            Directory.CreateDirectory(dir);
            w.WriteStartObject();
            foreach (var (file, layers, product) in new[]
                     {
                         ("qmodule_csharp.step", StepWriter.QModuleLayers(), "SNSS-QB quantum module"),
                         ("crystal_block_csharp.step", StepWriter.CrystalLayers(), "SNSS saline crystal block"),
                     })
            {
                var path = Path.Combine(dir, file);
                double vol = StepWriter.Write(path, layers, product);
                w.WriteStartObject(file);
                w.WriteString("path", Path.GetFullPath(path));
                w.WriteNumber("solids", layers.Count);
                w.WriteNumber("analytic_volume_mm3", vol);
                w.WriteEndObject();
            }
            w.WriteEndObject();
        }
        break;
    case "verify":
        Verify(args.Length > 1 ? args[1] : "../experiments/log.jsonl");
        break;
    default:
        Console.Error.WriteLine("사용법: Snss.Lab crosscheck <cases.json> | recipe <cases.json> | quantum | light <light_cases.json> | qcad <out.step> | verify <log.jsonl>");
        return 2;
}
w.Flush();
Console.WriteLine();
return 0;

void Crosscheck(string path)
{
    using var doc = JsonDocument.Parse(File.ReadAllText(path));
    w.WriteStartObject();
    foreach (var c in doc.RootElement.GetProperty("cases").EnumerateArray())
    {
        double N(string k) => c.GetProperty(k).GetDouble();
        var f = c.GetProperty("fractal");
        double F(string k) => f.GetProperty(k).GetDouble();
        var bat = new Case(N("bottle_ml"), N("bottle_d_mm"), N("nacl_wt"), N("temp_c"), N("go_mg_ml"), N("layer_mm"),
                           N("ratio"), N("shrink"), N("surface_go")).Build();
        var prm = new FractalParams(F("D"), F("roughness"), F("correlation"), F("Ds"), F("grains"),
                                    (int)F("window_layers"), F("window_mm"), (ulong)F("seed"));
        var s = bat.Stack;
        var net = Tess.Network(bat, Tess.Build(bat, prm));
        w.WriteStartObject(c.GetProperty("name").GetString()!);
        w.WriteNumber("n_pairs", s.NPairs);
        w.WriteNumber("c0", s.C0);
        w.WriteNumber("ocv_v", s.Ocv);
        w.WriteNumber("r_int_ohm", s.RInt);
        w.WriteNumber("capacity_c", s.CapacityC);
        w.WriteNumber("contact_f", s.Capacitance);
        w.WriteNumber("n_cells", net.NCells);
        w.WriteNumber("n_inner_ridges", net.NInner);
        w.WriteNumber("v_oc_window", net.VWin);
        w.WriteNumber("r_window", net.RWin);
        w.WriteNumber("p_loss_window", net.PLoss);
        w.WriteNumber("active_length", net.ActiveLen);
        w.WriteNumber("defect_length", net.DefectLen);
        w.WriteNumber("mean_neighbors", net.MeanNb);
        w.WriteNumber("net_ocv_v", net.Ocv);
        w.WriteNumber("net_r_ohm", net.R);
        w.WriteNumber("net_leak_ma", net.LeakMa);
        if (c.TryGetProperty("lighting", out var lt) && lt.GetBoolean())
        {
            var met = new Metabolism();
            var b2 = bat.Clone();
            met.Attach(b2);
            w.WriteNumber("light_pump_a", met.LightPump(b2));
            w.WriteNumber("fuel_pump_a", met.FuelPump(b2));
            w.WriteNumber("evap_emf_v", met.EvapEmf(b2));
            var led = Sim.Simulate(bat, met, new Led(), 168.0, 60.0, 1);
            w.WriteNumber("led_first_off_h", led.FirstOffH ?? -1.0);
            w.WriteNumber("led_on_fraction", led.OnFraction);
            w.WriteNumber("led_current_end_a", led.LastI);
            var (k, _) = Sim.BestParallel(bat, met, new Bulb());
            w.WriteNumber("bulb_best_k", k);
            double i0 = Sim.Operating(b2.Stack.Ocv / k, b2.Stack.RInt / ((double)k * k), new Bulb());
            w.WriteNumber("bulb_peak_w", i0 * new Bulb().Voltage(i0));
            var bulb = Sim.Simulate(bat, met, new Bulb(), 2.0, 2.0, k);
            w.WriteNumber("bulb_glow_min", bulb.FirstOffH is { } h ? h * 60.0 : -1.0);
        }
        w.WriteEndObject();
    }
    w.WriteEndObject();
}

void Recipes(string path)
{
    using var doc = JsonDocument.Parse(File.ReadAllText(path));
    w.WriteStartObject();
    if (doc.RootElement.TryGetProperty("recipes", out var list))
        foreach (var j in list.EnumerateArray())
        {
            w.WriteStartObject(j.GetProperty("name").GetString()!);
            foreach (var (k, v, isInt) in Recipe.From(j).Values())
                if (isInt) w.WriteNumber(k, (long)v); else w.WriteNumber(k, v);
            w.WriteEndObject();
        }
    w.WriteEndObject();
}

void LightJson(string path)
{
    using var doc = JsonDocument.Parse(File.ReadAllText(path));
    w.WriteStartObject();
    foreach (var c in doc.RootElement.GetProperty("cases").EnumerateArray())
    {
        double N(string k) => c.GetProperty(k).GetDouble();
        var l = new Light(N("go_mg_ml"), N("pva_wt"), N("nacl_mm"), N("eosin_um"), N("depth_mm"), N("irradiance"), N("green"));
        double x = l.LayerRatio;
        w.WriteStartObject(c.GetProperty("name").GetString()!);
        w.WriteNumber("dp_mm", l.DpMm);
        w.WriteNumber("dp_green_mm", l.DpGreenMm);
        w.WriteNumber("layer_ratio", x);
        w.WriteNumber("layer_mm", l.LayerMm);
        w.WriteNumber("membrane_leak", l.MembraneLeak(x));
        w.WriteNumber("e_cure", l.ECure);
        w.WriteNumber("e_graft_target", l.EGraftTarget);
        w.WriteNumber("ccc_mm", l.CccMm);
        w.WriteNumber("ink_density", l.InkDensity);
        w.WriteNumber("ink_life_h", l.InkLifeH);
        w.WriteNumber("surface_rise_k", l.SurfaceRiseK);
        w.WriteNumber("heat_rise_k", l.HeatRiseK);
        w.WriteNumber("build_time_h", l.BuildTimeH(N("height_mm")));
        int ci = 0;
        foreach (var col in c.GetProperty("columns").EnumerateArray())
        {
            var arrs = l.Column(col.GetString()!);
            string[] keys = ["E405", "D405", "E530", "D530"];
            for (int a = 0; a < 4; a++)
                for (int k = 0; k < arrs[a].Length; k++)
                    w.WriteNumber($"col{ci}.{keys[a]}.{k}", arrs[a][k]);
            ci++;
        }
        w.WriteEndObject();
    }
    w.WriteEndObject();
}

void QuantumJson()
{
    var (rows, a) = Quantum.Scaling([1, 2, 4, 8, 16, 32, 64, 128]);
    w.WriteStartObject();
    w.WriteNumber("exponent", a);
    w.WriteStartObject("rows");
    foreach (var r in rows)
    {
        w.WriteStartObject(r.N.ToString());
        w.WriteNumber("steps", r.Steps);
        w.WriteNumber("tau", r.Tau);
        w.WriteNumber("energy", r.Energy);
        w.WriteNumber("ergotropy", r.Ergotropy);
        w.WriteNumber("advantage", r.Advantage);
        w.WriteEndObject();
    }
    w.WriteEndObject();
    w.WriteEndObject();
}

void Verify(string path)
{
    var bat = new Case(500, 72, 0.9, 25, 5, 0.5, 20, 0, 0).Build();
    var verdicts = Lab.Judge(Lab.Read(path), bat.Stack.Ocv);
    w.WriteStartObject();
    w.WriteString("log", Path.GetFullPath(path));
    w.WriteNumber("model_ocv_v", bat.Stack.Ocv);
    w.WriteStartArray("verdicts");
    foreach (var v in verdicts)
    {
        w.WriteStartObject();
        w.WriteString("id", v.Id);
        w.WriteString("title", v.Title);
        w.WriteString("status", v.Status);
        w.WriteString("detail", v.Detail);
        w.WriteEndObject();
    }
    w.WriteEndArray();
    w.WriteEndObject();
}
