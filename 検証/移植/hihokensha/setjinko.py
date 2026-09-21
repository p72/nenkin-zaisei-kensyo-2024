# -*- coding: utf-8 -*-
"""
被保険者推計/setjinko.c の忠実移植
==================================
読み込んだ人口を整えて、**年度末の人口**（`jinko_m`）を作る。

`_c` と `_m` の意味
-------------------
①の配列は末尾が `_c` と `_m` で対になっている。

    _c  **年央**。各年10月1日。人口推計のファイルがこの時点の値
    _m  **年度末**。翌年3月31日。`_c` の前後2年から作る

`fout.c:473` / `roudfout.c:194` の見出しが「人口央」→`jinko_c`、
「人口末」→`jinko_m` の順に並んでいることと、`simlkou.c:256-257` が
`koyou_j_c[年度] = (koyou_j_m[年度-1] + koyou_j_m[年度]) / 2.0`（年度末
2つの平均＝年央）としていることから確かめた。実測でも
2021年度の `jinko_c` 計 110,718,012 > `jinko_m` 計 110,575,248 で、
人口が減る局面なので 年央 > 年度末 の向きに合う。

やっていること（`setjinko.c` の上から）
--------------------------------------
1. 106歳以上を105歳に寄せる（`setjinko.c:13-22`）
2. 有配偶割合を `YUHAIGY`（2070）より後の年度へ横引きする（23-27）
3. 女（性2）を有配偶（性3）と無配偶（性4）に割る（28-35）
4. 男女計（性0）を作る（36-41）
5. `STARTY == SJINKOY` を確かめる（42-45）
6. **年央の人口から年度末の人口を作る**（46-96）
7. 総人口の男女計（97-100）

6 の考え方
----------
年央の人口 `jinko_c[年度][性][年齢]`（10月1日）から年度末 `jinko_m`
（翌年3月31日）を作る。10月1日から3月31日へ半年ずらすので、
前後2年・前後2年齢の4点を取って `/2.0` する。**`jinko_wari`（誕生月の
分布）で重みを付ける**場合がある。

    nenrei + SJINKOY - nendo > 0   → 重み付き（jinko_wari を使う）
    それ以外                       → 単純に4点の平均（/4.0）

`nenrei + SJINKOY - nendo` は「2020年度に何歳だったか」で、正のときは
その世代の誕生月の分布（`jinko_wari`）が分かっているという意味に読める。
2020年度より後に生まれた世代（0以下）は分布が無いので単純平均にする。

添字が -1 にならないことの確認
------------------------------
`jinko_c[y][sei][nenrei-1]` を読むのは重み付きの枝だけで、そこは
`nenrei > nendo - SJINKOY >= 0` なので `nenrei >= 1`。
`nendo == STARTY` のときは `nenrei + 0 > 0` つまり `nenrei >= 1`。
`jinko_wari[sei][TMP-1]` も `TMP >= 1` なので 0 以上。**範囲外にならない。**

原本の癖をそのまま残しているところ
----------------------------------
1. **`nenrei == 105` の枝が前年度の同じ年齢を2回足す**
   （`setjinko.c:63-64, 86-87`）。105歳が最高齢（1 で寄せた）なので
   「106歳」に当たる項が無く、同じ値を使っている。重み付きの側は
   `jinko_wari[sei][TMP-1]` と `jinko_wari[sei][TMP]` で重みが違うので
   単純な2倍にはならない。

2. **`sei` のループが 1〜3 だけ**（`setjinko.c:48`）
   性4（女無配偶）は引き算で作る（91-92）。性0は足して作る（93-94）。

3. **`TMP = 0` を入れた直後に上書きしている**（`setjinko.c:50-51`）
   意味は無い。そのまま写した。
"""
import sys

from glva import G
from setconst import ENDY, STARTY

__all__ = ["setjinko"]


