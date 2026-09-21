# -*- coding: utf-8 -*-
"""
C の数値のふるまいを Python で厳密に再現する
============================================
移植の土台。ここが1ビットでも狂うと下流の全部が狂うので、
`検証/移植/test_cnum.py` が原本の C とランダム値で総当たり比較している。

Python の組込みと **意図的に違う** ものが3つある。

1. `round()`
   C99 の round() は「0 から遠い方へ」丸める（round-half-away-from-zero）。
   Python の組込み round() は「偶数へ」丸める（round-half-to-even）。
       C:      round(2.5) = 3.0   round(-2.5) = -3.0   round(0.5) = 1.0
       Python: round(2.5) = 2     round(-2.5) = -2     round(0.5) = 0
   ⑤では shus_calc.c:397,399 がモデル賃金（所得代替率の分母）で round() を
   直接使っているので、ここを間違えると看板の数字が狂う。

   なお `math.floor(x + 0.5)` は**使えない**。x = 0.49999999999999994
   （0.5 の直下の double）は x+0.5 が double では 1.0 に丸まるため
   floor が 1 を返すが、C の round() は 0 を返す。桁上がりを経由しない
   実装にしてある。

2. `atof()`
   C の atof() は strtod() と同じで、読める所まで読んで**エラーを出さない**。
   読めなければ 0.0 を返す。Python の float() は ValueError を投げる。
   原本 stdfun.c:26 は空文字列にも atof() をかけるので（末尾カンマの行）、
   0.0 を返す挙動がそのまま効いている。

3. `printf("%.*f")`
   C の printf は double の**厳密な2進値**を10進に正しく丸めて出す
   （偶数丸め）。Python の f'{x:.3f}' も同じ経路（David Gay / Grisu 系の
   正確な変換）なので一致する。1. の round() とは別物なので混ぜないこと。
       nround(x, 3)        → 1000 倍して 0 から遠い方へ丸めて 1000 で割る
       f'{x:.3f}'          → 10進3桁に偶数丸めして文字列化
   原本は両方を使い分けているので、移植でも別関数に分けてある。
"""
import math
import re

__all__ = ["c_round", "nround", "c_atof", "c_trunc", "c_idiv", "fmt"]


def c_round(x):
    """C99 の round()。0 から遠い方へ丸める。戻り値は float（C と同じ double）。

    小数部は **0 方向への切り捨て（trunc）を基準に**取る。floor を基準に
    すると負の値で誤差が出るのを差分テストで実測した。
        x    = -0.49999999999999994  （0.5 の直下の double = -(0.5 - 2^-54)）
        floor(x) = -1.0
        x - floor(x) = 0.5 + 2^-54 → これは double で表せないので 0.5 に丸まる
    結果「ちょうど半数」と誤判定して -1.0 を返してしまう。C は -0.0 が正解。
    trunc を基準にすれば差は必ず (-1, 1) に収まり、Sterbenz の補題により
    引き算が厳密になる（|t| >= 1 のとき |x| < 2|t|、|t| = 0 なら自明）。

    `math.floor(x + 0.5)` も使えない。x = 0.49999999999999994 は x + 0.5 が
    double では 1.0 に丸まるため floor が 1 を返すが、C の round() は 0。

    **負のゼロ**にも注意。C99 の round() は結果がゼロのとき引数の符号を残す。
        C: round(-0.3) = -0.0      round(-0.0) = -0.0
    nround(x, -8) のように桁を大きく落とすと実際に出てくる。
    """
    if math.isnan(x) or math.isinf(x):
        return x
    # 2^52 以上は double では整数しか表せないので丸める余地が無い。
    # ここで抜けておくと math.trunc が巨大な Python int を作らずに済む。
    if not (-4503599627370496.0 < x < 4503599627370496.0):
        return x

    t = float(math.trunc(x))       # 0 方向へ。x と同符号
    d = x - t                      # 厳密。(-1, 1) に入る
    if d >= 0.5:
        r = t + 1.0                # 2.5 → 3（半数は 0 から遠い方へ）
    elif d <= -0.5:
        r = t - 1.0                # -2.5 → -3（同じく 0 から遠い方へ）
    else:
        r = t
    return math.copysign(0.0, x) if r == 0.0 else r


def nround(x, n):
    """stdfun.c:124 の忠実移植。

        dtemp = pow(10.0, (double)n);
        x *= dtemp;
        x = round(x) / dtemp;

    演算の順序をそのまま保つ。10 の整数乗は n <= 22 なら double で厳密なので
    pow の誤差は入らないが、原本どおり pow() を経由する（libm と同じ値）。
    """
    dtemp = math.pow(10.0, float(n))
    x = x * dtemp
    return c_round(x) / dtemp


# strtod の文法。「読める最長の前置を取り、途中で崩れたら崩れる前まで戻る」
# という規則をそのまま写せるよう、形ごとに分けてある。指数部を必須にして
# あるので "1e" は自動的に "1" までしか一致しない（C と同じ挙動）。
_SPACE = re.compile(r"[ \t\n\r\f\v]*")
_HEX = re.compile(
    r"0[xX](?:[0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?|\.[0-9a-fA-F]+)(?:[pP][+-]?[0-9]+)?")
_DEC = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_INF = re.compile(r"[iI][nN][fF](?:[iI][nN][iI][tT][yY])?")
_NAN = re.compile(r"[nN][aA][nN](?:\([0-9a-zA-Z_]*\))?")


def c_atof(s):
    """C の atof()。読める先頭部分だけを double にし、読めなければ 0.0。

    原本 stdfun.c:26 は空文字列や空白のみの文字列にも呼ばれるので、
    例外ではなく 0.0 を返すことが挙動として必要。

    16進浮動小数（"0x10" → 16.0）も C は受け付ける。これも差分テストで
    実測して見つけた差。10進より先に試さないと "0x10" が "0" になる。
    """
    i = _SPACE.match(s).end()
    sign = 1.0
    if i < len(s) and s[i] in "+-":
        if s[i] == "-":
            sign = -1.0
        i += 1

    m = _HEX.match(s, i)            # 16進を先に。"0x10" が "0" にならないように
    if m:
        return sign * float.fromhex(m.group(0))
    m = _DEC.match(s, i)
    if m:
        return sign * float(m.group(0))
    m = _INF.match(s, i)
    if m:
        return sign * math.inf
    m = _NAN.match(s, i)
    if m:
        return sign * math.nan
    return 0.0                      # 数値として読めない。C はエラーにしない


def c_trunc(x):
    """C の double → int キャスト。0 方向への切り捨て。

    Python の int(x) と同じだが、意図を明示するために名前を付けてある
    （Python の // は負数で床方向に落ちるので別物）。
    """
    return int(x)


def c_idiv(a, b):
    """C の int / int。0 方向への切り捨て。

    Python の a // b は床方向なので、負数で答えが変わる。
        C:      -7 / 2 = -3
        Python: -7 // 2 = -4
    """
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def fmt(x, n):
    """C の printf("%.<n>f") と同じ文字列。

    double の厳密な2進値を10進 n 桁へ正しく丸める（半数は偶数へ）。
    Python の書式指定も同じ変換を使うので一致する。
    """
    return f"{x:.{n}f}"
