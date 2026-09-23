#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拠出金按分据置型で3号の保険料はどこへ行くか — 国民年金勘定の年度末積立金

現行制度と「3号廃止・拠出金按分据置型」の2本を、経済前提2ケース
（過去30年投影・高成長実現）× 2つの物差しで並べる。

  左: 年度末積立金（2024年度価格、兆円）
  右: 積立度合（前年度末積立金 ÷ 当年度支出。仕様書 §8.1）

  検証/3号廃止/図/国年積立金_按分据置.png

名目額は100年で賃金とともに何十倍にもなるので、④の換算率 kakaku[]
（2004年度価格への換算率。公表の「2024年度価格」と同じ割り戻し）で
2024年度価格に直す（検証/オプション試算/README.md「2024年度価格の換算率」）。

色は make_anbun_chart.py と揃える（現行制度 #2a78d6 / 按分据置型 #1baf7a）。
緑は白背景でコントラストが 3:1 を下回るので、線の末尾に直接ラベルを付ける。

使い方: python3 検証/3号廃止/make_tumitate_chart.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
import compare_option as co  # noqa: E402

BAS = os.path.join(ROOT, "work", "suuri", "rev2024", "bas", "rslt")
CASES = (("3003", "過去30年投影ケース"), ("3001", "高成長実現ケース"))
SCEN = (("000", "現行制度", "#2a78d6"),
        ("501", "3号廃止・拠出金按分据置型", "#1baf7a"))
JISSHI = 2027
Y0, Y1 = 2024, 2119                # 国民年金の収支見通しは2119年度まで
INK, INK2 = "#0b0b0b", "#52514e"
GRID = "#b8b7b2"


def load(case):
    ver = f"{case}-{case}-{case}-{case}"
    kk = co.read_kakaku(ver, "000", BAS)
    out = {}
    for yobi, _l, _c in SCEN:
        nat = co.read_nat(ver, yobi, BAS)
        yrs = [y for y in range(Y0, Y1 + 1) if y in nat]
        out[yobi] = {
            "yrs": yrs,
            "tumitate": [nat[y]["年度末積立金"] * kk[Y0] / kk[y] for y in yrs],
            "doai": [nat[y].get("積立度合") for y in yrs],
        }
    # 3号の保険料のうち、国年勘定が給付水準の上昇分として実際に使った割合
    # （保険料増と実負担増＝拠出金−国庫負担の増を、2024年度価格で累計）
    b, s = co.read_nat(ver, "000", BAS), co.read_nat(ver, "501", BAS)
    prem = used = 0.0
    for y in range(JISSHI, Y1 + 1):
        f = kk[Y0] / kk[y]
        prem += (s[y]["保険料収入"] - b[y]["保険料収入"]) * f
        used += ((s[y]["基礎年金拠出金"] - s[y]["国庫負担"])
                 - (b[y]["基礎年金拠出金"] - b[y]["国庫負担"])) * f
    out["share_used"] = used / prem
    out["prem"] = prem
    return out


def main():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        sys.exit("matplotlib が要ります: pip install matplotlib")
    for fp in ("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
               "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"):
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False

    data = {case: load(case) for case, _ in CASES}

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.4), sharex=True)
    axes[1][0].sharey(axes[0][0])
    axes[1][1].sharey(axes[0][1])
    PANELS = (("tumitate", "年度末積立金（2024年度価格、兆円）", "{:.0f}兆円"),
              ("doai", "積立度合（前年度末積立金 ÷ 当年度支出、年分）", "{:.0f}年分"))
    for row, (case, cname) in enumerate(CASES):
        d = data[case]
        for col, (key, ttl, fmt) in enumerate(PANELS):
            ax = axes[row][col]
            ends = []
            for yobi, label, color in SCEN:
                yrs = [y for y, v in zip(d[yobi]["yrs"], d[yobi][key]) if v is not None]
                v = [v for v in d[yobi][key] if v is not None]
                ax.plot(yrs, v, color=color, lw=2.2, solid_capstyle="round",
                        label=label, zorder=3)
                ends.append((yrs[-1], v[-1], color))
            if key == "doai":
                ax.axhline(1.0, color=INK2, lw=1.0, ls="--", zorder=2)
            ax.axvline(JISSHI, color=GRID, lw=0.9, ls=":", zorder=1)
            for x, val, color in ends:
                ax.annotate(fmt.format(val), xy=(x, val), xytext=(5, 0),
                            textcoords="offset points", va="center",
                            fontsize=10, color=INK, fontweight="bold")
            ax.set_title(f"{cname}｜{ttl}", fontsize=11.5, pad=8, color=INK, loc="left")
            ax.set_xlim(Y0, Y1 + 12)
            top = max(max(v for v in data[c][yb][key] if v is not None)
                      for c, _ in CASES for yb, _l, _c in SCEN)
            ax.set_ylim(0, top * 1.08)
            ax.grid(axis="y", color=GRID, lw=0.6, alpha=0.6)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(GRID)
            ax.tick_params(colors=INK2, labelsize=9.5)
        axes[row][0].annotate(
            f"3号の保険料（2024年度価格で累計 {d['prem']:.0f}兆円）のうち\n"
            f"国民年金勘定が給付に使ったのは {d['share_used'] * 100:.0f}%",
            xy=(0.03, 0.93), xycoords="axes fraction", va="top", fontsize=10,
            color=INK, bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID))
    axes[0][0].annotate(f"{JISSHI}年度\n実施", xy=(JISSHI, 0), xytext=(5, 4),
                        textcoords="offset points", fontsize=9, color=INK2, va="bottom")
    h, lb = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lb, loc="upper center", ncol=2, frameon=False, fontsize=11,
               bbox_to_anchor=(0.5, 0.925))
    fig.suptitle("拠出金按分据置型では、3号の保険料の大半が国民年金の積立金に積み上がる",
                 fontsize=14.5, y=0.985, color=INK)
    note = "\n".join((
        "読み方  縦の点線が実施年度。金額は④の換算率 kakaku[] で2024年度価格に割り戻した値（公表の「2024年度価格」と同じ）。",
        "　　　　左右とも、同じ列の2ケースは縦軸を共有している。右の破線は有限均衡の目標（2120年度に積立度合1年分）。",
        "",
        "仕組み  基礎年金の給付水準は国民年金勘定の財政だけで決まる（2段階均衡、仕様書 §8.2）。按分据置型では3号の保険料が",
        "　　　　国民年金勘定に入るのに、拠出金を負担する頭数は増えないので、国民年金はすぐに黒字になる。基礎年金はマクロ経済",
        "　　　　スライドが不要（カット率の上限）に張りつき、それ以上は給付に使い道がない。残りは運用収入とともに積み上がる。",
        "",
        "注意　　右の按分据置型は有限均衡（2120年度に1年分）から大きく外れている。基礎年金の水準は均衡解ではなく天井に",
        "　　　　当たった値で、上がった水準の費用の大半は厚生年金（報酬比例の削減）と国庫負担が払っている（README §4.7）。",
        "",
        "非公式の独自計算。厚生労働省の試算ではない。",
    ))
    fig.text(0.012, 0.008, note, ha="left", va="bottom", fontsize=9.3,
             color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.24, 1, 0.90))
    out = os.path.join(HERE, "図", "国年積立金_按分据置.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)
    for case, cname in CASES:
        d = data[case]
        print(f"  {cname}: 保険料累計 {d['prem']:.1f}兆円（2024年度価格）、使われた割合 {d['share_used']*100:.1f}%")


if __name__ == "__main__":
    main()
