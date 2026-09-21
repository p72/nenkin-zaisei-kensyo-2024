# -*- coding: utf-8 -*-
"""
③国民年金の移植を段階ごとに原本と突き合わせる
================================================
③は 16本の .c（10,528行）と 8本の .h（539行）。②と同じやり方で、
**計算の段階ごとにグローバル変数を CRC32 で比べる**。

丸ごと通した照合は `test_nat_full.py`（`-m slow`）が受け持つ。
こちらは `siml` を3年（45年化は15年）しか回さないかわりに、
**段階ごとに配列を突き合わせる**ので、どこで食い違ったかが分かる。

`harness_nat.cpp` が原本の .c を**無修正でリンク**して `main.c` の
代わりに走り、指定した段階までのグローバルを出す。

    ./h cntl  <argv1..15>   引数15個を読んだところまで
    ./h seid  ↑に続けて seid（制度の定数）
    ./h econ  ↑に続けて file_open → seid → econ（改定率と年金額）
    ./h kaizen ↑に続けて waku（外枠）→ kaizen（生命表と有配偶率）
    ./h noufuritu ↑に続けて noufuritu（納付率と免除の対象割合）
    ./h dtst   ↑に続けて、種別 2・3・5・6 で dtst（足元の基礎数）
    ./h kiso   ↑に続けて、種別 2・3・5・6 で dtst → kiso（基礎率）
    ./h shke   ↑に続けて shke（足元の1年度ぶんの集計。siml は呼ばない）
    ./h siml   ↑に続けて siml→shke を SIML_YEARS 年ぶん回す（既定3年）
    ./h stat   ↑に続けて stat（集計と KISONENKIN・DOKUZI の書き出し）
    ./h printout ↑に続けて printout（年度間への直しと参考出力5本）
    ./h strop `str_op.c` の8つの型 × 最大8つの演算を決めた入力で通す

③の特徴 — `struct` を値で受け渡す
---------------------------------
`scalar` `add` `multiply` `nendokan` `nendokan_64` `adjustbenefit`
`average_by_ninzu` `scalar_2` が**型ごとに多重定義**されている。
移植版は NumPy の構造化 dtype に写して `dtype` で振り分ける。

**`sizeof(struct)` が「欄数 × 8」であること**（詰め物が入って
いないこと）をハーネスで確かめてから比べる。これが成り立つので、
C の構造体のバイト列と NumPy の構造化 dtype の並びが一致し、
CRC32 で突き合わせられる。

`strop` 段階の入力
------------------
欄を順に `0.125 * (i + 1)` の倍数（1倍・3倍・7倍）で埋める。
**0.125 は2の冪**なので入力の丸めが入らず、演算の食い違いだけが
出る。改定率は `1.008` と `0.997`（2進で切れない値）にして、
掛ける順や括り方の違いが最後の桁に出るようにしている。

出力先は必ず書き替える
----------------------
③のファイルリスト（`nat/io_file/{in,out}file.csv`）は**絶対パスを
直に持っている**。そのまま走らせると

    nat/rslt/HIHO*.csv  ROREI*.csv  SHOGAI*.csv  IZOKU*.csv
    nat/data/KISONENKIN*  DOKUZI*.csv  nat_wariai*.csv
            KOKUKAITE-*.csv  PENSION_*.csv

を `"w"` で開くので、**`work/` の本物の出力を消してしまう**
（実際に1回やった。`KISONENKIN` は④基礎年金の入力なので
`run_pipeline.sh` の `STEPS=3` で作り直した）。

このテストはリストの控えを作って、**`nat/rslt` と `nat/data` を
指す行だけ**一時ディレクトリに書き替えてから渡す。入力は
`nat/base_data` `wakuc` `emp/data` の3か所だけなので、この2つを
替えれば出力は全部逃がせる（`_stage_lists`）。

前提
----
- `BUILD_DIR`（既定 `/tmp/nenkin-build`）に UTF-8 へ変換した原本
  （`run_pipeline.sh` が同じ既定値で作る）
- `econ` 段階は `work/suuri/rev2024/nat/io_file/` のリストと
  `emp/data/u-rev/econ/econ-3001.csv` が要る（`run_pipeline.sh` を
  1回通せば揃う）

無ければスキップする。`cntl` `seid` `strop` は入力ファイルを
読まないので `work/` は要らない。
"""
import os
import shutil
import subprocess
import tempfile
import sys
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402

SYSTEMS = ("clib", "nat")
select(*SYSTEMS)

BUILD = os.environ.get("BUILD_DIR", "/tmp/nenkin-build")
SRC = os.path.join(BUILD, "国民年金")

REPO = os.path.dirname(os.path.dirname(HERE))
SUURI = os.path.join(REPO, "work", "suuri", "rev2024")
NAT = os.path.join(SUURI, "nat")

# `run_pipeline.sh 3001` が③に渡すもの（`main.c` の argv[1..15]）
#   infile outfile 国年 経済前提 外枠 出生率 死亡率 過去債務 賃金スライド
#   適用拡大 適用拡大年度 オプション オプション開始年度 引上げ間隔 従来外枠
ARGV = ["in.csv", "out.csv", "3001", "3001", "3001", "0", "M", "0", "1",
        "0", "2027", "0", "2031", "3", "3001"]
# 45年化オプションを入れたもの（`seid` と `stdfm` の `encho_*` が動く）
ARGV_OP = ARGV[:11] + ["1"] + ARGV[12:]

STAGES = ("cntl", "seid", "strop", "econ", "kaizen", "noufuritu", "dtst",
          "kiso", "shke", "siml", "stat", "printout")

# dtst 段階で種別ごとに突き合わせる配列（`*_Nendomatu` の足元の年度）
DTST_ARRAYS = ("Hihokensha", "Taikisha", "Rorei_Nendomatu",
               "Rorei_Ichibu_Nendomatu", "Rorei_Kyu_Nendomatu",
               "Turo_Kyu_Nendomatu", "Gonen_Nendomatu",
               "Shogai_Ippan_Nendomatu", "Shogai_20mae_Nendomatu",
               "Shogai_Kyu_Nendomatu", "Izoku_Tuma_Nendomatu",
               "Izoku_Otto_Nendomatu", "Izoku_Ko_Nendomatu",
               "Kafu_Nendomatu", "Kafu_Kyu_Nendomatu",
               "Ichijikin_Nendomatu")
# kiso 段階で種別ごとに突き合わせる配列（`mkisoritu.h` と
# `mkisosu.h` の基礎率ぜんぶ。ハーネスの `K(…)` と同じ並び）
KISO_ARRAYS = (
    "Dattairyoku_Gokei", "Dattairyoku_Shibou", "Saikanyuritu",
    "Hassei_Wariai_Rorei", "Hasseiryoku_Shogai", "Hassei_Wariai_20mae",
    "Hassei_Wariai_Tuma", "Hassei_Wariai_Otto", "Hassei_Wariai_Ko",
    "Hassei_Wariai_Kafu", "Hassei_Wariai_Shibou",
    "Tokyu_Wariai_Ippan", "Tokyu_Wariai_20mae",
    "Kakyu_Wariai_Ippan_12shi", "Kakyu_Wariai_Ippan_3shiiko",
    "Kakyu_Wariai_20mae_12shi", "Kakyu_Wariai_20mae_3shiiko",
    "Kakyu_Wariai_Tuma_12shi", "Kakyu_Wariai_Tuma_3shiiko",
    "Kakyu_Wariai_Otto_12shi", "Kakyu_Wariai_Otto_3shiiko",
    "Kakyu_Wariai_Ko_12shi", "Kakyu_Wariai_Ko_3shiiko",
    "Sokan_Tuma", "Sokan_Otto", "Sokan_Ko", "Sokan_Kafu",
    "Shikkenritu_Rorei", "Shikkenritu_Ippan", "Shikkenritu_20mae",
    "Shikkenritu_Tuma", "Shikkenritu_Otto", "Shikkenritu_Ko",
    "Shikkenritu_Kafu",
    "Shikyuritu_Rorei", "Shikyuritu_Rorei_Kyu", "Shikyuritu_Turo_Kyu",
    "Shikyuritu_Gonen",
    "Shikyuritu_Shogai_Ippan", "Shikyuritu_Shogai_Ippan_keinen",
    "Shikyuritu_Shogai_20mae", "Shikyuritu_Shogai_20mae_keinen",
    "Shikyuritu_Shogai_Kyu",
    "Shikyuritu_Tuma", "Shikyuritu_Otto", "Shikyuritu_Ko",
    "Shikyuritu_Kafu", "Kakudai_Ichibu",
    "Waribikiritu", "Kyufu_ritu", "Kyufu_ritu1", "Kyufu_ritu2")

# printout 段階で突き合わせる配列（ハーネスの `P(…)` と同じ並び。
# `printout()` は年度末を**年度間に上書きする**ので、`stat` 段階とは
# 同じ配列でも中身が違う）
PRINTOUT_ARRAYS = ("Rorei", "Rorei_Kyu", "Turo_Kyu", "Gonen",
                   "Shogai_Ippan", "Shogai_20mae", "Shogai_Kyu",
                   "Izoku_Tuma", "Izoku_Otto", "Izoku_Ko",
                   "Kafu", "Kafu_Kyu", "Ichijikin")

# stat 段階で突き合わせる配列（ハーネスの `T(…)` と同じ並び。
# `stat()` は種別をまたいだ計を作るので**種別の接頭辞を付けない**）
STAT_ARRAYS = ("Hiho_Kei", "Hiho_Noufu", "Fuka_Hiho", "Hiho_Menjo",
               "Rorei", "Rorei_Kyu", "Turo_Kyu", "Gonen",
               "Shogai_Ippan", "Shogai_20mae", "Shogai_Kyu",
               "Izoku_Tuma", "Izoku_Otto", "Izoku_Ko",
               "Kafu", "Kafu_Kyu", "Ichijikin")

