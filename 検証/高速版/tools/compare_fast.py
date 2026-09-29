#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高速版の出力を公表値（詳細結果等の財政見通し Excel）か移植版の出力と突き合わせる
==================================================================================
    python3 検証/高速版/tools/compare_fast.py --against published <高速版の出力dir> --published <xlsx> [--case 3001]
    python3 検証/高速版/tools/compare_fast.py --against port <高速版の出力dir> [--case 3001] [--port-dir DIR]

`<高速版の出力dir>` は `pipeline.run(..., out_dir)` / `python -m kosoku run --dump-port-csv` が書いた場所
（`emp/shushi/01shushi…` `emp/shushi/03summary…` `bas/rslt/kekka…` を持つ）。読み手は
`検証/オプション試算/compare_option.py` を流用する（公表値）。移植版との比較は `01shushi`（30 列 × 5 制度）
と `03summary` の最終所得代替率・終了年度。

判定（`計画.md` の受け入れ）: 最終所得代替率 ±0.5 %pt、財政見通しの欄は相対 1e-3（終了年度 ±1 年の帯は
1e-2、1 億円未満の欄は見ない）。全ケースをまとめて回すのは `tools/run_cases.py`。
"""
import argparse
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
KENSHO = os.path.dirname(FAST)
sys.path.insert(0, FAST)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KENSHO, "オプション試算"))
sys.path.insert(0, KENSHO)

import compare_option as CO      # noqa: E402  読み手の流用
import suuri_env                 # noqa: E402

from kosoku.axis import YEARS    # noqa: E402

__all__ = ["compare_series", "SeriesResult", "against_published", "against_port"]


class SeriesResult(object):
    """1系列の比較結果。`ok` は許容内か。"""

    def __init__(self, name, n, n_bad, max_rel, max_abs, worst_year, rtol, atol):
        self.name, self.n, self.n_bad = name, n, n_bad
        self.max_rel, self.max_abs, self.worst_year = max_rel, max_abs, worst_year
        self.rtol, self.atol = rtol, atol

    @property
    def ok(self):
        return self.n_bad == 0

    def row(self):
        return "| %s | %d | %d | %.2e | %.2e | %s | %s |" % (
            self.name, self.n, self.n_bad, self.max_rel, self.max_abs,
            self.worst_year if self.worst_year is not None else "—",
            "OK" if self.ok else "**NG**")


def compare_series(name, fast, port, rtol, atol=0., years=None):
    """年度の配列 `fast` と `port`（どちらも YEARS の軸、または {西暦: 値}）を比べる。

    `years` は比べる年度の範囲 (first, last)。許容は
    `|fast − port| <= atol + rtol × |port|`。
    """
    if isinstance(fast, dict):
        ys = sorted(set(fast) & set(port))
        f = np.array([fast[y] for y in ys], dtype=np.float64)
        p = np.array([port[y] for y in ys], dtype=np.float64)
        labels = np.array(ys)
    else:
        f, p = np.asarray(fast, dtype=np.float64), np.asarray(port, dtype=np.float64)
        labels = YEARS.labels()
        if years is not None:
            sl = YEARS.s(*years)
            f, p, labels = f[sl], p[sl], labels[sl]
    diff = np.abs(f - p)
    tol = atol + rtol * np.abs(p)
    bad = diff > tol
    den = np.where(np.abs(p) > 0, np.abs(p), 1.)
    rel = np.where(np.abs(p) > 0, diff / den, np.where(diff > 0, np.inf, 0.))
    worst = int(labels[int(np.argmax(diff))]) if diff.size else None
    return SeriesResult(name, int(f.size), int(bad.sum()),
                        float(rel.max()) if rel.size else 0.,
                        float(diff.max()) if diff.size else 0., worst, rtol, atol)


def table(results):
    out = ["| 系列 | 項目 | 許容超過 | 最大相対差 | 最大絶対差 | 最悪の年度 | 判定 |",
           "|---|---:|---:|---:|---:|---|---|"]
    out.extend(r.row() for r in results)
    return "\n".join(out)


def _read_fast(fast_dir, case, yobi="000"):
    ver = "%s-%s-%s-%s" % ((case,) * 4)
    shushi, bas = os.path.join(fast_dir, "emp", "shushi"), os.path.join(fast_dir, "bas", "rslt")
    return ver, shushi, bas


def against_published(fast_dir, case, xlsx, yobi="000"):
    """公表の Excel と突き合わせ、(見出しの結果, 公表の終了年度, {sheet: {label: stats}}) を返す。"""
    from run_cases import compare_published
    ver, shushi, bas = _read_fast(fast_dir, case, yobi)
    pub = CO.read_published(xlsx)
    emp = CO.read_emp(ver, yobi, shushi)
    nat = CO.read_nat(ver, yobi, bas)
    rate = CO.read_rate(ver, yobi, shushi)
    kakaku = CO.read_kakaku(ver, yobi, bas)
    X = {}
    if pub["layout"] == "一元化":
        raise SystemExit("一元化レイアウト（調整期間の一致）は run_cases.py で（④の run から国年の独自給付を取る）")
    got = CO.build(pub["layout"], emp, nat, rate, X, kakaku)
    ps = CO.read_rate(ver, yobi, shushi)
    fin = ps[max(ps)]
    kend = {}
    return compare_published(pub, got, rate, kend), pub, fin


def against_port(fast_dir, case, port_dir, yobi="000"):
    """移植版（原本）の `01shushi` と `03summary` と突き合わせる。"""
    from kosoku.stages.s5_emp_shushi.output import read_summary, read_shushi, TITLE_BEFORE, TITLE_AFTER, COLS_SHUSHI
    ver = "%s-%s-%s-%s-1120" % ((case,) * 4)
    results = []
    for sysn in ("tou", "kou", "kok", "ren", "sig"):
        mp = os.path.join(fast_dir, "emp", "shushi", "01shushi.%s-%se_08%s.csv" % (ver, yobi, sysn))
        pp = os.path.join(port_dir, "emp", "rslt", "ez_arev", "shushi", "01shushi.%s-%se_08%s.csv" % (ver, yobi, sysn))
        if not (os.path.exists(mp) and os.path.exists(pp)):
            continue
        mine, port = read_shushi(mp), read_shushi(pp)
        for title in (TITLE_BEFORE, TITLE_AFTER):
            for i, col in enumerate(COLS_SHUSHI):
                f = {y: v[i] for y, v in mine[title].items() if abs(port[title][y][i]) >= 1.}
                p = {y: v[i] for y, v in port[title].items() if abs(v[i]) >= 1.}
                if p:
                    results.append(compare_series("%s %s %s" % (sysn, title[-7:], col), f, p, 1e-3))
    mp = os.path.join(fast_dir, "emp", "shushi", "03summary.%s-%s_08sum.csv" % (ver, yobi))
    pp = os.path.join(port_dir, "emp", "rslt", "ez_arev", "shushi", "03summary.%s-%s_08sum.csv" % (ver, yobi))
    head = None
    if os.path.exists(mp) and os.path.exists(pp):
        m, p = read_summary(mp), read_summary(pp)
        lm, lp = max(m["table"]), max(p["table"])
        head = {k: (m["table"][lm][k], p["table"][lp][k]) for k in ("所得代替率", "所得代替率(比例)", "所得代替率(基礎)")}
        head["kend"] = (m["kend"], p["kend"])
    return results, head


def main(argv=None):
    ap = argparse.ArgumentParser(description="高速版の出力を移植版／公表値と突き合わせる")
    ap.add_argument("fast_dir", help="高速版が `to_port_csv()` で書いた出力")
    ap.add_argument("--against", choices=("port", "published"), default="port")
    ap.add_argument("--case", default="3001")
    ap.add_argument("--published", default=None, help="公表 xlsx のパス（--against published）")
    ap.add_argument("--port-dir", default=None,
                    help="移植版（原本）の実行領域。既定は suuri_env.suuri()")
    a = ap.parse_args(argv)
    print("高速版: %s" % a.fast_dir)
    if a.against == "published":
        if not a.published:
            raise SystemExit("--published <xlsx> が要る")
        (head, pub_end, sheets), pub, fin = against_published(a.fast_dir, a.case, a.published)
        print("比較先: %s（%s）" % (os.path.basename(a.published), pub["layout"]))
        for k, v in head.items():
            print("  所得代替率 %s: 高速版 %.6f  公表 %.6f  差 %+.4f pt  %s" % (k, v["fast"], v["pub"], v["diff_pt"], "OK" if v["ok"] else "NG"))
        n = nb = 0
        for sn, st in sheets.items():
            for label, s in st.items():
                n += s["n"]; nb += s["n_bad"]
                if s["n_bad"]:
                    print("  %s/%s: %d/%d 許容超過（最大 %.2e @%s）" % (sn, label, s["n_bad"], s["n"], s["worst"], s["worst_year"]))
        print("  照合 %d 項目、許容超過 %d" % (n, nb))
        return 0 if nb == 0 and all(v["ok"] for v in head.values()) else 1
    port_dir = a.port_dir or suuri_env.suuri()
    print("比較先: 移植版 %s" % port_dir)
    results, head = against_port(a.fast_dir, a.case, port_dir)
    if head:
        for k in ("所得代替率", "所得代替率(比例)", "所得代替率(基礎)"):
            print("  %s: 高速版 %.6f  移植版 %.6f" % (k, head[k][0], head[k][1]))
        print("  終了年度: 高速版 %s  移植版 %s" % head["kend"])
    bad = [r for r in results if not r.ok]
    print("  01shushi: %d 系列、許容超過 %d 系列" % (len(results), len(bad)))
    if bad:
        print(table(bad[:20]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
