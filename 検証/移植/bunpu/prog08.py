# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog08.cpp の忠実移植
=========================================
`func07a` / `func07b` で遷移先が決まらなかった人に、**加入年数別の**
遷移確率で遷移先を割り当てる。`main.cpp:189` で `func07b` の直後に呼ばれる。

`func07` との違い
-----------------
`func07` の遷移確率は「状態 → 状態」の表だが、`func08a` は
**「状態 × 加入年数 → 状態」**の表を使う。加入年数は状態ごとに別の
フィールドに入っているので、状態コードで見る先が変わる。

    状態コード   加入月数を持つフィールド
    11〜20       var011 〜 var020（順に対応）
    31, 33       var028 - var029
    32, 34       var029
    40           var030
    50           var031
    60           var032
    70           var021

これを 12 で割った値（＝年数）が表の第2添字になる。
原本は18通りの `else if` を全部書き下している（`prog08.cpp:62-100` と
`prog08.cpp:108-344`）。移植では**同じ対応を表にした**。分岐の条件が
「`var007` がその値か」だけで互いに排他なので、`else if` の連鎖と
表引きは同じ結果になる。

入力表の形（`arg08a5`）
-----------------------
行が `m*16 + j`、列が `k`。`m` は加入年数（0〜49）、`j` は状態（16行）。
列のずらし（12, 13 を飛ばす）は `func07` と同じ。

    j < 12       → 表の m*16+j 行
    j == 12, 13  → 一律 0.0
    j >= 14      → 表の m*16+(j-2) 行

原本の癖をそのまま残しているところ
----------------------------------
1. **`arg08a8 >= 1` の枝と `else` の枝が完全に同じ**（`prog08.cpp:8-60`）
   53行が1文字違わず2回書かれている。`arg08a8`（`object01b.value001`）で
   分けるつもりだったが中身が同じなので、**この分岐は結果に効かない**。
   移植では1本にまとめ、ここに記録しておく。
   （`検証/原本の不具合.md`）

2. **人数を数えるときは `< 600` を見るのに、割り当てるときは見ない**
   数える側（`prog08.cpp:63` など）は `var011 < 600` を確かめてから
   `var011/12`（＝0〜49）を添字にする。割り当てる側（`prog08.cpp:111`）は
   **確かめずに** `var011/12` を添字にする。第2添字の寸法は 100 なので
   1200か月（100年）まではあふれないが、`m` のループが 0〜49 しか埋めて
   いないので、50年以上の人は**必ず 0 のまま**＝遷移しない。
   年度ループは最長48年（`main.cpp:39,104`）なので実データでは届かない。

3. **`var035` を見ない**
   `func07a`/`func07b` は `var035` で分けるが、`func08a` は見ない。
   `var037 != 1`（まだ遷移先が決まっていない）だけが条件。

4. **`k` のループは `size()-1`（19）まで**
   `vector001` の最後（99）は遷移先にならない。`vector08a2` の第3添字の
   寸法は 20 なので、20列目は作るだけで使わない。
"""
from libc import c_idiv, c_round
from cppnum import stod, stoi
from prog09 import func09a

__all__ = ["func08a"]

# prog08.cpp の18通りの else if で見ているフィールド。
#   状態コード → (足し合わせるフィールド, 引くフィールド or None)
# 31/33 は var028 - var029、それ以外は1つのフィールドそのまま。
_DUR08A = {
    11: ("var011", None), 12: ("var012", None), 13: ("var013", None),
    14: ("var014", None), 15: ("var015", None), 16: ("var016", None),
    17: ("var017", None), 18: ("var018", None), 19: ("var019", None),
    20: ("var020", None),
    31: ("var028", "var029"), 33: ("var028", "var029"),
    32: ("var029", None), 34: ("var029", None),
    40: ("var030", None), 50: ("var031", None), 60: ("var032", None),
    70: ("var021", None),
}


def _dur08a(o, code):
    """状態コードに対応する加入月数。表に無い状態なら None。"""
    ent = _DUR08A.get(code)
    if ent is None:
        return None
    a, b = ent
    v = getattr(o, a)
    if b is not None:
        v -= getattr(o, b)
    return v


def func08a(arg08a1, arg08a2, arg08a3, arg08a4, arg08a5, arg08a6, arg08a7,
            arg08a8):
    """prog08.cpp:5 の忠実移植。

    arg08a1  人数（main_var002）
    arg08a2  状態コードの一覧（vector001、20個）
    arg08a3  個人のリスト（書き換える）
    arg08a4  上限の表（vector026、文字列）
    arg08a5  加入年数別の遷移確率（vector034、文字列）
    arg08a6  使った数（vector030、書き換える）
    arg08a7  残りの数（vector029、書き換える）
    arg08a8  object01b.value001。**結果に効かない**（上の癖 1.）
    """
    n = len(arg08a2)              # 20
    nj = n - 2                    # 18。状態の行数
    nyear = 100                   # 第2添字の寸法。埋めるのは 0〜49 だけ

    # [18][100][20] の遷移確率。prog08.cpp:6
    v1 = [[[0.0] * n for _ in range(nyear)] for _ in range(nj)]
    # [18][100][20] の枠
    v2 = [[[0] * n for _ in range(nyear)] for _ in range(nj)]

    # prog08.cpp:8-60。2つの枝の中身が同じなので1本にまとめた（癖 1.）
    for j in range(nj):
        if j == 12 or j == 13:
            continue          # 一律 0.0。作ったときのまま
        jr = j if j < 12 else j - 2
        for m in range(50):
            row = arg08a5[m * 16 + jr]
            dst = v1[j]
            for k in range(n):
                if k < 12:
                    dst[m][k] = stod(row[k])
                elif k == 12 or k == 13:
                    dst[m][k] = 0.0
                else:
                    dst[m][k] = stod(row[k - 2])

    # 状態×加入年数ごとの人数を数える。prog08.cpp:61-100。
    # 原本は else if の連鎖で、j は arg08a2[j]（＝func09a の逆）と一致する
    v3 = [[0] * nyear for _ in range(nj)]
    for i in range(arg08a1):
        o = arg08a3[i]
        code = o.var007
        for j in range(nj):
            if code != arg08a2[j]:
                continue
            d = _dur08a(o, code)
            if d is not None and d < 600:
                v3[j][c_idiv(d, 12)] += 1
            break

    # 人数×確率を丸めて枠にする。prog08.cpp:101-107
    for j in range(nj):
        for m in range(50):
            cnt = float(v3[j][m])
            row1 = v1[j][m]
            row2 = v2[j][m]
            for k in range(n):
                row2[k] = int(c_round(cnt * row1[k]))

    # 枠の残っている遷移先を割り当てる。prog08.cpp:108-344。
    # k は size()-1（19）まで（癖 4.）
    for i in range(arg08a1):
        o = arg08a3[i]
        if o.var037 == 1:
            continue
        d = _dur08a(o, o.var007)
        if d is None:
            continue              # 80, 90, 99 はどの else if にも入らない
        r = func09a(o.var007)
        y = c_idiv(d, 12)         # **< 600 を確かめない**（癖 2.）
        for k in range(n - 1):
            if v2[r][y][k] > 0:
                if arg08a6[r][k] < stoi(arg08a4[r][k]):
                    o.var008 = arg08a2[k]
                    arg08a6[r][k] += 1
                    arg08a7[r][k] -= 1
                    o.var037 = 1
                    v2[r][y][k] -= 1
                    break
