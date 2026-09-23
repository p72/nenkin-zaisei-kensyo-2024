#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拠出金按分据置型 — 基礎年金の国庫負担の推移

  図/国庫負担_按分据置.png

基礎年金の国庫負担（全制度計）を2024年度価格（④の換算率 kakaku[] で賃金で
割り戻す。公表の慣行）で、経済前提2ケースについて描く。

  現行制度                         #2a78d6
  3号廃止・拠出金按分据置型          #1baf7a
  同・余剰を国庫負担の軽減に回した場合 #1baf7a 破線（按分据置型の変種なので同じ色）

3本目は概算で、按分据置型の国庫負担から、国民年金勘定の余剰（運用収入を除く
収支差の増）を毎年そのまま差し引いたもの。国年分の国庫負担割合を解く正式な
オプションではない。

使い方: python3 検証/3号廃止/make_kokko_chart.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
import compare_option as co  # noqa: E402

_spec = importlib.util.spec_from_file_location("sango", os.path.join(HERE, "analyze_sango.py"))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)
_st = importlib.util.spec_from_file_location("tumi", os.path.join(HERE, "make_tumitate_chart.py"))
_t = importlib.util.module_from_spec(_st)
_st.loader.exec_module(_t)

SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
BAS = os.path.join(SUURI, "bas", "rslt")
CASES = (("3003", "過去30年投影ケース"), ("3001", "高成長実現ケース"))
C_BASE, C_ANBUN = "#2a78d6", "#1baf7a"
JISSHI, Y0, Y1 = 2027, 2024, 2119
INK, INK2, GRID = "#0b0b0b", "#52514e", "#b8b7b2"


def load(case):
    ver = f"{case}-{case}-{case}-{case}"
    kk = co.read_kakaku(ver, "000", BAS)
    D = _t.discount(case)
    rb, rs = _m.load_run(SUURI, case, "000", "000"), _m.load_run(SUURI, case, "501", "501")
    b, s = co.read_nat(ver, "000", BAS), co.read_nat(ver, "501", BAS)
    yrs = list(range(Y0, Y1 + 1))
    f = {y: kk[Y0] / kk[y] for y in yrs}
    base = [rb["kokko_total"][y] / 1e12 * f[y] for y in yrs]
    anbun = [rs["kokko_total"][y] / 1e12 * f[y] for y in yrs]
    yojo = [((s[y]["収支差引残"] - b[y]["収支差引残"]) - (s[y]["運用収入"] - b[y]["運用収入"])) * f[y]
            if y >= JISSHI else 0.0 for y in yrs]
    offset = [a - e for a, e in zip(anbun, yojo)]
    # 2027〜2119年度の累積の現在価値（本文の数字）
    pv = lambda xs: sum(x / f[y] * D[y] for y, x in zip(yrs, xs) if y >= JISSHI)  # noqa: E731
    return {"yrs": yrs, "base": base, "anbun": anbun, "offset": offset,
            "pv_base": pv(base), "pv_up": pv(anbun) - pv(base), "pv_yojo": pv(yojo)}


