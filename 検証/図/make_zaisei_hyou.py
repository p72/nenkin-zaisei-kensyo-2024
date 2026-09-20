#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
概要資料スタイルの「財政見通し」表を作る
========================================
厚生労働省「令和6(2024)年財政検証結果の概要」6頁の

    厚生年金の財政見通し（令和6(2024)年財政検証）

と同じ体裁の表を、通し実行の結果から組み立てます。読み取りロジックは
`検証/オプション試算/compare_option.py` をそのまま使うので、公表値と
41,904項目照合した経路と同じ数字が出ます。

    検証/実行/run_pipeline.sh 3001
    python3 検証/図/make_zaisei_hyou.py --case 3001

    TOUGOU=1 YOBI=010 YOBI2=011 検証/実行/run_pipeline.sh 3003 1 1 0 2
    python3 検証/図/make_zaisei_hyou.py --case 3003 --yobi 010 --bas-yobi 011 \\
        --layout 一元化 --option 'マクロ経済スライドの調整期間の一致'

レイアウトは2つ。公表資料に合わせています。

| `--layout` | 見出し | 中身 |
|---|---|---|
| `厚生年金` | 厚生年金の財政見通し | 4制度（厚年・国共済・地共済・私学共済）の合計 |
| `一元化`   | 国民年金及び厚生年金の財政見通し | 上に国民年金を足したもの。調整期間の一致で使う |

長期の経済前提は `econ-XXXX.csv` の長期前提行（2034年度以降）から取ります。
経済成長率だけはプログラムの入出力に無い前提値なので、公表資料の値を
`GROWTH` に持っています。
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'オプション試算'))
sys.path.insert(0, os.path.dirname(HERE))
import compare_option as CO      # noqa: E402  読み取りロジックを使い回す
import suuri_env                 # noqa: E402  実行領域の場所（仕様書 §12.1）

plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

INK    = '#0b0b0b'
INK_2  = '#3f3e3b'
INK_3  = '#8a8880'
RULE   = '#0b0b0b'
RULE_2 = '#b8b6b0'
SURF   = '#ffffff'
BAND   = '#f4f3f0'
C_WARN = '#c2410c'

# ケース名（経済前提番号 → 表記）
CASES = {
    '3001': '高成長実現ケース', '3002': '成長型経済移行・継続ケース',
    '3003': '過去30年投影ケース', '3004': '１人当たりゼロ成長ケース',
    '3201': '高成長実現ケース（変動あり）',
    '3202': '成長型経済移行・継続ケース（変動あり）',
    '3203': '過去30年投影ケース（変動あり）',
    '3204': '１人当たりゼロ成長ケース（変動あり）',
}

# 経済成長率（実質、2034年度以降20〜30年）。プログラムの入出力に無い前提値
# なので公表資料（詳細結果等の財政見通し）の値をそのまま持つ。
# 括弧内は人口1人当たり実質経済成長率。
GROWTH = {
    '3001': '1.6％（2.3%）', '3002': '1.1％（1.8%）',
    '3003': '-0.1％（0.7%）', '3004': '-0.7％（0.1%）',
    '3201': '1.6％（2.3%）', '3202': '1.1％（1.8%）',
    '3203': '-0.1％（0.7%）', '3204': '-0.7％（0.1%）',
}

YEARS = [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2035, 2040,
         2050, 2060, 2070, 2080, 2090, 2100, 2110, 2120]

