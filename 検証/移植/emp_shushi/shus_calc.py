# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/shus_calc.c の忠実移植
====================================================
⑤の計算そのもの。給付費を年度内平均に直し（`shus_ave`）、収支を積み上げ
（`shus_shushi`）、有限均衡になるマクロ経済スライドの調整期間を解く
（`shus_calc8`）。所得代替率がここで出る。

原本の癖をそのまま残しているところ
----------------------------------
1. **`etoc` で jj が Cc の列に潰れる**（shus_calc.c:67）
       etoc = {13,14,15,6,7,8,16,5,16,5,16,5,16,5}
   jj=0〜9 に対して 13,14,15,6,7,8,16,5,16,5 なので、**jj=6 と jj=8 が同じ
   列 16 に、jj=7 と jj=9 が同じ列 5 に足し込まれる**。ゼロ埋めは jj=0〜7 で
   回すので、16 と 5 は1回ゼロにされたあと2回ぶん累積する。

2. **x の総和は逐次（縮約なので順序が結果に効く）**（shus_calc.c:109）
       Cc[ii][etoc[jj]][k] += (bpre * 2. + bpre * riv * 6. + bend * 4.) / 12.
   x=66〜115 の50項を昇順に足す。`np.sum` は対数的に足すので使えない。
   一方 **k には依存が無い**（読むのは E3dxb と改定率だけ）。だから
   `shus_calc_fast.py` では「x は逐次のまま k をベクトル化」している。

3. **`nendohosei` を掛けるのは jj<=2 だけ、しかも x の総和の後**
   （shus_calc.c:112）

4. **`Touitu>=1` のときは Escutrrt ではなく Escutrrh を使う**
   （shus_calc.c:151 と 99 を見比べる）。調整期間を一致させるのだから
   同じ率になる、というのが式に現れている。

5. **`shus_smodel` は C の `round()` を直接使う**（shus_calc.c:397,399）
   モデル世帯の手取り収入 `Kw` と比例部分 `Mhirei` を作るところ。
   **所得代替率の分母**なので、Python の組込み `round()`（偶数丸め）を
   使うと看板の数字が狂う。`cnum.c_round`（0から遠い方へ）を使う。

6. **反復は「割線法14回 → 2分法」**（shus_calc.c:302）
   `n<14` は割線法（secant）、以降は 2 分法。合計 62 回まで。
   収束判定は `fabs(Cc[0][20][kend-1]/Cc[0][11][kend] - Ca) < 0.5E-13`。
