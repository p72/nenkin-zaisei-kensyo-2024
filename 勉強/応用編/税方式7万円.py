#!/usr/bin/env python3
"""基礎年金を税方式にして65歳以上に一律月7万円を給付したら（思考実験・非公式）。

設計
  - 実施年度（2027年度）から、65歳以上の全員に月7万円（実施年度の額。以後は賃金に連動）
  - 障害・遺族の基礎年金は現行制度の水準のまま、税で払う
  - 国民年金保険料は廃止。厚生年金保険料は、基礎年金に当たる分（基礎年金拠出金の負担）を下げる
    → ⑤で ZEI レバー（検証/実行/run_pipeline.sh）。報酬比例は現行制度のまま
  - 足りない税は、所得税に一律の率で上乗せする（復興特別所得税と同じ「税額 × 率」の方式）

予備番号 901（ZEI=2027）。④は通常試算と同じ。

使い方（リポジトリの直下で）
  python3 勉強/応用編/税方式7万円.py run 3003 1 1 0 2   # ④⑤を流す（高成長実現は run 3001）
  python3 勉強/応用編/税方式7万円.py report              # 財源・所得税の上乗せ率・所得代替率
  python3 勉強/応用編/税方式7万円.py kakei               # 家計の負担の変化
  python3 勉強/応用編/税方式7万円.py table 3003 3001     # 財政見通し対照表（勉強/応用編/図/）
"""
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
SH = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi")
START = 2027
YOBI = "901"
GETSU = 70000                  # 実施年度（2027年度）の月額
SHOTOKU_2025 = 25.3e12         # 所得税収（一般会計、2025年度決算）。財務省「一般会計税収の推移」
CASES = (("3003", "過去30年投影"), ("3001", "高成長実現"))
YEARS = (2027, 2030, 2040, 2050, 2060, 2080, 2100, 2120)


def run(args):
    env = dict(os.environ, ZEI=str(START), YOBI=YOBI, STEPS="45")
    subprocess.run([os.path.join(ROOT, "検証", "実行", "run_pipeline.sh")] + args, env=env, check=True)
    for p in os.listdir(SH):
        if p.startswith("90nenbe.") and f"-1120-{YOBI}e_" in p:
            os.remove(os.path.join(SH, p))


def _mods():
    sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
    sys.path.insert(0, os.path.join(ROOT, "検証", "3号廃止"))
    import compare_option as co
    import make_taishohyo as T
    s = importlib.util.spec_from_file_location("a", os.path.join(ROOT, "検証", "3号廃止", "analyze_sango.py"))
    a = importlib.util.module_from_spec(s)
    s.loader.exec_module(a)
    return co, T, a


def pop65(case):
    """①被保険者推計が使う人口（男女計）の65歳以上。人。"""
    import csv
    p = os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", f"rslt{case}", f"waku{case}-20.csv")
    L = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    i = L[1].index("65")
    return {int(r[2]): sum(float(x) for x in r[i:]) for r in L[2:] if len(r) > 5 and r[1] == "0"}


def tedori(case):
    """⑤ 03summary（通常試算）の現役男子の平均手取り（月額・名目）。"""
    co, _, _ = _mods()
    p = co.find_one(f"03summary.{case}-{case}-{case}-{case}-1120-000*_08sum.csv", SH)
    L = co.lines_of(p)
    hi = [i for i, l in enumerate(L) if l.startswith("年度,物価")][0]
    c = [x.strip() for x in L[hi].split(",")].index("可処分所得")
    out = {}
    for l in L[hi + 1:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].isdigit():
            if out:
                break
            continue
        out[int(f[0]) + 2000] = float(f[c])
    return out


def delta(case):
    p = os.path.join(SUURI, "emp", "log", f"emp-{case}-{case}-{case}-{case}-1120-{YOBI}.log")
    return float(re.search(r"税方式：保険料率を\d+年度から ([0-9.]+)",
                           open(p, encoding="utf-8", errors="replace").read()).group(1))


