# -*- coding: utf-8 -*-
"""
被保険者推計/cutout.c の忠実移植
================================
**マクロ経済スライドの調整率**を作って `waku{BANGO}-m.csv` に書く。
①の最後。⑤収支計算の `cutritu` の入力にもなる考え方の元。

やっていること（`cutout.c` の上から）
------------------------------------
1. 公的年金の被保険者数 `kouteki` を年度ごとに積む（`cutout.c:44-68`）

       15〜69歳の 厚年(kounen[1]) ＋ パート
       ＋ 15〜110歳の 共済3制度
       ＋ 20〜XEND-1歳の 3号計 と 1号(一般)
       ＋ 20〜69歳の 1号(任意)

2. 年央の被保険者数 `kouteki_cent` を作る（70-80）。
   **2020〜2022年度は実績値を直値で入れている**

       2020 → 67,636,858
       2021 → 67,446,262
       2022 → 67,435,295

   2023年度以降は前年度と当年度の平均。

3. 調整率を作る（82-104）

       cutritu[年度] = ( (5年前の被保険者数 − TMQ) / (2年前 − TMP) )^(1/3)
                       × 0.997

   `0.997` は平均余命の伸びを表す固定値（`JYUMYO`）。3乗根は
   「3年分の変化を1年あたりに直す」ため。45年化のときだけ
   `TMP`/`TMQ` に60歳以上の1号・3号を足して除く（85-96）。

4. 1 を超えたら 1 に切り、`cutritu2 = 1/cutritu − 1` を作る（106-111）
5. `cutritu` を小数6桁、`cutritu2` を小数4桁に丸める（112-115）
6. `cutritu2` を `%7.6f` で書く（117-119）

原本の癖をそのまま残しているところ
----------------------------------
1. **`ii` のループ（0〜1）が2回同じことをする**（`cutout.c:46-67`）
   中身が `ii` に依らないので `kouteki[年度][0]` と `[1]` は同じ値に
   なる。使うのは `[0]` だけ。`kouteki_cent` も同じ。
   （`検証/原本の不具合.md`）

2. **`%7.6f` は幅7・小数6桁**。`0.998234` のように7文字になるので
   幅の指定は効かない。

3. **`cutritu2` を4桁に丸めてから6桁で書く**（`cutout.c:114,118`）
   末尾2桁は必ず 0 になる。

4. **`TMQEND = xend[nendo-2-STARTY]` の添字**（`cutout.c:84`）
   `nendo` は `CUT_JY+1`（2025）から始まるので `nendo-2 >= 2023`。
   範囲外にはならない。

5. **`nendo-6 >= STARTY` を確かめるのは45年化の枝だけ**（`cutout.c:86`）
   `cutritu` 本体（97-98）は `nendo-5-STARTY` を無条件に使うが、
   `nendo >= 2025` なので `nendo-5 >= 2020 == STARTY`。ちょうど収まる。

6. **`cutritu` が 0 だと `1/cutritu` が inf**（`cutout.c:110`）
   `CNENDO`（2005）〜`CUT_JY`（2024）は実績ファイルから読むので 0 には
   ならない。

7. **書くのは `KF`（2125）まで**（`cutout.c:117`）
   `cutritu` は `ENDY`（2150）まで作るが、出力は 2125 で止める。
"""
import math
import sys

from cnum import raund
from fopn import P
from glva import G
from setconst import CNENDO, CUT_JY, ENDY, KF, STARTY

__all__ = ["cutout"]


def _cpow(x, y):
    """C の `pow`。底が負で指数が整数でないとき **nan** を返す。

    Python の `math.pow` は同じ場合に `ValueError` を投げるので合わせる。
    被保険者数の比なので負にはならないが、原本と落ち方を揃えておく。
    """
    if x < 0.0 and y != int(y):
        return math.nan
    try:
        return math.pow(x, y)
    except (ValueError, OverflowError):
        return math.nan


