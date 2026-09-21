# -*- coding: utf-8 -*-
"""
国民年金/stdfm.c の忠実移植（入出力と小さな道具）
==================================================
394 行。CSV の読み込み、文字列の置換、`max`/`min`、0 割りを避ける
割り算、45年化オプションの年齢の伸ばし方。

`read_str` の `buffer` は**呼び出し側が持ち回す**
--------------------------------------------------
```c
int read_str( char buffer[][BUFFER_MAX] , FILE *fp , int *data_number_ptr )
```

`buffer` は呼ぶ側の配列で、`read_str` は**読めた欄だけ**書き換える。
`read_data` も

```c
for (i = 0 ; i <= *data_number_ptr ; i++ ) buffer[i] = atof(buffer_str[i]);
```

と `data_number` までしか入れない。呼ぶ側が同じ配列を使い回すと
**前の行の値が残る**。移植版も可変長リストを渡して同じにする
（`Buffer` クラス）。

`previous_c` が初期化されないまま読まれうる
-------------------------------------------
```c
int c;
int previous_c;          /* 初期化なし */
...
while( ( ( c = fgetc(fp) ) != EOF ) && ( c != '\\n' ) ) { … previous_c = c; }
if( previous_c != ',' ) { … }
```

**空行**（1文字目が `\\n`）だと `while` の中身が1回も走らないので
`previous_c` は未初期化。①④⑤にも同じ形がある
（`検証/原本の不具合.md` B4・B7）。同梱のデータに空行は無いので
起きない。移植版は `previous_c = None` で始めて、`None != ','` が
真になる側（ごみが偶然 `,` でない場合）に合わせる。

`c` も未初期化で読まれうる
--------------------------
```c
if( c == EOF ) return(EOF); else return(0);
```

`while` の条件で必ず `c` に代入されるので、こちらは無害
（条件の評価が1回は走る）。

`buffer_set1` / `buffer_set2` の `printf` が壊れている
------------------------------------------------------
```c
printf( "%sデータが不正です。buffer[0]=%d\\n" , msg,buffer[0] );
```

`buffer[0]` は `double` なのに `%d` で受けている。**未定義動作**。
さらに EOF の枝は

```c
printf( "%sデータ読み込み中にEOFを検出しました。\\n" );
```

と **`%s` に渡す引数が無い**。どちらも `exit(1)` する直前の
エラー表示なので、正常な入力では通らない。移植版は例外にする。

`array_sum` の引数名が `max`/`min` を隠す
-----------------------------------------
```c
double max( double a , double b );
double min( double a , double b );
...
double array_sum( double x[] , int min , int max )
{
  for( i = min ; i < max ; i++ ) sum += x[i];
}
```

引数の名前が同じファイルで定義している関数 `min`/`max` を隠すので、
`array_sum` の中では `min()`/`max()` を呼べない。呼んでいないので
害は無い。**上限は `i < max` で「含まない」**ので、呼ぶ側は
`array_sum(x, 1, MENJO_JOKYO)` のように1つ大きい値を渡す。

45年化オプションの4つ（`extenda`〜`extendd`）
---------------------------------------------
`Option == 1`（基礎年金の45年化）のときだけ効く。拠出年齢の上限を
60歳から `OP_MAX_KYOSHUTU_NENREI`（65歳）まで
`OP_HIKIAGE_KANKAKU` 年ごとに1歳ずつ上げていく。

    encho_year(nendo)          その年度までに何歳上がったか（0〜5）
    encho_nensu(nendo, nenrei) その生年の人が何歳ぶん延びるか
    extenda  延びた期間の中の年齢（60 + 延び 〜 65）
    extendb  延びる前の年齢（60 〜 60 + 延び − 1）
    extendc  延びの境目（ちょうど 60 + 延び）
    extendd  65歳超〜70歳

`encho_nensu` は `while( k < encho_year( nendo - nenrei + 60 + k ) )` と
**`k` を自分の条件の中で使う**ので、生年（`nendo - nenrei`）が
60歳になる年度を起点に、延びたぶんだけ後ろにずらして数え直す。
`max_hikiage_nensu` = 65 − 60 = 5 で止まる。
"""
import math

