# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shkejuk.cpp の忠実移植（受給者を給付費の表へ集計）
=======================================================================
339 行。`t4` `t6`（受給者）と `t4k` `t6k`（受給権者）を、給付費の
集計表 `d3` `d3x` `d3xs` の 58 列へ足し込む。

    d3  [k][s2][i][列][jj]   年度計
    d3x [k][x][s2][i][列]    年齢別（jj = 2 ＝ 受給者）
    d3xs[k][x][s2][i][列]    年齢別（jj = 1 ＝ 受給権者）

`jj` が 1 なら `t4k` `t6k`、2 なら `t4` `t6` を `tmp[0..23]` に写して
同じ式を回す。原本は 40 か所ほど

```c
d3.AT(k, s2, i, 列, jj) += 式;
if(jj == 2) { d3x .AT(k, x, s2, i, 列) += 式; }
else        { d3xs.AT(k, x, s2, i, 列) += 式; }
```

を並べている。移植版は `_add()` 1つにまとめた（足す順は同じ）。

`tmp[24]` は必ず 0
------------------
```c
v1_t tmp = VEC(double, 24);        /* 0〜24 の 25 要素 */
...
if(jj == 1) tmp.AT(0) = t4k.AT(x, xx, i);
FOR(j, 1, 23) tmp.AT(j) = t6k.AT(x, xx, i, j);
...
if(i <= 8) {
  d3.AT(k, s2, i, 31, jj) += tmp.AT(24) * (1 - ab * kk);
  d3.AT(k, s2, i, 32, jj) += tmp.AT(24) * ab;
```

写すのは `tmp[0]`〜`tmp[23]` だけなので、**`tmp[24]` は
`VEC` の既定値 0.0 のまま**。`d3[…][31]` と `d3[…][32]`（および
`d3x` `d3xs` の同じ列）は**必ず 0 が足される**。
`検証/原本の不具合.md` の D5。

`if(s <= 3 || …)` は常に真
-------------------------
```c
if(s <= 3 || (5 <= i && i <= 10) || 12 <= i) {
  … tmp に写す …
}
```

`s` は 1〜3 なので `s <= 3` は常に真。`||` の残りは見られない。
もし `s <= 3` が偽になる作りだったら、`tmp` が前の周の値を
持ち越して大事故になる（`tmp` は `jj` のループの外で作っている）。
同 F17。

`assert` が `||` なので効かない
-------------------------------
```c
double eps = 1.0e-6;
assert(-eps <= ab || ab <= 1.0 + eps);
```

`ab` は構造上 0 以上なので `-eps <= ab` が常に真。
**`||` なので `ab` がいくら大きくても止まらない。** `&&` の
書き間違いと読める。`krgn.cpp` の `assert(xx = x)`（F11）と同じ質。
同 F16。

これが効いていないため、次の J2 が見つからないまま残っている。

`ab` に掛ける係数が地方公務員共済だけ桁違い
-------------------------------------------
```c
if(pseid == 0)      ab *= 0.9301;
else if(pseid == 1) ab *= 0.8745;
else if(pseid == 4) ab *= 461.6518;      /* ← 他の3つと桁が3つ違う */
else if(pseid == 5) ab *= 0.7979;
```

