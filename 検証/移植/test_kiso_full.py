# -*- coding: utf-8 -*-
"""
④基礎年金の移植版が原本の出力とバイト一致するか
=================================================
原本（C++）と移植版（Python）に**同じ入力**を与えて、出力をバイト単位で
比べる。④は分岐で通る経路がまるごと変わるので**2通り**流す。

ケース1（`tyousei`）— `run_pipeline.sh` の1周目
-----------------------------------------------
`TOUGOU = 0` / `CUT_KOTEI = 0`。④が自前で有限均衡を解く。

    settei/SETTEI_{Version}-{Version_cut}      カット終了年度（追記）
    data/KYOSHUTUKIN{Version}-{YOBI}           ⑤へ渡す拠出金   7.4MB
    rslt/TUMATUMI-…-00.csv                     妻積の分配
    rslt/kekka…b.csv                           調整前の結果
    rslt/kekka…a.csv                           調整後の結果
    rslt/cuta-…csv                             ⑤へ渡すカット率
    rslt/output.csv                            代替率と終了年度（追記）

`tyousei()` → `Atamawari_cut()` を 160 回くらい、`file_write_cut()`、
`printout()` の「最終カット率」まで通る。

ケース2（`read_cut`）— `run_pipeline.sh` の2周目（調整期間一致）
----------------------------------------------------------------
`TOUGOU = 1` / `CUT_KOTEI = 1`。⑤が出した統一カット率を読む。
ケース1では1行も通らない経路が動く。

    file_open   「B」（`CUT_KOTEI == 1` で cuta を開く）と
                「D」（`TOUGOU == 1` で provide を書く）
    read_cut    ⑤のカット率を読み、2121年度以降を年齢をずらして伸ばす
                （**閉じていないストリームを閉じる**移植パッチの経路）
    dokuzi_cal  `tyousei()` の代わりに独自給付と改定率を直す
    file_write_kakyu  制度 7（国年）・8（特別国庫）のブロック
    printout    provide ファイル（`cut_ba == 0 && TOUGOU == 1`）

出力は上の7本に `data/provide{Version}-{YOBI}.csv` が増え、
`KYOSHUTUKIN` は 7.4MB → 9.5MB になる。

`KYOSHUTUKIN` の1行目だけは一致しない
-------------------------------------
`stdfm.c:160` の `write_BeginData` が

```c
time( &w_time ) ; w_tm = localtime( &w_time ) ;
fprintf( fp , "%s", asctime( w_tm ) ) ;
```

と**実行した時刻**を書くので、原本と移植版で必ず違う。日付の書式
（`Sun Sep 20 11:05:49 2026`）は合わせてあるが、秒がずれる。
このテストは1行目を除いて比べ、**1行目が `asctime` の書式であること**
だけを確かめる。

標準出力も突き合わせる
----------------------
④は `cout` で進み方と「マクロ経済スライド終了年度」「最終カット率」
「代替率換算」を出す。ここも1文字も違わないことを確かめる
（`%11.9e` と `%f` の書式まで）。

前提
----
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本が
  あること（`run_pipeline.sh` が同じ既定値で作る）
- `work/suuri/rev2024` に①②③の出力が揃っていること
  （`nat/data/KISONENKIN…`、`emp/rslt/u-rev/kiso/kiso.…`、
  `wakuc/rslt/ver_4_1/rslt3001/waku3001-*.csv`）
- ケース2はさらに `emp/rslt/ez_arev/cutr/cuta-…-1120-000.csv`
  （⑤が出す統一カット率）が要る

無ければスキップする。時間がかかる（1ケースあたり C 3秒＋Python 12秒）。
"""
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "kiso_nenkin")
select(*SYSTEMS)

REPO = os.path.dirname(os.path.dirname(HERE))
SUURI = os.path.join(REPO, "work", "suuri", "rev2024")
IO = os.path.join(SUURI, "bas", "io_file")
BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "基礎年金")

VERSION = "3001-3001-3001-3001"
VERSION_CUT = "1120-000"
YOBI = "000"

_COMMON = (
    "settei/SETTEI_%s-%s" % (VERSION, VERSION_CUT),
    "data/KYOSHUTUKIN%s-%s" % (VERSION, YOBI),
    "rslt/TUMATUMI-3001-3001-3001-%s-00.csv" % YOBI,
    "rslt/kekka%s-%sb.csv" % (VERSION, VERSION_CUT),
    "rslt/kekka%s-%sa.csv" % (VERSION, VERSION_CUT),
    "rslt/cuta-%s-%s.csv" % (VERSION, VERSION_CUT),
    "rslt/output.csv",
)

# 時刻が入るので1行目だけ突き合わせないファイル
TIMESTAMPED = "data/KYOSHUTUKIN%s-%s" % (VERSION, YOBI)

