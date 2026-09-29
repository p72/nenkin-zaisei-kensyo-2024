# -*- coding: utf-8 -*-
"""⑤厚生年金収支計算の通し（移植版 `main.c` `shus.c:shus` の順のまま）
=========================================================================
    入力（② shus.*、④ 拠出金・妻積・cuta、③ 改定率、① 調整率、納付金）
    → 経済前提 → 保険料率 → モデル世帯
    → 年齢別の給付 → 保険料収入 → 固定項目（積立金・納付金・事務費・妻積）
    → 調整前の収支（`Cc_before`）
    → 調整終了年度を解く（`solve`）→ 調整後の収支（`Cc`）→ 所得代替率

港: emp_shushi/main.py:main, set_filenum
港: emp_shushi/shus.py:shus, shus_calc_only
港: emp_shushi/shus_calc.py:shus_calc0
仕様: §7.2、§8、§9
"""
from dataclasses import dataclass
import os

import numpy as np

from ...axis import YEARS, AGES
from ...contracts import ShushiOut, Provenance, policy_hash, git_rev
from ...econ import read_econ_csv
from ...options import options_of
from . import inputs as IN
from .econ import shushi_econ
from .premium import premium_rates, model_household, Premium
from .shushi import C, NCOL, benefit_by_age, premium_income, fixed_items, nendokan, balance, fund_margin
from .solve import solve, Solution, rh_tokutyo
from ...balance import rule_of, fixed_benefit_Sh, margin_stationary, solve_premium, solve_payg

__all__ = ["ShushiInputs", "read_inputs", "ShushiRun", "run"]


@dataclass
class ShushiInputs:
    pol: object
    shus: dict                   # {制度名: ShusIn}
    kyos: IN.Kyos
    tumazumi: np.ndarray         # (NSYS, YEARS.n)
    nofu: np.ndarray             # (YEARS.n,)
    jyutaku: np.ndarray
    krb: np.ndarray              # (YEARS.n, AGES.n) 比例の改定率
    kra: np.ndarray              # 定額（国年）の改定率
    scutrk1: np.ndarray          # (YEARS.n,) 毎年のスライド調整率
    scutrrki: np.ndarray         # (YEARS.n, AGES.n) 国年の累積調整率（④）
    econ: object                 # EconAssumptions
    ks: int
    ke: int
    upstream: tuple = ()
    kokusyushi: np.ndarray = None   # 調整期間の一致のとき: 国年の収支項目 (10, YEARS.n)（港の provide）


def _expand_cuta(cuta):
    out = np.ones((YEARS.n, AGES.n))
    out[:, AGES.s(IN.AGE_LO, IN.AGE_HI)] = cuta
    has = cuta.any(axis=1)
    out[~has] = 1.
    return out


def read_inputs(pol, case, emp_dir, bas_dir, nat_dir, waku_dir, econ_csv, kiso=None, nat_out=None,
                yobi="000", shus_case=None, nofu_name="nof2024.csv", kyufu_dir=None):
    """④は `kiso`（高速版の `KisoRun`）があればそれを、無ければ港の CSV を読む。③も同様に `nat_out`。
    ②は `kyufu_dir`（高速版②の `to_port_csv` の出力先。`shus/` `kaite/` を持つ）があればそこから、
    無ければ `emp_dir/rslt/u-rev` の港の CSV を読む。"""
    sc = shus_case or case
    kdir = kyufu_dir or os.path.join(emp_dir, "rslt", "u-rev")
    shus = {}
    for name in IN.SYSTEMS:
        shus[name] = IN.read_shus(os.path.join(kdir, "shus", "shus.%s-%s-%s_%s" % (sc, case, case, name)))
    ks = shus["kou"].ks
    ke = shus["kou"].ke
    up = ()
    kokusyushi = None
    if kiso is not None:
        tougou = options_of(pol).tougou
        KY = kiso.out.kyoshutukin
        kyos = IN.kyos_from_kiso(kiso.kyo_b, (KY["tokubetu_nendomatu_P"], KY["tokubetu_nendomatu"]) if tougou else None)
        if tougou:
            kokusyushi = IN.kokusyushi_from_kiso(kiso)
        tumazumi = kiso.tumatumi[1:1 + IN.NSYS].copy()
        scutrrki = _expand_cuta(kiso.out.cuta)
        kra = IN.fill_under_67(kiso.inp.kaiteiritu)
        up = (kiso.out.prov,)
    else:
        kyos = IN.read_kyoshutukin(os.path.join(bas_dir, "data", "KYOSHUTUKIN%s-%s-%s-%s-%s" % ((case,) * 4 + (yobi,))))
        tumazumi = IN.read_tumatumi(os.path.join(bas_dir, "rslt", "TUMATUMI-%s-%s-%s-%s-00.csv" % ((case,) * 3 + (yobi,))))
        scutrrki = IN.read_cuta_kiso(os.path.join(bas_dir, "rslt", "cuta-%s-%s-%s-%s-1120-%s.csv" % ((case,) * 4 + (yobi,))))
        kra = None
    if nat_out is not None:
        kra = IN.fill_under_67(nat_out.kokukaite)
        if not up:
            up = (nat_out.prov,)                # ④が高速版なら③の来歴は④の upstream にある
    elif kra is None:
        kra = IN.read_kaite(os.path.join(nat_dir, "data", "KOKUKAITE-%s-%sE.csv" % (case, case)))
    krb = IN.read_kaite(os.path.join(kdir, "kaite", "kaiteb-%s-%se" % (sc, case)))
    scutrk1 = IN.read_scutrk1(os.path.join(waku_dir, "waku%s-m.csv" % case))
    nofu, jyutaku = IN.read_nofu(os.path.join(emp_dir, "data", "ez-arev", nofu_name))
    econ = read_econ_csv(econ_csv)
    if options_of(pol).tougou and kokusyushi is None:
        raise NotImplementedError("調整期間の一致（tougou）は高速版④の結果（kiso=）からだけ回せる（港の provide の読み手は無い）")
    return ShushiInputs(pol, shus, kyos, tumazumi, nofu, jyutaku, krb, kra, scutrk1, scutrrki, econ, ks, ke, up,
                        kokusyushi)


