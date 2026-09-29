# -*- coding: utf-8 -*-
"""均衡の解法 `BalanceRule` — (動かすもの, 合わせる条件) の組（計画 §H）
==========================================================================
現行の⑤は「保険料率を固定し、給付水準（マクロ経済スライドの終了年度）を動かして、
2125 年度の積立度合が 1 になる点を探す」。これを **lever × target** に分ける。

    lever   benefit_level   給付水準（厚年の調整終了年度。④の基礎は据え置き）
            premium_rate    保険料率（`premium_from` 年度から一定の率。4 制度と第3種に同じ率）
    target  fund_ratio_at_end   積立金[終期−1] = 支出[終期] × Ca（現行の有限均衡）
            annual_balance      各年度 収入 = 支出 ＋ 積立金の実質維持分（賦課方式。解法なし、逐次）
            perpetual           終期で定常: 収支差[終期] = 積立金[終期−1] × g（永久均衡の近似。
                                g は終期の名目賃金上昇率。終期以降は人口・経済前提を据え置く）

yaml `shushi.balance.rule` の名前 → 組:

    current            benefit_level × fund_ratio_at_end   （既定 = 移植版と一致）
    premium            premium_rate  × fund_ratio_at_end   給付固定・料率均衡（天井なし）
    payg               premium_rate  × annual_balance      賦課方式（積立金は物価で実質一定）
    perpetual          benefit_level × perpetual           永久均衡（給付水準を動かす）
    perpetual_premium  premium_rate  × perpetual           永久均衡（料率を動かす）

「給付固定」は、厚年の累積調整率を実績年度（2023・2024 年度）までで止めた状態（`fixed_benefit_Sh`）。
④の基礎年金側は現行の解法のまま（`St0`）なので、ここで動くのは報酬比例（厚年 4 制度）だけ。
構造を変えた設定に正解（移植版）は無い。言えるのは (1) 恒等式が成り立つ (2) 既定に戻せば移植版に
戻る (3) 玩具ケース（`tests/toy/`）が手計算と合う、の 3 つ。
`Options` の 7 本のレバー（§11.1）は BalanceRule と直交する。
"""
from dataclasses import dataclass

import numpy as np

from .axis import YEARS, AGES

__all__ = ["BalanceRule", "RULES", "rule_of", "fixed_benefit_Sh", "margin_fund_ratio", "margin_stationary",
           "solve_premium", "solve_payg"]

RULES = {
    "current": ("benefit_level", "fund_ratio_at_end"),
    "premium": ("premium_rate", "fund_ratio_at_end"),
    "payg": ("premium_rate", "annual_balance"),
    "perpetual": ("benefit_level", "perpetual"),
    "perpetual_premium": ("premium_rate", "perpetual"),
}


@dataclass(frozen=True)
class BalanceRule:
    name: str
    lever: str
    target: str
    premium_from: int          # 料率を動かす最初の年度
    payg_fund: str             # 賦課方式で積立金をどう保つか（real_constant: 物価で実質一定）
    growth: str                # 永久均衡の g（wage: 終期の名目賃金上昇率）

    @property
    def benefit_fixed(self):
        return self.lever == "premium_rate"


def rule_of(pol):
    """policy の `shushi.balance.*` → `BalanceRule`。無ければ current。"""
    B = pol.get("shushi.balance", {})
    name = str(B.get("rule", "current"))
    if name not in RULES:
        raise ValueError("shushi.balance.rule = %r（%s のどれか）" % (name, "/".join(RULES)))
    lever, target = RULES[name]
    return BalanceRule(name=name, lever=lever, target=target,
                       premium_from=int(B.get("premium_from", 2027)),
                       payg_fund=str(B.get("payg_fund", "real_constant")),
                       growth=str(B.get("growth", "wage")))


def fixed_benefit_Sh(rh, kijun_i, k_jis_i, ie, x_lo):
    """給付固定: 実績年度（`k_jis_i`）まで毎年の調整率を掛け、あとはコホートでずらすだけ（調整しない）。
    `rh[YEARS.n, AGES.n]` 毎年の名目下限つき調整率、`x_lo` 63 歳の添字。"""
    Sh = np.ones((YEARS.n, AGES.n))
    for i in range(kijun_i + 1, ie + 1):
        if i <= k_jis_i:
            Sh[i, x_lo] = Sh[i - 1, x_lo] / rh[i, x_lo]
            Sh[i, x_lo + 1:] = Sh[i - 1, x_lo:-1] / rh[i, x_lo + 1:]
        else:
            Sh[i, x_lo] = Sh[i - 1, x_lo]
            Sh[i, x_lo + 1:] = Sh[i - 1, x_lo:-1]
    return Sh


