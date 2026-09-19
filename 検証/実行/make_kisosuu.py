#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分布推計の初期母集団 kisosuu_set.csv を組み立てる
==================================================
同梱データには `bunpu/kisosuu/` がディレクトリごと欠落している（仕様書 §12.5）。
分布推計はこれを個人単位の初期母集団として読むため、そのままでは動かない。

このスクリプトは同梱の遷移確率ファイルから初期母集団を組み立てる。

【厚労省のデータから復元できる部分】
  `kisoritsu01/{性別}/{基準年齢}/seni_{性別}_{年度}_{年齢+1}_{試算番号}.csv` は
  20状態×20状態の**絶対人数**の遷移表（確率ではない。prog04.cpp は std::stoi
  で読む）。基準年齢の翌年齢への遷移表の**行和**が、基準年齢時点の状態別人数に
  なる。連鎖の整合性も確認済み——ある年齢の列和は、次の年齢の遷移表の行和と
  完全に一致する（状態99は新規流入の待機プールなので除く）。
  したがって次の項目は厚労省のデータそのものである。
      var003 年度 / var004 性別 / var005 年齢 / var007・var008 状態

【復元できない部分】
  個人ごとの加入月数（var009〜var032）と年金額（var038〜var043）は、
  集計表からは原理的に復元できない。ここではすべて 0 を入れる。
  推測値を入れて「それらしい数字」を作ることはしない。

  ひとつだけ 0 にできない列がある。var040（列36）は 42箇所で
  `vector[...][get_var040() - 1]` として添字に使われるため 1 以上でなければ
  ならない。同梱の `kisoritsu08/table_souhoushuu.csv` が 52本の境界値
  （100万円〜1,166万円）を持つので、これは**年間総報酬の等級**（1〜53）である。
  個人の報酬は復元できないので、既定では最低等級の 1 を入れる（--grade で変更可）。
  全員が最低等級になるため、これも出力を公表値と比較できない理由のひとつ。

  この結果、**基準年齢17歳のコホートだけが忠実な初期条件**になる
  （17歳に加入歴はないので月数0が正しい）。基準年齢27・37・47・57・62歳の
  コホートは加入歴を失った状態で走り出すため、その出力は年金額を過小に評価する。
  分布推計の出力を公表値と比較してはならない。

使い方:
    検証/実行/make_kisosuu.py [--kisoritsu DIR] [--out DIR] [--shisan 2011]