def compare(case):
    """基礎年金を上げる設計どうしで、国庫負担の増を比べる（2027〜2119年度の現在価値）。

    国庫負担は法定で基礎年金の1/2なので、どの設計でも「国庫負担の増 ÷ 基礎年金
    拠出金（全制度計）の増」は 0.50 になる。按分据置型に特有の費用ではなく、
    基礎年金を上げる目的の値段であることを示す。"""
    D = _t.discount(case)
    runs = {k: _m.load_run(SUURI, case, y5, y4) for k, y5, y4 in
            (("000", "000", "000"), ("100", "100", "101"),
             ("510", "510", "511"), ("501", "501", "501"))}
    pv = lambda r, key: sum(r[key][y] / 1e12 * D[y] for y in range(JISSHI, Y1 + 1))  # noqa: E731
    k0, c0 = pv(runs["000"], "kokko_total"), pv(runs["000"], "kyo_total")
    rows = []
    for k, label in (("100", "現行＋調整期間の一致"), ("510", "3号廃止＋調整期間の一致"),
                     ("501", "拠出金按分据置型")):
        dk = pv(runs[k], "kokko_total") - k0
        dc = pv(runs[k], "kyo_total") - c0
        rows.append((label, runs[k]["rr_kiso"][2120], dc, dk, dk / k0, dk / dc))
    return k0, rows


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
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.4), sharey=True)
    for ax, (case, cname) in zip(axes, CASES):
        d = data[case]
        series = (("base", "現行制度", C_BASE, "-"),
                  ("anbun", "3号廃止・拠出金按分据置型", C_ANBUN, "-"),
                  ("offset", "同・国民年金の余剰を国庫負担の軽減に回した場合（概算）", C_ANBUN, "--"))
        ends = []
        for key, label, color, ls in series:
            ax.plot(d["yrs"], d[key], color=color, lw=2.2, ls=ls, label=label, zorder=3)
            ends.append(d[key][-1])
        # 末尾ラベル（近い値は重ならないように離す）
        order = sorted(range(3), key=lambda i: ends[i])
        pos = [ends[i] for i in order]
        for i in range(1, 3):
            pos[i] = max(pos[i], pos[i - 1] + 0.8)
        for i, p in zip(order, pos):
            ax.annotate(f"{ends[i]:.1f}兆円", xy=(d["yrs"][-1], ends[i]), xytext=(d["yrs"][-1] + 1.5, p),
                        textcoords="data", va="center", fontsize=10, color=INK)
        up = d["pv_up"] / d["pv_base"]
        ax.annotate(f"国庫負担の増（2027〜2119年度、現在価値）\n"
                    f"{d['pv_up']:.0f}兆円＝現行の {up * 100:.0f}% 増\n"
                    f"余剰で埋まるのはその {d['pv_yojo'] / d['pv_up'] * 100:.0f}%",
                    xy=(0.36, 0.97), xycoords="axes fraction", va="top", fontsize=10, color=INK,
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID))
        ax.set_title(f"{cname}｜基礎年金の国庫負担（全制度計、2024年度価格、兆円／年）",
                     fontsize=11.5, pad=8, color=INK, loc="left")
        ax.set_xlim(Y0, Y1 + 16)
        ax.set_ylim(0, 16)
        ax.grid(axis="y", color=GRID, lw=0.6, alpha=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=9.5)
        ax.axvline(JISSHI, color=GRID, lw=0.9, ls=":", zorder=1)
    axes[0].annotate(f"{JISSHI}年度\n実施", xy=(JISSHI, 0), xytext=(5, 4),
                     textcoords="offset points", fontsize=9, color=INK2, va="bottom")
    h, lb = axes[0].get_legend_handles_labels()
    fig.legend(h, lb, loc="upper center", ncol=3, frameon=False, fontsize=10.5,
               bbox_to_anchor=(0.5, 0.915))
    fig.suptitle("拠出金按分据置型の国庫負担 — 国民年金の余剰では一部しか埋まらない",
                 fontsize=14.5, y=0.985, color=INK)
    note = "\n".join((
        "読み方  縦の点線が実施年度。金額は④の換算率 kakaku[] で2024年度価格（賃金で割り戻し）にした年あたりの国庫負担。",
        "　　　　破線は、国民年金勘定の余剰（運用収入を除く収支差の増）を毎年そのまま国庫負担から差し引いた概算。",
        "　　　　枠内の現在価値は、④の名目運用利回りで2024年度末に割り引いた2027〜2119年度の累積。",
        "",
        "仕組み  基礎年金の水準が上がると、費用は拠出金の頭数（約5,000万人）すべてにかかり、その半分が国庫負担になる。",
        "　　　　国民年金勘定の余剰は第1号の頭数分からしか生まれないので、構造的に届かない。時期もずれていて、",
        "　　　　余剰は実施直後が大きく（破線が現行を下回る）、国庫負担の増は後年に膨らむ。",
        "",
        "非公式の独自計算。厚生労働省の試算ではない。",
    ))
    fig.text(0.012, 0.008, note, ha="left", va="bottom", fontsize=9.3, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.25, 1, 0.88))
    out = os.path.join(HERE, "図", "国庫負担_按分据置.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)
    for case, cname in CASES:
        d = data[case]
        print(f"  {cname}: 現在価値 現行 {d['pv_base']:.1f} / 増 {d['pv_up']:.1f}（+{d['pv_up']/d['pv_base']*100:.0f}%）"
              f" / 余剰 {d['pv_yojo']:.1f}（{d['pv_yojo']/d['pv_up']*100:.0f}%）兆円")
    print("\n基礎年金を上げる設計の比較（2027〜2119年度、2024年度末の現在価値、兆円）")
    print("| ケース | 設計 | 基礎（2120年度） | 基礎年金の費用の増 | 国庫負担の増 | 比 |")
    print("|---|---|---|---|---|---|")
    for case, cname in CASES:
        k0, rows = compare(case)
        for label, kiso, dc, dk, rel, ratio in rows:
            print(f"| {cname} | {label} | {kiso:.2f}% | {dc:.1f} | {dk:.1f}（+{rel*100:.0f}%） | {ratio:.2f} |")


if __name__ == "__main__":
    main()
