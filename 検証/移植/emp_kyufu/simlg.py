# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/simlg.cpp の忠実移植（被保険者を1歳進める）
================================================================
363 行。年齢 `x` の被保険者を、前年の `x - 1` から1歳進めて作る。
`siml()` が `FOR(x, 15, xend)` で呼ぶ。

    gz  [x][t]    継続（前年から残った人）
    gn  [x][t]    新規・再加入
    gnn [x]       年度途中の加入（`t = 0` に入れる残り）
    gez [x][t]    受給待期（加入をやめて待っている人）
    ye  [x][t]    死亡で抜けた人
    y   [x][t][j] 脱退の内訳（0 計 / 1 生存 / 2 障害 / 3 死亡）
    g   [x][t]    被保険者（`gz + gn`）
    ge  [x][t]    受給待期の残り
    q2 [k][x]     実績から逆算した死亡率
    `*pt` はパート（短時間労働者）の同じもの

`t` は**加入からの経過年**。`tend = xend - 15`。

厚年と共済で残存の式が違う
--------------------------
```c
if(pseid == 0){
    gz.AT(x, t) = g.AT(x - 1, t - 1) * (1.0 - u.AT(k, x, 0));
}else{
    gz.AT(x, t) = g.AT(x - 1, t - 1) * exp(-u.AT(k, x, 0));
}
```

厚生年金は **1 − 脱退率**、共済は **exp(−脱退力)**。`u` の意味が
制度で違う（前者は1年の率、後者は力）。

**打ち切りの入れ方も対になっている。** `kiso.cpp:282-284` は
年齢の上限（厚年 85 / 共済 70）以上で

| 制度 | 入れる値 | `simlg` の式 | 残存率 |
|---|---|---|---|
| 厚生年金 `pseid == 0` | `u[1] = 1.0` | `1.0 - u[0]` | `1 - 1 = 0` |
| 国共済・地共済 `1`/`4` | `u[0] = 1000.0` | `exp(-u[0])` | `exp(-1000) = 0` |
| 私学共済 `5` | `u[1] = 1000.0` | `exp(-u[0])` | 同じく 0 |

と入れる。**`1000.0` は `exp(-)` の側にしか入らず、`1 - u` の側には
`1.0` が入る**ので、どちらもちょうど 0 になる（`exp(-1000)` は
倍精度で 0 にアンダーフローする）。`1 - 1000 = -999` のような
符号の反転は起きない。実測でも `pseid = 0` の
`u[k][x][0]`（x = 15〜85、全年度）の最大は **1.0** で、
`1 - u` が負になる年齢は無かった。

式が2通りあるのは**意図した違い**。`検証/原本の不具合.md` の E29。

`gezz` は 116×101 の局所配列だが1行しか使わない
-----------------------------------------------
```c
v2_t gezz = VEC(double, 115, 100);
...
gezz.AT(x, t) = ge.AT(x - 1, t) * (1.0 - q.AT(k, x, 1));
```

`x` は引数で固定なので、**使うのは1行（101 要素）だけ**。
呼ばれるたびに 94KB を確保して捨てる。`siml()` は
`x` を 15〜90 で回し、`k` を 104 年度、`s` を3通りなので
のべ 23,712 回 ＝ 2.2GB ぶんの確保と解放。移植版は
長さ 101 の配列1本にする（結果は同じ）。同 F18。

`assert(gnn.AT(x) > -1.0e-6)` の直前で補正している
--------------------------------------------------
```c
if(abs(gnn.AT(x)) < 1.0e-6) {
  l.AT(k, s, x) -= gnn.AT(x);
  gnn.AT(x) = 0.0;
}
assert(gnn.AT(x) > -1.0e-6);
```

`gnn`（年度途中の加入）が丸め誤差ぶんだけずれていたら、
**被保険者数 `l` の側を動かして** 0 にそろえる。`assert` は
そのあとなので、1e-6 を超える負のずれだけが引っかかる。