# siml 段階で回す年数。`siml()` は前年度から作るので飛ばせない。
# `_op`（45年化）は `OPTION_START` = 2031 なので、そこまで届かせないと
# `extenda/b/c` `Hihokensha2` `Nendomatu_Tyousei_Keisu` が1度も動かない
# `write_BeginData()` に渡す実行時刻。原本は走らせた時刻を書くので
# 1行目は必ず食い違うが、移植版はこれで固定して2行目から比べられる
# ようにする（`test_nat_full.py` も同じものを使う）
FIXED_ASCTIME = "Thu Jan  1 00:00:00 1970\n"

SIML_YEARS = {"siml": 3, "siml_op": 15, "stat": 3, "printout": 3}

# siml 段階で種別ごとに突き合わせる配列（ハーネスの `M(…)` と同じ並び）
SIML_ARRAYS = (
    "Hihokensha", "Taikisha", "Hihokensha2",
    "Rorei_Nendomatu", "Rorei_Ichibu_Nendomatu", "Rorei_Kyu_Nendomatu",
    "Turo_Kyu_Nendomatu", "Gonen_Nendomatu",
    "Shogai_Ippan_Nendomatu", "Shogai_20mae_Nendomatu",
    "Shogai_Kyu_Nendomatu",
    "Izoku_Tuma_Nendomatu", "Izoku_Otto_Nendomatu", "Izoku_Ko_Nendomatu",
    "Kafu_Nendomatu", "Kafu_Kyu_Nendomatu", "Ichijikin_Nendomatu",
    "Rorei_Shinki2",
    "Hiho_Kei", "Hiho_Noufu", "Fuka_Hiho", "Hiho_Noufu_P", "Fuka_Hiho_P",
    "Hiho_Menjo", "Hiho_Menjo_P",
    "Rorei", "Rorei_Kyu", "Turo_Kyu", "Gonen",
    "Shogai_Ippan", "Shogai_20mae", "Shogai_Kyu",
    "Izoku_Tuma", "Izoku_Otto", "Izoku_Ko", "Kafu", "Kafu_Kyu",
    "Ichijikin")

# shke 段階で種別ごとに突き合わせる配列（ハーネスの `S(…)` と同じ並び）
SHKE_ARRAYS = ("Hiho_Kei", "Hiho_Noufu", "Fuka_Hiho", "Hiho_Noufu_P",
               "Fuka_Hiho_P", "Hiho_Menjo", "Hiho_Menjo_P",
               "Rorei", "Rorei_Kyu", "Turo_Kyu", "Gonen",
               "Shogai_Ippan", "Shogai_20mae", "Shogai_Kyu",
               "Izoku_Tuma", "Izoku_Otto", "Izoku_Ko",
               "Kafu", "Kafu_Kyu", "Ichijikin")

# `main.c` が回す種別（`PerformSiml` が真を返すもの）
SHUBETU = (2, 3, 5, 6)

# econ 段階で突き合わせる配列
ECON_ARRAYS = ("kaiteiritu_tannen", "Full_Pension", "Kakyu_Tanka_12shi",
               "Kakyu_Tanka_3shiiko", "Tanka_Shibou", "Kanou_Nensu",
               "Full_Pension_Shonendo")

# kaizen 段階で突き合わせる配列（`waku()` のぶんも含む）
KAIZEN_ARRAYS = ("Sotowaku", "Sotowaku_2gou", "Sotowaku_Jurai",
                 "q", "Izoku_Keinen")

# noufuritu 段階で突き合わせる配列
NOUFU_ARRAYS = ("Noufuritu", "Noufuritu_Fuka", "Hiho_Sankyu_Sum",
                "Hiho_Ikukyu", "Hiho_Ikukyu_Sum")

# cntl 段階で突き合わせるもの
CNTL_STRS = ("KOKUNEN", "ECON", "SOTOWAKU", "SOTOWAKU_JURAI", "Version",
             "BIRTHFILE", "DEATH")
CNTL_INTS = ("Kako_Saimu", "TINSURA", "Kugiri_Nendo", "Jyukyusha_Nomi")
CNTL_INTS2 = ("Part", "Part_Year", "Option", "OPTION_START",
              "OP_HIKIAGE_KANKAKU")

# seid 段階で突き合わせるもの
SEID_ARRAYS = ("Kanou_Nensu", "Full_Pension_Shonendo",
               "Tanka_Shibou_Shonendo", "Hokenryou_Wariai",
               "Shogai_Bairitu", "Kokko_Wariai")
SEID_DBLS = ("Full_Pension_Fuka", "Kakyu_Tanka_12shi_Shonendo",
             "Kakyu_Tanka_3shiiko_Shonendo", "Tanka_Shibou_Fuka")

# 8つの struct（`sizeof` の確かめ用）
STRUCTS = ("hihokensha", "rorei", "rorei_kyu", "gonen", "shogai",
           "izoku", "kafu", "ichijikin")
# 原本の欄の数（`m*.h` の宣言から）
STRUCT_FIELDS = {
    "hihokensha": 3 + 5 * 3 + 3,    # ninzu kikan noufu menjo[5][3] × 3欄
    "rorei": 2 + 5 * 3 + 2,
    "rorei_kyu": 7,
    "gonen": 2,
    "shogai": 5,
    "izoku": 3,
    "kafu": 2 + 5 * 3,
    "ichijikin": 3,
}

# 原本の .c（`main.c` はハーネスが置き換える）
_SRCS = ("stdfm.c", "cntl.c", "file_open.c", "seid.c", "econ.c", "waku.c",
         "kaizen.c", "dtst.c", "kiso.c", "noufuritu.c", "siml.c",
         "str_op.c", "shke.c", "stat.c", "printout.c")


def _stage_lists(root):
    """③のファイルリストの控えを作り、**出力先だけ**を `root` に向ける。

    入力は `nat/base_data` `wakuc` `emp/data` の3か所なので、
    `nat/rslt` と `nat/data` を指す行を書き替えれば出力は全部
    一時ディレクトリに逃がせる。リストは EUC-JP なのでバイトで扱う。
    """
    os.makedirs(os.path.join(root, "rslt"), exist_ok=True)
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    io = os.path.join(root, "io_file")
    os.makedirs(io, exist_ok=True)
    got = []
    for name in ("infile.csv", "outfile.csv"):
        src = os.path.join(NAT, "io_file", name)
        b = open(src, "rb").read()
        for sub in (b"/rslt", b"/data"):
            b = b.replace(NAT.encode() + sub, root.encode() + sub)
        assert NAT.encode() + b"/rslt" not in b, "出力先が残っている"
        assert NAT.encode() + b"/data" not in b, "出力先が残っている"
        dst = os.path.join(io, name)
        open(dst, "wb").write(b)
        got.append(dst)
    return got


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
    cc = _cc()
    if cc is None:
        pytest.skip("C++ コンパイラが無い")

    tmp = tmp_path_factory.mktemp("nat_stage")
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

    runner = tmp / "run_py.py"
    src = _RUNNER % (os.path.join(HERE, "clib"), os.path.join(HERE, "nat"))
    # 配列の顔ぶれはモジュールの定数を使い回す（二重に書かない）
    src = src.replace("__DTST_NAMES__", repr(DTST_ARRAYS))
    src = src.replace("__KISO_NAMES__", repr(KISO_ARRAYS))
    src = src.replace("__SHKE_NAMES__", repr(SHKE_ARRAYS))
    src = src.replace("__SIML_NAMES__", repr(SIML_ARRAYS))
    src = src.replace("__STAT_NAMES__", repr(STAT_ARRAYS))
    src = src.replace("__PRINTOUT_NAMES__", repr(PRINTOUT_ARRAYS))
    src = src.replace("__ASCTIME__", repr(FIXED_ASCTIME))
    runner.write_text(src, encoding="utf-8")

    out = {}
    dirs = {}
    for stage in STAGES:
        for tag, argv in (("", ARGV), ("_op", ARGV_OP)):
            if stage in ("strop", "econ", "dtst", "kiso", "shke",
                         "stat", "printout") and tag:
                # `strop` は引数に依らない。あとは1通りだけ見る
                continue
            key = stage + tag

            if stage in ("econ", "kaizen", "noufuritu", "dtst", "kiso",
                         "shke", "siml", "stat", "printout"):
                # 入力ファイルが要る段階。**出力先を必ず書き替える**
                if not os.path.exists(os.path.join(NAT, "io_file",
                                                   "infile.csv")):
                    out[key] = None
                    continue
                # 段階ごとに別の木に出す（あとでファイルを比べるため）
                c_lists = _stage_lists(str(tmp / key / "c"))
                py_lists = _stage_lists(str(tmp / key / "py"))
                dirs[key] = (str(tmp / key / "c"), str(tmp / key / "py"))
                c_argv = c_lists + argv[2:]
                py_argv = py_lists + argv[2:]
            else:
                c_argv = py_argv = argv

            env = dict(os.environ)
            env["SIML_YEARS"] = str(SIML_YEARS.get(key, 3))

            r = subprocess.run([exe, stage] + c_argv, cwd=str(bsrc),
                               capture_output=True, timeout=1800, env=env)
            assert r.returncode == 0, (
                f"[{key}] 原本が異常終了:\n"
                + r.stderr.decode("utf-8", "replace")[:3000])
            c_out = _parse(r.stdout.decode("utf-8"))

            r = subprocess.run([sys.executable, str(runner), stage]
                               + py_argv, capture_output=True,
                               timeout=1800, env=env)
            assert r.returncode == 0, (
                f"[{key}] 移植版が異常終了:\n"
                + r.stderr.decode("utf-8", "replace")[:3000])
            py_out = _parse(r.stdout.decode("utf-8"))

            out[key] = (c_out, py_out)
    out["_dirs"] = dirs
    return out