from libc import c_atof
from setconst import (BUFFER_MAX, DATA_MAX, EPSILON, MAX_KYOSHUTU_NENREI,
                      OP_MAX_KYOSHUTU_NENREI)

__all__ = ["EOF", "NatError", "Buffer", "read_str", "read_data",
           "buffer_set1", "buffer_set2", "data_skip", "chg_str",
           "read_headder", "write_BeginData", "c_max", "c_min",
           "nenkin_fdiv", "array_sum", "encho_year", "encho_nensu",
           "extenda", "extendb", "extendc", "extendd"]

EOF = -1


class NatError(Exception):
    """原本が `exit(1)` するか未定義動作に入る条件に当たった。"""


class Buffer(object):
    """呼ぶ側が持ち回す `double buffer[]` / `char buffer[][]`。

    `read_str` / `read_data` は `data_number` までしか書き換えないので、
    **それより後ろは前の行の値が残る**。原本と同じにするため、
    添字で読み書きできる薄い入れ物にしている。

    原本の配列は `double buffer[BUFFER_MAX]`（呼ぶ側によっては
    `[DATA_MAX]`）で、範囲の外に出れば未定義動作。移植版は
    `NatError` にする。
    """

    __slots__ = ("num", "str", "data_number")

    def __init__(self, n=DATA_MAX):
        self.num = [0.0] * n            # `double buffer[]`
        self.str = [""] * n             # `char buffer[][BUFFER_MAX]`
        self.data_number = -1

    def __getitem__(self, i):
        return self.num[i]

    def __setitem__(self, i, v):
        self.num[i] = v

    def __len__(self):
        return len(self.num)


def read_str(buf, fp):
    """stdfm.c:15 の忠実移植。`buf.str` を書き換え、EOF か 0 を返す。"""
    data_number = -1
    comma_number = 0
    s = []
    c = None
    previous_c = None       # 原本は未初期化（空行だとここが読まれる）

    while True:
        ch = fp.read(1)
        c = EOF if ch == "" else ch
        if c == EOF or c == "\n":
            break
        if c == ",":
            comma_number += 1
            if comma_number > DATA_MAX:
                raise NatError(
                    "エラー(in read_data) １行の中のカンマの数が"
                    "%d個を超えています" % DATA_MAX)
            if len(s) > BUFFER_MAX - 1:
                raise NatError(
                    "エラー(in read_data) １つのデータの文字数が"
                    "%d個を超えています" % (BUFFER_MAX - 1))
            data_number += 1
            if data_number >= len(buf.str):
                raise NatError(
                    "read_str: buffer の外に書こうとした（%d 欄目）。"
                    "原本は未定義動作" % data_number)
            buf.str[data_number] = "".join(s)
            s = []
        else:
            s.append(c)
        previous_c = c

    if previous_c != ",":
        comma_number += 1
        if comma_number > DATA_MAX:
            raise NatError(
                "エラー(in read_data) １行の中のカンマの数が"
                "%d個を超えています" % DATA_MAX)
        if len(s) > BUFFER_MAX - 1:
            raise NatError(
                "エラー(in read_data) １つのデータの文字数が"
                "%d個を超えています" % (BUFFER_MAX - 1))
        data_number += 1
        if data_number >= len(buf.str):
            raise NatError(
                "read_str: buffer の外に書こうとした（%d 欄目）。"
                "原本は未定義動作" % data_number)
        buf.str[data_number] = "".join(s)

    buf.data_number = data_number

    if c == EOF:
        return EOF
    return 0


def read_data(buf, fp):
    """stdfm.c:99 の忠実移植。`buf.num` を `data_number` まで書き換える。"""
    value = read_str(buf, fp)
    for i in range(0, buf.data_number + 1):
        buf.num[i] = c_atof(buf.str[i])
    return value


