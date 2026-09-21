# -*- coding: utf-8 -*-
"""
被保険者推計/simlpart.c の忠実移植
==================================
**適用拡大（パート）の人数**を作る。①でいちばん大きい（694行）。
`partnin[年度][性][年齢][pkubun][tkubun][ykubun]` を埋め、その分を
1号・3号から差し引く。

添字の意味（読み解いた範囲）
----------------------------
    pkubun  0 計 / 1 元1号 / 2 元3号 / 3..6 元3号の制度別 / 7 元その他
    tkubun  0 計 / 1 週30時間以上 / 2 週20〜30時間 / 3 週20時間未満
    ykubun  0 累積 / 1 現行（2024年10月） / 2 1段階目 / 3 2段階目
    kubun   5歳きざみの年齢区分。`TMO = kubun*5 + 12` が中心年齢で、
            `TMO-2 .. TMO+2` の5歳が入る（kubun=1 → 15〜19歳、
            kubun=11 → 65〜69歳）

やっていること（`simlpart.c` の上から）
--------------------------------------
 1. 局所配列を 0 にする（`simlpart.c:26-44`）
 2. 年齢区分別の短時間雇用者数 `kbetu_tankoj` を作る（46-60）
      [1] = koyou_j_m[4]+[5]（週20時間未満とその下）
      [2] = koyou_j_m[1]+[2]+[6]
      [3] = koyou_j_m[3]
 3. 基礎数値（`kbetu_partkiso`）を短時間雇用者数の伸びで延ばして
    `kbetu_partnin` にする（62-106）。`kubun` 2〜9 は pkubun 7 を 1 に
    寄せ、`tkubun == 2` は pkubun 2 を 1 に寄せる
 4. 元制度の人数 `kbetu_partgen` を作る（108-124）
      kubun 2〜9  [1] = 1号(一般)、[2] = 3号計
      kubun 10,11 [1] = 1号(任意)
 5. 元制度の人数で頭を打ち、割合 `p_wari` を作る（126-214）
 6. 年齢別の短時間雇用者数 `nbetu_tankoj`（216-227）
 7. 15〜19歳のパート（229-252）
 8. 20〜59歳のパートを 1号・3号から差し引く（253-320）
 9. 60〜69歳（321-356）と 65〜74歳の pkubun 7（357-382）
10. **45年化のとき**の 60歳以上（383-541）。`MODE45 == 0` なら
    `XEND == 60` なので**このループは1回も回らない**
11. 合計の作り直し（544-588）
12. `tashikomi` で雇用者数・総労働時間にパートを足し込む（590-609）
13. 平均労働時間を作り直す（611-621）
14. 1号計・3号計の作り直し（623-636）

原本の癖をそのまま残しているところ
----------------------------------
1. **効かないループが2つある**
   - `simlpart.c:562` `for tkubun = 1..3` の中身が `tkubun` に依らない。
     同じ代入を3回する（`partnin[..][pkubun][0][ykubun]` を
     `[1]+[2]+[3]` で作る）。結果は同じ。
   - `simlpart.c:167-172` / `130-135` も `[0]` への足し込みで、
     `+=` なので**回数が意味を持つ**。こちらは 3 回足す（tkubun 1〜3）。

2. **年度の下限が直値の 2024**（`simlpart.c:108,126,229,544,558,574,590,611,623`）
   `CUT_JY` と同じ値だが定数を使っていない。

3. **`printf` と `fprintf(fp_err, …)` に同じ文を出す**
   パートの人数が合わないときの記録。7箇所ある。

4. **`exit(2)` する枝がある**（`simlpart.c:397`）
   45年化で1号または3号が負になったとき。`MODE45 == 0` なら
   そのループに入らないので到達しない。

5. **ゼロ除算を見ていない割り算が多い**
   `simlpart.c:236,243,365,372,411,416,483-492` など。
   同梱データでは 0 にならない。

6. **`kbetu_tankoj[PARTKYR]` が 0 のときの分岐でメッセージが紛らわしい**
   （`simlpart.c:77-80`）「短雇がマイナス!」と出すが、実際に見ている
   のは `> 0.0` なので「0 か負」。
"""
import sys

import numpy as np

from glva import G
from setconst import ENDY, NAGE, NSEI, NY, STARTY

__all__ = ["simlpart", "tashikomi"]


