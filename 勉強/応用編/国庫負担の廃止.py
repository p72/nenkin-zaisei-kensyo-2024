#!/usr/bin/env python3
"""厚生年金への国庫負担をなくしたらどうなるかの思考実験（非公式）。

「厚生年金の国庫負担をなくしたら」を再現するための道具。検証/実行/run_pipeline.sh の
KOKKO レバー（検証/実行/patches/kokko-cut.patch）で④⑤を流し、結果を集計する。

  予備番号 701  2027年度から国庫負担なし。報酬比例を一律に削って2120年度に均衡させる
  予備番号 702  2027年度から国庫負担なし。マクロ経済スライドだけで調整する（均衡しない）

使い方（リポジトリの直下で）
  python3 勉強/応用編/国庫負担の廃止.py run 3003       # 過去30年投影で 701・702 を流す
  python3 勉強/応用編/国庫負担の廃止.py run 3001       # 高成長実現で 701・702 を流す
  python3 勉強/応用編/国庫負担の廃止.py report         # 国の節約・給付の減・スライドだけの場合
  python3 勉強/応用編/国庫負担の廃止.py table 3003 3001  # 財政見通し対照表（勉強/応用編/図/）
  python3 勉強/応用編/国庫負担の廃止.py ichiritsu        # 浮いた財源を65歳以上に一律給付した場合の額
  python3 勉強/応用編/国庫負担の廃止.py ichiritsu-table 3003 3001  # その対照表

前提：通常試算（予備番号 000）が流してあること。①〜③は流し直さない。
"""
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
SH = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi")
LOG = os.path.join(SUURI, "emp", "log")
START = 2027
RUNS = (("701", "0"), ("702", "1"))     # (予備番号, KOKKO_MODE)
ARGS = {"3003": ["1", "1", "0", "2"], "3001": []}   # 過去30年投影は労働参加漸進
CASES = (("3003", "過去30年投影"), ("3001", "高成長実現"))


def run(case):
    for i, (yobi, mode) in enumerate(RUNS):
        env = dict(os.environ, KOKKO=str(START), KOKKO_MODE=mode, YOBI=yobi, STEPS="45")
        if i > 0:
            env["SKIP_BUILD"] = "1"         # 1回目でパッチ済みのビルドを作る
        subprocess.run([os.path.join(ROOT, "検証", "実行", "run_pipeline.sh"), case] + ARGS[case],
                       env=env, check=True)
        # 年齢別の詳細（1本130MB超）は使わないので消す
        for p in glob.glob(os.path.join(SH, f"90nenbe.{case}-*-1120-{yobi}e_*")):
            os.remove(p)


def _modules():
    sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
    sys.path.insert(0, os.path.join(ROOT, "検証", "3号廃止"))
    import compare_option as co
    import make_taishohyo as T
    return co, T


def detail(case, yobi):
    """厚生年金（4制度計）の国庫負担と、国が払わずに済んだ額（兆円）。"""
    co, _ = _modules()
    v = f"{case}-{case}-{case}-{case}"
    p = co.find_one(f"01shushi.{v}-1120-{yobi}*_08tou.csv", SH)
    out = {}
    for y, r in co.read_block(p, "収支見通し【スライド調整後】", 1, 2000).items():
        g = lambda n: float(r[n]) * co.OKU                                  # noqa: E731
        out[y] = dict(kokko=g("国庫負担"),
                      naiyaku=g("(再)国庫基礎") + g("(再)国庫経過比例")
                      + g("(再)国庫経過定額") + g("(再)国庫かさ上げ"),
                      kyufu=g("独自給付"), tumi=g("年度末積立金"))
    return out


