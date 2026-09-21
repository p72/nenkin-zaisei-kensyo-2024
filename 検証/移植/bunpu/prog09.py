# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog09.cpp の忠実移植（func09a / func09b / func09c）
========================================================================
状態コードの添字づけ、累積人数による状態の割り当て、そして年度1回分の
月数・年金額の積み上げ（`func09c`）。

func09a — 状態コード → 添字
---------------------------
`main.cpp:36` の `vector001`
`{11,12,…,20, 31,32,33,34, 40, 50, 60, 70, 80, 99}` を **0〜19** に写す。

**一覧に無い値を渡されると 99 を返す。** 呼び出し側（`prog06.cpp` など）は
戻り値を配列の添字に使うので、99 だと範囲外になる。実データでは起きないが
原本の作りとしては危うい（`検証/原本の不具合.md`）。

原本は if/else if を20回並べているが、対応は表そのものなので dict にした
（同じ入力に同じ出力を返す。順序に意味は無い）。

func09b — 累積人数で状態を割り当てる
------------------------------------
`arg09b3`（`main.cpp` の `vector035` ＝ 累積人数）を i, j の順に見て、
**`p < 累積人数` になった最初の (i, j) の j** に対応する状態コードを
`var008` に入れる。

    for p in 0..arg09b1-1:
        var09b1 = 0
        for i while var09b1 == 0:
            for j while var09b1 == 0:
                if p < arg09b3[i][j]:
                    ag09b5[p].var008 = arg09b4[j]
                    var09b1 = 1

つまり「累積人数の階段」に p を落とし込んで状態を決めている。
`arg09b4` は `vector001`（状態コード）で、**添字は j（列）だけ**。
行 i は累積の順序にしか効かない。

**`arg09b1` は人数ではなく `main_var007`**（`main.cpp:199`）で、これは
`vector029`（残りの数）の総和。`objects02` の要素数を超えると範囲外に
なるが、残りの数の総和なので人数以下に収まる。

func09c — 年度1回分の月数と年金額を積み上げる
---------------------------------------------
⑥の心臓部。`main.cpp:200` で年度ごとに全員に対して呼ばれる。
個人1人につき、次の4つの月数を決めて各フィールドに足し込む。

    var09c2  当年度側の「12か月のうちの月数」（var033 になる）
    var09c3  前年度側の「12か月のうちの月数」（var034 になる）
    var09c4  当年度側の「加入月数」（var009 などに足す）
    var09c5  前年度側の「加入月数」

月数の決め方は年齢（`var005`）で場合分けする（`prog09.cpp:117-180`）。

    19歳以下      c4=c5=0。前年度が被用者（is_func02）なら c2=0, c3=12
    20歳          誕生月で 12 を2つに割る
    21〜25歳かつ前年度が被用者   c2=0, c3=12, c4=0, c5=12
    var09c1 歳（支給開始年齢）   状態コードで分岐
    var09c1+1 歳以上             同上
    それ以外（26〜支給開始-1歳）  4つとも 6 のまま

最後の「4つとも 6」は初期値のまま抜けた場合で、**12 の半分**。
年度の途中で1年歳を取る扱いと読める（`prog09.cpp:85-88`）。

`var09c1` は支給開始年齢で、`object01c == 0` なら 60、そうでなければ
基準年齢で 60〜65（`prog09.cpp:66-83`）。`func06a` の閾値（414〜474 か月）
と同じ刻みで、**414 = 60歳×12 − 66** のように月数と年齢で対応している。

`var09c6` は誕生月から出す「12 のうちの前半の月数」（`prog09.cpp:90-116`）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`var09c6` が初期化されないまま読まれうる**（`prog09.cpp:89`）
   `int var09c6;` と宣言だけして if/else if の連鎖で決めるが、
   **`else` が無い**。`var006 % 10000` が 1231 より大きいと、どの枝にも
   入らず未初期化のまま `var09c2` などに使われる（未定義動作）。
   月日として正しい値なら 101〜1231 に収まるので実データでは起きない。
   （`検証/原本の不具合.md`）

2. **`var006 % 10000` は C の剰余**
   C の `%` は0方向に丸めた商の余りなので、`var006` が負なら結果も負。
   `class02()` の `var006` 初期値は **-1** で、そのまま呼ばれると
   `-1 % 10000 == -1`（C）→ `<= 201` に当たって `var09c6 = 9`。
   Python の `%` は `-1 % 10000 == 9999` で**違う**ので、
   下の `_cmod` で C に合わせている。

3. **`var007 == 80` と `== 99` は何も足さない**
   最後の `else if` は 70 までで、80（死亡か脱退と読める）と 99 は
   どの枝にも入らない。`var033`/`var034` だけが設定される。
