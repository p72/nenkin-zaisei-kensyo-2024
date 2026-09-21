# -*- coding: utf-8 -*-
"""
libstdc++ の `<random>` と `std::shuffle` を Python で厳密に再現する
====================================================================
⑥分布推計が使う（`分布推計/main.cpp:90,153`）。

    std::mt19937 gen_rand(0);
    std::shuffle(vector023.begin(), vector023.end(), gen_rand);

これがそのまま結果に効く。シャッフルした並びを
`objects02[i].set_var002(vector023[i])` で個人の属性に割り当てるので、
1つでも順序が違えば出力が変わる。

なぜ標準ライブラリを写す必要があるのか
--------------------------------------
`std::mt19937` の**生成する32bit列は規格で決まっている**ので、どの処理系でも
同じ。ところが

- `std::shuffle` が乱数を**何回どう消費するか**
- `std::uniform_int_distribution` が範囲へ**どう落とし込むか**

はどちらも**実装依存**で、規格は決めていない。NumPy や Python の
`random.shuffle` とも当然違う。だから libstdc++ の実装をそのまま写す。

実測した消費数（`g++ 13.3.0` / `libstdc++ 20240904`）

    n=1 → 0 回   n=2 → 1 回   n=3 → 1 回   n=4 → 2 回   n=5 → 2 回 …

`floor(n/2)` になる。**1個の乱数から2回のスワップを作る最適化**
（`__gen_two_uniform_ints`）が入っているため。1回1スワップの素朴な
Fisher-Yates とは並びが変わる。

`std::mt19937(0)` の種の入れ方
------------------------------
`std::mt19937(s)` は参照実装の `init_genrand(s)` と同じ。

    mt[0] = s;  mt[i] = 1812433253 * (mt[i-1] ^ (mt[i-1] >> 30)) + i

NumPy の `MT19937` や Python の `random.Random` は `init_by_array` で種を
入れるので**別の列になる**。だからそれらは使えない。

実測で確かめた（`検証/移植/test_cppstd.py`）: seed=0 の先頭は
2357136044, 2546248239, 3071714933, … で規格の既知の値と一致。
"""

__all__ = ["MT19937", "uniform_int", "gen_two_uniform_ints", "shuffle"]

_MASK = 0xFFFFFFFF
_N = 624
_M = 397
_MATRIX_A = 0x9908B0DF        # 2567483615
_UPPER_MASK = 0x80000000
_LOWER_MASK = 0x7FFFFFFF

# mt19937 の min()/max()。`std::shuffle` と `uniform_int_distribution` が
# 範囲の計算に使う。
URNG_MIN = 0
URNG_MAX = _MASK
URNG_RANGE = URNG_MAX - URNG_MIN


class MT19937:
    """`std::mt19937` と同じ32bit列を出す。

    種の入れ方は参照実装の `init_genrand`（= `std::mt19937(s)`）。
    """

    __slots__ = ("mt", "idx")

    def __init__(self, seed=5489):
        mt = [0] * _N
        mt[0] = seed & _MASK
        for i in range(1, _N):
            mt[i] = (1812433253 * (mt[i - 1] ^ (mt[i - 1] >> 30)) + i) & _MASK
        self.mt = mt
        self.idx = _N               # 次の __call__ で捻る

    def _twist(self):
        mt = self.mt
        for i in range(_N):
            y = (mt[i] & _UPPER_MASK) | (mt[(i + 1) % _N] & _LOWER_MASK)
            n = mt[(i + _M) % _N] ^ (y >> 1)
            if y & 1:
                n ^= _MATRIX_A
            mt[i] = n
        self.idx = 0

    def __call__(self):
        if self.idx >= _N:
            self._twist()
        y = self.mt[self.idx]
        self.idx += 1
        # tempering
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & _MASK

    # C++ の名前に合わせた別名
    def min(self):
        return URNG_MIN

    def max(self):
        return URNG_MAX


