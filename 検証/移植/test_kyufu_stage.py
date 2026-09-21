# -*- coding: utf-8 -*-
"""
②厚生年金給付費推計の移植を段階ごとに原本と突き合わせる
=========================================================
②は 10,870行・34本の .cpp で、出力は 5.2GB になる。丸ごと突き合わせる
前に、**計算の段階ごとにグローバル配列を比べる**（⑤の
`test_rdfl_emp.py` `test_shus_emp.py` と同じやり方）。

`harness_kyufu.cpp` が原本の .cpp を**無修正でリンク**して
`main.cpp` の代わりに走り、指定した段階までのグローバル配列を
**CRC32** で出す。CRC32 は C の行優先（row-major）で 8 バイトずつ
食わせるので、NumPy の `arr.tobytes()` と同じ並びになる。
倍精度をビット単位で比べていることになる。

    ./h cntl   main.cpp の入力4つ → zero_init → cntl
    ./h waku   ↑に続けて pseid=0 で zero_sepsd → fopn → flck → waku
    ./h econ   ↑に続けて econ
    ./h seid   ↑に続けて seid（set_hsr を含む）
    ./h krgn   ↑に続けて krgn
    ./h kiso   ↑に続けて、種別ループ（s = 1, 2, 3）で kiso を3回
    ./h dtst   ↑の種別ループで kiso → dtst を3回
    ./h shke   ↑の種別ループで kiso → dtst → shke を3回
    ./h siml2  ↑に続けて k = KIJUN+1, KIJUN+2 で siml → shke を2年ぶん
    ./h out    ↑に続けて outkn → rousaki → pstat → stat → crshfl → outhou
    ./h out:1  同じものを国家公務員共済（pseid = 1）で

段階名の末尾に `:1` `:4` `:5` を付けると制度（`pseid`）を変えられる。
既定は厚生年金（0）。`main.cpp` は 2 と 3 を飛ばす。

いま合わせている段階
--------------------
| 段階 | 原本 | 移植版 | 比べるもの |
|---|---|---|---|
| cntl | `cntl.cpp` | `cntl.py` | 設定値49個＋配列7本 |
| waku | `fileio.cpp` `flck.cpp` `waku.cpp` | 同名の .py | 配列7本＋`kiso`/`shus` の先頭 |
| econ | `econ.cpp` | `econ.py` | 配列15本＋スカラー3個＋`kaitea`/`kaiteb` |
| seid | `seid.cpp` | `seid.py` | 配列26本＋スカラー10個＋`sikr_out`/`hou_out` |
| krgn | `krgn.cpp` | `krgn.py` | 配列4本（繰上げ・繰下げの率） |
| kiso | `kiso.cpp` `sknr.cpp` | 同名の .py | 種別3通り × 配列11本＋`xxr`/`xrb`＋`kisor_out` |
| dtst | `dtst.cpp` `subrh.cpp` `subrj.cpp` | 同名の .py | 種別3通り × 配列25本（`f` 62万 要素 ×3 ほか） |
| shke | `shke.cpp` `shkehiho.cpp` `shkejken.cpp` `siku.cpp` `shkejsha.cpp` `shkejuk.cpp` `shkekiso.cpp` | 同名の .py | 種別3通り × 配列40本（`d3x` `d3xs` 各 8,451万 要素ほか） |
| siml2 | `siml.cpp` `simlg.cpp` `simlbzw.cpp` `dsitk.cpp` `simlsaite1.cpp` `simlsaite2.cpp` `simlrhnf.cpp` | 同名の .py | 種別3通り × 2年度 × 配列48本＋スカラー8個 |
| out | `outkn.cpp` `rousaki.cpp` `pstat.cpp` `stat.cpp` `crshfl.cpp` `outhou.cpp` | 同名の .py | 配列32本＋出力の木18ファイル丸ごと |
| out:1 | 同（`pseid = 1` 国家公務員共済） | 同 | 配列32本。**共済だけの枝**を通す |

原本は出力先を絶対パスで埋め込んでいるので、テストは
`fileio.cpp` のその1文字列だけを書き換えて建てる（`run_pipeline.sh` と
同じ規則）。移植版は環境変数 `SUURI_PREFIX` で差し替える。

前提
----
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本
- `work/suuri/rev2024/emp/data` と `wakuc/rslt/ver_4_1/rslt3001`
  （`run_pipeline.sh` を1回通せば揃う）

無ければスキップする。
"""
import os
import re
import shutil
import subprocess
import sys
import zlib

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
_BASE_DIR = os.path.join(SUURI).encode()

# main.cpp の4つ（key, 試算番号, 経済前提, 外枠）
STDIN_MAIN = "11\n3001\n3001\n3001\n"
# cntl.cpp の6つ（seimei, flg_part, flg_sigo, flg_kozax, houjou, flg_inout）
STDIN_CNTL = "4\n0\n0\n0\n0\n0\n"

# 出力用に作るディレクトリ（`fopn()` が開く先）
_OUT_DIRS = [
    "emp/rslt/u-rev/shus", "emp/rslt/u-rev/shusg", "emp/rslt/u-rev/kiso",
    "emp/rslt/u-rev/kisor", "emp/rslt/u-rev/hou", "emp/rslt/u-rev/kaite",
    "emp/rslt/u-rev/hikaku", "emp/rslt/u-rev/ashimoto",
    "emp/rslt/u-rev/bunpu", "emp/rslt/u-rev/prt",
]

STAGES = ("cntl", "waku", "econ", "seid", "krgn", "kiso", "dtst",
          "shke", "siml2", "out", "out:1")