@dataclass
class ShushiRun:
    out: ShushiOut
    inp: ShushiInputs
    E: object                    # ShushiEcon
    prem: object                 # Premium
    model: object                # Model
    A: dict                      # 適用拡大を足した後の報酬・被保険者数
    ben: np.ndarray              # 年齢別の給付（E3dxb）
    Cc_before: np.ndarray        # 調整前の台帳 (NSYS, NCOL, YEARS.n)
    Cc: np.ndarray               # 調整後
    sol: object                  # solve.Solution


def _solve_premium_lever(pol, rule, Cc, E, ben, inp, prem, ks, ke, carry, d_macro, touitu, houjou, margin):
    """料率を動かす解法（給付固定）。`premium` / `perpetual_premium` は `premium_from` 年度からの一定率を
    割線法で、`payg` は毎年の率を逐次で解く。"""
    Yn = pol.get("shushi.years")
    bal = pol.get("shushi.balance")
    kijun, ie = YEARS.i(Yn["kijun"]), YEARS.i(ke)
    kend, k_jis = YEARS.i(Yn["kend"]), YEARS.i(Yn["k_jisseki"])
    i1 = YEARS.i(ks) + 1
    nendohosei = pol.get("shushi.nendohosei")
    x63 = AGES.i(IN.AGE_LO)
    slide = rh_tokutyo(pol, inp.scutrk1, inp.krb, ke, carry, d_macro)
    Sh = fixed_benefit_Sh(slide.rh, kijun, k_jis, ie, x63)
    St = Sh.copy() if touitu else inp.scutrrki.copy()
    nendokan(Cc, ben, Sh, St, inp.kra, inp.krb, i1, ie, nendohosei, touitu)
    if rule.target == "annual_balance":
        balance(Cc, E, kijun, i1, ie)
        i_from = YEARS.i(rule.premium_from)
        rates = solve_payg(Cc, C, E, kijun, i_from, ie, E.ci)             # 積立金は物価で実質一定
        f = float(Cc[:, C.SHUSHISA, ie].sum() - Cc[:, C.TUMITATE, ie - 1].sum() * E.ci[ie])
        return Solution(YEARS.label(k_jis), Sh, St, slide, 0, 0, True, 0., f, rule.name, None, rates)

    def apply_rate(r):
        p = premium_rates(pol, ks, override={"from": rule.premium_from, "rate": r})
        premium_income(pol, inp.shus, p, Cc, ks, houjou, inp.kokusyushi if touitu else None)

    def evaluate():
        balance(Cc, E, kijun, i1, ie)
        return fund_margin(Cc, kend, bal["ca"]) if margin is None else margin(Cc)

    tol = bal["tol"] * abs(Cc[:, C.SHISHUTU, ie].sum()) * 1e3      # 支出の 5e-11（率の解は 1e-12 桁まで要らない）
    r0 = float(pol.get("shushi.hokenryoritu.kou.cap"))
    r, f, n, ok = solve_premium(apply_rate, evaluate, r0, r0 + 0.02, tol, bal["secant_iters"], bal["max_iters"])
    return Solution(YEARS.label(k_jis), Sh, St, slide, 0, n, ok, r, f, rule.name, r, None)


