# -*- coding: utf-8 -*-
"""通しの実行 — `run(case, policy, work, out_dir, …)`
=====================================================
段階の順は ① → ② → ③ → ④ → ⑤（`STAGES`）。段階の受け渡しは港の配置の CSV（`to_port_csv`）で、
下流の読み手がそのまま読む。`upstream_from={"waku": dir, "kyufu": dir}` で①②を港（原本）の CSV
に差し替えられる（ドリフトの帰属用）。

レバー（`kosoku/options.py`。policy の `options.*`）
    - 高在老の撤廃・標準報酬上限（`Options.freeze_kiso`）: ③④は**通常試算のまま据え置き**、②⑤だけ
      レバー付きで回す（仕様 §11.2、`run_pipeline.sh` の `STEPS=25`）。据え置く③④は `freeze_kiso_from`
      （通常試算の `run()` の結果）から取り、無ければ通常試算の policy で②③④を回して作る
    - 調整期間の一致（tougou）: ④（tougou=1。国年の拠出金 ss=7,8 と provide）→ ⑤（Touitu）。
      港はそのあと④をもう一度回して基礎年金の見通しを作り直す（`CUT_KOTEI=1`）が、⑤の結果は
      それに依らないので高速版はまだ回さない（`result["s4_second"]` は None）
    - 名目下限撤廃・キャリーオーバー廃止: ④⑤の引数（policy から自動）
    - 適用拡大: ①②③⑤、45年化: ①②⑤（③④の 45年化は `run_pipeline.sh` が常に 0 で渡すので無い）

戻り値は dict: `s1` `s2` `s3` `s4` `s5` の各 run、`dirs`（書いた CSV の場所）、`options`、
`timings`（段階ごとの秒。`s2_csv` のように CSV を書く時間は別）。
"""
import os
import time
from dataclasses import replace

from .contracts import Provenance, policy_hash, git_rev
from .options import options_of, Options
from .policy.model import Policy

__all__ = ["run", "STAGES", "Work", "base_policy"]

STAGES = ("s1_hihokensha", "s2_emp_kyufu", "s3_nat", "s4_kiso_nenkin", "s5_emp_shushi")
_QX_LETTER = {1: "M", 2: "H", 3: "L"}


class Work:
    """`work/suuri/rev2024` の下の置き場所。"""

    def __init__(self, root):
        self.root = root

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def waku_data(self):
        return self.p("wakuc", "data")

    def waku_port(self, case):
        return self.p("wakuc", "rslt", "ver_4_1", "rslt%s" % case)

    def emp(self):
        return self.p("emp")

    def nat(self):
        return self.p("nat")

    def bas(self):
        return self.p("bas")

    def econ_csv(self, case):
        return self.p("emp", "data", "u-rev", "econ", "econ-%s.csv" % case)

    def qx_csv(self, qx=1):
        return self.p("emp", "data", "u-sinj", "QX-%s2023.csv" % _QX_LETTER[qx])


def base_policy(pol):
    """レバーを全部通常試算に戻した policy（`options.*` を既定に）。"""
    base = {n: getattr(Options(), n) for n in Options.__dataclass_fields__}
    data = dict(pol.data)
    data["options"] = base
    return Policy(data=data, sources=pol.sources, origin=pol.origin + ("options=base",))


