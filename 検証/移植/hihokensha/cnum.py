# -*- coding: utf-8 -*-
"""
被保険者推計/stdfm.c の忠実移植（`raund` / `read_csv` / `karayomi`）
====================================================================
①の丸めは⑤の `nround` とは**別物**なので、⑤の `emp_shushi/cnum.py` を
使い回さずにここに書く。

`raund(a, b)` — ⑤の `nround` とどう違うか
-----------------------------------------
⑤（`厚生年金/収支計算/stdfun.c`）は C99 の `round()` を使う。

```c
/* ⑤ */
double nround(double x, int n){ double p = pow(10.0, n); return round(x*p)/p; }
```

①（`被保険者推計/stdfm.c:8`）は `round()` を使わず、**`int` へのキャストで
自前に丸める**。

```c
/* ① */
S = 1 ;
for ( i = 1 ; i <= b ; i++ ) S *= 10 ;      /* S は int */
a = a * S ;
if ( a > 0.0 ) d = (int)( a + 0.5 ) ;       /* d は int */
else           d = (int)( a - 0.5 ) ;
c = (double) d / S ;
```

違いは3つ。

1. **`int` に入れるので 2^31 を超えると壊れる。**
   `round()` は `double` を返すので桁数の上限が無いが、`raund` は
   `|a × 10^b| >= 2147483648` で未定義動作になる（gcc/x86-64 では
   `INT_MIN` に落ちる）。人数（万人単位）と割合しか通らないので
   実データでは起きない。
2. **10 の冪を `pow` でなく `int` の掛け算で作る。**
   `10^b` は `b <= 9` なら `int` で正確なので、結果は `pow` と同じ。
   `b >= 10` で `S` があふれる（`b = 10` で 1410065408）。
3. **`a > 0.0`（`>=` ではない）で分ける。**
   `a == 0.0` のとき `else` に入って `(int)(-0.5) == 0` になるので、
   結果は `+0.0`。C99 の `round(-0.0)` は `-0.0` を返すが、こちらは
   **`-0.0` を作らない**（`(int)` を経由するので符号が消える）。

丸めの向きは「0 から遠い方へ」で C99 の `round()` と同じ。
`0.5` ちょうどは切り上げ（負なら切り下げ）になる。

`b < 0` のときは掛けるかわりに割り、最後に掛け戻す。

`read_csv` — カンマ区切りを `atof` で読む
-----------------------------------------
`stdfm.c:55`。1行を読んで `buffer[0..]` に `atof` の結果を入れ、
読めた個数 − 1 を `*data_number_ptr` に返す。戻り値は `EOF` か 0。

原本の癖をそのまま残しているところ
----------------------------------
1. **`previous_c` が初期化されないまま読まれうる**（`stdfm.c:57,90`）
   `while` の中で `previous_c = c` を入れているが、**行の1文字目が
   `'\\n'` だと本体が1回も回らない**ので、`if (previous_c != ',')` が
   未初期化の値を読む（未定義動作）。空行を読むと起きる。
   移植版は「本体が回らなかった」ことを覚えて、原本の gcc/x86-64 での
   ふるまい（スタックに残った値。ほぼ常に `','` ではない）に合わせて
   **`','` ではなかった扱い**にしている。つまり空行では `buffer[0]` に
   `atof("")` ＝ 0.0 が入り、`data_number` は 0 になる。
   （`検証/原本の不具合.md`）

2. **1つのデータが31文字を超えるとスタックを壊す**（`stdfm.c:60,85`）
   `char s[BUFFER_MAX]`（31バイト）に `*sptr++ = c` で詰めていくが、
   文字数の検査はカンマが来たときにしかしない。32文字目の書き込みで
   配列の外に出る。同梱データの最長は十数文字なので起きない。
   移植版は Python の list なので伸びるだけ。**31文字を超えたら
   例外にする**（黙って違う結果を出さないため）。

3. **行末のフィールドも読む。** `previous_c != ','` のとき、最後の
   フィールドをもう1つ読む。⑤の `rd_drec`（行末のフィールドを捨てる）
   とは逆のふるまい。

`karayomi(fp)` は1行読み飛ばすだけ（`stdfm.c:116`）。
"""
import math
import re

