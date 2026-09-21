# -*- coding: utf-8 -*-
"""
C の scanf を模す
=================
⑤が使う書式は2つだけ。

    scanf("%d%*c", &x)    整数を1つ読み、続く1文字を読み捨てる
    scanf("%s%*c", s)     空白で区切られた語を1つ読み、続く1文字を読み捨てる

どちらも先頭の空白（改行を含む）を読み飛ばしてから本体を読む。`%*c` は
そのあとの1文字を捨てるもので、`run_pipeline.sh` のように1行1値で流す
場合は改行が捨てられるだけになる。つまり**空白区切りの語を順に取る**のと
同じ挙動なので、そう実装してある。

C の `%d` は「符号＋数字列」を読んで、数字でない文字が来たらそこで止まる。
読めるものが無ければ scanf は変数を書き換えず、戻り値が 0 になる。原本は
戻り値を見ていないので、その場合は**前の値が残る**（自動変数なら不定）。
移植では気付けるように例外にしてある。
"""

__all__ = ["Scan"]

_WS = " \t\n\r\f\v"


class Scan:
    """標準入力（または任意のテキスト）を C の scanf のように読む。"""

    def __init__(self, text):
        self._t = text
        self._i = 0

    @classmethod
    def from_stdin(cls):
        import sys
        return cls(sys.stdin.read())

    # ---- 内部 ----
    def _skip_ws(self):
        while self._i < len(self._t) and self._t[self._i] in _WS:
            self._i += 1

    def _token(self):
        """空白で区切られた次の語。無ければ None。"""
        self._skip_ws()
        if self._i >= len(self._t):
            return None
        j = self._i
        while j < len(self._t) and self._t[j] not in _WS:
            j += 1
        tok = self._t[self._i:j]
        self._i = j
        return tok

    # ---- 書式 ----
    def d(self):
        """`scanf("%d%*c", &x)` 相当。"""
        self._skip_ws()
        j = self._i
        n = len(self._t)
        if j < n and self._t[j] in "+-":
            j += 1
        k = j
        while k < n and self._t[k].isdigit() and self._t[k].isascii():
            k += 1
        if k == j:
            raise ValueError(
                f"scanf(\"%d\") が整数を読めなかった（位置 {self._i}、"
                f"残り {self._t[self._i:self._i + 20]!r}）。"
                "原本は戻り値を見ないので変数が前の値のまま進む。")
        val = int(self._t[self._i:k])
        self._i = k
        # %*c: 続く1文字を読み捨てる
        if self._i < n:
            self._i += 1
        return val

    def s(self):
        """`scanf("%s%*c", s)` 相当。"""
        tok = self._token()
        if tok is None:
            raise ValueError("scanf(\"%s\") が語を読めなかった（入力が尽きた）")
        # %*c: 続く1文字を読み捨てる
        if self._i < len(self._t):
            self._i += 1
        return tok

    def rest(self):
        """まだ読んでいない部分（デバッグ用）。"""
        return self._t[self._i:]