def _lemire32(g, rng):
    """libstdc++ の `uniform_int_distribution::_S_nd`（Lemire 法）。

    参考実装は
      Daniel Lemire, "Fast Random Integer Generation in an Interval",
      ACM TOMACS 29(1), 2019.  https://arxiv.org/abs/1805.10941

    生成器がちょうど 32bit を返すとき（mt19937 がそう）に選ばれる経路。
    32bit 値と範囲の積を 64bit で取り、上位 32bit を答えにする。下位 32bit が
    範囲より小さいときだけ偏りの検査をして、必要なら引き直す。

        product = g() * range          （64bit）
        low     = product の下位32bit
        if low < range:
            threshold = (2^32 - range) % range
            while low < threshold: 引き直す
        return product >> 32

    `[0, range)` を返す（`range = urange + 1`）。
    """
    product = g() * rng
    low = product & 0xFFFFFFFF
    if low < rng:
        threshold = ((1 << 32) - rng) % rng
        while low < threshold:
            product = g() * rng
            low = product & 0xFFFFFFFF
    return product >> 32


def uniform_int(g, a, b):
    """`std::uniform_int_distribution<T>{a, b}(g)` の libstdc++ 実装。

    **ここを古い実装で書くと外れる。** 実測で判明した落とし穴で、
    最近の libstdc++（少なくとも 20240904）は

    - 生成器がちょうど 32bit のとき → **Lemire 法**（`_S_nd`）
    - 64bit のとき → 128bit 整数を使う Lemire 法
    - それ以外 → 昔からの「scaling して棄却」

    を使い分ける。mt19937 は max() が 2^32-1 なので**Lemire 法が選ばれる**。
    小さい範囲だと昔の方法と偶然一致することが多く、`n<=101` では気付けず、
    `n=275` と `n=1000` で初めて差が出た（`検証/移植/test_cppstd.py`）。
    """
    urange = b - a
    if URNG_RANGE > urange:
        # uerange は urange==0 でも 1 以上になる
        uerange = urange + 1
        if URNG_RANGE == 0xFFFFFFFF:
            # 生成器がちょうど 32bit（mt19937 はここ）
            return _lemire32(g, uerange & 0xFFFFFFFF) + a
        # 昔からの経路（2回の除算）。mt19937 では通らない
        scaling = URNG_RANGE // uerange
        past = uerange * scaling
        while True:
            ret = g() - URNG_MIN
            if ret < past:
                break
        ret //= scaling
    elif URNG_RANGE < urange:
        # 生成器の範囲が足りない場合（mt19937 では起きない）
        raise NotImplementedError(
            "生成器の範囲より広い一様整数分布は未実装"
            "（mt19937 では起きない経路）")
    else:
        ret = g() - URNG_MIN
    return ret + a


def gen_two_uniform_ints(g, b0, b1):
    """libstdc++ の `std::__detail::__gen_two_uniform_ints`。

    1個の一様整数（範囲 b0*b1）から2つの値を割り算と余りで取り出す。
    これが `std::shuffle` の消費数を `floor(n/2)` にしている。
    """
    x = uniform_int(g, 0, b0 * b1 - 1)
    return x // b1, x % b1


def shuffle(v, g):
    """`std::shuffle(v.begin(), v.end(), g)` の libstdc++ 実装。

    `v` をその場で並べ替える。素朴な Fisher-Yates ではなく、
    2要素ずつまとめて交換する形なので並びが違う。
    """
    n = len(v)
    if n == 0:
        return v

    urange = n
    if URNG_RANGE // urange >= urange:
        # 生成器の範囲が十分広い（mt19937 なら n <= 65535 くらいまで）
        i = 1
        if (urange % 2) == 0:
            # 要素数が偶数だと「交換する回数」が奇数になるので、先に1回やる
            j = uniform_int(g, 0, 1)
            v[i], v[j] = v[j], v[i]
            i += 1
        while i != n:
            swap_range = i + 1
            p0, p1 = gen_two_uniform_ints(g, swap_range, swap_range + 1)
            v[i], v[p0] = v[p0], v[i]
            i += 1
            v[i], v[p1] = v[p1], v[i]
            i += 1
    else:
        # 要素数が大きい場合。1回1スワップ
        for i in range(1, n):
            j = uniform_int(g, 0, i)
            v[i], v[j] = v[j], v[i]
    return v