# out 段階で突き合わせる配列（`stat()` `rousaki()` が書き換えるもの）
OUT_ARRAYS = ("d3", "d3x", "d3xs", "kfprx", "a", "aal", "aiku", "ap",
              "appart", "at", "a60", "a65", "a70", "a75", "a85",
              "ap65", "ap70", "ap75", "ap85", "appart65", "appart70",
              "appart75", "appart85", "apart", "aikupart", "a60part",
              "a65part", "a70part", "a75part", "a85part", "gee",
              "geept")

# kiso 段階で種別ごとに突き合わせる配列
KISO_ARRAYS = ("q", "u", "rt", "yx", "ns", "rc", "cl", "cl2",
               "kd", "ikucoe", "jiiku")

# dtst 段階で種別ごとに突き合わせる配列
DTST_ARRAYS = ("g", "ge", "gpt", "bb", "bbpt", "z", "ze", "w", "we",
               "psz", "psze", "gd", "r", "f", "f_min", "f_hik", "hn",
               "pshn", "rsen", "hnsen", "pshnsen", "fsen", "fsenmin",
               "fsenhik", "fkouzai2")

# shke 段階で種別ごとに突き合わせる配列
SHKE_ARRAYS = ("t4", "t4k", "t6", "t6k", "hn2", "hn2k", "gee", "geept",
               "ap", "apdum", "ap65", "ap70", "ap75", "ap85", "appart",
               "a", "adum", "aiku", "a60", "a65", "a70", "a75", "a85",
               "apart", "ax", "gx", "gtal", "getal", "g2", "bb2", "z2",
               "w2", "g3", "bb3", "okisor", "okiso2x", "dk3x", "d3",
               "d3x", "d3xs")

# siml2 段階で種別ごとに突き合わせる配列
SIML_ARRAYS = ("g", "ge", "gpt", "gz", "gn", "gez", "gnn", "ye", "y",
               "ypt", "q2", "bb", "bbnp", "bbpt", "z", "ze", "w", "we",
               "chwd", "gd", "r", "rn", "hn", "hnn", "f", "fn", "f_hik",
               "f_min", "fnhik", "fnmin", "pshn", "rsen", "fsen",
               "fsenhik", "fsenmin", "rsenn", "fsenn", "hnsen",
               "rhantei", "fhantei", "fpart", "t4", "t6", "d3", "d3x",
               "okisor", "l", "lpt")
SIML_INTS = ("it", "xr", "xxr", "xrb")
SIML_DBLS = ("tn", "ta", "srv", "pslr")

# seid 段階で突き合わせる配列とスカラー（ハーネスと同じ並び）
SEID_ARRAYS = ("pre", "pres", "flt", "adt", "sadt", "cadt", "wife", "can",
               "can2", "ha", "hb", "ema", "emb", "emc", "ee", "rs", "sik",
               "sikr", "nos", "routsu", "qp", "br", "bn", "bnpt", "dmpt2",
               "partbbn")
SEID_DBLS = ("pra", "prb", "pras", "prbs", "fl", "fl1", "minb", "wif",
             "senll", "srv")


def _stage_tree(root):
    """`<root>/suuri/rev2024` に出力先を作り、入力を symlink する。"""
    base = os.path.join(root, "suuri", "rev2024")
    for d in _OUT_DIRS:
        os.makedirs(os.path.join(base, d), exist_ok=True)
    os.makedirs(os.path.join(base, "emp"), exist_ok=True)
    os.symlink(os.path.join(SUURI, "emp", "data"),
               os.path.join(base, "emp", "data"))
    os.symlink(os.path.join(SUURI, "wakuc"), os.path.join(base, "wakuc"))
    return base


def _cc():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """原本をリンクしたハーネスを建て、段階ごとに走らせる。"""
    if not os.path.isdir(SRC):
        pytest.skip(f"UTF-8 に変換した原本が無い（{SRC}）")
    for p in (os.path.join(SUURI, "emp", "data", "u-rev", "econ",
                           "econ-3001.csv"),
              os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", "rslt3001",
                           "waku3001-20.csv")):
        if not os.path.exists(p):
            pytest.skip(f"②の入力が無い（{p}）")
    cc = _cc()
    if cc is None:
        pytest.skip("C++ コンパイラが無い")

    tmp = tmp_path_factory.mktemp("kyufu_stage")
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

    c_root = tmp / "c"
    py_root = tmp / "py"
    c_base = _stage_tree(str(c_root))
    _stage_tree(str(py_root))

    # `fileio.cpp` の base_dir だけを書き換える
    p = bsrc / "fileio.cpp"
    b = p.read_bytes()
    assert _BASE_DIR in b, (
        f"fileio.cpp に {_BASE_DIR!r} が無い。run_pipeline.sh が"
        "書き換えた木を使っているか確認すること")
    p.write_bytes(b.replace(_BASE_DIR, c_base.encode()))

    exe = str(bsrc / "h")
    srcs = sorted(f for f in os.listdir(bsrc) if f.endswith(".cpp"))
    r = subprocess.run([cc, "-O2", "-w", "-I", "ext", "-I", "common",
                        "-I", "lib", "-o", exe] + srcs,
                       cwd=str(bsrc), capture_output=True, text=True)
    assert r.returncode == 0, f"ハーネスのビルドに失敗:\n{r.stderr[:3000]}"

    # 移植版を別プロセスで走らせる（G が1組しか無いので）
    runner = tmp / "run_py.py"
    runner.write_text(_RUNNER % os.path.join(HERE, "emp_kyufu"),
                      encoding="utf-8")

    out = {}
    for stage in STAGES:
        r = subprocess.run([exe, stage], cwd=str(bsrc),
                           input=(STDIN_MAIN + STDIN_CNTL).encode(),
                           capture_output=True, timeout=3600)
        assert r.returncode == 0, (
            f"[{stage}] 原本が異常終了:\n"
            + r.stderr.decode("utf-8", "replace")[:3000])
        c_out = _parse(r.stdout.decode("utf-8"))

        env = dict(os.environ, SUURI_PREFIX=str(py_root))
        r = subprocess.run([sys.executable, str(runner), stage],
                           input=(STDIN_MAIN + STDIN_CNTL).encode(),
                           capture_output=True, timeout=3600, env=env)
        assert r.returncode == 0, (
            f"[{stage}] 移植版が異常終了:\n"
            + r.stderr.decode("utf-8", "replace")[:3000])
        py_out = _parse(r.stdout.decode("utf-8"))

        out[stage] = (c_out, py_out)

    return out, c_base, str(py_root / "suuri" / "rev2024")