def discount(case):
    """経済前提の名目運用利回りで2024年度末に割り引く係数。"""
    rows = {int(float(l.split(",")[0])) + 2000: [float(x) for x in l.split(",")]
            for l in open(os.path.join(SUURI, "emp", "data", "u-rev", "econ", f"econ-{case}.csv"))}
    D, d = {2024: 1.0}, 1.0
    for y in range(2025, 2121):
        r = rows.get(y, rows[max(rows)])
        d /= (1 + r[1] / 100) * (1 + r[6] / 100)
        D[y] = d
    return D


def ichiritsu(case):
    """⑤のログから、報酬比例を何倍にしたかを読む。"""
    p = os.path.join(LOG, f"emp-{case}-{case}-{case}-{case}-1120-701.log")
    m = re.search(r"一律 ([0-9.]+) 倍", open(p, encoding="utf-8", errors="replace").read())
    return float(m.group(1))


def report():
    co, _ = _modules()
    print("| ケース | 報酬比例 | 所得代替率 | うち比例 | 国の節約 2027〜2100 名目 | 同 現在価値 "
          "| 国の節約 2027〜2120 現在価値 | 厚生年金の給付の減 2027〜2120 現在価値 |")
    print("|---|---|---|---|---|---|---|---|")
    for case, cname in CASES:
        v = f"{case}-{case}-{case}-{case}"
        b, c, D = detail(case, "000"), detail(case, "701"), discount(case)
        rb, rc = co.read_rate(v, "000", SH), co.read_rate(v, "701", SH)
        m = ichiritsu(case)
        nom = sum(c[y]["naiyaku"] for y in range(START, 2101))
        pv = sum(c[y]["naiyaku"] * D[y] for y in range(START, 2101))
        pv2 = sum(c[y]["naiyaku"] * D[y] for y in range(START, 2121))
        cut = sum((b[y]["kyufu"] - c[y]["kyufu"]) * D[y] for y in range(START, 2121))
        print(f"| {cname} | 一律 {(1 - m) * 100:.1f}%減 "
              f"| {rb[2120]['所得代替率']*100:.1f}% → {rc[2120]['所得代替率']*100:.1f}% "
              f"| {rb[2120]['代替率(比例)']*100:.1f}% → {rc[2120]['代替率(比例)']*100:.1f}% "
              f"| {nom:,.0f}兆円 | {pv:,.0f}兆円 | {pv2:,.0f}兆円 | {cut:,.0f}兆円 |")
    print()
    print("マクロ経済スライドだけで調整した場合（702）")
    for case, cname in CASES:
        v = f"{case}-{case}-{case}-{case}"
        e = co.read_emp(v, "702", SH)
        r = co.read_rate(v, "702", SH)
        neg = next((y for y in range(START, 2121) if e[y]["年度末積立金"] < 0), None)
        log = open(os.path.join(LOG, f"emp-{v}-1120-702.log"), encoding="utf-8", errors="replace").read()
        kin = re.search(r"調整最終年度 *厚年： *(\d+|-)", log).group(1)
        owari = "均衡せず（2120年度まで調整しても足りない）" if kin == "-" else f"{2000 + int(kin)}年度"
        print(f"  {cname}: 報酬比例の調整終了 {owari}、"
              f"積立金がマイナスになる年度 {neg or 'なし'}、"
              f"2120年度末の積立金 {e[2120]['年度末積立金']:,.0f}兆円、"
              f"所得代替率 {r[2120]['所得代替率']*100:.1f}%（うち比例 {r[2120]['代替率(比例)']*100:.1f}%）")


WHY = {
    "3003": "失う収入はマクロ経済スライドを2120年度まで続けても埋まらないので、",
    "3001": "マクロ経済スライドだけでも2061年度まで調整すれば均衡する（報酬比例16.2%）が、"
            "過去30年投影とそろえて、",
}

NOTES = {
    "3003": "過去30年投影ケースでは、国が払わずに済んだ額（現在価値）と厚生年金の給付の減（同）が"
            "ほぼ同じになる。国の財政が良くなった分は、厚生年金の受給者の給付の減でまかなわれている。",
    "3001": "高成長実現ケースでは、もともと使い切れずに余る積立金があるので、"
            "報酬比例の減らし方は過去30年投影より小さい。",
}


