# -*- coding: utf-8 -*-
"""
被保険者推計/set.h の忠実移植
=============================
①被保険者推計の定数と、原本の関数の一覧。

年度の表し方が⑤⑥と違う
-----------------------
⑤⑥は「西暦 − 2000」（2024年度 → 24）だったが、**①は西暦そのまま**で、
配列の添字は `nendo - STARTY` にする。

    STARTY   2020   配列の先頭に当たる年度
    ENDY     2150   配列の末尾に当たる年度（131年度ぶん）
    KIJUN    2022   実績の基準年度
    KIJUNMAP 2023   被保険者数（map）の最終実績年度
    KS       2021   推計の開始年度
    KF       2125   推計の終了年度
    CNENDO   2005   調整率（cutritu）の先頭年度
    CUT_JY   2024   調整率の実績がある最終年度
    DATA_MAX 130    read_csv が1行から読める最大個数
    BUFFER_MAX 31   read_csv が1つのデータに使う文字数の上限

`DATA_MAX` と `BUFFER_MAX` は `stdfun` の `read_csv` の上限で、
超えると原本は `exit(1)` する。

配列の寸法
----------
`cntl.h` の宣言から。年齢は 0〜120（121通り）、性別は 0〜4（5通り）で、
0 が「男女計」、1 が男、2 が女。3 と 4 は有配偶・無配偶の区分に使われる
（`readdata.c:72-75` が `jinko_wari[3]`/`[4]` に女の値を入れている）。

いちばん大きいのは `partnin` と `p_wari` で、どちらも

    [131][5][121][8][4][4] = 10,144,640 要素 = 81MB

原本は静的領域に置いているので、2つで 162MB。移植版は NumPy で同じ
バイト並びになる（`float64` の C 順）。
"""

__all__ = [
    "STARTY", "ENDY", "KIJUN", "KIJUNMAP", "KS", "KF", "CNENDO", "CUT_JY",
    "DATA_MAX", "BUFFER_MAX", "NY", "NSEI", "NAGE",
]

STARTY = 2020
ENDY = 2150
KIJUN = 2022
KIJUNMAP = 2023
KS = 2021
KF = 2125
CNENDO = 2005
CUT_JY = 2024
DATA_MAX = 130
BUFFER_MAX = 31

# よく出る寸法
NY = ENDY - STARTY + 1        # 131。年度
NSEI = 5                      # 0〜4。0 が男女計
NAGE = 121                    # 0〜120 歳
