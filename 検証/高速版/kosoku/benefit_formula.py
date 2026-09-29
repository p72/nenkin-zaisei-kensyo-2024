# -*- coding: utf-8 -*-
"""給付設計 `BenefitFormula`（計画 §J）— 拠出履歴から作る給付の式（設計例）
================================================================================
    earnings_related   現行の報酬比例（②の 13 給付。ここでは作らない。`stages/s2_emp_kyufu`）
    flat               定額（1 人あたりの額 × 受給者数）
    ndc                仮想口座（賃金評価の拠出累積 = 残高）÷ 年金現価率。裁定後は賃金スライド
    minimum_guarantee  基礎 ＋ 比例 が閾値未満なら補填（財源は国庫を既定。勘定の流れは `accounts.py`）

NDC の決定（計画 §J、利用者の決定）: 指標化率 = 名目賃金上昇率（記帳後の残高と裁定後の年金額の両方）、
年金現価率の生命表はコホート別（同梱の `QX-*` を生年で斜めに読む。2125 年度より先の死亡率は最終年度で
据え置き）、現価率の割引率 = 指標化率（裁定後の改定と相殺するので現価率は生存率の和だけになる）、
前取り `frontload` = 0 が既定（変えればケース比較に前取りの効きが混ざる）。移行は「旧制度なら受け取れた
はずの年金額 × コホート別現価率」を初期残高にする（`initial_balance_from_old`。旧制度の並走はしない）。
換算が旧制度の約束と同じ価値かは制度設計の主張なので、これは**設計例**。

世代別の給付負担倍率（`generational_ratio`）: 厚労省方式に合わせ、保険料と給付を名目賃金上昇率で割り引いて
65 歳時点の価値で比べる。給付に国庫負担分を含む／含まない、保険料は本人負担分／事業主負担込みの 2 通り。
**履歴が 2021 年度からしか無いので、拠出の全期間が窓に入る生年度（2006 年度生以降）だけ**が完全。
それより前の生年度は分子・分母とも窓の中の分だけ（`complete` で分かる）。
"""
from dataclasses import dataclass

import numpy as np

from .axis import YEARS, ALL_COHORTS

__all__ = ["cohort_survival", "annuity_divisor", "NDC", "ndc", "initial_balance_from_old", "flat",
           "minimum_guarantee", "generational_ratio"]


def cohort_survival(qp, birth, sex, last_year=2070, max_age=115):
    """生年度 `birth` のコホートの生存率 l[x]（l[0] = 1）。`qp[nensu, x, ss]` は②の `read_qx` の生命表
    （行は年度の添字 = `YEARS.i(年度)`、2015〜2070 年度。`last_year` より先は据え置き。それより前の年度は
    表が無いので死亡 0 と置く。現価率は 65 歳以降の比 l_a / l_65 しか使わないので効かない）。"""
    last = YEARS.i(last_year)
    l = np.ones(max_age + 1)
    for x in range(1, max_age + 1):
        nensu = min(max(birth + (x - 1) - YEARS.first, 0), last)
        q = qp[nensu, x - 1, sex]
        l[x] = l[x - 1] * (1. - q)
    return l


def annuity_divisor(surv, retire_age, growth=0., discount=0.):
    """年金現価率 = Σ_{a ≥ retire} (l_a + l_{a+1}) / 2 / l_retire × ((1 + growth) / (1 + discount))^(a − retire)。
    指標化率 = 割引率なら生存率の和だけ。"""
    l = np.asarray(surv, dtype=np.float64)
    a = np.arange(retire_age, len(l) - 1)
    v = ((1. + growth) / (1. + discount)) ** (a - retire_age)
    return float((((l[a] + l[a + 1]) / 2.) / l[retire_age] * v).sum())


@dataclass
class NDC:
    retire_age: int
    divisor: np.ndarray             # (ALL_COHORTS.n,) コホート別の年金現価率（男女平均）
    balance: np.ndarray             # 裁定時（retire_age の年度末）の残高（賃金評価）
    pension: np.ndarray             # 裁定時の年額（コホート計）
    outgo: np.ndarray               # (ALL_COHORTS.n, YEARS.n) 年度ごとの給付（賃金スライド、生存率で減る）
    per_head: np.ndarray            # 裁定時の 1 人あたり年額（残高 ÷ 裁定時の被保険者数の履歴平均）


