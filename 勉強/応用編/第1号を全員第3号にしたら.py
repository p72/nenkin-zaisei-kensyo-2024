#!/usr/bin/env python3
"""第1号被保険者を全員、第3号として登録したら（思考実験・非公式）：記事の表を出す。

原本にないレバー ICHIGO（検証/実行/patches/sango-haishi.patch）で、実施年度から
  ・国民年金の拠出金算定対象者（納付者ベース）と産休・育休の免除者を 0 にする
    （国民年金の保険料収入も、拠出金の按分の頭数も 0 になる）
  ・第1号被保険者数（未納・免除を含む頭数）を厚生年金の第3号の算定対象者に足す
  ・給付側は動かさない
とした試算（予備番号 601）を、現行制度（000）と比べる。

使い方（リポジトリの直下で）
  検証/実行/run_pipeline.sh 3003 1 1 0 2 && 検証/実行/run_pipeline.sh 3002 && 検証/実行/run_pipeline.sh 3001
  STEPS=45 YOBI=601 ICHIGO=2027 検証/実行/run_pipeline.sh 3003 1 1 0 2
  SKIP_BUILD=1 STEPS=45 YOBI=601 ICHIGO=2027 検証/実行/run_pipeline.sh 3002
  SKIP_BUILD=1 STEPS=45 YOBI=601 ICHIGO=2027 検証/実行/run_pipeline.sh 3001
  python3 勉強/応用編/第1号を全員第3号にしたら.py
財政見通し対照表（図）は python3 検証/3号廃止/make_taishohyo.py --case 3003 --yobi 601 など。
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"), ("3001", "高成長実現"))
YEARS = (2027, 2060, 2100)

_s = importlib.util.spec_from_file_location("sango", os.path.join(ROOT, "検証", "3号廃止", "analyze_sango.py"))
A = importlib.util.module_from_spec(_s)
_s.loader.exec_module(A)


def kekka(case, yobi):
    """④の結果の収支見通しの表（{年度: {列名: 値}}）。特別国庫の列を読むため"""
    kb = A.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{case}-{case}-{case}-{case}-1120-{yobi}a.csv"))
    h, rows = kb["収支見通し"]
    return {int(r[0]): {h[i]: r[i] for i in range(len(h)) if h[i]} for r in rows if r and r[0] is not None}


def cho(x):
    return x / 1e12


def main():
    R = {}
    for case, _ in CASES:
        R[case] = {y: (A.load_run(SUURI, case, y, y), kekka(case, y)) for y in ("000", "601")}
        if R[case]["601"][0] is None:
            raise SystemExit(f"★ {case} の 601 の出力がない。使い方の手順で流すこと")

    print("## 所得代替率（給付水準の調整が終わったあと）\n")
    print("| | 現行制度 | 第1号を全員第3号に | 差 |")
    print("|---|---|---|---|")
    for case, cname in CASES:
        b, x = R[case]["000"][0], R[case]["601"][0]
        tb, hb, kb = b["final_rr"]
        tx, hx, kx = x["final_rr"]
        print(f"| {cname} | {tb:.1f}%（比例 {hb:.1f}／基礎 {kb:.1f}） | **{tx:.1f}%**（比例 {hx:.1f}／基礎 **{kx:.1f}**） | "
              f"{tx - tb:+.1f}（比例 {hx - hb:+.1f}／基礎 {kx - kb:+.1f}） |")

    print("\n## 調整の終了年度\n")
    print("| | 現行：基礎／比例 | 第1号を全員第3号に：基礎／比例 |")
    print("|---|---|---|")
    for case, cname in CASES:
        b, x = R[case]["000"][0], R[case]["601"][0]
        print(f"| {cname} | {b['kiso_end']}／{b['hirei_end']}年度 | {x['kiso_end']}／{x['hirei_end']}年度 |")

    print("\n## 動く人数（2027年度）\n")
    for case, cname in CASES:
        b, x = R[case]["000"][0], R[case]["601"][0]
        print(f"- {cname}：第1号被保険者 {x['hiho_1go'][2027] / 1e4:,.0f}万人。拠出金の算定対象者は "
              f"第1号 {b['santei_1go'][2027] / 1e4:,.0f}万 → {x['santei_1go'][2027] / 1e4:,.0f}万人、"
              f"第3号 {b['santei_3go'][2027] / 1e4:,.0f}万 → {x['santei_3go'][2027] / 1e4:,.0f}万人")

    print("\n## お金の流れ（兆円・名目）\n")
    print("| | 年度 | 国民年金の保険料収入 | 国民年金が払う拠出金 | 厚生年金（4制度計）の拠出金 | 拠出金の単価（月額） | 国庫負担（基礎年金＋特別国庫） |")
    print("|---|---|---|---|---|---|---|")
    for case, cname in CASES:
        for y in YEARS:
            cell = []
            for k in ("000", "601"):
                r, kk = R[case][k]
                kokko = r["kokko_total"][y] + kk[y]["国庫（特別国庫）"]
                kou = r["kyo_total"][y] - r["kn_kyoshutu"][y]
                cell.append((cho(r["kn_hoken"][y]), cho(r["kn_kyoshutu"][y]), cho(kou), r["tanka"][y], cho(kokko)))
            a, c = cell
            print(f"| {cname} | {y} | {a[0]:.1f} → {c[0]:.1f} | {a[1]:.1f} → {c[1]:.1f} | {a[2]:.1f} → **{c[2]:.1f}** | "
                  f"{a[3]:,.0f} → {c[3]:,.0f}円 | {a[4]:.1f} → **{c[4]:.1f}** |")

    print("\n## 国民年金の積立金\n")
    print("| | 2060年度末（兆円・名目） | 2120年度末（兆円・名目） | 積立度合（2119年度末÷2120年度の支出） |")
    print("|---|---|---|---|")
    for case, cname in CASES:
        b, x = R[case]["000"][0], R[case]["601"][0]
        print(f"| {cname} | {cho(b['kn_tumitate'][2060]):.0f} → {cho(x['kn_tumitate'][2060]):.0f} | "
              f"{cho(b['kn_tumitate'][2120]):.0f} → {cho(x['kn_tumitate'][2120]):,.0f} | {b['kn_dogai_2119']:.1f} → {x['kn_dogai_2119']:.1f} |")

    print("\n## モデル年金（月額・2024年度の物価、夫婦2人分）\n")
    print("| | 年度 | 現行：計（基礎／比例） | 第1号を全員第3号に：計（基礎／比例） |")
    print("|---|---|---|---|")
    for case, cname in CASES:
        for y in (2040, 2060):
            b, x = R[case]["000"][0], R[case]["601"][0]
            print(f"| {cname} | {y} | {b['model_total'][y] / 1e4:.1f}万円（{b['model_kiso'][y] / 1e4:.1f}／{b['model_hirei'][y] / 1e4:.1f}） | "
                  f"{x['model_total'][y] / 1e4:.1f}万円（{x['model_kiso'][y] / 1e4:.1f}／{x['model_hirei'][y] / 1e4:.1f}） |")


if __name__ == "__main__":
    main()
