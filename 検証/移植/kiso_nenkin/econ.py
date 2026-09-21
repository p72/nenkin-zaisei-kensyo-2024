# -*- coding: utf-8 -*-
"""
基礎年金/econ.c の忠実移植（経済前提と改定率・特別調整率）
============================================================
③国民年金が出した改定率（`KOKUKAITE-...csv`）と単年度のカット率上限
（`waku{外枠}-m.csv`）を読み、マクロ経済スライドを効かせる前後の
改定率 `pre_cut` と特別調整率（キャリーオーバー）`T` を作る。

読むファイル3本
---------------
    fp_in[KEIZAI]     econ-{ECON}.csv     物価・賃金・運用利回り
    fp_in[KAITEI]     KOKUKAITE-...csv    年齢別の改定率（③が出す）
    fp_in[TANNEN_CUT] waku{外枠}-m.csv    単年度の調整率（①が出す）

`econ-{ECON}.csv` の列は 0 年度 / 2 運用利回り(実質) / 5 賃金上昇率(実質)
/ 6 物価上昇率。ファイルの最終年度より先は最終年度の値を引き延ばす。

`Kurikoshim`（キャリーオーバー）で2通り
---------------------------------------
    Kurikoshim == 0  持ち越しなし。`pre_cut` は
        `max( 1 , min( 単年度の調整率 , 改定率 ) )` だけ
    Kurikoshim == 1  持ち越しあり。前年の未消化分 `T` を割って使い、
        残った分を `T` に積む。**年齢を1つずつずらして持ち越す**
        （67歳の分は `T[前年][67歳]`、68歳は `T[前年][67歳]`……ではなく
        `T[前年][nenrei-1]`）

2022〜2024年度は実績があるので決め打ち。

    2022  pre_cut = 1        （名目下限で調整なし）、T = 1/0.997
    2023  pre_cut = 1/0.994  、T = 1（持ち越し消化）
    2024  pre_cut = 1/0.996  、T = 1

`D_MACRO == 1`（名目下限撤廃）なら 2025年度以降を上書きする。

`cut_ruiseki` — 累積の調整率
----------------------------
`econ.c:343` の四重ループ。`counter`（調整を始める年度）ごとに
`pre_cut[counter]` で割っていく。年齢の選び方が

```c
if( nenrei <= (int)( min( ( nendo + 67 - counter ) , MAX_JUKYU ) ) )
     ... /= pre_cut[counter][67 - 67] ;
else ... /= pre_cut[counter][nenrei - (int)min( nendo + 67 - counter , MAX_JUKYU )] ;
```

「`counter` 年度に 67 歳だった人が `nendo` 年度に何歳か」を境に、
それより下は 67 歳の改定率、上は歳の差だけずらした改定率を使う。

原本の癖をそのまま残しているところ
----------------------------------
1. **`double round( double , int )` を自前に定義している**（`econ.c:372`）。
   `<cmath>` の `std::round` とは多重定義で共存する。中身は
   `sprintf("%.*f")` → `strtod` なので「10進 n 桁に丸める」。
   `cnum.g_round` に移した。

2. **`econ_read` / `cut_read` がループ変数 `nendo` をループの外で使う。**
   `while` を抜けたあとの `nendo` は最後に読めた行の年度。
   ファイルが空だと未初期化の値を使う（同梱データでは起きない）。

3. **`cut_read` の `nendo` は 2000 を足さない。**`econ_read` と
   `kaitei_read` は `+ 2000` するが、`cut_read` はしない。
   `waku{外枠}-m.csv` が西暦で書いてあるため。

4. **`kakaku_make` の `base_up_avg` が初期化のない自動変数。**
   `ECON_SHONENDO + 5`（2006）から代入するので、2001〜2005 の5つは
   不定値のまま。読むのも 2006 以降なので結果には出ない。

5. **`counter` と `buffer` が使われていない。**`econ()` の
   `double buffer[100]` と `int data_number` はどこからも使われない。

6. **`base_up_avg[2018] = 0.992` の決め打ち。**3年平均の式で出した値を
   捨てて実績値に差し替えている。
"""
import math

import numpy as np

from cnum import Buffer, c_max, c_min, g_round
from glva import G
from setconst import (
    ECON_SHONENDO, KAITEI, KAKAKU_NENDO, KEIZAI, MAX_JUKYU, NENREI_SUM,
    SAISHUNENDO, TANNEN_CUT, UNDER_63, UNDER_67,
)

__all__ = ["econ"]

_NE = SAISHUNENDO - ECON_SHONENDO + 1
_NC = MAX_JUKYU - UNDER_67 + 1


