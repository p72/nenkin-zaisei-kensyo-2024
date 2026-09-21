# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/subrj.cpp の忠実移植（受給権者の基礎数の読み）
===================================================================
112 行。`jk2021-{1,2,3}.csv`（受給権者の基礎数）の1ブロックを読む。
入れる配列の次元だけが違う3つ（`subrj3` `subrj4` `subrj5`）で中身は同じ。

欄の並びが入れ子になっている
----------------------------
`jk` ファイルの1行は

    年齢, 計×4, 60歳×4, 61歳×4, …, 70歳×4, 計×2

という並びで、4欄ひと組が `t`（給付の種類。1 新老退職 / 2 新老在職 /
3 通老退職 / 4 通老在職）にあたる。原本はこれを

```c
FOR(t, 1, 4) {
  pos = t;                     /* 計（xx = 0） */
  v.AT(x, 0, t) = vals.at(pos) * pow(10.0, exp);
  FOR(xx, 1, 5)  { pos = 24 + t - xx * 4;  v.AT(x, xx, t) = vals.at(pos) * …; }
  FOR(xx, 6, 10) { pos = 4  + t + xx * 4;  v.AT(x, xx, t) = vals.at(pos) * …; }
}
FOR(t, 5, 13) { pos = 44 + t;  v.AT(x, 0, t) = vals.at(pos) * …; }
```

と読む。`xx` は**繰上げ・繰下げの月数の区分**で、`xx = 1〜5` が
64歳〜60歳（繰上げ。欄は逆順なので `24 + t - xx * 4` で遡る）、
`xx = 6〜10` が66歳〜70歳（繰下げ）。`t = 5〜13` は障害・遺族などで
繰上げ繰下げが無いので `xx = 0` だけ。

読む前に何行読み飛ばすか
------------------------
`subrj3` は 3 行、`subrj4` と `subrj5` は **4 行**。`jk` ファイルは
見出しが7行で、`dtst.cpp` が最初に 4 行読み飛ばしてから `subrj3` を
呼ぶので、1ブロックめは 4 + 3 = 7 行。2ブロックめ以降は前の
ブロックの最後の行が見出しの1行めを兼ねる形で 4 行ずつ。

`if(pos >= size) break` の検査は正しい
--------------------------------------
`subrh` の `min(50, size - 1)`（C8）と違って、こちらは
`vals.at(pos)` の直前に `pos >= size` を見ているので範囲外にならない。
いま使っているファイルは1行 58 欄で、最大の添字は 57 なので
`break` は1回も起きない。

`vals.AT(pos)`（`subrj4` だけ）
------------------------------
`subrj4` は 4 か所で `vals.AT(pos)` と書いている。`AT` は
`ext/_vecarray.h` のマクロで引数1つなら `at(pos)` に展開されるので、
`vals.at(pos)` と同じ。他の2つは `vals.at(pos)` と書いていて、
**同じ意味のものが2通りの綴りで並んでいる**。
"""
import math

__all__ = ["subrj3", "subrj4", "subrj5"]


def _read_block(fp, exp, v, tail, skip):
    """subrj.cpp の3つに共通の中身。`tail` は `t` より後ろの添字。"""
    fp.skip(skip)
    p = math.pow(10.0, exp)

    for x in range(0, 115 + 1):
        vals = fp.read()
        xtp = int(vals[0])
        assert xtp == x, "subrj: xtp = %d, x = %d" % (xtp, x)
        size = len(vals)

        for t in range(1, 4 + 1):
            pos = t
            if pos >= size:
                break
            v[(x, 0, t) + tail] = vals[pos] * p
            for xx in range(1, 5 + 1):
                pos = 24 + t - xx * 4
                if pos >= size:
                    break
                assert not math.isnan(vals[pos] * p)
                v[(x, xx, t) + tail] = vals[pos] * p
            for xx in range(6, 10 + 1):
                pos = 4 + t + xx * 4
                if pos >= size:
                    break
                assert not math.isnan(vals[pos] * p)
                v[(x, xx, t) + tail] = vals[pos] * p

        for t in range(5, 13 + 1):
            pos = 44 + t
            if pos >= size:
                break
            assert not math.isnan(vals[pos] * p)
            v[(x, 0, t) + tail] = vals[pos] * p


def subrj3(fp, exp, v):
    """subrj.cpp:11。`v[x][xx][t]`。読み飛ばしは 3 行。"""
    _read_block(fp, exp, v, (), 3)


def subrj4(fp, exp, v, j):
    """subrj.cpp:46。`v[x][xx][t][j]`。読み飛ばしは 4 行。"""
    _read_block(fp, exp, v, (j,), 4)


def subrj5(fp, exp, v, jj, ii):
    """subrj.cpp:80。`v[x][xx][t][jj][ii]`。読み飛ばしは 4 行。"""
    _read_block(fp, exp, v, (jj, ii), 4)