def ndc(H, qp, retire_age=65, frontload=0.0, initial_balance=None, max_age=115, last_year=2070):
    """`H`: `history.History`。`initial_balance[c]`（移行: 旧制度の年金額 × 現価率）があれば残高に足す。
    `frontload` は現価率の割引に上乗せする率（0 が既定）。"""
    NC, NY = H.cum_indexed.shape
    ys = YEARS.labels()
    div = np.zeros(NC); bal = np.zeros(NC); pen = np.zeros(NC); head = np.zeros(NC)
    outgo = np.zeros((NC, NY))
    for c in range(NC):
        birth = ALL_COHORTS.first + c
        yr = birth + retire_age
        if yr < YEARS.first or yr > YEARS.last:
            continue
        i = YEARS.i(yr)
        surv = [cohort_survival(qp, birth, s, last_year, max_age) for s in (1, 2)]
        lm = (surv[0] + surv[1]) / 2.
        div[c] = annuity_divisor(lm, retire_age, growth=0., discount=frontload)
        b = H.cum_indexed[c, i - 1] if i > 0 else 0.
        if initial_balance is not None:
            b += initial_balance[c]
        bal[c] = b
        if div[c] > 0.:
            pen[c] = b / div[c]
        n_ins = H.insured[c, :i].max() if i > 0 else 0.
        head[c] = pen[c] / n_ins if n_ins > 0 else 0.
        for j in range(i, NY):
            age = ys[j] - birth
            if age > max_age:
                break
            outgo[c, j] = pen[c] * lm[age] / lm[retire_age] * H.ad[j] / H.ad[i]
    return NDC(retire_age, div, bal, pen, outgo, head)


def initial_balance_from_old(old_pension_at_retire, divisor):
    """移行の初期残高: 旧制度なら裁定時に受け取れたはずの年額（コホート計）× コホート別現価率。"""
    return np.asarray(old_pension_at_retire, dtype=np.float64) * np.asarray(divisor, dtype=np.float64)


def flat(amount_per_head, recipients, ad=None, base_i=None):
    """定額: 1 人あたりの額（基準年度価格）× 受給者数 `recipients[c, y]`。`ad` があれば賃金スライド。"""
    r = np.asarray(recipients, dtype=np.float64)
    out = amount_per_head * r
    if ad is not None:
        out = out * (ad / ad[base_i])[None, :]
    return out


def minimum_guarantee(pension_per_head, floor):
    """最低保障の補填額（1 人あたり）: max(0, 閾値 − 年金額)。財源は国庫を既定（`accounts.py` の流れで選ぶ）。"""
    return np.maximum(0., floor - np.asarray(pension_per_head, dtype=np.float64))


def generational_ratio(H, benefits, at_age=65, employer=True, births=None):
    """世代別の給付負担倍率。`benefits[c, y]` コホート計の給付（年度）。`at_age` 歳時点の価値で
    Σ 給付 × ad[at] / ad[y] ÷ Σ 拠出 × ad[at] / ad[y]（拠出は事業主込み。`employer=False` で本人分＝半分）。
    戻り値 {生年度: (倍率, complete)}。complete は拠出の全期間（15 歳〜）と給付（100 歳まで）が窓に入るか。"""
    ad = H.ad
    out = {}
    births = births or range(ALL_COHORTS.first, ALL_COHORTS.last + 1)
    for birth in births:
        c = ALL_COHORTS.i(birth)
        yat = birth + at_age
        if not (YEARS.first <= yat <= YEARS.last):
            continue
        ia = YEARS.i(yat)
        w = np.where(ad > 0., ad[ia] / np.where(ad > 0., ad, 1.), 0.)
        con = float((H.contrib[c] * w).sum()) * (1. if employer else 0.5)
        ben = float((benefits[c] * w).sum())
        if con <= 0.:
            continue
        complete = (birth + 15 >= H.first_year) and (birth + 100 <= YEARS.last)
        out[birth] = (ben / con, complete)
    return out
