# -*- coding: utf-8 -*-
"""④の入力の読み手 — 受給者数（③④②）、拠出金算定対象者（①）、実績（base_data）
==============================================================================
配列は全部 `axis.py` の軸（年度 = YEARS）で持つ。年齢は 63〜115歳の53本
（`AGE_LO`〜`AGE_HI`、添字は `age - AGE_LO`）。制度は5つ（`SYSTEMS`）で
**制度計は計算で出す**（港の `SUM` の添字は持たない）。

受給者数（年金額。年度末値）
    ③ `KISONENKIN{国年}-{経済}-{外枠}`   年度は西暦。国年（`SYSTEMS[0]`）
    ② `kiso.{厚年}-{経済}-{外枠}_{kou,kok,ren,sig}`  年度は西暦−2000。被用者4制度
  行は「年度,1,年齢,新旧,種類,性, 値…」。性は読んだ時点で足す（港も男→女の順に
  足すだけ）。値には実績の補正率（`hosei_shin`・`hosei_kyu`）を掛ける。

拠出金算定対象者（`Santei`）
    1号   ③の「年度, 納付月数(男), 納付月数(女), 産休, 育休」の行（年度間値）
    2号   ①の waku-03/08/09/10 の 20〜59歳（男＋女）  → 年度末値2つの平均
    3号   ①の waku-15/16/17/18 の 20〜59歳（男＋女）  → 同上
    1号被保険者数  ①の waku-11 の「計」（男＋女）      → 同上

港: kiso_nenkin/readkokunen_jisseki.py:ReadKokunen_jisseki
港: kiso_nenkin/readhiyousha.py:ReadHiyousha
港: kiso_nenkin/waku.py:waku
港: kiso_nenkin/dtst.py:dtst
港: kiso_nenkin/read_file.py:read_file
仕様: §6.1、§6.2、§12.4
"""
from dataclasses import dataclass, field
import os

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import lines_of, read_waku_class, read_year_rows

__all__ = ["SYSTEMS", "AGE_LO", "AGE_HI", "NA", "Jukyu", "read_kisonenkin", "read_hiyousha",
           "jukyu_from_natout", "Santei", "read_santei_waku", "BaseData", "read_base_data",
           "RN", "RO", "SN", "SO", "IZ", "FK"]

SYSTEMS = ("kokunen", "kounen", "kokkyo", "chikyo", "shigaku")   # 国年・厚年・国共・地共・私学
NS = len(SYSTEMS)
AGE_LO, AGE_HI = 63, 115          # 63 は「63歳以下」の階級
NA = AGE_HI - AGE_LO + 1          # 53
KIHON, KAKYU = 0, 1               # 形態


class _Idx:
    """欄名 → 添字（港の `NOUFU` 等の名前を持つ小さな列挙）。"""
    def __init__(self, *names):
        self.names = names
        for i, n in enumerate(names):
            setattr(self, n, i)
        self.n = len(names)


RN = _Idx("noufu", "menjo_zenhan", "menjo_kouhan")                        # 新法老齢
RO = _Idx("noufu", "menjo", "kakyu_noufu", "kakyu_menjo", "kasanoufu", "kasamenjo",
          "rofuku_shitasasae", "gonen")                                    # 旧法老齢（②は8欄、③は6欄）
SN = _Idx("ippan", "hatachimae")                                          # 新法障害の給付方法
SO = _Idx("noufu", "menjo")                                               # 旧法の納付状態
IZ = _Idx("kihon", "kakyu")
FK = _Idx("rorei", "shogai")                                              # 振替加算


@dataclass
class Jukyu:
    """基礎年金の受給者の年金額（年度末値、男女計、補正率を掛けたあと）。
    形は [制度 5, YEARS.n, NA, …]。"""
    rorei_new: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, RN.n)))
    rorei_old: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, RO.n)))
    shogai_new: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, SN.n, 2)))
    shogai_old: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, 2, SO.n)))
    izoku_new: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, 2)))
    izoku_old: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, 2, SO.n)))
    furikae: np.ndarray = field(default_factory=lambda: np.zeros((NS, YEARS.n, NA, FK.n)))

    def apply_hosei(self, hosei_shin, hosei_kyu):
        """実績の補正率を掛ける。`hosei_shin[3, YEARS.n]`（老齢・障害・遺族）、
        `hosei_kyu[NS, YEARS.n]`（制度別）。港は読んだ値に掛ける。"""
        hr, hs, hi = (hosei_shin[k][None, :, None] for k in range(3))
        self.rorei_new *= hr[..., None]
        self.furikae[..., FK.rorei] *= hr
        self.shogai_new *= hs[..., None, None]
        self.furikae[..., FK.shogai] *= hs
        self.izoku_new *= hi[..., None]
        hk = hosei_kyu[:, :, None]
        self.rorei_old *= hk[..., None]
        self.shogai_old *= hk[..., None, None]
        self.izoku_old *= hk[..., None, None]
        return self


