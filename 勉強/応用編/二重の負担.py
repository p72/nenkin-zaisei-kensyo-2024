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
  python3 勉強/応用編/二重の負担.py
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
    o["nendo"] = {y: (out[""]["nen"].get(y, 0.0), out["AK"]["nen"].get(y, 0.0), out["AJ"]["nen"].get(y, 0.0))
                  for y in range(Y0 + 1, Y1 + 1)}
    return o


def f0(x):
    return f"{x:,.0f}"


def kohyo(case, k):
    v = KOHYO.get(case, {}).get(k)
    return f"{v:,}" if v is not None else "―"


def main():
    ok = False
    for case, name in CASES:
        o = keisan(case)
        if o is None:
            print(f"（未計算）{name}：通常試算・過去分試算・受給者分試算の3本が要る", file=sys.stderr)
            continue
        ok = True
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
        print(f"\n検算：{f0(o['kako'])} − {f0(o['kokko_kako'])} − {f0(o['tumi24'])} ＝ {f0(o['nijuu'])}")
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


if __name__ == "__main__":
    main()
