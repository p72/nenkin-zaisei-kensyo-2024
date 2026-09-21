# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/sknr.cpp の忠実移植（支給開始年齢）
========================================================
62 行。生年度（`k - x`。`k` は西暦−2000、`x` は年齢）から

    xxr   特別支給の老齢厚生年金の**定額部分**の支給開始年齢
    xrb   同じく**報酬比例部分**の支給開始年齢

を返す。段階的な引上げ（2年で1歳）をそのまま `if` の並びで書いている。

原本は `int &xxr, int &xrb` の参照引数で、呼び出し側は**グローバルの
`xxr` `xrb`** を渡す。つまり戻り値ではなくグローバルが書き換わる。
移植版も `G.xxr` `G.xrb` に入れる（原本と同じ副作用にする）。

`if` を重ねて上書きしていく書き方
---------------------------------
```c
xxr = 60;
if(k - x >= -59) xxr = 61;
if(k - x >= -57) xxr = 62;
...
```

`else if` ではないので、条件を満たすぶんだけ順に上書きされ、
**いちばん最後に満たした条件の値**が残る。男の定額部分を区間に直すと

    生年度 ≦ 1940  → 60
    1941〜1942     → 61
    1943〜1944     → 62
    1945〜1946     → 63
    1947〜1948     → 64
    1949 以降      → 65

で、法定の「昭和16年4月2日〜昭和18年4月1日生まれは61歳」と合う。
移植版も同じ `if` の並びで書く（区間に書き直すと読み替えの誤りが
入りやすい）。

男（`s2 == 1`）と共済（`konen != 1`）は同じ表、女（`s2 == 2`）は
5年遅い表、`s2 == 3`（男女計）は**さらに別の表**で `xrb = xxr`。

最後の検査
----------
```c
if(xrb > xxr || xxr > 65 || xrb > 65 || xrb < 55) throw std::logic_error(...)
```

報酬比例の方が定額より遅い、65歳を超える、55歳を下回る、のいずれかなら
落ちる。移植版も同じ条件で例外にする。
"""
import sys

from glva import G
from sepsstd import fmt

__all__ = ["sknr"]


def sknr(k, x):
    """sknr.cpp:6 の忠実移植。`G.xxr` と `G.xrb` に入れる。"""
    d = k - x                            # 生年度 − 2000

    # ---- 定額部分 ----
    G.xxr = 60

    if G.s2 == 1 or G.konen != 1:
        if d >= -59:
            G.xxr = 61
        if d >= -57:
            G.xxr = 62
        if d >= -55:
            G.xxr = 63
        if d >= -53:
            G.xxr = 64
        if d >= -51:
            G.xxr = 65
    elif G.s2 == 2:
        if d <= -61:
            G.xxr = 59
        if d >= -54:
            G.xxr = 61
        if d >= -52:
            G.xxr = 62
        if d >= -50:
            G.xxr = 63
        if d >= -48:
            G.xxr = 64
        if d >= -46:
            G.xxr = 65
    else:
        # s2 == 3（男女計）。下げる側の条件が4つ余分にある
        if d <= -47:
            G.xxr = 59
        if d <= -49:
            G.xxr = 58
        if d <= -51:
            G.xxr = 57
        if d <= -53:
            G.xxr = 56
        if d <= -55:
            G.xxr = 55
        if d >= -42:
            G.xxr = 61
        if d >= -40:
            G.xxr = 62
        if d >= -38:
            G.xxr = 63
        if d >= -36:
            G.xxr = 64
        if d >= -34:
            G.xxr = 65

    # ---- 報酬比例部分 ----
    G.xrb = 60

    if G.s2 == 1 or G.konen != 1:
        if d >= -47:
            G.xrb = 61
        if d >= -45:
            G.xrb = 62
        if d >= -43:
            G.xrb = 63
        if d >= -41:
            G.xrb = 64
        if d >= -39:
            G.xrb = 65
    elif G.s2 == 2:
        if d <= -61:
            G.xrb = 59
        if d >= -42:
            G.xrb = 61
        if d >= -40:
            G.xrb = 62
        if d >= -38:
            G.xrb = 63
        if d >= -36:
            G.xrb = 64
        if d >= -34:
            G.xrb = 65
    else:
        G.xrb = G.xxr

    if G.xrb > G.xxr or G.xxr > 65 or G.xrb > 65 or G.xrb < 55:
        sys.stderr.write(fmt(
            "支給開始年齢エラー: s = %d, k = %d, x = %d, xrb = %d, xxr = %d\n",
            G.s, k, x, G.xrb, G.xxr))
        raise ValueError("xrb, xxr")
