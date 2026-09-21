# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/simlsaite1.cpp の忠実移植（障害と遺族の裁定）
=================================================================
479 行。3つの関数を持つ。

    saitesho(x, t)      障害厚生年金の新規裁定（`i = 9`）
    saiteizohiho(x, t)  被保険者が死亡したときの遺族厚生年金（`i = 11`）
    saiteizojuk(x)      受給者が死亡したときの遺族厚生年金（`i = 11`）

入れる先は

    rn   [x][xx][i]       新規裁定の人数
    hnn  [x][xx][i][1,2]  うち配偶者の区分別
    pshnn[x][xx][i]       過去分試算の按分ぶん
    fn   [x][xx][i][j]    1人あたり年金額（本来水準）
    fnhik[x][xx][i][j]    同（従前額保障）
    fnmin[x][xx][i][j]    同（8割の下限）

`xx` は 0（繰上げ繰下げ無し）のみ。

`yx` の整数部と小数部で2人に分ける
----------------------------------
```c
int v = (int)(yx.AT(k, x, p));
tmp = yx.AT(k, x, p) - (int)(yx.AT(k, x, p));
FOR(bin1, 0, 1) {
  v = v + bin1;
  ...
  if(bin1 == 0) tmg = tmg * (1.0 - tmp);
  else          tmg = tmg * tmp;
```

`yx[k][x][p]` は「本人が `x` 歳のときの配偶者（`p = 0`）または
子（`p = 1`）の平均年齢」で、小数になる。整数の2つの年齢
`v` と `v + 1` に `(1 - 小数部)` と `小数部` で振り分ける。

**`v = v + bin1` は `v` を書き換える**ので、`bin1 = 1` の周では
`v` が1つ増えたまま。`bin1` のループを抜けると `v` は
`(int)yx + 1` になっている（`p` のループの先頭で作り直すので影響なし）。

`srv` と `pslr` はグローバルを上書きする
----------------------------------------
```c
srv = 0.75;
if(v >= 65) { srv = srv * (s2 != 2 ? 1.0357 : 1.2019); }
```

`srv`（遺族の給付割合 4分の3）は `seid()` が 0.75 を入れたグローバル。
ここで配偶者の年齢が65歳以上なら 1.0357（男）/ 1.2019（女）を掛けて
**上書きする**。`bin1` のループの中で毎回 0.75 に戻すので、
関数を抜けたあとの値は最後の周のもの。`pslr` も同じ。

`cl[k][1] + cl[k][2]` が 0 のとき `tmf2` `tmf3` が持ち越される
--------------------------------------------------------------
`saiteizojuk` の最後（`simlsaite1.cpp:418-443`）。

```c
if(cl.AT(k, 1)+cl.AT(k, 2) > 1.0e-6) {
  tmf  = …;
  tmf2 = …;
  tmf3 = …;
} else {
  tmf = 0.0;            /* tmf2 と tmf3 を 0 にしない */
}
```

`else` で 0 にするのは `tmf` だけ。`tmf2` `tmf3` は関数の
先頭で `double tmg, …, tmf2, tmf3;` と**初期化なしに宣言**されていて、

- `x >= 45` の周なら、すぐ上の通算老齢（`i = 3, 7`）のブロックで
  作った値が残ったまま `fnhik` `fnmin` に足される
- `x < 45` の周でこの `else` に入ると、**未初期化のスタックを読む**

障害の等級別割合 `cl[k][1] + cl[k][2]` が 0 になるのは `kisor` の
入力次第で、いまの入力では 0 にならないので**どちらも起きない**。
`検証/原本の不具合.md` の E30。

移植版は関数の先頭で `tmf2 = tmf3 = 0.0` にしてある。原本と違うのは
「いまの入力では通らない経路」だけ。

