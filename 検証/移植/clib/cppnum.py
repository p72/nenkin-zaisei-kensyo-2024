# -*- coding: utf-8 -*-
"""
C++ の `std::stoi` / `std::stod` を Python で厳密に再現する
===========================================================
⑥分布推計はこの2つで CSV の値を数値にする（`prog05.cpp` ほか）。
⑤が使っていた C の `atof`（`clib` ではなく `emp_shushi/cnum.py` の
`c_atof`）とは**ふるまいが違う**ので分けてある。

    C の atof()        読めなければ 0.0 を返す（エラーにしない）
    C++ の std::stod() 読めなければ std::invalid_argument を投げる

原本は例外を捕まえていないので、読めない値があればその場で
`std::terminate` して落ちる。移植でも同じ所で例外にする。

`std::stoi` / `std::stod` の規格どおりのふるまい
------------------------------------------------
- 先頭の空白（`isspace`）を飛ばす
- 読める所まで読む。`"12abc"` は 12、`"1.5xyz"` は 1.5
- 1文字も読めなければ `std::invalid_argument`
- 範囲外なら `std::out_of_range`
  （`stoi` は int に収まらないとき、`stod` は double に収まらないとき）
- **`stod` は非正規化数でも投げる。** glibc の `strtod` は結果が
  アンダーフローすると `ERANGE` を立て、`std::stod` がそれを
  `std::out_of_range` に変える。0 に潰れる場合だけではない。実測で判明。
      "4.9406564584124654e-324" → out_of_range （最小の非正規化数）
      "2.2250738585072014e-308" → 正常          （DBL_MIN そのもの）
- `std::stoi` は基数10のとき `"0x10"` を **0** と読む（`x` で止まる）。
  C の `atof`/`strtod` が16進を読むのとは違う。
- `std::stod` は16進浮動小数（`"0x10"` → 16.0）も inf/nan も読む
  （`strtod` と同じ文法）

実測で確かめてある（`検証/移植/test_cppnum.py`）。
"""
import math
import re

__all__ = ["stoi", "stod", "CppInvalidArgument", "CppOutOfRange"]

_INT_MIN = -2147483648
_INT_MAX = 2147483647

# 正規化された double の最小値。これより小さい非ゼロは非正規化数で、
# glibc の strtod が ERANGE を立てる（std::stod は out_of_range を投げる）
_DBL_MIN = 2.2250738585072014e-308


class CppInvalidArgument(ValueError):
    """`std::invalid_argument` に対応。原本は捕まえないので落ちる。"""


class CppOutOfRange(ValueError):
    """`std::out_of_range` に対応。原本は捕まえないので落ちる。"""


# C++ の isspace（既定ロケール）が飛ばす文字
_WS = " \t\n\v\f\r"

# std::stoi（基数10）。符号＋数字列。`0x` は読まない（x で止まる）
_INT10 = re.compile(r"[+-]?[0-9]+")

# std::stod。strtod と同じ文法。16進浮動小数・inf・nan も読む
_HEXF = re.compile(
    r"[+-]?0[xX](?:[0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?|\.[0-9a-fA-F]+)"
    r"(?:[pP][+-]?[0-9]+)?")
_DECF = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_INFF = re.compile(r"[+-]?[iI][nN][fF](?:[iI][nN][iI][tT][yY])?")
_NANF = re.compile(r"[+-]?[nN][aA][nN](?:\([0-9a-zA-Z_]*\))?")


def stoi(s, base=10):
    """`std::stoi(s)` の忠実移植。基数は 10 のみ対応（原本は 10 しか使わない）。

    読めなければ `CppInvalidArgument`、int に収まらなければ
    `CppOutOfRange`。
    """
    if base != 10:
        raise NotImplementedError("基数10以外は未実装（原本は使わない）")
    i = 0
    n = len(s)
    while i < n and s[i] in _WS:
        i += 1
    m = _INT10.match(s, i)
    if m is None:
        raise CppInvalidArgument(f"stoi: 数値として読めない {s!r}")
    v = int(m.group(0))
    if v < _INT_MIN or v > _INT_MAX:
        raise CppOutOfRange(f"stoi: int に収まらない {s!r}")
    return v


def stod(s):
    """`std::stod(s)` の忠実移植。

    読めなければ `CppInvalidArgument`、double に収まらなければ
    `CppOutOfRange`（`strtod` が `ERANGE` を立てる場合）。
    """
    i = 0
    n = len(s)
    while i < n and s[i] in _WS:
        i += 1

    m = _HEXF.match(s, i)          # 16進を10進より先に
    if m:
        return float.fromhex(m.group(0))
    m = _DECF.match(s, i)
    if m:
        tok = m.group(0)
        v = float(tok)
        if math.isinf(v):
            # 10進の表記から inf になったのは範囲外
            raise CppOutOfRange(f"stod: double に収まらない {s!r}")
        # **非正規化数も範囲外扱い**。glibc の strtod は結果が
        # アンダーフローすると ERANGE を立て、std::stod はそれを
        # std::out_of_range に変える。0 に潰れる場合だけでなく、
        # 非正規化数（0 < |v| < DBL_MIN）でも投げる。実測で判明した
        #   "4.9406564584124654e-324"  → out_of_range
        #   "2.2250738585072014e-308"  → 正常（DBL_MIN そのもの）
        if v != 0.0 and abs(v) < _DBL_MIN:
            raise CppOutOfRange(f"stod: 非正規化数になる {s!r}")
        if v == 0.0 and _is_underflow(tok):
            raise CppOutOfRange(f"stod: double で 0 に潰れる {s!r}")
        return v
    m = _INFF.match(s, i)
    if m:
        return -math.inf if m.group(0)[:1] == "-" else math.inf
    m = _NANF.match(s, i)
    if m:
        return -math.nan if m.group(0)[:1] == "-" else math.nan
    raise CppInvalidArgument(f"stod: 数値として読めない {s!r}")


def _is_underflow(tok):
    """`"1e-400"` のように 0 でない表記が 0 に潰れたか。

    `strtod` はこの場合 `ERANGE` を立て、`std::stod` は
    `std::out_of_range` を投げる。ただし `"0"` や `"0.0"` は正当な 0。
    """
    t = tok.lstrip("+-")
    # 指数部を落とした仮数部に 0 以外の数字があるか
    mant = re.split(r"[eE]", t, maxsplit=1)[0]
    return any(c in "123456789" for c in mant)
