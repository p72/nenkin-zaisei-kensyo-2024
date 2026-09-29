# -*- coding: utf-8 -*-
"""③の足元（2021年度末）の状態 — 基礎数13本の読み手（移植版 `dtst.c` 相当）
============================================================================
`nat/base_data/kisosu/NN_{1m,3m,1f,3f}_*.csv` を読んで `benefits.NatState` を作る。
行は「(種類, [欄番号,] 年齢, 値…)」で、**位置ではなくラベルで置く**
（`計画.md`「軸の統一」）。

    01/02  被保険者・待期者   (1|2, 欄 1〜14, 年齢 20〜69, 期間 0〜49 の値)。人数以外は月数 → 12 で割る
    03/04  老齢基礎（全部・一部繰上げ）(3|4, 欄 1〜12, 年齢 60〜115, 受給開始年齢 60〜70 の値)
    05/06  旧法老齢・通算老齢  (5|6, 欄 1〜7, 年齢, 受給開始年齢の値)
    07     5年年金            (7, 年齢, 人数, 納付分)。受給開始年齢は 65 固定
    08/09/10 障害（一般・20歳前・旧法）(N, 年齢 20〜115, 等級1の5欄, 等級2の5欄)
    11     遺族（男は妻・女は夫）(11, 年齢, 人数, 基本, 加給)
    12     遺族（子）          (12, 年齢 0〜19, 同)。男だけ
    13     寡婦               (13, 年齢 26〜69, 14欄)。64歳まで入れる。男だけ

第3号は被保険者・待期者（欄 1〜3）と老齢基礎の納付分（欄 2）だけ。死亡一時金は
足元が無い（推計で作る）。

港: nat/dtst.py:dtst
仕様: §12.5（足元の基礎数）、§4.2
"""
import os

import numpy as np

from ...axis import AGES
from ...io_port import lines_of
from .benefits import NatState, KURIAGE_N
from .layouts import HIHOKENSHA, ROREI, ROREI_KYU, GONEN, SHOGAI, IZOKU, KAFU
from .transition import HihoState, K

__all__ = ["read_initial"]

_SEX_TAG = {"male": "m", "female": "f"}

# 被保険者・待期者の欄番号 → スロット名（港: nat/dtst.py:_H_MEMBER）
_H_MEMBER = {1: "ninzu", 2: "kikan", 3: "noufu", 4: "menjo[1][1]", 5: "menjo[2][1]",
             6: "menjo[3][1]", 7: "menjo[4][1]", 8: "gakusei", 9: "wakamono", 10: "fuka",
             11: "menjo[1][2]", 12: "menjo[2][2]", 13: "menjo[3][2]", 14: "menjo[4][2]"}
# 老齢基礎（港: _R_MEMBER）
_R_MEMBER = {1: "ninzu", 2: "noufu", 3: "menjo[1][1]", 4: "menjo[2][1]", 5: "menjo[3][1]",
             6: "menjo[4][1]", 7: "rofuku_shitasasae", 8: "fuka", 9: "menjo[1][2]",
             10: "menjo[2][2]", 11: "menjo[3][2]", 12: "menjo[4][2]"}
# 旧法老齢・通算老齢（港: _K_MEMBER）
_K_MEMBER = {1: "ninzu", 2: "noufu", 3: "menjo", 4: "kasa_noufu", 5: "kasa_menjo",
             6: "rofuku_shitasasae", 7: "fuka"}
# 障害（港: _S_FIELD）。等級1が列 0〜4、等級2が列 5〜9
_S_FIELD = ("ninzu", "kihon", "kakyu", "menjo_kihon", "menjo_kakyu")
_I_FIELD = ("ninzu", "kihon", "kakyu")
# 寡婦の列 → (新旧, スロット名)（港: _KAFU_FIELD）
_KAFU_FIELD = {0: ("kyu", "ninzu"), 1: ("kyu", "noufu"), 2: ("kyu", "menjo[1][1]"),
               3: ("new", "ninzu"), 4: ("new", "noufu"), 5: ("new", "menjo[1][1]"),
               6: ("new", "menjo[2][1]"), 7: ("new", "menjo[3][1]"), 8: ("new", "menjo[4][1]"),
               9: ("kyu", "menjo[1][2]"), 10: ("new", "menjo[1][2]"), 11: ("new", "menjo[2][2]"),
               12: ("new", "menjo[3][2]"), 13: ("new", "menjo[4][2]")}

_FILES = {"hiho": "01", "taiki": "02", "rorei": "03", "ichibu": "04", "rorei_kyu": "05",
          "turo_kyu": "06", "gonen": "07", "shogai_ippan": "08", "shogai_20mae": "09",
          "shogai_kyu": "10", "izoku": "11", "izoku_ko": "12", "kafu": "13"}
_NAMES = {"01": "Hihokensha", "02": "Taikisha", "03": "Rorei_Zenbu", "04": "Rorei_Ichibu",
          "05": "Rorei_Kyu", "06": "Tsuro_Kyu", "07": "Gonen", "08": "Shogai_Ippan",
          "09": "Shogai_20mae", "10": "Shogai_Kyu", "11": "Izoku_Oya", "12": "Izoku_Ko",
          "13": "Kafu"}


