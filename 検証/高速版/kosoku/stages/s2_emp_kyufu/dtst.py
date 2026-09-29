# -*- coding: utf-8 -*-
"""②の足元（基準年度の実績）を推計の出発点に整える（`dtst.cpp`）
==================================================================
種別ごとに `hk`（被保険者）と `jk`（受給権者）の足元を `State` に入れ、

1. 標準報酬の内訳 `z` `ze` `w` `we` の区分を付け替えて「計」と整合させる
2. 115歳を114歳に寄せ、「計」から繰上げ繰下げの内訳を引いて 65歳裁定の残りを出す
3. 繰上げ減額・繰下げ増額・加給・有子割合で**割り戻して**減額前・加算前の
   1人あたり年金額にする
4. 実績に合わせる補正率（yaml `kounen.dtst.hosei`）を掛ける
5. 従前額保障（`f[..., 10]`）を賃金・物価の実績で足元まで引き直す
6. パート（`w[..., 2]` `[3]`）を「計」の比で按分する

港の癖で残すもの: E25 — 8割下限 `f_min` の従前額保障は生年に関係なく 2005〜2021 年度を
全部掛ける（`f` は「その生年が 67 歳以下の年度」だけ）。yaml `kounen.dtst.fmin_all_years`。

港: emp_kyufu/dtst.py:dtst
仕様: §5.6（足元の整理）
"""
import numpy as np

from ...axis import YEARS
from .inputs import NX, NT, NXX, NI, NJ
from .state import State

__all__ = ["dtst", "hosei_rates"]

J_JUZEN = 10                      # 従前額保障の内訳


def hosei_rates(pol, system, flg_hantei=0):
    """実績に合わせる補正率 (tmsi[i], tmsj[j], tmso[j])。港: emp_kyufu/dtst.py:dtst"""
    tmsi = np.ones(NI); tmsj = np.ones(NJ); tmso = np.ones(NJ)
    tmsi[0] = tmsj[0] = tmso[0] = 0.
    if flg_hantei != 0:
        return tmsi, tmsj, tmso
    H = pol.get("kounen.dtst.hosei")[system]
    tmsj[15] = H["j15"]; tmsj[16] = H["j16"]; tmsj[4] = H["j4"]; tmso[4] = H["o4"]
    tmsj[5] = tmsj[23] = tmsj[4]
    tmso[5] = tmso[23] = tmso[4]
    tmsj[17] = tmsj[18] = tmsj[19] = tmsj[20] = tmsj[15]
    for i, v in H["i"].items():
        tmsi[int(i)] = v
    return tmsi, tmsj, tmso


