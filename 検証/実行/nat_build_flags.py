#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原本③国民年金をコンパイル指定を変えて建て、出力の差の大きさを測る
=====================================================================
同じ原本 C を

    -O2                 同梱 Makefile の release と同じ（FMA 命令は出ない）
    -O2 -mfma           FMA（積和融合）命令を使わせる
    -O2 -march=native   このCPUの命令を全部使わせる（FMA を含む）
    -Ofast              演算順の書き換えを許す（`検証/原本の不具合.md` G1・G2）

の4通りで建てて、同じ入力で 105年度（2021〜2125年度）走らせ、
出力11本のうち数値を含む10本を `-O2` の出力と欄ごとに比べる。

何のためか
----------
厚労科研の報告書（川出他 2026、`検証/先行研究との比較.md`）は、国民年金
（nat）の Python 版と参照データの最大 2.36% の差を「C の FMA 命令と
Python の IEEE 754 厳格評価の差が 100 年分の漸化式で累積したもの」と
説明している。FMA で本当にその大きさの差が出るのかを、原本そのもので測る。

必要なもの
----------
- `検証/実行/run_pipeline.sh` を1回通してあること（`/tmp/nenkin-build` に
  UTF-8 変換済みの原本、`work/suuri/rev2024/nat/io_file/` に入力）
- g++、objdump（binutils）、numpy

使い方
------
    python3 検証/実行/nat_build_flags.py

`検証/移植/test_nat_stage.py` の仕掛け（`harness_nat.cpp`、出力先だけを
一時ディレクトリへ向けたファイルリスト）をそのまま使う。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.join(os.path.dirname(HERE), "移植")
sys.path.insert(0, PORT)
os.chdir(PORT)
from portpath import select  # noqa: E402
select("clib", "nat")
from test_nat_stage import ARGV, SRC, _SRCS, _stage_lists  # noqa: E402

FLAGS = (
    ("-O2",),
    ("-O2", "-mfma"),
    ("-O2", "-march=native"),
    ("-Ofast",),
)
# 数値を含む10本（`KOKUKAITE-AK3001E.csv` は空）
FILES = (
    "rslt/HIHO3001-3001-3001.csv", "rslt/IZOKU3001-3001-3001.csv",
    "rslt/ROREI3001-3001-3001.csv", "rslt/ROREI_SHINKI3001-3001-3001.csv",
    "rslt/SHOGAI3001-3001-3001.csv", "data/DOKUZI3001-3001-3001.csv",
    "data/KISONENKIN3001-3001-3001", "data/KOKUKAITE-3001-3001E.csv",
    "data/PENSION_3001-3001-3001.csv", "data/nat_wariai3001-3001.csv",
)
# 1行目に実行時刻が入る2本は2行目から比べる
TIMESTAMPED = ("KISONENKIN3001-3001-3001", "DOKUZI3001-3001-3001.csv")
NUM = re.compile(rb"-?\d+\.?\d*(?:[eE][-+]?\d+)?")
FMA_INSN = re.compile(r"\bvfn?m(add|sub)\d{3}[sp]d\b")


def build_and_run(bsrc, flags, root, env):
    exe = os.path.join(bsrc, "h_" + "_".join(f.strip("-") for f in flags))
    r = subprocess.run(["g++", *flags, "-w", "-o", exe, "harness_nat.cpp",
                        *_SRCS], cwd=bsrc, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ビルドに失敗（%s）:\n%s" % (" ".join(flags), r.stderr[:2000]))
    dis = subprocess.run(["objdump", "-d", exe], capture_output=True,
                         text=True).stdout
    nfma = len(FMA_INSN.findall(dis))
    lists = _stage_lists(root)
    t0 = time.time()
    r = subprocess.run([exe, "printout", *lists, *ARGV[2:]], cwd=bsrc,
                       capture_output=True, env=env, timeout=3600)
    if r.returncode != 0:
        sys.exit("実行に失敗（%s）:\n%s" % (" ".join(flags), r.stderr[:2000]))
    return nfma, time.time() - t0


def cells(path):
    b = open(path, "rb").read()
    if os.path.basename(path) in TIMESTAMPED:
        b = b.split(b"\n", 1)[1]
    return b, np.array([float(x) for x in NUM.findall(b)])


def main():
    if not os.path.isdir(SRC):
        sys.exit("UTF-8 に変換した原本が無い（%s）。run_pipeline.sh を1回通すこと" % SRC)
    tmp = tempfile.mkdtemp(prefix="nat_flags_")
    bsrc = os.path.join(tmp, "build")
    os.mkdir(bsrc)
    for f in os.listdir(SRC):
        if f.endswith(".h") or (f.endswith(".c") and f != "main.c"):
            shutil.copyfile(os.path.join(SRC, f), os.path.join(bsrc, f))
    shutil.copyfile(os.path.join(PORT, "harness_nat.cpp"),
                    os.path.join(bsrc, "harness_nat.cpp"))
    env = dict(os.environ)
    env["SIML_YEARS"] = "104"          # 2021年度 + 104 = 2125年度まで

    roots = {}
    print("| コンパイル指定 | FMA 命令の数 | 実行時間 |")
    print("|---|---:|---:|")
    for flags in FLAGS:
        root = os.path.join(tmp, "_".join(f.strip("-") for f in flags))
        nfma, t = build_and_run(bsrc, flags, root, env)
        print("| `%s` | %d | %.1fs |" % (" ".join(flags), nfma, t))
        roots[flags] = root

    base = roots[FLAGS[0]]
    print()
    print("| 比較（`-O2` と） | ファイル | 欄の数 | 違う欄 | 最大相対差 | 最大絶対差 |")
    print("|---|---|---:|---:|---:|---:|")
    for flags in FLAGS[1:]:
        tag = " ".join(flags)
        tot = ndiff = 0
        mrel = mabs = 0.
        for rel in FILES:
            b0, a = cells(os.path.join(base, rel))
            b1, b = cells(os.path.join(roots[flags], rel))
            tot += a.size
            if b0 == b1:
                continue
            assert a.size == b.size, rel
            den = np.maximum(np.abs(a), np.abs(b))
            relv = np.where(den > 0, np.abs(a - b) / np.where(den > 0, den, 1), 0.)
            n = int((a != b).sum())
            print("| `%s` | `%s` | %d | %d | %.1e | %.1e |"
                  % (tag, os.path.basename(rel), a.size, n, relv.max(),
                     np.abs(a - b).max()))
            ndiff += n
            mrel = max(mrel, float(relv.max()))
            mabs = max(mabs, float(np.abs(a - b).max()))
        print("| `%s` | **合計** | %d | %d | %.1e | %.1e |"
              % (tag, tot, ndiff, mrel, mabs))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
