# -*- coding: utf-8 -*-
"""移植版②を段階まで走らせて配列を npz に落とす — 高速版②の受け入れ用
=====================================================================
`検証/移植/emp_kyufu` を**読み取り専用**で import し、出力先だけ別の木
（`SUURI_PREFIX`）に向けて走らせる。`work/` の②の出力は上書きしない。

    python3 tools/kyufu_port_probe.py OUTDIR [--pseid 0] [--years 2] [--case 3001]

OUTDIR に
    setup.npz     econ / seid / krgn / waku のあとの配列
    s{1,2,3}.npz  種別ごとに kiso → dtst → shke(KIJUN) → siml×years → shke のあとの配列
    ...          （各段階の主要配列を `dtst_g` のように段階名を前置して持つ）
を書く。移植版は1年度あたり数十秒かかる。
"""
import argparse
import contextlib
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
KENSHO = os.path.dirname(FAST)
REPO = os.path.dirname(KENSHO)
PORT = os.path.join(KENSHO, "移植")
sys.path.insert(0, PORT)
sys.path.insert(0, KENSHO)
import suuri_env                                            # noqa: E402

_OUT_DIRS = ["emp/rslt/u-rev/shus", "emp/rslt/u-rev/shusg", "emp/rslt/u-rev/kiso",
             "emp/rslt/u-rev/kisor", "emp/rslt/u-rev/hou", "emp/rslt/u-rev/kaite",
             "emp/rslt/u-rev/hikaku", "emp/rslt/u-rev/ashimoto", "emp/rslt/u-rev/bunpu",
             "emp/rslt/u-rev/prt"]

SETUP_ARRAYS = ("pop", "l", "lpt", "lpt1", "ri", "h", "ci0", "dir", "jz_shk", "hh", "ci", "hdum",
                "ci2", "hp2", "ad", "ad2", "bd", "pre", "pres", "flt", "adt", "sadt", "cadt",
                "wife", "can", "can2", "ha", "hb", "ema", "emb", "ee", "rs", "sik", "sikr", "nos",
                "routsu", "qp", "br", "bn", "bnpt", "dmpt2", "partbbn", "riss", "rigd", "rigk",
                "rigbe", "kflcan")
SETUP_SCALARS = ("pra", "prb", "pras", "prbs", "fl", "fl1", "minb", "wif", "senll", "srv",
                 "hh2_1999", "hh2_2000", "hh2_2001")
KISO_ARRAYS = ("q", "u", "rt", "yx", "ns", "rc", "cl", "cl2", "kd", "ikucoe", "jiiku")
DTST_ARRAYS = ("g", "ge", "gpt", "bb", "bbpt", "z", "ze", "w", "we", "gd", "r", "f", "f_min",
               "f_hik", "hn", "pshn", "rsen", "hnsen", "pshnsen", "fsen", "fsenmin", "fsenhik")
SHKE_ARRAYS = ("t4", "t4k", "t6", "t6k", "hn2", "hn2k", "ap", "apdum", "ap65", "ap70", "ap75",
               "appart", "a", "adum", "aiku", "a60", "a65", "a70", "a75", "apart", "aikupart",
               "a60part", "a65part", "a70part", "okisor", "okiso2x", "dk3x", "d3")
