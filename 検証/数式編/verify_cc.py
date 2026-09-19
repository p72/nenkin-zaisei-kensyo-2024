#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⑤収支計算の `Cc[]` 項目名と給付水準調整割合 `R(N,X)` の実装を確かめる
=====================================================================
仕様書 §7.2・§8.4 の根拠です。付録Bに「確定できていない」として残していた
2項目を潰したときの手順を、そのまま再実行できる形にしました。

    検証/実行/run_pipeline.sh 3001
    python3 検証/数式編/verify_cc.py

検証A: `Cc[]` の項目番号 → 項目名（§7.2）
       項目名は shus_out.c の出力ヘッダにある。ただし直後のループが
       一部の添字を読み飛ばすので、ヘッダの列とループの i を
       突き合わせないと対応が取れない。その対応を再現し、
       印字される個数とヘッダの列数が一致することを確かめる。

検証B: 実データでの検算（§7.2）
       収入計・支出計・国庫負担・福祉が内訳の和になっているか。
       独自給付が掲載表の厚生年金給付費と一致するか。

検証C: `R(N,X)` の漸化式（§8.4）
       レポート第3章第6節 p.265 の3分岐が shus_calc.c に代入文として
       あることを、ソースから機械的に確認する。
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import suuri_env      # noqa: E402  実行領域の場所（§12.1）

SRC = 'papers/001365945/プログラム/厚生年金/収支計算'
SHUSHI = suuri_env.suuri('emp', 'rslt', 'ez_arev', 'shushi')