_RUNNER = '''# -*- coding: utf-8 -*-
import os, sys, zlib
import numpy as np
sys.path.insert(0, %r)          # clib（`libc.py`）
sys.path.insert(0, %r)          # nat
import glva
from glva import (G, HIHOKENSHA, ROREI, ROREI_KYU, GONEN, SHOGAI, IZOKU,
                  KAFU, ICHIJIKIN)
import cntl as cntl_mod
import econ as econ_mod
import file_open as fo
import dtst as dtst_mod
import kaizen as kaizen_mod
import kiso as kiso_mod
import noufuritu as nou_mod
import printout as printout_mod
import seid as seid_mod
import shke as shke_mod
import siml as siml_mod
from natload import load_stat   # `stat` は標準ライブラリとぶつかる
stat_mod = load_stat()
import str_op as so
import waku as waku_mod
from setconst import SUIKEISHONENDO, TOKUTEI_NENDO

STAGE = sys.argv[1]
argv = [None] + sys.argv[2:]        # 原本の argv と同じ並び（[0] は名前）

# 種別ごとに出す配列（ハーネスの並びと合わせる）
DTST_NAMES = __DTST_NAMES__
KISO_NAMES = __KISO_NAMES__
SHKE_NAMES = __SHKE_NAMES__
SIML_NAMES = __SIML_NAMES__
STAT_NAMES = __STAT_NAMES__
PRINTOUT_NAMES = __PRINTOUT_NAMES__
FIXED_ASCTIME = __ASCTIME__
YEARS = int(os.environ.get("SIML_YEARS", "3"))


def rep(name, a):
    a = np.ascontiguousarray(a)
    v = a.ravel() if a.dtype == np.float64 else a.reshape(-1).view(np.float64)
    nz = v[v != 0]
    first = float(nz[0]).hex() if nz.size else "-"
    print("## %%s %%d %%08x %%s" %% (name, v.size, zlib.crc32(v.tobytes()),
                                 first))


def rep_struct(name, o):
    v = np.asarray(o).reshape(1).view(np.float64)
    nz = v[v != 0]
    first = float(nz[0]).hex() if nz.size else "-"
    print("## %%s %%d %%08x %%s" %% (name, v.size, zlib.crc32(v.tobytes()),
                                 first))


def rep_int(n, v):
    print("## %%s int %%d -" %% (n, v))


def rep_dbl(n, v):
    print("## %%s dbl %%s -" %% (n, float(v).hex()))


def rep_str(n, v):
    print("## %%s str %%s -" %% (n, v))


def rep_sizes():
    for k in ("hihokensha", "rorei", "rorei_kyu", "gonen", "shogai",
              "izoku", "kafu", "ichijikin"):
        rep_int("sizeof_" + k, glva.STRUCT_DTYPES[k].itemsize)


if STAGE == "strop":
    R1, R2 = 1.008, 0.997

    def fill(dt, mul):
        """C の FILL と同じ：欄を順に mul * 0.125 * (i+1) で埋める。"""
        x = np.zeros((), dtype=dt)
        k = 0
        for f in dt.names:
            sh = dt.fields[f][0].shape
            m = int(np.prod(sh)) if sh else 1
            v = np.array([mul * 0.125 * (k + i + 1) for i in range(m)])
            x[f] = v.reshape(sh) if sh else v[0]
            k += m
        return x

    TYPES = [("hihokensha", HIHOKENSHA), ("rorei", ROREI),
             ("rorei_kyu", ROREI_KYU), ("gonen", GONEN), ("shogai", SHOGAI),
             ("izoku", IZOKU), ("kafu", KAFU), ("ichijikin", ICHIJIKIN)]
    HAS_SCALAR = {"hihokensha", "rorei", "rorei_kyu", "gonen", "shogai",
                  "izoku", "kafu"}
    HAS_MUL = {"rorei", "rorei_kyu", "shogai", "izoku", "kafu"}
    HAS_NENDOKAN = {"rorei", "rorei_kyu", "gonen", "shogai", "izoku",
                    "kafu", "ichijikin"}
    HAS_NENDOKAN2 = {"shogai", "izoku"}
    HAS_NENDOKAN64 = {"rorei", "rorei_kyu", "gonen", "shogai", "izoku",
                      "ichijikin"}
    HAS_ADJUST = {"rorei", "rorei_kyu", "gonen", "shogai", "izoku", "kafu"}

    for nm, dt in TYPES:
        x, y, z = fill(dt, 1.0), fill(dt, 3.0), fill(dt, 7.0)
        rep_struct(nm + "_add", so.add(x, y))
        if nm in HAS_SCALAR:
            rep_struct(nm + "_scalar", so.scalar(2.25, x))
        if nm == "hihokensha":
            rep_struct(nm + "_average_by_ninzu", so.average_by_ninzu(x))
            x0 = fill(dt, 1.0)
            x0["ninzu"] = 0.0
            rep_struct(nm + "_average_by_ninzu_0", so.average_by_ninzu(x0))
            for n in (TOKUTEI_NENDO - 1, TOKUTEI_NENDO, TOKUTEI_NENDO + 1):
                rep_struct("%%s_scalar_2_%%d" %% (nm, n),
                           so.scalar_2(2.25, fill(dt, 1.0), n))
        if nm in HAS_MUL:
            rep_struct(nm + "_multiply", so.multiply(x, y))
        if nm in HAS_NENDOKAN:
            if nm in HAS_NENDOKAN2:
                rep_struct(nm + "_nendokan", so.nendokan(x, y, R1, R2))
            else:
                rep_struct(nm + "_nendokan", so.nendokan(x, y, R1))
        if nm in HAS_NENDOKAN64:
            rep_struct(nm + "_nendokan_64", so.nendokan_64(x, y, z, R1))
        if nm in HAS_ADJUST:
            rep_struct(nm + "_adjustbenefit", so.adjustbenefit(0.9985, x))
    rep_sizes()
    sys.exit(0)

cntl_mod.cntl(G, argv)

if STAGE == "cntl":
    for n in ("KOKUNEN", "ECON", "SOTOWAKU", "SOTOWAKU_JURAI", "Version",
              "BIRTHFILE", "DEATH"):
        rep_str(n, getattr(G, n))
    for n in ("Kako_Saimu", "TINSURA", "Kugiri_Nendo", "Jyukyusha_Nomi"):
        rep_int(n, getattr(G, n))
    rep_dbl("Kisai_Shitasasae", G.Kisai_Shitasasae)
    for n in ("Part", "Part_Year", "Option", "OPTION_START",
              "OP_HIKIAGE_KANKAKU"):
        rep_int(n, getattr(G, n))
    rep_sizes()
    sys.exit(0)

# 種別ループ（`dtst` 以降）まで通す段階。ここまで来たら
# `waku` `kaizen` `noufuritu` は必ず走らせる
SHUBETU_STAGES = ("dtst", "kiso", "shke", "siml", "stat", "printout")

if STAGE in ("econ", "waku", "kaizen", "noufuritu") + SHUBETU_STAGES:
    fo.file_open(G, argv[1], G.fp_in, G.infile_name)
    fo.file_open(G, argv[2], G.fp_out, G.outfile_name)
    seid_mod.seid(G)
    econ_mod.econ(G)
    if STAGE == "econ":
        for n in ("kaiteiritu_tannen", "Full_Pension", "Kakyu_Tanka_12shi",
                  "Kakyu_Tanka_3shiiko", "Tanka_Shibou", "Kanou_Nensu",
                  "Full_Pension_Shonendo"):
            rep(n, getattr(G, n))
    else:
        waku_mod.waku(G)
        if STAGE == "waku":
            # ハーネスと同じ顔ぶれだけを出す（`_cmp` は C の側の名前を
            # なめるので、余分に出しても落ちないが揃えておく）
            for n in ("Sotowaku", "Sotowaku_2gou", "Sotowaku_Jurai"):
                rep(n, getattr(G, n))
        else:
            kaizen_mod.kaizen(G)
            if STAGE == "kaizen":
                for n in ("Sotowaku", "Sotowaku_2gou", "Sotowaku_Jurai",
                          "q", "Izoku_Keinen"):
                    rep(n, getattr(G, n))
            else:
                nou_mod.noufuritu(G)
                if STAGE == "noufuritu":
                    for n in ("Noufuritu", "Noufuritu_Fuka",
                              "Hiho_Sankyu_Sum", "Hiho_Ikukyu",
                              "Hiho_Ikukyu_Sum"):
                        rep(n, getattr(G, n))
                else:
                    # `main.c` と同じ順で 2 → 3 → 5 → 6。
                    # 段階は前の段階を必ず含むので、**通す番号**で見る
                    # （足すたびに `if` を3つ直す形にしないため）
                    step = SHUBETU_STAGES.index(STAGE)
                    names = (DTST_NAMES, KISO_NAMES, SHKE_NAMES,
                             SIML_NAMES, SIML_NAMES, SIML_NAMES)[step]
                    for shubetu in (2, 3, 5, 6):
                        dtst_mod.dtst(G, shubetu)
                        if step >= 1:
                            kiso_mod.kiso(G, shubetu)
                        if step >= 2:
                            shke_mod.shke(G, SUIKEISHONENDO, shubetu)
                        if step >= 3:
                            for nendo in range(SUIKEISHONENDO + 1,
                                               SUIKEISHONENDO + YEARS + 1):
                                siml_mod.siml(G, nendo, shubetu)
                                shke_mod.shke(G, nendo, shubetu)
                        if STAGE not in ("stat", "printout"):
                            for n in names:
                                rep("s%%d_%%s" %% (shubetu, n),
                                    getattr(G, n))
                    if STAGE in ("stat", "printout"):
                        # `main.c` は種別ループを抜けてから1回呼ぶ。
                        # 時刻の行が食い違わないように固定して渡す
                        stat_mod.stat(G, asctime=FIXED_ASCTIME)
                        names = STAT_NAMES
                    if STAGE == "printout":
                        printout_mod.printout(G)
                        names = PRINTOUT_NAMES
                    if STAGE in ("stat", "printout"):
                        for n in names:
                            rep(n, getattr(G, n))
    rep_sizes()
    fo.file_close(G)
    sys.exit(0)

if STAGE == "seid":
    seid_mod.seid(G)
    rep("Kanou_Nensu", G.Kanou_Nensu)
    rep("Full_Pension_Shonendo", G.Full_Pension_Shonendo)
    rep_dbl("Full_Pension_Fuka", G.Full_Pension_Fuka)
    rep_dbl("Kakyu_Tanka_12shi_Shonendo", G.Kakyu_Tanka_12shi_Shonendo)
    rep_dbl("Kakyu_Tanka_3shiiko_Shonendo", G.Kakyu_Tanka_3shiiko_Shonendo)
    rep("Tanka_Shibou_Shonendo", G.Tanka_Shibou_Shonendo)
    rep_dbl("Tanka_Shibou_Fuka", G.Tanka_Shibou_Fuka)
    rep("Hokenryou_Wariai", G.Hokenryou_Wariai)
    rep("Shogai_Bairitu", G.Shogai_Bairitu)
    rep("Kokko_Wariai", G.Kokko_Wariai)
    rep_sizes()
    sys.exit(0)

sys.exit("unknown stage " + STAGE)
'''


