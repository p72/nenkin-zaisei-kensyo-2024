# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/shus.c の忠実移植
===============================================
⑤の本体。給付を年齢別に集約し、保険料率を作り、収支の前提を並べる。

呼び出し順（shus.c:30）は結果に効くので崩せない。
出力関数（shus_out.c / shus_fullout.c）も `Cc[21][26][27][28]` や `Ukyu` を
書き換えるが、`shus_calc8` が読むのは `Cc[20]` と `Cc[11]` だけなので、
計算部分だけを切り出して照合できる。

原本の癖をそのまま残しているところ
----------------------------------
1. **67歳未満は 66 歳に寄せて集約する**（shus.c:77）
   `if(x<67){ dx = 66; }` なので、x=63,64,65,66 の4つが dx=66 に**足し込まれる**。
   x>=67 は1対1。つまり dx=66 だけが4項の総和になる。足す順序は x の昇順。

2. **`Cc[ii][17]`（事務費）は2004年度以降を比で延ばす**（shus.c:363）
   実績値を入れたあと、`zan_jimu==0` なら k>=25 を
   `Cc[17][24] / Ap[0][24] * Ap[0][k] * Id_Cid_2[k]` で置き換える。
   実績値の代入が先で、そのあと上書きされる順序に意味がある。

3. **保険料率の積み上げは 2004 年度から**（shus.c:138）
   `for(k=4; k<=ENDY; k++){ dtemp1 += 0.00354; ... if(k>=STTY) Prema[...] }`
   加算は k=4 から始まるが、配列に入れるのは k>=STTY（2009年度）から。
   ループの開始年度を変えると値が変わる。

4. **`Premb` は前年度と当年度の加重平均**（shus.c:169）
   制度ごとに (dtemp1, dtemp2) = (6,6) / (5,7) / (1,11) の重みで 12 で割る。
   厚年と私学（ii=1,5）は 6:6、国共済・地共済（ii=2,3）は 5:7、
   旧農林（ii=4）は 1:11。

5. **適用拡大の年度だけ被保険者数を足し込む**（shus.c:279）
   `if(k==Part_Yr2 || k==Part_Yr3)` のときに `A += Apart` のように
   **その年度だけ**加算する。年度をまたいで累積するわけではない。
