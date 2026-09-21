# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shkejsha.cpp の忠実移植（支給率を掛けて実際の受給者へ）
============================================================================
145 行。`shkejken()` が作った「受給**権**者」の数と年金額に
`siku()` の支給率を掛けて、「受給者」（実際に受け取る人）にする。

    t4[x][xx][i]       受給者数        ＝ t4k × gvr
    hn2[x][xx][i][1,2] うち配偶者の区分 ＝ hn2k × gvr
    t6[x][xx][i][j]    1人あたり年金額  ＝ t6k × gv / gvk / gvkk

`j` によって掛ける率が違う
--------------------------
| `j` | 掛ける率 |
|---|---|
| 6, 14, 21（加給・振替加算） | `gvk` |
| `i == 10` の 17, 19, 20 | `gvkk` |
| それ以外 | `gv`（`flg_toukei == 1` なら `gvr`） |

`set_jikoutou()` の事故等の補正
-------------------------------
厚生年金（`pseid == 0`）は `tmsii[i]` が**加算**（0.0009〜0.0269）で、
2022年度までは丸ごと掛け、2023〜2026年度は5年で線形に落とす。

```c
if(k <= 22)          t6 *= 1.0 + tmsii.AT(i);
else if(k <= 22 + 4) t6 *= 1.0 + tmsii.AT(i) * (22 + 5 - k) / 5.0;
```

`k == 22` は**両方の条件を満たす**が `else if` なので上だけ通る。
`k == 26` で `(27 - 26)/5 = 0.2`、`k == 27` からは補正なし。

共済（`pseid` 1・4・5）は `tmsii[i]` が**倍率**（0.94〜1.53）で、
`i >= 5 && i != 9 && i != 11` のときだけ `t6` と `t6k` の**両方**に
掛ける。`t6k` に掛けるのは他に無い（`t6` だけ掛けるのが普通）ので、
次の `shkejuk()` が `t6k` を読むところに効く。

`key_jikout` と `key_kyosai` は 1 固定
--------------------------------------
```c
int key_jikout = 1;
int key_kyosai = 1;
```

局所変数を 1 で初期化して `if(… && key_jikout == 1)` と見ている。
値を変えるコードは無いので、条件は制度の判定だけになる。
デッドな旗（F9 の仲間）。

宣言だけのものが2つ
-------------------
`tmsii2`（13要素）と、ファイル先頭の
`static void set_jshahosei(v1_t &);` が使われない。後者は
**宣言だけで定義も無い**（呼ばれないのでリンクは通る）。
同じ形のものが `shke.cpp` の `shke_e3x` にもある。
`検証/原本の不具合.md` の F16。

`nos`（裁定遅れ）の掛け方
-------------------------
```c
if(k <= KIJUN + 5 && (60 <= x && x <= 69) && i <= 4) {
  int ss = s;  if(s == 3) ss = 1;
  t4k.AT(x, xx, i) *= nos.AT(k, x, ss, i, 2);
  FOR(j, 1, 23) t6k.AT(x, xx, i, j) *= nos.AT(k, x, ss, i, 1);
}
```