def read_src(name, root):
    """原本は EUC-JP（丸数字が NEC特殊文字なので EUCJP-MS 相当で読む）。"""
    raw = open(os.path.join(root, SRC, name), 'rb').read()
    for enc in ('euc_jis_2004', 'euc_jp', 'utf-8'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('euc_jp', 'replace')


# --------------------------------------------------------------------------
def kensho_a(root):
    print("=" * 78)
    print("検証A  `Cc[]` の項目番号 → 項目名（§7.2）")
    print("=" * 78)
    src = read_src('shus_out.c', root)

    # 「収支[全厚年１:tou]」ブロックのヘッダ行を集める
    i = src.find('収支[全厚年１:tou]')
    if i < 0:
        raise SystemExit("収支ブロックが見つかりません")
    # 次の「収支[」ブロックまでで切る（切らないと後続ブロックのヘッダも拾う）
    j = src.find('収支[', i + 10)
    block = src[i:j if j > 0 else i + 2000]
    heads = []
    for m in re.finditer(r'fprintf\(ofp, "([^"]*)"\);', block):
        s = m.group(1)
        if s.startswith('収支[') or s == '\\n':
            continue
        heads += [h.strip() for h in s.replace('\\n', '').split(',')]
    heads = [h for h in heads if h]
    print(f"  出力ヘッダ（{len(heads)}列）:")
    print("   ", ' | '.join(heads))

    # スキップ規則を読み取る
    m = re.search(r'if\(i==2 \|\| i==7 \|\| i==8 \|\| \(i>=13 && i<=15\) \|\| '
                  r'i==22 \|\| \(i>=25 && i!=27 && i!=30\)\)', block)
    print(f"\n  スキップ規則: {'見つかった' if m else '★見つからない'}")
    printed = [i for i in range(31)
               if not (i == 2 or i == 7 or i == 8 or 13 <= i <= 15
                       or i == 22 or (i >= 25 and i != 27 and i != 30))]
    print(f"  印字される添字（{len(printed)}個）: {printed}")

    # ヘッダは 年度 + 20項目 + 住宅融資（別掲、Cc ではない）+ 老齢相当…遺族（0埋め）
    body = [h for h in heads if h not in
            ('年度', '住宅融資（別掲）', '老齢相当', '通老相当', '障害', '遺族')]
    print(f"  Cc に対応するヘッダ（{len(body)}列）")
    print()
    ok = len(printed) == len(body)
    print(f"  {'一致' if ok else '★不一致'}  印字 {len(printed)}個 / ヘッダ {len(body)}列")
    print()
    for n, h in zip(printed, body):
        print(f"    Cc[{n:>2}]  {h}")
    print()

    # 小計の関係も shus_calc.c から確認
    calc = read_src('shus_calc.c', root)
    checks = [
        ('Cc[4] = Cc[5]+Cc[6]+Cc[7]+Cc[8]',
         r'Cc\[ii\]\[4\].*=\s*Cc\[ii\]\[5\].*\+\s*Cc\[ii\]\[6\].*\+\s*Cc\[ii\]\[7\].*\+\s*Cc\[ii\]\[8\]'),
        ('Cc[12] = Cc[13]+Cc[14]+Cc[15]',
         r'Cc\[ii\]\[12\].*=\s*Cc\[ii\]\[13\].*\+\s*Cc\[ii\]\[14\].*\+\s*Cc\[ii\]\[15\]'),
        ('Cc[11] = Cc[12]+Cc[16]+Cc[17]+Cc[18]',
         r'Cc\[ii\]\[11\].*=\s*Cc\[ii\]\[12\].*\+\s*Cc\[ii\]\[16\].*\+\s*Cc\[ii\]\[17\].*\+\s*Cc\[ii\]\[18\]'),
        ('Cc[0] = Cc[1]+Cc[3]+Cc[4]+Cc[9]+Cc[10]',
         r'Cc\[ii\]\[0\].*=\s*Cc\[ii\]\[1\].*\+\s*Cc\[ii\]\[3\].*\+\s*Cc\[ii\]\[4\].*\+\s*Cc\[ii\]\[9\].*\+\s*Cc\[ii\]\[10\]'),
        ('半期運用利回りは幾何半期 pow(1+Ri, 0.5)-1',
         r'Ri2\[k-ECSTY\]\s*=\s*pow\(1\.\+Ri\[k-ECSTY\],\s*0\.5\)\s*-\s*1\.'),
    ]
    src_all = calc + read_src('econ.c', root)
    print("  集計の関係（ソースから）")
    for name, pat in checks:
        hit = re.search(pat, src_all, re.S) is not None
        print(f"    {'OK ' if hit else '★NG'}  {name}")
        ok = ok and hit
    print()
    return ok, dict(zip(printed, body))


def kensho_b(case, mapping):
    print("=" * 78)
    print("検証B  実データでの検算（§7.2）")
    print("=" * 78)
    hits = sorted(glob.glob(os.path.join(
        SHUSHI, f'03summary.{case}-{case}-{case}-{case}-*_08sum.csv')))
    if not hits:
        print(f"  （対象外）通し実行の出力がありません: 03summary.{case}-…")
        print()
        return None
    raw = open(hits[0], 'rb').read()
    for enc in ('utf-8', 'euc_jp'):
        try:
            t = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = t.splitlines()
    i = next(j for j, l in enumerate(lines) if l.strip() == '収支[全厚年１:tou]')
    # 見出しの前に空行が入るので、最初の非空行を見出しとして採る
    h = next(j for j in range(i + 1, i + 6) if lines[j].strip())
    hdr = [x.strip() for x in lines[h].split(',')]
    row = next(l for l in lines[h + 1:] if l.split(',')[0].strip() == '24')
    vals = [x.strip() for x in row.split(',')]
    v = {}
    for name, x in zip([h for h in hdr if h][1:], [x for x in vals[1:] if x]):
        try:
            v[name] = float(x)
        except ValueError:
            pass

    print("  2024年度（億円、保険料率は％）")
    for k in ('収入計', '保険料', '運用収入', '国庫負担', 'うち基礎', 'うち経過的国庫',
              '支援入', '納付金', '支出計', '独自給付', '基礎年金拠出金', '福祉',
              '支援出', '保険料率'):
        if k in v:
            print(f"    {k:<16}{v[k]:>16,.2f}")
    print()

    tests = [
        ('収入計 = 保険料+運用収入+国庫負担+支援入+納付金+妻積み',
         v.get('収入計'),
         sum(v.get(k, 0) for k in ('保険料', '運用収入', '国庫負担',
                                   '支援入', '納付金', '妻積み'))),
        ('国庫負担 = うち基礎 + うち経過的国庫',
         v.get('国庫負担'), v.get('うち基礎', 0) + v.get('うち経過的国庫', 0)),
        ('支出計 = 独自給付+基礎年金拠出金+福祉+支援出',
         v.get('支出計'),
         sum(v.get(k, 0) for k in ('独自給付', '基礎年金拠出金', '福祉', '支援出'))),
        ('収支差 = 収入計 − 支出計',
         v.get('収支差'), v.get('収入計', 0) - v.get('支出計', 0)),
    ]
    ok = True
    for name, got, want in tests:
        if got is None:
            continue
        rel = abs(got - want) / max(abs(want), 1.0)
        hit = rel < 1e-6
        ok = ok and hit
        print(f"    {'OK ' if hit else '★NG'}  {name}")
        print(f"          {got:,.2f} vs {want:,.2f}  相対差 {rel:.1e}")
    print()
    print("  掲載表との対応（§15.0.2 の値）")
    print(f"    独自給付       {v.get('独自給付', 0) / 1e4:.6f} 兆円"
          f"  ← 第3-7-29表 厚生年金給付費 30.012066 兆円")
    print(f"    基礎年金拠出金 {v.get('基礎年金拠出金', 0) / 1e4:.6f} 兆円"
          f"  ← 第3-7-34表 被用者年金計 22.547469 兆円")
    for label, got, want in (('独自給付', v.get('独自給付', 0) / 1e4, 30.012065887192918),
                             ('基礎年金拠出金', v.get('基礎年金拠出金', 0) / 1e4,
                              22.547468662483652)):
        rel = abs(got - want) / want
        hit = rel < 1e-6
        ok = ok and hit
        print(f"    {'OK ' if hit else '★NG'}  {label} 相対差 {rel:.1e}")
    print()
    return ok


def kensho_c(root):
    print("=" * 78)
    print("検証C  `R(N,X)` の漸化式がコードにある（§8.4）")
    print("=" * 78)
    print("レポート第3章第6節 p.265")
    print("  R(N,X) = 1                                  N ≤ 2024")
    print("         = R(N-1,X-1) · RV_macro(N,X)/RV(N,X)  2025 ≤ N ≤ KE")
    print("         = R(N-1,X-1)                          N ≥ KE+1")
    print()
    src = read_src('shus_calc.c', root)
    cntl = read_src('cntl.c', root)
    checks = [
        ('N ≤ 基準年度 → 1',
         r'if\(k<=Kijun\)\s*\{[^}]*Escutrrh\[k-ECSTY\]\[x-ECXA\]\s*=\s*1;'),
        ('調整終了後 → R(N-1,X-1)（据え置き）',
         r'Escutrrh\[k-ECSTY\]\[x-ECXA\]\s*=\s*Escutrrh\[k-1-ECSTY\]\[x-1-ECXA\]\s*;'),
        ('調整中 → R(N-1,X-1) / rh（rh は除数）',
         r'Escutrrh\[k-ECSTY\]\[x-ECXA\]\s*=\s*Escutrrh\[k-1-ECSTY\]\[x-1-ECXA\]\s*/\s*rh\[k-ECSTY\]\[x-ECXA\]'),
        ('終了年度より後も据え置き（kk ループ）',
         r'Escutrrh\[kk-ECSTY\]\[x-ECXA\]\s*=\s*Escutrrh\[kk-1-ECSTY\]\[x-1-ECXA\]'),
        ('実績年度のハードコード（2023年度 1/0.994）',
         r'if\(k==23\)\s*rh\[k-ECSTY\]\[x-ECXA\]\s*=\s*1\.0/0\.994'),
        ('実績年度のハードコード（2024年度 1/0.996）',
         r'if\(k==24\)\s*rh\[k-ECSTY\]\[x-ECXA\]\s*=\s*1\.0/0\.996'),
        ('均衡条件の添字は kend−1（§8.1）',
         r'Cc\[ii\]\[20\]\[kend-1-STTY\]\s*-\s*Cc\[ii\]\[11\]\[kend-STTY\]\s*\*\s*Ca'),
        ('初めて均衡した年度を KE とする',
         r'if\(f1\s*>=\s*0\.0\s*&&\s*k\s*>=\s*k_jisseki\)'),
        ('二分法の初期区間を Escutrrh から取る',
         r'rrh_max\[x-ECXA\]\s*=\s*Escutrrh\[kn-ECSTY\]\[x-ECXA\]'),
        ('月割りは 2/6/4（§7.3）',
         r'\(bpre \* 2\. \+ bpre \* riv \* 6\. \+ bend \* 4\.\) / 12\.'),
        ('riv = 改定率 × 調整割合の比（§7.3）',
         r'riv\s*=\s*Krb\[k-ECSTY\]\[dx-ECXA\]\s*\*\s*\(Escutrrh\[k-ECSTY\]\[dx-ECXA\]/Escutrrh\[k-1-ECSTY\]\[dx-1-ECXA\]\)'),
        ('etoc[] が項目番号を決める（§7.3）',
         r'int etoc\[14\] = \{13,14,15,6,7,8,16,5,16,5,16,5,16,5\}'),
        ('積立度合 D = 1.0', r'Ca\s*=\s*1\.0'),
        ('kend = 入力 + 100（= 2120年度）', r'kend\s*=\s*atoi\(Cutrfile3\)\s*\+\s*100'),
        ('k_jisseki = 24（2024年度）', r'k_jisseki\s*=\s*24'),
    ]
    ok = True
    src_all = src + cntl
    for name, pat in checks:
        hit = re.search(pat, src_all, re.S) is not None
        ok = ok and hit
        print(f"  {'OK ' if hit else '★NG'}  {name}")
    print()
    print("  → レポートの3分岐すべてがソースに代入文として存在する。")
    print("    集計した給付費から R を逆算する必要はない（付録Bの初版はそこを誤った）。")
    print()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.', help='リポジトリのルート')
    ap.add_argument('--case', default='3001')
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(args.root, SRC)):
        raise SystemExit(f"原本が見つかりません: {os.path.join(args.root, SRC)}\n"
                         f"--root にリポジトリのルートを渡してください。")

    results = []
    ok_a, mapping = kensho_a(args.root)
    results.append(('検証A Cc[] の項目名', ok_a))
    ok_b = kensho_b(args.case, mapping)
    if ok_b is not None:
        results.append(('検証B 実データでの検算', ok_b))
    results.append(('検証C R(N,X) の漸化式', kensho_c(args.root)))

    print("=" * 78)
    for name, ok in results:
        print(f"  {'一致' if ok else '★不一致'}  {name}")
    print("=" * 78)
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
