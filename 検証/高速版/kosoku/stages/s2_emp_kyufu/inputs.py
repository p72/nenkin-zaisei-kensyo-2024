# -*- coding: utf-8 -*-
"""②厚生年金給付費推計の入力（移植版 `fileio.cpp` `waku.cpp` `subrh.cpp` `subrj.cpp` と
`kiso.cpp` `seid.cpp` `krgn.cpp` の読む部分）
==========================================================================================
制度（kou / kok / ren / sig）ごとに読むもの:

    ① `waku{W}-20.csv`（人口）、`-05/-08/-09/-10`（被保険者数）、厚年だけ `-06`（3号）、
      `-07`（パート全体）、`-22`（2024年10月の適用拡大）
    基礎率 `kisor_{制度}2024.csv`  種別ごとの節（Q 失権率 / U 脱退力 / RT 再加入率 /
      YX 年齢相関 / RC 有子割合 / CL 障害等級 / KD 加給対象者割合 / IK 育休 / JIIKU）
    報酬 `hou_{制度}2024.csv`（BR 指数 / BN 新規加入報酬 / BNPTI）
    支給率 `sikur_{制度}2024.csv`、遺族の有遺族率 `yuizor_{制度}2024.csv`、
    繰上げ `kragsg_2024.csv`、生命表 `QX-M2023.csv`
    足元 `hk2021-{s}.csv`（被保険者）`jk2021-{s}.csv`（受給権者）

読み手の約束: 節の見出し（`Q` `U` `RT` …、`BR` `BN`、`RS`）と年齢ラベルで置く。
`hk`/`jk` は表題に添字が無いので、港の読む順（ブロックの並び）で置く。
配列の添字は港と同じ（年齢 x 0〜115、経過年 t 0〜100、繰上げ区分 xx 0〜15、
給付 i 1〜13、内訳 j 1〜23）。年度は `YEARS` の添字（= 港の k）。

港: emp_kyufu/waku.py:waku
港: emp_kyufu/subrh.py:subrh2, subrh4, subrh5
港: emp_kyufu/subrj.py:subrj3, subrj4, subrj5
仕様: §12.3（入力ファイル）、§4.3
"""
from dataclasses import dataclass, field
import os
import re

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import lines_of, read_waku_class

__all__ = ["SYSTEMS", "PSEID", "WAKU_FILE", "read_waku", "Kisor", "read_kisor", "Hou", "read_hou",
           "Sikur", "read_sikur", "read_yuizor", "read_kragsg", "read_qx", "HkIn", "read_hk",
           "JkIn", "read_jk", "NX", "NT", "NXX", "NI", "NJ"]

SYSTEMS = ("kou", "kok", "ren", "sig")
PSEID = {"kou": 0, "kok": 1, "ren": 4, "sig": 5}
WAKU_FILE = {"kou": "05", "kok": "08", "ren": "09", "sig": "10"}   # 制度の被保険者数の外枠

NX = 116          # 年齢 0〜115
NT = 101          # 経過年 0〜100
NXX = 16          # 繰上げ・繰下げの区分 0〜15
NI = 14           # 給付の種類 1〜13（0 は計）
NJ = 24           # 年金額の内訳 1〜23

_NUM = re.compile(r"^\s*-?\d")


def _is_num(line):
    return bool(_NUM.match(line))


def _nums(line):
    """カンマ区切りの数値列（空欄は 0）。港の `getnums`（atof）と同じで、読めない欄は 0。"""
    out = []
    for x in line.split(","):
        x = x.strip()
        try:
            out.append(float(x))
        except ValueError:
            out.append(0.)
    return out


# ---------------------------------------------------------------- ① 外枠

def _waku_table(path, sex_offset=0, skip_sum=False, only_male=False):
    """`waku…-NN.csv` → (YEARS.n, 4, AGES.n)。性の軸は港の `s`（0 計 / 1 男 / 2 女 / 3 男の3号）。"""
    tables, _ = read_waku_class(path)
    out = np.zeros((YEARS.n, 4, AGES.n))
    for (cls, sex), T in tables.items():
        if sex > 2:                       # 港は性 0〜2 の 315 行だけ読む（それより後の区分は読まない）
            continue
        if skip_sum and sex == 0:
            continue
        if only_male and sex != 1:
            continue
        out[:, sex + sex_offset, :] = T
    return out


