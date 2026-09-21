# -*- coding: utf-8 -*-
"""
①被保険者推計の数値のふるまいが原本と一致するか
=================================================
原本の `被保険者推計/stdfm.c` を**無修正でコンパイルしてリンク**し、
`raund` と `read_csv` の答えを取り出して移植版と比べる。

`raund` は⑤の `nround` と別物
-----------------------------
⑤は C99 の `round()` を使うが、①は `(int)(a + 0.5)` で自前に丸める。
10 の冪も `int` の掛け算で作る。向きは同じ（0 から遠い方へ）だが、
`int` を経由するぶん上限がある。境目の値をまとめて突き合わせる。

年齢の足し方（`np.add.accumulate`）
----------------------------------
`fout.c:441` は年齢 15〜120 を昇順に1つずつ足す。浮動小数の加算は
順序で答えが変わるので、移植版は `np.add.accumulate`（逐次の累積和）の
最後の要素を使う。`np.sum` は対和なので使えない。ここで両方を突き合わせ、
`accumulate` が素の Python ループと1ビットも違わないことを確かめる。
"""
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "hihokensha")
select(*SYSTEMS)

from cnum import CsvError, ReadCsv, c_atof, cdiv, raund  # noqa: E402

# 原本を UTF-8 に変換したもの（run_pipeline.sh が作るビルド用ツリー）
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "被保険者推計")

# raund の境目。(a, b) の組。
# **`int` に収まる組だけ**にする。はみ出す組は原本が未定義動作になるので
# 突き合わせようがない（`test_raundはintをはみ出すと例外` で別に押さえる）。
_INT_MAX = 2147483647
_A = ("0.0", "-0.0", "0.5", "-0.5", "1.5", "-1.5", "2.5", "-2.5",
      "1.25", "-1.25", "1.35", "1.0000005", "-1.0000005",
      "0.4999999999999999", "-0.4999999999999999",
      "1234.5678", "-1234.5678", "999999.5", "-999999.5",
      "1e9", "-1e9", "0.000123456789", "1.0000000000000002",
      "67382108.5", "33691054.5", "1728.123456789")
RAUND_CASES = []
OVERFLOW_CASES = []
for _a in _A:
    for _b in (0, 1, 2, 3, 4, 6, -1, -2, -3):
        _scaled = abs(float(_a)) * (10.0 ** _b)
        if _scaled + 0.5 < _INT_MAX:
            RAUND_CASES.append((_a, _b))
        else:
            OVERFLOW_CASES.append((_a, _b))

# read_csv に食わせる行。行末のカンマ・空行・長い値・読めない値を混ぜる
CSV_TEXT = (
    "1,2,3\n"
    "1.5,-2.5,1e3,\n"          # 行末がカンマ
    "\n"                        # 空行（previous_c が未初期化になる）
    "abc,1,,2\n"                # 読めない値と空フィールド
    "0x10,1e400,1e-400,nan\n"   # 16進・範囲外
    "  7 , 8\t,9\n"             # 空白
    "0000000000000000000000000001,2\n"   # 28文字（上限 30 の内側）
    "10,11,12"                  # 最終行に改行なし
)


