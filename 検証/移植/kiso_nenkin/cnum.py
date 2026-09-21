# -*- coding: utf-8 -*-
"""
基礎年金/stdfm.c の忠実移植（`read_str` / `read_data` / `Round` ほか）
=======================================================================
④の丸めは①の `raund` とも⑤の `nround` とも**別物**で、これで3種類目。

`Round(a, b)` — ①の `raund` とどう違うか
----------------------------------------
```c
/* ④ 基礎年金/stdfm.c:174 */
int Round( double a , int b )
{
    int c , d , i , S ;
    S = 1 ;
    for( i = 1 ; i <= b ; i++ ) S *= 10 ;
    a /= S ;                 /* ← ① は a *= S */
    d = (int)( a + 0.5 ) ;   /* ← ① は a>0 で分けて ±0.5 */
    c = d * S ;
    return( c ) ;            /* ← ① は double を返す */
}
```

違いは3つ。

1. **割ってから掛け戻す。**①は掛けてから割る。つまり④の `Round(x, 1)`
   は「10 の位への丸め」で、①の `raund(x, 1)` は「小数第1位への丸め」。
   向きが逆なので取り違えると桁が 100 倍ずれる。
2. **`int` を返す。**小数点以下は必ず消える。`double` に代入されるので
   呼び出し側では整数値の `double` になる。
3. **負の値で 0 方向に寄る。**`(int)(a + 0.5)` を場合分けせずに使うので、
   `a = -1.5` → `(int)(-1.0)` → `0`。①は `a - 0.5` を使うので `-2`。
   呼ばれるのは保険料月額（正）だけなので実データでは出ない。

`b = 0` のとき `S = 1` なので「整数への丸め」になる。原本の呼び出しは
`read_file.c:403` の `Round( Hokenryou_m , 1 )` だけ。

`g_round(a, n)` — econ.c だけが持つ別の丸め
--------------------------------------------
`econ.c:372` は `double round( double a , int n )` を**自前に定義**して
いる。C++ なので `std::round` とは多重定義で共存し、`econ.c` の中の
`round( x , 3 )` はこちらに解決される。中身は

```c
sprintf( buf , "%.*f" , n , a ) ; b = strtod( buf , &p ) ; return b ;
```

つまり「10進 n 桁に書き出して読み直す」。glibc の `printf` は正確な
2進値を10進に正しく丸める（最近接・偶数優先）ので、Python の
`"%.*f"` と1ビットも違わない。名前が衝突しないよう `g_round` にした。

`read_str` / `read_data` — カンマ区切りを `atof` で読む
--------------------------------------------------------
`read_str` が1行を文字列の配列に割り、`read_data` が `atof` を通す。
①の `read_csv` とほぼ同じ作りだが、上限が `DATA_MAX` = `BUFFER_MAX`
= 1000 と大きい。

原本の癖をそのまま残しているところ
----------------------------------
1. **`previous_c` が初期化されないまま読まれうる**（`stdfm.c:15,60`）。
   ①と同じ。行の1文字目が `'\\n'` だと `while` の本体が1回も回らず、
   `if( previous_c != ',' )` が未初期化の値を読む。移植版は①と同じく
   「`','` ではなかった」扱いにする（空行では `buffer[0]` に 0.0 が
   入り `data_number` は 0 になる）。

2. **`buffer` を読み切った個数より先は前回の値が残る。**`read_data` は
   `buffer[0..*data_number_ptr]` にしか書かない。呼び出し側の
   `double buffer[DATA_MAX]` は初期化のない自動変数なので、
   **1回目は不定値、2回目以降は前の行の値**が残る。読み込み側が
   列数より大きい添字を見ると前の行の値を拾う。
   移植版は `Buffer` クラスで「関数ごとに1本持ち回る list」として
   同じふるまいにし、最初は 0.0 にしておく（原本の1回目の不定値は
   再現できないので、出力がバイト一致することで到達しないと確かめる）。

3. **`read_str` の `s` は `char[1000]` で、長さの検査がカンマの時だけ。**
   1000 文字目の書き込みで配列の外に出る。同梱データの最長は
   20 数文字なので起きない。移植版は 1000 文字を超えたら例外にする。
"""
import math
import re
import time

from libc import c_atof, cdiv  # noqa: F401  （再輸出）
from setconst import BUFFER_MAX, DATA_MAX

__all__ = ["EOF", "CsvError", "c_atof", "cdiv", "Round", "g_round",
           "c_max", "c_min", "Buffer", "ReadStr", "chg_str",
           "asctime_now", "fmt_e", "fmt_f"]

EOF = -1

_INT_MIN = -2147483648
_INT_MAX = 2147483647