`tmrv` の積み上げ
-----------------
68歳以上は「賃金でなく物価で改定する」ので、`x` と配偶者の年齢 `v` の
どちらが68歳を超えているかで再評価率が変わる。
その差を `tmrv` に積み上げる。1999〜2001年度は `hh2_*`（`econ.cpp` が
作る特例の率）を使う。
"""
from glva import G
from sepsstd import c_round, std_max
from setconst import C19, KIJUN

from dsitk import dsitk

__all__ = ["saitesho", "saiteizohiho", "saiteizojuk"]


def saitesho(x, t):
    """simlsaite1.cpp:4。障害厚生年金の新規裁定。"""
    k = G.k
    s = G.s

    bk, bk2, bk3 = dsitk(x, t, 9)
    tmg = G.y[x, t, 2]
    tmg1 = tmg * G.cl[k, 1]
    tmg2 = tmg * G.cl[k, 2]
    tmg3 = tmg * G.cl[k, 3]
    G.rn[x, 0, 9] = G.rn[x, 0, 9] + tmg
    G.hnn[x, 0, 9, 1] = G.hnn[x, 0, 9, 1] + tmg * G.tz[1]
    G.hnn[x, 0, 9, 2] = G.hnn[x, 0, 9, 2] + tmg * G.tz[2]
    G.pshnn[x, 0, 9] = G.pshnn[x, 0, 9] + tmg * G.pslr

    G.fn[x, 0, 9, 1] = (G.fn[x, 0, 9, 1]
                        + (tmg1 * G.ha[1] + tmg2 * G.ha[2]) * bk)
    G.fnhik[x, 0, 9, 1] = (G.fnhik[x, 0, 9, 1]
                           + (tmg1 * G.ha[1] + tmg2 * G.ha[2]) * bk2)
    G.fnmin[x, 0, 9, 1] = (G.fnmin[x, 0, 9, 1]
                           + (tmg1 * G.ha[1] + tmg2 * G.ha[2]) * bk3)
    tmo = ((tmg1 * G.ha[1] + tmg2 * G.ha[2]) * G.fl1 * G.bd[k, 14] * G.pslr)

    G.fn[x, 0, 9, 14] = G.fn[x, 0, 9, 14] + tmo

    if (G.key == 12 or G.key == 13) and G.pslsi2 == 1 and k >= G.psly:
        pass
    else:
        G.fn[x, 0, 9, 21] = (G.fn[x, 0, 9, 21]
                             + (tmg1 + tmg2) * G.adt[2] * G.bd[k, 21] * G.pslr)
        G.fn[x, 0, 9, 4] = (G.fn[x, 0, 9, 4]
                            + (tmg1 + tmg2) * G.adt[1] * G.bd[k, 4] * G.pslr)
        G.fn[x, 0, 9, 6] += ((tmg1 + tmg2)
                             * G.cadt[C19(k - int(c_round(G.ns[k, x])))]
                             * G.bd[k, 6] * G.pslr)

    G.fn[x, 0, 9, 10] = G.fn[x, 0, 9, 10] + tmg3 * G.ha[3] * bk
    G.fnhik[x, 0, 9, 10] = G.fnhik[x, 0, 9, 10] + tmg3 * G.ha[3] * bk2
    G.fnmin[x, 0, 9, 10] = G.fnmin[x, 0, 9, 10] + tmg3 * G.ha[3] * bk3

    tmf = tmg3 * G.ha[3] * G.minb * G.bd[k, 12] * G.pslr

    G.fn[x, 0, 9, 12] = G.fn[x, 0, 9, 12] + tmf * G.ema[s]


def _srv(v):
    """遺族の給付割合。`srv` はグローバルを上書きする。"""
    G.srv = 0.75
    if v >= 65:
        if G.s2 != 2:
            G.srv = G.srv * 1.0357
        else:
            G.srv = G.srv * 1.2019
    return G.srv


def saiteizohiho(x, t):
    """simlsaite1.cpp:46。被保険者が死亡したときの遺族厚生年金。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pslsi2_kako = ((G.key == 12 or G.key == 13) and G.pslsi2 == 1
                   and k >= G.psly)

    for p in range(0, 1 + 1):
        if p == 1 and s != 2:
            continue
        jj = p * 2
        v = int(G.yx[k, x, p])
        tmp = G.yx[k, x, p] - int(G.yx[k, x, p])
        for bin1 in range(0, 1 + 1):
            v = v + bin1

            srv = _srv(v)

            bka, bka2, bka3 = dsitk(x, t, 15)
            bkb, bkb2, bkb3 = dsitk(x, t, 16)
            tmg = G.y[x, t, 3] * G.rs[s, k, x, 1 + jj]
            if bin1 == 0:
                tmg = tmg * (1.0 - tmp)
            else:
                tmg = tmg * tmp
            G.rn[v, 0, 11] = G.rn[v, 0, 11] + tmg
            G.hnn[v, 0, 11, 1] = G.hnn[v, 0, 11, 1] + tmg * G.tz[1]
            G.hnn[v, 0, 11, 2] = G.hnn[v, 0, 11, 2] + tmg * G.tz[2]

            G.fn[v, 0, 11, 1] = (G.fn[v, 0, 11, 1]
                                 + tmg * std_max(bkb, bka) * srv)
            G.fnhik[v, 0, 11, 1] = (G.fnhik[v, 0, 11, 1]
                                    + tmg * std_max(bkb2, bka2) * srv)
            G.fnmin[v, 0, 11, 1] = (G.fnmin[v, 0, 11, 1]
                                    + tmg * std_max(bkb3, bka3) * srv)
            tmo = tmg * G.fl1 * G.bd[k, 14] * G.pslr

            G.fn[v, 0, 11, 14] = G.fn[v, 0, 11, 14] + tmo

            if pslsi2_kako:
                pass
            else:
                G.fn[v, 0, 11, 21] = (G.fn[v, 0, 11, 21]
                                      + tmg * G.adt[2] * G.bd[k, 21] * G.pslr)
                if s2 != 2 and v >= 19:
                    tmf = tmg * G.wif * G.bd[k, 7] * G.pslr

                    G.fn[v, 0, 11, 7] = G.fn[v, 0, 11, 7] + tmf
                    G.fn[v, 0, 11, 8] = (G.fn[v, 0, 11, 8]
                                         + tmg * G.wife[C19(k - v)]
                                         * G.bd[k, 8] * G.pslr)

            bk, bk2, bk3 = dsitk(x, t, 17)
            if ((G.it == 1 or G.it == 2 or G.it == 3)
                    and (x <= max(60, G.xrb)
                         or (k <= KIJUN + 13 and x <= 69 + k - KIJUN))):

                tmg = G.ye[x, t] * G.rs[s, k, x, 1 + jj]
                if bin1 == 0:
                    tmg = tmg * (1.0 - tmp)
                else:
                    tmg = tmg * tmp
                G.rn[v, 0, 11] = G.rn[v, 0, 11] + tmg
                G.hnn[v, 0, 11, 1] = G.hnn[v, 0, 11, 1] + tmg * G.tz[1]
                G.hnn[v, 0, 11, 2] = G.hnn[v, 0, 11, 2] + tmg * G.tz[2]

                G.fn[v, 0, 11, 1] = G.fn[v, 0, 11, 1] + tmg * bk * srv
                G.fnhik[v, 0, 11, 1] = (G.fnhik[v, 0, 11, 1]
                                        + tmg * bk2 * srv)
                G.fnmin[v, 0, 11, 1] = (G.fnmin[v, 0, 11, 1]
                                        + tmg * bk3 * srv)

                if pslsi2_kako:
                    pass
                else:
                    if s2 != 2 and v >= 19:
                        tmf = tmg * G.wif * G.bd[k, 7] * G.pslr

                        G.fn[v, 0, 11, 7] = G.fn[v, 0, 11, 7] + tmf
                        G.fn[v, 0, 11, 8] = (G.fn[v, 0, 11, 8]
                                             + tmg * G.wife[C19(k - v)]
                                             * G.bd[k, 8] * G.pslr)


