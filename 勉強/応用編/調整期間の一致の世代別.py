#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""マクロ経済スライドの調整期間を一致させたら、誰の年金が減って誰の年金が増えるか（年度別・世代別・世帯別）

「調整期間の一致のバランスシート」と同じ試算（現行制度 000、調整期間の一致 TOUGOU=1 の統一カット率 101）を、
年度ごと・生まれた年度ごとに並べる。計算プログラムは流し直さず、出力を集計する。

  年度別   ：基礎年金給付費（制度計）と2階部分（厚生年金の独自給付＋国民年金の独自給付＋福祉）の名目額の差
  調整割合 ：④⑤が書く給付水準調整割合 R(年度, 年齢)（cuta＝基礎年金、cutb＝報酬比例、emp/rslt/ez_arev/cutr）。
             スライド前の年金額は2つの試算で同じなので、R の比がそのまま年金額の比になる
  世代別   ：2025年度以降に受け取る年金を、生存率で重み付けし、実質運用利回りで割り引いて足したもの
             （世代別の損得.py のモデル世帯。99歳まで。2025年度に65歳を超えている世代は、2025年度の年齢から）。
             調整期間の一致は、現行制度の基礎年金に cuta の比、報酬比例に cutb の比を掛ける

使い方（リポジトリの直下で。調整期間の一致のバランスシート.py の手順で 000 と 101 を流しておく）
  python3 勉強/応用編/調整期間の一致の世代別.py            # 表と図（勉強/応用編/図/調整期間の一致_世代別_*.png）
  python3 勉強/応用編/調整期間の一致の世代別.py --no-fig
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


B = _load("tougou_bs", "調整期間の一致のバランスシート.py")
S = _load("sedai", "世代別の損得.py")
N, M = B.N, S.M
SUURI = S.SUURI
CASES = B.CASES
CUTR = os.path.join(SUURI, "emp", "rslt", "ez_arev", "cutr")
COHORTS = range(1935, 2006)
# 世帯：(名前, 報酬比例の倍率)。夫婦と基礎年金だけは別に計算する
TYPES = (("hi", "高い報酬の単身（男・報酬が平均の1.5倍）"), ("tan", "会社員の単身（男・平均的な報酬）"),
         ("lo", "低い報酬の単身（男・報酬が平均の0.5倍）"), ("fufu", "夫婦（会社員の夫＋同い年の専業の妻）"),
         ("kiso", "基礎年金だけの単身（男女計）"))
BAI = {"hi": 1.5, "tan": 1.0, "lo": 0.5}


def wariai(case):
    """{"k"/"h": 関数(年度, 年齢) → 調整期間の一致 ÷ 現行制度}（k＝基礎年金、h＝報酬比例）"""
    v = f"{case}-{case}-{case}-{case}"
    out = {}
    for key, ab in (("k", "cuta"), ("h", "cutb")):
        c0 = M._read_cut(os.path.join(CUTR, f"{ab}-{v}-1120-000.csv"))
        c1 = M._read_cut(os.path.join(CUTR, f"{ab}-{v}-1120-101.csv"))

        def f(y, a, c0=c0, c1=c1):
            y, a = min(max(y, 2025), 2120), min(a, 115)
            return c1[y][a] / c0[y][a]
        out[key] = f
    return out


