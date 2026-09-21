# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/lib/_csvio.h と sepslib.cpp の `csvio` 名前空間
=====================================================================
②の CSV の読み書き。`split` / `getnums` / `read` / `skip` / `join` と、
逐次出力の `print_int` / `add_dbl` などから成る。

読み込みの流れ
--------------
    read(fp, begin, end)
      → fgets( __csvio_buf , 10000 , fp )
      → getnums( __csvio_buf , begin , end )
          → split( str , begin , end )      カンマで割る
          → trim → atof                     1つずつ数に直す

`begin` は「先頭から何個読み飛ばすか」、`end` は「何個目まで取るか」
（どちらも1始まりの数え方で、`counter <= begin` を飛ばし
`counter > end` で止める）。

原本の癖をそのまま残しているところ
----------------------------------
1. **カンマが1つも無い行は同じ値が2つ返る**（`sepslib.cpp:70-93`）。

   ```cpp
   string::size_type last = str.find_first_of(',');   /* npos になりうる */
   while(first < str.size()) {
     ... push_back( string(str, first, last - first) ) ;
     first = last + 1;                    /* npos + 1 == 0（符号なし） */
     last = str.find_first_of(',', first);
     if(last == string::npos) last = str.size();
   }
   ```

   1周目で `last` が `npos` のままなので、`string(str, 0, npos)` は
   文字列の末尾までを取る。そのあと `first = npos + 1` が**0 に戻る**
   ので、2周目でまったく同じ文字列をもう1つ積む。3周目は
   `first = size + 1` で止まる。
   つまりカンマ無しの行は**同じ要素が2つ**並ぶ。
   （`検証/原本の不具合.md`）

2. **`fgets` の戻り値を見ていない**（`_csvio.h:26,36,42`）。
   EOF に当たると `__csvio_buf` が**前の行のまま**なので、同じ行を
   もう一度読んだのと同じ結果になる。行数を数えて読む作りなので
   同梱データでは起きない。

3. **`__csvio_buf` が `static` でヘッダに書いてある**（`_csvio.h:12`）。
   `static` なので**翻訳単位ごとに別の実体**ができる。34本の .cpp が
   それぞれ 10,000 バイトのバッファを持つ（340KB）。1回の呼び出しの
   中で読んで使い切るので、ふるまいは変わらない。

4. **`getnums` が `atof` を `try` で囲んでいる**（`sepslib.cpp:124-130`）。
   `atof` は例外を投げないので `catch` に入らない。`std::stod` と
   間違えたものと思われる（⑥の `prog04` にも同じ形がある）。

5. **`add_dbl` が書式文字列を書き換える**（`_csvio.h:59`）。
   `fmt.insert(0, ",")` で先頭にカンマを足す。引数は値渡しなので
   呼び出し側の文字列は変わらない。
