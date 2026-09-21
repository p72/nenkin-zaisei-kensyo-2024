# -*- coding: utf-8 -*-
"""
基礎年金/read_file.c の忠実移植（国年の独自給付費と保険料）
============================================================
③国民年金が出した独自給付（死亡一時金・寡婦年金・付加年金）と、
決め打ちの保険料月額・住宅融資債権を読む。

読むファイル3本
---------------
    fp_in[DOKUZI]  DOKUZI{国年番号}-{経済}-{外枠}.csv  ③が出す独自給付
    fp_in[YUUSHI]  yuushi2024.csv                     住宅融資債権（百万円）
    fp_in[HOKEN]   hoken17000.csv                     保険料月額・付加保険料

`DOKUZI` の列は 0 年度 / 1 付加納付者数 / 2〜4 付加（新法・旧法老齢・
旧法通老）/ 5〜7 寡婦（新法・旧法納付・旧法免除）/ 8〜9 死亡一時金
（納付分・付加分）。

業務勘定への繰入の伸ばし方
--------------------------
`dtst()` が入れた 2020〜2024年度の実績・予算のあと、

1. 物価上昇率で伸ばす
2. さらに1号被保険者数の比で調整する

を**2つの別のループ**でやる。1つ目のループで `Fukushi[n]` が
`Fukushi[n-1]` を使うので、2つ目のループの結果は
「物価の累積 × 人数比」になる。

年度末値 → 年度間値
-------------------
支払遅れ2か月（`SHIHARAIOKURE`）で、

    年度間値 = 前年度末 × ( 2 + 6 ) / 12 + 当年度末 × ( 6 − 2 ) / 12

寡婦年金だけ前年度末に改定率を掛ける
（`( SHIHARAIOKURE + kaiteiritu × 6 ) / 12`）。

保険料の年額
------------
    保険料年額 = 前年度の月額 × 前年度の（1号 − 産休 − 育休）
               + 当年度の月額 × 当年度の（1号 − 産休 − 育休）× 11

3月分は前年度の月額で納めるので、前年度が1か月・当年度が11か月。

原本の癖をそのまま残しているところ
----------------------------------
1. **`while` の続行条件に `buffer[0] > previous_buffer0` が入っている。**
   年度が増えなくなったら止まる。ファイルの末尾に合計行などがあっても
   読み込まないようにする作り。`previous_buffer0` は関数の頭で
   `-1000.` に入れ直す。

2. **`Ichijikin` の係数だけ `( SHIHARAIOKURE + 6. )` と
   `( SHIHARAIOKURE + 6 )` で書き方が違う**（`read_file.c:336,340`）。
   前者は `double`、後者は `int` だが、どちらも 8 になるので同じ。

3. **`Kafu` のループが `counter <= OLD_MENJO`（3）、`Fuka` が
   `counter <= OLD_TURO`（3）。**`OLD_MENJO` と `OLD_TURO` は
   どちらも 3 なので同じ範囲。名前だけ違う。

4. **`SHIHARAIOKURE` を `#define` で関数の中に書いている**
   （`read_file.c:265`）。`Atamawari.c` と `Atamawari_cut.c` にも
   同じ `#define` がある（値も 2 で同じ）。

5. **`nenrei` を宣言するだけで使わない。**

6. **`fclose( fp_in[DOKUZI] )` のあと `main.c` がもう一度閉じようと
   する。**glibc ではヒープが壊れて落ちるので、移植パッチで
   `main.c` 側を消してある（`検証/実行/patches/glibc-portability.patch`）。
"""
from cnum import Buffer, Round
from glva import G
from setconst import (
    DOKUZI, ECON_SHONENDO, HOKEN, KOKUNEN, NEW, NOUFU, OLD_MENJO,
    OLD_NOUFU, OLD_ROREI, OLD_TURO, SAISHUNENDO, SHONENDO, SUIKEISHONENDO,
    SUM, UNDER_67, YUUSHI, FUKA,
)

__all__ = ["read_file"]

SHIHARAIOKURE = 2


