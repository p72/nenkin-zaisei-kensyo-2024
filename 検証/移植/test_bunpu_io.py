# -*- coding: utf-8 -*-
"""
bunpu/prog03.py と原本 prog03.cpp を突き合わせる
================================================
⑥分布推計の CSV 読み取り。`func03a`（行を割る）と `func03b`（ファイルを
2次元にする）。

`func03a` には**区切り文字が1つも無い行でフィールドを2回返す**という癖が
ある。`find_first_of` の戻り値（`size_t` の `npos`）を `int` に入れているので
-1 になり、そこから添字の計算が1周ずれる。実測で確かめる。

実データの CSV でも突き合わせる（⑥の入力が揃っていれば）。
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
REPO = os.path.dirname(os.path.dirname(HERE))
CSRC = os.path.join(REPO, "papers", "001365945", "プログラム", "分布推計")

SYSTEMS = ("clib", "bunpu")
select(*SYSTEMS)

from prog03 import func03a, func03b  # noqa: E402

# 区切りの有無・空フィールド・前後の空白など、癖が出る形を並べる
A_CASES = [
    "abc", "a,b", "a,b,c", "", ",", "a,", ",a", ",,", ",,,",
    "1", "1.5", "-1", "0", "a,,b", "  ", " a , b ",
    "0.5,1.5,2.5", "x,y,", "12345", "a,b,c,d,e",
    "1e5", "1,", ",1", "..", "1.2.3",
]


def find_cxx():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="session")
def harness():
    if not os.path.isdir(CSRC):
        pytest.skip("原本のソースが無い（./fetch.sh で取得してください）")
    cxx = find_cxx()
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")

    d = tempfile.mkdtemp(prefix="bunpu_io_")
    build = os.path.join(d, "src")
    os.makedirs(build)
    # 原本を UTF-8 に変換（原本には触らない）
    for fn in ("prog03.cpp", "_prototype.h"):
        with open(os.path.join(CSRC, fn), "rb") as f:
            raw = f.read()
        try:
            txt = raw.decode("euc_jp")
        except UnicodeDecodeError:
            txt = raw.decode("latin-1")
        with open(os.path.join(build, fn), "w", encoding="utf-8") as f:
            f.write(txt)

    exe = os.path.join(d, "harness")
    r = subprocess.run(
        [cxx, "-O2", "-w", "-o", exe,
         os.path.join(HERE, "harness_bunpu_io.cpp"),
         os.path.join(build, "prog03.cpp"), "-I", build],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")
    return exe


def parse_fields(parts):
    """`<長さ>:<中身>` の並びを文字列のリストに戻す。

    中身に空白が入っていると分割が崩れるので、長さを見て組み直す。
    """
    out = []
    for tok in parts:
        n, _, s = tok.partition(":")
        out.append((int(n), s))
    return out


def run_a(harness, cases):
    r = subprocess.run([harness, "a"] + cases, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode("latin-1")
    res = []
    for ln in r.stdout.decode("latin-1").splitlines():
        if not ln.startswith("a "):
            continue
        p = ln.split(" ")
        cnt = int(p[1])
        # 長さを使って復元する（中身に空白があっても崩れないように）
        fields = []
        rest = ln.split(" ", 2)[2] if cnt else ""
        i = 0
        for _ in range(cnt):
            colon = rest.index(":", i)
            ln_len = int(rest[i:colon])
            fields.append(rest[colon + 1:colon + 1 + ln_len])
            i = colon + 1 + ln_len
            if i < len(rest) and rest[i] == " ":
                i += 1
        res.append(fields)
    return res


def test_func03aが原本と一致(harness):
    got_c = run_a(harness, A_CASES)
    assert len(got_c) == len(A_CASES), (
        f"ハーネスが {len(got_c)} 件しか返していない")
    bad = []
    for s, c in zip(A_CASES, got_c):
        p = func03a(s, ",")
        if p != c:
            bad.append(f"{s!r}: C={c} Python={p}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_区切りの無い行はフィールドが2回返る():
    """原本の癖。ここが直ってしまうと列数が変わる（退行防止）。"""
    assert func03a("abc", ",") == ["abc", "abc"]
    assert func03a("1.5", ",") == ["1.5", "1.5"]
    # カンマが1つでもあれば普通に分割される
    assert func03a("a,b", ",") == ["a", "b"]
    assert func03a("a,", ",") == ["a"]


def test_func03bが原本と一致(harness, tmp_path):
    """作った CSV で読み飛ばし行数と空行の打ち切りを確かめる。"""
    cases = [
        ("a,b,c\n1,2,3\n4,5,6\n", 0),
        ("a,b,c\n1,2,3\n4,5,6\n", 1),
        ("h1\nh2\n1,2\n3,4\n", 2),
        ("1,2\n\n3,4\n", 0),            # 空行で打ち切る
        ("nocomma\n1,2\n", 0),          # 区切りの無い行が混ざる
        ("1,2\n3,4", 0),                # 末尾に改行が無い
        ("", 0),                        # 空ファイル
        ("\n", 0),                      # 改行だけ
        ("a,b\n", 5),                   # 読み飛ばしが行数を超える
    ]
    bad = []
    for i, (body, skip) in enumerate(cases):
        p = tmp_path / f"t{i}.csv"
        p.write_bytes(body.encode("ascii"))
        r = subprocess.run([harness, "b", str(p), str(skip)],
                           capture_output=True, timeout=60)
        assert r.returncode == 0, r.stderr.decode("latin-1")
        out = r.stdout.decode("latin-1").splitlines()
        n_c = int(out[0].split()[1])
        rows_c = []
        for ln in out[1:]:
            if not ln.startswith("br "):
                continue
            q = ln.split(" ")
            cnt = int(q[2])
            rest = ln.split(" ", 3)[3] if cnt else ""
            fields = []
            k = 0
            for _ in range(cnt):
                colon = rest.index(":", k)
                L = int(rest[k:colon])
                fields.append(rest[colon + 1:colon + 1 + L])
                k = colon + 1 + L
                if k < len(rest) and rest[k] == " ":
                    k += 1
            rows_c.append(fields)
        rows_p = func03b(str(p), skip)
        if len(rows_p) != n_c or rows_p != rows_c:
            bad.append(f"{body!r} skip={skip}: C={rows_c} Python={rows_p}")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)


def test_開けないファイルは空リスト(harness, tmp_path):
    missing = str(tmp_path / "no_such_file.csv")
    r = subprocess.run([harness, "b", missing, "0"],
                       capture_output=True, timeout=60)
    assert r.returncode == 0
    assert int(r.stdout.decode("latin-1").splitlines()[0].split()[1]) == 0
    assert func03b(missing, 0) == []


def _bunpu_dir():
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        prefix = os.path.join(REPO, "work")
    return prefix.rstrip("/") + "/suuri/rev2024/bunpu"


@pytest.mark.slow
def test_実データのCSVでも一致(harness):
    """⑥の実際の入力でも突き合わせる（あれば）。"""
    base = _bunpu_dir()
    cands = []
    for rel in ("kisoritsu/kisoritsu08/table_souhoushuu.csv",
                "kisosuu/1/17/kisosuu_set.csv",
                "kisosuu/2/17/kisosuu_set.csv"):
        p = os.path.join(base, rel)
        if os.path.isfile(p):
            cands.append(p)
    if not cands:
        pytest.skip("⑥の入力が無い（検証/実行/run_bunpu.sh を先に実行）")

    n_rows = 0
    for p in cands:
        for skip in (0, 1, 7):
            r = subprocess.run([harness, "b", p, str(skip)],
                               capture_output=True, timeout=300)
            assert r.returncode == 0
            n_c = int(r.stdout.decode("latin-1").splitlines()[0].split()[1])
            rows_p = func03b(p, skip)
            assert len(rows_p) == n_c, (
                f"{os.path.basename(p)} skip={skip}: "
                f"行数 C={n_c} Python={len(rows_p)}")
            n_rows += len(rows_p)
    assert n_rows > 0
    print(f"\n  実データ {len(cands)} ファイル / 計 {n_rows} 行が一致")
