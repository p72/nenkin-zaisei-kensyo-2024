#!/usr/bin/env python3
"""厚年留保案（RYUHO レバー）で⑤に渡す、第3号の保険料の年額を④の出力から作る。

  第3号の保険料[年度][制度] ＝ 第3号の人数[年度][制度] × 国民年金の保険料[年度] × 12 × 割合
  国民年金の保険料[年度]    ＝ 保険料月額 × 保険料改定率

  第3号の人数       ④ kekka の「拠出金算定対象者」の 厚年３号・国共３号・地共３号・私学３号
  保険料月額        ④ kekka の「収支見通し」の 保険料月額（法定額 17,000円。2004年度価格）
  保険料改定率      同じく 保険料改定率（2025年度 1.030 → 17,510円）。この積は、④の
                    国民年金の保険料収入 ÷（第1号 − 産休・育休免除）÷ 12 とほぼ一致する
  割合              RYUHO_RITU（1＝国民年金保険料相当額、0.5＝その50％）

実施年度より前は0。出力は1行＝「西暦,厚年,国共,地共,私学」（円）で、⑤の
patches/sango-ryuho.patch が読む。

使い方: ryuho_hokenryo.py <kekka…a.csv> <実施年度> <割合> > 出力.csv
"""
import re
import sys

SEIDO = ("厚年３号", "国共３号", "地共３号", "私学３号")


def block(lines, title, header_key):
    """タイトル行のあとの、header_key を含むヘッダ行と数値行を返す。"""
    i = next(n for n, l in enumerate(lines) if l.split(",")[0].strip() == title)
    j = next(n for n in range(i + 1, len(lines)) if header_key in lines[n].split(","))
    head = [c.strip() for c in lines[j].split(",")]
    rows = []
    for l in lines[j + 1:]:
        if not re.match(r"^\s*\d", l):
            break
        rows.append([c.strip() for c in l.split(",")])
    return head, rows


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    path, start, ritu = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    h, rows = block(lines, "拠出金算定対象者", "厚年３号")
    ninzu = {int(float(r[0])): [float(r[h.index(s)]) for s in SEIDO] for r in rows}
    h, rows = block(lines, "収支見通し", "保険料月額")
    getsu = {int(float(r[0])): float(r[h.index("保険料月額")]) * float(r[h.index("保険料改定率")])
             for r in rows}
    for y in sorted(ninzu):
        if y not in getsu:
            continue
        a = [n * getsu[y] * 12 * ritu if y >= start else 0.0 for n in ninzu[y]]
        print(f"{y}," + ",".join(f"{x:.6f}" for x in a))


if __name__ == "__main__":
    main()
