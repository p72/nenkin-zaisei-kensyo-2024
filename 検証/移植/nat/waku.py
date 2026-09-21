# -*- coding: utf-8 -*-
"""
国民年金/waku.c の忠実移植（外枠＝①被保険者推計の結果を読む）
===============================================================
211 行。①被保険者推計が出した被保険者数（外枠）を読み込む。

    Sotowaku[種別][年度][年齢]        第1号・第3号・人口
    Sotowaku_2gou[性別][年度][年齢]   第2号（厚年＋共済3制度の合計）
    Sotowaku_Jurai[種別][年度][年齢]  45年化のときの「従来の」外枠

種別の詰め方 — `( seibetu - 1 ) * 3 + waku_seido + 1`
-----------------------------------------------------
`waku_seido` が 0（人口）/ 1（第1号）/ 2（第3号）、
`seibetu` が 1（男）/ 2（女）。

| `seibetu` | `waku_seido` | 添字 | 中身 |
|---|---|---|---|
| 1 男 | 0 人口 | 1 | 男の人口 |
| 1 男 | 1 第1号 | 2 | `OTOKO_1GOU` |
| 1 男 | 2 第3号 | 3 | `OTOKO_3GOU` |
| 2 女 | 0 人口 | 4 | 女の人口 |
| 2 女 | 1 第1号 | 5 | `ONNA_1GOU` |
| 2 女 | 2 第3号 | 6 | `ONNA_3GOU` |

`setconst.py` の `OTOKO_1GOU = 2` などとちょうど合う。
`seibetu == 0`（男女計）の行は**読むが捨てる**
（`if( seibetu >= 1 )` の外）。

第2号は4制度を足し込む
----------------------
```c
Sotowaku_2gou[seibetu][sotai_nendo][…] += buffer[nenrei];
```

厚年・国共済・地共済・私学共済の4本を**同じ配列に足す**（`+=`）。
第1号・第3号は `=`（上書き）なのに、第2号だけ `+=`。
足す順はファイルの順（厚年 → 国共 → 地共 → 私学）。

列は 4〜89（`buffer[nenrei]`）
-----------------------------
```c
for( nenrei = MIN_WAKU_NENREI - 11 ; nenrei <= MAX_WAKU_NENREI - 11 ; nenrei++ )
  … = buffer[nenrei];
```

`MIN_WAKU_NENREI` = 15、`MAX_WAKU_NENREI` = 100 なので
`nenrei` は **4〜89**。`buffer[0..3]` は見出しの欄
（種別・性別・年度・何か）で、4列目から 15歳のぶんが始まる。
配列側の添字は `nenrei + 11 - MIN_WAKU_NENREI` = 0〜85。

**`for( seibetu = 0 ; shubetu <= 2 ; seibetu++ )` — 変数の書き間違い**
---------------------------------------------------------------------
`waku.c:43`。

```c
for( shubetu = 0 ; shubetu <= MAX_SHUBETU - 1 ; shubetu++ ) { …Sotowaku を 0 に… }

for( seibetu = 0 ; shubetu <= 2 ; seibetu++ )      /* ← seibetu のはず */
{
  … Sotowaku_2gou を 0 にする …
}
```

条件が **`seibetu` ではなく `shubetu`**。上のループを抜けた時点で
`shubetu` は `MAX_SHUBETU` = 7 なので `7 <= 2` は偽。
**ループの中身は1回も走らない。**

`Sotowaku_2gou` はグローバルなので C の規則で 0 から始まる。
`waku()` は `main.c` から1回だけ呼ばれるので、**0 にし直す必要が
無く、結果は変わらない**。

もし `shubetu` がたまたま 2 以下だったら、`shubetu` は
ループの中で変わらないので**無限ループ**になり、`seibetu` が
増え続けて配列の外に書き込む。**書き間違いが偶然その事故を
防いでいる。**

`検証/原本の不具合.md` の新しい項。移植版も**条件を `shubetu` で
書いて残す**。ただし Python の `for` はループを抜けたあとの値が
C と違う（C は 7、Python は最後の 6）ので、C と同じ 7 を入れ直して
から見る。どちらでも 2 以下にならないので結果は同じ。

EOF の見分けが雑
----------------
```c
if( read_data( … ) != EOF && buffer[1] == seibetu && buffer[2] == nendo ) { … }
else { cout << "外枠ファイル読込中にＥＯＦを検出しました" << endl; exit( 1 ); }
```

**性別や年度が合わないときも「ＥＯＦを検出」と出して落ちる。**
`buffer[1]` と `buffer[2]` は `double` なので、`== seibetu`
（`int`）は暗黙変換で比べる。外枠ファイルが期待どおり並んで
いれば通る。

見出しを2行読み捨てる
---------------------
```c
for( counter = 1 ; counter <= 2 ; counter++ ) read_data( buffer , fp , &data_number );
```

各ファイルの先頭2行が見出し。`read_data` は `buffer` を
書き換えるが、次の `read_data` で上書きされるので害は無い。
"""
from setconst import (BUFFER_MAX, MAX_SHUBETU, MAX_WAKU_NENREI,
                      MIN_WAKU_NENREI, SAISHUNENDO, SOTOWAKU_SAISHUNENDO,
                      SOTOWAKU_SHONENDO)
