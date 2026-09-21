# -*- coding: utf-8 -*-
"""
基礎年金/dtst.c の忠実移植（決め打ちの実績値と初期値）
========================================================
決算の実績値と、あとで上書きされる配列の初期値を置く。

ソースに埋まっている実績値
--------------------------
    Tumatumi_2014[SUM]  1,552,833,257,900 円
        2014年度末の「妻積」（基礎年金の積立金のうち各制度へ分配する分）
        の原価。10年（`TUMATUMI_KIKAN`）で均等に取り崩す。

    Tumatumi[BUNPAI][2015〜2024]  各年度の分配額（1,553〜1,597 億円）

    Fukushi[2020〜2024]  業務勘定への繰入
        `FUKUSHI_NENDO`（2024）を起点に5年ぶん。2020・2021・2022 は
        決算値、2023・2024 は予算値。

    Tumitate[2020〜2022]  国年の年度末積立金（億円 → 円に直す）
        116,365 / 121,176 / 124,290 億円

`zisseki_hosei.csv` から読む補正率
----------------------------------
`hosei_shin[老齢/障害/遺族]` と `hosei_kyu[国年/厚年]` を
2021〜2026年度ぶん読む（`SHONENDO + 1` 〜 `SHONENDO + 6`）。
1行目は読み捨てる。給付費の実績に合わせる補正。

モデル年金
----------
    MODEL_PENSION = 133960 / ( 0.994 × 0.996 )
    MODEL_WAGE    = 369915

`133960` は2024年度の夫婦2人ぶんの基礎年金の月額、`0.994 × 0.996` で
2023・2024年度のマクロ経済スライドを戻している。`tyousei()` が
「代替率換算」を出すのに使う。

原本の癖をそのまま残しているところ
----------------------------------
1. **`tuki[]` に 4 を入れる三重の `{}`。**
   ```c
   for( nendo = ... ) { sotai_nendo = ... ; { tuki[sotai_nendo] = 4 ; } }
   ```
   内側の `{}` に意味は無い。しかも `tuki` はどこからも読まれない。
   （`検証/原本の不具合.md`）

2. **`cut_ruiseki` の初期化が 125 × 125 × 54 = 843,750 回。**
   実際に使うのは `c_nendo >= 2005`・`nendo >= 2023` の一部だけ。
   移植版は NumPy の一括代入にしてある（値は同じ）。

3. **`Fukushi` の添字が `FUKUSHI_NENDO - 4 - SHONENDO` = 0 から。**
   `FUKUSHI_NENDO` を 2023 以下にすると負の添字になる。

4. **`MODEL_PENSION` の分子が整数の割り算にならないのは C の昇格規則
   のため。**`133960 / ( 0.994 * 0.996 )` は右辺が `double` なので
   `133960` も `double` に上がる。Python でも同じ。
"""
from cnum import Buffer
from glva import G
from setconst import (
    BUNPAI, ECON_SHONENDO, IZOKU, KOKUNEN, KOUNEN, MAX_JUKYU, NENREI_SUM,
    ROREI, SAISHUNENDO, SHIGAKU, SHOGAI, SHONENDO, SUM, TOKUBETU_20MAE,
    TOKUBETU_GONEN, TOKUBETU_KASAAGE, TOKUBETU_KASAMENJO, TOKUBETU_MENJO,
    TOKUBETU_SHITASASAE, TUMATUMI_NENDO, UNDER_63, UNDER_67, zisseki_hosei,
)

__all__ = ["dtst"]

HIKIAGE_NENDO = 2009

# 妻積の分配額（`dtst.c:30-39`）。2015〜2024年度
_TUMATUMI_BUNPAI = {
    2015: 159094034794.0,
    2016: 159113373167.0,
    2017: 155730757637.0,
    2018: 155722505415.0,
    2019: 155706999522.0,
    2020: 155691472107.0,
    2021: 155664967139.0,
    2022: 155622975560.0,
    2023: 155499428227.0,
    2024: 155334733769.0,
}

