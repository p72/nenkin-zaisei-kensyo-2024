#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第3号被保険者の廃止シナリオ — ④基礎年金・⑤収支計算の出力を読んで比較する

第3号に保険料を求める2つの財政構造（第1号移行型／拠出金按分据置型・国年充当）を、
現行の調整方式と「調整期間の一致」の両方で計算する。

読むもの（work/suuri/rev2024 配下、run_sango.sh が作る）
  bas/rslt/kekka{S}-{S}-{E}-{W}-1120-{Y}a.csv     ④ 調整後の結果（11ブロック）
  bas/log/bas-{S}-{S}-{E}-{W}-1120-{Y}.log          ④ の標準出力（3号振替の人数）
  emp/rslt/ez_arev/shushi/03summary.{S}-{S}-{E}-{W}-1120-{Y}_08sum.csv  ⑤ 要約

出すもの
  検証/3号廃止/結果.md     比較表（Markdown）
  検証/3号廃止/図/*.png    所得代替率・積立金・国年収支フローの図

使い方: python3 検証/3号廃止/analyze_sango.py [--suuri work/suuri/rev2024] [--year 2027]
"""
import argparse
import csv
import os
import re
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

CASES = OrderedDict([
    ("3003", "過去30年投影ケース"),
    ("3001", "高成長実現ケース"),
])
# 予備番号 → (ラベル, ⑤が読む予備番号, ④の最終結果の予備番号)
# 調整期間の一致（TOUGOU=1）は④を2周し、2周目（YOBI2）が最終の基礎年金見通し
SCEN = OrderedDict([
    ("000", ("現行制度（通常試算）",                    "000", "000")),
    ("301", ("3号廃止・第1号移行型",                    "301", "301")),
    ("501", ("3号廃止・拠出金按分据置型（国年充当）",            "501", "501")),
    ("100", ("現行制度＋調整期間の一致",                "100", "101")),
    ("310", ("3号廃止・第1号移行型＋調整期間の一致",    "310", "311")),
    ("510", ("3号廃止・拠出金按分据置型（国年充当）＋調整期間の一致", "510", "511")),
    ("321", ("3号廃止・第1号移行型・納付率0.8（感度）", "321", "321")),
])
# 差を取る組（ベース予備番号, 比較予備番号）
PAIRS = (("000", "301"), ("000", "501"), ("100", "310"), ("100", "510"), ("000", "321"))
# 調整期間の一致（④を2周する）シナリオ。国年単独の積立金は意味を持たない
TOUGOU_YOBI = ("100", "310", "510")


def fnum(s):
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_blocks(path):
    """kekka / 03summary を「タイトル行 → ヘッダ行 → 数値行…」のブロック群に分ける。
    戻り値: {title: (header[list], rows[list of list of float])}"""
    blocks = OrderedDict()
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f]
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line and not re.match(r"^-?\d", line) and not line.startswith(","):
            title = line.split(",")[0].strip()
            # タイトルとヘッダの間に空行が入るブロックがある（⑤の収支ブロック）
            hdr = []
            j = i + 1
            while j < n and lines[j].strip() == "" and j - i <= 3:
                j += 1
            # ヘッダは「先頭が数字でない」行を続けて読む
            while j < n and lines[j].strip() != "" and not re.match(r"^\s*-?\d", lines[j]):
                hdr.append([c.strip() for c in lines[j].split(",")])
                j += 1
            rows = []
            while j < n and re.match(r"^\s*-?\d", lines[j]):
                rows.append([fnum(c) for c in lines[j].split(",")])
                j += 1
            if rows:
                key = title
                k = 2
                while key in blocks:
                    key = f"{title}#{k}"
                    k += 1
                blocks[key] = (hdr[-1] if hdr else [], rows)
            i = j
        else:
            i += 1
    return blocks


def col(header, name):
    for k, h in enumerate(header):
        if h == name:
            return k
    raise KeyError(f"列 {name!r} がヘッダにありません: {header}")


def series(block, name, year_offset=0, key_col=0):
    header, rows = block
    c = col(header, name)
    out = OrderedDict()
    for r in rows:
        if r and r[key_col] is not None and c < len(r) and r[c] is not None:
            out[int(r[key_col]) + year_offset] = r[c]
    return out


def load_run(suuri, case, yobi5, yobi4, waku=None):
    """waku は外枠番号（既定は試算番号と同じ）。適用拡大のように①から流し直す
    シナリオは外枠番号を分けて通常試算の出力を上書きしないようにしている。"""
    S, W = case, (waku or case)
    kek = os.path.join(suuri, "bas", "rslt", f"kekka{S}-{S}-{S}-{W}-1120-{yobi4}a.csv")
    log = os.path.join(suuri, "bas", "log", f"bas-{S}-{S}-{S}-{W}-1120-{yobi4}.log")
    summ = os.path.join(suuri, "emp", "rslt", "ez_arev", "shushi",
                        f"03summary.{S}-{S}-{S}-{W}-1120-{yobi5}_08sum.csv")
    if not (os.path.exists(kek) and os.path.exists(summ)):
        return None
    r = {}
    kb = read_blocks(kek)
    # 先頭の見出し行。3号廃止で国年が枯渇すると「国年が2054年度に枯渇しました」の行が挟まる
    r["kokatsu_msg"] = None
    with open(kek, encoding="utf-8", errors="replace") as f:
        for _ in range(8):
            line = next(f, "")
            cells = [c.strip() for c in line.split(",")]
            if cells[0] == "カット終了年度":
                m = re.search(r"(\d{4})年度に枯渇", cells[1])
                if m:  # 「国年が2054年度に枯渇しました」— 終了年度は⑤の要約から取る
                    r["kokatsu_msg"] = cells[1]
                    r["kokatsu_year"] = int(m.group(1))
                    r["kiso_end"] = None
                elif cells[1].strip().isdigit():
                    r["kiso_end"] = int(cells[1])
                else:  # 調整期間の一致の2周目（カット率固定）は空欄。⑤の要約から取る
                    r["kiso_end"] = None
            elif cells[0] == "最終カット率":
                r["kiso_cut"] = float(cells[1]) if cells[1].strip() else None

    sh = kb["収支見通し"]
    r["kn_hoken"] = series(sh, "保険料収入（国年）")
    r["kn_kyoshutu"] = series(sh, "基礎年金拠出金")
    r["kn_kokko"] = series(sh, "国庫（基礎年金）")
    r["kn_unyo"] = series(sh, "運用収入")
    r["kn_in"] = series(sh, "収入合計")
    r["kn_out"] = series(sh, "支出合計")
    r["kn_tumitate"] = series(sh, "年度末積立金")
    r["hoken_m"] = series(sh, "保険料月額")

    kk = kb["基礎年金拠出金"]
    r["tanka"] = series(kk, "単価")
    r["kyo_kounen"] = series(kk, "厚年")
    r["kyo_total"] = series(kk, "合計")
    kkk = kb["基礎年金拠出金（国庫）"]
    r["tanka_kokko"] = series(kkk, "単価")
    r["kokko_total"] = series(kkk, "合計")
    r["kokko_kokunen"] = series(kkk, "国年")

    st = kb["拠出金算定対象者"]
    r["santei_total"] = series(st, "合計")
    r["santei_1go"] = series(st, "１号")
    s3 = OrderedDict()
    for nm in ("厚年３号", "国共３号", "地共３号", "私学３号"):
        for y, v in series(st, nm).items():
            s3[y] = s3.get(y, 0.0) + v
    r["santei_3go"] = s3
    dk = kb["独自給付費等"]
    r["hiho_1go"] = series(dk, "１号被保険者数")

    # ④の標準出力（号別振替）: 号別振替,年度,2号,3号,国年算定対象者,保険料のみ徴収人数
    r["furikae"] = OrderedDict()
    r["furikae_2"] = OrderedDict()
    r["furikae_3"] = OrderedDict()
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"号別振替,(\d{4}),([-\d.eE+]+),([-\d.eE+]+),", line)
                if m:
                    y, f2, f3 = int(m.group(1)), float(m.group(2)), float(m.group(3))
                    r["furikae_2"][y] = f2
                    r["furikae_3"][y] = f3
                    r["furikae"][y] = f2 + f3

    # ⑤ 要約
    sb = read_blocks(summ)
    with open(summ, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("終了年度"):
                p = [c.strip() for c in line.split(",")]
                r["hirei_end"] = 2000 + int(p[2])
                r["hirei_cut"] = float(p[3])
                r["kiso_end5"] = 2000 + int(p[5])
                r["kiso_cut5"] = float(p[6])
                break
    if r.get("kiso_end") is None:
        r["kiso_end"] = r["kiso_end5"]
    if r.get("kiso_cut") is None:
        r["kiso_cut"] = r["kiso_cut5"]
    ec = sb["経済前提等"]
    hdr_ec = ec[0]
    c_rr = col(hdr_ec, "所得代替率")
    assert hdr_ec[c_rr + 1] == "うち比例" and hdr_ec[c_rr + 2] == "うち基礎", hdr_ec[c_rr:c_rr + 3]
    r["rr_total"] = series(ec, "所得代替率", 2000)
    r["rr_hirei"] = series((hdr_ec, ec[1]), None, 2000) if False else OrderedDict(
        (int(row[0]) + 2000, row[c_rr + 1]) for row in ec[1] if row and row[0] is not None and row[c_rr + 1] is not None)
    r["rr_kiso"] = OrderedDict(
        (int(row[0]) + 2000, row[c_rr + 2]) for row in ec[1] if row and row[0] is not None and row[c_rr + 2] is not None)
    r["model_total"] = series(ec, "モデル年金額（物価割り戻し）", 2000)
    r["model_kiso"] = series(ec, "うち基礎（物価割り戻し）", 2000)
    r["model_hirei"] = series(ec, "うち比例（物価割り戻し）", 2000)
    tou = sb["収支[全厚年１:tou]"]
    r["kou_hoken"] = series(tou, "保険料", 2000)
    r["kou_kyoshutu"] = series(tou, "基礎年金拠出金", 2000)
    r["kou_kokko"] = series(tou, "国庫負担", 2000)
    r["kou_in"] = series(tou, "収入計", 2000)
    r["kou_out"] = series(tou, "支出計", 2000)
    r["kou_tumitate"] = series(tou, "積立金", 2000)
    r["kou_dokuji"] = series(tou, "独自給付", 2000)
    # 最終（調整終了後）の所得代替率 = 調整終了年度の値
    yend = max(r["kiso_end"], r["hirei_end"])
    r["final_year"] = yend
    # 国年・厚年の積立金が初めて負になる年度（無ければ None）
    r["kn_depleted"] = next((y for y, v in r["kn_tumitate"].items() if y >= 2024 and v < 0), None)
    r["kou_depleted"] = next((y for y, v in r["kou_tumitate"].items() if y >= 2024 and v < 0), None)
    r["kn_dogai_2119"] = r["kn_tumitate"].get(2119, float("nan")) / r["kn_out"].get(2120, float("nan"))
    r["final_rr"] = (r["rr_total"][yend], r["rr_hirei"][yend], r["rr_kiso"][yend])
    return r


def cho(x):  # 円 → 兆円
    return x / 1e12


def oku_to_cho(x):  # 億円 → 兆円
    return x / 1e4


def fmt(x, d=2):
    return f"{x:,.{d}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suuri", default=os.path.join(ROOT, "work", "suuri", "rev2024"))
    ap.add_argument("--year", type=int, default=2027, help="3号廃止の実施年度（表示用）")
    ap.add_argument("--no-fig", action="store_true")
    args = ap.parse_args()

    runs = OrderedDict()
    for case in CASES:
        for yobi, (label, y5, y4) in SCEN.items():
            r = load_run(args.suuri, case, y5, y4)
            if r is not None:
                runs[(case, yobi)] = r
            else:
                print(f"（未計算）{case} {yobi} {label}", file=sys.stderr)

    out = []
    w = out.append
    w("# 第3号被保険者の廃止（第1号への振替・全員納付）— 計算結果\n")
    w(f"実施年度 {args.year}年度。①〜③は通常試算のまま、④基礎年金と⑤収支計算だけを流し直した"
      "（`検証/3号廃止/run_sango.sh`）。数値は `analyze_sango.py` が出力ファイルから拾ったもので、"
      "手で書き写した数字はない。\n")

    # ---- 表1 所得代替率
    w("## 表1 給付水準の調整終了後の所得代替率\n")
    w("| ケース | シナリオ | 所得代替率 | うち比例 | うち基礎 | 調整終了（比例） | 調整終了（基礎） | 基礎の最終カット率 | 国年積立金が負になる年度 | 国年 2120年度初の積立度合 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for (case, yobi), r in runs.items():
        t, h, k = r["final_rr"]
        ke = f"{r['kiso_end']}年度" + ("（**均衡せず**）" if r["kiso_end"] >= 2120 else "")
        if yobi in TOUGOU_YOBI:   # 調整期間の一致: 国年と厚年を一体で均衡させるので国年単独の積立金は参照しない
            dep, dogai = "—（一体で均衡）", "—"
        else:
            dep = f"{r['kn_depleted']}年度" if r["kn_depleted"] else "なし"
            dogai = f"{r['kn_dogai_2119']:.2f}"
        w(f"| {CASES[case]} | {SCEN[yobi][0]} | **{t:.2f}%** | {h:.2f}% | {k:.2f}% | "
          f"{r['hirei_end']}年度 | {ke} | {r['kiso_cut']:.4f} | {dep} | {dogai} |")
    w("")
    w("「調整終了（基礎）」が2120年度のものは、有限均衡期間（2120年度）いっぱいマクロ経済スライドを続けても"
      "国民年金が均衡しない（積立度合1に届かない）ことを意味する。その場合の所得代替率は「2120年度まで調整を続けた"
      "ときの水準」であって、均衡解ではない。通常試算の1人当たりゼロ成長ケースと同じ扱い（仕様書 §15.0.0）。\n")
    w("逆に「基礎の最終カット率」が 0.9900 で「調整終了（基礎）」が2024年度のもの（拠出金按分据置型）は、"
      "**反対側の天井**に当たっている。マクロ経済スライドをまったくかけなくても国民年金が余り、"
      "2120年度の積立度合が1を大きく超える（最右列）。基礎の水準はこれ以上上がらないので、"
      "これも均衡解ではない。余った分は国民年金の積立金に積み上がる（`make_tumitate_chart.py`）。\n")
    w("調整期間の一致の下では、第1号移行型と拠出金按分据置型は同じ答えになる（15桁一致）。"
      "国民年金と厚生年金を一体で均衡させるので、拠出金の按分は勘定間の移転にすぎないからである。\n")
    # 差分
    w("### 現行制度との差（同じ経済前提・同じ調整方式で比較）\n")
    w("| ケース | 比較 | 所得代替率の差 | 比例の差 | 基礎の差 | 基礎の調整終了の差 |")
    w("|---|---|---|---|---|---|")
    for case in CASES:
        for base, alt in PAIRS:
            if (case, base) in runs and (case, alt) in runs:
                b, a = runs[(case, base)], runs[(case, alt)]
                d = [a["final_rr"][i] - b["final_rr"][i] for i in range(3)]
                w(f"| {CASES[case]} | {SCEN[alt][0]} − {SCEN[base][0]} | "
                  f"{d[0]:+.2f}pt | {d[1]:+.2f}pt | {d[2]:+.2f}pt | {a['kiso_end'] - b['kiso_end']:+d}年 |")
    w("")

    # ---- 表2 国年勘定への影響（実施年度と節目）
    years = [args.year, 2030, 2040, 2050, 2060, 2080, 2100, 2119]
    for case, alt_yobi in [(c, y) for c in CASES for y in ("301", "501")]:
        if (case, "000") not in runs or (case, alt_yobi) not in runs:
            continue
        b, a = runs[(case, "000")], runs[(case, alt_yobi)]
        w(f"## 表2-{case}-{alt_yobi} 国民年金勘定と厚生年金勘定の差分"
          f"（{CASES[case]}、{SCEN[alt_yobi][0]} − 現行、兆円・名目）\n")
        w("| 年度 | 振替人数（万人） | 国年 保険料収入の増 | 国年 拠出金の増 | 国年 国庫負担の増 | 国年 収支への純効果 | （参考）頭数効果だけ | 国年 年度末積立金の差 | 厚年 拠出金の減 | 厚年 積立金の差 | 同（厚年支出の年数） |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for y in years:
            if y not in a["kn_hoken"] or y not in a["kou_kyoshutu"]:
                continue
            dh = cho(a["kn_hoken"][y] - b["kn_hoken"][y])
            dk = cho(a["kn_kyoshutu"][y] - b["kn_kyoshutu"][y])
            dg = cho(a["kn_kokko"][y] - b["kn_kokko"][y])
            net = dh - dk + dg
            dt = cho(a["kn_tumitate"][y] - b["kn_tumitate"][y])
            dkk = oku_to_cho(a["kou_kyoshutu"][y] - b["kou_kyoshutu"][y])
            dkt = oku_to_cho(a["kou_tumitate"][y] - b["kou_tumitate"][y])
            fk = a["furikae"].get(y, b["santei_3go"].get(y))
            fk_s = f"{fk/1e4:,.0f}" if fk is not None else "—"
            # 頭数効果だけ: 振替人数 × （現行の実効保険料月額 − 現行の国年実負担単価）× 12
            eff = b["kn_hoken"][y] / b["santei_1go"][y] / 12.0
            head_only = cho(fk * (eff - (b["tanka"][y] - b["tanka_kokko"][y])) * 12.0) if fk is not None else float("nan")
            yrs_out = dkt / oku_to_cho(b["kou_out"][y]) if b["kou_out"].get(y) else float("nan")
            w(f"| {y} | {fk_s} | {dh:+.2f} | {dk:+.2f} | {dg:+.2f} | **{net:+.2f}** | {head_only:+.2f} | {dt:+.1f} | {dkk:+.2f} | {dkt:+.1f} | {yrs_out:+.2f}年 |")
        w("")
        w("注: 「国年 収支への純効果」= 保険料収入の増 − 拠出金の増 + 国庫負担の増（運用収入の差は含まない）。"
          "基礎年金の給付水準は現行と3号廃止で違う（調整終了年度が動く）ので、拠出金の差には水準の差も含まれる。"
          "「頭数効果だけ」は、現行制度の単価・保険料のまま振替人数だけを動かしたときの機械計算"
          "（振替人数 × （実効保険料月額 − （拠出金単価 − 国庫負担単価））× 12）で、水準の差を除いた純粋な振替の効果。\n")

    # ---- 表3 1人当たり（実施年度）
    w("## 表3 振替1人当たりの収支（実施年度、現行制度の単価、月額・名目）\n")
    w("| ケース | 年度 | 保険料月額（名目） | 拠出金単価 | うち国庫負担単価 | 国年の実負担（単価−国庫） | 保険料 − 実負担 |")
    w("|---|---|---|---|---|---|---|")
    for case in CASES:
        if (case, "000") not in runs:
            continue
        b = runs[(case, "000")]
        for y in (args.year, 2040, 2060, 2080, 2100):
            if y not in b["tanka"]:
                continue
            # 名目保険料 = 年間保険料収入 / (算定対象者 × 12) の近似ではなく、④の保険料月額（2004価格）×換算率が要る。
            # 換算率は kekka の経済前提ブロックにあるが、ここでは保険料収入/算定1号/12 で実効月額を出す。
            eff = b["kn_hoken"][y] / b["santei_1go"][y] / 12.0
            net = b["tanka"][y] - b["tanka_kokko"][y]
            w(f"| {CASES[case]} | {y} | {eff:,.0f}円 | {b['tanka'][y]:,.0f}円 | {b['tanka_kokko'][y]:,.0f}円 | {net:,.0f}円 | **{eff-net:+,.0f}円** |")
    w("")
    w("注: 保険料月額（名目）は「国年保険料収入 ÷ 1号算定対象者 ÷ 12」で出した実効値（産休・育休免除分の控除を含む）。\n")

    # ---- 表4 被保険者数の構成
    w("## 表4 拠出金算定対象者（現行制度、万人）\n")
    w("| ケース | 年度 | 合計 | 1号（納付・免除加重） | 3号（4制度計） | 3号／合計 |")
    w("|---|---|---|---|---|---|")
    for case in CASES:
        if (case, "000") not in runs:
            continue
        b = runs[(case, "000")]
        for y in (2025, args.year, 2040, 2060, 2080, 2100):
            if y in b["santei_total"]:
                w(f"| {CASES[case]} | {y} | {b['santei_total'][y]/1e4:,.0f} | {b['santei_1go'][y]/1e4:,.0f} | "
                  f"{b['santei_3go'][y]/1e4:,.0f} | "
                  f"{100*b['santei_3go'][y]/b['santei_total'][y]:.1f}% |")
    w("")

    # ---- 表5 国庫負担（総額は基礎年金の水準でしか動かない）
    w("## 表5 基礎年金拠出金の国庫負担（兆円・名目）\n")
    w("国庫負担は基礎年金給付費の1/2を頭数で按分したもの。振替は分子（基礎年金の総額）を"
      "動かさないので、**総額は配分が変わるだけで直接には動かない**。総額が動くのは"
      "基礎年金の給付水準そのものが変わったときだけ。\n")
    w("| ケース | シナリオ | 年度 | 国庫負担 合計 | 現行との差 | うち国年分の差 | うち被用者年金分の差 |")
    w("|---|---|---|---|---|---|---|")
    for case in CASES:
        for alt in ("301", "501", "310"):
            base = "100" if alt in TOUGOU_YOBI else "000"
            if (case, base) not in runs or (case, alt) not in runs:
                continue
            bb, aa = runs[(case, base)], runs[(case, alt)]
            for y in (args.year, 2040, 2060, 2080, 2100):
                if y not in aa["kokko_total"]:
                    continue
                d = cho(aa["kokko_total"][y] - bb["kokko_total"][y])
                dk = cho(aa["kokko_kokunen"][y] - bb["kokko_kokunen"][y])
                w(f"| {CASES[case]} | {SCEN[alt][0]} | {y} | {cho(aa['kokko_total'][y]):.2f} | "
                  f"{d:+.2f} | {dk:+.2f} | {d - dk:+.2f} |")
    w("")
    w("注: 「現行との差」の比較相手は、調整期間の一致のシナリオは一致ありの現行、"
      "それ以外は通常試算。\n")

    res_md = os.path.join(HERE, "結果.md")
    with open(res_md, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"書き出し: {res_md}")

    if args.no_fig:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("matplotlib が無いので図は省略", file=sys.stderr)
        return
    for fp in ("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
               "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"):
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    figdir = os.path.join(HERE, "図")
    os.makedirs(figdir, exist_ok=True)

    # 検証済みのカテゴリ配色（1:青 2:橙 3:緑）と、一致ありを表す無彩色・淡色
    C_BASE, C_ALT, C_SUE = "#2a78d6", "#eb6834", "#1baf7a"
    C_BASE_T, C_ALT_T = "#8C8C8C", "#eda100"

    for case in CASES:
        if (case, "000") not in runs or (case, "301") not in runs:
            continue
        b, a = runs[(case, "000")], runs[(case, "301")]
        bt = runs.get((case, "100"))
        at = runs.get((case, "310"))
        s1 = runs.get((case, "501"))
        yrs = [y for y in b["rr_total"] if 2024 <= y <= 2100]

        # 図1 所得代替率の推移（新規裁定時）
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
        lines = [(b, C_BASE, "-", 2.0, "現行制度"),
                 (a, C_ALT, "-", 2.0, "第1号移行型"),
                 (s1, C_SUE, "-", 2.0, "拠出金按分据置型"),
                 (bt, C_BASE_T, "--", 1.5, "現行＋調整期間の一致"),
                 (at, C_ALT_T, "--", 1.5, "第1号移行型＋調整期間の一致"),
                 ]
        for ax, key, ttl in zip(axes, ("rr_total", "rr_hirei", "rr_kiso"), ("所得代替率（計）", "うち報酬比例", "うち基礎")):
            for r_, c_, ls_, lw_, lb_ in lines:
                if r_ is None:
                    continue
                ax.plot(yrs, [r_[key][y] for y in yrs], color=c_, lw=lw_, ls=ls_, label=lb_)
            ax.set_title(ttl)
            ax.set_xlabel("年度")
            ax.set_ylabel("%")
            ax.grid(alpha=0.3)
        axes[0].legend(fontsize=8, loc="lower left")
        fig.suptitle(f"所得代替率の推移 — {CASES[case]}（{args.year}年度実施）", fontsize=13)
        fig.tight_layout()
        fig.savefig(os.path.join(figdir, f"所得代替率_{case}.png"), dpi=130)
        plt.close(fig)

        # 図2 国年・厚年の積立金
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
        yk = [y for y in b["kn_tumitate"] if 2024 <= y <= 2120]
        for r_, c_, lb_ in ((b, C_BASE, "現行制度"), (a, C_ALT, "第1号移行型"),
                            (s1, C_SUE, "拠出金按分据置型")):
            if r_ is None:
                continue
            axes[0].plot(yk, [cho(r_["kn_tumitate"][y]) for y in yk], color=c_, lw=2, label=lb_)
        axes[0].axhline(0, color="gray", lw=0.8)
        axes[0].set_title("国民年金勘定 年度末積立金（名目、兆円）")
        yk2 = [y for y in b["kou_tumitate"] if 2024 <= y <= 2120]
        for r_, c_, lb_ in ((b, C_BASE, "現行制度"), (a, C_ALT, "第1号移行型"),
                            (s1, C_SUE, "拠出金按分据置型")):
            if r_ is None:
                continue
            axes[1].plot(yk2, [oku_to_cho(r_["kou_tumitate"][y]) for y in yk2], color=c_, lw=2, label=lb_)
        axes[1].set_title("厚生年金勘定（4制度計） 年度末積立金（名目、兆円）")
        for ax in axes:
            ax.set_xlabel("年度")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=9)
        fig.suptitle(f"積立金の推移 — {CASES[case]}", fontsize=13)
        fig.tight_layout()
        fig.savefig(os.path.join(figdir, f"積立金_{case}.png"), dpi=130)
        plt.close(fig)

        # 図3 国年勘定のフロー差分
        yf = [y for y in a["kn_hoken"] if args.year <= y <= 2120]
        dh = [cho(a["kn_hoken"][y] - b["kn_hoken"][y]) for y in yf]
        dk = [-cho((a["kn_kyoshutu"][y] - b["kn_kyoshutu"][y]) - (a["kn_kokko"][y] - b["kn_kokko"][y])) for y in yf]
        net = [x + z for x, z in zip(dh, dk)]
        fig, ax = plt.subplots(figsize=(9, 4.8))
        ax.fill_between(yf, 0, dh, color=C_ALT, alpha=0.35, label="保険料収入の増（3号→1号）")
        ax.fill_between(yf, 0, dk, color=C_BASE, alpha=0.35, label="拠出金負担の増（国庫負担控除後、符号反転）")
        ax.plot(yf, net, color="black", lw=2, label="純効果（収入増 − 実負担増）")
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(f"国民年金勘定への年次フロー効果 — {CASES[case]}（名目、兆円）")
        ax.set_xlabel("年度")
        ax.set_ylabel("兆円")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(figdir, f"国年フロー_{case}.png"), dpi=130)
        plt.close(fig)

    # 図4 振替人数（3号 20〜59歳、年央値）
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for case, c in zip(CASES, (C_BASE, C_ALT)):
        if (case, "000") in runs:
            b = runs[(case, "000")]
            ys = [y for y in b["santei_3go"] if 2024 <= y <= 2120]
            ax.plot(ys, [b["santei_3go"][y] / 1e4 for y in ys], lw=2, color=c, label=CASES[case])
    ax.set_title("第3号被保険者（20〜59歳、拠出金算定対象、4制度計）の見通し（万人）")
    ax.set_xlabel("年度")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "3号被保険者数.png"), dpi=130)
    plt.close(fig)
    print(f"図: {figdir}")


if __name__ == "__main__":
    main()