def nendo(case):
    """年度別の名目の給付（兆円）。{"gen"/"tg": {"kiso": {年度: 値}, "nikai": {年度: 値}}} と、
    減る年度・増える年度の差の現在価値（2024年度末の価値）"""
    r = B.keisan(case)
    if r is None:
        return None
    d = N.load(case, "", N.RUN_GENKOU)
    mid, _ = N.factors(d["rate"])
    out = {k: dict(kiso=r[k]["kiso_nen"], nikai=r[k]["nikai_nen"]) for k in ("gen", "tg")}
    neg = pos = 0.0
    for y in range(B.Y0 + 1, B.Y1 + 1):
        x = sum(out["tg"][s][y] - out["gen"][s][y] for s in ("kiso", "nikai")) / mid[y]
        if x < 0:
            neg += x
        else:
            pos += x
    out["pv_neg"], out["pv_pos"] = neg, pos
    out["neg_years"] = [y for y in range(B.Y0 + 1, B.Y1 + 1)
                        if sum(out["tg"][s][y] for s in ("kiso", "nikai")) < sum(out["gen"][s][y] for s in ("kiso", "nikai")) - 1e-9]
    out["bs"] = r
    # 積立度合（前年度末の積立金 ÷ その年度の給付、公的年金全体）
    for k, run in (("gen", N.RUN_GENKOU), ("tg", N.RUN_TOUGOU)):
        dd = N.load(case, "", run)
        out[k]["tumido"] = {y: dd["tumi"][y - 1] / (dd["kiso"][y] + dd["dok"][y] + dd["fuku"][y] + dd["kn2"][y])
                            for y in range(B.Y0 + 1, B.Y1 + 1)}
    return out


def sedai(case):
    """{生年度: {世帯: (現行制度, 調整期間の一致)}}（万円、2024年度の物価、受け取り始めの時点の価値）"""
    W = wariai(case)
    Ser, SV = S._series(case, "unyo"), S._survival(case)
    R = Ser["R"]
    out = {}
    for c in COHORTS:
        a0 = max(65, 2025 - c)
        hb = Ser["hirei"](c + 65)
        res = {}
        for tag in ("gen", "tg"):
            t = {k: 0.0 for k, _ in TYPES}
            sm = sf = st = d = 1.0
            for a in range(a0, S.AGE_MAX + 1):
                y = c + a
                if a > a0:
                    sm *= SV["1"](a, y)
                    sf *= SV["2"](a, y)
                    st *= SV["0"](a, y)
                    d /= 1 + R[y]
                k, h = Ser["KISO"][a, y], hb
                if tag == "tg":
                    k *= W["k"](y, a)
                    h *= W["h"](y, a)
                for key, b in BAI.items():
                    t[key] += d * sm * (b * h + k)
                t["kiso"] += d * st * k
                t["fufu"] += d * (sm * (h + k) + sf * k + sf * (1 - sm) * 0.75 * h)
            res[tag] = t
        out[c] = {k: (res["gen"][k] / 1e4, res["tg"][k] / 1e4) for k, _ in TYPES}
    return out


def sakaime(sd, key):
    """損から得に変わる最初の生年度（それより後はずっと得のとき）"""
    cs = sorted(sd)
    for i, c in enumerate(cs):
        if all(sd[x][key][1] >= sd[x][key][0] for x in cs[i:]):
            return c if i > 0 else None      # None：全世代で得
    return None


def pct(g, t):
    return (t / g - 1) * 100