def read_waku(waku_dir, case, name, flg_part=0):
    """人口 `pop`、被保険者数 `l`（3号は `l[:, 3]`）、パート `lpt` `lpt1`（厚年だけ）。
    適用拡大（`flg_part ≥ 1`）なら 1 段階目の増分 `lpt2`（週 30 時間以上）`lpt3`（20〜30 時間）と、
    `flg_part == 4` だけ `lpt4`（20 時間未満）も（港の waku-30/31/32）。無いレバーは 0。
    港は 15〜100 歳を読む（101 歳以上は捨てる）。"""
    p = lambda nn: os.path.join(waku_dir, "waku%s-%s.csv" % (case, nn))   # noqa: E731
    pop = _waku_table(p("20"))
    l = _waku_table(p(WAKU_FILE[name]))
    lpt = np.zeros_like(l)
    lpt1 = np.zeros_like(l)
    lpt2 = np.zeros_like(l); lpt3 = np.zeros_like(l); lpt4 = np.zeros_like(l)
    if name == "kou":
        l3 = _waku_table(p("06"), sex_offset=2, skip_sum=True, only_male=True)   # 男の3号 → s=3
        l[:, 3] = l3[:, 3]
        lpt = _waku_table(p("07"))
        lpt1 = _waku_table(p("22"))
        if flg_part >= 1:
            lpt2 = _waku_table(p("30"))
            lpt3 = _waku_table(p("31"))
            if flg_part == 4:
                lpt4 = _waku_table(p("32"))
    for a in (pop, l, lpt, lpt1, lpt2, lpt3, lpt4):
        a[:, :, AGES.i(101):] = 0.
        a[:, :, :AGES.i(15)] = 0.
    return pop, l, lpt, lpt1, lpt2, lpt3, lpt4


# ---------------------------------------------------------------- 基礎率 kisor

@dataclass
class Kisor:
    """1種別ぶんの基礎率（基準年度の値）。"""
    q: np.ndarray            # (NX, 4) 失権率 i = 1 老齢 / 2 障害 / 3 遺族
    u: np.ndarray            # (NX, 4) 脱退力 i = 1 生存 / 2 障害 / 3 死亡（0 は計）
    rt: np.ndarray           # (NX,) 再加入率
    yx: np.ndarray           # (NX, 2) 年齢相関（0 配偶者 / 1 子）
    ns: np.ndarray           # (NX,)
    rc: np.ndarray           # (NX,) 有子割合
    cl: np.ndarray           # (4,) 障害等級の割合
    cl2: np.ndarray
    kd_raw: np.ndarray       # (NX, 12) KD の12列
    ikucoe: np.ndarray       # (NX,)
    jiiku: np.ndarray        # (NX,)


def _sections(lines):
    """`見出し,記号,…` の行で節を切る → [(記号, 節の行)]。"""
    out = []
    for i, l in enumerate(lines):
        f = [x.strip() for x in l.split(",")]
        if len(f) >= 2 and not _is_num(l) and f[1] in ("Q", "U", "RT", "YX", "RC", "CL", "KD", "IK", "JIIKU"):
            out.append((f[1], i))
    return out