def _rows(path):
    """数値の行だけを float の列で返す（見出し行は捨てる）。"""
    out = []
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].lstrip("-").isdigit():
            continue
        try:
            out.append([float(x) for x in f if x != ""])
        except ValueError:
            continue
    return out


def _path(kisosu_dir, key, gou, sex):
    no = _FILES[key]
    return os.path.join(kisosu_dir, "%s_%d%s_%s.csv" % (no, gou, _SEX_TAG[sex], _NAMES[no]))


def _read_hiho(path, kind, layout, n_member):
    """01/02 → (AGES.n, K, 21)。年齢 20〜69・期間 0〜49 だけ入る（70歳・50年目は 0）。"""
    out = np.zeros((AGES.n, K, layout.n))
    for r in _rows(path):
        if len(r) < 4 or int(r[0]) != kind:
            raise ValueError("%s: 種類 %d の行でない: %r" % (path, kind, r[:3]))
        member, age = int(r[1]), int(r[2])
        if member > n_member:
            continue
        vals = np.array(r[3:3 + K - 1])            # 期間 0〜49
        if member != 1:
            vals = vals / 12.                      # 月数 → 年
        out[AGES.i(age), :len(vals), layout.i(_H_MEMBER[member])] = vals
    return out


def _read_rorei(path, kind, layout, member_map, noufu_only=False):
    """03〜06 → (AGES.n, KURIAGE_N, slots)。"""
    out = np.zeros((AGES.n, KURIAGE_N, layout.n))
    for r in _rows(path):
        if len(r) < 4 or int(r[0]) != kind:
            raise ValueError("%s: 種類 %d の行でない: %r" % (path, kind, r[:3]))
        member, age = int(r[1]), int(r[2])
        if noufu_only and member != 2:
            continue
        vals = np.array(r[3:3 + KURIAGE_N])
        out[AGES.i(age), :len(vals), layout.i(member_map[member])] = vals
    return out


def _read_gonen(path):
    out = np.zeros((AGES.n, KURIAGE_N, GONEN.n))
    j65 = 65 - 60
    for r in _rows(path):
        if int(r[0]) != 7:
            raise ValueError("%s: 種類 7 の行でない" % path)
        age = int(r[1])
        out[AGES.i(age), j65, GONEN.i("ninzu")] = r[2]
        out[AGES.i(age), j65, GONEN.i("noufu")] = r[3]
    return out


def _read_shogai(path, kind):
    out = np.zeros((AGES.n, 3, SHOGAI.n))
    for r in _rows(path):
        if int(r[0]) != kind:
            raise ValueError("%s: 種類 %d の行でない" % (path, kind))
        age = int(r[1])
        for c in range(10):
            out[AGES.i(age), c // 5 + 1, SHOGAI.i(_S_FIELD[c % 5])] = r[2 + c]
    return out


def _read_izoku(path, kind):
    out = np.zeros((AGES.n, IZOKU.n))
    for r in _rows(path):
        if int(r[0]) != kind:
            raise ValueError("%s: 種類 %d の行でない" % (path, kind))
        age = int(r[1])
        for c in range(3):
            out[AGES.i(age), IZOKU.i(_I_FIELD[c])] = r[2 + c]
    return out


def _read_kafu(path, max_age=64):
    new = np.zeros((AGES.n, KAFU.n))
    kyu = np.zeros((AGES.n, KAFU.n))
    for r in _rows(path):
        if int(r[0]) != 13:
            raise ValueError("%s: 種類 13 の行でない" % path)
        age = int(r[1])
        if age > max_age:
            continue
        for c in range(14):
            which, slot = _KAFU_FIELD[c]
            (kyu if which == "kyu" else new)[AGES.i(age), KAFU.i(slot)] = r[2 + c]
    return new, kyu


def read_initial(kisosu_dir, sex, gou):
    """区分 (性, 号) の足元の `NatState`。`sex` は "male"/"female"、`gou` は 1/3。"""
    p = lambda key: _path(kisosu_dir, key, gou, sex)                # noqa: E731
    n_member = 14 if gou == 1 else 3
    st = NatState(hiho=HihoState(_read_hiho(p("hiho"), 1, HIHOKENSHA, n_member),
                                 _read_hiho(p("taiki"), 2, HIHOKENSHA, n_member)))
    only = gou == 3
    st.rorei = _read_rorei(p("rorei"), 3, ROREI, _R_MEMBER, noufu_only=only)
    st.rorei_ichibu = _read_rorei(p("ichibu"), 4, ROREI, _R_MEMBER, noufu_only=only)
    if gou == 1:
        st.rorei_kyu = _read_rorei(p("rorei_kyu"), 5, ROREI_KYU, _K_MEMBER)
        st.turo_kyu = _read_rorei(p("turo_kyu"), 6, ROREI_KYU, _K_MEMBER)
        st.gonen = _read_gonen(p("gonen"))
        st.shogai_ippan = _read_shogai(p("shogai_ippan"), 8)
        st.shogai_20mae = _read_shogai(p("shogai_20mae"), 9)
        st.shogai_kyu = _read_shogai(p("shogai_kyu"), 10)
        if sex == "male":
            st.izoku_tuma = _read_izoku(p("izoku"), 11)
            st.izoku_ko = _read_izoku(p("izoku_ko"), 12)
            st.kafu, st.kafu_kyu = _read_kafu(p("kafu"))
        else:
            st.izoku_otto = _read_izoku(p("izoku"), 11)
    return st