def dtst(pol, st, hk, jk, sd, ku, K, E, pseid, konen, s, sk, system):
    """`st`: `State`（外枠入り）。`hk` `jk`: 足元、`sd` `ku` `K` `E`: 制度定数・繰上げ率・
    基礎率・改定率、`sk`: 支給開始年齢。基準年度 KIJUN の値を `st` に入れて返す。"""
    KIJ = YEARS.i(pol.get("kounen.years.kijun"))
    C = pol.get("kounen.cohorts")
    keika_last = int(C["keika_last"])                     # 1946: これ以前の生まれが経過措置
    hikrate = float(pol.get("kounen.rates.hikrate"))
    xs = np.arange(NX)
    coh = YEARS.label(KIJ) - xs                            # 年齢 x の生年度
    new_law = coh > keika_last                            # 港: KIJUN − x > −54

    # ---- 被保険者 ----
    st.g[:] = hk.g; st.ge[:] = hk.ge; st.gpt[:] = hk.gpt; st.bb[:] = hk.bb; st.bbpt[:] = hk.bbpt
    st.z[:] = hk.z; st.ze[:] = hk.ze; st.w[:] = hk.w; st.we[:] = hk.we
    X = slice(15, 75); T = slice(0, 51)
    for v in (st.z, st.ze):
        a = v[X, T]                                        # (x, t, i, j) の view
        a[..., 9] = a[..., 3]
        a[..., 3] = a[..., 3] + a[..., 4]
        a[..., 4] = a[..., 5]; a[..., 5] = a[..., 6]; a[..., 6] = a[..., 7]; a[..., 7] = a[..., 8]
        a[..., 8] = 0.
        nl = new_law[X][:, None, None]
        a[..., 1] = np.where(nl & (a[..., 1] > 0.), 0., a[..., 1])
        tmp = a[..., 1] + a[..., 2] + a[..., 3] + a[..., 4]
        tot = a[..., 0]
        lower = tot < tmp
        higher = (tot > tmp)
        scale = np.where(higher & (tmp > 0.), tot / np.where(tmp > 0., tmp, 1.), 1.)
        a[..., 1:5] = a[..., 1:5] * scale[..., None]
        a[..., 0] = np.where(lower, tmp, np.where(higher, np.where(tmp > 0., a[..., 1:5].sum(-1), 0.), tot))
    for v in (st.w, st.we):
        a = v[X, T, 0]                                     # (x, t, j, ii)
        for ii in (0, 1):
            a[..., 7, ii] = a[..., 3, ii]
            a[..., 3, ii] = a[..., 3, ii] + a[..., 4, ii]
            a[..., 4, ii] = a[..., 5, ii]
            a[..., 5, ii] = 0.
            a[..., 0, ii] = a[..., 0, ii] - a[..., 4, ii]
    a = st.we[X, T, 0]
    a[..., 0, 2] -= a[..., 4, 2]
    a[..., 0, 3] -= a[..., 4, 3]

    # ---- 受給権者 ----
    st.r[:, :11] = jk.r; st.f[:, :11] = jk.f; st.f_hik[:, :11] = jk.f_hik; st.f_min[:, :11] = jk.f_min
    st.hn[:, :11] = jk.hn
    wn = np.zeros((NX, NXX, NI, 5, 2)); wn[:, :11] = jk.wn
    for v in (st.r, st.hn, st.f, st.f_hik, st.f_min):
        v[114] += v[115]
        v[115] = 0.
    for xx in range(1, 11):                                # 「計」から内訳を引く
        st.r[:, 0, 1:5] -= st.r[:, xx, 1:5]
        for v in (st.f, st.f_hik, st.f_min):
            v[:, 0, 1:5] -= v[:, xx, 1:5]
        st.hn[:, 0, 1:5] -= st.hn[:, xx, 1:5]
        wn[:, 0, 1:5] -= wn[:, xx, 1:5]
    st.r[:, 1:, 5:] = 0.
    for v in (st.f, st.f_hik, st.f_min, st.hn):
        v[:, 1:, 5:] = 0.
    wn[:, 1:, 5:] = 0.
    if konen != 1:
        st.f[:, 0, 9, 12] *= sd.ema[s]
    # 経過措置の生まれ以外は配偶者加給（hn[1]）を子の加給（hn[2]）に寄せる
    for i in range(1, 11):
        xxsl = slice(0, 11) if i < 5 else slice(0, 1)
        a1 = st.hn[new_law, xxsl, i, 1]
        m = a1 > 0.
        st.hn[new_law, xxsl, i, 2] += np.where(m, a1, 0.)
        st.hn[new_law, xxsl, i, 1] = np.where(m, 0., a1)

    # ---- 割り戻し ----
    if konen == 1:
        _warimodoshi_kounen(pol, st, sd, ku, K, sk, KIJ, s)
    else:
        for i in (5, 6, 10):
            st.f[:, :11, i, 19] = 0.
            st.f[:, :11, i, 20] = 0.
        st.f[19:, :11, 13, 17] *= K.rc[KIJ, 19:][:, None]

    # ---- 実績に合わせる補正率 ----
    tmsi, tmsj, tmso = hosei_rates(pol, system)
    for i in range(1, NI):
        xxn = 11 if i < 5 else 1
        if i <= 8 and konen != 1:
            st.f[:71 + KIJ, :xxn, i, 16] = 0.
        for j in (4, 5, 15, 16, 17, 18, 19, 20, 23):
            if (i >= 5 and i not in (9, 11)) and j in (4, 5, 23):
                st.f[:, :xxn, i, j] *= tmso[j]
            else:
                st.f[:, :xxn, i, j] *= tmsj[j]
        for j in (1, 2, 3, 7, 8, 9, 10, 11, 12):
            st.f[:, :xxn, i, j] *= tmsi[i]
        st.f_min[:, :xxn, i, 1] *= tmsi[i]
        st.f_hik[:, :xxn, i, 1] *= tmsi[i]

    # ---- 従前額保障を賃金・物価の実績で足元まで引き直す ----
    D = pol.get("kounen.dtst")
    XX = slice(0, 11); II = slice(1, NI)
    for j in range(2, NJ):
        if j != J_JUZEN:
            st.f_min[:, XX, II, j] = st.f[:, XX, II, j] * D["fmin_ratio"]
    st.f_hik[:, XX, II, J_JUZEN] = st.f[:, XX, II, J_JUZEN]
    chain = _juzen_chain(pol, E, coh)                      # (x,) 生年度ごとの累積係数
    full = _juzen_chain(pol, E, coh, fmin=bool(D["fmin_all_years"]))
    st.f[:, XX, II, J_JUZEN] = st.f_hik[:, XX, II, J_JUZEN] * (hikrate * chain)[:, None, None]
    st.f_min[:, XX, II, J_JUZEN] = st.f_hik[:, XX, II, J_JUZEN] * (hikrate * full * D["fmin_ratio"])[:, None, None]

    # ---- パートを「計」の比で按分 ----
    for v in (st.w, st.we):
        tot = v[14:, :, 0, 0, 0]
        m = tot > 1.0e-6
        for j in (0, 1, 2, 3, 7):
            base = v[14:, :, 0, j, 0]
            for ii in (2, 3):
                with np.errstate(divide="ignore", invalid="ignore"):
                    v[14:, :, 0, j, ii] = np.where(m, base * v[14:, :, 0, 0, ii] / np.where(m, tot, 1.), 0.)

    st.hn[:, :, :, 2] = st.hn[:, :, :, 2] + st.hn[:, :, :, 3] + st.hn[:, :, :, 4]
    st.hn[:, :, :, 3] = 0.
    st.hn[:, :, :, 4] = 0.
    return st


