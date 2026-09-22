#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拠出金按分据置型の効果 — 所得代替率の推移（README §4.8 用の図）

現行制度と「3号廃止・拠出金按分据置型」の2本だけを、経済前提2ケース
（過去30年投影・高成長実現）× 内訳3種（計・報酬比例・基礎）で並べる。

  検証/3号廃止/図/所得代替率_按分据置.png

色は検証/3号廃止/図の他の図と揃える（系列を減らしても残った系列の色は
塗り替えない）。現行制度 #2a78d6 / 拠出金按分据置型 #1baf7a。
小さな多重図なので全ペアで検証済み（CVD ΔE 23.1、通常視 ΔE 24.0）。
緑は白背景でコントラストが 3:1 を下回るので、線の末尾に直接ラベルを付ける。

使い方: python3 検証/3号廃止/make_anbun_chart.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
_spec = importlib.util.spec_from_file_location(
    "sango", os.path.join(HERE, "analyze_sango.py"))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASES = (("3003", "過去30年投影ケース"), ("3001", "高成長実現ケース"))
SCEN = (("000", "現行制度", "#2a78d6"),
        ("501", "3号廃止・拠出金按分据置型", "#1baf7a"))
PANELS = (("rr_total", "所得代替率（計）"),
          ("rr_hirei", "うち報酬比例"),
          ("rr_kiso", "うち基礎"))
JISSHI = 2027                      # 実施年度
INK, INK2 = "#0b0b0b", "#52514e"   # 本文・補助の文字色
GRID = "#b8b7b2"


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

    runs = {}
    for case, _ in CASES:
        for yobi, label, _c in SCEN:
            r = _m.load_run(SUURI, case, yobi, yobi)
            if r is None:
                sys.exit(f"（未計算）{case} {label}。先に通常試算と予備番号501を流すこと")
            runs[(case, yobi)] = r

    fig, axes = plt.subplots(2, 3, figsize=(14.5, 10.2), sharey=True, sharex=True)
    for row, (case, cname) in enumerate(CASES):
        for col, (key, ttl) in enumerate(PANELS):
            ax = axes[row][col]
            yrs = [y for y in runs[(case, "000")][key] if 2024 <= y <= 2120]
            ends = []
            for yobi, label, color in SCEN:
                v = [runs[(case, yobi)][key][y] for y in yrs]
                ax.plot(yrs, v, color=color, lw=2.2, solid_capstyle="round",
                        label=label, zorder=3)
                ends.append([v[-1], v[-1], color])
            # 実施年度の目印
            ax.axvline(JISSHI, color=GRID, lw=0.9, ls=":", zorder=1)
            # 直接ラベル（値が近いと重なるので下から最小間隔だけ離す）
            ends.sort(key=lambda e: e[1])
            for i in range(1, len(ends)):
                if ends[i][0] - ends[i - 1][0] < 2.4:
                    ends[i][0] = ends[i - 1][0] + 2.4
            for pos, val, color in ends:
                ax.annotate(f"{val:.1f}", xy=(yrs[-1], pos),
                            xytext=(5, 0), textcoords="offset points",
                            color=color, fontsize=10, va="center")
            # 差を矢印で示す（計のパネルだけ）
            if col == 0:
                lo, hi = sorted(e[1] for e in ends)
                ax.annotate("", xy=(2105, hi), xytext=(2105, lo),
                            arrowprops=dict(arrowstyle="<->", color=INK2, lw=1.1))
                ax.annotate(f"+{hi - lo:.1f}pt", xy=(2103, (hi + lo) / 2),
                            ha="right", va="center", fontsize=10, color=INK2)
            if row == 0:
                ax.set_title(ttl, fontsize=12.5, pad=9, color=INK)
            if row == 1:
                ax.set_xlabel("年度", fontsize=10, color=INK2)
            ax.set_xlim(2024, 2140)
            ax.set_ylim(18, 64)
            ax.grid(alpha=0.22, lw=0.6)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(GRID)
            ax.tick_params(labelsize=9, color=GRID, labelcolor=INK2)
        axes[row][0].set_ylabel(f"{cname}\n所得代替率（％）", fontsize=10.5, color=INK)

    # 実施年度の注記は左上の1枚だけ
    axes[0][0].annotate(f"{JISSHI}年度\n実施", xy=(JISSHI, 20.5), xytext=(6, 0),
                        textcoords="offset points", fontsize=9, color=INK2, va="bottom")
    axes[0][0].legend(fontsize=10, loc="lower left", frameon=False,
                      bbox_to_anchor=(0.0, 0.14))

    fig.suptitle("第3号被保険者に保険料を課し、基礎年金拠出金の按分は据え置いた場合"
                 "\n所得代替率の推移（2027年度実施・全員納付）",
                 fontsize=14, y=0.985, color=INK)
    note = "\n".join((
        "読み方  縦の点線が実施年度。末尾の数値は2120年度で、給付水準の調整終了後の値にあたる。",
        "　　　　6面とも同じ所得代替率（％）なので、縦軸はすべて共有している。",
        "",
        "仕組み  3号から保険料を徴収するが、3号分の基礎年金費用は引き続き被用者年金が負担する。",
        "　　　　被用者年金の負担は1円も動かず（2027年度の拠出金 23.84兆円 → 24.11兆円）、",
        "　　　　公的年金全体の純増1.23兆円が丸ごと基礎年金の財源になる。",
        "",
        "結果　　基礎年金はマクロ経済スライドが不要になり、調整終了年度が2024年度になる。",
        "　　　　代わりに拠出金が高いまま残るので、過去30年投影では報酬比例が3.2ポイント下がる。",
        "　　　　基礎を国民年金の財政で先に決め、比例を厚生年金の財政で後から決める2段階均衡による。",
        "　　　　高成長実現では基礎年金が調整不要になった時点で全体も調整不要になり、比例は削られない。",
    ))
    fig.text(0.012, 0.010, note, ha="left", va="bottom", fontsize=9.5,
             color=INK2, linespacing=1.55)
    fig.tight_layout(rect=(0, 0.235, 1, 0.955))
    out = os.path.join(HERE, "図", "所得代替率_按分据置.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=140, facecolor="white")
    plt.close(fig)
    print("図:", out)


if __name__ == "__main__":
    main()
