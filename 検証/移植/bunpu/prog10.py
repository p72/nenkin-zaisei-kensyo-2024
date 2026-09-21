# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog10.cpp の忠実移植
=========================================
標準報酬（と思われる金額）の割り当てと、年金額の積み上げ。4つの関数がある。

    func10a  4つの表から加重平均を作って vector012 に入れる（起動時1回）
    func10b  被用者の人に標準報酬の等級を割り当てる（var041, var042）
    func10c  等級別の平均を目標値に合わせて調整し、下限を当てる
    func10d  年金額（var043）を1年ぶん積み上げる

func10a — 加重平均
------------------
`vector012` は `[4][105][2][55]` で、4つの区分（`arg10a1`〜`arg10a4` が
値、`arg10a5`〜`arg10a8` が重み）ごとに

    Σ_t 値[t] × 重み[t] / Σ_t 重み[t]      （t は 0〜70、列は t+4）

を入れる。行は `3*55*i + 55*j + k`（i が年、j が性別、k が年齢）。

**区分 0 だけ `j==0` のときに `j==2` の行も足し込む**
（`prog10.cpp:15-18`）。3行のうち0番目と2番目を合わせる形なので、
「男＋不明」のような合算と読める。他の3区分には無い。

func10b — 等級の割り当て
------------------------
`var008`（遷移先の状態）が 31,32,33,34,40,50,60 の7通りについて

    vector10b5[g][var040-1]   前年度の等級別の人数（g は上の7通り）
    vector10b6[g]             前年度の等級が無い人の人数

を数え、遷移確率（`arg10b3` / `arg10b4`）を掛けて枠を作り、個人に
等級（`var042`）と金額（`var041`）を割り当てる。

丸めで合計がずれるので、**枠の合計を人数に合わせ直す**段がある
（`prog10.cpp:166-193`、`212-236`）。足りなければ確率が正のところへ
1ずつ配り、それでも足りなければ0列目にまとめて足す。多ければ正の
ところから1ずつ引く。

func10c — 目標値に合わせる
--------------------------
状態を4区分（31-34 / 40 / 50 / 60）にまとめ、`var041` の平均を出して
`vector012` の目標値との比を取り、全員の `var041` に掛ける。
そのあと下限（`arg10c8` ＝ 1,056,000円を賃金上昇で伸ばしたもの）を当てる。

func10d — 年金額の積み上げ
--------------------------
`add_var043(a, x, b, y, r)` は

    var043 = var043 * r + ( a * (x/12) + b * (y/12) )

で、`x` が当年度の月数（`var033`）、`y` が前年度の月数（`var034`）。
`a` が当年度の単価（`var039 * var10d1`）、`b` が前年度の単価
（`var041 * var10d1`）、`r` が持ち越し分の改定率（`var10d2`）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`var040 - 1` が添字になる。`var040 == 0` なら -1**
   （`prog10.cpp:117` など）
   C では配列の外を読む（未定義動作）。Python では負の添字が末尾から
   数える別の意味になってしまうので、移植では**そこで落とす**。
   `var040` は `var042` の前年度値（`main.cpp:165-166`）で、
   `var042` は `func10b` が 1 以上を入れるか、`is_func02()` が偽なら 0。
   `is_func01()`（＝前年度の `var008` が被用者）と `var040 == 0` が
   同時に成り立つ経路は見つかっていないが、**枠が全部 0 で
   `var042` が前の値のまま残る**場合に起こりうる。
   （`検証/原本の不具合.md`）

2. **`arg10b5` の行の刻みは5なのに、区分は7つある**（`prog10.cpp:246` など）
   行は `(var004-1)*275 + (var005-16)*5 + g` で `g` は 0〜6。
   275 = 55歳 × 5 なので刻みは5。`g` が 5, 6（状態 50 と 60）のときは
   **次の年齢の 0, 1 行目**を読むことになる。⑤の `etoc` と同じ形の
   重なりで、意図か書き間違いかはコードからは判別できない。
   （`検証/原本の不具合.md`）

3. **`func10c` の平均は整数除算**（`prog10.cpp:491`）
   `vector10c1` は `long long` で、`(long long)var041` と足し込み、
   `(double)(合計/人数)` としている。**`long long / long long` なので
   小数は切り捨てられる**。金額（円）なので意図的とも読めるが、
   `double` で割るのとは結果が違う。

4. **`arg10b9` は値渡しなので `--arg10b9` は呼び出し側に返らない**
   （`prog10.cpp:276` など）。移植でも局所変数にしている。

5. **`func10b` の `i==3` だけ `[0][0]` に 1.0 が入る**
   （`prog10.cpp:79-81, 97-99`）。`j==0` / `k==0` の行は他は 0 のまま。
   `var040 == 1` の人が枠にあふれたときの逃げ道と読める。
