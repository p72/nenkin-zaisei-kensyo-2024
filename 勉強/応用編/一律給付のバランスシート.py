#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""厚生年金の国庫負担を廃止して一律給付にした場合の、年金のバランスシート（推定）

「過去期間の給付と二重の負担」（二重の負担.py）と同じ表を、国庫負担の廃止案（予備番号701）で作る。

  廃止案：2027年度から被用者年金4制度の国庫負担を収入に入れず、報酬比例の給付を
          （すでに受け取っている人も含めて）一律に m 倍して2120年度に均衡させる。
          国が払わずに済んだ額は、年金の外で一律給付として配る（65歳以上の全員か、0歳からの全員）。

原本の債務の試算（SAIMU）は国庫負担の廃止のレバー（KOKKO）と組み合わせられないので、
過去期間分は次のように推定する。
  1. 通常試算（000）と廃止案（701）の独自給付の差は、報酬比例（年齢別出力の「1比例」）だけを削った分。
     年度ごとの実効の削り率 e(y) ＝ 1 − （独自給付000 − 独自給付701）÷ 報酬比例000
  2. 過去分試算（AK）・受給者分試算（AJ）の報酬比例に、同じ e(y) を掛ける（削減は全員に同じ率でかかるため）
  3. 基礎年金・国民年金の独自給付は変わらない（廃止案は④基礎年金に触らない）
  4. 過去期間に係る国庫負担は、国民年金の国庫負担（AK）＋ 厚生年金の国庫負担のうち2026年度まで（AK）

使い方（リポジトリの直下で）:
  二重の負担.py の手順で、3003・3001 の通常試算・過去分試算・受給者分試算を流しておく
  python3 勉強/応用編/国庫負担の廃止.py run 3003    # 廃止案（701）。3001 も同じ
  ※ 国庫負担の廃止.py run は年齢別出力（90nenbe）を消すが、この計算は 000・AK・AJ の年齢別出力だけを使う
  python3 勉強/応用編/一律給付のバランスシート.py   # 表と図（勉強/応用編/図/一律給付_バランスシート_*.png）
