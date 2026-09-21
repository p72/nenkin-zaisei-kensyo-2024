# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/kiso.cpp の忠実移植（基礎率の読み込みと将来への伸ばし）
============================================================================
575 行。`kisor_{制度}2024.csv` から**基礎率**を読み、基準年度の値を
将来年度へ伸ばす。`sepsd()` の種別ループ（`s` = 1 男 / 2 女 / 3 男女計）
の中で**1回ずつ呼ばれ、そのたびにファイルの次の節を読む**。

読む節と入れる配列
------------------
| 節 | 配列 | 中身 |
|---|---|---|
| `Q` | `q[k][x][i]` | 受給者の失権率（i = 1 老齢 / 2 障害 / 3 遺族） |
| `U` | `u[k][x][i]` | 被保険者の脱退力（i = 0 計 / 1 生存 / 2 障害 / 3 死亡） |
| `RT` | `rt[k][x]` | 再加入者 /（新規加入者＋再加入者） |
| `YX` | `yx[k][x][j]` ＋ `ns[k][x]` | 年齢相関と加給・加算用 |
| `RC` | `rc[s][k][x]` | 有子割合 |
| `CL` | `cl[k][i]` `cl2[k][i]` | 障害年金の等級別割合 |
| `KD` | `kd[k][i][j][x]` | 加給対象者割合・振替加算割合（20列） |
| `IK` | `ikucoe[k][x]` | 育休産休取得率 |
| `JI` | `jiiku[k][x]` | 標準報酬比率（2種のみ） |

節の見出しは `csv::read_str(fp).at(1).substr(0, n)` で頭文字を見て
`assert` する。**節の順番が固定**なので、途中で読み飛ばすと以降が全部
ずれる。

死亡率の正規化の分母が制度で違う
--------------------------------
厚生年金（`pseid == 0`）は

```c
u.AT(k, x, 3) = u.AT(KS + 1, x, 3) * qp.AT(min(k, seiy), x, s3) / qp.AT(21, x, s3);
```

と **2021年（`qp[21]`）の1年ぶん**で割るが、共済（`pseid` 1/4/5）は

```c
qp0.AT(x, ss) = (qp.AT(19, x, ss) + qp.AT(20, x, ss) + qp.AT(21, x, ss)) / 3.0;
u.AT(k, x, 3) = u.AT(KS + 1, x, 3) * qp.AT(min(k, seiy), x, ss) / qp0.AT(x, ss);
```

と **2019〜2021年の3年平均**で割る。`q` の方（老齢の失権率）は
どちらも3年平均なので、`u` の厚生年金だけが1年ぶん。
`検証/原本の不具合.md` の E23。**そのまま写す。**

`kzn != 1` だと `q` が入らない
------------------------------
```c
else if(i != 2) {
  if(x <= 104) {
      if(kzn == 1){
          qp0.AT(x, sss) = …;
          q.AT(k, x, i) = q.AT(KS, x, i) * qp.AT(min(k, seiy), x, sss) / qp0.AT(x, sss);
      }
  }
```

`kzn == 1` でないと `q.AT(k, x, i)` に**何も入らない**（0 のまま）。
`cntl.cpp` は `kzn = 1` 固定なので通る経路では起きないが、
`else` が無いので設定を変えると 104 歳以下の失権率が全部 0 になる。
同 E24。

`flg_hantei != 0` だと `kdc` が未初期化
---------------------------------------
```c
if(flg_hantei == 0){
    if(s != 2) kdc = 0.0340341;
    else       kdc = 0.0237070;
}
…
kdctmp = kdc * 0;        /* flg_hantei != 0 なら未初期化の kdc を読む */
```

`cntl.cpp` は `flg_hantei = 0` 固定なので通る経路では起きない。同 H2。
移植版は `kdc = None` で始めて、使うところで落ちるようにする
（原本は未初期化のスタックを読むので再現できない）。

