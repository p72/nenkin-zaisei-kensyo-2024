# -*- coding: utf-8 -*-
"""
プログラム/分布推計/_prototype.h と prog01.cpp / prog02.cpp の忠実移植
======================================================================
⑥分布推計の個人レコード（`class02`）と入力の読み取り（`class01`）。

このシステムは識別子が匿名化されている
--------------------------------------
`class01` / `class02` / `var001`〜`var044` / `func03a`〜`func13c` /
`main_var001` / `vector023` / `loop_var001` …
**意味のある名前が1つも無い。** ⑤（`Escutrrh`、`shus_ave` など）とは違って、
「何をしているか」はコードから読み解かないと分からない。

だから移植のコメントは、意味の推測ではなく

- 原本のどのファイルの何行目に対応するか
- そこで**観測できるふるまい**（初期値、条件、副作用）

を書く方針にしている。読み解けた範囲だけ、根拠を添えて書く。

読み解けた範囲
--------------
`class02` は個人1人を表す。使われ方から次が読める。

    var002  シャッフルで割り当てられる並び順（main.cpp:155）
    var005  年齢（`get_var005() >= var09c1 + 1` で支給開始年齢と比較。
            prog09.cpp:163）
    var006  生年月（`% 10000` を 101〜1231 と比べて月を出す。prog09.cpp:90）
    var007  当年度の状態コード（`is_func01()` が 31,32,33,34,40,50,60 を見る）
    var008  前年度の状態コード（`is_func02()` が同じ集合を見る）
    var009  加入月数（`var009 < 240` が `is_func03()` に出る＝20年）
    var033  当年度の厚年の月数（`add_var043` に x として渡る。prog10.cpp:547）
    var034  同・基礎の月数
    var043  年金額の累積（`var043 * r + (a*x/12 + b*y/12)`）
    var037  並べ替えの鍵の1つ（compare_var037）

状態コードの集合は main.cpp:36 の
`{11,12,13,14,15,16,17,18,19,20,31,32,33,34,40,50,60,70,80,99}`。

原本の癖をそのまま残しているところ
----------------------------------
1. **コピーコンストラクタが var033 と var034 を写さない**（prog02.cpp）
   `set_var001`〜`set_var032` のあと **`set_var035`** に飛んでいる。
   メンバ初期化子も無いので、C++ ではコピー後の `var033`/`var034` は
   **不定値**（未定義動作）。

   しかも `class02` はコピーコンストラクタを宣言しているため**ムーブ
   コンストラクタが暗黙に作られない**。`std::stable_sort` の要素の入れ替えも
   `std::vector` の再確保も**コピーを通る**ので、ソートするたびに
   `var033`/`var034` が壊れる。

   **これは観測できない**ことを確かめた。main.cpp の年次ループは

       198行  stable_sort(… compare_var037())   ← ここで壊れる
       200行  func09c(…)                        ← 全員に set_var033/034
       218行  func10d(…)                        ← ここで初めて読む

   の順で、`func09c`（prog09.cpp:181-182）は if/else の外で**全員に無条件で**
   代入する。`var033`/`var034` を読むのは `func10d`（prog10.cpp:547-553）だけ。
   つまり「壊れる → 必ず書く → 読む」なので、壊れた値が出力に出ることはない。

   Python ではそもそもソートで参照を並べ替えるだけでコピーが起きないので、
   **この未定義動作に対応する挙動が無い**。移植版は値を保持する。上の順序の
   おかげで出力は一致する。念のため `copy()` に印を付けてある。

2. **`class02()` の初期値が -1 と 0 で混ざる**（_prototype.h:65）
   var001, var003, var004, var005, var006, var008 が **-1**、残りは 0。
   `var002` だけ int で 0 から始まる。

3. **比較関数が値渡し**（_prototype.h:70,78,86）
   `bool operator()(class02 a, class02 b)` なので比較のたびにコピーが2つ
   できる。結果には影響しないが、原本が遅い理由の1つ。

4. **`class01::input_value001` は標準入力から読む**（prog01.cpp）
   引数の文字列をそのまま標準出力に出してから `std::cin >> int` する。
   `検証/実行/run_bunpu.sh` が6つの値を順に流す。
"""

__all__ = ["Class01", "Class02", "STATE_CODES", "cmp_var002", "cmp_var007",
           "cmp_var037"]

# main.cpp:36 vector001。状態コードの一覧
STATE_CODES = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
               31, 32, 33, 34, 40, 50, 60, 70, 80, 99]

# _prototype.h:210,211 is_func01()/is_func02() が見る集合
_FUNC12_SET = frozenset((31, 32, 33, 34, 40, 50, 60))


