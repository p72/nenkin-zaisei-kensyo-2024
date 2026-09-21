# -*- coding: utf-8 -*-
"""
④基礎年金の数値のふるまいが原本と一致するか
=============================================
原本の `基礎年金/stdfm.c` と `econ.c` を**無修正でコンパイルしてリンク**
し、`Round` / `read_data` / `read_str` / `econ.c の round` の答えを
取り出して移植版と比べる。

`Round` は①の `raund` とも⑤の `nround` とも別物
------------------------------------------------
    ⑤  `nround(x, n)`  C99 の `round( x * 10^n ) / 10^n`   → double
    ①  `raund(a, b)`   `(int)( a * 10^b ± 0.5 ) / 10^b`    → double
    ④  `Round(a, b)`   `(int)( a / 10^b + 0.5 ) * 10^b`    → **int**

④は**割ってから掛け戻す**ので「10^b の位への丸め」、①は逆で
「小数第 b 位への丸め」。しかも④は `int` を返すので小数点以下が消え、
負の値では 0 方向に寄る（`±0.5` の場合分けが無い）。
`Round( -1234.5678 , 1 )` は④が -1220、①の `raund` 相当なら -1230。

周辺和の足す順番（`atamawari._cal_sum`）
----------------------------------------
`Atamawari.c` の `cal_sum_kyufu` は6軸それぞれ「計にまとめるか否か」の
64 通りを回して元の値を足し込む。移植版は周辺和として
`np.add.accumulate` で計算するので、**原本の素の三十六重ループと
1ビットも違わないこと**をここで確かめる（小さな乱数の配列で
原本どおりのループを回した結果と突き合わせる）。
"""
import os
import struct
import subprocess

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "kiso_nenkin")
select(*SYSTEMS)

from cnum import Buffer, CsvError, ReadStr, Round, c_atof, g_round  # noqa: E402

# 原本を UTF-8 に変換したもの（run_pipeline.sh が作るビルド用ツリー）
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "基礎年金")

_INT_MAX = 2147483647

# Round の境目。(a, b) の組。原本は `int` を返すので桁あふれに注意
_A = ("0.0", "-0.0", "0.5", "-0.5", "1.5", "-1.5", "2.5", "-2.5",
      "4.999999", "-4.999999", "5.0", "-5.0", "5.000001",
      "1234.5678", "-1234.5678", "16590.5", "-16590.5",
      "17000", "16995", "16994.999999", "13300", "400",
      "1e6", "-1e6", "0.4", "-0.4", "123456789",
      "1e18", "-1e18", "2.1e9", "2147483647", "2147483648")
_INT_MIN = -2147483648
ROUND_CASES = []
OVERFLOW_CASES = []
for _a in _A:
    for _b in (0, 1, 2, 3, 4, 6, 10):
        # 原本の `Round` を辿って `int` に収まるかを見る。収まらない組は
        # 原本が未定義動作になるので突き合わせようがない
        # （`test_Roundはintをはみ出すと例外` で別に押さえる）
        _s = 1
        _ok = True
        for _ in range(_b):
            _s *= 10
            if _s > _INT_MAX:
                _ok = False
                break
        if _ok:
            _v = float(_a) / _s + 0.5
            _d = int(_v) if abs(_v) < 1e18 else None
            if _d is None or not _INT_MIN <= _d <= _INT_MAX:
                _ok = False
            elif not _INT_MIN <= _d * _s <= _INT_MAX:
                _ok = False
        (ROUND_CASES if _ok else OVERFLOW_CASES).append((_a, _b))

# econ.c の round（10進 n 桁）。丸めの境目を混ぜる
GROUND_CASES = [
    ("1.0005", 3), ("1.0015", 3), ("0.9995", 3), ("1.0025", 3),
    ("0.99949999999999994", 3), ("1.00050000000000006", 3),
    ("1.0004999999999999", 3), ("2.5", 0), ("3.5", 0), ("-2.5", 0),
    ("1.2345678901234567", 3), ("0.9920000000000001", 3),
    ("1.0083126", 3), ("123456.789", 3), ("1e-20", 3),
]

# read_data / read_str に食わせる行。行末カンマ・空行・長い値・
# 読めない値・列数のばらつきを混ぜる（列数が少ない行のあとで
# 前の行の値が残ることも見る）
CSV_TEXT = (
    "1,2,3,4,5,6,7,8,9,10,11,12,13,14\n"
    "1.5,-2.5,1e3,\n"                       # 行末がカンマ・列が少ない
    "\n"                                     # 空行（previous_c が未初期化）
    "abc,1,,2\n"                              # 読めない値と空フィールド
    "0x10,1e400,1e-400,nan,inf,-inf\n"        # 16進・範囲外・非数
    "  7 , 8\t,9\n"                           # 空白
    "2020,1,63,1,1,1,0.00000000000000e+00,1.5e+10,2,3\n"
    "0000000000000000000000000001,2\n"
    "10,11,12"                                # 最終行に改行なし
)


