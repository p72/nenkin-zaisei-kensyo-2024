# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/seid.cpp の忠実移植（制度の定数と支給率）
==============================================================
②で2番めに大きい 902 行。やることは大きく4つ。

1. **法定の定数を並べる** — 報酬比例部分の乗率、定額部分の単価と
   生年別読替率、加給年金額、配偶者加給の特別加算、中高齢寡婦加算、
   加入可能年数、障害・遺族の給付乗率、標準報酬の下限など
2. **遺族の失権率**（`yuizor` ファイル）を `rs` に読む
3. **支給率**（`sikur` ファイル）を `sik` に読み、基準年度から将来へ
   伸ばす。繰上げ・繰下げ・裁定遅れの処理もここ
4. `set_hsr()` — **報酬水準**（`hou` ファイル）を `bn` `br` に読み、
   男女差の縮小（`hsr_r`）とパート適用拡大の平均報酬を作る

法定の数値に写し間違いが1つある（J1）
-------------------------------------
`__tmq[]` の11番め（1936年度生まれ）が **`369`** になっている。
公表されている定額部分の生年別読替率では **1.369** なので1桁落ち。
並びは 1413 → **369** → 1327 と、その1点だけで折れる。

移植版は**`369` のまま写す**。目的は原本とのビット一致なので直せない。
正しい値は `_TMQ_HOUTEI` に並べてあるが**使わない**。
詳しくは `検証/原本の不具合.md` の J1。

`flt` が効くのは `simlsaite2.cpp` の4箇所だけで、どれも

    tmf = tmg * fl * flt[生年度] * bd[k][2] * tn

という**従前額保障の定額部分**。1936年度生まれのこの部分が
正しい額の 0.369/1.369 ≒ 27% で計上される。

添字の約束
----------
`kx` は**生年度 − 2000**（`C19(kx) = kx + 100` で配列の添字にする）。
`tmp` `tmp2` `tmq` は `kx + 74` で引くので、先頭が 1926年度（大正15年度）、
20番めが 1945年度（昭和20年度）。1946年度以降は直書きの 1.0 など。

`tmr`（中高齢寡婦加算の読替率）は 40 個で、`kx` が −74〜−35
（1926〜1965年度生まれ）。それより後は 0。

