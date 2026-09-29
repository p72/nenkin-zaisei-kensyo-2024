#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""フェーズ G: 通しの実行と公表値（詳細結果等1・2）との照合
==========================================================
    python3 検証/高速版/tools/run_cases.py [--only 3001,tougou] [--out-dir DIR] [--keep]

8 つの経済ケース（3001〜3004・3201〜3204）と、移植版が公表値と照合した 11 のレバーケース
（`検証/オプション試算/README.md` の表）を高速版①〜⑤で回し、公表の財政見通し Excel と
突き合わせる。読み手は `検証/オプション試算/compare_option.py` を流用する。

結果は `検証/高速版/結果/通し.md`（表）と `結果/通し/<name>.json`（明細・段階ごとの秒）。
出力 CSV（1 ケース約 400MB）は `--out-dir`（既定は一時ディレクトリ）に書き、照合が済んだら消す
（`--keep` で残す）。

許容（`計画.md` の受け入れ基準）: 最終所得代替率 ±0.5 %pt、終了年度 ±1 年、財政見通しの各欄は
相対 1e-3（終了年度 ±1 年の帯は 1e-2）、1 億円未満の欄は見ない。
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
KENSHO = os.path.dirname(FAST)
ROOT = os.path.dirname(KENSHO)
sys.path.insert(0, FAST)
sys.path.insert(0, os.path.join(KENSHO, "オプション試算"))
sys.path.insert(0, KENSHO)

import compare_option as CO                                  # noqa: E402
import suuri_env                                             # noqa: E402
from kosoku import pipeline                                  # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.stages.s5_emp_shushi.inputs import kokusyushi_from_kiso   # noqa: E402

P1 = os.path.join(ROOT, "papers", "001286770", "財政検証詳細結果等", "03財政検証詳細結果", "01財政見通し")
P2 = os.path.join(ROOT, "papers", "001286771", "オプション試算詳細結果", "01財政見通し")

RTOL, RTOL_BAND, ATOL_MIN = 1e-3, 1e-2, 1e-4        # 兆円の単位。1e-4 兆円 = 1 億円
RATE_TOL_PT = 0.5                                    # %pt

# name → 実行の指定。published は (dir, 番号)。freeze は③④を据え置く元の name（高在老・報酬上限）
CASES = {
    # ---- 通常試算 8 ケース（詳細結果等1 の 01〜04、等2 の 81〜84）----
    "3001": dict(case="3001", roudr=1, published=(P1, "01"), label="高成長実現"),
    "3002": dict(case="3002", roudr=1, published=(P1, "02"), label="成長型経済移行・継続"),
    "3003": dict(case="3003", roudr=2, published=(P1, "03"), label="過去30年投影（労働参加漸進）"),
    "3004": dict(case="3004", roudr=3, published=(P1, "04"), label="1人当たりゼロ成長（労働参加現状）"),
    "3201": dict(case="3201", roudr=1, published=(P2, "81"), label="高成長実現（経済変動）"),
    "3202": dict(case="3202", roudr=1, published=(P2, "82"), label="成長型経済移行・継続（経済変動）"),
    "3203": dict(case="3203", roudr=2, published=(P2, "83"), label="過去30年投影（経済変動）"),
    "3204": dict(case="3204", roudr=3, published=(P2, "84"), label="1人当たりゼロ成長（経済変動）"),
    # ---- 移植版が公表値と照合した 11 ケース（検証/オプション試算/README.md）----
    "3003L": dict(case="3003", jin=3, roudr=2, published=(P1, "11"), label="出生低位・過去30年投影"),
    "tougou": dict(case="3001", roudr=1, options=["tougou"], published=(P2, "21"), label="調整期間の一致（高成長実現）"),
    "kozax": dict(case="3003", roudr=2, options=["kozax"], freeze="3003", published=(P2, "25"),
                  label="高在老の撤廃（過去30年投影）"),
    "houjou_1": dict(case="3003", jin=3, roudr=2, options=["houjou_1"], freeze="3003L", published=(P2, "26"),
                     label="標報上限 75 万円（出生低位・過去30年投影）"),
    "houjou_2": dict(case="3003", jin=3, roudr=2, options=["houjou_2"], freeze="3003L", published=(P2, "27"),
                     label="標報上限 83 万円（同）"),
    "houjou_3": dict(case="3003", jin=3, roudr=2, options=["houjou_3"], freeze="3003L", published=(P2, "28"),
                     label="標報上限 98 万円（同）"),
    "dmacro": dict(case="3201", roudr=1, options=["dmacro"], published=(P2, "85"), label="名目下限の撤廃（高成長・変動）"),
    "nocarry": dict(case="3201", roudr=1, options=["nocarry"], published=(P2, "89"),
                    label="キャリーオーバー廃止（高成長・変動）"),
    # ---- 参考（移植版では公表値と未照合。KAKUDAI=1 ↔ 約 90 万人の対応は run_pipeline.sh の値から推定）----
    "kakudai_1": dict(case="3001", roudr=1, options=["kakudai_1"], published=(P2, "01"),
                      label="適用拡大（約90万人・高成長実現）※参考"),
    "sigo": dict(case="3001", roudr=1, options=["sigo"], published=(P2, "17"), label="基礎年金45年化（高成長実現）※参考"),
}
ORDER = list(CASES)


