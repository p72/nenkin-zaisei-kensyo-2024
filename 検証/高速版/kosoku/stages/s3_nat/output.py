# -*- coding: utf-8 -*-
"""③の受け渡しファイルの書き手（移植版の列配置。`KISONENKIN` `DOKUZI` `KOKUKAITE`）
=================================================================================
④基礎年金と比較ツールが無改造で読めるように、移植版と同じ並びで書く。
先頭の実行時刻の行は `asctime` で固定できる。数値は港と同じ `%20.14e`。

    KISONENKIN{case}-{case}-{case}
        年度,1,年齢階級,新旧,種類,性, 値…        （年齢階級 63 = 63歳以下、64〜115）
        年度, 納付月数(男), 納付月数(女), 産前産後, 育児     （5列の行）
        年度,2,1,性, 年度間受給者数（老齢 9列）
        年度,2,2,性, 年度間受給者数（障害 4列）
        年度,2,3,1, 遺族子 2列 ／ 年度,2,3,2, 遺族 2列
    DOKUZI{case}-{case}-{case}.csv   年度, 独自給付 10列
    KOKUKAITE-{case}-{case}E.csv     年度−2000, 単年度改定率（67〜115歳）

港: nat/stat.py:stat
港: nat/econ.py:rslt_out
仕様: §12.4
"""
import os

import numpy as np

from ...axis import YEARS, AGES
from .aggregate import AGE_CLASS_N, UNDER

__all__ = ["to_port_csv", "write_kisonenkin", "write_dokuzi", "write_kokukaite"]

_ASCTIME_FIXED = "Thu Jan  1 00:00:00 1970\n"


def _e(v):
    return "%20.14e" % v


def _header(case, pol, asctime):
    import time
    if asctime is None:
        asctime = time.asctime() + "\n"
    ks = pol.get("kokunen.kisai_shitasasae")
    return ("%s\n%s-%s-%s\nKisai_Shitasasae , %f\nHenkouSeinendo , %d\nKako_Saimu , 0\n"
            "Kugiri_Nendo , %d\nJyukyusha_Nomi , 0\n#99-0000-0000\n"
            % (asctime, case, case, case, ks, pol.get("kokunen.years.henkou_seinendo"),
               pol.get("kokunen.years.kugiri_nendo")))


def write_kisonenkin(out, pol, case, path, asctime=None, first_year=2020):
    K = out.kisonenkin
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(_header(case, pol, asctime))
        for year in range(first_year, YEARS.last + 1):
            yi = YEARS.i(year)
            for m in range(1, AGE_CLASS_N):
                age = UNDER + m - 1
                for tag, key in (((1, 1), "1-1"), ((1, 2), "1-2"), ((1, 3), "1-3"),
                                 ((2, 1), "2-1"), ((2, 2), "2-2"), ((2, 3), "2-3")):
                    for si in (0, 1):
                        vals = K[key][yi, m, si]
                        fp.write("%d,1,%d,%d,%d,%d," % (year, age, tag[0], tag[1], si + 1))
                        fp.write(",".join(_e(v) for v in vals) + "\n")
            nm = K["noufu_months"][yi]
            fp.write("%d,%s,%s,%s,%s\n" % (year, _e(nm[0]), _e(nm[1]), _e(nm[2]), _e(nm[3])))
            for si in (0, 1):
                fp.write("%d,2,1,%d," % (year, si + 1)
                         + ",".join(_e(v) for v in K["nendokan_rorei"][yi, si]) + "\n")
            for si in (0, 1):
                fp.write("%d,2,2,%d," % (year, si + 1)
                         + ",".join(_e(v) for v in K["nendokan_shogai"][yi, si]) + "\n")
            ko = K["nendokan_izoku_ko"][yi]
            fp.write("%d,2,3,1,%s,%s\n" % (year, _e(ko), _e(ko)))
            iz = K["nendokan_izoku"][yi]
            fp.write("%d,2,3,2,%s,%s\n" % (year, _e(iz[0]), _e(iz[1])))


def write_dokuzi(out, pol, case, path, asctime=None, first_year=2020):
    D = out.dokuzi["table"]
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(_header(case, pol, asctime))
        for year in range(first_year, YEARS.last + 1):
            fp.write("%d," % year + ",".join(_e(v) for v in D[YEARS.i(year)]) + "\n")


def write_kokukaite(out, path, first_age=67, last_age=115, first_year=2005):
    """単年度改定率（港: nat/econ.py:rslt_out。年度ラベルは西暦−2000）。"""
    kt = out.kokukaite
    with open(path, "w", encoding="utf-8") as fp:
        for year in range(first_year, YEARS.last + 1):
            row = kt[YEARS.i(year), AGES.s(first_age, last_age)]
            # 港のラベルは西暦−2000 ＝ 年度の軸の添字。行末のカンマも港のまま
            fp.write("%d," % YEARS.i(year) + ",".join(_e(v) for v in row) + ",\n")


def to_port_csv(out, pol, case, directory, asctime=_ASCTIME_FIXED):
    """`directory` に3本を書く。戻り値はパスの dict。"""
    os.makedirs(directory, exist_ok=True)
    paths = {
        "kisonenkin": os.path.join(directory, "KISONENKIN%s-%s-%s" % (case, case, case)),
        "dokuzi": os.path.join(directory, "DOKUZI%s-%s-%s.csv" % (case, case, case)),
        "kokukaite": os.path.join(directory, "KOKUKAITE-%s-%sE.csv" % (case, case)),
    }
    write_kisonenkin(out, pol, case, paths["kisonenkin"], asctime)
    write_dokuzi(out, pol, case, paths["dokuzi"], asctime)
    write_kokukaite(out, paths["kokukaite"])
    return paths
