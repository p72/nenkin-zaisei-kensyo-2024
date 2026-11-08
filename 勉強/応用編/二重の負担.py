#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年金財政のバランスシート（過去期間に係る給付・いわゆる二重の負担）を計算プログラムの出力から再現する

公表：2024年財政検証 結果レポート 第3章 第3-7-45〜48図
  過去30年投影ケース　 二重の負担 650 ＝ 過去期間に係る給付 1,280 − 過去期間に係る国庫負担 320 − 積立金 300
  成長型経済移行・継続 二重の負担 600 ＝ 1,220 − 320 − 300（2120年度末に残る積立金も使う前提）

原本には、加入期間を2024年度で打ち切って給付を計算する「過去分試算」と、
いまの受給者の分だけを計算する「受給者分試算」がある（SAIMU=1/2）。これと通常試算を並べて、
給付・国庫負担・保険料・積立金を2024年度末の価値（名目運用利回りで割り引く）に直す。

  給付        ＝ 基礎年金給付費（新法＋旧法、制度計）＋ 厚生年金4制度の独自給付・福祉 ＋ 国民年金の独自給付
  2階部分     ＝ 厚生年金4制度の独自給付・福祉 ＋ 国民年金の独自給付（付加年金・寡婦年金・死亡一時金）
  基礎年金分  ＝ 基礎年金給付費
  国庫負担    ＝ 厚生年金4制度の国庫負担 ＋ 国民年金の国庫負担（基礎年金・特別国庫ほか）
  積立金      ＝ 2024年度末の積立金（厚生年金4制度＋国民年金）
  割引        ＝ 給付・保険料・国庫負担は年度の真ん中で払うとみなす（推定。これがいちばん公表値に合う）
  「福祉」欄  ＝ 過去分試算・受給者分試算でも同じ額が出るので、その年の給付に占める割合で按分する（推定）

使い方（リポジトリの直下で）:
  検証/実行/run_pipeline.sh 3003 1 1 0 2                                  # 通常試算
  SAIMU=1 STEPS=2345 SKIP_BUILD=1 検証/実行/run_pipeline.sh 3003 1 1 0 2   # 過去分試算（AK）
  SAIMU=2 STEPS=2345 SKIP_BUILD=1 検証/実行/run_pipeline.sh 3003 1 1 0 2   # 受給者分試算（AJ）
  （3002・3001 は人口・労働力率の引数を付けずに同じように。通常試算と同じ引数にすること）
  過去分・受給者分の出力は AK・AJ の付いた別ファイルなので、通常試算の結果は上書きされない
  （④⑤の作業用のカット率ファイルは書き直されるが、中の値は同じ）。1本2分ほど。
  python3 勉強/応用編/二重の負担.py            # 表と図（勉強/応用編/図/二重の負担_*.png）。--no-fig で表だけ
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "検証", "3号廃止"))
import analyze_sango as A  # noqa: E402

SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"), ("3001", "高成長実現"))
Y0, Y1 = 2024, 2120      # 2024年度末を基準に、2025〜2120年度（財政均衡期間）
KN2 = ("死亡一時金納付分", "死亡一時金付加分", "新法寡婦年金", "旧法寡婦年金免除分以外",
       "旧法寡婦年金免除分", "付加年金")
KN_KOKKO = ("国庫（基礎年金）", "国庫（特別国庫）", "国庫（死亡一時金付加分）", "国庫（付加年金）",
            "国庫（旧法寡婦年金免除分）")
KN_HOKEN = ("保険料収入（国年）", "保険料収入（付加年金）")

