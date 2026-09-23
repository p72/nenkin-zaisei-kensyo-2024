#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""厚生労働省の「財政見通し」表の形で、現行制度と3号廃止・拠出金按分据置型を並べる

  図/財政見通し_按分据置_3003.png / .pdf   過去30年投影ケース
  図/財政見通し_按分据置_3001.png / .pdf   高成長実現ケース

厚生年金（被用者年金4制度計）と国民年金を1枚（A4縦）に並べ、各年度2行
（上が現行制度、網かけが按分据置型）にする。按分据置型の行で現行と値が違う
ところは太字。列は公表の財政見通しと同じ（報酬比例には独自給付を含む）。

現行制度の値は公表の財政見通しと一致する（検証/オプション試算/ で全項目照合済み）。

HTML を作り、ヘッドレス Chromium で PNG と PDF にする。Chromium は環境変数
CHROME、PATH 上の chromium / google-chrome、PLAYWRIGHT_BROWSERS_PATH の順に探す。
見つからなければ HTML だけ残す。

使い方: python3 検証/3号廃止/make_zaisei_hyou_sango.py
"""
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
import compare_option as co  # noqa: E402

_s = importlib.util.spec_from_file_location("sango", os.path.join(HERE, "analyze_sango.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
SH = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi")
BAS = os.path.join(SUURI, "bas", "rslt")
YEARS = (2024, 2027, 2030, 2035, 2040, 2050, 2060, 2080, 2100, 2120)
SCEN = (("000", "現行制度"), ("501", "按分据置型"))
CASES = {"3003": "過去30年投影ケース", "3001": "高成長実現ケース"}


def load(case):
    v = f"{case}-{case}-{case}-{case}"
    kk = co.read_kakaku(v, "000", BAS)
    out = {}
    for yb, _ in SCEN:
        out[yb] = dict(emp=co.read_emp(v, yb, SH), nat=co.read_nat(v, yb, BAS),
                       rate=co.read_rate(v, yb, SH), run=_m.load_run(SUURI, case, yb, yb))
    return kk, out


def f1(x):
    return f"{x:,.1f}".replace(",", "") if abs(x) < 10000 else f"{x:,.1f}".replace(",", "")


def rows(kind, kk, d):
    cols_emp = ("収入合計", "保険料収入", "運用収入", "国庫負担", "支出合計",
                "基礎年金拠出金", "独自給付", "収支差引残", "年度末積立金")
    cols_nat = ("収入合計", "保険料収入", "運用収入", "国庫負担", "支出合計",
                "基礎年金拠出金", "収支差引残", "年度末積立金")
    cols = cols_emp if kind == "emp" else cols_nat
    out = []
    for y in YEARS:
        vals = {}
        for yb, _ in SCEN:
            t = d[yb][kind][y]
            v = [t[c] for c in cols] + [t["年度末積立金"] * kk[2024] / kk[y], t.get("積立度合", float("nan"))]
            if kind == "emp":
                r = d[yb]["rate"][y]
                v += [r["所得代替率"] * 100, r["代替率(基礎)"] * 100, r["代替率(比例)"] * 100]
            vals[yb] = v
        for i, (yb, lab) in enumerate(SCEN):
            cells = []
            for j, x in enumerate(vals[yb]):
                s = f1(x)
                diff = yb != "000" and f1(x) != f1(vals["000"][j])
                cls = []
                if diff: cls.append("d")
                if j == len(cols) + 2 or (kind == "emp" and j == len(cols) + 2): cls.append("sep")
                cells.append(f'<td class="{" ".join(cls)}">{s}</td>')
            yc = f'<td class="y" rowspan="2">{y}</td>' if i == 0 else ""
            out.append(f'<tr class="{"alt" if yb != "000" else "base"}">{yc}<td class="lab">{lab}</td>{"".join(cells)}</tr>')
    return "\n".join(out)


def summary(d):
    trs = []
    for yb, lab in SCEN:
        r = d[yb]["rate"][2120]; run = d[yb]["run"]
        ke = run["kiso_end"]; he = run["hirei_end"]
        kes = "調整なし" if ke <= 2024 else (f"{ke}（均衡せず）" if ke >= 2120 else f"{ke}")
        hes = "調整なし" if he <= 2024 else f"{he}"
        trs.append(f"<tr class='{'alt' if yb!='000' else 'base'}'><td class='lab'>{lab}</td>"
                   f"<td>{r['所得代替率']*100:.1f}%</td><td>{r['代替率(比例)']*100:.1f}%</td><td>{hes}</td>"
                   f"<td>{r['代替率(基礎)']*100:.1f}%</td><td>{kes}</td></tr>")
    return "\n".join(trs)


HEAD_EMP = """<tr><th rowspan="2">年度</th><th rowspan="2"></th>
<th colspan="4" class="grp">収入</th><th colspan="3" class="grp">支出</th>
<th rowspan="2">収支<br>差引残</th><th rowspan="2">年度末<br>積立金</th><th rowspan="2">年度末<br>積立金<br><small>2024年度価格</small></th><th rowspan="2">積立<br>度合</th>
<th colspan="3" class="grp sep">（参考）所得代替率</th></tr>
<tr><th>合計</th><th>保険料<br>収入</th><th>運用<br>収入</th><th>国庫<br>負担</th><th>合計</th><th>基礎年金<br>拠出金</th><th>報酬<br>比例</th>
<th class="sep">計</th><th>基礎</th><th>比例</th></tr>
<tr class="unit"><td>西暦</td><td></td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td></td><td class="sep">%</td><td>%</td><td>%</td></tr>"""
HEAD_NAT = """<tr><th rowspan="2">年度</th><th rowspan="2"></th>
<th colspan="4" class="grp">収入</th><th colspan="2" class="grp">支出</th>
<th rowspan="2">収支<br>差引残</th><th rowspan="2">年度末<br>積立金</th><th rowspan="2">年度末<br>積立金<br><small>2024年度価格</small></th><th rowspan="2">積立<br>度合</th></tr>
<tr><th>合計</th><th>保険料<br>収入</th><th>運用<br>収入</th><th>国庫<br>負担</th><th>合計</th><th>基礎年金<br>拠出金</th></tr>
<tr class="unit"><td>西暦</td><td></td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td>兆円</td><td></td></tr>"""

CSS = """
@page { size: A4 portrait; margin: 0; }
@media print { .page { zoom: 0.64; } }
body { margin: 0; background: #fff; color: #0b0b0b; font-family: "IPAPGothic","IPAGothic",sans-serif; }
.page { width: 1240px; padding: 34px 40px 26px; box-sizing: border-box; }
h1 { font-size: 28px; margin: 0 0 4px; text-align: center; letter-spacing: .12em; }
.sub { text-align: center; font-size: 16px; margin-bottom: 16px; color: #333; }
.cond { font-size: 15px; line-height: 1.65; margin: 0 0 12px; }
.cond b { font-weight: normal; }
h2 { font-size: 19px; margin: 20px 0 8px; }
table.t { border-collapse: collapse; width: 100%; font-size: 15px; }
table.t th, table.t td { border: 1px solid #888; padding: 4px 6px; }
table.t th { background: #f2f2f0; font-weight: normal; line-height: 1.2; white-space: nowrap; }
table.t td { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.t td.y { text-align: center; }
table.t td.lab { text-align: left; font-size: 13px; color: #333; }
table.t tr.unit td { font-size: 10.5px; color: #555; text-align: right; border-top: 1.5px solid #333; }
table.t tr.alt td { background: #e3f5ee; }
table.t tr.alt td.y { background: #fff; }
table.t td.d { font-weight: bold; }
table.t .sep { border-left: 2px solid #333; }
table.t tr.base td { border-top: 1.5px solid #333; }
.row { display: flex; gap: 22px; align-items: flex-start; margin-top: 4px; }
table.s { border-collapse: collapse; font-size: 14px; }
table.s th, table.s td { border: 1px solid #888; padding: 4px 7px; text-align: center; white-space: nowrap; }
table.s th { background: #f2f2f0; font-weight: normal; }
table.s tr.alt td { background: #e3f5ee; }
.notes { font-size: 13px; color: #444; line-height: 1.6; margin-top: 12px; }
.stamp { display: inline-block; border: 1.5px solid #b00; color: #b00; padding: 1px 8px; font-size: 13px; margin-left: 10px; }
"""


def page(case):
    kk, d = load(case)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page">
<h1>厚生年金・国民年金の財政見通し<span class="stamp">非公式</span></h1>
<div class="sub">現行制度と、第3号被保険者に保険料を課し基礎年金拠出金の按分は据え置いた場合（拠出金按分据置型）の比較</div>
<div class="cond">○ 人口：出生中位、死亡中位、外国人の入国超過数16.4万人　○ 経済：{CASES[case]}<br>
○ 按分据置型：2027年度から第3号（20〜59歳）が第1号と同じ定額保険料を全員納付。基礎年金拠出金の按分（頭数）は現行のまま<br>
○ 網かけの行が按分据置型。<b style="font-weight:bold">太字</b>は現行制度と値が違うところ</div>
<h2>厚生年金（被用者年金4制度計）</h2>
<table class="t">{HEAD_EMP}
{rows("emp", kk, d)}</table>
<h2>国民年金</h2>
<div class="row"><table class="t" style="width:auto">{HEAD_NAT}
{rows("nat", kk, d)}</table>
<div><table class="s"><tr><th rowspan="2"></th><th rowspan="2">所得代替率<br><small>調整終了後</small></th><th colspan="2">比例</th><th colspan="2">基礎</th></tr>
<tr><th>水準</th><th>調整<br>終了年度</th><th>水準</th><th>調整<br>終了年度</th></tr>
{summary(d)}</table>
<div class="notes" style="max-width:400px">
<b style="font-weight:bold">按分据置型の基礎の「調整なし」は天井に当たった値</b>（マクロ経済スライドをかけなくても国民年金が余る）で、均衡解ではない。国民年金の積立度合が2120年度に1を大きく超えるのはそのため。<br><br>
年度末積立金の「2024年度価格」は賃金上昇率で割り戻したもので、運用で膨らんだ分を含む（現在価値ではない）。</div></div></div>
<div class="notes">
（注1）厚生年金は、公表の「厚生年金の財政見通し」と同じく被用者年金4制度（厚生年金・国共済・地共済・私学共済）の合計。「報酬比例」には厚生年金の独自給付（定額・加給・加算）を含む。<br>
（注2）「積立度合」は前年度末積立金の当年度の支出合計に対する倍率。所得代替率はモデル世帯の年金額のその年度の現役男子の平均手取りに対する比率（基礎は夫婦2人分）。<br>
（注3）現行制度の値は、厚生労働省「令和6(2024)年財政検証」詳細結果等の財政見通しと一致する（本リポジトリで全項目照合済み）。按分据置型は、公表された計算プログラムに独自のレバーを加えて計算した<b style="font-weight:bold">非公式の独自計算</b>で、厚生労働省の試算ではない。
</div></div></body></html>"""


def find_chrome():
    cands = [os.environ.get("CHROME")]
    cands += [shutil.which(n) for n in ("chromium", "chromium-browser", "google-chrome", "headless_shell")]
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if pw:
        cands += sorted(glob.glob(os.path.join(pw, "chromium_headless_shell-*", "chrome-linux", "headless_shell")))
        cands += sorted(glob.glob(os.path.join(pw, "chromium-*", "chrome-linux", "chrome")))
    return next((c for c in cands if c and os.path.exists(c)), None)


def main():
    outdir = os.path.join(HERE, "図")
    chrome = find_chrome()
    tmp = tempfile.mkdtemp()
    for case in ("3003", "3001"):
        name = f"財政見通し_按分据置_{case}"
        html_path = os.path.join(tmp if chrome else outdir, name + ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page(case))
        if not chrome:
            print("Chromium が見つからないので HTML だけ書いた:", html_path)
            continue
        url = "file://" + html_path
        base = [chrome, "--no-sandbox", "--hide-scrollbars"]
        subprocess.run(base + ["--force-device-scale-factor=1.5", "--window-size=1240,1754",
                               f"--screenshot={os.path.join(outdir, name + '.png')}", url],
                       check=True, capture_output=True)
        subprocess.run(base + ["--no-pdf-header-footer",
                               f"--print-to-pdf={os.path.join(outdir, name + '.pdf')}", url],
                       check=True, capture_output=True)
        print("書き出し:", os.path.join(outdir, name + ".png"), "/ .pdf")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
