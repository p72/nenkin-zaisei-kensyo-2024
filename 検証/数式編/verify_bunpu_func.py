#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⑥分布推計の関数がレポート第5章の手順に対応することを確かめる
=============================================================
仕様書 §10.4・§10.7 の根拠です。付録Bに「内部処理は推定に留まる」として
残していた項目を潰したときの手順を、再実行できる形にしました。

    python3 検証/数式編/verify_bunpu_func.py

ソースを読むだけなので、通し実行は不要です。

検証A: 基礎率8ディレクトリとレポートの記号の対応（§10.4）
検証B: 年次ループの処理がレポート第5章第1節 p.434-439 の手順と一致（§10.7）
検証C: 繰上げ・繰下げを扱っていないこと（§10.7）
"""
import argparse
import os
import re
import sys

SRC = 'papers/001365945/プログラム/分布推計'


def read_src(name, root):
    raw = open(os.path.join(root, SRC, name), 'rb').read()
    for enc in ('euc_jis_2004', 'euc_jp', 'utf-8'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('euc_jp', 'replace')


# func04X が読むパス → レポートの記号
EXPECT = [
    ('func04a',  'kisosuu/',                            '基礎数（同梱データに欠落）'),
    ('func04b',  'kisoritsu01/',                        'MatSedSni 制度遷移数行列'),
    ('func04c',  'kisoritsu02/prob_shougai_shikken_',   '障害失権確率'),
    ('func04d',  'kisoritsu03/prob_shougai_hassei_',    '障害発生確率'),
    ('func04e',  'kisoritsu04/prob_shougai_hassei_20mae_', '20歳前障害の発生確率'),
    ('func04f',  'kisoritsu05/prob_seni_kikan_',        'PrbSedSni 加入期間別制度間遷移確率'),
    ('func04g',  'kisoritsu06/prob_houshuu_seni_',      'PrbHshSni 総報酬遷移確率（継続）'),
    ('func04h',  'kisoritsu07/prob_houshuu_shinki_',    'PrbHshSet 総報酬設定確率（新規）'),
    ('func04i',  'kisoritsu08/table_souhoushuu.csv',    '総報酬の区分→金額の変換表'),
]


def kensho_a(root):
    print("=" * 78)
    print("検証A  基礎率8ディレクトリとレポートの記号の対応（§10.4）")
    print("=" * 78)
    src = read_src('prog04.cpp', root)
    # func04X ごとに直後のパス文字列を取る
    found = {}
    for m in re.finditer(r'func04([a-z]+)\([^)]*\)\s*\{(.*?)\n\}', src, re.S):
        body = m.group(2)
        p = re.search(r'"(\.\./[^"]+)"', body)
        if p:
            found['func04' + m.group(1)] = p.group(1)
    ok = True
    print(f"  {'関数':<10}{'読むパス':<46}レポートの記号")
    for fn, frag, sym in EXPECT:
        got = found.get(fn, '')
        hit = frag in got
        ok = ok and hit
        print(f"  {'OK ' if hit else '★NG'}{fn:<10}{got[:44]:<46}{sym}")
    print()
    print(f"  → kisoritsu01〜08 の8ディレクトリすべてが対応する。")
    print()
    return ok


def kensho_b(root):
    print("=" * 78)
    print("検証B  年次ループがレポートの手順と一致（§10.7）")
    print("=" * 78)
    src = read_src('main.cpp', root)
    checks = [
        ('①年齢を更新（年度と年齢を+1）',
         r'set_var003\(\s*\+\+tmp_var003\s*\)', r'set_var005\(\s*\+\+tmp_var005\s*\)'),
        ('前年度末の状態を引き継ぐ（var008 → var007）',
         r'get_var008\(\)', r'set_var007\(\s*tmp_var007\s*\)'),
        ('補論(2) ステップ1 乱数を付与',
         r'std::shuffle\(vector023\.begin\(\), vector023\.end\(\), gen_rand\)',
         r'set_var002\(\s*vector023\[i\]\s*\)'),
        ('補論(2) ステップ2 乱数→前年度加入制度で安定ソート',
         r'stable_sort\([^;]*compare_var002\(\)\)',
         r'stable_sort\([^;]*compare_var007\(\)\)'),
        ('割当済みフラグを年初に寝かせる（var037 = 0）',
         r'set_var037\(\s*0\s*\)', None),
        ('func09b の直前で未割当を前に集める',
         r'stable_sort\([^;]*compare_var037\(\)\)', r'func09b'),
        ('②の割当は func06a/06b → func07a/07b → func08a → func09b の順',
         r'func06a.*func06b.*func07a.*func07b.*func08a.*func09b', None),
        ('func06a は年齢59〜63歳', r'loop_var003 >= 59 && loop_var003 <= 63', None),
        ('func06b は年齢64歳以上', r'loop_var003 >= 64 && loop_var003 <= 69', None),
        ('⑥ 65歳到達で止まる', r'main_var001 = 65', r'loop_var003 < main_var001'),
    ]
    ok = True
    for item in checks:
        name, pats = item[0], [p for p in item[1:] if p]
        hit = all(re.search(p, src, re.S) for p in pats)
        ok = ok and hit
        print(f"  {'OK ' if hit else '★NG'}  {name}")

    prog08 = read_src('prog08.cpp', root)
    sub = [
        ('func08a は制度の枠と加入期間別の枠を同時に減らす',
         r'--\s*arg08a7\[func_orig::func09a\(arg08a3\[i\]\.get_var007\(\)\)\]\[k\]',
         r'--\s*vector08a2\[func_orig::func09a\(arg08a3\[i\]\.get_var007\(\)\)\]\[int\(arg08a3\[i\]\.get_var0\d+\(\)/12\)\]\[k\]'),
        ('割当時に var037 を立てる', r'set_var037\(1\)', None),
    ]
    for item in sub:
        name, pats = item[0], [p for p in item[1:] if p]
        hit = all(re.search(p, prog08, re.S) for p in pats)
        ok = ok and hit
        print(f"  {'OK ' if hit else '★NG'}  {name}")

    prog09 = read_src('prog09.cpp', root)
    hit = re.search(r'if \( p < arg09b3\[i\]\[j\] \) \{\s*ag09b5\[p\]\.set_var008\(arg09b4\[j\]\)',
                    prog09, re.S) is not None
    ok = ok and hit
    print(f"  {'OK ' if hit else '★NG'}  func09b は累積和で残りを順に割当（補論(2) ステップ3）")
    print()
    return ok


def kensho_c(root):
    print("=" * 78)
    print("検証C  繰上げ・繰下げを扱っていない（§10.7）")
    print("=" * 78)
    print("レポート第5章第1節 p.435")
    print("  「繰上げ、繰下げを選択せず65歳で裁定した場合の本来額とし、…")
    print("    加給年金は含めない。…在職老齢年金等による支給停止額は考慮しない」")
    print()
    hits = []
    for fn in sorted(os.listdir(os.path.join(root, SRC))):
        if not fn.endswith(('.cpp', '.h')):
            continue
        src = read_src(fn, root)
        for pat in (r'kuriage', r'kurisage', r'\b0\.7\b', r'\b1\.42\b', r'\b1\.84\b'):
            for m in re.finditer(pat, src, re.I):
                hits.append((fn, pat, src[max(0, m.start() - 40):m.start() + 40]
                             .replace('\n', ' ')))
    print(f"  減額率・増額率に相当する定数（0.7 / 1.42 / 1.84 / kuriage / kurisage）: "
          f"{len(hits)}件")
    for fn, pat, ctx in hits[:5]:
        print(f"    {fn}: {pat} … {ctx}")
    main_src = read_src('main.cpp', root)
    stop65 = re.search(r'main_var001 = 65', main_src) is not None
    print(f"  {'OK ' if stop65 else '★NG'}  main_var001 = 65（65歳でループが止まる）")
    ok = (len(hits) == 0) and stop65
    print()
    print(f"  → {'繰上げ・繰下げは扱っていない。' if ok else '★痕跡あり'}"
          f"{'出力は65歳時点の老齢年金額のみ。' if ok else ''}")
    print()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.', help='リポジトリのルート')
    args = ap.parse_args()
    if not os.path.isdir(os.path.join(args.root, SRC)):
        raise SystemExit(f"原本が見つかりません: {os.path.join(args.root, SRC)}")

    results = [('検証A 基礎率とレポートの記号の対応', kensho_a(args.root)),
               ('検証B 年次ループと手順の一致', kensho_b(args.root)),
               ('検証C 繰上げ・繰下げは扱わない', kensho_c(args.root))]
    print("=" * 78)
    for name, ok in results:
        print(f"  {'一致' if ok else '★不一致'}  {name}")
    print("=" * 78)
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