# `atof` と 0 割りの割り算は **`clib/libc.py` に移した**。
# ③国民年金も同じものを使うので、置き場を1つにしてある
# （`検証/移植/test_kiso_num.py` の突き合わせはそのまま効く）。
_WS = " \t\n\v\f\r"


class CsvError(Exception):
    """原本が `exit(1)` するか未定義動作に入る条件に当たった。"""


def _to_int(x):
    """C の `(int)double`。0方向へ切り捨て。範囲外は未定義動作。"""
    if math.isnan(x) or math.isinf(x):
        raise CsvError(f"Round: (int) に入らない値 {x!r}（原本は未定義動作）")
    t = math.trunc(x)
    if t < _INT_MIN or t > _INT_MAX:
        raise CsvError(
            f"Round: (int) に入らない値 {x!r}（原本は未定義動作。"
            "gcc/x86-64 では INT_MIN になる）")
    return t


def Round(a, b):
    """stdfm.c:174 の忠実移植。**10^b の位へ丸めた `int` を返す。**

    上の解説のとおり①の `raund` とは割る向きが逆で、戻り値が `int`。
    """
    S = 1
    for _ in range(1, b + 1):
        S = S * 10
        if S > _INT_MAX:
            raise CsvError("Round: 10 の冪が int に入らない（原本は未定義動作）")
    a = a / S
    d = _to_int(a + 0.5)
    c = d * S
    if c < _INT_MIN or c > _INT_MAX:
        raise CsvError("Round: 結果が int に入らない（原本は未定義動作）")
    return c


def g_round(a, n):
    """econ.c:372 の `round( double , int )`。10進 n 桁に丸める。

    `sprintf("%.*f")` → `strtod` と同じ。glibc も Python も正確な
    2進値を正しく丸めるので結果は1ビットも違わない。
    """
    return float("%.*f" % (n, a))


def c_max(a, b):
    """stdfm.c:194。`( a > b ) ? a : b`。nan の扱いまで原本と同じ。"""
    return a if a > b else b


def c_min(a, b):
    """stdfm.c:200。`( a < b ) ? a : b`。nan の扱いまで原本と同じ。"""
    return a if a < b else b


class Buffer(list):
    """呼び出し側の `double buffer[DATA_MAX]`（癖 2.）。

    原本は初期化のない自動変数で、同じ関数の中の `read_data` 呼び出しで
    使い回される。読み切った個数より先は**前の行の値が残る**。
    移植版もこの list を持ち回すことで同じふるまいになる。
    """

    def __init__(self, n=DATA_MAX):
        super().__init__([0.0] * n)


def chg_str(buf, str1, str2):
    """stdfm.c:117 の `chg_str`。`str1` を `str2` に全部置き換える。

    原本は `char *buf` を書き換えるので、移植版は置き換えた文字列を返す。
    `while( strstr( ... ) )` なので、`str2` が `str1` を含むと
    無限ループになる（原本の呼び出しでは起きない）。
    """
    if str1 and str1 in str2:
        # 原本はここで無限ループに落ちる。黙って進まず落とす
        raise CsvError(f"chg_str: 置換後の文字列が置換前を含む（{str1!r}）")
    return buf.replace(str1, str2)


# ---------------------------------------------------------------------------
# 出力の書式
# ---------------------------------------------------------------------------
_ASCTIME_WDAY = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
_ASCTIME_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def asctime_now():
    """stdfm.c:160 の `write_BeginData` が書く `asctime( localtime(...) )`。

    glibc の `asctime` は `"%.3s %.3s%3d %.2d:%.2d:%.2d %d\\n"`。
    日は**幅3の右詰め**（1桁なら前に空白2つ）なので `strftime` では
    そのまま作れない。ここで組み立てる。

    **時刻が入るので出力はその時刻ぶんだけ変わる。**原本との突き合わせは
    この行を除いて行う（`test_kiso_full.py`）。
    """
    t = time.localtime()
    return "%.3s %.3s%3d %.2d:%.2d:%.2d %d\n" % (
        _ASCTIME_WDAY[(t.tm_wday + 1) % 7], _ASCTIME_MON[t.tm_mon - 1],
        t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, t.tm_year)


def fmt_e(x, width=20, prec=14):
    """C の `%20.14e`（`%20.14le` も同じ。`l` は `double` では無視される）。

    Python の `%e` は指数を最低2桁で書くので glibc と同じ。
    `inf` / `nan` も同じ綴りになる。
    """
    return "%*.*e" % (width, prec, x)


def fmt_f(x, prec=6):
    """C の `%f`（既定は小数6桁）。"""
    return "%.*f" % (prec, x)