from setconst import BUFFER_MAX, DATA_MAX

__all__ = ["raund", "c_atof", "cdiv", "ReadCsv", "CsvError", "EOF"]

EOF = -1

_INT_MIN = -2147483648
_INT_MAX = 2147483647

# C の strtod が読む10進表記（16進浮動小数と inf/nan も読む）。
# ⑤の cnum.c_atof と同じ文法。①も同じ libc の atof を呼ぶ
_HEXF = re.compile(
    r"[+-]?0[xX](?:[0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?|\.[0-9a-fA-F]+)"
    r"(?:[pP][+-]?[0-9]+)?")
_DECF = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_INFF = re.compile(r"[+-]?[iI][nN][fF](?:[iI][nN][iI][tT][yY])?")
_NANF = re.compile(r"[+-]?[nN][aA][nN](?:\([0-9a-zA-Z_]*\))?")
_WS = " \t\n\v\f\r"


class CsvError(Exception):
    """原本が `exit(1)` する条件に当たった。"""


def c_atof(s):
    """C の `atof`。読めなければ 0.0（エラーにしない）。

    ⑤の `emp_shushi/cnum.py` の `c_atof` と同じもの。①も同じ libc を
    呼ぶので、同じふるまいになる。16進浮動小数も読む。
    """
    i = 0
    n = len(s)
    while i < n and s[i] in _WS:
        i += 1
    m = _HEXF.match(s, i)
    if m:
        try:
            return float.fromhex(m.group(0))
        except (ValueError, OverflowError):
            return 0.0
    m = _DECF.match(s, i)
    if m:
        try:
            return float(m.group(0))
        except (ValueError, OverflowError):
            return 0.0
    m = _INFF.match(s, i)
    if m:
        return -math.inf if m.group(0)[:1] == "-" else math.inf
    m = _NANF.match(s, i)
    if m:
        return -math.nan if m.group(0)[:1] == "-" else math.nan
    return 0.0


def cdiv(a, b):
    """C の `double / double`。**0 で割っても落ちない。**

    Python の `float / float` は `ZeroDivisionError` を投げるが、C は
    IEEE 754 どおり `±inf`（分子が 0 以外）か `nan`（0/0）を返す。
    ①には分母のゼロを確かめていない割り算がいくつもあり、実データでも
    **配列の端（`ENDY` の年度など）で 0/0 が起きる**。そこで出た nan は
    出力される年度（`KF` = 2125 まで）には届かないが、途中で落ちては
    原本と挙動が違ってしまう。

    `0.0/0.0` は x86 で符号ビットが立つので `printf` に `-nan` と出る
    （⑥で実測。`検証/原本の不具合.md` G1 と同じ確認のしかた）。
    """
    if b == 0.0:
        if a == 0.0:
            return -math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def _to_int(x):
    """C の `(int)double`。0方向へ切り捨て。範囲外は未定義動作。

    gcc/x86-64 の `cvttsd2si` は範囲外で `INT_MIN`（0x80000000）を返す。
    原本がそこに入ると結果が壊れるので、移植版は**例外にする**。
    """
    if math.isnan(x) or math.isinf(x):
        raise CsvError(f"raund: (int) に入らない値 {x!r}（原本は未定義動作）")
    t = math.trunc(x)
    if t < _INT_MIN or t > _INT_MAX:
        raise CsvError(
            f"raund: (int) に入らない値 {x!r}（原本は未定義動作。"
            "gcc/x86-64 では INT_MIN になる）")
    return t


