# -*- coding: utf-8 -*-
"""
②厚生年金給付費推計の移植版が原本の出力とバイト一致するか（丸ごと）
=====================================================================
`test_kyufu_stage.py` は段階ごとにグローバル配列を CRC32 で比べる。
こちらは **`sepsd()` を KIJUN〜KE（105年度）で丸ごと通して、
出力ファイルを全部バイト単位で比べる**。

比べるのは厚生年金（`pseid = 0`）だけ
-------------------------------------
`main.cpp` は `pseid` を 0（厚年）→ 1（国共済）→ 4（地共済）→
5（私学共済）と回す。**制度どうしは完全に独立**で、

- `zero_sepsd()` が制度ごとに配列を 0 に戻す
- 出力も `shus.{試算}_kou` のように制度名が付く
  （付かない5本は K1 で上書きされる。下記）

なので厚年だけを通して比べても照合として有効。105年度ぶんの
出力は 383MB・18ファイルになる。共済の枝は
`test_kyufu_stage.py` の `out:1` 段階が短く通している。

**原本は `-O2` で建てる**
-------------------------
同梱の `厚生年金/給付費推計/Makefile:68` は `-O2`（`-fast -xo2` の行は
コメントアウト済み）。`-Ofast` で建てると 12本のうち 11本が
食い違う（`検証/原本の不具合.md` G2）ので、原本の指定どおり
`-O2` で建てる。

一致しない3本 — H3
------------------
`pstat.cpp:11-35` の3つの小関数が `csv::join(...).c_str()` を返す。
`std::string` を値で返すので、`.c_str()` は `return` 文の終わりで
壊される一時オブジェクトの中を指す（use-after-free）。**原本の側で
数値の欄が数バイトのごみに化ける。**

    hikaku.*        216行のうち130行
    ashimotosum.*   581行のうち360行
    ashimotossum.*  581行のうち360行

ごみは ASLR で**実行のたびに変わる**（同じバイナリ・同じ入力でも。
`setarch -R` で ASLR を切ると再現する）。移植版は正しい文字列を
渡すので、この3本は一致しない。`検証/原本の不具合.md` の H3。

    test_出力がCとバイト一致        15ファイル（383MB）
    test_pstatの3本だけが化けている  3ファイル

前提
----
- `検証/実行/run_pipeline.sh` を1回通してあること
  （`work/suuri/rev2024/emp/data` と `wakuc/rslt/ver_4_1/rslt3001`）
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本

無ければスキップする。原本で数分、移植版で1〜2時間かかるので
`slow` を付けてある。

    python3 -m pytest 検証/移植/test_kyufu_full.py -q -m slow -s
"""
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "emp_kyufu")
select(*SYSTEMS)

REPO = os.path.dirname(os.path.dirname(HERE))
SUURI = os.path.join(REPO, "work", "suuri", "rev2024")
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "厚生年金", "給付費推計")

# 原本が埋め込んでいる出力先（`run_pipeline.sh` が書き換えたあとの値）
_BASE_DIR = SUURI.encode()

# main.cpp の4つ ＋ cntl.cpp の6つ（run_pipeline.sh 3001 の既定と同じ）
STDIN = "11\n3001\n3001\n3001\n4\n0\n0\n0\n0\n0\n"

_OUT_DIRS = [
    "emp/rslt/u-rev/shus", "emp/rslt/u-rev/shusg", "emp/rslt/u-rev/kiso",
    "emp/rslt/u-rev/kisor", "emp/rslt/u-rev/hou", "emp/rslt/u-rev/kaite",
    "emp/rslt/u-rev/hikaku", "emp/rslt/u-rev/ashimoto",
    "emp/rslt/u-rev/bunpu", "emp/rslt/u-rev/prt",
]

# H3 で原本の側が化ける3本（`pstat.cpp` の `hikaku_ns` を通るもの）
H3_FILES = (
    "u-rev/hikaku/hikaku.3001-3001-3001",
    "u-rev/ashimoto/ashimotosum.3001-3001-3001",
    "u-rev/ashimoto/ashimotossum.3001-3001-3001",
)


def _tree(root):
    base = os.path.join(root, "suuri", "rev2024")
    for d in _OUT_DIRS:
        os.makedirs(os.path.join(base, d), exist_ok=True)
    os.makedirs(os.path.join(base, "emp"), exist_ok=True)
    os.symlink(os.path.join(SUURI, "emp", "data"),
               os.path.join(base, "emp", "data"))
    os.symlink(os.path.join(SUURI, "wakuc"), os.path.join(base, "wakuc"))
    return base


