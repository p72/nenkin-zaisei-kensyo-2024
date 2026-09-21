# -*- coding: utf-8 -*-
"""
国民年金/kiso.c の忠実移植（基礎率を13本のファイルから読む）
=============================================================
1,663 行。`main.c` が種別（2 第1号男 / 3 第3号男 / 5 第1号女 /
6 第3号女）ごとに `dtst()` の直後に1回呼ぶ。`dtst()` が**足元の
人数**（基礎数）を読むのに対して、`kiso()` は**将来に向けた率**
（基礎率）を読む。

    Dattairyoku_Gokei / _Shibou           脱退力（総合・死亡）
    Hassei_Wariai_Rorei                   老齢基礎の受給発生割合
    Hasseiryoku_Shogai / Hassei_Wariai_…  障害の発生力・20歳前発生割合
    Hassei_Wariai_Tuma / _Otto / _Ko      遺族の発生割合
    Hassei_Wariai_Kafu / _Shibou          寡婦・死亡一時金の発生割合
    Tokyu_Wariai_Ippan / _20mae           障害の等級割合
    Kakyu_Wariai_*                        加算割合（12歳未満・3歳以降）
    Sokan_Tuma / _Otto / _Ko / _Kafu      遺族の相関（年齢差）
    Shikkenritu_*                         失権率
    Shikyuritu_*                          支給率（`struct` 3種を含む）
    Kakudai_Ichibu                        一部繰上げの適用拡大
    Waribikiritu / Kyufu_ritu{,1,2}       繰上げ・繰下げの割引率と給付率

`fp[…]` の中身（`fp` は14要素の局所配列。`mfile_open.h` の
`KISO_1M` = 49 / `KISO_3M` = 62 / `KISO_1F` = 65 / `KISO_3F` = 78）

    0     脱退力（総合・死亡）
    1     老齢基礎の受給発生割合          種別 3・6 は 301 / 発生割合(夫)
    2     障害の発生力・20歳前発生割合    種別 3・6 は 301 / 適用拡大
    3     遺族の発生割合（妻・子・寡婦 or 夫）
    4     死亡一時金の発生割合
    5     障害の等級割合
    6     加算割合
    7     遺族の相関
    8     老齢の失権率
    9     障害の失権率
    10    遺族・寡婦の失権率
    11    支給率（301〜309 をまとめて1本）
    12    一部繰上げの適用拡大

種別で読む本数が違う（13 / 3 / 13 / 4）
---------------------------------------
```c
case 2 : for( counter = 0 ; counter < 13 ; counter++ ) fp[counter] = fp_in[KISO_1M + counter]; break;
case 3 : for( counter = 0 ; counter <  3 ; counter++ ) fp[counter] = fp_in[KISO_3M + counter]; break;
case 5 : for( counter = 0 ; counter < 13 ; counter++ ) fp[counter] = fp_in[KISO_1F + counter]; break;
case 6 : for( counter = 0 ; counter <  4 ; counter++ ) fp[counter] = fp_in[KISO_3F + counter]; break;
```

種別 3・6 は `if( shubetu == 2 || shubetu == 5 )` の外側だけを通り、
支給率と適用拡大を **`fp[shubetu / 3]` と `fp[( shubetu / 3 ) + 1]`**
から読む。

| 種別 | `shubetu / 3` | 301 を読む | 適用拡大を読む |
|---|---:|---|---|
| 3 | 1 | `fp[1]`（= 63） | `fp[2]`（= 64） |
| 6 | 2 | `fp[2]`（= 80） | `fp[3]`（= 81） |

種別 6 は `fp[1]`（= 79）を「発生割合（夫）」として読むので4本とも
使うが、**種別 3 は3本で足りる**（遺族の発生割合を読まない）。

種別 3 が種別 2 の遺族発生割合をそのまま引き継ぐ
-------------------------------------------------
`Hassei_Wariai_Shibou` には種別 3・6 用に **0 で埋める `else`** が
書かれているのに、`Hassei_Wariai_Tuma` `_Ko` `_Kafu` `_Otto` には
それが無い。

- 種別 2 のブロックが `_Tuma` `_Ko` `_Kafu` を読み、`_Otto` を 0 に
- 種別 5・6 のブロックが `_Otto` を読み、`_Tuma` `_Ko` `_Kafu` を 0 に
- **種別 3 はどちらも通らない**

`main.c` は 2 → 3 → 5 → 6 の順に回すので、種別 3 の `siml()` は
**種別 2 が読んだ妻・子・寡婦の発生割合をそのまま使う**。
第3号被保険者にも遺族基礎の発生はあるので 0 が正しいとは
言い切れないが、「第1号男の率を第3号男に流用する」のが意図で
あれば `_Otto` を 0 にする行と揃っていないのが不自然。
`検証/原本の不具合.md` の **F24** に記録した。

失権率は生命表で将来に伸ばす
----------------------------
老齢・障害の失権率は「足元の失権率 × 各年度の死亡率 ÷ 足元3年平均の
死亡率」で将来に伸ばす。

```c
Shikkenritu_Rorei[nendo][nenrei]
 = shikkenritu[nenrei][0] * q[nendo][nenrei][sex]
    / ( ( q[LIFETABLE_NENDO - 1][nenrei][sex]
          + q[LIFETABLE_NENDO    ][nenrei][sex]
          + q[LIFETABLE_NENDO + 1][nenrei][sex] ) / 3. );
```

脱退力だけは3年平均ではなく `LIFETABLE_NENDO + 1` の1年だけで割る。
**割り方が2通りある**ので、括り方をそのまま写している。

105歳以上は 104歳の比で伸ばし、最終年齢（115歳）は 1 で固定する。
伸ばしたあとに `> 1.` を 1 に丸める後始末が入る（脱退力には無い）。

夫の失権率は19年かけて妻の率に寄せる
------------------------------------
```c
Shikkenritu_Otto[sotai_nendo][nenrei]
 = ( ( 2014 + 19 - SHONENDO - sotai_nendo ) * shikkenritu[nenrei][3]
     + sotai_nendo * Shikkenritu_Tuma[0][nenrei - 2 - MIN_IZOKU_TUMA_JUKYU] )
   / (double)( 2014 + 19 - SHONENDO );
```

`2014 + 19 - SHONENDO` = 13。`sotai_nendo` 1〜13 で夫の実績から
**2歳若い妻の失権率**へ線形に移る。`Shikkenritu_Tuma` は種別 2 の
ときに読んだ値がそのまま残っているものを使う（種別 5 の処理中に
参照するので、これも種別をまたいだ持ち越し。ただしこちらは
**夫の失権率を妻の率に寄せる**という趣旨がはっきりしているので
不具合ではない）。

`sotai_nendo` = 0 には何も入らない（`for` が 1 から始まる）。

障害の支給率は生年で経過措置に振り替える
----------------------------------------
`Shikyuritu_Shogai_Ippan` は `_keinen`（経過年金）と2本読んで、
生年（`nendo - nenrei`）と年齢の組み合わせで `_keinen` に
差し替える。差し替えの境目が**種別 2 と 5 で5年ずれる**
（男 1953年生から / 女 1958年生から）。支給開始年齢の
引き上げが女子で5年遅れたのに合わせたもの。

支給率だけ添字の基準年度が違う
------------------------------
`Shikyuritu_Rorei` `_Rorei_Kyu` `_Turo_Kyu` `_Gonen` は
`SUIKEISHONENDO`（2021年度）に読み込んでから将来に伸ばすのに、
`Shikyuritu_Shogai_*` `_Tuma` `_Otto` `_Ko` `_Kafu` は
`SHONENDO`（2020年度）に読み込む。**同じファイルの続きを読んで
いるのに入れる年度が1年違う**。

`Kyufu_ritu` の配列は1つ大きい
------------------------------
```c
EXTERN double Kyufu_ritu[KURI_AGE_SAGE_SHIKYU_KUBUN]
                        [( SAISHUNENDO - MIN_ROREI_JUKYU ) - ( SHONENDO - 70 ) + 1][2];
```

宣言は `SHONENDO - 70` = 1950年生を基準にしているが、書き込みも
`siml.c` の読み出しも `SUIKEISHONENDO - 70` = 1951年生が基準。
1年ぶん（8バイト × 11 × 2）余るだけで、**食い違いは無い**。

割引率・給付率のファイルは種別ごとに見出しを1行食う
---------------------------------------------------
```c
read_data( buffer , fp_in[WARIBIKI] , &data_number );
if( shubetu == 2 ) { … 本体を読む … }
```

見出しの読み飛ばしが `if( shubetu == 2 )` の**外**にあるので、
種別 3・5・6 でも1行ずつ進む。種別 2 が先に本体を読み切って
いるので、あとの3回は EOF か余った行を読んで捨てるだけ。
`Waribikiritu` `Kyufu_ritu*` は種別 2 のときにしか書かれない。
"""
import numpy as np

