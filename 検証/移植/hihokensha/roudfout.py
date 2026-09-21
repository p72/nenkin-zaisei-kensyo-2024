# -*- coding: utf-8 -*-
"""
被保険者推計/roudfout.c の忠実移植
==================================
労働力関係の出力。41ファイル書く。

    wakuroud{BANGO}-{00..39}.csv  分類 × 性 × 年度 × 年齢     40本
    waku{BANGO}-roudkei.csv       年齢計（分類を横に並べる）

40 の「分類」（`bunrui`）
------------------------
`roudfout.c:38-159` の `switch`。`_c`（年央）と `_m`（年度末）が
交互に並ぶ（`setjinko.py` の解説を参照）。

     0/1   人口                 jinko_c / jinko_m
     2/3   労働力人口           roud_j_c / roud_j_m
     4/5   就業者               syugyo_j_c / syugyo_j_m
     6/7   総雇用者             koyou_j_*[0]
     8/9   正規雇用者           koyou_j_*[1]
    10/11  非正規フル           koyou_j_*[2]
    12/13  非正規（30〜34時間） koyou_j_*[6]
    14/15  非正規（20〜29時間） koyou_j_*[4] + [5]
    16/17  非正規（20時間未満） koyou_j_*[3]
    18/19  被用者               koyou_j_*[7]
    20/21  正規被用者           koyou_j_*[8]
    22/23  非正規フル被用者     koyou_j_*[9]
    24/25  非正規フル以外被用者 koyou_j_*[10]
    26/27  自営業者             jieigyo_j_c / jieigyo_j_m
    28/29  総労働時間           soroudh_*[0] × 12 / 10000
    30/31  正規労働時間         soroudh_*[1] × 12 / 10000
    32/33  非正規フル労働時間   soroudh_*[2] × 12 / 10000
    34/35  非正規フル以外       soroudh_*[3] × 12 / 10000
    36/37  自営労働時間         soroudh_*[4] × 12 / 10000
    38/39  被用者労働時間       soroudh_*[9] × 12 / 10000

労働時間だけ `× 12 / 10000`（`roudfout.c:124` ほか）。`12` と `10000` は
`int` だが `double` に格上げされるので `(x * 12.0) / 10000.0`。
左から順に評価するので、移植版も同じ順で書く。

`waku{BANGO}-roudkei.csv` の最後の列
------------------------------------
`roudfout.c:207` が `raund(heikinh_c[10][年度] * 1000000, 0)` を足す。
被用者の平均労働時間（年額を100万倍した整数）。

原本の癖をそのまま残しているところ
----------------------------------
1. **見出しの数と分類の数が合わない**（`roudfout.c:194-201`）
   見出しは先頭に空欄を1つ置いてから40個並べ、最後に
   「被用者平均労働時間央」を足して41列。データ行は
   `"%4d, 0,"` で年度と 0 を出してから40個＋1個。
   `0` の列に見出しが無い（空欄がそれに当たる）。

2. **`nenrei_kei_ninzu[46][…]` だが使うのは 0〜39**
   （`roudfout.c:16`）。40 以上は触らない。

3. **`-roudkei.csv` は `nenrei_kei_ninzu` を年度ごとにそのまま出す**
   `fout.c` の `-nenkeikan.csv` のような前年度との平均は無いので、
   未初期化を読む問題は起きない。

4. **`raund(heikinh_c[10][…] * 1000000, 0)` は `int` を経由する**
   `heikinh_c[10]` は 1000〜2000 程度（時間）なので、100万倍すると
   10^9 のオーダーになり `int` の上限 2.1×10^9 に近い。
   これを超えると原本は壊れる（`cnum.py` の `raund` の解説）。
   同梱データでは 1.7×10^9 程度で収まっている。
"""
import sys

import numpy as np

from cnum import raund
from fopn import P
from fout import fmt6
from glva import G
from setconst import ENDY, KF, KS, STARTY

__all__ = ["roudfout"]

NB = 40
A0, A1 = 15, 121
KEI_OFF = 100 - A0

# roudfout.c:38-159。(配列名, 添字 or None, 時間か)
#   時間のものは × 12 / 10000 を掛ける
_SEL = {
    0: ("jinko_c", None, False), 1: ("jinko_m", None, False),
    2: ("roud_j_c", None, False), 3: ("roud_j_m", None, False),
    4: ("syugyo_j_c", None, False), 5: ("syugyo_j_m", None, False),
    6: ("koyou_j_c", 0, False), 7: ("koyou_j_m", 0, False),
    8: ("koyou_j_c", 1, False), 9: ("koyou_j_m", 1, False),
    10: ("koyou_j_c", 2, False), 11: ("koyou_j_m", 2, False),
    12: ("koyou_j_c", 6, False), 13: ("koyou_j_m", 6, False),
    # 14/15 は [4] + [5]
    16: ("koyou_j_c", 3, False), 17: ("koyou_j_m", 3, False),
    18: ("koyou_j_c", 7, False), 19: ("koyou_j_m", 7, False),
    20: ("koyou_j_c", 8, False), 21: ("koyou_j_m", 8, False),
    22: ("koyou_j_c", 9, False), 23: ("koyou_j_m", 9, False),
    24: ("koyou_j_c", 10, False), 25: ("koyou_j_m", 10, False),
    26: ("jieigyo_j_c", None, False), 27: ("jieigyo_j_m", None, False),
    28: ("soroudh_c", 0, True), 29: ("soroudh_m", 0, True),
    30: ("soroudh_c", 1, True), 31: ("soroudh_m", 1, True),
    32: ("soroudh_c", 2, True), 33: ("soroudh_m", 2, True),
    34: ("soroudh_c", 3, True), 35: ("soroudh_m", 3, True),
    36: ("soroudh_c", 4, True), 37: ("soroudh_m", 4, True),
    38: ("soroudh_c", 9, True), 39: ("soroudh_m", 9, True),
}

