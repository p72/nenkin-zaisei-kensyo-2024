# -*- coding: utf-8 -*-
"""④基礎年金の通し（移植版 `main.c` の順のまま）
==================================================
    入力（③の受給者数・②の受給者数・①の外枠・実績）
    → 経済前提（改定率・調整率・累積調整率）
    → 独自給付・保険料・妻積
    → 調整前の給付費と拠出金（`kekka…b`、⑤へ渡す `KYOSHUTUKIN` はこれ）
    → 終了年度を解く（`tyousei.solve`）→ `cuta`
    → 調整後の給付費と拠出金（`kekka…a`）

港: kiso_nenkin/main.py:run
港: kiso_nenkin/tumatumi_cal_jisseki.py:tumatumi_cal_jisseki
仕様: §6、§7.1、§8
"""
from dataclasses import dataclass
import os

import numpy as np

from ...axis import YEARS, AGES
from ...contracts import KisoOut, Provenance, policy_hash, git_rev
from ...econ import read_econ_csv
from ...options import options_of
from ...io_port import read_year_age_table
from . import inputs as IN
from .dokuzi import (Dokuzi, read_dokuzi_table, dokuzi_from_natout, dokuzi_from_table,
                     build_dokuzi, build_hokenryou)
from .econ import kiso_econ, read_max_cut
from .kyufu import build_kyufu, tanka_kyoshutukin, with_totals
from .tyousei import cut_base, fund_path, solve, atamawari_cut

__all__ = ["KisoInputs", "read_inputs", "KisoRun", "run", "tumatumi_bunpai"]

_HIYOUSHA = ("kou", "kok", "ren", "sig")


@dataclass
class KisoInputs:
    pol: object
    jukyu: IN.Jukyu
    santei: IN.Santei
    base: IN.BaseData
    econ: object                 # EconAssumptions
    kaiteiritu: np.ndarray       # (YEARS.n, AGES.n) ③の単年度改定率
    max_cut: np.ndarray          # (YEARS.n,)
    dokuzi: Dokuzi               # 年度末値だけ
    upstream: tuple = ()         # 上流の Provenance


def read_inputs(pol, case, nat_dir, emp_kiso_dir, waku_dir, bas_dir, econ_csv, nat_out=None,
                hiyousha_case=None):
    """③は `nat_out`（高速版の `NatOut`）があればそれを、無ければ `nat_dir/data` の港の CSV を読む。"""
    J = IN.Jukyu()
    if nat_out is not None:
        J, noufu = IN.jukyu_from_natout(nat_out, J)
        kaite = nat_out.kokukaite
        D = dokuzi_from_natout(nat_out)
        up = (nat_out.prov,)
    else:
        J, noufu = IN.read_kisonenkin(os.path.join(nat_dir, "data", "KISONENKIN%s-%s-%s" % (case, case, case)), J)
        kaite = read_year_age_table(os.path.join(nat_dir, "data", "KOKUKAITE-%s-%sE.csv" % (case, case)),
                                    2000, first_age=67)
        D = dokuzi_from_table(read_dokuzi_table(
            os.path.join(nat_dir, "data", "DOKUZI%s-%s-%s.csv" % (case, case, case))))
        up = ()
    # 改定率の表に無い年度（③の出力が始まる前）は 1（港の初期値）
    empty = ~kaite.any(axis=1)
    kaite = kaite.copy()
    kaite[empty] = 1.
    hc = hiyousha_case or case
    for s, tag in enumerate(_HIYOUSHA, start=1):
        IN.read_hiyousha(os.path.join(emp_kiso_dir, "kiso.%s-%s-%s_%s" % (hc, case, case, tag)), s, J,
                         first_year=pol.get("kiso.years.first_year") - 1)
    base = IN.read_base_data(os.path.join(bas_dir, "base_data"))
    J.apply_hosei(base.hosei_shin, base.hosei_kyu)
    santei = IN.read_santei_waku(waku_dir, case, noufu, first_year=pol.get("kiso.years.first_year"))
    econ = read_econ_csv(econ_csv)
    max_cut = read_max_cut(os.path.join(waku_dir, "waku%s-m.csv" % case))
    return KisoInputs(pol, J, santei, base, econ, kaite, max_cut, D, up)