def read_kisor(path, s):
    """`kisor_{制度}2024.csv` の種別 `s` の節を読む。"""
    L = lines_of(path)
    starts = [i for i, l in enumerate(L) if l.split(",")[0:1] and "種別" in l.split(",")[0]
              and len(l.split(",")) > 1 and l.split(",")[1].strip().isdigit()]
    heads = [i for i in starts if int(L[i].split(",")[1]) == s]
    if not heads:
        raise ValueError("%s: 種別 %d の節が無い" % (path, s))
    i0 = heads[0]
    i1 = min([i for i in starts if i > i0] + [len(L)])
    sec = L[i0:i1]
    secs = dict((tag, i) for tag, i in _sections(sec))

    def rows(tag, header_lines=1):
        i = secs[tag] + 1 + header_lines
        out = {}
        while i < len(sec) and _is_num(sec[i]):
            v = _nums(sec[i])
            out[int(v[0])] = v[1:]
            i += 1
        return out

    q = np.zeros((NX, 4)); u = np.zeros((NX, 4)); rt = np.zeros(NX)
    yx = np.zeros((NX, 2)); ns = np.zeros(NX); rc = np.zeros(NX)
    ikucoe = np.zeros(NX); jiiku = np.zeros(NX); kd = np.zeros((NX, 12))
    for x, v in rows("Q").items():
        q[x, 1:4] = v[:3]
    for x, v in rows("U").items():
        u[x, 1:4] = v[:3]
    for x, v in rows("RT").items():
        rt[x] = v[0]
    for x, v in rows("YX").items():
        if s != 2:
            yx[x, 0] = v[0]; ns[x] = v[1]
        else:
            yx[x, 0] = v[0]; yx[x, 1] = v[1]; ns[x] = v[2]
    for x, v in rows("RC").items():
        rc[x] = v[0]
    i = secs["CL"] + 2
    v = _nums(sec[i])
    cl = np.zeros(4); cl2 = np.zeros(4)
    cl[1:4] = v[1:4]; cl2[1:4] = v[4:7]
    for x, v in rows("KD", header_lines=2).items():
        kd[x, :len(v[:12])] = v[:12]
    for x, v in rows("IK").items():
        ikucoe[x] = v[0]
    for x, v in rows("JIIKU").items():
        jiiku[x] = v[0]
    return Kisor(q, u, rt, yx, ns, rc, cl, cl2, kd, ikucoe, jiiku)


# ---------------------------------------------------------------- 報酬 hou

@dataclass
class Hou:
    br: np.ndarray           # (NX, 4) 報酬指数（性 1〜3）
    bn: np.ndarray           # (NX, 4) 新規加入報酬
    bnpti: np.ndarray        # (NX, 4) フルタイム適用拡大の報酬


def read_hou(path):
    L = lines_of(path)
    out = {}
    for tag in ("BR", "BN", "BNPTI"):
        hits = [i for i, l in enumerate(L) if len(l.split(",")) > 1 and l.split(",")[1].strip() == tag]
        a = np.zeros((NX, 4))
        if hits:
            i = hits[0] + 3
            while i < len(L) and _is_num(L[i]):
                v = _nums(L[i])
                a[int(v[0]), 1:1 + len(v[1:4])] = v[1:4]
                i += 1
        out[tag] = a
    return Hou(out["BR"], out["BN"], out["BNPTI"])


# ---------------------------------------------------------------- 支給率 sikur

@dataclass
class Sikur:
    sik: np.ndarray          # (NX, 3, 20, 3) 基準年度の翌年度の支給率 [x, s, i(1..19), j(1..2)]
    sikr: np.ndarray         # (70, 3, 18, 3) 60歳代前半の補正
    routsu: np.ndarray       # (3, 5, 4) 老齢通老の判定用（厚年だけ）


def read_sikur(path, konen):
    L = lines_of(path)
    sik = np.zeros((NX, 3, 20, 3))
    i = 1
    for s in (1, 2):
        for j in (1, 2):
            i += 1                                    # 「年度,性別,J」
            kk, ss, jj = (int(v) for v in _nums(L[i])[:3])
            assert ss == s and jj == j, (path, kk, ss, jj)
            i += 2                                    # 列の見出し
            for x in range(NX):
                v = _nums(L[i]); assert int(v[0]) == x
                sik[x, s, 1:20, j] = v[1:20]
                i += 1
    i += 4
    sikr = np.zeros((70, 3, 18, 3))
    for x in range(60, 70):
        v = _nums(L[i]); assert int(v[0]) == x
        sikr[x, 1, 1, 1], sikr[x, 1, 1, 2], sikr[x, 1, 3, 1], sikr[x, 1, 3, 2] = v[1:5]
        sikr[x, 1, 2, 1], sikr[x, 1, 4, 1] = v[5:7]
        sikr[x, 2, 1, 1], sikr[x, 2, 1, 2], sikr[x, 2, 3, 1], sikr[x, 2, 3, 2] = v[7:11]
        sikr[x, 2, 2, 1], sikr[x, 2, 4, 1] = v[11:13]
        for ii in (2, 4):
            for s in (1, 2):
                sikr[x, s, ii, 2] = sikr[x, s, ii, 1]
        i += 1
    routsu = np.zeros((3, 5, 4))
    if konen:
        i += 4
        for j in (1, 2, 3):
            v = _nums(L[i])
            routsu[1, 1:5, j] = v[1:5]
            routsu[2, 1:5, j] = v[5:9]
            i += 1
    return Sikur(sik, sikr, routsu)


