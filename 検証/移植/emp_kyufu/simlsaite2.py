# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/simlsaite2.cpp の忠実移植（在職と退職の老齢の裁定）
========================================================================
516 行。2つの関数を持つ。

    saitezai(x, t)   **在職**のまま支給開始年齢に達した人の裁定（`i = 2, 4`）
    saitetai(x, t)   **退職**して裁定される人の裁定（`i = 1, 3`）

`i` の意味は `dtst.cpp` と同じで

| `i` | 中身 |
|---|---|
| 1 | 新法の老齢（退職） |
| 2 | 新法の老齢（在職） |
| 3 | 通算老齢（退職） |
| 4 | 通算老齢（在職） |

`ris[xx]` — 繰上げ繰下げの選択率
--------------------------------
`krgn()` が作った `riss[k][65-xx][xxr][s][i]` から「60〜64歳で
繰上げる割合」を取り、残りを `ris[0]`（繰上げない）にする。
`xx` は 1〜5 が繰上げ（64〜60歳）、6〜10 が繰下げ（66〜70歳）。

```c
ris.AT(0)=1.0;
FOR(xx, 1, 5) {
  if(xxr > 65-xx) ris.AT(xx)=riss.AT(k, 65-xx, xxr, s, 1);
  else            ris.AT(xx)=0.0;
}
FOR(xx, 1, 5) ris.AT(0)=ris.AT(0)-ris.AT(xx);
```

`taizai` — 在職のまま裁定する年齢
---------------------------------
```c
taizai = 0;
if( (xend > 65 && x == 65) || (xend > 70 && x == 70) || … ) taizai = 1;
else if( (xend > 66 && x == 66) || … (xend > 69 && x == 69) ) taizai = 2;
```

65歳・70歳（`taizai = 1`）と 66〜69歳（`taizai = 2`）で、
在職のまま裁定する。すぐ下に

```c
if(taizai == 1 || taizai == 2) {
  ...
  if(taizai == 1 || taizai == 2) {      /* 同じ条件を2回 */
```

と**同じ条件の入れ子**がある。内側は常に真。

定額部分に J1 の写し間違いが掛かる
----------------------------------
```c
tmf = tmg * fl * flt.AT(C19(max(-74, k-x))) * bd.AT(k, 2) * tn;
```

`flt` は `seid()` が作った定額部分の生年別読替率で、
**1936年度生まれのぶんが 0.369（公表値は 1.369）**。
`検証/原本の不具合.md` の J1。この式が4か所（113・212・274・479行）
にあって、どれも同じ。

`ge` を削って `ze` `we` をゼロにする
------------------------------------
裁定して受給者になった人は受給待期から抜くので、
`ge.AT(x, t)` を減らし、ぴったり 0 になったら
`ze` `we` の同じ (x, t) をゼロクリアする。

```c
sst::subc4(ze, x,x, t,t, 0,1, 0,9);
sst::subc5(we, x,x, t,t, 0,0, 0,7, 0,3);
```

`assert` が3つ効いている
------------------------
```c
assert(abs(ged-y.AT(x, t, 1)) <= 1.0e-6);
assert(abs(tmris) <= 1.0e-8);
assert(y.AT(x, t, 1)-ged > -1.0e-8);
```

