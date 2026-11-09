#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""マクロ経済スライドの調整期間を一致させたら、年金のバランスシート（財源と給付）はどう変わるか

「過去期間の給付と二重の負担」（二重の負担.py）と同じ計算を、調整期間の一致（TOUGOU=1）で行い、現行制度と並べる。

  現行制度        予備番号 000（通常試算・過去分試算・受給者分試算）
  調整期間の一致  通常試算は⑤ 100・④ 101（統一カット率）、過去分試算・受給者分試算は 101

調整期間の一致では、⑤が厚生年金と国民年金を一体で均衡させるので、⑤の要約（全厚年１）に国民年金が合算されている。
全体の合計はその要約をそのまま使う（二重の負担.py の RUN_TOUGOU）。過去分試算・受給者分試算は、
統一カット率（cuta・cutb-…-101）を読んで流す。④の過去分試算は bas/rslt の cuta-…-101 を読むが、
調整期間の一致の④の2周目はこのファイルを空のまま残すので、⑤が書いた統一カット率を写してから流す。

使い方（リポジトリの直下で。3003 は人口・労働力率の引数 1 1 0 2、3002 は引数なし）:
  # 現行制度：二重の負担.py の手順（通常試算・SAIMU=1・SAIMU=2）
  TOUGOU=1 YOBI=100 YOBI2=101 STEPS=45 SKIP_BUILD=1 検証/実行/run_pipeline.sh 3003 1 1 0 2
  cp work/suuri/rev2024/emp/rslt/ez_arev/cutr/cuta-3003-3003-3003-3003-1120-101.csv \\
     work/suuri/rev2024/bas/rslt/cuta-3003-3003-3003-3003-1120-101.csv
  SAIMU=1 YOBI=101 STEPS=45 SKIP_BUILD=1 検証/実行/run_pipeline.sh 3003 1 1 0 2
  SAIMU=2 YOBI=101 STEPS=45 SKIP_BUILD=1 検証/実行/run_pipeline.sh 3003 1 1 0 2
  python3 勉強/応用編/調整期間の一致のバランスシート.py   # 表と図（勉強/応用編/図/調整期間の一致_*.png）
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("nijuu", os.path.join(HERE, "二重の負担.py"))
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)

CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"))
LABEL = {"gen": "現行制度", "tg": "調整期間の一致"}
Y0, Y1 = N.Y0, N.Y1


def keisan(case):
    out = {}
    for k, run in (("gen", N.RUN_GENKOU), ("tg", N.RUN_TOUGOU)):
        o = N.keisan(case, run)
        if o is None:
            return None
        d = N.load(case, "", run)
        mid, end = N.factors(d["rate"])
        o["kiso_nen"] = d["kiso"]
        o["nikai_nen"] = N.add(d["dok"], d["kn2"], d["fuku"])
        o["tumiK_pv"] = {y: v / end[y] for y, v in d["kou"]["tumi"].items() if Y0 <= y <= Y1}
        o["tumiN_pv"] = {y: v / end[y] for y, v in d["kn"]["tumi"].items() if Y0 <= y <= Y1}
        o["tumiN_nen"] = d["kn"]["tumi"]
        z = o["seido"] = N.seido(case, o, run)
        z["kyuK"], z["kyuN"] = z["kyuK_p"] + z["kyuK_f"], z["kyuN_p"] + z["kyuN_f"]
        z["kokK"], z["kokN"] = z["kokK_p"] + z["kokK_f"], z["kokN_p"] + z["kokN_f"]
        z["tumiK"], z["tumiN"] = z["t24K"] - z["t120K"], z["t24N"]
        # 国民年金の給付のうち、国民年金の財源（保険料・国庫負担・2024年度末の積立金）で足りない分。
        # 一体で均衡させる調整期間の一致では、被用者年金の財源から回る（現行制度はほぼ0なので0とみなす）
        S = z["kyuN"] - (z["hokN"] + z["kokN"] + z["t24N"])
        z["S"] = max(S, 0.0)
        z["S_raw"] = S
        z["tumiK"] = z["kyuK"] + z["S"] - z["hokK"] - z["kokK"]     # 被用者年金の積立金からの財源（残り）
        z["hokN_f_disp"] = z["kyuN_f"] - z["kokN_f"] - z["S"]
        out[k] = o
    return out