def _parse(text):
    """ハーネスの出力を `{名前: 行の残り}` にする（`## ` の行だけ）。"""
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
    """同じ名前の行を突き合わせる。**%a の1ビットまで**。

    見る顔ぶれは**原本の側**。移植版だけにある名前があれば
    それも挙げる（段階ごとに出す物が揃っていることの確かめ）。
    """
    bad = []
    assert c_out, f"[{stage}] 原本の出力が空"
    dake = sorted(set(py_out) - set(c_out))
    if dake:
        bad.append(f"移植版だけにある: {', '.join(dake)}")
    for name, c_rest in c_out.items():
        if name not in py_out:
            bad.append(f"{name}: 移植版に無い（C = {c_rest}）")
            continue
        p_rest = py_out[name]
        cf = c_rest.split()
        pf = p_rest.split()
        if cf[0] == "int" or cf[0] == "str":
            same = cf[1] == pf[1]
        elif cf[0] == "dbl":
            same = float.fromhex(cf[1]) == float.fromhex(pf[1])
        else:
            if cf[0] != pf[0]:
                bad.append(f"{name}: 要素数が違う C = {cf[0]} / "
                           f"Python = {pf[0]}")
                continue
            same = cf[1].lower() == pf[1].lower()
        if not same:
            extra = ""
            if len(cf) > 2 and len(pf) > 2 and cf[2] != "-" and pf[2] != "-":
                extra = f"（先頭の非ゼロ C = {cf[2]} / Python = {pf[2]}）"
            bad.append(f"{name}: C = {c_rest} / Python = {p_rest}{extra}")
    return bad


def test_structの寸法に詰め物が無い(probe):
    """`sizeof(struct)` が「欄数 × 8」であること。

    これが成り立たないと、NumPy の構造化 dtype と C の構造体の
    バイト列が一致せず、下の CRC32 の突き合わせが意味を失う。
    """
    out = probe
    c_out, py_out = out["cntl"]
    for k in STRUCTS:
        name = f"sizeof_{k}"
        assert name in c_out, f"{name} がハーネスの出力に無い"
        n = int(c_out[name].split()[1])
        assert n == STRUCT_FIELDS[k] * 8, (
            f"struct {k} が {n} バイト（欄 {STRUCT_FIELDS[k]} 個 × 8 = "
            f"{STRUCT_FIELDS[k] * 8} を期待）。詰め物が入っている")
        assert py_out[name].split()[1] == str(n), (
            f"移植版の dtype が {py_out[name]}（C は {n} バイト）")


@pytest.mark.parametrize("tag", ["", "_op"])
def test_cntlの引数15個が原本と一致(probe, tag):
    """`cntl( argc , argv )` が入れる設定。`_op` は45年化を入れたもの。"""
    out = probe
    c_out, py_out = out["cntl" + tag]
    bad = _cmp(c_out, py_out, "cntl" + tag)
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in CNTL_STRS + CNTL_INTS + CNTL_INTS2:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 45年化の旗が効いていることの確かめ
    want = "1" if tag else "0"
    assert c_out["Option"].split()[1] == want


@pytest.mark.parametrize("tag", ["", "_op"])
def test_seidの制度定数が原本と一致(probe, tag):
    """`seid()` が入れる加入可能年数・満額・単価。

    `_op`（45年化）では `Kanou_Nensu` が 40年 → 最大45年に伸び、
    `Full_Pension_Shonendo` がそれに比例して増える。`stdfm.c` の
    `encho_nensu` / `encho_year` もここで通る。
    """
    out = probe
    c_out, py_out = out["seid" + tag]
    bad = _cmp(c_out, py_out, "seid" + tag)
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in SEID_ARRAYS + SEID_DBLS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ（21,200 要素）
    assert c_out["Kanou_Nensu"].split()[0] == "21200"


def test_45年化で加入可能年数が変わる(probe):
    """`Option = 1` のとき `Kanou_Nensu` と満額が変わること。

    変わらなければ `_op` の突き合わせは何も試していないことになる。
    """
    out = probe
    c_plain, _ = out["seid"]
    c_op, _ = out["seid_op"]
    for n in ("Kanou_Nensu", "Full_Pension_Shonendo"):
        assert c_plain[n].split()[1] != c_op[n].split()[1], (
            f"{n} が 45年化の有無で変わらない。`Option` が効いていない")
    # 死亡一時金の最高区分だけ 320,000 → 370,000 になる
    assert (c_plain["Tanka_Shibou_Shonendo"].split()[1]
            != c_op["Tanka_Shibou_Shonendo"].split()[1])


def test_str_opの8つの型の演算が原本と一致(probe):
    """`str_op.c` の 52 通りの演算。

    8つの `struct` × `scalar` / `scalar_2` / `add` / `multiply` /
    `nendokan` / `nendokan_64` / `adjustbenefit` / `average_by_ninzu`
    のうち、原本に定義があるものを全部。`nendokan` の重み
    （支払遅れ2か月）と、付加年金に改定率を掛けないところ、
    `shogai` / `izoku` が改定率を2つ取るところも通る。
    """
    out = probe
    c_out, py_out = out["strop"]
    bad = _cmp(c_out, py_out, "strop")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    # 空振りしていないことの確かめ
    ops = [n for n in c_out if not n.startswith("sizeof_")]
    assert len(ops) == 44, f"演算が {len(ops)} 通り（期待 44）"
    for t in STRUCTS:
        assert f"{t}_add" in c_out, f"{t}_add が無い"


def test_scalar_2が特定期間で按分する(probe):
    """`TOKUTEI_NENDO`（2009年度）の前後で `menjo` の欄が入れ替わること。

    国庫負担が3分の1から2分の1に変わったのは 2009年度の**4月**
    （`TOKUTEI_TUKI` = 4）。`scalar_2` は変わった年度を月数で按分する。

        ( TOKUTEI_TUKI - 4 ) / 12.  = 0 / 12   旧（3分の1）は 0 か月
        ( 16 - TOKUTEI_TUKI ) / 12. = 12 / 12  新（2分の1）が 12 か月

    なので**2009年度は 2010年度と同じ結果になる**（丸ごと新）。
    2008年度だけが違う。式は `TOKUTEI_TUKI` を 7 に変えれば
    3 / 12 と 9 / 12 になる書き換えられる形で、たまたま 0 と 1 に
    なっている（`検証/原本の不具合.md` の E の仲間）。

    ここで固定するのは

    - 2008年度 ≠ 2009年度（旧と新で欄が入れ替わる）
    - 2009年度 == 2010年度（`TOKUTEI_TUKI` が 4 だから）

    の2つ。原本と移植版の突き合わせは上のテストで済んでいる。
    """
    out = probe
    c_out, py_out = out["strop"]
    for src in (c_out, py_out):
        a = src["hihokensha_scalar_2_2008"].split()[1]
        b = src["hihokensha_scalar_2_2009"].split()[1]
        c = src["hihokensha_scalar_2_2010"].split()[1]
        assert a != b, "2008年度と2009年度が同じ。特定期間が効いていない"
        assert b == c, (
            "2009年度と2010年度が違う。`TOKUTEI_TUKI` が 4 なら"
            "2009年度は丸ごと新のはず")


def test_econの改定率と年金額が原本と一致(probe):
    """`econ()` が作る改定率と基礎年金の単価。

    経済前提（`econ-3001.csv`）を読んで、単年度と累積の改定率、
    基礎年金の満額、加給の単価、死亡一時金の単価を作る。
    `stdfm` の `read_data` と、`econ.c` 自前の `round`（`sprintf` を
    通す丸め）と `pension_marume`（100円単位）もここで通る。

    **`kaiteiritu_marume` の戻り値を捨てているところ3か所**（E1）も
    そのまま写しているので、一致すればそれも再現できている。
    """
    out = probe
    got = out.get("econ")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "econ")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in ECON_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ（125年度 × 116歳）
    assert c_out["kaiteiritu_tannen"].split()[0] == "14500"
    assert c_out["Full_Pension"].split()[2] != "-", "満額が全部 0"


