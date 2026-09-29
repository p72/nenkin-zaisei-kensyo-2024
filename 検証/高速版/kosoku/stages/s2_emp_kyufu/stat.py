# -*- coding: utf-8 -*-
"""②の締め — 老先振替・年度間平均・「計」（移植版 `rousaki.cpp` `stat.cpp` `outkn.cpp` の前半）
====================================================================================================
種別のループが終わったあと、制度ごとに 1 回。

    rousaki   80〜114 歳の遺族厚生年金のうち在職支給率が足元より下がったぶんを
              配偶者側（反対の性）の老齢厚生年金（i = 1〜4）へ振り替える（併給調整）
    stat      年度末の値を年度間の平均に直し（`d3x` の人数は前年度末との平均、報酬総額は
              6:6（共済 5:7、適用拡大の年度は拡大前の値と）、被保険者数は単純平均）、
              62 歳以下を 63 歳に寄せ、性別（s = 0）と給付（i = 0）の「計」を作る。
              基礎年金拠出金の算定対象 `kfprx` もここで作る
    outkn_collapse  ④へ渡す `okiso2x` の 62 歳以下を 63 歳に寄せる

港: emp_kyufu/stat.py:stat
仕様: §7.2（⑤への受け渡し）
"""
import numpy as np

from ...axis import YEARS
from .inputs import NX, NI
from .shke import D3X_COLS, D3XS_COLS, _C, _CS

__all__ = ["rousaki", "stat", "outkn_collapse"]

_JJ_MAP = {7: 7, 11: 9, 13: 13, 17: 15}          # 遺族の列 → 老齢の列（5・11・17… は 2 つ手前へ）


def rousaki(ctxs, ag):
    """老齢先充てへの振り替え。`ctxs`: {s: Ctx}。港: emp_kyufu/rousaki.py:rousaki"""
    c0 = next(iter(ctxs.values()))
    KIJ, KE, pseid = c0.KIJ, YEARS.n - 1, c0.pseid
    sik = c0.sik
    ss_list = (1, 2, 3) if pseid == 0 else (1, 2)
    for k in range(KIJ + 1, KE + 1):
        xs = np.arange(80, 115)
        xs = xs[(xs >= 66 + k - 7) & (xs <= 95 + k - KIJ)]
        if len(xs) == 0:
            continue
        sinrou = np.zeros((4, 5, len(xs)))
        for s in ss_list:
            s3 = 2 if s == 2 else 1
            for i in range(1, 5):
                v = sum(ag.d3xs[k, xs, s, i, _CS[j]] for j in (7, 8, 9, 10)) * (1. - sik[k, xs, s3, i, 1])
                sinrou[s, 0] += v
                sinrou[s, i] += v
        z13 = sinrou[1, 0] + sinrou[3, 0] <= 0.
        sinrou[1, 0][z13] = 1.; sinrou[1, 1][z13] = 1.
        z2 = sinrou[2, 0] <= 0.
        sinrou[2, 0][z2] = 1.; sinrou[2, 1][z2] = 1.
        for j, jj in _JJ_MAP.items():
            for s in ss_list:
                s3 = 2 if s == 2 else 1
                rtemp = np.maximum(0., sik[KIJ, xs, s3, 11, 1] - sik[k, xs, s3, 11, 1])
                dtemp = ag.d3xs[k, xs, s, 11, _CS[j]] * rtemp
                if jj != j:
                    dtemp = dtemp * (1. - ctxs[s].K.rc[k, xs])
                dtemp = np.where(dtemp > 0., dtemp, 0.)
                for ss in ss_list:
                    if (s == 2) == (ss == 2):
                        continue
                    rtemp2 = (sinrou[1, 0] + sinrou[3, 0]) if ss != 2 else sinrou[2, 0]
                    for i in range(1, 5):
                        ag.d3x[k, xs, ss, i, _C[jj]] += dtemp * sinrou[ss, i] / rtemp2