def simlpart():
    """simlpart.c:9 の忠実移植。"""
    PARTKYR, PARTYR1, PARTYR2 = G.PARTKYR, G.PARTYR1, G.PARTYR2
    partnin, p_wari = G.partnin, G.p_wari
    kbn, kbk = G.kbetu_partnin, G.kbetu_partkiso
    kjm = G.koyou_j_m
    ichigou, sangou = G.ichigou, G.sangou
    xend = G.xend
    err = G.fp_err

    # ---- 1. 局所配列。simlpart.c:21-44 ----
    ktj = np.zeros((NY, NSEI, 17, 4), dtype=np.float64)   # kbetu_tankoj
    ntj = np.zeros((NY, NSEI, NAGE, 4), dtype=np.float64)  # nbetu_tankoj
    kpg = np.zeros((NY, NSEI, 17, 8), dtype=np.float64)   # kbetu_partgen

    def note(msg):
        """`printf` と `fprintf(fp_err, …)` の両方に出す（癖 3.）。

        `msg` は改行込み。`print` は改行を足してしまうので
        `sys.stdout.write` を使う。
        """
        sys.stdout.write(msg)
        if err is not None:
            err.write(msg)

    # ---- 2. 年齢区分別の短時間雇用者数。simlpart.c:46-60 ----
    for nendo in range(PARTKYR, ENDY + 1):
        y = nendo - STARTY
        for sei in (1, 2):
            for kubun in range(1, 16):
                TMO = kubun * 5 + 12
                for nenrei in range(TMO - 2, TMO + 3):
                    ktj[y, sei, kubun, 1] += (
                        (kjm[4, y, sei, nenrei])
                        + (kjm[5, y, sei, nenrei]))
                    ktj[y, sei, kubun, 2] += (
                        (kjm[1, y, sei, nenrei])
                        + (kjm[2, y, sei, nenrei])
                        + (kjm[6, y, sei, nenrei]))
                    ktj[y, sei, kubun, 3] += (kjm[3, y, sei, nenrei])

    # ---- 3. 基礎数値を延ばす。simlpart.c:62-106 ----
    kp = PARTKYR - STARTY
    for nendo in range(PARTKYR + 1, ENDY + 1):
        y = nendo - STARTY
        for sei in (1, 2):
            for kubun in range(1, 16):
                for pkubun in range(1, 8):
                    if pkubun <= 2 or pkubun == 7:
                        for tkubun in range(1, 4):
                            for ykubun in range(1, 4):
                                base = (ktj[kp, sei, kubun, tkubun])
                                if base > 0.0:
                                    kbn[y, sei, kubun, pkubun, tkubun,
                                        ykubun] = (
                                        (kbk[sei, kubun, pkubun, tkubun,
                                                  ykubun])
                                        * (ktj[y, sei, kubun, tkubun])
                                        / base)
                                else:
                                    kbn[y, sei, kubun, pkubun, tkubun,
                                        ykubun] = 0.0
                                    # 癖 6.
                                    note(f"パート推計で{PARTKYR}年度の性{sei}"
                                         f"年齢区分{kubun}時間区分{tkubun}の"
                                         "短雇がマイナス!\n")
                for tkubun in range(1, 4):
                    for ykubun in range(1, 4):
                        if 2 <= kubun <= 9:
                            kbn[y, sei, kubun, 1, tkubun, ykubun] += \
                                kbn[y, sei, kubun, 7, tkubun, ykubun]
                            kbn[y, sei, kubun, 7, tkubun, ykubun] = 0.0
                        if tkubun == 2:
                            kbn[y, sei, kubun, 1, tkubun, ykubun] += \
                                kbn[y, sei, kubun, 2, tkubun, ykubun]
                            kbn[y, sei, kubun, 2, tkubun, ykubun] = 0.0
                        kbn[y, sei, kubun, 0, tkubun, ykubun] = (
                            (kbn[y, sei, kubun, 1, tkubun, ykubun])
                            + (kbn[y, sei, kubun, 2, tkubun, ykubun])
                            + (kbn[y, sei, kubun, 7, tkubun, ykubun]))

    # ---- 4. 元制度の人数。simlpart.c:108-124 ----
    for nendo in range(2024, ENDY + 1):          # 癖 2.：直値の 2024
        y = nendo - STARTY
        for sei in (1, 2):
            for kubun in range(2, 10):
                TMO = kubun * 5 + 12
                for nenrei in range(TMO - 2, TMO + 3):
                    kpg[y, sei, kubun, 1] += (ichigou[1, y, sei, nenrei])
                    kpg[y, sei, kubun, 2] += (sangou[0, y, sei, nenrei])
            for kubun in range(10, 12):
                TMO = kubun * 5 + 12
                for nenrei in range(TMO - 2, TMO + 3):
                    kpg[y, sei, kubun, 1] += (ichigou[2, y, sei, nenrei])

    # ---- 5. 頭を打って p_wari を作る。simlpart.c:126-214 ----
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        for sei in (1, 2):
            for kubun in range(2, 10):
                for pkubun in (1, 2):
                    # 癖 1.：[0] に tkubun 1〜3 を足し込む
                    for tkubun in range(1, 4):
                        for ykubun in range(1, 4):
                            kbn[y, sei, kubun, pkubun, 0, ykubun] += \
                                kbn[y, sei, kubun, pkubun, tkubun, ykubun]
                    gen = (kpg[y, sei, kubun, pkubun])
                    for tkubun in range(1, 4):
                        for ykubun in range(1, 4):
                            if gen < 0.0:
                                kbn[y, sei, kubun, pkubun, tkubun,
                                    ykubun] = 0.0
                                note(f"パート {nendo}年度の性{sei}、"
                                     f"年齢区分{kubun}の元制度{pkubun}が"
                                     "マイナス\n")
                            elif (kbn[y, sei, kubun, pkubun, 0,
                                           ykubun]) > gen:
                                kbn[y, sei, kubun, pkubun, tkubun,
                                    ykubun] *= (
                                    gen / (kbn[y, sei, kubun, pkubun, 0,
                                                    ykubun]))
                                note(f"パート {nendo}年度の性{sei}、"
                                     f"年齢区分{kubun}、元制度{pkubun}が"
                                     "減算しきれない\n")
                            TMO = kubun * 5 + 12
                            v = ((kbn[y, sei, kubun, pkubun, tkubun,
                                           ykubun]) / gen)
                            for nenrei in range(TMO - 2, TMO + 3):
                                p_wari[y, sei, nenrei, pkubun, tkubun,
                                       ykubun] = v

            for kubun in range(10, 12):
                for tkubun in range(1, 4):
                    for ykubun in range(1, 4):
                        kbn[y, sei, kubun, 1, 0, ykubun] += \
                            kbn[y, sei, kubun, 1, tkubun, ykubun]
                gen = (kpg[y, sei, kubun, 1])
                for tkubun in range(1, 4):
                    for ykubun in range(1, 4):
                        if gen < 0.0:
                            kbn[y, sei, kubun, 1, tkubun, ykubun] = 0.0
                            note(f"パート {nendo}年度の性{sei}、"
                                 f"年齢区分{kubun}の元制度1がマイナス\n")
                        elif (kbn[y, sei, kubun, 1, 0, ykubun]) > gen:
                            kbn[y, sei, kubun, 1, tkubun, ykubun] *= (
                                gen / (kbn[y, sei, kubun, 1, 0, ykubun]))
                            note(f"パート {nendo}年度の性{sei}、"
                                 f"年齢区分{kubun}、元制度1が減算しきれない\n")
                        TMO = kubun * 5 + 12
                        v = (kbn[y, sei, kubun, 1, tkubun, ykubun]) / gen
                        for nenrei in range(TMO - 2, TMO + 3):
                            p_wari[y, sei, nenrei, 1, tkubun, ykubun] = v

        # simlpart.c:202-213。女有配偶・無配偶は女（性2）の割合をそのまま
        for sei in (3, 4):
            p_wari[y, sei, 20:70, 1:8, 1:4, 1:4] = \
                p_wari[y, 2, 20:70, 1:8, 1:4, 1:4]

    # ---- 6. 年齢別の短時間雇用者数。simlpart.c:216-227 ----
    for nendo in range(PARTKYR, ENDY + 1):
        y = nendo - STARTY
        ntj[y, 1:5, 15:101, 1] = (kjm[4, y, 1:5, 15:101]
                                  + kjm[5, y, 1:5, 15:101])
        ntj[y, 1:5, 15:101, 2] = (kjm[1, y, 1:5, 15:101]
                                  + kjm[2, y, 1:5, 15:101]
                                  + kjm[6, y, 1:5, 15:101])
        ntj[y, 1:5, 15:101, 3] = kjm[3, y, 1:5, 15:101]

    # ---- 7〜11 ----
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        # 7. 15〜19歳。simlpart.c:229-252
        for nenrei in range(15, 20):
            for ykubun in range(1, 4):
                for sei in (1, 2):
                    for tkubun in range(1, 4):
                        partnin[y, sei, nenrei, 7, tkubun, ykubun] = (
                            (kbn[y, sei, 1, 7, tkubun, ykubun])
                            * (ntj[y, sei, nenrei, tkubun])
                            / (ktj[y, sei, 1, tkubun]))
                for sei in (3, 4):
                    for tkubun in range(1, 4):
                        partnin[y, sei, nenrei, 7, tkubun, ykubun] = (
                            (partnin[y, 2, nenrei, 7, tkubun, ykubun])
                            * (ntj[y, sei, nenrei, tkubun])
                            / (ntj[y, 2, nenrei, tkubun]))
                for tkubun in range(1, 4):
                    partnin[y, 0, nenrei, 7, tkubun, ykubun] = (
                        (partnin[y, 1, nenrei, 7, tkubun, ykubun])
                        + (partnin[y, 2, nenrei, 7, tkubun, ykubun]))

        # 8. 20〜59歳。simlpart.c:253-320
        for nenrei in range(20, 60):
            for tkubun in range(1, 4):
                for ykubun in range(1, 4):
                    for sei in range(1, 5):
                        w1 = (p_wari[y, sei, nenrei, 1, tkubun, ykubun])
                        w2 = (p_wari[y, sei, nenrei, 2, tkubun, ykubun])
                        partnin[y, sei, nenrei, 1, tkubun, ykubun] = (
                            (ichigou[1, y, sei, nenrei]) * w1)
                        partnin[y, sei, nenrei, 2, tkubun, ykubun] = (
                            (sangou[0, y, sei, nenrei]) * w2)
                        partnin[y, sei, nenrei, 3, tkubun, ykubun] = (
                            (sangou[1, y, sei, nenrei]) * w2)
                        partnin[y, sei, nenrei, 4, tkubun, ykubun] = (
                            (sangou[4, y, sei, nenrei]) * w2)
                        partnin[y, sei, nenrei, 5, tkubun, ykubun] = (
                            (sangou[5, y, sei, nenrei]) * w2)
                        partnin[y, sei, nenrei, 6, tkubun, ykubun] = (
                            (sangou[6, y, sei, nenrei]) * w2)
                    for pkubun in range(1, 7):
                        partnin[y, 0, nenrei, pkubun, tkubun, ykubun] = (
                            (partnin[y, 1, nenrei, pkubun, tkubun,
                                          ykubun])
                            + (partnin[y, 2, nenrei, pkubun, tkubun,
                                            ykubun]))
            yk = _ykubun(nendo, PARTYR1, PARTYR2)
            for sei in range(1, 5):
                for tkubun in range(1, 4):
                    ichigou[1, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 1, tkubun, yk]
                    sangou[1, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 3, tkubun, yk]
                    sangou[4, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 4, tkubun, yk]
                    sangou[5, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 5, tkubun, yk]
                    sangou[6, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 6, tkubun, yk]
            ichigou[1, y, 0, nenrei] = ((ichigou[1, y, 1, nenrei])
                                        + (ichigou[1, y, 2, nenrei]))
            for seido in (1, 4, 5, 6):
                sangou[seido, y, 0, nenrei] = (
                    (sangou[seido, y, 1, nenrei])
                    + (sangou[seido, y, 2, nenrei]))

        # 9. 60〜69歳。simlpart.c:321-356
        for nenrei in range(60, 70):
            for tkubun in range(1, 4):
                for ykubun in range(1, 4):
                    for sei in range(1, 5):
                        partnin[y, sei, nenrei, 1, tkubun, ykubun] = (
                            (ichigou[2, y, sei, nenrei])
                            * (p_wari[y, sei, nenrei, 1, tkubun,
                                           ykubun]))
                    partnin[y, 0, nenrei, 1, tkubun, ykubun] = (
                        (partnin[y, 1, nenrei, 1, tkubun, ykubun])
                        + (partnin[y, 2, nenrei, 1, tkubun, ykubun]))
            yk = _ykubun(nendo, PARTYR1, PARTYR2)
            for sei in range(1, 5):
                for tkubun in range(1, 4):
                    ichigou[2, y, sei, nenrei] -= \
                        partnin[y, sei, nenrei, 1, tkubun, yk]
            ichigou[2, y, 0, nenrei] = ((ichigou[2, y, 1, nenrei])
                                        + (ichigou[2, y, 2, nenrei]))

        # 9b. 65〜74歳の pkubun 7。simlpart.c:357-382
        for kubun in range(10, 12):
            TMO = kubun * 5 + 12
            for nenrei in range(TMO - 2, TMO + 3):
                for ykubun in range(1, 4):
                    for sei in (1, 2):
                        for tkubun in range(1, 4):
                            partnin[y, sei, nenrei, 7, tkubun, ykubun] = (
                                (kbn[y, sei, kubun, 7, tkubun, ykubun])
                                * (ntj[y, sei, nenrei, tkubun])
                                / (ktj[y, sei, kubun, tkubun]))
                    for sei in (3, 4):
                        for tkubun in range(1, 4):
                            partnin[y, sei, nenrei, 7, tkubun, ykubun] = (
                                (partnin[y, 2, nenrei, 7, tkubun,
                                              ykubun])
                                * (ntj[y, sei, nenrei, tkubun])
                                / (ntj[y, 2, nenrei, tkubun]))
                    for tkubun in range(1, 4):
                        partnin[y, 0, nenrei, 7, tkubun, ykubun] = (
                            (partnin[y, 1, nenrei, 7, tkubun, ykubun])
                            + (partnin[y, 2, nenrei, 7, tkubun, ykubun]))

        # 10. 45年化のときの 60歳以上。simlpart.c:383-541
        # MODE45 == 0 なら XEND == 60 なのでこのループは回らない（癖 4.）
        XEND = int(xend[y])
        for nenrei in range(60, XEND):
            _mode45_part(y, nendo, nenrei, partnin, p_wari, ichigou, sangou,
                         PARTYR1, PARTYR2, note)
            ichigou[1, y, 2, nenrei] = ((ichigou[1, y, 3, nenrei])
                                        + (ichigou[1, y, 4, nenrei]))
            ichigou[1, y, 0, nenrei] = ((ichigou[1, y, 1, nenrei])
                                        + (ichigou[1, y, 2, nenrei]))
            for seido in range(0, 7):
                sangou[seido, y, 2, nenrei] = (
                    sangou[seido, y, 3, nenrei])
                sangou[seido, y, 0, nenrei] = (
                    (sangou[seido, y, 1, nenrei])
                    + (sangou[seido, y, 2, nenrei]))
            for pkubun in range(1, 8):
                for tkubun in range(1, 4):
                    for ykubun in range(1, 4):
                        partnin[y, 2, nenrei, pkubun, tkubun, ykubun] = (
                            (partnin[y, 3, nenrei, pkubun, tkubun,
                                          ykubun])
                            + (partnin[y, 4, nenrei, pkubun, tkubun,
                                            ykubun]))
                        partnin[y, 0, nenrei, pkubun, tkubun, ykubun] = (
                            (partnin[y, 1, nenrei, pkubun, tkubun,
                                          ykubun])
                            + (partnin[y, 2, nenrei, pkubun, tkubun,
                                            ykubun]))

    # ---- 11. 合計の作り直し。simlpart.c:544-588 ----
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        # pkubun 0 = [1] + [2] + [7]
        partnin[y, 0:5, 15:80, 0, 1:4, 1:4] = (
            partnin[y, 0:5, 15:80, 1, 1:4, 1:4]
            + partnin[y, 0:5, 15:80, 2, 1:4, 1:4]
            + partnin[y, 0:5, 15:80, 7, 1:4, 1:4])
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        # tkubun 0 = [1] + [2] + [3]（癖 1.：原本は同じ代入を3回する）
        partnin[y, 0:5, 15:80, 0:8, 0, 1:4] = (
            partnin[y, 0:5, 15:80, 0:8, 1, 1:4]
            + partnin[y, 0:5, 15:80, 0:8, 2, 1:4]
            + partnin[y, 0:5, 15:80, 0:8, 3, 1:4])
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        yk = _ykubun(nendo, PARTYR1, PARTYR2)
        partnin[y, 0:5, 15:80, 0, 0, 0] += partnin[y, 0:5, 15:80, 0, 0, yk]

    # ---- 12. tashikomi。simlpart.c:590-609 ----
    for nendo in range(2024, ENDY + 1):
        G.nendo = nendo
        if nendo == 2024:
            tashikomi(0, 1, 1)
        elif nendo < PARTYR1:
            tashikomi(1, 1, 0)
        elif nendo == PARTYR1:
            tashikomi(1, 2, 0)
        elif nendo < PARTYR2:
            tashikomi(2, 2, 0)
        elif nendo == PARTYR2:
            tashikomi(2, 3, 0)
        else:
            tashikomi(3, 3, 0)

    # ---- 13. 平均労働時間。simlpart.c:611-621 ----
    kjc, sdm, sdc = G.koyou_j_c, G.soroudh_m, G.soroudh_c
    hm, hc = G.heikinh_m, G.heikinh_c
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        TMP = 0.0
        TMQ = 0.0
        TMR = 0.0
        TMS = 0.0
        for nenrei in range(15, 70):
            TMP += (kjm[7, y, 0, nenrei])
            TMQ += (sdm[9, y, 0, nenrei])
            TMR += (kjc[7, y, 0, nenrei])
            TMS += (sdc[9, y, 0, nenrei])
        hm[10, y] = TMQ / TMP
        hc[10, y] = TMS / TMR

    # ---- 14. 1号計・3号計。simlpart.c:623-636 ----
    for nendo in range(2024, ENDY + 1):
        y = nendo - STARTY
        XEND = int(xend[y])
        for sei in range(0, 5):
            ichigou[0, y, sei, 15:101] = (ichigou[1, y, sei, 15:101]
                                          + ichigou[2, y, sei, 15:101])
            sangou[0, y, sei, 20:XEND] = (sangou[1, y, sei, 20:XEND]
                                          + sangou[4, y, sei, 20:XEND]
                                          + sangou[5, y, sei, 20:XEND]
                                          + sangou[6, y, sei, 20:XEND])