def published_path(d, no):
    hits = sorted(glob.glob(os.path.join(d, "%s.*.xlsx" % no)))
    if not hits:
        raise FileNotFoundError("%s/%s.*.xlsx" % (d, no))
    return hits[0]


def _end_year(v):
    """公表の「終了年度」欄 → int か None（「調整なし」など）。"""
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.strip()[:4].isdigit():
        return int(v.strip()[:4])
    return None


def compare_published(pub, got, rate, kend):
    """公表の系列と突き合わせて {sheet: {label: stats}} と見出しの結果を返す。"""
    fin = rate[max(rate)]
    head = {}
    for key, label in (("計", "所得代替率"), ("基礎", "代替率(基礎)"), ("比例", "代替率(比例)")):
        p, g = pub["代替率"].get(key), fin.get(label)
        if isinstance(p, (int, float)) and g is not None:
            head[key] = dict(fast=g * 100., pub=p * 100., diff_pt=(g - p) * 100., ok=abs(g - p) * 100. <= RATE_TOL_PT)
    pe = {k: _end_year(v) for k, v in pub["終了年度"].items()}
    band = set()
    for y in (pe.get("基礎"), pe.get("比例"), kend.get("kiso"), kend.get("hirei")):
        if y:
            band.update(range(y - 1, y + 2))
    sheets = {}
    for sn, series in got.items():
        pubs = pub["sheets"].get(sn)
        if pubs is None:
            continue
        order = ([c[0] for c in CO.UNIFIED_PLAN["cols"]] if pub["layout"] == "一元化"
                 else [c[0] for c in CO.BYSYS_PLAN["sheets"][sn]])
        st = {}
        for label in order:
            pv, gv = pubs.get(label, {}), series.get(label, {})
            years = sorted(set(pv) & set(gv))
            if not years:
                continue
            n = n_bad = 0
            worst = (0., None)
            base = pubs.get("収入合計", {}) if label == "収支差引残" else None
            for y in years:
                p, g = pv[y], gv[y]
                a = abs(g - p)
                is_rate = label in CO.PCT
                if is_rate:
                    bad = a * 100. > RATE_TOL_PT
                    d = a * 100.                                  # %pt
                elif base is not None and y in base:
                    # 収支差引残は収入合計と支出合計の差なので、誤差の物差しは収入合計（相対差は桁落ちで膨らむ）
                    d = a / max(abs(base[y]), ATOL_MIN)
                    bad = d > (RTOL_BAND if y in band else RTOL)
                else:
                    if abs(p) < ATOL_MIN and a < ATOL_MIN:      # 1 億円未満の欄
                        continue
                    if abs(p) < ATOL_MIN:                       # 公表が 0（積立金の枯渇など）: 絶対差で
                        d = a
                        bad = a > 1e-3
                    else:
                        d = a / abs(p)
                        bad = d > (RTOL_BAND if y in band else RTOL)
                n += 1
                n_bad += int(bad)
                if d > worst[0]:
                    worst = (d, y)
            st[label] = dict(n=n, n_bad=n_bad, worst=worst[0], worst_year=worst[1], unit="pt" if label in CO.PCT else "rel",
                             series={"fast": {int(y): gv[y] for y in years}, "pub": {int(y): pv[y] for y in years}})
        sheets[sn] = st
    return head, pe, sheets


