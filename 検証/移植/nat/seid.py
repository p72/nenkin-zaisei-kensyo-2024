# -*- coding: utf-8 -*-
"""
国民年金/seid.c の忠実移植（制度の定数）
=========================================
92 行。法令で決まっている値を入れる。経済前提を掛ける前の
**平成16年度（2004年度）価格**。

加入可能年数（`Kanou_Nensu`）
-----------------------------
```c
if( seinendo <= 1941 ) Kanou_Nensu[…] = 25 + seinendo - N_O_NENDO;
else                   Kanou_Nensu[…] = 40;
```

`N_O_NENDO` は 1926（大正15年度＝昭和元年度）。1926年度生まれは
**25年**、そこから1年ごとに1年増えて 1941年度生まれで
25 + 15 = **40年**。1942年度生まれ以降は 40年で一定。

国民年金は 1961年度（昭和36年度）に始まったので、それ以前に
20歳を過ぎていた人は 40年ぶん納められない。その分の読み替え。

`nendo` のループの中で `seinendo` を回すが、**中身は `nendo` に
依存しない**（`Option == 1` の枝を除く）。106年度 × 200生年 =
21,200 回、同じ値を入れ直している。

45年化オプション
----------------
```c
if( Option == 1 && nendo >= OPTION_START ) {
  for( seinendo = OPTION_START - 60 ; seinendo <= SAISHUNENDO ; seinendo++ )
    Kanou_Nensu[…] = 40 + min( encho_nensu( seinendo , 0 ) , encho_year( nendo ) );
}
```

`encho_nensu( seinendo , 0 )` は**第2引数に 0（年齢）を渡す**ので、
`stdfm.c` の中では `nendo - nenrei + 60 + k` = `seinendo + 60 + k` に
なる。つまり「その生年の人が60歳になる年度」を起点に数える。
`encho_year( nendo )` は「その年度までに何歳上がったか」。
**小さい方**を採るので、生年が早い人は 40 年のまま、
遅い人はその年度までに上がったぶんだけ増える。

満額（`Full_Pension_Shonendo`）
------------------------------
```c
Full_Pension_Shonendo[…] = 780900.;
```

**全生年 780,900円**（2004年度価格の満額）。45年化のときだけ

```c
Full_Pension_Shonendo[…] *= Kanou_Nensu[…] / 40.;
```

と加入可能年数に比例して増やす。`*=` なので**上の 780900 の
代入のあとに掛ける**。`Kanou_Nensu` は上のループで入れた値
（`nendo` が同じ）を読む。

直書きの単価
------------
| 変数 | 値 | 中身 |
|---|---:|---|
| `Full_Pension_Fuka` | 2,400 | 付加年金（1年あたり） |
| `Kakyu_Tanka_12shi_Shonendo` | 224,700 | 加給（子1人目・2人目） |
| `Kakyu_Tanka_3shiiko_Shonendo` | 74,900 | 加給（子3人目以降） |
| `Tanka_Shibou_Fuka` | 8,500 | 死亡一時金の付加相当 |

死亡一時金の単価（`Tanka_Shibou_Shonendo[7]`）
----------------------------------------------
納付月数の区分ごと。区分の名前は `econ.c:494-496` の
`ichijikin_kubun[]`（出力の見出し）にある。

| 添字 | 納付月数 | 単価 |
|---|---|---:|
| 0 | 36月以上180月未満 | 120,000 |
| 1 | 180月以上240月未満 | 145,000 |
| 2 | 240月以上300月未満 | 170,000 |
| 3 | 300月以上360月未満 | 220,000 |
| 4 | 360月以上420月未満 | 270,000 |
| 5 | 420月以上 | 320,000 |
| 6 | （通常は使わない） | 320,000 |

`Option == 1`（45年化）のときだけ `[6]` を **370,000** に上げ、
`[5]` の意味が「420月以上**480月未満**」に、`[6]` が
「480月以上」になる。出力の見出しもそう変わる
（`econ.c:508` が `",%s"` ではなく `"480月未満,480月以上"` を
**カンマなしで**足すので、`[5]` の見出しが
`"420月以上480月未満"` につながる。意図どおり）。

45年化で納付月数が 540月まで伸びるので区分を1つ足したかたち。
通常試算では `[5]` と `[6]` が同じ 320,000 で、`[6]` は
出力にも出ない。

保険料の割合（`Hokenryou_Wariai[5]`）
------------------------------------
```c
Hokenryou_Wariai[SUM]       = 0.;      /* SUM = 0 */
Hokenryou_Wariai[ZENGAKU]   = 0.;      /* ZENGAKU = 1（全額免除） */
Hokenryou_Wariai[MENJO_3_4] = 0.25;    /* 4分の3免除 → 4分の1納付 */
Hokenryou_Wariai[MENJO_1_2] = 0.5;
Hokenryou_Wariai[MENJO_1_4] = 0.75;
```

**免除の段階に対して「納めた割合」**を持つ。全額免除は 0。

障害の倍率（`Shogai_Bairitu[3]`）
--------------------------------
`[0] = 0`（使わない）、`[1] = 1.25`（1級）、`[2] = 1.00`（2級）。

国庫負担の割合（`Kokko_Wariai[3]`）
----------------------------------
```c
Kokko_Wariai[1] = 1. / 3.;
Kokko_Wariai[2] = 1. / 2.;
```

**`Kokko_Wariai[0]` に代入が無い。** C のグローバルなので 0 のまま。
2009年度（`TOKUTEI_NENDO`）3月までが3分の1、4月からが2分の1で、
添字 0 は「国庫負担なし」の欄として 0 のまま使われる。
`検証/原本の不具合.md` の D の仲間（ただし**0 であることに
意味がある**のでこちらは意図どおりと読める）。
"""
from setconst import (MENJO_1_2, MENJO_1_4, MENJO_3_4, N_O_NENDO,
                      SAISHUNENDO, SHONENDO, SUM, ZENGAKU)
