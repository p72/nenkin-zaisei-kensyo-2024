# -*- coding: utf-8 -*-
"""
国民年金/econ.c の移植に対するテスト
====================================
    pytest 検証/                      # 全部
    pytest 検証/ -m "not slow"        # 差分テスト（要 g++）を除く

3層構成:
  1. 単位テスト     個々の関数を手計算値と照合
  2. ゴールデンテスト 公表された年金額・経済前提と照合
  3. 差分テスト     原本Cを無修正でコンパイルし、出力を1要素ずつ照合（要 g++）
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'differential'))

import port_econ as P  # noqa: E402

ECON_DIR = os.path.join(ROOT, 'papers', '001365945', 'データ', 'suuri',
                        'rev2024', 'emp', 'data', 'u-rev', 'econ')
# 2021年度以降のマクロ経済スライド調整率（基礎年金/econ.c の pre_cut）
EXTRA_MACRO = {2021: 1.0, 2022: 1.0, 2023: 0.994, 2024: 0.996}


@pytest.fixture(scope='module')
def series():
    """高成長実現ケースで、マクロ経済スライドを2024年度まで入れた系列"""
    return P.econ(os.path.join(ECON_DIR, 'econ-3001.csv'), extra_macro=EXTRA_MACRO)


# ------------------------------------------------------- 1. 単位テスト
class TestMarume:
    """丸めの3つの関数"""

    @pytest.mark.parametrize('a,n,want', [
        (1.0234, 3, 1.023),
        (1.0235, 3, 1.024),   # sprintf は 0.5 を上に丸める側に倒れる値
        (0.9995, 3, 1.0),
        (1.0, 3, 1.0),
    ])
    def test_c_round(self, a, n, want):
        assert P.c_round(a, n) == want

    def test_kaiteiritu_marume_丸め年度まで(self):
        assert P.kaiteiritu_marume(2024, 2024, 1.04549) == 1.045

    def test_kaiteiritu_marume_丸め年度より後は丸めない(self):
        assert P.kaiteiritu_marume(2025, 2024, 1.04549) == 1.04549

    @pytest.mark.parametrize('a,want', [
        (780_120.0, 780_100),   # 50円未満は切り捨て
        (780_150.0, 780_200),   # 50円以上は切り上げ
        (816_040.5, 816_000),
        (813_697.8, 813_700),
    ])
    def test_pension_marume(self, a, want):
        assert P.pension_marume(a) == want


class TestKaiteiritu:
    """改定率の選択ルール。§5.6 の分岐をひとつずつ踏む"""

    def test_2021年度前_新規裁定_賃金が物価を下回ると1に留まる(self):
        # 賃金 < 1 かつ 賃金 < 物価、物価 > 1 → 据え置き
        assert P.kaiteiritu_make_before(67, bui=0.996, cui=1.005) == 1.0

    def test_2021年度前_新規裁定_賃金が物価を下回り物価も1未満なら物価(self):
        assert P.kaiteiritu_make_before(67, bui=0.990, cui=0.997) == 0.997

    def test_2021年度前_新規裁定_それ以外は賃金(self):
        assert P.kaiteiritu_make_before(67, bui=1.023, cui=1.027) == 1.023

    def test_2021年度前_既裁定_物価より賃金が低く賃金1以上なら賃金(self):
        assert P.kaiteiritu_make_before(68, bui=1.003, cui=1.010) == 1.003

    def test_2021年度前_既裁定_物価1超で賃金1未満なら据え置き(self):
        assert P.kaiteiritu_make_before(68, bui=0.996, cui=1.005) == 1.0

    def test_2021年度前_既裁定_それ以外は物価(self):
        assert P.kaiteiritu_make_before(68, bui=1.010, cui=1.003) == 1.003

    def test_2021年度以降_新規裁定は常に賃金(self):
        # 名目下限が外れ、賃金がマイナスでも賃金に合わせる
        assert P.kaiteiritu_make(67, bui=0.996, cui=1.005) == 0.996

    def test_2021年度以降_既裁定は低いほう(self):
        assert P.kaiteiritu_make(68, bui=1.028, cui=1.025) == 1.025
        assert P.kaiteiritu_make(68, bui=1.031, cui=1.032) == 1.031


class TestIndexMake:
    """名目手取り賃金変動率の組み立て"""

    def test_可処分所得割合変化率は保険料率の引上げを反映する(self):
        cpi, bur = P.econ_read(os.path.join(ECON_DIR, 'econ-3001.csv'))
        bui, cui = P.index_make(bur, cpi, P.MARUME_NENDO)
        # 料率引上げ期（〜2020年度）は可処分所得が目減りするので
        # 名目手取り賃金変動率は「物価 × 実質賃金3年平均」より小さくなる
        assert bui[2015] < cui[2015]

    def test_物価変動率は前年度の物価上昇率(self):
        cpi, bur = P.econ_read(os.path.join(ECON_DIR, 'econ-3001.csv'))
        bui, cui = P.index_make(bur, cpi, P.MARUME_NENDO)
        assert cui[2024] == P.kaiteiritu_marume(2024, P.MARUME_NENDO, cpi[2023])

    def test_2005と2006年度は実質賃金3年平均を1に固定(self):
        cpi, bur = P.econ_read(os.path.join(ECON_DIR, 'econ-3001.csv'))
        bui, cui = P.index_make(bur, cpi, P.MARUME_NENDO)
        for nendo in (2005, 2006):
            assert bui[nendo] == cui[nendo]


# --------------------------------------------- 2. ゴールデンテスト
# 老齢基礎年金の満額（年額・円）。厚労省・日本年金機構の公表値。
# 2014年度までは物価スライド特例措置により支給額が本来水準を上回るため、
# プログラムが扱う本来水準と一致しない。比較は2015年度以降。
MANGAKU_SHINKI = {
    2015: 780_100, 2016: 780_100, 2017: 779_300, 2018: 779_300,
    2019: 780_100, 2020: 781_700, 2021: 780_900, 2022: 777_800,
    2023: 795_000, 2024: 816_000,
}
# 既裁定（物価に合わせる側）。境界年齢は年度によって動く。
MANGAKU_KISAI = {
    (2023, 68): 792_600,
    (2024, 69): 813_700,
}


def mangaku(series, nendo, nenrei):
    """満額を取り出す。

    原本の Full_Pension は SHONENDO(2020)年度からしか埋まらない
    （mseid.h の配列が [SAISHUNENDO - SHONENDO + 1] で切られている）。
    2019年度以前は、同じ式 780,900円 × 改定率 を直接評価する。
    """
    _, ruiseki, full = series
    if nendo >= P.SHONENDO:
        return full[nendo][nenrei]
    return P.pension_marume(P.FULL_PENSION_SHONENDO * ruiseki[nendo][nenrei])


@pytest.mark.parametrize('nendo,want', sorted(MANGAKU_SHINKI.items()))
def test_満額_新規裁定(series, nendo, want):
    assert mangaku(series, nendo, P.UNDER_67) == want


@pytest.mark.parametrize('key,want', sorted(MANGAKU_KISAI.items()))
def test_満額_既裁定(series, key, want):
    nendo, nenrei = key
    assert mangaku(series, nendo, nenrei) == want


@pytest.mark.parametrize('nendo', [2020, 2021, 2022, 2023, 2024])
def test_満額の2つの経路が一致する(series, nendo):
    """プログラムの Full_Pension と 780,900円×改定率 が一致することを確認。
    2019年度以前の比較が式の直接評価でよいことの裏付けになる。"""
    _, ruiseki, full = series
    direct = P.pension_marume(P.FULL_PENSION_SHONENDO * ruiseki[nendo][P.UNDER_67])
    assert full[nendo][P.UNDER_67] == direct


def test_満額の年齢境界(series):
    """2024年度は68歳までが816,000円、69歳以上が813,700円"""
    _, _, full = series
    assert full[2024][68] == 816_000
    assert full[2024][69] == 813_700
    assert full[2023][67] == 795_000
    assert full[2023][68] == 792_600


# 令和6年財政検証 長期の経済前提（2034年度以降）
# 厚生労働省「令和6(2024)年財政検証結果の概要」2頁
# https://www.mhlw.go.jp/content/001270476.pdf
CHOUKI_ZENTEI = {
    '3001': ('高成長実現ケース',           2.0, 2.0, 3.4, 1.4),
    '3002': ('成長型経済移行・継続ケース', 2.0, 1.5, 3.2, 1.7),
    '3003': ('過去30年投影ケース',         0.8, 0.5, 2.2, 1.7),
    '3004': ('1人当たりゼロ成長ケース',    0.4, 0.1, 1.4, 1.3),
}


@pytest.mark.parametrize('tag', sorted(CHOUKI_ZENTEI))
def test_長期の経済前提(tag):
    name, cpi, wage, ret, spread = CHOUKI_ZENTEI[tag]
    rows = [l for l in open(os.path.join(ECON_DIR, f'econ-{tag}.csv'), 'rb')
            .read().decode('euc_jp').splitlines() if l.strip()]
    d = [float(x) for x in rows[-1].split(',')]
    assert d[6] == cpi,  f'{name}: 物価上昇率'
    assert d[5] == wage, f'{name}: 実質賃金上昇率'
    assert d[1] == ret,  f'{name}: 実質運用利回り（対物価）'
    got = round(((1 + d[1] / 100) / (1 + d[5] / 100) - 1) * 100, 1)
    assert got == spread, f'{name}: スプレッド（対賃金）'


@pytest.mark.parametrize('tag', sorted(CHOUKI_ZENTEI))
def test_経済変動ケースは長期前提に収束する(tag):
    """econ-32XX は 2057年度以降 econ-30XX と一致する"""
    def rows(t):
        return [l for l in open(os.path.join(ECON_DIR, f'econ-{t}.csv'), 'rb')
                .read().decode('euc_jp').splitlines() if l.strip()]
    base, hendo = rows(tag), rows('32' + tag[2:])
    for a, b in zip(base, hendo):
        nendo = int(a.split(',')[0]) + 2000
        if nendo >= 2057:
            assert a == b, f'{nendo}年度で乖離'


@pytest.mark.parametrize('tag', ['3001', '3002', '3003', '3004',
                                 '3201', '3202', '3203', '3204'])
def test_econ列3と4は列5の複製(tag):
    """どの系統も読まない列。列5と同値であることを確認"""
    for line in open(os.path.join(ECON_DIR, f'econ-{tag}.csv'), 'rb') \
            .read().decode('euc_jp').splitlines():
        if not line.strip():
            continue
        d = [float(x) for x in line.split(',')]
        assert d[3] == d[4] == d[5], f'{tag}: {line}'


def test_法定額(series):
    """国民年金法27条の基準額。改定率1.000の年度で満額と一致する"""
    _, ruiseki, full = series
    assert P.FULL_PENSION_SHONENDO == 780_900.0
    assert ruiseki[2021][P.UNDER_67] == 1.0
    assert full[2021][P.UNDER_67] == 780_900


def test_保険料率テーブルが法定の引上げ幅に一致する():
    """2003年度13.58%から毎年0.354%、2017年度に18.3%で固定"""
    import inspect
    src = inspect.getsource(P.index_make)
    ns = {}
    exec('HOKENRYO = ' + src.split('HOKENRYO = ')[1].split(']')[0] + ']', ns)
    h = ns['HOKENRYO']
    assert h[0] == 0.1358
    assert h[-1] == 0.183
    for i in range(1, 14):
        assert round(h[i] - h[i - 1], 5) == 0.00354, f'{i}番目の引上げ幅'


# ------------------------------------------------------- 3. 差分テスト
@pytest.mark.slow
@pytest.mark.skipif(shutil.which('g++') is None, reason='g++ が無い')
@pytest.mark.parametrize('tag', ['3001', '3002', '3003', '3004',
                                 '3201', '3202', '3203', '3204'])
def test_差分_原本Cと一致する(tmp_path, tag):
    """原本 国民年金/econ.c を無修正でコンパイルし、全年度×全年齢で照合する。

    ここでは extra_macro を渡さない（原本は2021年度以降のマクロ経済スライドを
    持たないため）。渡すと当然ずれる。
    """
    build = str(tmp_path)
    env = dict(os.environ, BUILD_DIR=build)
    subprocess.run([os.path.join(HERE, 'differential', 'build_and_run.sh'),
                    os.path.join(ECON_DIR, f'econ-{tag}.csv')],
                   env=env, check=True, capture_output=True)
    r = subprocess.run([sys.executable,
                        os.path.join(HERE, 'differential', 'compare.py'), build],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '不一致 0' in r.stdout, r.stdout
