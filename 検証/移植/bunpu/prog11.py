# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog11.cpp の忠実移植
=========================================
個人ごとの**年金額（`var044`）**を組み立てる。`main.cpp:219` で年度ごとに
呼ばれ、`func12c` が集計するのはこの値。

年金額の内訳（読み解いた範囲）
------------------------------
`var044` は5つの足し合わせ（`prog11.cpp:235`）。

    var11a12  基礎年金の本体
              満額 × 加入月数 / 満額の月数 × 改定率 / 持ち越しの割り戻し
    var11a13  `var036 == 1` の人だけ足される額（`vector11a1` の表から）
    var11a14  比例部分（`var043` × 0.005481 × 改定率 / 割り戻し）
    var11a15  4つの「差額」の合計（var11a16〜19）。それぞれ
              `1628円 × 期間 − 満額 × 月数 / 満額の月数` の形で、
              **負なら 0 に切る**
    var11a20  200円 × `var012` に当たる月数

満額の月数（`var11a1`）は 480（40年）で、支給開始年齢の引き上げがある
ときは基準年齢に応じて 492〜540 に伸びる（`prog11.cpp:8-24`）。
`func06a` の 414〜474 や `func09c` の 60〜65歳と同じ刻み。

`var11a2` は「引き上げ途中の年度だけ効く倍率」で、40分のNN の形
（`prog11.cpp:26-80`）。分子が 41〜45、分母が 40〜44 で、基準年齢と
経過年数で決まる。

`var11a6 = 0.005481` は比例部分の給与比例乗率（1000分の5.481）。
`var11a8 = 200.0` は付加年金の月額（200円）と読める。

原本の癖をそのまま残しているところ
----------------------------------
1. **局所変数を21個まとめて 0.0 で作るが、使わないものがある**
   （`prog11.cpp:131-151`）。`var11a13` は `var036 == 1` のときだけ
   代入され、それ以外は 0.0 のまま足される。原本どおり。

2. **`var036` を立てる条件に `arg11a4 >= 56` が無い**
   （`prog11.cpp:125`）。数える側（`prog11.cpp:112`）は
   `arg11a4>=56 && arg11a4<65 && arg11a5==64` なのに、立てる側は
   `arg11a4<65 && arg11a5==64 && var11a11>0` で `>=56` が抜けている。
   ただし `var11a11` は数える側でしか 0 以外にならないので、
   **結果は変わらない**。

3. **`(int)((double)var11a10 * 0.027)` は0方向への切り捨て**
   （`prog11.cpp:119`）。`round` ではない。

4. **`vector11a1` は15個だが、使うのは `arg11a4 ∈ {57,62}` の2つだけ**
   `70 - arg11a4` が添字で、基準年齢は `{17,27,37,47,57,62}`
   （`main.cpp:38`）。57 → 13、62 → 8。残り13個は使われない。
   末尾5個が同じ値（15055.0）なのもそのため。
