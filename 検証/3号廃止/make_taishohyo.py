#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""財政見通し対照表 — 厚生労働省の「財政見通し」表の形で、現行制度とシナリオを並べる

法改正の「新旧対照表」に倣い、現行制度と改正案（シナリオ）を同じ表に並べる。
厚生年金（被用者年金4制度計）と国民年金を1枚（A4縦）にし、各年度2行
（上が比べる相手＝現行制度、網かけがシナリオ）。シナリオの行で相手と値が
違うところは太字。列は公表の財政見通しと同じ（報酬比例には独自給付を含む）。

  図/対照表_{試算番号}_{予備番号}_{短い名前}.png / .pdf

試算番号（3003 など）と予備番号（run_sango.sh の一覧、501 など）の組で一意に
決まる。シナリオの説明文は下の SCENARIOS 台帳に置き、新しいシナリオは
台帳に1項目足せば同じ表が出る。

現行制度の値は公表の財政見通しと一致する（検証/オプション試算/ で全項目照合済み）。

HTML を作り、ヘッドレス Chromium で PNG と PDF にする。Chromium は環境変数
CHROME、PATH 上の chromium / google-chrome、PLAYWRIGHT_BROWSERS_PATH の順に探す。
見つからなければ HTML だけ残す。

使い方:
  python3 検証/3号廃止/make_taishohyo.py                       # 3003・3001 × 501
  python3 検証/3号廃止/make_taishohyo.py --case 3003 --yobi 501