def tumatumi_bunpai(pol, santei):
    """妻積の取り崩しと各制度への分配。戻り値 (妻積残額[YEARS.n], 分配[NS, YEARS.n], 分配額[YEARS.n])。
    港: kiso_nenkin/tumatumi_cal_jisseki.py:tumatumi_cal_jisseki"""
    genka = pol.get("kiso.tumatumi_2014")
    y0 = pol.get("kiso.years.tumatumi_nendo")
    n = pol.get("kiso.years.tumatumi_kikan")
    zan = YEARS.zeros()
    prev = genka
    for y in range(y0, y0 + n):
        prev = prev - genka * 1. / n
        zan[YEARS.i(y)] = prev
    bunpai = YEARS.zeros()
    for y, v in pol.get("kiso.tumatumi_bunpai").items():
        bunpai[YEARS.i(int(y))] = v
    out = np.zeros((IN.NS, YEARS.n))
    St = santei.by_gou
    tot, al = santei.total, santei.all
    for y in range(pol.get("kiso.years.kaishi1") - 1, y0 + n):
        i = YEARS.i(y)
        out[0, i] = bunpai[i] / 2. * St[0, i, 0] / al[i]
        g23 = (St[:, i, 1] + St[:, i, 2]).sum()
        for s in range(1, IN.NS):
            out[s, i] = bunpai[i] / 2. * (tot[s, i] / al[i] + (St[s, i, 1] + St[s, i, 2]) / g23)
    return zan, out, bunpai


@dataclass
class KisoRun:
    out: KisoOut
    inp: KisoInputs
    E: object                    # KisoEcon
    D: Dokuzi
    tumatumi_zan: np.ndarray
    tumatumi: np.ndarray         # (NS, YEARS.n)
    tumitate_b: np.ndarray       # 調整前の積立金
    kyufu_b: object
    kyo_b: object                # Kyoshutu（調整前。⑤へ渡すのはこれ）
    sol: object                  # tyousei.Solution
    kyufu_a: object
    kyo_a: object
    kafu_cut: np.ndarray         # (YEARS.n, 3)
    tokubetu_cut: np.ndarray     # (YEARS.n,)
    kokatu_nendo: int


def _tumitate_before(pol, E, D, kyo, santei, tumatumi_kokunen, first_year):
    """調整前の積立金（`kekka…b`）。港: kiso_nenkin/printout.py:printout（`cut_ba == 0`）"""
    oku = {int(k): v for k, v in pol.get("kiso.tumitate_oku").items()}
    tm0_year = max(oku)
    income = (D.hokenryou_y + D.fuka_hokenryou_y + kyo.kyoshutukin_kokko[0, :, 0, 0]
              + tumatumi_kokunen + D.yuushi + D.kodomo_noufukin)
    outgo = (kyo.kyoshutukin[0, :, 0, 0] + D.ichijikin[:, 0] + D.ichijikin[:, 1] * 3. / 4.
             + D.kafu[:, 0] + D.kafu[:, 1] + D.fuka_sum * 3. / 4. + D.fukushi)
    tm = fund_path(oku[tm0_year] * 1e8, YEARS.i(tm0_year) + 1, income, outgo, E.interest_rate)
    for y, v in oku.items():
        tm[YEARS.i(y)] = v * 1e8
    return tm