def main():
    res = {}
    for case, name in CASES:
        nd = nendo(case)
        if nd is None:
            print(f"（未計算）{name}", file=sys.stderr)
            continue
        W = wariai(case)
        sd = sedai(case)
        res[case] = dict(nd=nd, W=W, sd=sd)
        g, t = nd["gen"], nd["tg"]
        print(f"\n## {name}ケース\n")
        print("| 年度 | 基礎年金の調整割合の比（65歳） | 報酬比例の調整割合の比（65歳） | 基礎年金（兆円） | 2階部分（兆円） | 給付の計 |")
        print("|---|---|---|---|---|---|")
        for y in (2026, 2030, 2033, 2036, 2040, 2043, 2045, 2050, 2057, 2060, 2080):
            dk = t["kiso"][y] - g["kiso"][y]
            dn = t["nikai"][y] - g["nikai"][y]
            tot = g["kiso"][y] + g["nikai"][y]
            print(f"| {y} | {W['k'](y, 65):.3f} | {W['h'](y, 65):.3f} | {dk:+.1f} | {dn:+.1f} | "
                  f"{(dk + dn) / tot * 100:+.1f}% |")
        neg = [y for y in range(2025, 2121) if t["kiso"][y] + t["nikai"][y] < g["kiso"][y] + g["nikai"][y] - 1e-9]
        print(f"\n給付の計が現行制度を下回る年度：{f'{neg[0]}〜{neg[-1]}年度' if neg else 'なし'}")
        print(f"差の現在価値（2024年度末）：減る年度の計 {nd['pv_neg']:+.1f}、増える年度の計 {nd['pv_pos']:+.1f}、"
              f"計 {nd['pv_neg'] + nd['pv_pos']:+.1f}兆円")
        print("積立度合（年）：" + "、".join(f"{y}年度 {g['tumido'][y]:.1f}→{t['tumido'][y]:.1f}"
                                         for y in (2030, 2050, 2080, 2100, 2120)))
        zg, zt = nd["bs"]["gen"]["seido"], nd["bs"]["tg"]["seido"]
        print(f"2120年度末の積立金（2024年度末の価値）：厚生年金 {nd['bs']['gen']['tumiK_pv'][2120]:.1f}→{nd['bs']['tg']['tumiK_pv'][2120]:.1f}、"
              f"国民年金 {nd['bs']['gen']['tumiN_pv'][2120]:.1f}→{nd['bs']['tg']['tumiN_pv'][2120]:.1f}")
        bg, bt = nd["bs"]["gen"], nd["bs"]["tg"]
        print(f"保険料 {bt['hoken'] - bg['hoken']:+.1f}、積立金 {bt['tumi'] - bg['tumi']:+.1f}")
        print(f"国庫負担 {bt['kokko'] - bg['kokko']:+.1f}、2階部分：いまの受給者 {bt['jukyu2'] - bg['jukyu2']:+.1f}・"
              f"まだ受け取っていない人の過去期間分 {(bt['kako2'] - bt['jukyu2']) - (bg['kako2'] - bg['jukyu2']):+.1f}・"
              f"将来期間分 {bt['shorai2'] - bg['shorai2']:+.1f}、基礎年金：いまの受給者 {bt['jukyuk'] - bg['jukyuk']:+.1f}")
        print("\n| 2025年度の年齢（生年度） | " + " | ".join(n for _, n in TYPES) + " |")
        print("|---|" + "---|" * len(TYPES))
        for c in (1940, 1945, 1950, 1955, 1960, 1965, 1970, 1975, 1980, 1985, 1990, 2000):
            row = " | ".join(f"{pct(*sd[c][k]):+.1f}%（{sd[c][k][1] - sd[c][k][0]:+,.0f}万円）" for k, _ in TYPES)
            print(f"| {2025 - c}歳（{c}） | {row} |")
        print("\n損から得に変わる生年度（2025年度の年齢）：" + "、".join(
            f"{n.split('（')[0]} {sakaime(sd, k)}（{2025 - sakaime(sd, k)}歳）" if sakaime(sd, k) else f"{n.split('（')[0]} 全世代で得"
            for k, n in TYPES))
    if "--no-fig" not in sys.argv and res:
        zu_nendo(res)
        zu_sedai(res)
        zu_mawasu(res)
        zu_tumido(res)


# ---------------------------------------------------------------------------- 図
INK, INK2, GRID = N.INK, N.INK2, N.GRID
COL = {"hi": "#1f5fae", "tan": "#5a8f8f", "lo": "#7fb1e8", "fufu": "#eb6834", "kiso": "#1baf7a"}
NOTE = ("非公式：2024年財政検証の計算プログラム（現行制度と調整期間の一致）の出力から作った推定。厚生労働省の試算ではない。"
        "調整期間の一致は、統一カット率（予備番号101）を読ませて流した。\n")


def _plt():
    return B._plt()


def _save(fig, name):
    d = os.path.join(HERE, "図")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"調整期間の一致_世代別_{name}.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)