def stat(ctxs, ag):
    """年度間の平均と「計」。港: emp_kyufu/stat.py:stat"""
    c0 = next(iter(ctxs.values()))
    pol, KIJ, KE, pseid = c0.pol, c0.KIJ, YEARS.n - 1, c0.pseid
    xa = int(pol.get("kounen.ages.xa"))                # 64: これ未満は 63 歳に寄せる
    xc = xa - 1
    d3x, d3xs = ag.d3x, ag.d3xs
    # ---- 人数（列 0）は前年度末の 1 歳下との平均 ----
    old = d3x[..., _C[0]].copy()
    new = old.copy() / 2.
    new[KIJ:, 1:] = (old[KIJ - 1:KE, :-1] + old[KIJ:, 1:]) / 2.
    d3x[KIJ:, :, :, :, _C[0]] = new[KIJ:]
    # ---- 62 歳以下を 63 歳へ、小さい列は 0 に ----
    for n, j in enumerate(D3X_COLS):
        if j != 0:
            tot = d3x[KIJ:, :, :, :, n].sum(1)                       # (k, s, i)
            d3x[KIJ:, :, :, :, n] *= (tot >= 1.0e-6)[:, None, :, :]
        d3x[KIJ:, xc, :, :, n] += d3x[KIJ:, :xc, :, :, n].sum(1)
        d3x[KIJ:, :xc, :, :, n] = 0.
    for n in range(len(D3XS_COLS)):
        d3xs[KIJ:, xc, :, :, n] += d3xs[KIJ:, :xc, :, :, n].sum(1)
        d3xs[KIJ:, :xc, :, :, n] = 0.
    # ---- 拠出金の算定対象 kfprx ----
    x = np.arange(NX)
    kf = ag.kfprx
    for s in (1, 2, 3):
        kk = np.full((NX, NI), c0.sd.ee[1] if s != 3 else c0.sd.ee[2])
        for i in (2, 4, 6, 8):
            kk[x < 65, i] = 0.
        tot = sum(d3x[KIJ:, :, s, :, _C[j]] for j in (13, 14, 15, 16, 17, 18))     # (k, x, i)
        kf[KIJ:, :, s, :, 0] = tot * kk[None]
        kf[KIJ:, :, s, :, 1] = d3x[KIJ:, :, s, :, _C[13]] * kk[None]
        kf[KIJ:, :, s, :, 2] = kf[KIJ:, :, s, :, 0] - kf[KIJ:, :, s, :, 1]
        for i in (2, 4, 6, 8):
            kf[KIJ:, :65, s, i, :] = 0.
    # ---- 「計」（s = 0, i = 0）----
    for a in (d3x, d3xs, kf):
        a[KIJ:, :, 0, :, :] = 0.; a[KIJ:, :, :, 0, :] = 0.
        a[KIJ:, :, 1:, 0, :] = a[KIJ:, :, 1:, 1:, :].sum(3)
        a[KIJ:, :, 0, 1:, :] = a[KIJ:, :, 1:, 1:, :].sum(2)
        a[KIJ:, :, 0, 0, :] = a[KIJ:, :, 1:, 1:, :].sum((2, 3))
    # ---- 報酬総額・被保険者数の年度間平均 ----
    A = ag.ks
    raw = {n: v.copy() for n, v in A.items()}
    K1 = slice(KIJ + 1, KE + 1); K0 = slice(KIJ, KE)
    A["aal"][K1] = raw["a"][K1] + raw["aiku"][K1]
    # 適用拡大の年度（2024年10月と、レバーならオプションの年度も）は当年度に `*dum`（拡大前）を使う
    part_years = [c0.partyr3] + ([c0.partyr4] if c0.flg_part >= 1 and c0.partyr4 >= 0 else [])
    for nm in ("a", "aiku", "a60", "a65", "a70", "a75", "a85"):
        if pseid in (1, 4):
            A[nm][K1] = (5. * raw[nm][K0] + 7. * raw[nm][K1]) / 12.
        else:
            A[nm][K1] = (6. * raw[nm][K0] + 6. * raw[nm][K1]) / 12.
            if pseid == 0:
                for p in part_years:
                    A[nm][p] = (6. * raw[nm][p - 1] + 6. * raw[nm + "dum"][p]) / 12.
    if pseid == 0:
        for nm in ("apart", "aikupart", "a60part", "a65part", "a70part", "a75part", "a85part"):
            for p in part_years:
                A[nm][p] = (6. * raw[nm][p - 1] + 6. * raw[nm][p]) / 12.
                A[nm][p - 1] = 0.
    for nm in ("ap", "appart", "at", "ap65", "ap70", "ap75", "ap85", "appart65", "appart70", "appart75", "appart85"):
        A[nm][K1] = (raw[nm][K0] + raw[nm][K1]) / 2.
    for nm in ("a", "ap", "appart", "at", "aiku", "a60", "a65", "a70", "a75", "a85", "ap65", "appart65",
               "ap70", "appart70", "ap75", "appart75", "ap85", "appart85"):
        A[nm][KIJ, :] = 0.
    ag.gee[KIJ] = 0.; ag.geept[KIJ] = 0.
    for nm in A:
        A[nm][K1, 0] = A[nm][K1, 1:].sum(1)
    ag.gee[K1, 0] = ag.gee[K1, 1:].sum(1); ag.geept[K1, 0] = ag.geept[K1, 1:].sum(1)


def outkn_collapse(ctxs, ag):
    """④へ渡す `okiso2x` の 62 歳以下を 63 歳へ。港: emp_kyufu/outkn.py:outkn（前半）"""
    c0 = next(iter(ctxs.values()))
    KIJ = c0.KIJ
    o = ag.okiso2x
    o[KIJ:, 63, 1:3, 1:4, 1:7] += o[KIJ:, :63, 1:3, 1:4, 1:7].sum(1)
    o[KIJ:, :63, 1:3, 1:4, 1:7] = 0.
