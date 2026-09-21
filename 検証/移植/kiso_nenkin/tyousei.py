# -*- coding: utf-8 -*-
"""
基礎年金/tyousei.c の忠実移植（マクロ経済スライドの終了年度を解く）
====================================================================
④のいちばん外側の目的。「国民年金の積立金が `T_NENDO`（2120）年度に
1年分の支出（`T_DOAI` = 1）を残すには、マクロ経済スライドをいつまで
続ければよいか」を探す。

段取り
------
1. **年単位で前から探す**（`c_nendo = 2005` から `T_NENDO` まで）
   `Atamawari_cut( c_nendo )` を呼んで積立金を試算し、
   `Tumitate[2119] >= Shishutu[2120] × 1` になった最初の年度で止める。
   ただし `c_nendo >= 2024` になるまでは止めない（2024年度までは
   実績で決まっているため）。
2. **その年度の中を二分法で 128 回刻む**（`S_C_NENDO > 2024` のとき）
   終了年度を「年度の途中」まで細かく決める。`cut_ruiseki` を
   前年度ぶんと当年度ぶんの平均に置き換えながら 128 回半分にすると、
   2^-128 の精度になる（実質は倍精度の限界まで）。
3. `kaiteiritu` を `kaiteiritu_cut`（調整後）に差し替える。

この「128 回の二分法」が④の実行時間のほとんどを占める。

出力
----
    標準出力    最終カット率 / 代替率換算
    output.csv  `試算番号,代替率,終了年度,`
    SETTEI      `main.c` が「カット終了年度 ○○」を書く

原本の癖をそのまま残しているところ
----------------------------------
1. **`c_nendo` をループの外で読む**（`tyousei.c:129`）。`for` を
   `break` で抜ければその年度、抜けずに終われば `T_NENDO + 1`。
   C ではループ変数が関数の先頭で宣言されているので合法。
   （`検証/原本の不具合.md`）

2. **「調整できません」の枝が `break` するだけで `S_C_NENDO` を
   直さない。**`c_nendo >= T_NENDO` で抜けるので `S_C_NENDO = T_NENDO`
   になる。

3. **`Shishutu` の作り方が1周目と二分法で違う。**
   1周目は
   `Kiso_Cut + Ichijikin_Cut[SUM] + Kafu_Cut[SUM] + Fuka[SUM] + Fukushi`、
   二分法は
   `Kiso_Cut + Ichijikin_Cut[0] + Kafu_Cut[0] + Fukushi + Fuka[SUM]`。
   `SUM` は 0 なので値は同じだが、**足す順番が違う**
   （`Fukushi` と `Fuka` が入れ替わっている）ので浮動小数では
   1ビット変わりうる。移植版も原本のとおり分けて書いてある。

4. **1周目の `nendo` ループが `T_NENDO` まで、二分法は
   `SAISHUNENDO` まで。**1周目は 2120年度までしか積立金を作らない。

5. **`Kiso_Cut_Jisshitu` などの局所配列を毎回 0 で埋め直さない。**
   頭で1回だけ埋める。`nendo` の範囲が変わるので 2121〜2125年度の
   `Shishutu` は1周目のあいだ 0 のまま。二分法で埋まる。

6. **`Fukushi_Cut` に `Fukushi` を写すだけ。**どこからも読まれない。

7. **`cut_ruiseki_a` / `cut_ruiseki_b` が初期化のない自動変数。**
   `S_C_NENDO > 2024` の枝で `KAISHI1`（2023）以降だけ埋めるので、
   2001〜2022年度ぶんは不定値のまま。読むのも 2023 年度以降。
"""
import math

import numpy as np

from atamawari_cut import Atamawari_cut
from glva import G
from setconst import (
    ECON_SHONENDO, FUKA, KOKUNEN, MAX_JUKYU, NENREI_SUM, NEW, NOUFU,
    OLD_NOUFU, OUTPUT, SAISHUNENDO, SETTEI, SHONENDO, SUM, TUMATUMI_NENDO,
    UNDER_63, UNDER_67,
)

__all__ = ["tyousei"]

_NY = SAISHUNENDO - SHONENDO + 1
_NE = SAISHUNENDO - ECON_SHONENDO + 1
_NJ = MAX_JUKYU - NENREI_SUM + 1
_J0 = NENREI_SUM - NENREI_SUM


