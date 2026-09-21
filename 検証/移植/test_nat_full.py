# -*- coding: utf-8 -*-
"""
③国民年金の移植版が原本の出力とバイト一致するか（丸ごと）
===========================================================
`test_nat_stage.py` は段階ごとにグローバル配列を CRC32 で比べ、
`siml` は3年（45年化は15年）しか回さない。こちらは

    種別 2 → 3 → 5 → 6 を、それぞれ 2021〜2125年度の 105年度ぶん

`main.c` と同じ順で丸ごと通して、**出力11本を全部バイト単位で
比べる**。

比べる11本
----------
| 出力先 | ファイル | 中身 |
|---|---|---|
| `rslt` | `HIHO*.csv` | 被保険者数（種別ごとの7表） |
| | `ROREI*.csv` | 新法・旧法老齢、通算老齢、5年年金、基礎年金満額 |
| | `ROREI_SHINKI*.csv` | 老齢基礎の新規裁定（1行1明細。8.5MB） |
| | `SHOGAI*.csv` | 障害基礎（一般・20歳前・旧法） |
| | `IZOKU*.csv` | 遺族基礎・寡婦・死亡一時金 |
| `data` | `KISONENKIN*` | **④基礎年金の入力**（7.1MB） |
| | `DOKUZI*.csv` | 独自給付（付加・寡婦・死亡一時金・国庫負担） |
| | `KOKUKAITE-*.csv` ×2 | 改定率（`econ()` が書く） |
| | `PENSION_*.csv` | 年金額（同） |
| | `nat_wariai*.csv` | 納付状況の割合（**⑥分布推計の入力**） |

合わせて 20MB。

1行目だけは食い違う（2本）
--------------------------
`KISONENKIN` と `DOKUZI` は `write_BeginData()` が**実行時刻**を
書くので、1行目は必ず違う（④の `KYOSHUTUKIN` と同じ）。
移植版は時刻を固定して渡し、**2行目から**比べる。残る9本は
1行目から比べる。

出力先は必ず書き替える
----------------------
③のファイルリストは絶対パスを直に持っているので、そのまま
走らせると `work/` の本物の出力を消す。`test_nat_stage.py` の
`_stage_lists()` を使って `nat/rslt` と `nat/data` を一時
ディレクトリに向ける。

前提
----
- `検証/実行/run_pipeline.sh` を1回通してあること
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本

無ければスキップする。原本で2秒、移植版で4分ほどかかるので
`slow` を付けてある。

    python3 -m pytest 検証/移植/test_nat_full.py -q -m slow -s
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

SYSTEMS = ("clib", "nat")
select(*SYSTEMS)

# 段階テストと同じ仕掛けを使い回す（出力先の書き替えと引数）
from test_nat_stage import (ARGV, FIXED_ASCTIME, SRC, _SRCS,  # noqa: E402
                            _cc, _stage_lists, NAT)

# `write_BeginData()` が実行時刻を書く2本（1行目だけ食い違う）
_TIMESTAMPED = ("KISONENKIN3001-3001-3001", "DOKUZI3001-3001-3001.csv")

_EXPECT = {
    "rslt/HIHO3001-3001-3001.csv": 60000,
    "rslt/IZOKU3001-3001-3001.csv": 250000,
    "rslt/ROREI3001-3001-3001.csv": 450000,
    "rslt/ROREI_SHINKI3001-3001-3001.csv": 8000000,
    "rslt/SHOGAI3001-3001-3001.csv": 150000,
    "data/DOKUZI3001-3001-3001.csv": 20000,
    "data/KISONENKIN3001-3001-3001": 7000000,
    "data/KOKUKAITE-3001-3001E.csv": 100000,
    "data/KOKUKAITE-AK3001E.csv": 0,
    "data/PENSION_3001-3001-3001.csv": 1300000,
    "data/nat_wariai3001-3001.csv": 1900000,
}

_RUNNER = '''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, %r)          # clib
sys.path.insert(0, %r)          # nat
import main as nat_main
nat_main.main([None] + sys.argv[1:], asctime=%r, echo=False)
'''


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    """原本と移植版を別の木で丸ごと走らせる。"""
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）")
    if not os.path.exists(os.path.join(NAT, "io_file", "infile.csv")):
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    cc = _cc()
    if cc is None:
        pytest.skip("C++ コンパイラが無い")

    tmp = tmp_path_factory.mktemp("nat_full")
    bsrc = tmp / "build"
    bsrc.mkdir()
    for f in os.listdir(SRC):
        if f.endswith(".h") or (f.endswith(".c") and f != "main.c"):
            shutil.copyfile(os.path.join(SRC, f), bsrc / f)
    shutil.copyfile(os.path.join(HERE, "harness_nat.cpp"),
                    bsrc / "harness_nat.cpp")

    exe = str(bsrc / "h")
    r = subprocess.run([cc, "-O2", "-w", "-o", exe, "harness_nat.cpp"]
                       + list(_SRCS),
                       cwd=str(bsrc), capture_output=True, text=True)
    assert r.returncode == 0, f"ハーネスのビルドに失敗:\n{r.stderr[:3000]}"

    c_root = str(tmp / "c")
    py_root = str(tmp / "py")
    c_lists = _stage_lists(c_root)
    py_lists = _stage_lists(py_root)

    env = dict(os.environ)
    # 2021年度 ＋ 104年度 = 2125年度まで（原本の `SUIKEISAISHUNENDO`）
    env["SIML_YEARS"] = "104"

    t0 = time.time()
    r = subprocess.run([exe, "printout"] + c_lists + list(ARGV[2:]),
                       cwd=str(bsrc), capture_output=True, timeout=3600,
                       env=env)
    assert r.returncode == 0, (
        "原本が異常終了:\n"
        + r.stderr.decode("utf-8", "replace")[:3000])
    t_c = time.time() - t0

    runner = tmp / "run_main.py"
    runner.write_text(
        _RUNNER % (os.path.join(HERE, "clib"), os.path.join(HERE, "nat"),
                   FIXED_ASCTIME),
        encoding="utf-8")

    t0 = time.time()
    r = subprocess.run([sys.executable, str(runner)]
                       + py_lists + list(ARGV[2:]),
                       capture_output=True, timeout=7200)
    assert r.returncode == 0, (
        "移植版が異常終了:\n"
        + r.stderr.decode("utf-8", "replace")[:3000])
    t_py = time.time() - t0

    print("\n  国民年金 105年度ぶん・4種別・出力 20MB")
    print("  原本（-O2）  %10.1fs" % t_c)
    print("  移植版       %10.1fs  （%.0f倍）" % (t_py, t_py / max(t_c, 1e-9)))

    return c_root, py_root


@pytest.mark.slow
def test_出力11本がCとバイト一致(full):
    """11本（20MB）をバイト単位で比べる。

    `KISONENKIN` と `DOKUZI` だけは1行目に実行時刻が入るので
    2行目から比べる。
    """
    c_root, py_root = full
    bad = []
    for rel in sorted(_EXPECT):
        cp = os.path.join(c_root, rel)
        pp = os.path.join(py_root, rel)
        assert os.path.exists(cp), f"原本が {rel} を書いていない"
        assert os.path.exists(pp), f"移植版が {rel} を書いていない"

        cb = open(cp, "rb").read()
        pb = open(pp, "rb").read()
        if os.path.basename(rel) in _TIMESTAMPED:
            cb = cb.split(b"\n", 1)[1] if b"\n" in cb else b""
            pb = pb.split(b"\n", 1)[1] if b"\n" in pb else b""

        if cb == pb:
            continue

        cl = cb.decode("utf-8", "replace").splitlines()
        pl = pb.decode("utf-8", "replace").splitlines()
        where = "行数が違う（C %d / Python %d）" % (len(cl), len(pl))
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                where = ("%d行目\n      C      %s\n      Python %s"
                         % (i, x[:180], y[:180]))
                break
        bad.append("%s: %s" % (rel, where))

    assert not bad, "原本と一致しない:\n    " + "\n    ".join(bad)


@pytest.mark.slow
def test_出力の大きさが期待どおり(full):
    """空振りしていないことの確かめ。

    `KOKUKAITE-AK*.csv` だけは**原本も 0 バイト**（`econ()` が
    開くだけで書かない。通常試算では従来推計の改定率を出さない）。
    """
    c_root, _ = full
    small = []
    for rel, least in sorted(_EXPECT.items()):
        n = os.path.getsize(os.path.join(c_root, rel))
        if n < least:
            small.append("%s: %d バイト（期待 %d 以上）" % (rel, n, least))
    assert not small, "出力が小さすぎる:\n    " + "\n    ".join(small)

    total = sum(os.path.getsize(os.path.join(c_root, r)) for r in _EXPECT)
    assert total > 19000000, f"合わせて {total} バイト（20MB 弱を期待）"


@pytest.mark.slow
def test_KISONENKINが基礎年金の入力として読める(full):
    """`KISONENKIN` の行の形が④が期待するものになっているか。

    ④基礎年金は「年度, 1, 年齢, 新旧, 種類, 男女」の6欄で引く。
    106年度 × 53歳階級 × 6種類 × 男女 = 67,416行 ＋ 年度ごとの
    まとめ行。**③の出力が④の入力になる**ので、ここが崩れると
    基礎年金拠出金が出せない。
    """
    c_root, _ = full
    p = os.path.join(c_root, "data", "KISONENKIN3001-3001-3001")
    n6 = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            fs = line.rstrip("\n").split(",")
            if len(fs) >= 6 and fs[0][:4].isdigit() and fs[1] == "1":
                n6 += 1
    assert n6 == 106 * 53 * 6 * 2, (
        f"6欄で引ける行が {n6}（期待 {106 * 53 * 6 * 2}）")