def f0(x):
    return f"{x:,.0f}"


def main():
    res = {}
    for case, name in CASES:
        r = keisan(case)
        if r is None:
            print(f"（未計算）{name}", file=sys.stderr)
            continue
        res[case] = r
        g, t = r["gen"], r["tg"]
        print(f"\n## {name}ケース（兆円、2024年度末の価値）\n")
        print("| 項目 | 現行制度 | 調整期間の一致 | 差 |")
        print("|---|---|---|---|")
        rows = [("**財源**", None), ("保険料", "hoken"), ("国庫負担", "kokko"), ("　過去期間に係る分", "kokko_kako"),
                ("　将来期間に係る分", "kokko_shorai"), ("積立金から得られる財源", "tumi"),
                ("2120年度末の積立金（現在価値）", "tumi120"),
                ("**給付**", None), ("給付の合計（2025〜2120年度）", "kyufu"), ("過去期間に係る給付", "kako"),
                ("　2階部分", "kako2"), ("　基礎年金分", "kakok"), ("　うち、いまの受給者の分", "jukyu"),
                ("　　2階部分", "jukyu2"), ("　　基礎年金分", "jukyuk"),
                ("将来期間に係る給付", "shorai"), ("　2階部分", "shorai2"), ("　基礎年金分", "shoraik")]
        for lab, k in rows:
            if k is None:
                print(f"| {lab} | | | |")
            else:
                print(f"| {lab} | {f0(g[k])} | {f0(t[k])} | {t[k] - g[k]:+,.0f} |")
        print(f"\n検算（調整期間の一致）：財源の合計 {f0(t['hoken'] + t['kokko'] + t['tumi'])} ／ 給付の合計 {f0(t['kyufu'])}")
        print("\n制度別（兆円、2024年度末の価値）\n")
        print("| 項目 | 被用者年金：現行 | 被用者年金：一致 | 国民年金：現行 | 国民年金：一致 |")
        print("|---|---|---|---|---|")
        zg, zt = g["seido"], t["seido"]
        for lab, kK, kN in (("給付の合計", "kyuK", "kyuN"), ("　過去期間", "kyuK_p", "kyuN_p"), ("　将来期間", "kyuK_f", "kyuN_f"),
                            ("　うち基礎年金（過去期間）", "kiso_pK", "kiso_pN"), ("　うち基礎年金（将来期間）", "kiso_fK", "kiso_fN"),
                            ("財源：保険料", "hokK", "hokN"), ("財源：国庫負担", "kokK", "kokN"),
                            ("財源：積立金", "tumiK", "tumiN")):
            print(f"| {lab} | {f0(zg[kK])} | {f0(zt[kK])} | {f0(zg[kN])} | {f0(zt[kN])} |")
        print(f"| 被用者年金の財源から国民年金の給付に回る分 | | | {zg['S_raw']:,.1f}（≒0） | {zt['S']:,.1f} |")
        print(f"| 国民年金の給付の割合 | | | {zg['kyuN'] / (zg['kyuK'] + zg['kyuN']) * 100:.1f}% | "
              f"{zt['kyuN'] / (zt['kyuK'] + zt['kyuN']) * 100:.1f}% |")
        neg = [y for y in sorted(t["tumiN_nen"]) if y > Y0 and t["tumiN_nen"][y] < 0]
        print(f"国民年金勘定（④）の積立金がマイナスになる年度：{neg[0] if neg else 'なし'}　"
              f"2120年度末（現在価値）：国民年金 {t['tumiN_pv'][Y1]:,.1f}、厚生年金 {t['tumiK_pv'][Y1]:,.1f}")
    if "--no-fig" not in sys.argv and res:
        zu(res)
        zu_seido(res)
        zu_size(res)
        zu_nijuu(res)


