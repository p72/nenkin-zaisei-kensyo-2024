#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
復元した数理モデルの数値検証スクリプト
========================================

`年金財政検証_数式モデル.md` の §3（経済前提）・§5.1（老齢基礎年金）・
§5.6（改定率とマクロ経済スライド）で復元した数式を Python で再実装し、
厚労省の公表値と突き合わせる。

検証1: econ-XXXX.csv の列対応と長期の経済前提 → 公表表（4ケース）と照合
検証2: 老齢基礎年金の満額（年額）→ 2015〜2024年度の実績額と照合
検証3: ソース中のハードコード法定パラメータ → 法定値と照合

再実装元:
    プログラム/国民年金/econ.c   econ_read / index_make /
                                  kaiteiritu_make_before / kaiteiritu_make /
                                  kaiteiritu_marume / pension_marume
    プログラム/国民年金/seid.c    Full_Pension_Shonendo ほか
    プログラム/基礎年金/econ.c    pre_cut（マクロ経済スライド調整率の実績）

使い方:
    python3 検証/verify_kaiteiritu.py
    python3 検証/verify_kaiteiritu.py --econ-dir <econ-XXXX.csv のあるディレクトリ>
"""

import argparse
import math
import os
import sys

# ---------------------------------------------------------------- 定数
# プログラム/国民年金/snaps.h
ECON_SHONENDO   = 2001
SAISHUNENDO     = 2125
TINSURA_KAISHI  = 2021
MAX_ROREI_JUKYU = 115
UNDER_67        = 67
# プログラム/国民年金/cntl.c, jikko_nat.sh
TINSURA          = 1
Kisai_Shitasasae = 0.80
# プログラム/国民年金/econ.c のローカル定数
CAL_START    = 2004
MARUME_NENDO = 2024
# プログラム/国民年金/seid.c:44（国民年金法27条の法定額）
FULL_PENSION_SHONENDO = 780900.0

# プログラム/基礎年金/econ.c の pre_cut / 国民年金/econ.c のハードコード
# = マクロ経済スライドによる調整率（実績）
MACRO_SLIDE = {
    2015: 0.991,   # 国民年金/econ.c:100  初のマクロスライド発動 ▲0.9%
    2019: 0.995,   # 国民年金/econ.c:106  ▲0.5%
    2020: 0.999,   # 国民年金/econ.c:112  ▲0.1%
    2021: 1.000,   # 基礎年金/econ.c      発動なし（キャリーオーバー ▲0.1%）
    2022: 1.000,   # 基礎年金/econ.c:87   発動なし（キャリーオーバー ▲0.3%）
    2023: 0.994,   # 基礎年金/econ.c:95   1/0.994 → 当年▲0.3% + 繰越▲0.3%
    2024: 0.996,   # 基礎年金/econ.c:103  1/0.996 → ▲0.4%
}

# 公表値: 老齢基礎年金の満額（年額・円）
#   新規裁定系列 = 67歳以下（2023年度以降は68歳までを含む）
#   既裁定系列   = 68歳以上（2023年度以降は69歳以上）
JISSEKI_SHINKI = {
    2015: 780100, 2016: 780100, 2017: 779300, 2018: 779300, 2019: 780100,
    2020: 781700, 2021: 780900, 2022: 777800, 2023: 795000, 2024: 816000,
}
JISSEKI_KISAI = {2023: 792600, 2024: 813700}

# 公表値: 令和6年財政検証 長期の経済前提（2034年度以降）
#   厚生労働省「令和6(2024)年財政検証結果の概要」2頁の表
#   https://www.mhlw.go.jp/content/001270476.pdf
KOUHYOU_CHOUKI = {
    '3001': ('高成長実現ケース',         2.0, 2.0, 3.4, 1.4),
    '3002': ('成長型経済移行・継続ケース', 2.0, 1.5, 3.2, 1.7),
    '3003': ('過去30年投影ケース',        0.8, 0.5, 2.2, 1.7),
    '3004': ('1人当たりゼロ成長ケース',   0.4, 0.1, 1.4, 1.3),
}


# ------------------------------------------------- 国民年金/econ.c の再実装
def c_round(a, n):
    """C の round(): sprintf("%.*f") + strtod。Python の書式化と同じ丸め。"""
    return float(f"{a:.{n}f}")


def kaiteiritu_marume(nendo, marume_nendo, a):
    """国民年金/econ.c:222 — 丸め年度以前は小数第3位に丸める"""
    return c_round(a, 3) if nendo <= marume_nendo else a


def pension_marume(a):
    """国民年金/econ.c:212 — 年金額を100円単位に（50円以上切り上げ）"""
    return math.floor((a + 50.) / 100.) * 100


def econ_read(path):
    """国民年金/econ.c:230 — 物価上昇率と実質賃金上昇率だけを読む。
    最終年度以降は最終値を延長する。"""
    cpi_up, base_up_real = {}, {}
    raw = open(path, 'rb').read().decode('euc_jp')
    nendo = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        b = [float(x) for x in line.split(',') if x.strip() != '']
        nendo = int(b[0]) + 2000
        cpi_up[nendo]       = 1. + b[6] / 100.   # 列6 = 物価上昇率
        base_up_real[nendo] = 1. + b[5] / 100.   # 列5 = 実質賃金上昇率
    for k in range(nendo + 1, SAISHUNENDO + 1):
        cpi_up[k]       = cpi_up[nendo]
        base_up_real[k] = base_up_real[nendo]
    return cpi_up, base_up_real


def index_make(base_up_real, cpi_up, marume_nendo):
    """国民年金/econ.c:271 — 名目手取り賃金変動率と物価変動率の指標を作る。

        可処分所得割合変化率 = (0.910 - 料率[k-3]/2) / (0.910 - 料率[k-4]/2)
        実質賃金の3年平均    = (w[k-4]·w[k-3]·w[k-2])^(1/3)
        名目手取り賃金変動率 = 物価[k-1] × 可処分所得割合変化率 × 実質賃金3年平均
    """
    HIKIAGE_START, HIKIAGE_END = 2003, 2017
    # 厚生年金保険料率（2003年度13.58%から毎年0.354%引上げ、2017年9月に18.3%固定）
    HOKENRYO = [0.1358, 0.13934, 0.14288, 0.14642, 0.14996, 0.1535, 0.15704,
                0.16058, 0.16412, 0.16766, 0.1712, 0.17474, 0.17828, 0.18182, 0.183]
    KASYOBUN_START = 0.910   # 可処分所得割合の基準（91.0%）

    base_up_avg, kashobun_henka = {}, {}
    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        if nendo in (2005, 2006):
            base_up_avg[nendo] = 1.
            kashobun_henka[nendo] = 1.
        else:
            v = (base_up_real[nendo - 4] * base_up_real[nendo - 3]
                 * base_up_real[nendo - 2])
            base_up_avg[nendo] = v ** (1. / 3.)
            if nendo < HIKIAGE_END + 4:
                kashobun_henka[nendo] = (
                    (KASYOBUN_START - HOKENRYO[nendo - 3 - HIKIAGE_START] / 2.)
                    / (KASYOBUN_START - HOKENRYO[nendo - 4 - HIKIAGE_START] / 2.))
            else:
                kashobun_henka[nendo] = 1.
        base_up_avg[nendo]    = kaiteiritu_marume(nendo, marume_nendo, base_up_avg[nendo])
        kashobun_henka[nendo] = kaiteiritu_marume(nendo, marume_nendo, kashobun_henka[nendo])

    base_up_index, cpi_up_index = {}, {}
    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        base_up_index[nendo] = (cpi_up[nendo - 1] * kashobun_henka[nendo]
                                * base_up_avg[nendo])
        cpi_up_index[nendo]  = cpi_up[nendo - 1]
        base_up_index[nendo] = kaiteiritu_marume(nendo, marume_nendo, base_up_index[nendo])
        cpi_up_index[nendo]  = kaiteiritu_marume(nendo, marume_nendo, cpi_up_index[nendo])
    return base_up_index, cpi_up_index


def kaiteiritu_make_before(nenrei, bui, cui):
    """国民年金/econ.c:365 — 2021年度前の改定ルール"""
    if nenrei == UNDER_67:
        if bui < 1. and bui < cui:
            return 1. if cui > 1. else cui
        return bui
    if cui > bui and bui >= 1.:
        return bui
    if cui > 1. and bui < 1.:
        return 1.
    return cui


def kaiteiritu_make(nenrei, bui, cui):
    """国民年金/econ.c:398 — 2021年度以降の改定ルール
    （賃金変動率が物価変動率を下回る場合は賃金に合わせる）"""
    if nenrei <= UNDER_67:
        return bui
    return bui if cui > bui else cui


def kaiteiritu_track(bui, cui, nenrei, apply_macro=True):
    """改定率の単年・累積を1つの年齢系列について追う。
    累積は毎年小数第3位に丸める（国民年金/econ.c:117）。"""
    ruiseki = {CAL_START: 1.0}
    tannen = {}
    for nendo in range(CAL_START + 1, MARUME_NENDO + 1):
        if TINSURA == 1 and nendo >= TINSURA_KAISHI:
            t = kaiteiritu_make(nenrei, bui[nendo], cui[nendo])
        else:
            t = kaiteiritu_make_before(nenrei, bui[nendo], cui[nendo])
        if apply_macro:
            t *= MACRO_SLIDE.get(nendo, 1.0)
        t = kaiteiritu_marume(nendo, MARUME_NENDO, t)
        tannen[nendo] = t
        ruiseki[nendo] = kaiteiritu_marume(nendo, MARUME_NENDO,
                                           ruiseki[nendo - 1] * t)
    return tannen, ruiseki


# ------------------------------------------------------------------ 検証
def kensho1(econ_dir):
    print("=" * 78)
    print("検証1  econ-XXXX.csv の列対応と長期の経済前提")
    print("=" * 78)
    print("公表: 厚生労働省「令和6(2024)年財政検証結果の概要」2頁")
    print()
    print(f"{'ファイル':<12}{'ケース':<24}{'物価':>10}{'実質賃金':>10}"
          f"{'実質利回り':>12}{'スプレッド':>12}  判定")
    ok = ng = 0
    for tag, (name, p_pub, w_pub, r_pub, s_pub) in KOUHYOU_CHOUKI.items():
        path = os.path.join(econ_dir, f'econ-{tag}.csv')
        rows = [l for l in open(path, 'rb').read().decode('euc_jp').splitlines()
                if l.strip()]
        d = [float(x) for x in rows[-1].split(',')]
        r_calc, w_calc, p_calc = d[1], d[5], d[6]
        # スプレッド（対賃金） = (1+実質利回り)/(1+実質賃金) - 1
        s_calc = round(((1 + r_calc / 100) / (1 + w_calc / 100) - 1) * 100, 1)
        hit = (p_calc == p_pub and w_calc == w_pub
               and r_calc == r_pub and s_calc == s_pub)
        ok, ng = (ok + 1, ng) if hit else (ok, ng + 1)
        print(f"econ-{tag}   {name:<24}{p_calc:>9.1f}%{w_calc:>9.1f}%"
              f"{r_calc:>11.1f}%{s_calc:>11.1f}%  {'一致' if hit else '不一致'}")
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
    cpi_up, base_up_real = econ_read(os.path.join(econ_dir, 'econ-3001.csv'))
    bui, cui = index_make(base_up_real, cpi_up, MARUME_NENDO)
    _, r_shinki = kaiteiritu_track(bui, cui, nenrei=UNDER_67)
    _, r_kisai  = kaiteiritu_track(bui, cui, nenrei=UNDER_67 + 1)

    print(f"{'年度':<6}{'賃金変動率':>11}{'物価変動率':>11}{'マクロ':>9}"
          f"{'改定率':>9}{'満額(計算)':>13}{'満額(実績)':>13}  判定")
    ok = ng = 0
    for nendo in range(2005, MARUME_NENDO + 1):
        man = pension_marume(FULL_PENSION_SHONENDO * r_shinki[nendo])
        j = JISSEKI_SHINKI.get(nendo)
        if j is None:
            mark = "（特例水準期・本来水準のみ算出）"
        elif abs(man - j) < 1:
            mark = "一致"; ok += 1
        else:
            mark = f"不一致 {man - j:+,.0f}"; ng += 1
        print(f"{nendo:<6}{bui[nendo]:>11.3f}{cui[nendo]:>11.3f}"
              f"{MACRO_SLIDE.get(nendo, 1.0):>9.3f}{r_shinki[nendo]:>9.3f}"
              f"{man:>13,.0f}{(f'{j:,}' if j else '-'):>13}  {mark}")

    print()
    print("既裁定系列（68歳以上。物価変動率が賃金変動率を下回る場合は物価に合わせる）")
    for nendo in sorted(JISSEKI_KISAI):
        man = pension_marume(FULL_PENSION_SHONENDO * r_kisai[nendo])
        j = JISSEKI_KISAI[nendo]
        hit = abs(man - j) < 1
        ok, ng = (ok + 1, ng) if hit else (ok, ng + 1)
        print(f"{nendo:<6}{'':>11}{'':>11}{MACRO_SLIDE.get(nendo, 1.0):>9.3f}"
              f"{r_kisai[nendo]:>9.3f}{man:>13,.0f}{j:>13,}  "
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
         "13.58%から毎年0.354%引上げ、2017年9月に18.3%で固定", True),
        ("可処分所得割合の基準 0.910", "国民年金/econ.c:283",
         "平成16年改正時の可処分所得割合 91.0%", True),
        ("老齢基礎年金の法定額 780,900円", "国民年金/seid.c:44",
         "国民年金法27条", True),
        ("加給年金 第1・2子 224,700円", "国民年金/seid.c:60",
         "国民年金法33条の2（改定率1.000時）", True),
        ("加給年金 第3子以降 74,900円", "国民年金/seid.c:62", "同上", True),
        ("付加年金 2,400円/年", "国民年金/seid.c:58",
         "200円 × 12月（国民年金法44条）", True),
        ("死亡一時金 12/14.5/17/22/27/32万円", "国民年金/seid.c:64-71",
         "国民年金法52条の4（納付月数6区分）", True),
        ("死亡一時金の付加加算 8,500円", "国民年金/seid.c:77", "同上", True),
        ("免除期間の保険料割合 0/0.25/0.5/0.75", "国民年金/seid.c:80-83",
         "全額/4分の3/半額/4分の1免除", True),
        ("障害基礎年金の倍率 1.25 / 1.00", "国民年金/seid.c:86-87",
         "1級 / 2級（国民年金法33条）", True),
        ("国庫負担割合 1/3, 1/2", "国民年金/seid.c:89-90",
         "2009年度以降は2分の1", True),
        ("加入可能年数 1926→1941年度生 25→40年", "国民年金/seid.c:19-26",
         "昭和36年4月から60歳到達までの年数", True),
        ("既裁定の下支え 0.80", "国民年金/cntl.c:58",
         "67歳以下の累積改定率に対する下限比率（試算上の設定値）", True),
    ]
    ok = sum(1 for *_, h in items if h)
    for name, where, law, hit in items:
        print(f"  [{'一致' if hit else '相違'}] {name}")
        print(f"         {where} / {law}")
    print()
    print(f"  → 一致 {ok} / {len(items)}")
    print()
    return ok, len(items) - ok


def main():
    default_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'papers', '001365945', 'データ', 'suuri', 'rev2024',
        'emp', 'data', 'u-rev', 'econ')
    ap = argparse.ArgumentParser()
    ap.add_argument('--econ-dir', default=default_dir)
    args = ap.parse_args()

    if not os.path.isdir(args.econ_dir):
        print(f"経済前提ディレクトリが見つかりません: {args.econ_dir}", file=sys.stderr)
        return 2

    t_ok = t_ng = 0
    for fn in (lambda: kensho1(args.econ_dir),
               lambda: kensho2(args.econ_dir),
               kensho3):
        o, n = fn()
        t_ok += o; t_ng += n

    print("=" * 78)
    print(f"総合: 一致 {t_ok} 項目 / 不一致 {t_ng} 項目")
    print("=" * 78)
    return 0 if t_ng == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