`ab = aba / abb` で `abb = aba + hn2k[…][2]`（どちらも人数）なので
`ab` は **0 以上 1 以下**。掛けたあとも 1 前後に収まるのが自然で、
実際 3 つは 0.79〜0.93。`461.6518` は小数点が3桁ずれたように見える。
`検証/原本の不具合.md` の J2。**そのまま写す。**
"""
import numpy as np

from glva import G

__all__ = ["shkejuk"]


def shkejuk(i, x, xx):
    """shkejuk.cpp:7 の忠実移植。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pseid = G.pseid

    d3 = G.d3
    d3x = G.d3x
    d3xs = G.d3xs

    tmp = np.zeros(25)              # tmp[24] は 0 のまま（D5）

    for jj in (1, 2):
        # `s <= 3` は常に真なので、この if は必ず通る（F17）
        if s <= 3 or (5 <= i <= 10) or i >= 12:
            if jj == 1:
                tmp[0] = G.t4k[x, xx, i]
            if jj == 2:
                tmp[0] = G.t4[x, xx, i]
            for j in range(1, 23 + 1):
                if jj == 1:
                    tmp[j] = G.t6k[x, xx, i, j]
                if jj == 2:
                    tmp[j] = G.t6[x, xx, i, j]

        if jj == 1:
            aba = G.hn2k[x, xx, i, 1]
            abb = G.hn2k[x, xx, i, 1] + G.hn2k[x, xx, i, 2]
        else:
            aba = G.hn2[x, xx, i, 1]
            abb = G.hn2[x, xx, i, 1] + G.hn2[x, xx, i, 2]

        if s != 3:
            kk = G.ee[1]
        else:
            kk = G.ee[2]

        if (i == 2 or i == 4 or i == 6 or i == 8) and x < 65:
            kk = 0.0

        if abb > 1.0e-6 and aba >= 1.0e-6:
            ab = aba / abb
        else:
            ab = 0.0

        if pseid == 0:
            ab *= 0.9301
        elif pseid == 1:
            ab *= 0.8745
        elif pseid == 4:
            # 他の3制度と桁が3つ違う（J2）。そのまま写す
            ab *= 461.6518
        elif pseid == 5:
            ab *= 0.7979

        # 原本の `assert(-eps <= ab || ab <= 1.0 + eps)` は `||` なので
        # 必ず真。効かない検査なので移植版も書かない（F16）

        if jj == 2:
            dx = d3x
        else:
            dx = d3xs

        def add(col, val):
            """`d3` → `d3x` / `d3xs` の順に足す。原本と同じ並び。"""
            d3[k, s2, i, col, jj] += val
            dx[k, x, s2, i, col] += val

        add(0, tmp[0])
        add(19, tmp[14])
        add(20, tmp[21])
        add(21, tmp[6])
        add(22, tmp[15] + tmp[16] * 3.0 / 4.0 + tmp[17])
        add(28, tmp[17])
        add(23, tmp[19] + tmp[20])
        add(24, tmp[18])
        add(25, tmp[16] / 4.0)

        if i <= 8:
            add(31, tmp[24] * (1 - ab * kk))
            add(32, tmp[24] * ab)

        # ---- 定額部分（1）と従前額保障（10）----
        tmx = tmp[1] + tmp[10]
        tmy = 0.0
        if i == 11:
            tmy = tmp[18]

        add(1, tmx)
        add(7, tmx - tmy)
        if x >= 65:
            add(35, tmx - tmy)
        add(13, (tmx - tmy) * ab)
        add(26, (tmx - tmy) * ab * kk)

        # ---- 報酬比例部分（2）と経過的加算（11）----
        tmx = tmp[2] + tmp[11]

        tmy = tmp[15] + tmp[16] * 3.0 / 4.0 + tmp[17]
        if i != 11:
            tmy += tmp[18]

        tmy2 = tmp[17]
        if i != 11:
            tmy2 += tmp[18]

        tmz = 0.0
        if i <= 4:
            tmz = tmp[14]

        add(2, tmx)
        add(8, tmx - tmy)
        add(14, (tmx - tmy2 + tmz) * ab)
        add(27, (tmx - tmy2 + tmz) * ab * kk)

        # ---- 定額部分の3（3）----
        tmx = tmp[3]

        add(3, tmx)
        add(9, tmx)
        add(15, tmx * ab)
        add(27, tmx * ab * kk)

        # ---- 加給年金（4, 5, 23）----
        tmx = tmp[4] + tmp[5] + tmp[23]
        tmy = tmp[19] + tmp[20]

        add(4, tmx)
        add(10, tmx - tmy)
        add(16, (tmx - tmy) * ab)
        add(27, (tmx - tmy) * ab * kk)

        # ---- 障害・遺族の内訳（7, 8, 9）----
        tmx = tmp[7] + tmp[8] + tmp[9]

        add(5, tmx)
        add(11, tmx)
        add(17, tmx * ab)
        add(27, tmx * ab * kk)

        # ---- 経過的な差額（12）----
        tmx = tmp[12]

        add(6, tmx)
        add(12, tmx)
        add(18, tmx * ab)
        add(27, tmx * ab * kk)