# 公表値（結果レポート第3章 第3-7-47図・第3-7-48図、兆円・2024年度価格・10兆円単位）
KOHYO = {
    "3003": dict(kyufu=2300, kako=1280, kako2=650, kakok=630, jukyu=590, jukyu2=300, jukyuk=290,
                 shorai=1020, hoken=1500, kokko=490, kokko_kako=320, kokko_jukyu=150, kokko_shorai=170,
                 tumi=300, nijuu=650),
    "3002": dict(kyufu=2260, kako=1220, kako2=600, kakok=610, jukyu=560, jukyu2=290, jukyuk=280,
                 shorai=1050, hoken=1570, kokko=510, kokko_kako=320, kokko_jukyu=140, kokko_shorai=200,
                 tumi=170, nijuu=600),
}
# 公表値（第3-7-45図、兆円・名目）：年度 → (給付計, 過去期間に係る分, うち受給者分)
NENDO = {
    "3003": {2025: (57.7, 57.4, 56.0), 2030: (61.1, 57.3, 43.6), 2040: (70.1, 56.1, 22.8),
             2050: (75.2, 47.6, 7.6), 2060: (78.4, 35.0, 1.5), 2070: (83.3, 20.5, 0.5),
             2080: (88.0, 8.8, 0.2), 2090: (90.8, 2.5, 0.1), 2100: (92.5, 0.3, 0.0),
             2120: (96.0, 0.0, 0.0)},
    "3002": {2025: (57.8, 57.5, 56.1), 2030: (64.4, 60.3, 45.8), 2040: (86.9, 68.9, 27.2),
             2050: (119.0, 73.7, 11.4), 2060: (160.7, 69.8, 3.1), 2070: (216.3, 51.4, 1.4),
             2080: (287.8, 27.6, 0.8), 2090: (370.1, 10.1, 0.4), 2100: (470.4, 1.5, 0.1),
             2120: (753.9, 0.0, 0.0)},
}


def add(*ss):
    out = {}
    for s in ss:
        for y, v in s.items():
            out[y] = out.get(y, 0.0) + v
    return out


def scale(s, k):
    return {y: v * k for y, v in s.items()}


def load(case, pre):
    """pre: "" 通常試算 / "AK" 過去分試算 / "AJ" 受給者分試算。金額は兆円（名目）"""
    c = case
    if pre:
        kek = f"kekka{pre}{c}-{c}{pre}-{c}-{c}-1120-000a.csv"
        summ = f"03summary.{pre}{c}-{c}-{c}-{c}-1120-000_09sum.csv"
    else:
        kek = f"kekka{c}-{c}-{c}-{c}-1120-000a.csv"
        summ = f"03summary.{c}-{c}-{c}-{c}-1120-000_08sum.csv"
    pk = os.path.join(SUURI, "bas", "rslt", kek)
    ps = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi", summ)
    if not (os.path.exists(pk) and os.path.exists(ps)):
        return None
    K, S = A.read_blocks(pk), A.read_blocks(ps)
    tou = S["収支[全厚年１:tou]"]           # 厚生年金4制度の合計（億円）
    sh = K["収支見通し"]                     # 国民年金勘定（円）
    _, rows = K["基礎年金給付費（新法＋旧法）"]  # 円。先頭の「制度計」を使う
    oku, en = 1e-4, 1e-12
    d = dict(
        kiso={int(r[0]): r[1] * en for r in rows},
        dok=scale(A.series(tou, "独自給付", 2000), oku),
        fuku=scale(A.series(tou, "福祉", 2000), oku),
        kn2=scale(add(*[A.series(sh, k) for k in KN2]), en),
        kokko=add(scale(A.series(tou, "国庫負担", 2000), oku),
                  scale(add(*[A.series(sh, k) for k in KN_KOKKO]), en)),
        hoken=add(scale(A.series(tou, "保険料", 2000), oku),
                  scale(add(*[A.series(sh, k) for k in KN_HOKEN]), en)),
        tumi=add(scale(A.series(tou, "積立金", 2000), oku),
                 scale(A.series(sh, "年度末積立金"), en)),
        rate=A.series(K["経済前提"], "運用利回り"),   # 名目運用利回り（1＋i の倍率）
    )
    return d


def factors(rate):
    """年度の真ん中の割引係数 mid[y] と、年度末の割引係数 end[y]（2024年度末＝1）"""
    mid, end, f = {}, {Y0: 1.0}, 1.0
    for y in range(Y0 + 1, Y1 + 1):
        mid[y] = f * rate[y] ** 0.5
        f *= rate[y]
        end[y] = f
    return mid, end


def pv(s, mid):
    return sum(s.get(y, 0.0) / mid[y] for y in mid)


