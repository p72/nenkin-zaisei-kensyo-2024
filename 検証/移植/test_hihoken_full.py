# -*- coding: utf-8 -*-
"""
①被保険者推計の移植版が原本の出力とバイト一致するか
=====================================================
原本（C）と移植版（Python）に**同じ入力**を与えて、出力104ファイルを
バイト単位で比べる。

    waku{BANGO}-err.csv            エラーの記録（空）
    waku{BANGO}-{00..57}.csv       分類別                      58本
    waku{BANGO}-nenreikei.csv      年度末の年齢計
    waku{BANGO}-nenkeikan.csv      年度間の平均      ← 1本だけ一致しない
    waku{BANGO}-settei.csv         設定値の控え
    wakuroud{BANGO}-{00..39}.csv   労働力の分類別              40本
    waku{BANGO}-roudkei.csv        労働力の年齢計
    waku{BANGO}-m.csv              調整率

**`-nenkeikan.csv` だけは一致しない。理由は原本の未初期化読み。**

`fout.c` の `nenrei_kei_ninzu[69][131][5]` は初期化なしの自動変数で、
`nendo = KS`（2021）から `KF` まで、つまり添字 **1〜105** にしか代入しない。
ところが `-nenkeikan.csv` は

```c
raund( ( nenrei_kei_ninzu[bunrui][nendo-STARTY][sei]
       + nenrei_kei_ninzu[bunrui][nendo-1-STARTY][sei] ) / 2.0 , 0 )
```

で `nendo = KS` のとき**添字 0**（一度も書いていない場所）を読む。
実測すると 58×5 = 290 箇所のうち **125 箇所が非ゼロ**で、値は
0.1375 〜 197,626 のばらばらな実数。スタックに残った前の関数の値で、
入力からは決まらない。

証拠として、原本の `fout.c` に

```c
{ int s3 ; for ( s3 = 0 ; s3 <= 4 ; s3++ )
    nenrei_kei_ninzu[bunrui][0][s3] = 0.0 ; }
```

の2行だけを足したものを建てると、**104本すべてが移植版とバイト一致する**。
つまり食い違いはこの1項だけに由来する。移植版は 0 で作るので
「本来意図されたであろう値」を出す。（`検証/原本の不具合.md` H1）

このテストは103本の一致を確かめ、`-nenkeikan.csv` は
**2021年度の行以外が一致すること**を確かめる。

前提
----
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本があること
  （`run_pipeline.sh` が同じ既定値で作る）
- `work/suuri/rev2024/wakuc/data/` に①の入力が揃っていること

どちらも無ければスキップする。時間がかかる（C 数秒＋Python 約10秒）。
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

SYSTEMS = ("clib", "hihokensha")
select(*SYSTEMS)

REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "work", "suuri", "rev2024", "wakuc", "data")
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "被保険者推計")

# run_pipeline.sh が①に流す7つの値（試算番号3001・出生中位・死亡中位・
# 入国16万・労働参加進展・適用拡大なし・基礎40年）
STDIN = "3001\n0\n0\n1\n1\n0\n1\n"
BANGO = 3001

# 原本のパスに埋め込まれているプレフィックス（run_pipeline.sh が書き換える）
_ORIG_PREFIX = "/suuri"


def _stage(tmp, name):
    """`<tmp>/<name>/suuri/rev2024/wakuc/{data,rslt}` を用意する。"""
    root = tmp / name
    w = root / "suuri" / "rev2024" / "wakuc"
    (w / "rslt").mkdir(parents=True)
    os.symlink(DATA, w / "data")
    return root


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """原本と移植版を別のディレクトリに出力させる。"""
    if not os.path.isdir(DATA):
        pytest.skip(f"①の入力が無い（{DATA}）")
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）")
    cc = None
    for c in ("gcc", "cc"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            cc = c
            break
    if cc is None:
        pytest.skip("C コンパイラが無い")

    tmp = tmp_path_factory.mktemp("hihoken_full")
    c_root = _stage(tmp, "c")
    py_root = _stage(tmp, "py")

    # ---- 原本。パスだけ書き換えて建てる（run_pipeline.sh と同じ規則）----
    bsrc = tmp / "build"
    shutil.copytree(SRC, bsrc)
    for f in os.listdir(bsrc):
        if not f.endswith((".c", ".h")):
            continue
        p = bsrc / f
        b = p.read_bytes()
        # `run_pipeline.sh` が絶対パスに書き換えたあとの木を使うことも、
        # 原本のまま（`/suuri/...`）のこともある。**どちらか一方だけ**
        # 置き換える（両方かけると二重に前置してしまう）
        dest = os.path.join(str(c_root), "suuri").encode()
        abs_pref = os.path.join(REPO, "work", "suuri").encode()
        if abs_pref in b:
            b = b.replace(abs_pref, dest)
        else:
            b = b.replace(_ORIG_PREFIX.encode() + b"/rev2024",
                          dest + b"/rev2024")
        # char filename[250] だと長い絶対パスであふれる（原本の不具合 C2/C3）
        b = b.replace(b"char filename[250]", b"char filename[1024]")
        b = b.replace(b"char pathname[250]", b"char pathname[1024]")
        p.write_bytes(b)
    exe = str(bsrc / "waku1")
    srcs = sorted(f for f in os.listdir(bsrc) if f.endswith(".c"))
    r = subprocess.run([cc, "-O2", "-w", "-o", exe] + srcs + ["-lm"],
                       cwd=str(bsrc), capture_output=True, text=True)
    assert r.returncode == 0, f"原本のビルドに失敗:\n{r.stderr[:3000]}"
    t = time.time()
    r = subprocess.run([exe], cwd=str(bsrc), input=STDIN.encode(),
                       capture_output=True, timeout=3600)
    assert r.returncode == 0, r.stderr[:2000]
    ct = time.time() - t

    # ---- 移植版 ----
    # `SUURI_PREFIX` はプロセス全体に効くので、**必ず元に戻す**。
    # 戻さないと、あとに走る⑤のテスト（`test_rdfl_*` / `test_shus_*` /
    # `test_full_emp`）が `econ-3001.csv` を開けずに落ちる
    # （`emp_shushi/fopn.py` が同じ環境変数を見ている）。
    # 実際に `pytest 検証/移植` を丸ごと回して踏んだ。
    saved = os.environ.get("SUURI_PREFIX")
    os.environ["SUURI_PREFIX"] = str(py_root)
    try:
        from cscan import Scan
        import main as waku_main
        import io
        import contextlib
        t = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            waku_main.run(Scan(STDIN))
        pt = time.time() - t
    finally:
        if saved is None:
            os.environ.pop("SUURI_PREFIX", None)
        else:
            os.environ["SUURI_PREFIX"] = saved

    d = f"suuri/rev2024/wakuc/rslt/ver_4_1/rslt{BANGO:04d}"
    return c_root / d, py_root / d, ct, pt


def _names(cdir):
    return sorted(os.listdir(cdir))


@pytest.mark.slow
def test_出力の本数が同じ(runs):
    cdir, pdir, _, _ = runs
    assert _names(cdir) == _names(pdir)
    assert len(_names(cdir)) == 104, f"{len(_names(cdir))} 本しかない"


@pytest.mark.slow
def test_nenkeikan以外はバイト一致(runs):
    cdir, pdir, _, _ = runs
    bad = []
    for name in _names(cdir):
        if name.endswith("-nenkeikan.csv"):
            continue
        cb = (cdir / name).read_bytes()
        pb = (pdir / name).read_bytes()
        if cb != pb:
            cl = cb.decode("utf-8", "replace").splitlines()
            pl = pb.decode("utf-8", "replace").splitlines()
            for i, (x, y) in enumerate(zip(cl, pl), 1):
                if x != y:
                    bad.append(f"{name} の {i}行目\n    C      {x[:160]}\n"
                               f"    Python {y[:160]}")
                    break
            else:
                bad.append(f"{name} の長さが違う "
                           f"（C {len(cb)} / Python {len(pb)}）")
    assert not bad, ("原本と一致しない:\n" + "\n".join(bad[:10])
                     + (f"\n… ほか {len(bad) - 10} 件" if len(bad) > 10
                        else ""))


@pytest.mark.slow
def test_nenkeikanは2021年度の行だけ食い違う(runs):
    """原本が未初期化の値を読むので、2021年度の行だけ再現できない。

    `検証/原本の不具合.md` H1。ここでは
    **2021年度以外の行が一致すること**と、
    **食い違うのが2021年度の5行（性別0〜4）だけであること**を確かめる。
    """
    cdir, pdir, _, _ = runs
    name = f"waku{BANGO:04d}-nenkeikan.csv"
    cl = (cdir / name).read_text(encoding="utf-8").splitlines()
    pl = (pdir / name).read_text(encoding="utf-8").splitlines()
    assert len(cl) == len(pl), f"行数が違う（C {len(cl)} / Python {len(pl)}）"
    diff = [i for i, (x, y) in enumerate(zip(cl, pl), 1) if x != y]
    # 食い違う行はすべて 2021年度の行
    for i in diff:
        assert cl[i - 1].startswith("2021,"), (
            f"{i}行目が2021年度ではないのに食い違う:\n"
            f"  C      {cl[i-1][:160]}\n  Python {pl[i-1][:160]}")
    assert len(diff) == 5, (
        f"食い違う行が {len(diff)} 行（期待 5＝性別0〜4）: {diff}")


@pytest.mark.slow
def test_速さを記録(runs, capsys):
    """C と Python の実測を残す。落ちる条件は付けない。"""
    _, _, ct, pt = runs
    with capsys.disabled():
        print(f"\n  原本（-O2）    {ct:8.1f}s")
        print(f"  移植版         {pt:8.1f}s  （{pt / ct:.1f}倍）")