def _ykubun(nendo, PARTYR1, PARTYR2):
    """`simlpart.c:277,288,299` ほかに何度も出てくる3分岐。

        nendo < PARTYR1  → 1（現行）
        nendo < PARTYR2  → 2（1段階目）
        それ以外         → 3（2段階目）
    """
    if nendo < PARTYR1:
        return 1
    if nendo < PARTYR2:
        return 2
    return 3


def _mode45_part(y, nendo, nenrei, partnin, p_wari, ichigou, sangou,
                 PARTYR1, PARTYR2, note):
    """simlpart.c:384-519 の1年齢ぶん。**45年化のときだけ回る**。

    `MODE45 == 0` では `xend` が一律 60 なので `for nenrei = 60 .. XEND-1`
    が空になり、ここは呼ばれない。移植はしてあるが**未検証**
    （`検証/移植/README.md` の「未検証のまま残っている枝」を参照）。
    """
    for sei in range(1, 5):
        for tkubun in range(1, 4):
            for ykubun in range(1, 4):
                partnin[y, sei, nenrei, 7, 0, ykubun] += \
                    partnin[y, sei, nenrei, 7, tkubun, ykubun]
        i1 = (ichigou[1, y, sei, nenrei])
        s0 = (sangou[0, y, sei, nenrei])
        if i1 < 0.0 or s0 < 0.0:
            note(f"パート(45年化) {nendo}年度の性{sei}、年齢{nenrei}の"
                 "１号または３号がマイナス\n")
            raise SystemExit(2)
        for tkubun in range(1, 4):
            for ykubun in range(1, 4):
                if ((partnin[y, sei, nenrei, 7, 0, ykubun])
                        > i1 + s0):
                    partnin[y, sei, nenrei, 7, tkubun, ykubun] *= (
                        (i1 + s0)
                        / (partnin[y, sei, nenrei, 7, 0, ykubun]))
                if tkubun != 2:
                    p_wari[y, sei, nenrei, 7, tkubun, ykubun] = (
                        (partnin[y, sei, nenrei, 7, tkubun, ykubun])
                        / (i1 + s0))
                else:
                    p_wari[y, sei, nenrei, 7, tkubun, ykubun] = (
                        (partnin[y, sei, nenrei, 7, tkubun, ykubun])
                        / i1)
                w7 = (p_wari[y, sei, nenrei, 7, tkubun, ykubun])
                partnin[y, sei, nenrei, 1, tkubun, ykubun] += i1 * w7
                if tkubun != 2:
                    partnin[y, sei, nenrei, 2, tkubun, ykubun] = s0 * w7
                    partnin[y, sei, nenrei, 3, tkubun, ykubun] = (
                        (sangou[1, y, sei, nenrei]) * w7)
                    partnin[y, sei, nenrei, 4, tkubun, ykubun] = (
                        (sangou[4, y, sei, nenrei]) * w7)
                    partnin[y, sei, nenrei, 5, tkubun, ykubun] = (
                        (sangou[5, y, sei, nenrei]) * w7)
                    partnin[y, sei, nenrei, 6, tkubun, ykubun] = (
                        (sangou[6, y, sei, nenrei]) * w7)
                partnin[y, sei, nenrei, 7, tkubun, ykubun] = 0.0

        for pkubun in (1, 2):
            for tkubun in range(1, 4):
                for ykubun in range(1, 4):
                    partnin[y, sei, nenrei, pkubun, 0, ykubun] += \
                        partnin[y, sei, nenrei, pkubun, tkubun, ykubun]

        for tkubun in range(1, 4):
            for ykubun in range(1, 4):
                if tkubun != 2:
                    i1b = (ichigou[1, y, sei, nenrei])
                    s0b = (sangou[0, y, sei, nenrei])
                    if (partnin[y, sei, nenrei, 1, 0, ykubun]) > i1b:
                        TMP = ((partnin[y, sei, nenrei, 1, 0, ykubun])
                               - i1b)
                        TMQ = (partnin[y, sei, nenrei, 1, tkubun,
                                            ykubun])
                        TMR = ((partnin[y, sei, nenrei, 1, 1, ykubun])
                               + (partnin[y, sei, nenrei, 1, 3, ykubun]))
                        if TMR > 0.0:
                            TMS = TMP * (TMQ / TMR)
                        else:
                            note(f"パート {nendo}年度の性{sei}、年齢{nenrei}"
                                 "の元１号の時間計がマイナス\n")
                            TMS = 0.0
                        partnin[y, sei, nenrei, 1, tkubun, ykubun] -= TMS
                        partnin[y, sei, nenrei, 2, tkubun, ykubun] += TMS
                    elif (partnin[y, sei, nenrei, 2, 0, ykubun]) > s0b:
                        TMP = ((partnin[y, sei, nenrei, 2, 0, ykubun])
                               - s0b)
                        TMQ = (partnin[y, sei, nenrei, 2, tkubun,
                                            ykubun])
                        TMR = ((partnin[y, sei, nenrei, 2, 1, ykubun])
                               + (partnin[y, sei, nenrei, 2, 3, ykubun]))
                        if TMR > 0.0:
                            TMS = TMP * (TMQ / TMR)
                        else:
                            if sei != 4:
                                note(f"パート {nendo}年度の性{sei}、"
                                     f"年齢{nenrei}の元３号の時間計が"
                                     "マイナス\n")
                            TMS = 0.0
                        partnin[y, sei, nenrei, 1, tkubun, ykubun] += TMS
                        partnin[y, sei, nenrei, 2, tkubun, ykubun] -= TMS
                if sei != 4:
                    s0c = (sangou[0, y, sei, nenrei])
                    p2 = (partnin[y, sei, nenrei, 2, tkubun, ykubun])
                    partnin[y, sei, nenrei, 3, tkubun, ykubun] = (
                        p2 * (sangou[1, y, sei, nenrei]) / s0c)
                    partnin[y, sei, nenrei, 4, tkubun, ykubun] = (
                        p2 * (sangou[4, y, sei, nenrei]) / s0c)
                    partnin[y, sei, nenrei, 5, tkubun, ykubun] = (
                        p2 * (sangou[5, y, sei, nenrei]) / s0c)
                    partnin[y, sei, nenrei, 6, tkubun, ykubun] = (
                        p2 * (sangou[6, y, sei, nenrei]) / s0c)

        yk = _ykubun(nendo, PARTYR1, PARTYR2)
        for tkubun in range(1, 4):
            ichigou[1, y, sei, nenrei] -= \
                partnin[y, sei, nenrei, 1, tkubun, yk]
            sangou[1, y, sei, nenrei] -= \
                partnin[y, sei, nenrei, 3, tkubun, yk]
            sangou[4, y, sei, nenrei] -= \
                partnin[y, sei, nenrei, 4, tkubun, yk]
            sangou[5, y, sei, nenrei] -= \
                partnin[y, sei, nenrei, 5, tkubun, yk]
            sangou[6, y, sei, nenrei] -= \
                partnin[y, sei, nenrei, 6, tkubun, yk]


