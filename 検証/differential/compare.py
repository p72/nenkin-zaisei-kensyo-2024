#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分テスト: 原本Cの出力 vs Python移植の出力
===========================================
build_and_run.sh が原本 プログラム/国民年金/econ.c を無修正でコンパイル・実行し、
c_series.csv を吐く。それを port_econ.py の出力と1要素ずつ突き合わせる。

使い方:
    検証/differential/build_and_run.sh            # → ビルドディレクトリのパスを出力
    python3 検証/differential/compare.py <そのパス>
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import port_econ as P

# Cが double を %.17g で出すので、往復誤差だけを許す
TOL_REL = 1e-14


def main():
    if len(sys.argv) < 2:
        print("usage: compare.py <build_dir>", file=sys.stderr)
        return 2
    build = sys.argv[1]
    econ_csv = os.path.join(build, 'econ_input.csv')
    series = os.path.join(build, 'c_series.csv')
    for p in (econ_csv, series):
        if not os.path.exists(p):
            print(f"見つかりません: {p}\nbuild_and_run.sh を先に実行してください。",
                  file=sys.stderr)
            return 2

    # 経済前提はCがUTF-8コピーを読むので、Python側も同じファイルを読む
    tannen, ruiseki, full = econ_utf8(econ_csv)

    rows = list(csv.DictReader(open(series, encoding='utf-8')))
    n_ok = n_ng = 0
    ng_samples = []
    for r in rows:
        nendo = int(r['nendo']); nenrei = int(r['nenrei'])
        for field, pyval in (('tannen', tannen[nendo][nenrei]),
                             ('full_pension',
                              full[nendo][nenrei] if nendo >= P.SHONENDO else 0.0)):
            cval = float(r[field])
            scale = max(abs(cval), abs(pyval), 1.0)
            if abs(cval - pyval) <= TOL_REL * scale:
                n_ok += 1
            else:
                n_ng += 1
                if len(ng_samples) < 15:
                    ng_samples.append((nendo, nenrei, field, cval, pyval))

    print("=" * 74)
    print("差分テスト: 原本C（無修正コンパイル） vs Python移植")
    print("=" * 74)
    print(f"比較対象: {len(rows)} 行 × 2 系列（単年改定率・老齢基礎年金満額）")
    print(f"年度 2005〜2035 / 年齢 60〜75歳")
    print()
    if ng_samples:
        print("不一致のサンプル:")
        for nendo, nenrei, field, cval, pyval in ng_samples:
            print(f"  {nendo}年度 {nenrei}歳 {field}: C={cval!r}  Python={pyval!r}")
        print()
    print(f"一致 {n_ok} / 不一致 {n_ng}")
    print("=" * 74)
    return 0 if n_ng == 0 else 1


def econ_utf8(path):
    """Cが読むUTF-8コピーをそのまま読ませるため、デコーダだけ差し替える"""
    real_read = P.econ_read

    def econ_read_utf8(p):
        cpi_up, base_up_real = {}, {}
        raw = open(p, encoding='utf-8').read()
        nendo = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            b = [float(x) for x in line.split(',') if x.strip() != '']
            nendo = int(b[0]) + 2000
            cpi_up[nendo] = 1. + b[6] / 100.
            base_up_real[nendo] = 1. + b[5] / 100.
        for k in range(nendo + 1, P.SAISHUNENDO + 1):
            cpi_up[k] = cpi_up[nendo]
            base_up_real[k] = base_up_real[nendo]
        return cpi_up, base_up_real

    P.econ_read = econ_read_utf8
    try:
        return P.econ(path)
    finally:
        P.econ_read = real_read


if __name__ == '__main__':
    sys.exit(main())
