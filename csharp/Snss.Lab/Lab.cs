using System.Text.Json;

namespace Snss;

/// <summary>
/// 실험 판정 — experiments/log.jsonl 의 측정 기록을 사전 등록 가설(spec/predictions.json)로 판정한다.
/// 판정: "충족" / "불충족" / "데이터 부족". 모델이 맞다는 증명은 '충족'이 쌓이는 것뿐이다.
/// </summary>
public sealed record Measurement(
    double? ElapsedH, string Sample, double? HeightMm, string Probe, string Polarity, string Phase,
    string Load, string Lit, double? VoltageV, double? CurrentMa, string Note);

public sealed record Verdict(string Id, string Title, string Status, string Detail);

public static class Lab
{
    public const string Main = "본 시료";

    public static List<Measurement> Read(string path)
    {
        var list = new List<Measurement>();
        if (!File.Exists(path)) return list;
        foreach (var line in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            using var doc = JsonDocument.Parse(line);
            var r = doc.RootElement;
            double? Num(string k) => r.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
            string Str(string k, string d) => r.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String
                                                  && v.GetString() is { Length: > 0 } s ? s : d;
            list.Add(new Measurement(Num("elapsed_h"), Str("sample", Main), Num("height_mm"), Str("probe", "미기록"),
                Str("polarity", "정"), Str("phase", "결정화 직후"), Str("load", "없음(개방)"), Str("lit", "-"),
                Num("voltage_v"), Num("current_ma"), Str("note", "")));
        }
        return list;
    }