"""
import sys

from sepsstd import c_atof, fmt as _fmt, trim

__all__ = ["split", "getnums", "join", "Reader", "INT_MAX",
           "print_int", "print_dbl", "add_int", "add_dbl", "line_feed"]

INT_MAX = 2147483647
BUF_SIZE = 10000


def split(s, begin=0, end=INT_MAX):
    """sepslib.cpp:70 の `split`。カンマで割って `begin`〜`end` を返す。

    `begin` 個を読み飛ばし、`end` 個目までを取る（1始まりの数え方）。
    カンマが無い行で同じ値が2つ返る癖もそのまま（癖 1.）。
    """
    first = 0
    last = s.find(",")
    if last < 0:
        last = _NPOS
    out = []
    counter = 0
    n = len(s)
    while first < n:
        counter += 1
        if counter <= begin:
            pass
        elif counter > end:
            break
        else:
            # C++ の `string(str, first, last - first)`。長さが文字列を
            # はみ出しても末尾までで止まる
            if last is _NPOS:
                out.append(s[first:])
            else:
                out.append(s[first:first + (last - first)])

        # `first = last + 1`。`last` が npos なら 0 に戻る（癖 1.）
        first = 0 if last is _NPOS else last + 1
        idx = s.find(",", first)
        last = n if idx < 0 else idx
    return out


class _Npos:
    """C++ の `string::npos`。`+1` で 0 に戻ることを表すための番兵。"""

    def __repr__(self):
        return "npos"


_NPOS = _Npos()


def getnums(s, begin=0, end=INT_MAX):
    """sepslib.cpp:116 の `getnums`。`split` の結果を `trim` → `atof`。"""
    if begin < 0:
        raise ValueError("begin = %d" % begin)
    if begin > end:
        raise ValueError("begin > end: %d > %d" % (begin, end))
    return [c_atof(trim(x)) for x in split(s, begin, end)]


def join(vals, format="%.14e"):
    """sepslib.cpp:96,99 の `join`。既定の書式は `%.14e`。

    原本は `join(format, vals)` と `join(vals)` の2つ。引数の順が
    Python では書きにくいので、こちらは `vals` を先にした。
    """
    return ",".join(_fmt(format, v) for v in vals)


class Reader:
    """`_csvio.h` の `read` / `read_str` / `skip`（`FILE *` の代わり）。

    原本は `fgets( __csvio_buf , BUF_SIZE , fp )` で**最大 9,999 バイト**
    ずつ読む。行が長ければ途中で切られ、続きが次の「行」になる。
    ②の入力でいちばん長い行は 1,700 バイトほどなので起きない。

    `fgets` の戻り値を見ていないので、EOF では `__csvio_buf` が前の行の
    まま残る（癖 2.）。移植版も同じく前の行を返す。
    """

    def __init__(self, path, mode="r"):
        with open(path, "rb") as f:
            self._buf = f.read().decode("latin-1")
        self._i = 0
        self.path = path
        self.mode = mode
        # `__csvio_buf` に相当する。EOF では前の行が残る
        self._line = ""

    def _fgets(self, size=BUF_SIZE):
        """C の `fgets`。読めなければ `__csvio_buf` を変えない。"""
        if self._i >= len(self._buf):
            return None
        out = []
        while len(out) < size - 1:
            c = self._buf[self._i]
            self._i += 1
            out.append(c)
            if c == "\n" or self._i >= len(self._buf):
                break
        self._line = "".join(out)
        return self._line

    def read(self, begin=0, end=INT_MAX):
        """`_csvio.h:24` の `read( fp , begin , end )`。"""
        self._fgets()
        return getnums(self._line, begin, end)

    def read_str(self):
        """`_csvio.h:34` の `read_str( fp )`。"""
        self._fgets()
        return split(self._line)

    def skip(self, lines=1):
        """`_csvio.h:39` の `skip( fp , lines )`。"""
        for _ in range(lines):
            self._fgets()

    @property
    def line(self):
        """いま `__csvio_buf` に入っている行。

        原本の `char buf[BUF_SIZE]` に `fgets` してから
        `csvio::getnums(buf)` に渡す書き方（`waku.cpp` など）を
        写すために使う。
        """
        return self._line

    def fgets(self, size=BUF_SIZE):
        """原本が `fgets( buf , BUF_SIZE , fp )` と直に書くところ用。"""
        return self._fgets(size)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# csvio::sequential — 1つずつ書き出す
# ---------------------------------------------------------------------------
def print_int(fp, val):
    """`_csvio.h:48`。`fprintf( fp , "%d" , val )`。"""
    fp.write("%d" % val)


def print_dbl(fp, format, val):
    """`_csvio.h:51`。`fprintf( fp , fmt , val )`。"""
    fp.write(_fmt(format, val))


def add_int(fp, val):
    """`_csvio.h:54`。`fprintf( fp , ",%d" , val )`。"""
    fp.write(",%d" % val)


def add_dbl(fp, format, val):
    """`_csvio.h:57`。書式の先頭に `,` を足して書く（癖 5.）。"""
    fp.write(_fmt("," + format, val))


def line_feed(fp):
    """`_csvio.h:62`。`fprintf( fp , "%s" , "\\n" )`。"""
    fp.write("\n")
