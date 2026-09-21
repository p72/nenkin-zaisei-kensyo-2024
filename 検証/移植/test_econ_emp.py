# -*- coding: utf-8 -*-
"""
emp_shushi/econ.py と原本 econ.c をビット単位で突き合わせる
===========================================================
harness_econ.c が原本 econ.c と stdfun.c をそのままリンクして走り、
計算後のグローバル配列を %a（16進浮動小数＝無損失）で吐く。それを
Python 移植版の結果と 1 要素ずつ比べる。1 ビットでも違えば落ちる。

経済前提ファイルは公表データ（papers/001365945）にある 9 本すべてを回す。
zan_jimu は Id_Cid_2 の分岐に効くので 0 と 1 の両方を試す。
"""
import math
import os
import struct
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
REPO = os.path.dirname(os.path.dirname(HERE))
CSRC = os.path.join(REPO, "papers", "001365945", "プログラム", "厚生年金", "収支計算")
ECON_DIR = os.path.join(REPO, "papers", "001365945", "データ", "suuri", "rev2024",
                        "emp", "data", "u-rev", "econ")

SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)

ARRAYS = ("Ri", "H", "Ci", "Ri2", "HCdum", "Id_Hhd", "Id_Cid", "Id_Cid_2")


def find_cc():
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            return cand
    return None


@pytest.fixture(scope="session")
def harness():
    if not os.path.isdir(CSRC):
        pytest.skip("原本のソースが無い（./fetch.sh で取得してください）")
    cc = find_cc()
    if cc is None:
        pytest.skip("C コンパイラが無い")

    exe = os.path.join(tempfile.mkdtemp(prefix="econ_emp_"), "harness")
    r = subprocess.run(
        [cc, "-O0", "-o", exe,
         os.path.join(HERE, "harness_econ.c"),
         os.path.join(CSRC, "econ.c"),
         os.path.join(CSRC, "stdfun.c"),
         "-I", CSRC, "-lm"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")
    return exe


def econ_files():
    if not os.path.isdir(ECON_DIR):
        return []
    return sorted(f for f in os.listdir(ECON_DIR)
                  if f.startswith("econ-") and f.endswith(".csv"))


def run_c(harness, path, zan_jimu):
    r = subprocess.run([harness, path, str(zan_jimu)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = {}
    for ln in r.stdout.splitlines():
        if not ln:
            continue
        name, idx, val = ln.split()
        out.setdefault(name, {})[int(idx)] = float.fromhex(val)
    return out


def run_py(path, zan_jimu):
    """移植版を走らせる。グローバルが1組しか無いので、毎回読み直して
    状態を作り直す（原本もプロセス1回に1計算）。"""
    for m in ("econ", "glva", "stdfun", "cnum", "setconst"):
        sys.modules.pop(m, None)
    import glva
    import econ as econ_mod

    glva.G.zan_jimu = zan_jimu
    with open(path, "r", encoding="euc_jp") as f:
        glva.G.ifp_econ = f
        econ_mod.econ()

    return {n: getattr(glva.G, n) for n in ARRAYS}


def bits(x):
    return struct.pack(">d", float(x)).hex()


def same(a, b):
    a, b = float(a), float(b)
    if math.isnan(a) and math.isnan(b):
        return True
    return bits(a) == bits(b)


@pytest.mark.parametrize("fname", econ_files())
@pytest.mark.parametrize("zan_jimu", [0, 1])
def test_econ_が原本と一致(harness, fname, zan_jimu):
    path = os.path.join(ECON_DIR, fname)
    got_c = run_c(harness, path, zan_jimu)
    got_p = run_py(path, zan_jimu)

    n_checked = 0
    for name in ARRAYS:
        cvals = got_c[name]
        pvals = got_p[name]
        assert len(cvals) == len(pvals), f"{name} の要素数が違う"
        for i in sorted(cvals):
            c = cvals[i]
            p = pvals[i]
            assert same(p, c), (
                f"{fname} zan_jimu={zan_jimu} {name}[{i}]: "
                f"C={c!r} ({float(c).hex()}) Python={float(p)!r} ({float(p).hex()})")
            n_checked += 1

    # 8 配列 × 129 年度
    assert n_checked == 8 * 129, n_checked


def test_econ_ファイルが見つかる():
    """データが無いまま「全部通った」と言わないための番犬。"""
    files = econ_files()
    if not os.path.isdir(ECON_DIR):
        pytest.skip("公表データが無い（./fetch.sh program で取得してください）")
    # papers/001365945 に入っているのは 3001〜3004 と 3201〜3204 の 8 本。
    assert len(files) >= 8, f"経済前提ファイルが {len(files)} 本しか無い"
