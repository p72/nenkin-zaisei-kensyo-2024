# -*- coding: utf-8 -*-
"""
被保険者推計/simlroud.c の忠実移植
==================================
労働力・就業者・雇用者・自営業者の人数と総労働時間を作る。①の第1段。

やっていること（`simlroud.c` の上から）
--------------------------------------
 1. 労働力率・就業率を `ROUDYR`（2040）より後へ横引き（`simlroud.c:17-24`）
 2. 人口 × 率 で**年央**の人数を作る（26-49）。`_c` が年央、
    `_m` が年度末（`setjinko.py` の解説を参照）
      roud_j_c   労働力人口   = jinko_c × roud_r
      syugyo_j_c 就業者       = jinko_c × syugyo_r
      koyou_j_c[0] 雇用者     = syugyo_j_c × koyou_r
 3. 正規・非正規の割合を `KIJUN`（2022）より後へ横引き（51-59）
 4. 非正規短時間の割合を全体の目標に合わせて補正（67-109）
 5. 雇用者を正規・非正規フル・非正規の時間3区分に割る（111-132）
      koyou_j_c[1] 正規、[2] 非正規フル、[3..6] 非正規の時間別
 6. 自営業者 = 就業者 − 雇用者（134-141）
 7. 平均労働時間を横引きし、総労働時間 `soroudh_c[0..4]` を作る（143-174）
 8. 年央から**年度末**を作る（181-302）。`setjinko` と同じ重み付け
 9. 年度末の自営業者と総労働時間（304-345）

4 の補正（`simlroud.c:67-109`）
------------------------------
`hiseiki_tan_r_all`（全体の非正規短時間の割合）が基準年度より増えている
年度について、年齢別の割合 `seiki_hiseiki_r[3]` を一律に引き上げる。

    TMP = Σ 雇用者(男女計) × 全体の割合          目標
    TMQ = Σ 雇用者(男,女有配偶,女無配偶) × 年齢別の割合   いまの合計
    TMR = Σ（女有配偶ぶん ＋ 60歳以上の男・女無配偶ぶん）  引き上げる母数

    TMP > TMQ なら seiki_hiseiki_r[3] *= 1 + (TMP-TMQ)/TMR

`TMR` の作りから、**60歳未満は女有配偶だけを動かす**ことが読める。

原本の癖をそのまま残しているところ
----------------------------------
1. **`TMP` の足し込みが年齢でループする意味が無い**
   （`simlroud.c:72`）。`hiseiki_tan_r_all[年度]` は年齢に依らないので、
   `Σ_n 雇用者[n] × 割合` は「雇用者の合計 × 割合」と同じはずだが、
   足す順が違うので**浮動小数の結果は一致しない**。原本の順（年齢ごとに
   掛けて足す）をそのまま写す。

2. **`TMR` が 0 のときの除算を見ていない**（`simlroud.c:84`）
   `TMP > TMQ` のときだけ割るが、`TMR == 0` なら inf/nan になる。
   同梱データでは起きない。

3. **`1 + (TMP-TMQ)/TMR` の `1` が int**
   `int + double` なので `1.0` に格上げされる。結果は同じ。

4. **`sei` のループが `0..4` のところと `1..4` のところが混在**
   自営業者（134-141）は 0〜4、総労働時間（149-174）は 1〜4 で
   0 と 2 はあとから足して作る。原本のまま。

5. **`nenrei == 15` の枝が同じ年齢を2回足すが、重みが違う**
   （`simlroud.c:208-209`）。`(1.0 - jinko_wari[sei][TMS])` と
   `jinko_wari[sei][TMS]` なので合計は `roud_j_c[…][15]` そのもの。
   `setjinko` の `nenrei == 0` は重みなしで2回足していた（そちらは
   単純平均の枝）。ここだけ `TMS-1` でなく `TMS` を使っている。
"""
import sys

import numpy as np

from glva import G
from setconst import ENDY, KIJUN, STARTY

__all__ = ["simlroud"]