# ---------------------------------------------------------------- 有遺族率 yuizor

def read_yuizor(path, konen, ks, ke, first_year=15, last_year=70):
    """→ rs[s, k, x, 1..4]（(4, YEARS.n, NX, 5)）。港の伸ばし方（71年度以降は 70 で止め、
    2〜4 は基準年度の値を横に）込み。"""
    L = lines_of(path)
    rs = np.zeros((4, YEARS.n, NX, 5))
    i = 0
    for s in (1, 2, 3):
        if not konen and s == 3:
            break
        assert L[i].startswith("RS"), (path, i)
        i += 1
        for k in range(first_year, last_year + 1):
            v = _nums(L[i]); assert int(v[0]) == k, (path, i, k)
            if k >= ks:
                rs[s, k, 15:116, 1] = v[1:102]
            i += 1
        if s != 2:
            rs[s, ks, 15:116, 2] = _nums(L[i])[1:102]; i += 1
        else:
            rs[s, ks, 15:116, 3] = _nums(L[i])[1:102]; i += 1
            rs[s, ks, 15:116, 2] = _nums(L[i])[1:102]; i += 1
            rs[s, ks, 15:116, 4] = _nums(L[i])[1:102]; i += 1
        for k in range(ks + 1, ke + 1):
            if k >= last_year + 1:
                rs[s, k, :, 1] = rs[s, last_year, :, 1]
            rs[s, k, :, 2:5] = rs[s, ks, :, 2:5]
    return rs


# ---------------------------------------------------------------- 繰上げ kragsg

def read_kragsg(path):
    """→ (rkrag[65, 3], rkrgn[65, 3, 2])。60〜64歳の繰上げ請求割合と繰下げ月数の分布。"""
    L = [l for l in lines_of(path)]
    rkrag = np.zeros((65, 3)); rkrgn = np.zeros((65, 3, 2))
    nums = [l for l in L if _is_num(l)]
    for blk, dest in enumerate((None, 0, 1)):
        for r in range(5):
            v = _nums(nums[blk * 5 + r])
            x = int(v[0])
            if dest is None:
                rkrag[x, 1:3] = v[1:3]
            else:
                rkrgn[x, 1:3, dest] = v[1:3]
    return rkrag, rkrgn


# ---------------------------------------------------------------- 生命表 QX

def read_qx(path, seiy=70):
    """→ qp[nensu, x, ss]（(100, 130, 3)、10万分率を率に）。"""
    L = lines_of(path)
    qp = np.zeros((100, 130, 3))
    i = 1
    for ss in (1, 2):
        for nensu in range(seiy - 55, seiy + 1):
            v = _nums(L[i]); assert int(v[0]) == nensu, (path, i)
            qp[nensu, 0:115, ss] = np.array(v[1:116]) / 1.0e5
            i += 1
    return qp


# ---------------------------------------------------------------- 足元 hk / jk

def _blocks_hk(lines):
    """`年齢` の見出し行のあとの 75 行（15〜89 歳）を順に返す。"""
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].startswith("年齢") and i + 1 < n and _is_num(lines[i + 1]):
            i += 1
            rows = []
            while i < n and _is_num(lines[i]):
                rows.append(_nums(lines[i]))
                i += 1
            yield rows
        else:
            i += 1


@dataclass
class HkIn:
    """被保険者の足元（港の `dtst` が `hk` から読む形のまま）。"""
    g: np.ndarray            # (NX, NT)
    ge: np.ndarray
    gpt: np.ndarray
    bb: np.ndarray
    bbpt: np.ndarray
    z: np.ndarray            # (NX, NT, 2, 10)
    ze: np.ndarray
    w: np.ndarray            # (NX, NT, 1, 8, 4)
    we: np.ndarray