def buffer_set1(buf, fp, buf_0, msg):
    """stdfm.c:119 の忠実移植。1つ目の欄が `buf_0` であることを確かめる。"""
    if read_data(buf, fp) != EOF:
        if int(buf.num[0]) != buf_0:
            # 原本は `%d` に double を渡す（未定義動作）
            raise NatError("%sデータが不正です。buffer[0]=%s"
                           % (msg, buf.num[0]))
    else:
        # 原本は `%s` に渡す引数が無い（未定義動作）
        raise NatError("%sデータ読み込み中にEOFを検出しました。" % msg)
    return 0


def buffer_set2(buf, fp, buf_0, buf_1, msg):
    """stdfm.c:139 の忠実移植。1つ目と2つ目の欄を確かめる。"""
    if read_data(buf, fp) != EOF:
        if int(buf.num[0]) != buf_0 or int(buf.num[1]) != buf_1:
            raise NatError("%sデータが不正です。buffer[0]=%s , buffer[1]=%s"
                           % (msg, buf.num[0], buf.num[1]))
    else:
        raise NatError("%sデータ読み込み中にEOFを検出しました。" % msg)
    return 0


def data_skip(fp, cnt):
    """stdfm.c:159 の忠実移植。`cnt` 行読み捨てる。

    原本は `double buffer[BUFFER_MAX]` を局所に取るので、呼ぶ側の
    `buffer` は汚れない。移植版も局所の `Buffer` を使う。
    """
    buf = Buffer(BUFFER_MAX)
    for _i in range(0, cnt):
        read_data(buf, fp)
    return 0


def chg_str(buf, str1, str2):
    """stdfm.c:174 の忠実移植。`buf` の中の `str1` を全部 `str2` に替える。

    原本は `char *buf` を書き換えるので、移植版は替えた文字列を返す。
    `while( (p = strstr(buf, str1)) != NULL )` なので、**置き換えた
    あとの文字列をまた探し直す**。`str2` の中に `str1` が入っていると
    無限に回る（`str1` が空文字列でも同じ）。同梱の呼び出しでは
    起きない。
    """
    if not str1:
        raise NatError("chg_str: str1 が空。原本は無限ループになる")
    if str1 in str2:
        raise NatError("chg_str: str2 の中に str1 がある（%r ⊂ %r）。"
                       "原本は無限ループになる" % (str1, str2))
    while str1 in buf:
        i = buf.index(str1)
        buf = buf[:i] + str2 + buf[i + len(str1):]
    return buf


def read_headder(fp):
    """stdfm.c:193 の忠実移植。`#99-…` の行まで読み飛ばす。

    ```c
    while( Done == 0 && fgets( char_buffer , 256 , fp ) != NULL ) {
      if( char_buffer[0] == '#' ) {
        sscanf( char_buffer , "#%d-%d-%d" , &seido , &system , &jouhou );
        if( seido == 99 ) Done = 1;
      }
    }
    ```

    `seido` は初期化なしの自動変数で、`sscanf` が1つも読めなければ
    **前の行の値**（または未初期化のごみ）が残る。`#` で始まるのに
    数字が続かない行があると、そこで `seido == 99` が成り立ちうる。
    同梱のファイルは `#99-0000-0000` で締めてあるので起きない。

    `fgets(char_buffer, 256, fp)` は**256文字までしか読まない**ので、
    長い行は途中で切れて次の呼び出しに続きが来る。続きの1文字目が
    `#` でなければ読み飛ばすだけ。移植版は1行ずつ読む（同梱の
    ヘッダは 256 文字より短い）。
    """
    seido = None
    done = 0
    while done == 0:
        line = fp.readline()
        if line == "":
            break
        if line[0] == "#":
            # `sscanf("#%d-%d-%d")`。読めた数だけ入る
            body = line[1:]
            got = []
            i = 0
            for _k in range(3):
                j = i
                if j < len(body) and body[j] in "+-":
                    j += 1
                k = j
                while k < len(body) and body[k].isdigit():
                    k += 1
                if k == j:
                    break
                got.append(int(body[i:k]))
                i = k
                if i < len(body) and body[i] == "-":
                    i += 1
                else:
                    break
            if got:
                seido = got[0]
            if seido == 99:
                done = 1