def _put_record(J, s, yi, ai, sk, kb, vals):
    """1行ぶん（性は呼び手が足す）。`sk` 1 新法 / 2 旧法、`kb` 1 老齢 / 2 障害 / 3 遺族。"""
    v = vals
    if sk == 1 and kb == 1:
        J.rorei_new[s, yi, ai, RN.noufu] += v[0]
        J.rorei_new[s, yi, ai, RN.menjo_zenhan] += v[1]
        J.rorei_new[s, yi, ai, RN.menjo_kouhan] += v[2]
        J.furikae[s, yi, ai, FK.rorei] += v[3]
    elif sk == 1 and kb == 2:
        J.shogai_new[s, yi, ai, SN.ippan, KIHON] += v[0]
        J.shogai_new[s, yi, ai, SN.ippan, KAKYU] += v[1]
        J.furikae[s, yi, ai, FK.shogai] += v[2]
        J.shogai_new[s, yi, ai, SN.hatachimae, KIHON] += v[3]
        J.shogai_new[s, yi, ai, SN.hatachimae, KAKYU] += v[4]
    elif sk == 1 and kb == 3:
        J.izoku_new[s, yi, ai, KIHON] += v[0]
        J.izoku_new[s, yi, ai, KAKYU] += v[1]
    elif sk == 2 and kb == 1:
        if len(v) >= 8:                                   # ②: 加給の2欄が挟まる
            cols = (RO.noufu, RO.menjo, RO.kakyu_noufu, RO.kakyu_menjo, RO.kasanoufu,
                    RO.kasamenjo, RO.rofuku_shitasasae, RO.gonen)
        else:                                             # ③: 6欄
            cols = (RO.noufu, RO.menjo, RO.kasanoufu, RO.kasamenjo, RO.rofuku_shitasasae, RO.gonen)
        for c, val in zip(cols, v):
            J.rorei_old[s, yi, ai, c] += val
    elif sk == 2 and kb == 2:
        J.shogai_old[s, yi, ai, KIHON, SO.noufu] += v[0]
        J.shogai_old[s, yi, ai, KIHON, SO.menjo] += v[1]
        J.shogai_old[s, yi, ai, KAKYU, SO.noufu] += v[2]
        J.shogai_old[s, yi, ai, KAKYU, SO.menjo] += v[3]
    elif sk == 2 and kb == 3:
        J.izoku_old[s, yi, ai, KIHON, SO.noufu] += v[0]
        J.izoku_old[s, yi, ai, KIHON, SO.menjo] += v[1]
        J.izoku_old[s, yi, ai, KAKYU, SO.noufu] += v[2]
        J.izoku_old[s, yi, ai, KAKYU, SO.menjo] += v[3]


def _records(path, year_base):
    """「年度,1,年齢,新旧,種類,性,値…」の行と、③の納付月数の行を返す。"""
    recs, noufu = [], {}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].lstrip("-").isdigit():
            continue
        try:
            nums = [float(x) for x in f if x != ""]
        except ValueError:
            continue
        y = int(nums[0]) + year_base
        if not YEARS.contains(y):
            continue
        if len(nums) >= 7 and int(nums[1]) == 1:
            recs.append((y, int(nums[2]), int(nums[3]), int(nums[4]), int(nums[5]), nums[6:]))
        elif len(nums) == 5 and year_base == 0:            # ③の納付月数の行
            noufu[y] = nums[1:]
    return recs, noufu


def read_kisonenkin(path, J=None):
    """③の `KISONENKIN` を国年（`SYSTEMS[0]`）に読む。戻り値 (Jukyu, 1号 {年度: [男, 女, 産休, 育休]})。"""
    J = J or Jukyu()
    recs, noufu = _records(path, 0)
    for y, age, sk, kb, sex, vals in recs:
        if AGE_LO <= age <= AGE_HI:
            _put_record(J, 0, YEARS.i(y), age - AGE_LO, sk, kb, vals)
    return J, noufu


def read_hiyousha(path, s, J=None, first_year=2020):
    """②の `kiso.*` を制度 `s`（1〜4）に読む。年度は西暦−2000。`first_year` より前（実績）は捨てる。"""
    J = J or Jukyu()
    recs, _ = _records(path, 2000)
    for y, age, sk, kb, sex, vals in recs:
        if y >= first_year and AGE_LO <= age <= AGE_HI:
            _put_record(J, s, YEARS.i(y), age - AGE_LO, sk, kb, vals)
    return J


def jukyu_from_natout(out, J=None):
    """高速版③の `NatOut.kisonenkin` から国年を入れる。戻り値 (Jukyu, 1号 {年度: [男, 女, 産休, 育休]})。"""
    J = J or Jukyu()
    K = out.kisonenkin
    for key, sk, kb in (("1-1", 1, 1), ("1-2", 1, 2), ("1-3", 1, 3), ("2-1", 2, 1),
                        ("2-2", 2, 2), ("2-3", 2, 3)):
        T = K[key]                                        # (YEARS, 54, 2 性, 欄)
        for yi in range(YEARS.n):
            for m in range(1, NA + 1):
                for si in (0, 1):
                    _put_record(J, 0, yi, m - 1, sk, kb, T[yi, m, si])
    nm = K["noufu_months"]
    noufu = {YEARS.label(yi): list(nm[yi]) for yi in range(YEARS.n)}
    return J, noufu


