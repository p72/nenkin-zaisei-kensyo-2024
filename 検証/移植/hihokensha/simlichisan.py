# -*- coding: utf-8 -*-
"""
被保険者推計/simlichisan.c の忠実移植
=====================================
1号（`ichigou`）・3号（`sangou`）・未加入外（`mika_soto`）を作る。①の第4段。

`ichigou` / `sangou` の添字（読み解いた範囲）
--------------------------------------------
    ichigou[0]  1号の計       = [1] + [2]
    ichigou[1]  1号（一般）
    ichigou[2]  1号（任意）
    sangou[0]   3号の計       = [1] + [4] + [5] + [6]
    sangou[1]   旧厚の3号     （[2] + [3] に割れる）
    sangou[2]   旧厚3号のうち旧厚12種
    sangou[3]   旧厚3号のうち旧厚3種
    sangou[4..6] 国共済・地共済・私学共済の3号

やっていること（`simlichisan.c` の上から）
-----------------------------------------
1. 実績年度（`STARTY`〜`KIJUNMAP`）の1号・3号を性別に割り、
   未加入外 `mika_soto` を残差で出す（`simlichisan.c:29-58`）

       mika_soto = 人口(央) − 1号計 − 2号 − 3号計 − パート

2. 1号（任意）の率 `r_ichigouni` を基準年度から取り、以降に当てる
   （60-97）。59歳以下は人口に対する率、60歳以上は
   「人口 − 2号 − パート」に対する率

3. 未加入外の率を年齢で1つずつ送りながら 2040年度に向けて 0 に寄せる
   （99-134）

       keisu = (2040 - 年度) / (2040 - 年度 + 1)      2040年度以降は 0
       率[年度][年齢] = 率[年度-1][年齢-1] × keisu

4. 3号（旧厚・共済）を基準年度からの比で延ばす（136-165）
5. 3号の男女・有配偶の割り振り（167-226）。45年化のときは
   45〜59歳に補正を掛ける（206-220）
6. 1号（一般）を残差で出す（228-254）

       1号一般 = 人口(央) − 未加入外 − 2号 − パート − 3号計 − 1号任意

   **負になったら 0 にして `stderr` に出す**（235-238）
7. 未加入外を 19歳以下と `XEND` 以上で 0 にし、基準年度の3号も
   `XEND` 以上を 0 にする（256-275）

原本の癖をそのまま残しているところ
----------------------------------
1. **局所配列の 0 埋めが 101〜120 歳を素通りする**
   （`simlichisan.c:20`）。`r_mika_soto[131][5][121]` に対して
   `nenrei` のループが 0〜100 なので、101〜120 は**未初期化のまま**。
   読むのは 15〜100 と 20〜64 だけなので害は無い。

2. **`keisu` の `2040` が直値**（`simlichisan.c:106-110`）
   `ROUDYR` と同じ値だが定数を使っていない。

3. **`nenrei <= 20 + 1` という書き方**（`simlichisan.c:102`）
   `<= 21` と同じ。ループが 20 から始まるので 20 と 21 が該当する。

4. **ゼロ除算を見ていない割り算が多い**
   - `simlichisan.c:55` `mika_soto / jinko_m`
   - `64, 69-70` `ichigou[2] / (人口 …)`
   - `89-91` `jinko_m[3] / jinko_m[2]` を2回
   - `121-123` `mika_soto[KIJUNMAP][4] / [2]` ほか
   - `187, 192, 202` `sangou[0] / (nigou + partnin)`
   - `483-492`（`simlpart.c`）も同様
   同梱データでは 0 にならない。

5. **`MODE45 == 1` の補正が `sei` 1〜3 にしか掛からない**
   （`simlichisan.c:207`）。性4（女無配偶）は掛からないが、
   直後の `sangou[seido][0]` は `[1] + [2]` で作るので、
   `[2]`（= `[3]`）が補正済みなら合計にも反映される。
"""
import sys

import numpy as np

from glva import G
from setconst import ENDY, KIJUNMAP, NAGE, NSEI, NY, STARTY

__all__ = ["simlichisan"]


