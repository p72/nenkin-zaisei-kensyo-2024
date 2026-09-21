# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/siml.cpp の忠実移植（1年度ぶんの推計）
===========================================================
475 行。`sepsd.cpp` が `k = KIJUN + 1 〜 KE` の 104 年度ぶん呼ぶ、
推計の本体。

    simlg(x, xrb)          被保険者を1歳進める（年齢の降順）
    simlbzw(x, t)          標準報酬と平均標準報酬額
    simlbzw0(x)            同（`t == 0`）
    saitesho(x, t)         障害の新規裁定
    saiteizohiho(x, t)     被保険者死亡の遺族
    saiteizojuk(x)         受給者死亡の遺族
    saitezai(x, t)         在職のままの裁定
    saitetai(x, t)         退職しての裁定
    simlrhnf(i, x, xx, xxr) 受給者を1歳進める
    simlrhnf0(i)           0歳の初期化
    simlrhnfsen(x)         長期加入者の特例を1歳進める
    simlrhnfsen60()        同じく60歳の初期化

年齢の向きが処理で違う
----------------------
```c
REV_FOR(x, xend, 15)     … simlg / simlbzw（高い年齢から）
FOR(x, 15, xend)         … saitesho / saiteizohiho（低い年齢から）
REV_FOR(x, xend, 55)     … saitezai
FOR(x, 55, xend)         … saitetai
REV_FOR(x, 115, 1)       … simlrhnf
```

`simlg` は `x - 1` から `x` を作るので**高い年齢から**回さないと
前年の値が壊れる。`saitezai` も `gd`（在職の待機）が
`x - 1` を見るので降順。逆に `saitesho` は年齢の向きに依らない。

`x >= 70 + k - KIJUN` は「足元で既に70歳以上だった人」
------------------------------------------------------
```c
REV_FOR(x, xend, 15) {
  if(x < 70 + k-KIJUN || pseid != 0) {
    … simlg() を呼ぶ …
  } else {
    … q2 だけ外枠から逆算する …
  }
```

`70 + k - KIJUN` は「2021年度に70歳だった人が `k` 年度で何歳か」。
それより上は被保険者の推計をせず、`q2`（死亡率）を外枠の人数から
逆算するだけ。厚年（`pseid == 0`）だけの扱いで、共済は
全年齢 `simlg()` を通す。

旧法（1946年度より前の生まれ）を `i + 4` へ移す
-----------------------------------------------
```c
FOR(xx, 0, 15) FOR(i, 1, 4) {
  if(k-x <= -75 && rn.AT(x, xx, i) > 1.0e-6) {
    rn.AT(x, xx, i + 4) = rn.AT(x, xx, i);
    …
    rn.AT(x, xx, i) = 0.0;
```

`k - x <= -75` は生年度が 1925年度以前。新法の 1〜4 で裁定された
ぶんを旧法の 5〜8 に移す。`fnhik` `fnmin` は
**`j` が 1・10・13・22 のときだけ**移す（他は `fn` から作り直せるので）。

`rhantei` は `i == 1` の `x == xrb` を飛ばすが `fhantei` は飛ばさない
--------------------------------------------------------------------
```c
if(x == xrb){
    if(i != 1){                      /* ← rhantei 側だけにある */
        rcoe = 0.0;
        if(s == 1 && i == 1) rcoe = 0.36;   /* i != 1 なので届かない */
        …
        if(i == 1 || i == 2){               /* i == 2 だけ届く */
            rhantei.AT(x, xx, i) = - (rhantei.AT(x, xx, 3) + rhantei.AT(x, xx, 4)) * rcoe;
        }
```

同じ形の `fhantei` の方には `if(i != 1)` が無く、`i == 1` でも
`-(fhantei[3] + fhantei[4]) * fcoe` を入れる。つまり

- **受給権者数の判定補正**（`rhantei`）の `i == 1` は
  `x == xrb` で**代入されず、前年度の値が残る**