# 移植版を段階ごとに走らせて、同じ書式で CRC32 を出す
_RUNNER = '''# -*- coding: utf-8 -*-
import contextlib, io, sys, zlib
sys.path.insert(0, %r)
from cinstream import Cin
from glva import G
import glva, cntl, fileio, flck, waku, econ, seid, krgn, kiso, dtst, shke, siml
import outkn, rousaki, pstat, crshfl, outhou
from setconst import KIJUN

# `stat` は Python 標準ライブラリにもあり、`os` が起動時に読み込むので
# `sys.modules` に先に入っている。素の `import stat` では標準の方を
# 取ってしまうので、ファイルを指して読み込む（原本の名前は変えない）
import importlib.util as _ilu
import os.path as _op
_spec = _ilu.spec_from_file_location(
    "emp_kyufu_stat", _op.join(sys.path[0], "stat.py"))
stat = _ilu.module_from_spec(_spec)
sys.modules["emp_kyufu_stat"] = stat
_spec.loader.exec_module(stat)

STAGE = sys.argv[1]
# 段階名の末尾の `:1` `:4` `:5` は制度（`pseid`）。既定は厚生年金 0
PSEID = 0
if ":" in STAGE:
    STAGE, _p = STAGE.split(":", 1)
    PSEID = int(_p)
text = sys.stdin.read()
cin = Cin(text)

CNTL_INTS = (
    "key", "iname", "iecon", "iwname", "seidver", "psly", "pslsi", "pslsi2",
    "seimei", "seiy", "kzn", "flg_part", "partyr1", "partyr2", "partyr3",
    "partyr4", "flg_sigo", "canyr", "flg_kozax", "kozaxyr", "kozax",
    "houjou", "houjouyr")
CNTL_DBLS = ("houjour1", "houjour2")
CNTL_INTS2 = (
    "flg_inout", "flg_hantei", "flg_okure", "flg_kurisage",
    "flg_tuuroutest", "flg_hsr", "hsr_endy")
CNTL_DBLS2 = ("hsr_r",)
CNTL_INTS3 = (
    "flg_siktuika", "flg_toukei", "flg_gtest", "flg_bzwtest", "chinsura",
    "kaite", "nenbeex", "xb", "xa", "cht_flg")
CNTL_DBLS3 = ("hikrate",)
CNTL_INTS4 = ("flg_hiho70", "hiho70yr", "flg_kaisho", "flg_sankyu",
              "nenbe65")


def rep(name):
    a = getattr(G, name)
    nz = a[a != 0]
    first = float(nz.flat[0]).hex() if nz.size else "-"
    print("## %%s %%d %%08x %%s" %% (name, a.size,
                                 zlib.crc32(a.tobytes()), first))


def rep_int(name):
    print("## %%s int %%d -" %% (name, getattr(G, name)))


def rep_int_p(pfx, name):
    print("## %%s%%s int %%d -" %% (pfx, name, getattr(G, name)))


def rep_dbl_p(pfx, name):
    print("## %%s%%s dbl %%s -" %% (pfx, name, float(getattr(G, name)).hex()))


def rep_p(pfx, name):
    a = getattr(G, name)
    nz = a[a != 0]
    first = float(nz.flat[0]).hex() if nz.size else "-"
    # `d3x` `d3xs` は 676MB あるので、tobytes() の複製を作らない
    print("## %%s%%s %%d %%08x %%s" %% (pfx, name, a.size,
                                    zlib.crc32(memoryview(a).cast("B")),
                                    first))


def rep_dbl(name):
    print("## %%s dbl %%s -" %% (name, float(getattr(G, name)).hex()))


with contextlib.redirect_stdout(io.StringIO()):
    G.key = cin.int_()
    G.iname = cin.int_()
    G.iecon = cin.int_()
    G.iwname = cin.int_()
    assert G.iwname >= 1000
    G.seidver = 1
    glva.zero_init()
    cntl.cntl(cin)

if STAGE == "cntl":
    for n in CNTL_INTS:
        rep_int(n)
    for n in CNTL_DBLS:
        rep_dbl(n)
    for n in CNTL_INTS2:
        rep_int(n)
    for n in CNTL_DBLS2:
        rep_dbl(n)
    for n in CNTL_INTS3:
        rep_int(n)
    for n in CNTL_DBLS3:
        rep_dbl(n)
    for n in CNTL_INTS4:
        rep_int(n)
    for n in ("kflcan", "partbbn", "partbbn2", "tz", "kfprx", "apdmy",
              "atdmy"):
        rep(n)
    sys.exit(0)

with contextlib.redirect_stdout(io.StringIO()):
    G.pseid = PSEID
    G.konen = 1 if PSEID == 0 else 0
    glva.zero_sepsd()
    fileio.fopn()
    flck.flck()

if STAGE == "waku":
    with contextlib.redirect_stdout(io.StringIO()):
        waku.waku()
    for n in ("pop", "l", "lpt", "lpt1", "lpt2", "lpt3", "lpt4"):
        rep(n)
    rep_int("s")
    rep_int("k")
    fileio.fcls()
    sys.exit(0)

with contextlib.redirect_stdout(io.StringIO()):
    waku.waku()
    econ.econ()

if STAGE == "econ":
    for n in ("ri", "h", "ci0", "dir", "jz_shk", "hh", "ci", "hdum",
              "ci2", "hp2", "ad", "ad2", "bd", "chwd", "qp"):
        rep(n)
    for n in ("hh2_1999", "hh2_2000", "hh2_2001"):
        rep_dbl(n)
    fileio.fcls()
    sys.exit(0)

with contextlib.redirect_stdout(io.StringIO()):
    seid.seid()

if STAGE == "seid":
    for n in ("pre", "pres", "flt", "adt", "sadt", "cadt", "wife", "can",
              "can2", "ha", "hb", "ema", "emb", "emc", "ee", "rs", "sik",
              "sikr", "nos", "routsu", "qp", "br", "bn", "bnpt", "dmpt2",
              "partbbn"):
        rep(n)
    for n in ("pra", "prb", "pras", "prbs", "fl", "fl1", "minb", "wif",
              "senll", "srv"):
        rep_dbl(n)
    fileio.fcls()
    sys.exit(0)

with contextlib.redirect_stdout(io.StringIO()):
    krgn.krgn()

if STAGE == "krgn":
    for n in ("riss", "rigd", "rigk", "rigbe"):
        rep(n)
    fileio.fcls()
    sys.exit(0)

if STAGE == "out":
    # `sepsd.cpp` の尾。siml は2年だけ回す（ハーネスと同じ）
    with contextlib.redirect_stdout(io.StringIO()):
        for s in range(1, 4):
            if G.pseid != 0 and s >= 3:
                break
            G.s = s
            G.s2 = s
            kiso.kiso()
            G.k = KIJUN
            G.xend = 90 if G.pseid == 0 else 75
            G.tend = G.xend - 15
            dtst.dtst()
            shke.shke()
            for kk in range(KIJUN + 1, KIJUN + 2 + 1):
                G.k = kk
                siml.siml()
                shke.shke()
        if G.key in (11, 12, 13):
            outkn.outkn()
        if G.flg_toukei == 0:
            rousaki.rousaki()
        if G.key in (11, 13):
            pstat.pstat()
        stat.stat()
        crshfl.crshfl()
        if G.key == 11:
            outhou.outhou()
    for n in ("d3", "d3x", "d3xs", "kfprx", "a", "aal", "aiku", "ap",
              "appart", "at", "a60", "a65", "a70", "a75", "a85",
              "ap65", "ap70", "ap75", "ap85", "appart65", "appart70",
              "appart75", "appart85", "apart", "aikupart", "a60part",
              "a65part", "a70part", "a75part", "a85part", "gee",
              "geept"):
        rep_p("", n)
    fileio.fcls()
    sys.exit(0)

if STAGE in ("kiso", "dtst", "shke", "siml2"):
    # `sepsd.cpp` の種別ループと同じ形。`kisor` `hk` `jk` は
    # 1回の呼び出しで1節ずつ進むので、s = 1, 2, 3 と3回呼ぶ
    for s in range(1, 4):
        if G.pseid != 0 and s >= 3:
            break
        G.s = s
        G.s2 = s
        with contextlib.redirect_stdout(io.StringIO()):
            kiso.kiso()
            if STAGE in ("dtst", "shke", "siml2"):
                G.k = KIJUN
                G.xend = 90 if G.pseid == 0 else 75
                G.tend = G.xend - 15
                dtst.dtst()
            if STAGE in ("shke", "siml2"):
                shke.shke()
            if STAGE == "siml2":
                for kk in range(KIJUN + 1, KIJUN + 2 + 1):
                    G.k = kk
                    siml.siml()
                    shke.shke()
        p = "s%%d_" %% s
        if STAGE == "kiso":
            names = ("q", "u", "rt", "yx", "ns", "rc", "cl", "cl2", "kd",
                     "ikucoe", "jiiku")
        elif STAGE == "dtst":
            names = ("g", "ge", "gpt", "bb", "bbpt", "z", "ze", "w", "we",
                     "psz", "psze", "gd", "r", "f", "f_min", "f_hik", "hn",
                     "pshn", "rsen", "hnsen", "pshnsen", "fsen", "fsenmin",
                     "fsenhik", "fkouzai2")
        elif STAGE == "shke":
            names = ("t4", "t4k", "t6", "t6k", "hn2", "hn2k", "gee",
                     "geept", "ap", "apdum", "ap65", "ap70", "ap75",
                     "ap85", "appart", "a", "adum", "aiku", "a60", "a65",
                     "a70", "a75", "a85", "apart", "ax", "gx", "gtal",
                     "getal", "g2", "bb2", "z2", "w2", "g3", "bb3",
                     "okisor", "okiso2x", "dk3x", "d3", "d3x", "d3xs")
        else:
            names = ("g", "ge", "gpt", "gz", "gn", "gez", "gnn", "ye",
                     "y", "ypt", "q2", "bb", "bbnp", "bbpt", "z", "ze",
                     "w", "we", "chwd", "gd", "r", "rn", "hn", "hnn",
                     "f", "fn", "f_hik", "f_min", "fnhik", "fnmin",
                     "pshn", "rsen", "fsen", "fsenhik", "fsenmin",
                     "rsenn", "fsenn", "hnsen", "rhantei", "fhantei",
                     "fpart", "t4", "t6", "d3", "d3x", "okisor", "l",
                     "lpt")
        for n in names:
            rep_p(p, n)
        if STAGE == "siml2":
            for n in ("it", "xr", "xxr", "xrb"):
                rep_int_p(p, n)
            for n in ("tn", "ta", "srv", "pslr"):
                rep_dbl_p(p, n)
        else:
            rep_int_p(p, "xxr")
            rep_int_p(p, "xrb")
    fileio.fcls()
    sys.exit(0)

sys.exit("unknown stage " + STAGE)
'''