def reevaluate(r):
    """保存した系列（`series`）から判定をやり直す（許容の規則を変えたとき用）。"""
    sheets = r["sheets"]
    pub = {"代替率": {k: v["pub"] / 100. for k, v in r["head"].items()}, "終了年度": r["published_end"],
           "layout": r["layout"], "sheets": {}}
    got = {}
    for sn, st in sheets.items():
        pub["sheets"][sn] = {l: {int(y): v for y, v in s["series"]["pub"].items()} for l, s in st.items() if "series" in s}
        got[sn] = {l: {int(y): v for y, v in s["series"]["fast"].items()} for l, s in st.items() if "series" in s}
    if not any(got.values()):
        return r
    rate = {}
    sn0 = next(iter(got))
    for label in ("所得代替率", "代替率(基礎)", "代替率(比例)"):
        for y, v in got[sn0].get(label, {}).items():
            rate.setdefault(y, {})[label] = v
    head, pe, new = compare_published(pub, got, rate, r["kend"])
    r = dict(r); r["sheets"] = new
    return r


def run_one(name, spec, out_root, base_results, keep):
    case = spec["case"]
    jin, qx, nc, roudr = spec.get("jin", 1), spec.get("qx", 1), spec.get("nc", 0), spec["roudr"]
    pol = load_policy(*spec.get("options", []))
    out = os.path.join(out_root, name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    freeze = base_results.get(spec["freeze"]) if spec.get("freeze") else None
    t0 = time.perf_counter()
    res = pipeline.run(case, pol, suuri_env.suuri(), out, jin=jin, qx=qx, nc=nc, roudr=roudr, freeze_kiso_from=freeze)
    wall = time.perf_counter() - t0
    r5 = res["s5"]
    f = r5.out.final_rate
    kend = dict(hirei=int(r5.out.owari["kend_h"]), kiso=int(r5.out.owari["kend_t"]))
    # ---- 公表値 ----
    ver = "%s-%s-%s-%s" % ((case,) * 4)
    shushi_dir = os.path.join(out, "emp", "shushi")
    bas_dir = os.path.join(out, "bas", "rslt")
    pub = CO.read_published(published_path(*spec["published"]))
    emp = CO.read_emp(ver, "000", shushi_dir)
    nat = CO.read_nat(ver, "000", bas_dir)
    rate = CO.read_rate(ver, "000", shushi_dir)
    kakaku = CO.read_kakaku(ver, "000", bas_dir)
    X = {}
    if pub["layout"] == "一元化":
        K = kokusyushi_from_kiso(res["s4"])
        from kosoku.axis import YEARS
        X = {int(y): float(K[5, i] + K[6, i] + K[7, i]) / CO.CHO for i, y in enumerate(YEARS.labels())}
    got = CO.build(pub["layout"], emp, nat, rate, X, kakaku)
    head, pub_end, sheets = compare_published(pub, got, rate, kend)
    result = dict(name=name, label=spec["label"], case=case, jin=jin, qx=qx, nc=nc, roudr=roudr,
                  options=spec.get("options", []), frozen_from=spec.get("freeze"),
                  published=os.path.basename(pub["path"]), layout=pub["layout"],
                  final=dict(total=f["total"], hirei=f["hirei"], kiso=f["kiso"]), kend=kend,
                  head=head, published_end=pub_end, sheets=sheets,
                  timings={k: round(v, 3) for k, v in res["timings"].items()}, wall=round(wall, 1))
    if not keep:
        shutil.rmtree(out, ignore_errors=True)
    return res, result


def fmt_row(r):
    h = r["head"]
    def cell(k):
        if k not in h:
            return "—"
        return "%.4f / %.4f (%+.4f)" % (h[k]["fast"], h[k]["pub"], h[k]["diff_pt"])
    pe = r["published_end"]
    ke = "%s／%s" % (r["kend"]["kiso"], r["kend"]["hirei"])
    pk = "%s／%s" % (pe.get("基礎") or "調整なし", pe.get("比例") or "調整なし")
    worst = (0., "")
    n = nb = 0
    for sn, st in r["sheets"].items():
        for label, s in st.items():
            n += s["n"]; nb += s["n_bad"]
            if s["unit"] == "rel" and s["worst"] > worst[0]:
                worst = (s["worst"], "%s/%s/%s" % (sn, label, s["worst_year"]))
    okhead = all(v["ok"] for v in h.values())
    return "| %s | %s | %s | %s | %s | %s | %s | %d / %d | %.1e（%s） | %s |" % (
        r["name"], r["label"], cell("計"), cell("基礎"), cell("比例"), ke, pk, nb, n, worst[0], worst[1],
        "OK" if okhead and nb == 0 else "**要確認**")


def write_report(results, path):
    lines = ["# 通しの結果（高速版①〜⑤ vs 公表 財政見通し）", "",
             "`tools/run_cases.py` の出力。所得代替率は「高速版 / 公表 (差 %pt)」。終了年度は「基礎／比例」。",
             "欄の照合は相対 1e-3（終了年度 ±1 年の帯は 1e-2、所得代替率は ±0.5 %pt、1 億円未満の欄は見ない。",
             "収支差引残は収入合計に対する相対差。公表が 0 の欄（積立金の枯渇）は絶対差 10 億円）。",
             "「最大相対差」は金額の欄の最大（所得代替率の欄は除く）。明細は `通し/<name>.json`。", "",
             "| name | ケース | 所得代替率 計 | 基礎 | 比例 | 終了年度 | 公表の終了年度 | 許容超過 / 欄 | 最大相対差 | 判定 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    lines.extend(fmt_row(r) for r in results)
    lines += ["", "## 段階ごとの時間（秒。numba 無し）", "",
              "| name | ① | ② | ③ | ④ | ⑤ | CSV 書き | 通し |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        T = r["timings"]
        csv = sum(v for k, v in T.items() if k.endswith("_csv"))
        lines.append("| %s | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f |" % (
            r["name"], T.get("s1", 0.), T.get("s2", 0.) + T.get("s2_base", 0.), T.get("s3", 0.),
            T.get("s4", 0.) + T.get("s4_read", 0.), T.get("s5", 0.) + T.get("s5_read", 0.), csv, r["wall"]))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")


def load_results(rdir):
    """`通し/<name>.json` を ORDER の順に読む（前の実行のぶんも表に載せる）。系列があれば判定をやり直す。"""
    out = []
    for name in ORDER:
        p = os.path.join(rdir, "%s.json" % name)
        if os.path.exists(p):
            out.append(reevaluate(json.load(open(p, encoding="utf-8"))))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--only", default="", help="name をコンマ区切り（既定は全部）")
    ap.add_argument("--out-dir", default=None, help="CSV の置き場所（既定は一時ディレクトリ）")
    ap.add_argument("--keep", action="store_true", help="出力 CSV を消さない")
    ap.add_argument("--result-dir", default=os.path.join(FAST, "結果"))
    ap.add_argument("--report-only", action="store_true", help="回さずに `通し/*.json` から表を書き直す")
    a = ap.parse_args(argv)
    if a.report_only:
        write_report(load_results(os.path.join(a.result_dir, "通し")), os.path.join(a.result_dir, "通し.md"))
        return 0
    names = [n for n in a.only.split(",") if n] or ORDER
    out_root = a.out_dir or tempfile.mkdtemp(prefix="kosoku-cases-")
    rdir = os.path.join(a.result_dir, "通し")
    os.makedirs(rdir, exist_ok=True)
    base_results, results = {}, []
    for name in names:
        spec = CASES[name]
        if spec.get("freeze") and spec["freeze"] not in base_results:
            print("[%s] 据え置きの元 %s を先に回す" % (name, spec["freeze"]), flush=True)
            res, r = run_one(spec["freeze"], CASES[spec["freeze"]], out_root, base_results, a.keep)
            base_results[spec["freeze"]] = res
            results.append(r)
            json.dump(r, open(os.path.join(rdir, "%s.json" % spec["freeze"]), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[%s] %s" % (name, spec["label"]), flush=True)
        res, r = run_one(name, spec, out_root, base_results, a.keep)
        if not spec.get("options"):
            base_results[name] = res
        results.append(r)
        json.dump(r, open(os.path.join(rdir, "%s.json" % name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("   %s  計 %.4f（公表 %s）終了 %s  %.0f 秒" % (
            name, r["final"]["total"], "%.4f" % r["head"]["計"]["pub"] if "計" in r["head"] else "—", r["kend"], r["wall"]), flush=True)
        write_report(load_results(rdir), os.path.join(a.result_dir, "通し.md"))
    print("→ %s" % os.path.join(a.result_dir, "通し.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