"""
from libc import c_round
from cppnum import stod

__all__ = ["func10a", "func10b", "func10c", "func10d"]

# func10b が扱う var008 の7通り。添字が vector10b5 などの第1添字になる
_GRP10B = (31, 32, 33, 34, 40, 50, 60)
_GRP10B_IDX = {c: i for i, c in enumerate(_GRP10B)}


def func10a(arg10a1, arg10a2, arg10a3, arg10a4, arg10a5, arg10a6, arg10a7,
            arg10a8, arg10a9):
    """prog10.cpp:6 の忠実移植。4区分の加重平均を `arg10a9` に入れる。

    arg10a1〜arg10a4  値の表（vector004〜vector007）
    arg10a5〜arg10a8  重みの表（vector008〜vector011）
    arg10a9           書き込み先（vector012、[4][105][2][55]）
    """
    # 区分0だけ j==0 のときに j==2 の行も足す（原本のとおり）
    _one10a(arg10a1, arg10a5, arg10a9, 0, extra_j2=True)
    _one10a(arg10a2, arg10a6, arg10a9, 1, extra_j2=False)
    _one10a(arg10a3, arg10a7, arg10a9, 2, extra_j2=False)
    _one10a(arg10a4, arg10a8, arg10a9, 3, extra_j2=False)


def _one10a(val, wgt, out, g, extra_j2):
    """`func10a` の4つのループのうち1つ。行は `3*55*i + 55*j + k`。"""
    o = out[g]
    for i in range(len(o)):
        for j in range(len(o[i])):
            for k in range(len(o[i][j])):
                num = 0.0
                den = 0.0
                r = 3 * 55 * i + 55 * j + k
                r2 = 3 * 55 * i + 55 * 2 + k
                for t in range(71):
                    w = stod(wgt[r][t + 4])
                    num += stod(val[r][t + 4]) * w
                    den += w
                    if extra_j2 and j == 0:
                        w2 = stod(wgt[r2][t + 4])
                        num += stod(val[r2][t + 4]) * w2
                        den += w2
                if den > 0:
                    o[i][j][k] = num / den


def _idx040(o):
    """`var040 - 1`。0 なら C は配列の外を読むので、移植では落とす（癖 1.）。"""
    v = o.var040 - 1
    if v < 0:
        raise IndexError(
            f"func10b: var040 = {o.var040} なので添字が {v} になる。"
            "原本は配列の外を読む（未定義動作）")
    return v


def func10b(arg10b1, arg10b2, arg10b3, arg10b4, arg10b5, arg10b6, arg10b7,
            arg10b8, arg10b9):
    """prog10.cpp:73 の忠実移植。等級（var042）と金額（var041）を割り当てる。

    arg10b1  人数（main_var002）
    arg10b2  個人のリスト（書き換える）
    arg10b3  等級の遷移確率（vector036、文字列）
    arg10b4  等級が無い人用の確率（vector037、文字列）
    arg10b5  等級別の金額（vector025、double の表）
    arg10b6  object01b.value001
    arg10b7  年度（loop_var003）
    arg10b8  基準年齢（loop_var002）
    arg10b9  2027年度の特例に使う人数（main_var005）。**値渡し**（癖 4.）
    """
    ng = 7
    nk = 53
    v1 = [[[0.0] * nk for _ in range(nk)] for _ in range(ng)]
    v2 = [[[0] * nk for _ in range(nk)] for _ in range(ng)]
    v3 = [[0.0] * nk for _ in range(ng)]
    v4 = [[0] * nk for _ in range(ng)]
    rest = arg10b9                    # 値渡しの複製（癖 4.）

    # 等級の遷移確率。prog10.cpp:78-95
    for i in range(ng):
        if i == 3:
            v1[i][0][0] = 1.0         # 癖 5.
        if i == 3:
            continue                  # 残りは 0.0 のまま
        row_base = (0 if (i == 0 or i == 2) else
                    (52 if i == 1 else (i - 2) * 52))
        for j in range(1, nk):
            src = arg10b3[row_base + (j - 1)]
            dst = v1[i][j]
            for k in range(1, nk):
                dst[k] = stod(src[k - 1])

    # 等級が無い人用の確率。prog10.cpp:96-111
    for i in range(ng):
        if i == 3:
            v3[i][0] = 1.0            # 癖 5.
            continue
        r = 0 if (i == 0 or i == 2) else (1 if i == 1 else i - 2)
        src = arg10b4[r]
        for j in range(1, nk):
            v3[i][j] = stod(src[j - 1])

    # 人数を数える。prog10.cpp:112-158
    v5 = [[0] * nk for _ in range(ng)]      # 前年度の等級がある人
    v6 = [0] * ng                           # 等級が無い人
    for p in range(arg10b1):
        o = arg10b2[p]
        g = _GRP10B_IDX.get(o.var008)
        if g is None:
            continue
        # var008==34（g==3）だけ var007!=34 を見ない（原本のとおり）
        if o.is_func01() and (g == 3 or o.var007 != 34):
            v5[g][_idx040(o)] += 1
        else:
            v6[g] += 1

    # 人数×確率を丸めて枠にする。prog10.cpp:159-165
    for i in range(ng):
        for j in range(nk):
            cnt = float(v5[i][j])
            row1 = v1[i][j]
            row2 = v2[i][j]
            for k in range(nk):
                row2[k] = int(c_round(cnt * row1[k]))

    # 丸めのずれを人数に合わせ直す。prog10.cpp:166-193
    for i in range(ng):
        for j in range(nk):
            row1 = v1[i][j]
            row2 = v2[i][j]
            tot = 0
            for k in range(nk):
                tot += row2[k]
            if v5[i][j] > tot:
                short = v5[i][j] - tot
                for k in range(nk):
                    if row1[k] > 0 and short > 0:
                        row2[k] += 1
                        short -= 1
                if short > 0:
                    row2[0] += short
            elif v5[i][j] < tot:
                over = tot - v5[i][j]
                for k in range(nk):
                    if row2[k] > 0 and over > 0:
                        row2[k] -= 1
                        over -= 1

    # 等級が無い人の枠。prog10.cpp:194-211。
    # 2027年度で i==1（var008==32）だけ、特例の人数を1列目に乗せる
    special = ((arg10b6 == 2 or arg10b6 == 3 or arg10b6 == 4)
               and (arg10b7 + 2022 - arg10b8 == 2027))
    for i in range(ng):
        for j in range(nk):
            if not (special and i == 1):
                v4[i][j] = int(c_round(float(v6[i]) * v3[i][j]))
            else:
                n = v6[i] - arg10b9
                if n < 0:
                    n = 0
                if j == 1:
                    v4[i][j] = int(c_round(float(n) * v3[i][j]
                                           + float(arg10b9)))
                else:
                    v4[i][j] = int(c_round(float(n) * v3[i][j]))

    # こちらも合わせ直す。prog10.cpp:212-236
    for i in range(ng):
        tot = 0
        for j in range(nk):
            tot += v4[i][j]
        if v6[i] > tot:
            short = v6[i] - tot
            for j in range(nk):
                if v3[i][j] > 0 and short > 0:
                    v4[i][j] += 1
                    short -= 1
            if short > 0:
                v4[i][0] += short
        elif v6[i] < tot:
            over = tot - v6[i]
            for j in range(nk):
                if v4[i][j] > 0 and over > 0:
                    v4[i][j] -= 1
                    over -= 1

    # 個人に等級と金額を割り当てる。prog10.cpp:237-466
    var10b8 = 0.9                     # 状態 33 のときだけ掛かる係数
    for p in range(arg10b1):
        o = arg10b2[p]
        if not o.is_func02():
            # 前年度が被用者でない人は等級なし
            o.var042 = 0
            o.var041 = 0.0
            continue

        g = _GRP10B_IDX.get(o.var008)
        if g is None:
            continue
        # 行は (var004-1)*275 + (var005-16)*5 + g。刻み5に対して g は 0〜6（癖 2.）
        row = (o.var004 - 1) * 275 + (o.var005 - 16) * 5 + g
        fac = var10b8 if g == 2 else 1.0

        if o.is_func01():
            # var008==34（g==3）だけ var007 を見ない
            use_grade = (g == 3 or o.var007 != 34)
            if use_grade:
                if v5[g][_idx040(o)] > 0:
                    col = _idx040(o)
                    slot = v2[g][col]
                    for k in range(nk):
                        if slot[k] > 0:
                            o.var042 = k + 1
                            o.var041 = arg10b5[row][k] * fac
                            slot[k] -= 1
                            v5[g][col] -= 1
                            break
                continue
            # var007==34 の人は「等級が無い」側の枠を使う
            if v6[g] <= 0:
                continue
        else:
            if v6[g] <= 0:
                continue

        # 等級が無い側。g==1（var008==32）だけ2027年度の特例が先に入る
        if g == 1 and special and rest > 0 and v4[1][1] > 0:
            o.var042 = 2
            o.var041 = arg10b5[row][1]
            v4[1][1] -= 1
            v6[1] -= 1
            rest -= 1
            continue
        for j in range(nk):
            if v4[g][j] > 0:
                o.var042 = j + 1
                o.var041 = arg10b5[row][j] * fac
                v4[g][j] -= 1
                v6[g] -= 1
                break


def func10c(arg10c1, arg10c2, arg10c3, arg10c4, arg10c5, arg10c6, arg10c7,
            arg10c8):
    """prog10.cpp:468 の忠実移植。平均を目標値に合わせ、下限を当てる。

    arg10c1  人数
    arg10c2  個人のリスト（書き換える）
    arg10c3  性別（loop_var001、1 か 2）
    arg10c4  基準年齢（loop_var002）
    arg10c5  年度（loop_var003。初回だけ loop_var002 - 1）
    arg10c6  目標値（vector012、[4][105][2][55]）
    arg10c7  object01b.value001
    arg10c8  下限（main_var006）
    """
    # **long long で足すので平均は整数除算**（癖 3.）
    v1 = [[0] * 4 for _ in range(2)]
    v2 = [0.0] * 4
    v3 = [1.0] * 4

    for p in range(arg10c1):
        o = arg10c2[p]
        c = o.var008
        if (c == 31 or c == 32 or c == 33 or c == 34) and not o.is_func04():
            i = 0
        elif c == 40 and not o.is_func04():
            i = 1
        elif c == 50 and not o.is_func04():
            i = 2
        elif c == 60 and not o.is_func04():
            i = 3
        else:
            continue
        # (long long)double は0方向への切り捨て
        v1[0][i] += int(o.var041)
        v1[1][i] += 1

    for i in range(4):
        if v1[1][i] != 0:
            # long long / long long。小数は落ちる（癖 3.）
            q = abs(v1[0][i]) // abs(v1[1][i])
            if (v1[0][i] < 0) != (v1[1][i] < 0):
                q = -q
            v2[i] = float(q)

    for i in range(4):
        if v2[i] > 0.0 and arg10c5 < 69:
            v3[i] = (arg10c6[i][2021 - arg10c4 + arg10c5 + 1 - 2021]
                     [arg10c3 - 1][arg10c5 + 1 - 15] / v2[i])

    lower = not (arg10c7 == 4 and (arg10c5 + 2022 - arg10c4 >= 2027))
    for p in range(arg10c1):
        o = arg10c2[p]
        c = o.var008
        if c == 31 or c == 32 or c == 33 or c == 34:
            i = 0
        elif c == 40:
            i = 1
        elif c == 50:
            i = 2
        elif c == 60:
            i = 3
        else:
            continue
        v = o.var041 * v3[i]
        if lower and v > 0 and v < arg10c8:
            v = arg10c8
        o.var041 = v


def func10d(arg10d1, arg10d2, arg10d3, arg10d4, arg10d5):
    """prog10.cpp:524 の忠実移植。年金額（var043）を1年ぶん積み上げる。

    arg10d1  人数
    arg10d2  個人のリスト（書き換える）
    arg10d3  基準年齢（loop_var002）
    arg10d4  年度（loop_var003）
    arg10d5  改定率などの表（vector015、文字列）

    `var10d1` は単価に掛かる係数（0.936 を年度ごとの比で割ったもの）、
    `var10d2` は持ち越し分に掛かる改定率。
    """
    var10d1 = 0.936
    var10d2 = 1.0
    b = arg10d4 - arg10d3              # 年度の経過

    def s(r, c):
        return stod(arg10d5[b + r][c])

    if arg10d4 == 64:
        var10d1 = (var10d1 / (s(18, 1) / s(18, 2)) / (s(19, 1) / s(19, 2))
                   / s(20, 2))
    elif arg10d4 == 65:
        var10d1 = var10d1 / (s(18, 1) / s(18, 2)) / s(20, 2)
    elif arg10d4 >= 66:
        var10d1 = var10d1 / s(20, 2)
    else:
        var10d1 = (var10d1 / (s(18, 1) / s(18, 2)) / (s(19, 1) / s(19, 2))
                   / s(20, 1))

    if arg10d4 < 67:
        var10d2 = s(17, 1)
    else:
        var10d2 = s(17, arg10d4 - 65)

    for p in range(arg10d1):
        o = arg10d2[p]
        if o.is_func02():
            if o.is_func01():
                o.add_var043(o.var039 * var10d1, o.var033,
                             o.var041 * var10d1, o.var034, var10d2)
            else:
                o.add_var043(0.0, 0, o.var041 * var10d1, o.var034, var10d2)
        else:
            if o.is_func01():
                o.add_var043(o.var039 * var10d1, o.var033, 0.0, 0, var10d2)
            else:
                o.add_var043(0.0, 0, 0.0, 0, var10d2)
