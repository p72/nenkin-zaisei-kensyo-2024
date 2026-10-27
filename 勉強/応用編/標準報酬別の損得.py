#!/usr/bin/env python3
"""厚生年金の国庫負担を廃止して国民全員に一律給付したら（財政均衡）：標準報酬月額別・世代別の損得（思考実験・非公式・推定）。

「…国民全員に一律給付したら」の案（予備番号701）を、会社員の標準報酬月額ごとに、生まれた年度ごとの
受給総額の増減で見る。経済前提は3つ並べる。

  3003  過去30年投影（公式）
  3901  独自の前提A：実質（賃金・運用利回り・人口・労働力）は過去30年投影のまま、物価だけ2026年度から2.0%。
        2025年度は実績（物価 +2.6%：総務省 CPI 総合の年度平均、実質賃金 −0.5%：毎月勤労統計の年度確報）
  3001  高成長実現（公式）

受給総額の増減（65歳時点の価値・2024年度の物価、年金と同じ実質の運用利回りで換算）
  単身 ＝ 0〜64歳の一律給付を65歳まで運用した額 ＋ 65歳以降の一律給付 − 報酬比例のカット × 標準報酬の割合
  夫婦 ＝ 一律給付は2人分。カットは夫の報酬比例と、夫が先に亡くなったあとの妻の遺族厚生年金（3/4）
  標準報酬の割合 ＝ 標準報酬月額 ÷ 平均（賞与込みの月額換算、2024年度 約42.6万円）。40年間ずっと同じ割合とする
  生存率・一律給付・報酬比例・カット率は 世代別の損得.py と同じ（平均の値はその記事と一致する）

使い方（リポジトリの直下で）
  python3 勉強/応用編/標準報酬別の損得.py econ        # 独自の前提A の経済前提 econ-3901.csv を作る
  検証/実行/run_pipeline.sh 3901 1 1 0 2              # その通常試算（過去30年投影と同じ労働参加漸進）
  python3 勉強/応用編/国庫負担の廃止.py run 3901       # 701・702（3003・3001 も同じように流しておく）
  python3 勉強/応用編/標準報酬別の損得.py report      # 記事の表
  python3 勉強/応用編/標準報酬別の損得.py graph       # 記事の図（勉強/応用編/図/）
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


G = _load("sedai", "世代別の損得.py")
K = G.K
CASES = (("3003", "過去30年投影"), ("3901", "独自の前提A（物価2%）"), ("3001", "高成長実現"))
LEVELS = (88000, 150000, 200000, 300000, None, 650000)     # None は平均（賞与込みの月額換算）
COHORTS = range(1940, 2061)
_CACHE = {}


def econ():
    """econ-3003.csv を写し、物価（7列目）と2025年度の実質賃金（4〜6列目）だけ書き換えて econ-3901.csv を作る。"""
    d = os.path.join(K.SUURI, "emp", "data", "u-rev", "econ")
    out = []
    for line in open(os.path.join(d, "econ-3003.csv")):
        f = line.rstrip("\n").split(",")
        y = int(f[0])
        if y == 25:            # 2025年度の実績
            f[3] = f[4] = f[5] = "-0.5"
            f[6] = "2.6"
        elif y >= 26:          # 2026年度以降の物価
            f[6] = "2"
        out.append(",".join(f))
    p = os.path.join(d, "econ-3901.csv")
    open(p, "w").write("\n".join(out) + "\n")
    print("書き出し:", p)


def keisan(case):
    """{生年度: dict(s, sc, f, fc)}（万円）と平均の標準報酬（円）・カット率。
    s・f は一律給付の分（単身・夫婦）、sc・fc は平均の人の報酬比例のカットの分。"""
    if case in _CACHE:
        return _CACHE[case]
    S, SV = G._series(case, "unyo"), G._survival(case)
    R = S["R"]
    out = {}
    for c in COHORTS:
        hb = S["hirei"](c + 65)
        pre = 0.0
        for a in range(65):
            pre = (pre + S["ichi"]["zenin"].get(c + a, 0.0)) * (1 + R[c + a + 1])
        sm = sf = d = 1.0
        bs = bf = cs = cf = 0.0
        for a in range(65, G.AGE_MAX + 1):
            y = c + a
            if a > 65:
                sm *= SV["1"](a, y)
                sf *= SV["2"](a, y)
                d /= 1 + R[y]
            ic = S["ichi"]["zenin"].get(y, 0.0)
            bs += d * sm * ic
            bf += d * (sm + sf) * ic
            if y >= G.START:
                cs += d * sm * hb * S["cut"]
                cf += d * (sm + sf * (1 - sm) * 0.75) * hb * S["cut"]
        out[c] = dict(s=(pre + bs) / 1e4, sc=cs / 1e4, f=(2 * pre + bf) / 1e4, fc=cf / 1e4)
    _CACHE[case] = (out, S["W"][2024], S["cut"])
    return _CACHE[case]


def songoku(case, typ, x):
    """標準報酬月額 x（円。None は平均）の世帯の、生年度ごとの受給総額の増減（万円）。typ は "s"（単身）・"f"（夫婦）。"""
    L, W24, _ = keisan(case)
    k = 1.0 if x is None else x / W24
    return {c: L[c][typ] - k * L[c][typ + "c"] for c in L}


def tenkan(v):
    """損から得に変わる生年度（最後に損だった年度の次）。ずっと得なら None、2060年度まで損なら '—'。"""
    neg = [c for c in v if v[c] < 0]
    if not neg:
        return None
    return max(neg) + 1 if max(neg) < max(v) else "—"


def label(x, W24):
    if x is None:
        return f"{W24 / 1e4:.1f}万円（平均・賞与込み）"
    return {88000: "8.8万円（最低等級）", 650000: "65万円（上限）"}.get(x, f"{x / 1e4:.0f}万円")


def getsu(case):
    """平均の会社員の月額（2024年度の物価）：報酬比例の現行・カット後、基礎年金1人分、一律給付1人分。"""
    co, _ = K._modules()
    out = {}
    for yobi in ("000", "701"):
        p = co.find_one(f"03summary.{case}-{case}-{case}-{case}-1120-{yobi}*_08sum.csv", K.SH)
        L = co.lines_of(p)
        hi = [i for i, l in enumerate(L) if l.startswith("年度,物価")][0]
        for l in L[hi + 1:]:
            f = [x.strip() for x in l.split(",")]
            if not f or not f[0].isdigit():
                break
            y = 2000 + int(f[0])
            out.setdefault(y, {})[yobi] = (float(f[22]), float(f[23]) / 2)   # 比例・基礎1人分（物価割り戻し）
    s = K.shinkyufu(case, "zenin")
    return {y: dict(hirei=out[y]["000"][0], hirei_cut=out[y]["701"][0], kiso=out[y]["000"][1], ichi=s[y]["getsu_r"])
            for y in (2027, 2060)}


def report():
    for case, cname in CASES:
        L, W24, cut = keisan(case)
        s = K.shinkyufu(case, "zenin")
        rb = K._modules()[0].read_rate(f"{case}-{case}-{case}-{case}", "000", K.SH)
        rc = K._modules()[0].read_rate(f"{case}-{case}-{case}-{case}", "701", K.SH)
        print(f"## {cname}（{case}）\n")
        print(f"- 報酬比例の一律カット {cut * 100:.1f}%。所得代替率（2120年度）現行 {rb[2120]['所得代替率'] * 100:.1f}% → "
              f"カット後 {rc[2120]['所得代替率'] * 100:.1f}%")
        print("- 一律給付（1人・月額・2024年度の物価）：" + "、".join(
            f"{y}年度 {s[y]['getsu_r']:,.0f}円（手取りの{s[y]['wari']:.1f}%）" for y in (2027, 2040, 2060, 2100)))
        g = getsu(case)
        for y in (2027, 2060):
            m = g[y]
            d = m["hirei_cut"] - m["hirei"]
            print(f"- {y}年度 平均の会社員：報酬比例 {m['hirei']:,.0f}円 → {m['hirei_cut']:,.0f}円（{d:+,.0f}円）、"
                  f"一律給付 1人 {m['ichi']:,.0f}円 → 差し引き 単身 {d + m['ichi']:+,.0f}円、夫婦 {d + 2 * m['ichi']:+,.0f}円")
        for typ, tname in (("s", "単身（会社員40年の男）"), ("f", "夫婦（会社員の夫＋専業の妻。標準報酬月額は夫）")):
            print(f"\n### {tname}（万円）\n")
            print("| 標準報酬月額 | 1962年度生まれ | 1970 | 1980 | 1990 | 2000 | 2010 | 損から得に変わる生年度 |")
            print("|---|---|---|---|---|---|---|---|")
            for x in LEVELS:
                v = songoku(case, typ, x)
                t = tenkan(v)
                tt = "どの世代も得" if t is None else (f"{t}年度" if t != "—" else "2060年度まで損")
                print(f"| {label(x, W24)} | " + " | ".join(f"{v[c]:+,.0f}" for c in (1962, 1970, 1980, 1990, 2000, 2010))
                      + f" | {tt} |")
        print()


NOTE = ("非公式：厚生労働省の試算ではない。2024年財政検証の計算プログラムに独自のレバー（国庫負担の廃止と報酬比例の一律カット）を加えた試算から推定。"
        "受給総額は65歳以降の年金＋一律給付（0〜64歳の分は65歳まで運用して足す）を、将来推計人口から作った生存率で重み付けし、"
        "年金と同じ実質の運用利回りで65歳時点の価値（2024年度の物価）にしたもの。標準報酬月額は2024年度の賃金水準で、"
        "40年間ずっと平均（賞与込みの月額換算）に対して同じ割合の会社員とした。基礎年金は40年納付。夫婦は専業の妻、夫が先に亡くなれば遺族厚生年金（報酬比例の3/4）。"
        "独自の前提Aは、実質は過去30年投影のまま物価だけ2%にしたもの。点線は1962年度生まれ（2027年度に65歳）。縦軸の範囲を超えた部分は切れている。")


def graph():
    matplotlib, plt = G._fig_base()
    # 標準報酬月額は大きさの違いなので、同じ色相の濃淡で表す（低い報酬ほど薄く）
    cols = ("#f2a65a", "#e07b39", "#c4562a", "#9c3a1f", "#6b2615", "#3a130a")
    fig, ax = plt.subplots(2, 3, figsize=(17, 10.5), sharex=True, sharey=True)
    cs = [c for c in COHORTS if c <= 2030]
    for j, (case, cname) in enumerate(CASES):
        _, W24, cut = keisan(case)
        for i, (typ, tname) in enumerate((("s", "単身（会社員40年の男）"), ("f", "夫婦（会社員の夫＋専業の妻）"))):
            a = ax[i][j]
            a.axhspan(-2000, 0, color="#fbeee8", zorder=0)
            for x, col in zip(LEVELS, cols):
                v = songoku(case, typ, x)
                a.plot(cs, [v[c] for c in cs], color=col, lw=2.1, label=f"標準報酬月額 {label(x, W24)}")
                t = tenkan(v)
                if isinstance(t, int) and t <= 2030:
                    a.plot([t], [0], "o", color=col, ms=5, zorder=5)
            a.axhline(0, color="#555", lw=0.9)
            a.axvline(1962, color="#999", lw=0.8, ls=":")
            a.set_ylim(-900, 1600)
            a.set_xlim(1938, 2032)
            a.grid(True, color="#ddd", lw=0.6)
            a.spines[["top", "right"]].set_visible(False)
            G._secx(a)
            a.set_title(f"{cname}（報酬比例 −{cut * 100:.1f}%）\n{tname}", fontsize=10.5)
            a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
            if i == 1:
                a.set_xlabel("生まれた年度（上の目盛りは65歳になる年度）")
            if j == 0:
                a.set_ylabel("受給総額の増減（万円、65歳時点・今の物価）")
    h, l = ax[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.955))
    fig.suptitle("厚生年金の国庫負担を廃止して国民全員に一律給付（財政均衡）：標準報酬月額別・世代別の損得（非公式の思考実験）"
                 "　●は損から得に変わる生まれ年度", fontsize=12.5, y=0.99)
    G._note(fig, NOTE)
    fig.tight_layout(rect=(0, 0.07, 1, 0.9))
    out = os.path.join(HERE, "図", "標準報酬別の損得.png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"econ": econ, "report": report, "graph": graph}[cmd]()