def tashikomi(yykubun1, yykubun2, just):
    """simlpart.c:640 の忠実移植。**グローバルの `nendo` を使う。**

    パートの人数を雇用者数（`koyou_j_*[7,9,10]`）と総労働時間
    （`soroudh_*[7,8,9]`）に足し込む。時間の単価は直値で

        tkubun 2（週20〜30時間） 120 時間
        tkubun 1（週30時間以上） 100 時間
        tkubun 3（週20時間未満）  60 時間

    年度末（`_c`）は年度央の半分ずつを前年度と当年度から取る
    （`just == 0`）。2024年度だけは当年度の半分だけ（`just == 1`）で、
    10月からの適用開始に当たると読める。
    """
    nendo = G.nendo
    y = nendo - STARTY
    partnin = G.partnin
    kjm, kjc = G.koyou_j_m, G.koyou_j_c
    sdm, sdc = G.soroudh_m, G.soroudh_c
    y1, y2 = yykubun1, yykubun2

    for sei in range(0, 5):
        G.sei = sei
        for nenrei in range(15, 80):
            G.nenrei = nenrei
            p0 = (partnin[y, sei, nenrei, 0, 0, y2])
            p1 = (partnin[y, sei, nenrei, 0, 1, y2])
            p2 = (partnin[y, sei, nenrei, 0, 2, y2])
            p3 = (partnin[y, sei, nenrei, 0, 3, y2])
            kjm[7, y, sei, nenrei] += p0
            kjm[9, y, sei, nenrei] += p2
            kjm[10, y, sei, nenrei] += p1 + p3
            if just == 1:
                kjc[7, y, sei, nenrei] += p0 / 2.0
                kjc[9, y, sei, nenrei] += p2 / 2.0
                kjc[10, y, sei, nenrei] += p1 / 2.0 + p3 / 2.0
            elif just == 0:
                q0 = (partnin[y - 1, sei, nenrei, 0, 0, y1])
                q1 = (partnin[y - 1, sei, nenrei, 0, 1, y1])
                q2 = (partnin[y - 1, sei, nenrei, 0, 2, y1])
                q3 = (partnin[y - 1, sei, nenrei, 0, 3, y1])
                kjc[7, y, sei, nenrei] += q0 / 2.0 + p0 / 2.0
                kjc[9, y, sei, nenrei] += q2 / 2.0 + p2 / 2.0
                kjc[10, y, sei, nenrei] += (q1 / 2.0 + p1 / 2.0
                                            + q3 / 2.0 + p3 / 2.0)
            sdm[9, y, sei, nenrei] += p2 * 120.0 + p1 * 100.0 + p3 * 60.0
            sdm[7, y, sei, nenrei] += p2 * 120.0
            sdm[8, y, sei, nenrei] += p1 * 100.0 + p3 * 60.0
            if just == 1:
                sdc[9, y, sei, nenrei] += (p2 * 60.0 + p1 * 50.0
                                           + p3 * 30.0)
                sdc[7, y, sei, nenrei] += p2 * 60.0
                sdc[8, y, sei, nenrei] += p1 * 50.0 + p3 * 30.0
            elif just == 0:
                q1 = (partnin[y - 1, sei, nenrei, 0, 1, y1])
                q2 = (partnin[y - 1, sei, nenrei, 0, 2, y1])
                q3 = (partnin[y - 1, sei, nenrei, 0, 3, y1])
                sdc[9, y, sei, nenrei] += (q2 * 60.0 + p2 * 60.0
                                           + q1 * 50.0 + p1 * 50.0
                                           + q3 * 30.0 + p3 * 30.0)
                sdc[7, y, sei, nenrei] += q2 * 60.0 + p2 * 60.0
                sdc[8, y, sei, nenrei] += (q1 * 50.0 + p1 * 50.0
                                           + q3 * 30.0 + p3 * 30.0)