def econ():
    """econ.c:173 の忠実移植。"""
    # 癖 4. 初期化のない自動変数
    max_cut_rate = [0.0] * _NE
    base_up_real = [0.0] * _NE
    interest_rate_real = [0.0] * _NE
    cpi_up = G.cpi_up

    _econ_read(G.fp_in[KEIZAI], cpi_up, base_up_real, interest_rate_real)
    _kaitei_read(G.fp_in[KAITEI], G.kaiteiritu)
    _cut_read(G.fp_in[TANNEN_CUT], max_cut_rate)

    for nendo in range(ECON_SHONENDO, SAISHUNENDO + 1):
        i = nendo - ECON_SHONENDO
        G.base_up[i] = base_up_real[i] * cpi_up[i]
        G.interest_rate[i] = interest_rate_real[i] * cpi_up[i]

    _kakaku_make(G.kakaku, G.base_up_k, base_up_real, cpi_up,
                 G.MARUME_NENDO)

    pre_cut = G.pre_cut
    T = G.T
    kaiteiritu = G.kaiteiritu
    o = UNDER_67 - UNDER_67          # = 0。67歳の置き場

    if G.Kurikoshim == 0:
        for nendo in range(G.C_NENDO + 1, G.KAISHI1):
            pre_cut[nendo - ECON_SHONENDO, 0:_NC] = 1.0

        for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
            i = nendo - ECON_SHONENDO
            if nendo == 2022:
                pre_cut[i, 0:_NC] = 1.0
            elif nendo == 2023:
                pre_cut[i, 0:_NC] = 1 / 0.994
            elif nendo == 2024:
                pre_cut[i, 0:_NC] = 1 / 0.996
            else:
                for nenrei in range(UNDER_67, MAX_JUKYU + 1):
                    pre_cut[i][nenrei - UNDER_67] = c_max(
                        1.0, c_min(max_cut_rate[i],
                                   kaiteiritu[i][nenrei - UNDER_67]))
    elif G.Kurikoshim == 1:
        for nendo in range(G.C_NENDO + 1, G.KAISHI1):
            i = nendo - ECON_SHONENDO
            pre_cut[i, 0:_NC] = 1.0
            T[i, 0:_NC] = 1.0

        for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
            i = nendo - ECON_SHONENDO
            if nendo == 2022:
                pre_cut[i, 0:_NC] = 1.0
                T[i, 0:_NC] = 1 / 0.997
            elif nendo == 2023:
                pre_cut[i, 0:_NC] = 1 / 0.994
                T[i, 0:_NC] = 1.0
            elif nendo == 2024:
                pre_cut[i, 0:_NC] = 1 / 0.996
                T[i, 0:_NC] = 1.0
            else:
                pre_cut[i][o] = c_max(
                    1.0, c_min(max_cut_rate[i] / T[i - 1][o],
                               kaiteiritu[i][o]))

                T[i][o] = T[i - 1][o] / max_cut_rate[i] * pre_cut[i][o]

                for nenrei in range(UNDER_67 + 1, MAX_JUKYU + 1):
                    k = nenrei - UNDER_67
                    pre_cut[i][k] = c_max(
                        1.0, c_min(max_cut_rate[i] / T[i - 1][k - 1],
                                   kaiteiritu[i][k]))

                    T[i][k] = (T[i - 1][k - 1] / max_cut_rate[i]
                               * pre_cut[i][k])

    if G.D_MACRO == 1:
        for nendo in range(G.D_M_NENDO, SAISHUNENDO + 1):
            i = nendo - ECON_SHONENDO
            if nendo == G.D_M_NENDO:
                pre_cut[i][o] = c_max(1.0, max_cut_rate[i] / T[i - 1][o])
            else:
                pre_cut[i][o] = c_max(1.0, max_cut_rate[i])

            for nenrei in range(UNDER_67 + 1, MAX_JUKYU + 1):
                k = nenrei - UNDER_67
                if nendo == G.D_M_NENDO:
                    pre_cut[i][k] = c_max(
                        1.0, max_cut_rate[i] / T[i - 1][k - 1])
                else:
                    pre_cut[i][k] = c_max(1.0, max_cut_rate[i])

    # 累積の調整率。`counter` 年度の調整を全部の（c_nendo, nendo, nenrei）
    # に掛け込む。原本は四重ループだが、c_nendo に依らない割り算なので
    # nenrei の軸をまとめて割る
    # 原本は四重ループだが、割る値は `c_nendo` に依らず、1つの
    # (c_nendo, nendo, nenrei) は `counter` ごとにちょうど1回しか
    # 割られない。`counter` を外側に保ったまま c_nendo と nenrei の軸を
    # まとめて割れば、**割る順番も回数も原本と同じ**（要素ごとの演算なので
    # 1ビットも変わらない）。
    cr = G.cut_ruiseki
    lo = UNDER_63 - NENREI_SUM
    hi = MAX_JUKYU - NENREI_SUM + 1
    nenrei_v = np.arange(UNDER_63, MAX_JUKYU + 1)
    for counter in range(G.C_NENDO + 1, SAISHUNENDO + 1):
        ci = counter - ECON_SHONENDO
        pre = G.pre_cut[ci]
        for nendo in range(counter, SAISHUNENDO + 1):
            ni = nendo - ECON_SHONENDO
            # `counter` 年度に 67 歳だった人の `nendo` 年度の年齢
            kyoukai = int(c_min(float(nendo + 67 - counter), MAX_JUKYU))
            # nenrei <= kyoukai は 67歳の pre_cut、それより上はずらす
            idx = np.where(nenrei_v <= kyoukai, 0, nenrei_v - kyoukai)
            cr[ci:_NE, ni, lo:hi] /= pre[idx]


