# -*- coding: utf-8 -*-
"""②の出力 — ⑤へ渡す `shus.*`、④へ渡す `kiso.*`、③⑤が読む `kaitea/b`（移植版 `crshfl.cpp`
`outkn.cpp` `econ.cpp` の書き手）
=====================================================================================
配置は移植版の CSV と同じにする（⑤の `read_shus`、④の `read_hiyousha`、`read_kaite` が
無改造で読める）。`shusg`（年齢 × 経過年の被保険者）と `bunpu_*`（⑥分布推計の入力）は
書かない（⑤④は読まない）。

港: emp_kyufu/crshfl.py:crshfl
港: emp_kyufu/outkn.py:outkn
仕様: §7.2、§7.3、§12.2
"""
import os

import numpy as np

from ...axis import YEARS
from .inputs import NX, NI, SYSTEMS
from .shke import _C

__all__ = ["write_shus", "write_kiso", "write_kaite", "to_port_csv"]

_F = "%21.14e"


def _row(vals, fmt=_F):
    return ",".join(fmt % v for v in vals)


def _header(pol, system, case):
    """港の `flck` が写す来歴の代わり（⑤は `#99` の行を探す）。"""
    L = ["case, %s" % case, "system, %s" % system, "source, kosoku(高速版)",
         "KS, %d" % (YEARS.i(pol.get("kounen.years.kijun")) - 1), "KE, %d" % (YEARS.n - 1),
         "KIJUN, %d" % YEARS.i(pol.get("kounen.years.kijun")), "#99-0000-0000"]
    return "\n".join(L) + "\n"


def write_shus(path, pol, system, case, ag, E, pseid, partyr3, flg_hiho70=0, partyr4=None):
    """⑤が読む `shus.{case}_{system}`。港: emp_kyufu/crshfl.py:crshfl"""
    KS = YEARS.i(pol.get("kounen.years.kijun")) - 1
    KE = YEARS.n - 1
    FLKS = YEARS.i(pol.get("kounen.years.stty"))
    xa, xb = int(pol.get("kounen.ages.xa")), int(pol.get("kounen.ages.xb"))
    A = ag.ks
    d3x, kf = ag.d3x, ag.kfprx
    out = [_header(pol, system, case)]
    w = out.append
    w("%d,%d\n" % (KS, KE))
    w("経済的要素\n")
    w("年度,利回り,賃金,物価,年金改定率(比例),年金改定率(加給),年金改定率(基礎),年金改定率(物価)\n")
    for k in range(1, KE + 1):
        w("%d,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f\n"
          % (k, E.ri[k], E.h[k], E.ci[k], E.hh[k], E.hp2[k, 67], E.hp2[k, 67], E.ci2[k, 67]))
    ks = range(FLKS, KE + 1)
    w(",AP,,,,APDUM\nK,S=0,S=1,S=2,S=3,S=1,S=2,S=3\n")
    for k in ks:
        w("%d,%s,%s\n" % (k, _row(A["ap"][k, 0:4]), _row(A["apdum"][k, 1:4])))
    if flg_hiho70 == 0:
        w(",AP65,,,,AP70,,,,AP75\nK,S=0,S=1,S=2,S=3,S=0,S=1,S=2,S=3,S=0,S=1,S=2,S=3\n")
        for k in ks:
            w("%d,%s,%s,%s\n" % (k, _row(A["ap65"][k]), _row(A["ap70"][k]), _row(A["ap75"][k])))
        w(",A,,,,ADUM,,,A60,,,,A65,,,,A70,,,,A75\n")
        w("k,s=0,s=1,s=2,s=3,s=1,s=2,s=3,s=0,s=1,s=2,s=3,s=0,s=1,s=2,s=3,s=0,s=1,s=2,s=3,s=0,s=1,s=2,s=3\n")
        for k in ks:
            w("%d,%s,%s,%s,%s,%s,%s\n" % (k, _row(A["a"][k]), _row(A["adum"][k, 1:4]), _row(A["a60"][k]),
                                          _row(A["a65"][k]), _row(A["a70"][k]), _row(A["a75"][k])))
    w("AIKU\nK,S=0,S=1,S=2,S=3\n")
    for k in ks:
        w("%d,%s,%s\n" % (k, _row(A["aiku"][k]), _row(A["aikudum"][k, 1:4])))
    w("AAL\nK,S=0,S=1,S=2,S=3\n")
    for k in ks:
        w("%d,%s\n" % (k, _row(A["aal"][k])))
    if pseid == 0:
        k = partyr3
        w("PARTHOU\nK,S=0,S=1,S=2,S=3\n")
        if flg_hiho70 == 0:
            w("%d,%s\n" % (k, ",".join(_row(A[n][k]) for n in ("apart", "aikupart", "a60part", "a65part", "a70part", "a75part"))))
            if partyr4 is not None and partyr4 >= 0:                # 適用拡大（レバー）の年度の行（港は見出し無しで続く）
                k = partyr4
                w("%d,%s\n" % (k, ",".join(_row(A[n][k]) for n in ("apart", "aikupart", "a60part", "a65part", "a70part", "a75part"))))
    xstrt = xa - 1
    for x in range(xstrt, xb + 1):
        for s in (1, 2, 3):
            w("D3X(k;s;i;0),%d,%d\nk,合計,老退,老在,通退,通在,障害,遺族\n" % (x, s))
            c = _C[0]
            for k in ks:
                d = d3x[k, x, s, :, c]
                w("%d,%s\n" % (k, _row([d[0], d[1] + d[5], d[2] + d[6], d[3] + d[7], d[4] + d[8], d[9] + d[10],
                                        d[11] + d[12] + d[13]])))
    for x in range(xstrt, xb + 1):
        for s in range(4):
            for i in range(NI):
                w("D3X,%d,%d,%d\nK,J=25,J=7,J=8,J=9,J=10,J=11,J=12,KOFU\n" % (x, s, i))
                for k in ks:
                    d = d3x[k, x, s, i]
                    vals = [d[_C[25]]] + [d[_C[j]] for j in range(7, 13)]
                    vals += [d[_C[22]] + d[_C[23]] + d[_C[24]], d[_C[22]] + d[_C[24]], d[_C[23]]]
                    w("%d,%s\n" % (k, _row(vals)))
    for x in range(xstrt, xb + 1):
        for i in range(NI):
            w("KFPRX,%d,%d\nK,(S-J)=0-1,0-2,1-1,1-2,2-1,2-2,3-1,3-2\n" % (x, i))
            for k in ks:
                w("%d,%s\n" % (k, _row([kf[k, x, s, i, j] for s in range(4) for j in (1, 2)])))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("".join(out))


