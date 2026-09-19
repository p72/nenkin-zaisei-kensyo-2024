# -*- coding: utf-8 -*-
"""
プログラム/国民年金/econ.c の忠実移植
=====================================
差分テスト（検証/differential/compare.py）で原本の出力と1要素ずつ突き合わせる
ことを前提に、C のふるまいをそのまま写す。以下はCの実挙動に合わせてある。

- 単年改定率は丸めない。原本 econ.c:104,110,116 は kaiteiritu_marume() を
  呼ぶが **戻り値を捨てている**（引数は値渡し）ので、丸めは効いていない。
- 累積改定率は年齢を1つずらして掛ける（コホートが歳を取る）:
      ruiseki[k][x] = ruiseki[k-1][max(x-1,0)] * tannen[k][x]
  つまり「k年度にx歳の人」はk-1年度にはx-1歳で、そのときの改定ルールを
  受けている。年齢を固定して追うのとは別物になる。
- 全年齢 0〜115歳を回す。既裁定の下支え（Kisai_Shitasasae）は
  67歳の累積改定率を基準に毎年かかる。
"""
import math

ECON_SHONENDO   = 2001
SHONENDO        = 2020
SAISHUNENDO     = 2125
N_O_NENDO       = 1926
TINSURA_KAISHI  = 2021
MAX_ROREI_JUKYU = 115
UNDER_67        = 67
TINSURA          = 1
Kisai_Shitasasae = 0.80
CAL_START    = 2004
MARUME_NENDO = 2024
FULL_PENSION_SHONENDO = 780900.0
EPSILON = 1e-14


def c_round(a, n):
    return float(f"{a:.{n}f}")


def kaiteiritu_marume(nendo, marume_nendo, a):
    return c_round(a, 3) if nendo <= marume_nendo else a


def pension_marume(a):
    return math.floor((a + 50.) / 100.) * 100


def marume_hantei(nendo, marume_nendo, marume_flg, pension):
    """econ.c:435"""
    if nendo <= marume_nendo:
        return pension_marume(pension)
    if marume_flg == 1:
        return max(pension, pension_marume(pension))
    return pension


def econ_read(path):
    """econ.c:456"""
    cpi_up, base_up_real = {}, {}
    raw = open(path, 'rb').read().decode('euc_jp')
    nendo = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        b = [float(x) for x in line.split(',') if x.strip() != '']
        nendo = int(b[0]) + 2000
        cpi_up[nendo]       = 1. + b[6] / 100.
        base_up_real[nendo] = 1. + b[5] / 100.
    for k in range(nendo + 1, SAISHUNENDO + 1):
        cpi_up[k]       = cpi_up[nendo]
        base_up_real[k] = base_up_real[nendo]
    return cpi_up, base_up_real


def index_make(base_up_real, cpi_up, marume_nendo):
    """econ.c:483"""
    HIKIAGE_START, HIKIAGE_END = 2003, 2017
    HOKENRYO = [0.1358, 0.13934, 0.14288, 0.14642, 0.14996, 0.1535, 0.15704,
                0.16058, 0.16412, 0.16766, 0.1712, 0.17474, 0.17828, 0.18182, 0.183]
    KASYOBUN_START = 0.910
    base_up_avg, kashobun_henka = {}, {}
    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        if nendo in (2005, 2006):
            base_up_avg[nendo] = 1.
            kashobun_henka[nendo] = 1.
        else:
            v = (base_up_real[nendo - 4] * base_up_real[nendo - 3]
                 * base_up_real[nendo - 2])
            base_up_avg[nendo] = v ** (1. / 3.)
            if nendo < HIKIAGE_END + 4:
                kashobun_henka[nendo] = (
                    (KASYOBUN_START - HOKENRYO[nendo - 3 - HIKIAGE_START] / 2.)
                    / (KASYOBUN_START - HOKENRYO[nendo - 4 - HIKIAGE_START] / 2.))
            else:
                kashobun_henka[nendo] = 1.
        base_up_avg[nendo]    = kaiteiritu_marume(nendo, marume_nendo, base_up_avg[nendo])
        kashobun_henka[nendo] = kaiteiritu_marume(nendo, marume_nendo, kashobun_henka[nendo])
    base_up_index, cpi_up_index = {}, {}
    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        base_up_index[nendo] = (cpi_up[nendo - 1] * kashobun_henka[nendo]
                                * base_up_avg[nendo])
        cpi_up_index[nendo]  = cpi_up[nendo - 1]
        base_up_index[nendo] = kaiteiritu_marume(nendo, marume_nendo, base_up_index[nendo])
        cpi_up_index[nendo]  = kaiteiritu_marume(nendo, marume_nendo, cpi_up_index[nendo])
    return base_up_index, cpi_up_index