class Class01:
    """_prototype.h:9 class01。標準入力から int を1つ読むだけ。"""

    __slots__ = ("value001",)

    def __init__(self):
        self.value001 = 0

    def input_value001(self, arg01a, scan):
        """prog01.cpp:5 の忠実移植。

        `std::cout << arg01a << std::endl;` のあと `std::cin >> int`。
        `scan` は標準入力を読むオブジェクト（`cscan.Scan` と同じ `d()`）。
        """
        print(arg01a)
        self.value001 = scan.d()


# class02 のフィールド。(名前, 初期値) を _prototype.h:65 の順に並べる。
# -1 で始まるものと 0 で始まるものが混ざっているので、表にして取り違えを防ぐ。
_FIELDS = (
    ("var001", -1), ("var002", 0), ("var003", -1), ("var004", -1),
    ("var005", -1), ("var006", -1), ("var007", 0), ("var008", -1),
    ("var009", 0), ("var010", 0), ("var011", 0), ("var012", 0),
    ("var013", 0), ("var014", 0), ("var015", 0), ("var016", 0),
    ("var017", 0), ("var018", 0), ("var019", 0), ("var020", 0),
    ("var021", 0), ("var022", 0), ("var023", 0), ("var024", 0),
    ("var025", 0), ("var026", 0), ("var027", 0), ("var028", 0),
    ("var029", 0), ("var030", 0), ("var031", 0), ("var032", 0),
    ("var033", 0), ("var034", 0), ("var035", 0), ("var036", 0),
    ("var037", 0),
    ("var038", 0.0), ("var039", 0.0),
    ("var040", 0),
    ("var041", 0.0),
    ("var042", 0),
    ("var043", 0.0), ("var044", 0.0),
)

# prog02.cpp のコピーコンストラクタが写すフィールド。
# **var033 と var034 が抜けている**（set_var032 の次が set_var035）。
_COPIED = tuple(n for n, _ in _FIELDS if n not in ("var033", "var034"))


class Class02:
    """_prototype.h:16 class02。個人1人のレコード（44フィールド）。

    原本は setter/getter/adder を全フィールドに並べているが、Python では
    属性に直接触る。原本の `set_varNNN(x)` は `o.varNNN = x`、
    `get_varNNN()` は `o.varNNN`、`add_varNNN(x)` は `o.varNNN += x` と
    1対1に対応する。
    """

    __slots__ = tuple(n for n, _ in _FIELDS)

    def __init__(self):
        for n, v in _FIELDS:
            setattr(self, n, v)

    # ---- prog02.cpp のコピーコンストラクタ ----
    def copy(self):
        """prog02.cpp:3 の忠実移植。

        **原本は var033 と var034 を写さない**（上の解説 1.）。C++ では
        コピー後にそこが不定値になるが、必ず `func09c` が書いてから
        `func10d` が読むので観測できない。Python では値を保持する。
        """
        o = Class02.__new__(Class02)
        for n in _COPIED:
            setattr(o, n, getattr(self, n))
        # 原本が写さない2つ。C++ では不定値になるところ。
        o.var033 = self.var033
        o.var034 = self.var034
        return o

    # ---- _prototype.h:207 add_var043 ----
    def add_var043(self, a, x, b, y, r):
        """_prototype.h:207 の忠実移植。

            var043 = var043 * r + ( a * ((double)x/12.0) + b * ((double)y/12.0) )

        `x` と `y` は int なので `(double)x/12.0` の順序で割る。
        """
        self.var043 = self.var043 * r + (a * (float(x) / 12.0)
                                         + b * (float(y) / 12.0))

    # ---- _prototype.h:210-213 の判定 ----
    def is_func01(self):
        """var007 が 31,32,33,34,40,50,60 のどれか。"""
        return self.var007 in _FUNC12_SET

    def is_func02(self):
        """var008 が 31,32,33,34,40,50,60 のどれか。"""
        return self.var008 in _FUNC12_SET

    def is_func03(self):
        """var008==99 または var035 が 1,2 または var009<240。"""
        return (self.var008 == 99 or self.var035 == 1 or self.var035 == 2
                or self.var009 < 240)

    def is_func04(self):
        """var008==99。"""
        return self.var008 == 99

    def __repr__(self):
        return (f"<Class02 var002={self.var002} var005={self.var005} "
                f"var007={self.var007} var008={self.var008} "
                f"var037={self.var037}>")


# ---- _prototype.h:68,76,84 の比較関数 ----
# 原本は `stable_sort(v.begin(), v.end(), class02::compare_varNNN())`。
# C++ の stable_sort も Python の list.sort も安定なので、鍵で並べ替えれば
# 同じ並びになる。
def cmp_var002(o):
    return o.var002


def cmp_var007(o):
    return o.var007


def cmp_var037(o):
    return o.var037
