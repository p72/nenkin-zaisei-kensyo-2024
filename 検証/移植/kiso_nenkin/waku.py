# -*- coding: utf-8 -*-
"""
基礎年金/waku.c の忠実移植（①被保険者推計の外枠を読む）
=========================================================
①が出した `waku{外枠}-11.csv`（1号）、`-03/-08/-09/-10`（2号）、
`-15/-16/-17/-18`（3号）の9本を読んで、拠出金の算定対象者数を作る。

`fp_in` の割り当て（`mfile_open.h`）
------------------------------------
    12 KOKUNEN_1GOU   waku-11  国年1号被保険者
    13 KOUNEN_2GOU    waku-03  厚年2号
    14 KOKKYOU_2GOU   waku-08  国共2号
    15 CHIKYOU_2GOU   waku-09  地共2号
    16 SHIGAKU_2GOU   waku-10  私学2号
    17 KOUNEN_3GOU    waku-15  厚年3号
    18 KOKKYOU_3GOU   waku-16  国共3号
    19 CHIKYOU_3GOU   waku-17  地共3号
    20 SHIGAKU_3GOU   waku-18  私学3号

`waku*.csv` は「2行の見出し → 性別（計・男・女）ごとに年度順」の並び。
列は `分類,性別,年度,15歳,16歳,…,120歳`。`buffer[3]` が15歳なので
`nenrei` 歳の列は `buffer[nenrei - 11]`（`fout.c` の並びと合う）。

2号・3号は20〜59歳を足す（`MIN_HIHO_NENREI - 11` から `59 - 11`）。
基礎45年化（`Option == 1`）なら上限を `encho_year( nendo )` だけ伸ばす。

年度間値への直し方
------------------
読んだあとで**年度末値2つの平均**にする。

```c
for( nendo = SAISHUNENDO ; nendo >= SHONENDO + 1 ; nendo-- )
    X[nendo] = ( X[nendo-1] + X[nendo] ) / 2. ;
```

年度を**降順**に回すので、`X[nendo-1]` はまだ年度末値のまま。
昇順だと平均の平均になってしまう。

原本の癖をそのまま残しているところ
----------------------------------
1. **1号だけ `buffer[3]`（15歳の列）を足している**（`waku.c:51`）。
   2号・3号は20〜59歳の合計だが、1号は15歳の列だけ。
   `waku{外枠}-11.csv` の「分類11」は年齢別ではなく総数を15歳の列に
   入れて出しているため（`fout.c` の分類11の作り）。

2. **`SanteiTaishou` の添字が制度番号と2つずれる。**
   2号は `waku_seido - SOTOWAKU_START + 1`（13→2、16→5）、
   3号は `waku_seido - SOTOWAKU_START - 3`（17→2、20→5）。
   同じ制度の2号と3号が `[2]` と `[3]` に入る。

3. **`Option == 0` と `Option == 1` の枝が、上限以外まったく同じ。**
   66行がほぼ丸ごと重複している。（`検証/原本の不具合.md`）

4. **`nendo >= SHONENDO` の判定が常に真。**`nendo` は
   `SOTOWAKU_SHONENDO`（2021）から回るので 2020 以上。

5. **平均のあと `SanteiTaishou[seido][0][2]` と `[3]` を 0 にするが
   `[1]` は消さない。**1号（`[1]`）は `ReadKokunen_jisseki` が入れた
   実績値をそのまま残す。

6. **`counter` / `counter2` / `seido` / `nenrei` を宣言しているが
   `counter2` はどこでも使わない。**

7. **見出しが合わなくても EOF と同じ扱いで `exit(1)`。**
   `if( read_data(...) != EOF && buffer[1] == seibetu && buffer[2] == nendo )`
   の `else` が「ＥＯＦを検出しました」と出す。
"""
import sys

from cnum import Buffer
from glva import G
from setconst import (
    KOKUNEN, KOKUNEN_1GOU, KOUNEN, MIN_HIHO_NENREI, ONNA, OTOKO,
    SAISHUNENDO, SHIGAKU, SHIGAKU_2GOU, SHIGAKU_3GOU, SHONENDO,
    SOTOWAKU_SAISHUNENDO, SOTOWAKU_SHONENDO, SOTOWAKU_START, SUM,
    MAX_KYOSHUTU_NENREI, OP_MAX_KYOSHUTU_NENREI,
)

