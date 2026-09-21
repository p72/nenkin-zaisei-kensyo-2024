# -*- coding: utf-8 -*-
"""
基礎年金/read_cut.c の忠実移植（既に決まったカット率を読む）
=============================================================
`tyousei()` で解く代わりに、**外から与えたカット率を使う**ときの入口。
2通りの経路から呼ばれる。

    CUT_KOTEI == 1   調整期間一致。⑤収支計算が出した統一カット率
                     （`fp_in[CUT]` = `cuta-{Version}-1120-{YOBI}.csv`）
    kako >= 1        過去債務推計。前に④が出したカット率
                     （`fp_in[CUT_K]` = `cuta-{Version_Jurai}-{Version_cut}.csv`）

`R_S_C_NENDO`（2120）より先の伸ばし方
--------------------------------------
```c
if( nenrei <= UNDER_67 ) Cut_ritu[n][nenrei] = Cut_ritu[n-1][nenrei] ;
else                     Cut_ritu[n][nenrei] = Cut_ritu[n-1][nenrei-1] ;
```

67歳までは前年度と同じ、68歳以上は**前年度の1歳下**を引き継ぐ。
同じ人が1年歳を取っても同じ率が付いていくようにする。

原本の癖をそのまま残しているところ
----------------------------------
1. **`fclose( fp_in[CUT] )` と `fclose( fp_in[CUT_K] )` を無条件に
   両方呼ぶ。**呼ばれるのはどちらか一方の経路だけなので、開いていない
   側は `NULL` のまま。glibc の `fclose(NULL)` は即 SEGV なので、
   移植パッチで `NULL` を避けるようにしてある
   （`検証/実行/patches/glibc-portability.patch`）。
   `CUT_KOTEI == 1` で初めて通る経路。

2. **`while` の続行条件に `buffer[0] > previous_buffer` が入る。**
   `read_file.c` と同じ作り。

3. **`counter` の伸ばしループが `R_S_C_NENDO + 1` から。**
   ファイルに 2121年度以降が書いてあっても上書きされる。

4. **`Cut_ritu[...][nenrei - 1 - UNDER_63]` が `nenrei = UNDER_67 + 1`
   （68歳）のとき添字 4。**67歳ぶんを引き継ぐので正しい。
"""
from cnum import Buffer
from glva import G
from setconst import (
    CUT, CUT_K, MAX_JUKYU, R_S_C_NENDO, SAISHUNENDO, SHONENDO, UNDER_63,
    UNDER_67,
)

__all__ = ["read_cut"]


def read_cut():
    """read_cut.c:9 の忠実移植。"""
    buffer = Buffer()
    previous_buffer = -1000.

    cutfile = CUT
    if G.kako >= 1:
        cutfile = CUT_K

    fp = G.fp_in[cutfile]
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1 or not buffer[0] > previous_buffer:
            break
        nendo = int(buffer[0]) + 2000
        if SHONENDO <= nendo <= SAISHUNENDO:
            for nenrei in range(1, MAX_JUKYU - UNDER_63 + 2):
                G.Cut_ritu[nendo - SHONENDO][nenrei - 1] = buffer[nenrei]
        previous_buffer = buffer[0]

    for counter in range(R_S_C_NENDO + 1, SAISHUNENDO + 1):
        sn = counter - SHONENDO
        for nenrei in range(UNDER_63, MAX_JUKYU + 1):
            if nenrei <= UNDER_67:
                G.Cut_ritu[sn][nenrei - UNDER_63] = \
                    G.Cut_ritu[sn - 1][nenrei - UNDER_63]
            else:
                G.Cut_ritu[sn][nenrei - UNDER_63] = \
                    G.Cut_ritu[sn - 1][nenrei - 1 - UNDER_63]

    # 癖 1. 開いていない側は閉じない
    G.fp_in[CUT] = None
    G.fp_in[CUT_K] = None

    return