def zu_nendo(res):
    """年度ごと：調整割合の比（基礎年金・報酬比例）と、給付の計の差（%）"""
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(15, 5.6))
    ys = list(range(2025, 2081))
    ls = {"3003": "-", "3002": "--"}
    for c, name in CASES:
        if c not in res:
            continue
        W, nd = res[c]["W"], res[c]["nd"]
        axs[0].plot(ys, [(W["k"](y, 65) - 1) * 100 for y in ys], color=B.C["kiso"], ls=ls[c], lw=2,
                    label=f"基礎年金（{name}）")
        axs[0].plot(ys, [(W["h"](y, 65) - 1) * 100 for y in ys], color=B.C["nikai"], ls=ls[c], lw=2,
                    label=f"報酬比例（{name}）")
        g, t = nd["gen"], nd["tg"]
        v = [((t["kiso"][y] + t["nikai"][y]) / (g["kiso"][y] + g["nikai"][y]) - 1) * 100 for y in ys]
        axs[1].plot(ys, v, color=INK, ls=ls[c], lw=2, label=name)
        if c == "3003":
            neg = [y for y, x in zip(ys, v) if x < 0]
            if neg:
                axs[1].axvspan(neg[0] - 0.5, neg[-1] + 0.5, color="#d9534f", alpha=0.12, lw=0)
                axs[1].text((neg[0] + neg[-1]) / 2, min(v) - 0.6, f"{neg[0]}〜{neg[-1]}年度\n現行制度より少ない",
                            ha="center", va="top", fontsize=9.5, color="#b52b27")
                i = v.index(min(v))
                axs[1].annotate(f"{ys[i]}年度 {v[i]:+.1f}%", (ys[i], v[i]), xytext=(18, -4),
                                textcoords="offset points", fontsize=9.5, color=INK)
    axs[0].set_title("65歳の人の年金額：調整期間の一致 ÷ 現行制度 − 1", fontsize=11.5, color=INK)
    axs[1].set_title("年金の給付の合計（基礎年金＋2階部分）：調整期間の一致 ÷ 現行制度 − 1", fontsize=11.5, color=INK)
    for ax in axs:
        ax.axhline(0, color=INK, lw=0.8)
        ax.set_ylabel("%")
        B._style(ax)
    axs[0].legend(fontsize=9, frameon=False, loc="upper left")
    axs[1].legend(fontsize=9.5, frameon=False, loc="upper left")
    lo = min(axs[1].get_ylim()[0], -6)
    axs[1].set_ylim(lo, None)
    fig.suptitle("年度ごとに見ると — 報酬比例はすぐ削られ（2026〜2036年度）、基礎年金の上乗せはあとから効く（非公式の推定）",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.01, NOTE + "左：給付水準調整割合（cuta・cutb）の比。右：基礎年金給付費（制度計）と2階部分（厚生年金・国民年金の独自給付、福祉）の名目額。",
             fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    _save(fig, "年度")
    plt.close(fig)


def zu_sedai(res):
    """生まれた年度ごと：2025年度から先に受け取る年金の合計の変化（%）"""
    plt = _plt()
    cases = [(c, n) for c, n in CASES if c in res]
    fig, axs = plt.subplots(1, len(cases), figsize=(8 * len(cases), 6.4), sharey=True, squeeze=False)
    for ax, (c, name) in zip(axs[0], cases):
        sd = res[c]["sd"]
        xs = sorted(sd)
        for k, lab in TYPES:
            ax.plot(xs, [pct(*sd[x][k]) for x in xs], color=COL[k], lw=2.2, label=lab)
        ax.axhline(0, color=INK, lw=0.9)
        ax.set_title(f"{name}ケース", fontsize=12, color=INK)
        ax.set_xlabel("生まれた年度（下は2025年度の年齢）")
        sec = ax.secondary_xaxis("top", functions=(lambda x: 2025 - x, lambda a: 2025 - a))
        sec.set_xlabel("2025年度の年齢", fontsize=9, color=INK2)
        B._style(ax)
        if c == "3003":
            for i, (k, lab) in enumerate((("fufu", "夫婦・低い報酬の単身"), ("tan", "会社員の単身"), ("hi", "高い報酬の単身"))):
                s = sakaime(sd, k)
                if s:
                    ax.plot([s], [pct(*sd[s][k])], "o", color=COL[k], ms=6)
                    yl = -8.0 + 2.0 * i
                    ax.plot([s, s], [pct(*sd[s][k]), yl], color=COL[k], lw=0.8, ls=":")
                    ax.text(s + 0.6, yl, f"{lab}：いま{2025 - s}歳より若いと得", fontsize=9.5, color=COL[k],
                            va="center", ha="left")
    axs[0][0].set_ylim(-9.5, None)
    axs[0][0].set_ylabel("2025年度から先に受け取る年金の合計の変化（%）")
    axs[0][0].legend(fontsize=9, frameon=False, loc="upper left")
    fig.suptitle("生まれた年度ごとに見ると — 過去30年投影では、いま50〜60歳より上の会社員OBは1〜3%減り、"
                 "若い世代・基礎年金だけの人は増える（非公式の推定）", fontsize=12.5, color=INK)
    fig.text(0.01, 0.01, NOTE + "2025年度から先に受け取る年金（65歳から99歳まで、2025年度に65歳を超えている人はその年齢から）を、"
             "将来推計人口から作った生存率で重み付けし、実質運用利回りで割り引いて足した。\n"
             "報酬比例は65歳時点の額を実質で据え置くとした（世代別の損得.py のモデル世帯）。"
             "調整期間の一致は、年度・年齢ごとの給付水準調整割合の比を掛けた。", fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    _save(fig, "生年度")
    plt.close(fig)


def zu_mawasu(res):
    """「減らした分を回す」のか：減る年度・増える年度の差と、財源の変化、誰の分が変わるか（2024年度末の価値）"""
    plt = _plt()
    cases = [(c, n) for c, n in CASES if c in res]
    fig, axs = plt.subplots(len(cases), 2, figsize=(15, 5.0 * len(cases)), squeeze=False, sharex="col")
    m2 = lambda o: o["kako2"] - o["jukyu2"]
    for i, (c, name) in enumerate(cases):
        nd = res[c]["nd"]
        bg, bt = nd["bs"]["gen"], nd["bs"]["tg"]
        ny = nd["neg_years"]
        left = [(f"給付が減る年度（{ny[0]}〜{ny[-1]}）の合計" if ny else "給付が減る年度：なし", nd["pv_neg"], "#d9534f"),
                (f"給付が増える年度（{ny[-1] + 1 if ny else B.Y0 + 1}〜{B.Y1}）の合計", nd["pv_pos"], B.C["kiso"]),
                ("財源：国庫負担", bt["kokko"] - bg["kokko"], B.C["kokko"]),
                ("財源：保険料", bt["hoken"] - bg["hoken"], B.C["hoken"]),
                ("財源：積立金", bt["tumi"] - bg["tumi"], B.C["tumi"])]
        right = [("2階部分：いまの受給者", bt["jukyu2"] - bg["jukyu2"], "#6c5aa8"),
                 ("2階部分：まだ受け取っていない人の\n過去期間分", m2(bt) - m2(bg), "#9d8fd0"),
                 ("2階部分：将来期間分", bt["shorai2"] - bg["shorai2"], B.C["shorai2"]),
                 ("基礎年金：いまの受給者", bt["jukyuk"] - bg["jukyuk"], "#6c5aa8"),
                 ("基礎年金：それ以外",
                  (bt["kakok"] + bt["shoraik"] - bt["jukyuk"]) - (bg["kakok"] + bg["shoraik"] - bg["jukyuk"]), B.C["shoraik"])]
        for ax, rows, title in ((axs[i][0], left, "給付の差（年度で分ける）と財源の差"),
                                (axs[i][1], right, "誰の分の給付が変わるか")):
            yy = list(range(len(rows)))[::-1]
            for y, (lab, v, cc) in zip(yy, rows):
                ax.barh(y, v, 0.6, color=cc, edgecolor="white")
                ax.annotate(B.d0(v), (v, y), xytext=(4 if v >= 0 else -4, 0), textcoords="offset points",
                            ha="left" if v >= 0 else "right", va="center", fontsize=10, color=INK)
            ax.set_yticks(yy)
            ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
            ax.axvline(0, color=INK, lw=0.8)
            ax.set_title(f"{name}ケース：{title}", fontsize=11.5, color=INK)
            B._style(ax, axis="x")
        axs[i][0].axhline(2.5, color=INK2, lw=0.6, ls=":")
    for j in range(2):
        lo = min(axs[i][j].get_xlim()[0] for i in range(len(cases)))
        hi = max(axs[i][j].get_xlim()[1] for i in range(len(cases)))
        axs[0][j].set_xlim(lo * 1.3 - 5, hi * 1.12)
        axs[-1][j].set_xlabel("調整期間の一致 − 現行制度（兆円、2024年度末の価値）")
    nd = res[cases[0][0]]["nd"]
    bg, bt = nd["bs"]["gen"], nd["bs"]["tg"]
    fig.suptitle(f"「減らした分を回す」のか — 過去30年投影でも、減る年度の分（{nd['pv_neg']:,.0f}兆円）は増える年度の分（{nd['pv_pos']:+,.0f}）の6分の1。"
                 "成長型では減る年度がない（非公式の推定）", fontsize=12.5, color=INK)
    fig.text(0.01, 0.005, NOTE + "名目運用利回りで2024年度末の価値に直した。年度で分けた差は、基礎年金給付費（制度計）と2階部分の名目額の差を割り引いて、"
             "マイナスの年度とプラスの年度で別々に足したもの。", fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))
    _save(fig, "回すのか")
    plt.close(fig)


def zu_tumido(res):
    """積立度合（前年度末の積立金 ÷ 給付）の推移：現行制度と調整期間の一致"""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(12, 6))
    ys = list(range(2026, 2121))
    ls = {"gen": ":", "tg": "-"}
    col = {"3003": "#1f5fae", "3002": "#eb6834"}
    for c, name in CASES:
        if c not in res:
            continue
        nd = res[c]["nd"]
        for k in ("gen", "tg"):
            v = [nd[k]["tumido"][y] for y in ys]
            ax.plot(ys, v, color=col[c], ls=ls[k], lw=2.2, label=f"{name}：{B.LABEL[k]}")
            if c == "3003" and k == "gen":
                continue                                  # 2つとも1.0年分で重なるので1回だけ書く
            ax.annotate(f"{v[-1]:.1f}年分", (ys[-1], v[-1]), xytext=(5, 9 if c == "3003" else 0),
                        textcoords="offset points", va="center", fontsize=9.5, color=col[c])
    ax.axhline(1, color=INK2, lw=0.8, ls="--")
    ax.text(2027, 1.3, "財政均衡の条件（2120年度に給付1年分）", fontsize=9, color=INK2)
    ax.set_xlim(2025, 2130)
    ax.set_ylim(0, None)
    ax.set_ylabel("積立度合（前年度末の積立金 ÷ その年度の給付、年分）")
    ax.legend(fontsize=9.5, frameon=False, loc="upper left")
    B._style(ax)
    fig.suptitle("積立金はどれだけ余るか — 成長型では、現行制度でも調整期間の一致でも、2120年度に給付の1年分を大きく超えて残る（非公式の推定）",
                 fontsize=12, color=INK)
    fig.text(0.01, 0.01, NOTE + "公的年金全体（厚生年金＋国民年金）。給付は基礎年金給付費（制度計）＋厚生年金・国民年金の独自給付＋福祉。"
             "名目額の比。", fontsize=7.8, color=INK2, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    _save(fig, "積立度合")
    plt.close(fig)


if __name__ == "__main__":
    main()