`dtem` を2回使い回している
--------------------------
`set_hsr` を呼ぶ前の大きな `k` ループでは `dtem` は男女別の
伸び率（0.995182 / 1.006545）だが、`flg_siktuika == 0` のブロックでは
**同じ変数を繰上げ・繰下げの減額率／増額率として上書きして使う**。
ブロックの順番が前後すると答えが変わるので、原本の並びをそのまま守る。
"""
import numpy as np

from csvio import join
from glva import G
from sepsstd import roundn, std_max, std_min, c_round
from setconst import BUF_SIZE, KE, KIJUN, KS

__all__ = ["seid"]


# 報酬比例部分の乗率（本来水準）を 10 万倍した値。1926〜1945年度生まれ。
# 1段めの 1000 が 1000分の10.000。1946年度以降は `7.5e-3` 直書き。
_TMP = (
    1000, 986, 972, 958, 944, 931, 917, 904, 891, 879,
    866, 854, 841, 829, 818, 806, 794, 783, 772, 761,
)

# 同（従前額保障）を 100 万倍した値。1段めの 7692 が 1000分の7.692。
# 1946年度以降は `5.481e-3 / hikrate`。
_TMP2 = (
    7692, 7585, 7477, 7369, 7262, 7162, 7054, 6954, 6854, 6762,
    6662, 6569, 6469, 6377, 6292, 6200, 6108, 6023, 5938, 5854,
)

# 定額部分の生年別読替率を 1000 倍した値。1926〜1945年度生まれ。
#
# **11番め（1936年度＝昭和11年度生まれ）が `369`。公表値は 1.369 で、
# 原本の写し間違い。** 直すと C 版とビットが合わなくなるので写す。
# `検証/原本の不具合.md` の J1 を参照。
_TMQ = (
    1875, 1817, 1761, 1707, 1654, 1603, 1553, 1505, 1458, 1413,
    369,  1327, 1286, 1246, 1208, 1170, 1134, 1099, 1065, 1032,
)

# 公表されている正しい並び（日本年金機構「定額部分の単価」）。
# **使わない。** 原本との差が `_TMQ[10]` の1点だけであることを示すために
# 置いてある。
_TMQ_HOUTEI = (
    1875, 1817, 1761, 1707, 1654, 1603, 1553, 1505, 1458, 1413,
    1369, 1327, 1286, 1246, 1208, 1170, 1134, 1099, 1065, 1032,
)

# 中高齢寡婦加算の生年別読替率を 1000 倍した値。1926〜1965年度生まれ。
# 末尾5つが 67 で並ぶ（下限）。
_TMR = (
    1000, 973, 947, 920, 893, 867, 840, 813, 787, 760,
    733, 707, 680, 653, 627, 600, 573, 547, 520, 493,
    467, 440, 413, 387, 360, 333, 307, 280, 253, 227,
    200, 173, 147, 120, 93, 67, 67, 67, 67, 67,
)


def _c19(kx):
    """setconst.C19 と同じ。ここでは名前を短くしておく。"""
    return kx + 100


def seid():
    """seid.cpp:11 の忠実移植。"""
    tmp = _TMP
    tmp2 = _TMP2
    tmq = _TMQ
    tmr = _TMR

    iqp = np.zeros((131, 3))
    dtem = np.zeros(3)
    # shosik は宣言されるだけで一度も使われない（F9 の仲間）
    # shosik = np.zeros(3)

    KIJ = KIJUN

    # ------------------------------------------------------------------
    # 報酬比例部分の乗率（本来水準・従前額保障）
    # ------------------------------------------------------------------
    for kx in range(-74, -54 + 1):
        if kx <= -55:
            G.pre[_c19(kx)] = float(tmp[kx + 74]) * 1.0e-5
        elif kx == -54:
            G.pre[_c19(kx)] = 7.5e-3

    G.pra = G.pre[_c19(-74)]
    G.prb = G.pre[_c19(-54)]

    for kx in range(-74, -54 + 1):
        if kx <= -55:
            G.pres[_c19(kx)] = tmp2[kx + 74] * 1.0e-6
        elif kx == -54:
            G.pres[_c19(kx)] = 5.481e-3 / G.hikrate

    G.pras = G.pres[_c19(-74)]
    G.prbs = G.pres[_c19(-54)]

    # ------------------------------------------------------------------
    # 定額部分の生年別読替率（J1 の写し間違いをそのまま写す）
    # ------------------------------------------------------------------
    for kx in range(-74, KE + 1):
        if kx <= -55:
            G.flt[_c19(kx)] = tmq[kx + 74] * 1.0e-3
        elif -54 <= kx:
            G.flt[_c19(kx)] = 1.0

    # ------------------------------------------------------------------
    # 定額部分の単価と、報酬比例の最低保障
    # ------------------------------------------------------------------
    G.fl1 = 8042.0e+2
    G.minb = 6032.0e+2

    G.fl1 = roundn(G.fl1 * G.ad2[KIJ], -2)
    # `fl` は sepsstd::roundn ではなく C99 の `round()`（1円単位）
    G.fl = c_round(1676.0 * G.ad2[KIJ]) * 12.0
    G.minb = roundn(G.minb * G.ad2[KIJ], -2)

    # ------------------------------------------------------------------
    # 加給年金額（1 配偶者 / 2 第1・2子 / 3 第3子以降）
    # ------------------------------------------------------------------
    G.adt[1] = 2314.0e+2
    G.adt[2] = 2314.0e+2
    G.adt[3] = 771.0e+2

    for ii in range(1, 3 + 1):
        G.adt[ii] = roundn(G.adt[ii] * G.ad2[KIJ], -2)

    # 配偶者加給の特別加算（生年度ごと）
    for kx in range(-74, KE + 1):
        if kx <= -67:
            G.sadt[_c19(kx)] = 0.0e+0
        if -66 <= kx <= -61:
            G.sadt[_c19(kx)] = 341.0e+2
        if kx == -60:
            G.sadt[_c19(kx)] = 683.0e+2
        if kx == -59:
            G.sadt[_c19(kx)] = 1025.0e+2
        if kx == -58:
            G.sadt[_c19(kx)] = 1366.0e+2
        if -57 <= kx:
            G.sadt[_c19(kx)] = 1707.0e+2

    for kx in range(-66, KE + 1):
        G.sadt[_c19(kx)] = roundn(G.sadt[_c19(kx)] * G.ad2[KIJ], -2)

    # 中高齢寡婦加算（配偶者加給の生年別読替）
    for kx in range(-100, KE + 1):
        if kx <= -75:
            G.cadt[_c19(kx)] = 0.0
        elif kx <= -35:
            G.cadt[_c19(kx)] = tmr[kx + 74] * 1.0e-3 * G.adt[1]
        elif -34 <= kx:
            G.cadt[_c19(kx)] = 0.0

    # ------------------------------------------------------------------
    # 寡婦年金（経過的寡婦加算）
    # ------------------------------------------------------------------
    G.wif = 6032.0e+2
    G.wif = roundn(G.wif * G.ad2[KIJ], -2)
    for kx in range(-100, KE + 1):
        if kx <= -74:
            G.wife[_c19(kx)] = G.wif
        elif kx <= -59:
            # 分母の `(kx + 24 + 75)` は int だが、左が double なので
            # 整数除算にはならない
            G.wife[_c19(kx)] = G.wif - G.fl1 * (kx - 1 + 75) / (kx + 24 + 75)
        elif kx <= -45:
            G.wife[_c19(kx)] = G.wif - G.fl1 * (kx - 1 + 75) / 40.0
        elif -44 <= kx:
            G.wife[_c19(kx)] = 0.0

    # ------------------------------------------------------------------
    # 加入可能年数。`flg_sigo >= 1`（基礎45年化）なら cntl が作った
    # `kflcan` に差し替える
    # ------------------------------------------------------------------
    for kx in range(-74, KE + 1):
        G.can[_c19(kx)] = std_min(float(kx) + 75 + 24, 40.0)

        if G.flg_sigo >= 1 and kx >= G.canyr - 60:
            G.can[_c19(kx)] = G.kflcan[KE, _c19(kx)]

    for kx in range(-74, KE + 1):
        if kx <= -72:
            G.can2[_c19(kx)] = 35.0
        elif -71 <= kx <= -67:
            G.can2[_c19(kx)] = 36.0
        elif -66 <= kx <= -57:
            G.can2[_c19(kx)] = 37.0
        elif kx == -56:
            G.can2[_c19(kx)] = 38.0
        elif kx == -55:
            G.can2[_c19(kx)] = 39.0
        elif -54 <= kx:
            G.can2[_c19(kx)] = 40.0

        if G.flg_sigo >= 1 and kx >= G.canyr - 60:
            G.can2[_c19(kx)] = G.kflcan[KE, _c19(kx)]

    # 長期加入者の特例（44年）
    G.senll = 44.0

    # ------------------------------------------------------------------
    # 障害・遺族の給付乗率
    # ------------------------------------------------------------------
    G.ha[1] = 1.25
    G.ha[2] = 1.00
    G.ha[3] = 1.00
    G.hb[1] = 1.25
    G.hb[2] = 1.00
    G.hb[3] = 0.75

    G.ema[1] = 1.284
    G.ema[2] = 1.031
    G.ema[3] = G.ema[1]
    G.emb[1] = 1.266
    G.emb[2] = 1.048
    G.emb[3] = G.emb[1]

    if G.flg_sigo == 2:
        G.emc[1] = 1.165
        G.emc[2] = 1.000
        G.emc[3] = G.emc[1]

    # 遺族厚生年金の給付割合（4分の3）
    G.srv = 0.75

    # ------------------------------------------------------------------
    # 脱退一時金などの率。制度（pseid）で変わる
    # ------------------------------------------------------------------
    G.ee[2] = 0.25
    if G.pseid == 0:
        G.ee[1] = 0.20
    elif G.pseid <= 4:
        G.ee[1] = 0.1585
    else:
        G.ee[1] = 0.1982

    # ------------------------------------------------------------------
    # 遺族の失権率 `rs` を読む
    # ------------------------------------------------------------------
    G.rs[1:3 + 1, KS:KE + 1, 15:115 + 1, 1:4 + 1] = 0.0

    fpy = G.fp_map["yuizor"]
    for s in range(1, 3 + 1):
        if G.konen != 1 and s == 3:
            continue
        fpy.fgets(BUF_SIZE)
        nensyu = fpy.line[0:2]
        assert nensyu == "RS", "yuizor: nensyu = %r" % nensyu

        for k in range(KS - 5, 70 + 1):
            vals = fpy.read()
            kk = int(vals[0])
            assert k == kk, "yuizor: k = %d, kk = %d" % (k, kk)

            if k >= KS:
                G.rs[s, k, 15:115 + 1, 1] = vals[1:1 + 101]

        if s != 2:
            vals = fpy.read()
            G.rs[s, KS, 15:115 + 1, 2] = vals[1:1 + 101]
        else:
            vals = fpy.read()
            G.rs[s, KS, 15:115 + 1, 3] = vals[1:1 + 101]
            vals = fpy.read()
            G.rs[s, KS, 15:115 + 1, 2] = vals[1:1 + 101]
            vals = fpy.read()
            G.rs[s, KS, 15:115 + 1, 4] = vals[1:1 + 101]

        # 71年度以降は 70年度で止め、2〜4 は基準年度の値を横に伸ばす
        for x in range(15, 115 + 1):
            for k in range(KS + 1, KE + 1):
                if k >= 71:
                    G.rs[s, k, x, 1] = G.rs[s, 70, x, 1]
                G.rs[s, k, x, 3] = G.rs[s, KS, x, 3]
                G.rs[s, k, x, 2] = G.rs[s, KS, x, 2]
                G.rs[s, k, x, 4] = G.rs[s, KS, x, 4]

    # ------------------------------------------------------------------
    # 支給率 `sik` を読む（基準年度 KS+1 のぶん）
    # ------------------------------------------------------------------
    fps = G.fp_map["sikur"]
    fps.read()
    for s in range(1, 2 + 1):
        for j in range(1, 2 + 1):
            fps.read()
            vals = fps.read()
            kk = int(vals[0])
            ss = int(vals[1])
            jj = int(vals[2])
            assert kk == KS + 1, "sikur: kk = %d" % kk
            assert ss == s, "sikur: ss = %d, s = %d" % (ss, s)
            assert jj == j, "sikur: jj = %d, j = %d" % (jj, j)
            vals = fps.read()
            for x in range(0, 115 + 1):
                vals = fps.read()
                xx = int(vals[0])       # 原本は `int xx = vals.at(0);`（切捨て）
                assert xx == x, "sikur: xx = %d, x = %d" % (xx, x)
                G.sik[KS + 1, x, s, 1:19 + 1, j] = vals[1:1 + 19]

    for k in range(KS, KE + 1):
        for x in range(60, 69 + 1):
            for s in range(1, 2 + 1):
                for i in range(1, 17 + 1):
                    for j in range(1, 2 + 1):
                        if k == KS:
                            G.sikr[x, s, i, j] = 1.0
                        G.nos[k, x, s, i, j] = 1.0

    fps.skip(4)

    for x in range(60, 69 + 1):
        vals = fps.read()
        xx = int(vals[0])
        assert xx == x, "sikur(sikr): xx = %d, x = %d" % (xx, x)
        G.sikr[x, 1, 1, 1] = vals[1]
        G.sikr[x, 1, 1, 2] = vals[2]
        G.sikr[x, 1, 3, 1] = vals[3]
        G.sikr[x, 1, 3, 2] = vals[4]
        G.sikr[x, 1, 2, 1] = vals[5]
        G.sikr[x, 1, 4, 1] = vals[6]
        G.sikr[x, 2, 1, 1] = vals[7]
        G.sikr[x, 2, 1, 2] = vals[8]
        G.sikr[x, 2, 3, 1] = vals[9]
        G.sikr[x, 2, 3, 2] = vals[10]
        G.sikr[x, 2, 2, 1] = vals[11]
        G.sikr[x, 2, 4, 1] = vals[12]
        for i in range(2, 4 + 1, 2):
            for s in range(1, 2 + 1):
                G.sikr[x, s, i, 2] = G.sikr[x, s, i, 1]

    if G.pseid == 0:
        fps.skip(4)

        for j in range(1, 3 + 1):
            vals = fps.read()
            G.routsu[1, 1, j] = vals[1]
            G.routsu[1, 2, j] = vals[2]
            G.routsu[1, 3, j] = vals[3]
            G.routsu[1, 4, j] = vals[4]
            G.routsu[2, 1, j] = vals[5]
            G.routsu[2, 2, j] = vals[6]
            G.routsu[2, 3, j] = vals[7]
            G.routsu[2, 4, j] = vals[8]

    # 高齢の在職支給率の男女別の伸び（この値はあとで上書きされる）
    dtem[1] = 0.995182
    dtem[2] = 1.006545

    if G.pseid == 0:
        xs = 81
        xe = 96
    else:
        xs = 80
        xe = 95

    # ------------------------------------------------------------------
    # 基準年度の支給率を将来へ伸ばす
    # ------------------------------------------------------------------
    for k in range(KS + 2, KE + 1):
        G.sik[k, 0:115 + 1, 1:2 + 1, 1:19 + 1, 1:2 + 1] = \
            G.sik[KS + 1, 0:115 + 1, 1:2 + 1, 1:19 + 1, 1:2 + 1]

        # 支給開始年齢の引上げが済んだ生年は 1.0
        for j in range(1, 2 + 1):
            for s in range(1, 2 + 1):
                if G.pseid == 0 and s == 2:
                    for x in range(62, 115 + 1):
                        if x - (k - (KS + 1)) < 62:
                            if x < 65:
                                G.sik[k, x, s, 9, j] = G.sik[k, 61, s, 9, j]
                                G.sik[k, x, s, 16, j] = G.sik[k, 61, s, 16, j]
                            if x >= 65:
                                G.sik[k, x, s, 9, j] = 1.0
                                G.sik[k, x, s, 16, j] = 1.0
                else:
                    for x in range(63, 115 + 1):
                        if x - (k - (KS + 1)) < 63:
                            if x < 65:
                                G.sik[k, x, s, 9, j] = G.sik[k, 62, s, 9, j]
                                G.sik[k, x, s, 16, j] = G.sik[k, 62, s, 16, j]
                            if x >= 65:
                                G.sik[k, x, s, 9, j] = 1.0
                                G.sik[k, x, s, 16, j] = 1.0

        # `if(k >= KS + 2)` は常に真（ループの下限がそれ）。原本のまま残す
        if k >= KS + 2:
            for ii in range(1, 2 + 1):
                i = 11 if ii == 1 else 17

                for x in range(0, 18 + 1):
                    for s in range(1, 2 + 1):
                        for j in range(1, 2 + 1):
                            if ii == 1:
                                numer = (std_max(0.0, float(x) + 1 - (k - (KS + 1)))
                                         * G.sik[KS + 1, x, s, i, j]
                                         + min(x + 1, k - (KS + 1)) * 1.0)
                            else:
                                numer = (std_max(0.0, float(x) + 1 - (k - (KS + 1)))
                                         * G.sik[KS + 1, x, s, i, j]
                                         + min(x + 1, k - (KS + 1))
                                         * G.sik[k, x, s, 19, j])
                            denom = x + 1
                            G.sik[k, x, s, i, j] = numer / denom

            # 裁定遅れの処理
            if G.flg_okure == 0:
                if k <= KIJ + 5:
                    for s in range(1, 2 + 1):
                        for i in range(1, 4 + 1):
                            for j in range(1, 2 + 1):
                                if s == 1 or (G.pseid != 0 and s == 2):
                                    if k == KIJ + 2:
                                        G.nos[k, 64, s, i, j] = \
                                            1.0 - (1.0 - G.sikr[64, s, i, j]) \
                                            * (3.0 - (k - KIJ)) / 2.0
                                        G.sik[k, 64, s, i, j] = \
                                            G.sik[KIJ, 64, s, i, j] * G.nos[k, 64, s, i, j]
                                else:
                                    if k <= KIJ + 3:
                                        for x in range(62, 62 + k - KIJ - 1 + 1):
                                            if k == KIJ + 3 and x == 62:
                                                pass
                                            else:
                                                G.nos[k, x, s, i, j] = \
                                                    1.0 - (1.0 - G.sikr[x, s, i, j]) \
                                                    * (4.0 - (k - KIJ)) / 3.0
                                                G.sik[k, x, s, i, j] = \
                                                    G.sik[KIJ, x, s, i, j] \
                                                    * G.nos[k, x, s, i, j]

                                if i == 2 or i == 4:
                                    if k <= KIJ + 2:
                                        if s == 1 or (G.pseid != 0 and s == 2):
                                            if k == KIJ + 1:
                                                assert G.sikr[64 - k + KIJ, s, i, j] > 0.0
                                                G.nos[k, 64, s, i, j] = \
                                                    G.sikr[64, s, i, j] \
                                                    / G.sikr[64 - k + KIJ, s, i, j]
                                                G.sik[k, 64, s, i, j] = \
                                                    G.sik[KIJ, 64, s, i, j] \
                                                    * G.nos[k, 64, s, i, j]
                                        else:
                                            for x in range(62 + k - KIJ, 64 + 1):
                                                assert G.sikr[x - k + KIJ, s, i, j] > 0.0
                                                G.nos[k, x, s, i, j] = \
                                                    G.sikr[x, s, i, j] \
                                                    / G.sikr[x - k + KIJ, s, i, j]
                                                G.sik[k, x, s, i, j] = \
                                                    G.sik[KIJ, x, s, i, j] \
                                                    * G.nos[k, x, s, i, j]

                                    for x in range(65, 69 + 1):
                                        G.nos[k, x, s, i, j] = \
                                            1.0 - (1.0 - G.sikr[x, s, i, j]) \
                                            * (6.0 - (k - KIJ)) / 5.0
                                        G.sik[k, x, s, i, j] = \
                                            G.sik[KIJ, x, s, i, j] * G.nos[k, x, s, i, j]

        # 年齢を1つずらして持ち越す給付（i = 5〜13, 18。14〜17 は飛ばす）
        for i in range(5, 18 + 1):
            if 14 <= i <= 17:
                continue
            for x in range(46, 115 + 1):
                if ((5 <= i <= 8 and x >= 46)
                        or (i == 10 and x >= 66)
                        or (12 <= i <= 13 and x >= 66)
                        or (i == 18 and x >= 66)):
                    for j in range(1, 2 + 1):
                        for s in range(1, 2 + 1):
                            if G.pseid == 0 and k == KS + 2:
                                continue
                            G.sik[k, x, s, i, j] = G.sik[k - 1, x - 1, s, i, j]

        # 支給開始年齢の段差を埋める。i の組ごとに男女の扱いが入れ替わる
        for i in (9, 10, 16):
            for j in range(1, 2 + 1):
                for s in range(1, 2 + 1):
                    if G.pseid == 0 and s == 2:
                        if k >= 24:
                            G.sik[k, 62, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 27:
                            G.sik[k, 63, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 30:
                            G.sik[k, 64, s, i, j] = G.sik[k, 61, s, i, j]
                    else:
                        if k >= 22:
                            G.sik[k, 63, s, i, j] = G.sik[k, 62, s, i, j]
                        if k >= 25:
                            G.sik[k, 64, s, i, j] = G.sik[k, 62, s, i, j]

        for i in range(11, 13 + 1):
            for j in range(1, 2 + 1):
                for s in range(1, 2 + 1):
                    # ここだけ `s == 1` 側が61歳を引く（他は `s == 2`）
                    if G.pseid == 0 and s == 1:
                        if k >= 24:
                            G.sik[k, 62, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 27:
                            G.sik[k, 63, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 30:
                            G.sik[k, 64, s, i, j] = G.sik[k, 61, s, i, j]
                    else:
                        if k >= 22:
                            G.sik[k, 63, s, i, j] = G.sik[k, 62, s, i, j]
                        if k >= 25:
                            G.sik[k, 64, s, i, j] = G.sik[k, 62, s, i, j]

        for i in range(1, 4 + 1):
            for j in range(1, 2 + 1):
                for s in range(1, 2 + 1):
                    if G.pseid == 0 and s == 2:
                        if k >= 24:
                            G.sik[k, 62, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 27:
                            G.sik[k, 63, s, i, j] = G.sik[k, 61, s, i, j]
                        if k >= 30:
                            G.sik[k, 64, s, i, j] = G.sik[k, 61, s, i, j]
                    else:
                        if k >= 22:
                            G.sik[k, 63, s, i, j] = G.sik[k, 62, s, i, j]
                        if k >= 25:
                            G.sik[k, 64, s, i, j] = G.sik[k, 62, s, i, j]

        # 高齢（xs 歳以上）の在職支給率を外挿する
        for x in range(xs, 115 + 1):
            if x <= 65 + k - 7:
                for s in range(1, 2 + 1):
                    if x == xs:
                        G.sik[k, x, s, 11, 1] = (G.sik[k, xs - 1, s, 11, 1] * 2.0
                                                 - G.sik[k, xs - 2, s, 11, 1])
                    elif x <= xe:
                        # 掛け算の括弧の位置が下の枝と違う。原本のまま
                        G.sik[k, x, s, 11, 1] = (
                            G.sik[KS + 1, min(x, xe), s, 11, 1]
                            * (G.sik[k, xs, s, 11, 1] / G.sik[KS + 1, xs, s, 11, 1]))
                    else:
                        G.sik[k, x, s, 11, 1] = std_min(
                            std_max(G.sik[k, x - 1, s, 11, 1] * 2.0
                                    - G.sik[k, x - 2, s, 11, 1],
                                    G.sik[k, x - 1, s, 11, 1]), 1.0)
                    for i in range(1, 4 + 1):
                        G.sik[k, x, s, i, 1] = G.sik[k - 1, x - 1, s, i, 1]
                        G.sik[k, x, s, i, 2] = G.sik[k - 1, x - 1, s, i, 2]
            elif x <= 95 + k - (KS + 1):
                for s in range(1, 2 + 1):
                    G.sik[k, x, s, 11, 1] = std_max(
                        G.sik[k - 1, x - 1, s, 11, 1] * dtem[s],
                        G.sik[KS + 1, min(x, xe), s, 11, 1]
                        * G.sik[k, xs, s, 11, 1] / G.sik[KS + 1, xs, s, 11, 1])

    # ------------------------------------------------------------------
    # 繰上げ・繰下げの減額率／増額率。`dtem` を別の意味で使い回す
    # ------------------------------------------------------------------
    if G.flg_siktuika == 0:
        for i in range(3, 4 + 1):
            for k in range(KIJ + 1, KE + 1):
                for x in range(0, 115 + 1):
                    dtem[1] = 1.0
                    dtem[2] = 1.0
                    if 23 - KIJ <= x - k <= 59 - KIJ:
                        if G.pseid == 0:
                            dtem[1] = 1.00
                            dtem[2] = (0.90 + (1.00 - 0.90) / 36.0
                                       * (x - k + KIJ - 23))
                        G.sik[k, x, 1, i, 2] = G.sik[k, x, 1, i, 2] * dtem[1]
                        G.sik[k, x, 2, i, 2] = G.sik[k, x, 2, i, 2] * dtem[2]
                    elif 60 - KIJ <= x - k <= 69 - KIJ:
                        if x - k == 60 - KIJ:
                            if G.pseid == 0:
                                dtem[1] = 1.00
                                dtem[2] = 1.00
                        else:
                            if G.pseid == 0:
                                dtem[1] = (0.80 + (0.70 - 0.80) / 8.0
                                           * (x - k + KIJ - 61))
                                dtem[2] = (0.95 + (0.90 - 0.95) / 8.0
                                           * (x - k + KIJ - 61))
                        if k <= KIJ + 5:
                            dtem[1] = 1.00 - (1.00 - dtem[1]) / 5.0 * (k - KIJ)
                            dtem[2] = 1.00 - (1.00 - dtem[2]) / 5.0 * (k - KIJ)
                        G.sik[k, x, 1, i, 2] = G.sik[k, x, 1, i, 2] * dtem[1]
                        G.sik[k, x, 2, i, 2] = G.sik[k, x, 2, i, 2] * dtem[2]

    # ------------------------------------------------------------------
    # 死亡率 `qp` を読む
    # ------------------------------------------------------------------
    fpqx = G.fp_map["qx"]
    fpqx.read()
    for ss in range(1, 2 + 1):
        if 4 <= G.seimei <= 6:
            for nensu in range(G.seiy - 55, G.seiy + 1):
                vals = fpqx.read()

                kk = int(vals[0])
                assert kk == nensu, "qx: kk = %d, nensu = %d" % (kk, nensu)
                iqp[0:114 + 1, ss] = vals[1:1 + 115]
                G.qp[nensu, 0:114 + 1, ss] = iqp[0:114 + 1, ss] / 1.0e+5

    set_hsr()

    # ------------------------------------------------------------------
    # 支給率の出力
    # ------------------------------------------------------------------
    if G.key == 11 and G.nenbeex == 0:
        fpso = G.fp_map["sikr_out"]
        fpso.write("%s\n" % "支給率の出力")
        fpso.write("k,x,s,i,j,sik\n")
        if G.pseid in (0, 1, 4, 5):
            for k in range(KIJ, KE + 1):
                for x in range(0, 115 + 1):
                    for s in range(1, 2 + 1):
                        for i in range(1, 19 + 1):
                            for j in range(1, 2 + 1):
                                fpso.write("%d,%d,%d,%d,%d,%15.10f\n"
                                           % (k, x, s, i, j, G.sik[k, x, s, i, j]))
        fpso.write("%s\n" % "裁定遅れの処理に使用する率の出力")
        fpso.write("k,x,s,i,j,nos\n")
        if G.pseid in (0, 1, 4, 5):
            for k in range(KIJ + 1, KIJ + 10 + 1):
                for x in range(60, 69 + 1):
                    for s in range(1, 2 + 1):
                        for i in range(1, 4 + 1):
                            for j in range(1, 2 + 1):
                                fpso.write("%d,%d,%d,%d,%d,%15.10f\n"
                                           % (k, x, s, i, j, G.nos[k, x, s, i, j]))


def set_hsr():
    """seid.cpp:644 の `static void set_hsr(void)` の忠実移植。

    報酬水準（`bn` 実額・`br` 20歳を1とした指数）を `hou` ファイルから
    読み、男女差を `hsr_r`（1.3%／年）ずつ縮める。パート適用拡大が
    入る年度は、被保険者の内訳（`lpt2` `lpt3` `lpt4`）で重みを付けた
    平均報酬 `bnpt` を作る。

    `tmp` `tmq` `tmr` が宣言だけされて一度も使われない（F9 の仲間）。
    """
    bnpti = np.zeros((85, 4))

    fph = G.fp_map["hou"]

    items = fph.read_str()
    nensyu = items[1][0:2]
    assert nensyu == "BR", "hou: nensyu = %r" % nensyu

    fph.skip(2)

    if G.konen == 1:
        for x in range(15, 84 + 1):
            vals = fph.read()
            xx = int(vals[0])
            assert xx == x, "hou(BR): xx = %d, x = %d" % (xx, x)
            for s in range(1, 3 + 1):
                G.br[KS, x, s] = vals[1 + (s - 1)]
    else:
        for x in range(15, 74 + 1):
            vals = fph.read()
            xx = int(vals[0])
            assert xx == x, "hou(BR): xx = %d, x = %d" % (xx, x)
            for s in range(1, 2 + 1):
                G.br[KS, x, s] = vals[1 + (s - 1)]

    items = fph.read_str()
    nensyu = items[1][0:2]
    assert nensyu == "BN", "hou: nensyu = %r" % nensyu

    fph.skip(2)

    if G.konen == 1:
        for x in range(15, 84 + 1):
            vals = fph.read()
            xx = int(vals[0])
            assert xx == x, "hou(BN): xx = %d, x = %d" % (xx, x)
            for s in range(1, 3 + 1):
                G.bn[KS, x, s] = vals[1 + (s - 1)]
    else:
        for x in range(15, 74 + 1):
            vals = fph.read()
            xx = int(vals[0])
            assert xx == x, "hou(BN): xx = %d, x = %d" % (xx, x)
            for s in range(1, 2 + 1):
                G.bn[KS, x, s] = vals[1 + (s - 1)]

    if G.pseid == 0:
        items = fph.read_str()
        nensyu = items[1][0:5]
        assert nensyu == "BNPTI", "hou: nensyu = %r" % nensyu

        fph.skip(2)

        for x in range(15, 84 + 1):
            vals = fph.read()
            xx = int(vals[0])
            assert xx == x, "hou(BNPTI): xx = %d, x = %d" % (xx, x)
            for s in range(1, 3 + 1):
                bnpti[x, s] = vals[1 + (s - 1)]
    else:
        bnpti[15:84 + 1, 1:3 + 1] = 0.0

    for s in range(1, 3 + 1):
        if G.pseid != 0 and s == 3:
            continue
        for x in range(15, 84 + 1):
            G.br[KS + 1, x, s] = G.br[KS, x, s]
            G.bn[KS + 1, x, s] = G.bn[KS, x, s]

    if G.pseid == 0:
        # x が外・k が内。`bn[k]` が `bn[k-1]` を見る漸化式なのでこの順が要る
        for x in range(15, 84 + 1):
            for k in range(KS + 2, KE + 1):
                if k <= G.hsr_endy:
                    tbn1 = G.bn[k - 1, x, 1]
                    tbn2 = G.bn[k - 1, x, 2]
                    tml = G.l[k, 1, x] + G.l[k, 2, x]
                    if tml > 0.0:
                        G.bn[k, x, 1] = tbn1 - G.l[k, 2, x] / tml * G.hsr_r * (tbn1 - tbn2)
                        G.bn[k, x, 2] = tbn2 + G.l[k, 1, x] / tml * G.hsr_r * (tbn1 - tbn2)
                    else:
                        G.bn[k, x, 1] = tbn1 - G.hsr_r * (tbn1 - tbn2) / 2.0
                        G.bn[k, x, 2] = tbn2 + G.hsr_r * (tbn1 - tbn2) / 2.0
                else:
                    G.bn[k, x, 1] = G.bn[k - 1, x, 1]
                    G.bn[k, x, 2] = G.bn[k - 1, x, 2]
                G.bn[k, x, 3] = G.bn[k - 1, x, 3]

                for s in range(1, 3 + 1):
                    G.br[k, x, s] = G.bn[k, x, s] / G.bn[KS + 1, 20, s]
    else:
        for s in range(1, 3 + 1):
            # `continue` ではなく `break`。s = 3 でループそのものが終わる
            if G.pseid != 0 and s == 3:
                break
            for x in range(15, 84 + 1):
                for k in range(KS + 2, KE + 1):
                    G.br[k, x, s] = G.br[KS + 1, x, s]
                    G.bn[k, x, s] = G.bn[KS + 1, x, s]

    # ------------------------------------------------------------------
    # パート（短時間労働者）の標準報酬。第1添字 0 が現行、1 が適用拡大後
    # ------------------------------------------------------------------
    G.partbbn[0, 0, 1, 1] = 16.9e4 * 12.0
    G.partbbn[0, 0, 2, 1] = 16.9e4 * 12.0
    G.partbbn[0, 0, 1, 2] = 15.1e4 * 12.0
    G.partbbn[0, 0, 2, 2] = 15.1e4 * 12.0

    if G.flg_part == 1:
        G.partbbn[1, 0, 1, 1] = 16.9e4 * 12.0
        G.partbbn[1, 0, 2, 1] = 16.9e4 * 12.0
        G.partbbn[1, 0, 1, 2] = 15.1e4 * 12.0
        G.partbbn[1, 0, 2, 2] = 15.1e4 * 12.0
    elif G.flg_part == 2:
        G.partbbn[1, 0, 1, 1] = 13.9e4 * 12.0
        G.partbbn[1, 0, 2, 1] = 13.9e4 * 12.0
        G.partbbn[1, 0, 1, 2] = 11.1e4 * 12.0
        G.partbbn[1, 0, 2, 2] = 11.1e4 * 12.0
    elif G.flg_part == 3:
        G.partbbn[1, 0, 1, 1] = 14.1e4 * 12.0
        G.partbbn[1, 0, 2, 1] = 14.1e4 * 12.0
        G.partbbn[1, 0, 1, 2] = 11.4e4 * 12.0
        G.partbbn[1, 0, 2, 2] = 11.4e4 * 12.0
    elif G.flg_part == 4:
        G.partbbn[1, 0, 1, 1] = 9.7e4 * 12.0
        G.partbbn[1, 0, 2, 1] = 9.7e4 * 12.0
        G.partbbn[1, 0, 1, 2] = 8.8e4 * 12.0
        G.partbbn[1, 0, 2, 2] = 8.8e4 * 12.0
    elif G.flg_part == 5:
        G.partbbn[1, 0, 1, 1] = 8.8e4 * 12.0
        G.partbbn[1, 0, 2, 1] = 8.8e4 * 12.0
        G.partbbn[1, 0, 1, 2] = 8.8e4 * 12.0
        G.partbbn[1, 0, 2, 2] = 8.8e4 * 12.0

    if G.pseid == 0:
        for s in range(1, 2 + 1):
            for x in range(15, 84 + 1):
                for k in range(KS, KE + 1):
                    x2 = 1 if x <= 59 else 2

                    G.bnpt[k, x, s] = G.partbbn[0, 0, x2, s] / G.ad[22]

                    if G.flg_part >= 1:
                        if k == G.partyr4:
                            if (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                                    + G.lpt4[k, s, x] > 1.0e-6):
                                G.bnpt[k, x, s] = (
                                    (G.lpt2[k, s, x] * bnpti[x, s]
                                     + (G.lpt3[k, s, x] + G.lpt4[k, s, x])
                                     * G.partbbn[1, 0, x2, s])
                                    / (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                                       + G.lpt4[k, s, x]) / G.ad[22])
                            else:
                                G.bnpt[k, x, s] = 0.0
                        elif k > G.partyr4:
                            if G.lpt[k, s, x] > 1.0e-6:
                                G.bnpt[k, x, s] = (
                                    (G.lpt2[k, s, x] * bnpti[x, s]
                                     + (G.lpt3[k, s, x] + G.lpt4[k, s, x])
                                     * G.partbbn[1, 0, x2, s]
                                     + (G.lpt[k, s, x] - G.lpt2[k, s, x]
                                        - G.lpt3[k, s, x] - G.lpt4[k, s, x])
                                     * G.partbbn[0, 0, x2, s])
                                    / G.lpt[k, s, x] / G.ad[22])
                            else:
                                G.bnpt[k, x, s] = 0.0

                    if k == G.partyr3 - 1 or k == G.partyr3:
                        G.dmpt2[k, x, s] = G.partbbn[0, 0, x2, s] / G.ad[22]
                    elif G.flg_part >= 1 and (k == G.partyr4 - 1
                                              or k == G.partyr4):
                        if (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                                + G.lpt4[k, s, x] > 1.0e-6):
                            G.dmpt2[k, x, s] = (
                                (G.lpt2[k, s, x] * bnpti[x, s]
                                 + (G.lpt3[k, s, x] + G.lpt4[k, s, x])
                                 * G.partbbn[1, 0, x2, s])
                                / (G.lpt2[k, s, x] + G.lpt3[k, s, x]
                                   + G.lpt4[k, s, x]) / G.ad[22])
                        else:
                            G.dmpt2[k, x, s] = 0.0

    # 70歳以上の被保険者を置かない年度は報酬水準も 0 にする
    if G.pseid == 0:
        for k in range(KS, KE + 1):
            if G.flg_hiho70 == 0 or (G.flg_hiho70 >= 1 and k < G.hiho70yr - 5):
                for x in range(70, 84 + 1):
                    for s in range(1, 3 + 1):
                        G.bn[k, x, s] = 0.0
                        if s <= 2:
                            G.bnpt[k, x, s] = 0.0

    # ------------------------------------------------------------------
    # 報酬設定ファイルの出力
    # ------------------------------------------------------------------
    if G.key == 11 and G.nenbeex == 0:
        fpho = G.fp_map["hou_out"]
        fpho.write("%s\n" % "報酬設定ファイルの出力（パート適用拡分を除く）")

        for s in range(1, 2 + 1):
            for k in range(KS, 35 + 1):
                vals = [G.l[k, s, x] for x in range(15, 69 + 1)]
                fpho.write("L,%d,%d,%s\n" % (s, k, join(vals, "%.0f")))

                vals = [G.bn[k, x, s] for x in range(15, 69 + 1)]
                fpho.write("BN,%d,%d,%s\n" % (s, k, join(vals)))

                vals = [G.br[k, x, s] for x in range(15, 69 + 1)]
                fpho.write("BR,%d,%d,%s\n" % (s, k, join(vals)))
