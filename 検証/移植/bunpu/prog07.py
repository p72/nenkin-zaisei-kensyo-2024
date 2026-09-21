# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog07.cpp の忠実移植
=========================================
年度ごとに、**個人を状態から状態へ遷移させる**ところ。⑥の中核の1つ。

やっていること（読み解いた範囲）
--------------------------------
どちらの関数も3段構えになっている。

1. **遷移確率の表を組む**（`vector07a1` / `vector07b1`）
   形は `[2][19][20]`（`func07b` は `[2][19][19]`）。第1添字の 2 は
   `var035` の区分（0 側が `var035 ∈ {1,2}`、1 側が `var035 == 3`）で、
   入力表 `arg07a6` の**上半分と下半分**に対応する（行に `17*m` を足す）。

2. **状態ごとの人数を数え、確率を掛けて「枠」にする**
   `round(人数 × 確率)` を `vector07a2` に入れる。C99 の `round` なので
   0から遠い方へ丸める（`clib/libc.py` の `c_round`）。

3. **個人を順に見て、枠の残っている遷移先を1つ割り当てる**
   `var008` に遷移先の状態コードを入れ、枠を1つ減らして `var037 = 1` を
   立てる。上限は `arg07a5`（`vector026`）の `std::stoi`。

`func07a` は `var035 ∈ {1,2,3}`（すでに受給か何かの区分）の人を、
`func07b` は `var035 == 9`（まだ区分の付いていない人）を扱い、
`func07b` は遷移先を決めるときに `var035` も 1 か 3 に書き換える。

添字のずらし（12, 13 を飛ばす）
------------------------------
`arg07a3`（`vector001`）は20個の状態コードだが、入力表の列は18個しか
無い。そこで

    k < 12        → 表の k 列
    k == 12, 13   → 0.0（表に対応する列が無い）
    k >= 14       → 表の k-2 列

とずらしている。`vector001` の 12,13 番目は **33, 34**（`main.cpp:36`）で、
31/32 と対になる区分。入力表では 31/32 の列に畳まれていて、
33/34 のぶんは別扱いという読み。行側（j）も同じく `j-2` でずらす。

`j == 12` / `j == 13` だけは、`arg07a9 >= 1` のときに
**10行目・11行目を列を入れ替えて読む**（`prog07.cpp:22-49`）。
`arg07a9`（`object01b.value001`）はオプションの切り替えで、
0 のときは `j == 12, 13` は一律 0.0 になる。

原本の癖をそのまま残しているところ
----------------------------------
1. **`var007 != 90` は常に真**（`prog07.cpp:126,129,143` など）
   `vector001` に 90 は無い。ただし `main.cpp:147` が新規追加の人に
   `set_var008(90)` を入れていて、翌年度の先頭（`main.cpp:160-161`）で
   `var007 = var008` と写されるので、**`var007 == 90` の人は実在する**。
   つまりこの条件は「その年に生まれた（追加された）人を外す」働きを
   していて、書き間違いではない。
   （`func06a`/`func06b` の `var007 != 90` は `var035 == 9` と重なるので
   結果に効かない。`検証/原本の不具合.md` E7 を参照）

2. **`arg07b1 == 19 && var007 == 90` は1コホートの1年度だけ**（`prog07.cpp:309,355`）
   `main.cpp:104` の年度ループは `loop_var003 = loop_var002` から始まり、
   `loop_var002 ∈ {17,27,37,47,57,62}`。`loop_var003 == 19` になるのは
   `loop_var002 == 17` の3年目だけ。その年に `var007 == 90` の人は
   前年度に追加された人なので**居る**。よってここは到達する。
   `var07b1` と `vector07b4` はそのための経路。

3. **`func09a` の戻り値をそのまま添字にする**（`prog07.cpp:146` など）
   一覧に無い状態コードが来ると 99 が返り、範囲外になる。
   上の条件で 90, 99 を外しているので実データでは起きない。

4. **同じ `func09a(var007)` を1行に4回も呼ぶ**
   結果は同じなので、移植では1回だけ呼んで変数に入れている。