def tyousei():
    """tyousei.c:17 の忠実移植。"""
    # 癖 7. 初期化のない自動変数
    cut_ruiseki_a = np.zeros((_NE, _NJ))
    cut_ruiseki_b = np.zeros((_NE, _NJ))

    Kiso_Cut_Jisshitu = np.zeros(_NY)
    Kiso_Cut = np.zeros(_NY)
    Shishutu_Jisshitu = np.zeros(_NY)
    Shishutu = np.zeros(_NY)

    # ---- 調整前の積立金 ----
    for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        ir = G.interest_rate[nendo - ECON_SHONENDO]
        G.Tumitate[sn] = (
            G.Tumitate[sn - 1] * ir
            + (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
               + G.Kyoshutukin_Kokko[KOKUNEN][sn][_J0][SUM]
               + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
               + G.Yuushi_Saiken[sn]
               + G.Kodomo_Noufukin[sn]
               - G.Kyoshutukin[KOKUNEN][sn][_J0][SUM]
               - G.Ichijikin[sn][NOUFU] - G.Ichijikin[sn][FUKA] * 3. / 4.
               - G.Kafu[sn][NEW] - G.Kafu[sn][OLD_NOUFU]
               - G.Fuka[sn][SUM] * 3. / 4.
               - G.Fukushi[sn])
            * math.pow(ir, 1. / 2.))

    nc = MAX_JUKYU - UNDER_67 + 1
    G.kaiteiritu_cut[0:_NE, 0:nc] = G.kaiteiritu[0:_NE, 0:nc]

    # ---- 1. 年単位で前から探す（癖 1.） ----
    c_nendo = G.C_NENDO + 1
    for c_nendo in range(G.C_NENDO + 1, G.T_NENDO + 1):
        ci = c_nendo - ECON_SHONENDO
        G.kaiteiritu_cut[ci, 0:nc] = (G.kaiteiritu[ci, 0:nc]
                                      / G.pre_cut[ci, 0:nc])

        Atamawari_cut(c_nendo)

        _shishutu_1(Kiso_Cut_Jisshitu, Kiso_Cut, Shishutu_Jisshitu, Shishutu,
                    G.T_NENDO)

        if (G.Tumitate[G.T_NENDO - 1 - SHONENDO]
                < Shishutu[G.T_NENDO - SHONENDO] * G.T_DOAI):
            if c_nendo >= G.T_NENDO:
                print("調整できません")
                G.fp_out[SETTEI].write("調整期間中に調整出来ず\n")
                break
        elif c_nendo >= 2024:
            break
    else:
        # `for` を抜けずに終わったとき、C の `c_nendo` は T_NENDO + 1
        c_nendo = G.T_NENDO + 1

    G.S_C_NENDO = c_nendo
    print("マクロ経済スライド終了年度 %d" % G.S_C_NENDO)

    # ---- 2. 年度の中を二分法で 128 回刻む ----
    if G.S_C_NENDO > 2024:
        si = G.S_C_NENDO - ECON_SHONENDO
        lo = G.KAISHI1 - ECON_SHONENDO
        hi = SAISHUNENDO - ECON_SHONENDO + 1
        J = slice(0, _NJ)

        cut_ruiseki_b[lo:hi, J] = G.cut_ruiseki[si, lo:hi, J]
        cut_ruiseki_a[lo:hi, J] = G.cut_ruiseki[si - 1, lo:hi, J]

        counter = 1
        while counter <= 128:
            G.cut_ruiseki[si, lo:hi, J] = (cut_ruiseki_a[lo:hi, J]
                                           + cut_ruiseki_b[lo:hi, J]) / 2.

            G.kaiteiritu_cut[si, 0:nc] = (
                G.kaiteiritu[si, 0:nc]
                * G.cut_ruiseki[si, si, UNDER_67 - NENREI_SUM:_NJ]
                / G.cut_ruiseki[si - 1, si, UNDER_67 - NENREI_SUM:_NJ])

            Atamawari_cut(G.S_C_NENDO)

            _shishutu_2(Kiso_Cut_Jisshitu, Kiso_Cut, Shishutu_Jisshitu,
                        Shishutu)

            if (G.Tumitate[G.T_NENDO - 1 - SHONENDO]
                    < Shishutu[G.T_NENDO - SHONENDO] * G.T_DOAI):
                cut_ruiseki_a[lo:hi, J] = G.cut_ruiseki[si, lo:hi, J]
            else:
                cut_ruiseki_b[lo:hi, J] = G.cut_ruiseki[si, lo:hi, J]
            counter += 1

    si = G.S_C_NENDO - ECON_SHONENDO
    saisyu = G.cut_ruiseki[si][si][UNDER_63 - NENREI_SUM]
    print("最終カット率 %11.9e" % saisyu)
    print("代替率換算 %f％"
          % (G.MODEL_PENSION * saisyu / G.MODEL_WAGE * 100.0))

    fo = G.fp_out[OUTPUT]
    fo.write("%s-%s," % (G.Version, G.Version_cut))
    fo.write("%f," % (G.MODEL_PENSION * saisyu / G.MODEL_WAGE * 100.0))
    fo.write("%d," % G.S_C_NENDO)

    G.kaiteiritu[0:_NE, 0:nc] = G.kaiteiritu_cut[0:_NE, 0:nc]

    return


