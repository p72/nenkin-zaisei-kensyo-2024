#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プレゼン用の1枚: 経済前提8ケースの所得代替率と公表値の照合
===========================================================
データは 検証/実行/run_all_cases.sh の実行結果（仕様書 §15.0.0）。
公表値は厚生労働省「令和6(2024)年財政検証結果の概要」3頁。
https://www.mhlw.go.jp/content/001270476.pdf

    python3 検証/図/make_chart.py [出力パス]
"""
import os
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

# ---- 配色（dataviz スキルの検証済みパレット、light モード全チェック PASS）----
SURFACE   = '#ffffff'
INK       = '#0b0b0b'   # text-primary
INK_2     = '#52514e'   # text-secondary
INK_3     = '#8a8880'   # muted
S_HIREI   = '#2a78d6'   # categorical slot 1 : 報酬比例部分
S_KISO    = '#eb6834'   # categorical slot 2 : 基礎年金部分
GRID      = '#e8e7e3'

# ---- データ ----
# (ラベル, 経済変動, 比例, 基礎, 公表合計, 調整終了年度)
ROWS = [
    ('高成長実現',           False, 24.9711, 31.9411, 56.9, 2039),
    ('成長型経済移行・継続', False, 24.9711, 32.6495, 57.6, 2037),
    ('過去30年投影',         False, 24.8761, 25.5153, 50.4, 2057),
    ('1人当たりゼロ成長',    False, 17.9072, 21.8476, None, 2120),
    ('高成長実現',           True,  24.9711, 32.3287, None, 2038),
    ('成長型経済移行・継続', True,  24.9711, 33.1655, None, 2036),
    ('過去30年投影',         True,  24.9711, 26.6646, None, 2054),
    ('1人当たりゼロ成長',    True,  21.7772, 18.4234, None, 2120),
]
ASHIMOTO = ('2024年度（足元・実績）', 25.0, 36.2)   # 公表 61.2%

rows = sorted(ROWS, key=lambda r: -(r[2] + r[3]))


HERE = os.path.dirname(os.path.abspath(__file__))


def main(out=None):
    out = out or os.path.join(HERE, '所得代替率_8ケース.png')
    fig, ax = plt.subplots(figsize=(13.4, 7.4), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    BH = 0.52          # 棒の太さ（スロットを埋めない）
    GAP = 2 / 100      # 積み上げ segment 間の 2px 相当のサーフェス gap
    ys, labels = [], []

    # 足元の実績（基準行）。将来ケースとは1行分空ける
    y_ashi = len(rows) + 0.5
    ax.barh(y_ashi, ASHIMOTO[1], height=BH, color=S_HIREI, alpha=0.32,
            zorder=3, linewidth=0)
    ax.barh(y_ashi, ASHIMOTO[2], left=ASHIMOTO[1] + GAP, height=BH,
            color=S_KISO, alpha=0.32, zorder=3, linewidth=0)
    ax.text(ASHIMOTO[1] + ASHIMOTO[2] + 0.7, y_ashi, '61.2',
            va='center', ha='left', fontsize=13, color=INK_2)
    ax.text(-1.0, y_ashi, ASHIMOTO[0], va='center', ha='right',
            fontsize=11.5, color=INK_2)

    for i, (name, hendo, pro, kiso, pub, endy) in enumerate(rows):
        y = len(rows) - 1 - i
        ys.append(y)
        labels.append(name + ('（経済変動）' if hendo else ''))
        ax.barh(y, pro, height=BH, color=S_HIREI, zorder=3, linewidth=0)
        ax.barh(y, kiso, left=pro + GAP, height=BH, color=S_KISO,
                zorder=3, linewidth=0)

        total = pro + kiso
        # 合計は棒の先に（1本1つだけの直接ラベル）
        ax.text(total + 0.7, y, f'{total:.1f}', va='center', ha='left',
                fontsize=14, color=INK, fontweight='bold')
        # 調整終了年度
        ey = '調整終了せず' if endy >= 2120 else f'{endy}年度'
        ax.text(total + 4.3, y, ey, va='center', ha='left',
                fontsize=10, color=INK_3)
        # 公表値のマーカー（系列色ではなくインク＋サーフェスリング）
        if pub is not None:
            ax.plot([pub], [y], marker='D', markersize=8.5,
                    color=INK, markeredgecolor=SURFACE, markeredgewidth=2,
                    zorder=6, linestyle='none')

    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=11.5, color=INK)
    ax.tick_params(axis='y', length=0, pad=8)

    ax.set_xlim(0, 71)
    ax.set_xticks(range(0, 71, 10))
    ax.set_xticklabels([f'{v}%' for v in range(0, 71, 10)],
                       fontsize=10.5, color=INK_2)
    ax.tick_params(axis='x', length=0, pad=6)
    ax.xaxis.grid(True, color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_ylim(-0.75, y_ashi + 1.1)

    # 凡例（2系列以上は必ず置く）＋ 公表値マーカーの説明
    h_pro = plt.Rectangle((0, 0), 1, 1, color=S_HIREI)
    h_kis = plt.Rectangle((0, 0), 1, 1, color=S_KISO)
    h_pub = plt.Line2D([], [], marker='D', markersize=8.5, color=INK,
                       markeredgecolor=SURFACE, markeredgewidth=2, linestyle='none')
    ax.legend([h_pro, h_kis, h_pub],
              ['厚生年金（報酬比例部分）', '基礎年金部分', '厚労省の公表値'],
              loc='upper left', bbox_to_anchor=(0.0, -0.075), frameon=False,
              fontsize=11, handlelength=1.3, columnspacing=2.4,
              labelcolor=INK_2, ncol=3)

    # タイトル
    fig.text(0.012, 0.968,
             '公開された財政検証プログラムを動かしたら、公表値と一致した',
             fontsize=19, color=INK, fontweight='bold', va='top')
    fig.text(0.012, 0.912,
             '所得代替率（将来の年金額 ÷ その時の現役男子の平均手取り収入）。経済前提8ケースを通しで実行した結果。',
             fontsize=11.5, color=INK_2, va='top')
    fig.text(0.012, 0.876,
             '公表値のある3ケースで、合計・比例・基礎・調整終了年度の12項目すべてが一致。',
             fontsize=11.5, color=INK_2, va='top')

    # 読み取りの補助: 25%の参照線。比例部分がここに揃うことが幾何で見える
    ax.axvline(24.97, color=INK_3, linewidth=1.2, linestyle=(0, (4, 3)),
               zorder=4)
    ax.text(24.4, y_ashi + 0.62, '比例部分は約25%でほぼ一定 —— 差はほとんど基礎年金部分',
            fontsize=10.5, color=INK_2, ha='left', va='center')
    # 下2ケースは棒の外側でまとめて注記（棒を矢印で横切らない）
    ax.plot([52.6, 52.6], [-0.28, 1.28], color=INK_3, linewidth=1.2, zorder=4)
    ax.text(53.6, 0.5, 'この2ケースは\n比例部分も削られ、\n調整が期間内に\n終わらない',
            fontsize=10.5, color=INK_2, ha='left', va='center', linespacing=1.5)

    fig.text(0.012, 0.022,
             '計算: 厚生労働省が公開した2024年財政検証の数理計算プログラム（資料001365945、C/C++約38,000行）を'
             'そのままビルドして実行。\n'
             '公表値: 厚生労働省「令和6(2024)年財政検証結果の概要」3頁。'
             '1人当たりゼロ成長ケースは公表資料が単一の代替率を示していないため照合対象外。',
             fontsize=8.8, color=INK_3, va='bottom')

    fig.subplots_adjust(left=0.245, right=0.985, top=0.845, bottom=0.185)
    fig.savefig(out, facecolor=SURFACE)
    print(f'保存: {out}')
    return out


if __name__ == '__main__':
    main(*(sys.argv[1:2] or []))