- **年金額の判定補正**（`fhantei`）の `i == 1` はちゃんと入る

`if(i != 1)` の中に `if(s == 1 && i == 1) rcoe = 0.36;` が
2行あるのも、`i != 1` を後から足した跡と読める。
`検証/原本の不具合.md` の E31。**そのまま写す。**

`i` のループは `REV_FOR(i, 4, 1)`（4 → 1）なので、`i == 2` が
`rhantei[3]` `rhantei[4]` を読むときには既に入っている。
"""
from glva import G
from sepsstd import fmt, std_max, std_min, subc
from setconst import KIJUN

from simlbzw import simlbzw, simlbzw0
from simlg import simlg
from simlrhnf import (simlrhnf, simlrhnf0, simlrhnfsen, simlrhnfsen60)
from simlsaite1 import saitesho, saiteizohiho, saiteizojuk
from simlsaite2 import saitetai, saitezai
from sknr import sknr

__all__ = ["siml"]


def siml():
    """siml.cpp:6 の忠実移植。"""
    k = G.k
    s = G.s
    pseid = G.pseid
    xend = G.xend
    tend = G.tend
    key = G.key
    psly = G.psly

    r = G.r
    rn = G.rn
    hnn = G.hnn
    fn = G.fn
    fnhik = G.fnhik
    fnmin = G.fnmin

    if k == KIJUN + 1:
        subc(G.y, 14, 115, 0, 100, 0, 3)
        subc(G.ypt, 14, 115, 0, 100, 0, 3)

        subc(G.bbnp, 14, 115, 0, 100)
        for x in range(15, xend - 1 + 1):
            for t in range(0, tend - 2 + 1):
                if G.g[x, t] - G.gpt[x, t] > 1.0e-6:
                    G.bbnp[x, t] = ((G.bb[x, t] * G.g[x, t]
                                     - G.bbpt[x, t] * G.gpt[x, t])
                                    / (G.g[x, t] - G.gpt[x, t]))
                else:
                    G.bbnp[x, t] = 0.0

        subc(G.gzpt, 14, 115, 0, 100)
        subc(G.gnpt, 14, 115, 0, 100)
        subc(G.gnnpt, 4, 115)
        subc(G.gd, 55, 65, 0, 100)

    # ---- 被保険者を1歳進める（高い年齢から）----
    for x in range(xend, 15 - 1, -1):
        if x < 70 + k - KIJUN or pseid != 0:
            sknr(k, x)
            G.xrb = max(60, G.xrb)
            simlg(x, G.xrb)
        else:
            if G.l[k - 1, s, x - 1] > 1.0e-6:
                G.q2[k, x] = 1.0 - std_min(
                    1.0, G.l[k, s, x] / G.l[k - 1, s, x - 1])
                if G.q2[k, x] < G.q[k, x, 1]:
                    print(fmt("  [log] (q2[外枠] < q[生命表]) = "
                              "(%lf < %lf); (s, k, x) = (%d, %d, %d)\n",
                              G.q2[k, x], G.q[k, x, 1], s, k, x), end="")
            else:
                G.q2[k, x] = 1.0

    # ---- 標準報酬と平均標準報酬額 ----
    if key == 13 and k >= psly:
        pass
    else:
        for x in range(xend, 15 - 1, -1):
            for t in range(tend - 1, 1 - 1, -1):
                simlbzw(x, t)
            simlbzw0(x)

    subc(rn, 0, 115, 0, 15, 1, 13)
    subc(fn, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(fnhik, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(fnmin, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(hnn, 0, 115, 0, 15, 1, 13, 1, 2)
    subc(G.pshnn, 0, 115, 0, 15, 1, 13)
    subc(G.rsenn, 60, 70)
    subc(G.fsenn, 60, 70, 1, 23)
    subc(G.fsennhik, 60, 70, 1, 23)
    subc(G.fsennmin, 60, 70, 1, 23)
    subc(G.hnsenn, 60, 70, 1, 2)
    subc(G.pshnsenn, 60, 70)

    calc_shinshoizo = True
    if key == 12:
        if k >= psly and (G.pslsi == 0 or G.pslsi == 2):
            calc_shinshoizo = False
    elif key == 13:
        if k >= psly:
            calc_shinshoizo = False

    if calc_shinshoizo:
        for x in range(15, xend + 1):
            for t in range(0, tend - 1 + 1):
                saitesho(x, t)
        for x in range(15, xend + 1):
            for t in range(0, tend - 1 + 1):
                saiteizohiho(x, t)

    if (key == 12 or key == 13) and k >= psly and G.pslsi == 2:
        pass
    else:
        for x in range(15, 115 + 1):
            saiteizojuk(x)

    if key == 13 and k >= psly:
        pass
    else:
        for x in range(xend, 55 - 1, -1):
            for t in range(0, tend - 1 + 1):
                if G.z[x, t, 0, 0] < 1.0 - 1.0e-6 and x < 65:
                    continue
                saitezai(x, t)

        for x in range(55, xend + 1):
            for t in range(0, tend - 1 + 1):
                if G.ze[x, t, 0, 0] < 1.0 - 1.0e-6 and x < 65:
                    continue
                saitetai(x, t)
            # 1925年度以前の生まれを旧法（i + 4）へ移す
            for xx in range(0, 15 + 1):
                for i in range(1, 4 + 1):
                    if k - x <= -75 and rn[x, xx, i] > 1.0e-6:
                        rn[x, xx, i + 4] = rn[x, xx, i]
                        hnn[x, xx, i + 4, 1] = hnn[x, xx, i, 1]
                        hnn[x, xx, i + 4, 2] = hnn[x, xx, i, 2]
                        G.pshnn[x, xx, i + 4] = G.pshnn[x, xx, i]
                        rn[x, xx, i] = 0.0
                        hnn[x, xx, i, 1] = 0.0
                        hnn[x, xx, i, 2] = 0.0
                        G.pshnn[x, xx, i] = 0.0
                        for j in range(1, 23 + 1):
                            fn[x, xx, i + 4, j] = fn[x, xx, i, j]
                            fn[x, xx, i, j] = 0.0
                            if j == 1 or j == 10 or j == 13 or j == 22:
                                fnhik[x, xx, i + 4, j] = fnhik[x, xx, i, j]
                                fnmin[x, xx, i + 4, j] = fnmin[x, xx, i, j]
                                fnhik[x, xx, i, j] = 0.0
                                fnmin[x, xx, i, j] = 0.0

    # ---- 受給者を1歳進める ----
    for i in range(1, 13 + 1):
        for x in range(115, 1 - 1, -1):
            sknr(k, x)
            G.xxr = max(60, G.xxr)
            G.xrb = max(60, G.xrb)

            for xx in range(0, 15 + 1):
                if i >= 5 and xx != 0:
                    continue
                simlrhnf(i, x, xx, G.xxr)

            if i == 12 and x >= 19:
                tmz = G.rc[s, k, x]
                tmx = (G.f[x, 0, i, 2]
                       + G.f[x, 0, i, 3]
                       + G.f[x, 0, i, 11]
                       - G.f[x, 0, i, 15]
                       - G.f[x, 0, i, 16] * 3.0 / 4.0
                       - G.f[x, 0, i, 17] * tmz
                       - G.f[x, 0, i, 18] * (1.0 - tmz))
                if tmx < 0.0:
                    tmy = (-G.f[x, 0, i, 2]
                           - G.f[x, 0, i, 3]
                           + G.f[x, 0, i, 15]
                           + G.f[x, 0, i, 16] * 3.0 / 4.0)
                    G.f[x, 0, i, 11] = (tmy
                                        + G.f[x, 0, i, 17] * tmz
                                        + G.f[x, 0, i, 18] * (1.0 - tmz))
        simlrhnf0(i)

    for x in range(70, 61 - 1, -1):
        simlrhnfsen(x)

    simlrhnfsen60()

    # ---- パートの適用拡大で老齢から在職へ移す ----
    if pseid == 0 and s <= 2:
        if k == KIJUN + 1:
            subc(G.fpart, 60, 70, 0, 15, 1, 2)
            subc(G.fpart2, 60, 70, 0, 15, 1, 2)
        if k == G.partyr3:
            for x in range(60, 70 + 1):
                sknr(k, x)
                if x <= G.xrb:
                    continue
                tmp = 0.0
                for xx in range(0, 15 + 1):
                    tmp += r[x, xx, 1] + r[x, xx, 3]
                tmq = G.lpt1[k, s, x] * G.rt[k, G.xrb]
                tmq = std_min(tmq, tmp)
                if tmp > 1.0e-6:
                    for xx in range(0, 15 + 1):
                        tmr = r[x, xx, 1] * tmq / tmp
                        tms = r[x, xx, 3] * tmq / tmp
                        r[x, xx, 1] -= tmr
                        r[x, xx, 3] -= tms
                        if x < 65:
                            r[x, xx, 2] += tmr
                            r[x, xx, 4] += tms
                        G.fpart[x, xx, 1] += G.f[x, xx, 1, 1] * tmq / tmp
                        G.fpart[x, xx, 2] += G.f[x, xx, 3, 1] * tmq / tmp
        if G.flg_part >= 1 and k == G.partyr4:
            for x in range(60, 70 + 1):
                sknr(k, x)
                if x <= G.xrb:
                    continue
                tmp2 = 0.0
                for xx in range(0, 15 + 1):
                    tmp2 += r[x, xx, 1] + r[x, xx, 3]
                tmq2 = ((G.lpt2[k, s, x] + G.lpt3[k, s, x]
                         + G.lpt4[k, s, x]) * G.rt[k, G.xrb])
                tmq2 = std_min(tmq2, tmp2)
                if tmp2 > 1.0e-6:
                    for xx in range(0, 15 + 1):
                        tmr2 = r[x, xx, 1] * tmq2 / tmp2
                        tms2 = r[x, xx, 3] * tmq2 / tmp2
                        r[x, xx, 1] -= tmr2
                        r[x, xx, 3] -= tms2
                        if x < 65:
                            r[x, xx, 2] += tmr2
                            r[x, xx, 4] += tms2
                        G.fpart2[x, xx, 1] += (G.f[x, xx, 1, 1]
                                               * tmq2 / tmp2)
                        G.fpart2[x, xx, 2] += (G.f[x, xx, 3, 1]
                                               * tmq2 / tmp2)

        if k > G.partyr3:
            for x in range(70, 61 - 1, -1):
                tmr = 1.0 - G.q2[k, x]
                if x <= 67:
                    tms = 1.0 + G.hh[k]
                else:
                    tms = 1.0 + G.ci[k]
                for xx in range(0, 15 + 1):
                    G.fpart[x, xx, 1] = G.fpart[x - 1, xx, 1] * tmr * tms
                    G.fpart[x, xx, 2] = G.fpart[x - 1, xx, 2] * tmr * tms
                    if G.flg_part >= 1 and k == G.partyr4:
                        G.fpart[x, xx, 1] += G.fpart2[x, xx, 1]
                        G.fpart[x, xx, 2] += G.fpart2[x, xx, 2]
            for xx in range(0, 15 + 1):
                G.fpart[60, xx, 1] = 0.0
                G.fpart[60, xx, 2] = 0.0

    # ---- 足元の実績に合わせる判定補正（rhantei / fhantei）----
    if G.flg_hantei == 0 and pseid == 0 and s <= 2:
        _hantei()

    # ---- 過去分試算のために足元を控える ----
    if key == 12 and k == psly - 1:
        for x in range(15, xend - 1 + 1):
            for t in range(0, tend - 1 + 1):
                for i in range(0, 1 + 1):
                    for j in range(0, 6 + 1):
                        G.psz[x, t, i, j] = G.z[x, t, i, j]
                        G.psze[x, t, i, j] = G.ze[x, t, i, j]
        for x in range(0, 114 + 1):
            if 60 <= x <= 70:
                G.pshnsen[x] = G.rsen[x]
            for xx in range(0, 15 + 1):
                for i in range(1, 13 + 1):
                    G.pshn[x, xx, i] = r[x, xx, i]


def _hantei():
    """siml.cpp:322-455。足元の実績に合わせる判定補正。"""
    k = G.k
    s = G.s
    xend = G.xend
    rn = G.rn
    fn = G.fn
    routsu = G.routsu
    rhantei = G.rhantei
    fhantei = G.fhantei

    for i in range(4, 1 - 1, -1):
        for x in range(xend, 60 - 1, -1):
            sknr(k, x)
            xxr = G.xxr
            xrb = G.xrb
            for xx in range(0, 15 + 1):
                if xx != 0:
                    continue

                # ---- 受給権者数の判定補正 ----
                if x == xrb:
                    # `i != 1` があるので i == 1 は代入されない（E31）
                    if i != 1:
                        rcoe = 0.0
                        if s == 1 and i == 1:
                            rcoe = 0.36        # i != 1 なので届かない
                        if s == 1 and i == 2:
                            rcoe = 0.64
                        if s == 2 and i == 1:
                            rcoe = 0.60        # 同じく届かない
                        if s == 2 and i == 2:
                            rcoe = 0.40

                        if i == 1 or i == 2:
                            rhantei[x, xx, i] = -(rhantei[x, xx, 3]
                                                  + rhantei[x, xx, 4]) * rcoe
                        if i == 3 or i == 4:
                            rhantei[x, xx, i] = (rn[x, xx, i]
                                                 * (routsu[s, i, 1] - 1.0))
                elif ((i == 2 or i == 4) and k == KIJUN + 1
                      and 65 <= x <= 70):
                    rtemp = 0.0
                    if i == 2 and s == 1:
                        rtemp = routsu[s, i, 1] - 0.06
                    if i == 4 and s == 1:
                        rtemp = routsu[s, i, 1] + 0.13
                    if i == 2 and s == 2:
                        rtemp = routsu[s, i, 1] - 0.06
                    if i == 4 and s == 2:
                        rtemp = routsu[s, i, 1] + 0.03
                    rhantei[x, xx, i] = rn[x, xx, i] * (rtemp - 1.0)
                elif (((i == 2 or i == 4) and s == 1 and k == KIJUN + 2
                       and x == 65)
                      or ((i == 2 or i == 4) and s == 2
                          and ((k == KIJUN + 2 and x == 65)
                               or (k == KIJUN + 3 and x == 65)))):
                    rhantei[x, xx, i] = (rn[x, xx, i]
                                         * (routsu[s, i, 1] - 1.0))
                else:
                    if i == 1 or i == 3:
                        rhantei[x, xx, i] = (rhantei[x - 1, xx, i]
                                             * (1.0 - G.q[k, x, 1]))
                    if i == 2 or i == 4:
                        rhantei[x, xx, i] = (rhantei[x - 1, xx, i]
                                             * (1.0 - G.q2[k, x]))

                if (k == KIJUN + 1 and (i == 1 or i == 3)
                        and ((s == 1 and x >= 65) or (s == 2 and x >= 63))):
                    rhantei[x, xx, i] = 0.0
                if (k == KIJUN + 1 and (i == 2 or i == 4) and x >= 71):
                    rhantei[x, xx, i] = 0.0

                # ---- 年金額の判定補正 ----
                for j in range(1, 23 + 1):
                    if not (j == 1 or (3 <= j <= 6) or j == 14 or j == 23):
                        continue

                    if (3 <= j <= 6) or j == 23:
                        n = 1
                    if j == 1:
                        n = 2
                    if j == 14:
                        n = 3

                    if x == xrb:
                        # ここには `i != 1` が無い（E31）
                        fcoe = 0.0
                        if (3 <= j <= 6) or j == 23:
                            if s == 1 and i == 1:
                                fcoe = 0.36
                            if s == 1 and i == 2:
                                fcoe = 0.64
                            if s == 2 and i == 1:
                                fcoe = 0.60
                            if s == 2 and i == 2:
                                fcoe = 0.40
                        if j == 1:
                            if s == 1 and i == 1:
                                fcoe = 0.11
                            if s == 1 and i == 2:
                                fcoe = 0.89
                            if s == 2 and i == 1:
                                fcoe = 0.46
                            if s == 2 and i == 2:
                                fcoe = 0.54
                        if j == 14:
                            if s == 1 and i == 1:
                                fcoe = 0.15
                            if s == 1 and i == 2:
                                fcoe = 0.85
                            if s == 2 and i == 1:
                                fcoe = 0.50
                            if s == 2 and i == 2:
                                fcoe = 0.50

                        if i == 1 or i == 2:
                            fhantei[x, xx, i, j] = -(
                                fhantei[x, xx, 3, j]
                                + fhantei[x, xx, 4, j]) * fcoe
                        if i == 3 or i == 4:
                            fhantei[x, xx, i, j] = (
                                fn[x, xx, i, j] * (routsu[s, i, n] - 1.0))
                    elif ((i == 2 or i == 4) and k == KIJUN + 1
                          and 65 <= x <= 70):
                        ftemp = 0.0
                        if (3 <= j <= 6) or j == 23:
                            if i == 2 and s == 1:
                                ftemp = routsu[s, i, n] - 0.06
                            if i == 4 and s == 1:
                                ftemp = routsu[s, i, n] + 0.13
                            if i == 2 and s == 2:
                                ftemp = routsu[s, i, n] - 0.06
                            if i == 4 and s == 2:
                                ftemp = routsu[s, i, n] + 0.03
                        if j == 1:
                            if i == 2 and s == 1:
                                ftemp = routsu[s, i, n] - 0.00
                            if i == 4 and s == 1:
                                ftemp = routsu[s, i, n] + 0.03
                            if i == 2 and s == 2:
                                ftemp = routsu[s, i, n] - 0.01
                            if i == 4 and s == 2:
                                ftemp = routsu[s, i, n] + 0.01
                        if j == 14:
                            if i == 2 and s == 1:
                                ftemp = routsu[s, i, n] - 0.01
                            if i == 4 and s == 1:
                                ftemp = routsu[s, i, n] + 0.01
                            if i == 2 and s == 2:
                                ftemp = routsu[s, i, n] - 0.02
                            if i == 4 and s == 2:
                                ftemp = routsu[s, i, n] + 0.01
                        fhantei[x, xx, i, j] = (fn[x, xx, i, j]
                                                * (ftemp - 1.0))
                    elif (((i == 2 or i == 4) and s == 1
                           and k == KIJUN + 2 and x == 65)
                          or ((i == 2 or i == 4) and s == 2
                              and ((k == KIJUN + 2 and x == 65)
                                   or (k == KIJUN + 3 and x == 65)))):
                        fhantei[x, xx, i, j] = (
                            fn[x, xx, i, j] * (routsu[s, i, n] - 1.0))
                    else:
                        if i == 1 or i == 3:
                            fhantei[x, xx, i, j] = (
                                fhantei[x - 1, xx, i, j]
                                * (1.0 - G.q[k, x, 1]))
                        if i == 2 or i == 4:
                            fhantei[x, xx, i, j] = (
                                fhantei[x - 1, xx, i, j]
                                * (1.0 - G.q2[k, x]))
                    if (k == KIJUN + 1 and (i == 1 or i == 3)
                            and ((s == 1 and x >= 65)
                                 or (s == 2 and x >= 63))):
                        fhantei[x, xx, i, j] = 0.0
                    if (k == KIJUN + 1 and (i == 2 or i == 4)
                            and x >= 71):
                        fhantei[x, xx, i, j] = 0.0