# 年齢の範囲（15〜105）をスライスで書くための定数
A0, A1 = 15, 106


def simlroud():
    """simlroud.c:8 の忠実移植。"""
    ROUDYR = G.ROUDYR
    SJINKOY = G.SJINKOY
    jc, jw = G.jinko_c, G.jinko_wari
    rr, sr, kr = G.roud_r, G.syugyo_r, G.koyou_r
    rjc, sjc, kjc = G.roud_j_c, G.syugyo_j_c, G.koyou_j_c
    shr = G.seiki_hiseiki_r
    hjr, htra = G.hiseiki_jikan_r, G.hiseiki_tan_r_all
    jgc = G.jieigyo_j_c
    hc, sdc = G.heikinh_c, G.soroudh_c

    # ---- 1. 労働力率・就業率の横引き。simlroud.c:17-24 ----
    for nendo in range(ROUDYR + 1, ENDY + 1):
        y = nendo - STARTY
        rr[y, 1:5, A0:A1] = rr[y - 1, 1:5, A0:A1]
        sr[y, 1:5, A0:A1] = sr[y - 1, 1:5, A0:A1]

    # ---- 2. 人口 × 率。simlroud.c:26-49 ----
    rjc[:, 1:5, A0:A1] = jc[:, 1:5, A0:A1] * rr[:, 1:5, A0:A1]
    sjc[:, 1:5, A0:A1] = jc[:, 1:5, A0:A1] * sr[:, 1:5, A0:A1]
    kjc[0, :, 1:5, A0:A1] = sjc[:, 1:5, A0:A1] * kr[:, 1:5, A0:A1]
    # 性2（女）は有配偶＋無配偶、性0（男女計）は男＋女
    rjc[:, 2, A0:A1] = rjc[:, 3, A0:A1] + rjc[:, 4, A0:A1]
    rjc[:, 0, A0:A1] = rjc[:, 1, A0:A1] + rjc[:, 2, A0:A1]
    sjc[:, 2, A0:A1] = sjc[:, 3, A0:A1] + sjc[:, 4, A0:A1]
    sjc[:, 0, A0:A1] = sjc[:, 1, A0:A1] + sjc[:, 2, A0:A1]
    kjc[0, :, 2, A0:A1] = kjc[0, :, 3, A0:A1] + kjc[0, :, 4, A0:A1]
    kjc[0, :, 0, A0:A1] = kjc[0, :, 1, A0:A1] + kjc[0, :, 2, A0:A1]

    # ---- 3. 正規・非正規の割合の横引き。simlroud.c:51-65 ----
    for nendo in range(KIJUN + 1, ENDY + 1):
        y = nendo - STARTY
        shr[1:4, y, 1:5, A0:A1] = shr[1:4, y - 1, 1:5, A0:A1]
    for nendo in range(ROUDYR + 1, ENDY + 1):
        y = nendo - STARTY
        htra[y] = htra[y - 1]
        hjr[1:5, y] = hjr[1:5, y - 1]

    # ---- 4. 非正規短時間の補正。simlroud.c:67-109 ----
    for nendo in range(KIJUN + 1, ENDY + 1):
        y = nendo - STARTY
        TMP = 0.0
        TMQ = 0.0
        TMR = 0.0
        if nendo <= ROUDYR:
            if htra[y] > htra[KIJUN - STARTY]:
                for nenrei in range(A0, A1):
                    # 癖 1.：年齢ごとに掛けて足す（合計×割合とは足す順が違う）
                    TMP += (kjc[0, y, 0, nenrei]) * (htra[y])
                    TMQ += ((kjc[0, y, 1, nenrei])
                            * (shr[3, y, 1, nenrei])
                            + (kjc[0, y, 3, nenrei])
                            * (shr[3, y, 3, nenrei])
                            + (kjc[0, y, 4, nenrei])
                            * (shr[3, y, 4, nenrei]))
                    TMR += ((kjc[0, y, 3, nenrei])
                            * (shr[3, y, 3, nenrei]))
                    if nenrei >= 60:
                        TMR += ((kjc[0, y, 1, nenrei])
                                * (shr[3, y, 1, nenrei])
                                + (kjc[0, y, 4, nenrei])
                                * (shr[3, y, 4, nenrei]))
                if TMP > TMQ:
                    # 癖 2.：TMR == 0 を見ていない
                    f = 1 + (TMP - TMQ) / TMR
                    for nenrei in range(A0, A1):
                        shr[3, y, 3, nenrei] *= f
                        if nenrei >= 60:
                            shr[3, y, 1, nenrei] *= f
                            shr[3, y, 4, nenrei] *= f
        else:
            shr[3, y, 1:5, A0:A1] = shr[3, ROUDYR - STARTY, 1:5, A0:A1]

        # simlroud.c:100-108。合計が1を超えないように切って、[2] を残りにする
        over = (shr[3, y, 1:5, A0:A1] + shr[1, y, 1:5, A0:A1]) > 1.0
        cut = 1.0 - shr[1, y, 1:5, A0:A1]
        shr[3, y, 1:5, A0:A1] = np.where(
            over, cut, shr[3, y, 1:5, A0:A1])
        shr[2, y, 1:5, A0:A1] = (1.0 - shr[3, y, 1:5, A0:A1]
                                 - shr[1, y, 1:5, A0:A1])

    # ---- 5. 雇用者を区分に割る。simlroud.c:111-132 ----
    kjc[1, :, 1:5, A0:A1] = kjc[0, :, 1:5, A0:A1] * shr[1, :, 1:5, A0:A1]
    kjc[2, :, 1:5, A0:A1] = kjc[0, :, 1:5, A0:A1] * shr[2, :, 1:5, A0:A1]
    for ii in range(3, 7):
        # hiseiki_jikan_r[ii-2][年度] は年齢に依らないので軸を足して掛ける
        kjc[ii, :, 1:5, A0:A1] = (kjc[0, :, 1:5, A0:A1]
                                  * shr[3, :, 1:5, A0:A1]
                                  * hjr[ii - 2, :][:, None, None])
    for ii in range(1, 7):
        kjc[ii, :, 2, A0:A1] = kjc[ii, :, 3, A0:A1] + kjc[ii, :, 4, A0:A1]
    for ii in range(1, 7):
        kjc[ii, :, 0, A0:A1] = kjc[ii, :, 1, A0:A1] + kjc[ii, :, 2, A0:A1]

    # ---- 6. 自営業者。simlroud.c:134-141 ----
    jgc[:, 0:5, A0:A1] = sjc[:, 0:5, A0:A1] - kjc[0, :, 0:5, A0:A1]

    # ---- 7. 平均労働時間の横引きと総労働時間。simlroud.c:143-174 ----
    for nendo in range(ROUDYR + 1, ENDY + 1):
        y = nendo - STARTY
        hc[1:10, y] = hc[1:10, y - 1]

    # heikinh_c[区分][年度] は年齢に依らない。年度ループで素直に書く
    for nendo in range(STARTY, ENDY + 1):
        y = nendo - STARTY
        sdc[1, y, 1:5, A0:A1] = kjc[1, y, 1:5, A0:A1] * hc[1, y]
        sdc[2, y, 1:5, A0:A1] = kjc[2, y, 1:5, A0:A1] * hc[2, y]
        sdc[3, y, 1:5, A0:A1] = (kjc[3, y, 1:5, A0:A1] * hc[3, y]
                                 + kjc[4, y, 1:5, A0:A1] * hc[4, y]
                                 + kjc[5, y, 1:5, A0:A1] * hc[5, y]
                                 + kjc[6, y, 1:5, A0:A1] * hc[6, y])
        sdc[4, y, 1:5, A0:A1] = jgc[y, 1:5, A0:A1] * hc[7, y]
        sdc[0, y, 1:5, A0:A1] = (sdc[1, y, 1:5, A0:A1]
                                 + sdc[2, y, 1:5, A0:A1]
                                 + sdc[3, y, 1:5, A0:A1]
                                 + sdc[4, y, 1:5, A0:A1])
        for ii in range(0, 5):
            sdc[ii, y, 2, A0:A1] = sdc[ii, y, 3, A0:A1] + sdc[ii, y, 4, A0:A1]
            sdc[ii, y, 0, A0:A1] = sdc[ii, y, 1, A0:A1] + sdc[ii, y, 2, A0:A1]

    # ---- simlroud.c:176-179 ----
    if STARTY != SJINKOY:
        print("推計初年度 (STARTY) が人口のスタート年度 (JINKOY) と"
              "一致していません", file=sys.stderr)
        raise SystemExit(2)

    # ---- 8. 年度末を作る。simlroud.c:181-302 ----
    rjm, sjm, kjm = G.roud_j_m, G.syugyo_j_m, G.koyou_j_m
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            for sei in (1, 2, 3):
                if nenrei + SJINKOY - nendo > 0:
                    TMS = nenrei + SJINKOY - nendo
                    w0 = 1.0 - jw[sei, TMS - 1]
                    w1 = jw[sei, TMS]
                    if 15 < nenrei < 105:
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei - 1] * w0
                            + rjc[y, sei, nenrei] * w1
                            + rjc[y + 1, sei, nenrei] * w0
                            + rjc[y + 1, sei, nenrei + 1] * w1) / 2.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei - 1] * w0
                            + sjc[y, sei, nenrei] * w1
                            + sjc[y + 1, sei, nenrei] * w0
                            + sjc[y + 1, sei, nenrei + 1] * w1) / 2.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei - 1] * w0
                                + kjc[ii, y, sei, nenrei] * w1
                                + kjc[ii, y + 1, sei, nenrei] * w0
                                + kjc[ii, y + 1, sei, nenrei + 1] * w1) / 2.0
                    elif nenrei == 15:
                        # 癖 5.：ここだけ 1つ目の重みが (1 - jw[TMS])
                        v0 = 1.0 - jw[sei, TMS]
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei] * v0
                            + rjc[y, sei, nenrei] * w1
                            + rjc[y + 1, sei, nenrei] * w0
                            + rjc[y + 1, sei, nenrei + 1] * w1) / 2.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei] * v0
                            + sjc[y, sei, nenrei] * w1
                            + sjc[y + 1, sei, nenrei] * w0
                            + sjc[y + 1, sei, nenrei + 1] * w1) / 2.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei] * v0
                                + kjc[ii, y, sei, nenrei] * w1
                                + kjc[ii, y + 1, sei, nenrei] * w0
                                + kjc[ii, y + 1, sei, nenrei + 1] * w1) / 2.0
                    elif nenrei == 105:
                        w2 = jw[sei, TMS - 1]
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei - 1] * w0
                            + rjc[y, sei, nenrei] * w1
                            + rjc[y + 1, sei, nenrei] * w0
                            + rjc[y + 1, sei, nenrei] * w2) / 2.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei - 1] * w0
                            + sjc[y, sei, nenrei] * w1
                            + sjc[y + 1, sei, nenrei] * w0
                            + sjc[y + 1, sei, nenrei] * w2) / 2.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei - 1] * w0
                                + kjc[ii, y, sei, nenrei] * w1
                                + kjc[ii, y + 1, sei, nenrei] * w0
                                + kjc[ii, y + 1, sei, nenrei] * w2) / 2.0
                else:
                    if 15 < nenrei < 105:
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei - 1] + rjc[y, sei, nenrei]
                            + rjc[y + 1, sei, nenrei]
                            + rjc[y + 1, sei, nenrei + 1]) / 4.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei - 1] + sjc[y, sei, nenrei]
                            + sjc[y + 1, sei, nenrei]
                            + sjc[y + 1, sei, nenrei + 1]) / 4.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei - 1]
                                + kjc[ii, y, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei + 1]) / 4.0
                    elif nenrei == 15:
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei] + rjc[y, sei, nenrei]
                            + rjc[y + 1, sei, nenrei]
                            + rjc[y + 1, sei, nenrei + 1]) / 4.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei] + sjc[y, sei, nenrei]
                            + sjc[y + 1, sei, nenrei]
                            + sjc[y + 1, sei, nenrei + 1]) / 4.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei]
                                + kjc[ii, y, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei + 1]) / 4.0
                    elif nenrei == 105:
                        rjm[y, sei, nenrei] = (
                            rjc[y, sei, nenrei - 1] + rjc[y, sei, nenrei]
                            + rjc[y + 1, sei, nenrei]
                            + rjc[y + 1, sei, nenrei]) / 4.0
                        sjm[y, sei, nenrei] = (
                            sjc[y, sei, nenrei - 1] + sjc[y, sei, nenrei]
                            + sjc[y + 1, sei, nenrei]
                            + sjc[y + 1, sei, nenrei]) / 4.0
                        for ii in range(0, 7):
                            kjm[ii, y, sei, nenrei] = (
                                kjc[ii, y, sei, nenrei - 1]
                                + kjc[ii, y, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei]
                                + kjc[ii, y + 1, sei, nenrei]) / 4.0
            # simlroud.c:287-300
            rjm[y, 4, nenrei] = rjm[y, 2, nenrei] - rjm[y, 3, nenrei]
            rjm[y, 0, nenrei] = rjm[y, 1, nenrei] + rjm[y, 2, nenrei]
            sjm[y, 4, nenrei] = sjm[y, 2, nenrei] - sjm[y, 3, nenrei]
            sjm[y, 0, nenrei] = sjm[y, 1, nenrei] + sjm[y, 2, nenrei]
            for ii in range(0, 7):
                kjm[ii, y, 4, nenrei] = (kjm[ii, y, 2, nenrei]
                                         - kjm[ii, y, 3, nenrei])
                kjm[ii, y, 0, nenrei] = (kjm[ii, y, 1, nenrei]
                                         + kjm[ii, y, 2, nenrei])

    # ---- 9. 年度末の自営業者と総労働時間。simlroud.c:304-345 ----
    jgm, sdm, hm = G.jieigyo_j_m, G.soroudh_m, G.heikinh_m
    n = ENDY - STARTY            # STARTY..ENDY-1
    jgm[0:n, 0:5, A0:A1] = sjm[0:n, 0:5, A0:A1] - kjm[0, 0:n, 0:5, A0:A1]
    hm[1:10, 0:n] = (hc[1:10, 0:n] + hc[1:10, 1:n + 1]) / 2.0
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        sdm[1, y, 1:5, A0:A1] = kjm[1, y, 1:5, A0:A1] * hm[1, y]
        sdm[2, y, 1:5, A0:A1] = kjm[2, y, 1:5, A0:A1] * hm[2, y]
        sdm[3, y, 1:5, A0:A1] = (kjm[3, y, 1:5, A0:A1] * hm[3, y]
                                 + kjm[4, y, 1:5, A0:A1] * hm[4, y]
                                 + kjm[5, y, 1:5, A0:A1] * hm[5, y]
                                 + kjm[6, y, 1:5, A0:A1] * hm[6, y])
        sdm[4, y, 1:5, A0:A1] = jgm[y, 1:5, A0:A1] * hm[7, y]
        sdm[0, y, 1:5, A0:A1] = (sdm[1, y, 1:5, A0:A1]
                                 + sdm[2, y, 1:5, A0:A1]
                                 + sdm[3, y, 1:5, A0:A1]
                                 + sdm[4, y, 1:5, A0:A1])
        for ii in range(0, 5):
            sdm[ii, y, 2, A0:A1] = sdm[ii, y, 3, A0:A1] + sdm[ii, y, 4, A0:A1]
            sdm[ii, y, 0, A0:A1] = sdm[ii, y, 1, A0:A1] + sdm[ii, y, 2, A0:A1]
