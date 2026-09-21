# -*- coding: utf-8 -*-
"""
基礎年金/dokuzi_cal.c の忠実移植（外から与えたカット率での独自給付）
======================================================================
`read_cut()` が読んだ `Cut_ritu` を使って、独自給付（死亡一時金・
寡婦年金）の調整後の値と、改定率の調整を作る。`tyousei()` を通らない
経路（調整期間一致・過去債務推計）で `Atamawari_cut()` の代わりに使う。

`Atamawari_cut()` との違い
--------------------------
`Atamawari_cut()` は `cut_ruiseki[c_nendo][nendo][nenrei]`（調整終了年度
ごとの累積率）を掛けるが、こちらは `Cut_ritu[nendo][nenrei]`
（ファイルから読んだ率）を直に掛ける。給付費の側は作らない
（続く `Atamawari()` が `Cut_ritu` を見て作るため）。

改定率の直し方
--------------
```c
kaiteiritu[nendo][nenrei] *= Cut_ritu[nendo][nenrei] / Cut_ritu[nendo-1][nenrei-1] ;
```

「1歳上がった同じ人の累積率の伸び」を改定率に掛け込む。
`nenrei - 1 - UNDER_63` なので 67歳のときは 66歳ぶんを見る。

原本の癖をそのまま残しているところ
----------------------------------
1. **`Ichijikin_Cut_Nendomatu` に調整率を掛けない。**
   `Atamawari_cut()` と同じ（死亡一時金はスライドの対象外）。

2. **`Kafu_Cut_Nendomatu` に掛ける率が 64 歳固定**
   （`Cut_ritu[sotai_nendo][UNDER_64 - UNDER_63]`）。
   `Atamawari_cut()` の 64 歳固定と揃っている。

3. **`nenrei` を宣言するだけで使わない枝がある。**

4. **`SHIHARAIOKURE` の `#define` が関数の中**（`dokuzi_cal.c:143`）。
   `Atamawari.c` `Atamawari_cut.c` `read_file.c` にも同じものがある。

5. **`kaiteiritu` を書き換えたあとに `Kafu_Cut` を作る。**
   `Kafu_Cut` は書き換えた `kaiteiritu` を使う（`Atamawari_cut()` は
   `kaiteiritu_cut` を使う）。片方は `_cut` 付き、もう片方は素の
   `kaiteiritu` で、名前が揃っていない。
"""
import numpy as np

from glva import G
from setconst import (
    ECON_SHONENDO, FUKA, MAX_JUKYU, NOUFU, OLD_MENJO, SAISHUNENDO,
    SHONENDO, SUM, UNDER_63, UNDER_64, UNDER_67,
)

__all__ = ["dokuzi_cal"]

SHIHARAIOKURE = 2
_NY = SAISHUNENDO - SHONENDO + 1


def dokuzi_cal():
    """dokuzi_cal.c:134 の忠実移植。"""
    Ichijikin_Cut_Nendomatu = np.zeros((_NY, 3))
    Kafu_Cut_Nendomatu = np.zeros((_NY, 4))
    sho = SHIHARAIOKURE

    # ---- 癖 1.・2. ----
    Ichijikin_Cut_Nendomatu[:, NOUFU] = G.Ichijikin_Nendomatu[:, NOUFU]
    Ichijikin_Cut_Nendomatu[:, FUKA] = G.Ichijikin_Nendomatu[:, FUKA]

    Kafu_Cut_Nendomatu[:, SUM:OLD_MENJO + 1] = (
        G.Kafu_Nendomatu[:, SUM:OLD_MENJO + 1]
        * G.Cut_ritu[:, UNDER_64 - UNDER_63].reshape(-1, 1))

    # ---- 改定率を直す ----
    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        ei = nendo - ECON_SHONENDO
        sn = nendo - SHONENDO
        for nenrei in range(UNDER_67, MAX_JUKYU + 1):
            G.kaiteiritu[ei][nenrei - UNDER_67] *= (
                G.Cut_ritu[sn][nenrei - UNDER_63]
                / G.Cut_ritu[sn - 1][nenrei - 1 - UNDER_63])

    # ---- 年度末値 → 年度間値（癖 5.） ----
    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        ei = nendo - ECON_SHONENDO

        G.Ichijikin_Cut[sn][NOUFU] = (
            Ichijikin_Cut_Nendomatu[sn - 1][NOUFU] * (sho + 6.) / 12.
            + Ichijikin_Cut_Nendomatu[sn][NOUFU] * (6. - sho) / 12.)

        G.Ichijikin_Cut[sn][FUKA] = (
            Ichijikin_Cut_Nendomatu[sn - 1][FUKA] * (sho + 6.) / 12.
            + Ichijikin_Cut_Nendomatu[sn][FUKA] * (6. - sho) / 12.)

        G.Ichijikin_Cut[sn][SUM] = (G.Ichijikin_Cut[sn][NOUFU]
                                    + G.Ichijikin_Cut[sn][FUKA])

        kt = G.kaiteiritu[ei][UNDER_67 - UNDER_67]
        G.Kafu_Cut[sn, SUM:OLD_MENJO + 1] = (
            Kafu_Cut_Nendomatu[sn - 1, SUM:OLD_MENJO + 1]
            * (sho + kt * 6.) / 12.
            + Kafu_Cut_Nendomatu[sn, SUM:OLD_MENJO + 1] * (6. - sho) / 12.)

    return