def zaigen(case):
    """年度ごとの税方式の基礎年金の費用と財源（円・名目）。"""
    co, _, a = _mods()
    v = f"{case}-{case}-{case}-{case}"
    kb = a.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{v}-1120-000a.csv"))
    h, rows = kb["基礎年金給付費（新法＋旧法）"]
    # 見出しは「合計×6・老齢×6・障害×6・遺族×6」。制度計は各グループの先頭（列1・7・13・19）
    shogai = {int(r[0]): r[13] + r[19] for r in rows}
    run = a.load_run(SUURI, case, "000", "000")
    toku = a.series(kb["特別国庫負担内訳"], "合計")
    emp0 = co.read_emp(v, "000", SH)
    P, kw = pop65(case), tedori(case)
    d = delta(case)
    out = {"kiso": 2 * GETSU / kw[START] * 100}   # 夫婦2人分の一律給付の、手取りに対する割合（%）
    for y in range(START, 2121):
        g = GETSU * kw[y] / kw[START]
        kyufu = g * 12 * P[y]
        cost = kyufu + shogai[y]
        old = run["kokko_total"][y] + toku[y]
        shotoku = SHOTOKU_2025 * emp0[y]["標準報酬総額"] / emp0[2025]["標準報酬総額"]
        out[y] = dict(getsu=g, pop=P[y], kyufu=kyufu, shogai=shogai[y], cost=cost, old=old,
                      extra=cost - old, shotoku=shotoku, ritu=(cost - old) / shotoku,
                      kn_hoken=run["kn_hoken"][y], kou_down=d * emp0[y]["標準報酬総額"] * 1e12)
    return out, d


