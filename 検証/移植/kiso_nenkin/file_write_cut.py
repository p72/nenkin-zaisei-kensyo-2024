# -*- coding: utf-8 -*-
"""
基礎年金/file_write_cut.c の忠実移植（カット率ファイル cuta*.csv）
===================================================================
`tyousei()` が解いた累積カット率を `cuta-{Version}-{Version_cut}.csv` に
書く。⑤厚生年金収支計算がこれを読んで所得代替率を出すので、
**④→⑤の受け渡しの要**。

    年度（西暦下2桁）,63歳,64歳,…,115歳     ← 54 列（2005〜2125年度）

同時に `Cut_ritu` にも入れ直す。このあと `main.c` が
`Atamawari()` を呼び直すので、この率で給付費が作り直される。

`CUT_ONE_SHUTU == 1` なら全部 1.0
---------------------------------
「カット率一本出し」。調整をまったく掛けない場合の比較用。
`Cut_ritu` の方は書き換えるので、ファイルだけが 1.0 になる。

原本の癖をそのまま残しているところ
----------------------------------
1. **`CUT_ONE_SHUTU == 1` でもファイルにしか効かない。**
   `Cut_ritu` には `cut_ruiseki` の値が入るので、続く `Atamawari()` は
   調整後の給付費を作る。ファイルと計算が食い違う。
   （`検証/原本の不具合.md`）

2. **`shutu` という変数に 1.0 を入れて使い回す。**定数で足りる。

3. **`nendo = 2005` から書く。**`SHONENDO`（2020）より前の年度も
   `cut_ruiseki` から取れるので書く。⑤が 2005年度から読むため。

4. **`Cut_ritu` を書き換える範囲が 2020〜2125年度、ファイルは
   2005〜2125年度。**`Cut_ritu` は `[106]` しかないので 2020 より
   前は持てない。
"""
from glva import G
from setconst import (
    CUTA, ECON_SHONENDO, MAX_JUKYU, NENREI_SUM, SAISHUNENDO, SHONENDO,
    UNDER_63,
)

__all__ = ["file_write_cut"]


def file_write_cut():
    """file_write_cut.c:78 の忠実移植。"""
    shutu = 1.0
    si = G.S_C_NENDO - ECON_SHONENDO

    for nenrei in range(UNDER_63, MAX_JUKYU + 1):
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            G.Cut_ritu[nendo - SHONENDO][nenrei - UNDER_63] = \
                G.cut_ruiseki[si][nendo - ECON_SHONENDO][nenrei - NENREI_SUM]

    fp = G.fp_out[CUTA]
    w = fp.write

    for nendo in range(2005, SAISHUNENDO + 1):
        ni = nendo - ECON_SHONENDO
        out = ["%4d," % (nendo - 2000)]

        for nenrei in range(UNDER_63, MAX_JUKYU):
            if G.CUT_ONE_SHUTU == 1:
                out.append("%20.14e," % shutu)
            else:
                out.append("%20.14e,"
                           % G.cut_ruiseki[si][ni][nenrei - NENREI_SUM])

        if G.CUT_ONE_SHUTU == 1:
            out.append("%20.14e\n" % shutu)
        else:
            out.append("%20.14e\n"
                       % G.cut_ruiseki[si][ni][MAX_JUKYU - NENREI_SUM])

        w("".join(out))

    fp.close()
    G.fp_out[CUTA] = None
