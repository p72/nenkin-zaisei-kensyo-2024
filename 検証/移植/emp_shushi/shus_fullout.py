# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/shus_fullout.c の忠実移植
=======================================================
給付費を給付種別×新旧×在退×種類×年齢まで分解して書き出す。
`01shushi.*` の後半（詳細収支）と `90nenbe.*`（年齢別）を作る。

局所の静的配列が大きい
----------------------
原本は関数外の `static` として持っている（shus_fullout.c:11）。

    d4x[5][4][14][8][117][116]   30,401,280 要素   243MB
    d4a[5][4][14][8][117]           262,080 要素     2MB
    d65[5][4][14][8][117]           262,080 要素     2MB
    dkof[5][3][117]                              小
    ddaik[5][117]                                小

`static` なのでゼロ初期化され、`shus_fullout(0)` と `shus_fullout(1)` の
2回の呼び出しをまたいで残る。ただし各呼び出しの先頭で ii ごとに
ゼロ埋めし直すので、実際には持ち越さない。移植でもモジュール単位で持つ。

原本の癖をそのまま残しているところ
----------------------------------
1. **`ddaik` はどこにも代入が無い**
   `shus_fullout.c:190` が「代行相当給付」として出力するが、代入する
   コードが無いので**常に 0**（static のゼロのまま）。

2. **`j==2` は入力として飛ばし、出力では合計として使う**
   累積ループは `if(j==2) continue;` で飛ばすが、`j>2` のとき
   `d4x[..][2][..] += dtemp` で j=2 に足し込んでいる。つまり j=2 は
   「j=3〜7 の合計」の置き場。

3. **`j==5`（加給）だけ年齢を 67 歳に固定**（shus_fullout.c:70）
   他は `dx = MAX(x, 67)` だが、j=5 は `67-ECXA` を直に使う。

4. **`x>=65` で `d65` に足すが、x のループは 63 から**
   つまり x=63,64 は `d4a` には入るが `d65` には入らない。

5. **`Flg_matsu==1` の枝では `dtemp` が前の値のまま残りうる**
   `if(Flg_matsu == 0){...}else if(Flg_matsu == 1){...}` で、どちらでも
   ない値なら `dtemp` が未更新のまま使われる（C の未定義寄りの挙動）。
   `Flg_matsu` は `cntl.c:221` で 0 固定なので実際には通らない。

6. **`shus_nenbeout` の出力は巨大**
   ii=0〜4 × 性別2 × 給付種別13 × 種類7 × 年度105 × 年齢53 で
   **約506万行**になる。`Nenbeex2==1`（既定）かつ `Flg_matsu==0` のときだけ
   書く。照合には使わないが、原本と同じものを出すために実装してある。