def _parse(text):
    """ハーネスの出力を `{名前: 行の残り}` にする。

    原本は `cout` で入力の案内も出すので、**`## ` で始まる行だけ**を取る。
    """
    out = {}
    for line in text.splitlines():
        if not line.startswith("## "):
            continue
        parts = line[3:].split(None, 1)
        if len(parts) != 2:
            continue
        name, rest = parts
        assert name not in out, f"同じ名前が2回出ている: {name}"
        out[name] = rest
    return out


def _cmp(c_out, py_out, stage):
    """同じ名前の行を突き合わせる。**%a の1ビットまで**。"""
    bad = []
    assert c_out, f"[{stage}] 原本の出力が空"
    for name, c_rest in c_out.items():
        if name not in py_out:
            bad.append(f"{name}: 移植版に無い（C = {c_rest}）")
            continue
        p_rest = py_out[name]
        cf = c_rest.split()
        pf = p_rest.split()
        if cf[0] == "int" or cf[0] == "dbl":
            # int はそのまま、dbl は %a を float にして比べる
            if cf[0] == "int":
                same = cf[1] == pf[1]
            else:
                same = float.fromhex(cf[1]) == float.fromhex(pf[1])
            if not same:
                bad.append(f"{name}: C = {c_rest} / Python = {p_rest}")
            continue
        # 配列。要素数と CRC32、先頭の非ゼロ要素
        if cf[0] != pf[0]:
            bad.append(f"{name}: 要素数が違う C = {cf[0]} / Python = {pf[0]}")
            continue
        if cf[1].lower() != pf[1].lower():
            extra = ""
            if len(cf) > 2 and len(pf) > 2 and cf[2] != "-" and pf[2] != "-":
                extra = (f"（先頭の非ゼロ C = {cf[2]} / Python = {pf[2]}）")
            bad.append(f"{name}: CRC32 が違う C = {cf[1]} / "
                       f"Python = {pf[1]}{extra}")
    return bad


