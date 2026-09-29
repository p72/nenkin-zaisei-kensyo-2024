# -*- coding: utf-8 -*-
"""癖（B11・J3）を直した移植版③を別の木で走らせる — 高速版の受け入れ用
=========================================================================
高速版③は台帳の癖を**意図どおり**に直しているので、移植版の出力とは遺族基礎（B11）と
年度間受給者数の老齢（J3）で必ず違う。その2か所も 1e-6 で突き合わせるために、
移植版 `nat/` の写しを作り、2行だけ直して走らせる（`検証/移植/` には触らない）。

    B11  siml.py   `_c_at(G.q, yq, nenrei, seibetu)` → `G.q[yq, nenrei, seibetu - 1]`
    J3   shke.py   `Waribikiritu[seibetu, 0, jukyu_nenrei - 66, 1]` → `[..., 9]`

    python3 tools/nat_port_fixed.py OUTDIR [--case 3001]

`OUTDIR/data/KISONENKIN…` ができる。`KOSOKU_NAT_PORTFIX=OUTDIR` を置くと
`tests/test_s3_nat.py` が全項目を 1e-6 で比べる。移植版③は1ケース 2〜3分。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
PORT = os.path.normpath(os.path.join(FAST, "..", "移植"))
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

PATCHES = (
    ("nat/siml.py", "_c_at(G.q, yq, nenrei, seibetu)", "G.q[yq, nenrei, seibetu - 1]"),
    ("nat/shke.py", "*= G.Waribikiritu[seibetu, 0, jukyu_nenrei - 66, 1]",
     "*= G.Waribikiritu[seibetu, 0, jukyu_nenrei - 66, 9]"),
)
ASCTIME = "Thu Jan  1 00:00:00 1970\\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--case", default="3001")
    ap.add_argument("--birth", default="0", help="出生 0 中位 / 1 高位 / 2 低位")
    ap.add_argument("--death", default="M", help="死亡 M 中位 / H 高位 / L 低位")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.outdir)
    nat_src = os.path.join(PORT, "nat")
    nat_dst = os.path.join(root, "nat")
    if os.path.isdir(nat_dst):
        shutil.rmtree(nat_dst)
    shutil.copytree(nat_src, nat_dst, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, old, new in PATCHES:
        p = os.path.join(root, rel)
        s = open(p, encoding="utf-8").read()
        if s.count(old) != 1:
            raise SystemExit("%s: 直す行が1つでない（%d）" % (rel, s.count(old)))
        open(p, "w", encoding="utf-8").write(s.replace(old, new))
    for d in ("rslt", "data", "io_file"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    NAT = suuri_env.suuri("nat")
    lists = []
    for name in ("infile.csv", "outfile.csv"):
        b = open(os.path.join(NAT, "io_file", name), "rb").read()
        for sub in (b"/rslt", b"/data"):
            b = b.replace(NAT.encode() + sub, root.encode() + sub)
        dst = os.path.join(root, "io_file", name)
        open(dst, "wb").write(b)
        lists.append(dst)
    runner = os.path.join(root, "run_main.py")
    open(runner, "w", encoding="utf-8").write(
        "import sys\nsys.path.insert(0, %r)\nsys.path.insert(0, %r)\n"
        "import main as nat_main\n"
        "nat_main.main([None] + sys.argv[1:], asctime=\"%s\", echo=False)\n"
        % (os.path.join(PORT, "clib"), nat_dst, ASCTIME))
    c = a.case
    argv = [sys.executable, runner] + lists + [c, c, c, a.birth, a.death, "0", "1", "0", "2027",
                                               "0", "2031", "3", c]
    t0 = time.time()
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit("移植版が異常終了")
    print("done %.0fs → %s" % (time.time() - t0, os.path.join(root, "data")))


if __name__ == "__main__":
    main()