# (表示名, compare_option のキー, 単位) 単位は '兆円' / '' / '％'
COLS = {
    '厚生年金': [
        ('収入合計',                  '収入合計',              '兆円'),
        ('保険料\n収　入',            '保険料収入',            '兆円'),
        ('運用収入',                  '運用収入',              '兆円'),
        ('国庫負担',                  '国庫負担',              '兆円'),
        ('支出合計',                  '支出合計',              '兆円'),
        ('基礎年金\n拠 出 金',        '基礎年金拠出金',        '兆円'),
        ('報酬比例',                  '給付費',                '兆円'),
        ('収　支\n差引残',            '収支差引残',            '兆円'),
        ('年度末\n積立金',            '年度末積立金',          '兆円'),
        ('年度末\n積立金\n(2024年度\n価格)', '年度末積立金(2024価格)', '兆円'),
        ('積立\n度合',                '積立度合',              ''),
        ('所得代替率',                '所得代替率',            '％'),
        ('基礎',                      '代替率(基礎)',          '％'),
        ('比例',                      '代替率(比例)',          '％'),
    ],
    '一元化': [
        ('収入合計',                  '収入合計',              '兆円'),
        ('保険料収入\n国年',          '保険料収入(国年)',      '兆円'),
        ('保険料収入\n厚年',          '保険料収入(厚年)',      '兆円'),
        ('国庫負担',                  '国庫負担',              '兆円'),
        ('運用収入',                  '運用収入',              '兆円'),
        ('支出合計',                  '支出合計',              '兆円'),
        ('基礎年金',                  '基礎年金',              '兆円'),
        ('報酬比例',                  '報酬比例',              '兆円'),
        ('収　支\n差引残',            '収支差引残',            '兆円'),
        ('年度末\n積立金',            '年度末積立金',          '兆円'),
        ('年度末\n積立金\n(2024年度\n価格)', '年度末積立金(2024価格)', '兆円'),
        ('積立\n度合',                '積立度合',              ''),
        ('所得代替率',                '所得代替率',            '％'),
        ('基礎',                      '代替率(基礎)',          '％'),
        ('比例',                      '代替率(比例)',          '％'),
    ],
}

# 上段のグループ見出し: (ラベル, 何列ぶんか)
GROUPS = {
    '厚生年金': [('収入合計', 4), ('支出合計', 3), ('', 1), ('', 1), ('', 1),
                 ('', 1), ('所得代替率', 3)],
    '一元化':   [('収入合計', 5), ('支出合計', 3), ('', 1), ('', 1), ('', 1),
                 ('', 1), ('所得代替率', 3)],
}


def fmt(v, unit):
    if v is None:
        return '―'
    if unit == '％':
        return f'{v * 100:.1f}'
    return f'{v:.1f}'