def run(inp, case, carry=None, d_macro=None, touitu=None, houjou=None):
    """⑤を通しで回す。`carry=0` キャリーオーバー廃止、`d_macro=1` 名目下限撤廃、`touitu` 調整期間の一致、
    `houjou` 標準報酬上限の見直し。省略なら policy の `options.*`（`kosoku/options.py`）。"""
    pol = inp.pol
    opt = options_of(pol)
    carry = opt.carry if carry is None else carry
    d_macro = opt.dmacro if d_macro is None else d_macro
    touitu = bool(opt.tougou) if touitu is None else touitu
    houjou = opt.houjou if houjou is None else houjou
    ks, ke = inp.ks, inp.ke
    kijun = YEARS.i(pol.get("shushi.years.kijun"))
    nendohosei = pol.get("shushi.nendohosei")
    E = shushi_econ(pol, inp.econ)
    prem = premium_rates(pol, ks)
    model = model_household(pol, E.h, prem.rate["kou"], ke)
    ben = benefit_by_age(inp.shus, inp.kyos, inp.kokusyushi if touitu else None, nendohosei)

    Cc = np.zeros((IN.NSYS, NCOL, YEARS.n))
    A = premium_income(pol, inp.shus, prem, Cc, ks, houjou, inp.kokusyushi if touitu else None)
    fixed_items(pol, inp.shus, E, inp.nofu, inp.tumazumi, Cc, ks, inp.kokusyushi if touitu else None)

    # ---- 調整前（調整率は全部 1） ----
    ones = np.ones((YEARS.n, AGES.n))
    i1, ie = YEARS.i(ks) + 1, YEARS.i(ke)
    nendokan(Cc, ben, ones, ones, inp.kra, inp.krb, i1, ie, nendohosei, touitu)
    balance(Cc, E, kijun, i1, ie)
    Cc_before = Cc.copy()

    # ---- 均衡を解く → 調整後（`kosoku/balance.py`。既定 current は移植版と同じ解法）----
    rule = rule_of(pol)
    margin = None
    if rule.target == "perpetual":
        g = float(E.h[ie])                                       # 終期の名目賃金上昇率
        margin = lambda Cc_: margin_stationary(Cc_, C, ie, g)    # noqa: E731
    if rule.lever == "benefit_level":
        sol = solve(pol, Cc, E, ben, inp.scutrk1, inp.scutrrki, inp.kra, inp.krb, ke, carry, d_macro, touitu,
                    margin=margin)
        sol.rule = rule.name
    else:
        sol = _solve_premium_lever(pol, rule, Cc, E, ben, inp, prem, ks, ke, carry, d_macro, touitu, houjou, margin)
        if sol.premium_rate is not None:
            prem = premium_rates(pol, ks, override={"from": rule.premium_from, "rate": sol.premium_rate})
        elif sol.rates is not None:                              # 賦課方式: 解いた毎年の率を持たせる
            rate = dict(prem.rate)
            for s_, name in enumerate(IN.SYSTEMS):
                rate[name] = np.where(sol.rates[s_] > 0., sol.rates[s_], prem.rate[name])
            prem = Premium(rate, prem.avg)
        model = model_household(pol, E.h, prem.rate["kou"], ke)   # 可処分所得は解いた率で

    x67 = AGES.i(67)
    kend = YEARS.i(pol.get("shushi.years.kend"))
    kw = model.kw[ie, 0]
    final = {"total": (model.mhirei[ie, 0] * sol.Sh[ie, x67] + model.mkiso[ie] * sol.St[ie, x67]) / kw * 100.,
             "hirei": model.mhirei[ie, 0] * sol.Sh[ie, x67] / kw * 100.,
             "kiso": model.mkiso[ie] * sol.St[ie, x67] / kw * 100.}
    prov = Provenance(case=case, stage="s5", source="fast", policy=policy_hash(pol.data),
                      rev=git_rev(), upstream=inp.upstream)
    from .output import shushi_table, summary_table, kend_of, SYS_OUT, COLS_SHUSHI
    r = ShushiRun(None, inp, E, prem, model, A, ben, Cc_before, Cc, sol)
    T = shushi_table(r, Cc)
    shushi = {name: {col: T[j, c].copy() for c, col in enumerate(COLS_SHUSHI) if col}
              for j, name in enumerate(SYS_OUT)}
    out = ShushiOut(prov=prov, shushi=shushi, summary=summary_table(r),
                    owari={"kend_h": kend_of(sol.Sh, ks, ke), "kend_t": kend_of(sol.St, ks, ke),
                           "kn": sol.kn, "cut_h": 1. - sol.Sh[ie, x67], "cut_t": 1. - sol.St[ie, x67],
                           "margin": sol.margin, "n_scan": sol.n_scan, "n_iter": sol.n_iter, "ok": sol.ok},
                    final_rate=final)
    r.out = out
    return r
