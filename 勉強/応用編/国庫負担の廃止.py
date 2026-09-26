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


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        run(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "report":
        report()
    elif len(sys.argv) >= 3 and sys.argv[1] == "table":
        table(sys.argv[2:])
    else:
        sys.exit(__doc__)