def run(case, policy, work, out_dir, *, jin=1, qx=1, nc=0, roudr=1, upstream_from=None,
        freeze_kiso_from=None, stages=STAGES, write_csv=True):
    """段階を順に走らせ、各段階の run を dict で返す。`work` は `work/suuri/rev2024`（str か `Work`）、
    `out_dir` に港の配置で CSV を書く。"""
    from .stages.s1_hihokensha import run as H1
    from .stages.s1_hihokensha.output import to_port_csv as h1_csv
    from .stages.s2_emp_kyufu import run as KY
    from .stages.s2_emp_kyufu.output import to_port_csv as ky_csv
    from .stages.s3_nat import run as NAT
    from .stages.s3_nat.output import to_port_csv as nat_csv
    from .stages.s4_kiso_nenkin import run as KISO
    from .stages.s4_kiso_nenkin.output import to_port_csv as kiso_csv
    from .stages.s5_emp_shushi import run as SH
    from .stages.s5_emp_shushi.output import to_port_csv as sh_csv

    W = work if isinstance(work, Work) else Work(work)
    case = str(case)
    up = dict(upstream_from or {})
    opt = options_of(policy)
    os.makedirs(out_dir, exist_ok=True)
    res = {"case": case, "options": opt, "dirs": {}, "policy": policy, "timings": {}}
    T = res["timings"]

    def timed(key, fn, *args, **kw):
        t0 = time.perf_counter()
        out = fn(*args, **kw)
        T[key] = T.get(key, 0.) + time.perf_counter() - t0
        return out

    econ = W.econ_csv(case)

    # ---- ① 外枠 ----
    if "waku" in up:
        waku_dir = up["waku"]
    elif "s1_hihokensha" in stages:
        r1 = timed("s1", lambda: H1.run(H1.read_inputs(policy, W.waku_data(), jin, qx, nc, roudr), case))
        res["s1"] = r1
        waku_dir = os.path.join(out_dir, "waku")
        timed("s1_csv", h1_csv, r1, case, waku_dir)
    else:
        waku_dir = W.waku_port(case)
    res["dirs"]["waku"] = waku_dir

    # ---- ② 給付費（レバー付き）----
    def run_kyufu(pol, sub):
        runs = timed("s2" if sub == "kyufu" else "s2_base", KY.run, pol, case, W.emp(), waku_dir, econ, W.qx_csv(qx),
                     flg_inout=roudr - 1)                       # 港: run_pipeline.sh は ROUDR−1 を②に渡す
        d = os.path.join(out_dir, sub)
        timed("s2_csv", ky_csv, runs, case, d)
        return runs, d

    if "kyufu" in up:
        kyufu_dir = up["kyufu"]
    elif "s2_emp_kyufu" in stages:
        res["s2"], kyufu_dir = run_kyufu(policy, "kyufu")
    else:
        kyufu_dir = os.path.join(W.emp(), "rslt", "u-rev")
    res["dirs"]["kyufu"] = kyufu_dir

    # ---- ③④（据え置くレバーなら通常試算の②③④で）----
    if opt.freeze_kiso and freeze_kiso_from is not None:
        nat_r, kiso_r = freeze_kiso_from["s3"], freeze_kiso_from["s4"]
        res["frozen_from"] = freeze_kiso_from.get("case")
    else:
        pol34 = policy
        kyufu34 = kyufu_dir
        if opt.freeze_kiso:
            pol34 = base_policy(policy)
            if "kyufu_base" in up:
                kyufu34 = up["kyufu_base"]
            else:
                res["s2_base"], kyufu34 = run_kyufu(pol34, "kyufu_base")
            res["dirs"]["kyufu_base"] = kyufu34
        if "nat" in up:                                   # ③を港の CSV で（`nat/data` を持つ dir）
            nat_r, nat_dir, nat_out = None, up["nat"], None
        else:
            nat_r = timed("s3", lambda: NAT.run(NAT.read_inputs(pol34, W.nat(), waku_dir, case, econ,
                                                                 lifetable="QX-%s2023.csv" % _QX_LETTER[qx],
                                                                 birth="birth_ratio_%d.csv" % (jin - 1)), case))
            nat_dir, nat_out = W.nat(), nat_r.out
        kinp = timed("s4_read", KISO.read_inputs, pol34, case, nat_dir, os.path.join(kyufu34, "kiso"), waku_dir,
                     W.bas(), econ, nat_out=nat_out)
        kiso_r = timed("s4", KISO.run, kinp, case, tougou=opt.tougou)
    res["s3"], res["s4"] = nat_r, kiso_r
    if write_csv and nat_r is not None:
        timed("s3_csv", nat_csv, nat_r.out, policy, case, os.path.join(out_dir, "nat"))
        res["dirs"]["nat"] = os.path.join(out_dir, "nat")
    if write_csv:
        timed("s4_csv", kiso_csv, kiso_r, case, os.path.join(out_dir, "bas"), tougou=opt.tougou)
        res["dirs"]["bas"] = os.path.join(out_dir, "bas")

    # ---- ⑤ 収支 ----
    nat_dir5 = up.get("nat", W.nat())
    inp = timed("s5_read", SH.read_inputs, policy, case, W.emp(), W.bas(), nat_dir5, waku_dir, econ, kiso=kiso_r,
                nat_out=(nat_r.out if nat_r is not None else None), kyufu_dir=kyufu_dir)
    r5 = timed("s5", SH.run, inp, case)
    res["s5"] = r5
    res["s4_second"] = None
    if write_csv:
        timed("s5_csv", sh_csv, r5, case, os.path.join(out_dir, "emp"))
        res["dirs"]["emp"] = os.path.join(out_dir, "emp")
    T["total"] = sum(v for k, v in T.items() if k != "total")
    return res


def provenance(case, policy, stage, source, upstream=()):
    return Provenance(case=str(case), stage=stage, source=source,
                      policy=policy_hash(policy.data), rev=git_rev(),
                      upstream=tuple(upstream))