"""
import numpy as np

from glva import G
from setconst import (ECSTY as ECSTY_, ECXA as ECXA_, FLKE, FLKS, MAX, NX, NY,
                      STTY, XA, XB)

# shus_fullout.c:11 の static 配列。原本と同じくゼロ初期化で、呼び出しを
# またいで残る（ただし各呼び出しの先頭で ii ごとに埋め直す）。
_d4x = None
_d4a = None
_d65 = None
_dkof = None
_ddaik = None


def _alloc():
    """static 配列を確保する（初回だけ。243MB あるので遅延）。"""
    global _d4x, _d4a, _d65, _dkof, _ddaik
    if _d4x is None:
        _d4x = np.zeros((5, 4, 14, 8, NY, NX), dtype=np.float64)   # 243MB
        _d4a = np.zeros((5, 4, 14, 8, NY), dtype=np.float64)
        _d65 = np.zeros((5, 4, 14, 8, NY), dtype=np.float64)
        _dkof = np.zeros((5, 3, NY), dtype=np.float64)
        _ddaik = np.zeros((5, NY), dtype=np.float64)   # 代入が無いので常に 0


def shus_fullout(mode):
    """shus_fullout.c:18 詳細収支を書く。mode=0 調整前、1 調整後。"""
    _alloc()
    d4x, d4a, d65, dkof, ddaik = _d4x, _d4a, _d65, _dkof, _ddaik

    is_, ie = 0, 4

    for ii in range(is_, ie + 1):
        # ii ごとにゼロ埋め（原本 shus_fullout.c:30-47）
        d4x[ii] = 0.
        d4a[ii] = 0.
        d65[ii] = 0.
        dkof[ii] = 0.

        if ii == 0:
            continue

        se = 3 if ii == 1 else 2

        for s in range(0, se + 1):
            for i in range(0, 14):
                for j in range(1, 8):
                    if j == 2:
                        continue          # j=2 は j>2 の合計の置き場
                    for k in range(G.Ks + 1, G.Ke + 1):
                        for x in range(XA - 1, XB + 1):
                            dx = MAX(x, 67)
                            if j == 1:
                                riv = (float(G.Krb[k - ECSTY_, dx - ECXA_])
                                       * (float(G.Escutrrh[k - ECSTY_, dx - ECXA_])
                                          / float(G.Escutrrh[k - 1 - ECSTY_,
                                                             dx - 1 - ECXA_])))
                                bpre = (float(G.D3bxtp[ii, s, i, j, k - 1 - STTY, x - 1])
                                        * float(G.Escutrrh[k - 1 - ECSTY_,
                                                           dx - 1 - ECXA_]))
                                bend = (float(G.D3bxtp[ii, s, i, j, k - STTY, x])
                                        * float(G.Escutrrh[k - ECSTY_, dx - ECXA_]))
                            elif j != 5:
                                riv = (float(G.Kra[k - ECSTY_, dx - ECXA_])
                                       * (float(G.Escutrrt[k - ECSTY_, dx - ECXA_])
                                          / float(G.Escutrrt[k - 1 - ECSTY_,
                                                             dx - 1 - ECXA_])))
                                bpre = (float(G.D3bxtp[ii, s, i, j, k - 1 - STTY, x - 1])
                                        * float(G.Escutrrt[k - 1 - ECSTY_,
                                                           dx - 1 - ECXA_]))
                                bend = (float(G.D3bxtp[ii, s, i, j, k - STTY, x])
                                        * float(G.Escutrrt[k - ECSTY_, dx - ECXA_]))
                            else:
                                # j==5（加給）だけ年齢を 67 歳に固定
                                riv = (float(G.Kra[k - ECSTY_, 67 - ECXA_])
                                       * (float(G.Escutrrt[k - ECSTY_, 67 - ECXA_])
                                          / float(G.Escutrrt[k - 1 - ECSTY_,
                                                             67 - ECXA_])))
                                bpre = (float(G.D3bxtp[ii, s, i, j, k - 1 - STTY, x - 1])
                                        * float(G.Escutrrt[k - 1 - ECSTY_,
                                                           67 - ECXA_]))
                                bend = (float(G.D3bxtp[ii, s, i, j, k - STTY, x])
                                        * float(G.Escutrrt[k - ECSTY_, 67 - ECXA_]))

                            if G.Flg_matsu == 0:
                                dtemp = ((bpre * 2.0 + bpre * riv * 6.0
                                          + bend * 4.0) / 12.0
                                         * G.nendohosei / 1.0E+8)
                            elif G.Flg_matsu == 1:
                                dtemp = bend * G.nendohosei / 1.0E+8

                            d4x[ii, s, i, j, k - STTY, x] = dtemp
                            d4x[ii, s, i, 0, k - STTY, x] += dtemp
                            if j > 2:
                                d4x[ii, s, i, 2, k - STTY, x] += dtemp

                            d4a[ii, s, i, j, k - STTY] += dtemp
                            d4a[ii, s, i, 0, k - STTY] += dtemp
                            if j > 2:
                                d4a[ii, s, i, 2, k - STTY] += dtemp

                            if x >= 65:
                                d65[ii, s, i, j, k - STTY] += dtemp
                                d65[ii, s, i, 0, k - STTY] += dtemp
                                if j > 2:
                                    d65[ii, s, i, 2, k - STTY] += dtemp

                            d4x[0, s, i, j, k - STTY, x] += dtemp
                            d4x[0, s, i, 0, k - STTY, x] += dtemp
                            if j > 2:
                                d4x[0, s, i, 2, k - STTY, x] += dtemp

                            d4a[0, s, i, j, k - STTY] += dtemp
                            d4a[0, s, i, 0, k - STTY] += dtemp
                            if j > 2:
                                d4a[0, s, i, 2, k - STTY] += dtemp

                            if x >= 65:
                                d65[0, s, i, j, k - STTY] += dtemp
                                d65[0, s, i, 0, k - STTY] += dtemp
                                if j > 2:
                                    d65[0, s, i, 2, k - STTY] += dtemp

        # 基礎年金交付金（shus_fullout.c:114）
        for i in range(1, 3):
            for k in range(G.Ks + 1, G.Ke + 1):
                for x in range(XA - 1, XB + 1):
                    dx = MAX(x, 67)
                    src = G.Kofte if i == 1 else G.Kofkk
                    riv = (float(G.Kra[k - ECSTY_, dx - ECXA_])
                           * (float(G.Escutrrt[k - ECSTY_, dx - ECXA_])
                              / float(G.Escutrrt[k - 1 - ECSTY_, dx - 1 - ECXA_])))
                    bpre = (float(src[ii, 0, 0, k - 1 - STTY, x - 1])
                            * float(G.Escutrrt[k - 1 - ECSTY_, dx - 1 - ECXA_]))
                    bend = (float(src[ii, 0, 0, k - STTY, x])
                            * float(G.Escutrrt[k - ECSTY_, dx - ECXA_]))

                    if G.Flg_matsu == 0:
                        dtemp = ((bpre * 2.0 + bpre * riv * 6.0 + bend * 4.0)
                                 / 12.0 / 1.0E+8)

                    dkof[ii, i, k - STTY] += dtemp
                    dkof[ii, 0, k - STTY] += dtemp

                    dkof[0, i, k - STTY] += dtemp
                    dkof[0, 0, k - STTY] += dtemp

    # ---- 出力 ----
    for ii in range(is_, ie + 1):
        ofp = G.ofp01_shushi[ii]

        ofp.fp("\n詳細収支")
        if mode == 0:
            ofp.fp("【スライド調整前】\n")
        else:
            ofp.fp("【スライド調整後】\n")
        _fullout_header(ofp)

        for k in range(FLKS, FLKE + 1):
            ofp.fp(f"{k:3d},")
            ofp.fp(f"{float(dkof[ii, 0, k - STTY]):20.13e},"
                   f"{float(ddaik[ii, k - STTY]):20.13e},")
            ofp.fp(f"{float(d4a[ii, 0, 0, 0, k - STTY]):20.13e},")
            dtemp = 0.
            for i in range(5, 9):
                dtemp += float(d4a[ii, 0, i, 0, k - STTY])
            ofp.fp(f"{dtemp:20.13e},")
            ofp.fp(f"{float(d4a[ii, 0, 10, 0, k - STTY]):20.13e},")
            ofp.fp(f"{float(d4a[ii, 0, 12, 0, k - STTY]) + float(d4a[ii, 0, 13, 0, k - STTY]):20.13e},")
            ofp.fp(",")

            for s in range(0, 4):
                for i in range(1, 5):
                    ofp.fp(f"{float(d4a[ii, s, i, 0, k - STTY]) + float(d4a[ii, s, i + 4, 0, k - STTY]):20.13e},")
                ofp.fp(f"{float(d4a[ii, s, 9, 0, k - STTY]) + float(d4a[ii, s, 10, 0, k - STTY]):20.13e},")
                dtemp = 0.
                for i in range(11, 14):
                    dtemp += float(d4a[ii, s, i, 0, k - STTY])
                ofp.fp(f"{dtemp:20.13e},")
            for i in range(1, 5):
                ofp.fp(f"{float(d65[ii, 0, i, 0, k - STTY]) + float(d65[ii, 0, i + 4, 0, k - STTY]):20.13e},")
            ofp.fp(f"{float(d65[ii, 0, 9, 0, k - STTY]) + float(d65[ii, 0, 10, 0, k - STTY]):20.13e},")
            dtemp = 0.
            for i in range(11, 14):
                dtemp += float(d65[ii, 0, i, 0, k - STTY])
            ofp.fp(f"{dtemp:20.13e},")
            ofp.fp(",")

            for i in range(1, 5):
                ofp.fp(f"{float(d4a[ii, 0, i, 1, k - STTY]) + float(d4a[ii, 0, i + 4, 1, k - STTY]):20.13e},")
            ofp.fp(f"{float(d4a[ii, 0, 9, 1, k - STTY]) + float(d4a[ii, 0, 10, 1, k - STTY]):20.13e},")
            dtemp = 0.
            for i in range(11, 14):
                dtemp += float(d4a[ii, 0, i, 1, k - STTY])
            ofp.fp(f"{dtemp:20.13e},")
            for i in range(1, 5):
                ofp.fp(f"{float(d65[ii, 0, i, 1, k - STTY]) + float(d65[ii, 0, i + 4, 1, k - STTY]):20.13e},")
            ofp.fp(f"{float(d65[ii, 0, 9, 1, k - STTY]) + float(d65[ii, 0, 10, 1, k - STTY]):20.13e},")
            dtemp = 0.
            for i in range(11, 14):
                dtemp += float(d65[ii, 0, i, 1, k - STTY])
            ofp.fp(f"{dtemp:20.13e},")
            ofp.fp(",")

            for j in range(2, 8):
                ofp.fp(f"{float(d4a[ii, 0, 0, j, k - STTY]):20.13e},")
            for j in range(2, 8):
                ofp.fp(f"{float(d65[ii, 0, 0, j, k - STTY]):20.13e},")
            ofp.fp(",")

            for j in range(0, 8):
                for i in range(1, 14):
                    ofp.fp(f"{float(d4a[ii, 0, i, j, k - STTY]):20.13e},")

            ofp.fp("\n")
        ofp.fp("\n")

    if G.Nenbeex2 == 1:
        if G.Flg_matsu == 0:
            shus_nenbeout(mode)

    if (G.Saimu == 0 or G.Saimu == 1 or G.Saimu == 2) and mode == 1:
        for ii in range(1, 5):
            for i in range(1, 14):
                if i == 1 or i == 2 or i == 5 or i == 6:
                    j = 0
                elif i == 3 or i == 4 or i == 7 or i == 8:
                    j = 1
                elif i <= 10:
                    j = 2
                else:
                    j = 3
                for k in range(G.Ks, G.Ke + 1):
                    v = float(d4a[ii, 0, i, 0, k - STTY])
                    G.Ukyu[1, ii, j, k - STTY] += v
                    G.Ukyu[1, 0, j, k - STTY] += v


def shus_nenbeout(mode):
    """shus_fullout.c:278 年齢別の給付費を書く（約506万行）。"""
    _alloc()
    d4x = _d4x

    sei = ["0合計", "1男性", "2女性"]
    kyufus = ["0合計", "1老齢", "2障害", "3遺族"]
    newold = ["0合計", "1新法", "2旧法"]
    zaitai = ["0合計", "1退職", "2在職", "3障遺"]
    shurui = ["0合計", "1比例", "2他計", "3定額", "4経加", "5加給", "6遺加",
              "7最保"]
    i2k = [0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 3]
    i2n = [0, 1, 1, 1, 1, 2, 2, 2, 2, 1, 2, 1, 2, 2]
    i2z = [0, 1, 2, 1, 2, 1, 2, 1, 2, 3, 3, 3, 3, 3]

    is_, ie = 0, 4

    for ii in range(is_, ie + 1):
        ofp = G.ofp90_nenbe[ii]

        if G.Flg_matsu == 0:
            if mode == 0:
                ofp.fp("【スライド調整前】\n")
            else:
                ofp.fp("【スライド調整後】\n")

        ofp.fp("年度,性別,給付種別,新旧別,在退別,種類,年齢,給付費\n")
        buf = []
        for s in range(1, 3):
            for i in range(1, 14):
                head_i = f"{kyufus[i2k[i]]},{newold[i2n[i]]},{zaitai[i2z[i]]}"
                for j in range(1, 8):
                    head = f"{sei[s]},{head_i},{shurui[j]},"
                    merge = (s == 1 and (ii == 0 or ii == 1))
                    for k in range(G.Ks + 1, G.Ke + 1):
                        pre = f"{k:d},{head}"
                        if merge:
                            row1 = d4x[ii, 1, i, j, k - STTY]
                            row3 = d4x[ii, 3, i, j, k - STTY]
                            for x in range(XA - 1, XB + 1):
                                dtemp = float(row1[x]) + float(row3[x])
                                buf.append(f"{pre}{x:d},{dtemp:20.13e}\n")
                        else:
                            row = d4x[ii, s, i, j, k - STTY]
                            for x in range(XA - 1, XB + 1):
                                buf.append(f"{pre}{x:d},{float(row[x]):20.13e}\n")
                    if len(buf) > 200000:
                        ofp.fp("".join(buf))
                        buf = []
        if buf:
            ofp.fp("".join(buf))


def _fullout_header(ofp):
    """shus_fullout.c:147 の見出し。"""
    ofp.fp("年度,")
    ofp.fp("基礎年金交付金,代行相当給付,独自合計,旧法老齢,旧法障害,旧法遺族,,")

    ofp.fp("老退,老在,通退,通在,障害,遺族,")
    ofp.fp("老退①,老在①,通退①,通在①,障害①,遺族①,")
    ofp.fp("老退②,老在②,通退②,通在②,障害②,遺族②,")
    ofp.fp("老退③,老在③,通退③,通在③,障害③,遺族③,")
    ofp.fp("65-老退,65-老在,65-通退,65-通在,65-障害,65-遺族,,")

    ofp.fp("比老退,比老在,比通退,比通在,比障害,比遺族,")
    ofp.fp("65-比老退,65-比老在,65-比通退,65-比通在,65-比障害,65-比遺族,,")

    ofp.fp("その他計,定額,経過的加算,加給,遺族加算,最低保障,")
    ofp.fp("65-その他計,65-定額,65-経過的加算,65-加給,65-遺族加算,65-最低保障,,")

    ofp.fp("新老退計,新老在計,新通退計,新通在計,")
    ofp.fp("旧老退計,旧老在計,旧通退計,旧通在計,")
    ofp.fp("新障害計,旧障害計,新遺族計,旧遺族計,旧通遺計,")
    ofp.fp("新老退比,新老在比,新通退比,新通在比,")
    ofp.fp("旧老退比,旧老在比,旧通退比,旧通在比,")
    ofp.fp("新障害比,旧障害比,新遺族比,旧遺族比,旧通遺比,")
    ofp.fp("新老退他,新老在他,新通退他,新通在他,")
    ofp.fp("旧老退他,旧老在他,旧通退他,旧通在他,")
    ofp.fp("新障害他,旧障害他,新遺族他,旧遺族他,旧通遺他,")
    ofp.fp("新老退定,新老在定,新通退定,新通在定,")
    ofp.fp("旧老退定,旧老在定,旧通退定,旧通在定,")
    ofp.fp("新障害定,旧障害定,新遺族定,旧遺族定,旧通遺定,")
    ofp.fp("新老退経,新老在経,新通退経,新通在経,")
    ofp.fp("旧老退経,旧老在経,旧通退経,旧通在経,")
    ofp.fp("新障害経,旧障害経,新遺族経,旧遺族経,旧通遺経,")
    ofp.fp("新老退加,新老在加,新通退加,新通在加,")
    ofp.fp("旧老退加,旧老在加,旧通退加,旧通在加,")
    ofp.fp("新障害加,旧障害加,新遺族加,旧遺族加,旧通遺加,")
    ofp.fp("新老退遺加,新老在遺加,新通退遺加,新通在遺加,")
    ofp.fp("旧老退遺加,旧老在遺加,旧通退遺加,旧通在遺加,")
    ofp.fp("新障害遺加,旧障害遺加,新遺族遺加,旧遺族遺加,旧通遺遺加,")
    ofp.fp("新老退最,新老在最,新通退最,新通在最,")
    ofp.fp("旧老退最,旧老在最,旧通退最,旧通在最,")
    ofp.fp("新障害最,旧障害最,新遺族最,旧遺族最,旧通遺最,")
    ofp.fp("\n")
