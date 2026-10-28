#!/usr/bin/env python3
"""厚生年金の国庫負担を廃止して国民全員に一律給付（財政均衡）に、年4兆円の一律給付を上乗せしたら：損得（思考実験・非公式・推定）。

「…国民全員に一律給付したら」の案（予備番号701）の一律給付に、別の財源（赤字国債）で年4兆円を上乗せする。
上乗せは2027年度に4兆円（2024年度の物価）とし、そのあとは一律給付の総額と同じ割合で動かす。
つまり1人あたりの一律給付を、どの年度も同じ倍率 f ＝ 1 ＋ 4兆円 ÷ 2027年度の一律給付の総額 にする。
年金の側（報酬比例の一律カット）は変えない。上乗せの財源（国債の返済）は損得に入れない。

損得の出し方は 得する人の割合.py（厚労省「年金額の分布推計」で重み付け）と 標準報酬別の損得.py（仮想の会社員）と同じで、
一律給付だけを f 倍にする。経済前提は、分布推計が出ている過去30年投影（3003）と成長型経済移行・継続（3002）。

使い方（リポジトリの直下で。得する人の割合.py の準備がしてあること）
  python3 勉強/応用編/一律給付の上乗せ.py report      # 記事の表
  python3 勉強/応用編/一律給付の上乗せ.py graph       # 記事の図（図/得する人の割合_上乗せ4兆円.png ほか）
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADD = 4.0                                  # 上乗せ（兆円、2027年度・2024年度の物価）
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"))


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


T = _load("tokusuru", "得する人の割合.py")
H = _load("hyojun", "標準報酬別の損得.py")
K = T.G.K


def bairitsu(case):
    """1人あたりの一律給付の倍率 f。2027年度の一律給付の総額（実質）に ADD を足した比。"""
    s = K.shinkyufu(case, "zenin")[2027]
    return 1 + ADD / (s["zaigen"] * s["getsu_r"] / s["getsu"])


F = {case: bairitsu(case) for case, _ in CASES}


def _install(mod):
    """mod（得する人の割合.py か 標準報酬別の損得.py）の一律給付を F 倍にする。元に戻す関数を返す。"""
    orig = mod.G._series

    def series(case, rate):
        S = dict(orig(case, rate))
        S["ichi"] = dict(S["ichi"])
        S["ichi"]["zenin"] = {y: v * F[case] for y, v in S["ichi"]["zenin"].items()}
        return S

    mod.G._series = series
    if hasattr(mod, "_CACHE"):
        mod._CACHE.clear()

    def undo():
        mod.G._series = orig
        if hasattr(mod, "_CACHE"):
            mod._CACHE.clear()
    return undo


def _both(fn):
    """上乗せなし・ありの2回、fn(...) を呼んで (なし, あり) を返す。"""
    a = fn()
    u1, u2 = _install(T), _install(H)
    try:
        b = fn()
    finally:
        u1()
        u2()
    return a, b


def report():
    for case, cname in CASES:
        f = F[case]
        s = K.shinkyufu(case, "zenin")
        print(f"## {cname}：1人あたりの一律給付を {f:.3f} 倍\n")
        print("| 年度 | 1人あたり月額（2024年度の物価）：上乗せなし → あり | 手取りに対して |")
        print("|---|---|---|")
        for y in (2027, 2040, 2060, 2100):
            print(f"| {y} | {s[y]['getsu_r']:,.0f}円 → {s[y]['getsu_r'] * f:,.0f}円 | {s[y]['wari']:.1f}% → {s[y]['wari'] * f:.1f}% |")
        (r0, _), (r1, _) = _both(lambda: T.keisan(case))
        print("\n| 生まれた年度 | 得をする人（男女計）なし → あり | 男性 | 女性 | 男女計の平均（万円）なし → あり | 男性の平均 | 女性の平均 |")
        print("|---|---|---|---|---|---|---|")
        for c in T.COHORTS:
            a, b = r0[c], r1[c]
            print(f"| {c} | {a['計']['share'] * 100:.0f}% → **{b['計']['share'] * 100:.0f}%** | "
                  f"{a['男']['share'] * 100:.0f} → {b['男']['share'] * 100:.0f}% | {a['女']['share'] * 100:.0f} → {b['女']['share'] * 100:.0f}% | "
                  f"{a['計']['mean']:+,.0f} → **{b['計']['mean']:+,.0f}** | {a['男']['mean']:+,.0f} → {b['男']['mean']:+,.0f} | "
                  f"{a['女']['mean']:+,.0f} → {b['女']['mean']:+,.0f} |")
        print("\n| 標準報酬月額 | 単身：損から得に変わる生年度 なし → あり | 1962年度生まれ なし → あり | 夫婦：なし → あり | 1962年度生まれ なし → あり |")
        print("|---|---|---|---|---|")

        def tbl():
            H._CACHE.clear()
            _, W24, _ = H.keisan(case)
            return {(typ, x): (H.tenkan(v := H.songoku(case, typ, x)), v[1962]) for typ in ("s", "f") for x in H.LEVELS}, W24
        (t0, W24), (t1, _) = _both(tbl)
        H._CACHE.clear()

        def nen(t):
            return "どの世代も得" if t is None else (f"{t}年度" if t != "—" else "2060年度まで損")
        for x in H.LEVELS:
            print(f"| {H.label(x, W24)} | {nen(t0['s', x][0])} → **{nen(t1['s', x][0])}** | {t0['s', x][1]:+,.0f} → {t1['s', x][1]:+,.0f} | "
                  f"{nen(t0['f', x][0])} → **{nen(t1['f', x][0])}** | {t0['f', x][1]:+,.0f} → {t1['f', x][1]:+,.0f} |")
        print()


def graph():
    u1, u2 = _install(T), _install(H)
    title = "厚生年金の国庫負担を廃止して国民全員に一律給付（財政均衡）＋年4兆円を上乗せ"
    note = (f"一律給付は年{ADD:.0f}兆円（2027年度・2024年度の物価）の上乗せで、1人あたり"
            + "・".join(f"{F[c]:.2f}倍（{n}）" for c, n in CASES) + "。上乗せの財源（赤字国債の返済）は損得に入れていない。")
    keep = (T.TITLE, T.NOTE_ADD, T.SUFFIX, H.TITLE, H.NOTE_ADD, H.SUFFIX, H.CASES, H.NOTE)
    try:
        T.TITLE, T.NOTE_ADD, T.SUFFIX = title, note, "_上乗せ4兆円"
        H.TITLE, H.NOTE_ADD, H.SUFFIX, H.CASES = title, note, "_上乗せ4兆円", CASES
        H.NOTE = H.NOTE.replace("独自の前提Aは、実質は過去30年投影のまま物価だけ2%にしたもの。", "")
        H._CACHE.clear()
        T.graph()
        H.graph()
    finally:
        T.TITLE, T.NOTE_ADD, T.SUFFIX, H.TITLE, H.NOTE_ADD, H.SUFFIX, H.CASES, H.NOTE = keep
        u1()
        u2()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": report, "graph": graph}[cmd]()
