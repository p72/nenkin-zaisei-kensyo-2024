# -*- coding: utf-8 -*-
"""
⑥分布推計の移植版が原本の出力とバイト一致するか
=================================================
原本（C++）と移植版（Python）に**同じ入力**を与えて、出力3ファイル×
コホートをバイト単位で比べる。

比べるのは基準年齢17歳の2コホートだけ
--------------------------------------
`main.cpp` のコホート（性別×基準年齢）は完全に独立している。

- `objects02` と `vector023` は `loop_var002` のループの中で作り直す
- `std::mt19937 gen_rand(0)` も**コホートごとに種 0 でまき直す**
  （`main.cpp:90`）
- 出力もコホートごとに別ファイル

なので、移植版を基準年齢17歳だけに絞って走らせ、`*_17.csv` だけを
比べても照合として有効。17歳は初期母集団が一番小さい
（性別1で473人、性別2で112人。他は13万〜20万人）ので、
テストとして現実的な時間で終わる。

**原本は `-O2` で建て直す**
---------------------------
同梱の `分布推計/Makefile:24` は `-Ofast` を指定しているが、
`-ffast-math` は浮動小数の結合則の書き換えを許すので、IEEE 754 どおりの
Python とは最後の1桁が食い違う（`検証/原本の不具合.md` G1）。
実際 `01_2011_1_1_17.csv` の1つ目の値が

    -O2    90.2981492346258    ← (a/b)*100     IEEE どおり
    -Ofast 90.2981492346259    ← a*(100/b)     書き換えた順

と違う。残り35ファイルは両方で一致する。ここでは `-O2` で建てた原本と
比べる。

前提
----
- `検証/実行/run_bunpu.sh` を1回通してあること
  （`work/suuri/rev2024/bunpu/` に初期母集団と基礎率が揃っていること）
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本が
  あること。`run_pipeline.sh` が同じ既定値で作る

どちらも無ければスキップする。時間がかかる（C 約2分＋Python 約5分）ので
`slow` を付けてある。

> **出力を公表値と比べてはいけない。** 同梱データには初期母集団
> `bunpu/kisosuu/` が欠落しており（仕様書 §12.5）、`make_kisosuu.py` が
> 遷移表から状態別人数を復元して補っている。個人ごとの加入月数と年金額は
> 集計表からは原理的に復元できない。ここで確かめているのは
> **「C と Python が同じ入力から同じ出力を出すか」**だけ。
"""
import io
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "bunpu")
select(*SYSTEMS)
ROOT = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(ROOT, "work", "suuri", "rev2024")
BUNPU = os.path.join(WORK, "bunpu")
# 原本を UTF-8 に変換したもの（run_pipeline.sh が作るビルド用ツリー）
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "分布推計")

# run_bunpu.sh が流す6つの値（外枠2011 / 経済前提3001）
STDIN = "2011\n0\n0\n3001\n3001\n1\n"
WAKU, OF = 2011, 1


def _need(path, what):
    if not os.path.exists(path):
        pytest.skip(f"{what} が無い（{path}）。検証/実行/run_bunpu.sh を"
                    "1回通してから実行してください")


