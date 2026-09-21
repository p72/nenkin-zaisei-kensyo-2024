# -*- coding: utf-8 -*-
"""
国民年金/shke.c の忠実移植（1年度ぶんの集計）
=============================================
539 行。`main.c` が種別ごとに

```c
shke( SUIKEISHONENDO , shubetu );
for( nendo = SUIKEISHONENDO + 1 ; nendo <= SUIKEISAISHUNENDO ; nendo++ ) {
    siml( nendo , shubetu );
    shke( nendo , shubetu );
}
```

の形で **105回 + 1回** 呼ぶ。`siml()` が「年度末の人数」
（`*_Nendomatu`）を1年進め、`shke()` がそれに**支給率を掛けて
年度中の受給者数を出し、年齢階級ごとに足し上げる**。

出す先（`mkisosu.h`）

    Hiho_Kei / Hiho_Noufu / Fuka_Hiho          被保険者・納付・付加
    Hiho_Noufu_P / Fuka_Hiho_P                 ↑の「翌年度の率で見た」ぶん
    Hiho_Menjo / Hiho_Menjo_P                  免除（段階別）
    Rorei / Rorei_Kyu / Turo_Kyu / Gonen       老齢（新法・旧法・通算・5年）
    Shogai_Ippan / _20mae / _Kyu               障害
    Izoku_Tuma / _Otto / _Ko                   遺族
    Kafu / Kafu_Kyu                            寡婦
    Ichijikin                                  死亡一時金

年齢は 63歳以下をまとめる
-------------------------
```c
if( nenrei <= 63 ) …[UNDER_63 - NENREI_SUM]… else …[nenrei - NENREI_SUM]…
```

`NENREI_SUM` = 62、`UNDER_63` = 63 なので添字は

    [0] = 合計（`SUM`。`stat()` が埋める）
    [1] = 63歳以下
    [2]〜[8] = 64歳〜70歳（老齢は 115歳まで）

`+=` で足し込むので**年度をまたいで消さない**
-------------------------------------------
`Hiho_*` も `Rorei` 系も 0 に戻さずに `+=` する。年度の添字
（`sotai_nendo`）が違うので同じ年度を2回呼ばなければ足し込みは
起きないが、**`shke( SUIKEISHONENDO )` は種別ごとに1回ずつなので
種別の添字で分かれている**。`main.c` の呼び方でしか成り立たない。

局所の `*_Shikyu` は全部 0 から始まる
-------------------------------------
```c
struct rorei Rorei_Shikyu[56][11] = {0.,0.,{0.},0.,0.};
```

C の集成体初期化は「最初の要素を書いた値で埋め、**残りは
ゼロ初期化**」なので、これは全要素 0 と同じ。移植版も
`np.zeros` にした。

最終年度の枝は境界を守るためだけにある
--------------------------------------
`Hiho_Noufu_P` `Hiho_Menjo_P` `Fuka_Hiho_P` は「翌年度の納付率を
今年度の人数に掛けたもの」で、ふつうは
`Noufuritu[shubetu][sotai_nendo + 1][nenrei + 1]` を読む。
`nendo == SAISHUNENDO`（2125年度）では `sotai_nendo + 1` が
配列の外（106。寸法は 106）になるので、**年度を進めない枝**が
別に書かれている。

その枝の中で**年齢の添字が段階で食い違っている**。

```c
if( dankai == ZENGAKU )
    … Hihokensha[sotai_nendo][nenrei     - MIN_HIHO_NENREI][kikan].ninzu …
else
    … Hihokensha[sotai_nendo][nenrei + 1 - MIN_HIHO_NENREI][kikan].ninzu …
```

`Hiho_Noufu_P` も一般の枝も `nenrei` を使うので、`nenrei + 1` の
ほうが浮いている。ただし `stat()` が読むのは
`Hiho_Menjo_P[shubetu][sotai_nendo - 1]`（`nendo` は 2022〜2125）
なので**2125年度ぶんは誰も読まない**。出力には出ない
（`検証/原本の不具合.md` **F25**）。

繰下げ75歳化の移行措置（`Waribikiritu`）
---------------------------------------
2020年改正で繰下げの上限が 70歳 → 75歳になったが、`Rorei_Nendomatu`
の受給開始年齢の枠は **60〜70歳しか無い**（`KURI_AGE_SAGE_SHIKYU_KUBUN`
= 11）。そこで**繰下げ年齢の枠に入れたまま人数と年金額を係数で
調整する**形で近似している。

対象は `shke.c:295-299` の条件で選ばれる**5つの（生年度, 繰下げ年齢）
の組だけ**。`nendo - nenrei` が生年度なので **生年度 = 2022 −
繰下げ年齢**（1952〜1956年度生）。1952年度生が改正の適用境界そのもの。

人数に掛ける係数（入力の4列目）は同梱データで

    min( (年齢 − 繰下げ年齢 + 1) / (76 − 繰下げ年齢) , 1 )

に完全に一致する。繰下げの実際の開始時期を**繰下げ年齢〜75歳に
均等に散らした**ときの「もう受給を始めている割合」で、75歳で 1 に
到達する。年金額に掛ける係数（5列目）の作り方は同梱資料からは
決められない（基礎率ファイル ＝ 外から与える前提）。

### 2032年度以降は人数の添字だけ間違えている

```c
else if( nendo > SUIKEISHONENDO + 10 )
{
    … .ninzu *= Waribikiritu[seibetu][0][jukyu_nenrei - 66][1];      /* ← 1 */
    … = adjustbenefit( Waribikiritu[seibetu][1][jukyu_nenrei - 66][9] , … );
}
```

4番目の添字は `nendo - SUIKEISHONENDO - 1` で読み込むので
**0 = 2022年度、9 = 2031年度**。移行が終わったあとは 9（= 1.0）を
使うのが筋で、**年金額のほうはそうしている**。人数だけ
**1（2023年度 = 0.2）**。

    0,66,2023,0.2,0.207580201236295     ← 添字 1
    0,66,2031,1.0,1.338929747777830     ← 添字 9

移植版で `[9]` に直した版と突き合わせると、老齢基礎（新法）の
年度末受給者数（4種別合計）はこうなる。

    2032年度  38,395,556 →  38,928,482 人  (+1.39%)
    2040年度  46,841,615 →  47,267,747 人  (+0.91%)
    2050年度  55,697,968 →  55,871,496 人  (+0.31%)

1マスの動きは極端で、第1号男・1956年度生・66歳繰下げは

    2031年度（75歳）  97,956 人
    2032年度（76歳）  19,153 人   ← ちょうど 1/5。以後、死亡するまで

**効くのは受給者数だけで給付費には出ない**（年金額は `[9]` を使い、
④が読む `KISONENKIN` は年金額の欄しか使わない）。同 **J3**。
移植版はそのまま写した。
"""
import numpy as np