"""
import math

import numpy as np

from cnum import c_round, nround
from glva import G
from setconst import (ECEDY, ECSTY, ECXA, MAX, MIN, NE, NXE, STTY, XA, XB)

# shus_calc.c:67  jj → Cc の列。jj=6,8 が 16 に、jj=7,9 が 5 に潰れる
etoc = [13, 14, 15, 6, 7, 8, 16, 5, 16, 5, 16, 5, 16, 5]


def shus_shushi(ks, ke):
    """shus_calc.c:10 収支を積み上げて年度末積立金 Cc[20] を出す。

    Cc[20][k] が Cc[20][k-1] に依存するので **k は逐次**。
    """
    is_, ie = 1, 4

    for k in range(ks, ke + 1):
        for ii in range(is_, ie + 1):
            G.Cc[ii, 4, k - STTY] = (G.Cc[ii, 5, k - STTY] + G.Cc[ii, 6, k - STTY]
                                     + G.Cc[ii, 7, k - STTY] + G.Cc[ii, 8, k - STTY])
            G.Cc[ii, 12, k - STTY] = (G.Cc[ii, 13, k - STTY]
                                      + G.Cc[ii, 14, k - STTY]
                                      + G.Cc[ii, 15, k - STTY])
            G.Cc[ii, 11, k - STTY] = (G.Cc[ii, 12, k - STTY] + G.Cc[ii, 16, k - STTY]
                                      + G.Cc[ii, 17, k - STTY]
                                      + G.Cc[ii, 18, k - STTY])
            G.Cc[ii, 3, k - STTY] = (
                G.Cc[ii, 20, k - 1 - STTY] * G.Ri[k - ECSTY]
                + (G.Cc[ii, 1, k - STTY] + G.Cc[ii, 4, k - STTY]
                   + G.Cc[ii, 9, k - STTY] + G.Cc[ii, 10, k - STTY]
                   - G.Cc[ii, 11, k - STTY]) * G.Ri2[k - ECSTY])
            G.Cc[ii, 3, k - STTY] += G.Cc[ii, 30, k - STTY] * G.Ri2[k - ECSTY]

            G.Cc[ii, 0, k - STTY] = (G.Cc[ii, 1, k - STTY] + G.Cc[ii, 3, k - STTY]
                                     + G.Cc[ii, 4, k - STTY] + G.Cc[ii, 9, k - STTY]
                                     + G.Cc[ii, 10, k - STTY])
            G.Cc[ii, 0, k - STTY] += G.Cc[ii, 30, k - STTY]
            G.Cc[ii, 19, k - STTY] = G.Cc[ii, 0, k - STTY] - G.Cc[ii, 11, k - STTY]

            if k > G.Kijun:
                G.Cc[ii, 20, k - STTY] = (G.Cc[ii, 20, k - 1 - STTY]
                                          + G.Cc[ii, 19, k - STTY])
            else:
                G.Cc[ii, 0, k - STTY] = 0.
                G.Cc[ii, 3, k - STTY] = 0.
                G.Cc[ii, 19, k - STTY] = 0.

            # 4制度合計。ii==1 は代入、ii>=2 は加算（shus_calc.c:40）
            if ii == 1:
                G.Cc[0, 0, k - STTY] = G.Cc[ii, 0, k - STTY]
                G.Cc[0, 3, k - STTY] = G.Cc[ii, 3, k - STTY]
                G.Cc[0, 4, k - STTY] = G.Cc[ii, 4, k - STTY]
                G.Cc[0, 11, k - STTY] = G.Cc[ii, 11, k - STTY]
                G.Cc[0, 12, k - STTY] = G.Cc[ii, 12, k - STTY]
                G.Cc[0, 19, k - STTY] = G.Cc[ii, 19, k - STTY]
                G.Cc[0, 20, k - STTY] = G.Cc[ii, 20, k - STTY]
            else:
                G.Cc[0, 0, k - STTY] += G.Cc[ii, 0, k - STTY]
                G.Cc[0, 3, k - STTY] += G.Cc[ii, 3, k - STTY]
                G.Cc[0, 4, k - STTY] += G.Cc[ii, 4, k - STTY]
                G.Cc[0, 11, k - STTY] += G.Cc[ii, 11, k - STTY]
                G.Cc[0, 12, k - STTY] += G.Cc[ii, 12, k - STTY]
                G.Cc[0, 19, k - STTY] += G.Cc[ii, 19, k - STTY]
                G.Cc[0, 20, k - STTY] += G.Cc[ii, 20, k - STTY]


def shus_ave(ks, ke, calhh, calhp):
    """shus_calc.c:63 年齢別の給付を年度内平均（2:6:4 の加重）に直す。

    `Touitu==0` と `Touitu>=1` で参照する調整率が違う（前者は Escutrrt、
    後者は Escutrrh）。原本は同じループを2つ書いているので、移植でも
    分岐を残して式を別々に書いてある。
    """
    is_, ie = 0, 4

    use_h = (G.Touitu >= 1)      # 調整期間の一致では Escutrrh を使う

    for ii in range(is_, ie + 1):
        for jj in range(0, 8):
            if calhh <= 0 and (jj == 0 or jj == 3):
                continue
            if calhp <= 0 and (jj == 1 or jj == 2 or jj >= 4):
                continue
            for k in range(ks, ke + 1):
                G.Cc[ii, etoc[jj], k - STTY] = 0.

        if ii == 0:
            continue

        for jj in range(0, 10):
            if calhh <= 0 and (jj == 0 or jj == 3):
                continue
            if calhp <= 0 and (jj == 1 or jj == 2 or jj >= 4):
                continue
            for k in range(ks, ke + 1):
                # 【重要】0 から溜めて最後に足すのではなく、**今の値から**
                # 溜める。etoc で jj=6 と jj=8 が同じ列 16 に、jj=7 と jj=9 が
                # 同じ列 5 に入るので、2回目の jj は前の合計の上に積まれる。
                # 0 から溜めて後で足すと丸めが変わる。
                acc = float(G.Cc[ii, etoc[jj], k - STTY])
                for x in range(66, XB + 1):
                    dx = 67 if (jj == 2 or jj == 8 or jj == 9) else x

                    if jj == 0 or jj == 3:
                        riv = (G.Krb[k - ECSTY, dx - ECXA]
                               * (G.Escutrrh[k - ECSTY, dx - ECXA]
                                  / G.Escutrrh[k - 1 - ECSTY, dx - 1 - ECXA]))
                        bpre = (G.E3dxb[ii, jj, k - 1 - STTY, x - 1]
                                * G.Escutrrh[k - 1 - ECSTY, dx - 1 - ECXA])
                        bend = (G.E3dxb[ii, jj, k - STTY, x]
                                * G.Escutrrh[k - ECSTY, dx - ECXA])
                    elif jj == 1 or jj == 2 or jj == 4 or jj == 5:
                        S = G.Escutrrh if use_h else G.Escutrrt
                        riv = (G.Kra[k - ECSTY, dx - ECXA]
                               * (S[k - ECSTY, dx - ECXA]
                                  / S[k - 1 - ECSTY, dx - 1 - ECXA]))
                        bpre = (G.E3dxb[ii, jj, k - 1 - STTY, x - 1]
                                * S[k - 1 - ECSTY, dx - 1 - ECXA])
                        bend = (G.E3dxb[ii, jj, k - STTY, x]
                                * S[k - ECSTY, dx - ECXA])
                    else:            # jj == 6, 7, 8, 9
                        S = G.Escutrrh if use_h else G.Escutrrt
                        riv = (G.Kra[k - ECSTY, dx - ECXA]
                               * (S[k - ECSTY, dx - ECXA]
                                  / S[k - 1 - ECSTY, dx - 1 - ECXA]))
                        bpre = (G.E3dxb[ii, jj, k - STTY, x - 1]
                                * S[k - 1 - ECSTY, dx - 1 - ECXA])
                        bend = (G.E3dxb[ii, jj + 4, k - STTY, x]
                                * S[k - ECSTY, dx - ECXA])

                    if G.Flg_matsu == 0:
                        acc += (bpre * 2. + bpre * riv * 6. + bend * 4.) / 12.

                G.Cc[ii, etoc[jj], k - STTY] = acc

                if jj <= 2:
                    G.Cc[ii, etoc[jj], k - STTY] *= G.nendohosei

        for jj in range(0, 8):
            if calhh <= 0 and (jj == 0 or jj == 3):
                continue
            if calhp <= 0 and (jj == 1 or jj == 2 or jj >= 4):
                continue
            for k in range(ks, ke + 1):
                G.Cc[0, etoc[jj], k - STTY] += G.Cc[ii, etoc[jj], k - STTY]


def shus_calc0():
    """shus_calc.c:180 調整なしの収支を1回だけ出す。"""
    shus_ave(G.Ks + 1, G.Ke, 1, 1)
    shus_shushi(G.Ks + 1, G.Ke)


def shus_calc8():
    """shus_calc.c:187 有限均衡になる調整期間を解く。

    手順は2段。
      1. 調整終了年度 kn を整数で探す（年度を1つ進めるごとに収支を解き直し、
         均衡終了年度 kend の積立金が正に転じたところで止める）
      2. その年度の調整率を割線法14回＋2分法で詰める（合計62回まで）

    戻り値は 0 が成功、1 が失敗（原本と同じ）。
    """
    from main import print_number

    ii = 0
    k_jisseki = 24

    kend = _atoi(G.Cutrfile3) + 100      # 20 + 100 = 120（2120年度）
    kn = kend + 1

    rh = np.zeros((NE, NXE), dtype=np.float64)     # double rh[129][56]
    rrh_max = np.zeros(NXE, dtype=np.float64)
    rrh_min = np.zeros(NXE, dtype=np.float64)

    # ---- 毎年の名目下限つき調整率 rh と、特別調整率 Tokutyo ----
    for k in range(5, G.Ke + 1):
        for x in range(ECXA, XB + 1):
            if x < 68:
                dx = 67
                dcutr = MAX(0.0, float(G.Scutrk1[k - ECSTY]))
            else:
                dx = x
                dcutr = MAX(0.0, float(G.Scutrk1[k - ECSTY]))

            if ((k >= G.Kmakuro_Yr and G.Flg_Dmakuro != 1)
                    or (G.Flg_Dmakuro == 1 and k <= G.Dmakuro_Yr)):
                dcutr = ((1.0 + dcutr)
                         / G.Tokutyo[k - 1 - ECSTY,
                                     MAX(ECXA, x - 1) - ECXA] - 1.0)

            if G.Flg_Dmakuro != 1 or k < G.Dmakuro_Yr:
                rh[k - ECSTY, x - ECXA] = 1.0 + MAX(
                    0.0, MIN(dcutr, float(G.Krb[k - ECSTY, dx - ECXA]) - 1.0))
                if k == 14 and x <= 76:
                    rh[k - ECSTY, x - ECXA] = nround(0.978 / 0.9761, 3)
            else:
                rh[k - ECSTY, x - ECXA] = 1.0 + MAX(0.0, dcutr)

            if k >= G.Kmakuro_Yr:
                G.Tokutyo[k - ECSTY, x - ECXA] = (rh[k - ECSTY, x - ECXA]
                                                  / (1.0 + dcutr))
                if k == 23:
                    G.Tokutyo[k - ECSTY, x - ECXA] = 1.0
                if k == 24:
                    G.Tokutyo[k - ECSTY, x - ECXA] = 1.0

                t = float(G.Tokutyo[k - ECSTY, x - ECXA])
                if t < -0. or t > 1.:
                    print(f"特別調整率エラー x={x}, k={k}, {t:.0f}")
                    raise SystemExit(1)

            if k == 23:
                rh[k - ECSTY, x - ECXA] = 1.0 / 0.994
            if k == 24:
                rh[k - ECSTY, x - ECXA] = 1.0 / 0.996

            if G.Flg_Kmakuro == 1:
                if k >= G.Kmakuro_Yr2:
                    G.Tokutyo[k - ECSTY, x - ECXA] = 1.0

        # 基準年度までは調整なし、以降はコホートを1つずらして持ち越す
        if k <= G.Kijun:
            G.Escutrrh[k - ECSTY, XA - 1 - ECXA] = 1
            for x in range(XA, XB + 1):
                G.Escutrrh[k - ECSTY, x - ECXA] = 1
        else:
            G.Escutrrh[k - ECSTY, XA - 1 - ECXA] = \
                G.Escutrrh[k - 1 - ECSTY, XA - 1 - ECXA]
            for x in range(XA, XB + 1):
                G.Escutrrh[k - ECSTY, x - ECXA] = \
                    G.Escutrrh[k - 1 - ECSTY, x - 1 - ECXA]

        for x in range(XA - 1, XB + 1):
            G.Escutrrt[k - ECSTY, x - ECXA] = G.Scutrrki[k - ECSTY, x - ECXA]

    shus_ave(G.Kijun, G.Ke, 1, 1)
    shus_shushi(G.Kijun + 1, G.Ke)
    f0 = 0.0
    f1 = (float(G.Cc[ii, 20, kend - 1 - STTY])
          - float(G.Cc[ii, 11, kend - STTY]) * G.Ca)

    # ---- 1段目: 調整終了年度を整数で探す ----
    flg_end = 1
    k = G.Kijun + 1
    while k < G.Ke and flg_end > 0:
        G.Escutrrh[k - ECSTY, XA - 1 - ECXA] = (
            G.Escutrrh[k - 1 - ECSTY, XA - 1 - ECXA] / rh[k - ECSTY, XA - 1 - ECXA])
        for x in range(XA, XB + 1):
            G.Escutrrh[k - ECSTY, x - ECXA] = (
                G.Escutrrh[k - 1 - ECSTY, x - 1 - ECXA] / rh[k - ECSTY, x - ECXA])
        for kk in range(k + 1, G.Ke + 1):
            G.Escutrrh[kk - ECSTY, XA - 1 - ECXA] = \
                G.Escutrrh[kk - 1 - ECSTY, XA - 1 - ECXA]
            for x in range(XA, XB + 1):
                G.Escutrrh[kk - ECSTY, x - ECXA] = \
                    G.Escutrrh[kk - 1 - ECSTY, x - 1 - ECXA]

        shus_ave(k, G.Ke, 1, 1)
        shus_shushi(k, G.Ke)
        f0 = f1
        f1 = (float(G.Cc[ii, 20, kend - 1 - STTY])
              - float(G.Cc[ii, 11, kend - STTY]) * G.Ca)
        if f1 >= 0.0 and k >= k_jisseki:
            kn = k
            flg_end = 0
        k += 1

    if kn > kend or flg_end > 0:
        print("最終年度まで調整しても均衡できませんでした")
        return 1

    for x in range(XA - 1, XB + 1):
        rrh_max[x - ECXA] = G.Escutrrh[kn - ECSTY, x - ECXA]
        rrh_min[x - ECXA] = G.Escutrrh[kn - 1 - ECSTY,
                                       MAX(x - 1, XA - 1) - ECXA]

    # ---- 2段目: その年度の調整率を詰める（割線法14回→2分法） ----
    flg_end = 1 if kn > k_jisseki else 0
    r0, r1 = 0.0, 1.0
    n = 0
    while n < 62 and flg_end > 0:
        print(f"{kn:2d}年度{n + 1:2d}回目の反復計算 ", end="")
        if n < 14:
            if f1 == f0:
                print("（エラー）分母がゼロになり発散しています")
            r = r1 - f1 * (r1 - r0) / (f1 - f0)
        else:
            r = (r1 + r0) / 2.0
            print("<2分法>", end="")

        for x in range(XA - 1, XB + 1):
            G.Escutrrh[kn - ECSTY, x - ECXA] = (rrh_min[x - ECXA] * (1.0 - r)
                                                + rrh_max[x - ECXA] * r)
        for kk in range(kn + 1, G.Ke + 1):
            G.Escutrrh[kk - ECSTY, XA - 1 - ECXA] = \
                G.Escutrrh[kk - 1 - ECSTY, XA - 1 - ECXA]
            for x in range(XA, XB + 1):
                G.Escutrrh[kk - ECSTY, x - ECXA] = \
                    G.Escutrrh[kk - 1 - ECSTY, x - 1 - ECXA]

        shus_ave(kn, G.Ke, 1, 1)
        shus_shushi(kn, G.Ke)
        f = (float(G.Cc[ii, 20, kend - 1 - STTY])
             - float(G.Cc[ii, 11, kend - STTY]) * G.Ca)
        print(f"r = {r:15.13f} ({r1 - r0:9.7f}), f = {f:f}")

        if abs(float(G.Cc[ii, 20, kend - 1 - STTY])
               / float(G.Cc[ii, 11, kend - STTY]) - G.Ca) < 0.5E-13:
            flg_end = 0
        elif f * f0 > 0.0:
            r0 = r
            f0 = f
        else:
            r1 = r
            f1 = f
        n += 1

    if flg_end > 0:
        print("収束しませんでした")
        return 1

    if G.Touitu >= 1:
        for k in range(5, G.Ke + 1):
            for x in range(XA - 1, XB + 1):
                G.Escutrrt[k - ECSTY, x - ECXA] = G.Escutrrh[k - ECSTY, x - ECXA]

    print_number()
    print(" 最終代替率")

    dtemp = ((float(G.Mhirei[G.Ke - STTY, 0])
              * float(G.Escutrrh[G.Ke - ECSTY, 67 - ECXA])
              + float(G.Mkiso[G.Ke - STTY])
              * float(G.Escutrrt[G.Ke - ECSTY, 67 - ECXA]))
             / float(G.Kw[G.Ke - STTY, 0]) * 100.)
    print(f"  一元化モデル：{dtemp:.13f} ")

    dtemp = (float(G.Mhirei[G.Ke - STTY, 0])
             * float(G.Escutrrh[G.Ke - ECSTY, 67 - ECXA])
             / float(G.Kw[G.Ke - STTY, 0]) * 100.)
    dtemp2 = (float(G.Mkiso[G.Ke - STTY])
              * float(G.Escutrrt[G.Ke - ECSTY, 67 - ECXA])
              / float(G.Kw[G.Ke - STTY, 0]) * 100.)
    print(f"      うち比例：{dtemp:.13f} , うち基礎：{dtemp2:.13f}")
    print(f" 最終カット率  厚年： "
          f"{1.0 - float(G.Escutrrh[kend - ECSTY, 67 - ECXA]):.14f},"
          f"      国年： "
          f"{1.0 - float(G.Escutrrt[kend - ECSTY, 67 - ECXA]):.14f}")

    return 0


def shus_calc9():
    """shus_calc.c:364 カット率をファイルから与えて収支だけ解く。"""
    from main import print_number

    print_number()
    for k in range(5, G.Ke + 1):
        for x in range(XA - 1, XB + 1):
            G.Escutrrh[k - ECSTY, x - ECXA] = G.Scutrrh[k - ECSTY, x - ECXA]
            G.Escutrrt[k - ECSTY, x - ECXA] = G.Scutrrt[k - ECSTY, x - ECXA]
    shus_ave(G.Kijun, G.Ke, 1, 1)
    shus_shushi(G.Kijun + 1, G.Ke)


def shus_smodel():
    """shus_calc.c:379 モデル世帯の賃金・手取り・年金額を作る。

    **所得代替率の分母（Kw）がここで決まる。** `round()` は C99 の
    「0 から遠い方へ」でなければならない（`cnum.c_round`）。
    Python の組込み `round()` は偶数丸めなので使えない。
    """
    mdlk = 24
    kasho = 0.813
    mihanei = 0.985

    G.W[mdlk - STTY, 0] = 455000.
    G.W[mdlk - STTY, 1] = 443000.
    G.W[mdlk - STTY, 2] = 580000.
    G.W[mdlk - STTY, 3] = 174000.
    G.W[mdlk - STTY, 4] = 305000.

    G.Mkiso[mdlk - STTY] = 136000. * mihanei / 0.994 / 0.996

    for i in range(0, 5):
        G.Kw[mdlk - STTY, i] = c_round(float(G.W[mdlk - STTY, i]) * kasho)
        G.Mhirei[mdlk - STTY, i] = (
            c_round(float(G.W[mdlk - STTY, i]) * 5.481E-3 * 0.926 * 40.)
            / 0.994 / 0.996)

    for k in range(mdlk + 1, G.Ke + 1):
        if G.kakusa == 2:
            for i in range(0, 5):
                G.W[k - STTY, i] = ((1.0 + G.H[k - 1 - ECSTY])
                                    * G.W[k - 1 - STTY, i])

        for i in range(0, 5):
            G.Kw[k - STTY, i] = (
                G.Kw[k - 1 - STTY, i] * G.W[k - STTY, i] / G.W[k - 1 - STTY, i]
                * (0.91 - G.Prema[1, k - 1 - STTY] / 2.)
                / (0.91 - G.Prema[1, k - 2 - STTY] / 2.))
            G.Mhirei[k - STTY, i] = (G.Mhirei[k - 1 - STTY, i]
                                     * G.Kw[k - STTY, i] / G.Kw[k - 1 - STTY, i])
        G.Mkiso[k - STTY] = (G.Mkiso[k - 1 - STTY] * (1.0 + G.H[k - 1 - ECSTY])
                             * (0.91 - G.Prema[1, k - 1 - STTY] / 2.)
                             / (0.91 - G.Prema[1, k - 2 - STTY] / 2.))


def _atoi(s):
    """C の atoi。"""
    i = 0
    n = len(s)
    while i < n and s[i] in " \t\n\r\f\v":
        i += 1
    j = i
    if j < n and s[j] in "+-":
        j += 1
    k = j
    while k < n and s[k].isdigit() and s[k].isascii():
        k += 1
    if k == j:
        return 0
    return int(s[i:k])