    public static List<Verdict> Judge(List<Measurement> m, double modelOcv)
    {
        var v = new List<Verdict>();
        var open = m.Where(x => x.Load.StartsWith("없음") && x.VoltageV is not null && x.Polarity == "정").ToList();
        var main = open.Where(x => x.Sample == Main && (x.Phase == "결정화 직후" || x.Phase == "절단 후")).ToList();
        var ctrl = open.Where(x => x.Sample.StartsWith("대조군")).ToList();

        // H1 정렬 층이 만드는 전압
        if (main.Count == 0 || ctrl.Count == 0)
            v.Add(new("H1", "정렬된 결정이 대조군보다 확실히 높은 전압", "데이터 부족",
                $"본 시료 {main.Count}건, 대조군 {ctrl.Count}건 — 둘 다 필요 (대조군 A 농도차 없음 · B 한 통에 섞음 · C 식염수만)"));
        else
        {
            double vm = main.Average(x => Math.Abs(x.VoltageV!.Value)), vc = ctrl.Average(x => Math.Abs(x.VoltageV!.Value));
            bool ok = vm >= 0.3 && vm >= 10 * Math.Max(vc, 1e-6);
            v.Add(new("H1", "정렬된 결정이 대조군보다 확실히 높은 전압", ok ? "충족" : "불충족",
                $"본 시료 평균 {vm:F3} V, 대조군 평균 {vc:F3} V (기준: ≥0.3 V 이고 대조군의 10배 이상, 모델 {modelOcv:F2} V)"));
        }

        // H2 직렬 구조: 전압 ∝ 높이
        var withH = main.Where(x => x.HeightMm is > 0).ToList();
        var heights = withH.Select(x => x.HeightMm!.Value).Distinct().ToList();
        if (heights.Count < 2 || heights.Max() / heights.Min() < 1.5)
            v.Add(new("H2", "전압이 결정 높이에 비례 (층이 직렬로 쌓였다는 증거)", "데이터 부족",
                "높이가 1.5배 이상 다른 조각 2개 이상 필요 (예: 통째 측정 후 절반으로 잘라 측정)"));
        else
        {
            var perMm = withH.Select(x => Math.Abs(x.VoltageV!.Value) / x.HeightMm!.Value).ToList();
            double mean = perMm.Average(), spread = perMm.Max() / Math.Max(perMm.Min(), 1e-12);
            bool ok = spread <= 1.25 / 0.75;
            v.Add(new("H2", "전압이 결정 높이에 비례 (층이 직렬로 쌓였다는 증거)", ok ? "충족" : "불충족",
                $"높이당 전압 평균 {mean * 1000:F1} mV/mm, 최대/최소 {spread:F2} (기준 ≤ 1.67, 모델 {modelOcv / 127.6 * 1000:F1} mV/mm)"));
        }

        // H3 극성 반전
        var rev = m.Where(x => x.Polarity == "역" && x.VoltageV is not null && x.Load.StartsWith("없음")).ToList();
        var pairs = rev.Select(r => (r, f: open.Where(o => o.Sample == r.Sample && o.ElapsedH is not null && r.ElapsedH is not null
                                                       && Math.Abs(o.ElapsedH.Value - r.ElapsedH.Value) <= 0.5)
                                              .OrderBy(o => Math.Abs(o.ElapsedH!.Value - r.ElapsedH!.Value)).FirstOrDefault()))
                       .Where(p => p.f is not null).ToList();
        if (pairs.Count == 0)
            v.Add(new("H3", "프로브를 바꾸면 부호만 반대 (접촉 전위가 아닌 내부 전압)", "데이터 부족",
                "같은 시료를 30분 안에 정·역 극성으로 각각 측정한 기록 필요"));
        else
        {
            double worst = pairs.Max(p => Math.Abs(p.r.VoltageV!.Value + p.f!.VoltageV!.Value) / Math.Max(Math.Abs(p.f.VoltageV.Value), 1e-9));
            v.Add(new("H3", "프로브를 바꾸면 부호만 반대 (접촉 전위가 아닌 내부 전압)", worst <= 0.15 ? "충족" : "불충족",
                $"{pairs.Count}쌍, |V정 + V역| / |V정| 최대 {worst * 100:F0} % (기준 ≤ 15 %)"));
        }

        // H4 재충전
        double? Avg(string phase) => open.Where(x => x.Sample == Main && x.Phase == phase).Select(x => x.VoltageV!.Value).DefaultIfEmpty(double.NaN).Average() is var a && !double.IsNaN(a) ? a : null;
        var (v0, v1, v2) = (Avg("결정화 직후") ?? Avg("절단 후"), Avg("방전 후"), Avg("재충전 후"));
        if (v0 is null || v1 is null || v2 is null)
            v.Add(new("H4", "방전 후 낮아진 전압이 재충전으로 회복 (2차 전지)", "데이터 부족", "결정화 직후 · 방전 후 · 재충전 후 측정 필요"));
        else
        {
            double drop = v0.Value - v1.Value, rec = v2.Value - v1.Value;
            bool ok = drop > 0 && rec >= 0.5 * drop;
            v.Add(new("H4", "방전 후 낮아진 전압이 재충전으로 회복 (2차 전지)", ok ? "충족" : "불충족",
                $"{v0:F3} → 방전 후 {v1:F3} → 재충전 후 {v2:F3} V (기준: 떨어진 만큼의 50 % 이상 회복)"));
        }

        // H5, H6 부하 점등
        foreach (var (id, load, title, model) in new[]
                 {
                     ("H5", "LED", "LED 가 켜짐", "모델: LED+470 Ω, 처음 약 14 mA 로 밝다가 연료+빛으로 약 93시간 희미하게 유지"),
                     ("H6", "꼬마전구", "꼬마전구가 빛남", "모델: 6조각 병렬 시 처음 약 6분만 붉게 빛남, 지속 불가"),
                 })
        {
            var rec = m.Where(x => x.Load == load).ToList();
            if (rec.Count == 0) v.Add(new(id, title, "데이터 부족", $"{load} 연결 기록 없음. {model}"));
            else
            {
                bool lit = rec.Any(x => x.Lit is "켜짐" or "희미");
                v.Add(new(id, title, lit ? "충족" : "불충족", $"{rec.Count}건 중 점등 {rec.Count(x => x.Lit is "켜짐" or "희미")}건. {model}"));
            }
        }

        // H7 보관 감쇠 시간 (정보)
        var shelf = open.Where(x => x.Sample == Main && x.ElapsedH is not null && x.VoltageV is > 0
                                    && (x.Phase == "보관 중" || x.Phase == "절단 후")).OrderBy(x => x.ElapsedH).ToList();
        if (shelf.Count < 3 || shelf[^1].ElapsedH - shelf[0].ElapsedH < 24)
            v.Add(new("H7", "보관 중 전압 감쇠 시간 (모델 약 72일)", "데이터 부족", "하루 이상 간격으로 3번 이상 개방전압 측정 필요"));
        else
        {
            double mx = shelf.Average(x => x.ElapsedH!.Value), my = shelf.Average(x => Math.Log(x.VoltageV!.Value));
            double slope = shelf.Sum(x => (x.ElapsedH!.Value - mx) * (Math.Log(x.VoltageV!.Value) - my))
                           / shelf.Sum(x => Math.Pow(x.ElapsedH!.Value - mx, 2));
            double tauDays = slope < 0 ? -1.0 / slope / 24.0 : double.PositiveInfinity;
            bool ok = tauDays >= 24 && tauDays <= 216;
            v.Add(new("H7", "보관 중 전압 감쇠 시간 (모델 약 72일)", ok ? "충족" : "불충족",
                $"측정 시상수 {(double.IsInfinity(tauDays) ? "감쇠 없음" : $"{tauDays:F1}일")} (기준: 모델의 1/3~3배)"));
        }

        if (m.Any(x => x.Probe.Contains("금속")))
            v.Add(new("주의", "금속 프로브 사용 기록 있음", "확인 필요",
                "금속 프로브는 식염수와 닿으면 접촉 전위(수십~수백 mV)로 가짜 전압을 만들 수 있음 → 흑연 막대 2개 사용 권장, 대조군과 반드시 비교"));
        return v;
    }
}