def test_econが書く2ファイルがバイト一致(probe):
    """`econ()` が書く `KOKUKAITE-*.csv` と `PENSION_*.csv`。

    `rslt_out`（67歳以上の欄）と `kaitei_out`（0〜115歳の欄を
    見出し付きで5回）と `ichijikin_out`（死亡一時金）の書式が
    バイト単位で合っているか。

    `"%20.14e,"` の行末カンマや、`ichijikin_out` が
    `option == 1` のとき見出しをカンマなしで足すところも含む。
    """
    out = probe
    if out.get("econ") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, py_dir = out["_dirs"]["econ"]
    bad = []
    n_chk = 0
    for sub in ("rslt", "data"):
        cd = os.path.join(c_dir, sub)
        pd = os.path.join(py_dir, sub)
        for f in sorted(os.listdir(cd)):
            cb = open(os.path.join(cd, f), "rb").read()
            pb = open(os.path.join(pd, f), "rb").read()
            n_chk += 1
            if cb == pb:
                continue
            cl = cb.decode("utf-8", "replace").splitlines()
            pl = pb.decode("utf-8", "replace").splitlines()
            for i, (x, y) in enumerate(zip(cl, pl), 1):
                if x != y:
                    bad.append(f"{f} の {i}行目\n    C      {x[:200]}\n"
                               f"    Python {y[:200]}")
                    break
            else:
                bad.append(f"{f} の行数が違う "
                           f"（C {len(cl)} / Python {len(pl)}）")
    assert not bad, "原本と一致しない:\n" + "\n".join(bad[:10])
    # 空振りしていないことの確かめ（`econ()` が中身を書くのは2本）
    assert n_chk == 11, f"{n_chk} 本しか見ていない（期待 11）"
    kaite = os.path.join(c_dir, "data", "KOKUKAITE-3001-3001E.csv")
    pension = os.path.join(c_dir, "data", "PENSION_3001-3001-3001.csv")
    assert os.path.getsize(kaite) > 100000, "KOKUKAITE が小さすぎる"
    assert os.path.getsize(pension) > 1000000, "PENSION が小さすぎる"


@pytest.mark.parametrize("tag", ["", "_op"])
def test_wakuとkaizenの基礎数が原本と一致(probe, tag):
    """`waku()` が読む外枠と、`kaizen()` が読む生命表・有配偶率。

    - `Sotowaku`（63,210 要素）… 第1号・第3号・人口を種別に詰める
    - `Sotowaku_2gou`（27,090）… 厚年＋共済3制度を `+=` で足し込む
    - `Sotowaku_Jurai`（63,210）… 45年化のときの「従来の」外枠
    - `q`（11,960）… 死亡率（10万分の1に直す）
    - `Izoku_Keinen`（10,812）… 有配偶率（2071年度以降は延ばす）

    `waku.c:43` の書き間違い（F22。条件の変数が `shubetu`）も
    そのまま写しているので、一致すればそれも再現できている。
    """
    out = probe
    got = out.get("kaizen" + tag)
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "kaizen" + tag)
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in KAIZEN_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    assert c_out["Sotowaku"].split()[2] != "-", "外枠が全部 0"
    assert c_out["q"].split()[2] != "-", "死亡率が全部 0"


def test_45年化のときだけ従来外枠を読む(probe):
    """`Option = 1` のときだけ `Sotowaku_Jurai` に値が入ること。

    `waku.c:156-203` の `if( Option == 1 )` の枝。通常試算では
    **全部 0 のまま**で、45年化のときだけ `waku{従来外枠}-20/11/14.csv`
    を読む。ここが動かないと F22 の周りも試せていないことになる。
    """
    out = probe
    if out.get("kaizen") is None or out.get("kaizen_op") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_plain, p_plain = out["kaizen"]
    c_op, p_op = out["kaizen_op"]
    for src in (c_plain, p_plain):
        assert src["Sotowaku_Jurai"].split()[2] == "-", (
            "通常試算で `Sotowaku_Jurai` に値が入っている")
    for src in (c_op, p_op):
        assert src["Sotowaku_Jurai"].split()[2] != "-", (
            "45年化でも `Sotowaku_Jurai` が全部 0。"
            "`Option` の枝が動いていない")
    # 外枠そのものは `Option` で変わらない
    assert c_plain["Sotowaku"] == c_op["Sotowaku"]


@pytest.mark.parametrize("tag", ["", "_op"])
def test_noufurituの納付率が原本と一致(probe, tag):
    """`noufuritu()` が作る納付率と免除の対象割合。

    - `Noufuritu`（416,262 要素）… 種別 × 年度 × 年齢 × 納付区分
    - `Noufuritu_Fuka`（37,842）… 付加年金の納付率
    - `Hiho_Sankyu_Sum`（106）… 産前産後免除の人数
    - `Hiho_Ikukyu`（51）/ `Hiho_Ikukyu_Sum`（106）… 育児期間免除

    `tuinou_make` の「11回足す」順、`noufu_hosei` の目標合わせ、
    `taishou_hosei` の人口比での伸ばし、`sankyu_taishou_cal` と
    `ikukyu_taishou_cal_f/m` の付け替え、`ikukyu_taishou_cal_m` の
    **0 割り**（`nenkin_fdiv` を使っていない）まで通る。
    """
    out = probe
    got = out.get("noufuritu" + tag)
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "noufuritu" + tag)
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in NOUFU_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    assert c_out["Noufuritu"].split()[0] == "416262"
    assert c_out["Noufuritu"].split()[2] != "-", "納付率が全部 0"


@pytest.mark.parametrize("tag", ["", "_op"])
def test_noufurituが書くnat_wariaiがバイト一致(probe, tag):
    """`bunpu_data_out` が書く `nat_wariai*.csv`（1.9MB）。

    ⑥分布推計が読むファイル。10列の並び（全額納付・付加・法定免除・
    申請全額・4分の3・半額・4分の1・学生・若年者・未納）と
    `"%11.9e"` の書式がバイト単位で合っているか。

    最後の列は `1.` から8つを**書いてある順に**引くので、
    足す順を変えると最後の桁が変わる。通常試算と45年化の2通りで見る。
    """
    out = probe
    key = "noufuritu" + tag
    if out.get(key) is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, py_dir = out["_dirs"][key]
    rel = os.path.join("data", "nat_wariai3001-3001.csv")
    cp = os.path.join(c_dir, rel)
    pp = os.path.join(py_dir, rel)
    assert os.path.exists(cp), f"原本が {rel} を書いていない"
    cb = open(cp, "rb").read()
    pb = open(pp, "rb").read()
    if cb != pb:
        cl = cb.decode("utf-8", "replace").splitlines()
        pl = pb.decode("utf-8", "replace").splitlines()
        for i, (x, y) in enumerate(zip(cl, pl), 1):
            assert x == y, (f"nat_wariai の {i}行目\n    C      {x[:200]}\n"
                            f"    Python {y[:200]}")
        raise AssertionError(f"行数が違う（C {len(cl)} / Python {len(pl)}）")
    # 空振りしていないことの確かめ（2性別 × 105年度 × 51歳 ＋ 見出し）
    n = len(cb.decode("utf-8").splitlines())
    assert n == 2 * 105 * 51 + 1, f"{n} 行（期待 {2 * 105 * 51 + 1}）"


def test_45年化で納付率が変わる(probe):
    """`Option = 1` のとき `Noufuritu` と `Noufuritu_Fuka` が変わること。

    45年化では拠出年齢の上限が60歳から最大65歳に伸びるので、
    `extendb` / `extendc` の枝で 61〜65歳の納付率が埋まる。
    ここが動かないと `_op` の突き合わせは何も試していない。
    """
    out = probe
    if out.get("noufuritu") is None or out.get("noufuritu_op") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_plain, _ = out["noufuritu"]
    c_op, _ = out["noufuritu_op"]
    chigau = [n for n in NOUFU_ARRAYS
              if c_plain[n].split()[1] != c_op[n].split()[1]]
    assert set(chigau) == {"Noufuritu", "Noufuritu_Fuka"}, (
        f"45年化で変わる配列が {chigau}（期待 Noufuritu と "
        "Noufuritu_Fuka の2本）")


def test_dtstの足元の基礎数が原本と一致(probe):
    """種別 2・3・5・6 で `dtst()` を呼んだあとの `*_Nendomatu` 16本。

    13本のファイルから 2021年度の実績を `struct` に読む。
    `str_op` の `*_Zero` での初期化、`menjo[段階][期間]` の
    2次元の欄、`/ 12.`（月数 → 年数）まで通る。

    種別ごとに読むファイルの本数が違う（13 / 4 / 11 / 4）ので、
    4通り全部を見る。`*_Nendomatu` は種別ごとに**上書きされる**
    ので、種別ごとに配列を出して比べている。
    """
    out = probe
    got = out.get("dtst")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "dtst")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for sh in SHUBETU:
        for n in DTST_ARRAYS:
            assert f"s{sh}_{n}" in c_out, f"s{sh}_{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ
    assert c_out["s2_Hihokensha"].split()[0] == "5789826"
    assert c_out["s2_Hihokensha"].split()[2] != "-", "被保険者が全部 0"


def test_dtstは種別3と6で読む本数が少ない(probe):
    """種別 3・6（第3号）では寡婦・遺族・障害・5年年金を読まないこと。

    第3号のファイルは4本（被保険者・待期者・老齢基礎2本）だけ。
    `if( shubetu == 2 || shubetu == 5 )` で守られた枝を通らないので、
    それらの `*_Nendomatu` は**足元の年度が 0 のまま**になる。

    種別は 2 → 3 → 5 → 6 の順に走るので、種別 3 のあとは
    「種別 2 で読んだ値が消えて 0 になっている」ことを見る。
    """
    out = probe
    if out.get("dtst") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, _ = out["dtst"]
    # 第3号で読まないもの（足元の年度が 0 に戻る）
    for n in ("Gonen_Nendomatu", "Shogai_Ippan_Nendomatu",
              "Izoku_Tuma_Nendomatu", "Kafu_Nendomatu"):
        assert c_out[f"s2_{n}"].split()[1] != c_out[f"s3_{n}"].split()[1], (
            f"{n} が種別 2 と 3 で同じ。第3号の枝が効いていない")
    # 被保険者は第3号でも読む
    assert c_out["s3_Hihokensha"].split()[2] != "-", "第3号の被保険者が 0"
    # 寡婦と遺族（子）は**男の第1号だけ**が持つので種別 5 でも 0 に戻る
    for n in ("Kafu_Nendomatu", "Izoku_Ko_Nendomatu"):
        assert c_out[f"s5_{n}"].split()[2] == "-", (
            f"{n} が種別 5 で 0 ではない（男の第1号だけのはず）")