def _shishutu_1(Kiso_Cut_Jisshitu, Kiso_Cut, Shishutu_Jisshitu, Shishutu,
                last):
    """tyousei.c:78-112。1周目の支出と積立金（`nendo` は `T_NENDO` まで）。"""
    for nendo in range(G.KAISHI1, last + 1):
        sn = nendo - SHONENDO

        Kiso_Cut_Jisshitu[sn] = (G.Kyoshutukin_Cut[sn][_J0]
                                 - G.Kyoshutukin_Kokko_Cut[sn][_J0])

        Kiso_Cut[sn] = (G.Kyoshutukin_Cut[sn][_J0]
                        + G.Tokubetukokko_Cut[sn][_J0][SUM])

        G.Fukushi_Cut[sn] = G.Fukushi[sn]      # 癖 6.

        Shishutu_Jisshitu[sn] = (
            Kiso_Cut_Jisshitu[sn]
            + G.Ichijikin_Cut[sn][NOUFU] + G.Ichijikin_Cut[sn][FUKA] * 3. / 4.
            + G.Kafu_Cut[sn][NEW] + G.Kafu_Cut[sn][OLD_NOUFU]
            + G.Fuka[sn][SUM] * 3. / 4.
            + G.Fukushi[sn])

        # 癖 3. 1周目はこの順番
        Shishutu[sn] = (Kiso_Cut[sn]
                        + G.Ichijikin_Cut[sn][SUM]
                        + G.Kafu_Cut[sn][SUM]
                        + G.Fuka[sn][SUM]
                        + G.Fukushi[sn])

        ir = G.interest_rate[nendo - ECON_SHONENDO]
        G.Tumitate[sn] = (
            G.Tumitate[sn - 1] * ir
            + (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
               + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
               + G.Yuushi_Saiken[sn]
               + G.Kodomo_Noufukin[sn]
               - Shishutu_Jisshitu[sn])
            * math.pow(ir, 1. / 2.))


def _shishutu_2(Kiso_Cut_Jisshitu, Kiso_Cut, Shishutu_Jisshitu, Shishutu):
    """tyousei.c:171-202。二分法の中（`nendo` は `SAISHUNENDO` まで）。"""
    for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO

        Kiso_Cut_Jisshitu[sn] = (G.Kyoshutukin_Cut[sn][_J0]
                                 - G.Kyoshutukin_Kokko_Cut[sn][_J0])

        Kiso_Cut[sn] = (G.Kyoshutukin_Cut[sn][_J0]
                        + G.Tokubetukokko_Cut[sn][_J0][SUM])

        G.Fukushi_Cut[sn] = G.Fukushi[sn]

        Shishutu_Jisshitu[sn] = (
            Kiso_Cut_Jisshitu[sn]
            + G.Ichijikin_Cut[sn][NOUFU] + G.Ichijikin_Cut[sn][FUKA] * 3. / 4.
            + G.Kafu_Cut[sn][NEW] + G.Kafu_Cut[sn][OLD_NOUFU]
            + G.Fuka[sn][SUM] * 3. / 4.
            + G.Fukushi[sn])

        # 癖 3. 二分法ではこの順番（Fukushi と Fuka が逆）
        Shishutu[sn] = (Kiso_Cut[sn]
                        + G.Ichijikin_Cut[sn][0]
                        + G.Kafu_Cut[sn][0]
                        + G.Fukushi[sn]
                        + G.Fuka[sn][SUM])

        ir = G.interest_rate[nendo - ECON_SHONENDO]
        G.Tumitate[sn] = (
            G.Tumitate[sn - 1] * ir
            + (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
               + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
               + G.Yuushi_Saiken[sn]
               + G.Kodomo_Noufukin[sn]
               - Shishutu_Jisshitu[sn])
            * math.pow(ir, 1. / 2.))
