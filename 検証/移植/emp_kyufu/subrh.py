# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/subrh.cpp の忠実移植（基礎数ファイルの年齢×経過年読み）
==============================================================================
81 行。`hk2021-{1,2,3}.csv`（被保険者の基礎数）の1ブロックを読む。
入れる配列の次元だけが違う3つの関数（`subrh2` `subrh4` `subrh5`）で、
中身は同じ。

1ブロックの形
-------------
    見出し7行 → 年齢 15〜89 の75行 → 区切り1行

各行は `年齢, t=0 の値, t=1 の値, …` で、`t` は加入からの**経過年**。
`t` は 50 までしか使わない。

```c
int t_max = min(50, (int)vals.size() - 1);
FOR(t, 0, t_max) {
  assert(!isnan(vals.at(1 + t) * pow(10.0, exp)));
  v.AT(x, t) = vals.at(1 + t) * pow(10.0, exp);
}
```

`min(50, size - 1)` は1つ足りない
---------------------------------
`t` の上限が `size - 1` のとき、読むのは `vals.at(1 + (size - 1))`
つまり **`vals.at(size)`**。`std::vector::at` は範囲外で
`std::out_of_range` を投げる。正しくは `min(50, size - 2)`。

いま使っている `hk2021-*.csv` は行末にカンマが付いていて1行 54 欄
あるので `t_max` は 50 で止まり、最大の添字は 51。落ちない。
**欄が 51 以下のファイルを渡すと落ちる。**
`検証/原本の不具合.md` の C8。

`exp` は 10 の冪。`dtst.cpp` からの呼び出しは全部 0 なので
`pow(10.0, 0) = 1.0` の掛け算になる（`subrj` の方は 3 を渡す）。
"""
import math
import sys

import numpy as np

__all__ = ["subrh2", "subrh4", "subrh5"]


def _read_block(fp, exp, v, v_name, tail, ctx):
    """subrh.cpp の3つに共通の中身。`tail` は年齢・経過年より後ろの添字。"""
    fp.skip(7)
    p = math.pow(10.0, exp)

    for x in range(15, 89 + 1):
        vals = fp.read()
        xx = int(vals[0])
        if xx != x:
            if ctx:
                msg = ("基礎数の年齢が違います（%s）: x = %d, xx = %d, %s\n"
                       % (v_name, x, xx, ctx))
            else:
                msg = ("基礎数の年齢が違います（%s）: x = %d, xx= %d\n"
                       % (v_name, x, xx))
            sys.stderr.write(msg)
            raise ValueError("subrh")

        # 原本は `min(50, size - 1)`（C8。1つ足りない）
        t_max = min(50, len(vals) - 1)
        chunk = np.array(vals[1:1 + t_max + 1]) * p
        assert not np.isnan(chunk).any()
        v[(x, slice(0, t_max + 1)) + tail] = chunk

    fp.skip(1)


def subrh2(fp, exp, v, v_name):
    """subrh.cpp:11。`v[x][t]`。"""
    _read_block(fp, exp, v, v_name, (), "")


def subrh4(fp, exp, v, v_name, i, j):
    """subrh.cpp:34。`v[x][t][i][j]`。"""
    _read_block(fp, exp, v, v_name, (i, j), "i = %d, j = %d" % (i, j))


def subrh5(fp, exp, v, v_name, i, j, ii):
    """subrh.cpp:60。`v[x][t][i][j][ii]`。"""
    _read_block(fp, exp, v, v_name, (i, j, ii),
                "i = %d, j = %d, ii = %d" % (i, j, ii))