# `run_pipeline.sh` が④に渡す17個のうち argv[3] 以降の15個。
#   試算,国年,経済,外枠,外枠(カット),予備,過去分,キャリーオーバー,
#   名目下限撤廃,オプション,オプション開始,引上げ間隔,調整期間一致,
#   カット率固定,一本出し
CASES = {
    "tyousei": {
        "args": ["3001", "3001", "3001", "3001", "3001", YOBI,
                 "0", "1", "0", "0", "2031", "3", "0", "0", "0"],
        "outputs": _COMMON,
        "needs_cutr": False,
    },
    "read_cut": {
        "args": ["3001", "3001", "3001", "3001", "3001", YOBI,
                 "0", "1", "0", "0", "2031", "3", "1", "1", "0"],
        "outputs": _COMMON + ("data/provide%s-%s.csv" % (VERSION, YOBI),),
        "needs_cutr": True,
    },
}

# glibc の `asctime` は `"%.3s %.3s%3d %.2d:%.2d:%.2d %d\n"`。
# 日が幅3の右詰めなので、月のあとは「空白＋空白＋数字」〜「数字2桁」の3文字
_ASCTIME = re.compile(
    r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[ \d]{2}\d \d\d:\d\d:\d\d \d{4}$")

_CUTR = os.path.join(SUURI, "emp", "rslt", "ez_arev", "cutr",
                     "cuta-%s-%s.csv" % (VERSION, VERSION_CUT))


def _stage(tmp, name):
    """`<tmp>/<name>/bas/{rslt,data,settei}` と書き換えた一覧を用意する。"""
    root = tmp / name
    base = root / "bas"
    for d in ("rslt", "data", "settei"):
        (base / d).mkdir(parents=True)
    shutil.copyfile(os.path.join(IO, "infile.csv"), root / "infile.csv")
    b = open(os.path.join(IO, "outfile.csv"), "rb").read()
    b = b.replace(os.path.join(SUURI, "bas").encode(), str(base).encode())
    open(root / "outfile.csv", "wb").write(b)
    return root


def _cc():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """原本を UTF-8 に変換した木から1回だけ建てる。"""
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）")
    if not os.path.isdir(IO):
        pytest.skip(f"④の入出力一覧が無い（{IO}）")
    need = (
        os.path.join(SUURI, "nat", "data", "KISONENKIN3001-3001-3001"),
        os.path.join(SUURI, "emp", "rslt", "u-rev", "kiso",
                     "kiso.3001-3001-3001_kou"),
        os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", "rslt3001",
                     "waku3001-m.csv"),
    )
    for p in need:
        if not os.path.exists(p):
            pytest.skip(f"④の入力が無い（{p}）")

    cc = _cc()
    if cc is None:
        pytest.skip("C++ コンパイラが無い")

    bsrc = tmp_path_factory.mktemp("kiso_build")
    for f in os.listdir(SRC):
        if f.endswith((".c", ".h")):
            shutil.copyfile(os.path.join(SRC, f), bsrc / f)
    exe = str(bsrc / "ver0000.out")
    srcs = sorted(f for f in os.listdir(bsrc) if f.endswith(".c"))
    r = subprocess.run([cc, "-O2", "-w", "-o", exe] + srcs,
                       cwd=str(bsrc), capture_output=True, text=True)
    assert r.returncode == 0, f"原本のビルドに失敗:\n{r.stderr[:3000]}"
    return exe, str(bsrc)


@pytest.fixture(scope="module")
def runs(built, tmp_path_factory):
    """ケースごとに原本と移植版を別のディレクトリに出力させる。"""
    exe, cwd = built
    out = {}

    runner = tmp_path_factory.mktemp("kiso_runner") / "run_py.py"
    runner.write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n"       # clib（`cnum.py` が読む `libc.py`）
        "sys.path.insert(0, %r)\n"       # kiso_nenkin
        "import main\n"
        "main.run(['ver0000'] + sys.argv[1:])\n"
        % (os.path.join(HERE, "clib"), os.path.join(HERE, "kiso_nenkin")),
        encoding="utf-8")

    for key, case in CASES.items():
        if case["needs_cutr"] and not os.path.exists(_CUTR):
            out[key] = ("skip", f"⑤の統一カット率が無い（{_CUTR}）")
            continue

        tmp = tmp_path_factory.mktemp("kiso_" + key)
        c_root = _stage(tmp, "c")
        py_root = _stage(tmp, "py")

        t = time.time()
        r = subprocess.run([exe, str(c_root / "infile.csv"),
                            str(c_root / "outfile.csv")] + case["args"],
                           cwd=cwd, capture_output=True, timeout=3600)
        assert r.returncode == 0, (
            f"[{key}] 原本が異常終了: "
            + r.stderr.decode("utf-8", "replace")[:2000])
        c_out = r.stdout.decode("utf-8")
        ct = time.time() - t

        t = time.time()
        r = subprocess.run([sys.executable, str(runner),
                            str(py_root / "infile.csv"),
                            str(py_root / "outfile.csv")] + case["args"],
                           capture_output=True, timeout=3600)
        assert r.returncode == 0, (
            f"[{key}] 移植版が異常終了: "
            + r.stderr.decode("utf-8", "replace")[:3000])
        py_out = r.stdout.decode("utf-8")
        pt = time.time() - t

        out[key] = ("ok", (c_root / "bas", py_root / "bas", c_out, py_out,
                           ct, pt))
    return out


