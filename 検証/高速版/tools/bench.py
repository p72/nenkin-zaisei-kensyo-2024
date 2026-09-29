#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段階別と通しの時間・ピーク RSS を測る
========================================
    python3 検証/高速版/tools/bench.py [--case 3001] [--option kozax] [--roudr 1] [--repeat 1]

`pipeline.run` を回して `timings`（段階ごとの `perf_counter` の秒。CSV を書く時間は `*_csv`）と
`resource.getrusage` の ru_maxrss を取る。結果は `検証/高速版/結果/bench_<case>[_<tag>].json`。
原本と移植版の参照時間は `REFERENCE`（`検証/実行/README.md`・`検証/移植/README.md` の実測）。
"""
import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
KENSHO = os.path.dirname(FAST)
sys.path.insert(0, FAST)
sys.path.insert(0, KENSHO)

import suuri_env                                   # noqa: E402
from kosoku.kernels import jit                     # noqa: E402
from kosoku import pipeline                        # noqa: E402
from kosoku.policy import load_policy              # noqa: E402

REFERENCE = {
    # 秒。原本 C（-O2、ケース 3001、この作業環境）は 検証/実行/README.md と lever_out の log、
    # 移植版は 検証/移植/README.md の実測（②は 27× 原本、③ 36×）
    "original_c": {"total": 93.0, "s1": 1.0, "s2": 83.0, "s3": 2.0, "s4": 1.0, "s5": 7.0},
    "port": {"s1": 10.0, "s2": 2200.0, "s3": 70.0, "s4": 5.0, "s5": 100.0},
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="段階別と通しの時間・RSS")
    ap.add_argument("--case", default="3001")
    ap.add_argument("--option", action="append", default=[])
    ap.add_argument("--jin", type=int, default=1)
    ap.add_argument("--qx", type=int, default=1)
    ap.add_argument("--nc", type=int, default=0)
    ap.add_argument("--roudr", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=1, help="回数（最小の秒を採る）")
    ap.add_argument("--out", default=os.path.join(FAST, "結果"))
    a = ap.parse_args(argv)
    pol = load_policy(*a.option)
    tag = pipeline.options_of(pol).tag
    print("numba: %s" % ("あり" if jit.ENABLED else "なし（恒等デコレータ）"))
    best, rss = None, 0.
    for i in range(a.repeat):
        out = tempfile.mkdtemp(prefix="kosoku-bench-")
        t0 = time.perf_counter()
        res = pipeline.run(a.case, pol, suuri_env.suuri(), out, jin=a.jin, qx=a.qx, nc=a.nc, roudr=a.roudr)
        wall = time.perf_counter() - t0
        rss = max(rss, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.)
        T = dict(res["timings"]); T["wall"] = wall
        shutil.rmtree(out, ignore_errors=True)
        if best is None or T["wall"] < best["wall"]:
            best = T
        print("  %d 回目: 通し %.1f 秒（① %.1f ② %.1f ③ %.1f ④ %.1f ⑤ %.1f、CSV %.1f）" % (
            i + 1, wall, T.get("s1", 0), T.get("s2", 0), T.get("s3", 0), T.get("s4", 0) + T.get("s4_read", 0),
            T.get("s5", 0) + T.get("s5_read", 0), sum(v for k, v in T.items() if k.endswith("_csv"))))
    result = {"case": a.case, "options": tag, "numba": jit.ENABLED, "repeat": a.repeat,
              "timings": {k: round(v, 3) for k, v in best.items()}, "peak_rss_mb": round(rss, 1),
              "reference": REFERENCE}
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, "bench_%s%s.json" % (a.case, "" if tag == "base" else "_" + tag))
    with open(p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=1)
    print("ピーク RSS %.0f MB → %s" % (rss, p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