def setjinko():
    """setjinko.c:8 の忠実移植。"""
    jc = G.jinko_c
    jm = G.jinko_m
    jw = G.jinko_wari
    yr = G.yuhaig_r
    SJINKOY = G.SJINKOY

    # ---- 1. 106歳以上を105歳に寄せる。setjinko.c:13-22 ----
    # nenrei の昇順に足すので、その順は保つ（浮動小数の足す順が変わる）
    for nendo in range(STARTY, ENDY + 1):
        y = nendo - STARTY
        for sei in (1, 2):
            for nenrei in range(106, 121):
                v = jc[y, sei, nenrei]
                if v > 0.0:
                    jc[y, sei, 105] += v
                    jc[y, sei, nenrei] = 0.0

    # ---- 2. 有配偶割合の横引き。setjinko.c:23-27 ----
    for nendo in range(G.YUHAIGY + 1, ENDY + 1):
        y = nendo - STARTY
        yr[y, 0:106] = yr[y - 1, 0:106]

    # ---- 3. 女を有配偶・無配偶に割る。setjinko.c:28-35 ----
    jc[:, 3, 0:106] = jc[:, 2, 0:106] * yr[:, 0:106]
    jc[:, 4, 0:106] = jc[:, 2, 0:106] - jc[:, 3, 0:106]

    # ---- 4. 男女計。setjinko.c:36-41 ----
    jc[:, 0, 0:106] = jc[:, 1, 0:106] + jc[:, 2, 0:106]

    # ---- 5. setjinko.c:42-45 ----
    if STARTY != SJINKOY:
        print("推計初年度 (STARTY) が人口のスタート年度 (JINKOY) と"
              "一致していません", file=sys.stderr)
        raise SystemExit(2)

    # ---- 6. 年度末の人口。setjinko.c:46-96 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(0, 106):
            for sei in (1, 2, 3):
                if nenrei + SJINKOY - nendo > 0:
                    TMP = nenrei + SJINKOY - nendo   # 直前の TMP = 0 は無意味
                    w0 = 1.0 - jw[sei, TMP - 1]
                    w1 = jw[sei, TMP]
                    if nenrei < 105:
                        jm[y, sei, nenrei] = (
                            jc[y, sei, nenrei - 1] * w0
                            + jc[y, sei, nenrei] * w1
                            + jc[y + 1, sei, nenrei] * w0
                            + jc[y + 1, sei, nenrei + 1] * w1) / 2.0
                    elif nenrei == 105:
                        # 「106歳」の項が無いので同じ年齢を2回使う（癖 1.）
                        jm[y, sei, nenrei] = (
                            jc[y, sei, nenrei - 1] * w0
                            + jc[y, sei, nenrei] * w1
                            + jc[y + 1, sei, nenrei] * w0
                            + jc[y + 1, sei, nenrei] * jw[sei, TMP - 1]) / 2.0
                else:
                    if 0 < nenrei < 105:
                        jm[y, sei, nenrei] = (
                            jc[y, sei, nenrei - 1]
                            + jc[y, sei, nenrei]
                            + jc[y + 1, sei, nenrei]
                            + jc[y + 1, sei, nenrei + 1]) / 4.0
                    elif nenrei == 0:
                        # 「-1歳」の項が無いので同じ年齢を2回使う
                        jm[y, sei, nenrei] = (
                            jc[y, sei, nenrei]
                            + jc[y, sei, nenrei]
                            + jc[y + 1, sei, nenrei]
                            + jc[y + 1, sei, nenrei + 1]) / 4.0
                    elif nenrei == 105:
                        jm[y, sei, nenrei] = (
                            jc[y, sei, nenrei - 1]
                            + jc[y, sei, nenrei]
                            + jc[y + 1, sei, nenrei]
                            + jc[y + 1, sei, nenrei]) / 4.0
            # setjinko.c:91-94。性4は引き算、性0は足し算
            jm[y, 4, nenrei] = jm[y, 2, nenrei] - jm[y, 3, nenrei]
            jm[y, 0, nenrei] = jm[y, 1, nenrei] + jm[y, 2, nenrei]

    # ---- 7. 総人口の男女計。setjinko.c:97-100 ----
    G.sojinko_c[:, 0] = G.sojinko_c[:, 1] + G.sojinko_c[:, 2]