# 業務勘定への繰入（`dtst.c:43-47`）。FUKUSHI_NENDO からの相対年
_FUKUSHI = {-4: 64122425512.0, -3: 61434162241.0, -2: 55579456448.0,
            -1: 54100000000.0, 0: 53900000000.0}

# 国年の年度末積立金（`dtst.c:50-52`）。億円
_TUMITATE_OKU = {2020: 116365.0, 2021: 121176.0, 2022: 124290.0}


def dtst():
    """dtst.c:12 の忠実移植。"""
    fp_z = G.fp_in[zisseki_hosei]
    buffer = Buffer()

    G.Tumatumi_2014[SUM] = 1552833257900.0
    for nendo, v in _TUMATUMI_BUNPAI.items():
        G.Tumatumi[BUNPAI][nendo - TUMATUMI_NENDO] = v

    G.FUKUSHI_NENDO = 2024
    for d, v in _FUKUSHI.items():
        G.Fukushi[G.FUKUSHI_NENDO + d - SHONENDO] = v

    for nendo, v in _TUMITATE_OKU.items():
        G.Tumitate[nendo - SHONENDO] = v * 100000000

    # 癖 1. tuki はどこからも読まれない
    G.tuki[0:SAISHUNENDO - SHONENDO + 1] = 4

    # 国庫負担割合。2009年度から 1/2（それ以前は 1/3 + 25/1000）
    for nendo in range(SHONENDO - 1, SAISHUNENDO + 1):
        i = nendo - (SHONENDO - 1)
        G.Kokko_Wariai[i] = 1.0 / 3.0 + 25.0 / 1000.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_MENJO] = 1.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_KASAAGE] = 1.0 / 4.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_KASAMENJO] = 1.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_SHITASASAE] = 1.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_GONEN] = 1.0 / 8.0
        G.Tokubetu_Kokko_Wariai[i][TOKUBETU_20MAE] = 38.0 / 100.0

        if nendo >= HIKIAGE_NENDO:
            G.Kokko_Wariai[i] = 1.0 / 2.0
            G.Tokubetu_Kokko_Wariai[i][TOKUBETU_20MAE] = 2.0 / 10.0

    # 給付費の補正率。既定は 1.0
    ny = SAISHUNENDO - SHONENDO + 1
    G.hosei_shin[ROREI][0:ny] = 1.0
    G.hosei_shin[SHOGAI][0:ny] = 1.0
    G.hosei_shin[IZOKU][0:ny] = 1.0
    for seido in range(SUM, SHIGAKU + 1):
        G.hosei_kyu[seido][0:ny] = 1.0

    # zisseki_hosei.csv。1行目を読み捨てて6行
    fp_z.read_data(buffer)
    for nendo in range(SHONENDO + 1, SHONENDO + 7):
        rc, _ = fp_z.read_data(buffer)
        if rc != -1:
            i = nendo - SHONENDO
            G.hosei_shin[ROREI][i] = buffer[1]
            G.hosei_shin[SHOGAI][i] = buffer[2]
            G.hosei_shin[IZOKU][i] = buffer[3]

            G.hosei_kyu[KOKUNEN][i] = buffer[4]
            G.hosei_kyu[KOUNEN][i] = buffer[5]

    G.MODEL_PENSION = 133960 / (0.994 * 0.996)
    G.MODEL_WAGE = 369915

    # カット率の初期値（`read_cut` か `file_write_cut` が上書きする）
    G.Cut_ritu[0:ny, UNDER_63 - UNDER_63:MAX_JUKYU - UNDER_63 + 1] = 1.0

    # 癖 2. 累積カット率の初期値
    ne = SAISHUNENDO - ECON_SHONENDO + 1
    G.cut_ruiseki[0:ne, 0:ne,
                  NENREI_SUM - NENREI_SUM:MAX_JUKYU - NENREI_SUM + 1] = 1.0

    nc = MAX_JUKYU - UNDER_67 + 1
    G.pre_cut[0:ne, 0:nc] = 1.0
    G.kaiteiritu[0:ne, 0:nc] = 1.0
    G.kaiteiritu_cut[0:ne, 0:nc] = 1.0
    G.T[0:ne, 0:nc] = 1.0

    return