def test_cntlの設定値と配列が原本と一致(probe):
    out, _, _ = probe
    c_out, py_out = out["cntl"]
    bad = _cmp(c_out, py_out, "cntl")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    # 空振りしていないことの確かめ
    assert "kflcan" in c_out and "seimei" in c_out


def test_wakuの外枠が原本と一致(probe):
    out, _, _ = probe
    c_out, py_out = out["waku"]
    bad = _cmp(c_out, py_out, "waku")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    assert "pop" in c_out and "l" in c_out


def test_econの経済前提と改定率が原本と一致(probe):
    out, _, _ = probe
    c_out, py_out = out["econ"]
    bad = _cmp(c_out, py_out, "econ")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    # 空振りしていないことの確かめ
    for n in ("ri", "h", "ci0", "ci2", "hp2", "bd", "jz_shk"):
        assert n in c_out, f"{n} がハーネスの出力に無い"


def test_econのkaiteファイルが一致(probe):
    """`econ()` が書く `kaitea` `kaiteb`（③国民年金が読む改定率）。

    `kaiteb` に `arv_hh`、`kaitea` に `arv_hp` が入る（名前と中身が
    入れ替わって見える。`検証/原本の不具合.md`）。
    """
    _, c_base, py_base = probe
    bad = []
    for rel in ("emp/rslt/u-rev/kaite/kaitea-3001-3001e",
                "emp/rslt/u-rev/kaite/kaiteb-3001-3001e"):
        cb = open(os.path.join(c_base, rel), encoding="utf-8").read()
        pb = open(os.path.join(py_base, rel), encoding="utf-8").read()
        if cb == pb:
            continue
        cl, pl = cb.splitlines(), pb.splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                bad.append(f"{rel} の {i}行目\n    C      {x[:200]}\n"
                           f"    Python {y[:200]}")
                break
        else:
            bad.append(f"{rel} の行数が違う "
                       f"（C {len(cl)} / Python {len(pl)}）")
    assert not bad, "原本と一致しない:\n" + "\n".join(bad)
    # 空振りしていないことの確かめ（121行 × 50列）
    n = len(open(os.path.join(c_base,
                              "emp/rslt/u-rev/kaite/kaitea-3001-3001e"),
                 encoding="utf-8").read().splitlines())
    assert n == 121, f"kaitea が {n} 行（期待 121）"


def test_seidの制度定数と支給率が原本と一致(probe):
    out, _, _ = probe
    c_out, py_out = out["seid"]
    bad = _cmp(c_out, py_out, "seid")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    # 空振りしていないことの確かめ
    for n in SEID_ARRAYS + SEID_DBLS:
        assert n in c_out, f"{n} がハーネスの出力に無い"


def test_seidのfltに原本の写し間違いがそのまま残っている():
    """J1。1936年度生まれの定額部分の読替率が `0.369`（公表値は 1.369）。

    移植版が「直してしまっていない」ことを固定する。`flt` の CRC32 が
    一致していること（上のテスト）に加えて、**その1点だけが公表値と
    違う**ことを確かめる。
    """
    # `seid.py` を import すると glva が 2.5GB 確保するので、
    # ソースから2つの表だけを取り出す
    src = open(os.path.join(HERE, "emp_kyufu", "seid.py"),
               encoding="utf-8").read()
    tables = {}
    for name in ("_TMQ", "_TMQ_HOUTEI"):
        m = re.search(r"^%s = \((.*?)\)$" % name, src, re.M | re.S)
        assert m, f"{name} が seid.py に無い"
        tables[name] = [int(x) for x in m.group(1).replace("\n", "").split(",")
                        if x.strip()]

    genpon, houtei = tables["_TMQ"], tables["_TMQ_HOUTEI"]
    assert len(genpon) == 20 and len(houtei) == 20
    chigau = [i for i in range(20) if genpon[i] != houtei[i]]
    assert chigau == [10], f"食い違う位置が {chigau}"
    assert genpon[10] == 369 and houtei[10] == 1369
    # 添字 10 は kx = -74 + 10 = -64、つまり1936年度（昭和11年度）生まれ
    assert -74 + 10 == -64