def raund(a, b):
    """stdfm.c:8 の忠実移植。0 から遠い方向へ丸める。

    `b > 0` なら小数第 `b` 位、`b == 0` なら整数、`b < 0` なら
    10^|b| の位に丸める。

    上の解説のとおり `int` を経由するので、`|a × 10^b|` が 2^31 を
    超えると原本は壊れる。移植版はそこで例外にする。
    """
    S = 1
    if b > 0:
        for _ in range(1, b + 1):
            S = _wrap_int(S * 10)
        a = a * S
        d = _to_int(a + 0.5) if a > 0.0 else _to_int(a - 0.5)
        return float(d) / S
    elif b == 0:
        d = _to_int(a + 0.5) if a > 0.0 else _to_int(a - 0.5)
        return float(d) / 1
    else:
        i = -1
        while i >= b:
            S = _wrap_int(S * 10)
            i -= 1
        a = a / S
        d = _to_int(a + 0.5) if a > 0.0 else _to_int(a - 0.5)
        return float(d) * S


def _wrap_int(v):
    """`int` の掛け算のあふれ。原本は未定義動作なので例外にする。

    `b >= 10` で起きる（`10^10` は `int` に入らない）。原本の呼び出しは
    すべて `b <= 4` なので到達しない。
    """
    if v < _INT_MIN or v > _INT_MAX:
        raise CsvError("raund: 10 の冪が int に入らない（原本は未定義動作）")
    return v


class ReadCsv:
    """`stdfm.c:55` の `read_csv` と `stdfm.c:116` の `karayomi`。

    原本は `FILE *` を1文字ずつ `fgetc` で読む。移植版はファイルを
    バイト列で読み込んで、同じ位置を指す添字を持つ。

    数値は ASCII なので latin-1（バイト透過）で扱う。
    """

    def __init__(self, path):
        with open(path, "rb") as f:
            self._buf = f.read().decode("latin-1")
        self._i = 0

    # ---- fgetc ----
    def _getc(self):
        if self._i >= len(self._buf):
            return EOF
        c = self._buf[self._i]
        self._i += 1
        return c

    def karayomi(self):
        """stdfm.c:116。`'\\n'` か EOF まで読み飛ばす。"""
        while True:
            c = self._getc()
            if c == EOF or c == "\n":
                return

    def read_csv(self, buffer):
        """stdfm.c:55。`buffer` を書き換え、`(戻り値, data_number)` を返す。

        `buffer` は長さ `DATA_MAX` のリスト（原本の `double buffer[130]`）。
        戻り値は `EOF` か 0。
        """
        data_number = -1
        comma_number = 0
        s = []
        # 原本の `int previous_c;` は初期化されていない（癖 1.）。
        # 本体が1回も回らなければ未初期化のまま読まれる。ここでは
        # 「',' ではなかった」に当たる値を入れておく
        previous_c = None
        c = EOF
        while True:
            c = self._getc()
            if c == EOF or c == "\n":
                break
            if c == ",":
                comma_number += 1
                if comma_number > DATA_MAX:
                    raise CsvError(
                        "エラー(in read_data) １行の中のカンマの数が"
                        f"{DATA_MAX}個を超えています。")
                if len(s) > BUFFER_MAX - 1:
                    raise CsvError(
                        "エラー(in read_data) １つのデータの文字数が"
                        f"{BUFFER_MAX - 1}個を超えています。")
                data_number += 1
                buffer[data_number] = c_atof("".join(s))
                s = []
            else:
                s.append(c)
                if len(s) > BUFFER_MAX:
                    # 原本はここでスタックを壊す（癖 2.）
                    raise CsvError(
                        f"read_csv: 1つのデータが {BUFFER_MAX} 文字を"
                        "超えた（原本は s[31] の外に書き込む）")
            previous_c = c

        # 原本の `if (previous_c != ',')`
        if previous_c != ",":
            comma_number += 1
            if comma_number > DATA_MAX:
                raise CsvError(
                    "エラー(in read_data) １行の中のカンマの数が"
                    f"{DATA_MAX}個を超えています。")
            if len(s) > BUFFER_MAX - 1:
                raise CsvError(
                    "エラー(in read_data) １つのデータの文字数が"
                    f"{BUFFER_MAX - 1}個を超えています。")
            data_number += 1
            buffer[data_number] = c_atof("".join(s))

        return (EOF if c == EOF else 0), data_number
