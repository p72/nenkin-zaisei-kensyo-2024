# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/simlrhnf.cpp の忠実移植（受給者を1歳進める）
=================================================================
309 行。4つの関数を持つ。

    simlrhnf(i, x, xx, xxr)  受給者を `x - 1` から `x` へ1歳進める
    simlrhnf0(i)             0歳（新規裁定だけ）の初期化
    simlrhnfsen(x)           長期加入者の特例（`*sen`）を1歳進める
    simlrhnfsen60()          同じく60歳の初期化

漸化式は

    r[x][xx][i]      = r[x-1][xx][i]      * tmo + rn[x][xx][i]
    f[x][xx][i][j]   = f[x-1][xx][i][j]   * tmo * riv  + fn[x][xx][i][j]
    f_hik[…]         = f_hik[x-1][…]      * tmo * riv3 + fnhik[…]
    f_min[…]         = f_min[x-1][…]      * tmo * riv4（または riv5）+ fnmin[…]

`tmo` が残存率、`riv*` が改定率。`rn` `fn` `fnhik` `fnmin` は
`simlsaite1/2` が作った新規裁定ぶん。

`tmo` — 給付の種類で残存率が違う
--------------------------------
| `i` | `tmo` |
|---|---|
| 1, 3, 5, 7（退職） | `1 - q[k][x][1]`（生命表の死亡率） |
| 2, 4, 6, 8（在職） | 55〜60歳は `exp(-u[k][x][0])`、60歳超は `1 - q2[k][x]`、それ以外 0 |
| 9, 10（障害） | `1 - q[k][x][2]` |
| 11〜13（遺族） | `1 - q[k][x][3]` |

`i` が 6・8 で `x > 70 + k - KIJUN` のときだけ1段めに入る（在職なのに
退職の残存率を使う）。足元の在職受給者が70歳を超えたぶんの扱い。

在職は `x == 65` と `x == 70` で残存率が 0
-----------------------------------------
```c
if(i == 2 || i == 4) {
  if(x == 65) tmo=0.0;
  if(xend > 70 && x == 70) tmo=0.0;
  if( (xend > 66 && x == 66) || … ) { taizai=2; tmo=0.0; }
}
```

65歳・70歳・66〜69歳で在職の受給者を打ち切り、`saitezai()` が
そこで裁定し直す（`taizai` の枝）。`taizai` は**代入するだけで
一度も読まない**局所変数（F9 の仲間）。

`riv*` の4種類
--------------
| 名前 | 中身 | 使う先 |
|---|---|---|
| `riv` | `j` が 1・10 なら 67歳以下 `1+hh` / 68歳以上 `1+ci`、`kku == 1` なら `1+hp2[k][67]`、他は `1+hp2[k][dx]` | `f` |
| `riv2` | 68歳超で `kku != 1` のとき、`hp2` の年齢差を積み上げた補正 | `fn` を直に補正 |
| `riv3` | `1 + ci2[k][dx]` | `f_hik` |
| `riv4` | `1 + hh[k]` | `f_min`（`j` が 1・10） |
| `riv5` | `1 + hp2[k][67]` | `f_min`（それ以外） |

`kku == 1` は `j` が 4・5・9・19・20・21・23（加給・振替加算）で、
年齢に依らず67歳の率を使う。

遺族の65歳の割り増し
--------------------
```c
} else if(i == 11 && s2 != 2 && x == 65) {
  f.AT(x, xx, i, j)=f.AT(x-1, xx, i, j)*tmo*riv*1.0628+fn.AT(x, xx, i, j);
  f_hik … *1.0608 …
  f_min … *1.0608 …
} else if(i == 11 && s2 == 2 && x == 65) {
  f … *2.5057 …
  f_hik … *2.9759 …
  f_min … *2.9759 …
```

65歳で遺族厚生年金に経過的寡婦加算が付く（女は 2.5〜3.0 倍）。
`f` と `f_hik`／`f_min` で係数が違う（1.0628 と 1.0608、
2.5057 と 2.9759）。本来水準と従前額保障で分母が違うため。

`simlrhnf0` の `i <= 10` と `i >= 11` の非対称
---------------------------------------------
```c
FOR(j, 1, 23) {
  if(i <= 10) { f_hik.AT(0,0,i,j)=0.0; f_min.AT(0,0,i,j)=0.0; }
  else { … 中身を入れる … }
  f.AT(0, 0, i, j)=fn.AT(0, 0, i, j);
}
```

