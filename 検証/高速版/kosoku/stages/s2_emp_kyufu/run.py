# -*- coding: utf-8 -*-
"""②厚生年金給付費推計の通し（移植版 `main.cpp` `sepsd.cpp`）
==============================================================
制度（厚年 kou / 国共済 kok / 地共済 ren / 私学 sig）ごとに

    read_inputs   外枠・経済前提・基礎率・足元・支給率・生命表を読む
    run_system    econ → seid → krgn → 種別 s ごとに kiso → dtst → shke(基準年度) →
                  年度ループ（siml → shke）→ rousaki → stat → `KyufuOut`
    run           4 制度をまとめて回す

港: emp_kyufu/sepsd.py:sepsd
港: emp_kyufu/main.py:main
仕様: §12.2（②の流れ）
"""
import os
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS
from ...contracts import KyufuOut, Provenance, policy_hash, git_rev
from ...econ import read_econ_csv
from ...options import options_of
from . import inputs as IN
from .context import Ctx
from .dtst import dtst
from .econ import kyufu_econ
from .kiso import kiso_rates
from .krgn import kuriage
from .seid import seid_consts, sik_extend, set_hsr, kflcan_table
from .shke import new_agg, shke
from .siml import siml
from .sknr import shikyu_kaishi
from .stat import rousaki, stat, outkn_collapse
from .state import new_state

__all__ = ["KyufuInputs", "KyufuRun", "read_inputs", "run_system", "run"]

KONEN = {"kou": 1, "kok": 0, "ren": 0, "sig": 0}


@dataclass
class KyufuInputs:
    pol: object
    system: str
    case: str
    econ: object                 # EconAssumptions
    pop: np.ndarray
    l: np.ndarray
    lpt: np.ndarray
    lpt1: np.ndarray
    lpt2: np.ndarray
    lpt3: np.ndarray
    lpt4: np.ndarray
    kisor: dict                  # {s: Kisor}
    hou: object
    sikur: object
    rs: np.ndarray
    rkrag: np.ndarray
    rkrgn: np.ndarray
    qp: np.ndarray
    hk: dict                     # {s: HkIn}
    jk: dict                     # {s: JkIn}


@dataclass
class KyufuRun:
    out: KyufuOut
    pol: object
    system: str
    pseid: int
    partyr3: int
    E: object
    ag: object
    ctxs: dict
    partyr4: int = -1
    flg_part: int = 0


def read_inputs(pol, system, case, emp_dir, waku_dir, econ_csv, qx_csv):
    """`emp_dir`: `work/.../emp`（`data/u-rev/{kisor,kisos,econ}`）。"""
    konen = KONEN[system]
    data = os.path.join(emp_dir, "data", "u-rev")
    ns = 3 if konen else 2
    pop, l, lpt, lpt1, lpt2, lpt3, lpt4 = IN.read_waku(waku_dir, case, system, options_of(pol).kakudai)
    kis = os.path.join(data, "kisor")
    KS = YEARS.i(pol.get("kounen.years.kijun")) - 1
    return KyufuInputs(
        pol, system, case, read_econ_csv(econ_csv), pop, l, lpt, lpt1, lpt2, lpt3, lpt4,
        {s: IN.read_kisor(os.path.join(kis, "kisor_%s2024.csv" % system), s) for s in range(1, ns + 1)},
        IN.read_hou(os.path.join(kis, "hou_%s2024.csv" % system)),
        IN.read_sikur(os.path.join(kis, "sikur_%s2024.csv" % system), konen),
        IN.read_yuizor(os.path.join(kis, "yuizor_%s2024.csv" % system), konen, KS, YEARS.n - 1),
        *IN.read_kragsg(os.path.join(kis, "kragsg_2024.csv")),
        IN.read_qx(qx_csv, seiy=YEARS.i(pol.get("kounen.flags.seiy"))),
        {s: IN.read_hk(os.path.join(data, "kisos", system, "hk2021-%d.csv" % s)) for s in range(1, ns + 1)},
        {s: IN.read_jk(os.path.join(data, "kisos", system, "jk2021-%d.csv" % s)) for s in range(1, ns + 1)})


