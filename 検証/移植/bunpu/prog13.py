# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog13.cpp の忠実移植
=========================================
⑥の唯一の出力。`main.cpp:226-228` でコホート（性別×基準年齢）ごとに
3ファイル書く。中身は **割合（％）**で、人数そのものは出さない。

    01_{a}_{f}_{性別}_{基準年齢}.csv   4区分の割合
    02_{a}_{f}_{性別}_{基準年齢}.csv   期間の長さ別の割合＋平均年数
    03_{a}_{f}_{性別}_{基準年齢}.csv   年金額の階級別の割合＋平均月額（万円）

形（`prog13.cpp:6-23`）

    1行目  性別
    2行目  基準年齢
    3行目  object01a（外枠番号）
    4行目  object01f
    5行目  "01" / "02" / "03"
    6行目  65,{2086 - 基準年齢},{値},{値},…

6行目の先頭の `65` は `main_var001`（年度ループの終わり）、
`2086 - 基準年齢` はそのコホートが65歳になる西暦。

数の書き方
----------
原本は `std::setprecision(15)` で `double` を流す。C++ の既定の
浮動小数形式は `%g` なので、**`%.15g` と同じ**（実測で確認）。
`65` と `2086 - 基準年齢` は `int` なのでそのまま10進。
改行は `std::endl` なので `"\\n"`。

0除算になる場合（対象者が1人も居ないコホート）は C の `double` の
割り算そのままで、`0.0/0.0` は x86 で `-nan`、`x/0.0` は `±inf` と
出る（実測）。移植でもそう書く。

原本の癖をそのまま残しているところ
----------------------------------
1. **`func13c` の合計が `int` なのに `double` を足している**
   （`prog13.cpp:49`）。`int var13c1 = 0; var13c1 += arg13c5[i];` は
   **1回ごとに0方向へ切り捨てる**。`arg13c5` は人数なので整数値で、
   結果は変わらない。

2. **`func13b` の平均年数は `[0..5]` の合計で割る**
   （`prog13.cpp:37`）。`arg13b5[6]`（月数の合計）を「人数の合計」で
   割って 12 で割るので年数になる。`[6]` は合計に入らない。

3. **`func13a` は割合だけで平均が無い**
   `func13b` / `func13c` には末尾に平均が付くが、`func13a` には無い。

4. **ディレクトリが無いと黙って何も書かない**
   `std::ofstream` は失敗しても例外を投げない設定（既定）で、原本は
   `is_open()` も見ていない。移植では**そこで落とす**ようにしている
   （黙って出力が欠けるより気付ける）。
"""
import math

from prog04 import resolve

__all__ = ["func13a", "func13b", "func13c"]


def _g15(x):
    """C++ の `operator<<(double)`＋`setprecision(15)`。＝ `%.15g`。"""
    if math.isnan(x):
        # x86 の 0.0/0.0 は符号ビットが立つので "-nan" と出る（実測）
        return "-nan" if math.copysign(1.0, x) < 0 else "nan"
    if math.isinf(x):
        return "-inf" if x < 0 else "inf"
    return f"{x:.15g}"


def _cdiv(a, b):
    """C の `double / double`。0で割っても落ちずに inf / nan になる。"""
    if b == 0.0:
        if a == 0.0:
            return -math.nan          # x86 の 0.0/0.0（"-nan" と出る）
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def _head(a1, a2, a3, a4, tag):
    """1〜6行目の頭。どの関数も同じ形。"""
    return (f"{a1}\n{a2}\n{a3}\n{a4}\n{tag}\n65,{2086 - a2}")


def _write(path, body):
    """原本の `std::ofstream output_file(path)`。癖 4. のとおり落とす。"""
    with open(resolve(path), "w", encoding="ascii", newline="") as f:
        f.write(body)


def func13a(arg13a1, arg13a2, arg13a3, arg13a4, arg13a5):
    """prog13.cpp:6 の忠実移植。4区分の割合。

    arg13a1  性別（loop_var001）
    arg13a2  基準年齢（loop_var002）
    arg13a3  object01a.value001
    arg13a4  object01f.value001
    arg13a5  vector019（長さ4、int）
    """
    total = 0
    for i in range(4):
        total += arg13a5[i]
    out = [_head(arg13a1, arg13a2, arg13a3, arg13a4, "01")]
    for i in range(4):
        out.append("," + _g15(_cdiv(float(arg13a5[i]), float(total)) * 100.0))
    out.append("\n")
    _write(f"../rslt/01_{arg13a3}_{arg13a4}_{arg13a1}_{arg13a2}.csv",
           "".join(out))


def func13b(arg13b1, arg13b2, arg13b3, arg13b4, arg13b5):
    """prog13.cpp:25 の忠実移植。期間の長さ別の割合＋平均年数。

    arg13b5  vector020（長さ7、int）。`[6]` は月数の合計
    """
    total = 0
    for i in range(6):
        total += arg13b5[i]
    out = [_head(arg13b1, arg13b2, arg13b3, arg13b4, "02")]
    for i in range(6):
        out.append("," + _g15(_cdiv(float(arg13b5[i]), float(total)) * 100.0))
    # 平均年数。合計月数 / 人数 / 12（癖 2.）
    out.append("," + _g15(_cdiv(_cdiv(float(arg13b5[6]), float(total)),
                                12.0)))
    out.append("\n")
    _write(f"../rslt/02_{arg13b3}_{arg13b4}_{arg13b1}_{arg13b2}.csv",
           "".join(out))


def func13c(arg13c1, arg13c2, arg13c3, arg13c4, arg13c5):
    """prog13.cpp:45 の忠実移植。年金額の階級別の割合＋平均月額（万円）。

    arg13c5  vector021（長さ8、double）。`[7]` は平均月額（円）
    """
    # **int に double を足すので1回ごとに切り捨てる**（癖 1.）
    total = 0
    for i in range(7):
        total = int(total + arg13c5[i])
    out = [_head(arg13c1, arg13c2, arg13c3, arg13c4, "03")]
    for i in range(7):
        out.append("," + _g15(_cdiv(arg13c5[i], float(total)) * 100.0))
    out.append("," + _g15(arg13c5[7] / 10000.0))
    out.append("\n")
    _write(f"../rslt/03_{arg13c3}_{arg13c4}_{arg13c1}_{arg13c2}.csv",
           "".join(out))