0歳の受給者は遺族（`i >= 11`）しかいないので、それ以外は 0 にする。
`f` は種類に関係なく `fn` を写す。
"""
import math

from glva import G
from sepsstd import std_max

from setconst import KIJUN

__all__ = ["simlrhnf", "simlrhnf0", "simlrhnfsen", "simlrhnfsen60"]

# `riv` に 67歳の率を使う `j`（加給・振替加算）
_KKU_JS = (4, 5, 9, 19, 20, 21, 23)


def simlrhnf0(i):
    """simlrhnf.cpp:4。0歳（新規裁定だけ）の初期化。"""
    G.r[0, 0, i] = G.rn[0, 0, i]
    G.hn[0, 0, i, 1] = G.hnn[0, 0, i, 1]
    G.hn[0, 0, i, 2] = G.hnn[0, 0, i, 2]
    G.pshn[0, 0, i] = G.pshnn[0, 0, i]
    for j in range(1, 23 + 1):
        if i <= 10:
            G.f_hik[0, 0, i, j] = 0.0
            G.f_min[0, 0, i, j] = 0.0
        else:
            if j == 1 or j == 10:
                G.f_hik[0, 0, i, j] = G.fnhik[0, 0, i, j]
                G.f_min[0, 0, i, j] = G.fnmin[0, 0, i, j]
            elif j == 13 or j == 22:
                G.f_hik[0, 0, i, j] = 0.0
                G.f_min[0, 0, i, j] = 0.0
                G.fn[0, 0, i, j] = 0.0
            else:
                G.fnmin[0, 0, i, j] = G.fn[0, 0, i, j] * 0.8
                G.f_min[0, 0, i, j] = G.fnmin[0, 0, i, j]
        G.f[0, 0, i, j] = G.fn[0, 0, i, j]


def simlrhnf(i, x, xx, xxr):
    """simlrhnf.cpp:34。受給者を1歳進める。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pseid = G.pseid
    xend = G.xend

    r = G.r
    rn = G.rn
    hn = G.hn
    hnn = G.hnn
    f = G.f
    fn = G.fn
    f_hik = G.f_hik
    fnhik = G.fnhik
    f_min = G.f_min
    fnmin = G.fnmin
    q = G.q
    hh = G.hh
    ci = G.ci
    ci2 = G.ci2
    hp2 = G.hp2

    dx = max(x, 67)

    tmo = 0.0
    if (i == 1 or i == 3 or i == 5 or i == 7
            or ((i == 6 or i == 8) and x > 70 + k - KIJUN)):
        tmo = 1.0 - q[k, x, 1]
    elif i == 2 or i == 4 or i == 6 or i == 8:
        if 55 < x <= 60:
            tmo = math.exp(-G.u[k, x, 0])
        elif 60 < x <= xend - 1:
            tmo = 1.0 - G.q2[k, x]
        else:
            tmo = 0.0
    if i == 9 or i == 10:
        tmo = 1.0 - q[k, x, 2]
    if i >= 11:
        tmo = 1.0 - q[k, x, 3]

    if i == 2 or i == 4:
        if x == 65:
            tmo = 0.0
        if xend > 70 and x == 70:
            tmo = 0.0

        if ((xend > 66 and x == 66) or (xend > 67 and x == 67)
                or (xend > 68 and x == 68) or (xend > 69 and x == 69)):
            # `taizai` は代入するだけで読まれない
            tmo = 0.0

    if pseid == 0 and (i == 1 or i == 3) and x >= 70 + k - KIJUN:
        if G.l[k - 1, s, x - 1] > 1.0e-6:
            tmp = std_max(0.0,
                          G.q2[k, x]
                          - (1.0 + G.l[k, s, x] / G.l[k - 1, s, x - 1])
                          * G.u[k, x, 3] / 2.0)
        else:
            tmp = 0.0
    else:
        tmp = 0.0

    if i == 1 and x == xxr and xxr > 60 and xx == 0:
        # 長期加入者の特例から本流へ合流させる
        r[x, 0, 1] = (r[x - 1, 0, 1] + G.rsen[x - 1]) * tmo + rn[x, 0, 1]
        hn[x, 0, 1, 1] = ((hn[x - 1, 0, 1, 1] + G.hnsen[x - 1, 1]) * tmo
                          + hnn[x, 0, 1, 1])
        hn[x, 0, 1, 2] = ((hn[x - 1, 0, 1, 2] + G.hnsen[x - 1, 2]) * tmo
                          + hnn[x, 0, 1, 2])
        G.pshn[x, 0, 1] = ((G.pshn[x - 1, 0, 1] + G.pshnsen[x - 1]) * tmo
                           + G.pshnn[x, 0, 1])
        G.rsen[x - 1] = 0.0
        G.hnsen[x - 1, 1] = 0.0
        G.hnsen[x - 1, 2] = 0.0
        G.pshnsen[x - 1] = 0.0
    else:
        r[x, xx, i] = r[x - 1, xx, i] * tmo + rn[x, xx, i]
        hn[x, xx, i, 1] = hn[x - 1, xx, i, 1] * tmo + hnn[x, xx, i, 1]
        hn[x, xx, i, 2] = hn[x - 1, xx, i, 2] * tmo + hnn[x, xx, i, 2]
        G.pshn[x, xx, i] = G.pshn[x - 1, xx, i] * tmo + G.pshnn[x, xx, i]

    if pseid == 0 and (i == 1 or i == 3) and x >= 70 + k - KIJUN:
        r[x, xx, i] = r[x, xx, i] + r[x - 1, xx, i + 1] * tmp
        hn[x, xx, i, 1] = hn[x, xx, i, 1] + hn[x - 1, xx, i + 1, 1] * tmp
        hn[x, xx, i, 2] = hn[x, xx, i, 2] + hn[x - 1, xx, i + 1, 2] * tmp
        G.pshn[x, xx, i] = (G.pshn[x, xx, i]
                            + G.pshn[x - 1, xx, i + 1] * tmp)

    for j in range(1, 23 + 1):
        if j == 13 or j == 22:
            continue

        kku = 1 if j in _KKU_JS else 0

        if j == 1 or j == 10:
            if x <= 67:
                riv = 1.0 + hh[k]
            else:
                riv = 1.0 + ci[k]
        elif kku == 1:
            riv = 1.0 + hp2[k, 67]
        else:
            riv = 1.0 + hp2[k, dx]

        riv3 = 1.0 + ci2[k, dx]
        riv4 = 1.0 + hh[k]
        riv5 = 1.0 + hp2[k, 67]

        if j != 1 and j != 10:
            fnmin[x, xx, i, j] = fn[x, xx, i, j] * 0.80

            if x > 67 and kku != 1:
                riv2 = 1.0
                k_vs_x = min(k - 5, x - 68)
                for kk in range(0, k_vs_x + 1):
                    riv2 = (riv2 * (1.0 + hp2[k - kk, x - kk])
                            / (1.0 + hp2[k - kk, 67]))
                fn[x, xx, i, j] = fn[x, xx, i, j] * riv2

        if i == 1 and x == xxr and xxr > 60 and xx == 0:
            f[x, xx, 1, j] = ((f[x - 1, xx, 1, j] + G.fsen[x - 1, j])
                              * tmo * riv + fn[x, xx, 1, j])
            G.fsen[x - 1, j] = 0.0
            if j == 1 or j == 10:
                f_hik[x, xx, 1, j] = ((f_hik[x - 1, xx, 1, j]
                                       + G.fsenhik[x - 1, j])
                                      * tmo * riv3 + fnhik[x, xx, 1, j])
                f_min[x, xx, 1, j] = ((f_min[x - 1, xx, 1, j]
                                       + G.fsenmin[x - 1, j])
                                      * tmo * riv4 + fnmin[x, xx, 1, j])
                G.fsenhik[x - 1, j] = 0.0
                G.fsenmin[x - 1, j] = 0.0
            else:
                f_min[x, xx, 1, j] = ((f_min[x - 1, xx, 1, j]
                                       + G.fsenmin[x - 1, j])
                                      * tmo * riv5 + fnmin[x, xx, 1, j])
                G.fsenmin[x - 1, j] = 0.0
        elif i == 11 and s2 != 2 and x == 65:
            if j == 1 or j == 10:
                f[x, xx, i, j] = (f[x - 1, xx, i, j] * tmo * riv * 1.0628
                                  + fn[x, xx, i, j])
                f_hik[x, xx, i, j] = (f_hik[x - 1, xx, i, j] * tmo * riv3
                                      * 1.0608 + fnhik[x, xx, i, j])
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv4
                                      * 1.0608 + fnmin[x, xx, i, j])
            else:
                f[x, xx, i, j] = (f[x - 1, xx, i, j] * tmo * riv
                                  + fn[x, xx, i, j])
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv5
                                      + fnmin[x, xx, i, j])
        elif i == 11 and s2 == 2 and x == 65:
            if j == 1 or j == 10:
                f[x, xx, i, j] = (f[x - 1, xx, i, j] * tmo * riv * 2.5057
                                  + fn[x, xx, i, j])
                f_hik[x, xx, i, j] = (f_hik[x - 1, xx, i, j] * tmo * riv3
                                      * 2.9759 + fnhik[x, xx, i, j])
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv4
                                      * 2.9759 + fnmin[x, xx, i, j])
            else:
                f[x, xx, i, j] = (f[x - 1, xx, i, j] * tmo * riv
                                  + fn[x, xx, i, j])
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv5
                                      + fnmin[x, xx, i, j])
        else:
            f[x, xx, i, j] = (f[x - 1, xx, i, j] * tmo * riv
                              + fn[x, xx, i, j])
            if j == 1 or j == 10:
                f_hik[x, xx, i, j] = (f_hik[x - 1, xx, i, j] * tmo * riv3
                                      + fnhik[x, xx, i, j])
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv4
                                      + fnmin[x, xx, i, j])
            else:
                f_min[x, xx, i, j] = (f_min[x - 1, xx, i, j] * tmo * riv5
                                      + fnmin[x, xx, i, j])

        if pseid == 0 and (i == 1 or i == 3) and x >= 70 + k - KIJUN:
            f[x, xx, i, j] = (f[x, xx, i, j]
                              + f[x - 1, xx, i + 1, j] * tmp * riv)
            if j == 1 or j == 10:
                f_hik[x, xx, i, j] = (f_hik[x, xx, i, j]
                                      + f_hik[x - 1, xx, i + 1, j]
                                      * tmp * riv3)
                f_min[x, xx, i, j] = (f_min[x, xx, i, j]
                                      + f_min[x - 1, xx, i + 1, j]
                                      * tmp * riv4)
            else:
                f_min[x, xx, i, j] = (f_min[x, xx, i, j]
                                      + f_min[x - 1, xx, i + 1, j]
                                      * tmp * riv5)