def write_BeginData(ver, ShisanNaiyou, fp, asctime=None):
    """stdfm.c:217 の忠実移植。出力の先頭に実行時刻と試算の内容を書く。

    ```c
    fprintf( fp , "%s\\n", asctime( w_tm ) );
    ```

    `asctime()` は末尾に `\\n` を付けて返すので、`%s\\n` で
    **空行が1行入る**。原本のとおりに写す。

    実行時刻を書くので、**このファイルの1行目は必ず食い違う**
    （④の `KYOSHUTUKIN` と同じ。`検証/移植/README.md`）。
    突き合わせるときは `asctime` を渡して固定する。
    """
    if asctime is None:
        asctime = _asctime_now()
    fp.write("%s\n" % asctime)
    fp.write("%s\n" % ver)
    fp.write("%s" % ShisanNaiyou)
    fp.write("#99-0000-0000\n")


_WDAY = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _asctime_now():
    """C の `asctime(localtime(&t))`。末尾の `\\n` まで同じ形にする。"""
    import time
    t = time.localtime()
    return "%s %s %2d %02d:%02d:%02d %d\n" % (
        _WDAY[(t.tm_wday + 1) % 7], _MON[t.tm_mon - 1], t.tm_mday,
        t.tm_hour, t.tm_min, t.tm_sec, t.tm_year)


def c_max(a, b):
    """stdfm.c:234 の `max`。`(a > b) ? a : b`。"""
    return a if a > b else b


def c_min(a, b):
    """stdfm.c:240 の `min`。`(a < b) ? a : b`。"""
    return a if a < b else b


def nenkin_fdiv(a, b):
    """stdfm.c:246 の忠実移植。`|b| < 1e-14` なら 0 を返す。"""
    if math.fabs(b) < EPSILON:
        return 0.
    return a / b


def array_sum(x, min_, max_):
    """stdfm.c:259 の忠実移植。**`max_` は含まない**（`i < max`）。

    足す順は原本と同じ左から右。
    """
    total = 0.
    for i in range(min_, max_):
        total += x[i]
    return total


# ---- 45年化オプション（`Option == 1` のときだけ効く）----------------
_MAX_HIKIAGE_NENSU = OP_MAX_KYOSHUTU_NENREI - MAX_KYOSHUTU_NENREI   # 5


def encho_year(G, nendo):
    """stdfm.c:274 の忠実移植。`nendo` までに拠出年齢が何歳上がったか。"""
    r = 0
    if G.Option == 1:
        while nendo >= G.OPTION_START + r * G.OP_HIKIAGE_KANKAKU:
            r += 1
            if r >= _MAX_HIKIAGE_NENSU:
                break
    return r


def encho_nensu(G, nendo, nenrei):
    """stdfm.c:299 の忠実移植。その生年の人が何歳ぶん延びるか。"""
    k = 0
    if G.Option == 1:
        while k < encho_year(G, nendo - nenrei + 60 + k):
            k += 1
            if k >= _MAX_HIKIAGE_NENSU:
                break
    return k


def extenda(G, nendo, nenrei):
    """stdfm.c:324 の忠実移植。延びた期間の中の年齢か。"""
    counter = 0
    if G.Option == 1:
        n = encho_nensu(G, nendo, nenrei)
        if n > 0 and nenrei <= 65 and nenrei >= 60 + n:
            counter = 1
    return counter


def extendb(G, nendo, nenrei):
    """stdfm.c:343 の忠実移植。延びる前の年齢か。"""
    counter = 0
    if G.Option == 1:
        if nenrei >= 60 and nenrei < 60 + encho_nensu(G, nendo, nenrei):
            counter = 1
    return counter


def extendc(G, nendo, nenrei):
    """stdfm.c:361 の忠実移植。延びの境目の年齢か。"""
    counter = 0
    if G.Option == 1:
        n = encho_nensu(G, nendo, nenrei)
        if n > 0 and nenrei == 60 + n:
            counter = 1
    return counter


def extendd(G, nendo, nenrei):
    """stdfm.c:379 の忠実移植。65歳超〜70歳か。"""
    counter = 0
    if G.Option == 1:
        if encho_nensu(G, nendo, nenrei) > 0 and nenrei > 65 and nenrei <= 70:
            counter = 1
    return counter