def test_seidが書くsikr_outとhou_outが一致(probe):
    """`seid()` が書く2ファイル（支給率と報酬設定の出力）。"""
    _, c_base, py_base = probe
    bad = []
    for rel in ("emp/rslt/u-rev/kisor/sikr.3001-3001-3001_kou.csv",
                "emp/rslt/u-rev/hou/hou.3001-3001-3001_kou.csv"):
        cp = os.path.join(c_base, rel)
        pp = os.path.join(py_base, rel)
        if not os.path.exists(cp):
            pytest.skip(f"原本が {rel} を書いていない")
        cb = open(cp, encoding="utf-8").read()
        pb = open(pp, encoding="utf-8").read()
        if cb == pb:
            continue
        cl, pl = cb.splitlines(), pb.splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            if x != y:
                bad.append(f"{rel} の {i}行目\n    C      {x[:200]}\n"
                           f"    Python {y[:200]}")
                break
        else:
            bad.append(f"{rel} の行数が違う "
                       f"（C {len(cl)} / Python {len(pl)}）")
    assert not bad, "原本と一致しない:\n" + "\n".join(bad)


def test_krgnの繰上げ繰下げの率が原本と一致(probe):
    out, _, _ = probe
    c_out, py_out = out["krgn"]
    bad = _cmp(c_out, py_out, "krgn")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in ("riss", "rigd", "rigk", "rigbe"):
        assert n in c_out, f"{n} がハーネスの出力に無い"


def test_kisoの基礎率が原本と一致(probe):
    """種別 s = 1, 2, 3 それぞれで `kiso()` を呼んだあとの配列11本。

    `kisor` ファイルは1回の呼び出しで1節ずつ進むので、原本も移植版も
    `sepsd.cpp` と同じ形で3回呼ぶ。
    """
    out, _, _ = probe
    c_out, py_out = out["kiso"]
    bad = _cmp(c_out, py_out, "kiso")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for s in (1, 2, 3):
        for n in KISO_ARRAYS + ("xxr", "xrb"):
            assert f"s{s}_{n}" in c_out, f"s{s}_{n} がハーネスの出力に無い"


def test_dtstの足元の基礎数が原本と一致(probe):
    """種別 s = 1, 2, 3 それぞれで `kiso()` → `dtst()` を呼んだあとの配列25本。

    `hk2021-{s}.csv`（被保険者）と `jk2021-{s}.csv`（受給権者）を読んで、
    繰上げ減額・加給・有子割合で割り戻し、補正率を掛けたところまで。
    """
    out, _, _ = probe
    c_out, py_out = out["dtst"]
    bad = _cmp(c_out, py_out, "dtst")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for s in (1, 2, 3):
        for n in DTST_ARRAYS:
            assert f"s{s}_{n}" in c_out, f"s{s}_{n} がハーネスの出力に無い"


def test_shkeの年度集計が原本と一致(probe):
    """種別 s = 1, 2, 3 それぞれで `shke()` を1年度（k = KIJUN）走らせた
    あとの配列40本。

    `shke()` は `shkejken` `shkejsha` `shkejuk` を (i, x, xx) の
    8,395 通りで呼ぶので、1年度でも 25,185 回ずつ走る。
    `d3x` `d3xs` は 8,451万 要素（676MB）。
    """
    out, _, _ = probe
    c_out, py_out = out["shke"]
    bad = _cmp(c_out, py_out, "shke")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for s in (1, 2, 3):
        for n in SHKE_ARRAYS:
            assert f"s{s}_{n}" in c_out, f"s{s}_{n} がハーネスの出力に無い"


def test_simlの2年ぶんの推計が原本と一致(probe):
    """種別 s = 1, 2, 3 それぞれで k = KIJUN+1, KIJUN+2 の2年度ぶん
    `siml()` → `shke()` を回したあとの配列48本とスカラー8個。

    `siml()` は `simlg` `simlbzw` `dsitk` `simlsaite1/2` `simlrhnf` を
    年齢 × 経過年で呼ぶ。2年ぶん回すことで、`f[x] = f[x-1] * … + fn[x]`
    のような年度をまたぐ漸化式も突き合わせられる。
    """
    out, _, _ = probe
    c_out, py_out = out["siml2"]
    bad = _cmp(c_out, py_out, "siml2")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for s in (1, 2, 3):
        for n in SIML_ARRAYS + SIML_INTS + SIML_DBLS:
            assert f"s{s}_{n}" in c_out, f"s{s}_{n} がハーネスの出力に無い"


def test_outの集計と出力が原本と一致(probe):
    """`sepsd.cpp` の尾（`outkn` → `rousaki` → `pstat` → `stat` →
    `crshfl` → `outhou`）を通したあとの配列32本。

    `stat()` は年度末の値を年度間の平均に直し、性別（`s = 0`）と
    給付の種類（`i = 0`）の「計」を作る。`d3x` `d3xs` は 8,451万 要素
    ずつあり、`kfprx`（基礎年金拠出金の算定対象）もここで埋まる。
    `rousaki()` は 80〜114歳の遺族厚生年金を老齢へ振り替える。
    """
    out, _, _ = probe
    c_out, py_out = out["out"]
    bad = _cmp(c_out, py_out, "out")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in OUT_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ（`kfprx` は cntl の段階では全部 0）
    assert c_out["kfprx"].split()[2] != "-", "kfprx が全部 0 のまま"