def draw(got, side, title, subtitle, layout, out, years=YEARS):
    cols = COLS[layout]
    nc = len(cols) + 1                     # 年度列を足す
    nr = len(years)

    fig = plt.figure(figsize=(16.6, 9.6), dpi=200)
    fig.patch.set_facecolor(SURF)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    ax.set_facecolor(SURF)

    # 見出し
    ax.text(0.5, 0.965, title, fontsize=25, color=INK, ha='center',
            va='center', fontweight='bold')
    ax.text(0.5, 0.925, '（令和6(2024)年財政検証）', fontsize=13.5, color=INK,
            ha='center', va='center')
    # PDL1.0「国が作成したかのような態様で公表・利用してはいけません」への対応。
    # 公表資料と体裁が同じなので、非公式であることを表の中に必ず入れる。
    ax.text(0.5, 0.893, '非公式の再現 — 厚生労働省が作成したものではありません',
            fontsize=11, color=C_WARN, ha='center', va='center',
            fontweight='bold')
    for i, s in enumerate(subtitle):
        ax.text(0.045, 0.882 - i * 0.030, s, fontsize=13, color=INK, va='center')

    # ---- 表の骨格
    L, R = 0.035, 0.715
    TOP = 0.800
    HDR = 0.115                            # 見出し4段ぶんの高さ
    BOT = 0.100
    rowh = (TOP - HDR - BOT) / nr
    w_year = (R - L) * 0.052
    w = (R - L - w_year) / (nc - 1)
    xs = [L, L + w_year] + [L + w_year + w * (i + 1) for i in range(nc - 1)]

    def line(x0, y0, x1, y1, lw=1.0, c=RULE):
        ax.plot([x0, x1], [y0, y1], color=c, lw=lw, solid_capstyle='butt',
                zorder=5)

    y_grp = TOP
    y_sub = TOP - HDR * 0.33
    y_unit = TOP - HDR * 0.84
    y_body = TOP - HDR

    # 外枠と横罫
    line(L, TOP, R, TOP, 1.4)
    line(L, y_body, R, y_body, 1.4)
    line(L, BOT, R, BOT, 1.4)
    line(L, y_unit, R, y_unit, 0.8, RULE_2)

    # 縦罫。グループ見出しの結合セルの中では上段を引かない
    spans = []
    k = 0
    for lab, sp in GROUPS[layout]:
        spans.append((k, k + sp, bool(lab) and sp > 1))
        k += sp
    merged = set()
    for a, b, m in spans:
        if m:
            merged.update(range(a + 1, b))      # 結合セル内部の境界
    for j, x in enumerate(xs):
        if x in (L, R):
            line(x, TOP, x, BOT, 1.4)
        elif (j - 1) in merged:
            line(x, y_sub, x, BOT, 1.0)         # 上段は引かない
        else:
            line(x, TOP, x, BOT, 1.0)

    # 年度列
    ax.text((xs[0] + xs[1]) / 2, (TOP + y_sub) / 2, '年度', fontsize=11.5,
            color=INK, ha='center', va='center')
    ax.text((xs[0] + xs[1]) / 2, (y_unit + y_body) / 2 + rowh * 0.0, '西暦',
            fontsize=10.5, color=INK_2, ha='center', va='center')

    # グループ見出し
    i = 0
    for lab, span in GROUPS[layout]:
        x0, x1 = xs[1 + i], xs[1 + i + span]
        if lab:
            if lab == '所得代替率':
                ax.text((x0 + x1) / 2, y_grp + 0.018, '(参考)', fontsize=10,
                        color=INK_2, ha='center', va='center')
            ax.text((x0 + x1) / 2, (TOP + y_sub) / 2, lab, fontsize=11.5,
                    color=INK, ha='center', va='center')
            line(x0, y_sub, x1, y_sub, 0.8, RULE_2)
        i += span

    # 小見出しと単位
    i = 0
    grp_first = set()
    k = 0
    for lab, span in GROUPS[layout]:
        if lab:
            grp_first.add(k)
        k += span
    for j, (name, key, unit) in enumerate(cols):
        x0, x1 = xs[1 + j], xs[2 + j]
        xm = (x0 + x1) / 2
        if j in grp_first and GROUPS[layout]:
            pass
        # グループの先頭列（＝合計列）は上段にラベルがあるので小見出しを出さない
        show = not (j in grp_first and any(
            lab and span > 1 and s == j
            for s, (lab, span) in zip(
                [sum(sp for _, sp in GROUPS[layout][:m])
                 for m in range(len(GROUPS[layout]))], GROUPS[layout])))
        if show:
            fs = 9.6 if name.count('\n') < 2 else 8.2
            ax.text(xm, (y_sub + y_unit) / 2, name, fontsize=fs, color=INK,
                    ha='center', va='center', linespacing=1.22)
        ax.text(xm, (y_unit + y_body) / 2, unit, fontsize=9.6, color=INK_2,
                ha='center', va='center')
        i += 1

    # ---- 本体
    for r, y in enumerate(years):
        yc = y_body - rowh * (r + 0.5)
        if r % 2 == 1:
            ax.add_patch(plt.Rectangle((L, yc - rowh / 2), R - L, rowh,
                                       facecolor=BAND, edgecolor='none',
                                       zorder=1))
        ax.text((xs[0] + xs[1]) / 2, yc, str(y), fontsize=10.8, color=INK,
                ha='center', va='center', zorder=4)
        for j, (name, key, unit) in enumerate(cols):
            v = got.get(key, {}).get(y)
            ax.text(xs[2 + j] - w * 0.14, yc, fmt(v, unit), fontsize=10.8,
                    color=INK, ha='right', va='center', zorder=4)

    # ---- 右の3つの箱
    bx0, bx1 = 0.740, 0.985

    def box(y_top, rows, head=None, colw=(0.60, 0.40), fs=11):
        h = 0.040
        n = len(rows) + (1 if head else 0)
        y_bot = y_top - h * n
        ax.add_patch(plt.Rectangle((bx0, y_bot), bx1 - bx0, y_top - y_bot,
                                   facecolor=SURF, edgecolor=RULE, lw=1.3,
                                   zorder=3))
        yy = y_top
        if head:
            ax.text((bx0 + bx1) / 2, yy - h / 2, head, fontsize=fs + 0.5,
                    color=INK, ha='center', va='center', zorder=4,
                    fontweight='bold')
            yy -= h
            line(bx0, yy, bx1, yy, 1.0)
        xsplit = bx0 + (bx1 - bx0) * colw[0]
        for lab, val in rows:
            ax.text(bx0 + 0.012, yy - h / 2, lab, fontsize=fs, color=INK,
                    ha='left', va='center', zorder=4, linespacing=1.2)
            ax.text(bx1 - 0.012, yy - h / 2, val, fontsize=fs, color=INK,
                    ha='right', va='center', zorder=4)
            yy -= h
            if yy > y_bot + 1e-9:
                line(bx0, yy, bx1, yy, 0.7, RULE_2)
        line(xsplit, y_top - (h if head else 0), xsplit, y_bot, 0.7, RULE_2)
        return y_bot

    y = 0.800
    y = box(y, [('物価上昇率', side['bukka']),
                ('賃金上昇率（実質<対物価>）', side['chingin']),
                ('運用利回り　実質<対物価>', side['unyou']),
                ('　　　　　　スプレッド<対賃金>', side['spread']),
                ('経済成長率（実質）\n2034年度以降20〜30年', side['growth'])],
             head='長期の経済前提', colw=(0.62, 0.38))

    y -= 0.055
    y = box(y, [('所得代替率', f'{side["r_total"]}　　{side["e_total"]}'),
                ('　うち比例', f'{side["r_hirei"]}　　{side["e_hirei"]}'),
                ('　うち基礎', f'{side["r_kiso"]}　　{side["e_kiso"]}')],
             head='所得代替率（給付水準の調整終了後）／調整終了年度',
             colw=(0.44, 0.56), fs=10.5)

    y -= 0.055
    y = box(y, [('厚生年金の保険料率', side['ryoritsu']),
                ('国民年金の保険料月額\n（2004年度価格）', side['gessha'])],
             colw=(0.62, 0.38))

    # ---- 注記
    notes = [
        '(注0) 本表は第三者が公開プログラムを実行して作成した非公式の再現であり、'
        '厚生労働省が作成・承認したものではない。公表値と食い違う場合は公表値が正。',
        '(注1) 存続厚生年金基金の代行部分を含む。' +
        ('厚生年金全体の財政見通しである。' if layout == '厚生年金'
         else '国民年金と厚生年金を合わせた財政見通しである。'),
        '(注2) 「2024年度価格」は、④基礎年金が持つ2004年度価格への換算率 '
        'kakaku[] の比（kakaku[2024]/kakaku[k]）で換算したもの。',
        '(注3) 「積立度合」は、前年度末積立金の当年度の支出合計に対する倍率。',
        '(注4) 「報酬比例」には厚生年金の独自給付（定額、加給、加算）を含む。'
        '「その他収入」「その他支出」は列を省いているので、内訳の和は合計に一致しない。',
        '(注5) 「令和6(2024)年財政検証」（厚生労働省）'
        'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/nenkin/nenkin/zaisei-kensyo/index.html'
        ' の計算プログラム（資料001365945）を加工して作成。経済成長率のみ公表資料の値。',
    ]
    for i, s in enumerate(notes):
        ax.text(0.035, 0.074 - i * 0.0126, s, fontsize=8.2, color=INK_3,
                va='center')

    fig.savefig(out, facecolor=SURF)
    plt.close(fig)
    return out