SIML_ARRAYS = ("g", "ge", "gpt", "gz", "gn", "gez", "gnn", "ye", "y", "ypt", "q2", "bb", "bbnp",
               "bbpt", "z", "ze", "w", "we", "chwd", "gd", "r", "rn", "hn", "hnn", "f", "fn",
               "f_hik", "f_min", "fnhik", "fnmin", "rsen", "fsen", "fsenhik", "fsenmin", "rsenn",
               "fsenn", "hnsen", "rhantei", "fhantei", "fpart", "l", "lpt")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--pseid", type=int, default=0)
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--case", default="3001")
    ap.add_argument("--stdin", default="4\n0\n0\n0\n0\n0\n")
    a = ap.parse_args(argv)
    os.makedirs(a.outdir, exist_ok=True)

    # 出力先の木（入力は symlink）
    tree = os.path.join(os.path.abspath(a.outdir), "tree")
    base = os.path.join(tree, "suuri", "rev2024")
    S = suuri_env.suuri()
    for d in _OUT_DIRS:
        os.makedirs(os.path.join(base, d), exist_ok=True)
    os.makedirs(os.path.join(base, "emp"), exist_ok=True)
    for src, dst in ((os.path.join(S, "emp", "data"), os.path.join(base, "emp", "data")),
                     (os.path.join(S, "wakuc"), os.path.join(base, "wakuc"))):
        if not os.path.lexists(dst):
            os.symlink(src, dst)
    os.environ["SUURI_PREFIX"] = tree

    from portpath import select
    select("clib", "emp_kyufu")
    from cinstream import Cin
    from glva import G
    import glva, cntl, fileio, flck, waku, econ, seid, krgn, kiso, dtst, shke, siml   # noqa: E401
    from setconst import KIJUN

    cin = Cin("11\n%s\n%s\n%s\n%s" % (a.case, a.case, a.case, a.stdin))
    with contextlib.redirect_stdout(io.StringIO()):
        G.key = cin.int_(); G.iname = cin.int_(); G.iecon = cin.int_(); G.iwname = cin.int_()
        G.seidver = 1
        glva.zero_init()
        cntl.cntl(cin)
        G.pseid = a.pseid
        G.konen = 1 if a.pseid == 0 else 0
        glva.zero_sepsd()
        fileio.fopn()
        flck.flck()
        waku.waku()
        econ.econ()
        seid.seid()
        krgn.krgn()
    d = {n: np.array(getattr(G, n)) for n in SETUP_ARRAYS}
    d.update({n: np.array(float(getattr(G, n))) for n in SETUP_SCALARS})
    np.savez_compressed(os.path.join(a.outdir, "setup.npz"), **d)
    print("setup done", flush=True)

    for s in range(1, 4):
        if a.pseid != 0 and s >= 3:
            break
        G.s = s
        G.s2 = s
        d = {}
        with contextlib.redirect_stdout(io.StringIO()):
            kiso.kiso()
        d.update({"kiso_" + n: np.array(getattr(G, n)) for n in KISO_ARRAYS})
        G.k = KIJUN
        G.xend = 90 if a.pseid == 0 else 75
        G.tend = G.xend - 15
        with contextlib.redirect_stdout(io.StringIO()):
            dtst.dtst()
        d.update({"dtst_" + n: np.array(getattr(G, n)) for n in DTST_ARRAYS})
        with contextlib.redirect_stdout(io.StringIO()):
            shke.shke()
        d.update({"shke0_" + n: np.array(getattr(G, n)) for n in SHKE_ARRAYS})
        d["shke0_d3x"] = np.array(G.d3x[KIJUN])
        d["shke0_d3xs"] = np.array(G.d3xs[KIJUN])
        print("s=%d dtst/shke done" % s, flush=True)
        for kk in range(KIJUN + 1, KIJUN + a.years + 1):
            G.k = kk
            with contextlib.redirect_stdout(io.StringIO()):
                siml.siml()
            d.update({"siml%d_%s" % (kk, n): np.array(getattr(G, n)) for n in SIML_ARRAYS})
            with contextlib.redirect_stdout(io.StringIO()):
                shke.shke()
            d.update({"shke%d_%s" % (kk, n): np.array(getattr(G, n)) for n in SHKE_ARRAYS})
            d["shke%d_d3x" % kk] = np.array(G.d3x[kk])
            d["shke%d_d3xs" % kk] = np.array(G.d3xs[kk])
            print("s=%d k=%d done" % (s, kk), flush=True)
        np.savez_compressed(os.path.join(a.outdir, "s%d.npz" % s), **d)
    fileio.fcls()


if __name__ == "__main__":
    main()