"""
import argparse
import os
import sys

# main.cpp:36 の vector001（20状態）
STATES = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
          31, 32, 33, 34, 40, 50, 60, 70, 80, 99]
# main.cpp:37-38 の vector002（性別）と vector003（基準年齢）
SEXES = [1, 2]
BASE_AGES = [17, 27, 37, 47, 57, 62]

# func05a（prog05.cpp:5-48）が読む列数。0〜39 の40列。
NCOL = 40
# func03b(path, 7) なのでヘッダは7行読み捨てられる（prog03.cpp:30）
NHEADER = 7


def initial_distribution(kisoritsu_dir, sei, base_age, shisan):
    """基準年齢の翌年齢への遷移表の行和 = 基準年齢時点の状態別人数"""
    d = os.path.join(kisoritsu_dir, 'kisoritsu01', str(sei), str(base_age))
    target = f'_{base_age + 1}_{shisan}.csv'
    cands = [f for f in sorted(os.listdir(d)) if f.endswith(target)]
    if not cands:
        raise SystemExit(f'遷移表が見つかりません: {d}/*{target}')
    path = os.path.join(d, cands[0])
    rows = [[int(x) for x in line.split(',')]
            for line in open(path).read().splitlines() if line.strip()]
    # 状態99の行は「まだ母集団に入っていない人」の待機プールなので初期人口に含めない
    return {STATES[i]: sum(rows[i]) for i in range(20)
            if STATES[i] != 99 and sum(rows[i]) > 0}, os.path.basename(path)


def build(sei, base_age, dist, grade):
    """個人1人＝1行。40列。"""
    # ヘッダはちょうど NHEADER 行。func03b(path, 7) が読み捨てるので
    # 中身は計算に影響しないが、行数がずれると1行目がデータとして
    # std::stoi に渡されて例外になる。
    header = [
        '# 分布推計 初期母集団 kisosuu_set.csv（同梱データに欠落）',
        '# 検証/実行/make_kisosuu.py が生成',
        f'# 性別={sei} 基準年齢={base_age}歳 年度=2022',
        '# 状態別人数は同梱の遷移表の行和から復元（厚労省データ）',
        f'# 加入月数・年金額は復元不能のため0、総報酬等級(var040)は{grade}',
        '# → 基準年齢17歳以外のコホートは加入歴を失った状態で走る',
        ','.join(f'col{i}' for i in range(NCOL)),
    ]
    assert len(header) == NHEADER, f'ヘッダは{NHEADER}行でなければならない'
    lines = list(header)

    # 生年月日コード: main.cpp:146 の新規流入と同じ規約（年度*10000 + 1010）
    birth_code = (2022 - base_age) * 10000 + 1010
    pid = 0
    for state, n in sorted(dist.items()):
        for _ in range(n):
            pid += 1
            row = [0] * NCOL
            row[0] = pid          # var001 個人ID
            row[1] = pid - 1      # var002 並び順キー
            row[2] = 2022         # var003 年度
            row[3] = sei          # var004 性別
            row[4] = base_age     # var005 年齢
            row[5] = birth_code   # var006 生年月日コード
            row[6] = state        # var007 状態（当年）
            row[7] = state        # var008 状態（前年）
            # row[8..31]  var009〜var032 加入月数 → 0
            row[32] = 1           # var035 区分（1 = 通常。9は新規流入用）
            row[33] = 0           # var036
            # row[34..35] var038, var039 → 0
            row[36] = grade       # var040 総報酬等級（1以上でなければ添字が負になる）
            # row[37] var041 → 0
            row[38] = grade       # var042 翌年の var040 に引き継がれる
            # row[39] var043 → 0
            lines.append(','.join(str(v) for v in row))
    return lines


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser()
    ap.add_argument('--kisoritsu',
                    default='/suuri/rev2024/bunpu/kisoritsu')
    ap.add_argument('--out', default='/suuri/rev2024/bunpu/kisosuu')
    ap.add_argument('--shisan', default='2011', help='外枠番号（遷移表のファイル名末尾）')
    ap.add_argument('--grade', type=int, default=1,
                    help='総報酬等級 var040 の初期値（1〜53、既定1＝最低等級）')
    args = ap.parse_args()

    if not os.path.isdir(args.kisoritsu):
        print(f'遷移確率ディレクトリがありません: {args.kisoritsu}', file=sys.stderr)
        return 2

    total = 0
    print(f'{"性別":<6}{"基準年齢":<10}{"人数":>10}  {"由来":<34}状態別')
    for sei in SEXES:
        for base in BASE_AGES:
            dist, src = initial_distribution(args.kisoritsu, sei, base, args.shisan)
            lines = build(sei, base, dist, args.grade)
            outdir = os.path.join(args.out, str(sei), str(base))
            os.makedirs(outdir, exist_ok=True)
            with open(os.path.join(outdir, 'kisosuu_set.csv'), 'w') as f:
                f.write('\n'.join(lines) + '\n')
            n = sum(dist.values())
            total += n
            summary = ' '.join(f'{k}:{v}' for k, v in sorted(dist.items()))
            print(f'{sei:<6}{base:<10}{n:>10,}  {src:<34}{summary[:60]}')
    print()
    print(f'合計 {total:,} 人分を {args.out} に出力しました。')
    print(f'※ 加入月数・年金額は 0、総報酬等級は {args.grade}。')
    print('   基準年齢17歳以外の出力は年金額を過小評価します。公表値と比較しないこと。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
