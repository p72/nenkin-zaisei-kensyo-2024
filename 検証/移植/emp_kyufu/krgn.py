# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/krgn.cpp の忠実移植（繰上げ・繰下げの率）
==============================================================
170 行。`kragsg_2024.csv` から60〜64歳の**繰上げ受給の選択率**と
**繰下げ月数の分布**を読んで、3つの率を作る。

    riss[k][x1][x2][s][i]   支給開始年齢 x2 の人が x1 歳で繰上げる割合
    rigd[s][x1][x2][j]      繰上げ減額率（定額部分ぶん）
    rigk[s][x1][x2][j]      繰上げ減額率（報酬比例ぶん）
    rigbe[s][x1][x2][j]     繰上げ減額率（基礎年金ぶん）

`j` は 0（2022年3月以前の裁定。1か月 0.5% 減額）と
1（2022年4月以降。0.4% 減額）。`tmp[0] = 0.005` `tmp[1] = 0.004` が
その減額率で、`tuki` は「何か月ぶん繰上げたことになるか」。

`assert(xx = x)` — 検査が効いていない
------------------------------------
```c
int xx = vals2.at(0);
assert(xx = x);          /* `==` ではなく `=` */
```

3か所とも**代入**になっている。`x` は 60〜64 なので代入した値は
必ず非0で、`assert` は必ず通る。年齢の並びが違っていても気づけない。
`検証/原本の不具合.md` の F11。移植版も**検査しない**（原本と同じ）。

`rkrgn` の女のぶんを読むが使わない
----------------------------------
`rkrgn.AT(x, s, j)` は `s = 1, 2` の両方をファイルから読むが、
`tuki` を作るのに使うのは `rkrgn.AT(x, 1, j)`（男）だけ。
`s = 2`（女）の 10 個は**1回も読まれない**。同 F12。

`tuki` と `tmp` を作るループの外で使う
--------------------------------------
`tmp` と `tuki` は2つめの `FOR(s, 1, 3)` の**中**で作られるが、
`rigbe` を作るのは**そのループの外**。つまり `s = 3` の周で入った値を
使っている。中身は `s` に依らないので値は変わらないが、見た目は危うい。

`prtfil` の出力に改行が無い
---------------------------
```c
fprintf(fp, "rigd,%d", s);                 /* "\n" が無い */
fprintf(fp, "%d,%s", x1, csv::join(vals).c_str());   /* ここにも無い */
```