__all__ = ["waku", "encho_year"]


def encho_year(nendo):
    """waku.c:155。基礎45年化で拠出年齢の上限を何歳伸ばすか。

    `Option == 1` のとき `OPTION_START` から `OP_HIKIAGE_KANKAKU` 年
    おきに1歳ずつ、`OP_MAX_KYOSHUTU_NENREI - MAX_KYOSHUTU_NENREI`
    （65 − 60 = 5）歳まで伸ばす。`Option == 0` なら 0。
    """
    r = 0
    max_hikiage_nensu = OP_MAX_KYOSHUTU_NENREI - MAX_KYOSHUTU_NENREI

    if G.Option == 1:
        while nendo >= G.OPTION_START + r * G.OP_HIKIAGE_KANKAKU:
            r += 1
            if r >= max_hikiage_nensu:
                break

    return r


def waku():
    """waku.c:17 の忠実移植。"""
    buffer = Buffer()
    St = G.SanteiTaishou

    for waku_seido in range(SOTOWAKU_START, SHIGAKU_3GOU + 1):
        fp = G.fp_in[waku_seido]

        # 見出し2行を読み捨てる
        for _counter in range(1, 3):
            fp.read_data(buffer)

        for seibetu in range(SUM, ONNA + 1):
            for nendo in range(SOTOWAKU_SHONENDO, SOTOWAKU_SAISHUNENDO + 1):
                rc, _ = fp.read_data(buffer)
                if not (rc != -1 and buffer[1] == seibetu
                        and buffer[2] == nendo):
                    # 癖 7.
                    print("外枠ファイル読込中にＥＯＦを検出しました。"
                          "枠制度番号は %d" % waku_seido)
                    sys.exit(1)

                if not (seibetu >= OTOKO and nendo >= SHONENDO):
                    continue

                # 癖 3. Option の枝は上限だけが違う
                if G.Option == 0:
                    ue = 59 - 11
                elif G.Option == 1:
                    ue = 59 - 11 + encho_year(nendo)
                else:
                    continue

                if waku_seido == KOKUNEN_1GOU:
                    # 癖 1. 1号は15歳の列（総数）だけ
                    G.Hiho_Kokunen[nendo - SHONENDO] += buffer[3]
                elif waku_seido <= SHIGAKU_2GOU:
                    k = waku_seido - SOTOWAKU_START + 1     # 癖 2.
                    for nenrei in range(MIN_HIHO_NENREI - 11, ue + 1):
                        St[k][nendo - SHONENDO][2] += buffer[nenrei]
                else:
                    k = waku_seido - SOTOWAKU_START - 3     # 癖 2.
                    for nenrei in range(MIN_HIHO_NENREI - 11, ue + 1):
                        St[k][nendo - SHONENDO][3] += buffer[nenrei]

    # 年度末値 → 年度間値（降順に回すのが要）
    for nendo in range(SAISHUNENDO, SHONENDO, -1):
        sn = nendo - SHONENDO

        G.Hiho_Kokunen[sn] = (G.Hiho_Kokunen[sn - 1] + G.Hiho_Kokunen[sn]) / 2.

        for seido in range(KOUNEN, SHIGAKU + 1):
            for goubetu in range(1, 4):
                St[seido][sn][goubetu] = (St[seido][sn - 1][goubetu]
                                          + St[seido][sn][goubetu]) / 2.

    # 癖 5. 2020年度の2号・3号を 0 に（1号は消さない）
    for seido in range(KOKUNEN, SHIGAKU + 1):
        for goubetu in range(2, 4):
            St[seido][SHONENDO - SHONENDO][goubetu] = 0.
    G.Hiho_Kokunen[SHONENDO - SHONENDO] = 0.

    # 号別計 → 制度計
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        for seido in range(KOKUNEN, SHIGAKU + 1):
            for goubetu in range(1, 4):
                St[seido][sn][SUM] += St[seido][sn][goubetu]

        for seido in range(KOKUNEN, SHIGAKU + 1):
            for goubetu in range(SUM, 4):
                St[SUM][sn][goubetu] += St[seido][sn][goubetu]

    # 原本は `fclose( fp_in[seido] )` を main.c でまとめてやる
    return
