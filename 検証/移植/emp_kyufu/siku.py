# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/siku.cpp の忠実移植（給付の種類ごとの支給率を引く）
========================================================================
129 行。給付の種類 `i`（1〜13）と年齢 `x` から、`seid()` が作った
支給率 `sik[k][x][s3][*][1 or 2]` の中から4つを選んで返す。

    gv    年金額に掛ける支給率
    gvr   受給者数に掛ける支給率（`sik` の第5添字が 2）
    gvk   加給・振替加算に掛ける支給率
    gvkk  一部の内訳（`i == 10` の 17・19・20 番）に掛ける支給率

原本は `double &gv, …` の参照引数で返す。移植版はタプルで返す。

`dkzik` は 0.0 のまま
--------------------
```c
double dkzik;
...
dkzik = 0.0;
...
gvkk = dkzik;      /* i = 2, 4, 6, 8 のとき */
```

`dkzik` に 0 以外を入れるコードは無い。`i` が 2・4・6・8（在職）の
ときは `gvkk = 0.0`、つまり在職老齢年金には振替加算を付けないという
意味で、名前を付けた 0 になっている。

`gv1` `gvr1` を経由する意味
---------------------------
`i` が 2・4 のときだけ `gv1` `gvr1` に入れて最後に `gv` `gvr` へ移す。
途中に `flg_kozax`（高在の適用拡大）の枝があって上書きするため。
`i` が 6・8 のときは同じことを `gv` `gvr` に直接やっている。
**書き方が揃っていない**が動きは同じ。

`flg_toukei != 0` なら全部 1.0
------------------------------
関数の中身まるごとが `if(flg_toukei == 0)` で囲まれている。統計用の
試算では支給率を掛けない（`gv = gvr = gvk = gvkk = 1.0`）。

`sknr()` を呼ぶので `xxr` `xrb` が書き換わる
--------------------------------------------
先頭で `seps::sknr(k, x, xxr, xrb); xrb = max(60, xrb);` を呼ぶ。
`xxr` には **`max(60, …)` を掛けていない**ので、`s2 == 3` の生年では
60 未満（55〜59）が入りうる。`siku()` の呼び出し側（`shkejsha`
`shkekiso`）はそのあと `xxr` を読まないので影響しないが、
**グローバルが書き換わる**ことは覚えておく必要がある。
"""
from glva import G
from sknr import sknr

__all__ = ["siku"]


def siku(x, i):
    """siku.cpp:3 の忠実移植。`(gv, gvr, gvk, gvkk)` を返す。"""
    sknr(G.k, x)
    G.xrb = max(60, G.xrb)

    gv = 1.0
    gvr = 1.0
    gvk = 1.0
    gv1 = 1.0
    gvr1 = 1.0
    gvkk = 1.0
    dkzik = 0.0                     # 0 以外を入れるコードは無い

    if G.s2 != 2:
        s3 = 1
    else:
        s3 = 2

    if G.flg_toukei != 0:
        return gv, gvr, gvk, gvkk

    sik = G.sik
    k = G.k

    if i == 1:
        gv = sik[k, x, s3, 1, 1]
        gvr = sik[k, x, s3, 1, 2]
        gvk = sik[k, x, s3, 14, 1]
        gvkk = gv
    elif i == 2:
        gv1 = sik[k, x, s3, 2, 1]
        gvr1 = sik[k, x, s3, 2, 2]
        gvk = sik[k, x, s3, 14, 1]
        gvkk = dkzik

        if G.flg_kozax == 1 and k >= G.kozaxyr and x >= G.kozax:
            gv1 = sik[k, x, s3, 1, 1]
            gvr1 = sik[k, x, s3, 1, 2]

        gv = gv1
        gvr = gvr1
    elif i == 3:
        gv = sik[k, x, s3, 3, 1]
        gvr = sik[k, x, s3, 3, 2]
        gvk = sik[k, x, s3, 15, 1]
        gvkk = gv
    elif i == 4:
        gv1 = sik[k, x, s3, 4, 1]
        gvr1 = sik[k, x, s3, 4, 2]
        gvk = sik[k, x, s3, 15, 1]
        gvkk = dkzik

        if G.flg_kozax == 1 and k >= G.kozaxyr and x >= G.kozax:
            gv1 = sik[k, x, s3, 3, 1]
            gvr1 = sik[k, x, s3, 3, 2]

        gv = gv1
        gvr = gvr1
    elif i == 5 or (i == 6 and x >= max(G.xend, 85)):
        gv = sik[k, x, s3, 5, 1]
        gvr = sik[k, x, s3, 5, 2]
        gvk = gvr
        gvkk = gv
    elif i == 6:
        gv = sik[k, x, s3, 6, 1]
        gvr = sik[k, x, s3, 6, 2]
        gvk = gvr
        gvkk = dkzik

        # ここだけ `flg_kozax >= 1`（他は `== 1`）
        if G.flg_kozax >= 1 and k >= G.kozaxyr and x >= G.kozax:
            gv = sik[k, x, s3, 5, 1]
            gvr = sik[k, x, s3, 5, 2]
    elif i == 7 or (i == 8 and x >= max(G.xend, 85)):
        gv = sik[k, x, s3, 7, 1]
        gvr = sik[k, x, s3, 7, 2]
        gvk = gvr
        gvkk = gv
    elif i == 8:
        gv = sik[k, x, s3, 8, 1]
        gvr = sik[k, x, s3, 8, 2]
        gvk = gvr
        gvkk = dkzik

        if G.flg_kozax == 1 and k >= G.kozaxyr and x >= G.kozax:
            gv = sik[k, x, s3, 7, 1]
            gvr = sik[k, x, s3, 7, 2]
    elif i == 9 or i == 10:
        gv = sik[k, x, s3, i, 1]
        gvr = sik[k, x, s3, i, 2]
        gvk = sik[k, x, s3, 16, 1]
        if i == 10:
            gvkk = sik[k, x, s3, 18, 1]
    elif i >= 11:
        gv = sik[k, x, s3, i, 1]
        gvr = sik[k, x, s3, i, 2]
        gvk = sik[k, x, s3, 17, 1]

    return gv, gvr, gvk, gvkk