def _juzen_chain(pol, E, coh, fmin=False):
    """従前額保障を足元へ引き直す累積係数（生年度ごと）。

    2004年度までの改定（`base`）と 1999〜2001 年度の特例（`hh2`）を生年度に応じて掛け、
    2005年度〜基準年度は「その年度に 67 歳以下」なら賃金／物価で引き直す。
    `fmin=True` は 8割下限用で、全年度を掛ける（E25）。
    """
    D = pol.get("kounen.dtst.juzen")
    KIJ = YEARS.i(pol.get("kounen.years.kijun"))
    coh = np.asarray(coh)
    out = np.ones(coh.shape)
    for key, facs in sorted((int(k), v) for k, v in D["base"].items()):
        m = coh >= key
        v = np.ones(coh.shape)
        for f in facs:
            v = v * f
        out = np.where(m, v, out)
    has = coh >= min(int(k) for k in D["base"])           # それより前の生まれは引き直さない
    hh2 = E.hh2
    n_hh2 = np.zeros(coh.shape, dtype=int)
    for key, n in sorted((int(k), v) for k, v in D["hh2_count"].items()):
        n_hh2[coh >= key] = int(n)
    for i in range(3):
        out = out * np.where(n_hh2 > i, 1. + hh2[i], 1.)
    out = np.where(has, out / D["divisor"], 1.)
    if fmin:                                               # 8割下限は基準年度の生まれと同じ扱い（E25）
        out = np.full(coh.shape, float(out[np.argmax(coh)]))
    k0 = YEARS.i(D["chain_from"])
    age_limit = int(D["chain_age"])
    for kk in range(k0, KIJ + 1):
        ok = np.ones(coh.shape, dtype=bool) if fmin else (YEARS.label(kk) - coh <= age_limit)
        out = np.where(ok, out * (1. + E.hh[kk]) / (1. + E.ci[kk]), out)
    return out


def _warimodoshi_kounen(pol, st, sd, ku, K, sk, KIJ, s):
    """厚生年金の割り戻し。港: emp_kyufu/dtst.py:_warimodoshi_kounen"""
    xs = np.arange(NX)
    coh = YEARS.label(KIJ) - xs
    xxr_a = np.maximum(60, sk.xxr(coh))
    xrb_a = np.maximum(60, sk.xrb(coh))
    ratio32 = sd.adt[3] / sd.adt[2]
    zogaku = float(pol.get("kounen.siml.kurisage_zogaku"))
    for i in range(1, NI):
        ii = {1: 1, 2: 1, 3: 6, 4: 6, 5: 2, 6: 2, 7: 2, 8: 2, 9: 3, 10: 4, 11: 5, 12: 5, 13: 5}[i]
        nxx = 11 if i < 5 else 1
        for x in range(NX):
            xxr = int(xxr_a[x]); xrb = int(xrb_a[x])
            if ii in (1, 6):
                for xx in range(0, min(nxx, 6)):
                    if x >= 60 and xrb > 60 and (65 - xx) >= 60 and (65 - xx) < xrb:
                        rbe = ku.rigbe[s, 65 - xx, xrb, 0]
                        st.f[x, xx, i, 1] /= rbe
                        st.f_hik[x, xx, i, 1] /= rbe
                        st.f_min[x, xx, i, 1] /= rbe
                        st.f[x, xx, i, 3] /= ku.rigk[s, 65 - xx, xxr, 0]
                    if (65 - xx) < xxr and x >= 65 - xx and x < 65 and xxr < 65:
                        st.f[x, xx, i, 2] /= ku.rigd[s, 65 - xx, xxr, 0]
                for xx in range(6, nxx):
                    tmgbe = 1. + zogaku * (xx - 5) * 12.
                    st.f[x, xx, i, 1] /= tmgbe
                    st.f_hik[x, xx, i, 1] /= tmgbe
                    st.f_min[x, xx, i, 1] /= tmgbe
                    st.f[x, xx, i, 3] /= tmgbe
            kd1 = K.kd[KIJ, ii, 1, x]
            if kd1 >= 1.0e-6:
                if 5 <= i <= 13:
                    st.f[x, :nxx, i, 4] /= kd1
                    st.f[x, :nxx, i, 23] /= kd1
                st.f[x, :nxx, i, 19] /= kd1
            kd_sum = K.kd[KIJ, ii, 2, x] + K.kd[KIJ, ii, 3, x] * ratio32
            if kd_sum >= 1.0e-6:
                if 5 <= i <= 13:
                    st.f[x, :nxx, i, 5] /= kd_sum
                st.f[x, :nxx, i, 20] /= kd_sum
                st.f[x, :nxx, i, 21] /= kd_sum
            if i in (11, 12) and x >= 19:
                rc = K.rc[KIJ, x]
                if rc >= 1.0e-6:
                    st.f[x, :nxx, i, 14] /= rc
                    st.f[x, :nxx, i, 17] /= rc
                if 1. - rc >= 1.0e-6:
                    st.f[x, :nxx, i, 18] /= (1. - rc)