def keisan(case):
    R = {p: load(case, p) for p in ("", "AK", "AJ")}
    if any(v is None for v in R.values()):
        return None
    base = R[""]
    mid, end = factors(base["rate"])
    tot0 = add(base["kiso"], base["dok"], base["kn2"])
    out = {}
    for p, r in R.items():
        tot = add(r["kiso"], r["dok"], r["kn2"])
        # 福祉は3つの試算で同じ額が出る → その年の給付（通常試算）に占める割合で按分する
        fuku = {y: r["fuku"].get(y, 0.0) * (tot.get(y, 0.0) / tot0[y] if tot0.get(y) else 0.0)
                for y in r["fuku"]}
        nikai = add(r["dok"], r["kn2"], fuku)
        out[p] = dict(nikai=pv(nikai, mid), kiso=pv(r["kiso"], mid), kokko=pv(r["kokko"], mid),
                      nen=add(nikai, r["kiso"]))
        out[p]["kyufu"] = out[p]["nikai"] + out[p]["kiso"]
    t24 = base["tumi"][Y0]
    t120 = base["tumi"][Y1] / end[Y1]
    o = dict(kyufu=out[""]["kyufu"], kako=out["AK"]["kyufu"], kako2=out["AK"]["nikai"],
             kakok=out["AK"]["kiso"], jukyu=out["AJ"]["kyufu"], jukyu2=out["AJ"]["nikai"],
             jukyuk=out["AJ"]["kiso"], shorai=out[""]["kyufu"] - out["AK"]["kyufu"],
             shorai2=out[""]["nikai"] - out["AK"]["nikai"], shoraik=out[""]["kiso"] - out["AK"]["kiso"],
             hoken=pv(base["hoken"], mid), kokko=out[""]["kokko"], kokko_kako=out["AK"]["kokko"],
             kokko_jukyu=out["AJ"]["kokko"], kokko_shorai=out[""]["kokko"] - out["AK"]["kokko"],
             tumi24=t24, tumi120=t120, tumi=t24 - t120)
    # いわゆる二重の負担：2120年度末に残る積立金も使う前提（公表の注2）なので、2024年度末の積立金を全部引く
    o["nijuu"] = o["kako"] - o["kokko_kako"] - t24
    # 内訳（ざっくり）：積立金はすべて報酬比例（2階部分）に、国庫負担はすべて基礎年金に充てるとみなす
    o["nijuu_hirei"] = o["kako2"] - t24
    o["nijuu_kiso"] = o["kakok"] - o["kokko_kako"]
    o["nendo"] = {y: (out[""]["nen"].get(y, 0.0), out["AK"]["nen"].get(y, 0.0), out["AJ"]["nen"].get(y, 0.0))
                  for y in range(Y0 + 1, Y1 + 1)}
    return o


def f0(x):
    return f"{x:,.0f}"


def kohyo(case, k):
    v = KOHYO.get(case, {}).get(k)
    return f"{v:,}" if v is not None else "―"


C_JUKYU, C_KAKO, C_SHORAI = "#1f5fae", "#7fb1e8", "#cfe0f5"     # 給付：受給者分・過去期間の残り・将来期間
C_KOKKO, C_KOKKO2 = "#1baf7a", "#a6e3cb"                          # 国庫負担：過去期間・将来期間
C_TUMI, C_NIJUU, C_HOKEN2 = "#8c8c8c", "#eb6834", "#f8c9b3"       # 積立金・二重の負担（基礎年金分）・保険料の残り
C_NIJUU2 = "#c0461a"                                              # 二重の負担（報酬比例分）
INK, INK2, GRID = "#222222", "#555555", "#dddddd"
NOTE = ("非公式：2024年財政検証の計算プログラム（過去分試算・受給者分試算・通常試算）の出力を、名目運用利回りで"
        "2024年度末の価値に直した再現。厚生労働省の計算そのものではない。\n"
        "公表値は結果レポート第3章 第3-7-45〜48図。割り引きは年度の真ん中、「福祉」欄はその年の給付の割合で按分（推定）。")