def read_hk(path):
    blocks = _blocks_hk(lines_of(path))

    def take(dest, tail=()):
        rows = next(blocks)
        for v in rows:
            x = int(v[0])
            if not (15 <= x <= 89):
                continue
            vals = v[1:1 + 51]
            dest[(x, slice(0, len(vals))) + tail] = vals

    g = np.zeros((NX, NT)); ge = np.zeros((NX, NT)); gpt = np.zeros((NX, NT))
    bb = np.zeros((NX, NT)); bbpt = np.zeros((NX, NT))
    z = np.zeros((NX, NT, 2, 10)); ze = np.zeros((NX, NT, 2, 10))
    w = np.zeros((NX, NT, 1, 8, 4)); we = np.zeros((NX, NT, 1, 8, 4))
    take(g); take(ge); take(gpt); take(bb); take(bbpt)
    for i in range(2):
        for j in range(9):
            take(z, (i, j))
    for i in range(2):
        for j in range(9):
            take(ze, (i, j))
    for arr in (w, we):
        for ii in (2, 3):
            take(arr, (0, 0, ii))
        for j in range(7):
            take(arr, (0, j, 0))
            take(arr, (0, j, 1))
            if j == 4:
                take(arr, (0, j, 2))
                take(arr, (0, j, 3))
    return HkIn(g, ge, gpt, bb, bbpt, z, ze, w, we)


def _blocks_jk(lines):
    """`年　　齢；` の見出し行のあとの 116 行（0〜115 歳）を順に返す。"""
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].startswith("年") and "齢" in lines[i][:8] and i + 1 < n and _is_num(lines[i + 1]):
            i += 1
            rows = []
            while i < n and _is_num(lines[i]):
                rows.append(_nums(lines[i]))
                i += 1
            yield rows
        else:
            i += 1


@dataclass
class JkIn:
    """受給権者の足元（港の `dtst` が `jk` から読む形のまま。額は 10^3 倍済み）。"""
    r: np.ndarray            # (NX, 11, NI)
    f: np.ndarray            # (NX, 11, NI, NJ)
    f_hik: np.ndarray
    f_min: np.ndarray
    hn: np.ndarray           # (NX, 11, NI, 5)
    wn: np.ndarray           # (NX, 11, NI, 5, 2)


def _put_jk(dest, rows, scale, tail):
    for v in rows:
        x = int(v[0])
        size = len(v)
        for t in range(1, 5):
            if t < size:
                dest[(x, 0, t) + tail] = v[t] * scale
            for xx in range(1, 6):
                pos = 24 + t - xx * 4
                if pos < size:
                    dest[(x, xx, t) + tail] = v[pos] * scale
            for xx in range(6, 11):
                pos = 4 + t + xx * 4
                if pos < size:
                    dest[(x, xx, t) + tail] = v[pos] * scale
        for t in range(5, 14):
            pos = 44 + t
            if pos < size:
                dest[(x, 0, t) + tail] = v[pos] * scale


def read_jk(path):
    blocks = _blocks_jk(lines_of(path))
    r = np.zeros((NX, 11, NI)); f = np.zeros((NX, 11, NI, NJ))
    f_hik = np.zeros_like(f); f_min = np.zeros_like(f)
    hn = np.zeros((NX, 11, NI, 5)); wn = np.zeros((NX, 11, NI, 5, 2))
    _put_jk(r, next(blocks), 1., ())
    for j in range(1, 24):
        _put_jk(f, next(blocks), 1e3, (j,))
    _put_jk(f_hik, next(blocks), 1e3, (1,))
    _put_jk(f_min, next(blocks), 1e3, (1,))
    for j in range(1, 5):
        _put_jk(hn, next(blocks), 1., (j,))
    for jj in range(1, 5):
        _put_jk(wn, next(blocks), 1e3, (jj, 0))
        _put_jk(wn, next(blocks), 1e3, (jj, 1))
    return JkIn(r, f, f_hik, f_min, hn, wn)
