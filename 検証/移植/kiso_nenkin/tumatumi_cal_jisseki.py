# -*- coding: utf-8 -*-
"""
基礎年金/tumatumi_cal_jisseki.c の忠実移植（妻積の取り崩しと分配）
===================================================================
「妻積」は2014年度末までに積み上がった基礎年金の積立金のうち、各制度へ
返す分。原価 `Tumatumi_2014[SUM]`（1兆5,528億円）を10年
（`TUMATUMI_KIKAN`）で**均等に取り崩す**。

    Tumatumi[SUM][2015] = 原価 − 原価/10
    Tumatumi[SUM][n]    = Tumatumi[SUM][n-1] − 原価/10

なので `Tumatumi[SUM][2024]` は 0 になる（浮動小数の丸めぶんだけ残る）。

各制度への分配（2022〜2024年度）
--------------------------------
`Tumatumi[BUNPAI][年度]`（`dtst()` が置いた実績の分配額）を半分ずつ、

    国年   拠出金算定対象者の1号の割合
    被用者 制度計の割合 ＋ （2号＋3号）の割合

で分ける。1号は「制度計の割合」しか使わず、被用者は2つの割合を足すので
**合計は 1 にならない**（1号の2号3号ぶんが抜ける）。実績値を割り振る
ための便宜的な按分。

出力（`TUMATUMI-...-00.csv`）
-----------------------------
    2014年度（原価の行）  0, 0, 0, 0, 0, 原価
    2015〜2125年度        国年, 厚年, 国共, 地共, 私学, 妻積残額

原本の癖をそのまま残しているところ
----------------------------------
1. **`KAISHI1 - 1` から回すので 2022〜2024年度の3年ぶんだけ。**
   `TUMATUMI_NENDO + TUMATUMI_KIKAN - 1` = 2024。2015〜2021年度の
   制度別は 0 のまま出力される。（`検証/原本の不具合.md`）

2. **`buffer` と `data_number` を宣言するだけで使わない。**

3. **1行目の「原価」の年度を `TUMATUMI_NENDO - 1 - 2000` = 14 と書く。**
   西暦下2桁。以降の行も `nendo - 2000`。

4. **出力を閉じたあと `printout()` が同じ配列を読む。**閉じるのは
   ファイルだけなので問題にならない。
"""
from glva import G
from setconst import (
    BUNPAI, KOKUNEN, KOUNEN, SAISHUNENDO, SHIGAKU, SHONENDO, SUM,
    TUMATUMI_KIKAN, TUMATUMI_NENDO, TUMATUMI_OUT,
)

__all__ = ["tumatumi_cal_jisseki"]


def tumatumi_cal_jisseki():
    """tumatumi_cal_jisseki.c:190 の忠実移植。"""
    Tu = G.Tumatumi
    St = G.SanteiTaishou

    for nendo in range(TUMATUMI_NENDO,
                       TUMATUMI_NENDO + TUMATUMI_KIKAN):
        i = nendo - TUMATUMI_NENDO
        if nendo == TUMATUMI_NENDO:
            Tu[SUM][i] = (G.Tumatumi_2014[SUM]
                          - (G.Tumatumi_2014[SUM] * 1. / TUMATUMI_KIKAN))
        else:
            Tu[SUM][i] = (Tu[SUM][i - 1]
                          - (G.Tumatumi_2014[SUM] * 1. / TUMATUMI_KIKAN))

    # 癖 1. 2022〜2024年度の3年ぶん
    for nendo in range(G.KAISHI1 - 1,
                       TUMATUMI_NENDO + TUMATUMI_KIKAN):
        i = nendo - TUMATUMI_NENDO
        sn = nendo - SHONENDO

        Tu[KOKUNEN][i] = (Tu[BUNPAI][i] / 2.
                          * St[KOKUNEN][sn][1] / St[SUM][sn][SUM])

        for seido in range(KOUNEN, SHIGAKU + 1):
            Tu[seido][i] = (
                Tu[BUNPAI][i] / 2.
                * (St[seido][sn][SUM] / St[SUM][sn][SUM]
                   + ((St[seido][sn][2] + St[seido][sn][3])
                      / (St[SUM][sn][2] + St[SUM][sn][3]))))

    fp = G.fp_out[TUMATUMI_OUT]
    w = fp.write

    w("%d," % (TUMATUMI_NENDO - 1 - 2000))
    w("%20.14e," % 0.)
    for _seido in range(KOUNEN, SHIGAKU + 1):
        w("%20.14e," % 0.)
    w("%20.14e\n" % G.Tumatumi_2014[SUM])

    for nendo in range(TUMATUMI_NENDO, SAISHUNENDO + 1):
        i = nendo - TUMATUMI_NENDO
        w("%d," % (nendo - 2000))
        for seido in range(KOKUNEN, SHIGAKU + 1):
            w("%20.14e," % Tu[seido][i])
        w("%20.14e\n" % Tu[SUM][i])

    fp.close()
    G.fp_out[TUMATUMI_OUT] = None
