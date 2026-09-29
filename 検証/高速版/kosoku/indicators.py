# -*- coding: utf-8 -*-
"""看板の指標（計画 §H「指標」）— ⑤の台帳 `Cc` と経済前提から
====================================================================
    所得代替率・終了年度           ⑤ `final_rate` / `owari`（既定。公表値と比べられる唯一の指標）
    保険料 ÷ 総報酬（実効料率）     Σ保険料収入 ÷ Σ総報酬額（制度計と制度別）。賦課方式なら解いた毎年の率
    給付総額 ÷ GDP                 Σ支出計 ÷ 名目 GDP。GDP は yaml `gdp.base`（内閣府 SNA 確報、10 億円）の
                                   基準年（2024 年度）を**名目賃金上昇率で延ばす**（経済前提の CSV に GDP の
                                   成長率が無いので近似。README に明記）
    積立度合・積立金の実質額        前年度末積立金 ÷ 当年度支出、積立金 ÷ 物価指数（2024 年度価格）

構造を変えた設定（`kosoku/balance.py`）にも同じ式が当たる。
"""
import numpy as np

from .axis import YEARS

__all__ = ["indicators"]


def indicators(run, pol=None):
    """`run`: `stages.s5_emp_shushi.run.ShushiRun`。戻り値は {指標名: {年度: 値}}（制度計）と `final`。"""
    from .stages.s5_emp_shushi.shushi import C
    pol = pol or run.inp.pol
    Cc, E = run.Cc, run.E
    ys = YEARS.labels()
    i1, ie = YEARS.i(run.inp.ks) + 1, YEARS.i(run.inp.ke)
    tot = Cc.sum(axis=0)
    sl = slice(i1, ie + 1)
    out = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        rate = np.where(tot[C.SOHOSHU] > 0., tot[C.HOKENRYO] / tot[C.SOHOSHU], np.nan)
        doai = np.full(YEARS.n, np.nan)
        doai[1:] = np.where(tot[C.SHISHUTU, 1:] > 0., tot[C.TUMITATE, :-1] / tot[C.SHISHUTU, 1:], np.nan)
    # GDP: 基準年の名目値を名目賃金上昇率で延ばす（近似）
    G = pol.get("gdp.base")
    gy = max(int(y) for y in G)
    gdp = np.full(YEARS.n, np.nan)
    gi = YEARS.i(gy)
    gdp[gi] = float(G[str(gy)] if str(gy) in G else G[gy]) * 1e9
    for i in range(gi + 1, YEARS.n):
        gdp[i] = gdp[i - 1] * (1. + E.h[i - 1])
    for i in range(gi - 1, -1, -1):
        y = ys[i]
        v = G.get(str(y), G.get(y))
        gdp[i] = float(v) * 1e9 if v is not None else np.nan
    benefit_gdp = tot[C.SHISHUTU] / gdp
    real_fund = tot[C.TUMITATE] / E.id_cid * E.id_cid[YEARS.i(gy)]
    def series(v):
        return {int(ys[i]): float(v[i]) for i in range(i1, ie + 1) if np.isfinite(v[i])}
    out["premium_rate"] = series(rate)
    out["benefit_to_gdp"] = series(benefit_gdp)
    out["fund_ratio"] = series(doai)
    out["fund_real"] = series(real_fund)
    out["gdp"] = series(gdp)
    out["final"] = dict(run.out.final_rate, kend_h=run.out.owari["kend_h"], kend_t=run.out.owari["kend_t"],
                        rule=run.sol.rule, premium_rate=run.sol.premium_rate)
    if run.sol.rates is not None:
        out["payg_rates"] = {name: series(run.sol.rates[s]) for s, name in enumerate(("kou", "kok", "ren", "sig"))}
    return out
