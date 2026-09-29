# -*- coding: utf-8 -*-
"""`python -m kosoku run 3001 --option kozax --dump-port-csv DIR`

    policy  [--option NAME ...]           policy を読んで葉の数と出典の無い項目を表示
    run CASE [--option NAME ...] [--jin 1] [--qx 1] [--nc 0] [--roudr 1]
             [--work DIR] [--dump-port-csv DIR] [--json PATH]
                                           ①〜⑤を通しで回し、最終所得代替率・終了年度・段階ごとの秒を表示

`--work` は `work/suuri/rev2024`（既定はリポジトリの `work/`）。`--dump-port-csv` は港の配置の CSV の
置き場所（既定は一時ディレクトリ。段階の受け渡しに使うので必ず書く）。
"""
import argparse
import json
import os
import sys
import tempfile

from .policy import load_policy
from .indicators import indicators
from .accounts import ledger_of, identities

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "work", "suuri", "rev2024")


def summary(res):
    """`pipeline.run` の戻り値 → JSON にできる要約。"""
    r5 = res["s5"]
    f = r5.out.final_rate
    return {
        "case": res["case"], "options": res["options"].tag,
        "final_rate": {"total": f["total"], "hirei": f["hirei"], "kiso": f["kiso"]},
        "kend": {"hirei": int(r5.out.owari["kend_h"]), "kiso": int(r5.out.owari["kend_t"])},
        "timings": {k: round(v, 3) for k, v in res["timings"].items()},
        "dirs": res["dirs"],
        "indicators": indicators(r5),
        "identities": [(n, d, ok) for n, d, ok in identities(ledger_of(res["policy"], r5, res.get("s4")))]
        if res.get("s4") is not None else [],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kosoku")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("policy", help="policy を読んで葉の数と出典の無い項目を表示")
    p.add_argument("--option", action="append", default=[])
    p = sub.add_parser("run", help="①〜⑤を通しで走らせる")
    p.add_argument("case")
    p.add_argument("--option", action="append", default=[], help="policy/options/*.yaml の名前（複数可）")
    p.add_argument("--balance", default=None, help="均衡の解法 premium / payg / perpetual / perpetual_premium（kosoku/balance.py）")
    p.add_argument("--jin", type=int, default=1, help="出生率 1 中位 / 2 高位 / 3 低位")
    p.add_argument("--qx", type=int, default=1, help="死亡率 1 中位 / 2 高位 / 3 低位")
    p.add_argument("--nc", type=int, default=0, help="入国超過 0 16万 / 1 6.9万 / 2 25万")
    p.add_argument("--roudr", type=int, default=1, help="労働力率 1 進展 / 2 漸進 / 3 現状")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--dump-port-csv", default=None)
    p.add_argument("--json", default=None, help="要約を JSON で書く先")
    a = ap.parse_args(argv)

    if a.cmd == "policy":
        pol = load_policy(*a.option)
        n_leaf = len(pol.unsourced()) + len(pol.sources)
        print("読み込み: %s" % " + ".join(pol.origin))
        print("葉 %d（出典つき %d）" % (n_leaf, len(pol.sources)))
        for p in pol.unsourced():
            print("  出典なし: %s" % p)
        return 0
    if a.cmd == "run":
        from .pipeline import run
        pol = load_policy(*(a.option + (["balance_" + a.balance] if a.balance else [])))
        out = a.dump_port_csv or tempfile.mkdtemp(prefix="kosoku-%s-" % a.case)
        res = run(a.case, pol, a.work, out, jin=a.jin, qx=a.qx, nc=a.nc, roudr=a.roudr)
        s = summary(res)
        print("ケース %s  レバー %s" % (s["case"], s["options"]))
        print("最終所得代替率  計 %.4f  比例 %.4f  基礎 %.4f" % (
            s["final_rate"]["total"], s["final_rate"]["hirei"], s["final_rate"]["kiso"]))
        print("調整終了年度    厚年 %d  国年 %d" % (s["kend"]["hirei"], s["kend"]["kiso"]))
        ind = s["indicators"]
        print("均衡の解法      %s%s" % (ind["final"]["rule"], "  料率 %.4f" % ind["final"]["premium_rate"] if ind["final"]["premium_rate"] else ""))
        print("指標（2050）    実効料率 %.4f  給付÷GDP %.4f  積立度合 %.2f" % (
            ind["premium_rate"].get(2050, float("nan")), ind["benefit_to_gdp"].get(2050, float("nan")), ind["fund_ratio"].get(2050, float("nan"))))
        bad = [n for n, d, ok in s["identities"] if not ok]
        print("恒等式          %d 本%s" % (len(s["identities"]), "、全部 OK" if not bad else "、NG: " + ", ".join(bad)))
        T = s["timings"]
        print("時間（秒）      " + "  ".join("%s %.1f" % (k, v) for k, v in T.items()))
        print("CSV → %s" % out)
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fp:
                json.dump(s, fp, ensure_ascii=False, indent=1)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