# H3（`pstat.cpp` の `csv::join(…).c_str()` が解放済みの領域を指す）で
# 原本の側が化けるので、バイト一致しない3本。`test_pstatの3本だけが
# B9で化けている` が「どう違うか」を固定する
B9_FILES = (
    "emp/rslt/u-rev/hikaku/hikaku.3001-3001-3001",
    "emp/rslt/u-rev/ashimoto/ashimotosum.3001-3001-3001",
    "emp/rslt/u-rev/ashimoto/ashimotossum.3001-3001-3001",
)


def test_出力の木が丸ごとバイト一致(probe):
    """`c_base` と `py_base` の下のファイルを**全部**突き合わせる。

    段階ごとに C 版と移植版を同じ順で走らせているので、最後には
    両方の木に同じ顔ぶれのファイルが同じ中身で並んでいるはず。
    `crshfl()` `pstat()` `outkn()` `outhou()` が書くものも含む。

    `flck()` が書く来歴（`kiso.*` `shus.*`）だけは自分の絶対パスを
    書くので、出力先の違いを読み替えてから比べる。

    `pstat()` が書く3本（`B9_FILES`）は**原本の側が化ける**ので
    ここでは外す。H3 を参照。
    """
    _, c_base, py_base = probe

    def tree(base):
        got = {}
        for root, _dirs, files in os.walk(base):
            for f in files:
                p = os.path.join(root, f)
                got[os.path.relpath(p, base)] = p
        return got

    ct, pt = tree(c_base), tree(py_base)
    assert ct, "原本が1つもファイルを書いていない"
    only_c = sorted(set(ct) - set(pt))
    only_p = sorted(set(pt) - set(ct))
    bad = []
    if only_c:
        bad.append("移植版が書いていない: " + ", ".join(only_c[:20]))
    if only_p:
        bad.append("原本が書いていない: " + ", ".join(only_p[:20]))
    for rel in sorted(set(ct) & set(pt)):
        if rel.replace(os.sep, "/") in B9_FILES:
            continue
        cb = open(ct[rel], "rb").read()
        pb = open(pt[rel], "rb").read()
        if cb == pb:
            continue
        # 来歴は自分の絶対パスを書くので読み替える
        cs = cb.decode("utf-8", "replace").replace(c_base, "PFX")
        ps = pb.decode("utf-8", "replace").replace(py_base, "PFX")
        if cs == ps:
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


def test_共済の経路も原本と一致(probe):
    """`pseid = 1`（国家公務員共済）で `out` 段階を通したもの。

    厚生年金（`pseid = 0`）しか通していないと、**共済だけの枝**が
    一度も走らない。②には `pseid` で分かれるところが多い。

    - `simlg` の残存率が `exp(-u)`（厚年は `1 - u`）— E29
    - `xend` が 75（厚年は 90）、年齢の上限が 70（厚年は 85）
    - `stat()` の年度間の平均が **5 : 7**（厚年は 6 : 6）
    - 第3号被保険者（`s = 3`）が無いので `s` のループを2回で抜ける
    - パート（`gpt` `bbpt` `apart` …）の枝を通らない
    - `shkejuk` の `ab` に掛ける係数が制度ごとに違う（J2）

    `main.cpp` は `pseid` を 0・1・4・5 で回す（2 と 3 は飛ばす）。
    ここでは 1 を見る。
    """
    out, _, _ = probe
    c_out, py_out = out["out:1"]
    bad = _cmp(c_out, py_out, "out:1")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in OUT_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 厚年と同じ値になっていないこと（段階を取り違えていない確かめ）。
    # **中身のある配列はすべて厚年と違う値**になる。一致する15本は
    # どちらの制度でも全要素 0（`at` `a70` `a75` `a85` `*part` など。
    # E27 で 70歳以上の標準報酬総額が 0 のままになるものを含む）
    c_kou, _ = out["out"]
    onaji = [n for n in OUT_ARRAYS if c_out[n] == c_kou[n]]
    for n in onaji:
        f = c_out[n].split()
        assert f[-1] == "-", (
            f"{n} が厚年と同じ値なのに全要素 0 ではない（{c_out[n]}）。"
            "`pseid` が効いていない疑い")
    chigau = [n for n in OUT_ARRAYS if n not in onaji]
    assert len(chigau) == 17, (
        f"共済と厚年で違う配列が {len(chigau)} 本（期待 17）")


def test_pstatの3本だけがB9で化けている(probe):
    """H3。`pstat.cpp:11-35` の `csv::join(…).c_str()` は**解放済みの
    領域**を指すので、原本が書く数値の欄が数バイトのごみに化ける。

    移植版は正しい文字列を渡すので、この3本は**バイト一致しない**。
    ここでは「どう違うか」を固定する。

    - 行数は同じ
    - 見出し・単位・添字の欄は一致する（化けるのは数値の欄だけ）
    - 原本の側は**数値として読めない**

    原本は `papers/` の下で1バイトも変えないので、「直した原本」と
    比べることはしない。化ける位置が決まっていることだけを示す。
    """
    _, c_base, py_base = probe
    for rel in B9_FILES:
        cl = open(os.path.join(c_base, rel), "rb").read().split(b"\n")
        pl = open(os.path.join(py_base, rel), "rb").read().split(b"\n")
        assert len(cl) == len(pl), (
            f"{rel} の行数が違う（C {len(cl)} / Python {len(pl)}）。"
            "B9 は数値の欄だけを壊すので行数は変わらないはず")
        kowareta = 0
        for i, (a, b) in enumerate(zip(cl, pl), 1):
            if a == b:
                continue
            kowareta += 1
            # 食い違う区間を切り出す（前後の共通部分を外す）
            h = 0
            while h < min(len(a), len(b)) and a[h] == b[h]:
                h += 1
            t = 0
            while (t < min(len(a), len(b)) - h
                   and a[len(a) - 1 - t] == b[len(b) - 1 - t]):
                t += 1
            gomi = a[h:len(a) - t]
            hontai = b[h:len(b) - t]
            # 移植版の側は `%16.8lf` か `%16.10lf` の並び
            tama = [x.strip() for x in hontai.split(b",")]
            assert tama and all(x for x in tama), (
                f"{rel}:{i} 移植版の側が数値の欄になっていない: "
                f"{hontai[:120]!r}")
            for x in tama:
                float(x)        # 読めなければここで落ちる
            # 原本の側は数値として読めない
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


