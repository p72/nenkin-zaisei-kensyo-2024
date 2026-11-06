#!/usr/bin/env python3
"""基礎年金拠出金の頭数と、厚生年金から国民年金への補填（非公式・推定）。

基礎年金拠出金は、制度ごとの拠出金算定対象者（頭数）に共通の単価を掛けて割り振る。
国民年金の頭数は第1号のうち保険料を納めた人だけ、被用者年金は第2号（20〜59歳）と第3号の全員。
ここでは、
  - 単価が制度で同じこと（拠出金 ÷ 頭数 ÷ 12）
  - 第1号のうち頭数に入っている割合
  - 第1号を全員頭数に入れたら、単価と制度ごとの拠出金がどう変わるか（拠出金の合計はそのまま、推定）
  - 1人あたりの保険料と基礎年金の実負担（単価 − 国庫負担単価）のくらべ
を、通常試算（予備番号000）の④の出力から出す。

使い方（リポジトリの直下で。通常試算の 3003・3002・3001 が要る）
  python3 勉強/応用編/拠出金の頭数.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"), ("3001", "高成長実現"))
YEARS = (2027, 2040, 2060)
HYOJUN = (88_000, 118_000, 400_000)      # 第2号の標準報酬月額の例（2027年度。最低等級・単価と釣り合うあたり・平均的な会社員）
                                         # 2028年度以降は国民年金の保険料改定率（名目賃金に連動）で延ばす
RITU = 0.183

_s = importlib.util.spec_from_file_location("sango", os.path.join(ROOT, "検証", "3号廃止", "analyze_sango.py"))
A = importlib.util.module_from_spec(_s)
_s.loader.exec_module(A)


def blocks(case):
    return A.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{case}-{case}-{case}-{case}-1120-000a.csv"))


def row(block, y):
    h, rows = block
    r = [x for x in rows if x and x[0] == y][0]
    return {k: v for k, v in zip(h, r) if k}


def main():
    for case, cname in CASES:
        r = A.load_run(SUURI, case, "000", "000")
        kb = blocks(case)
        print(f"## {cname}（{case}）\n")
        print("| 年度 | 単価（月額） | 国年の拠出金÷国年の頭数 | 厚年の拠出金÷厚年の頭数 | 第1号被保険者 | うち頭数に入る人 | 割合 |")
        print("|---|---|---|---|---|---|---|")
        for y in YEARS:
            st, kk = row(kb["拠出金算定対象者"], y), row(kb["基礎年金拠出金"], y)
            kou = st["厚年２号"] + st["厚年３号"]
            print(f"| {y} | {r['tanka'][y]:,.0f}円 | {r['kn_kyoshutu'][y] / (r['santei_1go'][y] * 12):,.0f}円 | "
                  f"{kk['厚年'] / (kou * 12):,.0f}円 | {r['hiho_1go'][y] / 1e4:,.0f}万人 | {r['santei_1go'][y] / 1e4:,.0f}万人 | "
                  f"{r['santei_1go'][y] / r['hiho_1go'][y] * 100:.0f}% |")
        print("\n第1号を全員頭数に入れたら（拠出金の合計はそのまま、推定）\n")
        print("| 年度 | 単価：いま → 全員 | いまの単価の高さ | 国民年金の拠出金 | 被用者年金の拠出金 | 被用者年金の負担の差 |")
        print("|---|---|---|---|---|---|")
        for y in YEARS:
            tot, one, hiho = r["santei_total"][y], r["santei_1go"][y], r["hiho_1go"][y]
            t = r["tanka"][y]
            t2 = r["kyo_total"][y] / ((tot + hiho - one) * 12)
            kn2 = hiho * t2 * 12
            hy, hy2 = r["kyo_total"][y] - r["kn_kyoshutu"][y], r["kyo_total"][y] - kn2
            print(f"| {y} | {t:,.0f}円 → {t2:,.0f}円 | ＋{(t / t2 - 1) * 100:.1f}% | {r['kn_kyoshutu'][y] / 1e12:.2f} → {kn2 / 1e12:.2f}兆円 | "
                  f"{hy / 1e12:.2f} → {hy2 / 1e12:.2f}兆円 | {(hy - hy2) / 1e12:.2f}兆円（うち国庫負担の分 {(hy - hy2) / 2e12:.2f}兆円） |")
        print("\n1人あたり（月額）：保険料と基礎年金の実負担（単価 − 国庫負担単価）\n")
        print("第1号は保険料収入 ÷ 頭数 ÷ 12（実効。前納割引などを含む）。第2号は標準報酬 × 18.3%（労使計・賞与なし）で、"
              "標準報酬は2027年度の額を保険料改定率で延ばした\n")
        sh = kb["収支見通し"]
        k0 = row(sh, YEARS[0])["保険料改定率"]
        print("| 年度 | 実負担 | 第1号の保険料（実効） | 差 | " + " | ".join(f"第2号 標準報酬{w / 1e4:.1f}万円 | 差" for w in HYOJUN) + " |")
        print("|---|---|---|---|" + "---|---|" * len(HYOJUN))
        for y in YEARS:
            jf = r["tanka"][y] - r["tanka_kokko"][y]
            ich = r["kn_hoken"][y] / (r["santei_1go"][y] * 12)
            sc = row(sh, y)["保険料改定率"] / k0
            cells = [f"{w * sc * RITU:,.0f}円 | {w * sc * RITU - jf:+,.0f}円" for w in HYOJUN]
            print(f"| {y} | {jf:,.0f}円 | {ich:,.0f}円 | {ich - jf:+,.0f}円 | " + " | ".join(cells) + " |")
        y = YEARS[0]
        jf = r["tanka"][y] - r["tanka_kokko"][y]
        print(f"\n- 基礎年金の実負担と釣り合う標準報酬月額（{y}年度）：{jf / RITU:,.0f}円（賞与なし、報酬比例の分は入れない）\n")


if __name__ == "__main__":
    main()
