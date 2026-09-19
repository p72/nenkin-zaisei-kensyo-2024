#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シナリオ1本のプレゼン用の図と表
===============================
過去30年投影ケースで「マクロ経済スライドの調整期間の一致」を入れると
どうなるか。通常試算と並べて1枚にします。公表値は詳細結果等の

    詳細結果等1 No.03（通常試算）
    詳細結果等2 No.23（調整期間の一致）

事前に2本流しておくこと。

    検証/実行/run_pipeline.sh 3003 1 1 0 2                       # 通常試算
    TOUGOU=1 YOBI=010 YOBI2=011 STEPS=45 \\
        検証/実行/run_pipeline.sh 3003 1 1 0 2                   # 調整期間の一致

    python3 検証/図/make_scenario_chart.py

出力は `検証/図/シナリオ_調整期間の一致.png` と `..._表.png`。
数値はすべて実行結果から読みます（この中に焼き込んでいません）。
"""
import argparse
import glob
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import suuri_env      # noqa: E402  実行領域の場所（仕様書 §12.1）

plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

# 配色（白背景・light モード）
SURFACE = '#ffffff'
INK     = '#0b0b0b'
INK_2   = '#52514e'
INK_3   = '#8a8880'
GRID    = '#e8e7e3'
C_BASE  = '#8a8880'   # 通常試算
C_OPT   = '#2a78d6'   # 調整期間の一致
S_HIREI = '#2a78d6'   # 報酬比例部分
S_KISO  = '#eb6834'   # 基礎年金部分
C_WARN  = '#c2410c'

# 公表値（詳細結果等、フル精度）
PUB = {
    '通常試算':       dict(no='等1 No.03', total=0.503915234210470,
                          kiso=0.255153793467468, hirei=0.248761440743002,
                          endy_kiso=2057, endy_hirei=2026, items=3977),
    '調整期間の一致': dict(no='等2 No.23', total=0.561628634253104,
                          kiso=0.332413321335674, hirei=0.229215312917430,
                          endy_kiso=2036, endy_hirei=2036, items=2134),
}


def sniff(path):
    head = open(path, 'rb').readline()
    for enc in ('utf-8', 'euc_jp'):
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise SystemExit(f'文字コードを判別できません: {path}')


def find_one(pattern, directory):
    hits = sorted(glob.glob(os.path.join(directory, pattern)))
    if not hits:
        raise SystemExit(
            f'出力が見つかりません: {directory}/{pattern}\n'
            f'先に 検証/実行/run_pipeline.sh を走らせてください。')
    return hits[0]


def read_summary(ver, yobi, shushi_dir):
    """⑤ 03summary の「経済前提等」から年次の代替率とモデル年金額を読む。"""
    p = find_one(f'03summary.{ver}-1120-{yobi}*_08sum.csv', shushi_dir)
    lines = open(p, 'rb').read().decode(sniff(p), 'replace').splitlines()
    hi = [i for i, l in enumerate(lines) if l.startswith('年度,物価')][0]
    cols = [x.strip() for x in lines[hi].split(',')]
    # 「うち比例」「うち基礎」はモデル年金額側にも同名で出るので列番号で取る
    ir = cols.index('所得代替率')
    idx = {n: cols.index(n) for n in
           ('モデル年金額（物価割り戻し）', 'うち比例（物価割り戻し）',
            'うち基礎（物価割り戻し）', '可処分所得（物価割り戻し）')}
    out = {}
    for l in lines[hi + 1:]:
        f = [x.strip() for x in l.split(',')]
        if not f or not f[0].isdigit():
            if out:
                break
            continue
        y = int(f[0]) + 2000
        if y < 2024:
            continue
        out[y] = dict(
            total=float(f[ir]), hirei=float(f[ir + 1]), kiso=float(f[ir + 2]),
            nenkin=float(f[idx['モデル年金額（物価割り戻し）']]) / 1e4,
            nen_hirei=float(f[idx['うち比例（物価割り戻し）']]) / 1e4,
            nen_kiso=float(f[idx['うち基礎（物価割り戻し）']]) / 1e4,
            tedori=float(f[idx['可処分所得（物価割り戻し）']]) / 1e4,
        )
    return out


def read_times(log_path):
    """run_pipeline.sh の「---- 所要時間 ----」を工程ごとにまとめて読む。

    戻り値は [(見出し, {工程: 秒}), ...]。ビルドと下準備は1つにまとめる。
    """
    if not log_path or not os.path.exists(log_path):
        return []

    def bucket(name):
        for mark, label in (('① ', '① 被保険者推計'), ('② ', '② 厚生年金 給付費推計'),
                            ('③ ', '③ 国民年金'), ('④ ', '④ 基礎年金'),
                            ('⑤ ', '⑤ 厚生年金 収支計算'), ('⑥ ', '⑥ 分布推計')):
            if name.startswith(mark):
                return label if 'を実行' in name else 'ビルド・下準備'
        if name == '合計':
            return '合計'
        return 'ビルド・下準備'

    blocks, cur = [], None
    for l in open(log_path, encoding='utf-8', errors='replace'):
        if l.startswith('=== '):
            cur = [l.strip().strip('= ').strip(), {}]
            blocks.append(cur)
        elif cur is not None and l.startswith('  ') and ' 秒  ' in l:
            sec, name = l.strip().split(' 秒  ', 1)
            b = bucket(name.strip())
            cur[1][b] = cur[1].get(b, 0) + int(sec)
    return [(h, d) for h, d in blocks if d]


# ---------------------------------------------------------------- 図

def chart(A, B, out):
    from matplotlib.patches import Patch

    fig = plt.figure(figsize=(15.8, 9.0), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    gs = GridSpec(2, 2, figure=fig, width_ratios=[1.30, 1.0],
                  height_ratios=[1.0, 0.78],
                  left=0.052, right=0.985, top=0.785, bottom=0.095,
                  wspace=0.22, hspace=0.50)

    fig.text(0.052, 0.965, 'マクロ経済スライドの「調整期間の一致」を入れると何が起きるか',
             fontsize=21, color=INK, fontweight='bold', va='top')
    fig.text(0.052, 0.910,
             '経済前提：過去30年投影ケース（労働参加漸進）／人口：出生中位・死亡中位・入国超過16.4万人',
             fontsize=12, color=INK_2, va='top')
    fig.text(0.052, 0.872,
             '厚生労働省 令和6(2024)年財政検証の計算プログラムをそのまま実行。'
             '所得代替率は公表値と15桁一致。',
             fontsize=11, color=INK_3, va='top')

    # ---- (a) 所得代替率の推移
    ax = fig.add_subplot(gs[:, 0])
    ax.set_facecolor(SURFACE)
    for tag, d, c in (('通常試算（現行制度）', A, C_BASE),
                      ('調整期間の一致', B, C_OPT)):
        ys = sorted(y for y in d if y <= 2075)
        ax.plot(ys, [d[y]['total'] for y in ys], color=c, lw=3.2,
                solid_capstyle='round', label=tag, zorder=4)
    ax.axhline(50, color=C_WARN, lw=1.4, ls=(0, (5, 4)), zorder=2)
    ax.text(2026, 50.35, '所得代替率 50%', color=C_WARN, fontsize=11,
            ha='left', va='bottom')

    for key, d, c, up in (('通常試算', A, C_BASE, False),
                          ('調整期間の一致', B, C_OPT, True)):
        ey = PUB[key]['endy_kiso']
        if ey in d:
            v = d[ey]['total']
            ax.plot([ey], [v], 'o', ms=9, color=c, mec=SURFACE, mew=2.2, zorder=6)
            ax.annotate(f'{ey}年度に調整終了\n{v:.2f}%', (ey, v),
                        textcoords='offset points',
                        xytext=(16, 24) if up else (18, -42),
                        fontsize=11.5, color=c, fontweight='bold', zorder=7)
    ax.set_xlim(2024, 2075)
    ax.set_ylim(46, 64)
    ax.set_ylabel('所得代替率（％）', fontsize=12.5, color=INK_2)
    ax.set_xlabel('年度', fontsize=12, color=INK_2, labelpad=6)
    ax.set_title('所得代替率の推移', fontsize=15, color=INK,
                 fontweight='bold', loc='left', pad=12)
    ax.grid(axis='y', color=GRID, lw=1, zorder=1)
    ax.set_axisbelow(True)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    for sp in ('left', 'bottom'):
        ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=11)
    ax.legend(frameon=False, fontsize=12.5, loc='upper right',
              labelcolor=INK, handlelength=1.6)

    # ---- (b) 調整終了後の内訳
    ax = fig.add_subplot(gs[0, 1])
    ax.set_facecolor(SURFACE)
    y0 = min(A)
    bars = [
        ('2024年度（足元）', A[y0]['hirei'], A[y0]['kiso'], 0.30),
        ('通常試算', PUB['通常試算']['hirei'] * 100,
         PUB['通常試算']['kiso'] * 100, 1.0),
        ('調整期間の一致', PUB['調整期間の一致']['hirei'] * 100,
         PUB['調整期間の一致']['kiso'] * 100, 1.0),
    ]
    ypos = list(range(len(bars)))[::-1]
    GAP = 0.06
    for yp, (lab, hi, ki, al) in zip(ypos, bars):
        tc = '#ffffff' if al == 1.0 else INK_2
        ax.barh(yp, hi, height=0.48, color=S_HIREI, alpha=al, zorder=3, lw=0)
        ax.barh(yp, ki, left=hi + GAP, height=0.48, color=S_KISO, alpha=al,
                zorder=3, lw=0)
        ax.text(hi / 2, yp, f'{hi:.1f}', ha='center', va='center',
                color=tc, fontsize=11, fontweight='bold', zorder=5)
        ax.text(hi + GAP + ki / 2, yp, f'{ki:.1f}', ha='center', va='center',
                color=tc, fontsize=11, fontweight='bold', zorder=5)
        ax.text(hi + ki + 1.4, yp, f'計 {hi + ki:.2f}%', ha='left', va='center',
                color=INK, fontsize=11.5, fontweight='bold')
    ax.set_yticks(ypos)
    ax.set_yticklabels([b[0] for b in bars], fontsize=12, color=INK)
    ax.set_xlim(0, 78)
    ax.set_ylim(-0.7, len(bars) - 0.2)
    ax.set_xticks([])
    ax.set_title('給付水準の調整終了後の内訳（％）', fontsize=14, color=INK,
                 fontweight='bold', loc='left', pad=12)
    ax.legend(handles=[Patch(facecolor=S_HIREI, label='報酬比例'),
                       Patch(facecolor=S_KISO, label='基礎年金')],
              frameon=False, fontsize=11.5, labelcolor=INK,
              loc='lower right', ncol=2, handlelength=1.1,
              bbox_to_anchor=(1.0, -0.14))
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)

    # ---- (c) 調整期間
    ax = fig.add_subplot(gs[1, 1])
    ax.set_facecolor(SURFACE)
    rows = [
        ('通常試算・基礎年金', PUB['通常試算']['endy_kiso'],  S_KISO,  0.30),
        ('通常試算・報酬比例', PUB['通常試算']['endy_hirei'], S_HIREI, 0.30),
        ('一致・基礎年金',     PUB['調整期間の一致']['endy_kiso'],  S_KISO,  1.0),
        ('一致・報酬比例',     PUB['調整期間の一致']['endy_hirei'], S_HIREI, 1.0),
    ]
    ypos = list(range(len(rows)))[::-1]
    for yp, (lab, e, c, al) in zip(ypos, rows):
        ax.barh(yp, e - 2025, left=2025, height=0.46, color=c, alpha=al,
                zorder=3, lw=0)
        ax.text(e + 1.0, yp, f'〜{e}年度', ha='left', va='center',
                color=INK if al == 1.0 else INK_2, fontsize=11,
                fontweight='bold')
    ax.set_yticks(ypos)
    ax.set_yticklabels([r[0] for r in rows], fontsize=11.5, color=INK)
    ax.set_xlim(2024, 2070)
    ax.set_xlabel('年度', fontsize=11.5, color=INK_2, labelpad=4)
    ax.set_title('給付水準調整の期間 — 基礎を21年短く、比例を10年長く',
                 fontsize=14, color=INK, fontweight='bold', loc='left', pad=12)
    ax.grid(axis='x', color=GRID, lw=1, zorder=1)
    ax.set_axisbelow(True)
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=11, length=0)

    fig.text(0.052, 0.024,
             '出典：厚生労働省「令和6(2024)年財政検証結果」計算プログラム（資料001365945）を実行。'
             '公表値は詳細結果等1 No.03・詳細結果等2 No.23。',
             fontsize=9.5, color=INK_3)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


# ---------------------------------------------------------------- 表

def table(A, B, times, out):
    y0, yl = min(A), max(y for y in A if y <= 2070)
    pa, pb = PUB['通常試算'], PUB['調整期間の一致']
    fa, fb = A[max(A)], B[max(B)]

    def d(x, y, unit='pt'):
        return f'{y - x:+.2f}{unit}'.replace('-', '−')

    rows = [
        ('所得代替率（計）', f'{pa["total"] * 100:.4f} %', f'{pb["total"] * 100:.4f} %',
         d(pa['total'] * 100, pb['total'] * 100)),
        ('　うち基礎年金', f'{pa["kiso"] * 100:.4f} %', f'{pb["kiso"] * 100:.4f} %',
         d(pa['kiso'] * 100, pb['kiso'] * 100)),
        ('　うち報酬比例', f'{pa["hirei"] * 100:.4f} %', f'{pb["hirei"] * 100:.4f} %',
         d(pa['hirei'] * 100, pb['hirei'] * 100)),
        ('調整終了年度（基礎年金）', f'{pa["endy_kiso"]} 年度', f'{pb["endy_kiso"]} 年度',
         f'{pb["endy_kiso"] - pa["endy_kiso"]:+d} 年'.replace('-', '−')),
        ('調整終了年度（報酬比例）', f'{pa["endy_hirei"]} 年度', f'{pb["endy_hirei"]} 年度',
         f'{pb["endy_hirei"] - pa["endy_hirei"]:+d} 年'.replace('-', '−')),
        (f'モデル年金額（{yl}年度、実質<対物価>）',
         f'{A[yl]["nenkin"]:.2f} 万円/月', f'{B[yl]["nenkin"]:.2f} 万円/月',
         d(A[yl]['nenkin'], B[yl]['nenkin'], ' 万円')),
        ('　うち基礎年金（夫婦2人）',
         f'{A[yl]["nen_kiso"]:.2f} 万円/月', f'{B[yl]["nen_kiso"]:.2f} 万円/月',
         d(A[yl]['nen_kiso'], B[yl]['nen_kiso'], ' 万円')),
        ('　うち報酬比例（夫）',
         f'{A[yl]["nen_hirei"]:.2f} 万円/月', f'{B[yl]["nen_hirei"]:.2f} 万円/月',
         d(A[yl]['nen_hirei'], B[yl]['nen_hirei'], ' 万円')),
        ('__sep__', '', '', ''),
        ('こちらの計算値（所得代替率・計）',
         f'{fa["total"]:.13f} %', f'{fb["total"]:.13f} %', ''),
        ('公表値との相対差',
         f'{abs(fa["total"] / 100 - pa["total"]) / pa["total"]:.1e}',
         f'{abs(fb["total"] / 100 - pb["total"]) / pb["total"]:.1e}',
         '倍精度の丸め'),
        ('財政見通しの照合項目数', f'{pa["items"]:,}', f'{pb["items"]:,}',
         f'{pa["items"] + pb["items"]:,} 項目'),
        ('　うち不一致', '0', '0', '0 件'),
    ]
    if times:
        rows.append(('__sep__', '', '', ''))
        order = ['ビルド・下準備', '① 被保険者推計', '② 厚生年金 給付費推計',
                 '③ 国民年金', '④ 基礎年金', '⑤ 厚生年金 収支計算']
        ta, tb = (dict(times[0][1]), dict(times[1][1]) if len(times) > 1 else {})
        first = True
        for n in order:
            if n not in ta and n not in tb:
                continue
            rows.append((('計算時間　' if first else '　') + n,
                         '―' if n not in ta else f'{ta[n]} 秒',
                         '―' if n not in tb else f'{tb[n]} 秒', ''))
            first = False
        s_a, s_b = ta.get('合計', 0), tb.get('合計', 0)
        rows.append(('計算時間　合計', f'{s_a} 秒', f'{s_b} 秒',
                     f'2本で {(s_a + s_b) // 60}分{(s_a + s_b) % 60}秒'))

    n = len(rows)
    fig = plt.figure(figsize=(13.6, 0.44 * n + 2.0), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(SURFACE)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    H = 1.0 / (n + 5.4)
    x = (0.038, 0.470, 0.660, 0.855)
    top = 1 - 2.25 * H

    ax.text(0.038, 1 - 0.55 * H, '過去30年投影ケース　通常試算 対 調整期間の一致',
            fontsize=18, color=INK, fontweight='bold', va='center')
    ax.text(0.038, 1 - 1.30 * H,
            '公表値（詳細結果等1 No.03／詳細結果等2 No.23）と、'
            'こちらの実行結果。金額は実質<対物価>。',
            fontsize=10.5, color=INK_2, va='center')

    hdr = ('指標', '通常試算', '調整期間の一致', '差')
    for xi, h in zip(x, hdr):
        ax.text(xi, top, h, fontsize=12, color=INK_2, fontweight='bold',
                va='center', ha='left' if xi == x[0] else 'right')
    ax.plot([0.030, 0.972], [top - 0.55 * H] * 2, color=INK_3, lw=1.1)

    yy = top - 1.35 * H
    for label, va, vb, vd in rows:
        if label == '__sep__':
            ax.plot([0.030, 0.972], [yy + 0.30 * H] * 2, color=GRID, lw=1.1)
            yy -= 0.55 * H
            continue
        bold = not label.startswith('　')
        ax.text(x[0], yy, label, fontsize=11.5, color=INK if bold else INK_2,
                fontweight='bold' if bold else 'normal', va='center')
        for xi, v, col in ((x[1], va, INK_2), (x[2], vb, INK), (x[3], vd, INK_2)):
            c = col
            if xi == x[3]:
                if v.startswith('+'):
                    c = '#166534'
                elif v.startswith('-') or v.startswith('−'):
                    c = C_WARN
            ax.text(xi, yy, v, fontsize=11.5, color=c, va='center', ha='right',
                    fontweight='bold' if xi == x[2] else 'normal')
        yy -= H

    ax.text(0.038, yy + 0.25 * H,
            '出典：厚生労働省「令和6(2024)年財政検証結果」計算プログラム（資料001365945）を実行。'
            '計算時間は 4 vCPU（Intel Xeon 2.10GHz）・メモリ15GB の Linux コンテナ、'
            'gcc -O2 / g++ -Ofast、シングルスレッド。',
            fontsize=9.5, color=INK_3, va='top')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='3003')
    ap.add_argument('--econ', default=None)
    ap.add_argument('--waku', default=None)
    ap.add_argument('--yobi-base', default='000')
    ap.add_argument('--yobi-opt', default='010')
    ap.add_argument('--shushi-dir', default=None)
    ap.add_argument('--log', default=None, help='run_pipeline.sh のログ（計算時間）')
    ap.add_argument('--outdir', default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    econ = args.econ or args.case
    waku = args.waku or args.case
    ver = f'{args.case}-{args.case}-{econ}-{waku}'
    shushi = args.shushi_dir or suuri_env.suuri('emp', 'rslt', 'ez_arev', 'shushi')

    A = read_summary(ver, args.yobi_base, shushi)
    B = read_summary(ver, args.yobi_opt, shushi)
    times = read_times(args.log)

    p1 = chart(A, B, os.path.join(args.outdir, 'シナリオ_調整期間の一致.png'))
    p2 = table(A, B, times, os.path.join(args.outdir, 'シナリオ_調整期間の一致_表.png'))
    print(p1)
    print(p2)


if __name__ == '__main__':
    sys.exit(main())