def simlichisan():
    """simlichisan.c:8 の忠実移植。"""
    MODE45 = G.MODE45
    jm = G.jinko_m
    ichigou, sangou, nigou = G.ichigou, G.sangou, G.nigou
    kounen, partnin = G.kounen, G.partnin
    mika = G.mika_soto
    iyr = G.ichiyuhaigr
    xend = G.xend
    k0 = KIJUNMAP - STARTY

    # 局所配列（原本は関数の自動変数）。癖 1. のとおり原本は 101〜120 を
    # 0 で埋めないが、そこは読まれないので 0 で作ってよい
    r_ichigouni = np.zeros((NSEI, NAGE), dtype=np.float64)
    r_mika_soto = np.zeros((NY, NSEI, NAGE), dtype=np.float64)

    # ---- 1. 実績年度。simlichisan.c:29-58 ----
    for nendo in range(STARTY, KIJUNMAP + 1):
        y = nendo - STARTY
        for nenrei in range(15, 101):
            for ii in (1, 2):
                ichigou[ii, y, 3, nenrei] = ((ichigou[ii, y, 2, nenrei])
                                             * (iyr[nenrei]))
                ichigou[ii, y, 4, nenrei] = ((ichigou[ii, y, 2, nenrei])
                                             * (1.0 - (iyr[nenrei])))
            for sei in range(0, 5):
                ichigou[0, y, sei, nenrei] = (
                    (ichigou[1, y, sei, nenrei])
                    + (ichigou[2, y, sei, nenrei]))
            for ii in range(0, 7):
                sangou[ii, y, 3, nenrei] = (sangou[ii, y, 2, nenrei])
                sangou[ii, y, 4, nenrei] = 0.0
            for sei in range(0, 5):
                sangou[0, y, sei, nenrei] = (sangou[1, y, sei, nenrei])
                for seido in range(4, 7):
                    sangou[0, y, sei, nenrei] += (
                        sangou[seido, y, sei, nenrei])
            for sei in range(0, 5):
                mika[y, sei, nenrei] = (
                    (jm[y, sei, nenrei])
                    - (ichigou[0, y, sei, nenrei])
                    - (nigou[y, sei, nenrei])
                    - (sangou[0, y, sei, nenrei])
                    - (partnin[y, sei, nenrei, 0, 0, 0]))
                # 癖 4.：分母のゼロを見ていない
                r_mika_soto[y, sei, nenrei] = ((mika[y, sei, nenrei])
                                               / (jm[y, sei, nenrei]))

    # ---- 2. 1号（任意）。simlichisan.c:60-97 ----
    for sei in (1, 2):
        for nenrei in range(20, 70):
            if nenrei <= 59:
                r_ichigouni[sei, nenrei] = ((ichigou[2, k0, sei, nenrei])
                                            / (jm[k0, sei, nenrei]))
            else:
                r_ichigouni[sei, nenrei] = (
                    (ichigou[2, k0, sei, nenrei])
                    / ((jm[k0, sei, nenrei])
                       - (nigou[k0, sei, nenrei])
                       - (partnin[k0, sei, nenrei, 0, 0, 0])))
    for nendo in range(KIJUNMAP + 1, ENDY):
        y = nendo - STARTY
        for nenrei in range(20, 70):
            for sei in (1, 2):
                if nenrei <= 59:
                    ichigou[2, y, sei, nenrei] = (
                        (jm[y, sei, nenrei])
                        * (r_ichigouni[sei, nenrei]))
                else:
                    ichigou[2, y, sei, nenrei] = (
                        ((jm[y, sei, nenrei])
                         - (nigou[y, sei, nenrei])
                         - (partnin[y, sei, nenrei, 0, 0, 0]))
                        * (r_ichigouni[sei, nenrei]))
            ichigou[2, y, 3, nenrei] = (
                (ichigou[2, y, 2, nenrei]) * (iyr[nenrei])
                * ((jm[y, 3, nenrei]) / (jm[y, 2, nenrei]))
                / ((jm[k0, 3, nenrei]) / (jm[k0, 2, nenrei])))
            ichigou[2, y, 4, nenrei] = ((ichigou[2, y, 2, nenrei])
                                        - (ichigou[2, y, 3, nenrei]))
            ichigou[2, y, 0, nenrei] = ((ichigou[2, y, 1, nenrei])
                                        + (ichigou[2, y, 2, nenrei]))

    # ---- 3. 未加入外。simlichisan.c:99-134 ----
    for nendo in range(KIJUNMAP + 1, ENDY + 1):
        y = nendo - STARTY
        d = nendo - KIJUNMAP            # 基準年度からの経過
        for nenrei in range(20, 65):
            for sei in (1, 2):
                if nenrei <= 20 + 1:    # 癖 3.
                    r_mika_soto[y, sei, nenrei] = 0.0
                else:
                    if nendo >= 2040:   # 癖 2.：直値の 2040
                        keisu = 0.0
                    else:
                        keisu = (2040 - nendo) / (2040 - nendo + 1)
                    r_mika_soto[y, sei, nenrei] = (
                        (r_mika_soto[y - 1, sei, nenrei - 1]) * keisu)
                mika[y, sei, nenrei] = ((jm[y, sei, nenrei])
                                        * (r_mika_soto[y, sei, nenrei]))
            if nenrei - d > 20:
                b = nenrei - d          # 基準年度で対応する年齢
                mika[y, 4, nenrei] = (
                    (mika[y, 2, nenrei])
                    * ((mika[k0, 4, b]) / (mika[k0, 2, b]))
                    * ((jm[y, 4, nenrei]) / (jm[y, 2, nenrei]))
                    / ((jm[k0, 4, b]) / (jm[k0, 2, b])))
            else:
                mika[y, 4, nenrei] = (
                    (mika[y, 2, nenrei])
                    * ((jm[y, 4, nenrei]) / (jm[y, 2, nenrei])))
            mika[y, 3, nenrei] = ((mika[y, 2, nenrei])
                                  - (mika[y, 4, nenrei]))
            mika[y, 0, nenrei] = ((mika[y, 1, nenrei])
                                  + (mika[y, 2, nenrei]))

    # ---- 4. 3号（男・性1）。simlichisan.c:136-165 ----
    for nendo in range(KIJUNMAP + 1, ENDY + 1):
        y = nendo - STARTY
        XEND = int(xend[y])
        for nenrei in range(20, XEND):
            den = ((kounen[1, k0, 3, nenrei])
                   + (partnin[k0, 3, nenrei, 0, 0, 0]))
            if den > 0.0:
                sangou[1, y, 1, nenrei] = (
                    (sangou[1, k0, 1, nenrei])
                    * ((kounen[1, y, 3, nenrei])
                       + (partnin[y, 3, nenrei, 0, 0, 0])) / den)
            else:
                sangou[1, y, 1, nenrei] = 0.0
            sangou[3, y, 1, nenrei] = 0.0
            sangou[2, y, 1, nenrei] = (sangou[1, y, 1, nenrei])
            for seido in range(4, 7):
                if (kounen[seido, k0, 3, nenrei]) > 0.0:
                    sangou[seido, y, 1, nenrei] = (
                        (sangou[seido, k0, 1, nenrei])
                        * (kounen[seido, y, 3, nenrei])
                        / (kounen[seido, k0, 3, nenrei]))
                else:
                    sangou[seido, y, 1, nenrei] = 0.0
            sangou[0, y, 1, nenrei] = (sangou[1, y, 1, nenrei])
            for seido in range(4, 7):
                sangou[0, y, 1, nenrei] += (
                    sangou[seido, y, 1, nenrei])

    # ---- 5. 3号の女・有配偶。simlichisan.c:167-226 ----
    for nendo in range(KIJUNMAP + 1, ENDY + 1):
        y = nendo - STARTY
        XEND = int(xend[y])
        for nenrei in range(20, XEND):
            TMP = ((jm[k0, 3, nenrei]) - (nigou[k0, 3, nenrei])
                   - (partnin[k0, 3, nenrei, 0, 0, 0]))
            TMQ = ((jm[y, 3, nenrei]) - (nigou[y, 3, nenrei])
                   - (partnin[y, 3, nenrei, 0, 0, 0]))
            if TMP > 0.0 and TMQ > 0.0:
                sangou[0, y, 3, nenrei] = (
                    (sangou[0, k0, 3, nenrei]) * TMQ / TMP
                    * (((nigou[y, 1, nenrei])
                        + (partnin[y, 1, nenrei, 0, 0, 0]))
                       / (jm[y, 1, nenrei]))
                    / (((nigou[k0, 1, nenrei])
                        + (partnin[k0, 1, nenrei, 0, 0, 0]))
                       / (jm[k0, 1, nenrei])))
            else:
                sangou[0, y, 3, nenrei] = 0.0
            sangou[0, y, 4, nenrei] = 0.0
            sangou[0, y, 2, nenrei] = (sangou[0, y, 3, nenrei])

            # 分母は「2号＋パート（男）」。癖 4.
            den1 = ((nigou[y, 1, nenrei])
                    + (partnin[y, 1, nenrei, 0, 0, 0]))
            sangou[1, y, 3, nenrei] = (
                (sangou[0, y, 3, nenrei])
                * ((kounen[1, y, 1, nenrei])
                   + (partnin[y, 1, nenrei, 0, 0, 0])) / den1)
            sangou[1, y, 4, nenrei] = 0.0
            sangou[1, y, 2, nenrei] = (sangou[1, y, 3, nenrei])
            sangou[3, y, 3, nenrei] = ((sangou[0, y, 3, nenrei])
                                       * (kounen[3, y, 1, nenrei])
                                       / den1)
            sangou[3, y, 4, nenrei] = 0.0
            sangou[3, y, 2, nenrei] = (sangou[3, y, 3, nenrei])
            for sei in range(2, 5):
                sangou[2, y, sei, nenrei] = (
                    (sangou[1, y, sei, nenrei])
                    - (sangou[3, y, sei, nenrei]))
            for seido in range(4, 7):
                sangou[seido, y, 3, nenrei] = (
                    (sangou[0, y, 3, nenrei])
                    * (kounen[seido, y, 1, nenrei]) / den1)
                sangou[seido, y, 4, nenrei] = 0.0
                sangou[seido, y, 2, nenrei] = (
                    sangou[seido, y, 3, nenrei])
            if MODE45 == 1:
                # 癖 5.：sei 1〜3 だけ
                for sei in range(1, 4):
                    for seido in range(0, 7):
                        if 45 <= nenrei <= 49:
                            sangou[seido, y, sei, nenrei] *= (
                                1.0 + (XEND - 60) / 5.0 * 0.003)
                        elif 50 <= nenrei <= 54:
                            sangou[seido, y, sei, nenrei] *= (
                                1.0 + (XEND - 60) / 5.0 * 0.011)
                        elif 55 <= nenrei <= 59:
                            sangou[seido, y, sei, nenrei] *= (
                                1.0 + (XEND - 60) / 5.0 * 0.063)
            for seido in range(0, 7):
                sangou[seido, y, 0, nenrei] = (
                    (sangou[seido, y, 1, nenrei])
                    + (sangou[seido, y, 2, nenrei]))

    # ---- 6. 1号（一般）。simlichisan.c:228-254 ----
    for nendo in range(KIJUNMAP + 1, ENDY):
        y = nendo - STARTY
        XEND = int(xend[y])
        for nenrei in range(20, XEND):
            for sei in range(1, 5):
                TMP = ((jm[y, sei, nenrei])
                       - (mika[y, sei, nenrei])
                       - (nigou[y, sei, nenrei])
                       - (partnin[y, sei, nenrei, 0, 0, 0])
                       - (sangou[0, y, sei, nenrei])
                       - (ichigou[2, y, sei, nenrei]))
                if TMP < 0.0:
                    print(f"{nendo}年度 性{sei} 年齢{nenrei}の１号一般が"
                          "マイナス!", file=sys.stderr)
                    ichigou[1, y, sei, nenrei] = 0.0
                else:
                    ichigou[1, y, sei, nenrei] = TMP
            ichigou[1, y, 2, nenrei] = ((ichigou[1, y, 3, nenrei])
                                        + (ichigou[1, y, 4, nenrei]))
            ichigou[1, y, 0, nenrei] = ((ichigou[1, y, 1, nenrei])
                                        + (ichigou[1, y, 2, nenrei]))
        for sei in range(0, 5):
            for nenrei in range(20, 70):
                ichigou[0, y, sei, nenrei] = (
                    (ichigou[1, y, sei, nenrei])
                    + (ichigou[2, y, sei, nenrei]))

    # ---- 7. 端の年齢を 0 にする。simlichisan.c:256-275 ----
    for nendo in range(STARTY, ENDY + 1):
        y = nendo - STARTY
        XEND = int(xend[y])
        mika[y, 0:5, 0:20] = 0.0
        mika[y, 0:5, XEND:101] = 0.0
    XEND = int(xend[k0])
    sangou[0:7, k0, 0:5, XEND:101] = 0.0