def find_cc():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """原本の `stdfm.c` と `econ.c` をそのままリンクして問い合わせる。"""
    cc = find_cc()
    if cc is None:
        pytest.skip("C++ コンパイラが無い")
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）。"
                    "検証/実行/run_pipeline.sh を1回通してください")

    d = tmp_path_factory.mktemp("kiso_num")
    for f in ("stdfm.c", "econ.c"):
        src = os.path.join(SRC, f)
        if not os.path.exists(src):
            pytest.skip(f"{src} が無い")
        open(d / f, "wb").write(open(src, "rb").read())
    for f in os.listdir(SRC):
        if f.endswith(".h"):
            open(d / f, "wb").write(open(os.path.join(SRC, f), "rb").read())
    for f in ("harness_kiso_num.cpp", "harness_kiso_glva.cpp"):
        open(d / f, "wb").write(open(os.path.join(HERE, f), "rb").read())

    exe = str(d / "h")
    r = subprocess.run(
        [cc, "-O2", "-w", "-o", exe, "harness_kiso_num.cpp",
         "harness_kiso_glva.cpp", "stdfm.c", "econ.c"],
        cwd=str(d), capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:3000]}")

    # Round
    args = ["round"]
    for a, b in ROUND_CASES:
        args += [a, str(b)]
    r = subprocess.run([exe] + args, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    round_out = r.stdout.splitlines()
    assert len(round_out) == len(ROUND_CASES), (
        f"Round の出力が {len(round_out)} 行（期待 {len(ROUND_CASES)}）")

    # econ.c の round
    args = ["ground"]
    for a, n in GROUND_CASES:
        args += [a, str(n)]
    r = subprocess.run([exe] + args, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    ground_out = r.stdout.splitlines()
    assert len(ground_out) == len(GROUND_CASES)

    # read_data / read_str
    csv = d / "in.csv"
    open(csv, "w", newline="").write(CSV_TEXT)
    r = subprocess.run([exe, "csv", str(csv)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    csv_out = r.stdout.splitlines()
    r = subprocess.run([exe, "str", str(csv)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    str_out = r.stdout.splitlines()

    return round_out, ground_out, csv_out, str_out, str(csv)


def bits(x):
    return struct.pack(">d", float(x)).hex()


def test_Roundが原本と一致(probe):
    round_out, _, _, _, _ = probe
    bad = []
    for (a, b), want in zip(ROUND_CASES, round_out):
        got = Round(float(a), b)
        if got != int(want):
            bad.append(f"Round({a}, {b}): C={want} Python={got}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_Roundは10の冪の位へ丸める():
    """①の `raund` と**割る向きが逆**なことを押さえておく。"""
    # b = 1 は「10 の位へ」。①の raund(x, 1) は「小数第1位へ」
    assert Round(1234.5678, 1) == 1230
    assert Round(1234.5678, 0) == 1235
    assert Round(16590.5, 1) == 16590
    # 負の値は 0 方向に寄る（`a - 0.5` の場合分けが無い）
    assert Round(-1234.5678, 1) == -1220
    assert Round(-1234.5678, 0) == -1234
    # 戻り値は int なので小数点以下が消える
    assert isinstance(Round(1.9, 0), int)
    assert Round(0.4, 0) == 0
    assert Round(-0.4, 0) == 0


def test_Roundはintをはみ出すと例外():
    """原本は `(int)` のキャストで未定義動作になる。移植版は落とす。"""
    with pytest.raises(CsvError):
        Round(1e18, 0)
    with pytest.raises(CsvError):
        Round(1.0, 10)          # 10^10 が int に入らない
    # 上で外した組がちゃんとあることを確かめる（テストが空振りしていない）
    assert len(OVERFLOW_CASES) > 0
    for a, b in OVERFLOW_CASES:
        with pytest.raises(CsvError):
            Round(float(a), b)


def test_econのroundが原本と一致(probe):
    """`econ.c` が自前に定義している `round( double , int )`。"""
    _, ground_out, _, _, _ = probe
    bad = []
    for (a, n), want in zip(GROUND_CASES, ground_out):
        got = g_round(float(a), n)
        if bits(got) != bits(float.fromhex(want)):
            bad.append(f"round({a}, {n}): C={want} Python={float(got).hex()}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_read_dataが原本と一致(probe):
    _, _, csv_out, _, path = probe
    fp = ReadStr(path)
    buf = Buffer()
    bad = []
    for k, want in enumerate(csv_out):
        parts = want.split()
        rc_c, dn_c = int(parts[0]), int(parts[1])
        vals_c = [float.fromhex(x) for x in parts[2:]]
        rc_p, dn_p = fp.read_data(buf)
        if (rc_p, dn_p) != (rc_c, dn_c):
            bad.append(f"{k}行目: C=({rc_c},{dn_c}) Python=({rc_p},{dn_p})")
            continue
        for i, v in enumerate(vals_c):
            if bits(buf[i]) != bits(v):
                bad.append(f"{k}行目 [{i}]: C={v!r} Python={buf[i]!r}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_read_strが原本と一致(probe):
    _, _, _, str_out, path = probe
    fp = ReadStr(path)
    buf = [""] * 1000
    bad = []
    for k, want in enumerate(str_out):
        head, _, rest = want.partition(" [")
        parts = head.split()
        rc_c, dn_c = int(parts[0]), int(parts[1])
        vals_c = ("[" + rest).split("] [")
        vals_c = [v.lstrip("[").rstrip("]") for v in vals_c]
        rc_p, dn_p = fp.read_str(buf)
        if (rc_p, dn_p) != (rc_c, dn_c):
            bad.append(f"{k}行目: C=({rc_c},{dn_c}) Python=({rc_p},{dn_p})")
            continue
        for i, v in enumerate(vals_c):
            if buf[i] != v:
                bad.append(f"{k}行目 [{i}]: C={v!r} Python={buf[i]!r}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_atofは読めなければ0():
    assert c_atof("") == 0.0
    assert c_atof("abc") == 0.0
    assert c_atof("0x10") == 16.0          # 16進も読む
    assert c_atof("1.5xyz") == 1.5


def test_周辺和が原本のループと1ビットも違わない():
    """`atamawari._cal_sum` が原本の `cal_sum_kyufu` と同じ答えを出すか。

    原本の三十六重ループを**そのまま**素の Python で回した結果と、
    `np.add.accumulate` を使う移植版の周辺和を突き合わせる。
    軸の大きさは原本より小さくして（6軸ぜんぶ回すと 4 億回になる）、
    足す順番が効く桁の乱数を入れる。
    """
    import atamawari

    rng = np.random.default_rng(0)
    # (制度, 年齢, 新旧, 区分, 対象, 形態) を原本より小さく取る
    shape = (4, 6, 3, 4, 3, 3)
    src_slices = (slice(1, 4), slice(1, 6), slice(1, 3), slice(1, 4),
                  slice(1, 3), slice(1, 3))

    A = np.zeros(shape)
    # 元の値の範囲だけに乱数を入れる（桁を大きく散らす）
    idx = tuple(src_slices)
    A[idx] = rng.standard_normal(A[idx].shape) * 1e12

    # ---- 原本のループをそのまま回す ----
    ref = A.copy()
    rng_ax = [range(s.start, s.stop) for s in src_slices]
    for i0 in rng_ax[0]:
        for i1 in rng_ax[1]:
            for i2 in rng_ax[2]:
                for i3 in rng_ax[3]:
                    for i4 in rng_ax[4]:
                        for i5 in rng_ax[5]:
                            src = (i0, i1, i2, i3, i4, i5)
                            for mask in range(64):
                                sel = [(mask >> a) & 1 for a in range(6)]
                                # sel[a] == 0 → 計（添字 0）にまとめる
                                if (sel[0] == 1 and sel[2] == 1
                                        and sel[3] == 1 and sel[4] == 1
                                        and sel[5] == 1):
                                    continue
                                dst = tuple(src[a] if sel[a] else 0
                                            for a in range(6))
                                ref[dst] += A[src]

    # ---- 移植版 ----
    got = A.copy()
    subs = atamawari._subsets(6, frozenset({1}))
    atamawari._cal_sum(got, src_slices, subs)

    assert got.shape == ref.shape
    d = np.flatnonzero(got.ravel() != ref.ravel())
    assert d.size == 0, (
        f"{d.size} か所が原本のループと違う。最初の3つ:\n  "
        + "\n  ".join(
            f"{np.unravel_index(i, shape)}: 原本={ref.ravel()[i]!r} "
            f"移植={got.ravel()[i]!r}" for i in d[:3]))


def test_年齢だけまとめる周辺和が0のまま残る():
    """原本の `continue` が「年齢だけ計」も落としてしまうことを押さえる。

    `Kyufu[制度][年度][年齢計][新旧][区分][対象][形態]` が
    すべて 0 のままになる（`検証/原本の不具合.md`）。
    """
    import atamawari

    subs = atamawari._subsets(6, frozenset({1}))
    assert frozenset() not in subs          # 自分自身に足す（正しく除外）
    assert frozenset({1}) not in subs       # 年齢だけ計（落ちてしまう）
    assert len(subs) == 62
    # 年齢と他の軸を一緒にまとめる組み合わせは残る
    assert frozenset({0, 1}) in subs