def table(cases):
    """財政見通し対照表を 勉強/応用編/図/ に書く（make_taishohyo の台帳に一時的に足す）。"""
    _, T = _modules()
    out = os.path.join(HERE, "図")
    os.makedirs(out, exist_ok=True)
    for case in cases:
        m = ichiritsu(case)
        T.SCENARIOS["701"] = dict(
            name="国庫負担廃止", label="国庫負担なし", yobi4="701", base=("000", "000", "現行制度"),
            title="厚生年金への国庫負担をなくした場合（思考実験）",
            desc=f"国庫負担なし：{START}年度から、厚生年金（被用者年金4制度）への国庫負担をなくす。"
                 "基礎年金拠出金は全額を厚生年金が払う。" + WHY[case]
                 + f"{START}年度から報酬比例の給付（既に受け取っている人を含む）を一律に"
                 f"{(1 - m) * 100:.1f}%減らして2120年度に均衡させた",
            note=f'<b style="font-weight:bold">報酬比例は{START}年度に一律{(1 - m) * 100:.1f}%減。</b>'
                 "国民年金（基礎年金の水準）は動かない。厚生年金の「国庫負担」の欄は0になる。"
                 + NOTES[case],
            hirei_end={case: f"{START}<br><small>一律{(1 - m) * 100:.1f}%減</small>"},
            note3="国庫負担なしは、公表された計算プログラムに独自のレバーを加えて計算した"
                  '<b style="font-weight:bold">非公式の思考実験</b>で、厚生労働省の試算ではない。')
        sys.argv = ["make_taishohyo.py", "--case", case, "--yobi", "701"]
        T.main()
        for ext in ("png", "pdf"):
            src = os.path.join(T.HERE, "図", f"対照表_{case}_701_国庫負担廃止.{ext}")
            shutil.move(src, os.path.join(out, f"対照表_{case}_国庫負担廃止.{ext}"))
        print("移した:", os.path.join(out, f"対照表_{case}_国庫負担廃止.png"))


# ---------------------------------------------------------------------------
# 一律給付：国が払わずに済んだ額を、その年度の65歳以上の全員に同じ額で配る
# ---------------------------------------------------------------------------
def pop65(case):
    """①被保険者推計が使う人口（男女計）のうち65歳以上（100歳以上を含む）。人。"""
    import csv
    p = os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", f"rslt{case}", f"waku{case}-20.csv")
    L = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    i = L[1].index("65")
    return {int(r[2]): sum(float(x) for x in r[i:]) for r in L[2:] if len(r) > 5 and r[1] == "0"}


def tedori(case, yobi):
    """⑤ 03summary の現役男子の平均手取り（月額・円）。名目と物価で2024年度に割り戻した値。"""
    co, _ = _modules()
    p = co.find_one(f"03summary.{case}-{case}-{case}-{case}-1120-{yobi}*_08sum.csv", SH)
    L = co.lines_of(p)
    hi = [i for i, l in enumerate(L) if l.startswith("年度,物価")][0]
    cols = [x.strip() for x in L[hi].split(",")]
    out = {}
    for l in L[hi + 1:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].isdigit():
            if out:
                break
            continue
        out[int(f[0]) + 2000] = (float(f[cols.index("可処分所得")]),
                                 float(f[cols.index("可処分所得（物価割り戻し）")]))
    return out


def shinkyufu(case):
    """年度ごとの一律給付。月額（名目・物価で2024年度に割り戻し）と手取りに対する割合。"""
    c, P, kw = detail(case, "701"), pop65(case), tedori(case, "701")
    out = {}
    for y in range(START, 2121):
        m = c[y]["naiyaku"] * 1e12 / P[y] / 12
        out[y] = dict(zaigen=c[y]["naiyaku"], pop=P[y], getsu=m,
                      getsu_r=m * kw[y][1] / kw[y][0], wari=m / kw[y][0] * 100)
    return out