_SEI_LABEL = ("男女計", "男", "女", "女有配偶", "女無配偶")

# roudfout.c:194-201 の列見出し
_HEAD = (
    ",人口央,人口末,労働力人口央,労働力人口末,就業者央,就業者末,"
    "総雇用者数央,総雇用者数末,正規雇用者数央,正規雇用者数末,"
    "非正規（フル）雇用者数央,非正規（フル）雇用者数末,"
    "非正規（30～34時間）雇用者数央,非正規（30～34時間）雇用者数末,"
    "非正規（20～29時間）雇用者数央,非正規（20～29時間）雇用者数末,"
    "非正規（20時間未満）雇用者数央,非正規（20時間未満）雇用者数末,"
    "被用者数央,被用者数末,正規被用者数央,正規被用者数末,"
    "非正規（フル）被用者数央,非正規（フル）被用者数末,"
    "非正規（フル以外）被用者数央,非正規（フル以外）被用者数末,"
    "自営業者数央,自営業者数末,"
    "総労働時間央,総労働時間末,正規労働時間央,正規労働時間末,"
    "非正規（フル）労働時間央,非正規（フル）労働時間末,"
    "非正規（フル以外）労働時間央,非正規（フル以外）労働時間末,"
    "自営労働時間央,自営労働時間末,被用者労働時間央,被用者労働時間末,"
    "被用者平均労働時間央\n"
)


def _vec(bunrui, y, sei):
    """`roudfout.c:38-159` の `switch` を年齢 15〜120 のベクトルで返す。"""
    if bunrui == 14:
        return (G.koyou_j_c[4, y, sei, A0:A1] + G.koyou_j_c[5, y, sei, A0:A1])
    if bunrui == 15:
        return (G.koyou_j_m[4, y, sei, A0:A1] + G.koyou_j_m[5, y, sei, A0:A1])
    name, idx, is_time = _SEL[bunrui]
    a = getattr(G, name)
    v = a[y, sei, A0:A1] if idx is None else a[idx, y, sei, A0:A1]
    if is_time:
        # roudfout.c:124。`x * 12 / 10000` を左から
        return v * 12 / 10000
    return v


def _open_w(path):
    try:
        return open(path, "w", encoding="utf-8", newline="")
    except OSError:
        print("出力wakuファイルを開けません!", file=sys.stderr)
        raise SystemExit(2)


def roudfout():
    """roudfout.c:10 の忠実移植。"""
    BANGO = G.BANGO
    # double nenrei_kei_ninzu[46][131][5]（癖 2.）
    kei = np.zeros((46, ENDY - STARTY + 1, 5), dtype=np.float64)

    for bunrui in range(NB):
        out = [f"試算番号,BANGO=,{BANGO}\n", "分類,性,年度,計,"]
        out.append("".join(f"{ii:02d}," for ii in range(15, 100)))
        out.append("100\n")
        for sei in range(0, 5):
            for nendo in range(KS, KF + 1):
                y = nendo - STARTY
                v = np.asarray(_vec(bunrui, y, sei), dtype=np.float64)
                kei[bunrui, y, sei] = np.add.accumulate(v)[-1]
                v100 = np.add.accumulate(v[KEI_OFF:])[-1]
                out.append(f"roud-{bunrui:2d},{sei:1d},{nendo:4d},")
                out.append(fmt6(raund(float(kei[bunrui, y, sei]), 0)) + ",")
                out.append("".join(
                    fmt6(raund(float(v[i]), 0)) + ","
                    for i in range(0, 100 - A0)))
                out.append(fmt6(raund(float(v100), 0)) + "\n")
        with _open_w(P.wakuroud(BANGO, bunrui)) as f:
            f.write("".join(out))

    # ---- 年齢計。roudfout.c:177-210 ----
    out = [f"15歳以上全年齢,試算番号,BANGO=,{BANGO},",
           f"出生率,JIN=,{G.JIN},",
           f"死亡率,QX=,{G.QX},",
           f"労働力率,ROUDR=,{G.ROUDR}\n"]
    for sei in range(0, 5):
        out.append(_SEI_LABEL[sei] + ", ")
        out.append(_HEAD)
        for nendo in range(KS, KF + 1):
            y = nendo - STARTY
            out.append(f"{nendo:4d}, 0,")
            out.append("".join(
                fmt6(raund(float(kei[b, y, sei]), 0)) + ","
                for b in range(0, NB)))
            out.append(fmt6(raund(float(G.heikinh_c[10, y]) * 1000000, 0))
                       + " \n")
    with _open_w(P.roudkei(BANGO)) as f:
        f.write("".join(out))