class ReadStr:
    """`stdfm.c:12` の `read_str` と `stdfm.c:96` の `read_data`。

    原本は `FILE *` を1文字ずつ `fgetc` で読む。移植版はファイルを
    バイト列で読み込んで、同じ位置を指す添字を持つ。
    数値は ASCII なので latin-1（バイト透過）で扱う。
    """

    def __init__(self, path):
        with open(path, "rb") as f:
            self._buf = f.read().decode("latin-1")
        self._i = 0
        self.path = path

    # ---- fgetc ----
    def _getc(self):
        if self._i >= len(self._buf):
            return EOF
        c = self._buf[self._i]
        self._i += 1
        return c

    def _fields(self):
        """`read_str` の1行を、原本と同じ切り方でフィールドの list にする。

        原本は1文字ずつ回すが、意味は「`'\\n'` か EOF までを `','` で
        割り、**行末が `','` なら最後の空フィールドは作らない**」と同じ。

            "1,2,3"   → ['1','2','3']   previous_c = '3' ≠ ','
            "1,2,3,"  → ['1','2','3']   previous_c = ','（最後を作らない）
            ""（空行） → ['']            previous_c は未初期化（癖 1.）

        戻り値は `(fields, rc)`。`rc` は `EOF` か 0。
        """
        buf = self._buf
        n = len(buf)
        i = self._i
        if i >= n:
            self._i = i
            # 1文字も読めずに EOF。原本は s が空のまま previous_c が
            # 未初期化なので、フィールド1つ（空文字）ができる（癖 1.）
            return [""], EOF
        j = buf.find("\n", i)
        if j < 0:
            line = buf[i:]
            self._i = n
            rc = EOF
        else:
            line = buf[i:j]
            self._i = j + 1
            rc = 0
        fields = line.split(",")
        tail_comma = line.endswith(",")
        if tail_comma:
            # previous_c == ',' なので最後のフィールドは作られない
            fields.pop()
        # 原本の `comma_number`（`','` の数＋行末が `','` でなければ 1）
        ncomma = line.count(",") + (0 if tail_comma else 1)
        if ncomma > DATA_MAX:
            raise CsvError(
                "エラー(in read_data) １行の中のカンマの数が"
                f"{DATA_MAX}個を超えています")
        for f in fields:
            if len(f) > BUFFER_MAX - 1:
                raise CsvError(
                    "エラー(in read_data) １つのデータの文字数が"
                    f"{BUFFER_MAX - 1}個を超えています")
        return fields, rc

    def read_str(self, buffer):
        """stdfm.c:12。`buffer` に文字列を入れ、`(戻り値, data_number)`。

        `buffer` は長さ `DATA_MAX` のリスト（原本の
        `char buffer[DATA_MAX][BUFFER_MAX]`）。戻り値は `EOF` か 0。
        原本と同じく**読み切った個数より先は書き換えない**。
        """
        fields, rc = self._fields()
        for k, f in enumerate(fields):
            buffer[k] = f
        return rc, len(fields) - 1

    def read_data(self, buffer):
        """stdfm.c:96。`buffer[0..data_number]` に `atof` の結果を入れる。

        `buffer` は `Buffer`（原本の `double buffer[DATA_MAX]`）。
        **読み切った個数より先は書き換えない**（癖 2.）。
        """
        fields, rc = self._fields()
        for k, f in enumerate(fields):
            # ふつうの10進表記は Python の `float` が C の `strtod` と
            # 同じに読む。`_` を含む（Python だけが受ける）ものと
            # `float` が投げるものは `c_atof` に回す
            try:
                if "_" in f:
                    raise ValueError
                buffer[k] = float(f)
            except ValueError:
                buffer[k] = c_atof(f)
        return rc, len(fields) - 1

    def read_headder(self):
        """stdfm.c:136。`#99-...` の行まで読み飛ばす。

        原本は `fgets( char_buffer , 256 , fp )` なので**256 バイトずつ**
        読む。1行が 255 バイトを超えると途中で切られ、続きが次の
        「行」として扱われる。同梱データのヘッダは短いので起きない。

        `sscanf( char_buffer , "#%d-%d-%d" , &seido , ... )` は
        **戻り値を見ていない**ので、`'#'` だけの行では `seido` が
        前の行の値（初回は不定値）のまま `== 99` と比べられる。
        移植版は「読めなければ前の値を残す」ことで同じふるまいにし、
        初回は `None`（99 ではない）にしておく。
        """
        seido = None
        while True:
            line = self._fgets(256)
            if line is None:
                return
            if line[:1] == "#":
                m = re.match(r"#\s*([+-]?\d+)", line)
                if m:
                    seido = int(m.group(1))
                if seido == 99:
                    return

    def _fgets(self, size):
        """C の `fgets( buf , size , fp )`。最大 size-1 バイト＋改行。"""
        if self._i >= len(self._buf):
            return None
        out = []
        while len(out) < size - 1:
            c = self._getc()
            if c == EOF:
                break
            out.append(c)
            if c == "\n":
                break
        return "".join(out)