"""
from libc import c_round
from cppnum import stod, stoi
from prog09 import func09a

__all__ = ["func07a", "func07b"]


def _prob_row(tbl, row, k, ncol_break=12):
    """入力表の1マスを読む。列の 12, 13 を飛ばすずらしを1か所にまとめる。

        k < 12       → tbl[row][k]
        k == 12, 13  → 0.0
        k >= 14      → tbl[row][k-2]
    """
    if k < ncol_break:
        return stod(tbl[row][k])
    if k == 12 or k == 13:
        return 0.0
    return stod(tbl[row][k - 2])


def func07a(arg07a1, arg07a2, arg07a3, arg07a4, arg07a5, arg07a6,
            arg07a7, arg07a8, arg07a9, arg07a10, arg07a11):
    """prog07.cpp:6 の忠実移植。`var035 ∈ {1,2,3}` の人の遷移。

    arg07a1   年度（loop_var003）
    arg07a2   人数（main_var002）
    arg07a3   状態コードの一覧（vector001、20個）
    arg07a4   個人のリスト（書き換える）
    arg07a5   上限の表（vector026、文字列）
    arg07a6   遷移確率の表（vector031、文字列）
    arg07a7   使った数（vector030、書き換える）
    arg07a8   残りの数（vector029、書き換える）
    arg07a9   object01b.value001
    arg07a10  object01c.value001
    arg07a11  基準年齢（loop_var002）
    """
    n = len(arg07a3)              # 20
    off = n - 3                   # 17。表の上半分と下半分の行数
    nj = n - 1                    # 19

    # [2][19][20] の遷移確率
    v1 = [[[0.0] * n for _ in range(nj)] for _ in range(2)]
    # [2][19][20] の枠（人数×確率を丸めたもの）
    v2 = [[[0] * n for _ in range(nj)] for _ in range(2)]

    if arg07a9 >= 1:
        for j in range(nj):
            for k in range(n):
                for m in range(2):
                    if j < 12:
                        v1[m][j][k] = _prob_row(arg07a6, j + off * m, k)
                    elif j == 12:
                        # 10行目を、10列と11列を入れ替えて読む
                        r = 10 + off * m
                        if k < 10:
                            v1[m][j][k] = stod(arg07a6[r][k])
                        elif k == 10:
                            v1[m][j][k] = 0.0
                        elif k == 11:
                            v1[m][j][k] = stod(arg07a6[r][11])
                        elif k == 12:
                            v1[m][j][k] = stod(arg07a6[r][10])
                        elif k == 13:
                            v1[m][j][k] = 0.0
                        else:
                            v1[m][j][k] = stod(arg07a6[r][k - 2])
                    elif j == 13:
                        # 11行目。こちらは 11列 を 13 に送る
                        r = 11 + off * m
                        if k < 10:
                            v1[m][j][k] = stod(arg07a6[r][k])
                        elif k == 10:
                            v1[m][j][k] = stod(arg07a6[r][10])
                        elif k == 11:
                            v1[m][j][k] = 0.0
                        elif k == 12:
                            v1[m][j][k] = 0.0
                        elif k == 13:
                            v1[m][j][k] = stod(arg07a6[r][11])
                        else:
                            v1[m][j][k] = stod(arg07a6[r][k - 2])
                    else:
                        v1[m][j][k] = _prob_row(arg07a6, (j - 2) + off * m, k)
    elif arg07a10 == 1 and (
            ((arg07a11 == 49 or arg07a11 == 50) and arg07a1 == 60)
            or ((arg07a11 == 47 or arg07a11 == 48)
                and 60 <= arg07a1 <= 61)
            or ((arg07a11 == 45 or arg07a11 == 46)
                and 60 <= arg07a1 <= 62)
            or ((arg07a11 == 43 or arg07a11 == 44)
                and 60 <= arg07a1 <= 63)
            or (arg07a11 <= 42 and 60 <= arg07a1 <= 64)):
        # 支給開始年齢の引き上げ途中の年度。j<10 と j==17 は
        # 「16行17列の値で抜けるか、残りは自分のまま」の2択になる
        for j in range(nj):
            for k in range(n):
                for m in range(2):
                    if j < 10 or j == 17:
                        p = stod(arg07a6[16 + off * m][17])
                        if k == 19:
                            v1[m][j][k] = p
                        elif k == j:
                            v1[m][j][k] = 1.0 - p
                        else:
                            v1[m][j][k] = 0.0
                    elif j == 10 or j == 11:
                        v1[m][j][k] = _prob_row(arg07a6, j + off * m, k)
                    elif j == 12 or j == 13:
                        v1[m][j][k] = 0.0
                    else:
                        v1[m][j][k] = _prob_row(arg07a6, (j - 2) + off * m, k)
    else:
        for j in range(nj):
            for k in range(n):
                for m in range(2):
                    if j < 12:
                        v1[m][j][k] = _prob_row(arg07a6, j + off * m, k)
                    elif j == 12 or j == 13:
                        v1[m][j][k] = 0.0
                    else:
                        v1[m][j][k] = _prob_row(arg07a6, (j - 2) + off * m, k)

    # 状態ごとの人数を数える。prog07.cpp:123-134
    v3 = [[0] * nj for _ in range(2)]
    for i in range(arg07a2):
        o = arg07a4[i]
        for j in range(nj):
            ok = (not (arg07a1 < 59 and o.var007 == 80)
                  and o.var007 != 90 and o.var007 != 99
                  and o.var007 == arg07a3[j])
            if ok and (o.var035 == 1 or o.var035 == 2):
                v3[0][j] += 1
                break
            elif ok and o.var035 == 3:
                v3[1][j] += 1
                break

    # 人数×確率を丸めて枠にする。prog07.cpp:135-141
    for m in range(2):
        for j in range(nj):
            row1 = v1[m][j]
            row2 = v2[m][j]
            cnt = float(v3[m][j])
            for k in range(n):
                row2[k] = int(c_round(cnt * row1[k]))

    # 枠の残っている遷移先を割り当てる。prog07.cpp:142-172
    for i in range(arg07a2):
        o = arg07a4[i]
        if (not (arg07a1 < 59 and o.var007 == 80)
                and o.var007 != 90 and o.var007 != 99 and o.var037 != 1):
            if o.var035 == 1 or o.var035 == 2:
                m = 0
            elif o.var035 == 3:
                m = 1
            else:
                continue
            r = func09a(o.var007)
            for k in range(n):
                if v2[m][r][k] > 0:
                    if arg07a7[r][k] < stoi(arg07a5[r][k]):
                        o.var008 = arg07a3[k]
                        arg07a7[r][k] += 1
                        arg07a8[r][k] -= 1
                        o.var037 = 1
                        v2[m][r][k] -= 1
                        break


def func07b(arg07b1, arg07b2, arg07b3, arg07b4, arg07b5, arg07b6, arg07b7,
            arg07b8, arg07b9, arg07b10, arg07b11, arg07b12):
    """prog07.cpp:175 の忠実移植。`var035 == 9`（区分未定）の人の遷移。

    `func07a` とほぼ同じ形だが、次が違う。

    - 遷移確率の3番目の寸法が **19**（`size()-1`）で、k は 19 まで行かない
    - 遷移先を決めるときに **`var035` も 1 か 3 に書き換える**
      （`func07a` は `var035` を触らない）
    - `var035 == 9` のうち `var007 == 90`（その年度に追加された人）を
      `arg07b7`（`vector033`）の1行だけの確率で別扱いする

    arg07b1   年度（loop_var003）
    arg07b2   人数
    arg07b3   状態コードの一覧
    arg07b4   個人のリスト（書き換える）
    arg07b5   上限の表（vector026）
    arg07b6   遷移確率の表（vector032）
    arg07b7   var007==90 用の確率（vector033、1行）
    arg07b8   使った数（vector030、書き換える）
    arg07b9   残りの数（vector029、書き換える）
    arg07b10  object01b.value001
    arg07b11  object01c.value001
    arg07b12  基準年齢（loop_var002）
    """
    n = len(arg07b3)              # 20
    off = n - 3                   # 17
    nj = n - 1                    # 19

    v1 = [[[0.0] * nj for _ in range(nj)] for _ in range(2)]
    v2 = [[[0] * nj for _ in range(nj)] for _ in range(2)]
    v3 = [0.0] * nj               # var007==90 用の確率
    v4 = [0] * nj                 # var007==90 用の枠

    if arg07b10 >= 1:
        for j in range(nj):
            for k in range(nj):
                for m in range(2):
                    if j < 12:
                        v1[m][j][k] = _prob_row(arg07b6, j + off * m, k)
                    elif j == 12:
                        r = 10 + off * m
                        if k < 10:
                            v1[m][j][k] = stod(arg07b6[r][k])
                        elif k == 10:
                            v1[m][j][k] = 0.0
                        elif k == 11:
                            v1[m][j][k] = stod(arg07b6[r][11])
                        elif k == 12:
                            v1[m][j][k] = stod(arg07b6[r][10])
                        elif k == 13:
                            v1[m][j][k] = 0.0
                        else:
                            v1[m][j][k] = stod(arg07b6[r][k - 2])
                    elif j == 13:
                        r = 11 + off * m
                        if k < 10:
                            v1[m][j][k] = stod(arg07b6[r][k])
                        elif k == 10:
                            v1[m][j][k] = stod(arg07b6[r][10])
                        elif k == 11:
                            v1[m][j][k] = 0.0
                        elif k == 12:
                            v1[m][j][k] = 0.0
                        elif k == 13:
                            v1[m][j][k] = stod(arg07b6[r][11])
                        else:
                            v1[m][j][k] = stod(arg07b6[r][k - 2])
                    else:
                        v1[m][j][k] = _prob_row(arg07b6, (j - 2) + off * m, k)
    elif arg07b11 == 1 and (
            ((arg07b12 == 49 or arg07b12 == 50) and arg07b1 == 60)
            or ((arg07b12 == 47 or arg07b12 == 48)
                and 60 <= arg07b1 <= 61)
            or ((arg07b12 == 45 or arg07b12 == 46)
                and 60 <= arg07b1 <= 62)
            or ((arg07b12 == 43 or arg07b12 == 44)
                and 60 <= arg07b1 <= 63)
            or (arg07b12 <= 42 and 60 <= arg07b1 <= 64)):
        for j in range(nj):
            for k in range(nj):
                for m in range(2):
                    if j < 10 or j == 17:
                        # func07a と違って 16行 **16列**。対角だけに入る
                        if k == j:
                            v1[m][j][k] = stod(arg07b6[16 + off * m][16])
                        else:
                            v1[m][j][k] = 0.0
                    elif j == 10 or j == 11:
                        v1[m][j][k] = _prob_row(arg07b6, j + off * m, k)
                    elif j == 12 or j == 13:
                        v1[m][j][k] = 0.0
                    else:
                        v1[m][j][k] = _prob_row(arg07b6, (j - 2) + off * m, k)
    else:
        for j in range(nj):
            for k in range(nj):
                for m in range(2):
                    if j < 12:
                        v1[m][j][k] = _prob_row(arg07b6, j + off * m, k)
                    elif j == 12 or j == 13:
                        v1[m][j][k] = 0.0
                    else:
                        v1[m][j][k] = _prob_row(arg07b6, (j - 2) + off * m, k)

    # var007==90 用。arg07b7 は1行だけ。prog07.cpp:291-299
    for k in range(nj):
        v3[k] = _prob_row(arg07b7, 0, k)

    # 状態ごとの人数を数える。prog07.cpp:300-312
    v5 = [0] * nj
    var07b1 = 0
    for i in range(arg07b2):
        o = arg07b4[i]
        for j in range(nj):
            if (not (arg07b1 < 59 and o.var007 == 80)
                    and o.var007 != 90 and o.var007 != 99
                    and o.var007 == arg07b3[j] and o.var035 == 9):
                v5[j] += 1
                break
        if (arg07b1 == 19 and o.var007 == 90) and o.var035 == 9:
            var07b1 += 1

    for m in range(2):
        for j in range(nj):
            row1 = v1[m][j]
            row2 = v2[m][j]
            cnt = float(v5[j])
            for k in range(nj):
                row2[k] = int(c_round(cnt * row1[k]))

    for k in range(nj):
        v4[k] = int(c_round(float(var07b1) * v3[k]))

    # 枠の残っている遷移先を割り当てる。prog07.cpp:323-370
    for i in range(arg07b2):
        o = arg07b4[i]
        if (not (arg07b1 < 59 and o.var007 == 80)
                and o.var007 != 90 and o.var007 != 99
                and o.var035 == 9 and o.var037 != 1):
            r = func09a(o.var007)
            flag_kiso_hassei = 0
            for k in range(nj):
                if v2[0][r][k] > 0:
                    if arg07b8[r][k] < stoi(arg07b5[r][k]):
                        o.var035 = 1
                        o.var008 = arg07b3[k]
                        arg07b8[r][k] += 1
                        arg07b9[r][k] -= 1
                        o.var037 = 1
                        v2[0][r][k] -= 1
                        flag_kiso_hassei = 1
                        break
            if flag_kiso_hassei != 1:
                for k in range(nj):
                    if v2[1][r][k] > 0:
                        if arg07b8[r][k] < stoi(arg07b5[r][k]):
                            o.var035 = 3
                            o.var008 = arg07b3[k]
                            arg07b8[r][k] += 1
                            arg07b9[r][k] -= 1
                            o.var037 = 1
                            v2[1][r][k] -= 1
                            break
        elif ((arg07b1 == 19 and o.var007 == 90)
                and o.var035 == 9 and o.var037 != 1):
            # その年度に追加された人。使う行は **末尾から2行目**
            r8 = len(arg07b8) - 2
            r5 = len(arg07b5) - 2
            r9 = len(arg07b9) - 2
            for k in range(nj):
                if v4[k] > 0:
                    if arg07b8[r8][k] < stoi(arg07b5[r5][k]):
                        o.var035 = 1
                        o.var008 = arg07b3[k]
                        arg07b8[r8][k] += 1
                        arg07b9[r9][k] -= 1
                        o.var037 = 1
                        v4[k] -= 1
                        break