def _econ_read(fp, cpi_up, base_up_real, interest_rate_real):
    """econ.c:385。物価・賃金・運用利回りを読む。"""
    buffer = Buffer()
    nendo = None
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1:
            break
        nendo = int(buffer[0]) + 2000
        i = nendo - ECON_SHONENDO
        cpi_up[i] = 1.0 + buffer[6] / 100.0
        base_up_real[i] = 1.0 + buffer[5] / 100.0
        interest_rate_real[i] = 1.0 + buffer[2] / 100.0

    # 癖 2. ループの外で nendo を使う
    if nendo is None:
        raise RuntimeError("econ-*.csv が空（原本は未初期化の nendo を使う）")
    last = nendo - ECON_SHONENDO
    for counter in range(nendo + 1, SAISHUNENDO + 1):
        i = counter - ECON_SHONENDO
        cpi_up[i] = cpi_up[last]
        base_up_real[i] = base_up_real[last]
        interest_rate_real[i] = interest_rate_real[last]


def _kaitei_read(fp, kaiteiritu):
    """econ.c:411。③が出した年齢別の改定率を読む。"""
    buffer = Buffer()
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1:
            break
        nendo = int(buffer[0]) + 2000
        i = nendo - ECON_SHONENDO
        for nenrei in range(1, _NC + 1):
            kaiteiritu[i][nenrei - 1] = buffer[nenrei]


def _cut_read(fp, max_cut_rate):
    """econ.c:431。①が出した単年度の調整率を読む。

    癖 3. ここだけ `+ 2000` しない（ファイルが西暦で書いてある）。
    """
    for nendo in range(ECON_SHONENDO, SAISHUNENDO + 1):
        max_cut_rate[nendo - ECON_SHONENDO] = 1.0

    buffer = Buffer()
    nendo = None
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1:
            break
        nendo = int(buffer[0])
        if nendo >= ECON_SHONENDO:
            max_cut_rate[nendo - ECON_SHONENDO] = 1.0 + buffer[1]

    if nendo is None:
        raise RuntimeError("waku*-m.csv が空（原本は未初期化の nendo を使う）")
    for counter in range(nendo + 1, SAISHUNENDO + 1):
        max_cut_rate[counter - ECON_SHONENDO] = \
            max_cut_rate[nendo - ECON_SHONENDO]


def _kakaku_make(kakaku, base_up_k, base_up_real, cpi_up, marume_nendo):
    """econ.c:461。保険料の改定に使う「価格」を作る。"""
    # 癖 4. 初期化のない自動変数（2001〜2005 は不定値のまま）
    base_up_avg = [0.0] * _NE

    for nendo in range(ECON_SHONENDO + 5, SAISHUNENDO + 1):
        i = nendo - ECON_SHONENDO
        base_up_avg[i] = (base_up_real[i - 5] * base_up_real[i - 4]
                          * base_up_real[i - 3])

        base_up_avg[i] = math.pow(base_up_avg[i], 1.0 / 3.0)

        if nendo <= marume_nendo:
            base_up_avg[i] = g_round(base_up_avg[i], 3)

        if nendo == 2018:
            base_up_avg[i] = 0.992          # 癖 6.

    for nendo in range(ECON_SHONENDO + 5, SAISHUNENDO + 1):
        i = nendo - ECON_SHONENDO
        if nendo == 2006 or nendo == 2007:
            base_up_k[i] = cpi_up[i - 2]
        else:
            base_up_k[i] = base_up_avg[i] * cpi_up[i - 2]

            if nendo <= marume_nendo:
                base_up_k[i] = g_round(base_up_k[i], 3)

    for nendo in range(ECON_SHONENDO, SAISHUNENDO + 1):
        i = nendo - ECON_SHONENDO
        if nendo <= KAKAKU_NENDO:
            kakaku[i] = 1.0
        elif nendo == KAKAKU_NENDO + 1:
            kakaku[i] = 1.0
        else:
            kakaku[i] = kakaku[i - 1] * base_up_k[i]

            if nendo <= marume_nendo:
                kakaku[i] = g_round(kakaku[i], 3)
