# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shkekiso.cpp の忠実移植（基礎年金へ渡す数の集計）
======================================================================
141 行。④基礎年金が読む

    okisor [k][ss][i][j]        基礎年金の受給者数
    okiso2x[k][x][ss][区分][列] 基礎年金の給付費（年齢別）
    dk3x   [k][x][ss][区分][0]  同（別の区分の切り方）

を作る。`ss` は**基礎年金の側の性別**で、遺族（`i >= 11`）だけ
**男女が入れ替わる**（遺族基礎年金を受けるのは配偶者なので）。

```c
if(i <= 10) { ss = (s2 == 2) ? 2 : 1; }
else        { ss = (s2 == 2) ? 1 : 2; }
```

`j` の意味（`okisor` の第4添字）
--------------------------------
| `j` | 中身 |
|---|---|
| 1 | 65歳以上（老齢基礎年金） |
| 2 | 支給開始年齢に達した人 |
| 3 | うち65歳未満 |
| 4 | うち65歳以上 |

`i == 9` `10` `11` のときだけ `siku()` を j のループの中で呼ぶ
--------------------------------------------------------------
```c
FOR(j, 1, 4) {
  if(flg_toukei == 0){
    if(i == 9 || i == 11){
      seps::siku(x, i, gv, gvr, gvk, gvkk);
      tmq = t4k.AT(x, xx, i) * gvk;
    } else if(i == 10){
      seps::siku(x, i, gv, gvr, gvk, gvkk);
      tmq = t4k.AT(x, xx, i) * gvkk;
    } else{
      tmq = t4.AT(x, xx, i);
    }
  }
  ...
}
```

同じ引数で **`j` ごとに4回**呼ぶ（結果は毎回同じ）。`siku()` は
中で `sknr()` を呼んで `xxr` `xrb` を書き換えるので、
**グローバルが j のループの中で 4 回書き換わる**。
そのあと `xxr` を読まないので影響はしない。

`flg_toukei != 0` だと `tmq` が持ち越される
-------------------------------------------
`tmq = 0.0` は `FOR(j, 1, 4)` の**外**にあるので、
`flg_toukei != 0`（`tmq` に代入されない）のときは
`j = 1` で `tmq * (cl[1] + cl[2])` のような書き換えを受けた値が
`j = 2, 3, 4` に持ち越される。`cntl.cpp` は `flg_toukei = 0` 固定なので
通る経路では起きない。`検証/原本の不具合.md` の E28。

最後に制度をまとめる
--------------------
```c
FOR(j, 1, 4) {
  okisor.AT(k, ss, 1, j) += okisor.AT(k, ss, 2, j);
  okisor.AT(k, ss, 3, j) += okisor.AT(k, ss, 4, j);
  ...
  okisor.AT(k, ss, 2, j) = 0.0;
```

