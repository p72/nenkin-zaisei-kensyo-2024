# -*- coding: utf-8 -*-
"""③の給付ごとの欄の並び（`algebra.Layout`）
=============================================
移植版③の8つの構造体（`nat/glva.py`）と同じ欄を、同じ順で平らに持つ。
`menjo[d][k]` は免除段階 d（0 計・1 全額・2 4分の3・3 半額・4 4分の1）×
国庫負担区分 k（0 計・1 2009年3月まで・2 2009年4月から）の15スロット。

港: nat/glva.py:zero_init
仕様: §4.2 ⑤（期間は納付・免除の区分別に持つ）、§5.1
"""
from ...algebra import Layout

__all__ = ["HIHOKENSHA", "ROREI", "ROREI_KYU", "GONEN", "SHOGAI", "IZOKU", "KAFU",
           "ICHIJIKIN", "MENJO", "menjo_slots", "MENJO_DANKAI", "KOKKO_KUBUN"]

MENJO_DANKAI = 5      # 0 計、1 全額、2 4分の3、3 半額、4 4分の1
KOKKO_KUBUN = 3       # 0 計、1 1/3 の時代、2 1/2 の時代

MENJO = tuple("menjo[%d][%d]" % (d, k) for d in range(MENJO_DANKAI) for k in range(KOKKO_KUBUN))


def menjo_slots(layout, dankai=None, kokko=None):
    """`menjo[d][k]` のスロット番号（d または k で絞る）。"""
    names = [f for f in MENJO
             if (dankai is None or f.startswith("menjo[%d]" % dankai))
             and (kokko is None or f.endswith("[%d]" % kokko))]
    return layout.slots(names)


HIHOKENSHA = Layout("hihokensha",
                    ("ninzu", "kikan", "noufu") + MENJO + ("gakusei", "wakamono", "fuka"))
ROREI = Layout("rorei", ("ninzu", "noufu") + MENJO + ("rofuku_shitasasae", "fuka"),
               no_kaitei=("fuka",), keep=("fuka",))
ROREI_KYU = Layout("rorei_kyu", ("ninzu", "noufu", "menjo", "kasa_noufu", "kasa_menjo",
                                 "rofuku_shitasasae", "fuka"),
                   no_kaitei=("fuka",), keep=("fuka",))
GONEN = Layout("gonen", ("ninzu", "noufu"))
SHOGAI = Layout("shogai", ("ninzu", "kihon", "kakyu", "menjo_kihon", "menjo_kakyu"),
                kaitei2=("kakyu", "menjo_kakyu"))
IZOKU = Layout("izoku", ("ninzu", "kihon", "kakyu"), kaitei2=("kakyu",))
KAFU = Layout("kafu", ("ninzu", "noufu") + MENJO)
ICHIJIKIN = Layout("ichijikin", ("ninzu", "kyufu", "kyufu_fuka"), no_kaitei=("kyufu_fuka",))