def run(inp, case, carry=None, d_macro=None, tougou=None):
    """④を通しで回す。`carry` キャリーオーバー、`d_macro` 名目下限撤廃、`tougou` 調整期間一致。
    省略なら policy の `options.*`。"""
    pol = inp.pol
    opt = options_of(pol)
    carry = opt.carry if carry is None else carry
    d_macro = opt.dmacro if d_macro is None else d_macro
    tougou = opt.tougou if tougou is None else tougou
    first_year = pol.get("kiso.years.first_year")            # 2021
    i0 = YEARS.i(first_year)
    santei = inp.santei
    E = kiso_econ(pol, inp.econ, inp.kaiteiritu, inp.max_cut, carry, d_macro)

    D = build_dokuzi(pol, inp.dokuzi, E.kaiteiritu, E.kakaku, E.cpi_up, santei, first_year)
    D.yuushi = inp.base.yuushi
    D = build_hokenryou(pol, D, inp.base, E.kakaku, santei)
    zan, tumatumi, _ = tumatumi_bunpai(pol, santei)

    # ---- 調整前 ----
    ones = np.ones((YEARS.n, IN.NA))
    kyufu_b = build_kyufu(pol, inp.jukyu, ones, E.kaiteiritu, first_year)
    kyo_b = tanka_kyoshutukin(kyufu_b, santei, first_year)
    tumitate_b = _tumitate_before(pol, E, D, kyo_b, santei, tumatumi[0], first_year)

    # ---- 終了年度を解く ----
    oku = {int(k): v for k, v in pol.get("kiso.tumitate_oku").items()}
    income = D.hokenryou_y + D.fuka_hokenryou_y + tumatumi[0] + D.yuushi + D.kodomo_noufukin
    base = cut_base(kyufu_b)
    sol = solve(pol, E, base, santei, D, income, oku[max(oku)] * 1e8, first_year)
    for y, v in oku.items():
        sol.tumitate[YEARS.i(y)] = v * 1e8
    x67 = AGES.i(pol.get("kiso.ages.under_67"))
    _, _, _, _, tk_cut, kafu_cut = atamawari_cut(base, sol.cut_ritu, sol.kaiteiritu_cut, santei, D, i0, x67)

    # ---- 調整後 ----
    kyufu_a = build_kyufu(pol, inp.jukyu, sol.cut_ritu, sol.kaiteiritu_cut, first_year)
    kyo_a = tanka_kyoshutukin(kyufu_a, santei, first_year)

    # 国年が枯渇する年度（港は 2022〜2120 の範囲で探す）
    kokatu = -1
    for y in range(pol.get("kiso.years.kaishi1") - 1, YEARS.last - 4):
        if sol.tumitate[YEARS.i(y)] < 0.:
            kokatu = y
            break

    prov = Provenance(case=case, stage="s4", source="fast", policy=policy_hash(pol.data),
                      rev=git_rev(), upstream=inp.upstream)
    tok_nm = with_totals(kyufu_b.nm.tokubetu.sum(axis=2), 1)
    tok_P = with_totals(kyufu_b.P.tokubetu.sum(axis=2), 1)
    out = KisoOut(prov=prov,
                  kyoshutukin={"nendomatu": kyo_b.kyoshutukin_nm, "nendomatu_P": kyo_b.kyoshutukin_P,
                               "kokko_nendomatu": kyo_b.kyoshutukin_kokko_nm,
                               "kokko_nendomatu_P": kyo_b.kyoshutukin_kokko_P,
                               "tokubetu_nendomatu": tok_nm, "tokubetu_nendomatu_P": tok_P},
                  cuta=sol.cut_ritu.copy(),
                  kekka={}, tumatumi={"zan": zan, "bunpai": tumatumi},
                  owari={"s_c_nendo": sol.s_c_nendo, "saisyu_cut": sol.saisyu_cut,
                         "daitai": sol.daitai, "margin": sol.margin, "kokatu_nendo": kokatu,
                         "ok": sol.ok})
    r = KisoRun(out, inp, E, D, zan, tumatumi, tumitate_b, kyufu_b, kyo_b, sol, kyufu_a, kyo_a,
                kafu_cut, tk_cut, kokatu)
    from .output import kekka_series
    out.kekka["b"] = kekka_series(r, "b")
    out.kekka["a"] = kekka_series(r, "a")
    return r