`i` の 2・4・6・8（在職）を 1・3・5・7（退職）へ寄せる。
`i` は 13 まであるが、寄せるのは 8 まで。
"""
from glva import G
from siku import siku
from sknr import sknr

__all__ = ["shkekiso"]


def shkekiso():
    """shkekiso.cpp:3 の忠実移植。"""
    k = G.k
    s = G.s
    s2 = G.s2

    t4 = G.t4
    t4k = G.t4k
    t6 = G.t6
    okisor = G.okisor
    okiso2x = G.okiso2x
    dk3x = G.dk3x

    for x in range(0, 115 + 1):
        G.xrb = 0
        sknr(k, x)
        G.xxr = max(60, G.xxr)
        G.xrb = max(60, G.xrb)

        for i in range(1, 13 + 1):
            if i <= 10:
                ss = 2 if s2 == 2 else 1
            else:
                # 遺族は受け取る側（配偶者）の性別になる
                ss = 1 if s2 == 2 else 2

            for xx in range(0, 15 + 1):

                tmq = 0.0

                for j in range(1, 4 + 1):
                    if G.flg_toukei == 0:
                        if i == 9 or i == 11:
                            _gv, _gvr, gvk, _gvkk = siku(x, i)
                            tmq = t4k[x, xx, i] * gvk
                        elif i == 10:
                            _gv, _gvr, _gvk, gvkk = siku(x, i)
                            tmq = t4k[x, xx, i] * gvkk
                        else:
                            tmq = t4[x, xx, i]
                    # flg_toukei != 0 なら tmq が持ち越される（E28）

                    if tmq <= 1.0e-30:
                        tmq = 0.0
                    if j == 1:
                        if x < 65:
                            tmq = 0.0
                    elif j >= 2:
                        if i <= 4:
                            if x < 65 - xx:
                                tmq = 0.0
                        elif i <= 8:
                            if x < 65:
                                tmq = 0.0
                        elif i <= 10:
                            if i == 9:
                                tmq = tmq * (G.cl[k, 1] + G.cl[k, 2])
                            else:
                                tmq = tmq * (G.cl2[k, 1] + G.cl2[k, 2])
                        else:
                            if x >= 19:
                                tmq = tmq * G.rc[s, k, x]
                        if j == 3 and x >= 65:
                            tmq = 0.0
                        if j == 4 and x < 65:
                            tmq = 0.0
                    okisor[k, ss, i, j] += tmq

                if i <= 4:
                    okiso2x[k, x, ss, 1, 1] += t6[x, xx, i, 14]
                    okiso2x[k, x, ss, 1, 3] += t6[x, xx, i, 6]
                    okiso2x[k, x, ss, 1, 5] += t6[x, xx, i, 19]
                    dk3x[k, x, ss, 1, 0] += (t6[x, xx, i, 6]
                                             + t6[x, xx, i, 14])
                    dk3x[k, x, ss, 2, 0] += (t6[x, xx, i, 15]
                                             + t6[x, xx, i, 16] * 3.0 / 4.0
                                             + t6[x, xx, i, 19])
                elif xx == 0:
                    if i <= 8:
                        okiso2x[k, x, ss, 1, 4] += t6[x, xx, i, 15]
                        okiso2x[k, x, ss, 1, 5] += t6[x, xx, i, 19]
                        okiso2x[k, x, ss, 1, 6] += (t6[x, xx, i, 16]
                                                    * 3.0 / 4.0)
                        dk3x[k, x, ss, 2, 0] += (
                            t6[x, xx, i, 15]
                            + t6[x, xx, i, 16] * 3.0 / 4.0
                            + t6[x, xx, i, 19])
                    elif i == 9:
                        okiso2x[k, x, ss, 2, 1] += t6[x, xx, i, 14]
                        okiso2x[k, x, ss, 2, 2] += t6[x, xx, i, 21]
                        okiso2x[k, x, ss, 2, 3] += t6[x, xx, i, 6]
                        okiso2x[k, x, ss, 2, 5] += t6[x, xx, i, 19]
                        dk3x[k, x, ss, 3, 0] += (t6[x, xx, i, 6]
                                                 + t6[x, xx, i, 14]
                                                 + t6[x, xx, i, 21])
                        dk3x[k, x, ss, 4, 0] += t6[x, xx, i, 19]
                    elif i == 10:
                        okiso2x[k, x, ss, 2, 4] += t6[x, xx, i, 17]
                        okiso2x[k, x, ss, 2, 5] += (t6[x, xx, i, 19]
                                                    + t6[x, xx, i, 20])
                        dk3x[k, x, ss, 4, 0] += (t6[x, xx, i, 17]
                                                 + t6[x, xx, i, 19]
                                                 + t6[x, xx, i, 20])
                    elif i == 11:
                        okiso2x[k, x, ss, 1, 5] += t6[x, xx, i, 18]
                        okiso2x[k, x, ss, 3, 1] += t6[x, xx, i, 14]
                        okiso2x[k, x, ss, 3, 2] += t6[x, xx, i, 21]
                        dk3x[k, x, ss, 5, 0] += (t6[x, xx, i, 14]
                                                 + t6[x, xx, i, 21])
                        dk3x[k, x, ss, 2, 0] += t6[x, xx, i, 18]
                    elif i >= 12:
                        okiso2x[k, x, ss, 1, 5] += t6[x, xx, i, 18]
                        okiso2x[k, x, ss, 3, 4] += t6[x, xx, i, 17]
                        okiso2x[k, x, ss, 3, 5] += t6[x, xx, i, 20]
                        dk3x[k, x, ss, 6, 0] += (t6[x, xx, i, 17]
                                                 + t6[x, xx, i, 20])
                        dk3x[k, x, ss, 2, 0] += t6[x, xx, i, 18]

    if s2 == 2:
        ss = 2
    else:
        ss = 1

    for j in range(1, 4 + 1):
        okisor[k, ss, 1, j] += okisor[k, ss, 2, j]
        okisor[k, ss, 3, j] += okisor[k, ss, 4, j]
        okisor[k, ss, 5, j] += okisor[k, ss, 6, j]
        okisor[k, ss, 7, j] += okisor[k, ss, 8, j]
        okisor[k, ss, 2, j] = 0.0
        okisor[k, ss, 4, j] = 0.0
        okisor[k, ss, 6, j] = 0.0
        okisor[k, ss, 8, j] = 0.0