# ---------------------------------------------------------------------------- 図
C = dict(hoken="#f2a27e", kokko="#1baf7a", tumi="#8c8c8c", kakok="#1f5fae", kako2="#7fb1e8", shoraik="#5a8f8f",
         shorai2="#b5d6d6", kiso="#1f5fae", nikai="#eb6834", kou="#1f5fae", kn="#1baf7a")
DARK = {"#8c8c8c", "#1baf7a", "#1f5fae", "#5a8f8f"}
INK, INK2, GRID = N.INK, N.INK2, N.GRID
NOTE = ("非公式：2024年財政検証の計算プログラム（通常試算・過去分試算・受給者分試算、現行制度と調整期間の一致）の出力を、"
        "名目運用利回りで2024年度末の価値に直した再現と推定。厚生労働省の試算ではない。\n"
        "調整期間の一致の過去分試算・受給者分試算は、統一カット率を読ませて流した。割り引きは年度の真ん中、「福祉」欄は給付の割合で按分（推定）。")


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _style(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def _save(fig, name):
    d = os.path.join(HERE, "図")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"調整期間の一致_{name}.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)


def zu(res):
    plt = _plt()
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    cases = [(c, n) for c, n in CASES if c in res]

    # ---- 図1 比較型のバランスシート
    fig, axs = plt.subplots(1, len(cases), figsize=(7.6 * len(cases), 8.2), squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        w = 0.36
        for x0, k in ((0.0, "gen"), (1.25, "tg")):
            d = res[c][k]
            zai = [(d["tumi"], C["tumi"]), (d["kokko"], C["kokko"]), (d["hoken"], C["hoken"])]
            kyu = [(d["kakok"], C["kakok"]), (d["kako2"], C["kako2"]), (d["shoraik"], C["shoraik"]),
                   (d["shorai2"], C["shorai2"])]
            for x, segs in ((x0, zai), (x0 + w + 0.04, kyu)):
                b = 0.0
                for v, col in segs:
                    ax.bar(x, v, w, bottom=b, color=col, edgecolor="white", lw=1.2)
                    if v > 55:
                        ax.text(x, b + v / 2, f"{v:,.0f}", ha="center", va="center", fontsize=9.5,
                                color="white" if col in DARK else INK)
                    b += v
            ax.plot([x0 + w / 2 + 0.04 - w / 2 - 0.02, x0 + w + 0.04 + w / 2 + 0.02], [d["kako"]] * 2,
                    color=INK, lw=1, ls="--")
            ax.text(x0 + w / 2 + 0.02, -150, f"{LABEL[k]}\n財源　給付", ha="center", va="top", fontsize=10, color=INK)
            ax.text(x0 + w / 2 + 0.02, d["kyufu"] + 25, f"合計 {d['kyufu']:,.0f}", ha="center", fontsize=10, color=INK)
        ax.set_xticks([])
        ax.set_xlim(-0.4, 1.85)
        ax.set_ylim(0, 2550)
        ax.set_ylabel("兆円（2024年度末の価値）")
        ax.set_title(f"{name}ケース", fontsize=12, color=INK)
        _style(ax)
    h = [Patch(color=C[k], label=l) for k, l in (
        ("hoken", "財源：保険料"), ("kokko", "財源：国庫負担"), ("tumi", "財源：積立金"),
        ("kakok", "給付：過去期間の基礎年金"), ("kako2", "給付：過去期間の2階部分"),
        ("shoraik", "給付：将来期間の基礎年金"), ("shorai2", "給付：将来期間の2階部分"))]
    h.append(Line2D([], [], color=INK, ls="--", label="給付の過去期間と将来期間の境"))
    fig.legend(handles=h, loc="lower center", ncol=4, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.06))
    fig.suptitle("調整期間を一致させると、年金の財源と給付はどう変わるか — 基礎年金が増え、その半分を国庫負担が持つ"
                 "（非公式の推定）\n財源と給付は2025〜2120年度の合計（比較型のバランスシート）", fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.13, 1, 0.93))
    _save(fig, "バランスシート_比較")
    plt.close(fig)

    # ---- 図2 何がいくら変わるか（差分図）
    items = [("財源：保険料", "hoken", C["hoken"]), ("財源：国庫負担", "kokko", C["kokko"]),
             ("財源：積立金", "tumi", C["tumi"]),
             ("給付：過去期間の基礎年金\n（いまの受給者）", "jukyuk", C["kakok"]),
             ("給付：過去期間の基礎年金\n（まだ受け取っていない人）", "kakok_mada", C["kakok"]),
             ("給付：過去期間の2階部分\n（いまの受給者）", "jukyu2", C["kako2"]),
             ("給付：過去期間の2階部分\n（まだ受け取っていない人）", "kako2_mada", C["kako2"]),
             ("給付：将来期間の基礎年金", "shoraik", C["shoraik"]),
             ("給付：将来期間の2階部分", "shorai2", C["shorai2"])]
    fig, axs = plt.subplots(1, len(cases), figsize=(7.4 * len(cases), 6.6), sharey=True, squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        g, t = res[c]["gen"], res[c]["tg"]
        for d in (g, t):
            d["kakok_mada"] = d["kakok"] - d["jukyuk"]
            d["kako2_mada"] = d["kako2"] - d["jukyu2"]
        ys = list(range(len(items)))[::-1]
        for y, (lab, k, col) in zip(ys, items):
            v = t[k] - g[k]
            ax.barh(y, v, 0.62, color=col, edgecolor="white")
            ax.text(v + (2 if v >= 0 else -2), y, f"{v:+,.0f}", va="center", ha="left" if v >= 0 else "right",
                    fontsize=9.5, color=INK)
        ax.axvline(0, color=INK, lw=0.8)
        ax.axhline(5.5, color=GRID, lw=1)
        ax.set_yticks(ys)
        ax.set_yticklabels([x[0] for x in items], fontsize=9)
        ax.set_xlim(-120, 120)
        ax.set_xlabel("調整期間の一致 − 現行制度（兆円、2024年度末の価値）")
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        _style(ax, "x")
    fig.suptitle("何がいくら変わるか — 基礎年金はいまの受給者も含めて増え、その半分は国庫負担。2階部分は過去30年投影では減る（非公式の推定）",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "変化")
    plt.close(fig)

    # ---- 図3 毎年の給付（名目）：基礎年金と2階部分
    fig, axs = plt.subplots(1, len(cases), figsize=(7.0 * len(cases), 5.6), squeeze=False)
    ys = list(range(Y0 + 1, Y1 + 1))
    for ax, (c, name) in zip(axs[0], cases):
        g, t = res[c]["gen"], res[c]["tg"]
        for key, col, lab in (("kiso_nen", C["kiso"], "基礎年金"), ("nikai_nen", C["nikai"], "2階部分")):
            ax.plot(ys, [g[key].get(y, 0) for y in ys], color=col, lw=1.6, ls="--", label=f"{lab}：現行制度")
            ax.plot(ys, [t[key].get(y, 0) for y in ys], color=col, lw=2.2, label=f"{lab}：調整期間の一致")
        ax.set_xlim(2025, 2120)
        ax.set_ylim(0, None)
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        ax.set_xlabel("年度")
        ax.set_ylabel("兆円（名目）")
        _style(ax)
    axs[0][0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("毎年の給付（名目）— 調整期間を一致させると基礎年金が増える。2階部分は過去30年投影では減り、成長型ではほぼ同じ（非公式の推定）",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE.replace("名目運用利回りで2024年度末の価値に直した再現と推定", "年度ごとの名目の額で並べた再現"),
             fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "年度別")
    plt.close(fig)

    # ---- 図4 積立金（2024年度末の価値）：厚生年金と国民年金の勘定
    fig, axs = plt.subplots(1, len(cases), figsize=(7.0 * len(cases), 5.6), squeeze=False)
    ys = list(range(Y0, Y1 + 1))
    for ax, (c, name) in zip(axs[0], cases):
        g, t = res[c]["gen"], res[c]["tg"]
        for key, col, lab in (("tumiK_pv", C["kou"], "厚生年金"), ("tumiN_pv", C["kn"], "国民年金")):
            ax.plot(ys, [g[key][y] for y in ys], color=col, lw=1.6, ls="--", label=f"{lab}：現行制度")
            ax.plot(ys, [t[key][y] for y in ys], color=col, lw=2.2, label=f"{lab}：調整期間の一致")
        ax.axhline(0, color=INK, lw=0.8)
        ax.set_xlim(2024, 2120)
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        ax.set_xlabel("年度")
        ax.set_ylabel("年度末の積立金（兆円、2024年度末の価値）")
        _style(ax)
    axs[0][0].legend(frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("積立金の行方 — 調整期間を一致させると、国民年金の勘定だけでは積立金がマイナスになり、厚生年金の積立金と一体で支える"
                 "（非公式の推定）", fontsize=12, color=INK)
    fig.text(0.01, 0.005, NOTE + "\n厚生年金は⑤の要約から国民年金勘定を引いたもの。国民年金は④の国民年金勘定（一体の均衡とは別に④が出す勘定。マイナスになってからの運用収入の扱いは確かめていない）。",
             fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    _save(fig, "積立金")
    plt.close(fig)

    # ---- 図5 過去期間に係る給付の内訳
    fig, axs = plt.subplots(1, len(cases), figsize=(6.8 * len(cases), 5.6), sharey=True, squeeze=False)
    cats = [("基礎年金\nいまの受給者", "jukyuk"), ("基礎年金\nまだ受け取って\nいない人", "kakok_mada"),
            ("2階部分\nいまの受給者", "jukyu2"), ("2階部分\nまだ受け取って\nいない人", "kako2_mada")]
    for ax, (c, name) in zip(axs[0], cases):
        g, t = res[c]["gen"], res[c]["tg"]
        for i, (lab, k) in enumerate(cats):
            for j, (d, col) in enumerate(((g, "#9a9a9a"), (t, C["kiso"]))):
                v = d[k]
                ax.bar(i + (j - 0.5) * 0.36, v, 0.34, color=col, edgecolor="white")
                ax.annotate(f"{v:,.0f}", (i + (j - 0.5) * 0.36, v), xytext=(0, 3), textcoords="offset points",
                            ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels([x[0] for x in cats], fontsize=9)
        ax.set_ylim(0, 430)
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        _style(ax)
    axs[0][0].set_ylabel("兆円（2024年度末の価値）")
    axs[0][0].legend(handles=[Patch(color="#9a9a9a", label="現行制度"), Patch(color=C["kiso"], label="調整期間の一致")],
                     frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("過去期間に係る給付（すでに加入した期間の分）の内訳 — いまの受給者も基礎年金が増える。2階部分は過去30年投影で減る（非公式の推定）",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "過去期間の内訳")
    plt.close(fig)


def zu_seido(res):
    """期間・制度型のバランスシート：現行制度と調整期間の一致を並べる（ケースごとに1枚）。斜線が国民年金"""
    plt = _plt()
    col = dict(tumi=N.C_TUMI, kok_p=N.C_KOKKO, kok_f=N.C_KOKKO2, hok_p=N.C_NIJUU, hok_f=N.C_HOKEN2,
               kiso_p="#1f5fae", nikai_p="#7fb1e8", kiso_f="#5a8f8f", nikai_f="#b5d6d6")
    dark = {N.C_TUMI, N.C_KOKKO, N.C_NIJUU, "#1f5fae", "#5a8f8f"}
    files = {"3003": "バランスシート_期間と制度", "3002": "バランスシート_期間と制度_成長型"}
    for c, name in CASES:
        if c not in res:
            continue
        fig, axs = plt.subplots(1, 2, figsize=(23, 9.8), sharey=True)
        for ax, k in zip(axs, ("gen", "tg")):
            o = res[c][k]
            z = o["seido"]
            w, X0, X1 = 0.8, 0.0, 1.35
            zai = [(z["t24K"], col["tumi"], "積立金（2024年度末）\n被用者年金", None),
                   (z["t24N"], col["tumi"], "積立金・国民年金", "//"),
                   (z["kokK_p"], col["kok_p"], "国庫負担（過去期間分）\n被用者年金へ", None),
                   (z["kokN_p"], col["kok_p"], "国庫負担（過去期間分）・国民年金へ", "//"),
                   (z["hokK_p"], col["hok_p"], "保険料（過去期間分）\n被用者年金", None),
                   (z["hokN_p"], col["hok_p"], "保険料（過去期間分）・国民年金", "//"),
                   (z["kokK_f"], col["kok_f"], "国庫負担（将来期間分）・被用者年金へ", None),
                   (z["kokN_f"], col["kok_f"], "国庫負担（将来期間分）・国民年金へ", "//"),
                   (z["kyuK_f"] - z["kokK_f"], col["hok_f"], "保険料（将来期間分）\n被用者年金", None),
                   (z["hokN_f_disp"], col["hok_f"], "保険料（将来期間分）・国民年金", "//")]
            if z["S"] > 0.5:
                zai.append((z["S"], "#d9534f", "被用者年金の財源から国民年金の給付へ（一体）", "xx"))
            kyu = [(z["kiso_pK"], col["kiso_p"], "過去期間・基礎年金\n被用者年金が払う分", None),
                   (z["kiso_pN"], col["kiso_p"], "過去期間・基礎年金・国民年金が払う分", "//"),
                   (o["kako2"], col["nikai_p"], "過去期間・2階部分", None),
                   (z["kiso_fK"], col["kiso_f"], "将来期間・基礎年金\n被用者年金が払う分", None),
                   (z["kiso_fN"], col["kiso_f"], "将来期間・基礎年金・国民年金が払う分", "//"),
                   (o["shorai2"], col["nikai_f"], "将来期間・2階部分", None)]
            for x, segs, side in ((X0, zai, "left"), (X1, kyu, "right")):
                b, last = 0.0, -1e9
                for v, cc, lab, h in segs:
                    ax.bar(x, v, w, bottom=b, color=cc, edgecolor="white", lw=1.2, hatch=h)
                    if v > 170 and h is None:
                        ax.text(x, b + v / 2, f"{lab}\n{v:,.0f}", ha="center", va="center", fontsize=9,
                                color="white" if cc in dark else INK, linespacing=1.3)
                    else:
                        t_ = f"{lab.replace(chr(10), '・')} {v:,.0f}"
                        y_ = max(b + v / 2, last + 40)     # 小さい区分のラベルが重ならないように上へずらす
                        last = y_
                        if side == "left":
                            ax.text(x - w / 2 - 0.03, y_, t_, ha="right", va="center", fontsize=8.2, color=INK)
                        else:
                            ax.text(x + w / 2 + 0.03, y_, t_, ha="left", va="center", fontsize=8.2, color=INK)
                    b += v
                ax.annotate(f"合計 {b:,.0f}", (x, b), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=11)
            ax.plot([X0 - w / 2 - 0.05, X1 + w / 2 + 0.05], [o["kako"]] * 2, color=INK, lw=1.1, ls="--")
            ax.text(X1 + w / 2 + 0.08, o["kako"], "↑ 将来期間\n↓ 過去期間", ha="left", va="center", fontsize=9, color=INK)
            ax.set_xticks([X0, X1])
            ax.set_xticklabels(["財源", "給付"], fontsize=12)
            ax.set_xlim(-1.9, 3.0)
            ax.set_ylim(0, 2550)
            ax.set_title(LABEL[k], fontsize=13, color=INK)
            _style(ax)
        axs[0].set_ylabel("兆円（2024年度末の価値、2025〜2120年度の合計）")
        zt = res[c]["tg"]["seido"]
        fig.suptitle(f"公的年金のバランスシート（期間・制度型） — {name}ケース：現行制度と調整期間の一致（非公式の推定）\n"
                     f"斜線が国民年金の分。調整期間の一致では、国民年金の財源で足りない {zt['S']:,.0f}兆円を被用者年金の財源で支える（×印）",
                     fontsize=12.5, color=INK)
        fig.text(0.01, 0.008, NOTE + "\n基礎年金は「誰が払うか」で分けた（被用者年金4制度の基礎年金拠出金／国民年金の拠出金と特別国庫負担）。"
                 "保険料は制度ごとに 過去期間分＝過去期間の給付−過去期間分の国庫負担−2024年度末の積立金、将来期間分＝将来期間の給付−将来期間分の国庫負担。\n"
                 "国民年金の財源で足りない分＝国民年金の給付−（保険料＋国庫負担＋2024年度末の積立金）。2120年度末に残る積立金の分だけ、被用者年金の保険料の合計とずれる。",
                 fontsize=7.6, color=INK2, linespacing=1.5)
        fig.tight_layout(rect=(0, 0.075, 1, 0.94))
        _save(fig, files[c])
        plt.close(fig)


def zu_size(res):
    """国民年金と被用者年金の大きさのくらべ（財源と給付、現行制度と調整期間の一致）"""
    plt = _plt()
    from matplotlib.patches import Patch
    cases = [(c, n) for c, n in CASES if c in res]
    fig, axs = plt.subplots(len(cases), 2, figsize=(16, 6.2 * len(cases)), squeeze=False,
                            gridspec_kw=dict(width_ratios=[1.35, 1]))
    for i, (c, name) in enumerate(cases):
        for j, (seidos, title) in enumerate(((("K", "N"), "同じ目盛りで"), (("N",), "国民年金だけ拡大"))):
            ax = axs[i][j]
            xs, labs = [], []
            x = 0.0
            for sd in seidos:
                for k in ("gen", "tg"):
                    z = res[c][k]["seido"]
                    if sd == "K":
                        kyu = [(z["kiso_pK"] + z["kiso_fK"], C["kiso"]),
                               (z["kyuK"] - z["kiso_pK"] - z["kiso_fK"], C["kako2"])]
                        zai = [(z["hokK"], C["hoken"]), (z["kokK"], C["kokko"]), (z["tumiK"], C["tumi"])]
                    else:
                        kyu = [(z["kiso_pN"] + z["kiso_fN"], C["kiso"]),
                               (z["kyuN"] - z["kiso_pN"] - z["kiso_fN"], C["kako2"])]
                        zai = [(z["hokN"], C["hoken"]), (z["kokN"], C["kokko"]), (z["tumiN"], C["tumi"]),
                               (z["S"], "#d9534f")]
                    for dx, segs in ((0.0, zai), (0.42, kyu)):
                        bb = 0.0
                        for v, cc in segs:
                            if v <= 0:
                                continue
                            ax.bar(x + dx, v, 0.38, bottom=bb, color=cc, edgecolor="white", lw=1,
                                   hatch="xx" if cc == "#d9534f" else None)
                            bb += v
                        ax.annotate(f"{bb:,.0f}", (x + dx, bb), xytext=(0, 3), textcoords="offset points",
                                    ha="center", fontsize=8.5, color=INK)
                    xs.append(x + 0.21)
                    labs.append(f"{'被用者年金' if sd == 'K' else '国民年金'}\n{LABEL[k]}\n財源　給付")
                    x += 1.15
                x += 0.35
            ax.set_xticks(xs)
            ax.set_xticklabels(labs, fontsize=8.8)
            ax.set_title(f"{name}ケース：{title}", fontsize=11.5, color=INK)
            ax.set_ylabel("兆円（2024年度末の価値）")
            ax.set_ylim(0, None)
            ax.margins(y=0.08)
            _style(ax)
    h = [Patch(color=C["hoken"], label="財源：保険料"), Patch(color=C["kokko"], label="財源：国庫負担"),
         Patch(color=C["tumi"], label="財源：積立金"),
         Patch(facecolor="#d9534f", hatch="xx", edgecolor="white", label="財源：被用者年金の財源から（一体）"),
         Patch(color=C["kiso"], label="給付：基礎年金"), Patch(color=C["kako2"], label="給付：2階部分")]
    fig.legend(handles=h, loc="lower center", ncol=6, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.035))
    g0 = res[cases[0][0]]
    zg, zt = g0["gen"]["seido"], g0["tg"]["seido"]
    fig.suptitle(f"国民年金と被用者年金の大きさ — 国民年金は給付全体の{zg['kyuN'] / (zg['kyuK'] + zg['kyuN']) * 100:.0f}%ほど。"
                 f"調整期間の一致で国民年金の給付は{zg['kyuN']:,.0f}→{zt['kyuN']:,.0f}兆円に増え、"
                 f"足りない{zt['S']:,.0f}兆円を被用者年金が支える（{cases[0][1]}、非公式の推定）", fontsize=12, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.955))
    _save(fig, "制度の大きさ")
    plt.close(fig)


def zu_nijuu(res):
    """二重負担型のバランスシート：現行制度と調整期間の一致を並べる（過去30年投影）"""
    plt = _plt()
    c, name = CASES[0]
    if c not in res:
        return
    fig, axs = plt.subplots(1, 2, figsize=(17, 8.6), sharey=True)
    for ax, k in zip(axs, ("gen", "tg")):
        o = res[c][k]
        w = 0.5
        zai = [(o["tumi24"], N.C_TUMI, f"積立金（2024年度末）\n{o['tumi24']:,.0f}", "white"),
               (o["nijuu_hirei"], N.C_NIJUU2, f"二重の負担のうち\n報酬比例分 {o['nijuu_hirei']:,.0f}", "white"),
               (o["kokko_kako"], N.C_KOKKO, f"国庫負担（過去期間分）\n{o['kokko_kako']:,.0f}", "white"),
               (o["nijuu_kiso"], N.C_NIJUU, f"二重の負担のうち\n基礎年金分 {o['nijuu_kiso']:,.0f}", "white"),
               (o["kokko_shorai"], N.C_KOKKO2, f"国庫負担（将来期間分）{o['kokko_shorai']:,.0f}", INK),
               (o["shorai"] - o["kokko_shorai"], N.C_HOKEN2,
                f"保険料のうち\n将来期間分の給付に回る分\n{o['shorai'] - o['kokko_shorai']:,.0f}", INK)]
        kyu = [(o["jukyu"], N.C_JUKYU, f"過去期間分のうち\nいまの受給者\n{o['jukyu']:,.0f}", "white"),
               (o["kako"] - o["jukyu"], N.C_KAKO, f"過去期間分のうち\nまだ受け取っていない人\n{o['kako'] - o['jukyu']:,.0f}", INK),
               (o["shorai"], N.C_SHORAI, f"将来期間に係る分\n（2025年度以降の加入）\n{o['shorai']:,.0f}", INK)]
        for x, segs in ((0, zai), (1, kyu)):
            b = 0.0
            for v, cc, lab, tc in segs:
                ax.bar(x, v, w, bottom=b, color=cc, edgecolor="white", lw=1.5)
                ax.text(x, b + v / 2, lab, ha="center", va="center", fontsize=9, color=tc, linespacing=1.3)
                b += v
            ax.annotate(f"合計 {b:,.0f}", (x, b), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=11)
        ax.plot([-0.4, 1.4], [o["kako"]] * 2, color=INK, lw=1.1, ls="--")
        ax.text(1.42, o["kako"], "↑ 将来期間\n↓ 過去期間", va="center", fontsize=9, color=INK)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["財源", "給付"], fontsize=12)
        ax.set_xlim(-0.55, 1.75)
        ax.set_ylim(0, 2550)
        ax.set_title(f"{LABEL[k]}：いわゆる二重の負担 {o['nijuu']:,.0f}兆円", fontsize=12.5, color=INK)
        _style(ax)
    axs[0].set_ylabel("兆円（2024年度末の価値、2025〜2120年度の合計）")
    fig.suptitle(f"公的年金のバランスシート（二重負担型） — {name}ケース：現行制度と調整期間の一致（非公式の推定）",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.008, NOTE + "\n二重の負担の内訳は、積立金をすべて報酬比例に、国庫負担をすべて基礎年金に充てるとみなした。"
             "保険料（将来期間分）は 将来期間の給付 − 将来期間分の国庫負担。", fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "バランスシート_二重負担型")
    plt.close(fig)


if __name__ == "__main__":
    main()