"""
from cppnum import stod

__all__ = ["func11a"]

# prog11.cpp:88。添字は 70 - 基準年齢。実際に引かれるのは 13 と 8 だけ
_TBL11A = [74825.0, 68983.0, 62916.0, 56849.0, 51007.0, 44940.0, 38873.0,
           33031.0, 26964.0, 20897.0, 15055.0, 15055.0, 15055.0, 15055.0,
           15055.0]

# prog11.cpp:26-80 の倍率。基準年齢 → [(経過年数の上限, 分子, 分母), …]。
# 最後まで当たらなければ 1.0。分子は基準年齢の組ごとに 41〜45 と決まる。
_RATE11A = {
    (49, 50): (41.0, [(8, 40.0)]),
    (47, 48): (42.0, [(8, 40.0), (11, 41.0)]),
    (45, 46): (43.0, [(8, 40.0), (11, 41.0), (14, 42.0)]),
    (43, 44): (44.0, [(8, 40.0), (11, 41.0), (14, 42.0), (17, 43.0)]),
}
# 上のどれにも当たらない（42以下）ときの組
_RATE11A_ELSE = (45.0, [(8, 40.0), (11, 41.0), (14, 42.0), (17, 43.0),
                        (20, 44.0)])


def _mangetsu(arg11a4, arg11a10):
    """満額の月数（`var11a1`）。prog11.cpp:8-24。"""
    if arg11a10 == 0:
        return 480.0
    if arg11a4 >= 51:
        return 480.0
    if arg11a4 == 49 or arg11a4 == 50:
        return 492.0
    if arg11a4 == 47 or arg11a4 == 48:
        return 504.0
    if arg11a4 == 45 or arg11a4 == 46:
        return 516.0
    if arg11a4 == 43 or arg11a4 == 44:
        return 528.0
    return 540.0


def _rate(arg11a4, arg11a5, arg11a10):
    """引き上げ途中の倍率（`var11a2`）。prog11.cpp:26-80。"""
    if not (arg11a10 == 1 and arg11a4 <= 50):
        return 1.0
    num, steps = _RATE11A_ELSE
    for keys, ent in _RATE11A.items():
        if arg11a4 in keys:
            num, steps = ent
            break
    d = arg11a5 - arg11a4
    for lim, den in steps:
        if d <= lim:
            return num / den
    return 1.0


def _cap(v, lim):
    """`if (x > lim) y = lim; else y = x;` の形。prog11.cpp:152-211。"""
    return lim if v > lim else float(v)


def func11a(arg11a1, arg11a2, arg11a3, arg11a4, arg11a5, arg11a6, arg11a7,
            arg11a8, arg11a9, arg11a10):
    """prog11.cpp:6 の忠実移植。個人ごとの年金額（var044）を作る。

    arg11a1   人数
    arg11a2   個人のリスト（書き換える）
    arg11a3   性別（loop_var001）
    arg11a4   基準年齢（loop_var002）
    arg11a5   年度（loop_var003。初回だけ loop_var002 - 1）
    arg11a6   国年の年金額（vector016）
    arg11a7   基礎のカット率（vector017）
    arg11a8   比例のカット率（vector018）
    arg11a9   経済前提（vector013）
    arg11a10  object01c.value001
    """
    var11a1 = _mangetsu(arg11a4, arg11a10)
    var11a2 = _rate(arg11a4, arg11a5, arg11a10)

    var11a3 = 66 if arg11a5 <= 66 else arg11a5
    col = var11a3 - 65                     # カット率の列
    rowc = arg11a5 - arg11a4 + 17          # カット率の行

    # 満額（1人あたりの年額）。prog11.cpp:87
    var11a4 = stod(arg11a6[arg11a5 - arg11a4 + 2][arg11a5 + 2]) * var11a2

    # var036 の人に足す額。prog11.cpp:89-92
    var11a5 = 0.0
    if 56 <= arg11a4 <= 70:
        var11a5 = (_TBL11A[70 - arg11a4]
                   * stod(arg11a6[arg11a5 - arg11a4 + 2][arg11a5 + 2])
                   * var11a2 / stod(arg11a6[1][68]))

    var11a6 = 0.005481                     # 給与比例乗率（1000分の5.481）
    # 1628円 × 満額の比。prog11.cpp:94
    var11a7 = (1628.0 * stod(arg11a6[arg11a5 - arg11a4 + 2][arg11a5 + 2])
               * var11a2 / stod(arg11a6[1][68]) * 480.0 / var11a1)
    var11a8_ = 200.0                       # 付加年金の月額

    # 持ち越し分の割り戻し。prog11.cpp:97-109
    var11a9_ = 1.0
    if arg11a5 == arg11a4 - 1:
        var11a9_ = (1.0 / (1.0 + stod(arg11a9[21][6]) / 100.0)
                    / (1.0 + stod(arg11a9[22][6]) / 100.0)
                    / (1.0 + stod(arg11a9[23][6]) / 100.0))
    elif arg11a5 == arg11a4:
        var11a9_ = (1.0 / (1.0 + stod(arg11a9[22][6]) / 100.0)
                    / (1.0 + stod(arg11a9[23][6]) / 100.0))
    elif arg11a5 == arg11a4 + 1:
        var11a9_ = 1.0 / (1.0 + stod(arg11a9[23][6]) / 100.0)
    elif arg11a5 == arg11a4 + 2:
        var11a9_ = 1.0
    else:
        for years in range(arg11a4 + 3, arg11a5 + 1):
            var11a9_ *= (1.0
                         + stod(arg11a9[years - arg11a4 + 21][6]) / 100.0)

    # var036 を立てる人数。prog11.cpp:110-123
    var11a10_ = 0
    var11a11 = 0
    if 56 <= arg11a4 < 65 and arg11a5 == 64:
        for p in range(arg11a1):
            o = arg11a2[p]
            if not o.is_func04() and o.var022 < 240:
                var11a10_ += 1
        if arg11a3 == 1:
            var11a11 = int(float(var11a10_) * 0.027)    # 0方向へ切り捨て
        else:
            var11a11 = int(float(var11a10_) * 0.503)

    cut_kiso = stod(arg11a7[rowc][col])
    cut_hirei = stod(arg11a8[rowc][col])

    for p in range(arg11a1):
        o = arg11a2[p]
        # **>=56 が抜けているが var11a11 が 0 なので効かない**（癖 2.）
        if arg11a4 < 65 and arg11a5 == 64 and var11a11 > 0:
            if not o.is_func04() and o.var022 < 240:
                o.var036 = 1
                var11a11 -= 1

        # 満額の月数で頭を打つ。prog11.cpp:152-211。
        # var11a22（var022）と var11a27（var023）は原本でも作るだけで
        # 使わないので、移植では作らない（癖 1.）
        v21 = _cap(o.var038, var11a1)      # 基礎の月数（重み付き）
        v23 = _cap(o.var028, var11a1)
        v28 = _cap(o.var024, var11a1)
        v24 = _cap(o.var030, var11a1)
        v29 = _cap(o.var025, var11a1)
        v25 = _cap(o.var031, var11a1)
        v30 = _cap(o.var026, var11a1)
        v26 = _cap(o.var032, var11a1)
        v31 = _cap(o.var027, var11a1)
        v32 = _cap(o.var012, var11a1)

        # 基礎年金の本体
        v12 = var11a4 * v21 / var11a1 * cut_kiso / var11a9_
        # var036 の人だけ
        v13 = var11a5 / var11a9_ if o.var036 == 1 else 0.0
        # 比例部分
        v14 = o.var043 * var11a6 * cut_hirei / var11a9_
        # 4つの差額。負なら 0
        v16 = (var11a7 * v23 - var11a4 * v28 / var11a1) * cut_kiso / var11a9_
        if v16 < 0.0:
            v16 = 0.0
        v17 = (var11a7 * v24 - var11a4 * v29 / var11a1) * cut_kiso / var11a9_
        if v17 < 0.0:
            v17 = 0.0
        v18 = (var11a7 * v25 - var11a4 * v30 / var11a1) * cut_kiso / var11a9_
        if v18 < 0.0:
            v18 = 0.0
        v19 = (var11a7 * v26 - var11a4 * v31 / var11a1) * cut_kiso / var11a9_
        if v19 < 0.0:
            v19 = 0.0
        v15 = v16 + v17 + v18 + v19
        # 付加年金
        v20 = var11a8_ * v32 / var11a9_

        o.var044 = v12 + v13 + v14 + v15 + v20
