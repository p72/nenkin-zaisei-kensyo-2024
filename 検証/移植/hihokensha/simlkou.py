# -*- coding: utf-8 -*-
"""
被保険者推計/simlkou.c の忠実移植
=================================
厚生年金の2号被保険者数（`kounen[1..3]`）と、それを反映した雇用者数
（`koyou_j_*[7..10]`）・総労働時間（`soroudh_*[6..9]`）を作る。①の第3段。

やっていること（`simlkou.c` の上から）
-------------------------------------
 1. 厚年適用率 `kounenteki_c` を `ROUDYR` より後へ横引きし、年度末を作る
    （`simlkou.c:29-39`）
 2. パート（`partnin[..][0][0][0]`）を `KIJUNMAP` より後へ、雇用者の
    短時間区分（`koyou_j_m[4]+[5]`）の伸びで延ばす（41-50）
 3. パートを女有配偶・無配偶に割る（51-69）
 4. **補正率 `kounen_cho` を作る**（71-107）
      実績年度（`nendo <= KIJUNMAP`）は
        （厚年＋パート＋共済3つ）/ Σ 雇用者×適用率
      それ以降は前年度から引き継ぐ。70歳以上は前年度の1つ下の年齢と
      比べて小さい方を取る（単調性の担保と読める）
 5. `kounen[1]`（厚年の2号）を作る（109-127）
      Σ 雇用者×適用率 × 補正率 − パート − 共済3つ
 6. 70歳以上に 0.98 の上限を掛け、補正率を作り直す（128-150）
 7. 厚年の被用者を正規・非正規に割る（152-179）
      koyou_j_m[8] 正規、[9] 非正規フル、[10] 非正規短時間、[7] 合計
 8. 旧厚3種（`kounen[3]`）の割合を作り、`kounen[2]`/`[3]` に割る（181-224）
 9. 年度末の総労働時間（226-249）と年度末→年央（251-282）
10. `kounen[0]` と `nigou`（2号の合計）を作る（284-303）

原本の癖をそのまま残しているところ
----------------------------------
1. **局所配列の外に書き込む**（`simlkou.c:21`）

   ```c
   double partyuhaigr_m[ENDY-STARTY+1][121] ;   /* [131][121] */
   ...
   partyuhaigr_m[nendo-STARTY+1][nenrei] = 0.0 ;   /* nendo = ENDY で [131] */
   ```

   添字が `nendo-STARTY+1` なので 1〜131 を回り、**131 は配列の外**。
   0 は 0 で埋められないが、使う前に必ず代入される（57/60行）ので
   害は無い。外への書き込みはスタックを壊す未定義動作。
   移植版は 0〜130 の範囲に収め、**131 への書き込みは捨てる**。
   （`検証/原本の不具合.md`）

2. **ゼロ除算を見ていない割り算がいくつもある**
   - `simlkou.c:47` パートを延ばすとき（分母は `KIJUNMAP` の
     `koyou_j_m[4]+[5]`）
   - `simlkou.c:138-145` 補正率を作り直すとき
   - `simlkou.c:248, 281` 平均労働時間 `TMQ / TMP`
   同梱データでは 0 にならない。

3. **`kounen_cho[3]` と `[4]` に女（性2）の値をそのまま入れる**
   （`simlkou.c:104-105`）。有配偶・無配偶で補正率を分けていない。

4. **`rk_sen` の実績平均が「足してから割る」**（`simlkou.c:194-197`）

   ```c
   for ( ii = STARTY ; ii <= KIJUNMAP ; ii++ )
     rk_sen[nendo-STARTY][1][nenrei] += rk_sen[ii-STARTY][1][nenrei] ;
   rk_sen[nendo-STARTY][1][nenrei] /= KIJUNMAP - STARTY + 1 ;
   ```

   `rk_sen[nendo-STARTY]` は（`KIJUNMAP` より後なので）0 から始まり、
   実績4年度ぶん（2020〜2023）を足して 4 で割る。`ii` の範囲が実績年度に
   固定なので、**どの年度でも同じ4年平均**になる。

5. **`heikinh_m[10]` / `heikinh_c[10]` の分母が「69歳以下の合計」**
   （`simlkou.c:242-243, 275-276`）。`sei == 0` かつ `nenrei <= 69` の
   ときだけ足す。`sei` のループの中に `if (sei==0)` を置いているので、
   `sei` 1〜4 の周回は何もしない。
"""
import numpy as np

from glva import G
from setconst import ENDY, KIJUNMAP, NAGE, NSEI, NY, STARTY

__all__ = ["simlkou"]

