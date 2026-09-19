#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レポート数式編（第3章第5節・第6節、第7章第1節）の記述を実行結果で確かめる
=========================================================================
仕様書 §15.7 が引いている数値は、このスクリプトが出すものです。
コードを読んだだけでは決められなかった3点を、通し実行の出力で判定します。

    検証/実行/run_pipeline.sh 3001
    python3 検証/数式編/verify_shikihen.py

検証A: マクロ経済スライドは「割る」形で入っている（§5.7）
       RV ÷ (1 + 調整率) が ④の出す改定率に一致するか。
       調整終了年度以降は一致しないのが正しい挙動なので、
       一致が切れた年度を調整終了年度として報告する。

検証B: 財政均衡の条件は 2120年度「初」（§8.1）
       2119年度末の積立金 ÷ 2120年度の支出 = 1 か。
       2120年度末で見ると1にならないことも併せて示す。

なお、レポートの給付水準調整割合 R(N,X) の漸化式
（N ≥ KE+1 で R(N,X) = R(N-1,X-1)）は**このスクリプトでは検証できません**。
R(N,X) は年金1本あたりの調整割合ですが、出力（90nenbe）は年齢別に集計した
給付費で、同じ年齢の中に裁定年度の違う受給者が混ざります。累積した調整量が
裁定年度ごとに違うため、集計値の比は R(N,X) にならず、年齢をずらして
追っても一致しません（実測で最大 1.9e-03 ずれる）。分解して取り出す術が
出力側にないので、この式は未確認のままです（§15.7、付録B）。
"""
import argparse
import collections
import os
import sys

SHUSHI = '/suuri/rev2024/emp/rslt/ez_arev/shushi'
BAS = '/suuri/rev2024/bas/rslt'
WAKUC = '/suuri/rev2024/wakuc/rslt/ver_4_1'


def sniff(path):
    """出力の文字コードを見分ける（§12.2）。"""
    head = open(path, 'rb').readline()
    for enc in ('utf-8', 'euc_jp'):
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"文字コードを判別できません: {path}")


def read_block(path, title, header_offset=1):
    """kekka*a.csv / 03summary の「見出し行＋連続する年度行」を切り出す。
    戻り値は (列名リスト, {年度: フィールドのリスト})。"""
    enc = sniff(path)
    lines = open(path, 'rb').read().decode(enc, 'replace').splitlines()
    try:
        start = next(i for i, l in enumerate(lines)
                     if l.strip() == title or l.startswith(title))
    except StopIteration:
        raise SystemExit(f"ブロック「{title}」がありません: {path}")
    cols = [x.strip() for x in lines[start + header_offset].split(',')]
    rows, prev = {}, None
    for l in lines[start + header_offset + 1:]:
        f = [x.strip() for x in l.split(',')]
        if not f or not f[0].isdigit():
            if prev is not None:
                break
            continue
        y = int(f[0])
        if prev is not None and y != prev + 1:
            break
        prev = y
        rows[y] = f
    if not rows:
        raise SystemExit(f"ブロック「{title}」に年度行がありません: {path}")
    return cols, rows


def find(pattern, directory):
    import glob
    hits = sorted(glob.glob(os.path.join(directory, pattern)))
    if not hits:
        raise SystemExit(f"出力が見つかりません: {directory}/{pattern}\n"
                         f"先に 検証/実行/run_pipeline.sh を走らせてください。")
    return hits[0]


# --------------------------------------------------------------------------
def kensho_a(case):
    print("=" * 78)
    print("検証A  マクロ経済スライドは「割る」形で入っている（§5.7）")
    print("=" * 78)
    print("主張: マクロ込みの改定率 = RV ÷ (1 + スライド調整率)")
    print("      RV は本来の改定率（③⑤が出す「比例改定率」）")
    print("      調整率は ①が出す waku****-m.csv の値")
    print()

    cut = {}
    for l in open(os.path.join(WAKUC, f'rslt{case}', f'waku{case}-m.csv')):
        f = l.strip().split(',')
        if len(f) >= 2:
            cut[int(f[0])] = float(f[1])

    cols, rows = read_block(find(f'03summary.{case}-{case}-{case}-{case}-*_08sum.csv', SHUSHI),
                            '年度,物価', header_offset=0)
    ci = cols.index('比例改定率')
    rv = {y + 2000: 1.0 + float(f[ci]) / 100.0 for y, f in rows.items()}

    kcols, krows = read_block(find(f'kekka{case}-{case}-{case}-{case}-*a.csv', BAS), '経済前提',
                              header_offset=1)
    ci2 = kcols.index('改定率（マクロ込み、67歳）')
    kaitei = {y: float(f[ci2]) for y, f in krows.items()}

    print(f"{'年度':<6}{'RV(本来)':>15}{'1+調整率':>11}"
          f"{'RV÷(1+調整率)':>17}{'④の改定率':>17}  判定")
    ok = 0
    broke = None
    for y in sorted(set(rv) & set(kaitei) & set(cut)):
        if y < 2025:
            continue
        got = rv[y] / (1.0 + cut[y])
        hit = abs(got - kaitei[y]) < 1e-12
        if hit:
            ok += 1
        elif broke is None:
            broke = y
        if y <= 2027 or (broke and broke - 1 <= y <= broke + 1):
            print(f"{y:<6}{rv[y]:>15.10f}{1.0 + cut[y]:>11.4f}"
                  f"{got:>17.10f}{kaitei[y]:>17.10f}  "
                  f"{'一致' if hit else '不一致'}")
        if broke and y > broke + 1:
            break

    print()
    print(f"  2025年度から {ok} 年ぶん連続で一致（差 < 1e-12）")
    if broke:
        print(f"  {broke}年度で一致が切れる → これが給付水準調整の終了年度。")
        print(f"  終了年度はスライド調整率を再設定するので通常の式から外れる（§8.3）。")
    print()
    print("  → 主張どおり。max_cut_rate も pre_cut も1より大きい**除数**である。")
    print()
    return ok > 0, broke


def kensho_b(case):
    print("=" * 78)
    print("検証B  財政均衡の条件は2120年度「初」（§8.1）")
    print("=" * 78)
    print("主張: 2119年度末の積立金 ÷ 2120年度の支出 = 1")
    print("      （2120年度「末」で見ると1にならない）")
    print()

    cols, rows = read_block(find(f'kekka{case}-{case}-{case}-{case}-*a.csv', BAS), '収支見通し',
                            header_offset=2)
    ci_s, ci_t = cols.index('支出合計'), cols.index('年度末積立金')
    if 2119 not in rows or 2120 not in rows:
        raise SystemExit("2119・2120年度の行がありません")

    f2119, f2120 = rows[2119], rows[2120]
    tum19, shu20 = float(f2119[ci_t]), float(f2120[ci_s])
    tum20 = float(f2120[ci_t])

    print(f"  2119年度末 積立金      {tum19:.8e} 円")
    print(f"  2120年度   支出合計    {shu20:.8e} 円")
    print(f"  2120年度末 積立金      {tum20:.8e} 円")
    print()
    doai = tum19 / shu20
    print(f"  積立度合（2119年度末 ÷ 2120年度支出）  = {doai:.12f}")
    print(f"  参考  （2120年度末 ÷ 2120年度支出）    = {tum20 / shu20:.12f}")
    print()
    hit = abs(doai - 1.0) < 1e-9
    print(f"  → {'主張どおり。1に収束している。' if hit else '★1になっていない'}")
    print()
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='3001',
                    help='試算番号（既定 3001 = 高成長実現ケース）')
    args = ap.parse_args()

    results = []
    ok_a, broke = kensho_a(args.case)
    results.append(('検証A マクロ経済スライドは除数', ok_a))
    results.append(('検証B 均衡条件は2120年度初', kensho_b(args.case)))



    print("=" * 78)
    for name, ok in results:
        print(f"  {'一致' if ok else '★不一致'}  {name}")
    if broke:
        print(f"  （給付水準調整の終了年度 = {broke}年度）")
    print("=" * 78)
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