def report():
    co, _, _ = _mods()
    for case, cname in CASES:
        z, d = zaigen(case)
        v = f"{case}-{case}-{case}-{case}"
        rb, rz = co.read_rate(v, "000", SH)[2120], co.read_rate(v, YOBI, SH)[2120]
        kiso = z["kiso"]
        print(f"## {cname}  厚生年金保険料率 18.3% → {18.3 - d * 100:.2f}%（−{d * 100:.2f}％pt）")
        print(f"所得代替率（2120年度）: 現行 {rb['所得代替率']*100:.1f}%（比例 {rb['代替率(比例)']*100:.1f}・基礎 "
              f"{rb['代替率(基礎)']*100:.1f}） → 税方式 {rz['代替率(比例)']*100 + kiso:.1f}%（比例 "
              f"{rz['代替率(比例)']*100:.1f}・基礎 {kiso:.1f}）")
        print("| 年度 | 月額（名目） | 65歳以上 | 給付費（65歳以上） | 障害・遺族 | 現行の国庫負担 | 追加の税 | "
              "所得税収（見込み） | 所得税の上乗せ率 | 廃止する国年保険料 | 厚年保険料の減 |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for y in YEARS:
            t = z[y]
            print(f"| {y} | {t['getsu']:,.0f}円 | {t['pop'] / 1e4:,.0f}万人 | {t['kyufu'] / 1e12:.1f}兆円 | "
                  f"{t['shogai'] / 1e12:.1f}兆円 | {t['old'] / 1e12:.1f}兆円 | {t['extra'] / 1e12:.1f}兆円 | "
                  f"{t['shotoku'] / 1e12:.1f}兆円 | {t['ritu'] * 100:.0f}% | {t['kn_hoken'] / 1e12:.1f}兆円 | "
                  f"{t['kou_down'] / 1e12:.1f}兆円 |")
        print()


# ---------------------------------------------------------------------------
# 家計の負担（2024年度の税制・賃金水準。所得税だけで住民税は含めない）
# ---------------------------------------------------------------------------
def kyuyo_kojo(x):
    if x <= 1_625_000: return 550_000
    if x <= 1_800_000: return x * 0.4 - 100_000
    if x <= 3_600_000: return x * 0.3 + 80_000
    if x <= 6_600_000: return x * 0.2 + 440_000
    if x <= 8_500_000: return x * 0.1 + 1_100_000
    return 1_950_000


def shotokuzei(kazei):
    """所得税額（2024年分の税率表、復興特別所得税を含めない）。"""
    kazei = max(0, int(kazei // 1000 * 1000))
    for lim, r, k in ((1_950_000, .05, 0), (3_300_000, .10, 97_500), (6_950_000, .20, 427_500),
                      (9_000_000, .23, 636_000), (18_000_000, .33, 1_536_000),
                      (40_000_000, .40, 2_796_000), (float("inf"), .45, 4_796_000)):
        if kazei <= lim:
            return kazei * r - k


def kaishain(nenshu, kounen_ritu):
    """単身の会社員（40歳未満、賞与なし）。社会保険料＝厚年本人分＋健保5.0%＋雇用0.6%。"""
    hyo = min(nenshu, 650_000 * 12)                  # 標準報酬月額の上限 65万円
    kounen = hyo * kounen_ritu / 2
    shaho = kounen + min(nenshu, 1_390_000 * 12) * 0.05 + nenshu * 0.006
    tax = shotokuzei(nenshu - kyuyo_kojo(nenshu) - 480_000 - shaho)
    return kounen, tax, hyo


def kakei():
    for case, cname in CASES:
        z, d = zaigen(case)
        r = z[START]["ritu"]
        print(f"## {cname}（{START}年度の率：厚生年金保険料率 −{d * 100:.2f}％pt、所得税の上乗せ {r * 100:.0f}%。"
              "2024年度の賃金水準・税制、年額）")
        print("| 世帯 | 保険料の減 | 所得税の増 | 差し引き（＋は負担増） | 参考：会社の保険料の減 |")
        print("|---|---|---|---|---|")
        for n in (3_000_000, 5_000_000, 8_000_000, 12_000_000):
            k0, t0, hyo = kaishain(n, 0.183)
            k1, t1, _ = kaishain(n, 0.183 - d)
            dz = t1 * (1 + r) - t0
            print(f"| 会社員・単身 年収{n // 10000}万円 | −{k0 - k1:,.0f}円 | +{dz:,.0f}円 | "
                  f"{dz - (k0 - k1):+,.0f}円".replace("-", "−") + f" | −{hyo * d / 2:,.0f}円 |")
        # 自営業（第1号）：事業所得300万円、国民健康保険料は所得の約10%と置く
        for sho in (3_000_000, 6_000_000):
            kokunen = 16_980 * 12
            kokuho = sho * 0.10
            t0 = shotokuzei(sho - 480_000 - kokunen - kokuho)
            t1 = shotokuzei(sho - 480_000 - kokuho) * (1 + r)
            print(f"| 自営業（第1号） 所得{sho // 10000}万円 | −{kokunen:,.0f}円 | +{t1 - t0:,.0f}円 | "
                  f"{t1 - t0 - kokunen:+,.0f}円".replace("-", "−") + " | — |")
        # 年金生活（65歳以上・単身）：公的年金等控除110万円、社会保険料（介護・国保）は年金の約8%
        for nenkin in (1_000_000, 2_000_000, 3_000_000):
            t0 = shotokuzei(nenkin - 1_100_000 - 480_000 - nenkin * 0.08)
            print(f"| 年金生活・単身 年金{nenkin // 10000}万円 | — | +{t0 * r:,.0f}円 | {t0 * r:+,.0f}円 | — |")
        print()


# ---------------------------------------------------------------------------
# 対照表
# ---------------------------------------------------------------------------
def table(cases):
    import subprocess as sp
    co, T, _ = _mods()
    out = os.path.join(HERE, "図")
    chrome = T.find_chrome()
    for case in cases:
        z, d = zaigen(case)
        T.SCEN = (("000", "000", "現行制度", None), (YOBI, "000", "税方式（一律7万円）", None))
        kk, dd = T.load(case)
        html = _page(case, d, z, kk, dd, T)
        name = f"対照表_{case}_税方式7万円"
        hp = os.path.join(out, name + ".html")
        open(hp, "w", encoding="utf-8").write(html)
        base = [chrome, "--no-sandbox", "--hide-scrollbars"]
        sp.run(base + ["--force-device-scale-factor=1.5", "--window-size=1240,1754",
                       f"--screenshot={os.path.join(out, name + '.png')}", "file://" + hp], check=True, capture_output=True)
        sp.run(base + ["--no-pdf-header-footer", f"--print-to-pdf={os.path.join(out, name + '.pdf')}",
                       "file://" + hp], check=True, capture_output=True)
        os.remove(hp)
        print("書き出し:", os.path.join(out, name + ".png"), "/ .pdf")


def _page(case, d, z, kk, dd, T):
    f1 = T.f1
    kiso = z["kiso"]
    cols = ("収入合計", "保険料収入", "運用収入", "国庫負担", "支出合計",
            "基礎年金拠出金", "独自給付", "収支差引残", "年度末積立金")
    trs = []
    for y in T.YEARS:
        vals = {}
        for yb in ("000", YOBI):
            t, r = dd[yb]["emp"][y], dd[yb]["rate"][y]
            zei = yb == YOBI and y >= START
            k = kiso if zei else r["代替率(基礎)"] * 100
            vals[yb] = ([t[c] for c in cols] + [t["年度末積立金"] * kk[2024] / kk[y], t["積立度合"]]
                        + [r["代替率(比例)"] * 100 + k, k, r["代替率(比例)"] * 100])
        for i, (yb, lab) in enumerate((("000", "現行制度"), (YOBI, "税方式（一律7万円）"))):
            cells = []
            for j, x in enumerate(vals[yb]):
                cls = (["d"] if yb != "000" and f1(x) != f1(vals["000"][j]) else []) + (["sep"] if j == len(cols) + 2 else [])
                cells.append(f'<td class="{" ".join(cls)}">{f1(x)}</td>')
            yc = f'<td class="y" rowspan="2">{y}</td>' if i == 0 else ""
            trs.append(f'<tr class="{"alt" if yb != "000" else "base"}">{yc}<td class="lab">{lab}</td>{"".join(cells)}</tr>')
    sk = "\n".join(
        f"<tr><td class='y'>{y}</td><td>{z[y]['getsu']:,.0f}</td><td>{z[y]['pop'] / 1e4:,.0f}</td>"
        f"<td>{f1(z[y]['cost'] / 1e12)}</td><td>{f1(z[y]['old'] / 1e12)}</td><td>{f1(z[y]['extra'] / 1e12)}</td>"
        f"<td>{f1(z[y]['shotoku'] / 1e12)}</td><td><b style='font-weight:bold'>{z[y]['ritu'] * 100:.0f}%</b></td></tr>"
        for y in YEARS)
    head_sk = """<tr><th>年度</th><th>給付<br>月額</th><th>65歳<br>以上</th><th>基礎年金<br>の費用</th><th>現行の<br>国庫負担</th>
<th>追加の<br>税</th><th>所得税収<br><small>見込み</small></th><th>所得税の<br>上乗せ率</th></tr>
<tr class="unit"><td>西暦</td><td>円</td><td>万人</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td></td></tr>"""
    co = __import__("compare_option")
    rb = dd["000"]["rate"][2120]
    rz = dd[YOBI]["rate"][2120]
    summ = f"""<table class="s"><tr><th></th><th>現行制度</th><th>税方式</th></tr>
<tr><td class='lab'>厚生年金保険料率</td><td>18.3%</td><td><b style="font-weight:bold">{18.3 - d * 100:.2f}%</b></td></tr>
<tr><td class='lab'>国民年金保険料</td><td>月17,510円<small>（2025年度）</small></td><td><b style="font-weight:bold">0円</b></td></tr>
<tr><td class='lab'>所得代替率（モデル世帯）</td><td>{rb['所得代替率'] * 100:.1f}%</td><td>{rz['代替率(比例)'] * 100 + kiso:.1f}%</td></tr>
<tr><td class='lab'>　うち基礎（夫婦）</td><td>{rb['代替率(基礎)'] * 100:.1f}%</td><td>{kiso:.1f}%</td></tr>
<tr><td class='lab'>　うち比例</td><td>{rb['代替率(比例)'] * 100:.1f}%</td><td>{rz['代替率(比例)'] * 100:.1f}%</td></tr>
<tr><td class='lab'>基礎年金だけの単身</td><td>{rb['代替率(基礎)'] * 50:.1f}%</td><td>{kiso / 2:.1f}%</td></tr></table>"""
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{T.CSS}
table.t td.lab {{ font-size: 12px; }} table.s td.lab {{ text-align: left; }}</style></head><body><div class="page">
<h1>財政見通し対照表<span class="stamp">非公式</span></h1>
<div class="sub">現行制度と、基礎年金を税方式にして65歳以上に一律月7万円を給付した場合（思考実験）の対照表</div>
<div class="cond">○ 人口：出生中位、死亡中位、外国人の入国超過数16.4万人　○ 経済：{T.CASES[case]}<br>
○ 税方式（一律7万円）：{START}年度から、65歳以上の全員に月7万円（{START}年度の額、以後は賃金に連動）を税で給付する。
障害・遺族の基礎年金は現行の水準のまま税で払う。国民年金保険料は廃止し、厚生年金は基礎年金拠出金を払わず基礎年金の国庫負担も受け取らない。
報酬比例は現行制度のままで、2120年度の積立度合が変わらないよう厚生年金保険料率を{d * 100:.2f}％pt下げる。
足りない税は所得税に一律の率で上乗せする（復興特別所得税と同じ方式）<br>
○ 網かけの行が税方式。<b style="font-weight:bold">太字</b>は現行制度と値が違うところ</div>
<h2>厚生年金（被用者年金4制度計）</h2>
<table class="t">{T.HEAD_EMP}
{chr(10).join(trs)}</table>
<h2>税方式の基礎年金（一般会計）</h2>
<div class="row"><table class="t" style="width:auto">{head_sk}
{sk}</table>
<div>{summ}
<div class="notes" style="max-width:470px">
基礎年金の費用は、65歳以上への一律給付と、現行水準の障害・遺族の基礎年金の合計。現行の国庫負担は、基礎年金の国庫負担と特別国庫負担の合計。
所得税収は2025年度決算（一般会計 25.3兆円、財務省）を標準報酬総額の伸びで延ばした見込みで、所得税の上乗せ率は「追加の税 ÷ 所得税収」。
国民年金勘定は保険料も拠出金もなくなり、積立金（2024年度末 約14兆円）が残る（表には入れていない）。</div></div></div>
<div class="notes">
（注1）厚生年金は被用者年金4制度（厚生年金・国共済・地共済・私学共済）の合計。税方式の行では「国庫負担」は経過的な国庫負担だけになり、「基礎年金拠出金」は0になる。<br>
（注2）所得代替率はモデル世帯の年金額の、その年度の現役男子の平均手取り（現行制度の値）に対する比率。税方式の基礎は夫婦2人分の一律給付で、保険料の引き下げと所得税の増税による手取りの変化は入れていない。<br>
（注3）現行制度の値は、厚生労働省「令和6(2024)年財政検証」詳細結果等の財政見通しと一致する（本リポジトリで全項目照合済み）。税方式は、公表された計算プログラムに独自のレバーを加えて計算した<b style="font-weight:bold">非公式の思考実験</b>で、厚生労働省の試算ではない。
</div></div></body></html>"""


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"] and len(a) >= 2:
        run(a[1:])
    elif a == ["report"]:
        report()
    elif a == ["kakei"]:
        kakei()
    elif a[:1] == ["table"] and len(a) >= 2:
        table(a[1:])
    else:
        sys.exit(__doc__)