"""

__all__ = ["func09a", "func09b", "func09c"]

# prog09.cpp:5 の if/else if 20本と同じ対応
_STATE_TO_IDX = {
    11: 0, 12: 1, 13: 2, 14: 3, 15: 4, 16: 5, 17: 6, 18: 7, 19: 8, 20: 9,
    31: 10, 32: 11, 33: 12, 34: 13, 40: 14, 50: 15, 60: 16, 70: 17,
    80: 18, 99: 19,
}


def func09a(arg09a1):
    """prog09.cpp:5 の忠実移植。一覧に無い値は 99（＝呼び出し側で範囲外）。"""
    return _STATE_TO_IDX.get(arg09a1, 99)


def func09b(arg09b1, arg09b2, arg09b3, arg09b4, ag09b5):
    """prog09.cpp:50 の忠実移植。

    arg09b1  対象人数（main_var007 ＝ 残りの数の総和）
    arg09b2  遷移表（vector026）。寸法を取るためだけに使う
    arg09b3  累積人数（vector035）
    arg09b4  状態コードの一覧（vector001）
    ag09b5   個人のリスト（書き換える）
    """
    n_i = len(arg09b2)
    for p in range(arg09b1):
        var09b1 = 0
        i = 0
        while i < n_i and var09b1 == 0:
            row = arg09b3[i]
            n_j = len(arg09b2[i])
            j = 0
            while j < n_j and var09b1 == 0:
                if p < row[j]:
                    ag09b5[p].var008 = arg09b4[j]
                    var09b1 = 1
                j += 1
            i += 1


def _cmod(a, b):
    """C の `%`。0方向に丸めた商の余りなので、`a` が負なら結果も負。

    Python の `%` は法の符号に合わせるので `-1 % 10000 == 9999` になり
    **違う**。`var006` の初期値が -1 なので効いてくる。
    """
    r = abs(a) % abs(b)
    return -r if a < 0 else r


# prog09.cpp:183-358 の長い if/else if を表にしたもの。
#
#   key   状態コード（前半は var007、後半は var008 を見る。分岐は同じ形）
#   [0]   「加入月数」を足すフィールド（前半は var09c4、後半は var09c5）
#   [1]   「12か月のうちの月数」を足すフィールド（前半 var09c2、後半 var09c3）
#   [2]   var038 に足すときの係数 (分子, 分母)。None なら var038 は触らない
#
# 原本は同じ並びを2回書いているが、足す先も係数も完全に同じで、渡す値だけが
# 違う。表にしても代入先が重なることは無いので、順序で結果は変わらない。
_ADD09C = {
    11: (("var009",), ("var010", "var011"), (1.0, None)),
    12: (("var009",), ("var010", "var012"), (1.0, None)),
    13: (("var009",), ("var010", "var013"), (1.0, 2.0)),
    14: (("var009",), ("var010", "var014"), (1.0, 2.0)),
    15: (("var009",), ("var010", "var015"), (5.0, 8.0)),
    16: (("var009",), ("var010", "var016"), (6.0, 8.0)),
    17: (("var009",), ("var010", "var017"), (7.0, 8.0)),
    18: (("var009",), ("var010", "var018"), None),
    19: (("var009",), ("var010", "var019"), None),
    20: (("var009",), ("var010", "var020"), None),
    31: (("var009", "var023", "var024"), ("var022", "var028"), (1.0, None)),
    33: (("var009", "var023", "var024"), ("var022", "var028"), (1.0, None)),
    32: (("var009", "var023", "var024"),
         ("var022", "var028", "var029"), (1.0, None)),
    34: (("var009", "var023", "var024"),
         ("var022", "var028", "var029"), (1.0, None)),
    40: (("var009", "var023", "var025"), ("var022", "var030"), (1.0, None)),
    50: (("var009", "var023", "var026"), ("var022", "var031"), (1.0, None)),
    60: (("var009", "var023", "var027"), ("var022", "var032"), (1.0, None)),
    70: (("var009",), ("var021",), (1.0, None)),
    # 80 と 99 はどの枝にも入らない（原本のとおり何も足さない）
}


def _apply09c(o, code, months, share):
    """`_ADD09C` の1行を適用する。`months` が var09c4/var09c5、
    `share` が var09c2/var09c3 に当たる。"""
    ent = _ADD09C.get(code)
    if ent is None:
        return
    mf, sf, w = ent
    for n in mf:
        setattr(o, n, getattr(o, n) + months)
    for n in sf:
        setattr(o, n, getattr(o, n) + share)
    if w is not None:
        num, den = w
        # 原本は `(double)var09c4 * 5.0/8.0` の形。左から掛けて割る
        v = float(months) * num
        if den is not None:
            v = v / den
        o.var038 += v


def func09c(arg09c1, arg09c2, arg09c3, arg09c4):
    """prog09.cpp:65 の忠実移植。年度1回分の月数と年金額を積み上げる。

    arg09c1  人数（main_var002）
    arg09c2  個人のリスト（書き換える）
    arg09c3  object01c.value001（0 なら支給開始年齢は一律60）
    arg09c4  基準年齢（loop_var002）
    """
    # 支給開始年齢。prog09.cpp:66-83。func06a の閾値と同じ刻み
    var09c1 = 60
    if arg09c3 == 0:
        var09c1 = 60
    else:
        if arg09c4 >= 51:
            var09c1 = 60
        elif arg09c4 == 49 or arg09c4 == 50:
            var09c1 = 61
        elif arg09c4 == 47 or arg09c4 == 48:
            var09c1 = 62
        elif arg09c4 == 45 or arg09c4 == 46:
            var09c1 = 63
        elif arg09c4 == 43 or arg09c4 == 44:
            var09c1 = 64
        else:
            var09c1 = 65

    for p in range(arg09c1):
        o = arg09c2[p]

        # 初期値は4つとも 6（＝12の半分）。どの枝にも入らなければこのまま
        var09c2 = 6
        var09c3 = 6
        var09c4_ = 6
        var09c5 = 6

        # 誕生月から「12 のうちの前半の月数」を出す。prog09.cpp:89-116。
        # **else が無いので 1231 より大きいと未初期化**（原本の癖 1.）
        md = _cmod(o.var006, 10000)
        if md == 101:
            var09c6 = 8
        elif md <= 201:
            var09c6 = 9
        elif md <= 301:
            var09c6 = 10
        elif md <= 401:
            var09c6 = 11
        elif md <= 501:
            var09c6 = 0
        elif md <= 601:
            var09c6 = 1
        elif md <= 701:
            var09c6 = 2
        elif md <= 801:
            var09c6 = 3
        elif md <= 901:
            var09c6 = 4
        elif md <= 1001:
            var09c6 = 5
        elif md <= 1101:
            var09c6 = 6
        elif md <= 1201:
            var09c6 = 7
        elif md <= 1231:
            var09c6 = 8
        else:
            # 原本はここで未初期化の値を読む（未定義動作）。移植では
            # 黙って進まずに落とす。実データでは到達しない
            raise ValueError(
                f"func09c: var006 % 10000 = {md} は 1231 を超えている。"
                "原本は var09c6 が未初期化のまま使われる（未定義動作）")

        a = o.var005
        if a <= 19:
            if o.is_func02():
                var09c2 = 0
                var09c3 = 12
                var09c4_ = 0
                var09c5 = 0
            else:
                var09c4_ = 0
                var09c5 = 0
        elif a == 20:
            if o.is_func02():
                var09c2 = 0
                var09c3 = 12
                var09c4_ = 0
                var09c5 = 12 - var09c6
            else:
                var09c2 = var09c6
                var09c3 = 12 - var09c6
                var09c4_ = 0
                var09c5 = 12 - var09c6
        elif (21 <= a <= 25) and o.is_func02():
            var09c2 = 0
            var09c3 = 12
            var09c4_ = 0
            var09c5 = 12
        elif a == var09c1:
            if o.var007 == 40 or o.var007 == 50 or o.var007 == 60:
                var09c2 = 12
                var09c3 = 0
                var09c4_ = var09c6
                var09c5 = 0
            else:
                if o.var008 == 11 or o.var008 == 12 or o.var008 == 20:
                    var09c2 = var09c6
                    var09c3 = 12 - var09c6
                    var09c4_ = var09c6
                    var09c5 = 12 - var09c6
                else:
                    var09c2 = var09c6
                    var09c3 = 12 - var09c6
                    var09c4_ = var09c6
                    var09c5 = 0
        elif a >= var09c1 + 1:
            if o.var007 == 40 or o.var007 == 50 or o.var007 == 60:
                var09c2 = 12
                var09c3 = 0
                var09c4_ = 0
                var09c5 = 0
            elif o.var007 == 11 or o.var007 == 12 or o.var007 == 20:
                var09c2 = var09c6
                var09c3 = 12 - var09c6
                var09c4_ = var09c6
                var09c5 = 0
            else:
                var09c2 = var09c6
                var09c3 = 12 - var09c6
                var09c4_ = 0
                var09c5 = 0
        # 26歳〜支給開始年齢-1歳はどの枝にも入らず、4つとも 6 のまま

        # prog09.cpp:181-182。**if/else の外なので全員に無条件で入る**。
        # これがコピーコンストラクタの未定義動作を観測できなくしている
        o.var033 = var09c2
        o.var034 = var09c3

        # 当年度側（var007）と前年度側（var008）を同じ形で足す
        _apply09c(o, o.var007, var09c4_, var09c2)
        _apply09c(o, o.var008, var09c5, var09c3)