"""
import argparse
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
# 対照表にするシナリオの台帳。キーは予備番号（⑤が読む番号）。
#   name   ファイル名に使う短い名前
#   label  表の行見出し
#   yobi4  ④の最終結果の予備番号（調整期間の一致では⑤と違う）
#   base   比べる相手（⑤の予備番号, ④の予備番号, 行見出し）。調整期間の一致の
#          シナリオは、現行＋一致（100/101）と比べるのが筋
#   waku   外枠番号（試算番号 → 外枠番号）。①から流し直すシナリオ（適用拡大など）は
#          通常試算の出力を上書きしないよう外枠番号を分けている。省略時は試算番号
#   yobi   シナリオの予備番号（省略時はキー）。キーを「相手-シナリオ」にすれば、
#          現行制度以外の2つのシナリオどうしも対照表にできる
#   base_waku  比べる相手の外枠番号（省略時は試算番号）
#   note3  表の下の注3（省略時は official フラグから決める）
SCENARIOS = {
    "501": dict(
        name="按分据置", label="按分据置型", yobi4="501", base=("000", "000", "現行制度"),
        title="第3号被保険者に保険料を課し基礎年金拠出金の按分は据え置いた場合（拠出金按分据置型）",
        desc="按分据置型：2027年度から第3号（20〜59歳）が第1号と同じ定額保険料を全員納付。"
             "基礎年金拠出金の按分（頭数）は現行のまま",
        note='<b style="font-weight:bold">按分据置型の基礎の「調整なし」は天井に当たった値</b>'
             "（マクロ経済スライドをかけなくても国民年金が余る）で、均衡解ではない。"
             "国民年金の積立度合が2120年度に1を大きく超えるのはそのため。",
    ),
    "040": dict(
        name="適用拡大860万", label="適用拡大", yobi4="040", base=("000", "000", "現行制度"),
        waku={"3003": "3403", "3001": "3401"},
        title="被用者保険の適用拡大（約860万人）を行った場合（厚生労働省のオプション試算）",
        desc="適用拡大：週10時間以上の全ての雇用者を被用者保険（厚生年金）の適用対象とする"
             "（約860万人）。①被保険者推計から流し直した（KAKUDAI=4）",
        note="適用拡大は厚生労働省自身のオプション試算で、この行は公表の財政見通し"
             "（詳細結果等2 No.13・No.15）と全項目一致する。",
        official=True,
    ),
    "501-040": dict(
        name="按分据置対適用拡大", label="適用拡大", yobi="040", yobi4="040",
        base=("501", "501", "按分据置型"), waku={"3003": "3403", "3001": "3401"},
        title="被用者保険の適用拡大（約860万人）",
        desc="按分据置型（上の行）：2027年度から第3号（20〜59歳）が第1号と同じ定額保険料を全員納付。"
             "基礎年金拠出金の按分（頭数）は現行のまま<br>"
             "○ 適用拡大（網かけの行）：週10時間以上の全ての雇用者を被用者保険（厚生年金）の"
             "適用対象とする（約860万人）。厚生労働省のオプション試算",
        note="どちらも現行制度より基礎年金の水準を上げるが、経路が逆である。按分据置型は"
             "第1号に保険料を払う人を足し、適用拡大は第1号から人を抜く。"
             "按分据置型の基礎の「調整なし」は天井に当たった値で、均衡解ではない。",
        note3="按分据置型は、公表された計算プログラムに独自のレバーを加えて計算した"
              '<b style="font-weight:bold">非公式の独自計算</b>で、厚生労働省の試算ではない。'
              "適用拡大は厚生労働省のオプション試算の財政見通しと一致する。",
    ),
    "541": dict(
        name="按分据置と適用拡大", label="按分据置＋適用拡大", yobi4="541", base=("000", "000", "現行制度"),
        waku={"3003": "3403", "3001": "3401"},
        title="被用者保険の適用拡大（約860万人）と拠出金按分据置型を組み合わせた場合",
        desc="按分据置＋適用拡大：適用拡大（約860万人、厚生労働省のオプション試算）を行ったうえで、"
             "2027年度から残った第3号（20〜59歳）が第1号と同じ定額保険料を全員納付。"
             "基礎年金拠出金の按分は据え置き",
        note="第1号・第3号のどちらから何人が適用拡大されるかは、①被保険者推計の適用拡大の前提"
             "（KAKUDAI=4）がそのまま決める。保険料を求める第3号は適用拡大の後に残った人数"
             "（2027年度末 339万人、現行 606万人）。"
             "基礎の「調整なし」は天井に当たった値で、均衡解ではない。",
    ),
    "501-541": dict(
        name="按分据置対按分据置と適用拡大", label="＋適用拡大", yobi="541", yobi4="541",
        base=("501", "501", "按分据置型"), waku={"3003": "3403", "3001": "3401"},
        title="拠出金按分据置型に被用者保険の適用拡大（約860万人）を重ねた場合",
        desc="按分据置型（上の行）：2027年度から第3号（20〜59歳）が第1号と同じ定額保険料を全員納付。"
             "基礎年金拠出金の按分（頭数）は現行のまま<br>"
             "○ ＋適用拡大（網かけの行）：そのうえで週10時間以上の全ての雇用者を被用者保険"
             "（厚生年金）の適用対象とする（約860万人）。保険料を求める第3号は適用拡大の後に残った人",
        note="どちらも基礎は「調整なし」の天井に当たっていて、均衡解ではない。"
             "天井の上では適用拡大を重ねても基礎年金は上がらず、差は報酬比例と積立金に出る。",
        note3="どちらの行も、公表された計算プログラムに独自のレバーを加えて計算した"
              '<b style="font-weight:bold">非公式の独自計算</b>で、厚生労働省の試算ではない。'
              "適用拡大の部分は厚生労働省のオプション試算の前提をそのまま使っている。",
    ),
    "601": dict(
        name="1号全員3号登録", label="1号→3号登録", yobi4="601", base=("000", "000", "現行制度"),
        title="第1号被保険者の全員を第3号として登録した場合（思考実験）",
        desc="1号→3号登録：2027年度から第1号被保険者の全員（2027年度 約1,220万〜1,240万人）を"
             "厚生年金の第3号として数える。保険料は誰も払わない。給付側は据え置き",
        note='<b style="font-weight:bold">国民年金の拠出金の按分がゼロになり、基礎年金の水準は'
             "国民年金勘定から切り離される。</b>基礎の「調整なし」は天井に当たった値で、"
             "基礎年金の費用は被用者年金と国庫が全部持つ（国民年金に残る拠出金は"
             "ほぼ同額の国庫負担が付いてくる通り抜け）。"
             "未納・免除の期間が第3号の納付済期間に変わる分の給付増は入っていない。",
    ),
}
SCEN = ()   # ((⑤の予備番号, ④の予備番号, 行見出し), …) の2つ組。main() が台帳から組む
CASES = {"3003": "過去30年投影ケース", "3001": "高成長実現ケース"}


def load(case):
    v = f"{case}-{case}-{case}-{case}"
    kk = co.read_kakaku(v, "000", BAS)
    out = {}
    for yb, y4, _lab, waku in SCEN:
        vv = f"{case}-{case}-{case}-{waku or case}"
        out[yb] = dict(emp=co.read_emp(vv, yb, SH), nat=co.read_nat(vv, y4, BAS),
                       rate=co.read_rate(vv, yb, SH),
                       run=_m.load_run(SUURI, case, yb, y4, waku))
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
        for yb, _y4, _l, _w in SCEN:
            t = d[yb][kind][y]
            v = [t[c] for c in cols] + [t["年度末積立金"] * kk[2024] / kk[y], t.get("積立度合", float("nan"))]
            if kind == "emp":
                r = d[yb]["rate"][y]
                v += [r["所得代替率"] * 100, r["代替率(基礎)"] * 100, r["代替率(比例)"] * 100]
            vals[yb] = v
        base = SCEN[0][0]
        for i, (yb, _y4, lab, _w) in enumerate(SCEN):
            cells = []
            for j, x in enumerate(vals[yb]):
                s = f1(x)
                diff = yb != base and f1(x) != f1(vals[base][j])
                cls = []
                if diff: cls.append("d")
                if j == len(cols) + 2 or (kind == "emp" and j == len(cols) + 2): cls.append("sep")
                cells.append(f'<td class="{" ".join(cls)}">{s}</td>')
            yc = f'<td class="y" rowspan="2">{y}</td>' if i == 0 else ""
            out.append(f'<tr class="{"alt" if yb != base else "base"}">{yc}<td class="lab">{lab}</td>{"".join(cells)}</tr>')
    return "\n".join(out)


def summary(d):
    trs = []
    base = SCEN[0][0]
    for yb, _y4, lab, _w in SCEN:
        r = d[yb]["rate"][2120]; run = d[yb]["run"]
        ke = run["kiso_end"]; he = run["hirei_end"]
        kes = "調整なし" if ke <= 2024 else (f"{ke}（均衡せず）" if ke >= 2120 else f"{ke}")
        hes = "調整なし" if he <= 2024 else f"{he}"
        trs.append(f"<tr class='{'alt' if yb != base else 'base'}'><td class='lab'>{lab}</td>"
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


def note3_head():
    if SCEN[0][0] == "000":
        return ("現行制度の値は、厚生労働省「令和6(2024)年財政検証」詳細結果等の財政見通しと"
                "一致する（本リポジトリで全項目照合済み）。")
    return ""


def note3(spec):
    if spec.get("note3"):
        return spec["note3"]
    if spec.get("official"):
        return (f'{spec["label"]}の行も厚生労働省のオプション試算の財政見通しと一致する。'
                "表の組み方は本リポジトリによるもので、厚生労働省の資料ではない。")
    return (f'{spec["label"]}は、公表された計算プログラムに独自のレバーを加えて計算した'
            '<b style="font-weight:bold">非公式の独自計算</b>で、厚生労働省の試算ではない。')


def page(case, spec):
    kk, d = load(case)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page">
<h1>財政見通し対照表<span class="stamp">非公式</span></h1>
<div class="sub">{SCEN[0][2]}と、{spec["title"]}の対照表</div>
<div class="cond">○ 人口：出生中位、死亡中位、外国人の入国超過数16.4万人　○ 経済：{CASES[case]}<br>
○ {spec["desc"]}<br>
○ 網かけの行が{spec["label"]}。<b style="font-weight:bold">太字</b>は{SCEN[0][2]}と値が違うところ</div>
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
{spec["note"]}<br><br>
年度末積立金の「2024年度価格」は賃金上昇率で割り戻したもので、運用で膨らんだ分を含む（現在価値ではない）。</div></div></div>
<div class="notes">
（注1）厚生年金は、公表の「厚生年金の財政見通し」と同じく被用者年金4制度（厚生年金・国共済・地共済・私学共済）の合計。「報酬比例」には厚生年金の独自給付（定額・加給・加算）を含む。<br>
（注2）「積立度合」は前年度末積立金の当年度の支出合計に対する倍率。所得代替率はモデル世帯の年金額のその年度の現役男子の平均手取りに対する比率（基礎は夫婦2人分）。<br>
（注3）{note3_head()}{note3(spec)}
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
    global SCEN
    ap = argparse.ArgumentParser(description="財政見通し対照表を作る")
    ap.add_argument("--case", nargs="+", default=["3003", "3001"], help="試算番号（既定 3003 3001）")
    ap.add_argument("--yobi", nargs="+", default=["501"], help="シナリオの予備番号（既定 501）")
    a = ap.parse_args()
    outdir = os.path.join(HERE, "図")
    chrome = find_chrome()
    tmp = tempfile.mkdtemp()
    for yobi in a.yobi:
        if yobi not in SCENARIOS:
            sys.exit(f"予備番号 {yobi} は SCENARIOS 台帳にありません（{', '.join(SCENARIOS)}）")
        spec = SCENARIOS[yobi]
        for case in a.case:
            SCEN = (spec["base"] + (spec.get("base_waku", {}).get(case),),
                    (spec.get("yobi", yobi), spec["yobi4"], spec["label"],
                     spec.get("waku", {}).get(case)))
            name = f"対照表_{case}_{yobi}_{spec['name']}"
            html_path = os.path.join(tmp if chrome else outdir, name + ".html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page(case, spec))
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