def _get(runs, key):
    state, val = runs[key]
    if state == "skip":
        pytest.skip(val)
    return val


def _names(d):
    got = []
    for root, _dirs, files in os.walk(str(d)):
        for f in files:
            got.append(os.path.relpath(os.path.join(root, f), str(d)))
    return sorted(got)


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(CASES))
def test_出力の本数が同じ(runs, key):
    cdir, pdir, _, _, _, _ = _get(runs, key)
    assert _names(cdir) == _names(pdir)
    assert _names(cdir) == sorted(CASES[key]["outputs"]), (
        f"[{key}] 出力が想定と違う: {_names(cdir)}")


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(CASES))
def test_KYOSHUTUKIN以外はバイト一致(runs, key):
    cdir, pdir, _, _, _, _ = _get(runs, key)
    bad = []
    for name in CASES[key]["outputs"]:
        if name == TIMESTAMPED:
            continue
        cb = (cdir / name).read_bytes()
        pb = (pdir / name).read_bytes()
        if cb == pb:
            continue
        cl = cb.decode("utf-8", "replace").splitlines()
        pl = pb.decode("utf-8", "replace").splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                bad.append(f"{name} の {i}行目\n    C      {x[:200]}\n"
                           f"    Python {y[:200]}")
                break
        else:
            bad.append(f"{name} の長さが違う "
                       f"（C {len(cb)} / Python {len(pb)}）")
    assert not bad, f"[{key}] 原本と一致しない:\n" + "\n".join(bad[:10])


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(CASES))
def test_KYOSHUTUKINは1行目の時刻以外が一致(runs, key):
    """`write_BeginData` が実行時刻を書くので1行目だけは一致しない。"""
    cdir, pdir, _, _, _, _ = _get(runs, key)
    cb = (cdir / TIMESTAMPED).read_bytes()
    pb = (pdir / TIMESTAMPED).read_bytes()

    c1, _, crest = cb.partition(b"\n")
    p1, _, prest = pb.partition(b"\n")

    assert _ASCTIME.match(c1.decode()), f"原本の1行目が asctime でない: {c1!r}"
    assert _ASCTIME.match(p1.decode()), f"移植の1行目が asctime でない: {p1!r}"

    assert len(crest) == len(prest), (
        f"[{key}] 2行目以降の長さが違う"
        f"（C {len(crest)} / Python {len(prest)}）")
    assert crest == prest, f"[{key}] 2行目以降が一致しない"


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(CASES))
def test_標準出力が一致(runs, key):
    """進み方と数字の書式まで1文字も違わないこと。"""
    _, _, c_out, py_out, _, _ = _get(runs, key)
    assert c_out == py_out, (
        f"[{key}] 標準出力が違う:\n--- C ---\n" + c_out[-800:]
        + "\n--- Python ---\n" + py_out[-800:])


@pytest.mark.slow
def test_tyouseiのケースは終了年度と代替率を出す(runs):
    """空振りしていないことの確かめ。`tyousei()` を通る経路だけ。"""
    _, _, c_out, _, _, _ = _get(runs, "tyousei")
    assert "マクロ経済スライド終了年度" in c_out
    assert "最終カット率" in c_out
    assert "代替率換算" in c_out


@pytest.mark.slow
def test_read_cutのケースはtyouseiを通らない(runs):
    """ケース2が本当に別の経路を通っていることの確かめ。"""
    _, _, c_out, _, _, _ = _get(runs, "read_cut")
    assert "read_cut" in c_out
    assert "dokuzi_cal" in c_out
    assert "tyousei" not in c_out


@pytest.mark.slow
def test_速さを記録(runs, capsys):
    """C と Python の実測を残す。落ちる条件は付けない。"""
    with capsys.disabled():
        print()
        for key in sorted(CASES):
            state, val = runs[key]
            if state == "skip":
                print(f"  {key:10s} スキップ")
                continue
            _, _, _, _, ct, pt = val
            print(f"  {key:10s} 原本（-O2） {ct:6.1f}s / "
                  f"移植版 {pt:6.1f}s  （{pt / ct:.1f}倍）")