def test_kisoが書くkisor_outがバイト一致(probe):
    """`kiso()` が3回で書く `kisor.*.csv`（31.6MB・28.5万行）。"""
    _, c_base, py_base = probe
    rel = "emp/rslt/u-rev/kisor/kisor.3001-3001-3001_kou.csv"
    cb = open(os.path.join(c_base, rel), encoding="utf-8").read()
    pb = open(os.path.join(py_base, rel), encoding="utf-8").read()
    if cb != pb:
        cl, pl = cb.splitlines(), pb.splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            assert x == y, (f"{rel} の {i}行目\n    C      {x[:200]}\n"
                            f"    Python {y[:200]}")
        raise AssertionError(f"{rel} の行数が違う "
                             f"（C {len(cl)} / Python {len(pl)}）")
    # 空振りしていないことの確かめ
    n = len(cb.splitlines())
    assert n == 285306, f"kisor_out が {n} 行（期待 285306）"


def test_krgnが書くPRTFILがバイト一致(probe):
    """`econ()` と `krgn()` が書く `PRTFIL_1_0`。

    `krgn.cpp:122-138` は `fprintf` に `\n` を付けていないので、
    `rigd` と `rigk` のぶんは全部が1行につながる（F13）。
    移植版もそのバイト列を書くことを確かめる。
    """
    _, c_base, py_base = probe
    rel = "emp/rslt/u-rev/PRTFIL_1_0"
    cb = open(os.path.join(c_base, rel), encoding="utf-8").read()
    pb = open(os.path.join(py_base, rel), encoding="utf-8").read()
    if cb != pb:
        cl, pl = cb.splitlines(), pb.splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            assert x == y, (f"{rel} の {i}行目\n    C      {x[:300]}\n"
                            f"    Python {y[:300]}")
        raise AssertionError(f"{rel} の行数が違う "
                             f"（C {len(cl)} / Python {len(pl)}）")
    # 空振りしていないことの確かめ。改行の無い行がつながって長くなる
    lines = cb.splitlines()
    assert lines[0] == "経済的要素"
    nagai = [x for x in lines if x.startswith("rigd,")]
    # `\n` がどこにも無いので、s = 1,2 × j = 0,1 の4ブロックと rigk の
    # ぶんが**まとめて1行**になり、次の見出しまで飲み込む
    assert len(nagai) == 1, f"rigd で始まる行が {len(nagai)} 本（期待 1）"
    assert len(nagai[0]) > 4000, (
        f"rigd の行が {len(nagai[0])} 文字しかない。改行が入ってしまって"
        "いる（F13 を再現できていない）")
    assert nagai[0].endswith("繰り上げ減額率"), (
        "次の見出しを飲み込んでいない（F13 を再現できていない）")


def test_flckが書く来歴が一致(probe):
    """`kiso.*` と `shus.*` の先頭（読んだファイルの一覧と設定値19行）。

    原本は自分の絶対パスを書くので、出力先の違いだけ読み替えて比べる。
    """
    _, c_base, py_base = probe
    bad = []
    for rel in ("emp/rslt/u-rev/kiso/kiso.3001-3001-3001_kou",
                "emp/rslt/u-rev/shus/shus.3001-3001-3001_kou"):
        cb = open(os.path.join(c_base, rel), encoding="utf-8").read()
        pb = open(os.path.join(py_base, rel), encoding="utf-8").read()
        cb = cb.replace(c_base, "PFX")
        pb = pb.replace(py_base, "PFX")
        if cb != pb:
            cl, pl = cb.splitlines(), pb.splitlines()
            for i, (x, y) in enumerate(zip(cl, pl), 1):
                if x != y:
                    bad.append(f"{rel} の {i}行目\n    C      {x}\n"
                               f"    Python {y}")
                    break
            else:
                bad.append(f"{rel} の行数が違う "
                           f"（C {len(cl)} / Python {len(pl)}）")
    assert not bad, "原本と一致しない:\n" + "\n".join(bad)


def test_CRC32の並びが行優先であること():
    """ハーネスの CRC32 と NumPy の `tobytes()` が同じ並びになるか。

    ハーネスは `std::vector` の入れ子を行優先でたどって 8 バイトずつ
    食わせる。NumPy の C 順の `tobytes()` と同じであることを、
    小さな配列で確かめる（上の突き合わせの前提）。
    """
    import numpy as np
    a = np.arange(24, dtype=np.float64).reshape(2, 3, 4)
    # 行優先に自分でたどったもの
    h = zlib.crc32(b"")
    for i in range(2):
        for j in range(3):
            for m in range(4):
                h = zlib.crc32(np.float64(a[i][j][m]).tobytes(), h)
    assert h == zlib.crc32(a.tobytes())