def read_file():
    """read_file.c:263 の忠実移植。"""
    buffer = Buffer()

    # ---- 業務勘定への繰入を伸ばす ----
    for nendo in range(G.FUKUSHI_NENDO + 1, SAISHUNENDO + 1):
        G.Fukushi[nendo - SHONENDO] = (G.Fukushi[nendo - 1 - SHONENDO]
                                       * G.cpi_up[nendo - ECON_SHONENDO])

    for nendo in range(G.FUKUSHI_NENDO + 1, SAISHUNENDO + 1):
        G.Fukushi[nendo - SHONENDO] *= (
            G.Hiho_Kokunen[nendo - SHONENDO]
            / G.Hiho_Kokunen[G.FUKUSHI_NENDO - SHONENDO])

    # ---- 独自給付（DOKUZI） ----
    previous_buffer0 = -1000.
    fp = G.fp_in[DOKUZI]
    fp.read_headder()

    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1 or not buffer[0] > previous_buffer0:
            break
        nendo = int(buffer[0])
        if SHONENDO <= nendo <= SAISHUNENDO:
            sn = nendo - SHONENDO
            G.Fuka_Ninzu[sn] = buffer[1]
            G.Fuka_Nendomatu[sn][NEW] = buffer[2]
            G.Fuka_Nendomatu[sn][OLD_ROREI] = buffer[3]
            G.Fuka_Nendomatu[sn][OLD_TURO] = buffer[4]

            G.Kafu_Nendomatu[sn][NEW] = buffer[5]
            G.Kafu_Nendomatu[sn][OLD_NOUFU] = buffer[6]
            G.Kafu_Nendomatu[sn][OLD_MENJO] = buffer[7]

            G.Ichijikin_Nendomatu[sn][NOUFU] = buffer[8]
            G.Ichijikin_Nendomatu[sn][FUKA] = buffer[9]
        previous_buffer0 = buffer[0]

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        G.Fuka_Nendomatu[sn][SUM] = (G.Fuka_Nendomatu[sn][NEW]
                                     + G.Fuka_Nendomatu[sn][OLD_ROREI]
                                     + G.Fuka_Nendomatu[sn][OLD_TURO])

        G.Kafu_Nendomatu[sn][SUM] = (G.Kafu_Nendomatu[sn][NEW]
                                     + G.Kafu_Nendomatu[sn][OLD_NOUFU]
                                     + G.Kafu_Nendomatu[sn][OLD_MENJO])

        G.Ichijikin_Nendomatu[sn][SUM] = (G.Ichijikin_Nendomatu[sn][NOUFU]
                                          + G.Ichijikin_Nendomatu[sn][FUKA])

    G.fp_in[DOKUZI] = None          # 原本の `fclose( fp_in[DOKUZI] )`

    # ---- 年度末値 → 年度間値 ----
    for nendo in range(SUIKEISHONENDO + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO

        G.Ichijikin[sn][NOUFU] = (
            G.Ichijikin_Nendomatu[sn - 1][NOUFU] * (SHIHARAIOKURE + 6.) / 12.
            + G.Ichijikin_Nendomatu[sn][NOUFU] * (6 - SHIHARAIOKURE) / 12.)

        G.Ichijikin[sn][FUKA] = (
            G.Ichijikin_Nendomatu[sn - 1][FUKA] * (SHIHARAIOKURE + 6) / 12.
            + G.Ichijikin_Nendomatu[sn][FUKA] * (6 - SHIHARAIOKURE) / 12.)

        G.Ichijikin[sn][SUM] = G.Ichijikin[sn][NOUFU] + G.Ichijikin[sn][FUKA]

        kt = G.kaiteiritu[nendo - ECON_SHONENDO][UNDER_67 - UNDER_67]
        for counter in range(SUM, OLD_MENJO + 1):
            G.Kafu[sn][counter] = (
                G.Kafu_Nendomatu[sn - 1][counter]
                * (SHIHARAIOKURE + kt * 6) / 12.
                + G.Kafu_Nendomatu[sn][counter] * (6 - SHIHARAIOKURE) / 12.)

        for counter in range(SUM, OLD_TURO + 1):
            G.Fuka[sn][counter] = (
                G.Fuka_Nendomatu[sn - 1][counter] * (SHIHARAIOKURE + 6) / 12.
                + G.Fuka_Nendomatu[sn][counter] * (6 - SHIHARAIOKURE) / 12.)

    # ---- 住宅融資債権（百万円） ----
    previous_buffer0 = -1000.
    fp = G.fp_in[YUUSHI]
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1 or not buffer[0] > previous_buffer0:
            break
        nendo = int(buffer[0])
        if SHONENDO <= nendo <= SAISHUNENDO:
            G.Yuushi_Saiken[nendo - SHONENDO] = buffer[1] * 1000000.
        previous_buffer0 = buffer[0]

    G.fp_in[YUUSHI] = None

    # ---- 保険料月額・付加保険料 ----
    previous_buffer0 = -1000.
    fp = G.fp_in[HOKEN]
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1 or not buffer[0] > previous_buffer0:
            break
        nendo = int(buffer[0])
        if nendo >= SHONENDO:
            G.Hokenryou_m[nendo - SHONENDO][0] = buffer[1]
            G.Fuka_Hokenryou_m[nendo - SHONENDO] = buffer[2]
        previous_buffer0 = buffer[0]

    G.fp_in[HOKEN] = None

    # ---- 価格をかけて 10 円単位に丸める ----
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        G.Hokenryou_m[sn][1] = (G.Hokenryou_m[sn][0]
                                * G.kakaku[nendo - ECON_SHONENDO])

        if nendo <= G.MARUME_NENDO:
            G.Hokenryou_m[sn][1] = Round(G.Hokenryou_m[sn][1], 1)

    # ---- 保険料の年額・子ども納付金・付加保険料の年額 ----
    St = G.SanteiTaishou
    for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        G.Hokenryou_y[sn] = (
            G.Hokenryou_m[sn - 1][1]
            * (St[KOKUNEN][sn - 1][1] - G.Sankyu_Taishou[sn - 1]
               - G.Ikukyu_Taishou[sn - 1])
            + G.Hokenryou_m[sn][1]
            * (St[KOKUNEN][sn][1] - G.Sankyu_Taishou[sn]
               - G.Ikukyu_Taishou[sn]) * 11.)

        G.Kodomo_Noufukin[sn] = (
            G.Hokenryou_m[sn - 1][1] * G.Ikukyu_Taishou[sn - 1]
            + G.Hokenryou_m[sn][1] * G.Ikukyu_Taishou[sn] * 11.)

        G.Fuka_Hokenryou_y[sn] = (
            G.Fuka_Hokenryou_m[sn - 1] * G.Fuka_Ninzu[sn - 1]
            + G.Fuka_Hokenryou_m[sn] * G.Fuka_Ninzu[sn] * 11.)

    return
