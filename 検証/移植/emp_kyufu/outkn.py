# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/outkn.cpp の忠実移植（④基礎年金へ渡すファイルを書く）
==========================================================================
89 行。`shkekiso()` が作った `okiso2x` `okisor` `dk3x` をまとめて
`kiso.{試算番号}_{制度}` に書く。**④基礎年金の入力**になるファイル。

62歳以下を63歳に寄せる
----------------------
```c
REV_FOR(k, KE, KIJUN) FOR(ss, 1, 2) FOR(i, 1, 3) FOR(j, 1, 6) FOR(x, 0, 62) {
  okiso2x.AT(k, 63, ss, i, j) += okiso2x.AT(k, x, ss, i, j);
  okiso2x.AT(k, x, ss, i, j) = 0.0;
}
```

基礎年金は65歳からなので、62歳以下を「63歳」にまとめてしまう
（出力は63〜115歳だけ）。`k` の向きが `REV_FOR`（降順）だが
`x` の寄せ方は `k` に依らないので向きは関係ない。

`dk3x` の「計」を3通り作る
--------------------------
```c
FOR(k, KIJUN, KE) FOR(ss, 1, 2) FOR(i, 1, 6) FOR(x, 0, 115) {
  dk3x.AT(k, x,  0, i, 0) += dk3x.AT(k, x, ss, i, 0);   /* 性別計 */
  dk3x.AT(k, x, ss, 0, 0) += dk3x.AT(k, x, ss, i, 0);   /* 区分計 */
  dk3x.AT(k, x,  0, 0, 0) += dk3x.AT(k, x, ss, i, 0);   /* 両方の計 */
}
```

`ss` が外・`i` が内なので、`dk3x[k][x][0][0][0]` には
`ss = 1` の `i = 1〜6`、続いて `ss = 2` の `i = 1〜6` の順に足される。
**縮約なので順序を守る。**

出力の書式
----------
1行の頭が `年度, 区分, …` で、区分 1 が年齢別の給付費、
区分 2 が受給者数。`0.0` を直に書いている欄が多い
（④が読む位置を合わせるための場所取り）。

```c
fprintf(fp, "%d, 1, %d, 1, 1, %d, %21.14e, %21.14e, %21.14e, %21.14e\n",
    k, x, ss, okiso2x.AT(k, x, ss, 1, 1), 0.0, 0.0, okiso2x.AT(k, x, ss, 1, 3));
```
"""
from glva import G
from setconst import FLKE, FLKS, KE, KIJUN

__all__ = ["outkn"]


def outkn():
    """outkn.cpp:5 の忠実移植。"""
    okiso2x = G.okiso2x
    okisor = G.okisor
    dk3x = G.dk3x

    # 62歳以下を63歳に寄せる
    for k in range(KE, KIJUN - 1, -1):
        for ss in range(1, 2 + 1):
            for i in range(1, 3 + 1):
                for j in range(1, 6 + 1):
                    for x in range(0, 62 + 1):
                        okiso2x[k, 63, ss, i, j] += okiso2x[k, x, ss, i, j]
                        okiso2x[k, x, ss, i, j] = 0.0

    # `dk3x` の「計」（性別・区分・両方）
    for k in range(KIJUN, KE + 1):
        for ss in range(1, 2 + 1):
            for i in range(1, 6 + 1):
                for x in range(0, 115 + 1):
                    dk3x[k, x, 0, i, 0] += dk3x[k, x, ss, i, 0]
                    dk3x[k, x, ss, 0, 0] += dk3x[k, x, ss, i, 0]
                    dk3x[k, x, 0, 0, 0] += dk3x[k, x, ss, i, 0]

    fp = G.fp_map["kiso"]

    for k in range(FLKS, FLKE + 1):
        for x in range(63, 115 + 1):
            for ss in range(1, 2 + 1):
                fp.write("%d, 1, %d, 1, 1, %d, %21.14e, %21.14e, %21.14e,"
                         " %21.14e\n"
                         % (k, x, ss, okiso2x[k, x, ss, 1, 1], 0.0, 0.0,
                            okiso2x[k, x, ss, 1, 3]))
            for ss in range(1, 2 + 1):
                fp.write("%d, 1, %d, 1, 2, %d, %21.14e, %21.14e, %21.14e,"
                         " %21.14e, %21.14e\n"
                         % (k, x, ss, okiso2x[k, x, ss, 2, 1],
                            okiso2x[k, x, ss, 2, 2],
                            okiso2x[k, x, ss, 2, 3], 0.0, 0.0))
            for ss in range(1, 2 + 1):
                fp.write("%d, 1, %d, 1, 3, %d, %21.14e, %21.14e\n"
                         % (k, x, ss, okiso2x[k, x, ss, 3, 1],
                            okiso2x[k, x, ss, 3, 2]))
            for ss in range(1, 2 + 1):
                fp.write("%d, 1, %d, 2, 1, %d, "
                         "%21.14e, %21.14e, %21.14e, %21.14e, %21.14e,"
                         " %21.14e, %21.14e, %21.14e\n"
                         % (k, x, ss,
                            okiso2x[k, x, ss, 1, 4], 0.0,
                            okiso2x[k, x, ss, 1, 5], 0.0,
                            okiso2x[k, x, ss, 1, 6], 0.0,
                            0.0, 0.0))
            for ii in range(2, 3 + 1):
                for ss in range(1, 2 + 1):
                    fp.write("%d, 1, %d, 2, %d, %d, %21.14e, %21.14e,"
                             " %21.14e, %21.14e\n"
                             % (k, x, ii, ss, okiso2x[k, x, ss, ii, 4],
                                0.0, okiso2x[k, x, ss, ii, 5], 0.0))

        for ss in range(1, 2 + 1):
            fp.write("%d, 2, 1, %d, "
                     "%21.14e, %21.14e, "
                     "%21.14e, %21.14e, "
                     "%21.14e, %21.14e, "
                     "%21.14e, %21.14e, "
                     "%21.14e\n"
                     % (k, ss,
                        okisor[k, ss, 1, 2], okisor[k, ss, 1, 3],
                        okisor[k, ss, 3, 2], okisor[k, ss, 3, 3],
                        okisor[k, ss, 5, 2], okisor[k, ss, 5, 3],
                        okisor[k, ss, 7, 2], okisor[k, ss, 7, 3],
                        0.0))
        for ss in range(1, 2 + 1):
            fp.write("%d, 2, 2, %d, %21.14e, %21.14e, %21.14e, %21.14e\n"
                     % (k, ss,
                        okisor[k, ss, 9, 2], okisor[k, ss, 9, 3],
                        okisor[k, ss, 10, 2], okisor[k, ss, 10, 3]))
        for ss in range(1, 2 + 1):
            fp.write("%d, 2, 3, %d, "
                     "%21.14e, %21.14e, %21.14e, "
                     "%21.14e, %21.14e, %21.14e\n"
                     % (k, ss,
                        okisor[k, ss, 11, 2], okisor[k, ss, 11, 3],
                        okisor[k, ss, 12, 2], okisor[k, ss, 12, 3],
                        okisor[k, ss, 13, 2], okisor[k, ss, 13, 3]))
