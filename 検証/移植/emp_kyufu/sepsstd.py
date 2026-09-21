# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/lib/_sepsstd.h と sepslib.cpp の `sepsstd` 名前空間
=========================================================================
②は自前の小さな標準ライブラリを持っている。⑥分布推計と同じ
`lib/` `common/` `ext/` の構えだが、**中身は別物**（⑥のヘッダと
`diff` を取るとどれも違う）。

移植するもの
------------
    to_string(int)     `snprintf("%d")`
    to_string(double)  `snprintf("%lf")`    ← `%f` と同じ（小数6桁）
    trim(str)          既定の空白集合は `"\\t\\v\\r\\n"`（**半角空白を含まない**）
    dparse(str)        `atof(trim(str))`
    format(fmt, ...)   `snprintf` で書式化
    roundn(val, n)     `round( val * 10^n ) / 10^n`
    subc1〜subc6       多次元 vector の一部を 0 で埋める

`trim` の空白集合に半角空白が入っていない
-----------------------------------------
```cpp
string trim(const string str) {
  return trim(str, "\t\v\r\n");     /* ' ' が無い */
}
```

`dparse` が `atof(trim(str))` を呼ぶが、`atof` は先頭の空白を読み飛ばす
ので前は問題にならない。**後ろの半角空白**は `atof` が数値の後で
止まるのでこれも問題にならない。つまり結果は変わらないが、
「trim なのに空白が残る」のは意図と違う可能性がある。
（`検証/原本の不具合.md`）

`roundn` は⑤の `nround` と同じ
------------------------------
```cpp
inline double roundn(double val, int n) {
  return round(val * pow(10.0, n)) / pow(10.0, n);
}
```

C99 の `round()`（0 から遠い方へ）を使う。⑤の
`厚生年金/収支計算/stdfun.c` の `nround` と**1文字違わず同じ式**なので、
`clib/libc.py` の `c_round` をそのまま使う。①の `raund`（`int` 経由）と
④の `Round`（割る向きが逆・`int` を返す）とは別物。

`subc*` は「0 で埋める」だけ
----------------------------
`v.at(i) = 0.0` を入れ子に回すだけ。範囲は呼び出し側が渡す
（`from` 〜 `to` で**両端を含む**）。移植版はスライス代入にする。
`vector::at()` は範囲外で例外を投げるので、原本は範囲外を渡すと
`std::out_of_range` で落ちる（移植版は NumPy の添字エラーになる）。
"""
import importlib.util
import math
import os

# ⑤で C と突き合わせ済みの `c_round` と `c_atof` をそのまま使い回す。
# `sys.path` はいじらない（`setconst.py` などが他のシステムと衝突するため。
# `検証/移植/portpath.py` と `clib/libc.py` と同じやり方）
_CNUM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "emp_shushi", "cnum.py")
_spec = importlib.util.spec_from_file_location("_emp_cnum_for_kyufu", _CNUM)
_cnum = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cnum)

c_round = _cnum.c_round
c_atof = _cnum.c_atof

__all__ = ["to_string", "to_string_int", "trim", "dparse", "fmt",
           "roundn", "subc", "std_max", "std_min", "TRIM_CHARS",
           "c_round", "c_atof"]

# `trim` の既定の空白集合（**半角空白を含まない**）
TRIM_CHARS = "\t\v\r\n"


def to_string(val):
    """sepslib.cpp:8 の `to_string(double)`。`snprintf("%lf")`。

    `%lf` は `double` では `%f` と同じ（小数6桁）。
    """
    return "%f" % val


def to_string_int(val):
    """sepslib.cpp:13 の `to_string(int)`。`snprintf("%d")`。"""
    return "%d" % val


def trim(s, blank_charset=TRIM_CHARS):
    """sepslib.cpp:19,22 の `trim`。両端から `blank_charset` を落とす。

    見つからなければ `""` を返す（原本と同じ）。
    """
    left = None
    for i, ch in enumerate(s):
        if ch not in blank_charset:
            left = i
            break
    if left is None:
        return ""
    right = len(s) - 1
    while right >= 0 and s[right] in blank_charset:
        right -= 1
    return s[left:right + 1]


def dparse(s):
    """_sepsstd.h:21 の `dparse`。`atof( trim(str) )`。"""
    return c_atof(trim(s))


def fmt(f, *args):
    """_sepsstd.h の `format`。`snprintf` の書式をそのまま使う。

    Python の `%` 書式は C の `printf` と同じ綴りなので、そのまま渡す。
    `%lf` `%le` `%ld` の `l` だけは Python が受けないので落とす。
    """
    return _strip_l(f) % args


def _strip_l(f):
    """`%20.14le` のような `l` 修飾子を落とす（`double` では無意味）。"""
    out = []
    i = 0
    n = len(f)
    while i < n:
        c = f[i]
        out.append(c)
        i += 1
        if c != "%":
            continue
        # 変換指定を読み切る
        while i < n and f[i] in "-+ #0123456789.*'":
            out.append(f[i])
            i += 1
        while i < n and f[i] in "hlLqjzt":
            i += 1                      # 長さ修飾子を捨てる
        if i < n:
            out.append(f[i])
            i += 1
    return "".join(out)


def roundn(val, n):
    """_sepsstd.h:100 の `roundn`。⑤の `nround` と同じ式。"""
    p = math.pow(10.0, n)
    return c_round(val * p) / p


def std_max(a, b):
    """C++ の `std::max(a, b)`。`a < b ? b : a`。

    **等しいときは `a` を返す**（`-0.0` と `0.0` のような区別が残る）。
    Python の `max` は同じ規則だが、はっきりさせるために書いておく。
    """
    return b if a < b else a


def std_min(a, b):
    """C++ の `std::min(a, b)`。`b < a ? b : a`。等しいときは `a`。"""
    return b if b < a else a


def subc(v, *ranges):
    """sepslib.cpp:31-60 の `subc1`〜`subc6`。`from`〜`to`（両端込み）を 0 に。

    原本は次元ごとに別の関数だが、中身は同じ入れ子。移植版は
    NumPy のスライス代入1行にまとめる。
    """
    idx = tuple(slice(ranges[i], ranges[i + 1] + 1)
                for i in range(0, len(ranges), 2))
    v[idx] = 0.0