def _files(rslt):
    got = {}
    for root, _d, fs in os.walk(rslt):
        for f in fs:
            p = os.path.join(root, f)
            got[os.path.relpath(p, rslt)] = p
    return got


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    """原本（`-O2`）と移植版を別の木で丸ごと走らせる。"""
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）")
    for p in (os.path.join(SUURI, "emp", "data", "u-rev", "econ",
                           "econ-3001.csv"),
              os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", "rslt3001",
                           "waku3001-20.csv")):
        if not os.path.exists(p):
            pytest.skip(f"②の入力が無い（{p}）")
    cxx = None
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            cxx = c
            break
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")

    tmp = tmp_path_factory.mktemp("kyufu_full")
    c_base = _tree(str(tmp / "c"))
    py_base = _tree(str(tmp / "py"))

    # 原本は `main.cpp` の代わりにハーネスの `full` 段階で走らせる
    # （`sepsd()` を1制度ぶん呼ぶだけ。`main.cpp` は4制度を回すので
    #  K1 で確認用の5本が上書きされてしまう）
    bsrc = tmp / "build"
    bsrc.mkdir()
    for f in os.listdir(SRC):
        s = os.path.join(SRC, f)
        if os.path.isdir(s):
            shutil.copytree(s, bsrc / f)
        elif f.endswith(".cpp") and f != "main.cpp":
            shutil.copyfile(s, bsrc / f)
    shutil.copyfile(os.path.join(HERE, "harness_kyufu.cpp"),
                    bsrc / "harness_kyufu.cpp")
    p = bsrc / "fileio.cpp"
    b = p.read_bytes()
    assert _BASE_DIR in b, (
        f"fileio.cpp に {_BASE_DIR!r} が無い。run_pipeline.sh が"
        "書き換えた木を使っているか確認すること")
    p.write_bytes(b.replace(_BASE_DIR, c_base.encode()))

    exe = str(bsrc / "h")
    srcs = sorted(f for f in os.listdir(bsrc) if f.endswith(".cpp"))
    r = subprocess.run([cxx, "-O2", "-w", "-I", "ext", "-I", "common",
                        "-I", "lib", "-o", exe] + srcs,
                       cwd=str(bsrc), capture_output=True, text=True)
    assert r.returncode == 0, f"原本のビルドに失敗:\n{r.stderr[:3000]}"

    t = time.time()
    r = subprocess.run([exe, "full"], cwd=str(bsrc), input=STDIN.encode(),
                       capture_output=True, timeout=7200)
    assert r.returncode == 0, ("原本が異常終了:\n"
                               + r.stderr.decode("utf-8", "replace")[:3000])
    ct = time.time() - t

    # 移植版は別プロセスで走らせる（`G` が1組しか無いので）
    runner = tmp / "run_py.py"
    runner.write_text(_RUNNER % os.path.join(HERE, "emp_kyufu"),
                      encoding="utf-8")
    env = dict(os.environ, SUURI_PREFIX=str(tmp / "py"))
    t = time.time()
    r = subprocess.run([sys.executable, str(runner)], input=STDIN.encode(),
                       capture_output=True, timeout=21600, env=env)
    assert r.returncode == 0, ("移植版が異常終了:\n"
                               + r.stderr.decode("utf-8", "replace")[:3000])
    pt = time.time() - t

    c_rslt = os.path.join(c_base, "emp", "rslt")
    py_rslt = os.path.join(py_base, "emp", "rslt")
    return (c_rslt, py_rslt, c_base, py_base, ct, pt)


# 移植版の厚生年金を丸ごと走らせる（ハーネスの `full` 段階と同じ）
_RUNNER = '''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, %r)
import glva, cntl, sepsd
from cinstream import Cin
from glva import G

cin = Cin(sys.stdin.read())
G.key = cin.int_()
G.iname = cin.int_()
G.iecon = cin.int_()
G.iwname = cin.int_()
assert G.iwname >= 1000
G.seidver = 1
glva.zero_init()
cntl.cntl(cin)
G.pseid = 0
G.konen = 1
glva.zero_sepsd()
sepsd.sepsd()
'''