def test_kisoの基礎率が原本と一致(probe):
    """種別 2・3・5・6 で `kiso()` を呼んだあとの基礎率 52本。

    13本（第3号は3〜4本）のファイルから足元の率を読み、生命表と
    `Izoku_Keinen` で 2125年度まで伸ばす。失権率の3年平均の割り方、
    旧法の構造体まるごとの1年1歳ずらし、障害の経過措置への
    生年での振り替え、`Option` = 1 の 45年化の枝まで通る。

    種別ごとに読む本数が違い、しかも**前の種別の値を引き継ぐ配列が
    ある**ので、`main.c` と同じ 2 → 3 → 5 → 6 の順で回して
    そのたびに全部を出して比べている。
    """
    out = probe
    got = out.get("kiso")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "kiso")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for sh in SHUBETU:
        for n in KISO_ARRAYS:
            assert f"s{sh}_{n}" in c_out, f"s{sh}_{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ（106年度 × 51歳 = 5406要素）
    assert c_out["s2_Dattairyoku_Gokei"].split()[0] == "5406"
    assert c_out["s2_Dattairyoku_Gokei"].split()[2] != "-", "脱退力が全部 0"
    # 支給率の構造体3種も埋まっていること
    for n in ("Shikyuritu_Rorei", "Shikyuritu_Rorei_Kyu",
              "Shikyuritu_Turo_Kyu", "Kakudai_Ichibu"):
        assert c_out[f"s2_{n}"].split()[2] != "-", f"{n} が全部 0"


def test_kisoの遺族の率は種別をまたいで持ち越される(probe):
    """`Hassei_Wariai_Tuma` などを 0 で埋め直す枝が**種別 3 に無い**。

    `kiso.c` の遺族の発生割合は

    - 種別 2 が妻・子・寡婦を読み、夫を 0 に
    - 種別 5・6 が夫を読み、妻・子・寡婦を 0 に
    - **種別 3 はどちらの枝も通らない**

    `main.c` は 2 → 3 → 5 → 6 の順に回すので、種別 3 の `siml()` は
    **種別 2 が読んだ妻・子・寡婦の発生割合をそのまま使う**。
    第3号男が亡くなれば遺族基礎（妻）は出るので 0 が正しいとは
    言えないが、`Hassei_Wariai_Shibou` には種別 3・6 用に 0 で
    埋める `else` が書かれているのと揃っていない。
    `Sokan_*` と `Shikyuritu_Tuma` `_Ko` も同じで、種別 2 で読んだ
    ものが最後まで残る。**呼ぶ順を変えると結果が変わる**ことを
    ここで固定しておく（`検証/原本の不具合.md` **F24**）。
    """
    out = probe
    if out.get("kiso") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, _ = out["kiso"]

    def crc(name):
        return c_out[name].split()[1]

    def zero_p(name):
        return c_out[name].split()[2] == "-"

    # 種別 3 は種別 2 の値をそのまま持っている
    for n in ("Hassei_Wariai_Tuma", "Hassei_Wariai_Ko",
              "Hassei_Wariai_Kafu"):
        assert crc(f"s2_{n}") == crc(f"s3_{n}"), (
            f"{n} が種別 2 と 3 で違う。持ち越しが無くなっている")
        assert not zero_p(f"s2_{n}"), f"{n} が種別 2 で全部 0"
        # 種別 5・6 では 0 で埋め直される
        assert zero_p(f"s5_{n}"), f"{n} が種別 5 で 0 になっていない"
        assert zero_p(f"s6_{n}"), f"{n} が種別 6 で 0 になっていない"

    # 死亡一時金だけは種別 3・6 用に 0 で埋める `else` がある
    assert not zero_p("s2_Hassei_Wariai_Shibou")
    assert zero_p("s3_Hassei_Wariai_Shibou"), (
        "Hassei_Wariai_Shibou の else が効いていない")
    assert not zero_p("s5_Hassei_Wariai_Shibou")
    assert zero_p("s6_Hassei_Wariai_Shibou")

    # 相関と遺族の支給率は**どこでも 0 に戻らない**
    for n in ("Sokan_Tuma", "Sokan_Ko", "Sokan_Kafu",
              "Shikyuritu_Tuma", "Shikyuritu_Ko"):
        for sh in (3, 5, 6):
            assert crc(f"s2_{n}") == crc(f"s{sh}_{n}"), (
                f"{n} が種別 2 と {sh} で違う")

    # 夫は逆向き（種別 2・3 では 0、種別 5 で読む）
    assert zero_p("s2_Hassei_Wariai_Otto")
    assert zero_p("s3_Hassei_Wariai_Otto")
    assert not zero_p("s5_Hassei_Wariai_Otto")
    assert not zero_p("s6_Hassei_Wariai_Otto")


def test_kisoの夫の失権率は妻の率に13年で寄せる(probe):
    """`Shikkenritu_Otto` が種別 5 でだけ作られ、13年で妻の率になる。

    ```c
    for( sotai_nendo = 1 ; sotai_nendo <= 2014 + 19 - SHONENDO ; sotai_nendo++ )
      Shikkenritu_Otto[sotai_nendo][nenrei]
       = ( ( 2014 + 19 - SHONENDO - sotai_nendo ) * shikkenritu[nenrei][3]
           + sotai_nendo * Shikkenritu_Tuma[0][nenrei - 2 - MIN_IZOKU_TUMA_JUKYU] )
         / (double)( 2014 + 19 - SHONENDO );
    ```

    `2014 + 19 - SHONENDO` = 13。`sotai_nendo` = 0 には**何も入らない**
    （`for` が 1 から始まる）。使うのは**種別 2 で読んだ妻の失権率**
    なので、これも種別をまたいだ持ち越し（ただし「夫の率を妻の率に
    寄せる」という趣旨がはっきりしているので不具合ではない）。
    """
    out = probe
    if out.get("kiso") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, _ = out["kiso"]
    # 種別 2・3 では作られない（全部 0）
    assert c_out["s2_Shikkenritu_Otto"].split()[2] == "-"
    assert c_out["s3_Shikkenritu_Otto"].split()[2] == "-"
    # 種別 5 で埋まり、種別 6 には持ち越される
    assert c_out["s5_Shikkenritu_Otto"].split()[2] != "-"
    assert (c_out["s5_Shikkenritu_Otto"].split()[1]
            == c_out["s6_Shikkenritu_Otto"].split()[1])
    # 妻の失権率は種別 2 で読んだものが残っている
    assert (c_out["s2_Shikkenritu_Tuma"].split()[1]
            == c_out["s5_Shikkenritu_Tuma"].split()[1])


def test_shkeの足元の集計が原本と一致(probe):
    """種別 2・3・5・6 で `shke( 2021年度 )` を呼んだあとの集計 20本。

    `*_Nendomatu`（年度末の人数）に支給率を掛けて年度中の受給者数を
    出し、63歳以下をひとまとめにして年齢階級ごとに足し上げる。
    `str_op.c` の `add` `multiply` `scalar` `adjustbenefit` が
    構造体の値渡しで動くところまで通る。

    `shke()` は 0 に戻さず `+=` で足し込むので、`main.c` と同じ
    2 → 3 → 5 → 6 の順で回してそのたびに全部を出している。
    """
    out = probe
    got = out.get("shke")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "shke")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for sh in SHUBETU:
        for n in SHKE_ARRAYS:
            assert f"s{sh}_{n}" in c_out, f"s{sh}_{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ
    assert c_out["s2_Hiho_Kei"].split()[2] != "-", "被保険者の集計が全部 0"
    assert c_out["s2_Rorei"].split()[2] != "-", "老齢の集計が全部 0"