配り切ったことを確かめる検査で、`||` ではなく単独なので**効いている**
（F16 の効かない `assert` とは別）。移植版も同じ条件で入れる。
"""
from glva import G
from sepsstd import c_round, fmt, std_max, std_min, subc
from setconst import C19, KIJUN

from dsitk import dsitk

__all__ = ["saitezai", "saitetai"]


def saitezai(x, t):
    """simlsaite2.cpp:8。在職のまま支給開始年齢に達した人の裁定。"""
    k = G.k
    s = G.s
    pseid = G.pseid
    xend = G.xend

    r = G.r
    rn = G.rn
    fn = G.fn
    bd = G.bd
    adt = G.adt

    ris = [0.0] * 16
    tmrp = [0.0] * 16

    tmo = G.z[x, t, 0, 0]
    bk, bk2, bk3 = dsitk(x, t, 2)

    xr = G.xr
    xxr = G.xxr
    xrb = G.xrb
    it = G.it

    i = 0
    if (((x == xr and x < 65)
         or (x > xr and x < 65 and x <= xrb and xrb > 60))
            and it != 3 and it != 4):
        i = 2
    if (((((x == xr and x < 65)
           or (x > xr and x < 65 and x <= xrb and xrb > 60))
          and (it == 3 or it == 4) and 1.0 - 1.0e-6 <= tmo))
            or (x > xrb and x < 65
                and 1.0 - 1.0e-6 <= tmo and tmo < 2.0 - 1.0e-6)):
        i = 4

    if i == 2 or i == 4:

        ris[0] = 1.0
        for xx in range(1, 15 + 1):
            ris[xx] = 0.0

        if xr >= 60:
            for xx in range(1, 5 + 1):
                if xxr > 65 - xx:
                    ris[xx] = G.riss[k, 65 - xx, xxr, s, 1]
                else:
                    ris[xx] = 0.0
            for xx in range(1, 5 + 1):
                ris[0] = ris[0] - ris[xx]
            tmris = 0.0
            for xx in range(0, 5 + 1):
                if 65 - xx >= x:
                    tmris = tmris + ris[xx]
                else:
                    ris[xx] = 0.0
            tmris2 = 0.0
            for xx in range(0, 5 + 1):
                if tmris >= 1.0e-6:
                    ris[xx] = ris[xx] / tmris
                else:
                    if xx == 0:
                        ris[xx] = 1.0
                    else:
                        ris[xx] = 0.0
                tmris2 = tmris2 + ris[xx]
            assert tmris2 - 1.0 <= 1.0e-6

        if k == KIJUN + 1:
            if xrb > 60 and x > 60 and x <= xrb and t > 0:
                for xx in range(0, 5 + 1):
                    tmgd = ((r[x - 1, xx, 2] + r[x - 1, xx, 4])
                            * (1.0 - G.q2[k, x]) * G.g[x, t]
                            / G.l[k, s, x])
                    if xrb > 60 and x < xrb:
                        G.gd[x, t] = G.gd[x, t] + tmgd
                    else:
                        G.gd[x, t] = 0.0
            else:
                G.gd[x, t] = 0.0
        else:
            if xrb > 60 and x > 60 and x <= xrb and t > 0:
                G.gd[x, t] = G.gd[x - 1, t - 1] * (1.0 - G.q2[k, x])
            else:
                G.gd[x, t] = 0.0

        for xx in range(0, 5 + 1):
            if x < 60 and xx >= 1:
                continue
            tmg = ris[xx] * (G.g[x, t] - G.gd[x, t])
            if xrb > 60 and x < xrb and x != 65 - xx:
                tmg = 0.0

            if xrb > 60 and x < xrb:
                G.gd[x, t] = G.gd[x, t] + tmg

            rn[x, xx, i] = rn[x, xx, i] + tmg
            G.hnn[x, xx, i, 1] = G.hnn[x, xx, i, 1] + tmg * G.tz[1]
            G.hnn[x, xx, i, 2] = G.hnn[x, xx, i, 2] + tmg * G.tz[2]
            G.pshnn[x, xx, i] = G.pshnn[x, xx, i] + tmg * G.pslr

            fn[x, xx, i, 1] = fn[x, xx, i, 1] + tmg * bk
            G.fnhik[x, xx, i, 1] = G.fnhik[x, xx, i, 1] + tmg * bk2
            G.fnmin[x, xx, i, 1] = G.fnmin[x, xx, i, 1] + tmg * bk3

            # `flt` に J1 の写し間違いが入っている
            tmf = (tmg * G.fl * G.flt[C19(max(-74, k - x))]
                   * bd[k, 2] * G.tn)
            fn[x, xx, i, 2] = fn[x, xx, i, 2] + tmf
            tmo = (tmg * G.fl1 * bd[k, 14]
                   * std_min(G.ta / G.can[C19(max(-74, k - x))], 1.0))
            if G.flg_sigo >= 1:
                tmo = (tmo * std_max(G.can[C19(max(-74, k - x))], 40.0)
                       / 40.0)
            fn[x, xx, i, 14] = fn[x, xx, i, 14] + tmo

            do_calc = True
            if ((G.key == 12 or G.key == 13) and G.pslsi2 == 1
                    and k >= G.psly):
                do_calc = False
            if s >= 4:
                do_calc = False

            if do_calc:
                if i == 2 or i == 4:
                    fn[x, xx, i, 4] = (fn[x, xx, i, 4]
                                       + tmg * adt[1] * bd[k, 4] * G.pslr)
                    fn[x, xx, i, 23] = (fn[x, xx, i, 23]
                                        + tmg
                                        * G.sadt[C19(max(-74, k - x))]
                                        * bd[k, 23] * G.pslr)
                    fn[x, xx, i, 5] = (fn[x, xx, i, 5]
                                       + tmg * adt[2] * bd[k, 5] * G.pslr)
                    fn[x, xx, i, 6] = (fn[x, xx, i, 6]
                                       + tmg
                                       * G.cadt[C19(k - int(
                                           c_round(G.ns[k, x])))]
                                       * bd[k, 6] * G.pslr)

    # ------------------------------------------------------------------
    # 在職のまま裁定する年齢（65歳・70歳、66〜69歳）
    # ------------------------------------------------------------------
    taizai = 0
    if ((xend > 65 and x == 65) or (xend > 70 and x == 70)
            or (xend > 75 and x == 75 and G.flg_hiho70 == 1
                and k >= G.hiho70yr)
            or (xend > 85 and x == 85 and G.flg_hiho70 == 2
                and k >= G.hiho70yr)):
        taizai = 1
    elif ((xend > 66 and x == 66) or (xend > 67 and x == 67)
          or (xend > 68 and x == 68) or (xend > 69 and x == 69)):
        taizai = 2

    if taizai == 1 or taizai == 2:
        if it == 1 or it == 2:
            i = 2
        if it == 3 or it == 4:
            i = 4

        if pseid == 0 and s <= 2:
            tml = G.l[k, s, x] + G.lpt[k, s, x]
        else:
            tml = G.l[k, s, x]
        tmrps = 0.0
        for xx in range(0, 15 + 1):
            tmrp[xx] = ((r[x - 1, xx, 2] + r[x - 1, xx, 4]
                         + r[x - 1, xx, 6] + r[x - 1, xx, 8])
                        * (1.0 - G.q2[k, x]))
            tmrps = tmrps + tmrp[xx]

        # 原本は同じ条件をもう1回入れ子にしている（常に真）
        if taizai == 1 or taizai == 2:
            ris[0] = 1.0
            for xx in range(1, 10 + 1):
                if tml > 1.0e-6 and tml >= tmrps:
                    ris[xx] = tmrp[xx] / tml
                else:
                    if tmrps > 1.0e-6:
                        ris[xx] = tmrp[xx] / tmrps
                    else:
                        ris[xx] = 0.0
                ris[0] = ris[0] - ris[xx]
            assert ris[0] >= 0.0

        for xx in range(0, 15 + 1):
            tmg = ris[xx] * G.g[x, t]
            tmgp = 0.0
            if s <= 2 and pseid == 0:
                if k >= G.partyr3 and x - k > xrb - G.partyr3:
                    if G.lpt[k, s, x] > 1.0e-6:
                        tmgp += (ris[xx] * G.gpt[x, t] * G.lpt1[k, s, x]
                                 / G.lpt[k, s, x] * G.rt[G.partyr3, xrb])
                if (G.flg_part >= 1 and k >= G.partyr4
                        and x - k > xrb - G.partyr4):
                    if G.lpt[k, s, x] > 1.0e-6:
                        tmgp += (ris[xx] * G.gpt[x, t]
                                 * (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                                    + G.lpt4[k, s, x]) / G.lpt[k, s, x]
                                 * G.rt[G.partyr4, xrb])

            rn[x, xx, i] = rn[x, xx, i] + tmg
            G.hnn[x, xx, i, 1] = G.hnn[x, xx, i, 1] + tmg * G.tz[1]
            G.hnn[x, xx, i, 2] = G.hnn[x, xx, i, 2] + tmg * G.tz[2]
            G.pshnn[x, xx, i] = G.pshnn[x, xx, i] + tmg * G.pslr

            fn[x, xx, i, 1] = fn[x, xx, i, 1] + tmg * bk
            G.fnhik[x, xx, i, 1] = G.fnhik[x, xx, i, 1] + tmg * bk2
            G.fnmin[x, xx, i, 1] = G.fnmin[x, xx, i, 1] + tmg * bk3

            tmf = (tmg * G.fl * G.flt[C19(max(-74, k - x))]
                   * bd[k, 2] * G.tn)
            fn[x, xx, i, 2] = fn[x, xx, i, 2] + tmf
            tmo = (tmg * G.fl1 * bd[k, 14]
                   * std_min(G.ta / G.can[C19(max(-74, k - x))], 1.0))
            if G.flg_sigo >= 1:
                tmo = (tmo * std_max(G.can[C19(max(-74, k - x))], 40.0)
                       / 40.0)
            fn[x, xx, i, 14] = fn[x, xx, i, 14] + tmo

            tmf = std_max(tmf - tmo, 0.0)
            fn[x, xx, i, 3] = fn[x, xx, i, 3] + tmf

            calc_flag = True
            if ((G.key == 12 or G.key == 13) and G.pslsi2 == 1
                    and k >= G.psly):
                calc_flag = False
            if s >= 4:
                calc_flag = False

            if calc_flag:
                if i == 2 or i == 4:
                    fn[x, xx, i, 4] = (fn[x, xx, i, 4]
                                       + (tmg - tmgp) * adt[1] * bd[k, 4]
                                       * G.pslr)
                    fn[x, xx, i, 23] = (fn[x, xx, i, 23]
                                        + (tmg - tmgp)
                                        * G.sadt[C19(max(-74, k - x))]
                                        * bd[k, 23] * G.pslr)
                    fn[x, xx, i, 5] = (fn[x, xx, i, 5]
                                       + (tmg - tmgp) * adt[2] * bd[k, 5]
                                       * G.pslr)
                    fn[x, xx, i, 6] = (fn[x, xx, i, 6]
                                       + (tmg - tmgp)
                                       * G.cadt[C19(k - int(
                                           c_round(G.ns[k, x])))]
                                       * bd[k, 6] * G.pslr)


def saitetai(x, t):
    """simlsaite2.cpp:243。退職して裁定される人の裁定。"""
    k = G.k
    s = G.s
    pseid = G.pseid

    r = G.r
    rn = G.rn
    fn = G.fn
    bd = G.bd
    adt = G.adt
    ge = G.ge
    y = G.y

    tmg2 = [0.0] * 16
    ris = [0.0] * 16
    tmrp = [0.0] * 16

    tmo = G.ze[x, t, 0, 0]
    bk, bk2, bk3 = dsitk(x, t, 1)

    xr = G.xr
    xxr = G.xxr
    xrb = G.xrb
    it = G.it

    if (tmo >= G.senll - 1.0e-6 and it != 2
            and x >= xrb and x < xxr and xxr > 60):
        # ---- 長期加入者の特例（44年以上）----
        tmg = ge[x, t]

        G.rsenn[x] = G.rsenn[x] + tmg
        G.hnsenn[x, 1] = G.hnsenn[x, 1] + tmg * G.tz[1]
        G.hnsenn[x, 2] = G.hnsenn[x, 2] + tmg * G.tz[2]
        G.pshnsenn[x] = G.pshnsenn[x] + tmg * G.pslr

        G.fsenn[x, 1] = G.fsenn[x, 1] + tmg * bk
        G.fsennhik[x, 1] = G.fsennhik[x, 1] + tmg * bk2
        G.fsennmin[x, 1] = G.fsennmin[x, 1] + tmg * bk3

        tmf = tmg * G.fl * G.flt[C19(max(-74, k - x))] * bd[k, 2] * G.tn
        G.fsenn[x, 2] = G.fsenn[x, 2] + tmf
        tmo = (tmg * G.fl1 * bd[k, 14]
               * std_min(G.ta / G.can[C19(max(-74, k - x))], 1.0))
        if G.flg_sigo >= 1:
            tmo = tmo * std_max(G.can[C19(max(-74, k - x))], 40.0) / 40.0
        G.fsenn[x, 14] = G.fsenn[x, 14] + tmo
        tmf = std_max(tmf - tmo, 0.0)
        G.fsenn[x, 3] = G.fsenn[x, 3] + tmf

        calc_flag = True
        if (G.key == 12 or G.key == 13) and G.pslsi2 == 1 and k >= G.psly:
            calc_flag = False
        if s >= 4:
            calc_flag = False

        if calc_flag:
            G.fsenn[x, 4] = (G.fsenn[x, 4]
                             + tmg * adt[1] * bd[k, 4] * G.pslr)
            G.fsenn[x, 23] = (G.fsenn[x, 23]
                              + tmg * G.sadt[C19(max(-74, k - x))]
                              * bd[k, 23] * G.pslr)
            G.fsenn[x, 5] = (G.fsenn[x, 5]
                             + tmg * adt[2] * bd[k, 5] * G.pslr)
            G.fsenn[x, 6] = (G.fsenn[x, 6]
                             + tmg
                             * G.cadt[C19(k - int(c_round(G.ns[k, x])))]
                             * bd[k, 6] * G.pslr)

        ge[x, t] = 0.0
        subc(G.ze, x, x, t, t, 0, 1, 0, 9)
        subc(G.we, x, x, t, t, 0, 0, 0, 7, 0, 3)

    elif x >= xr:

        if it == 1 or it == 2:
            i = 1
        if it == 3 or it == 4:
            i = 3

        for xx in range(0, 15 + 1):
            tmg2[xx] = 0.0
            ris[xx] = 0.0

        if y[x, t, 1] > 1.0e-6:
            if pseid == 0 and s <= 2:
                tmlp = G.l[k - 1, s, x - 1] + G.lpt[k - 1, s, x - 1]
            else:
                tmlp = G.l[k - 1, s, x - 1]
            tmrps = 0.0
            for xx in range(0, 15 + 1):
                tmrp[xx] = (r[x - 1, xx, 2] + r[x - 1, xx, 4]
                            + r[x - 1, xx, 6] + r[x - 1, xx, 8])
                tmrps = tmrps + tmrp[xx]

            ged = 0.0
            if xr < 60 or tmlp <= 1.0e-6:
                tmg2[0] = y[x, t, 1]
                ged = tmg2[0]
            elif x > xrb:
                if tmrps >= tmlp:
                    for xx in range(0, 15 + 1):
                        ris[xx] = tmrp[xx] / tmrps
                        tmg2[xx] = y[x, t, 1] * ris[xx]
                else:
                    if x > 65:
                        for xx in range(0, 15 + 1):
                            ris[xx] = tmrp[xx] / tmlp
                            tmg2[xx] = y[x, t, 1] * ris[xx]
                        tmg2[min(10, x - 60)] = (
                            tmg2[min(10, x - 60)]
                            + y[x, t, 1] * (tmlp - tmrps) / tmlp)
                    else:
                        for xx in range(0, 15 + 1):
                            ris[xx] = tmrp[xx] / tmlp
                            tmg2[xx] = y[x, t, 1] * ris[xx]
                        tmg2[0] = (tmg2[0]
                                   + y[x, t, 1] * (tmlp - tmrps) / tmlp)
                ged = 0.0
                for xx in range(0, 15 + 1):
                    ged = ged + tmg2[xx]
                assert abs(ged - y[x, t, 1]) <= 1.0e-6

            elif x <= xrb and xrb > 60:
                assert tmrps - tmlp <= 1.0e-6
                ris[0] = 1.0
                tmris = 1.0
                for xx in range(1, 5 + 1):
                    if 65 - xx < x:
                        ris[xx] = tmrp[xx] / tmlp
                        ris[0] = ris[0] - ris[xx]
                    else:
                        ris[xx] = G.riss[k, 65 - xx, xxr, s, 0]
                        tmris = tmris - ris[xx]
                tmris2 = ris[0]
                ris[0] = tmris
                for xx in range(0, 65 - x + 1):
                    ris[xx] = ris[xx] * tmris2

                tmris = 1.0
                for xx in range(0, 15 + 1):
                    tmris = tmris - ris[xx]
                assert abs(tmris) <= 1.0e-8

                ged = 0.0
                for xx in range(1, 5 + 1):
                    if 65 - xx < x:
                        tmg2[xx] = y[x, t, 1] * ris[xx]
                    ged = ged + tmg2[xx]
                assert y[x, t, 1] - ged > -1.0e-8

            ge[x, t] = ge[x, t] - ged
            if ge[x, t] < -1.0e-6:
                print(fmt("在老転び裁定エラー３(saiteitai) "
                          "(x, t, y, ge) = (%d, %d, %lf, %lf)\n",
                          x, t, y[x, t, 1], ge[x, t]), end="")
            elif ge[x, t] < 1.0e-6:
                ge[x, t] = 0.0

            tmrps = 0.0
            for xx in range(0, 15 + 1):
                tmrps = tmrps + tmg2[xx]
            assert tmrps - ged > -1.0e-8

        ris[0] = 1.0
        for xx in range(1, 15 + 1):
            ris[xx] = 0.0

        if 60 + k - KIJUN <= x <= 69 + k - KIJUN and x > 65:
            for xx in range(0, 15 + 1):
                ris[xx] = 0.0
            ris[min(15, x - 60)] = 1.0
        elif xr == 60 and ((xr <= x <= xrb)
                           or (k == KIJUN + 1 and x <= xxr)):
            for xx in range(1, 5 + 1):
                if xx > 65 - xxr:
                    ris[xx] = G.riss[k, 65 - xx, xxr, s, 0]
            for xx in range(1, 5 + 1):
                ris[0] = ris[0] - ris[xx]
            tmris = 0.0
            for xx in range(0, 5 + 1):
                if x <= 65 - xx:
                    tmris = tmris + ris[xx]
                else:
                    ris[xx] = 0.0
            tmris2 = 0.0
            for xx in range(0, 5 + 1):
                if tmris > 1.0e-6:
                    ris[xx] = ris[xx] / tmris
                else:
                    if xx == 0:
                        ris[xx] = 1.0
                    else:
                        ris[xx] = 0.0
                tmris2 = tmris2 + ris[xx]
            assert tmris2 - 1.0 <= 1.0e-6

        ged = 0.0
        for xx in range(0, 15 + 1):
            if x < 60 and xx >= 1:
                continue
            if x >= xrb or (x == 65 - xx and xx <= 5):
                tmg = ris[xx] * ge[x, t]
                if ((((pseid == 0 and s == 1) or pseid != 0)
                     and KIJUN - 69 <= k - x <= KIJUN - 63)
                        or ((pseid == 0 and s != 1)
                            and KIJUN - 69 <= k - x <= KIJUN - 62)):
                    tmg = tmg / std_max(
                        1.0, float((k - x + 54) - (k - KIJUN - 1)))
            else:
                tmg = 0.0
            ged = ged + tmg
            tmg = tmg + tmg2[xx]

            rn[x, xx, i] = rn[x, xx, i] + tmg
            G.hnn[x, xx, i, 1] = G.hnn[x, xx, i, 1] + tmg * G.tz[1]
            G.hnn[x, xx, i, 2] = G.hnn[x, xx, i, 2] + tmg * G.tz[2]
            G.pshnn[x, xx, i] = G.pshnn[x, xx, i] + tmg * G.pslr

            fn[x, xx, i, 1] = fn[x, xx, i, 1] + tmg * bk
            G.fnhik[x, xx, i, 1] = G.fnhik[x, xx, i, 1] + tmg * bk2
            G.fnmin[x, xx, i, 1] = G.fnmin[x, xx, i, 1] + tmg * bk3

            tmf = (tmg * G.fl * G.flt[C19(max(-74, k - x))]
                   * bd[k, 2] * G.tn)
            fn[x, xx, i, 2] = fn[x, xx, i, 2] + tmf
            tmo = (tmg * G.fl1 * bd[k, 14]
                   * std_min(G.ta / G.can[C19(max(-74, k - x))], 1.0))
            if G.flg_sigo >= 1:
                tmo = (tmo * std_max(G.can[C19(max(-74, k - x))], 40.0)
                       / 40.0)
            fn[x, xx, i, 14] = fn[x, xx, i, 14] + tmo
            tmf = std_max(tmf - tmo, 0.0)
            fn[x, xx, i, 3] = fn[x, xx, i, 3] + tmf

            calc_flag = True
            if ((G.key == 12 or G.key == 13) and G.pslsi2 == 1
                    and k >= G.psly):
                calc_flag = False
            if s >= 4:
                calc_flag = False

            if calc_flag:
                if i == 1 or i == 3:
                    fn[x, xx, i, 4] = (fn[x, xx, i, 4]
                                       + tmg * adt[1] * bd[k, 4] * G.pslr)
                    fn[x, xx, i, 23] = (fn[x, xx, i, 23]
                                        + tmg
                                        * G.sadt[C19(max(-74, k - x))]
                                        * bd[k, 23] * G.pslr)
                    fn[x, xx, i, 5] = (fn[x, xx, i, 5]
                                       + tmg * adt[2] * bd[k, 5] * G.pslr)
                    fn[x, xx, i, 6] = (fn[x, xx, i, 6]
                                       + tmg
                                       * G.cadt[C19(k - int(
                                           c_round(G.ns[k, x])))]
                                       * bd[k, 6] * G.pslr)

        ge[x, t] = ge[x, t] - ged
        if abs(ge[x, t]) < 1.0e-6:
            ge[x, t] = 0.0
            subc(G.ze, x, x, t, t, 0, 1, 0, 9)
            subc(G.we, x, x, t, t, 0, 0, 0, 7, 0, 3)
        else:
            assert ge[x, t] > -1.0e-6