A0, A1 = 15, 101          # 年齢 15〜100


def simlkou():
    """simlkou.c:8 の忠実移植。"""
    ROUDYR = G.ROUDYR
    kounen = G.kounen
    partnin = G.partnin
    kjm, kjc = G.koyou_j_m, G.koyou_j_c
    ktc, ktm = G.kounenteki_c, G.kounenteki_m
    sdm, sdc = G.soroudh_m, G.soroudh_c
    hm, hc = G.heikinh_m, G.heikinh_c
    nigou = G.nigou

    # 局所配列（原本は関数の自動変数）
    kounen_cho = np.zeros((NY, NSEI, NAGE), dtype=np.float64)
    rk_sen = np.zeros((NY, NSEI, NAGE), dtype=np.float64)
    partyuhaigr_m = np.zeros((NY, NAGE), dtype=np.float64)
    # simlkou.c:19-27 の 0 埋め。原本は [131] にも書く（癖 1.）ので、
    # 移植版は範囲内だけにする（結果は同じ）

    # ---- 1. 厚年適用率。simlkou.c:29-39 ----
    for nendo in range(ROUDYR + 1, ENDY + 1):
        y = nendo - STARTY
        ktc[1:7, y] = ktc[1:7, y - 1]
    n = ENDY - STARTY
    ktm[1:7, 0:n] = (ktc[1:7, 0:n] + ktc[1:7, 1:n + 1]) / 2.0

    # ---- 2. パートを延ばす。simlkou.c:41-50 ----
    k0 = KIJUNMAP - STARTY
    for nendo in range(KIJUNMAP + 1, ENDY):
        y = nendo - STARTY
        for sei in (1, 2):
            for nenrei in range(A0, A1):
                partnin[y, sei, nenrei, 0, 0, 0] = (
                    (partnin[k0, sei, nenrei, 0, 0, 0])
                    * ((kjm[4, y, sei, nenrei])
                       + (kjm[5, y, sei, nenrei]))
                    / ((kjm[4, k0, sei, nenrei])
                       + (kjm[5, k0, sei, nenrei])))

    # ---- 3. パートを女有配偶・無配偶に割る。simlkou.c:51-69 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            TMP = (kjm[4, y, 3, nenrei]) + (kjm[5, y, 3, nenrei])
            TMQ = (kjm[4, y, 4, nenrei]) + (kjm[5, y, 4, nenrei])
            if TMP + TMQ > 0.0:
                partyuhaigr_m[y, nenrei] = TMP / (TMP + TMQ)
            else:
                partyuhaigr_m[y, nenrei] = 0.0
            p2 = (partnin[y, 2, nenrei, 0, 0, 0])
            partnin[y, 3, nenrei, 0, 0, 0] = p2 * partyuhaigr_m[y, nenrei]
            partnin[y, 4, nenrei, 0, 0, 0] = (
                p2 * (1.0 - partyuhaigr_m[y, nenrei]))
            partnin[y, 0, nenrei, 0, 0, 0] = (
                (partnin[y, 1, nenrei, 0, 0, 0]) + p2)

    # ---- 4. 補正率 kounen_cho。simlkou.c:71-107 ----
    for nendo in range(STARTY, ENDY + 1):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            for sei in (1, 2):
                if nendo <= KIJUNMAP:
                    TMP = 0.0
                    for ii in range(1, 7):
                        TMP += ((kjm[ii, y, sei, nenrei])
                                * (ktm[ii, y]))
                    if TMP > 0.0:
                        kounen_cho[y, sei, nenrei] = (
                            ((kounen[1, y, sei, nenrei])
                             + (partnin[y, sei, nenrei, 0, 0, 0])
                             + (kounen[4, y, sei, nenrei])
                             + (kounen[5, y, sei, nenrei])
                             + (kounen[6, y, sei, nenrei])) / TMP)
                    else:
                        kounen_cho[y, sei, nenrei] = 0.0
                else:
                    if nenrei <= 69:
                        kounen_cho[y, sei, nenrei] = \
                            kounen_cho[y - 1, sei, nenrei]
                    else:
                        if (kounen_cho[y - 1, sei, nenrei]
                                < kounen_cho[y - 1, sei, nenrei - 1]):
                            kounen_cho[y, sei, nenrei] = \
                                kounen_cho[y - 1, sei, nenrei]
                        else:
                            kounen_cho[y, sei, nenrei] = \
                                kounen_cho[y - 1, sei, nenrei - 1]
            # 癖 3.：性3・性4 は性2 と同じ
            kounen_cho[y, 3, nenrei] = kounen_cho[y, 2, nenrei]
            kounen_cho[y, 4, nenrei] = kounen_cho[y, 2, nenrei]

    # ---- 5. kounen[1]。simlkou.c:109-127 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            for sei in range(1, 5):
                kounen[1, y, sei, nenrei] = (
                    ((kjm[1, y, sei, nenrei]) * (ktm[1, y])
                     + (kjm[2, y, sei, nenrei]) * (ktm[2, y])
                     + (kjm[3, y, sei, nenrei]) * (ktm[3, y])
                     + (kjm[4, y, sei, nenrei]) * (ktm[4, y])
                     + (kjm[5, y, sei, nenrei]) * (ktm[5, y])
                     + (kjm[6, y, sei, nenrei]) * (ktm[6, y]))
                    * (kounen_cho[y, sei, nenrei])
                    - (partnin[y, sei, nenrei, 0, 0, 0])
                    - (kounen[4, y, sei, nenrei])
                    - (kounen[5, y, sei, nenrei])
                    - (kounen[6, y, sei, nenrei]))
            kounen[1, y, 0, nenrei] = ((kounen[1, y, 1, nenrei])
                                       + (kounen[1, y, 2, nenrei]))

    # ---- 6. 70歳以上の上限と補正率の作り直し。simlkou.c:128-150 ----
    for nendo in range(KIJUNMAP + 1, ENDY):
        y = nendo - STARTY
        for nenrei in range(70, A1):
            for sei in range(1, 5):
                cap = (kounen[1, y - 1, sei, nenrei - 1]) * 0.98
                if (kounen[1, y, sei, nenrei]) > cap:
                    kounen[1, y, sei, nenrei] = cap
            kounen[1, y, 2, nenrei] = ((kounen[1, y, 3, nenrei])
                                       + (kounen[1, y, 4, nenrei]))
            for sei in range(1, 5):
                # 癖 2.：分母のゼロを見ていない
                kounen_cho[y, sei, nenrei] = (
                    (kounen[1, y, sei, nenrei])
                    / ((kjm[1, y, sei, nenrei]) * (ktm[1, y])
                       + (kjm[2, y, sei, nenrei]) * (ktm[2, y])
                       + (kjm[3, y, sei, nenrei]) * (ktm[3, y])
                       + (kjm[4, y, sei, nenrei]) * (ktm[4, y])
                       + (kjm[5, y, sei, nenrei]) * (ktm[5, y])
                       + (kjm[6, y, sei, nenrei]) * (ktm[6, y])))
            kounen[1, y, 0, nenrei] = ((kounen[1, y, 1, nenrei])
                                       + (kounen[1, y, 2, nenrei]))

    # ---- 7. 厚年の被用者を区分に割る。simlkou.c:152-179 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(A0, 70):
            for sei in range(1, 5):
                cho = (kounen_cho[y, sei, nenrei])
                kjm[8, y, sei, nenrei] = ((kjm[1, y, sei, nenrei])
                                          * (ktm[1, y]) * cho)
                kjm[9, y, sei, nenrei] = ((kjm[2, y, sei, nenrei])
                                          * (ktm[2, y]) * cho)
                kjm[10, y, sei, nenrei] = (
                    ((kjm[3, y, sei, nenrei]) * (ktm[3, y])
                     + (kjm[4, y, sei, nenrei]) * (ktm[4, y])
                     + (kjm[5, y, sei, nenrei]) * (ktm[5, y])
                     + (kjm[6, y, sei, nenrei]) * (ktm[6, y]))
                    * cho)
                kjm[7, y, sei, nenrei] = ((kjm[8, y, sei, nenrei])
                                          + (kjm[9, y, sei, nenrei])
                                          + (kjm[10, y, sei, nenrei]))
            for ii in range(7, 11):
                kjm[ii, y, 0, nenrei] = ((kjm[ii, y, 1, nenrei])
                                         + (kjm[ii, y, 2, nenrei]))

    # ---- 8. 旧厚3種の割合。simlkou.c:181-224 ----
    for nendo in range(STARTY, KIJUNMAP + 1):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            for sei in (1, 2):
                if (kounen[1, y, sei, nenrei]) > 0.0:
                    rk_sen[y, sei, nenrei] = (
                        (kounen[3, y, sei, nenrei])
                        / (kounen[1, y, sei, nenrei]))
    for nendo in range(KIJUNMAP + 1, ENDY + 1):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            if nenrei <= 29:
                # 癖 4.：実績4年度ぶんを足して割る
                for ii in range(STARTY, KIJUNMAP + 1):
                    rk_sen[y, 1, nenrei] += rk_sen[ii - STARTY, 1, nenrei]
                rk_sen[y, 1, nenrei] /= KIJUNMAP - STARTY + 1
            elif nenrei >= 85:
                rk_sen[y, 1, nenrei] = 0.0
            else:
                rk_sen[y, 1, nenrei] = rk_sen[y - 1, 1, nenrei - 1]
            for sei in range(2, 5):
                rk_sen[y, sei, nenrei] = 0.0
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for nenrei in range(A0, A1):
            for sei in range(1, 5):
                kounen[3, y, sei, nenrei] = ((kounen[1, y, sei, nenrei])
                                             * (rk_sen[y, sei, nenrei]))
                kounen[2, y, sei, nenrei] = (
                    (kounen[1, y, sei, nenrei])
                    - (kounen[3, y, sei, nenrei]))
            kounen[3, y, 0, nenrei] = ((kounen[3, y, 1, nenrei])
                                       + (kounen[3, y, 2, nenrei]))
            kounen[2, y, 0, nenrei] = ((kounen[2, y, 1, nenrei])
                                       + (kounen[2, y, 2, nenrei]))

    # ---- 9. 年度末の総労働時間。simlkou.c:226-249 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        TMP = 0.0
        TMQ = 0.0
        for sei in range(0, 5):
            for nenrei in range(A0, A1):
                sdm[6, y, sei, nenrei] = ((kjm[8, y, sei, nenrei])
                                          * (hm[1, y]))
                sdm[7, y, sei, nenrei] = ((kjm[9, y, sei, nenrei])
                                          * (hm[2, y]))
                sdm[8, y, sei, nenrei] = ((kjm[10, y, sei, nenrei])
                                          * (hm[8, y]))
                sdm[9, y, sei, nenrei] = ((sdm[6, y, sei, nenrei])
                                          + (sdm[7, y, sei, nenrei])
                                          + (sdm[8, y, sei, nenrei]))
                # 癖 5.：sei == 0 かつ 69歳以下のときだけ足す
                if sei == 0 and nenrei <= 69:
                    TMP += (kjm[7, y, 0, nenrei])
                    TMQ += (sdm[9, y, 0, nenrei])
        hm[10, y] = TMQ / TMP

    # ---- 年度末→年央。simlkou.c:251-282 ----
    for nendo in range(STARTY + 1, ENDY):
        y = nendo - STARTY
        TMP = 0.0
        TMQ = 0.0
        for sei in range(0, 5):
            for nenrei in range(A0, A1):
                for ii in range(8, 11):
                    kjc[ii, y, sei, nenrei] = (
                        ((kjm[ii, y - 1, sei, nenrei])
                         + (kjm[ii, y, sei, nenrei])) / 2.0)
                kjc[7, y, sei, nenrei] = ((kjc[8, y, sei, nenrei])
                                          + (kjc[9, y, sei, nenrei])
                                          + (kjc[10, y, sei, nenrei]))
                sdc[6, y, sei, nenrei] = ((kjc[8, y, sei, nenrei])
                                          * (hc[1, y]))
                sdc[7, y, sei, nenrei] = ((kjc[9, y, sei, nenrei])
                                          * (hc[2, y]))
                sdc[8, y, sei, nenrei] = ((kjc[10, y, sei, nenrei])
                                          * (hc[8, y]))
                sdc[9, y, sei, nenrei] = ((sdc[6, y, sei, nenrei])
                                          + (sdc[7, y, sei, nenrei])
                                          + (sdc[8, y, sei, nenrei]))
                if sei == 0 and nenrei <= 69:
                    TMP += (kjc[7, y, 0, nenrei])
                    TMQ += (sdc[9, y, 0, nenrei])
        hc[10, y] = TMQ / TMP

    # ---- 10. kounen[0] と nigou。simlkou.c:284-303 ----
    for nendo in range(STARTY, ENDY):
        y = nendo - STARTY
        for sei in range(0, 5):
            for nenrei in range(A0, A1):
                kounen[1, y, sei, nenrei] = (
                    (kounen[2, y, sei, nenrei])
                    + (kounen[3, y, sei, nenrei]))
                kounen[0, y, sei, nenrei] = (kounen[1, y, sei, nenrei])
                if nenrei <= 69:
                    nigou[y, sei, nenrei] = (kounen[1, y, sei, nenrei])
                else:
                    nigou[y, sei, nenrei] = 0.0
                for seido in range(4, 7):
                    nigou[y, sei, nenrei] += (
                        kounen[seido, y, sei, nenrei])
                    kounen[0, y, sei, nenrei] += (
                        kounen[seido, y, sei, nenrei])