def zu(res):
    """図1：二重の負担の内訳　図2：バランスシート（過去30年投影）　図3：年度ごとの給付"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams["font.family"] = "IPAPGothic"
    plt.rcParams["axes.unicode_minus"] = False
    outdir = os.path.join(HERE, "図")
    os.makedirs(outdir, exist_ok=True)
    cases = [(c, n) for c, n in CASES if c in res and c in KOHYO]

    def style(ax):
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

    # ---- 図1 二重の負担の内訳（滝グラフ）
    fig, axs = plt.subplots(1, len(cases), figsize=(6.2 * len(cases), 6.2), sharey=True)
    for ax, (c, name) in zip(axs, cases):
        o, k = res[c], KOHYO[c]
        kako, kk, t24, nj = o["kako"], o["kokko_kako"], o["tumi24"], o["nijuu"]
        w = 0.62
        ax.bar(0, o["jukyu"], w, color=C_JUKYU, edgecolor="white", lw=1.5)
        ax.bar(0, kako - o["jukyu"], w, bottom=o["jukyu"], color=C_KAKO, edgecolor="white", lw=1.5)
        ax.bar(1, kk, w, bottom=kako - kk, color=C_KOKKO, edgecolor="white", lw=1.5)
        ax.bar(2, t24, w, bottom=nj, color=C_TUMI, edgecolor="white", lw=1.5)
        ax.bar(3, o["nijuu_kiso"], w, color=C_NIJUU, edgecolor="white", lw=1.5)
        ax.bar(3, o["nijuu_hirei"], w, bottom=o["nijuu_kiso"], color=C_NIJUU2, edgecolor="white", lw=1.5)
        ax.text(3, o["nijuu_kiso"] / 2, f"基礎年金分\n{o['nijuu_kiso']:,.0f}\n（公表 {k['kakok'] - k['kokko_kako']}）",
                ha="center", va="center", fontsize=9.5, color="white")
        ax.text(3, o["nijuu_kiso"] + o["nijuu_hirei"] / 2,
                f"報酬比例分\n{o['nijuu_hirei']:,.0f}\n（公表 {k['kako2'] - 300}）",
                ha="center", va="center", fontsize=9.5, color="white")
        for x0, y in ((0, kako), (1, kako - kk), (2, nj)):
            ax.plot([x0 + w / 2, x0 + 1 - w / 2], [y, y], color=INK2, lw=0.8, ls=":")
        lab = [(0, kako, f"{kako:,.0f}", f"公表 {k['kako']:,}"),
               (1, kako, f"−{kk:,.0f}", f"公表 −{k['kokko_kako']:,}"),
               (2, kako - kk, f"−{t24:,.0f}", "公表 −300"),
               (3, nj, f"{nj:,.0f}", f"公表 {k['nijuu']:,}")]
        for x, y, v, kv in lab:
            ax.annotate(v, (x, y), xytext=(0, 16), textcoords="offset points", ha="center",
                        fontsize=12, color=INK)
            ax.annotate(kv, (x, y), xytext=(0, 3), textcoords="offset points", ha="center",
                        fontsize=9, color=INK2)
        ax.text(0, o["jukyu"] / 2, f"うち\nいまの受給者\n{o['jukyu']:,.0f}", ha="center", va="center",
                fontsize=9.5, color="white")
        ax.text(0, o["jukyu"] + (kako - o["jukyu"]) / 2, f"まだ受け取って\nいない人の\n過去の加入分\n{kako - o['jukyu']:,.0f}",
                ha="center", va="center", fontsize=9, color=INK)
        ax.set_xticks(range(4))
        ax.set_xticklabels(["過去期間に係る\n給付", "過去期間に係る\n国庫負担", "積立金\n（2024年度末）",
                            "いわゆる\n二重の負担"], fontsize=10)
        ax.set_title(f"{name}ケース", fontsize=12, color=INK)
        ax.set_ylim(0, 1450)
        style(ax)
    axs[0].set_ylabel("兆円（2024年度末の価値）", fontsize=10.5)
    fig.suptitle("いわゆる二重の負担 ＝ 過去期間に係る給付 − 国庫負担 − 積立金（非公式の再現）",
                 fontsize=13.5, color=INK)
    fig.text(0.01, 0.01, NOTE + "\n二重の負担の内訳は、積立金をすべて報酬比例（2階部分）に、国庫負担をすべて基礎年金に充てるとみなした"
             "ざっくりの割り振り。公表値の内訳も同じ割り振りで、丸めた公表値から計算した。",
             fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    out = os.path.join(outdir, "二重の負担_内訳.png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", out)

    # ---- 図2 バランスシート（過去30年投影）
    c, name = cases[0]
    o, k = res[c], KOHYO[c]
    hoken_shorai = o["shorai"] - o["kokko_shorai"]
    fig, ax = plt.subplots(figsize=(10.5, 7.6))
    w = 0.5
    zai = [(o["tumi24"], C_TUMI, f"積立金（2024年度末）\n{o['tumi24']:,.0f}", "white"),
           (o["nijuu_hirei"], C_NIJUU2, f"二重の負担のうち\n報酬比例分 {o['nijuu_hirei']:,.0f}", "white"),
           (o["kokko_kako"], C_KOKKO, f"国庫負担（過去期間分）\n{o['kokko_kako']:,.0f}", "white"),
           (o["nijuu_kiso"], C_NIJUU, f"二重の負担のうち\n基礎年金分 {o['nijuu_kiso']:,.0f}", "white"),
           (o["kokko_shorai"], C_KOKKO2, f"国庫負担（将来期間分）{o['kokko_shorai']:,.0f}", INK),
           (hoken_shorai, C_HOKEN2, f"保険料のうち\n将来期間分の給付に回る分\n{hoken_shorai:,.0f}", INK)]
    kyu = [(o["jukyu"], C_JUKYU, f"過去期間分のうち\nいまの受給者\n{o['jukyu']:,.0f}", "white"),
           (o["kako"] - o["jukyu"], C_KAKO, f"過去期間分のうち\nまだ受け取っていない人\n{o['kako'] - o['jukyu']:,.0f}", INK),
           (o["shorai"], C_SHORAI, f"将来期間に係る分\n（2025年度以降の加入）\n{o['shorai']:,.0f}", INK)]
    for x, segs in ((0, zai), (1, kyu)):
        b = 0.0
        for v, col, lab, tc in segs:
            ax.bar(x, v, w, bottom=b, color=col, edgecolor="white", lw=1.5)
            ax.text(x, b + v / 2, lab, ha="center", va="center", fontsize=9.5, color=tc, linespacing=1.35)
            b += v
        ax.annotate(f"合計 {b:,.0f}", (x, b), xytext=(0, 5), textcoords="offset points", ha="center",
                    fontsize=11, color=INK)
    # 過去期間の財源の組：積立金＋報酬比例分 ＝ 2階部分、国庫負担＋基礎年金分 ＝ 基礎年金分
    for y0, y1, lab in ((0, o["kako2"], f"過去期間の\n2階部分\n{o['kako2']:,.0f}"),
                        (o["kako2"], o["kako"], f"過去期間の\n基礎年金分\n{o['kakok']:,.0f}")):
        xb = -0.29
        ax.plot([xb, xb - 0.03, xb - 0.03, xb], [y0 + 4, y0 + 4, y1 - 4, y1 - 4], color=INK2, lw=1)
        ax.text(xb - 0.05, (y0 + y1) / 2, lab, ha="right", va="center", fontsize=9, color=INK2)
    y = o["kako"]
    ax.plot([-0.45, 1.45], [y, y], color=INK, lw=1.2, ls="--")
    ax.text(1.47, y, "↑ 将来期間\n↓ 過去期間", va="center", fontsize=9.5, color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["財源", "給付"], fontsize=12)
    ax.set_xlim(-0.75, 1.85)
    ax.set_ylabel("兆円（2024年度末の価値、2025〜2120年度の合計）", fontsize=10.5)
    style(ax)
    ax.set_title(f"公的年金のバランスシート — {name}ケース（非公式の再現）\n"
                 f"保険料 {o['hoken']:,.0f}兆円のうち {o['nijuu']:,.0f}兆円（報酬比例分 {o['nijuu_hirei']:,.0f}＋基礎年金分 {o['nijuu_kiso']:,.0f}）が、過去期間に係る給付に回る",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.01, NOTE + f"\n保険料の内訳は、将来期間分＝将来期間に係る給付 − 将来期間分の国庫負担、で割り振った"
             f"（2120年度末に残る積立金の現在価値 {o['tumi120']:,.0f}兆円の分だけ合計がずれる）。"
             f"\n二重の負担の内訳は、積立金をすべて報酬比例に、国庫負担をすべて基礎年金に充てるとみなした。",
             fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    out = os.path.join(outdir, "二重の負担_バランスシート.png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", out)

    # ---- 図3 年度ごとの給付（名目）
    fig, axs = plt.subplots(1, len(cases), figsize=(6.4 * len(cases), 5.8))
    for ax, (c, name) in zip(axs, cases):
        o = res[c]
        ys = list(range(Y0 + 1, Y1 + 1))
        tot = [o["nendo"][y][0] for y in ys]
        kako = [o["nendo"][y][1] for y in ys]
        juk = [o["nendo"][y][2] for y in ys]
        ax.stackplot(ys, juk, [a - b for a, b in zip(kako, juk)], [a - b for a, b in zip(tot, kako)],
                     colors=(C_JUKYU, C_KAKO, C_SHORAI), lw=0)
        ky = sorted(NENDO[c])
        for i, (mk, lab) in enumerate((("o", "公表：給付計"), ("s", "公表：過去期間に係る分"), ("D", "公表：うち受給者分"))):
            ax.scatter(ky, [NENDO[c][y][i] for y in ky], marker=mk, s=26, facecolor="white",
                       edgecolor=INK, lw=1.1, zorder=4, label=lab)
        ax.set_xlim(2025, 2120)
        ax.set_ylim(0, None)
        ax.set_title(f"{name}ケース", fontsize=12, color=INK)
        ax.set_xlabel("年度")
        ax.set_ylabel("兆円（名目）")
        style(ax)
    h = [Patch(color=C_JUKYU, label="過去期間に係る分：いまの受給者"),
         Patch(color=C_KAKO, label="過去期間に係る分：まだ受け取っていない人"),
         Patch(color=C_SHORAI, label="将来期間に係る分")]
    h2, l2 = axs[0].get_legend_handles_labels()
    axs[-1].legend(handles=h + h2, frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("毎年の給付を、加入した時期で分けると（非公式の再現。帯がこのリポジトリ、白い印が公表値）",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.01, NOTE.replace("名目運用利回りで2024年度末の価値に直した再現", "年度ごとの名目の額で並べた再現"),
             fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    out = os.path.join(outdir, "二重の負担_年度別.png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", out)


def main():
    res = {}
    ok = False
    for case, name in CASES:
        o = keisan(case)
        if o is None:
            print(f"（未計算）{name}：通常試算・過去分試算・受給者分試算の3本が要る", file=sys.stderr)
            continue
        ok = True
        res[case] = o
        print(f"\n## {name}ケース（兆円、2024年度末の価値）\n")
        print("| 項目 | このリポジトリ | 公表値 |")
        print("|---|---|---|")
        rows = [
            ("給付の合計（2025〜2120年度）", "kyufu"),
            ("**過去期間に係る分（2024年度以前）**", "kako"),
            ("　2階部分", "kako2"), ("　基礎年金分", "kakok"),
            ("　うち受給者分", "jukyu"), ("　　2階部分", "jukyu2"), ("　　基礎年金分", "jukyuk"),
            ("将来期間に係る分（2025年度以降）", "shorai"),
            ("保険料", "hoken"),
            ("国庫負担", "kokko"), ("　過去期間に係る分", "kokko_kako"),
            ("　　うち受給者分", "kokko_jukyu"), ("　将来期間に係る分", "kokko_shorai"),
            ("積立金から得られる財源（2024年度末 − 2120年度末の現在価値）", "tumi"),
        ]
        for lab, k in rows:
            print(f"| {lab} | {f0(o[k])} | {kohyo(case, k)} |")
        print(f"| 2024年度末の積立金（厚生年金4制度＋国民年金） | {f0(o['tumi24'])} | ― |")
        print(f"| 2120年度末の積立金（現在価値） | {f0(o['tumi120'])} | "
              f"{'130' if case == '3002' else '―'} |")
        print(f"| **いわゆる二重の負担** ＝ 過去期間の給付 − 過去期間の国庫負担 − 2024年度末の積立金 | "
              f"**{f0(o['nijuu'])}** | **{kohyo(case, 'nijuu')}** |")
        kh = KOHYO.get(case)
        kh_h = f"{kh['kako2'] - 300}（{kh['kako2']} − 300）" if kh else "―"
        kh_k = f"{kh['kakok'] - kh['kokko_kako']}（{kh['kakok']} − {kh['kokko_kako']}）" if kh else "―"
        print(f"| 　うち報酬比例分 ＝ 過去期間の2階部分 − 積立金 | {f0(o['nijuu_hirei'])} | {kh_h} |")
        print(f"| 　うち基礎年金分 ＝ 過去期間の基礎年金分 − 国庫負担 | {f0(o['nijuu_kiso'])} | {kh_k} |")
        print(f"\n検算：{f0(o['kako'])} − {f0(o['kokko_kako'])} − {f0(o['tumi24'])} ＝ {f0(o['nijuu'])}"
              f"（報酬比例 {f0(o['nijuu_hirei'])} ＋ 基礎年金 {f0(o['nijuu_kiso'])}）")
        print(f"財源の合計 {f0(o['hoken'] + o['kokko'] + o['tumi'])} ／ 給付の合計 {f0(o['kyufu'])}")
        if case in NENDO:
            print(f"\n年度ごと（兆円・名目）\n")
            print("| 年度 | 給付計 | 公表 | 過去期間に係る分 | 公表 | うち受給者分 | 公表 |")
            print("|---|---|---|---|---|---|---|")
            for y, (k1, k2, k3) in NENDO[case].items():
                a1, a2, a3 = o["nendo"][y]
                print(f"| {y} | {a1:.1f} | {k1} | {a2:.1f} | {k2} | {a3:.1f} | {k3} |")
    if not ok:
        sys.exit(1)
    if "--no-fig" not in sys.argv:
        zu(res)


if __name__ == "__main__":
    main()