`rigd` と `rigk` のぶんは**全部が1行につながって出る**。
`RIGBE` のぶんだけ `\n` が付いている。同 F13。
移植版も同じバイト列を書く。
"""
import numpy as np

from csvio import join
from glva import G
from sepsstd import subc
from setconst import KE, KS

__all__ = ["krgn"]


def krgn():
    """krgn.cpp:11 の忠実移植。"""
    tuki = np.zeros((6, 2))
    tmp = np.zeros(2)
    tmq = np.zeros(65)

    # rtemp と s2 は宣言だけで一度も使われない（F9 の仲間）
    # rtemp = np.zeros(3)

    rkrag = np.zeros((65, 3))
    rkrgn = np.zeros((65, 3, 3))

    subc(G.riss, KS, KE, 60, 70, 60, 65, 1, 3, 0, 1)

    fpk = G.fp_map["kragsg"]

    # ---- 繰上げの選択率（60〜64歳・男女別）----
    fpk.skip(2)
    for x in range(60, 64 + 1):
        vals2 = fpk.read()
        # 原本は `int xx = vals2.at(0); assert(xx = x);` — `==` ではなく
        # `=`。代入した x は必ず非0なので検査は必ず通る。年齢の並びが
        # 違っても気づけない。移植版も検査しない（F11）
        _xx = int(vals2[0])             # noqa: F841  原本と同じく使わない
        for s in range(1, 2 + 1):
            rkrag[x, s] = vals2[s]

    # ---- 繰下げ月数の分布（j = 0: 0.5%減額 / j = 1: 0.4%減額）----
    fpk.skip(2)
    for x in range(60, 64 + 1):
        vals2 = fpk.read()
        _xx = int(vals2[0])             # noqa: F841  同上（F11）
        for s in range(1, 2 + 1):
            rkrgn[x, s, 0] = vals2[s]

    fpk.skip(2)
    for x in range(60, 64 + 1):
        vals2 = fpk.read()
        _xx = int(vals2[0])             # noqa: F841  同上（F11）
        for s in range(1, 2 + 1):
            rkrgn[x, s, 1] = vals2[s]

    # ------------------------------------------------------------------
    # riss — 支給開始年齢 x2 の人が x1 歳で繰上げる割合
    # ------------------------------------------------------------------
    for s in range(1, 3 + 1):
        # s = 3（男女計）は男の列を使う
        if s != 2:
            tmq[60] = rkrag[60, 1]
            tmq[61] = rkrag[61, 1]
            tmq[62] = rkrag[62, 1]
            tmq[63] = rkrag[63, 1]
            tmq[64] = rkrag[64, 1]
        else:
            tmq[60] = rkrag[60, 2]
            tmq[61] = rkrag[61, 2]
            tmq[62] = rkrag[62, 2]
            tmq[63] = rkrag[63, 2]
            tmq[64] = rkrag[64, 2]

        for i in range(0, 1 + 1):
            for k in range(KS, KE + 1):
                for x2 in range(60, 65 + 1):
                    G.riss[k, 65, x2, s, i] = 1.0
                    for x1 in range(60, 64 + 1):
                        # x2 == 60 なら初回で抜ける。あとは x1 < x2 のあいだ
                        if x2 == 60 or x1 >= x2:
                            break
                        if i == 0:
                            G.riss[k, x1, x2, s, i] = tmq[x1]
                        G.riss[k, 65, x2, s, i] = (G.riss[k, 65, x2, s, i]
                                                   - G.riss[k, x1, x2, s, i])

    # ------------------------------------------------------------------
    # rigd / rigk — 繰上げ減額率
    # ------------------------------------------------------------------
    for s in range(1, 3 + 1):
        for x1 in range(60, 70 + 1):
            for x2 in range(60, 70 + 1):
                for j in range(0, 1 + 1):
                    G.rigd[s, x1, x2, j] = 0.0
                    G.rigk[s, x1, x2, j] = 0.0
                    G.rigbe[s, x1, x2, j] = 0.0

        tmp[0] = 0.005
        tmp[1] = 0.004
        # `rkrgn` は男（s = 1）の列しか読まない（F12）
        tuki[0, 0] = (1.0 - rkrgn[60, 1, 0]) / tmp[0]
        tuki[1, 0] = (1.0 - rkrgn[61, 1, 0]) / tmp[0]
        tuki[2, 0] = (1.0 - rkrgn[62, 1, 0]) / tmp[0]
        tuki[3, 0] = (1.0 - rkrgn[63, 1, 0]) / tmp[0]
        tuki[4, 0] = (1.0 - rkrgn[64, 1, 0]) / tmp[0]
        tuki[5, 0] = 0.0
        tuki[0, 1] = (1.0 - rkrgn[60, 1, 1]) / tmp[1]
        tuki[1, 1] = (1.0 - rkrgn[61, 1, 1]) / tmp[1]
        tuki[2, 1] = (1.0 - rkrgn[62, 1, 1]) / tmp[1]
        tuki[3, 1] = (1.0 - rkrgn[63, 1, 1]) / tmp[1]
        tuki[4, 1] = (1.0 - rkrgn[64, 1, 1]) / tmp[1]
        tuki[5, 1] = 0.0

        for j in range(0, 1 + 1):
            G.rigd[s, 65, 60, j] = 1.0
            for x1 in range(60, 65 + 1):
                for x2 in range(61, 65 + 1):
                    if x2 < 65:
                        if x1 < x2:
                            G.rigd[s, x1, x2, j] = (
                                (65 - x2) / (tuki[x1 - 60, j] / 12.0))
                            G.rigk[s, x1, x2, j] = (
                                (1.0 - G.rigd[s, x1, x2, j])
                                * (1.0 - tuki[x1 - 60, j] * tmp[j]))
                        elif x1 == 65:
                            G.rigd[s, x1, x2, j] = (
                                (65 - x2) / (tuki[5, j] / 12.0 + (x1 - x2)))
                            G.rigk[s, x1, x2, j] = (
                                1.0 - tuki[5, j] * tmp[j]
                                - G.rigd[s, x1, x2, j])
                        # x2 <= x1 <= 64 は 0 のまま
                    else:
                        G.rigk[s, x1, x2, j] = 1.0 - tuki[x1 - 60, j] * tmp[j]

    # ------------------------------------------------------------------
    # prtfil への出力（改行が無いので1行につながる。F13）
    # ------------------------------------------------------------------
    fp = G.fp_map["prtfil"]
    fp.write("%s\n" % "繰り上げ減額率")

    for s in range(1, 2 + 1):
        for j in range(0, 1 + 1):
            fp.write("rigd,%d" % s)
            for x1 in range(60, 65 + 1):
                vals = [G.rigd[s, x1, x2, j] for x2 in range(60, 65 + 1)]
                fp.write("%d,%s" % (x1, join(vals)))

            fp.write("rigk,%d" % s)
            for x1 in range(60, 65 + 1):
                vals = [G.rigk[s, x1, x2, j] for x2 in range(60, 65 + 1)]
                fp.write("%d,%s" % (x1, join(vals)))

    # ------------------------------------------------------------------
    # rigbe — 基礎年金ぶんの繰上げ減額率
    # `tuki` `tmp` は上のループ（s = 3 の周）の値をそのまま使う
    # ------------------------------------------------------------------
    for s in range(1, 3 + 1):
        for j in range(0, 1 + 1):
            G.rigbe[s, 60, 60, j] = 1.0
            for x1 in range(60, 65 + 1):
                for x2 in range(61, 65 + 1):
                    if x2 < 65:
                        if x1 < x2:
                            G.rigbe[s, x1, x2, j] = (
                                1.0 - (tuki[x1 - 60, j] / 12.0 - (65 - x2))
                                * 12.0 * tmp[j])
                        elif x1 == x2:
                            # rigd 側は `x1 == 65` だった。条件が違う
                            G.rigbe[s, x1, x2, j] = 1.0 - tuki[5, j] * tmp[j]
                    else:
                        G.rigbe[s, x1, x2, j] = (1.0 - tuki[x1 - 60, j]
                                                 * tmp[j])

    fp.write("繰り上げ減額率\n")           # 上と同じ見出し
    for s in range(1, 2 + 1):
        for j in range(0, 1 + 1):
            fp.write("RIGBE,%d\n" % s)
            for x1 in range(60, 65 + 1):
                vals = [G.rigbe[s, x1, x2, j] for x2 in range(60, 65 + 1)]
                fp.write("%d,%s\n" % (x1, join(vals, "%10.5f")))