def write_kiso(path, pol, system, case, ag):
    """④が読む `kiso.{case}_{system}`。港: emp_kyufu/outkn.py:outkn"""
    FLKS = YEARS.i(pol.get("kounen.years.stty")); KE = YEARS.n - 1
    o, r = ag.okiso2x, ag.okisor
    out = [_header(pol, system, case)]
    w = out.append
    for k in range(FLKS, KE + 1):
        for x in range(63, NX):
            for ss in (1, 2):
                w("%d, 1, %d, 1, 1, %d, %s\n" % (k, x, ss, _row([o[k, x, ss, 1, 1], 0., 0., o[k, x, ss, 1, 3]], " " + _F)))
            for ss in (1, 2):
                w("%d, 1, %d, 1, 2, %d, %s\n" % (k, x, ss, _row([o[k, x, ss, 2, 1], o[k, x, ss, 2, 2], o[k, x, ss, 2, 3], 0., 0.], " " + _F)))
            for ss in (1, 2):
                w("%d, 1, %d, 1, 3, %d, %s\n" % (k, x, ss, _row([o[k, x, ss, 3, 1], o[k, x, ss, 3, 2]], " " + _F)))
            for ss in (1, 2):
                w("%d, 1, %d, 2, 1, %d, %s\n" % (k, x, ss, _row([o[k, x, ss, 1, 4], 0., o[k, x, ss, 1, 5], 0., o[k, x, ss, 1, 6], 0., 0., 0.], " " + _F)))
            for ii in (2, 3):
                for ss in (1, 2):
                    w("%d, 1, %d, 2, %d, %d, %s\n" % (k, x, ii, ss, _row([o[k, x, ss, ii, 4], 0., o[k, x, ss, ii, 5], 0.], " " + _F)))
        for ss in (1, 2):
            w("%d, 2, 1, %d, %s\n" % (k, ss, _row([r[k, ss, 1, 2], r[k, ss, 1, 3], r[k, ss, 3, 2], r[k, ss, 3, 3],
                                                 r[k, ss, 5, 2], r[k, ss, 5, 3], r[k, ss, 7, 2], r[k, ss, 7, 3], 0.], " " + _F)))
        for ss in (1, 2):
            w("%d, 2, 2, %d, %s\n" % (k, ss, _row([r[k, ss, 9, 2], r[k, ss, 9, 3], r[k, ss, 10, 2], r[k, ss, 10, 3]], " " + _F)))
        for ss in (1, 2):
            w("%d, 2, 3, %d, %s\n" % (k, ss, _row([r[k, ss, 11, 2], r[k, ss, 11, 3], r[k, ss, 12, 2], r[k, ss, 12, 3],
                                                 r[k, ss, 13, 2], r[k, ss, 13, 3]], " " + _F)))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("".join(out))


def write_kaite(path_a, path_b, E):
    """`kaitea`（比例 `arv_hp`）と `kaiteb`（定額 `arv_hh`）: 年度, 67〜115 歳。港: emp_kyufu/econ.py:econ"""
    KE = YEARS.n - 1
    for path, arr in ((path_a, E.arv_hp), (path_b, E.arv_hh)):
        with open(path, "w", encoding="utf-8") as fp:
            for k in range(5, KE + 1):
                fp.write("%d,%s\n" % (k, _row(arr[k, 67:116], "%.14e")))


def to_port_csv(runs, case, outdir):
    """{system: KyufuRun} を港の配置で `outdir` に書く。戻り値は書いたパス。"""
    for d in ("shus", "kiso", "kaite"):
        os.makedirs(os.path.join(outdir, d), exist_ok=True)
    paths = {}
    for name, r in runs.items():
        p = os.path.join(outdir, "shus", "shus.%s-%s-%s_%s" % (case, case, case, name))
        write_shus(p, r.pol, name, case, r.ag, r.E, r.pseid, r.partyr3, partyr4=(r.partyr4 if r.flg_part else None))
        q = os.path.join(outdir, "kiso", "kiso.%s-%s-%s_%s" % (case, case, case, name))
        write_kiso(q, r.pol, name, case, r.ag)
        paths[name] = {"shus": p, "kiso": q}
        if r.pseid == 0:
            a = os.path.join(outdir, "kaite", "kaitea-%s-%se" % (case, case))
            b = os.path.join(outdir, "kaite", "kaiteb-%s-%se" % (case, case))
            write_kaite(a, b, r.E)
            paths[name]["kaitea"] = a; paths[name]["kaiteb"] = b
    return paths