def report_shinkyufu():
    co, _ = _modules()
    for case, cname in CASES:
        v = f"{case}-{case}-{case}-{case}"
        s, rb, rc = shinkyufu(case), co.read_rate(v, "000", SH), co.read_rate(v, "701", SH)
        print(f"{cname}")
        print("| 年度 | 財源（国が払わずに済んだ額） | 65歳以上 | 一律給付（月額） | 物価で2024年度に割り戻し "
              "| 手取りに対する割合 | モデル世帯の所得代替率 現行 → 国庫負担なし → ＋一律給付 |")
        print("|---|---|---|---|---|---|---|")
        for y in YEARS_S:
            t = s[y]
            print(f"| {y} | {t['zaigen']:.1f}兆円 | {t['pop'] / 1e4:,.0f}万人 | {t['getsu']:,.0f}円 "
                  f"| {t['getsu_r']:,.0f}円 | {t['wari']:.2f}% "
                  f"| {rb[y]['所得代替率']*100:.1f}% → {rc[y]['所得代替率']*100:.1f}% → "
                  f"{rc[y]['所得代替率']*100 + 2 * t['wari']:.1f}% |")
        print()


YEARS_S = (2027, 2030, 2035, 2040, 2050, 2060, 2080, 2100, 2120)


def table_shinkyufu(cases):
    """国庫負担なし＋一律給付の対照表を 勉強/応用編/図/ に書く。
    厚生年金の表は国庫負担なしの対照表と同じで、所得代替率に一律給付の列を足す。
    国民年金は現行制度と同じなので、代わりに一律給付の表を置く。"""
    co, T = _modules()
    out = os.path.join(HERE, "図")
    os.makedirs(out, exist_ok=True)
    chrome = T.find_chrome()
    for case in cases:
        v = f"{case}-{case}-{case}-{case}"
        m = ichiritsu(case)
        T.SCEN = (("000", "000", "現行制度", None), ("701", "701", "国庫負担なし＋一律給付", None))
        kk, d = T.load(case)
        s = shinkyufu(case)
        html = _page_shinkyufu(case, m, kk, d, s, T)
        name = f"対照表_{case}_国庫負担廃止_一律給付"
        hp = os.path.join(out, name + ".html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(html)
        if not chrome:
            print("Chromium が見つからないので HTML だけ書いた:", hp)
            continue
        base = [chrome, "--no-sandbox", "--hide-scrollbars"]
        subprocess.run(base + ["--force-device-scale-factor=1.5", "--window-size=1240,1754",
                               f"--screenshot={os.path.join(out, name + '.png')}", "file://" + hp],
                       check=True, capture_output=True)
        subprocess.run(base + ["--no-pdf-header-footer",
                               f"--print-to-pdf={os.path.join(out, name + '.pdf')}", "file://" + hp],
                       check=True, capture_output=True)
        os.remove(hp)
        print("書き出し:", os.path.join(out, name + ".png"), "/ .pdf")


def _page_shinkyufu(case, m, kk, d, s, T):
    f1 = T.f1
    cols = ("収入合計", "保険料収入", "運用収入", "国庫負担", "支出合計",
            "基礎年金拠出金", "独自給付", "収支差引残", "年度末積立金")
    trs = []
    for y in T.YEARS:
        vals = {}
        for yb in ("000", "701"):
            t = d[yb]["emp"][y]
            r = d[yb]["rate"][y]
            w = s[y]["wari"] if (yb == "701" and y >= START) else 0.0
            vals[yb] = ([t[c] for c in cols] + [t["年度末積立金"] * kk[2024] / kk[y], t["積立度合"]]
                        + [r["所得代替率"] * 100 + 2 * w, r["代替率(基礎)"] * 100,
                           r["代替率(比例)"] * 100, 2 * w])
        for i, (yb, lab) in enumerate((("000", "現行制度"), ("701", "国庫負担なし＋一律給付"))):
            cells = []
            for j, x in enumerate(vals[yb]):
                cls = []
                if yb != "000" and f1(x) != f1(vals["000"][j]):
                    cls.append("d")
                if j == len(cols) + 2:
                    cls.append("sep")
                cells.append(f'<td class="{" ".join(cls)}">{f1(x)}</td>')
            yc = f'<td class="y" rowspan="2">{y}</td>' if i == 0 else ""
            trs.append(f'<tr class="{"alt" if yb != "000" else "base"}">{yc}<td class="lab">{lab}</td>{"".join(cells)}</tr>')
    head_emp = T.HEAD_EMP.replace(
        '<th colspan="3" class="grp sep">（参考）所得代替率</th>',
        '<th colspan="4" class="grp sep">（参考）所得代替率</th>').replace(
        '<th class="sep">計</th><th>基礎</th><th>比例</th>',
        '<th class="sep">計</th><th>基礎</th><th>比例</th><th>一律<br>給付</th>').replace(
        '<td class="sep">%</td><td>%</td><td>%</td>',
        '<td class="sep">%</td><td>%</td><td>%</td><td>%</td>')

    sk = []
    for y in YEARS_S:
        t = s[y]
        sk.append(f"<tr><td class='y'>{y}</td><td>{f1(t['zaigen'])}</td><td>{t['pop'] / 1e4:,.0f}</td>"
                  f"<td>{t['getsu']:,.0f}</td><td>{t['getsu_r']:,.0f}</td><td>{t['wari']:.2f}</td></tr>")
    head_sk = """<tr><th>年度</th><th>財源<br><small>国が払わずに<br>済んだ額</small></th><th>65歳<br>以上</th>
<th>一律給付<br>月額</th><th>同<br><small>物価で2024年度<br>に割り戻し</small></th><th>現役の<br>手取りに<br>対する割合</th></tr>
<tr class="unit"><td>西暦</td><td>兆円</td><td>万人</td><td>円</td><td>円</td><td>%</td></tr>"""

    rb, rc = d["000"]["rate"][2120], d["701"]["rate"][2120]
    w = s[2120]["wari"]
    hk_b, hk_c = rb["代替率(比例)"] * 100, rc["代替率(比例)"] * 100
    ks_b, ks_c = rb["代替率(基礎)"] * 100, rc["代替率(基礎)"] * 100
    sm = [("現行制度", rb["所得代替率"] * 100, hk_b, ks_b, 0.0, ks_b / 2, hk_b + ks_b / 2, "base"),
          ("国庫負担なし", rc["所得代替率"] * 100, hk_c, ks_c, 0.0, ks_c / 2, hk_c + ks_c / 2, "base"),
          ("＋一律給付", rc["所得代替率"] * 100 + 2 * w, hk_c, ks_c, 2 * w, ks_c / 2 + w,
           hk_c + ks_c / 2 + w, "alt")]
    smr = "\n".join(f"<tr class='{c}'><td class='lab'>{lab}</td><td>{a:.1f}%</td><td>{h:.1f}%</td><td>{k:.1f}%</td>"
                    f"<td>{g:.1f}%</td><td>{k1:.1f}%</td><td>{h1:.1f}%</td></tr>"
                    for lab, a, h, k, g, k1, h1, c in sm)
    cut = (1 - m) * 100
    even = w / (cut / 100) / hk_b * 100   # 損得なしになる報酬比例（モデル世帯の夫の現行の比例に対する %）
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{T.CSS}
table.t td.lab {{ font-size: 12px; }}</style></head><body><div class="page">
<h1>財政見通し対照表<span class="stamp">非公式</span></h1>
<div class="sub">現行制度と、厚生年金への国庫負担をなくし浮いた財源を65歳以上に一律給付した場合（思考実験）の対照表</div>
<div class="cond">○ 人口：出生中位、死亡中位、外国人の入国超過数16.4万人　○ 経済：{T.CASES[case]}<br>
○ 国庫負担なし：{START}年度から、厚生年金（被用者年金4制度）への国庫負担をなくす。基礎年金拠出金は全額を厚生年金が払い、
{START}年度から報酬比例の給付（既に受け取っている人を含む）を一律に{cut:.1f}%減らして2120年度に均衡させた<br>
○ 一律給付：国が払わずに済んだ額（厚生年金の国庫負担に当たる額）を、その年度の65歳以上の全員に同じ額で毎年配る。
年金制度の外の給付で、厚生年金・国民年金の収支には入らない<br>
○ 網かけの行が国庫負担なし＋一律給付。<b style="font-weight:bold">太字</b>は現行制度と値が違うところ</div>
<h2>厚生年金（被用者年金4制度計）</h2>
<table class="t">{head_emp}
{chr(10).join(trs)}</table>
<h2>一律給付（国庫負担なしの対照表の国民年金は現行制度と同じなので、代わりに載せる）</h2>
<div class="row"><table class="t" style="width:auto">{head_sk}
{chr(10).join(sk)}</table>
<div><table class="s"><tr><th rowspan="2"></th><th colspan="4">モデル世帯（夫婦）</th><th colspan="2">単身</th></tr>
<tr><th>所得代替率</th><th>比例</th><th>基礎<br><small>2人分</small></th><th>一律給付<br><small>2人分</small></th><th>基礎年金<br>だけ</th><th>平均賃金<br>40年</th></tr>
{smr}</table>
<div class="notes" style="max-width:560px">
調整終了後（2120年度）の値。単身は「基礎年金だけ」が第1号で40年納付、「平均賃金40年」がモデル世帯の夫と
同じ会社員で、どちらも現役男子の平均手取りに対する比率。<br><br>
<b style="font-weight:bold">一律給付は1人ずつ配るので、夫婦は2人分になる。</b>報酬比例が現行の約{even:.0f}%より少ない人
（会社員の期間が短い人、賃金が低い人、基礎年金だけの人）は、国庫負担なし＋一律給付のほうが年金が多くなる（推定）。<br><br>
一律給付の額は、国が払わずに済んだ額（厚生年金の国庫負担に当たる額）を①被保険者推計が使う65歳以上人口で割ったもの。
年金を受け取っていない人も含めて配る。</div></div></div>
<div class="notes">
（注1）厚生年金は、公表の「厚生年金の財政見通し」と同じく被用者年金4制度（厚生年金・国共済・地共済・私学共済）の合計。「報酬比例」には厚生年金の独自給付（定額・加給・加算）を含む。国庫負担なしの行では「国庫負担」の欄が0になる。<br>
（注2）「積立度合」は前年度末積立金の当年度の支出合計に対する倍率。所得代替率はモデル世帯の年金額のその年度の現役男子の平均手取りに対する比率（基礎・一律給付は夫婦2人分）。「一律給付」の列は夫婦2人分の一律給付の手取りに対する割合で、「計」に含む。<br>
（注3）現行制度の値は、厚生労働省「令和6(2024)年財政検証」詳細結果等の財政見通しと一致する（本リポジトリで全項目照合済み）。国庫負担なし＋一律給付は、公表された計算プログラムに独自のレバーを加えて計算した<b style="font-weight:bold">非公式の思考実験</b>で、厚生労働省の試算ではない。一律給付の額は計算プログラムの出力からの推定。
</div></div></body></html>"""


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        run(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "report":
        report()
    elif len(sys.argv) >= 3 and sys.argv[1] == "table":
        table(sys.argv[2:])
    elif len(sys.argv) == 2 and sys.argv[1] == "ichiritsu":
        report_shinkyufu()
    elif len(sys.argv) >= 3 and sys.argv[1] == "ichiritsu-table":
        table_shinkyufu(sys.argv[2:])
    else:
        sys.exit(__doc__)