@pytest.fixture(scope="module")
def stage(tmp_path_factory):
    """原本（-O2）と移植版を、同じ入力を見る別のディレクトリで走らせる。"""
    _need(os.path.join(BUNPU, "kisosuu"), "初期母集団 bunpu/kisosuu")
    _need(os.path.join(BUNPU, "kisoritsu"), "基礎率 bunpu/kisoritsu")
    _need(os.path.join(WORK, "emp"), "⑤の出力 emp/")
    _need(os.path.join(WORK, "nat"), "③の出力 nat/")
    _need(SRC, "UTF-8 に変換した原本（BUILD_DIR）")

    cxx = None
    for c in ("g++", "c++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            cxx = c
            break
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")

    # 原本は相対パスで開く（bunpu/exec から起動する前提）。
    #   ../kisosuu   ../kisoritsu   ../rslt   ../../emp   ../../nat
    # なので base/{c,py}/exec を起動位置にして、次の形に組む。
    #   base/emp -> work/…/emp,  base/nat -> work/…/nat
    #   base/{c,py}/{kisosuu,kisoritsu} -> work/…/bunpu/…
    #   base/{c,py}/rslt                  出力先（別々）
    base = tmp_path_factory.mktemp("bunpu_full")
    for name in ("emp", "nat"):
        os.symlink(os.path.join(WORK, name), base / name)
    out = {}
    for who in ("c", "py"):
        d = base / who
        (d / "exec").mkdir(parents=True)
        (d / "rslt").mkdir()
        os.symlink(os.path.join(BUNPU, "kisosuu"), d / "kisosuu")
        os.symlink(os.path.join(BUNPU, "kisoritsu"), d / "kisoritsu")
        out[who] = d
    return base, out, cxx


@pytest.fixture(scope="module")
def c_rslt(stage):
    """原本を `-O2` で建てて走らせる（12コホート全部）。"""
    base, out, cxx = stage
    d = out["c"]
    exe = str(d / "exec" / "prog_o2")
    srcs = sorted(f for f in os.listdir(SRC) if f.endswith(".cpp"))
    r = subprocess.run(
        [cxx, "-O2", "-w", "-I", "ext", "-I", "common", "-I", "lib",
         "-o", exe] + srcs,
        cwd=SRC, capture_output=True, text=True)
    assert r.returncode == 0, f"原本のビルドに失敗:\n{r.stderr[:3000]}"

    t = time.time()
    r = subprocess.run([exe], cwd=str(d / "exec"), input=STDIN.encode(),
                       capture_output=True, timeout=3600)
    assert r.returncode == 0, r.stderr[:2000]
    return d / "rslt", time.time() - t


@pytest.fixture(scope="module")
def py_rslt(stage):
    """移植版を基準年齢17歳だけで走らせる。"""
    base, out, cxx = stage
    d = out["py"]
    import main as bunpu_main

    saved = bunpu_main.BASE_AGES
    bunpu_main.BASE_AGES = [17]          # コホートは独立（上の解説）
    t = time.time()
    try:
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            bunpu_main.run(bunpu_main._Scan(io.StringIO(STDIN)),
                           str(d / "exec"))
    finally:
        bunpu_main.BASE_AGES = saved
    return d / "rslt", time.time() - t


@pytest.mark.slow
@pytest.mark.parametrize("sex", [1, 2])
@pytest.mark.parametrize("kind", ["01", "02", "03"])
def test_出力がCとバイト一致(c_rslt, py_rslt, kind, sex):
    cdir, _ = c_rslt
    pdir, _ = py_rslt
    name = f"{kind}_{WAKU}_{OF}_{sex}_17.csv"
    cf, pf = cdir / name, pdir / name
    assert cf.exists(), f"原本の出力が無い: {cf}"
    assert pf.exists(), f"移植版の出力が無い: {pf}"
    cb, pb = cf.read_bytes(), pf.read_bytes()
    if cb != pb:
        cl = cb.decode("ascii").splitlines()
        pl = pb.decode("ascii").splitlines()
        msg = [f"{name} が一致しない"]
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                msg.append(f"  {i}行目")
                msg.append(f"    C      {x}")
                msg.append(f"    Python {y}")
        assert False, "\n".join(msg)


@pytest.mark.slow
def test_速さを記録(c_rslt, py_rslt, capsys):
    """C と Python の実測を残す。落ちる条件は付けない。"""
    _, ct = c_rslt
    _, pt = py_rslt
    # C は12コホート、Python は17歳の2コホートだけ
    with capsys.disabled():
        print(f"\n  原本（-O2、12コホート）      {ct:8.1f}s")
        print(f"  移植版（17歳の2コホート）    {pt:8.1f}s")
