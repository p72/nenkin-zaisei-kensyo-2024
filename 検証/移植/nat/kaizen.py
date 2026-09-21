# -*- coding: utf-8 -*-
"""
国民年金/kaizen.c の忠実移植（生命表と有配偶率を読む）
=======================================================
108 行。2つのファイルを読む。

    q[年度][年齢][性別]            死亡率（生命表。10万人あたり）
    Izoku_Keinen[年度][年齢][性別] 有配偶率（遺族の発生に使う）

死亡率は 10万分の1
------------------
```c
q[nendo - SHIKKENRITU_MIN][nenrei - 1][seibetu] = buffer[nenrei];
q[nendo - SHIKKENRITU_MIN][nenrei - 1][seibetu] /= 100000.;
```

生命表は「10万人あたり何人死ぬか」で書いてあるので 100000 で割る。
**2文に分けて書いてある**（代入してから割る）。1文にまとめても
同じ値になるが、原本のとおり2文で写す。

年度は `SHIKKENRITU_MIN`（2019）〜`SHIKKENRITU_MAX`（2070）の 52年ぶん。
年齢は `nenrei` を 1〜115 で回して `nenrei - 1`（0〜114）に入れる。
**列は `buffer[1]` から**で、`buffer[0]` は性別か年度の欄。

有配偶率は 2070年度までしか無い
------------------------------
```c
for( nendo = I_KEINEN_SHONENDO ; nendo <= I_KEINEN_SAISHUNENDO ; nendo++ )
  Izoku_Keinen[…] = buffer[nendo - I_KEINEN_SHONENDO + 2];
…
for( nendo = I_KEINEN_SAISHUNENDO + 1 ; nendo <= SAISHUNENDO ; nendo++ )
  Izoku_Keinen[nendo - …] = Izoku_Keinen[I_KEINEN_SAISHUNENDO - …];
```

ファイルにあるのは 2020〜2070年度（`I_KEINEN_*`）の 51年ぶん。
2071〜2125年度は**2070年度の値をそのまま延ばす**。

`if( … ) { }` の空の分岐が2か所
-------------------------------
```c
if( read_data( buffer , fp_in[LIFETABLE] , &data_number ) != EOF )
{

}
else
{
	cout << "LIFETABLEファイル読込途中にＥＯＦを検出しました" << endl;
	exit( 1 );
}
```

**中身が空**。「見出しを1行読み捨てて、EOF なら落ちる」だけなら
`if( read_data(…) == EOF ) { … exit(1); }` と書けるところを、
空の `if` を置いて `else` に落としている。`検証/原本の不具合.md` の
F15（②の空の分岐）の仲間。同じ形が `IZOKU_KEINEN` の側にもある。

`Izoku_Keinen` を 0 にするループの年度の範囲
--------------------------------------------
```c
for( nendo = SHONENDO ; nendo <= SAISHUNENDO ; nendo++ )
  Izoku_Keinen[nendo - I_KEINEN_SHONENDO][…] = 0.;
```

**添字の基準が `SHONENDO` ではなく `I_KEINEN_SHONENDO`**。
どちらも 2020 なので同じ値になり、添字は 0〜105 で
`Izoku_Keinen[106]` の中に収まる。定数を片方だけ変えると
配列の外に出るが、いまは合っている。

EOF の見分けが雑
----------------
```c
if( read_data( … ) != EOF && buffer[0] == seibetu && buffer[1] == nenrei ) { … }
else { printf( "有配偶率ファイル読込途中にＥＯＦを検出しました\\n" ); exit( 1 ); }
```

性別や年齢が合わないときも「ＥＯＦを検出」と出して落ちる
（`waku.c` と同じ形）。
"""
from setconst import (I_KEINEN_SAISHUNENDO, I_KEINEN_SHONENDO,
                      MAX_HIHO_NENREI, MAX_ROREI_JUKYU, MIN_HIHO_NENREI,
                      SAISHUNENDO, SHIKKENRITU_MAX, SHIKKENRITU_MIN,
                      SHONENDO)
from stdfm import EOF, Buffer, NatError, read_data

__all__ = ["kaizen"]

# `mfile_open.h` の入力番号
_LIFETABLE = 11
_IZOKU_KEINEN = 85


def kaizen(G):
    """kaizen.c:12 の忠実移植。"""
    buf = Buffer(120)           # 原本は `double buffer[120]`

    q = G.q
    Izoku_Keinen = G.Izoku_Keinen

    # 原本は `if( … != EOF ) { }` と**空の分岐**で書いてある
    if read_data(buf, G.fp_in[_LIFETABLE]) != EOF:
        pass
    else:
        raise NatError("LIFETABLEファイル読込途中にＥＯＦを検出しました")

    for seibetu in range(0, 1 + 1):
        for nendo in range(SHIKKENRITU_MIN, SHIKKENRITU_MAX + 1):
            if read_data(buf, G.fp_in[_LIFETABLE]) != EOF:
                for nenrei in range(0 + 1, MAX_ROREI_JUKYU - 1 + 1 + 1):
                    # 原本は代入してから割る（2文）
                    q[nendo - SHIKKENRITU_MIN][nenrei - 1][seibetu] = \
                        buf.num[nenrei]
                    q[nendo - SHIKKENRITU_MIN][nenrei - 1][seibetu] /= 100000.
            else:
                raise NatError(
                    "LIFETABLEファイル読込途中にＥＯＦを検出しました")

    for seibetu in range(0, 1 + 1):
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                # 添字の基準は `I_KEINEN_SHONENDO`（どちらも 2020）
                Izoku_Keinen[nendo - I_KEINEN_SHONENDO][
                    nenrei - MIN_HIHO_NENREI][seibetu] = 0.

    if read_data(buf, G.fp_in[_IZOKU_KEINEN]) != EOF:
        pass
    else:
        raise NatError("有配偶率ファイル読込途中にＥＯＦを検出しました")

    for seibetu in range(0, 1 + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            if (read_data(buf, G.fp_in[_IZOKU_KEINEN]) != EOF
                    and buf.num[0] == seibetu
                    and buf.num[1] == nenrei):
                for nendo in range(I_KEINEN_SHONENDO,
                                   I_KEINEN_SAISHUNENDO + 1):
                    Izoku_Keinen[nendo - I_KEINEN_SHONENDO][
                        nenrei - MIN_HIHO_NENREI][seibetu] = \
                        buf.num[nendo - I_KEINEN_SHONENDO + 2]
            else:
                raise NatError(
                    "有配偶率ファイル読込途中にＥＯＦを検出しました")

    for seibetu in range(0, 1 + 1):
        for nendo in range(I_KEINEN_SAISHUNENDO + 1, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                # 2071年度以降は 2070年度の値をそのまま延ばす
                Izoku_Keinen[nendo - I_KEINEN_SHONENDO][
                    nenrei - MIN_HIHO_NENREI][seibetu] = \
                    Izoku_Keinen[I_KEINEN_SAISHUNENDO - I_KEINEN_SHONENDO][
                        nenrei - MIN_HIHO_NENREI][seibetu]