# ---------------------------------------------------------------- 合わせる条件（制度計）

def margin_fund_ratio(Cc, C, kend_i, ca):
    """有限均衡: 積立金[kend−1] − 支出[kend] × Ca。"""
    return Cc[:, C.TUMITATE, kend_i - 1].sum() - Cc[:, C.SHISHUTU, kend_i].sum() * ca


def margin_stationary(Cc, C, ie, g):
    """永久均衡の近似: 収支差[ie] − 積立金[ie−1] × g（終期で積立金が名目 g で伸びる定常状態）。"""
    return Cc[:, C.SHUSHISA, ie].sum() - Cc[:, C.TUMITATE, ie - 1].sum() * g


# ---------------------------------------------------------------- 料率を動かす

def solve_premium(apply_rate, evaluate, r0, r1, tol, n_sec=14, n_max=62):
    """料率 r を割線法（`n_sec` 回）→ 二分法で解く。`apply_rate(r)` が台帳の保険料収入を書き換え、
    `evaluate()` が合わせる条件の余裕 f（符号つき）を返す。収束は |f| < tol。
    戻り値 (r, f, 反復回数, 収束したか)。二分法に入るときは f の符号が変わる区間を持つ。"""
    apply_rate(r0); f0 = evaluate()
    apply_rate(r1); f1 = evaluate()
    n = 0
    r, f = r1, f1
    if abs(f1) < tol:
        return r1, f1, 0, True
    # 符号の変わる区間を作る（料率が高いほど f は増える）
    while f0 * f1 > 0. and n < n_max:
        if f1 > 0.:
            r0, f0 = r1, f1
            r1 = r1 - 0.05
        else:
            r0, f0 = r1, f1
            r1 = r1 + 0.05
        apply_rate(r1); f1 = evaluate()
        n += 1
    ok = False
    while n < n_max and not ok:
        if n < n_sec and f1 != f0:
            r = r1 - f1 * (r1 - r0) / (f1 - f0)
            if not (min(r0, r1) <= r <= max(r0, r1)):
                r = (r0 + r1) / 2.
        else:
            r = (r0 + r1) / 2.
        apply_rate(r); f = evaluate()
        if abs(f) < tol:
            ok = True
        elif f * f0 > 0.:
            r0, f0 = r, f
        else:
            r1, f1 = r, f
        n += 1
    return r, f, n, ok


def solve_payg(Cc, C, E, kijun_i, i_from, ie, fund_growth):
    """賦課方式（逐次）。各制度・各年度で

        保険料 P = [F (φ − ri) − (K + T − X)(1 + ri2)] / (1 + ri2)

    F 前年度末積立金、φ 積立金の名目維持率（`fund_growth[i]`。物価で実質一定なら物価上昇率）、
    ri 積立金の利回り、ri2 年度内の収支に掛かる利回り、K 国庫＋支援＋納付金、T 妻積、X 支出。
    このとき 収入 − 支出 = F φ（積立金が φ で伸びる）。戻り値は料率 P ÷ 総報酬 `(NSYS, YEARS.n)`。
    `Cc` の保険料・運用・収入・収支差・積立金を書き換える。"""
    rates = np.zeros(Cc.shape[::2])
    for i in range(max(i_from, kijun_i + 1), ie + 1):
        F = Cc[:, C.TUMITATE, i - 1]
        K = Cc[:, C.KOKKO, i] + Cc[:, C.SHIEN_IN, i] + Cc[:, C.NOFUKIN, i]
        T = Cc[:, C.TUMATUMI, i]
        X = Cc[:, C.SHISHUTU, i]
        phi = fund_growth[i]
        P = (F * (phi - E.ri[i]) - (K + T - X) * (1. + E.ri2[i])) / (1. + E.ri2[i])
        Cc[:, C.HOKENRYO, i] = P
        Cc[:, C.UWANOSE, i] = 0.
        Cc[:, C.PART_HOKENRYO, i] = 0.
        unyo = F * E.ri[i] + (P + K - X + T) * E.ri2[i]
        Cc[:, C.UNYO, i] = unyo
        Cc[:, C.SHUNYU, i] = P + unyo + K + T
        Cc[:, C.SHUSHISA, i] = Cc[:, C.SHUNYU, i] - X
        Cc[:, C.TUMITATE, i] = F + Cc[:, C.SHUSHISA, i]
        with np.errstate(divide="ignore", invalid="ignore"):
            rates[:, i] = np.where(Cc[:, C.SOHOSHU, i] > 0., P / Cc[:, C.SOHOSHU, i], 0.)
    return rates