`abs` は `<math.h>` 経由の `abs(double)`（= `fabs`）で、
`int abs(int)` には落ちない（手元の gcc で確かめた）。
"""
import math

from glva import G
from sepsstd import std_max, std_min

__all__ = ["simlg"]


def simlg(x, xrb):
    """simlg.cpp:6 の忠実移植。"""
    k = G.k
    s = G.s
    pseid = G.pseid
    tend = G.tend

    g = G.g
    ge = G.ge
    gpt = G.gpt
    gz = G.gz
    gzpt = G.gzpt
    gn = G.gn
    gnpt = G.gnpt
    gez = G.gez
    y = G.y
    ypt = G.ypt
    u = G.u
    lpt = G.lpt

    # 原本は 116×101 の局所配列だが、使うのは1行だけ（F18）
    gezz = [0.0] * 101

    kou2 = (s <= 2 and pseid == 0)

    # ---- 継続（前年から残る人）----
    gz[x, 0] = 0.0
    gzpt[x, 0] = 0.0
    for t in range(1, tend - 2 + 1):
        if pseid == 0:
            gz[x, t] = g[x - 1, t - 1] * (1.0 - u[k, x, 0])
        else:
            # 共済だけ exp(-u)（E29）
            gz[x, t] = g[x - 1, t - 1] * math.exp(-u[k, x, 0])

        if kou2:
            gzpt[x, t] = gpt[x - 1, t - 1] * (1.0 - u[k, x, 0])
            gz[x, t] -= gzpt[x, t]

    if pseid == 0:
        gz[x, tend - 1] = ((g[x - 1, tend - 2] + g[x - 1, tend - 1])
                           * (1.0 - u[k, x, 0]))
    else:
        gz[x, tend - 1] = ((g[x - 1, tend - 2] + g[x - 1, tend - 1])
                           * math.exp(-u[k, x, 0]))

    if kou2:
        gzpt[x, tend - 1] = ((gpt[x - 1, tend - 2] + gpt[x - 1, tend - 1])
                             * (1.0 - u[k, x, 0]))
        gz[x, tend - 1] -= gzpt[x, tend - 1]

    # ---- 受給待期の残存と死亡 ----
    for t in range(0, tend - 1 + 1):
        gezz[t] = ge[x - 1, t] * (1.0 - G.q[k, x, 1])
        G.ye[x, t] = ge[x - 1, t] - gezz[t]

    tmp = gezz[0]
    tmq = 0.0
    tmv = 0.0
    for t in range(1, tend - 1 + 1):
        tmp += gezz[t]
        tmq += gz[x, t]
        tmv += gzpt[x, t]

    # ---- 継続が被保険者数を超えたら比例で落とす ----
    if G.l[k, s, x] < tmq:
        for t in range(1, tend - 1 + 1):
            if tmq > 1.0e-6:
                gz[x, t] *= G.l[k, s, x] / tmq
            else:
                gz[x, t] = 0.0
        tmq = G.l[k, s, x]

    if k == G.partyr3 and kou2:
        if lpt[k, s, x] - G.lpt1[k, s, x] < tmv:
            for t in range(1, tend - 1 + 1):
                if tmv > 1.0e-6:
                    gzpt[x, t] *= (lpt[k, s, x] - G.lpt1[k, s, x]) / tmv
                else:
                    gzpt[x, t] = 0.0
            tmv = lpt[k, s, x] - G.lpt1[k, s, x]
    elif G.flg_part >= 1 and k == G.partyr4 and kou2:
        rest = (lpt[k, s, x] - G.lpt2[k, s, x] - G.lpt3[k, s, x]
                - G.lpt4[k, s, x])
        if rest < tmv:
            for t in range(1, tend - 1 + 1):
                if tmv > 1.0e-6:
                    gzpt[x, t] *= (lpt[k, s, x] - G.lpt2[k, s, x]
                                   - G.lpt3[k, s, x] - G.lpt4[k, s, x]) / tmv
                else:
                    gzpt[x, t] = 0.0
            tmv = (lpt[k, s, x] - G.lpt2[k, s, x] - G.lpt3[k, s, x]
                   - G.lpt4[k, s, x])
    elif kou2:
        if lpt[k, s, x] < tmv:
            for t in range(1, tend - 1 + 1):
                if tmv > 1.0e-6:
                    gzpt[x, t] *= lpt[k, s, x] / tmv
                else:
                    gzpt[x, t] = 0.0
            tmv = lpt[k, s, x]

    # ---- 新規・再加入の人数 ----
    tmr2 = 0.0
    if s <= 2:
        if tmp + tmq + tmv < G.pop[k, s, x]:
            base = std_min(1.0, std_max(G.rt[k, x],
                                        tmp / (G.pop[k, s, x] - tmq - tmv)))
            tmr1 = base * (G.l[k, s, x] - tmq)
            if pseid == 0:
                if k == G.partyr3:
                    tmr2 = (std_min(1.0, std_max(
                                G.rt[k, x],
                                tmp / (G.pop[k, s, x] - tmq - tmv)))
                            * (lpt[k, s, x] - G.lpt1[k, s, x] - tmv)
                            + G.rt[k, x]
                            * std_min(1.0, std_max(0.0, (x - 25) / 40.0))
                            * G.lpt1[k, s, x])
                elif G.flg_part >= 1 and k == G.partyr4:
                    tmr2 = (std_min(1.0, std_max(
                                G.rt[k, x],
                                tmp / (G.pop[k, s, x] - tmq - tmv)))
                            * (lpt[k, s, x] - G.lpt2[k, s, x]
                               - G.lpt3[k, s, x] - G.lpt4[k, s, x] - tmv)
                            + G.rt[k, x]
                            * std_min(1.0, std_max(0.0, (x - 25) / 40.0))
                            * (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                               + G.lpt4[k, s, x]))
                else:
                    tmr2 = (std_min(1.0, std_max(
                                G.rt[k, x],
                                tmp / (G.pop[k, s, x] - tmq - tmv)))
                            * (lpt[k, s, x] - tmv))
        else:
            tmr1 = std_max(0.0, G.l[k, s, x] - tmq)
            if pseid == 0:
                tmr2 = std_max(0.0, lpt[k, s, x] - tmv)
    else:
        tmr1 = G.rt[k, x] * std_max(0.0, G.l[k, s, x] - tmq)

    # ---- 新規・再加入を経過年に配る ----
    for t in range(0, tend - 1 + 1):
        if x <= xrb and tmp > 1.0e-6:
            if kou2:
                if tmp >= tmr1 + tmr2:
                    gn[x, t] = gezz[t] * tmr1 / tmp
                    gnpt[x, t] = gezz[t] * tmr2 / tmp
                else:
                    if tmr1 + tmr2 > 1.0e-6:
                        gn[x, t] = gezz[t] * tmr1 / (tmr1 + tmr2)
                        gnpt[x, t] = gezz[t] * tmr2 / (tmr1 + tmr2)
                    else:
                        gn[x, t] = 0.0
                        gnpt[x, t] = 0.0
            else:
                if tmp >= tmr1:
                    gn[x, t] = gezz[t] * tmr1 / tmp
                else:
                    gn[x, t] = gezz[t]
                gnpt[x, t] = 0.0
        else:
            gn[x, t] = 0.0
            gnpt[x, t] = 0.0
        gez[x, t] = std_max(0.0, gezz[t] - gn[x, t] - gnpt[x, t])

    # ---- 年度途中の加入（残り）----
    G.gnn[x] = G.l[k, s, x] - gn[x, 0]
    for t in range(1, tend - 1 + 1):
        G.gnn[x] -= gz[x, t] + gn[x, t]
    if abs(G.gnn[x]) < 1.0e-6:
        # 丸め誤差ぶんは被保険者数の側を動かしてそろえる
        G.l[k, s, x] -= G.gnn[x]
        G.gnn[x] = 0.0

    assert G.gnn[x] > -1.0e-6

    g[x, tend - 1] = gz[x, tend - 1] + gn[x, tend - 1]

    tm0 = 0.0
    if kou2:
        y[x, tend - 1, 0] = (g[x - 1, tend - 2] + g[x - 1, tend - 1]
                             - gpt[x - 1, tend - 2] - gpt[x - 1, tend - 1]
                             - gz[x, tend - 1])
        tm0 = (g[x - 1, tend - 2] + g[x - 1, tend - 1]
               - gpt[x - 1, tend - 2] - gpt[x - 1, tend - 1])
    else:
        y[x, tend - 1, 0] = (g[x - 1, tend - 2] + g[x - 1, tend - 1]
                             - gz[x, tend - 1])
        if pseid == 0:
            tm0 = g[x - 1, tend - 2] + g[x - 1, tend - 1]
        else:
            tm0 = ((g[x - 1, tend - 2] + g[x - 1, tend - 1]
                    + gz[x, tend - 1]) / 2.0)
    y[x, tend - 1, 2] = tm0 * u[k, x, 2]
    y[x, tend - 1, 3] = tm0 * u[k, x, 3]
    y[x, tend - 1, 1] = (y[x, tend - 1, 0] - y[x, tend - 1, 2]
                         - y[x, tend - 1, 3])
    if y[x, tend - 1, 1] < -1.0e-12:
        assert x > xrb and y[x, tend - 1, 1] > -1.0e-2
        y[x, tend - 1, 1] = 0.0
        tmp = y[x, tend - 1, 2] + y[x, tend - 1, 3]
        if tmp > 1.0e-12:
            y[x, tend - 1, 2] = (y[x, tend - 1, 0] * y[x, tend - 1, 2] / tmp)
            y[x, tend - 1, 3] = (y[x, tend - 1, 0] * y[x, tend - 1, 3] / tmp)
        else:
            y[x, tend - 1, 0] = 0.0
            y[x, tend - 1, 2] = 0.0
            y[x, tend - 1, 3] = 0.0
    ge[x, tend - 1] = gez[x, tend - 1] + y[x, tend - 1, 1]

    for t in range(tend - 2, 1 - 1, -1):
        g[x, t] = gz[x, t] + gn[x, t]
        if kou2:
            y[x, t, 0] = (g[x - 1, t - 1] - gpt[x - 1, t - 1] - gz[x, t])
            tm0 = g[x - 1, t - 1] - gpt[x - 1, t - 1]
        else:
            y[x, t, 0] = g[x - 1, t - 1] - gz[x, t]
            if pseid == 0:
                tm0 = g[x - 1, t - 1]
            else:
                tm0 = (g[x - 1, t - 1] + gz[x, t]) / 2.0
        y[x, t, 2] = tm0 * u[k, x, 2]
        y[x, t, 3] = tm0 * u[k, x, 3]
        y[x, t, 1] = y[x, t, 0] - y[x, t, 2] - y[x, t, 3]

        if y[x, t, 1] < -1.0e-12:
            assert x > xrb and y[x, t, 1] > -1.0e-2

            y[x, t, 1] = 0.0
            tmp = y[x, t, 2] + y[x, t, 3]
            if tmp > 1.0e-12:
                y[x, t, 2] = y[x, t, 0] * y[x, t, 2] / tmp
                y[x, t, 3] = y[x, t, 0] * y[x, t, 3] / tmp
            else:
                y[x, t, 0] = 0.0
                y[x, t, 2] = 0.0
                y[x, t, 3] = 0.0
        ge[x, t] = gez[x, t] + y[x, t, 1]

    g[x, 0] = gn[x, 0] + G.gnn[x]
    ge[x, 0] = gez[x, 0]

    # ------------------------------------------------------------------
    # パート（短時間労働者）の同じ計算
    # ------------------------------------------------------------------
    if kou2:
        G.gnnpt[x] = lpt[k, s, x] - gnpt[x, 0]
        for t in range(1, tend - 1 + 1):
            G.gnnpt[x] -= gzpt[x, t] + gnpt[x, t]
        if abs(G.gnnpt[x]) < 1.0e-6:
            lpt[k, s, x] = lpt[k, s, x] - G.gnnpt[x]
            G.gnnpt[x] = 0.0
        assert G.gnnpt[x] > -1.0e-6

        gpt[x, tend - 1] = gzpt[x, tend - 1] + gnpt[x, tend - 1]
        ypt[x, tend - 1, 0] = (gpt[x - 1, tend - 2] + gpt[x - 1, tend - 1]
                               - gzpt[x, tend - 1])
        tm0 = gpt[x - 1, tend - 2] + gpt[x - 1, tend - 1]
        ypt[x, tend - 1, 2] = tm0 * u[k, x, 2]
        ypt[x, tend - 1, 3] = tm0 * u[k, x, 3]
        ypt[x, tend - 1, 1] = (ypt[x, tend - 1, 0] - ypt[x, tend - 1, 2]
                               - ypt[x, tend - 1, 3])

        if ypt[x, tend - 1, 1] < -1.0e-12:
            assert x > xrb and ypt[x, tend - 1, 1] >= -1.0e-2

            ypt[x, tend - 1, 1] = 0.0
            tmp = ypt[x, tend - 1, 2] + ypt[x, tend - 1, 3]
            if tmp > 1.0e-12:
                ypt[x, tend - 1, 2] = (ypt[x, tend - 1, 0]
                                       * ypt[x, tend - 1, 2] / tmp)
                ypt[x, tend - 1, 3] = (ypt[x, tend - 1, 0]
                                       * ypt[x, tend - 1, 3] / tmp)
            else:
                ypt[x, tend - 1, 0] = 0.0
                ypt[x, tend - 1, 2] = 0.0
                ypt[x, tend - 1, 3] = 0.0

        for t in range(tend - 2, 1 - 1, -1):
            gpt[x, t] = gzpt[x, t] + gnpt[x, t]
            ypt[x, t, 0] = gpt[x - 1, t - 1] - gzpt[x, t]
            tm0 = gpt[x - 1, t - 1]
            ypt[x, t, 2] = tm0 * u[k, x, 2]
            ypt[x, t, 3] = tm0 * u[k, x, 3]
            ypt[x, t, 1] = ypt[x, t, 0] - ypt[x, t, 2] - ypt[x, t, 3]

            if ypt[x, t, 1] < -1.0e-12:
                assert x > xrb and ypt[x, t, 1] >= -1.0e-2
                ypt[x, t, 1] = 0.0
                tmp = ypt[x, t, 2] + ypt[x, t, 3]
                if tmp > 1.0e-12:
                    ypt[x, t, 2] = ypt[x, t, 0] * ypt[x, t, 2] / tmp
                    ypt[x, t, 3] = ypt[x, t, 0] * ypt[x, t, 3] / tmp
                else:
                    ypt[x, t, 0] = 0.0
                    ypt[x, t, 2] = 0.0
                    ypt[x, t, 3] = 0.0
        gpt[x, 0] = gnpt[x, 0] + G.gnnpt[x]

        for t in range(1, tend - 1 + 1):
            g[x, t] += gpt[x, t]
            y[x, t, 0] += ypt[x, t, 0]
            y[x, t, 1] += ypt[x, t, 1]
            y[x, t, 2] += ypt[x, t, 2]
            y[x, t, 3] += ypt[x, t, 3]
            ge[x, t] += ypt[x, t, 1]

            gn[x, t] += gnpt[x, t]
            gz[x, t] += gzpt[x, t]
        g[x, 0] += gpt[x, 0]
        gn[x, 0] += gnpt[x, 0]
        G.gnn[x] += G.gnnpt[x]

    # ------------------------------------------------------------------
    # 実績から逆算した死亡率
    # ------------------------------------------------------------------
    if x >= 61:
        tmz = gz[x, 0]
        for t in range(1, tend - 1 + 1):
            tmz += gz[x, t]

        if pseid == 0 and s <= 2:
            if G.l[k - 1, s, x - 1] + lpt[k - 1, s, x - 1] > 1.0e-6:
                G.q2[k, x] = 1.0 - std_max(0.0, std_min(
                    1.0, tmz / (G.l[k - 1, s, x - 1]
                                + lpt[k - 1, s, x - 1])))
            else:
                G.q2[k, x] = 1.0
        else:
            if G.l[k - 1, s, x - 1] > 1.0e-6:
                G.q2[k, x] = 1.0 - std_max(0.0, std_min(
                    1.0, tmz / (G.l[k - 1, s, x - 1])))
            else:
                G.q2[k, x] = 1.0
