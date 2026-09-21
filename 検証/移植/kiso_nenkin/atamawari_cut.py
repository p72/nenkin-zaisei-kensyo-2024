# -*- coding: utf-8 -*-
"""
基礎年金/Atamawari_cut.c の忠実移植（調整率を当てた拠出金の試算）
==================================================================
`tyousei()` が「マクロ経済スライドをいつまで続けるか」を解くために、
**調整終了年度の候補 `c_nendo` ごとに呼ぶ**。`Atamawari()` が作った
年度末の給付費に累積調整率 `cut_ruiseki[c_nendo]` を掛け、年度間値に
直して頭割りし、国年の支出を出す。

`Atamawari()` との違い
----------------------
`Atamawari()` は制度・新旧・区分・対象・形態のすべての組み合わせを
持ち回すが、こちらは**制度計・新旧計・区分計・拠出のみ**の1本しか
作らない（国年の収支だけが要るため）。そのぶん軽く、150 回くらい
呼ばれても持つ。

年度間値の式（`Atamawari.c` と同じ形だが年齢の枝が3つ）
--------------------------------------------------------
    nenrei == 64        前年度末の63歳 ＋ 当年度末の63歳と64歳
    65 <= nenrei <= 67  67歳の改定率
    nenrei >= 68        年齢別の改定率（加給は67歳の率）

`Atamawari.c` の `cal_kyufu_nendokan` は `nenrei <= UNDER_67` を
ひとまとめにするが、こちらは 64 歳だけ別に書いてある。中身は同じ。

原本の癖をそのまま残しているところ
----------------------------------
1. **局所変数の大きな配列が8本（各 137KB）。**`Kyufu_Cut` など
   `[106][54][3]` が8本で 1.1MB をスタックに取る。既定のスタック
   （8MB）には収まる。

2. **`Ichijikin_Cut_Nendomatu` と `Kafu_Cut_Nendomatu` だけ 0 で
   埋めない。**他の8本は頭の三重ループで 0 にするが、この2本は
   埋めずに全年度へ代入するので結果は変わらない。

3. **`Kyufu_Cut` の年齢計が `[0][SUM]` に足し込まれる。**
   `[0][KIHON]` や `[0][KAKYU]` は作らない。足す順番は
   「年齢の昇順 → 形態（基本→加給）」。

4. **`Tokubetukokko_Cut` だけグローバル**（`mkiso.h`）。他の
   `*_Cut_Nendomatu` は局所。`tyousei()` が `Tokubetukokko_Cut` を
   読むため。

5. **`Kafu_Cut_Nendomatu` に掛ける調整率が 64 歳固定**
   （`Atamawari_cut.c:473` の `UNDER_64 - NENREI_SUM`）。寡婦年金は
   年齢別に持っていないため。

6. **`Ichijikin_Cut_Nendomatu` に調整率を掛けない。**死亡一時金は
   マクロ経済スライドの対象外。`Ichijikin_Nendomatu` をそのまま写す。
"""
import numpy as np

from glva import G
from setconst import (
    ECON_SHONENDO, FUKA, KAKYU, KIHON, KOKUNEN, KYOSHUTU, MAX_JUKYU,
    NENREI_SUM, NOUFU, OLD_MENJO, SAISHUNENDO, SHONENDO, SUM, UNDER_63,
    UNDER_64, UNDER_67,
)

__all__ = ["Atamawari_cut"]

SHIHARAIOKURE = 2

_NY = SAISHUNENDO - SHONENDO + 1                 # 106
_NJ = MAX_JUKYU - NENREI_SUM + 1                 # 54
_NI0 = SHONENDO - ECON_SHONENDO                  # 19（cut_ruiseki の年度）

_J63 = UNDER_63 - NENREI_SUM                     # 1
_J64 = UNDER_64 - NENREI_SUM                     # 2
_J67 = UNDER_67 - NENREI_SUM                     # 5
_J68 = 68 - NENREI_SUM                           # 6