def saiteizojuk(x):
    """simlsaite1.cpp:134。受給者が死亡したときの遺族厚生年金。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pseid = G.pseid
    hh = G.hh
    ci = G.ci
    ci2 = G.ci2
    q = G.q
    rs = G.rs
    r = G.r
    hn = G.hn
    f = G.f
    f_hik = G.f_hik
    f_min = G.f_min
    bd = G.bd
    adt = G.adt
    cl = G.cl
    cl2 = G.cl2
    pslsi2_kako = ((G.key == 12 or G.key == 13) and G.pslsi2 == 1
                   and k >= G.psly)

    dx = max(x, 67)
    if x > 70 and G.l[k - 1, s, x - 1] > 1.0e-6:
        tmq3 = ((1.0 + G.l[k, s, x] / G.l[k - 1, s, x - 1])
                * G.u[k, x, 3] / 2.0)
    else:
        tmq3 = 0.0

    # 原本は tmf2 / tmf3 が枝をまたいで持ち越される（E30）
    tmf2 = 0.0
    tmf3 = 0.0

    for p in range(0, 1 + 1):
        if p == 1 and s != 2:
            continue
        jj = p * 2
        v = int(G.yx[k, x, p])
        tmp = G.yx[k, x, p] - int(G.yx[k, x, p])
        for bin1 in range(0, 1 + 1):
            v = v + bin1
            srv = _srv(v)
            if x <= 67:
                riv = 1.0 + hh[k]
            else:
                riv = 1.0 + ci[k]

            riv2 = 1.0
            if k - x >= -62 and k - v >= -62:
                riv2 = 1.0
            elif k - x >= -62 and k - v < -62:
                riv2 = riv2 / 0.998
            elif k - x < -62 and k - v >= -62:
                riv2 = riv2 * 0.998

            tmrv = 1.0
            if x > 67:
                for kk in range(0, x - 68 + 1):
                    if kk <= k - 5:
                        tmrv = tmrv * (1.0 + hh[k - kk]) / (1.0 + ci[k - kk])
                    elif kk <= k - 2:
                        assert -1 <= k - kk - 3 <= 1
                        if k - kk - 3 == -1:
                            tmrv = tmrv * (1.0 + G.hh2_1999)
                        if k - kk - 3 == 0:
                            tmrv = tmrv * (1.0 + G.hh2_2000)
                        if k - kk - 3 == 1:
                            tmrv = tmrv * (1.0 + G.hh2_2001)
            if k - x >= -62:
                tmrv = tmrv / 0.998

            if v > 67:
                for kk in range(0, v - 68 + 1):
                    if kk <= k - 5:
                        tmrv = tmrv * (1.0 + ci[k - kk]) / (1.0 + hh[k - kk])
                    elif kk <= k - 2:
                        assert -1 <= k - kk - 3 <= 1
                        if k - kk - 3 == -1:
                            tmrv = tmrv / (1.0 + G.hh2_1999)
                        if k - kk - 3 == 0:
                            tmrv = tmrv / (1.0 + G.hh2_2000)
                        if k - kk - 3 == 1:
                            tmrv = tmrv / (1.0 + G.hh2_2001)
            if k - v >= -62:
                tmrv = tmrv * 0.998

            if x >= 45:
                # ---- 老齢（i = 1, 5）の受給者が死亡したぶん ----
                tmg = 0.0
                tmg1 = 0.0
                tmg2 = 0.0
                tmh1 = 0.0
                tmh2 = 0.0
                tmf = 0.0
                tmf2 = 0.0
                tmf3 = 0.0

                for xx in range(0, 15 + 1):
                    tmg1 = tmg1 + G.pshn[x - 1, xx, 1]
                    tmg2 = tmg2 + r[x - 1, xx, 1]
                    tmg = tmg + r[x - 1, xx, 1] * q[k, x, 1] * rs[s, k, x, 1 + jj]
                    tmh1 = (tmh1 + hn[x - 1, xx, 1, 1] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])
                    tmh2 = (tmh2 + hn[x - 1, xx, 1, 2] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])

                    tmf = (tmf + f[x - 1, xx, 1, 1] * riv
                           * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * tmrv)
                    tmf2 = (tmf2 + f_hik[x - 1, xx, 1, 1]
                            * (1.0 + ci2[k, dx])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                    tmf3 = (tmf3 + f_min[x - 1, xx, 1, 1] * (1.0 + hh[k])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                    if pseid == 0 and x >= 70 + k - KIJUN:
                        tmg1 = tmg1 + G.pshn[x - 1, xx, 2]
                        tmg2 = tmg2 + r[x - 1, xx, 2]
                        tmg = (tmg + r[x - 1, xx, 2] * tmq3
                               * rs[s, k, x, 1 + jj])
                        tmh1 = (tmh1 + hn[x - 1, xx, 2, 1] * tmq3
                                * rs[s, k, x, 1 + jj])
                        tmh2 = (tmh2 + hn[x - 1, xx, 2, 2] * tmq3
                                * rs[s, k, x, 1 + jj])

                        tmf = (tmf + f[x - 1, xx, 2, 1] * riv
                               * srv * tmq3 * rs[s, k, x, 1 + jj] * tmrv)
                        tmf2 = (tmf2 + f_hik[x - 1, xx, 2, 1]
                                * (1.0 + ci2[k, dx])
                                * srv * tmq3 * rs[s, k, x, 1 + jj] * riv2)
                        tmf3 = (tmf3 + f_min[x - 1, xx, 2, 1]
                                * (1.0 + hh[k])
                                * srv * tmq3 * rs[s, k, x, 1 + jj] * riv2)
                tmg1 = tmg1 + G.pshn[x - 1, 0, 5]
                tmg2 = tmg2 + r[x - 1, 0, 5]
                tmg = tmg + r[x - 1, 0, 5] * q[k, x, 1] * rs[s, k, x, 1 + jj]
                tmh1 = (tmh1 + hn[x - 1, 0, 5, 1] * q[k, x, 1]
                        * rs[s, k, x, 1 + jj])
                tmh2 = (tmh2 + hn[x - 1, 0, 5, 2] * q[k, x, 1]
                        * rs[s, k, x, 1 + jj])

                tmf = (tmf + f[x - 1, 0, 5, 1] * riv
                       * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * tmrv)
                tmf2 = (tmf2 + f_hik[x - 1, 0, 5, 1] * (1.0 + ci2[k, dx])
                        * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                tmf3 = (tmf3 + f_min[x - 1, 0, 5, 1] * (1.0 + hh[k])
                        * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                if 61 <= x <= 70:
                    tmg1 = tmg1 + G.pshnsen[x - 1]
                    tmg2 = tmg2 + G.rsen[x - 1]
                    tmg = (tmg + G.rsen[x - 1] * q[k, x, 1]
                           * rs[s, k, x, 1 + jj])
                    tmh1 = (tmh1 + G.hnsen[x - 1, 1] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])
                    tmh2 = (tmh2 + G.hnsen[x - 1, 2] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])

                    tmf = (tmf + G.fsen[x - 1, 1] * riv * srv * q[k, x, 1]
                           * rs[s, k, x, 1 + jj] * tmrv)
                    tmf2 = (tmf2 + G.fsenhik[x - 1, 1] * (1.0 + ci2[k, dx])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                    tmf3 = (tmf3 + G.fsenmin[x - 1, 1] * (1.0 + hh[k])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                if G.key == 12 and k >= G.psly and tmg2 > 1.0e-6:
                    G.pslr = tmg1 / tmg2
                else:
                    G.pslr = 1.0
                if bin1 == 0:
                    tmg = tmg * (1.0 - tmp)
                    tmh1 = tmh1 * (1.0 - tmp)
                    tmh2 = tmh2 * (1.0 - tmp)
                    tmf = tmf * (1.0 - tmp)
                    tmf2 = tmf2 * (1.0 - tmp)
                    tmf3 = tmf3 * (1.0 - tmp)
                else:
                    tmg = tmg * tmp
                    tmh1 = tmh1 * tmp
                    tmh2 = tmh2 * tmp
                    tmf = tmf * tmp
                    tmf2 = tmf2 * tmp
                    tmf3 = tmf3 * tmp
                G.rn[v, 0, 11] = G.rn[v, 0, 11] + tmg
                G.hnn[v, 0, 11, 1] = G.hnn[v, 0, 11, 1] + tmh1
                G.hnn[v, 0, 11, 2] = G.hnn[v, 0, 11, 2] + tmh2

                G.fn[v, 0, 11, 1] = G.fn[v, 0, 11, 1] + tmf
                G.fnhik[v, 0, 11, 1] = G.fnhik[v, 0, 11, 1] + tmf2
                G.fnmin[v, 0, 11, 1] = G.fnmin[v, 0, 11, 1] + tmf3
                tmo1 = tmg * G.fl1 * bd[k, 14] * G.pslr

                G.fn[v, 0, 11, 14] = G.fn[v, 0, 11, 14] + tmo1

                if pslsi2_kako:
                    pass
                else:
                    G.fn[v, 0, 11, 21] = (G.fn[v, 0, 11, 21]
                                          + tmg * adt[2] * bd[k, 21] * G.pslr)
                    if s2 != 2 and v >= 19:
                        tmo2 = tmg * G.wif * bd[k, 7] * G.pslr

                        G.fn[v, 0, 11, 7] = G.fn[v, 0, 11, 7] + tmo2
                        G.fn[v, 0, 11, 8] = (G.fn[v, 0, 11, 8]
                                             + tmg * G.wife[C19(k - v)]
                                             * bd[k, 8] * G.pslr)
                # ---- 通算老齢（i = 3, 7）の受給者が死亡したぶん ----
                tmg = 0.0
                tmh1 = 0.0
                tmh2 = 0.0
                tmf = 0.0
                tmf2 = 0.0
                tmf3 = 0.0
                tmtu = 0.0

                for xx in range(0, 15 + 1):
                    tmg = (tmg + r[x - 1, xx, 3] * q[k, x, 1]
                           * rs[s, k, x, 1 + jj])
                    tmh1 = (tmh1 + hn[x - 1, xx, 3, 1] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])
                    tmh2 = (tmh2 + hn[x - 1, xx, 3, 2] * q[k, x, 1]
                            * rs[s, k, x, 1 + jj])
                    tmtu = (tmtu + f[x - 1, xx, 3, 4]
                            / (adt[1] * bd[k - 1, 4])
                            * q[k, x, 1] * rs[s, k, x, 1 + jj])
                    tmf = (tmf + f[x - 1, xx, 3, 1] * riv
                           * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * tmrv)
                    tmf2 = (tmf2 + f_hik[x - 1, xx, 3, 1]
                            * (1.0 + ci2[k, dx])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                    tmf3 = (tmf3 + f_min[x - 1, xx, 3, 1] * (1.0 + hh[k])
                            * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                    if pseid == 0 and x >= 70 + k - KIJUN:
                        tmg = (tmg + r[x - 1, xx, 4] * tmq3
                               * rs[s, k, x, 1 + jj])
                        tmh1 = (tmh1 + hn[x - 1, xx, 4, 1] * tmq3
                                * rs[s, k, x, 1 + jj])
                        tmh2 = (tmh2 + hn[x - 1, xx, 4, 2] * tmq3
                                * rs[s, k, x, 1 + jj])

                        tmf = (tmf + f[x - 1, xx, 4, 1] * riv
                               * srv * tmq3 * rs[s, k, x, 1 + jj] * tmrv)
                        tmf2 = (tmf2 + f_hik[x - 1, xx, 4, 1]
                                * (1.0 + ci2[k, dx])
                                * srv * tmq3 * rs[s, k, x, 1 + jj] * riv2)
                        tmf3 = (tmf3 + f_min[x - 1, xx, 4, 1]
                                * (1.0 + hh[k])
                                * srv * tmq3 * rs[s, k, x, 1 + jj] * riv2)
                tmg = tmg + r[x - 1, 0, 7] * q[k, x, 1] * rs[s, k, x, 1 + jj]
                tmh1 = (tmh1 + hn[x - 1, 0, 7, 1] * q[k, x, 1]
                        * rs[s, k, x, 1 + jj])
                tmh2 = (tmh2 + hn[x - 1, 0, 7, 2] * q[k, x, 1]
                        * rs[s, k, x, 1 + jj])

                tmf = (tmf + f[x - 1, 0, 7, 1] * riv
                       * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * tmrv)
                tmf2 = (tmf2 + f_hik[x - 1, 0, 7, 1] * (1.0 + ci2[k, dx])
                        * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                tmf3 = (tmf3 + f_min[x - 1, 0, 7, 1] * (1.0 + hh[k])
                        * srv * q[k, x, 1] * rs[s, k, x, 1 + jj] * riv2)
                if bin1 == 0:
                    tmg = tmg * (1.0 - tmp)
                    tmh1 = tmh1 * (1.0 - tmp)
                    tmh2 = tmh2 * (1.0 - tmp)
                    tmf = tmf * (1.0 - tmp)
                    tmf2 = tmf2 * (1.0 - tmp)
                    tmf3 = tmf3 * (1.0 - tmp)
                    tmtu = tmtu * (1.0 - tmp)
                else:
                    tmg = tmg * tmp
                    tmh1 = tmh1 * tmp
                    tmh2 = tmh2 * tmp
                    tmf = tmf * tmp
                    tmf2 = tmf2 * tmp
                    tmf3 = tmf3 * tmp
                    tmtu = tmtu * tmp
                G.rn[v, 0, 11] = G.rn[v, 0, 11] + tmg
                G.hnn[v, 0, 11, 1] = G.hnn[v, 0, 11, 1] + tmh1
                G.hnn[v, 0, 11, 2] = G.hnn[v, 0, 11, 2] + tmh2

                G.fn[v, 0, 11, 1] = G.fn[v, 0, 11, 1] + tmf
                G.fnhik[v, 0, 11, 1] = G.fnhik[v, 0, 11, 1] + tmf2
                G.fnmin[v, 0, 11, 1] = G.fnmin[v, 0, 11, 1] + tmf3
                tmo1 = tmtu * G.fl1 * bd[k, 14] * G.pslr

                G.fn[v, 0, 11, 14] = G.fn[v, 0, 11, 14] + tmo1
                if pslsi2_kako:
                    pass
                else:
                    G.fn[v, 0, 11, 21] = (G.fn[v, 0, 11, 21]
                                          + tmtu * adt[2] * bd[k, 21]
                                          * G.pslr)
                    if s2 != 2 and v >= 19:
                        tmo2 = tmtu * G.wif * bd[k, 7] * G.pslr

                        G.fn[v, 0, 11, 7] = G.fn[v, 0, 11, 7] + tmo2
                        G.fn[v, 0, 11, 8] = (G.fn[v, 0, 11, 8]
                                             + tmtu * G.wife[C19(k - v)]
                                             * bd[k, 8] * G.pslr)

            # ---- 障害（i = 9, 10）の受給者が死亡したぶん ----
            if (G.key == 12 and k >= G.psly
                    and (r[x - 1, 0, 9] + r[x - 1, 0, 10]) > 1.0e-6):
                G.pslr = ((G.pshn[x - 1, 0, 9] + G.pshn[x - 1, 0, 10])
                          / (r[x - 1, 0, 9] + r[x - 1, 0, 10]))
            else:
                G.pslr = 1.0
            tmg = (r[x - 1, 0, 9] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                   * (cl[k, 1] + cl[k, 2])
                   + r[x - 1, 0, 10] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                   * (cl2[k, 1] + cl2[k, 2]))
            tmh1 = (hn[x - 1, 0, 9, 1] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                    * (cl[k, 1] + cl[k, 2])
                    + hn[x - 1, 0, 10, 1] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                    * (cl2[k, 1] + cl2[k, 2]))
            tmh2 = (hn[x - 1, 0, 9, 2] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                    * (cl[k, 1] + cl[k, 2])
                    + hn[x - 1, 0, 10, 2] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                    * (cl2[k, 1] + cl2[k, 2]))

            if cl[k, 1] + cl[k, 2] > 1.0e-6:
                tmf = (f[x - 1, 0, 9, 1] * q[k, x, 2] * rs[s, k, x, 2 + jj]
                       * riv * srv
                       * (cl[k, 1] + cl[k, 2])
                       / (cl[k, 1] * G.ha[1] + cl[k, 2] * G.ha[2]) * tmrv
                       + f[x - 1, 0, 10, 1] * G.prb / G.pra * 25.0 / 20.0
                       * q[k, x, 2] * rs[s, k, x, 2 + jj] * riv * srv
                       * (cl2[k, 1] + cl2[k, 2])
                       / (cl2[k, 1] * G.hb[1] + cl2[k, 2] * G.hb[2]) * tmrv)

                tmf2 = (f_hik[x - 1, 0, 9, 1] * (1.0 + ci2[k, dx])
                        * q[k, x, 2] * rs[s, k, x, 2 + jj] * srv
                        * (cl[k, 1] + cl[k, 2])
                        / (cl[k, 1] * G.ha[1] + cl[k, 2] * G.ha[2]) * riv2
                        + f_hik[x - 1, 0, 10, 1] * (1.0 + ci2[k, dx])
                        * G.prb / G.pra * 25.0 / 20.0
                        * q[k, x, 2] * rs[s, k, x, 2 + jj] * srv * riv2
                        * (cl2[k, 1] + cl2[k, 2])
                        / (cl2[k, 1] * G.hb[1] + cl2[k, 2] * G.hb[2]))

                tmf3 = (f_min[x - 1, 0, 9, 1] * (1.0 + hh[k])
                        * q[k, x, 2] * rs[s, k, x, 2 + jj] * srv
                        * (cl[k, 1] + cl[k, 2])
                        / (cl[k, 1] * G.ha[1] + cl[k, 2] * G.ha[2]) * riv2
                        + f_min[x - 1, 0, 10, 1] * (1.0 + hh[k])
                        * G.prb / G.pra * 25.0 / 20.0
                        * q[k, x, 2] * rs[s, k, x, 2 + jj] * srv
                        * (cl2[k, 1] + cl2[k, 2])
                        / (cl2[k, 1] * G.hb[1] + cl2[k, 2] * G.hb[2]) * riv2)
            else:
                # 原本は tmf だけ 0 にする。tmf2 / tmf3 は前の値のまま（E30）
                tmf = 0.0
            if bin1 == 0:
                tmg = tmg * (1.0 - tmp)
                tmh1 = tmh1 * (1.0 - tmp)
                tmh2 = tmh2 * (1.0 - tmp)
                tmf = tmf * (1.0 - tmp)
                tmf2 = tmf2 * (1.0 - tmp)
                tmf3 = tmf3 * (1.0 - tmp)
            else:
                tmg = tmg * tmp
                tmh1 = tmh1 * tmp
                tmh2 = tmh2 * tmp
                tmf = tmf * tmp
                tmf2 = tmf2 * tmp
                tmf3 = tmf3 * tmp
            G.rn[v, 0, 11] = G.rn[v, 0, 11] + tmg
            G.hnn[v, 0, 11, 1] = G.hnn[v, 0, 11, 1] + tmh1
            G.hnn[v, 0, 11, 2] = G.hnn[v, 0, 11, 2] + tmh2

            G.fn[v, 0, 11, 1] = G.fn[v, 0, 11, 1] + tmf
            G.fnhik[v, 0, 11, 1] = G.fnhik[v, 0, 11, 1] + tmf2
            G.fnmin[v, 0, 11, 1] = G.fnmin[v, 0, 11, 1] + tmf3

            if pslsi2_kako:
                pass
            else:
                if s2 != 2 and v >= 19:
                    tmo3 = tmg * G.wif * bd[k, 7] * G.pslr

                    G.fn[v, 0, 11, 7] = G.fn[v, 0, 11, 7] + tmo3
                    G.fn[v, 0, 11, 8] = (G.fn[v, 0, 11, 8]
                                         + tmg * G.wife[C19(k - v)]
                                         * bd[k, 8] * G.pslr)