"""
import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


N = _load("nijuu", os.path.join(HERE, "二重の負担.py"))          # バランスシートの計算
K = _load("kokko", os.path.join(HERE, "国庫負担の廃止.py"))       # 国が払わずに済んだ額・人口
A = N.A
SUURI, SH = N.SUURI, os.path.join(N.SUURI, "emp", "rslt", "ez_arev", "shushi")
CASES = (("3003", "過去30年投影"), ("3001", "高成長実現"))
START, Y0, Y1 = 2027, N.Y0, N.Y1
YOBI = "701"


def hirei(case, pre):
    """年齢別出力（スライド調整後）の「1比例」の年度別合計（兆円）"""
    tag = "09" if pre else "08"
    p = os.path.join(SH, f"90nenbe.{pre}{case}-{case}-{case}-{case}-1120-000e_{tag}tou.csv")
    out, block = collections.defaultdict(float), None
    with open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("【"):
                block = line.strip()
                continue
            if block != "【スライド調整後】":
                continue
            q = line.split(",")
            if len(q) < 8 or q[5].strip() != "1比例" or not q[0].strip().isdigit():
                continue
            out[int(q[0]) + 2000] += float(q[7]) * 1e-4      # 億円 → 兆円
    return dict(out)


def tou(case, yobi):
    S = A.read_blocks(os.path.join(SH, f"03summary.{case}-{case}-{case}-{case}-1120-{yobi}_08sum.csv"))
    return S["収支[全厚年１:tou]"]


def keisan(case):
    """現行（N.keisan）と廃止案の両方の値を返す"""
    gen = N.keisan(case)
    if gen is None:
        return None
    b0, ak, aj = N.load(case, ""), N.load(case, "AK"), N.load(case, "AJ")
    mid, end = N.factors(b0["rate"])
    pv = lambda s: N.pv(s, mid)                                         # noqa: E731
    t701 = tou(case, YOBI)
    dok1 = N.scale(A.series(t701, "独自給付", 2000), 1e-4)
    kok1 = N.scale(A.series(t701, "国庫負担", 2000), 1e-4)
    fuku1 = N.scale(A.series(t701, "福祉", 2000), 1e-4)
    hok1 = N.scale(A.series(t701, "保険料", 2000), 1e-4)
    tum1 = N.scale(A.series(t701, "積立金", 2000), 1e-4)
    # 実効の削り率 e(y)
    h0 = hirei(case, "")
    e = {y: (1 - (b0["dok"][y] - dok1[y]) / h0[y]) if y >= START else 1.0 for y in range(Y0 + 1, Y1 + 1)}
    # 国民年金・基礎年金は変わらない（④のkekka 701 も同じ）
    kn_kokko = lambda d: {y: d["kokko"][y] - N.scale(A.series(d["_tou"], "国庫負担", 2000), 1e-4).get(y, 0.0)   # noqa: E731
                          for y in d["kokko"]}
    for d, pre in ((b0, ""), (ak, "AK"), (aj, "AJ")):
        d["_tou"] = A.read_blocks(os.path.join(SH, f"03summary.{pre}{case}-{case}-{case}-{case}-1120-000_"
                                                   f"{'09' if pre else '08'}sum.csv"))["収支[全厚年１:tou]"]
    tot0_k = N.add(b0["kiso"], dok1, b0["kn2"])                          # 廃止案の給付（福祉を除く）
    res = {}
    for name, d, pre in (("", b0, ""), ("AK", ak, "AK"), ("AJ", aj, "AJ")):
        if pre:
            h = hirei(case, pre)
            dok = {y: d["dok"][y] - (1 - e.get(y, 1.0)) * h.get(y, 0.0) for y in d["dok"]}
        else:
            dok = dok1
        tot = N.add(d["kiso"], dok, d["kn2"])
        fk = {y: fuku1.get(y, 0.0) * (tot.get(y, 0.0) / tot0_k[y] if tot0_k.get(y) else 0.0) for y in fuku1}
        nikai = N.add(dok, d["kn2"], fk)
        kou_kok = N.scale(A.series(d["_tou"], "国庫負担", 2000), 1e-4)
        kn = kn_kokko(d)
        if pre:   # 厚生年金の国庫負担は2026年度まで
            kok = N.add(kn, {y: v for y, v in kou_kok.items() if y < START})
        else:
            kok = N.add(kn, kok1)
        res[name] = dict(nikai=pv(nikai), kiso=pv(d["kiso"]), kokko=pv(kok), nen=N.add(nikai, d["kiso"]),
                         kokko_nen=kok)
        res[name]["kyufu"] = res[name]["nikai"] + res[name]["kiso"]
    t24 = gen["tumi24"]
    tum_kn = N.scale(A.series(N.A.read_blocks(os.path.join(SUURI, "bas", "rslt",
                     f"kekka{case}-{case}-{case}-{case}-1120-{YOBI}a.csv"))["収支見通し"], "年度末積立金"), 1e-12)
    t120 = (tum1[Y1] + tum_kn[Y1]) / end[Y1]
    # 保険料：厚生年金は廃止案の出力、国民年金は通常試算と同じ（b0["hoken"] は厚生年金＋国民年金）
    kn_hoken = {y: v - N.scale(A.series(b0["_tou"], "保険料", 2000), 1e-4).get(y, 0.0) for y, v in b0["hoken"].items()}
    hoken = pv(N.add(hok1, kn_hoken))
    o = dict(kyufu=res[""]["kyufu"], kako=res["AK"]["kyufu"], kako2=res["AK"]["nikai"], kakok=res["AK"]["kiso"],
             jukyu=res["AJ"]["kyufu"], jukyu2=res["AJ"]["nikai"], jukyuk=res["AJ"]["kiso"],
             shorai=res[""]["kyufu"] - res["AK"]["kyufu"], shorai2=res[""]["nikai"] - res["AK"]["nikai"],
             shoraik=res[""]["kiso"] - res["AK"]["kiso"], hoken=hoken, kokko=res[""]["kokko"],
             kokko_kako=res["AK"]["kokko"], kokko_jukyu=res["AJ"]["kokko"],
             kokko_shorai=res[""]["kokko"] - res["AK"]["kokko"], tumi24=t24, tumi120=t120, tumi=t24 - t120)
    # 年度ごとの財源（名目）：保険料・国庫負担。積立金から得られる財源は 給付 − 保険料 − 国庫負担
    o["hoken_nen"] = N.add(hok1, kn_hoken)
    gen["hoken_nen"], gen["kokko_nen"] = b0["hoken"], b0["kokko"]
    o["nendo"] = {y: (res[""]["nen"].get(y, 0.0), res["AK"]["nen"].get(y, 0.0), res["AJ"]["nen"].get(y, 0.0))
                  for y in range(Y0 + 1, Y1 + 1)}
    o["kokko_nen"] = res[""]["kokko_nen"]
    o["e"] = e
    # 一律給付：国が払わずに済んだ額（701 の内訳）。年金の外
    c = K.detail(case, YOBI)
    ichi = {y: c[y]["naiyaku"] for y in range(START, Y1 + 1)}
    o["ichi_nen"] = ichi
    o["ichi"] = pv(ichi)
    # 0歳からの全員に配るときの年齢の内訳（人口の割合で分ける）
    o["ichi_zenin"] = ichi_by_age(case, ichi, mid)
    o["m"] = K.ichiritsu(case)
    return gen, o


def pop_by_age(case):
    """将来推計人口（男女計、外国人を含む）を 0〜19・20〜64・65歳以上 に分ける"""
    import csv
    out = {}
    for sx in ("1", "2"):
        p = os.path.join(SUURI, "wakuc", "data", "sinj", f"pop{sx}-110.csv")
        for r in list(csv.reader(open(p, encoding="cp932")))[1:]:
            y, v = int(r[0]), [float(x) for x in r[3:]]
            a = out.setdefault(y, [0.0, 0.0, 0.0])
            a[0] += sum(v[:20])
            a[1] += sum(v[20:65])
            a[2] += sum(v[65:])
    return out


def ichi_by_age(case, ichi, mid):
    P = pop_by_age(case)
    res = [0.0, 0.0, 0.0]
    for y, v in ichi.items():
        t = sum(P[y])
        for i in range(3):
            res[i] += v * P[y][i] / t / mid[y]
    return dict(u20=res[0], g20=res[1], o65=res[2])


def f0(x):
    return f"{x:,.0f}"


def main():
    out = {}
    for case, name in CASES:
        r = keisan(case)
        if r is None:
            print(f"（未計算）{name}", file=sys.stderr)
            continue
        gen, o = r
        out[case] = (gen, o)
        print(f"\n## {name}ケース（兆円、2024年度末の価値）\n")
        print(f"報酬比例の一律削減 m ＝ {o['m']:.4f}（{(1 - o['m']) * 100:.1f}%減）。"
              f"実効の削り率 e(2027) ＝ {o['e'][2027]:.4f}、e(2030) ＝ {o['e'][2030]:.4f}、e(2100) ＝ {o['e'][2100]:.4f}\n")
        print("| 項目 | 現行制度 | 国庫負担の廃止＋一律給付 | 差 |")
        print("|---|---|---|---|")
        rows = [("**財源**", None), ("保険料", "hoken"), ("国庫負担（年金の中）", "kokko"),
                ("　過去期間に係る分", "kokko_kako"), ("　将来期間に係る分", "kokko_shorai"),
                ("積立金から得られる財源", "tumi"), ("**給付**", None), ("給付の合計（2025〜2120年度）", "kyufu"),
                ("過去期間に係る給付", "kako"), ("　2階部分", "kako2"), ("　基礎年金分", "kakok"),
                ("　うち、いまの受給者の分", "jukyu"), ("　　2階部分", "jukyu2"),
                ("将来期間に係る給付", "shorai"), ("　2階部分", "shorai2"), ("　基礎年金分", "shoraik")]
        for lab, k in rows:
            if k is None:
                print(f"| {lab} | | | |")
            else:
                print(f"| {lab} | {f0(gen[k])} | {f0(o[k])} | {o[k] - gen[k]:+,.0f} |")
        z = o["ichi_zenin"]
        print("| **年金の外** | | | |")
        print(f"| 一律給付（2027〜2120年度） | ― | {f0(o['ichi'])} | {o['ichi']:+,.0f} |")
        print(f"| 　0歳からの全員に配る場合：0〜19歳 ／ 20〜64歳 ／ 65歳以上 | ― | "
              f"{f0(z['u20'])} ／ {f0(z['g20'])} ／ {f0(z['o65'])} | |")
        print(f"| 国の支出（国庫負担＋一律給付） | {f0(gen['kokko'])} | {f0(o['kokko'] + o['ichi'])} | "
              f"{o['kokko'] + o['ichi'] - gen['kokko']:+,.0f} |")
        print(f"| 2120年度末の積立金（現在価値） | {f0(gen['tumi120'])} | {f0(o['tumi120'])} | "
              f"{o['tumi120'] - gen['tumi120']:+,.0f} |")
        print(f"\n検算（廃止案）：財源の合計 {f0(o['hoken'] + o['kokko'] + o['tumi'])} ／ 給付の合計 {f0(o['kyufu'])}")
    if "--no-fig" not in sys.argv and out:
        zu(out)
    return out


C = dict(jukyu=N.C_JUKYU, kako=N.C_KAKO, shorai=N.C_SHORAI, kokko=N.C_KOKKO, kokko2=N.C_KOKKO2, tumi=N.C_TUMI,
         hoken="#f2a27e",                                      # 財源：保険料
         kakok="#1f5fae", kako2="#7fb1e8", shoraik="#5a8f8f", shorai2="#b5d6d6",   # 給付：過去・将来 × 基礎・2階
         u20="#d9c8ef", g20="#a98bd6", o65="#6a3d9a")
DARK = (N.C_TUMI, N.C_KOKKO, "#1f5fae", "#5a8f8f")
INK, INK2, GRID = N.INK, N.INK2, N.GRID
NOTE = ("非公式の思考実験：2024年財政検証の計算プログラムの出力（通常試算・過去分試算・受給者分試算・国庫負担の廃止案）から"
        "推定した。厚生労働省の試算ではない。\n金額は名目運用利回りで2024年度末の価値に直した2025〜2120年度の合計（兆円）。"
        "廃止案の過去期間分は、過去分試算の報酬比例に廃止案と同じ削り率を掛けた推定。")
LABEL = {"gen": "現行制度", "hai": "国庫負担の廃止＋一律給付"}


def _style(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _save(fig, name):
    d = os.path.join(HERE, "図")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"一律給付_バランスシート_{name}.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)


def zu(out):
    plt = _plt()
    from matplotlib.patches import Patch
    cases = [(c, n) for c, n in CASES if c in out]

    # ---- 図1 バランスシートの並べ比べ：財源（保険料・国庫負担・積立金）と給付（過去・将来 × 2階・基礎）
    fig, axs = plt.subplots(1, len(cases), figsize=(8.2 * len(cases), 8.2), squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        gen, o = out[c]
        w = 0.36
        for x0, d, k in ((0.0, gen, "gen"), (1.25, o, "hai")):
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
            ax.text(x0 + w / 2 + 0.02, -150, f"{LABEL[k]}\n財源　給付", ha="center", va="top", fontsize=10, color=INK)
            ax.text(x0 + w / 2 + 0.02, d["kyufu"] + 25, f"合計 {d['kyufu']:,.0f}", ha="center", fontsize=10, color=INK)
        z = o["ichi_zenin"]
        xb, b = 2.35, 0.0
        for v, col in ((z["o65"], C["o65"]), (z["g20"], C["g20"]), (z["u20"], C["u20"])):
            ax.bar(xb, v, w, bottom=b, color=col, edgecolor="white", lw=1.2)
            ax.text(xb, b + v / 2, f"{v:,.0f}", ha="center", va="center", fontsize=9,
                    color="white" if col == C["o65"] else INK)
            b += v
        ax.text(xb, b + 25, f"合計 {o['ichi']:,.0f}", ha="center", fontsize=10, color=INK)
        ax.text(xb, -150, "一律給付\n（年金の外）", ha="center", va="top", fontsize=10, color=INK)
        ax.set_xticks([])
        ax.set_xlim(-0.4, 2.7)
        ax.set_ylim(0, 2550)
        ax.set_ylabel("兆円（2024年度末の価値）")
        ax.set_title(f"{name}ケース", fontsize=12, color=INK)
        _style(ax)
    h = [Patch(color=C[k], label=l) for k, l in (
        ("hoken", "財源：保険料"), ("kokko", "財源：国庫負担"), ("tumi", "財源：積立金"),
        ("kakok", "給付：過去期間の基礎年金"), ("kako2", "給付：過去期間の2階部分"),
        ("shoraik", "給付：将来期間の基礎年金"), ("shorai2", "給付：将来期間の2階部分"),
        ("o65", "一律給付：65歳以上"), ("g20", "一律給付：20〜64歳"), ("u20", "一律給付：0〜19歳"))]
    fig.legend(handles=h, loc="lower center", ncol=5, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.07))
    fig.suptitle("年金の財源と給付はどう変わるか — 国庫負担が年金の外の一律給付になり、2階部分の給付がその分減る（非公式の推定）\n"
                 "財源と給付は2025〜2120年度の合計。一律給付は0歳からの全員に配る場合の年齢の内訳",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.13, 1, 0.94))
    _save(fig, "比較")
    plt.close(fig)

    # ---- 図2 何がいくら変わるか（差の横棒）
    fig, axs = plt.subplots(1, len(cases), figsize=(7.4 * len(cases), 6.2), sharey=True, squeeze=False)
    items = [("財源：保険料", "hoken", C["hoken"]), ("財源：国庫負担（年金の中）", "kokko", C["kokko"]),
             ("財源：積立金", "tumi", C["tumi"]),
             ("給付：過去期間の2階部分\n（いまの受給者）", "jukyu2", C["kako2"]),
             ("給付：過去期間の2階部分\n（まだ受け取っていない人）", "kako2_mada", C["kako2"]),
             ("給付：過去期間の基礎年金", "kakok", C["kakok"]),
             ("給付：将来期間の2階部分", "shorai2", C["shorai2"]),
             ("給付：将来期間の基礎年金", "shoraik", C["shoraik"]),
             ("年金の外：一律給付", "ichi", C["g20"])]
    for ax, (c, name) in zip(axs[0], cases):
        gen, o = out[c]
        for d in (gen, o):
            d["kako2_mada"] = d["kako2"] - d["jukyu2"]
        gen.setdefault("ichi", 0.0)
        ys = list(range(len(items)))[::-1]
        for y, (lab, k, col) in zip(ys, items):
            v = o[k] - gen[k]
            ax.barh(y, v, 0.62, color=col, edgecolor="white")
            ax.text(v + (6 if v >= 0 else -6), y, f"{v:+,.0f}", va="center", ha="left" if v >= 0 else "right",
                    fontsize=9.5, color=INK)
        ax.axvline(0, color=INK, lw=0.8)
        ax.axhline(5.5, color=GRID, lw=1)
        ax.set_yticks(ys)
        ax.set_yticklabels([x[0] for x in items], fontsize=9)
        ax.set_xlim(-520, 520)
        ax.set_xlabel("廃止案 − 現行制度（兆円、2024年度末の価値）")
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        _style(ax, "x")
    fig.suptitle("何がいくら変わるか — 減るのは国庫負担と2階部分の給付、増えるのは一律給付（非公式の推定）",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "変化")
    plt.close(fig)

    # ---- 図3 国庫負担の行き先（横棒）
    fig, axs = plt.subplots(len(cases), 1, figsize=(12, 3.4 * len(cases)), squeeze=False)
    for ax, (c, name) in zip(axs[:, 0], cases):
        gen, o = out[c]
        z = o["ichi_zenin"]
        rows = [("現行制度", [(gen["kokko_kako"], C["kokko"]), (gen["kokko_shorai"], C["kokko2"])]),
                ("廃止案：一律給付を\n0歳からの全員に", [(o["kokko_kako"], C["kokko"]), (o["kokko_shorai"], C["kokko2"]),
                                             (z["o65"], C["o65"]), (z["g20"], C["g20"]), (z["u20"], C["u20"])]),
                ("廃止案：一律給付を\n65歳以上の全員に", [(o["kokko_kako"], C["kokko"]), (o["kokko_shorai"], C["kokko2"]),
                                              (o["ichi"], C["o65"])])]
        for i, (lab, segs) in enumerate(rows):
            y, b = 2 - i, 0.0
            for v, col in segs:
                ax.barh(y, v, 0.62, left=b, color=col, edgecolor="white", lw=1.2)
                if v > 25:
                    ax.text(b + v / 2, y, f"{v:,.0f}", ha="center", va="center", fontsize=9,
                            color="white" if col in (C["kokko"], C["o65"]) else INK)
                b += v
            ax.text(b + 6, y, f"計 {b:,.0f}", va="center", fontsize=9.5, color=INK)
        ax.set_yticks([2, 1, 0])
        ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
        ax.set_xlim(0, max(gen["kokko"], o["kokko"] + o["ichi"]) * 1.12)
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK, loc="left")
        ax.set_xlabel("兆円（2024年度末の価値）")
        _style(ax, "x")
    h = [Patch(color=C["kokko"], label="年金の中：過去期間分"), Patch(color=C["kokko2"], label="年金の中：将来期間分"),
         Patch(color=C["o65"], label="一律給付：65歳以上"), Patch(color=C["g20"], label="一律給付：20〜64歳"),
         Patch(color=C["u20"], label="一律給付：0〜19歳")]
    fig.legend(handles=h, loc="lower center", ncol=5, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.06))
    fig.suptitle("国庫負担の行き先 — 合計は変わらず、年金の過去期間分から一律給付へ移る（非公式の推定）", fontsize=13, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.11, 1, 0.95))
    _save(fig, "国庫の行き先")
    plt.close(fig)

    # ---- 図4 過去期間に係る給付の内訳（現行と廃止案）
    fig, axs = plt.subplots(1, len(cases), figsize=(6.6 * len(cases), 5.6), sharey=True, squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        gen, o = out[c]
        cats = [("2階部分\nいまの受給者", "jukyu2", None), ("2階部分\nまだ受け取って\nいない人", "kako2", "jukyu2"),
                ("基礎年金分\nいまの受給者", "jukyuk", None), ("基礎年金分\nまだ受け取って\nいない人", "kakok", "jukyuk")]
        for i, (lab, k, sub) in enumerate(cats):
            for j, (d, col) in enumerate(((gen, "#9a9a9a"), (o, C["jukyu"]))):
                v = d[k] - (d[sub] if sub else 0.0)
                ax.bar(i + (j - 0.5) * 0.36, v, 0.34, color=col, edgecolor="white")
                ax.annotate(f"{v:,.0f}", (i + (j - 0.5) * 0.36, v), xytext=(0, 3), textcoords="offset points",
                            ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(4))
        ax.set_xticklabels([x[0] for x in cats], fontsize=9)
        ax.set_title(f"{name}ケース（一律削減 {(1 - o['m']) * 100:.1f}%）", fontsize=11.5, color=INK)
        ax.set_ylim(0, 430)
        _style(ax)
    axs[0][0].set_ylabel("兆円（2024年度末の価値）")
    axs[0][0].legend(handles=[Patch(color="#9a9a9a", label="現行制度"), Patch(color=C["jukyu"], label="国庫負担の廃止＋一律給付")],
                     frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("過去期間に係る給付のうち、削られるのは2階部分だけ（いまの受給者も含めて一律）（非公式の推定）",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.005, NOTE, fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "過去期間の内訳")
    plt.close(fig)

    # ---- 図5 年度ごとの給付（名目）と一律給付
    fig, axs = plt.subplots(1, len(cases), figsize=(6.6 * len(cases), 5.8), squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        gen, o = out[c]
        ys = list(range(Y0 + 1, Y1 + 1))
        tot = [o["nendo"][y][0] for y in ys]
        kako = [o["nendo"][y][1] for y in ys]
        juk = [o["nendo"][y][2] for y in ys]
        ichi = [o["ichi_nen"].get(y, 0.0) for y in ys]
        ax.stackplot(ys, juk, [a - b for a, b in zip(kako, juk)], [a - b for a, b in zip(tot, kako)], ichi,
                     colors=(C["jukyu"], C["kako"], C["shorai"], C["g20"]), lw=0)
        ax.plot(ys, [gen["nendo"][y][0] for y in ys], color=INK, lw=1.4, ls="--", label="現行制度：給付計")
        ax.plot(ys, [gen["nendo"][y][1] for y in ys], color=INK, lw=1.2, ls=":", label="現行制度：過去期間に係る分")
        ax.set_xlim(2025, 2120)
        ax.set_ylim(0, None)
        ax.set_title(f"{name}ケース", fontsize=11.5, color=INK)
        ax.set_xlabel("年度")
        ax.set_ylabel("兆円（名目）")
        _style(ax)
    h = [Patch(color=C["jukyu"], label="廃止案：過去期間・いまの受給者"),
         Patch(color=C["kako"], label="廃止案：過去期間・まだ受け取っていない人"),
         Patch(color=C["shorai"], label="廃止案：将来期間"), Patch(color=C["g20"], label="一律給付（年金の外）")]
    h2, _ = axs[0][0].get_legend_handles_labels()
    axs[0][-1].legend(handles=h + h2, frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle("毎年の給付（名目）— 帯が廃止案、線が現行制度。年金の給付が減った分と同じくらいが一律給付になる（非公式の推定）",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE.replace("金額は名目運用利回りで2024年度末の価値に直した2025〜2120年度の合計（兆円）。",
                                      "この図は年度ごとの名目の額。"), fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    _save(fig, "年度別")
    plt.close(fig)

    # ---- 図6 年度ごとの財源（名目）：現行と廃止案
    fig, axs = plt.subplots(len(cases), 2, figsize=(13, 5.2 * len(cases)), squeeze=False)
    for i, (c, name) in enumerate(cases):
        gen, o = out[c]
        ys = list(range(Y0 + 1, Y1 + 1))
        top = 0
        for j, (d, k) in enumerate(((gen, "gen"), (o, "hai"))):
            ax = axs[i][j]
            hok = [d["hoken_nen"].get(y, 0.0) for y in ys]
            kok = [d["kokko_nen"].get(y, 0.0) for y in ys]
            tum = [d["nendo"][y][0] - a - b for y, a, b in zip(ys, hok, kok)]
            ichi = [o["ichi_nen"].get(y, 0.0) if k == "hai" else 0.0 for y in ys]
            ax.stackplot(ys, hok, kok, [max(t, 0) for t in tum], ichi,
                         colors=(C["hoken"], C["kokko"], C["tumi"], C["g20"]), lw=0)
            ax.plot(ys, [gen["nendo"][y][0] for y in ys], color=INK, lw=1.2, ls="--")
            ax.set_xlim(2025, 2120)
            top = max(top, max(a + b + max(t, 0) + e for a, b, t, e in zip(hok, kok, tum, ichi)))
            ax.set_title(f"{name}ケース：{LABEL[k]}", fontsize=11, color=INK)
            ax.set_ylabel("兆円（名目）")
            _style(ax)
        for j in range(2):
            axs[i][j].set_ylim(0, top * 1.05)
    h = [Patch(color=C["hoken"], label="保険料"), Patch(color=C["kokko"], label="国庫負担（年金の中）"),
         Patch(color=C["tumi"], label="積立金から（取り崩しと運用収入）"), Patch(color=C["g20"], label="一律給付（年金の外）")]
    from matplotlib.lines import Line2D
    h.append(Line2D([], [], color=INK, ls="--", label="現行制度の年金の給付"))
    fig.legend(handles=h, loc="lower center", ncol=5, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.045))
    fig.suptitle("毎年の財源（名目）— 国庫負担の緑が細くなり、その分が年金の外の一律給付になる（非公式の推定）",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.005, NOTE.replace("金額は名目運用利回りで2024年度末の価値に直した2025〜2120年度の合計（兆円）。",
                                      "この図は年度ごとの名目の額。積立金からの財源は 給付 − 保険料 − 国庫負担 で、"
                                      "積立金が増える年（負）は0として描いた。"), fontsize=8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.08, 1, 0.96))
    _save(fig, "財源の年度別")
    plt.close(fig)


if __name__ == "__main__":
    main()