def kaiteiritu_make_before(nenrei, bui, cui):
    """econ.c:565 — 2021年度前"""
    if nenrei == UNDER_67:
        if bui < 1. and bui < cui:
            return 1. if cui > 1. else cui
        return bui
    if cui > bui and bui >= 1.:
        return bui
    if cui > 1. and bui < 1.:
        return 1.
    return cui


def kaiteiritu_make(nenrei, bui, cui):
    """econ.c:598 — 2021年度以降"""
    if nenrei <= UNDER_67:
        return bui
    return bui if cui > bui else cui


def econ(econ_path, extra_macro=None):
    """econ.c:60 の econ() 本体。返り値は (単年改定率, 累積改定率, 満額)。
    いずれも [年度][年齢] の辞書。

    extra_macro: 原本にない年度のマクロ経済スライド調整率 {年度: 率}。
        None（既定）なら原本と完全に同じ挙動になる。差分テストは必ず None で
        回すこと。国民年金モジュールは2020年度分までしか持っておらず、
        2021年度以降は基礎年金モジュール側の pre_cut が担うため、
        公表値と突き合わせるときだけここに渡す。"""
    cpi_up, base_up_real = econ_read(econ_path)
    bui, cui = index_make(base_up_real, cpi_up, MARUME_NENDO)

    NM = MAX_ROREI_JUKYU
    tannen  = {CAL_START: {x: 1. for x in range(NM + 1)}}
    ruiseki = {CAL_START: {x: 1. for x in range(NM + 1)}}

    for nendo in range(CAL_START + 1, SAISHUNENDO + 1):
        tannen[nendo], ruiseki[nendo] = {}, {}
        for nenrei in range(NM + 1):
            if TINSURA == 1 and nendo >= TINSURA_KAISHI:
                t = kaiteiritu_make(nenrei, bui[nendo], cui[nendo])
            else:
                t = kaiteiritu_make_before(nenrei, bui[nendo], cui[nendo])
            # econ.c:102-118 — 実績のマクロ経済スライド調整率。
            # 原本は直後に kaiteiritu_marume() を呼ぶが戻り値を捨てており
            # 丸めは効かないので、ここでも丸めない。
            if nendo == 2015:
                t *= 0.991
            elif nendo == 2019:
                t *= 0.995
            elif nendo == 2020:
                t *= 0.999
            if extra_macro and nendo in extra_macro:
                t *= extra_macro[nendo]
            tannen[nendo][nenrei] = t
            # econ.c:120 — 年齢を1つずらす（コホートが歳を取る）
            prev = ruiseki[nendo - 1][max(nenrei - 1, 0)]
            ruiseki[nendo][nenrei] = kaiteiritu_marume(
                nendo, MARUME_NENDO, prev * t)
            # econ.c:124-133 — 既裁定の下支え。
            # 原本は年齢ループの中で ruiseki[nendo][UNDER_67] を参照するため、
            # nenrei < 67 の時点では当年度の67歳がまだ埋まっていない。
            # C のグローバル配列はゼロ初期化なので基準値は 0 になり、
            # 下支えは実質 nenrei > 67 でしか働かない。その挙動をそのまま写す。
            base = ruiseki[nendo].get(UNDER_67, 0.0)
            if ruiseki[nendo][nenrei] < Kisai_Shitasasae * base:
                ruiseki[nendo][nenrei] = Kisai_Shitasasae * base
                tannen[nendo][nenrei] = (ruiseki[nendo][nenrei]
                                         / ruiseki[nendo - 1][max(nenrei - 1, 0)])

    # econ.c:140-160 — 100円丸めを続けるかの判定フラグ
    marume_flg = {}
    for nendo in range(SHONENDO, MARUME_NENDO + 1):
        marume_flg[nendo] = {x: 1 for x in range(NM + 1)}
    for nendo in range(MARUME_NENDO + 1, SAISHUNENDO + 1):
        marume_flg[nendo] = {}
        for nenrei in range(NM + 1):
            prev_flg = marume_flg[nendo - 1][max(nenrei - 1, 0)]
            same = abs(ruiseki[nendo][nenrei]
                       - ruiseki[nendo - 1][max(nenrei - 1, 0)]) < EPSILON
            marume_flg[nendo][nenrei] = 1 if (prev_flg == 1 and same) else 0

    # econ.c:163-200 — 満額
    full = {}
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        full[nendo] = {}
        for nenrei in range(NM + 1):
            temp = FULL_PENSION_SHONENDO * ruiseki[nendo][nenrei]
            full[nendo][nenrei] = marume_hantei(
                nendo, MARUME_NENDO, marume_flg[nendo][nenrei], temp)
    return tannen, ruiseki, full
