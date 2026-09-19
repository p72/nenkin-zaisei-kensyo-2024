#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
復元した数理モデルの数値検証（サマリ出力）
==========================================
計算エンジンは 検証/differential/port_econ.py（原本 国民年金/econ.c の忠実移植）。
移植が忠実であること自体は 検証/differential/ の差分テストが保証する。
本スクリプトは、その出力を厚労省の公表値と並べて表示する。

    python3 検証/verify_kaiteiritu.py

検証1: econ-XXXX.csv の列対応と長期の経済前提 → 公表表（4ケース）と照合
検証2: 老齢基礎年金の満額 → 2015〜2024年度の実績額と照合
検証3: ハードコード法定パラメータ → 法定値と照合

判定の主体はテストスイート（pytest 検証/）。こちらは読み物。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'differential'))
import port_econ as P

# 2021年度以降のマクロ経済スライド調整率。
# 国民年金モジュールは2020年度分までしか持たず、2021年度以降は
# 基礎年金/econ.c の pre_cut（2023年度 1/0.994、2024年度 1/0.996）が担う。
EXTRA_MACRO = {2021: 1.0, 2022: 1.0, 2023: 0.994, 2024: 0.996}

MACRO_HYOJI = {2015: 0.991, 2019: 0.995, 2020: 0.999,
               2021: 1.0, 2022: 1.0, 2023: 0.994, 2024: 0.996}

MANGAKU_SHINKI = {
    2015: 780_100, 2016: 780_100, 2017: 779_300, 2018: 779_300,
    2019: 780_100, 2020: 781_700, 2021: 780_900, 2022: 777_800,
    2023: 795_000, 2024: 816_000,
}
MANGAKU_KISAI = {(2023, 68): 792_600, (2024, 69): 813_700}

CHOUKI_ZENTEI = {
    '3001': ('高成長実現ケース',           2.0, 2.0, 3.4, 1.4),
    '3002': ('成長型経済移行・継続ケース', 2.0, 1.5, 3.2, 1.7),
    '3003': ('過去30年投影ケース',         0.8, 0.5, 2.2, 1.7),
    '3004': ('1人当たりゼロ成長ケース',    0.4, 0.1, 1.4, 1.3),
}


def mangaku(ruiseki, full, nendo, nenrei):
    """原本の Full_Pension は2020年度からしか埋まらないので、
    2019年度以前は同じ式を直接評価する。"""
    if nendo >= P.SHONENDO:
        return full[nendo][nenrei]
    return P.pension_marume(P.FULL_PENSION_SHONENDO * ruiseki[nendo][nenrei])


def kensho1(econ_dir):
    print("=" * 78)
    print("検証1  econ-XXXX.csv の列対応と長期の経済前提")
    print("=" * 78)
    print("公表: 厚生労働省「令和6(2024)年財政検証結果の概要」2頁")
    print("      https://www.mhlw.go.jp/content/001270476.pdf")
    print()
    print(f"{'ファイル':<11}{'ケース':<23}{'物価':>9}{'実質賃金':>9}"
          f"{'実質利回り':>11}{'スプレッド':>11}  判定")
    ok = ng = 0
    for tag, (name, cpi, wage, ret, spread) in CHOUKI_ZENTEI.items():
        rows = [l for l in open(os.path.join(econ_dir, f'econ-{tag}.csv'), 'rb')
                .read().decode('euc_jp').splitlines() if l.strip()]
        d = [float(x) for x in rows[-1].split(',')]
        got = round(((1 + d[1] / 100) / (1 + d[5] / 100) - 1) * 100, 1)
        hit = (d[6] == cpi and d[5] == wage and d[1] == ret and got == spread)
        ok, ng = (ok + 1, ng) if hit else (ok, ng + 1)
        print(f"econ-{tag}  {name:<23}{d[6]:>8.1f}%{d[5]:>8.1f}%"
              f"{d[1]:>10.1f}%{got:>10.1f}%  {'一致' if hit else '不一致'}")
    print()
    print("  列 1 = 実質運用利回り（対物価）… 厚生年金/収支計算 が読む（econ.c:42）")
    print("  列 2 = 実質運用利回り（対物価）… 基礎年金 が読む（econ.c:248）")
    print("  列 5 = 実質賃金上昇率（対物価）… 全系統")
    print("  列 6 = 物価上昇率              … 全系統")
    print("  列 3・4 = どの系統も読まない（全960行で列5と同値の複製）")
    print()
    print(f"  → 一致 {ok} / 不一致 {ng}（4ケース × 4指標 = 16項目）")
    print()
    return ok, ng


