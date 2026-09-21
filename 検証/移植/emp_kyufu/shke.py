# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shke.cpp の忠実移植（1年度ぶんの集計をまとめる）
=====================================================================
74 行。`sepsd.cpp` から**年度ごとに**呼ばれる集計の入口。

    shkehiho()                  被保険者を集計
    shkejken(i, x, xx) × 8,395  受給権者の年金額を作る
    shke_sigonen()              基礎45年化のとき年金額を読み替える
    shkejsha(i, x, xx) × 8,395  支給率を掛けて受給者にする
    shkejuk (i, x, xx) × 8,395  給付費の表 d3 / d3x / d3xs に足す
    shkekiso()                  基礎年金へ渡す数を集計

呼び出し回数は `FOR(i, 1, 13) FOR(xx, 0, 15)` のうち
`i >= 5 && xx != 0` を飛ばすので 4×16 + 9 = 73 通り × `FOR(x, 0, 114)`
の 115 で **8,395 回**。`sepsd.cpp` は `k = KIJUN` で1回、
そのあと `k = KIJUN+1 〜 KE` の 104 年度で 1 回ずつ `shke()` を呼ぶので、
種別ごとに 105 回、合計 315 回。**`shkejken` 〜 `shkejuk` は
のべ 264 万回呼ばれる**。

`shke_e3x` が宣言だけで定義が無い
---------------------------------
```c
static void shke_sigonen(void);
static void shke_e3x(void);          /* 定義も呼び出しも無い */
```

`static` 関数の宣言だけがあって定義が無い。呼ばれないのでリンクは
通る（gcc は `-Wunused-function` でも警告しない）。
`shkejsha.cpp` の `set_jshahosei` も同じ。
`検証/原本の不具合.md` の F16。

`shke_sigonen()` — 基礎45年化のときの読み替え
---------------------------------------------
`flg_sigo == 1` のときだけ走る。障害（`i == 9`）と遺族（`i == 11`）の
基礎年金相当分に「加入可能年数 ÷ 40」を掛ける。`j == 12`
（経過的な差額）だけ**2乗**する。

```c
if(j != 12){
    t6k.AT(x, 0, i, j) *= kflcan.AT(k, C19(max(k-x,-74)))/40.0;
}else if(j == 12){
    t6k.AT(x, 0, i, j) *= pow(kflcan.AT(k, C19(max(k-x,-74)))/40.0, 2.0);
}
```

`xx` は 0 だけ（繰上げ繰下げのあるものは読み替えない）。
`j` は 2・7・11・12・14 だけ。
"""
import math

from glva import G
from sepsstd import subc
from setconst import C19
from shkehiho import shkehiho
from shkejken import shkejken
from shkejsha import shkejsha
from shkejuk import shkejuk
from shkekiso import shkekiso

__all__ = ["shke"]


def shke():
    """shke.cpp:8 の忠実移植。"""
    subc(G.t4, 0, 115, 0, 15, 0, 13)
    subc(G.t4k, 0, 115, 0, 15, 0, 13)
    subc(G.hn2, 0, 115, 0, 15, 0, 13, 1, 2)
    subc(G.hn2k, 0, 115, 0, 15, 0, 13, 1, 2)
    subc(G.t6, 0, 115, 0, 15, 0, 13, 0, 23)
    subc(G.t6k, 0, 115, 0, 15, 0, 13, 0, 23)

    shkehiho()

    for i in range(1, 13 + 1):
        for xx in range(0, 15 + 1):
            if i >= 5 and xx != 0:
                continue
            for x in range(0, 114 + 1):
                shkejken(i, x, xx)

    if G.flg_sigo == 1:
        _shke_sigonen()

    for i in range(1, 13 + 1):
        for xx in range(0, 15 + 1):
            if i >= 5 and xx != 0:
                continue
            for x in range(0, 114 + 1):
                shkejsha(i, x, xx)

    for i in range(1, 13 + 1):
        for xx in range(0, 15 + 1):
            if i >= 5 and xx != 0:
                continue
            for x in range(0, 114 + 1):
                shkejuk(i, x, xx)

    if 11 <= G.key <= 13:
        shkekiso()


def _shke_sigonen():
    """shke.cpp:55 の `static void shke_sigonen`。基礎45年化の読み替え。"""
    k = G.k
    for i in range(9, 13 + 1):
        if i != 9 and i != 11:
            continue

        for j in range(2, 23 + 1):
            if j == 2 or j == 7 or j == 11 or j == 12 or j == 14:
                for x in range(0, 114 + 1):
                    r = G.kflcan[k, C19(max(k - x, -74))] / 40.0
                    if j != 12:
                        G.t6k[x, 0, i, j] *= r
                    elif j == 12:
                        G.t6k[x, 0, i, j] *= math.pow(r, 2.0)