def find_cc():
    for c in ("gcc", "cc", "clang"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """原本の `stdfm.c` をそのままリンクして問い合わせる。"""
    cc = find_cc()
    if cc is None:
        pytest.skip("C コンパイラが無い")
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）。"
                    "検証/実行/run_pipeline.sh を1回通してください")

    d = tmp_path_factory.mktemp("hihoken_num")
    for f in ("stdfm.c", "set.h"):
        src = os.path.join(SRC, f)
        if not os.path.exists(src):
            pytest.skip(f"{src} が無い")
        open(d / f, "wb").write(open(src, "rb").read())
    open(d / "harness.c", "wb").write(
        open(os.path.join(HERE, "harness_hihoken_num.c"), "rb").read())

    exe = str(d / "h")
    r = subprocess.run(
        [cc, "-O2", "-w", "-o", exe, "harness.c", "stdfm.c", "-lm"],
        cwd=str(d), capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")

    # raund
    args = ["raund"]
    for a, b in RAUND_CASES:
        args += [a, str(b)]
    r = subprocess.run([exe] + args, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    raund_out = r.stdout.splitlines()
    assert len(raund_out) == len(RAUND_CASES), (
        f"raund の出力が {len(raund_out)} 行（期待 {len(RAUND_CASES)}）")

    # read_csv
    csv = d / "in.csv"
    open(csv, "w", newline="").write(CSV_TEXT)
    r = subprocess.run([exe, "csv", str(csv)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    csv_out = r.stdout.splitlines()
    return raund_out, csv_out, str(csv)


def bits(x):
    return struct.pack(">d", float(x)).hex()


def test_raundが原本と一致(probe):
    raund_out, _, _ = probe
    bad = []
    for (a, b), want in zip(RAUND_CASES, raund_out):
        got = raund(float(a), b)
        if bits(got) != bits(float.fromhex(want)):
            bad.append(f"raund({a}, {b}): C={want} Python={float(got).hex()}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_raundは5の丸めを0から遠い方へ():
    """`(int)(a + 0.5)` の向きを押さえておく。⑤の `nround` と同じ向き。"""
    assert raund(0.5, 0) == 1.0
    assert raund(-0.5, 0) == -1.0
    assert raund(1.5, 0) == 2.0
    assert raund(2.5, 0) == 3.0        # 偶数丸めではない
    assert raund(-2.5, 0) == -3.0
    # `a == 0.0` は else に入るが (int)(-0.5) == 0 なので -0.0 は作らない
    assert bits(raund(0.0, 0)) == bits(0.0)
    assert bits(raund(-0.0, 0)) == bits(0.0)


def test_raundはintをはみ出すと例外():
    """原本は `(int)` のキャストで未定義動作になる。移植版は落とす。

    `|a × 10^b| >= 2^31` になる組は上の突き合わせから外してある。
    gcc/x86-64 の `cvttsd2si` は `INT_MIN`（-2147483648）を返すので、
    原本はそこで**でたらめな値**を出す。移植版は黙って進まず落とす。
    """
    with pytest.raises(CsvError):
        raund(1e18, 0)
    with pytest.raises(CsvError):
        raund(1e6, 4)          # 1e6 × 10^4 = 1e10 > 2^31
    # 10 の冪が int に入らない
    with pytest.raises(CsvError):
        raund(1.0, 10)
    # 上で外した組がちゃんとあることを確かめる（テストが空振りしていない）
    assert len(OVERFLOW_CASES) > 0
    for a, b in OVERFLOW_CASES:
        with pytest.raises(CsvError):
            raund(float(a), b)


def test_read_csvが原本と一致(probe):
    _, csv_out, path = probe
    fp = ReadCsv(path)
    bad = []
    for k, want in enumerate(csv_out):
        parts = want.split()
        rc_c, dn_c = int(parts[0]), int(parts[1])
        vals_c = [float.fromhex(x) for x in parts[2:]]
        buf = [-12345.0] * 130
        rc_p, dn_p = fp.read_csv(buf)
        if (rc_p, dn_p) != (rc_c, dn_c):
            bad.append(f"{k}行目: C=({rc_c},{dn_c}) Python=({rc_p},{dn_p})")
            continue
        for i, v in enumerate(vals_c):
            if bits(buf[i]) != bits(v):
                bad.append(f"{k}行目 [{i}]: C={v!r} Python={buf[i]!r}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_read_csvは31文字を超えたら例外(tmp_path):
    """原本は `char s[31]` の外に書き込む（`検証/原本の不具合.md`）。"""
    p = tmp_path / "long.csv"
    p.write_text("1234567890123456789012345678901234,2\n")
    fp = ReadCsv(str(p))
    with pytest.raises(CsvError):
        fp.read_csv([0.0] * 130)


def test_atofは読めなければ0():
    assert c_atof("") == 0.0
    assert c_atof("abc") == 0.0
    assert c_atof("0x10") == 16.0          # 16進も読む
    assert c_atof("1.5xyz") == 1.5


def test_cdivはCと同じく落ちない():
    """①には分母のゼロを確かめていない割り算がある。実データでも
    配列の端で 0/0 が起きるので、落ちずに nan / inf を返す必要がある。"""
    import math
    assert math.isnan(cdiv(0.0, 0.0))
    assert cdiv(1.0, 0.0) == math.inf
    assert cdiv(-1.0, 0.0) == -math.inf
    assert cdiv(1.0, 4.0) == 0.25


def test_accumulateが逐次加算と一致():
    """`fout.py` / `roudfout.py` が使う年齢の足し方。

    `np.sum` は対和（pairwise）なので順序が違い、`np.add.accumulate` は
    逐次。原本は逐次なので後者を使う。
    """
    rng = np.random.default_rng(0)
    bad = []
    for k in range(30):
        v = rng.standard_normal(106) * 1e6
        s = 0.0
        for x in v:
            s += float(x)
        a = float(np.add.accumulate(v)[-1])
        if bits(s) != bits(a):
            bad.append(f"{k}: loop={s!r} accumulate={a!r}")
    assert not bad, "accumulate が逐次加算と違う:\n  " + "\n  ".join(bad)

    # np.sum は違うことを記録しておく（使ってはいけない理由）
    w = np.full(1000, 0.1)
    seq = 0.0
    for x in w:
        seq += float(x)
    assert bits(seq) == bits(float(np.add.accumulate(w)[-1]))
    assert bits(seq) != bits(float(np.sum(w)))