def read_econ(econ, data_dir):
    """econ-XXXX.csv の長期前提行（2034年度以降）から前提を取る。
    列は 年度, 運用利回り(厚年), 運用利回り(国年), 列3, 列4, 実質賃金上昇率,
    物価上昇率（仕様書 §3.1）。"""
    p = os.path.join(data_dir, f'econ-{econ}.csv')
    for l in open(p, encoding='utf-8', errors='replace'):
        f = [x.strip() for x in l.split(',')]
        if f and f[0].isdigit() and int(f[0]) == 60:     # 2060年度＝長期前提
            r, chin, bukka = float(f[1]), float(f[5]), float(f[6])
            return dict(bukka=f'{bukka:.1f}%', chingin=f'{chin:.1f}%',
                        unyou=f'{r:.1f}%', spread=f'{r - chin:.1f}%')
    raise SystemExit(f'長期前提行が読めません: {p}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='3001')
    ap.add_argument('--econ', default=None)
    ap.add_argument('--waku', default=None)
    ap.add_argument('--yobi', default='000')
    ap.add_argument('--bas-yobi', default=None)
    ap.add_argument('--layout', default='厚生年金', choices=['厚生年金', '一元化'])
    ap.add_argument('--option', default=None, help='オプション名（1行目に出す）')
    ap.add_argument('--pop', default='出生中位、死亡中位、外国人の入国超過数16.4万人')
    ap.add_argument('--shushi-dir', default=None)
    ap.add_argument('--bas-dir', default=None)
    ap.add_argument('--econ-dir', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    econ = args.econ or args.case
    waku = args.waku or args.case
    bas_yobi = args.bas_yobi or args.yobi
    ver = f'{args.case}-{args.case}-{econ}-{waku}'
    shushi = args.shushi_dir or suuri_env.suuri('emp', 'rslt', 'ez_arev', 'shushi')
    bas = args.bas_dir or suuri_env.suuri('bas', 'rslt')
    econ_dir = args.econ_dir or suuri_env.suuri('emp', 'data', 'u-rev', 'econ')

    emp = CO.read_emp(ver, args.yobi, shushi)
    nat = CO.read_nat(ver, bas_yobi, bas)
    rate = CO.read_rate(ver, args.yobi, shushi)
    kakaku = CO.read_kakaku(ver, bas_yobi, bas)
    X = CO.read_provide(ver, args.yobi, bas) if args.layout == '一元化' else {}
    lay = '制度別' if args.layout == '厚生年金' else '一元化'
    built = CO.build(lay, emp, nat, rate, X, kakaku)
    got = built['厚生年金'] if lay == '制度別' else built[CO.UNIFIED_SHEET]

    # 調整終了年度は、代替率が動かなくなった最初の年度
    def endy(key):
        """代替率が動かなくなった最初の年度。足元から動かないなら「調整なし」。"""
        ys = [y for y in sorted(rate) if rate[y][key] > 0]
        if not ys:
            return None
        last = rate[ys[-1]][key]
        first = next(y for y in ys if abs(rate[y][key] - last) < 1e-13)
        return None if first == ys[0] else first

    fin = rate[max(rate)]
    e_t, e_k, e_h = (endy('所得代替率'), endy('代替率(基礎)'), endy('代替率(比例)'))
    side = read_econ(econ, econ_dir)
    side.update(
        growth=GROWTH.get(econ, '―'),
        r_total=f'{fin["所得代替率"] * 100:.1f}%',
        r_kiso=f'{fin["代替率(基礎)"] * 100:.1f}%',
        r_hirei=f'{fin["代替率(比例)"] * 100:.1f}%',
        e_total=f'{e_t}' if e_t else '調整なし',
        e_kiso=f'{e_k}' if e_k else '調整なし',
        e_hirei=f'{e_h}' if e_h else '調整なし',
        ryoritsu='18.3%',
        gessha='17,000円',
    )

    title = ('厚生年金の財政見通し' if args.layout == '厚生年金'
             else '国民年金及び厚生年金の財政見通し')
    sub = [f'○　人口：{args.pop}', f'○　経済：{CASES.get(econ, econ)}']
    if args.option:
        sub.insert(0, f'○　オプション：{args.option}')

    out = args.out or os.path.join(
        HERE, f'財政見通し_{CASES.get(econ, econ)}'
              + (f'_{args.option}' if args.option else '') + '.png')
    print(draw(got, side, title, sub, args.layout, out))


if __name__ == '__main__':
    sys.exit(main())