def simlrhnfsen(x):
    """simlrhnf.cpp:220。長期加入者の特例（`*sen`）を1歳進める。"""
    k = G.k
    hh = G.hh
    ci = G.ci
    ci2 = G.ci2
    hp2 = G.hp2

    dx = max(x, 67)

    tmo = 1.0 - G.q[k, x, 1]
    G.rsen[x] = G.rsen[x - 1] * tmo + G.rsenn[x]
    G.hnsen[x, 1] = G.hnsen[x - 1, 1] * tmo + G.hnsenn[x, 1]
    G.hnsen[x, 2] = G.hnsen[x - 1, 2] * tmo + G.hnsenn[x, 2]
    G.pshnsen[x] = G.pshnsen[x - 1] * tmo + G.pshnsenn[x]

    for j in range(1, 23 + 1):
        if j == 13 or j == 22:
            continue

        kku = 1 if j in _KKU_JS else 0

        if j == 1 or j == 10:
            if x <= 67:
                riv = 1.0 + hh[k]
            else:
                riv = 1.0 + ci[k]
        elif kku == 1:
            riv = 1.0 + hp2[k, 67]
        else:
            riv = 1.0 + hp2[k, dx]

        riv3 = 1.0 + ci2[k, dx]
        riv4 = 1.0 + hh[k]

        if j != 1 and j != 10:
            G.fsennmin[x, j] = G.fsenn[x, j] * 0.8

            if x > 67 and kku != 1:
                riv2 = 1.0
                k_vs_x = min(k - 5, x - 68)
                for kk in range(0, k_vs_x + 1):
                    riv2 = (riv2 * (1.0 + hp2[k - kk, x - kk])
                            / (1.0 + hp2[k - kk, 67]))
                G.fsenn[x, j] = G.fsenn[x, j] * riv2

        G.fsen[x, j] = G.fsen[x - 1, j] * tmo * riv + G.fsenn[x, j]

        if j == 1 or j == 10:
            G.fsenhik[x, j] = (G.fsenhik[x - 1, j] * tmo * riv3
                               + G.fsennhik[x, j])
            G.fsenmin[x, j] = (G.fsenmin[x - 1, j] * tmo * riv4
                               + G.fsennmin[x, j])


def simlrhnfsen60():
    """simlrhnf.cpp:288。60歳の初期化。"""
    G.rsen[60] = G.rsenn[60]
    G.hnsen[60, 1] = G.hnsenn[60, 1]
    G.hnsen[60, 2] = G.hnsenn[60, 2]
    G.pshnsen[60] = G.pshnsenn[60]
    for j in range(1, 23 + 1):
        if j == 13 or j == 22:
            continue
        G.fsen[60, j] = G.fsenn[60, j]
        if j != 1 and j != 10:
            G.fsennmin[60, j] = G.fsenn[60, j] * 0.8
        else:
            G.fsenhik[60, j] = G.fsennhik[60, j]
        G.fsenmin[60, j] = G.fsennmin[60, j]