def test_shkeが種別ごとに埋める面が制度と合っている(probe):
    """どの配列がどの種別で増えるか。`shubetu` の添字の使い方の確かめ。

    `Hiho_Kei[shubetu][…]` のように**種別が先頭の添字**なので、
    配列ぜんぶの CRC32 を種別ごとに見ると「その種別が値を入れたか」
    が分かる。入れた値が 0 なら CRC32 は変わらない。

    ハーネスで測った結果（`○` = そこで変わる）。

    | 配列 | 2 | 3 | 5 | 6 | なぜ |
    |---|:-:|:-:|:-:|:-:|---|
    | `Hiho_Kei` `Rorei` `Hiho_Noufu_P` | ○ | ○ | ○ | ○ | 4種別とも被保険者と老齢基礎を持つ |
    | `Fuka_Hiho` `Rorei_Kyu` `Turo_Kyu` `Gonen` `Shogai_*` `Izoku_Otto` | ○ | | ○ | | 第1号だけ（第3号は基礎数も率も無い） |
    | `Hiho_Noufu` | ○ | ○ | | ○ | **足元の第1号の納付率が 0**（下記） |
    | `Izoku_Tuma` `Izoku_Ko` `Kafu` `Kafu_Kyu` `Ichijikin` | ○ | | | | 第1号男だけ |
    | `Hiho_Menjo` | ○ | | | | 足元の免除率も 0（同じ理由） |

    `Hiho_Noufu` が種別 5 で変わらないのは、**`noufuritu()` が
    第1号の納付率を足元（2021年度）に入れていない**から。

        Noufuritu[2][2021年度][…]  全部 0
        Noufuritu[2][2022年度][…]  51歳ぶん埋まる
        Noufuritu[3][2021年度][…]  41歳ぶん 1.0（第3号は納付済み扱い）

    足元の納付月数は `dtst()` が実績として直に読むので、率のほうは
    推計初年度の翌年からしか要らない。種別 2 の `Hiho_Noufu` が
    「変わる」のは最初の観測だからで、中身は 0
    （`first` が `-`）。
    """
    out = probe
    if out.get("shke") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, _ = out["shke"]

    def crc(n, sh):
        return c_out[f"s{sh}_{n}"].split()[1]

    def zero_p(n, sh):
        return c_out[f"s{sh}_{n}"].split()[2] == "-"

    def kawaru(n):
        """種別を 2→3→5→6 と進めて、値が変わった種別の並び。"""
        got, prev = [], None
        for sh in SHUBETU:
            v = crc(n, sh)
            if v != prev:
                got.append(sh)
            prev = v
        return got

    # 4種別とも自分のぶんを入れる
    for n in ("Hiho_Kei", "Hiho_Noufu_P", "Rorei"):
        assert kawaru(n) == [2, 3, 5, 6], f"{n}: {kawaru(n)}"

    # 第1号だけ（種別 3・6 では据え置き）
    for n in ("Fuka_Hiho", "Fuka_Hiho_P", "Hiho_Menjo_P", "Rorei_Kyu",
              "Turo_Kyu", "Gonen", "Shogai_Ippan", "Shogai_20mae",
              "Shogai_Kyu", "Izoku_Otto"):
        assert kawaru(n) == [2, 5], f"{n}: {kawaru(n)}"

    # 第1号男だけ
    for n in ("Izoku_Tuma", "Izoku_Ko", "Kafu", "Kafu_Kyu", "Ichijikin"):
        assert kawaru(n) == [2], f"{n}: {kawaru(n)}"

    # 足元の第1号の納付率・免除率は 0（種別 5 で増えない）
    assert kawaru("Hiho_Noufu") == [2, 3, 6], kawaru("Hiho_Noufu")
    assert zero_p("Hiho_Noufu", 2), "足元の第1号男の納付が 0 でない"
    assert kawaru("Hiho_Menjo") == [2], kawaru("Hiho_Menjo")
    assert zero_p("Hiho_Menjo", 2), "足元の第1号男の免除が 0 でない"

    # 翌年度の率で見たぶんは埋まる（`stat()` が読むのはこちら）
    assert not zero_p("Hiho_Noufu_P", 2), "Hiho_Noufu_P が全部 0"
    assert not zero_p("Hiho_Menjo_P", 2), "Hiho_Menjo_P が全部 0"

    # 死亡一時金は `dtst` が 0 にするだけ（`siml` が埋める）
    assert zero_p("Ichijikin", 2), "死亡一時金が足元で 0 でない"
    assert zero_p("Kafu_Kyu", 2), "旧法寡婦が足元で 0 でない"


@pytest.mark.parametrize("tag", ["", "_op"])
def test_simlの推計が原本と一致(probe, tag):
    """`siml()` → `shke()` を何年か回したあとの配列 38本。

    ③の心臓部。被保険者・待期者を1年進め、障害・遺族・寡婦・
    死亡一時金の新規発生と老齢基礎の新規裁定を出して、全部の
    `*_Nendomatu` を作り直す。`str_op.c` の8つの演算が
    ぜんぶ通る。

    `""` は通常試算を3年（2022〜2024年度）、`_op` は45年化を
    15年（2022〜2036年度）。`_op` を長く回すのは `OPTION_START`
    が 2031年度で、そこまで届かないと `extenda/b/c`
    `Hihokensha2` `Nendomatu_Tyousei_Keisu` が1度も動かないから。
    """
    out = probe
    got = out.get("siml" + tag)
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "siml" + tag)
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for sh in SHUBETU:
        for n in SIML_ARRAYS:
            assert f"s{sh}_{n}" in c_out, f"s{sh}_{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ
    for n in ("Hihokensha", "Taikisha", "Rorei_Nendomatu",
              "Shogai_Ippan_Nendomatu", "Izoku_Tuma_Nendomatu",
              "Kafu_Nendomatu", "Ichijikin_Nendomatu"):
        assert c_out[f"s2_{n}"].split()[2] != "-", f"{n} が全部 0"


def test_simlの45年化の枝が実際に動いている(probe):
    """`_op` でだけ動く配列と、通常試算との違い。

    45年化（`Option` = 1）では 60歳以降の第1号を `Hihokensha2`
    という別の面で追い、65歳でまとめて裁定する（`Rorei_Shinki2`）。
    通常試算ではどちらも**全年度 0 のまま**でなければならない。

    `OPTION_START` = 2031年度から5年かけて 40年 → 45年に伸ばすので、
    15年（2036年度まで）回せば `Nendomatu_Tyousei_Keisu` の
    41/40・42/41・43/42 の枝まで通る。
    """
    out = probe
    if out.get("siml") is None or out.get("siml_op") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_plain, _ = out["siml"]
    c_op, _ = out["siml_op"]

    # 通常試算では 45年化の配列は 0 のまま
    for sh in SHUBETU:
        assert c_plain[f"s{sh}_Hihokensha2"].split()[2] == "-", (
            f"種別 {sh}: 通常試算で Hihokensha2 に値が入っている")
        assert c_plain[f"s{sh}_Rorei_Shinki2"].split()[2] == "-", (
            f"種別 {sh}: 通常試算で Rorei_Shinki2 に値が入っている")

    # 45年化では入る（第1号だけ。第3号は 60歳で脱退する）
    for sh in (2, 5):
        assert c_op[f"s{sh}_Hihokensha2"].split()[2] != "-", (
            f"種別 {sh}: 45年化で Hihokensha2 が 0")

    # 45年化で被保険者と老齢基礎が変わる
    for n in ("Hihokensha", "Rorei_Nendomatu", "Hiho_Kei"):
        assert (c_plain[f"s2_{n}"].split()[1]
                != c_op[f"s2_{n}"].split()[1]), (
            f"{n} が 45年化で変わっていない")


def test_siml_20歳で読む配列の外は全年度0():
    """`siml.c:328-349` の配列外の読みが出力に出ない理由を確かめる。

    ```c
    Hasseisha_Shogai[nenrei - MIN_HIHO_NENREI][kikan]
     = Hihokensha[nendo - 1 - SHONENDO][nenrei - 1 - MIN_HIHO_NENREI][kikan - 1].ninzu
        * Hasseiryoku_Shogai[sotai_nendo][nenrei - MIN_HIHO_NENREI];
    ```

    20歳のとき2番目の添字が **-1**。C の番地計算では

        Hihokensha[y][-1][k]  →  Hihokensha[y - 1][70歳][k]

    を読む。**70歳の被保険者は全年度 0** なので結果は変わらない。
    人が 70歳の面に入る道は3つしか無く、どれも閉じている。

    1. 足元（`dtst`）は 20〜**69歳**しか読まない
    2. `kiso()` が 65歳以上の脱退力を 1 にするので残存が 0
    3. 新規加入は外枠（①被保険者推計）の 70歳のぶんだが、
       これが **4種別とも全年度 0**

    ここでは 1 と 3 を移植版を同じプロセスで動かして直に見て、
    さらに5年ぶん回して `Hihokensha[…][70歳][…]` が 0 のままで
    あることを確かめる。`検証/原本の不具合.md` **B10**。
    """
    if not os.path.exists(os.path.join(NAT, "io_file", "infile.csv")):
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")

    from glva import G
    import cntl as cntl_mod
    import dtst as dtst_mod
    import econ as econ_mod
    import file_open as fo
    import kaizen as kaizen_mod
    import kiso as kiso_mod
    import noufuritu as nou_mod
    import seid as seid_mod
    import shke as shke_mod
    import siml as siml_mod
    import waku as waku_mod
    from setconst import (MAX_HIHO_NENREI, MIN_HIHO_NENREI, MIN_WAKU_NENREI,
                          SUIKEISHONENDO)

    tmp = tempfile.mkdtemp(prefix="nat_b10_")
    try:
        lists = _stage_lists(tmp)
        argv = [None] + lists + ARGV[2:]
        cntl_mod.cntl(G, argv)
        fo.file_open(G, argv[1], G.fp_in, G.infile_name)
        fo.file_open(G, argv[2], G.fp_out, G.outfile_name)
        seid_mod.seid(G)
        econ_mod.econ(G)
        waku_mod.waku(G)
        kaizen_mod.kaizen(G)
        nou_mod.noufuritu(G)

        # (3) 外枠の70歳は 4種別とも全年度 0
        x70 = MAX_HIHO_NENREI - MIN_WAKU_NENREI     # 70歳の列
        for sh in SHUBETU:
            assert not G.Sotowaku[sh, :, x70].any(), (
                f"種別 {sh}: 外枠の70歳に値がある"
                f"（最大 {G.Sotowaku[sh, :, x70].max()}）。"
                "B10 の前提が崩れている")

        i70 = MAX_HIHO_NENREI - MIN_HIHO_NENREI     # 70歳の面
        for sh in SHUBETU:
            dtst_mod.dtst(G, sh)
            # (1) 足元は69歳まで
            assert not _flat_any(G.Hihokensha[SUIKEISHONENDO - 2020,
                                              i70]), (
                f"種別 {sh}: 足元の70歳に値がある")
            kiso_mod.kiso(G, sh)
            shke_mod.shke(G, SUIKEISHONENDO, sh)
            for nendo in range(SUIKEISHONENDO + 1, SUIKEISHONENDO + 6):
                siml_mod.siml(G, nendo, sh)
                shke_mod.shke(G, nendo, sh)
            # (2)(3) 5年回しても 70歳の面は 0
            for nendo in range(SUIKEISHONENDO, SUIKEISHONENDO + 6):
                assert not _flat_any(G.Hihokensha[nendo - 2020, i70]), (
                    f"種別 {sh} {nendo}年度: 70歳の被保険者が 0 でない")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _flat_any(a):
    """構造化配列のバイト列に 0 以外があるか。"""
    import numpy as np
    return bool(np.ascontiguousarray(a).reshape(-1).view(np.float64).any())