"""
from glva import G
from setconst import ECSTY, ENDY, MIN, STTY, XA, XB
from cntl import ii2psd, ii2usd


def shus_init():
    """shus.c:64 給付を年齢別（66歳以上）に集約して E3dxb を作る。"""
    is_, ie = 1, 4

    for ii in range(is_, ie + 1):
        usd = ii2usd(ii)

        for k in range(G.Ks, G.Ke + 1):
            for x in range(XA - 1, XB + 1):
                dx = 66 if x < 67 else x

                G.E3dxb[ii, 0, k - STTY, dx] += G.D3bxtp[ii, 0, 0, 1, k - STTY, x]
                G.E3dxb[ii, 1, k - STTY, dx] += (
                    G.D3bxtp[ii, 0, 0, 3, k - STTY, x]
                    + G.D3bxtp[ii, 0, 0, 4, k - STTY, x]
                    + G.D3bxtp[ii, 0, 0, 6, k - STTY, x]
                    + G.D3bxtp[ii, 0, 0, 7, k - STTY, x])
                G.E3dxb[ii, 2, k - STTY, dx] += G.D3bxtp[ii, 0, 0, 5, k - STTY, x]
                G.E3dxb[ii, 3, k - STTY, dx] += G.Kfpbxtp[ii, 0, 0, 1, k - STTY, x]
                G.E3dxb[ii, 4, k - STTY, dx] += G.Kfpbxtp[ii, 0, 0, 2, k - STTY, x]
                G.E3dxb[ii, 5, k - STTY, dx] += G.Kfpbxtp[ii, 0, 0, 7, k - STTY, x]

                G.E3dxb[ii, 6, k - STTY, dx] += G.Kyosdx[0, usd, 0, k - STTY, x]
                G.E3dxb[ii, 7, k - STTY, dx] += G.Kfkyosdx[0, usd, 0, k - STTY, x]
                G.E3dxb[ii, 8, k - STTY, dx] += G.Kyosdx[1, usd, 0, k - STTY, x]
                G.E3dxb[ii, 9, k - STTY, dx] += G.Kfkyosdx[1, usd, 0, k - STTY, x]
                G.E3dxb[ii, 10, k - STTY, dx] += G.Kyosdx[0, usd, 1, k - STTY, x]
                G.E3dxb[ii, 11, k - STTY, dx] += G.Kfkyosdx[0, usd, 1, k - STTY, x]
                G.E3dxb[ii, 12, k - STTY, dx] += G.Kyosdx[1, usd, 1, k - STTY, x]
                G.E3dxb[ii, 13, k - STTY, dx] += G.Kfkyosdx[1, usd, 1, k - STTY, x]

    # 調整期間の一致では、国年側の拠出金（ss=7,8）も厚年に足し込む
    if G.Touitu >= 1:
        for k in range(G.Ks, G.Ke + 1):
            for x in range(XA - 1, XB + 1):
                dx = 66 if x < 67 else x
                G.E3dxb[1, 6, k - STTY, dx] += (
                    G.Kyosdx[0, 7, 0, k - STTY, x] + G.Kyosdx[0, 8, 0, k - STTY, x])
                G.E3dxb[1, 7, k - STTY, dx] += (
                    G.Kfkyosdx[0, 7, 0, k - STTY, x] + G.Kfkyosdx[0, 8, 0, k - STTY, x])
                G.E3dxb[1, 8, k - STTY, dx] += (
                    G.Kyosdx[1, 7, 0, k - STTY, x] + G.Kyosdx[1, 8, 0, k - STTY, x])
                G.E3dxb[1, 9, k - STTY, dx] += (
                    G.Kfkyosdx[1, 7, 0, k - STTY, x] + G.Kfkyosdx[1, 8, 0, k - STTY, x])
                G.E3dxb[1, 10, k - STTY, dx] += (
                    G.Kyosdx[0, 7, 1, k - STTY, x] + G.Kyosdx[0, 8, 1, k - STTY, x])
                G.E3dxb[1, 11, k - STTY, dx] += (
                    G.Kfkyosdx[0, 7, 1, k - STTY, x] + G.Kfkyosdx[0, 8, 1, k - STTY, x])
                G.E3dxb[1, 12, k - STTY, dx] += (
                    G.Kyosdx[1, 7, 1, k - STTY, x] + G.Kyosdx[1, 8, 1, k - STTY, x])
                G.E3dxb[1, 13, k - STTY, dx] += (
                    G.Kfkyosdx[1, 7, 1, k - STTY, x] + G.Kfkyosdx[1, 8, 1, k - STTY, x])

            G.E3dxb[1, 2, k - STTY, 66] += (G.Kokusyushi[9, k - STTY] / G.nendohosei)

    # 4制度合計（ii=0）。ii の昇順に足す（shus.c:117）
    for ii in range(1, 5):
        for jj in range(0, 14):
            for k in range(G.Ks, G.Ke + 1):
                for x in range(66, XB + 1):
                    G.E3dxb[0, jj, k - STTY, x] += G.E3dxb[ii, jj, k - STTY, x]


def init_premium():
    """shus.c:128 保険料率 Prema と、年度内平均の Premb を作る。"""
    if G.Ks < 10 or G.Ks < STTY:
        print("【警告】保険料率が正しくセットできていません")

    # 厚年（ii=1）と私学（ii=5）。加算は k=4 から、代入は k>=STTY から
    dtemp1 = 0.1358
    dtemp2 = 0.1496
    for k in range(4, ENDY + 1):
        dtemp1 += 0.00354
        dtemp2 += 0.00248
        if k >= STTY:
            G.Prema[1, k - STTY] = MIN(0.183, dtemp1)
            G.Prema[5, k - STTY] = MIN(0.183, dtemp2)

    # 国共済・地共済（ii=2,3）と旧農林（ii=4）。加算は k=10 から
    dtemp1 = 0.15154
    dtemp2 = 0.1223
    for k in range(10, ENDY + 1):
        dtemp1 += 0.00354
        dtemp2 += 0.00354
        if k >= STTY:
            G.Prema[2, k - STTY] = MIN(0.183, dtemp1)
            G.Prema[3, k - STTY] = MIN(0.183, dtemp1)
            G.Prema[4, k - STTY] = MIN(0.183, dtemp2)

    # 年度内平均。制度ごとに前年度:当年度の重みが違う
    for ii in range(1, 6):
        if ii == 1 or ii == 5:
            dtemp1, dtemp2 = 6.0, 6.0
        elif ii == 2 or ii == 3:
            dtemp1, dtemp2 = 5.0, 7.0
        elif ii == 4:
            dtemp1, dtemp2 = 1.0, 11.0
        for k in range(G.Ks + 1, ENDY + 1):
            G.Premb[ii, k - STTY] = (
                (dtemp1 * G.Prema[ii, k - 1 - STTY]
                 + dtemp2 * G.Prema[ii, k - STTY]) / 12.)


def shus_premium():
    """shus.c:175 保険料収入 Cc[1] と、報酬総額 Cc[23][24][25] を作る。"""
    is_, ie = 1, 4

    # ---- 標準報酬上限の見直し（オプション。shus.c:184） ----
    if G.Flg_Houjou >= 1:
        for ii in range(is_, ie + 1):
            se = 3 if ii == 1 else 2
            for s in range(1, se + 1):
                for k in range(G.Ks, G.Ke + 1):
                    if k == G.Houjou_Yr:
                        # 施行年度は半年分だけ効かせる
                        r = (G.Houjou_R1 if (s == 1 or s == 3) else G.Houjou_R2)
                        f = 1.0 + (r - 1.0) / 2.0
                        G.An[ii, s, k - STTY] *= f
                        G.Aniku[ii, s, k - STTY] *= f
                        G.A[ii, s, k - STTY] *= f
                        G.Aiku[ii, s, k - STTY] *= f
                        if k == G.Part_Yr2 or k == G.Part_Yr3:
                            G.Anpart[s, k - STTY] *= r
                            G.Anikupart[s, k - STTY] *= r
                            G.Apart[s, k - STTY] *= r
                            G.Aikupart[s, k - STTY] *= r
                    elif k > G.Houjou_Yr:
                        r = (G.Houjou_R1 if (s == 1 or s == 3) else G.Houjou_R2)
                        G.An[ii, s, k - STTY] *= r
                        G.Aniku[ii, s, k - STTY] *= r
                        G.A[ii, s, k - STTY] *= r
                        G.Aiku[ii, s, k - STTY] *= r
                        if k == G.Part_Yr2 or k == G.Part_Yr3:
                            G.Anpart[s, k - STTY] *= r
                            G.Anikupart[s, k - STTY] *= r
                            G.Apart[s, k - STTY] *= r
                            G.Aikupart[s, k - STTY] *= r

            for k in range(G.Ks, G.Ke + 1):
                G.An[ii, 0, k - STTY] = (G.An[ii, 1, k - STTY]
                                         + G.An[ii, 2, k - STTY]
                                         + G.An[ii, 3, k - STTY])
                G.Aniku[ii, 0, k - STTY] = (G.Aniku[ii, 1, k - STTY]
                                            + G.Aniku[ii, 2, k - STTY]
                                            + G.Aniku[ii, 3, k - STTY])
                G.A[ii, 0, k - STTY] = (G.A[ii, 1, k - STTY]
                                        + G.A[ii, 2, k - STTY]
                                        + G.A[ii, 3, k - STTY])
                G.Aiku[ii, 0, k - STTY] = (G.Aiku[ii, 1, k - STTY]
                                           + G.Aiku[ii, 2, k - STTY]
                                           + G.Aiku[ii, 3, k - STTY])
                G.Anpart[0, k - STTY] = (G.Anpart[1, k - STTY]
                                         + G.Anpart[2, k - STTY]
                                         + G.Anpart[3, k - STTY])
                G.Anikupart[0, k - STTY] = (G.Anikupart[1, k - STTY]
                                            + G.Anikupart[2, k - STTY]
                                            + G.Anikupart[3, k - STTY])
                G.Apart[0, k - STTY] = (G.Apart[1, k - STTY]
                                        + G.Apart[2, k - STTY]
                                        + G.Apart[3, k - STTY])
                G.Aikupart[0, k - STTY] = (G.Aikupart[1, k - STTY]
                                           + G.Aikupart[2, k - STTY]
                                           + G.Aikupart[3, k - STTY])

    # ---- 保険料収入（shus.c:257） ----
    prem = [0.0, 0.0, 0.0]
    for ii in range(is_, ie + 1):
        for k in range(G.Ks + 1, G.Ke + 1):
            if ii == 1:
                # 第1号厚生年金。第3号（私学）の上乗せ分を分けて持つ
                prem[1] = G.An[ii, 0, k - STTY] * G.Premb[1, k - STTY]
                prem[2] = G.An[ii, 3, k - STTY] * (G.Premb[5, k - STTY]
                                                   - G.Premb[1, k - STTY])

                G.Cc[ii, 1, k - STTY] = prem[1] + prem[2]
                G.Cc[ii, 2, k - STTY] = prem[2]

                if k == G.Part_Yr2 or k == G.Part_Yr3:
                    dtemp = G.Cbm_Pt1
                    if dtemp <= 6.0:
                        dtemp = G.Prema[1, k - STTY]
                    else:
                        dtemp = ((dtemp - 6.0) * G.Prema[1, k - 1 - STTY]
                                 + 6.0 * G.Prema[1, k - STTY]) / dtemp

                    G.Cc[ii, 22, k - STTY] = G.Anpart[0, k - STTY] * dtemp
                    G.Cc[ii, 1, k - STTY] += G.Cc[ii, 22, k - STTY]
                    for s in range(0, 4):
                        G.A[ii, s, k - STTY] += G.Apart[s, k - STTY]
                        G.Aiku[ii, s, k - STTY] += G.Aikupart[s, k - STTY]
                        G.A60[ii, s, k - STTY] += G.A60part[s, k - STTY]
                        G.A65[ii, s, k - STTY] += G.A65part[s, k - STTY]
                        G.A70[ii, s, k - STTY] += G.A70part[s, k - STTY]

                        G.An[ii, s, k - STTY] += G.Anpart[s, k - STTY]
                        G.Aniku[ii, s, k - STTY] += G.Anikupart[s, k - STTY]
            else:
                G.Cc[ii, 1, k - STTY] = (G.An[ii, 0, k - STTY]
                                         * G.Premb[ii2psd(ii), k - STTY])

            G.Cc[ii, 23, k - STTY] = (G.A[ii, 0, k - STTY]
                                      + G.Aiku[ii, 0, k - STTY])
            G.Cc[ii, 24, k - STTY] = G.An[ii, 0, k - STTY]
            G.Cc[ii, 25, k - STTY] = G.Aniku[ii, 0, k - STTY]

    if G.Touitu >= 1:
        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[1, 1, k - STTY] += G.Kokusyushi[0, k - STTY]

    # 4制度合計（shus.c:306）
    for ii in range(1, 5):
        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[0, 1, k - STTY] += G.Cc[ii, 1, k - STTY]
            if ii == 1:
                G.Cc[0, 2, k - STTY] += G.Cc[ii, 2, k - STTY]
            if (k == G.Part_Yr2 or k == G.Part_Yr3) and ii == 1:
                G.Cc[0, 22, k - STTY] += G.Cc[ii, 22, k - STTY]
            G.Cc[0, 23, k - STTY] += G.Cc[ii, 23, k - STTY]
            G.Cc[0, 24, k - STTY] += G.Cc[ii, 24, k - STTY]
            G.Cc[0, 25, k - STTY] += G.Cc[ii, 25, k - STTY]


def shus_fukkjn():
    """shus.c:322 積立金の期首残高、納付金、事務費を並べる。"""
    is_, ie = 1, 4

    for ii in range(is_, ie + 1):
        psd = ii2psd(ii)

        # 2022年度末の積立金（実績）。単位は円
        if G.zan_fund == 0:
            if G.Kijun == 22:
                G.Cc[1, 20, 22 - STTY] = 2088227.0E+8
                G.Cc[2, 20, 22 - STTY] = 84763.0E+8
                G.Cc[3, 20, 22 - STTY] = 250513.0E+8
                G.Cc[4, 20, 22 - STTY] = 31275.0E+8

        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[ii, 9, k - STTY] = 0
            G.Cc[ii, 10, k - STTY] = G.Nofu[psd, k - STTY]

            # 事務費の実績値
            if ii == 1:
                if k == 21:
                    G.Cc[ii, 17, k - STTY] = 1787.94E+8
                if k == 22:
                    G.Cc[ii, 17, k - STTY] = 1698.49E+8
                if k == 23:
                    G.Cc[ii, 17, k - STTY] = 2000.00E+8
                if k >= 24:
                    G.Cc[ii, 17, k - STTY] = 2300.00E+8
            elif ii == 2:
                if k == 21:
                    G.Cc[ii, 17, k - STTY] = 48.95E+8
                if k >= 22:
                    G.Cc[ii, 17, k - STTY] = 52.56E+8
            elif ii == 3:
                if k == 21:
                    G.Cc[ii, 17, k - STTY] = 73.59E+8
                if k >= 22:
                    G.Cc[ii, 17, k - STTY] = 75.30E+8
            elif ii == 4:
                if k == 21:
                    G.Cc[ii, 17, k - STTY] = 26.93E+8
                if k >= 22:
                    G.Cc[ii, 17, k - STTY] = 29.49E+8

            # 2025年度以降は被保険者数と物価で延ばす（実績値の代入より後）
            if G.zan_jimu == 0:
                if k >= 25:
                    G.Cc[ii, 17, k - STTY] = (
                        G.Cc[ii, 17, 24 - STTY] / G.Ap[ii, 0, 24 - STTY]
                        * G.Ap[ii, 0, k - STTY] * G.Id_Cid_2[k - ECSTY])
            G.Cc[ii, 18, k - STTY] = 0

    if G.Touitu >= 1:
        if G.Kijun == 21:
            G.Np[23, 21 - STTY] = 121176.0E+8
            G.Cc[1, 20, 21 - STTY] += 121176.0E+8
        if G.Kijun == 22:
            G.Np[23, 22 - STTY] = 124290.0E+8
            G.Cc[1, 20, 22 - STTY] += 124290.0E+8

        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[1, 9, k - STTY] += (G.Kokusyushi[1, k - STTY]
                                     + G.Kokusyushi[2, k - STTY])
            G.Cc[1, 10, k - STTY] += G.Kokusyushi[3, k - STTY]
            G.Cc[1, 17, k - STTY] += (G.Kokusyushi[5, k - STTY]
                                      + G.Kokusyushi[6, k - STTY]
                                      + G.Kokusyushi[7, k - STTY]
                                      + G.Kokusyushi[8, k - STTY])

    for ii in range(1, 5):
        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[0, 9, k - STTY] += G.Cc[ii, 9, k - STTY]
            G.Cc[0, 10, k - STTY] += G.Cc[ii, 10, k - STTY]
            G.Cc[0, 17, k - STTY] += G.Cc[ii, 17, k - STTY]
            if ii == 1:
                G.Cc[0, 20, k - STTY] = G.Cc[ii, 20, k - STTY]
            G.Cc[ii, 30, k - STTY] = G.Tumazumi[ii, k - STTY]
            G.Cc[0, 30, k - STTY] += G.Tumazumi[ii, k - STTY]

    if G.Touitu >= 1:
        for k in range(G.Ks + 1, G.Ke + 1):
            G.Cc[1, 30, k - STTY] += G.Kokusyushi[4, k - STTY]
            G.Cc[0, 30, k - STTY] += G.Kokusyushi[4, k - STTY]


def shus_calc_only():
    """shus.c:30 shus() のうち、出力を伴わない計算部分だけ。

    差分テストで計算だけを切り出して突き合わせるための経路。
    出力関数が書き換える Cc[21][26][27][28] と Ukyu は、
    shus_calc8 が読まないのでここまでの結果には影響しない。
    """
    import shus_calc

    shus_init()
    init_premium()
    shus_calc.shus_smodel()

    shus_premium()
    shus_fukkjn()

    shus_calc.shus_calc0()

    if G.Fpset == 8:
        shus_calc.shus_calc8()

    if G.Fpset == 9:
        shus_calc.shus_calc9()


def shus():
    """shus.c:30 void shus(void) の忠実移植。

    呼び出し順は結果に効くので崩せない。出力関数も Cc[21][26][27][28] や
    Ukyu、Ap[0] を書き換えるので、「出力」と言いながら状態が変わる。
    """
    import shus_calc
    import shus_fullout
    import shus_out

    shus_init()
    init_premium()
    shus_calc.shus_smodel()

    shus_premium()

    shus_fukkjn()

    shus_out.shus_econ_out()
    shus_out.shus_nin_out()

    shus_calc.shus_calc0()
    shus_out.shus_shushiout(0)
    shus_fullout.shus_fullout(0)

    if G.Fpset == 8:
        shus_calc.shus_calc8()

    if G.Fpset == 9:
        shus_calc.shus_calc9()

    shus_out.shus_shushiout(1)
    shus_fullout.shus_fullout(1)

    if G.Fpset != 9:
        shus_out.shus_cutout()

    shus_out.shus_Tokutyoout()

    if G.Saimu == 0 or G.Saimu == 1 or G.Saimu == 2:
        shus_out.shus_summary()