from setconst import (HIHO_NENREI_SUM, KOKKO_HIKIAGE,
                      KURI_AGE_SAGE_SHIKYU_KUBUN, MAX_HIHO_KIKAN,
                      MAX_HIHO_NENREI, MAX_IZOKU_KO_JUKYU,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_KAFU_JUKYU, MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU,
                      MENJO_DANKAI, MENJO_HOUTEI, MENJO_SHINSEI,
                      MIN_HIHO_NENREI, MIN_IZOKU_KO_JUKYU,
                      MIN_IZOKU_OTTO_JUKYU, MIN_IZOKU_TUMA_JUKYU,
                      MIN_KAFU_JUKYU, MIN_ROREI_JUKYU, MIN_SHOGAI_JUKYU,
                      NENREI_SUM, NOUFU, SAISHUNENDO, SHOGAI_TOKYU,
                      SHONENDO, SUIKEISHONENDO, SUM, UNDER_63, ZENGAKU)
from stdfm import NatError, extendb
from str_op import add, adjustbenefit, multiply, scalar

__all__ = ["shke"]


def shke(G, nendo, shubetu):
    """shke.c:13 の忠実移植。"""
    # 原本の局所配列。集成体初期化で全要素 0
    _R = G.Rorei.dtype
    _RK = G.Rorei_Kyu.dtype
    _G = G.Gonen.dtype
    _S = G.Shogai_Ippan.dtype
    _I = G.Izoku_Tuma.dtype
    _K = G.Kafu.dtype

    _ROREI_N = MAX_ROREI_JUKYU - MIN_ROREI_JUKYU + 1
    _KAS = KURI_AGE_SAGE_SHIKYU_KUBUN
    _SHOGAI_N = MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU + 1

    Rorei_Shikyu = np.zeros((_ROREI_N, _KAS), dtype=_R)
    Rorei_Kyu_Shikyu = np.zeros((_ROREI_N, _KAS), dtype=_RK)
    Turo_Kyu_Shikyu = np.zeros((_ROREI_N, _KAS), dtype=_RK)
    Gonen_Shikyu = np.zeros((_ROREI_N, _KAS), dtype=_G)
    Shogai_Ippan_Shikyu = np.zeros((_SHOGAI_N, SHOGAI_TOKYU), dtype=_S)
    Shogai_20mae_Shikyu = np.zeros((_SHOGAI_N, SHOGAI_TOKYU), dtype=_S)
    Shogai_Kyu_Shikyu = np.zeros((_SHOGAI_N, SHOGAI_TOKYU), dtype=_S)
    Izoku_Tuma_Shikyu = np.zeros(
        MAX_IZOKU_TUMA_JUKYU - MIN_IZOKU_TUMA_JUKYU + 1, dtype=_I)
    Izoku_Otto_Shikyu = np.zeros(
        MAX_IZOKU_OTTO_JUKYU - MIN_IZOKU_OTTO_JUKYU + 1, dtype=_I)
    Izoku_Ko_Shikyu = np.zeros(
        MAX_IZOKU_KO_JUKYU - MIN_IZOKU_KO_JUKYU + 1, dtype=_I)
    Kafu_Shikyu = np.zeros(MAX_KAFU_JUKYU - MIN_KAFU_JUKYU + 1, dtype=_K)
    Kafu_Kyu_Shikyu = np.zeros(MAX_KAFU_JUKYU - MIN_KAFU_JUKYU + 1, dtype=_K)

    seibetu = 0 if shubetu <= 3 else 1

    sotai_nendo = nendo - SHONENDO
    if sotai_nendo < 0:
        raise NatError("年度エラー")

    # ---- 被保険者・納付・付加・免除 --------------------------------
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        i = nenrei - MIN_HIHO_NENREI
        # 45年化のときだけ 60歳以上の「延長ぶん」を足す
        extend = (G.Option == 1 and extendb(G, nendo, nenrei) == 1)

        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            G.Hiho_Kei[shubetu, sotai_nendo, i] \
                += G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]

            G.Hiho_Noufu[shubetu, sotai_nendo, i] \
                += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                    * G.Noufuritu[shubetu, sotai_nendo, i, NOUFU])

            G.Fuka_Hiho[shubetu, sotai_nendo, i] \
                += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                    * G.Noufuritu_Fuka[shubetu, sotai_nendo, i])

            if extend:
                G.Hiho_Kei[shubetu, sotai_nendo, i] \
                    += G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]

                G.Hiho_Noufu[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu[shubetu, sotai_nendo, i, NOUFU])

                G.Fuka_Hiho[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu_Fuka[shubetu, sotai_nendo, i])

            if nenrei == MAX_HIHO_NENREI:
                G.Hiho_Noufu_P[shubetu, sotai_nendo, i] = 0.
                G.Fuka_Hiho_P[shubetu, sotai_nendo, i] = 0.
            elif nendo == SAISHUNENDO:
                # 年度を進めない枝（`sotai_nendo + 1` が配列の外）
                G.Hiho_Noufu_P[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu[shubetu, sotai_nendo, i + 1, NOUFU])

                G.Fuka_Hiho_P[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu_Fuka[shubetu, sotai_nendo, i + 1])

                if extend:
                    G.Hiho_Noufu_P[shubetu, sotai_nendo, i] \
                        += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                            * G.Noufuritu[shubetu, sotai_nendo, i + 1,
                                          NOUFU])

                    G.Fuka_Hiho_P[shubetu, sotai_nendo, i] \
                        += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                            * G.Noufuritu_Fuka[shubetu, sotai_nendo, i + 1])
            else:
                G.Hiho_Noufu_P[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu[shubetu, sotai_nendo + 1, i + 1,
                                      NOUFU])

                G.Fuka_Hiho_P[shubetu, sotai_nendo, i] \
                    += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                        * G.Noufuritu_Fuka[shubetu, sotai_nendo + 1, i + 1])

                if extend:
                    G.Hiho_Noufu_P[shubetu, sotai_nendo, i] \
                        += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                            * G.Noufuritu[shubetu, sotai_nendo + 1, i + 1,
                                          NOUFU])

                    G.Fuka_Hiho_P[shubetu, sotai_nendo, i] \
                        += (G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                            * G.Noufuritu_Fuka[shubetu, sotai_nendo + 1,
                                               i + 1])

            for dankai in range(1, MENJO_DANKAI):
                # 全額免除は「法定」＋「申請」の2つを足す
                if dankai == ZENGAKU:
                    G.Hiho_Menjo[shubetu, sotai_nendo, i, dankai] \
                        += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                            * (G.Noufuritu[shubetu, sotai_nendo, i,
                                           MENJO_HOUTEI]
                               + G.Noufuritu[shubetu, sotai_nendo, i,
                                             MENJO_SHINSEI]))
                else:
                    G.Hiho_Menjo[shubetu, sotai_nendo, i, dankai] \
                        += (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                            * G.Noufuritu[shubetu, sotai_nendo, i, dankai])

                if extend:
                    if dankai == ZENGAKU:
                        G.Hiho_Menjo[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha2[sotai_nendo, i,
                                              kikan]["ninzu"]
                                * (G.Noufuritu[shubetu, sotai_nendo, i,
                                               MENJO_HOUTEI]
                                   + G.Noufuritu[shubetu, sotai_nendo, i,
                                                 MENJO_SHINSEI]))
                    else:
                        G.Hiho_Menjo[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha2[sotai_nendo, i,
                                              kikan]["ninzu"]
                                * G.Noufuritu[shubetu, sotai_nendo, i,
                                              dankai])

                if nenrei == MAX_HIHO_NENREI:
                    G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai] = 0.
                elif nendo == SAISHUNENDO:
                    if dankai == ZENGAKU:
                        G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha[sotai_nendo, i,
                                             kikan]["ninzu"]
                                * (G.Noufuritu[shubetu, sotai_nendo, i + 1,
                                               MENJO_HOUTEI]
                                   + G.Noufuritu[shubetu, sotai_nendo,
                                                 i + 1, MENJO_SHINSEI]))
                    else:
                        # **年齢の添字が ZENGAKU と食い違っている**
                        # （F25。2125年度ぶんは誰も読まない）
                        G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha[sotai_nendo, i + 1,
                                             kikan]["ninzu"]
                                * G.Noufuritu[shubetu, sotai_nendo, i + 1,
                                              dankai])

                    if extend:
                        if dankai == ZENGAKU:
                            G.Hiho_Menjo_P[shubetu, sotai_nendo, i,
                                           dankai] \
                                += (G.Hihokensha2[sotai_nendo, i,
                                                  kikan]["ninzu"]
                                    * (G.Noufuritu[shubetu, sotai_nendo,
                                                   i + 1, MENJO_HOUTEI]
                                       + G.Noufuritu[shubetu, sotai_nendo,
                                                     i + 1,
                                                     MENJO_SHINSEI]))
                        else:
                            G.Hiho_Menjo_P[shubetu, sotai_nendo, i,
                                           dankai] \
                                += (G.Hihokensha2[sotai_nendo, i + 1,
                                                  kikan]["ninzu"]
                                    * G.Noufuritu[shubetu, sotai_nendo,
                                                  i + 1, dankai])
                else:
                    if dankai == ZENGAKU:
                        G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha[sotai_nendo, i,
                                             kikan]["ninzu"]
                                * (G.Noufuritu[shubetu, sotai_nendo + 1,
                                               i + 1, MENJO_HOUTEI]
                                   + G.Noufuritu[shubetu, sotai_nendo + 1,
                                                 i + 1, MENJO_SHINSEI]))
                    else:
                        G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai] \
                            += (G.Hihokensha[sotai_nendo, i,
                                             kikan]["ninzu"]
                                * G.Noufuritu[shubetu, sotai_nendo + 1,
                                              i + 1, dankai])

                    if extend:
                        if dankai == ZENGAKU:
                            G.Hiho_Menjo_P[shubetu, sotai_nendo, i,
                                           dankai] \
                                += (G.Hihokensha2[sotai_nendo, i,
                                                  kikan]["ninzu"]
                                    * (G.Noufuritu[shubetu,
                                                   sotai_nendo + 1, i + 1,
                                                   MENJO_HOUTEI]
                                       + G.Noufuritu[shubetu,
                                                     sotai_nendo + 1,
                                                     i + 1,
                                                     MENJO_SHINSEI]))
                        else:
                            G.Hiho_Menjo_P[shubetu, sotai_nendo, i,
                                           dankai] \
                                += (G.Hihokensha2[sotai_nendo, i,
                                                  kikan]["ninzu"]
                                    * G.Noufuritu[shubetu,
                                                  sotai_nendo + 1, i + 1,
                                                  dankai])

    # ---- 年齢の合計 ------------------------------------------------
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        i = nenrei - MIN_HIHO_NENREI

        G.Hiho_Kei[shubetu, sotai_nendo, HIHO_NENREI_SUM] \
            += G.Hiho_Kei[shubetu, sotai_nendo, i]

        G.Hiho_Noufu[shubetu, sotai_nendo, HIHO_NENREI_SUM] \
            += G.Hiho_Noufu[shubetu, sotai_nendo, i]

        G.Fuka_Hiho[shubetu, sotai_nendo, HIHO_NENREI_SUM] \
            += G.Fuka_Hiho[shubetu, sotai_nendo, i]

        G.Hiho_Noufu_P[shubetu, sotai_nendo, HIHO_NENREI_SUM] \
            += G.Hiho_Noufu_P[shubetu, sotai_nendo, i]

        G.Fuka_Hiho_P[shubetu, sotai_nendo, HIHO_NENREI_SUM] \
            += G.Fuka_Hiho_P[shubetu, sotai_nendo, i]

        for dankai in range(1, MENJO_DANKAI):
            G.Hiho_Menjo[shubetu, sotai_nendo, HIHO_NENREI_SUM, dankai] \
                += G.Hiho_Menjo[shubetu, sotai_nendo, i, dankai]

            G.Hiho_Menjo_P[shubetu, sotai_nendo, HIHO_NENREI_SUM, dankai] \
                += G.Hiho_Menjo_P[shubetu, sotai_nendo, i, dankai]

    # ---- 老齢（新法・旧法・通算・5年） -----------------------------
    for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
        j = jukyu_nenrei - MIN_ROREI_JUKYU
        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            n = nenrei - MIN_ROREI_JUKYU

            Rorei_Shikyu[n, j] = multiply(
                G.Shikyuritu_Rorei[sotai_nendo, n],
                add(G.Rorei_Nendomatu[sotai_nendo, n, j],
                    G.Rorei_Ichibu_Nendomatu[sotai_nendo, n, j]))

            Rorei_Kyu_Shikyu[n, j] = multiply(
                G.Shikyuritu_Rorei_Kyu[sotai_nendo, n],
                G.Rorei_Kyu_Nendomatu[sotai_nendo, n, j])

            Turo_Kyu_Shikyu[n, j] = multiply(
                G.Shikyuritu_Turo_Kyu[sotai_nendo, n],
                G.Turo_Kyu_Nendomatu[sotai_nendo, n, j])

            Gonen_Shikyu[n, j] = scalar(
                G.Shikyuritu_Gonen[sotai_nendo, n],
                G.Gonen_Nendomatu[sotai_nendo, n, j])

            # 繰下げ（66〜70歳）を 2021年度の翌年に選んだ世代だけ、
            # 割引率で人数と年金額を調整する
            if (66 <= jukyu_nenrei <= 70
                    and nendo - nenrei == SUIKEISHONENDO + 1 - jukyu_nenrei):
                if SUIKEISHONENDO + 1 <= nendo <= SUIKEISHONENDO + 10:
                    k = nendo - SUIKEISHONENDO - 1
                    Rorei_Shikyu[n, j]["ninzu"] \
                        *= G.Waribikiritu[seibetu, 0, jukyu_nenrei - 66, k]

                    Rorei_Shikyu[n, j] = adjustbenefit(
                        G.Waribikiritu[seibetu, 1, jukyu_nenrei - 66, k],
                        Rorei_Shikyu[n, j])
                elif nendo > SUIKEISHONENDO + 10:
                    # **人数だけ添字が 1（2023年度）**（J3）
                    Rorei_Shikyu[n, j]["ninzu"] \
                        *= G.Waribikiritu[seibetu, 0, jukyu_nenrei - 66, 1]

                    Rorei_Shikyu[n, j] = adjustbenefit(
                        G.Waribikiritu[seibetu, 1, jukyu_nenrei - 66, 9],
                        Rorei_Shikyu[n, j])

            m = (UNDER_63 - NENREI_SUM) if nenrei <= 63 \
                else (nenrei - NENREI_SUM)

            G.Rorei[shubetu, sotai_nendo, m, j] = add(
                G.Rorei[shubetu, sotai_nendo, m, j], Rorei_Shikyu[n, j])

            G.Rorei_Kyu[shubetu, sotai_nendo, m, j] = add(
                G.Rorei_Kyu[shubetu, sotai_nendo, m, j],
                Rorei_Kyu_Shikyu[n, j])

            G.Turo_Kyu[shubetu, sotai_nendo, m, j] = add(
                G.Turo_Kyu[shubetu, sotai_nendo, m, j],
                Turo_Kyu_Shikyu[n, j])

            G.Gonen[shubetu, sotai_nendo, m, j] = add(
                G.Gonen[shubetu, sotai_nendo, m, j], Gonen_Shikyu[n, j])

    # 老齢の免除の「計」（段階と国庫引上げの2方向＋両方）
    for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
        j = jukyu_nenrei - MIN_ROREI_JUKYU
        for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
            m = nenrei - NENREI_SUM
            menjo = G.Rorei[shubetu, sotai_nendo, m, j]["menjo"]
            for dankai in range(1, MENJO_DANKAI):
                for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                    menjo[SUM, kokko] += menjo[dankai, kokko]
                    menjo[dankai, SUM] += menjo[dankai, kokko]
                    menjo[SUM, SUM] += menjo[dankai, kokko]

    # ---- 障害（一般・20歳前・旧法） --------------------------------
    for tokyu in range(1, 2 + 1):
        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            n = nenrei - MIN_SHOGAI_JUKYU

            Shogai_Ippan_Shikyu[n, tokyu] = scalar(
                G.Shikyuritu_Shogai_Ippan[sotai_nendo, n, tokyu],
                G.Shogai_Ippan_Nendomatu[sotai_nendo, n, tokyu])

            Shogai_20mae_Shikyu[n, tokyu] = scalar(
                G.Shikyuritu_Shogai_20mae[sotai_nendo, n, tokyu],
                G.Shogai_20mae_Nendomatu[sotai_nendo, n, tokyu])

            Shogai_Kyu_Shikyu[n, tokyu] = scalar(
                G.Shikyuritu_Shogai_Kyu[sotai_nendo, n, tokyu],
                G.Shogai_Kyu_Nendomatu[sotai_nendo, n, tokyu])

            m = (UNDER_63 - NENREI_SUM) if nenrei <= 63 \
                else (nenrei - NENREI_SUM)

            G.Shogai_Ippan[shubetu, sotai_nendo, m] = add(
                G.Shogai_Ippan[shubetu, sotai_nendo, m],
                Shogai_Ippan_Shikyu[n, tokyu])

            G.Shogai_20mae[shubetu, sotai_nendo, m] = add(
                G.Shogai_20mae[shubetu, sotai_nendo, m],
                Shogai_20mae_Shikyu[n, tokyu])

            G.Shogai_Kyu[shubetu, sotai_nendo, m] = add(
                G.Shogai_Kyu[shubetu, sotai_nendo, m],
                Shogai_Kyu_Shikyu[n, tokyu])

    # ---- 遺族（妻） ------------------------------------------------
    for nenrei in range(MIN_IZOKU_TUMA_JUKYU, MAX_IZOKU_TUMA_JUKYU + 1):
        n = nenrei - MIN_IZOKU_TUMA_JUKYU
        Izoku_Tuma_Shikyu[n] = scalar(
            G.Shikyuritu_Tuma[sotai_nendo],
            G.Izoku_Tuma_Nendomatu[sotai_nendo, n])

        m = (UNDER_63 - NENREI_SUM) if nenrei <= 63 \
            else (nenrei - NENREI_SUM)
        G.Izoku_Tuma[shubetu, sotai_nendo, m] = add(
            G.Izoku_Tuma[shubetu, sotai_nendo, m], Izoku_Tuma_Shikyu[n])

    # ---- 遺族（夫） ------------------------------------------------
    for nenrei in range(MIN_IZOKU_OTTO_JUKYU, MAX_IZOKU_OTTO_JUKYU + 1):
        n = nenrei - MIN_IZOKU_OTTO_JUKYU
        Izoku_Otto_Shikyu[n] = scalar(
            G.Shikyuritu_Otto[sotai_nendo],
            G.Izoku_Otto_Nendomatu[sotai_nendo, n])

        m = (UNDER_63 - NENREI_SUM) if nenrei <= 63 \
            else (nenrei - NENREI_SUM)
        G.Izoku_Otto[shubetu, sotai_nendo, m] = add(
            G.Izoku_Otto[shubetu, sotai_nendo, m], Izoku_Otto_Shikyu[n])

    # ---- 遺族（子。年齢で分けない） --------------------------------
    for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
        n = nenrei - MIN_IZOKU_KO_JUKYU
        # 原本は `Shikyuritu_Ko[nendo - SHONENDO]`（= sotai_nendo）
        Izoku_Ko_Shikyu[n] = scalar(
            G.Shikyuritu_Ko[nendo - SHONENDO],
            G.Izoku_Ko_Nendomatu[sotai_nendo, n])

        G.Izoku_Ko[shubetu, sotai_nendo] = add(
            G.Izoku_Ko[shubetu, sotai_nendo], Izoku_Ko_Shikyu[n])

    # ---- 寡婦（新法・旧法。60〜64歳だけ） --------------------------
    for nenrei in range(60, MAX_KAFU_JUKYU + 1):
        n = nenrei - MIN_KAFU_JUKYU

        Kafu_Shikyu[n] = scalar(
            G.Shikyuritu_Kafu[nendo - SHONENDO, nenrei - 60],
            G.Kafu_Nendomatu[sotai_nendo, n])

        Kafu_Kyu_Shikyu[n] = scalar(
            G.Shikyuritu_Kafu[nendo - SHONENDO, nenrei - 60],
            G.Kafu_Kyu_Nendomatu[sotai_nendo, n])

        G.Kafu[shubetu, sotai_nendo] = add(
            G.Kafu[shubetu, sotai_nendo], Kafu_Shikyu[n])

        G.Kafu_Kyu[shubetu, sotai_nendo] = add(
            G.Kafu_Kyu[shubetu, sotai_nendo], Kafu_Kyu_Shikyu[n])

    # 寡婦の免除の「計」（原本は足す順が老齢と違うが結果は同じ）
    kafu_menjo = G.Kafu[shubetu, sotai_nendo]["menjo"]
    kafu_kyu_menjo = G.Kafu_Kyu[shubetu, sotai_nendo]["menjo"]
    for dankai in range(1, MENJO_DANKAI):
        for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
            kafu_menjo[SUM, kokko] += kafu_menjo[dankai, kokko]
            kafu_kyu_menjo[SUM, kokko] += kafu_kyu_menjo[dankai, kokko]
            kafu_menjo[dankai, SUM] += kafu_menjo[dankai, kokko]
            kafu_kyu_menjo[dankai, SUM] += kafu_kyu_menjo[dankai, kokko]
            kafu_menjo[SUM, SUM] += kafu_menjo[dankai, kokko]
            kafu_kyu_menjo[SUM, SUM] += kafu_kyu_menjo[dankai, kokko]

    # ---- 死亡一時金（支給率を掛けない。`dtst`/`siml` が入れた値） ---
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        i = nenrei - MIN_HIHO_NENREI
        m = (UNDER_63 - NENREI_SUM) if nenrei <= 63 \
            else (nenrei - NENREI_SUM)
        G.Ichijikin[shubetu, sotai_nendo, m] = add(
            G.Ichijikin[shubetu, sotai_nendo, m],
            G.Ichijikin_Nendomatu[sotai_nendo, i])

    return