from setconst import (BUFFER_MAX, I_KEINEN_SHONENDO, KOKKO_HIKIAGE,
                      KURI_AGE_SAGE_SHIKYU_KUBUN, LIFETABLE_NENDO,
                      MAX_HIHO_NENREI, MAX_IZOKU_KO_JUKYU,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_KAFU_JUKYU, MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU,
                      MENJO_1_2, MENJO_1_4, MENJO_3_4, MENJO_DANKAI,
                      MIN_HIHO_NENREI, MIN_IZOKU_KO_JUKYU,
                      MIN_IZOKU_OTTO_JUKYU, MIN_IZOKU_TUMA_JUKYU,
                      MIN_KAFU_JUKYU, MIN_ROREI_JUKYU, MIN_SHOGAI_JUKYU,
                      N_O_NENDO, SAISHUNENDO, SHIKKENRITU_MAX,
                      SHIKKENRITU_MIN, SHONENDO, SUIKEISAISHUNENDO,
                      SUIKEISHONENDO, TANSHUKU_NENDO, ZENGAKU)
from stdfm import EOF, Buffer, NatError, extendb, extendc, read_data

__all__ = ["kiso"]

# `mfile_open.h` の入力番号
_KISO_1M = 49
_KISO_3M = 62
_KISO_1F = 65
_KISO_3F = 78
_WARIBIKI = 82
_KYUFU = 83
_KYUFU2 = 84

# `snaps.h` の `#define HenkouSeinendo 1941`
_HENKOU_SEINENDO = 1941


def readkiso_error(shurui):
    """kiso.c:1659 の忠実移植。"""
    raise NatError(
        "基礎率ファイル読み込み中にＥＯＦを検出しました。 基礎率種類は、%d"
        % shurui)


def _expect(buf, fp, *want):
    """`read_data( … ) != EOF && buffer[0] == a && buffer[1] == b` の形。

    原本は `&&` の短絡でしか書けないので、判定をここにまとめた。
    `want` が1個なら `buffer[0]` だけを見る。
    """
    if read_data(buf, fp) == EOF:
        return False
    for i, v in enumerate(want):
        if buf.num[i] != v:
            return False
    return True