from stdfm import EOF, Buffer, NatError, read_data

__all__ = ["waku"]

# `mfile_open.h` の入力番号
_SOTOWAKU_JINKO = 1
_SOTOWAKU_1GOU = 2
_SOTOWAKU_3GOU = 3
_SOTOWAKU_2GOU_KOU = 4
_SOTOWAKU_2GOU_KOK = 5
_SOTOWAKU_2GOU_REN = 6
_SOTOWAKU_2GOU_SIG = 7
_SOTOWAKU_JINKO_JURAI = 8
_SOTOWAKU_1GOU_JURAI = 9
_SOTOWAKU_3GOU_JURAI = 10


def waku(G):
    """waku.c:13 の忠実移植。"""
    buf = Buffer(BUFFER_MAX)

    Sotowaku = G.Sotowaku
    Sotowaku_2gou = G.Sotowaku_2gou
    Sotowaku_Jurai = G.Sotowaku_Jurai

    shubetu = 0
    for shubetu in range(0, MAX_SHUBETU - 1 + 1):
        for nendo in range(SOTOWAKU_SHONENDO, SAISHUNENDO + 1):
            sotai_nendo = nendo - SOTOWAKU_SHONENDO
            for nenrei in range(MIN_WAKU_NENREI, MAX_WAKU_NENREI + 1):
                Sotowaku[shubetu][sotai_nendo][nenrei - MIN_WAKU_NENREI] = 0.
                Sotowaku_Jurai[shubetu][sotai_nendo][
                    nenrei - MIN_WAKU_NENREI] = 0.
    # C の `for` はループを抜けた時点で上限＋1 になる。下の条件で使う
    shubetu = MAX_SHUBETU

    # 原本は条件が `seibetu <= 2` ではなく **`shubetu <= 2`**。
    # `shubetu` は 7 なので中身は1回も走らない（そのまま写す）
    seibetu = 0
    while shubetu <= 2:
        for nendo in range(SOTOWAKU_SHONENDO, SAISHUNENDO + 1):
            sotai_nendo = nendo - SOTOWAKU_SHONENDO
            for nenrei in range(MIN_WAKU_NENREI, MAX_WAKU_NENREI + 1):
                Sotowaku_2gou[seibetu][sotai_nendo][
                    nenrei - MIN_WAKU_NENREI] = 0.
        seibetu += 1

    for waku_seido in range(0, 2 + 1):
        if waku_seido == 0:
            fp = G.fp_in[_SOTOWAKU_JINKO]
        elif waku_seido == 1:
            fp = G.fp_in[_SOTOWAKU_1GOU]
        elif waku_seido == 2:
            fp = G.fp_in[_SOTOWAKU_3GOU]

        for _counter in range(1, 2 + 1):
            read_data(buf, fp)          # 見出しを2行捨てる

        for seibetu in range(0, 2 + 1):
            for nendo in range(SOTOWAKU_SHONENDO,
                               SOTOWAKU_SAISHUNENDO + 1):
                sotai_nendo = nendo - SOTOWAKU_SHONENDO

                if (read_data(buf, fp) != EOF
                        and buf.num[1] == seibetu
                        and buf.num[2] == nendo):
                    if seibetu >= 1:
                        for nenrei in range(MIN_WAKU_NENREI - 11,
                                            MAX_WAKU_NENREI - 11 + 1):
                            Sotowaku[(seibetu - 1) * 3 + waku_seido + 1][
                                sotai_nendo][
                                    nenrei + 11 - MIN_WAKU_NENREI] = \
                                buf.num[nenrei]
                else:
                    # 原本は性別・年度が合わないときも同じ文言で落ちる
                    raise NatError("外枠ファイル読込中にＥＯＦを検出しました")

    for waku_seido_2gou in range(1, 4 + 1):
        if waku_seido_2gou == 1:
            fp = G.fp_in[_SOTOWAKU_2GOU_KOU]
        elif waku_seido_2gou == 2:
            fp = G.fp_in[_SOTOWAKU_2GOU_KOK]
        elif waku_seido_2gou == 3:
            fp = G.fp_in[_SOTOWAKU_2GOU_REN]
        elif waku_seido_2gou == 4:
            fp = G.fp_in[_SOTOWAKU_2GOU_SIG]

        for _counter in range(1, 2 + 1):
            read_data(buf, fp)

        for seibetu in range(0, 2 + 1):
            for nendo in range(SOTOWAKU_SHONENDO,
                               SOTOWAKU_SAISHUNENDO + 1):
                sotai_nendo = nendo - SOTOWAKU_SHONENDO

                if (read_data(buf, fp) != EOF
                        and buf.num[1] == seibetu
                        and buf.num[2] == nendo):
                    if seibetu >= 1:
                        for nenrei in range(MIN_WAKU_NENREI - 11,
                                            MAX_WAKU_NENREI - 11 + 1):
                            # 第2号だけ `+=`（4制度を足し込む）
                            Sotowaku_2gou[seibetu][sotai_nendo][
                                nenrei + 11 - MIN_WAKU_NENREI] += \
                                buf.num[nenrei]
                else:
                    raise NatError("外枠ファイル読込中にＥＯＦを検出しました")

    if G.Option == 1:
        for waku_seido in range(0, 2 + 1):
            if waku_seido == 0:
                fp = G.fp_in[_SOTOWAKU_JINKO_JURAI]
            elif waku_seido == 1:
                fp = G.fp_in[_SOTOWAKU_1GOU_JURAI]
            elif waku_seido == 2:
                fp = G.fp_in[_SOTOWAKU_3GOU_JURAI]

            for _counter in range(1, 2 + 1):
                read_data(buf, fp)

            for seibetu in range(0, 2 + 1):
                for nendo in range(SOTOWAKU_SHONENDO,
                                   SOTOWAKU_SAISHUNENDO + 1):
                    sotai_nendo = nendo - SOTOWAKU_SHONENDO

                    if (read_data(buf, fp) != EOF
                            and buf.num[1] == seibetu
                            and buf.num[2] == nendo):
                        if seibetu >= 1:
                            for nenrei in range(MIN_WAKU_NENREI - 11,
                                                MAX_WAKU_NENREI - 11 + 1):
                                Sotowaku_Jurai[
                                    (seibetu - 1) * 3 + waku_seido + 1][
                                        sotai_nendo][
                                            nenrei + 11 - MIN_WAKU_NENREI] = \
                                    buf.num[nenrei]
                    else:
                        raise NatError(
                            "外枠ファイル読込中にＥＯＦを検出しました")