# ---------------------------------------------------------------- 拠出金算定対象者

@dataclass
class Santei:
    """拠出金算定対象者数（年度間値）。`by_gou[s, y, g]` の g は 0 1号 / 1 2号 / 2 3号。"""
    by_gou: np.ndarray                 # (NS, YEARS.n, 3)
    hiho_kokunen: np.ndarray           # (YEARS.n,) 1号被保険者数（①の計）
    sankyu: np.ndarray                 # (YEARS.n,)
    ikukyu: np.ndarray

    @property
    def total(self):                   # (NS, YEARS.n) 制度計
        return self.by_gou.sum(axis=2)

    @property
    def all(self):                     # (YEARS.n,) 全制度
        return self.by_gou.sum(axis=(0, 2))


_WAKU_2GOU = ("03", "08", "09", "10")
_WAKU_3GOU = ("15", "16", "17", "18")


def _yearend_to_nendokan(x, first_year):
    """年度末値 → 年度間値（前年度との平均）。`first_year` 以降を書き換え、その前年は 0。"""
    out = x.copy()
    i0 = YEARS.i(first_year)
    out[i0:] = (x[i0 - 1:-1] + x[i0:]) / 2.
    out[i0 - 1] = 0.
    return out


def read_santei_waku(waku_dir, case, noufu_1gou, first_year=2021, age_lo=20, age_hi=59):
    """①の外枠から 2号・3号・1号被保険者数を作り、③の1号（納付月数）と合わせる。"""
    def p(nn):
        return os.path.join(waku_dir, "waku%s-%s.csv" % (case, nn))
    sl = AGES.s(age_lo, age_hi)
    by = np.zeros((NS, YEARS.n, 3))
    for s, nn in enumerate(_WAKU_2GOU, start=1):
        t, _ = read_waku_class(p(nn))
        v = sum(t[k][:, sl].sum(axis=1) for k in t if k[1] in (1, 2))
        by[s, :, 1] = _yearend_to_nendokan(v, first_year)
    for s, nn in enumerate(_WAKU_3GOU, start=1):
        t, _ = read_waku_class(p(nn))
        v = sum(t[k][:, sl].sum(axis=1) for k in t if k[1] in (1, 2))
        by[s, :, 2] = _yearend_to_nendokan(v, first_year)
    _, tot = read_waku_class(p("11"))
    hk = sum(tot[k] for k in tot if k[1] in (1, 2))
    hiho_kokunen = _yearend_to_nendokan(hk, first_year)
    sankyu, ikukyu = YEARS.zeros(), YEARS.zeros()
    for y, v in noufu_1gou.items():
        yi = YEARS.i(y)
        by[0, yi, 0] = v[0] + v[1]
        sankyu[yi], ikukyu[yi] = v[2], v[3]
    return Santei(by, hiho_kokunen, sankyu, ikukyu)


# ---------------------------------------------------------------- 実績（base_data）

@dataclass
class BaseData:
    hosei_shin: np.ndarray             # (3, YEARS.n) 老齢・障害・遺族の補正率（既定 1）
    hosei_kyu: np.ndarray              # (NS, YEARS.n)
    hokenryou_m0: np.ndarray           # (YEARS.n,) 保険料月額（2004年度価格）
    fuka_hokenryou_m: np.ndarray       # (YEARS.n,) 付加保険料月額
    yuushi: np.ndarray                 # (YEARS.n,) 住宅融資債権（円）


def read_base_data(bas_dir):
    """`bas/base_data/{zisseki_hosei,hoken17000,yuushi2024}.csv`。"""
    hs = np.ones((3, YEARS.n))
    hk = np.ones((NS, YEARS.n))
    for y, v in read_year_rows(os.path.join(bas_dir, "zisseki_hosei.csv")).items():
        if YEARS.contains(y) and len(v) >= 5:
            yi = YEARS.i(y)
            hs[:, yi] = v[0:3]
            hk[0, yi], hk[1, yi] = v[3], v[4]
    m0, fm = YEARS.zeros(), YEARS.zeros()
    for y, v in read_year_rows(os.path.join(bas_dir, "hoken17000.csv")).items():
        if YEARS.contains(y):
            m0[YEARS.i(y)], fm[YEARS.i(y)] = v[0], v[1]
    yu = YEARS.zeros()
    for y, v in read_year_rows(os.path.join(bas_dir, "yuushi2024.csv")).items():
        if YEARS.contains(y):
            yu[YEARS.i(y)] = v[0] * 1e6
    return BaseData(hs, hk, m0, fm, yu)