def kiso(G, shubetu):
    """kiso.c:17 の忠実移植。"""
    buf = Buffer(BUFFER_MAX)    # 原本は `double buffer[BUFFER_MAX]`

    # 原本は `double shikkenritu[MAX_ROREI_JUKYU - 0 + 1][4]`
    shikkenritu = np.zeros((MAX_ROREI_JUKYU + 1, 4))
    # 原本は `double kyufu_temp[KURI_AGE_SAGE_SHIKYU_KUBUN][2]`
    kyufu_temp = np.zeros((KURI_AGE_SAGE_SHIKYU_KUBUN, 2))

    # 原本は `FILE *fp[14]`。種別 3 は3本、種別 6 は4本しか入れない
    fp = [None] * 14
    if shubetu == 2:
        for counter in range(0, 13):
            fp[counter] = G.fp_in[_KISO_1M + counter]
    elif shubetu == 3:
        for counter in range(0, 3):
            fp[counter] = G.fp_in[_KISO_3M + counter]
    elif shubetu == 5:
        for counter in range(0, 13):
            fp[counter] = G.fp_in[_KISO_1F + counter]
    elif shubetu == 6:
        for counter in range(0, 4):
            fp[counter] = G.fp_in[_KISO_3F + counter]
    else:
        raise NatError("指定外のshubetu %d を読み込みました" % shubetu)

    for sotai_nendo in range(0, SAISHUNENDO - SHONENDO + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            G.Saikanyuritu[sotai_nendo, nenrei - MIN_HIHO_NENREI] = 0.

    # ---- 脱退力（総合・死亡） --------------------------------------
    read_data(buf, fp[0])                       # 見出しを1行

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        if _expect(buf, fp[0], 1, nenrei):
            G.Dattairyoku_Gokei[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
        else:
            readkiso_error(1)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        if _expect(buf, fp[0], 2, nenrei):
            G.Dattairyoku_Shibou[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
        else:
            readkiso_error(2)

    # 死亡脱退力は生命表で伸ばす。**割るのは1年だけ**（失権率は3年平均）
    sex = 0 if shubetu <= 3 else 1
    for nendo in range(SHONENDO + 1, SHIKKENRITU_MAX + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            G.Dattairyoku_Shibou[nendo - SHONENDO, nenrei - MIN_HIHO_NENREI] \
                = (G.Dattairyoku_Shibou[0, nenrei - MIN_HIHO_NENREI]
                   * G.q[nendo - SHIKKENRITU_MIN, nenrei - 0, sex]
                   / G.q[LIFETABLE_NENDO + 1 - SHIKKENRITU_MIN,
                         nenrei - 0, sex])

            G.Dattairyoku_Gokei[nendo - SHONENDO, nenrei - MIN_HIHO_NENREI] \
                = (G.Dattairyoku_Gokei[0, nenrei - MIN_HIHO_NENREI]
                   - G.Dattairyoku_Shibou[0, nenrei - MIN_HIHO_NENREI]
                   + G.Dattairyoku_Shibou[nendo - SHONENDO,
                                          nenrei - MIN_HIHO_NENREI])

            # 65歳（第3号は60歳）以上は必ず脱退する
            if nenrei >= 65 or ((shubetu == 3 or shubetu == 6)
                                and nenrei >= 60):
                G.Dattairyoku_Gokei[nendo - SHONENDO,
                                    nenrei - MIN_HIHO_NENREI] = 1.

    for nendo in range(SHIKKENRITU_MAX + 1, SAISHUNENDO + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            G.Dattairyoku_Shibou[nendo - SHONENDO, nenrei - MIN_HIHO_NENREI] \
                = G.Dattairyoku_Shibou[SHIKKENRITU_MAX - SHONENDO,
                                       nenrei - MIN_HIHO_NENREI]

            G.Dattairyoku_Gokei[nendo - SHONENDO, nenrei - MIN_HIHO_NENREI] \
                = G.Dattairyoku_Gokei[SHIKKENRITU_MAX - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI]

    if G.Option == 1:
        # 基礎45年化のとき、60歳以上の脱退力を59歳・60歳の値で置く
        for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
            for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1, -1):
                if extendb(G, nendo, nenrei) == 1:
                    G.Dattairyoku_Gokei[nendo - SHONENDO,
                                        nenrei - MIN_HIHO_NENREI] \
                        = G.Dattairyoku_Gokei[nendo - SHONENDO,
                                              59 - MIN_HIHO_NENREI]

                if extendc(G, nendo, nenrei) == 1:
                    G.Dattairyoku_Gokei[nendo - SHONENDO,
                                        nenrei - MIN_HIHO_NENREI] \
                        = G.Dattairyoku_Gokei[nendo - SHONENDO,
                                              60 - MIN_HIHO_NENREI]

    # ---- 老齢基礎の受給発生割合 ------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[1])
        for nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            if _expect(buf, fp[1], 4, nenrei):
                G.Hassei_Wariai_Rorei[0, nenrei - MIN_ROREI_JUKYU] \
                    = buf.num[2]
            else:
                readkiso_error(4)

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
                G.Hassei_Wariai_Rorei[sotai_nendo,
                                      nenrei - MIN_ROREI_JUKYU] \
                    = G.Hassei_Wariai_Rorei[0, nenrei - MIN_ROREI_JUKYU]

    # ---- 障害の発生力・20歳前発生割合 ------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[2])
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[2], 5, nenrei):
                G.Hasseiryoku_Shogai[0, nenrei - MIN_HIHO_NENREI] \
                    = buf.num[2]
            else:
                readkiso_error(5)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[2], 6, nenrei):
                G.Hassei_Wariai_20mae[0, nenrei - MIN_HIHO_NENREI] \
                    = buf.num[2]
            else:
                readkiso_error(6)

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hasseiryoku_Shogai[sotai_nendo, nenrei - MIN_HIHO_NENREI] \
                    = G.Hasseiryoku_Shogai[0, nenrei - MIN_HIHO_NENREI]

                G.Hassei_Wariai_20mae[sotai_nendo,
                                      nenrei - MIN_HIHO_NENREI] \
                    = G.Hassei_Wariai_20mae[0, nenrei - MIN_HIHO_NENREI]

    # ---- 遺族の発生割合（妻・子・寡婦） ----------------------------
    if shubetu == 2:
        read_data(buf, fp[3])
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[3], 7, nenrei):
                G.Hassei_Wariai_Tuma[SUIKEISHONENDO - SHONENDO,
                                     nenrei - MIN_HIHO_NENREI] = buf.num[2]
            else:
                readkiso_error(7)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[3], 8, nenrei):
                G.Hassei_Wariai_Ko[SUIKEISHONENDO - SHONENDO,
                                   nenrei - MIN_HIHO_NENREI] = buf.num[2]
            else:
                readkiso_error(8)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[3], 9, nenrei):
                G.Hassei_Wariai_Kafu[SUIKEISHONENDO - SHONENDO,
                                     nenrei - MIN_HIHO_NENREI] = buf.num[2]
            else:
                readkiso_error(9)

        # 遺族基礎の経過（`kaizen()` が作る `Izoku_Keinen`）で伸ばす。
        # **年度を降る**（`nendo--`）が、基準の 2021年度は上書きされても
        # 同じ値になる（比が 1 になる）ので結果は変わらない
        for nendo in range(SAISHUNENDO, SUIKEISHONENDO - 1, -1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Tuma[nendo - SHONENDO,
                                     nenrei - MIN_HIHO_NENREI] \
                    = (G.Hassei_Wariai_Tuma[SUIKEISHONENDO - SHONENDO,
                                            nenrei - MIN_HIHO_NENREI]
                       * G.Izoku_Keinen[nendo - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0]
                       / G.Izoku_Keinen[I_KEINEN_SHONENDO + 1
                                        - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0])

                G.Hassei_Wariai_Ko[nendo - SHONENDO,
                                   nenrei - MIN_HIHO_NENREI] \
                    = (G.Hassei_Wariai_Ko[SUIKEISHONENDO - SHONENDO,
                                          nenrei - MIN_HIHO_NENREI]
                       * G.Izoku_Keinen[nendo - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0]
                       / G.Izoku_Keinen[I_KEINEN_SHONENDO + 1
                                        - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0])

                G.Hassei_Wariai_Kafu[nendo - SHONENDO,
                                     nenrei - MIN_HIHO_NENREI] \
                    = (G.Hassei_Wariai_Kafu[SUIKEISHONENDO - SHONENDO,
                                            nenrei - MIN_HIHO_NENREI]
                       * G.Izoku_Keinen[nendo - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0]
                       / G.Izoku_Keinen[I_KEINEN_SHONENDO + 1
                                        - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 0])

                # 寡婦年金の受給資格期間が25年から10年に短縮される前は
                # 44歳以下の寡婦は出ない
                if nendo <= TANSHUKU_NENDO - 1 and nenrei <= 44:
                    G.Hassei_Wariai_Kafu[nendo - SHONENDO,
                                         nenrei - MIN_HIHO_NENREI] = 0.

        for sotai_nendo in range(0, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Otto[sotai_nendo,
                                     nenrei - MIN_HIHO_NENREI] = 0.

    # ---- 遺族の発生割合（夫） --------------------------------------
    if shubetu == 5 or shubetu == 6:
        if shubetu == 5:
            read_data(buf, fp[3])
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[3], 7, nenrei):
                    G.Hassei_Wariai_Otto[SUIKEISHONENDO - SHONENDO,
                                         nenrei - MIN_HIHO_NENREI] \
                        = buf.num[2]
                else:
                    readkiso_error(7)
        else:
            read_data(buf, fp[1])
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[1], 7, nenrei):
                    G.Hassei_Wariai_Otto[SUIKEISHONENDO - SHONENDO,
                                         nenrei - MIN_HIHO_NENREI] \
                        = buf.num[2]
                else:
                    readkiso_error(7)

        for nendo in range(SAISHUNENDO, SUIKEISHONENDO - 1, -1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Otto[nendo - SHONENDO,
                                     nenrei - MIN_HIHO_NENREI] \
                    = (G.Hassei_Wariai_Otto[SUIKEISHONENDO - SHONENDO,
                                            nenrei - MIN_HIHO_NENREI]
                       * G.Izoku_Keinen[nendo - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 1]
                       / G.Izoku_Keinen[I_KEINEN_SHONENDO + 1
                                        - I_KEINEN_SHONENDO,
                                        nenrei - MIN_HIHO_NENREI, 1])

        for sotai_nendo in range(0, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Tuma[sotai_nendo,
                                     nenrei - MIN_HIHO_NENREI] = 0.
                G.Hassei_Wariai_Ko[sotai_nendo,
                                   nenrei - MIN_HIHO_NENREI] = 0.
                G.Hassei_Wariai_Kafu[sotai_nendo,
                                     nenrei - MIN_HIHO_NENREI] = 0.

    # ---- 死亡一時金の発生割合 --------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[4])
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if _expect(buf, fp[4], 10, nenrei):
                G.Hassei_Wariai_Shibou[0, nenrei - MIN_HIHO_NENREI] \
                    = buf.num[2]
            else:
                readkiso_error(10)

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Shibou[sotai_nendo,
                                       nenrei - MIN_HIHO_NENREI] \
                    = G.Hassei_Wariai_Shibou[0, nenrei - MIN_HIHO_NENREI]
    else:
        # **死亡一時金だけ 0 で埋める `else` がある**（遺族には無い）
        for sotai_nendo in range(0, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Hassei_Wariai_Shibou[sotai_nendo,
                                       nenrei - MIN_HIHO_NENREI] = 0.

    # ---- 障害の等級割合 --------------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[5])
        if _expect(buf, fp[5], 11):
            G.Tokyu_Wariai_Ippan[0, 1] = buf.num[1]
            G.Tokyu_Wariai_Ippan[0, 2] = 1. - buf.num[1]
        else:
            readkiso_error(11)

        if _expect(buf, fp[5], 12):
            G.Tokyu_Wariai_20mae[0, 1] = buf.num[1]
            G.Tokyu_Wariai_20mae[0, 2] = 1. - buf.num[1]
        else:
            readkiso_error(12)

        G.Tokyu_Wariai_Ippan[0, 0] = 0.
        G.Tokyu_Wariai_20mae[0, 0] = 0.

        for counter in range(0, 3):
            for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
                G.Tokyu_Wariai_Ippan[sotai_nendo, counter] \
                    = G.Tokyu_Wariai_Ippan[0, counter]
                G.Tokyu_Wariai_20mae[sotai_nendo, counter] \
                    = G.Tokyu_Wariai_20mae[0, counter]

    # ---- 加算割合 --------------------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[6])

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[6], 13, nenrei):
                G.Kakyu_Wariai_Ippan_12shi[0, nenrei - MIN_SHOGAI_JUKYU] \
                    = buf.num[2]
            else:
                readkiso_error(13)

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[6], 14, nenrei):
                G.Kakyu_Wariai_Ippan_3shiiko[0, nenrei - MIN_SHOGAI_JUKYU] \
                    = buf.num[2]
            else:
                readkiso_error(14)

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[6], 15, nenrei):
                G.Kakyu_Wariai_20mae_12shi[0, nenrei - MIN_SHOGAI_JUKYU] \
                    = buf.num[2]
            else:
                readkiso_error(15)

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[6], 16, nenrei):
                G.Kakyu_Wariai_20mae_3shiiko[0, nenrei - MIN_SHOGAI_JUKYU] \
                    = buf.num[2]
            else:
                readkiso_error(16)

        if shubetu == 2:
            for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                                MAX_IZOKU_TUMA_JUKYU + 1):
                if _expect(buf, fp[6], 17, nenrei):
                    G.Kakyu_Wariai_Tuma_12shi[
                        0, nenrei - MIN_IZOKU_TUMA_JUKYU] = buf.num[2]
                else:
                    readkiso_error(17)

            for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                                MAX_IZOKU_TUMA_JUKYU + 1):
                if _expect(buf, fp[6], 18, nenrei):
                    G.Kakyu_Wariai_Tuma_3shiiko[
                        0, nenrei - MIN_IZOKU_TUMA_JUKYU] = buf.num[2]
                else:
                    readkiso_error(18)

            for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
                if _expect(buf, fp[6], 19, nenrei):
                    G.Kakyu_Wariai_Ko_12shi[
                        0, nenrei - MIN_IZOKU_KO_JUKYU] = buf.num[2]
                else:
                    readkiso_error(19)

            for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
                if _expect(buf, fp[6], 20, nenrei):
                    G.Kakyu_Wariai_Ko_3shiiko[
                        0, nenrei - MIN_IZOKU_KO_JUKYU] = buf.num[2]
                else:
                    readkiso_error(20)

        if shubetu == 5:
            for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                MAX_IZOKU_OTTO_JUKYU + 1):
                if _expect(buf, fp[6], 17, nenrei):
                    G.Kakyu_Wariai_Otto_12shi[
                        0, nenrei - MIN_IZOKU_OTTO_JUKYU] = buf.num[2]
                else:
                    readkiso_error(17)
            for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                MAX_IZOKU_OTTO_JUKYU + 1):
                if _expect(buf, fp[6], 18, nenrei):
                    G.Kakyu_Wariai_Otto_3shiiko[
                        0, nenrei - MIN_IZOKU_OTTO_JUKYU] = buf.num[2]
                else:
                    readkiso_error(18)

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
                G.Kakyu_Wariai_Ippan_12shi[sotai_nendo,
                                           nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Kakyu_Wariai_Ippan_12shi[0,
                                                 nenrei - MIN_SHOGAI_JUKYU]

                G.Kakyu_Wariai_Ippan_3shiiko[sotai_nendo,
                                             nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Kakyu_Wariai_Ippan_3shiiko[0,
                                                   nenrei - MIN_SHOGAI_JUKYU]

                G.Kakyu_Wariai_20mae_12shi[sotai_nendo,
                                           nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Kakyu_Wariai_20mae_12shi[0,
                                                 nenrei - MIN_SHOGAI_JUKYU]

                G.Kakyu_Wariai_20mae_3shiiko[sotai_nendo,
                                             nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Kakyu_Wariai_20mae_3shiiko[0,
                                                   nenrei - MIN_SHOGAI_JUKYU]

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                                MAX_IZOKU_TUMA_JUKYU + 1):
                G.Kakyu_Wariai_Tuma_12shi[sotai_nendo,
                                          nenrei - MIN_IZOKU_TUMA_JUKYU] \
                    = G.Kakyu_Wariai_Tuma_12shi[
                        0, nenrei - MIN_IZOKU_TUMA_JUKYU]

                G.Kakyu_Wariai_Tuma_3shiiko[sotai_nendo,
                                            nenrei - MIN_IZOKU_TUMA_JUKYU] \
                    = G.Kakyu_Wariai_Tuma_3shiiko[
                        0, nenrei - MIN_IZOKU_TUMA_JUKYU]

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                MAX_IZOKU_OTTO_JUKYU + 1):
                G.Kakyu_Wariai_Otto_12shi[sotai_nendo,
                                          nenrei - MIN_IZOKU_OTTO_JUKYU] \
                    = G.Kakyu_Wariai_Otto_12shi[
                        0, nenrei - MIN_IZOKU_OTTO_JUKYU]

                G.Kakyu_Wariai_Otto_3shiiko[sotai_nendo,
                                            nenrei - MIN_IZOKU_OTTO_JUKYU] \
                    = G.Kakyu_Wariai_Otto_3shiiko[
                        0, nenrei - MIN_IZOKU_OTTO_JUKYU]

        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
                G.Kakyu_Wariai_Ko_12shi[sotai_nendo,
                                        nenrei - MIN_IZOKU_KO_JUKYU] \
                    = G.Kakyu_Wariai_Ko_12shi[0,
                                              nenrei - MIN_IZOKU_KO_JUKYU]

                G.Kakyu_Wariai_Ko_3shiiko[sotai_nendo,
                                          nenrei - MIN_IZOKU_KO_JUKYU] \
                    = G.Kakyu_Wariai_Ko_3shiiko[0,
                                                nenrei - MIN_IZOKU_KO_JUKYU]

    # ---- 遺族の相関（年齢差） --------------------------------------
    if shubetu == 2 or shubetu == 5:
        if shubetu == 2:
            read_data(buf, fp[7])

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[7], 21, nenrei):
                    G.Sokan_Tuma[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
                else:
                    readkiso_error(21)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[7], 22, nenrei):
                    G.Sokan_Ko[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
                else:
                    readkiso_error(22)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[7], 23, nenrei):
                    G.Sokan_Kafu[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
                else:
                    readkiso_error(23)

        if shubetu == 5:
            read_data(buf, fp[7])

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if _expect(buf, fp[7], 21, nenrei):
                    G.Sokan_Otto[0, nenrei - MIN_HIHO_NENREI] = buf.num[2]
                else:
                    readkiso_error(21)

        # **4本まとめて伸ばす**（種別 2 は Otto、種別 5 は Tuma/Ko/Kafu が
        # 前の種別の値のまま）
        for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                G.Sokan_Tuma[sotai_nendo, nenrei - MIN_HIHO_NENREI] \
                    = G.Sokan_Tuma[0, nenrei - MIN_HIHO_NENREI]
                G.Sokan_Otto[sotai_nendo, nenrei - MIN_HIHO_NENREI] \
                    = G.Sokan_Otto[0, nenrei - MIN_HIHO_NENREI]
                G.Sokan_Ko[sotai_nendo, nenrei - MIN_HIHO_NENREI] \
                    = G.Sokan_Ko[0, nenrei - MIN_HIHO_NENREI]
                G.Sokan_Kafu[sotai_nendo, nenrei - MIN_HIHO_NENREI] \
                    = G.Sokan_Kafu[0, nenrei - MIN_HIHO_NENREI]

    # ---- 老齢の失権率 ----------------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[8])

        for nenrei in range(MIN_HIHO_NENREI, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[8], 24, nenrei):
                shikkenritu[nenrei - 0, 0] = buf.num[2]
            else:
                readkiso_error(24)

        for nendo in range(SUIKEISHONENDO, SHIKKENRITU_MAX + 1):
            for nenrei in range(MIN_HIHO_NENREI, 104 + 1):
                # **3年平均で割る**（脱退力は1年だけ）
                G.Shikkenritu_Rorei[nendo - SHONENDO,
                                    nenrei - MIN_HIHO_NENREI] \
                    = (shikkenritu[nenrei - 0, 0]
                       * G.q[nendo - SHIKKENRITU_MIN, nenrei - 0, sex]
                       / ((G.q[LIFETABLE_NENDO - 1 - SHIKKENRITU_MIN,
                               nenrei - 0, sex]
                           + G.q[LIFETABLE_NENDO - SHIKKENRITU_MIN,
                                 nenrei - 0, sex]
                           + G.q[LIFETABLE_NENDO + 1 - SHIKKENRITU_MIN,
                                 nenrei - 0, sex]) / 3.))

            for nenrei in range(105, MAX_ROREI_JUKYU - 1 + 1):
                G.Shikkenritu_Rorei[nendo - SHONENDO,
                                    nenrei - MIN_HIHO_NENREI] \
                    = (shikkenritu[nenrei - 0, 0]
                       * G.Shikkenritu_Rorei[nendo - SHONENDO,
                                             104 - MIN_HIHO_NENREI]
                       / shikkenritu[104 - 0, 0])

            G.Shikkenritu_Rorei[nendo - SHONENDO,
                                MAX_ROREI_JUKYU - MIN_HIHO_NENREI] = 1.

        for nendo in range(SHIKKENRITU_MAX + 1, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_ROREI_JUKYU + 1):
                G.Shikkenritu_Rorei[nendo - SHONENDO,
                                    nenrei - MIN_HIHO_NENREI] \
                    = G.Shikkenritu_Rorei[SHIKKENRITU_MAX - SHONENDO,
                                          nenrei - MIN_HIHO_NENREI]

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_ROREI_JUKYU + 1):
                if G.Shikkenritu_Rorei[nendo - SHONENDO,
                                       nenrei - MIN_HIHO_NENREI] > 1.:
                    G.Shikkenritu_Rorei[nendo - SHONENDO,
                                        nenrei - MIN_HIHO_NENREI] = 1.

    # ---- 障害の失権率 ----------------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[9])

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[9], 25, nenrei):
                shikkenritu[nenrei - 0, 1] = buf.num[2]
            else:
                readkiso_error(25)

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[9], 26, nenrei):
                shikkenritu[nenrei - 0, 2] = buf.num[2]
            else:
                readkiso_error(26)

        for nendo in range(SUIKEISHONENDO, SHIKKENRITU_MAX + 1):
            for nenrei in range(MIN_SHOGAI_JUKYU, 104 + 1):
                # 原本は同じ3年平均を2回書いている（同じ演算・同じ順なので
                # ビット一致。ここでは1回だけ計算して使い回す）
                heikin = ((G.q[LIFETABLE_NENDO - 1 - SHIKKENRITU_MIN,
                               nenrei - 0, sex]
                           + G.q[LIFETABLE_NENDO - SHIKKENRITU_MIN,
                                 nenrei - 0, sex]
                           + G.q[LIFETABLE_NENDO + 1 - SHIKKENRITU_MIN,
                                 nenrei - 0, sex]) / 3.)

                G.Shikkenritu_Ippan[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = (shikkenritu[nenrei - 0, 1]
                       * G.q[nendo - SHIKKENRITU_MIN, nenrei - 0, sex]
                       / heikin)

                G.Shikkenritu_20mae[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = (shikkenritu[nenrei - 0, 2]
                       * G.q[nendo - SHIKKENRITU_MIN, nenrei - 0, sex]
                       / heikin)

            for nenrei in range(105, MAX_SHOGAI_JUKYU - 1 + 1):
                G.Shikkenritu_Ippan[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = (shikkenritu[nenrei - 0, 1]
                       * G.Shikkenritu_Ippan[nendo - SHONENDO,
                                             104 - MIN_SHOGAI_JUKYU]
                       / shikkenritu[104 - 0, 1])

                G.Shikkenritu_20mae[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = (shikkenritu[nenrei - 0, 2]
                       * G.Shikkenritu_20mae[nendo - SHONENDO,
                                             104 - MIN_SHOGAI_JUKYU]
                       / shikkenritu[104 - 0, 2])

            G.Shikkenritu_Ippan[nendo - SHONENDO,
                                MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU] = 1.
            G.Shikkenritu_20mae[nendo - SHONENDO,
                                MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU] = 1.

        for nendo in range(SHIKKENRITU_MAX + 1, SAISHUNENDO + 1):
            for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
                G.Shikkenritu_Ippan[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Shikkenritu_Ippan[SHIKKENRITU_MAX - SHONENDO,
                                          nenrei - MIN_SHOGAI_JUKYU]

                G.Shikkenritu_20mae[nendo - SHONENDO,
                                    nenrei - MIN_SHOGAI_JUKYU] \
                    = G.Shikkenritu_20mae[SHIKKENRITU_MAX - SHONENDO,
                                          nenrei - MIN_SHOGAI_JUKYU]

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
                if G.Shikkenritu_Ippan[nendo - SHONENDO,
                                       nenrei - MIN_SHOGAI_JUKYU] > 1.:
                    G.Shikkenritu_Ippan[nendo - SHONENDO,
                                        nenrei - MIN_SHOGAI_JUKYU] = 1.
                if G.Shikkenritu_20mae[nendo - SHONENDO,
                                       nenrei - MIN_SHOGAI_JUKYU] > 1.:
                    G.Shikkenritu_20mae[nendo - SHONENDO,
                                        nenrei - MIN_SHOGAI_JUKYU] = 1.

    # ---- 遺族・寡婦の失権率 ----------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[10])

        if shubetu == 2:
            for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                                MAX_IZOKU_TUMA_JUKYU + 1):
                if _expect(buf, fp[10], 27, nenrei):
                    G.Shikkenritu_Tuma[0, nenrei - MIN_IZOKU_TUMA_JUKYU] \
                        = buf.num[2]
                else:
                    readkiso_error(27)
            # 18歳・19歳は20歳の値で置く（ファイルに無い）
            G.Shikkenritu_Tuma[0, 18 - MIN_IZOKU_TUMA_JUKYU] \
                = G.Shikkenritu_Tuma[0, 20 - MIN_IZOKU_TUMA_JUKYU]
            G.Shikkenritu_Tuma[0, 19 - MIN_IZOKU_TUMA_JUKYU] \
                = G.Shikkenritu_Tuma[0, 20 - MIN_IZOKU_TUMA_JUKYU]

            for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
                if _expect(buf, fp[10], 28, nenrei):
                    G.Shikkenritu_Ko[0, nenrei - MIN_IZOKU_KO_JUKYU] \
                        = buf.num[2]
                else:
                    readkiso_error(28)

            for nenrei in range(MIN_KAFU_JUKYU, MAX_KAFU_JUKYU + 1):
                if _expect(buf, fp[10], 29, nenrei):
                    G.Shikkenritu_Kafu[0, nenrei - MIN_KAFU_JUKYU] \
                        = buf.num[2]
                else:
                    readkiso_error(29)

            for sotai_nendo in range(1, SAISHUNENDO - SHONENDO + 1):
                for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                                    MAX_IZOKU_TUMA_JUKYU + 1):
                    G.Shikkenritu_Tuma[sotai_nendo,
                                       nenrei - MIN_IZOKU_TUMA_JUKYU] \
                        = G.Shikkenritu_Tuma[0,
                                             nenrei - MIN_IZOKU_TUMA_JUKYU]

                for nenrei in range(MIN_IZOKU_KO_JUKYU,
                                    MAX_IZOKU_KO_JUKYU + 1):
                    G.Shikkenritu_Ko[sotai_nendo,
                                     nenrei - MIN_IZOKU_KO_JUKYU] \
                        = G.Shikkenritu_Ko[0, nenrei - MIN_IZOKU_KO_JUKYU]

                for nenrei in range(MIN_KAFU_JUKYU, MAX_KAFU_JUKYU + 1):
                    G.Shikkenritu_Kafu[sotai_nendo,
                                       nenrei - MIN_KAFU_JUKYU] \
                        = G.Shikkenritu_Kafu[0, nenrei - MIN_KAFU_JUKYU]

        if shubetu == 5:
            for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                MAX_IZOKU_OTTO_JUKYU + 1):
                if _expect(buf, fp[10], 27, nenrei):
                    shikkenritu[nenrei - 0, 3] = buf.num[2]
                else:
                    readkiso_error(27)

            # 13年（`2014 + 19 - SHONENDO`）かけて **2歳若い妻**の
            # 失権率へ線形に移す。`Shikkenritu_Tuma` は種別 2 で読んだ値
            for sotai_nendo in range(1, 2014 + 19 - SHONENDO + 1):
                for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                    MAX_IZOKU_OTTO_JUKYU + 1):
                    G.Shikkenritu_Otto[sotai_nendo,
                                       nenrei - MIN_IZOKU_OTTO_JUKYU] \
                        = ((( 2014 + 19 - SHONENDO - sotai_nendo)
                            * shikkenritu[nenrei - 0, 3]
                            + sotai_nendo
                            * G.Shikkenritu_Tuma[
                                0, nenrei - 2 - MIN_IZOKU_TUMA_JUKYU])
                           / float(2014 + 19 - SHONENDO))

            for sotai_nendo in range(2014 + 19 + 1 - SHONENDO,
                                     SAISHUNENDO - SHONENDO + 1):
                for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                                    MAX_IZOKU_OTTO_JUKYU + 1):
                    G.Shikkenritu_Otto[sotai_nendo,
                                       nenrei - MIN_IZOKU_OTTO_JUKYU] \
                        = G.Shikkenritu_Otto[2014 + 19 - SHONENDO,
                                             nenrei - MIN_IZOKU_OTTO_JUKYU]

    # ---- 支給率（301 老齢基礎） ------------------------------------
    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[11])

        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[11], 301, nenrei):
                rec = G.Shikyuritu_Rorei[SUIKEISHONENDO - SHONENDO,
                                         nenrei - MIN_ROREI_JUKYU]
                rec["ninzu"] = buf.num[2]
                rec["noufu"] = buf.num[3]
                # 段階 0・1 は buffer[4]、段階 2 以上は buffer[5]
                for dankai in range(0, 1 + 1):
                    for kokko in range(0, KOKKO_HIKIAGE - 1 + 1):
                        rec["menjo"][dankai, kokko] = buf.num[4]
                for dankai in range(2, MENJO_DANKAI):
                    for kokko in range(0, KOKKO_HIKIAGE - 1 + 1):
                        rec["menjo"][dankai, kokko] = buf.num[5]
                rec["rofuku_shitasasae"] = buf.num[6]
                rec["fuka"] = buf.num[7]
            else:
                readkiso_error(301)
    else:
        # 種別 3・6 は `fp[shubetu / 3]` から納付だけ読む
        read_data(buf, fp[shubetu // 3])

        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[shubetu // 3], 301, nenrei):
                G.Shikyuritu_Rorei[SUIKEISHONENDO - SHONENDO,
                                   nenrei - MIN_ROREI_JUKYU]["noufu"] \
                    = buf.num[2]
            else:
                readkiso_error(301)

    # 老齢基礎の支給率を将来に伸ばす。労福下支えだけ**1年1歳ずらす**
    for nendo in range(SUIKEISHONENDO + 1, SAISHUNENDO + 1):
        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            dst = G.Shikyuritu_Rorei[nendo - SHONENDO,
                                     nenrei - MIN_ROREI_JUKYU]
            src = G.Shikyuritu_Rorei[SUIKEISHONENDO - SHONENDO,
                                     nenrei - MIN_ROREI_JUKYU]

            dst["ninzu"] = src["ninzu"]
            dst["noufu"] = src["noufu"]

            for dankai in range(0, MENJO_DANKAI):
                for kokko in range(0, KOKKO_HIKIAGE - 1 + 1):
                    dst["menjo"][dankai, kokko] = src["menjo"][dankai, kokko]

            dst["fuka"] = src["fuka"]

            if nenrei >= MIN_ROREI_JUKYU + 1:
                dst["rofuku_shitasasae"] = G.Shikyuritu_Rorei[
                    nendo - 1 - SHONENDO,
                    nenrei - 1 - MIN_ROREI_JUKYU]["rofuku_shitasasae"]
            else:
                dst["rofuku_shitasasae"] = 1.

    # ---- 支給率（302 旧法老齢・303 旧法通算老齢） ------------------
    if shubetu == 2 or shubetu == 5:
        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[11], 302, nenrei):
                rec = G.Shikyuritu_Rorei_Kyu[SUIKEISHONENDO - SHONENDO,
                                             nenrei - MIN_ROREI_JUKYU]
                rec["ninzu"] = buf.num[2]
                rec["noufu"] = buf.num[3]
                rec["menjo"] = buf.num[4]
                rec["kasa_noufu"] = buf.num[5]
                rec["kasa_menjo"] = buf.num[6]
                rec["rofuku_shitasasae"] = buf.num[7]
                rec["fuka"] = buf.num[8]
            else:
                readkiso_error(302)

        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[11], 303, nenrei):
                rec = G.Shikyuritu_Turo_Kyu[SUIKEISHONENDO - SHONENDO,
                                            nenrei - MIN_ROREI_JUKYU]
                rec["ninzu"] = buf.num[2]
                rec["noufu"] = buf.num[3]
                rec["menjo"] = buf.num[4]
                rec["kasa_noufu"] = buf.num[5]
                rec["kasa_menjo"] = buf.num[6]
                rec["rofuku_shitasasae"] = buf.num[7]
                rec["fuka"] = buf.num[8]
            else:
                readkiso_error(303)

        # 旧法は**構造体まるごと1年1歳ずらす**（新規裁定が無いので）
        for nendo in range(SUIKEISHONENDO + 1, SAISHUNENDO + 1):
            for nenrei in range(MIN_ROREI_JUKYU + 1, MAX_ROREI_JUKYU + 1):
                G.Shikyuritu_Rorei_Kyu[nendo - SHONENDO,
                                       nenrei - MIN_ROREI_JUKYU] \
                    = G.Shikyuritu_Rorei_Kyu[nendo - 1 - SHONENDO,
                                             nenrei - 1 - MIN_ROREI_JUKYU]

                G.Shikyuritu_Turo_Kyu[nendo - SHONENDO,
                                      nenrei - MIN_ROREI_JUKYU] \
                    = G.Shikyuritu_Turo_Kyu[nendo - 1 - SHONENDO,
                                            nenrei - 1 - MIN_ROREI_JUKYU]

            for name in ("Shikyuritu_Rorei_Kyu", "Shikyuritu_Turo_Kyu"):
                rec = getattr(G, name)[nendo - SHONENDO,
                                       MIN_ROREI_JUKYU - MIN_ROREI_JUKYU]
                rec["ninzu"] = 1.
                rec["noufu"] = 1.
                rec["menjo"] = 1.
                rec["kasa_noufu"] = 1.
                rec["kasa_menjo"] = 1.
                rec["rofuku_shitasasae"] = 1.
                rec["fuka"] = 1.

        # ---- 支給率（304 5年年金） ---------------------------------
        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if _expect(buf, fp[11], 304, nenrei):
                G.Shikyuritu_Gonen[SUIKEISHONENDO - SHONENDO,
                                   nenrei - MIN_ROREI_JUKYU] = buf.num[2]
            else:
                readkiso_error(304)

        for nendo in range(SUIKEISHONENDO + 1, SAISHUNENDO + 1):
            for nenrei in range(MIN_ROREI_JUKYU + 1, MAX_ROREI_JUKYU + 1):
                G.Shikyuritu_Gonen[nendo - SHONENDO,
                                   nenrei - MIN_ROREI_JUKYU] \
                    = G.Shikyuritu_Gonen[nendo - 1 - SHONENDO,
                                         nenrei - 1 - MIN_ROREI_JUKYU]

            G.Shikyuritu_Gonen[nendo - SHONENDO,
                               MIN_ROREI_JUKYU - MIN_ROREI_JUKYU] = 1.

        # ---- 支給率（305 障害一般・306 20歳前） --------------------
        # **入れる年度が `SHONENDO`**（老齢は `SUIKEISHONENDO`）
        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[11], 305, nenrei):
                i = nenrei - MIN_SHOGAI_JUKYU
                G.Shikyuritu_Shogai_Ippan[0, i, 1] = buf.num[4]
                G.Shikyuritu_Shogai_Ippan[0, i, 2] = buf.num[5]
                G.Shikyuritu_Shogai_Ippan_keinen[0, i, 1] = buf.num[2]
                G.Shikyuritu_Shogai_Ippan_keinen[0, i, 2] = buf.num[3]
            else:
                readkiso_error(305)

        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[11], 306, nenrei):
                i = nenrei - MIN_SHOGAI_JUKYU
                G.Shikyuritu_Shogai_20mae[0, i, 1] = buf.num[4]
                G.Shikyuritu_Shogai_20mae[0, i, 2] = buf.num[5]
                G.Shikyuritu_Shogai_20mae_keinen[0, i, 1] = buf.num[2]
                G.Shikyuritu_Shogai_20mae_keinen[0, i, 2] = buf.num[3]
            else:
                readkiso_error(306)

        # 経過措置の生年の境目（種別 2 は男、5 は女で**5年ずれる**）
        if shubetu == 2:
            keinen = ((1953, 1954, 60), (1955, 1956, 61),
                      (1957, 1958, 62), (1959, 1960, 63))
            keinen_ijou = 1961
        else:
            keinen = ((1958, 1959, 60), (1960, 1961, 61),
                      (1962, 1963, 62), (1964, 1965, 63))
            keinen_ijou = 1966

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for tokyu in range(1, 2 + 1):
                for nenrei in range(MIN_SHOGAI_JUKYU,
                                    SUIKEISHONENDO - N_O_NENDO + 1):
                    i = nenrei - MIN_SHOGAI_JUKYU

                    G.Shikyuritu_Shogai_Ippan[nendo - SHONENDO, i, tokyu] \
                        = G.Shikyuritu_Shogai_Ippan[0, i, tokyu]

                    G.Shikyuritu_Shogai_20mae[nendo - SHONENDO, i, tokyu] \
                        = G.Shikyuritu_Shogai_20mae[0, i, tokyu]

                    # 原本は同じ形の `if` を5つ並べて書いている。
                    # 生年で排他なのでまとめても結果は同じ
                    seinen = nendo - nenrei
                    hit = False
                    for a, b, ue in keinen:
                        if ((seinen == a or seinen == b)
                                and 60 <= nenrei <= ue):
                            hit = True
                    if seinen >= keinen_ijou and 60 <= nenrei <= 64:
                        hit = True

                    if hit:
                        G.Shikyuritu_Shogai_Ippan[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_Ippan_keinen[0, i, tokyu]
                        G.Shikyuritu_Shogai_20mae[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_20mae_keinen[0, i, tokyu]

                for nenrei in range(SUIKEISHONENDO - N_O_NENDO + 1,
                                    MAX_SHOGAI_JUKYU + 1):
                    i = nenrei - MIN_SHOGAI_JUKYU

                    if SHONENDO + 1 <= nendo <= SUIKEISHONENDO:
                        # 年度だけ1年ずらす（年齢は据え置き）
                        G.Shikyuritu_Shogai_Ippan[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_Ippan[
                                nendo - 1 - SHONENDO, i, tokyu]
                        G.Shikyuritu_Shogai_20mae[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_20mae[
                                nendo - 1 - SHONENDO, i, tokyu]

                    if nendo >= SUIKEISHONENDO + 1:
                        # 1年1歳ずらす
                        G.Shikyuritu_Shogai_Ippan[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_Ippan[
                                nendo - 1 - SHONENDO, i - 1, tokyu]
                        G.Shikyuritu_Shogai_20mae[
                            nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_20mae[
                                nendo - 1 - SHONENDO, i - 1, tokyu]

        # ---- 支給率（307 旧法障害） --------------------------------
        for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
            if _expect(buf, fp[11], 307, nenrei):
                i = nenrei - MIN_SHOGAI_JUKYU
                G.Shikyuritu_Shogai_Kyu[0, i, 1] = buf.num[2]
                G.Shikyuritu_Shogai_Kyu[0, i, 2] = buf.num[3]
            else:
                readkiso_error(307)

        for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
            for tokyu in range(1, 2 + 1):
                for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
                    i = nenrei - MIN_SHOGAI_JUKYU
                    if nenrei == MIN_SHOGAI_JUKYU:
                        G.Shikyuritu_Shogai_Kyu[nendo - SHONENDO, i,
                                                tokyu] = 1.
                    elif nenrei == 65:
                        # 65歳だけ足元の値に戻す（老齢基礎への切替）
                        G.Shikyuritu_Shogai_Kyu[nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_Kyu[0, i, tokyu]
                    else:
                        G.Shikyuritu_Shogai_Kyu[nendo - SHONENDO, i, tokyu] \
                            = G.Shikyuritu_Shogai_Kyu[nendo - 1 - SHONENDO,
                                                      i - 1, tokyu]

    # ---- 支給率（308 遺族・309 寡婦） ------------------------------
    if shubetu == 2 or shubetu == 5:
        if _expect(buf, fp[11], 308, 308):
            if shubetu == 2:
                G.Shikyuritu_Tuma[0] = buf.num[2]
                G.Shikyuritu_Ko[0] = buf.num[3]
            if shubetu == 5:
                G.Shikyuritu_Otto[0] = buf.num[2]
        else:
            readkiso_error(308)

        if shubetu == 2:
            for nenrei in range(60, MAX_KAFU_JUKYU + 1):
                if _expect(buf, fp[11], 309, nenrei):
                    G.Shikyuritu_Kafu[0, nenrei - 60] = buf.num[2]
                else:
                    readkiso_error(309)

        # **3本まとめて伸ばす**（種別 2 は Otto、種別 5 は Tuma/Ko が
        # 前の種別の値のまま。`Sokan_*` と同じ形）
        for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
            G.Shikyuritu_Tuma[nendo - SHONENDO] = G.Shikyuritu_Tuma[0]
            G.Shikyuritu_Otto[nendo - SHONENDO] = G.Shikyuritu_Otto[0]
            G.Shikyuritu_Ko[nendo - SHONENDO] = G.Shikyuritu_Ko[0]

        for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
            for nenrei in range(60, MAX_KAFU_JUKYU + 1):
                G.Shikyuritu_Kafu[nendo - SHONENDO, nenrei - 60] \
                    = G.Shikyuritu_Kafu[0, nenrei - 60]

                if G.Option == 1:
                    # 基礎45年化のときは寡婦年金の支給を止める
                    if extendb(G, nendo, nenrei) == 1:
                        G.Shikyuritu_Kafu[nendo - SHONENDO,
                                          nenrei - 60] = 0.

    # ---- 一部繰上げの適用拡大 --------------------------------------
    # まず全部 1 で埋める（`fp[12]` で上書きするのは 60〜64歳だけ）
    for seinendo in range(SUIKEISHONENDO - MAX_ROREI_JUKYU,
                          SUIKEISAISHUNENDO - MIN_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            rec = G.Kakudai_Ichibu[
                seinendo - (SUIKEISHONENDO - MAX_ROREI_JUKYU),
                jukyu_nenrei - MIN_ROREI_JUKYU]
            rec["ninzu"] = 1.
            rec["noufu"] = 1.
            for dankai in range(0, MENJO_DANKAI):
                for kokko in range(0, KOKKO_HIKIAGE - 1 + 1):
                    rec["menjo"][dankai, kokko] = 1.
            rec["rofuku_shitasasae"] = 1.
            rec["fuka"] = 1.

    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[12])

        for seinendo in range(SUIKEISHONENDO - 64, SUIKEISHONENDO - 60 + 1):
            for jukyu_nenrei in range(60, 64 + 1):
                if _expect(buf, fp[12], seinendo, jukyu_nenrei):
                    rec = G.Kakudai_Ichibu[
                        seinendo - (SUIKEISHONENDO - MAX_ROREI_JUKYU),
                        jukyu_nenrei - MIN_ROREI_JUKYU]
                    rec["noufu"] = buf.num[2]
                    rec["menjo"][ZENGAKU, 1] = buf.num[3]
                    rec["menjo"][MENJO_3_4, 1] = buf.num[4]
                    rec["menjo"][MENJO_1_2, 1] = buf.num[5]
                    rec["menjo"][MENJO_1_4, 1] = buf.num[6]
                    rec["fuka"] = buf.num[7]
                else:
                    readkiso_error(31)
    else:
        # 種別 3・6 は `fp[( shubetu / 3 ) + 1]` から納付だけ
        read_data(buf, fp[(shubetu // 3) + 1])
        for seinendo in range(SUIKEISHONENDO - 64, SUIKEISHONENDO - 60 + 1):
            for jukyu_nenrei in range(60, 64 + 1):
                if _expect(buf, fp[(shubetu // 3) + 1],
                           seinendo, jukyu_nenrei):
                    G.Kakudai_Ichibu[
                        seinendo - (SUIKEISHONENDO - MAX_ROREI_JUKYU),
                        jukyu_nenrei - MIN_ROREI_JUKYU]["noufu"] \
                        = buf.num[2]
                else:
                    readkiso_error(31)

    # ---- 繰上げの割引率 --------------------------------------------
    # 見出しの読み飛ばしは種別を問わず走る（本体は種別 2 だけ）
    read_data(buf, G.fp_in[_WARIBIKI])
    if shubetu == 2:
        for counter in range(0, 1 + 1):
            for jukyu_nenrei in range(66, 70 + 1):
                for nendo in range(SUIKEISHONENDO + 1,
                                   SUIKEISHONENDO + 10 + 1):
                    if _expect(buf, G.fp_in[_WARIBIKI],
                               counter, jukyu_nenrei, nendo):
                        G.Waribikiritu[counter, 0, jukyu_nenrei - 66,
                                       nendo - SUIKEISHONENDO - 1] \
                            = buf.num[3]
                        G.Waribikiritu[counter, 1, jukyu_nenrei - 66,
                                       nendo - SUIKEISHONENDO - 1] \
                            = buf.num[4]
                    else:
                        raise NatError(
                            "割引率ファイル読込途中にＥＯＦを検出しました")

    # ---- 給付率（1本目） -------------------------------------------
    read_data(buf, G.fp_in[_KYUFU])

    if shubetu == 2:
        for counter in range(0, 1 + 1):
            for jukyu_nenrei in range(60, 70 + 1):
                if _expect(buf, G.fp_in[_KYUFU], counter, jukyu_nenrei):
                    kyufu_temp[jukyu_nenrei - MIN_ROREI_JUKYU, counter] \
                        = buf.num[2]
                else:
                    raise NatError(
                        "給付率ファイル読込途中にＥＯＦを検出しました")

        for seinendo in range(SUIKEISHONENDO - 70,
                              SUIKEISAISHUNENDO - MIN_ROREI_JUKYU + 1):
            for jukyu_nenrei in range(60, 70 + 1):
                j = jukyu_nenrei - MIN_ROREI_JUKYU
                s = seinendo - (SUIKEISHONENDO - 70)
                if seinendo < _HENKOU_SEINENDO:
                    G.Kyufu_ritu1[j, s, 0] = kyufu_temp[j, 0]
                    G.Kyufu_ritu1[j, s, 1] = kyufu_temp[j, 0]
                    G.Kyufu_ritu[j, s, 0] = kyufu_temp[j, 0]
                    G.Kyufu_ritu[j, s, 1] = kyufu_temp[j, 0]
                else:
                    # **`Kyufu_ritu` は入れない**（あとでまとめて作る）
                    G.Kyufu_ritu1[j, s, 0] = kyufu_temp[j, 1]
                    G.Kyufu_ritu1[j, s, 1] = kyufu_temp[j, 1]

    # ---- 給付率（2本目） -------------------------------------------
    read_data(buf, G.fp_in[_KYUFU2])

    if shubetu == 2:
        for counter in range(0, 1 + 1):
            for jukyu_nenrei in range(60, 70 + 1):
                if _expect(buf, G.fp_in[_KYUFU2], counter, jukyu_nenrei):
                    kyufu_temp[jukyu_nenrei - MIN_ROREI_JUKYU, counter] \
                        = buf.num[2]
                else:
                    raise NatError(
                        "給付率ファイル読込途中にＥＯＦを検出しました")

        for seinendo in range(SUIKEISHONENDO - 70,
                              SUIKEISAISHUNENDO - MIN_ROREI_JUKYU + 1):
            for jukyu_nenrei in range(60, 70 + 1):
                j = jukyu_nenrei - MIN_ROREI_JUKYU
                s = seinendo - (SUIKEISHONENDO - 70)
                if seinendo < _HENKOU_SEINENDO:
                    G.Kyufu_ritu2[j, s, 0] = kyufu_temp[j, 0]
                    G.Kyufu_ritu2[j, s, 1] = kyufu_temp[j, 0]
                else:
                    G.Kyufu_ritu2[j, s, 0] = kyufu_temp[j, 1]
                    G.Kyufu_ritu2[j, s, 1] = kyufu_temp[j, 1]

    # 1962年生以降は2本目、それより前は1本目
    if shubetu == 2:
        for seinendo in range(SUIKEISHONENDO - 70,
                              SUIKEISAISHUNENDO - MIN_ROREI_JUKYU + 1):
            for jukyu_nenrei in range(60, 70 + 1):
                j = jukyu_nenrei - MIN_ROREI_JUKYU
                s = seinendo - (SUIKEISHONENDO - 70)
                if seinendo >= 1962:
                    G.Kyufu_ritu[j, s, 0] = G.Kyufu_ritu2[j, s, 0]
                    G.Kyufu_ritu[j, s, 1] = G.Kyufu_ritu2[j, s, 1]
                else:
                    G.Kyufu_ritu[j, s, 0] = G.Kyufu_ritu1[j, s, 0]
                    G.Kyufu_ritu[j, s, 1] = G.Kyufu_ritu1[j, s, 1]

    return