`t4`（受給者数）ではなく **`t4k`（受給権者数）を後から掛け直す**。
`t4` は既に上で作ってあるので、`t4` には裁定遅れが入らず
`t4k` にだけ入る。次の `shkejuk()` が `jj == 1` で `t4k` を読むので
そちらに効く。
"""
import numpy as np

from glva import G
from setconst import KIJUN
from siku import siku

__all__ = ["shkejsha"]


def shkejsha(i, x, xx):
    """shkejsha.cpp:7 の忠実移植。"""
    k = G.k
    s = G.s
    pseid = G.pseid

    gv, gvr, gvk, gvkk = siku(x, i)

    tmsii = _set_jikoutou()

    t4k = G.t4k
    t6k = G.t6k

    G.t4[x, xx, i] = t4k[x, xx, i] * gvr

    G.hn2[x, xx, i, 1] = G.hn2k[x, xx, i, 1] * gvr
    G.hn2[x, xx, i, 2] = G.hn2k[x, xx, i, 2] * gvr

    for j in range(1, 23 + 1):
        if j == 6 or j == 14 or j == 21:
            G.t6[x, xx, i, j] = t6k[x, xx, i, j] * gvk
        elif i == 10 and (j == 17 or j == 19 or j == 20):
            G.t6[x, xx, i, j] = t6k[x, xx, i, j] * gvkk
        else:
            if G.flg_toukei == 1:
                G.t6[x, xx, i, j] = t6k[x, xx, i, j] * gvr
            else:
                G.t6[x, xx, i, j] = t6k[x, xx, i, j] * gv

        if pseid == 0 and ((j <= 12 and j != 6) or j == 23):
            if k <= 22:
                G.t6[x, xx, i, j] *= 1.0 + tmsii[i]
            elif k <= 22 + 4:
                G.t6[x, xx, i, j] *= (1.0 + tmsii[i] * (22 + 5 - k) / 5.0)
        elif pseid == 1 or pseid == 4 or pseid == 5:
            if ((j == 1 or j == 2 or j == 3 or 7 <= j <= 12)
                    and (i >= 5 and i != 9 and i != 11)):
                G.t6[x, xx, i, j] *= tmsii[i]
                t6k[x, xx, i, j] *= tmsii[i]

    # 裁定遅れ。`t4` ではなく `t4k` に掛ける
    if k <= KIJUN + 5 and 60 <= x <= 69 and i <= 4:
        ss = s
        if s == 3:
            ss = 1

        t4k[x, xx, i] *= G.nos[k, x, ss, i, 2]

        for j in range(1, 23 + 1):
            t6k[x, xx, i, j] *= G.nos[k, x, ss, i, 1]

    # 遺族（子のない妻）の割り戻し。掛けるのは `k` 年度、割るのは基準年度
    if (s != 2 and x >= 19 and i == 11
            and 1.0 - G.rc[s, k, x] >= 1.0e-6):
        t6k[x, xx, i, 7] /= 1.0 - G.rc[s, KIJUN, x]
        t6k[x, xx, i, 8] /= 1.0 - G.rc[s, KIJUN, x]


def _set_jikoutou():
    """shkejsha.cpp:82 の `static void set_jikoutou`。

    事故等（`pseid == 0`）または共済の補正率。`flg_hantei != 0` なら
    厚年は 0.0、共済は 1.0 のまま（補正しない）。
    """
    if G.pseid == 0:
        tmsii = np.zeros(14)
    else:
        tmsii = np.ones(14)
    # 添字 0 は原本では触らない（`VEC(double, 13)` の既定 0.0）
    tmsii[0] = 0.0

    key_jikout = 1                  # 1 固定のデッドな旗
    key_kyosai = 1

    if G.flg_hantei != 0:
        return tmsii

    if G.pseid == 0 and key_jikout == 1:
        tmsii[1] = 0.0009
        tmsii[5] = 0.0015
        tmsii[7] = 0.0269
        tmsii[9] = 0.0001
        tmsii[10] = 0.0049
        tmsii[11] = 0.0000
        tmsii[12] = 0.0009
        tmsii[13] = 0.0028
        tmsii[2] = tmsii[1]
        tmsii[3] = tmsii[1]
        tmsii[4] = tmsii[1]
        tmsii[6] = tmsii[5]
        tmsii[8] = tmsii[7]
    elif key_kyosai == 1:
        if G.pseid == 1:
            tmsii[5] = 1.1296
            tmsii[6] = 1.0000
            tmsii[7] = 1.0311
            tmsii[8] = 1.0000
            tmsii[10] = 0.9977
            tmsii[12] = 0.9488
            tmsii[13] = 1.3214
        elif G.pseid == 4:
            tmsii[5] = 1.0517
            tmsii[6] = 1.0000
            tmsii[7] = 1.0022
            tmsii[8] = 1.0000
            tmsii[10] = 1.0118
            tmsii[12] = 1.0155
            tmsii[13] = 1.5290
        elif G.pseid == 5:
            tmsii[5] = 1.0298
            tmsii[6] = 1.0000
            tmsii[7] = 1.0001
            tmsii[8] = 1.0000
            tmsii[10] = 0.9866
            tmsii[12] = 0.9887
            tmsii[13] = 1.5069

    return tmsii
