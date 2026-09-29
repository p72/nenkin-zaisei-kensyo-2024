# -*- coding: utf-8 -*-
"""③の入力の読み手 — 外枠・生命表・有配偶率（基礎率と足元は `rates.py` / `initial.py`）
=================================================================================
配列は全部 `axis.py` の軸（年度 = YEARS、年齢 = AGES）で持つ。移植版の
`nendo - SOTOWAKU_SHONENDO` や `nenrei - MIN_WAKU_NENREI` のようなずらしは
読み手の中で `YEARS.i()` `AGES.i()` に畳む。

外枠（①被保険者推計の出力 `waku-NN.csv`）
-------------------------------------------
    人口     waku-20     第1号  waku-11     第3号  waku-14
    第2号    waku-03（厚年）+ waku-08（国共済）+ waku-09（地共済）+ waku-10（私学）

港: nat/waku.py:waku
港: nat/kaizen.py:kaizen
仕様: §2（外枠）、§4.2
"""
from dataclasses import dataclass
import os

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import lines_of, read_waku_class

__all__ = ["Sotowaku", "read_sotowaku", "Lifetable", "read_lifetable",
           "read_yuhaigu", "MALE", "FEMALE"]

MALE, FEMALE = 1, 2          # ①の外枠の「性」の列（0 は男女計）

WAKU_JINKO, WAKU_1GOU, WAKU_3GOU = "20", "11", "14"
WAKU_2GOU = ("03", "08", "09", "10")


@dataclass(frozen=True)
class Sotowaku:
    """外枠。`jinko[sex]`, `gou1[sex]`, `gou3[sex]`, `gou2[sex]` は (YEARS.n, AGES.n)。
    `sex` は MALE / FEMALE。"""
    jinko: dict
    gou1: dict
    gou3: dict
    gou2: dict

    def by_class(self, cls):
        """`InsuredClass` 相当の (号, 性) で引く。`cls` は ("1gou"|"3gou", sex)。"""
        gou, sex = cls
        return (self.gou1 if gou == "1gou" else self.gou3)[sex]


def _class_tables(path):
    """`waku-NN.csv` を {性: (YEARS.n, AGES.n)} に（男女計は捨てる）。"""
    tables, _ = read_waku_class(path)
    out = {}
    for (bunrui, sex), t in tables.items():
        if sex in (MALE, FEMALE):
            out[sex] = t
    if set(out) != {MALE, FEMALE}:
        raise ValueError("%s: 性 1・2 の行が無い" % path)
    return out


def read_sotowaku(waku_dir, case):
    """`waku{case}-NN.csv` を読む。"""
    def p(nn):
        return os.path.join(waku_dir, "waku%s-%s.csv" % (case, nn))
    jinko = _class_tables(p(WAKU_JINKO))
    gou1 = _class_tables(p(WAKU_1GOU))
    gou3 = _class_tables(p(WAKU_3GOU))
    gou2 = {MALE: YEARS.zeros(AGES.n), FEMALE: YEARS.zeros(AGES.n)}
    for nn in WAKU_2GOU:                      # 4制度を足す
        t = _class_tables(p(nn))
        for sex in (MALE, FEMALE):
            gou2[sex] += t[sex]
    return Sotowaku(jinko, gou1, gou3, gou2)


@dataclass(frozen=True)
class Lifetable:
    """死亡率 `q[sex][YEARS.i(y), AGES.i(x)]`（率。ファイルは10万人あたり）。
    表に無い年度は最後の年度で延ばす（港は 2070年度で止め、siml.c が
    `min(nendo, SHIKKENRITU_MAX)` で読む）。"""
    q: dict
    first: int
    last: int


def read_lifetable(path):
    """`QX-M2023.csv`: 見出し1行、性 0（男）・1（女）の順に年度ごと1行
    （列0 = 年度か性、列1〜115 = 0〜114歳）。港: nat/kaizen.py:kaizen"""
    L = [l for l in lines_of(path) if l.strip()]
    rows = []
    for l in L[1:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].lstrip("-").replace(".", "").isdigit():
            continue
        rows.append([float(x) for x in f if x != ""])
    if len(rows) % 2:
        raise ValueError("%s: 行数が偶数でない（%d）" % (path, len(rows)))
    n = len(rows) // 2
    q = {}
    first = last = None
    for si, sex in enumerate((MALE, FEMALE)):
        t = YEARS.zeros(AGES.n)
        years = []
        for k in range(n):
            r = rows[si * n + k]
            y = int(r[0])
            if y < YEARS.first:                 # 下2桁で書いてある（19 = 2019年度）
                y += 2000
            if not YEARS.contains(y):
                continue
            years.append(y)
            vals = np.array(r[1:1 + 115]) / 100000.
            t[YEARS.i(y), :len(vals)] = vals
        first, last = min(years), max(years)
        t[YEARS.i(last) + 1:] = t[YEARS.i(last)]
        q[sex] = t
    return Lifetable(q, first, last)


def read_yuhaigu(path):
    """有配偶率 `yu_haigu_2024.csv`: 見出し1行、(性 0/1, 年齢 20〜70) の行に
    2020〜2070年度の値。戻り値 {性: (YEARS.n, AGES.n)}。2070年度より先は
    2070年度で延ばす。港: nat/kaizen.py:kaizen"""
    L = [l for l in lines_of(path) if l.strip()]
    out = {MALE: YEARS.zeros(AGES.n), FEMALE: YEARS.zeros(AGES.n)}
    first_y, last_y = None, None
    for l in L[1:]:
        f = [x.strip() for x in l.split(",")]
        try:
            sex_i, age = int(float(f[0])), int(float(f[1]))
        except (ValueError, IndexError):
            continue
        sex = (MALE, FEMALE)[sex_i]
        vals = [float(x) for x in f[2:] if x != ""]
        y0 = 2020                                   # 港: I_KEINEN_SHONENDO
        for k, v in enumerate(vals):
            y = y0 + k
            if YEARS.contains(y):
                out[sex][YEARS.i(y), AGES.i(age)] = v
        first_y, last_y = y0, y0 + len(vals) - 1
    for sex in out:
        out[sex][YEARS.i(last_y) + 1:] = out[sex][YEARS.i(last_y)]
    return out
