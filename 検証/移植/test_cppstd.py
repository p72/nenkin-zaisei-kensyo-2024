# -*- coding: utf-8 -*-
"""
cppstd.py が libstdc++ の `std::mt19937` と `std::shuffle` と一致するか
======================================================================
⑥分布推計は `std::mt19937 gen_rand(0)` で `std::shuffle` を呼び、その並びを
そのまま個人の属性に割り当てる（`分布推計/main.cpp:90,153`）。だから
シャッフルの並びが1つ違えば出力が変わる。

`std::mt19937` の32bit列は規格で決まっているが、**`std::shuffle` と
`std::uniform_int_distribution` は実装依存**。だから値を埋め込むのではなく
**その場の libstdc++ をコンパイルして問い合わせる**。標準ライブラリが
変わったらこのテストが落ちて気付ける。

ここで踏んだ落とし穴（実測でしか分からなかった）
------------------------------------------------
最初は `uniform_int_distribution` を「scaling して棄却」の古い実装で書いた。
`n <= 101` では全部一致したのに `n = 275` と `n = 1000` で外れた。
調べると最近の libstdc++ は生成器がちょうど 32bit のとき
**Lemire の nearly divisionless 法**を使っていた（`_S_nd`、
`/usr/include/c++/13/bits/uniform_int_dist.h:255`）。小さい範囲では
昔の方法と偶然一致するので、大きい要素数を試すまで気付けない。
"""
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
SYSTEMS = ("clib",)
select(*SYSTEMS)

from cppstd import MT19937, shuffle  # noqa: E402


def find_cxx():
    for cand in ("g++", "c++", "clang++"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            return cand
    return None


@pytest.fixture(scope="session")
def probe():
    """その場の libstdc++ に問い合わせた結果を読んで返す。"""
    cxx = find_cxx()
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")

    d = tempfile.mkdtemp(prefix="cppstd_")
    exe = os.path.join(d, "probe")
    r = subprocess.run(
        [cxx, "-O2", "-w", "-o", exe, os.path.join(HERE, "harness_cppstd.cpp")],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")

    r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr

    raw, shuf, rep, ver = [], {}, [], None
    for ln in r.stdout.splitlines():
        p = ln.split()
        if not p:
            continue
        if p[0] == "raw":
            raw = [int(x) for x in p[1:]]
        elif p[0] == "shuf":
            n = int(p[1])
            bar = p.index("|")
            shuf[n] = ([int(x) for x in p[2:bar]], int(p[bar + 1]))
        elif p[0] == "rep":
            rep.append([int(x) for x in p[2:]])
        elif p[0] == "ver":
            ver = (p[1], p[2])
    assert raw and shuf and rep and ver, "ハーネスの出力を読めなかった"
    return raw, shuf, rep, ver


def test_mt19937の生の列が一致(probe):
    raw, _, _, _ = probe
    g = MT19937(0)
    got = [g() for _ in range(len(raw))]
    assert got == raw, f"C={raw[:6]} … Python={got[:6]} …"


def test_mt19937の既知の値():
    """規格で決まっている値。ハーネスが無い環境でも最低限これは守る。

    seed=0 の先頭は参照実装 init_genrand(0) の既知の出力。
    """
    g = MT19937(0)
    assert [g() for _ in range(4)] == [2357136044, 2546248239,
                                       3071714933, 3626093760]
    # 規格の代表値: seed 5489（既定）で 10000 回目が 4123659995
    g = MT19937(5489)
    for _ in range(9999):
        g()
    assert g() == 4123659995


def test_shuffleの並びが一致(probe):
    _, shuf, _, _ = probe
    bad = []
    for n, (exp, nxt) in sorted(shuf.items()):
        g = MT19937(0)
        v = list(range(n))
        shuffle(v, g)
        if v != exp:
            # 最初に違う位置を出す
            i = next(j for j in range(n) if v[j] != exp[j])
            bad.append(f"n={n}: {i} 番目から違う "
                       f"C={exp[i:i + 6]} Python={v[i:i + 6]}")
        got_next = g()
        if got_next != nxt:
            bad.append(f"n={n}: 乱数の消費数が違う "
                       f"（次の値 C={nxt} Python={got_next}）")
    assert not bad, ("libstdc++ と一致しない:\n  " + "\n  ".join(bad))
    assert len(shuf) >= 30, f"試した要素数が {len(shuf)} 通りしかない"


def test_続けてシャッフルしても一致(probe):
    """原本は同じ生成器で毎年シャッフルする。状態の持ち越しまで見る。"""
    _, _, rep, _ = probe
    g = MT19937(0)
    v = list(range(137))
    for r, exp in enumerate(rep):
        shuffle(v, g)
        assert v == exp, f"{r + 1} 回目が違う: C={exp[:8]} Python={v[:8]}"
    assert len(rep) >= 10


def test_古い実装では外れることを記録():
    """『scaling して棄却』の古い実装だと n=275 で外れる、という記録。

    ここが一致してしまうようなら、libstdc++ が Lemire 法をやめた可能性が
    あるので、上の probe を使ったテストの結果を確かめる。
    """
    def uniform_int_old(g, a, b):
        urange = b - a
        uerange = urange + 1
        scaling = 0xFFFFFFFF // uerange
        past = uerange * scaling
        while True:
            ret = g()
            if ret < past:
                break
        return ret // scaling + a

    def shuffle_old(v, g):
        n = len(v)
        i = 1
        if n % 2 == 0:
            j = uniform_int_old(g, 0, 1)
            v[i], v[j] = v[j], v[i]
            i += 1
        while i != n:
            sr = i + 1
            x = uniform_int_old(g, 0, sr * (sr + 1) - 1)
            p0, p1 = x // (sr + 1), x % (sr + 1)
            v[i], v[p0] = v[p0], v[i]
            i += 1
            v[i], v[p1] = v[p1], v[i]
            i += 1

    g = MT19937(0)
    a = list(range(275))
    shuffle(a, g)
    g = MT19937(0)
    b = list(range(275))
    shuffle_old(b, g)
    assert a != b, ("古い実装と新しい実装が一致してしまった。"
                    "libstdc++ の実装が変わった可能性があるので、"
                    "probe を使ったテストの結果を確認すること")


def test_版を記録(probe):
    """どの版の libstdc++ で一致を確認したかを出す（情報表示）。"""
    _, _, _, ver = probe
    gcc, glibcxx = ver
    print(f"\n  gcc {gcc} / libstdc++ {glibcxx} と一致")
    assert gcc and glibcxx