def cutout():
    """cutout.c:9 の忠実移植。"""
    BANGO = G.BANGO
    kounen, partnin = G.kounen, G.partnin
    ichigou, sangou = G.ichigou, G.sangou
    cutritu, xend = G.cutritu, G.xend
    NY = ENDY - STARTY + 1
    NC2 = ENDY - CNENDO + 1

    try:
        fp = open(P.cutm(BANGO), "w", encoding="utf-8", newline="")
    except OSError:
        print("出力cutファイルを開けません!", file=sys.stderr)
        raise SystemExit(2)

    # 局所配列。cutout.c:15-21
    TMP = [0.0] * NY
    TMQ = [0.0] * NY
    cutritu2 = [0.0] * NC2
    kouteki = [[0.0, 0.0] for _ in range(NY)]
    kouteki_cent = [[0.0, 0.0] for _ in range(NY)]

    JYUMYO = 0.997

    # ---- 1. 被保険者数を積む。cutout.c:44-68 ----
    # 癖 1.：ii の 0 と 1 で同じことを2回する
    for nendo in range(STARTY, ENDY + 1):
        y = nendo - STARTY
        XEND = int(xend[y])
        for ii in (0, 1):
            acc = kouteki[y][ii]
            for sei in (1, 2):
                for nenrei in range(15, 111):
                    if nenrei < 70:
                        acc += ((kounen[1, y, sei, nenrei])
                                + (partnin[y, sei, nenrei, 0, 0, 0]))
                    for seido in range(4, 7):
                        acc += (kounen[seido, y, sei, nenrei])
                    if 20 <= nenrei < XEND:
                        acc += (sangou[0, y, sei, nenrei])
                    if 20 <= nenrei < XEND:
                        acc += (ichigou[1, y, sei, nenrei])
                    if 20 <= nenrei < 70:
                        acc += (ichigou[2, y, sei, nenrei])
            kouteki[y][ii] = acc

    # ---- 2. 年央の被保険者数。cutout.c:70-80 ----
    for ii in (0, 1):
        kouteki_cent[0][ii] = 67636858.0
        kouteki_cent[1][ii] = 67446262.0
        kouteki_cent[2][ii] = 67435295.0
    for nendo in range(STARTY + 3, ENDY + 1):
        y = nendo - STARTY
        for ii in (0, 1):
            kouteki_cent[y][ii] = (kouteki[y - 1][ii] + kouteki[y][ii]) / 2.0

    # ---- 3. 調整率。cutout.c:82-104 ----
    for nendo in range(CUT_JY + 1, ENDY + 1):
        y = nendo - STARTY
        if kouteki_cent[y - 5][0] > 0.0:
            TMQEND = int(xend[y - 2])
            if G.MODE45 == 1:
                if TMQEND > 60 and nendo - 6 >= STARTY:
                    for nenrei in range(60, TMQEND):
                        TMP[y] += (
                            (ichigou[1, y - 6, 0, nenrei])
                            + (ichigou[1, y - 5, 0, nenrei])
                            + (sangou[0, y - 6, 0, nenrei])
                            + (sangou[0, y - 5, 0, nenrei])) / 2.0
                        TMQ[y] += (
                            (ichigou[1, y - 3, 0, nenrei])
                            + (ichigou[1, y - 2, 0, nenrei])
                            + (sangou[0, y - 3, 0, nenrei])
                            + (sangou[0, y - 2, 0, nenrei])) / 2.0
            cutritu[nendo - CNENDO] = _cpow(
                (kouteki_cent[y - 2][0] - TMQ[y])
                / (kouteki_cent[y - 5][0] - TMP[y]), 1.0 / 3.0) * JYUMYO
        else:
            print(f"{nendo - 5:02d}年度の公的年金被保険者数が"
                  "正しくありません!", file=sys.stderr)
            raise SystemExit(2)

    # ---- 4. 1 で切って cutritu2 を作る。cutout.c:106-111 ----
    for nendo in range(CNENDO, ENDY + 1):
        k = nendo - CNENDO
        if (cutritu[k]) > 1.0:
            cutritu[k] = 1.0
        cutritu2[k] = 1.0 / (cutritu[k]) - 1.0

    # ---- 5. 丸め。cutout.c:112-115 ----
    for nendo in range(CNENDO, ENDY + 1):
        k = nendo - CNENDO
        cutritu[k] = raund((cutritu[k]), 6)
        cutritu2[k] = raund(cutritu2[k], 4)

    # ---- 6. 書く。cutout.c:117-119 ----
    out = []
    for nendo in range(CNENDO, KF + 1):
        k = nendo - CNENDO
        out.append(f"{nendo:4d},{cutritu2[k]:7.6f}\n")
    fp.write("".join(out))
    fp.close()