def Atamawari_cut(c_nendo):
    """Atamawari_cut.c:271 の忠実移植。"""
    ci = c_nendo - ECON_SHONENDO

    # ---- 局所の配列（癖 1.・2.） ----
    Kyufu_Cut = np.zeros((_NY, _NJ, 3))
    Kyufu_Cut_Nendomatu = np.zeros((_NY, _NJ, 3))
    Kyufu_Cut_Nendomatu_P = np.zeros((_NY, _NJ, 3))
    kokko_Cut = np.zeros((_NY, _NJ, 3))
    kokko_Cut_Nendomatu = np.zeros((_NY, _NJ, 3))
    kokko_Cut_Nendomatu_P = np.zeros((_NY, _NJ, 3))
    Tokubetukokko_Cut_Nendomatu = np.zeros((_NY, _NJ, 3))
    Tokubetukokko_Cut_Nendomatu_P = np.zeros((_NY, _NJ, 3))

    G.Tokubetukokko_Cut[...] = 0.0
    G.Kyoshutukin_Cut[...] = 0.0
    G.Kyoshutukin_Kokko_Cut[...] = 0.0

    # ---- 年度末値に累積調整率を掛ける ----
    J = slice(_J63, _NJ)
    cr = G.cut_ruiseki[ci, _NI0:_NI0 + _NY]          # (106, 54)
    cr_kihon = cr[:, J]                              # (106, 53)
    cr_kakyu = cr[:, _J63].reshape(-1, 1)            # (106, 1)

    src = (
        (Kyufu_Cut_Nendomatu,
         G.Kyufu_Nendomatu[SUM, :, J, SUM, SUM, KYOSHUTU, :]),
        (Kyufu_Cut_Nendomatu_P,
         G.Kyufu_Nendomatu_P[SUM, :, J, SUM, SUM, KYOSHUTU, :]),
        (kokko_Cut_Nendomatu, G.Kokko_Nendomatu[SUM, :, J, SUM, SUM, :]),
        (kokko_Cut_Nendomatu_P, G.Kokko_Nendomatu_P[SUM, :, J, SUM, SUM, :]),
        (Tokubetukokko_Cut_Nendomatu, G.Tokubetukokko_Nendomatu[:, J, SUM, :]),
        (Tokubetukokko_Cut_Nendomatu_P,
         G.Tokubetukokko_Nendomatu_P[:, J, SUM, :]),
    )
    for dst, s in src:
        dst[:, J, KIHON] = s[:, :, KIHON] * cr_kihon
        dst[:, J, KAKYU] = s[:, :, KAKYU] * cr_kakyu

    # ---- 年度末値 → 年度間値 ----
    kc = G.kaiteiritu_cut
    sho = SHIHARAIOKURE
    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        ei = nendo - ECON_SHONENDO
        kc0 = kc[ei][UNDER_67 - UNDER_67]
        # 68〜115歳の年齢別の改定率
        kc_age = kc[ei][68 - UNDER_67:MAX_JUKYU - UNDER_67 + 1]

        for out, nm, nmP in ((Kyufu_Cut, Kyufu_Cut_Nendomatu,
                              Kyufu_Cut_Nendomatu_P),
                             (kokko_Cut, kokko_Cut_Nendomatu,
                              kokko_Cut_Nendomatu_P),
                             (G.Tokubetukokko_Cut, Tokubetukokko_Cut_Nendomatu,
                              Tokubetukokko_Cut_Nendomatu_P)):
            for k in (KIHON, KAKYU):
                # 64歳
                out[sn, _J64, k] = (
                    nmP[sn - 1, _J64 - 1, k] * (sho + kc0 * 6.) / 12.
                    + (nm[sn, _J64 - 1, k] + nm[sn, _J64, k])
                    * (6. - sho) / 12.)

                # 65〜67歳
                out[sn, _J64 + 1:_J67 + 1, k] = (
                    nmP[sn - 1, _J64:_J67, k] * (sho + kc0 * 6.) / 12.
                    + nm[sn, _J64 + 1:_J67 + 1, k] * (6. - sho) / 12.)

                # 68〜115歳（加給は67歳の率）
                kk = kc0 if k == KAKYU else kc_age
                out[sn, _J68:_NJ, k] = (
                    nmP[sn - 1, _J68 - 1:_NJ - 1, k] * (sho + kk * 6.) / 12.
                    + nm[sn, _J68:_NJ, k] * (6. - sho) / 12.)

            # ---- 年齢計（年齢の昇順 → 形態の順。癖 3.） ----
            out[sn, 0, SUM] += np.add.accumulate(
                np.ascontiguousarray(
                    out[sn, _J64:_NJ, KIHON:KAKYU + 1]).ravel())[-1]

    # ---- 国年の拠出金（頭割り） ----
    St = G.SanteiTaishou
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        G.Kyoshutukin_Cut[sn][0] = (Kyufu_Cut[sn][0][SUM]
                                    * St[KOKUNEN][sn][SUM]
                                    / St[SUM][sn][SUM])
        G.Kyoshutukin_Kokko_Cut[sn][0] = (kokko_Cut[sn][0][SUM]
                                          * St[KOKUNEN][sn][SUM]
                                          / St[SUM][sn][SUM])

    # ---- 独自給付（死亡一時金・寡婦年金） ----
    Ichijikin_Cut_Nendomatu = np.zeros((_NY, 3))
    Kafu_Cut_Nendomatu = np.zeros((_NY, 4))

    Ichijikin_Cut_Nendomatu[:, NOUFU] = G.Ichijikin_Nendomatu[:, NOUFU]
    Ichijikin_Cut_Nendomatu[:, FUKA] = G.Ichijikin_Nendomatu[:, FUKA]
    Ichijikin_Cut_Nendomatu[:, SUM] = (Ichijikin_Cut_Nendomatu[:, NOUFU]
                                       + Ichijikin_Cut_Nendomatu[:, FUKA])

    # 癖 5. 寡婦年金は64歳の調整率を掛ける
    Kafu_Cut_Nendomatu[:, SUM:OLD_MENJO + 1] = (
        G.Kafu_Nendomatu[:, SUM:OLD_MENJO + 1]
        * cr[:, _J64].reshape(-1, 1))

    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        ei = nendo - ECON_SHONENDO

        G.Ichijikin_Cut[sn][NOUFU] = (
            Ichijikin_Cut_Nendomatu[sn - 1][NOUFU] * (sho + 6.) / 12.
            + Ichijikin_Cut_Nendomatu[sn][NOUFU] * (6. - sho) / 12.)

        G.Ichijikin_Cut[sn][FUKA] = (
            Ichijikin_Cut_Nendomatu[sn - 1][FUKA] * (sho + 6.) / 12.
            + Ichijikin_Cut_Nendomatu[sn][FUKA] * (6. - sho) / 12.)

        G.Ichijikin_Cut[sn][SUM] = (G.Ichijikin_Cut[sn][NOUFU]
                                    + G.Ichijikin_Cut[sn][FUKA])

        kt = kc[ei][UNDER_67 - UNDER_67]
        G.Kafu_Cut[sn, SUM:OLD_MENJO + 1] = (
            Kafu_Cut_Nendomatu[sn - 1, SUM:OLD_MENJO + 1]
            * (sho + kt * 6.) / 12.
            + Kafu_Cut_Nendomatu[sn, SUM:OLD_MENJO + 1] * (6. - sho) / 12.)

    return