from stdfm import c_min, encho_nensu, encho_year

__all__ = ["seid"]


def seid(G):
    """seid.c:8 の忠実移植。"""
    Kanou_Nensu = G.Kanou_Nensu
    Full_Pension_Shonendo = G.Full_Pension_Shonendo

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for seinendo in range(N_O_NENDO, SAISHUNENDO + 1):
            if seinendo <= 1941:
                Kanou_Nensu[nendo - SHONENDO][seinendo - N_O_NENDO] = (
                    25 + seinendo - N_O_NENDO)
            else:
                Kanou_Nensu[nendo - SHONENDO][seinendo - N_O_NENDO] = 40

        if G.Option == 1 and nendo >= G.OPTION_START:
            for seinendo in range(G.OPTION_START - 60, SAISHUNENDO + 1):
                Kanou_Nensu[nendo - SHONENDO][seinendo - N_O_NENDO] = (
                    40 + c_min(encho_nensu(G, seinendo, 0),
                               encho_year(G, nendo)))

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for seinendo in range(N_O_NENDO, SAISHUNENDO + 1):
            Full_Pension_Shonendo[nendo - SHONENDO][
                seinendo - N_O_NENDO] = 780900.

        if G.Option == 1 and nendo >= G.OPTION_START:
            for seinendo in range(G.OPTION_START - 60, SAISHUNENDO + 1):
                # 原本は `*=`。上で入れた 780900 に掛ける
                Full_Pension_Shonendo[nendo - SHONENDO][
                    seinendo - N_O_NENDO] *= (
                        Kanou_Nensu[nendo - SHONENDO][
                            seinendo - N_O_NENDO] / 40.)

    G.Full_Pension_Fuka = 2400.

    G.Kakyu_Tanka_12shi_Shonendo = 224700.

    G.Kakyu_Tanka_3shiiko_Shonendo = 74900.

    G.Tanka_Shibou_Shonendo[0] = 120000.
    G.Tanka_Shibou_Shonendo[1] = 145000.
    G.Tanka_Shibou_Shonendo[2] = 170000.
    G.Tanka_Shibou_Shonendo[3] = 220000.
    G.Tanka_Shibou_Shonendo[4] = 270000.
    G.Tanka_Shibou_Shonendo[5] = 320000.

    G.Tanka_Shibou_Shonendo[6] = 320000.
    if G.Option == 1:
        G.Tanka_Shibou_Shonendo[6] = 370000.

    G.Tanka_Shibou_Fuka = 8500.

    G.Hokenryou_Wariai[SUM] = 0.
    G.Hokenryou_Wariai[ZENGAKU] = 0.
    G.Hokenryou_Wariai[MENJO_3_4] = 0.25
    G.Hokenryou_Wariai[MENJO_1_2] = 0.5
    G.Hokenryou_Wariai[MENJO_1_4] = 0.75

    G.Shogai_Bairitu[0] = 0.
    G.Shogai_Bairitu[1] = 1.25
    G.Shogai_Bairitu[2] = 1.00

    # 原本は `Kokko_Wariai[0]` に代入しない（0 のまま）
    G.Kokko_Wariai[1] = 1. / 3.
    G.Kokko_Wariai[2] = 1. / 2.