def test_statの集計が原本と一致(probe):
    """`stat()` のあとの配列 17本。種別をまたいだ計が正しく積めたか。

    `shke()` が種別・年齢階級ごとに積んだものを

    1. 被保険者・納付・免除を**年度間平均**に直す（年度を降りながら
       前年度の「翌年度の率で見たぶん」と当年度の平均を採る）
    2. `Hanbetu()` で男（添字 7）・女（同 8）の計を作る
    3. `SHUBETU_SUM`（同 0）に全部を足す
    """
    out = probe
    got = out.get("stat")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "stat")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)
    for n in STAT_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
    # 空振りしていないことの確かめ。**`Kafu_Kyu` だけは 0 が正しい**
    # （旧法の寡婦年金は新規裁定が無く、足元の基礎数も 0。`dtst` が
    # 読む13本のファイルに旧法寡婦の行が無い）
    for n in STAT_ARRAYS:
        if n == "Kafu_Kyu":
            assert c_out[n].split()[2] == "-", (
                "旧法寡婦に値が入っている（同梱データでは 0 のはず）")
        else:
            assert c_out[n].split()[2] != "-", f"{n} が全部 0"


def test_statが書く2本のファイルがバイト一致(probe):
    """`stat()` が書く `KISONENKIN`（7.1MB）と `DOKUZI`（23KB）。

    `KISONENKIN` は**④基礎年金の入力**なので、ここが合わないと
    基礎年金拠出金が合わない。`%20.14le` の書式（幅20・指数部2桁）と
    `,` の入れ方、`Rorei_Kyu` と `Turo_Kyu` を足す順まで見る。

    **1行目は食い違う。** `write_BeginData()` が実行時刻を書くので、
    原本は走らせた時刻・移植版は固定した時刻になる（④の
    `KYOSHUTUKIN` と同じ）。2行目から比べる。
    """
    out = probe
    if out.get("stat") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, py_dir = out["_dirs"]["stat"]

    for rel, least in (("KISONENKIN3001-3001-3001", 7000000),
                       ("DOKUZI3001-3001-3001.csv", 20000)):
        cp = os.path.join(c_dir, "data", rel)
        pp = os.path.join(py_dir, "data", rel)
        assert os.path.exists(cp), f"原本が {rel} を書いていない"
        assert os.path.exists(pp), f"移植版が {rel} を書いていない"
        assert os.path.getsize(cp) >= least, f"{rel} が小さすぎる"

        cl = open(cp, "rb").read().splitlines()
        pl = open(pp, "rb").read().splitlines()
        assert len(cl) == len(pl), (
            f"{rel} の行数が違う（C {len(cl)} / Python {len(pl)}）")
        # 1行目は実行時刻なので飛ばす
        for i in range(1, len(cl)):
            assert cl[i] == pl[i], (
                f"{rel} の {i + 1}行目\n"
                f"    C      {cl[i][:200]}\n"
                f"    Python {pl[i][:200]}")


def test_statの旧法遺族の欄は必ず0(probe):
    """`KISONENKIN` の `2,3` の行（旧法遺族）が4欄とも 0 であること。

    ```c
    fprintf( … , "%d,%d,%d,%d,%d,%d," , nendo , 1 , nenrei , 2 , 3 , shubetu - 6 );
    OutputValue = 0.;    …4回
    ```

    ③は旧法の遺族年金を推計しない（該当者がほぼ居ないため）。
    書式を揃えるために欄だけ作って 0 を書いている。
    ④基礎年金がこの欄を読むので、消すと列がずれる。
    """
    out = probe
    if out.get("stat") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, _ = out["_dirs"]["stat"]
    cp = os.path.join(c_dir, "data", "KISONENKIN3001-3001-3001")

    zero = _e_zero()
    n = 0
    with open(cp, encoding="utf-8") as f:
        for line in f:
            fs = line.rstrip("\n").split(",")
            # 年度, 1, 年齢, 2, 3, 男女 の6欄 ＋ 値4欄
            if len(fs) == 10 and fs[1] == "1" and fs[3] == "2" \
                    and fs[4] == "3":
                assert fs[6:] == [zero] * 4, (
                    f"旧法遺族の欄が 0 でない: {line[:120]}")
                n += 1
    # 106年度 × 53歳階級 × 男女
    assert n == 106 * 53 * 2, f"{n} 行（期待 {106 * 53 * 2}）"


def _e_zero():
    """`fprintf( fp , "%20.14le" , 0. )` が書く文字列。"""
    return "%20.14e" % 0.


def test_printoutの年度間への直しが原本と一致(probe):
    """`printout()` のあとの配列 13本。年度末 → 年度間の直し。

    `nendokan()` `nendokan_64()` が前年度末と当年度末を支払遅れ
    2か月ぶんで混ぜる。年度を**降りながら**前年度を読むので、
    若い年度を先に書き換えると値が変わる。

    `stat` 段階と同じ配列名だが**中身は違う**（`printout()` が
    その場で上書きする）ことも見る。
    """
    out = probe
    got = out.get("printout")
    if got is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_out, py_out = got
    bad = _cmp(c_out, py_out, "printout")
    assert not bad, "原本と一致しない:\n  " + "\n  ".join(bad)

    c_stat, _ = out["stat"]
    for n in PRINTOUT_ARRAYS:
        assert n in c_out, f"{n} がハーネスの出力に無い"
        if n == "Kafu_Kyu":
            continue                    # 旧法寡婦は同梱データでは 0
        assert c_out[n].split()[2] != "-", f"{n} が全部 0"
        assert c_out[n].split()[1] != c_stat[n].split()[1], (
            f"{n} が `printout()` の前後で変わっていない"
            "（年度間への直しが効いていない）")


def test_printoutが書く5本のファイルがバイト一致(probe):
    """`printout()` が書く参考出力5本（合わせて 7.9MB）。

    `%f`（小数6桁）の書式、`sum` の足す順、見出しの文字まで見る。
    **見出しの区切りは旧法障害だけ空白1つ**で、ほかは2つ
    （実際にここで1回踏んだ）。

    `write_BeginData()` を通さないので**1行目から比べられる**。
    """
    out = probe
    if out.get("printout") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, py_dir = out["_dirs"]["printout"]

    names = ("HIHO3001-3001-3001.csv", "ROREI3001-3001-3001.csv",
             "ROREI_SHINKI3001-3001-3001.csv",
             "SHOGAI3001-3001-3001.csv", "IZOKU3001-3001-3001.csv")
    for rel in names:
        cp = os.path.join(c_dir, "rslt", rel)
        pp = os.path.join(py_dir, "rslt", rel)
        assert os.path.exists(cp), f"原本が {rel} を書いていない"
        assert os.path.exists(pp), f"移植版が {rel} を書いていない"
        cb = open(cp, "rb").read()
        pb = open(pp, "rb").read()
        if cb != pb:
            cl = cb.decode("utf-8", "replace").splitlines()
            pl = pb.decode("utf-8", "replace").splitlines()
            for i, (x, y) in enumerate(zip(cl, pl), 1):
                assert x == y, (f"{rel} の {i}行目\n    C      {x[:200]}\n"
                                f"    Python {y[:200]}")
            raise AssertionError(
                f"{rel} の行数が違う（C {len(cl)} / Python {len(pl)}）")
    # 空振りしていないことの確かめ
    total = sum(os.path.getsize(os.path.join(c_dir, "rslt", r))
                for r in names)
    assert total > 7000000, f"出力が小さすぎる（{total} バイト）"


def test_printoutの満額の表は全列が67歳以下の値になる(probe):
    """`Full_Pension[年度][nenrei - UNDER_67]` の添字ずれ（J4）。

    見出しは「67歳以下,68歳,…,115歳」の 50列だが、書くのは
    `Full_Pension[年度][0..48]`。`Full_Pension` の2番目の添字は
    `econ.c` が**生の年齢**（0〜115）で埋めているので、0〜48 は
    どれも「67歳以下」と同じ値になる。

    つまり**表が約束している年齢別の内訳が1つも出ていない**。
    原本の出力そのものでそれを確かめる。
    """
    out = probe
    if out.get("printout") is None:
        pytest.skip("③の入力が無い（run_pipeline.sh を1回通すこと）")
    c_dir, _ = out["_dirs"]["printout"]
    cp = os.path.join(c_dir, "rslt", "ROREI3001-3001-3001.csv")

    found = 0
    with open(cp, encoding="utf-8") as f:
        in_table = False
        for line in f:
            if line.startswith("基礎年金満額"):
                in_table = True
                continue
            if in_table and line.startswith("年度,67歳以下,"):
                cols = line.rstrip("\n").split(",")
                assert len(cols) == 50, f"見出しが 50列でない（{len(cols)}）"
                assert cols[1] == "67歳以下" and cols[2] == "68歳"
                assert cols[-1] == "115歳"
                continue
            if in_table and line[:4].isdigit():
                fs = line.rstrip("\n").split(",")
                if len(fs) != 50:
                    in_table = False
                    continue
                assert len(set(fs[1:])) == 1, (
                    "年齢別に値が違う（J4 が直っている？）:\n  "
                    + line[:200])
                found += 1
            elif in_table:
                in_table = False
    # 3つの表 × 106年度
    assert found == 3 * 106, f"{found} 行（期待 {3 * 106}）"


def test_CRC32の並びがCの構造体と同じであること():
    """NumPy の構造化 dtype のバイト列が C の構造体と同じ並びか。

    ハーネスは構造体の先頭から `double` を順に食わせる。NumPy の
    構造化 dtype も宣言した順に詰むので、詰め物が無ければ一致する
    （上の `test_structの寸法に詰め物が無い` が前提）。
    小さな例で確かめる。
    """
    import numpy as np
    dt = np.dtype([("a", "f8"), ("b", "f8", (2, 2)), ("c", "f8")])
    x = np.zeros((), dtype=dt)
    x["a"] = 1.0
    x["b"] = np.array([[2.0, 3.0], [4.0, 5.0]])
    x["c"] = 6.0
    want = np.array([1., 2., 3., 4., 5., 6.])
    assert zlib.crc32(np.asarray(x).tobytes()) == zlib.crc32(want.tobytes())