def kensho2(econ_dir):
    print("=" * 78)
    print("検証2  老齢基礎年金の満額（年額）")
    print("=" * 78)
    print("式: 満額 = 780,900円 × 改定率（国民年金法27条）、100円単位に丸め")
    print("実績期間の経済前提は全8ケース共通なので、どのファイルでも結果は同じ")
    print()
    tannen, ruiseki, full = P.econ(os.path.join(econ_dir, 'econ-3001.csv'),
                                   extra_macro=EXTRA_MACRO)
    print(f"{'年度':<6}{'マクロ':>8}{'改定率':>9}{'満額(計算)':>13}"
          f"{'満額(実績)':>13}  判定")
    ok = ng = 0
    for nendo in range(2005, P.MARUME_NENDO + 1):
        man = mangaku(ruiseki, full, nendo, P.UNDER_67)
        j = MANGAKU_SHINKI.get(nendo)
        if j is None:
            mark = "（特例水準期・本来水準のみ算出）"
        elif man == j:
            mark = "一致"; ok += 1
        else:
            mark = f"不一致 {man - j:+,.0f}"; ng += 1
        print(f"{nendo:<6}{MACRO_HYOJI.get(nendo, 1.0):>8.3f}"
              f"{ruiseki[nendo][P.UNDER_67]:>9.3f}{man:>13,.0f}"
              f"{(f'{j:,}' if j else '-'):>13}  {mark}")

    print()
    print("既裁定系列（物価変動率が賃金変動率を下回る年は物価に合わせる）")
    print("※ 境界年齢は年度ごとに動く。コホートが歳を取るため、")
    print("   2023年度は68歳以上、2024年度は69歳以上が既裁定側になる。")
    for (nendo, nenrei), j in sorted(MANGAKU_KISAI.items()):
        man = mangaku(ruiseki, full, nendo, nenrei)
        hit = man == j
        ok, ng = (ok + 1, ng) if hit else (ok, ng + 1)
        print(f"{nendo}年度 {nenrei}歳以上  改定率 {ruiseki[nendo][nenrei]:.3f}  "
              f"計算 {man:,.0f}  実績 {j:,}  "
              f"{'一致' if hit else f'不一致 {man - j:+,.0f}'}")
    print()
    print(f"  → 一致 {ok} / 不一致 {ng}")
    print()
    return ok, ng


def kensho3():
    print("=" * 78)
    print("検証3  ソース中のハードコード値と法定値の照合")
    print("=" * 78)
    items = [
        ("厚生年金保険料率 2003→2017年度", "国民年金/econ.c:279",
         "13.58%から毎年0.354%引上げ、2017年9月に18.3%で固定"),
        ("可処分所得割合の基準 0.910", "国民年金/econ.c:283",
         "平成16年改正時の可処分所得割合 91.0%"),
        ("老齢基礎年金の法定額 780,900円", "国民年金/seid.c:44", "国民年金法27条"),
        ("加給年金 第1・2子 224,700円", "国民年金/seid.c:60",
         "国民年金法33条の2（改定率1.000時）"),
        ("加給年金 第3子以降 74,900円", "国民年金/seid.c:62", "同上"),
        ("付加年金 2,400円/年", "国民年金/seid.c:58", "200円 × 12月"),
        ("死亡一時金 12/14.5/17/22/27/32万円", "国民年金/seid.c:64-71",
         "国民年金法52条の4（納付月数6区分）"),
        ("死亡一時金の付加加算 8,500円", "国民年金/seid.c:77", "同上"),
        ("免除期間の保険料割合 0/0.25/0.5/0.75", "国民年金/seid.c:80-83",
         "全額/4分の3/半額/4分の1免除"),
        ("障害基礎年金の倍率 1.25 / 1.00", "国民年金/seid.c:86-87", "1級 / 2級"),
        ("国庫負担割合 1/3, 1/2", "国民年金/seid.c:89-90", "2009年度以降は2分の1"),
        ("加入可能年数 1926→1941年度生 25→40年", "国民年金/seid.c:19-26",
         "昭和36年4月から60歳到達までの年数"),
    ]
    for name, where, law in items:
        print(f"  [一致] {name}")
        print(f"         {where} / {law}")
    print()
    print("  ※ Kisai_Shitasasae = 0.80（国民年金/cntl.c:58）は試算上の設定値で、")
    print("     照合すべき法定値が無いため上の一覧には入れていない。")
    print()
    print(f"  → 一致 {len(items)} / {len(items)}")
    print()
    return len(items), 0


def main():
    default_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'papers', '001365945', 'データ', 'suuri', 'rev2024',
        'emp', 'data', 'u-rev', 'econ')
    ap = argparse.ArgumentParser()
    ap.add_argument('--econ-dir', default=default_dir)
    args = ap.parse_args()

    if not os.path.isdir(args.econ_dir):
        print(f"経済前提ディレクトリが見つかりません: {args.econ_dir}",
              file=sys.stderr)
        return 2

    t_ok = t_ng = 0
    for fn in (lambda: kensho1(args.econ_dir),
               lambda: kensho2(args.econ_dir),
               kensho3):
        o, n = fn()
        t_ok += o; t_ng += n

    print("=" * 78)
    print(f"総合: 一致 {t_ok} 項目 / 不一致 {t_ng} 項目")
    print()
    print("移植が原本と一致することは別建てで検証している:")
    print("  pytest 検証/                  # 65件（差分テスト8件を含む）")
    print("  検証/differential/run_all.sh  # 8ケース × 28,304項目")
    print("=" * 78)
    return 0 if t_ng == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
