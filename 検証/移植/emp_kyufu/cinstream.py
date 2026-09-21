# -*- coding: utf-8 -*-
"""
C++ の `std::cin >> int` を模す
===============================
②は標準入力を `cin >> key` の形で読む。⑤①が使う
`scanf("%d%*c", &x)` とは細かく違うので、ここに別に書く。

    scanf("%d%*c")   数を読んだあと**1文字を読み捨てる**
    cin >> int       数を読むだけ。区切りの空白は次の `>>` が飛ばす

読み方（C++11 以降の `num_get`）
--------------------------------
1. 先頭の空白（`isspace`）を飛ばす
2. 省略可能な符号（`+` `-`）
3. 数字の並び
4. 数字が1つも無ければ `failbit` を立て、**値を 0 にする**
   （C++11 で変わった。C++03 は値を触らなかった）
5. `int` に収まらなければ `failbit` を立て、`INT_MAX` か `INT_MIN` を入れる

②は読んだ値を `assert` で確かめるので、ここで 0 が入れば
そのあとの `assert` で落ちる。移植版も同じふるまいにしてある。

原本は読めなかったときの確認をしていない
----------------------------------------
`cin >> key` の戻り値（ストリームの状態）を見ていないので、
標準入力が空でも `key = 0` のまま進む。`main.cpp:34` の
`assert(iwname >= 1000)` で止まるのが最初の砦。
（`検証/原本の不具合.md`）
"""
__all__ = ["Cin"]

_WS = " \t\n\v\f\r"
_INT_MAX = 2147483647
_INT_MIN = -2147483648


class Cin:
    """標準入力（または任意のテキスト）を `std::cin >>` のように読む。"""

    def __init__(self, text):
        self._t = text
        self._i = 0
        self.fail = False

    @classmethod
    def from_stdin(cls):
        import sys
        return cls(sys.stdin.read())

    def int_(self):
        """`cin >> int` 相当。読めなければ `failbit` を立てて 0 を返す。"""
        t = self._t
        n = len(t)
        i = self._i
        while i < n and t[i] in _WS:
            i += 1
        j = i
        if j < n and t[j] in "+-":
            j += 1
        k = j
        while k < n and "0" <= t[k] <= "9":
            k += 1
        if k == j:
            # 数字が1つも無い。C++11 は値を 0 にして failbit を立てる
            self._i = i
            self.fail = True
            return 0
        self._i = k
        v = int(t[i:k])
        if v > _INT_MAX:
            self.fail = True
            return _INT_MAX
        if v < _INT_MIN:
            self.fail = True
            return _INT_MIN
        return v