宣言だけして使わない局所配列
----------------------------
`beta`（126×116 = 14,616 要素・117KB）と `rdsp1` `rdsp2` `rdsp3`、
`items` は一度も使われない。同 F14。移植版は作らない。
"""
import math

import numpy as np

from csvio import join
from glva import G
from sepsstd import std_max, std_min
from setconst import KE, KS
from sknr import sknr

__all__ = ["kiso"]


def kiso():
    """kiso.cpp:11 の忠実移植。"""
    qp0 = np.zeros((116, 4))

    # beta / rdsp1 / rdsp2 / rdsp3 / items は宣言だけで使われない（F14）
    rds = np.zeros(3)
    qpr = np.zeros(3)

    kdc = None                          # flg_hantei != 0 だと未初期化（H2）

    fp = G.fp_map["kisor"]

    fp.read()
    stmp = int(fp.read()[1])
    assert stmp == G.s, "kisor: stmp = %d, s = %d" % (stmp, G.s)

    if G.s2 != 2:
        ss = 1
    if G.s2 == 2:
        ss = 2

    # ------------------------------------------------------------------
    # Q — 受給者の失権率
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:1]
    assert nensyu == "Q", "kisor: nensyu = %r" % nensyu

    fp.read()
    for x in range(0, 115 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(Q): xx = %d, x = %d" % (xx, x)
        G.q[KS, x, 1:3 + 1] = vals[1:1 + 3]

    if G.pseid != 0 and ss == 2:
        for x in range(20, 54 + 1):
            G.q[KS, x, 3] = (G.qp[19, x, 1] + G.qp[20, x, 1]
                             + G.qp[21, x, 1]) / 3.0

    for k in range(KS + 1, KE + 1):
        for x in range(0, 115 + 1):
            for i in range(1, 3 + 1):
                if i == 3:
                    # 遺族は相手の性の死亡率を使う
                    if ss == 1:
                        sss = 2
                    if ss == 2:
                        sss = 1
                else:
                    sss = ss
                # qpr は代入されるだけで使われない（F14 の仲間）
                qpr[1] = 1.0
                qpr[2] = 1.0

                if G.q[KS, x, i] > 0.0:
                    if i == 3 and x < 60:
                        G.q[k, x, i] = G.q[KS, x, i]
                    elif i != 2:
                        if x <= 104:
                            if G.kzn == 1:
                                qp0[x, sss] = (G.qp[19, x, sss]
                                               + G.qp[20, x, sss]
                                               + G.qp[21, x, sss]) / 3.0
                                G.q[k, x, i] = (
                                    G.q[KS, x, i]
                                    * G.qp[min(k, G.seiy), x, sss]
                                    / qp0[x, sss])
                            # kzn != 1 なら何も入らない（E24）
                        else:
                            if G.q[KS, 104, i] > 1.0e-6:
                                G.q[k, x, i] = std_min(
                                    1.0,
                                    G.q[k, 104, i] * G.q[KS, x, i]
                                    / G.q[KS, 104, i])
                            else:
                                G.q[k, x, i] = 0.0
                    elif i == 2:
                        if G.q[KS, x, 1] > 1.0e-6:
                            G.q[k, x, i] = std_min(
                                1.0,
                                G.q[KS, x, i] * G.q[k, x, 1] / G.q[KS, x, 1])
                        else:
                            G.q[k, x, i] = 0.0
                else:
                    G.q[k, x, i] = 0.0

                G.q[k, x, i] = std_min(1.0, std_max(0.0, G.q[k, x, i]))

                if x == 115 or (i == 3 and x == 19):
                    G.q[k, x, i] = 1.0

    # 65歳の障害の失権率を、64歳と66歳の平均へ40年かけて寄せる
    for k in range(KS + 1, KE + 1):
        G.q[k, 65, 2] = (G.q[k, 65, 2] * std_max(0.0, (KS + 40 - k) / 40.0)
                         + (G.q[k, 64, 2] + G.q[k, 66, 2]) / 2.0
                         * std_min(1.0, (k - KS) / 40.0))

    # ------------------------------------------------------------------
    # U — 被保険者の脱退力
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:1]
    assert nensyu == "U", "kisor: nensyu = %r" % nensyu

    fp.read()
    if G.pseid == 0:
        for x in range(15, 84 + 1):
            vals = fp.read()
            xx = int(vals[0])
            assert xx == x, "kisor(U): xx = %d, x = %d" % (xx, x)
            G.u[KS + 1, x, 1:3 + 1] = vals[1:1 + 3]
    else:
        for x in range(15, 74 + 1):
            vals = fp.read()
            xx = int(vals[0])
            assert xx == x, "kisor(U): xx = %d, x = %d" % (xx, x)
            G.u[KS + 1, x, 1:3 + 1] = vals[1:1 + 3]

    if G.pseid == 0:
        s3 = 0
        for k in range(KS + 1, KE + 1):
            for x in range(15, 84 + 1):

                if G.s2 <= 3:
                    if G.s2 != 2:
                        s3 = 1
                    else:
                        s3 = 2

                    if G.flg_inout <= 1 and G.pseid == 0:
                        if G.flg_inout == 0:
                            if s3 == 1:
                                if x <= 39:
                                    rds[s3] = 0.00
                                if 40 <= x <= 59:
                                    rds[s3] = 0.20
                                if 60 <= x <= 64:
                                    rds[s3] = 0.40
                                if x >= 65:
                                    rds[s3] = 0.00
                            if s3 == 2:
                                if x <= 24:
                                    rds[s3] = 0.00
                                if 25 <= x <= 59:
                                    rds[s3] = 0.35
                                if 60 <= x <= 64:
                                    rds[s3] = 0.55
                                if x >= 65:
                                    rds[s3] = 0.00
                        elif G.flg_inout == 1:
                            if s3 == 1:
                                if x <= 39:
                                    rds[s3] = 0.00
                                if 40 <= x <= 59:
                                    rds[s3] = 0.00
                                if 60 <= x <= 64:
                                    rds[s3] = 0.30
                                if x >= 65:
                                    rds[s3] = 0.00
                            if s3 == 2:
                                if x <= 24:
                                    rds[s3] = 0.00
                                if 25 <= x <= 59:
                                    rds[s3] = 0.20
                                if 60 <= x <= 64:
                                    rds[s3] = 0.55
                                if x >= 65:
                                    rds[s3] = 0.00

                        if KS + 1 < k <= 40:
                            G.u[k, x, 1] = (
                                G.u[KS + 1, x, 1]
                                * (1.0 - rds[s3] * (k - (KS + 1.0))
                                   / (40.0 - (KS + 1.0))))
                        elif k > 40:
                            G.u[k, x, 1] = G.u[40, x, 1]
                    else:
                        G.u[k, x, 1] = G.u[KS + 1, x, 1]

                # 厚生年金だけ分母が1年ぶん（2021年）。共済は3年平均（E23）
                G.u[k, x, 3] = (G.u[KS + 1, x, 3]
                                * G.qp[min(k, G.seiy), x, s3]
                                / G.qp[21, x, s3])
                if x >= 70:
                    if G.q[k, x, 1] < 1.0 - 1.0e-6:
                        G.u[k, x, 3] = -math.log(1.0 - G.q[k, x, 1])
                    else:
                        G.u[k, x, 3] = 1000.0

    if G.pseid == 1 or G.pseid == 4:
        for x in range(15, 84 + 1):
            G.u[KS + 1, x, 0] = (G.u[KS + 1, x, 1] + G.u[KS + 1, x, 2]
                                 + G.u[KS + 1, x, 3])

        if G.s == 2:
            if G.pseid == 1:
                tmp = 0.16302
            if G.pseid == 4:
                tmp = 0.23008
        else:
            if G.pseid == 1:
                tmp = 0.08676
            if G.pseid == 4:
                tmp = 0.25681

        for k in range(KS + 1, KE + 1):
            for x in range(15, 84 + 1):
                if k >= 23 and x == 64:
                    G.u[k, x, 0] = G.u[KS + 1, x, 0] - tmp
                elif (((k == 24 or k == 25) and x == 65)
                      or (k >= 27 and x == 66)):
                    G.u[k, x, 0] = G.u[KS + 1, x, 0] + tmp
                else:
                    G.u[k, x, 0] = G.u[KS + 1, x, 0]

                qp0[x, ss] = (G.qp[19, x, ss] + G.qp[20, x, ss]
                              + G.qp[21, x, ss]) / 3.0
                G.u[k, x, 3] = (G.u[KS + 1, x, 3]
                                * G.qp[min(k, G.seiy), x, ss] / qp0[x, ss])
                if x >= 70:
                    if G.q[k, x, 1] < 1.0 - 1.0e-6:
                        G.u[k, x, 3] = -math.log(1.0 - G.q[k, x, 1])
                    else:
                        G.u[k, x, 3] = 1000.0

                G.u[k, x, 0] += G.u[k, x, 3] - G.u[KS + 1, x, 3]

    if G.pseid == 5:
        for x in range(15, 84 + 1):
            G.u[KS + 1, x, 0] = (G.u[KS + 1, x, 1] + G.u[KS + 1, x, 2]
                                 + G.u[KS + 1, x, 3])
        # 上のループは x ≦ 84 だが、こちらは 85 まで回る
        for k in range(KS + 1, KE + 1):
            for x in range(15, 85 + 1):
                qp0[x, ss] = (G.qp[19, x, ss] + G.qp[20, x, ss]
                              + G.qp[21, x, ss]) / 3.0
                G.u[k, x, 3] = (G.u[KS + 1, x, 3]
                                * G.qp[min(k, G.seiy), x, ss] / qp0[x, ss])
                if x >= 70:
                    if G.q[k, x, 1] < 1.0 - 1.0e-6:
                        G.u[k, x, 3] = -math.log(1.0 - G.q[k, x, 1])
                    else:
                        G.u[k, x, 3] = 1000.0

                # 右辺が `k` ではなく `KS + 1`。原本のまま
                G.u[k, x, 1] = (G.u[KS + 1, x, 0] - G.u[KS + 1, x, 2]
                                - G.u[KS + 1, x, 3])

    for k in range(KS + 1, KE + 1):
        for x in range(15, 84 + 1):
            if x <= 64:
                G.u[k, x, 2] = G.u[KS + 1, x, 2]
            else:
                G.u[k, x, 2] = 0.0
            sknr(k, x)
            G.xrb = max(60, G.xrb)
            if x > G.xrb:
                if G.pseid == 0 or G.pseid == 5:
                    G.u[k, x, 1] = 0.0
                if G.pseid == 1 or G.pseid == 4:
                    G.u[k, x, 0] = G.u[k, x, 2] + G.u[k, x, 3]

    for k in range(KS + 1, KE + 1):
        if G.pseid == 0:
            tmxend = 85
        else:
            tmxend = 70
        for x in range(15, 85 + 1):
            if G.pseid == 0 and x >= tmxend:
                G.u[k, x, 1] = 1.0
            if (G.pseid == 1 or G.pseid == 4) and x >= tmxend:
                G.u[k, x, 0] = 1000.0
            if G.pseid == 5 and x >= tmxend:
                G.u[k, x, 1] = 1000.0

            if G.pseid == 0 or G.pseid == 5:
                G.u[k, x, 0] = (G.u[k, x, 1] + G.u[k, x, 2] + G.u[k, x, 3])
            G.u[k, x, 0] = std_max(0.0, G.u[k, x, 0])
            G.u[k, x, 2] = std_min(1.0, std_max(0.0, G.u[k, x, 2]))
            G.u[k, x, 3] = std_min(std_max(0.0, G.u[k, x, 3]),
                                   1.0 - G.u[k, x, 2])
            G.u[k, x, 1] = G.u[k, x, 0] - G.u[k, x, 2] - G.u[k, x, 3]

    # ------------------------------------------------------------------
    # RT — 再加入者 /（新規加入者＋再加入者）
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "RT", "kisor: nensyu = %r" % nensyu

    fp.read()
    for x in range(15, 74 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(RT): xx = %d, x = %d" % (xx, x)
        G.rt[KS + 1, x] = vals[1]

    for x in range(15, 74 + 1):
        for k in range(KS + 2, KE + 1):
            G.rt[k, x] = G.rt[KS + 1, x]
            sknr(k, x)
            G.xrb = max(60, G.xrb)
            if x > G.xrb:
                G.rt[k, x] = 0.0

    # ------------------------------------------------------------------
    # YX — 年齢相関（被保険者から配偶者・子）と NS
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "YX", "kisor: nensyu = %r" % nensyu

    fp.read()
    for x in range(15, 115 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(YX): xx = %d, x = %d" % (xx, x)

        if G.s != 2:
            G.yx[KS, x, 0] = vals[1]
            G.yx[KS, x, 1] = 0.0
            G.ns[KS, x] = vals[2]
        else:
            G.yx[KS, x, 0] = vals[1]
            G.yx[KS, x, 1] = vals[2]
            G.ns[KS, x] = vals[3]

    for k in range(KS + 1, KE + 1):
        for x in range(15, 115 + 1):
            G.yx[k, x, 0] = G.yx[KS, x, 0]
            G.yx[k, x, 1] = G.yx[KS, x, 1]
            G.ns[k, x] = G.ns[KS, x]

    # ------------------------------------------------------------------
    # RC — 有子割合
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "RC", "kisor: nensyu = %r" % nensyu

    fp.read()
    for x in range(15, 115 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(RC): xx = %d, x = %d" % (xx, x)
        G.rc[G.s, KS, x] = vals[1]

    for k in range(KS + 1, KE + 1):
        for x in range(15, 115 + 1):
            G.rc[G.s, k, x] = G.rc[G.s, KS, x]

    if G.s == 2:
        # 女は1955年度生まれ以降の有子割合を年度ごとに伸ばす
        for k in range(KS + 1, KE + 1):
            for x in range(58, 115 + 1):
                if k - 14 == x - 55:
                    G.rc[G.s, k, x] = (G.rc[G.s, k - 1, x]
                                       * (k - 13 - 0.5) / float((k - 1) - 13))
                elif k - 14 < x - 55:
                    G.rc[G.s, k, x] = (G.rc[G.s, k - 1, x]
                                       * (k - 13) / float((k - 1) - 13))
                else:
                    G.rc[G.s, k, x] = G.rc[G.s, k - 1, x]

    # ------------------------------------------------------------------
    # CL — 障害年金の等級別割合
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "CL", "kisor: nensyu = %r" % nensyu

    fp.read()
    vals = fp.read()
    G.cl[KS, 1:3 + 1] = vals[1:1 + 3]
    G.cl2[KS, 1:3 + 1] = vals[4:4 + 3]

    for k in range(KS + 1, KE + 1):
        for i in range(1, 3 + 1):
            G.cl[k, i] = G.cl[KS, i]
            G.cl2[k, i] = G.cl2[KS, i]

    # ------------------------------------------------------------------
    # KD — 加給対象者割合・振替加算割合
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "KD", "kisor: nensyu = %r" % nensyu

    fp.skip(2)

    for x in range(0, 115 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(KD): xx = %d, x = %d" % (xx, x)
        for i in range(1, 2 + 1):
            G.kd[KS, i, 1, x] = vals[1 + (i - 1)]
        for j in range(2, 3 + 1):
            G.kd[KS, 1, j, x] = vals[3 + (j - 2)]
        for i in range(3, 4 + 1):
            G.kd[KS, i, 1, x] = vals[5 + (i - 3)]
        for j in range(2, 3 + 1):
            G.kd[KS, 3, j, x] = vals[7 + (j - 2)]
        for j in range(2, 3 + 1):
            G.kd[KS, 5, j, x] = vals[9 + (j - 2)]
        G.kd[KS, 1, 4, x] = vals[11]

        for j in range(2, 3 + 1):
            G.kd[KS, 2, j, x] = G.kd[KS, 1, j, x]
            G.kd[KS, 4, j, x] = G.kd[KS, 3, j, x]
        G.kd[KS, 3, 4, x] = G.kd[KS, 1, 4, x]

    if G.flg_hantei == 0:
        if G.s != 2:
            kdc = 0.0340341
        else:
            kdc = 0.0237070

    for j in range(1, 4 + 1):
        for i in range(1, 6 + 1):
            if (((i == 2 or i == 4 or i == 5) and j == 4)
                    or (i == 5 and j == 1)):
                continue
            for k in range(KS, KE + 1):
                for x in range(0, 115 + 1):
                    if i != 5 and i != 6:
                        G.kd[k, i, j, x] = G.kd[KS, i, j, x]
                    elif i == 5:
                        # 上の枝と同じ中身（E18 の仲間）
                        G.kd[k, i, j, x] = G.kd[KS, i, j, x]
                    elif i == 6:
                        # 新通（配・子）は振替加算の段階的な立ち上げ
                        if k - 20 <= x - 69:
                            kdctmp = kdc * 0
                        elif k - 20 == x - 68:
                            kdctmp = kdc * 1
                        elif k - 20 == x - 67:
                            kdctmp = kdc * 2
                        elif k - 20 == x - 66:
                            kdctmp = kdc * 3
                        elif k - 20 == x - 65:
                            kdctmp = kdc * 4
                        elif k - 20 >= x - 64:
                            kdctmp = kdc * 5
                        G.kd[k, i, j, x] = G.kd[KS, 1, j, x] * kdctmp

    if G.s == 2:
        for k in range(KS + 1, KE + 1):
            for x in range(58, 115 + 1):
                for j in range(2, 3 + 1):
                    if k - 14 == x - 55:
                        G.kd[k, 5, j, x] = (G.kd[k - 1, 5, j, x]
                                            * (k - 13 - 0.5)
                                            / float((k - 1) - 13))
                    elif k - 14 < x - 55:
                        G.kd[k, 5, j, x] = (G.kd[k - 1, 5, j, x]
                                            * (k - 13) / float((k - 1) - 13))
                    else:
                        G.kd[k, 5, j, x] = G.kd[k - 1, 5, j, x]

    # ------------------------------------------------------------------
    # IK — 育休産休取得率
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "IK", "kisor: nensyu = %r" % nensyu
    fp.read()
    for x in range(20, 49 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(IK): xx = %d, x = %d" % (xx, x)
        G.ikucoe[KS + 1, x] = vals[1]

    for k in range(KS + 2, KE + 1):
        for x in range(20, 49 + 1):
            G.ikucoe[k, x] = G.ikucoe[KS + 1, x]

    # ------------------------------------------------------------------
    # JI — 標準報酬比率（2種のみ）
    # ------------------------------------------------------------------
    nensyu = fp.read_str()[1][0:2]
    assert nensyu == "JI", "kisor: nensyu = %r" % nensyu
    fp.read()
    for x in range(20, 49 + 1):
        vals = fp.read()
        xx = int(vals[0])
        assert xx == x, "kisor(JI): xx = %d, x = %d" % (xx, x)
        G.jiiku[KS + 1, x] = vals[1]

    for k in range(KS + 2, KE + 1):
        for x in range(20, 49 + 1):
            G.jiiku[k, x] = G.jiiku[KS + 1, x]

    # ------------------------------------------------------------------
    # 基礎率の出力
    # ------------------------------------------------------------------
    fpo = G.fp_map["kisor_out"]
    if G.key == 11 and G.nenbeex == 0:
        s = G.s
        fpo.write("受給者の失権率 Q\n")
        fpo.write("記号,種別,年度,年齢,老齢,障害,遺族\n")
        for k in range(KS, KE + 1):
            for x in range(0, 115 + 1):
                fpo.write("Q,%d,%d,%d,%22.15e,%22.15e,%22.15e\n"
                          % (s, k, x, G.q[k, x, 1], G.q[k, x, 2],
                             G.q[k, x, 3]))

        fpo.write("被保険者の脱退力 U\n")
        fpo.write("記号,種別,年度,年齢,計,生存,障害,死亡\n")
        for k in range(KS, KE + 1):
            for x in range(15, 85 + 1):
                fpo.write("U,%d,%d,%d,%22.15e,%22.15e,%22.15e,%22.15e\n"
                          % (s, k, x, G.u[k, x, 0], G.u[k, x, 1],
                             G.u[k, x, 2], G.u[k, x, 3]))

        fpo.write("再加入者/(新規加入者+再加入者) RT\n")
        fpo.write("記号,種別,年度,年齢,再加入者/(新規加入者+再加入者)\n")
        for k in range(KS, KE + 1):
            for x in range(15, 74 + 1):
                fpo.write("RT,%d,%d,%d,%22.15e\n" % (s, k, x, G.rt[k, x]))

        fpo.write("年齢相関 YX\n")
        fpo.write("記号,種別,年度,年齢,被保から妻/夫,被保から子\n")
        for k in range(KS, KE + 1):
            for x in range(15, 115 + 1):
                fpo.write("YX,%d,%d,%d,%22.15e,%22.15e\n"
                          % (s, k, x, G.yx[k, x, 0], G.yx[k, x, 1]))

        fpo.write("加給・加算用（受給者から配偶者） NS\n")
        fpo.write("記号,種別,年度,年齢,加給・加算用（受給者から配偶者）\n")
        for k in range(KS, KE + 1):
            for x in range(15, 115 + 1):
                fpo.write("NS,%d,%d,%d,%22.15e\n" % (s, k, x, G.ns[k, x]))

        fpo.write("有子割合 RC\n")
        fpo.write("記号,種別,年度,年齢,有子割合\n")
        for k in range(KS, KE + 1):
            for x in range(0, 115 + 1):
                fpo.write("RC,%d,%d,%d,%22.15e\n"
                          % (s, k, x, G.rc[s, k, x]))

        fpo.write("障害年金割合 CL\n")
        fpo.write("記号,種別,年度,年齢,1級,2級,3級\n")
        for k in range(KS, KE + 1):
            for x in range(0, 115 + 1):
                # 年齢に依らない値を年齢ごとに 116 回書く
                fpo.write("CL,%d,%d,%d,%22.15e,%22.15e,%22.15e\n"
                          % (s, k, x, G.cl[k, 1], G.cl[k, 2], G.cl[k, 3]))

        fpo.write("加給対象者割合、振替加算割合 kd\n")
        fpo.write("記号,種別,年度,年齢,"
                  "新老（配）,新老（子12）,新老（子3）,新老（配振）,"
                  "旧老（配）,旧老（子12）,旧老（子3）,"
                  "新障（配）,新障（子12）,新障（子3）,新障（配振）,"
                  "旧障（配）,旧障（子12）,旧障（子3）,"
                  "遺族（子12）,遺族（子3）,"
                  "新通（配）,新通（子12）,新通（子3）,新通（配振）\n")
        for k in range(KS, KE + 1):
            for x in range(0, 115 + 1):
                vals = []
                for j in range(1, 4 + 1):
                    vals.append(G.kd[k, 1, j, x])
                for j in range(1, 3 + 1):
                    vals.append(G.kd[k, 2, j, x])
                for j in range(1, 4 + 1):
                    vals.append(G.kd[k, 3, j, x])
                for j in range(1, 3 + 1):
                    vals.append(G.kd[k, 4, j, x])
                for j in range(2, 3 + 1):
                    vals.append(G.kd[k, 5, j, x])
                for j in range(1, 4 + 1):
                    vals.append(G.kd[k, 6, j, x])
                assert len(vals) == 20
                fpo.write("KD,%d,%d,%d,%s\n"
                          % (s, k, x, join(vals, "%22.15e")))

        fpo.write("育休産休取得率 IKUCOE\n")
        fpo.write("記号,種別,年度,育休産休取得率\n")
        for k in range(KS, KE + 1):
            for x in range(15, 64 + 1):
                fpo.write("IKUCOE,%d,%d,%d,%22.15e\n"
                          % (s, k, x, G.ikucoe[k, x]))

        fpo.write("標準報酬比率（２種のみセット） JIIKU\n")
        fpo.write("記号,種別,年度,標準報酬比率\n")
        for k in range(KS, KE + 1):
            for x in range(15, 64 + 1):
                fpo.write("JIIKU,%d,%d,%d,%22.15e\n"
                          % (s, k, x, G.jiiku[k, x]))