@pytest.mark.slow
def test_出力がCとバイト一致(full):
    """105年度ぶんの出力18ファイルのうち、H3 の3本以外が一致するか。

    `kiso.*_kou` だけは `flck()` が自分の絶対パスを書くので、
    出力先の違いを読み替えてから比べる。
    """
    c_rslt, py_rslt, c_base, py_base, _ct, _pt = full
    ct, pt = _files(c_rslt), _files(py_rslt)
    assert ct, "原本が1つもファイルを書いていない"
    assert sorted(ct) == sorted(pt), (
        "書いたファイルの顔ぶれが違う\n  原本のみ: %s\n  移植版のみ: %s"
        % (sorted(set(ct) - set(pt)), sorted(set(pt) - set(ct))))

    itti = []
    bad = []
    for rel in sorted(ct):
        if rel.replace(os.sep, "/") in H3_FILES:
            continue
        cb = open(ct[rel], "rb").read()
        pb = open(pt[rel], "rb").read()
        if cb == pb:
            itti.append(rel)
            continue
        # 来歴は自分の絶対パスを書くので読み替える
        cs = cb.decode("utf-8", "replace").replace(c_base, "PFX")
        ps = pb.decode("utf-8", "replace").replace(py_base, "PFX")
        if cs == ps:
            itti.append(rel)
            continue
        cl, pl = cs.splitlines(), ps.splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                bad.append(f"{rel} の {i}行目\n    C      {x[:200]}\n"
                           f"    Python {y[:200]}")
                break
        else:
            bad.append(f"{rel} の行数が違う "
                       f"（C {len(cl)} / Python {len(pl)}）")
    assert not bad, "原本と一致しない:\n" + "\n".join(bad[:20])
    # 空振りしていないことの確かめ
    assert len(itti) == 15, f"一致したのが {len(itti)} 本（期待 15）"
    ookii = [r for r in itti if os.path.getsize(ct[r]) > 10_000_000]
    assert len(ookii) >= 8, (
        f"10MB 超のファイルが {len(ookii)} 本しか一致していない")


@pytest.mark.slow
def test_pstatの3本だけが化けている(full):
    """H3。原本の側だけ数値の欄がごみに化ける3本。

    行数は同じ・見出しと単位は一致・原本の側は数値として読めない、
    という形を固定する（`test_kyufu_stage.py` と同じ確かめ方）。
    """
    c_rslt, py_rslt, _cb, _pb, _ct, _pt = full
    ct, pt = _files(c_rslt), _files(py_rslt)
    for rel in H3_FILES:
        key = rel.replace("/", os.sep)
        assert key in ct, f"原本が {rel} を書いていない"
        cl = open(ct[key], "rb").read().split(b"\n")
        pl = open(pt[key], "rb").read().split(b"\n")
        assert len(cl) == len(pl), (
            f"{rel} の行数が違う（C {len(cl)} / Python {len(pl)}）。"
            "H3 は数値の欄だけを壊すので行数は変わらないはず")
        kowareta = 0
        for i, (a, b) in enumerate(zip(cl, pl), 1):
            if a == b:
                continue
            kowareta += 1
            h = 0
            while h < min(len(a), len(b)) and a[h] == b[h]:
                h += 1
            t = 0
            while (t < min(len(a), len(b)) - h
                   and a[len(a) - 1 - t] == b[len(b) - 1 - t]):
                t += 1
            gomi = a[h:len(a) - t]
            hontai = b[h:len(b) - t]
            for x in hontai.split(b","):
                float(x.strip())        # 移植版は数値として読める
            assert len(gomi) < len(hontai), (
                f"{rel}:{i} 原本の側が短くなっていない: {gomi!r}")
            try:
                float(gomi.split(b",")[0].strip())
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"{rel}:{i} 原本の側が数値として読めてしまう: "
                    f"{gomi!r}。H3 を再現できていない")
        assert kowareta, f"{rel} に化けた行が無い。H3 が起きていない"


@pytest.mark.slow
def test_速さを記録(full, capsys):
    """C と Python の実測を残す。落ちる条件は付けない。"""
    c_rslt, py_rslt, _cb, _pb, ct, pt = full
    n = sum(os.path.getsize(p) for p in _files(c_rslt).values())
    with capsys.disabled():
        print(f"\n  厚生年金 105年度ぶん・出力 {n / 1e6:.0f}MB")
        print(f"  原本（-O2）    {ct:8.1f}s")
        print(f"  移植版         {pt:8.1f}s  （{pt / ct:.0f}×）")