def run_system(inp, upstream=(), flg_inout=0):
    """1 制度を通す。`flg_inout` は労働参加のシナリオ（労働力率 − 1: 0 進展 / 1 漸進 / 2 現状。厚年の
    生存脱退力の縮小率 `kounen.kiso.rds` を選ぶ）。港: emp_kyufu/sepsd.py:sepsd"""
    pol, system = inp.pol, inp.system
    pseid, konen = IN.PSEID[system], KONEN[system]
    KIJ = YEARS.i(pol.get("kounen.years.kijun")); KE = YEARS.n - 1
    partyr3 = YEARS.i(pol.get("kounen.years.part_yr3"))
    opt = options_of(pol)
    partyr4 = YEARS.i(pol.get("kounen.years.part_yr_option")) if opt.kakudai else -1
    kfl = kflcan_table(pol) if opt.sigo else None
    hr = tuple(float(v) for v in pol.get("kounen.houjou")[("r75", "r83", "r98")[opt.houjou - 1]]) if opt.houjou else (1., 1.)
    E = kyufu_econ(pol, inp.econ, YEARS.last)
    sd = seid_consts(pol, E.ad2, pseid, konen, kflcan=(kfl[-1] if opt.sigo else None), flg_sigo=opt.sigo)
    sik, nos = sik_extend(pol, inp.sikur, pseid)
    ku = kuriage(pol, inp.rkrag, inp.rkrgn)
    hs = set_hsr(pol, inp.hou, inp.l, E.ad, pseid, flg_part=opt.kakudai,
                 lpt=inp.lpt, lpt2=inp.lpt2, lpt3=inp.lpt3, lpt4=inp.lpt4)
    sks = {s: shikyu_kaishi(pol, s, konen) for s in (1, 2, 3)}
    xend = 90 if pseid == 0 else 75
    ag = new_agg()
    ctxs = {}
    for s in (1, 2, 3):
        if not konen and s == 3:
            break
        K = kiso_rates(pol, inp.kisor[s], inp.qp, pseid, s, sks[s], flg_inout=flg_inout)
        ctx = Ctx(pol=pol, system=system, pseid=pseid, konen=konen, s=s, xend=xend, tend=xend - 15,
                  sd=sd, ku=ku, K=K, E=E, hs=hs, sk=sks[s], sk_male=sks[1], sk_female=sks[2], sk_total=sks[3],
                  rs=inp.rs, pop=inp.pop, lpt1=inp.lpt1, lpt2=inp.lpt2, lpt3=inp.lpt3, lpt4=inp.lpt4,
                  partyr4=partyr4, flg_part=opt.kakudai, flg_sigo=opt.sigo, kflcan=kfl,
                  sik=sik, nos=nos, routsu=inp.sikur.routsu,
                  KIJ=KIJ, partyr3=partyr3, C=pol.get("kounen.siml"),
                  kyuho_last=int(pol.get("kounen.cohorts.kyuho_last")),
                  flg_kozax=opt.kozax, kozaxyr=YEARS.i(pol.get("kounen.years.kozaxyr")),
                  kozax=int(pol.get("kounen.ages.kozax")),
                  houjou=opt.houjou, houjouyr=YEARS.i(pol.get("kounen.years.houjouyr")), houjou_r=hr)
        ctxs[s] = ctx
        st = new_state(inp.l, inp.lpt)
        dtst(pol, st, inp.hk[s], inp.jk[s], sd, ku, K, E, pseid, konen, s, sks[s], system)
        shke(ctx, st, ag, KIJ)
        for k in range(KIJ + 1, KE + 1):
            siml(ctx, st, k)
            shke(ctx, st, ag, k)
    outkn_collapse(ctxs, ag)
    rousaki(ctxs, ag)
    stat(ctxs, ag)
    prov = Provenance(case=inp.case, stage="s2", source="fast", policy=policy_hash(pol.data),
                      rev=git_rev(), upstream=tuple(upstream), note=system)
    A = ag.ks
    out = KyufuOut(prov=prov, system=system,
                   kiso={"okisor": ag.okisor, "okiso2x": ag.okiso2x},
                   shus={n: A[n] for n in ("ap", "ap65", "ap70", "ap75", "a", "a60", "a65", "a70", "a75", "aiku",
                                          "aal", "apart", "aikupart", "a60part", "a65part", "a70part")}
                   | {"d3x": ag.d3x, "kfprx": ag.kfprx},
                   kaite={"arv_hh": E.arv_hh, "arv_hp": E.arv_hp} if pseid == 0 else {})
    return KyufuRun(out, pol, system, pseid, partyr3, E, ag, ctxs, partyr4, opt.kakudai)


def run(pol, case, emp_dir, waku_dir, econ_csv, qx_csv, systems=IN.SYSTEMS, upstream=(), flg_inout=0):
    """4 制度を回す → {system: KyufuRun}。`flg_inout` は `run_pipeline.sh` が②に渡す `ROUDR − 1`。
    港: emp_kyufu/main.py:main"""
    return {s: run_system(read_inputs(pol, s, case, emp_dir, waku_dir, econ_csv, qx_csv), upstream, flg_inout)
            for s in systems}
