# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog04.cpp の忠実移植
=========================================
入力ファイルのパスを組み立てて、開けるか確かめる。開けなければ
`std::exit(1)`（原本どおり）。

**パスは相対**。原本は `../kisosuu/…` や `../../emp/…` と書いているので、
`bunpu/exec` から起動する前提になっている（`検証/実行/run_bunpu.sh` が
`cd "$BUNPU/exec"` してから走らせている）。移植でもそれに合わせる。

引数の対応（`検証/実行/run_bunpu.sh` のコメントより）

    object01a = 外枠番号      seni_*_{a}.csv, PENSION_{d}-{e}-{a}, bunpu_*.{d}-{e}-{a}
    object01d = 試算番号      kaitea-{d}-{e}e, cuta-{d}-{d}-{e}-{a}-1120-125
    object01e = 経済前提番号  econ-{e}.csv
    object01f = 1 なら cuta/cutb の予備番号 125、そうでなければ 925

関数名と読むファイルの対応（原本の順）

    func04a   ../kisosuu/{a1}/{a2}/kisosuu_set.csv          初期母集団
    func04b   ../kisoritsu/kisoritsu01/{b1}/{b2}/seni_{b1}_{b3}_{b4}_{b5}.csv  遷移表
    func04c   ../kisoritsu/kisoritsu02/prob_shougai_shikken_{c1}_{c2}.csv      障害失権
    func04d   ../kisoritsu/kisoritsu03/prob_shougai_hassei_{d1}_{d2}.csv       障害発生
    func04e   ../kisoritsu/kisoritsu04/prob_shougai_hassei_20mae_{e1}.csv      20歳前障害
    func04f   ../kisoritsu/kisoritsu05/prob_seni_kikan_{f1}_{f2}.csv           期間の遷移
    func04g   ../kisoritsu/kisoritsu06/prob_houshuu_seni_{g1}_{g2}.csv         報酬の遷移
    func04h   ../kisoritsu/kisoritsu07/prob_houshuu_shinki_{h1}_{h2}.csv       報酬（新規）
    func04i   ../kisoritsu/kisoritsu08/table_souhoushuu.csv                    総報酬の表
    func04j   ../../emp/data/u-rev/econ/econ-{j1}.csv                          経済前提
    func04k   ../../emp/rslt/u-rev/kaite/kaitea-{k1}-{k2}e                     基礎の改定率
    func04m   ../../emp/rslt/u-rev/kaite/kaiteb-{m1}-{m2}e                     比例の改定率
    func04n   ../../nat/data/PENSION_{n2}-{n3}-{n1}.csv                        国年の年金額
    func04p/q ../../emp/rslt/ez_arev/cutr/cut{a,b}-…-1120-125.csv              カット率
    func04r/s 同上だが末尾が 925
    func04t〜aa ../../emp/rslt/u-rev/bunpu/bunpu_{bb,g}.{d}-{e}-{a}_{制度}.csv 分布

ファイル名の中の数字は `std::to_string(int)` なので、前ゼロは付かない。
Python の f-string の `{x}` と同じ（`int` を素直に10進化する）。
"""
import os

__all__ = [f"func04{s}" for s in
           "a b c d e f g h i j k m n p q r s t u v w x y z".split()] + \
          ["func04aa", "set_base", "resolve"]

# 原本は相対パスで開く（bunpu/exec から起動する前提）。テストでは
# ディレクトリを移らずに動かしたいので、基点を差し替えられるようにした。
# 既定は "" で、原本とまったく同じ相対パスになる。
_BASE = ""


def set_base(base):
    """相対パスの基点を差し替える（既定は空＝原本どおりカレント基準）。"""
    global _BASE
    _BASE = base


def resolve(path_file):
    """相対パスに基点を足す。`prog13`（出力）も同じ基点を使う。"""
    return os.path.join(_BASE, path_file) if _BASE else path_file


def _chk(path_file):
    """原本の `if((ifp_file=fopen(...,"r"))==NULL) std::exit(1);`。

    開けるかだけ見て、パスの文字列を返す（原本は fclose もしていない）。
    """
    full = resolve(path_file)
    try:
        f = open(full, "rb")
    except OSError:
        raise SystemExit(1)
    # 原本は fclose していない（プロセス終了まで開いたまま）。Python では
    # 参照が切れると閉じるので、ここで明示的に閉じる。観測できる差は無い。
    f.close()
    return full


def func04a(arg04a1, arg04a2):
    """prog04.cpp:5 初期母集団。"""
    return _chk(f"../kisosuu/{arg04a1}/{arg04a2}/kisosuu_set.csv")


def func04b(arg04b1, arg04b2, arg04b3, arg04b4, arg04b5):
    """prog04.cpp:14 遷移表。"""
    return _chk(f"../kisoritsu/kisoritsu01/{arg04b1}/{arg04b2}"
                f"/seni_{arg04b1}_{arg04b3}_{arg04b4}_{arg04b5}.csv")


def func04c(arg04c1, arg04c2):
    """prog04.cpp:23 障害失権の確率。"""
    return _chk(f"../kisoritsu/kisoritsu02"
                f"/prob_shougai_shikken_{arg04c1}_{arg04c2}.csv")


def func04d(arg04d1, arg04d2):
    """prog04.cpp:32 障害発生の確率。"""
    return _chk(f"../kisoritsu/kisoritsu03"
                f"/prob_shougai_hassei_{arg04d1}_{arg04d2}.csv")


def func04e(arg04e1):
    """prog04.cpp:41 20歳前障害の発生確率。"""
    return _chk(f"../kisoritsu/kisoritsu04"
                f"/prob_shougai_hassei_20mae_{arg04e1}.csv")


def func04f(arg04f1, arg04f2):
    """prog04.cpp:50 期間の遷移確率。"""
    return _chk(f"../kisoritsu/kisoritsu05"
                f"/prob_seni_kikan_{arg04f1}_{arg04f2}.csv")


def func04g(arg04g1, arg04g2):
    """prog04.cpp:59 報酬の遷移確率。"""
    return _chk(f"../kisoritsu/kisoritsu06"
                f"/prob_houshuu_seni_{arg04g1}_{arg04g2}.csv")


def func04h(arg04h1, arg04h2):
    """prog04.cpp:68 報酬（新規加入）の確率。"""
    return _chk(f"../kisoritsu/kisoritsu07"
                f"/prob_houshuu_shinki_{arg04h1}_{arg04h2}.csv")


def func04i():
    """prog04.cpp:77 総報酬の表。"""
    return _chk("../kisoritsu/kisoritsu08/table_souhoushuu.csv")


def func04j(arg04j1):
    """prog04.cpp:86 経済前提（⑤と同じファイル）。"""
    return _chk(f"../../emp/data/u-rev/econ/econ-{arg04j1}.csv")


def func04k(arg04k1, arg04k2):
    """prog04.cpp:95 基礎（定額）の改定率。"""
    return _chk(f"../../emp/rslt/u-rev/kaite/kaitea-{arg04k1}-{arg04k2}e")


def func04m(arg04m1, arg04m2):
    """prog04.cpp:104 比例の改定率。"""
    return _chk(f"../../emp/rslt/u-rev/kaite/kaiteb-{arg04m1}-{arg04m2}e")


def func04n(arg04n1, arg04n2, arg04n3):
    """prog04.cpp:113 国年の年金額。引数の順が入れ替わる（n2-n3-n1）。"""
    return _chk(f"../../nat/data/PENSION_{arg04n2}-{arg04n3}-{arg04n1}.csv")


def _cutr(kind, a1, a2, a3, yobi):
    """cuta/cutb の共通形。原本は func04p/q/r/s に同じ形を4回書いている。"""
    return _chk(f"../../emp/rslt/ez_arev/cutr/{kind}-{a2}-{a2}-{a3}-{a1}"
                f"-1120-{yobi}.csv")


def func04p(arg04p1, arg04p2, arg04p3):
    """prog04.cpp:122 基礎のカット率（予備125）。"""
    return _cutr("cuta", arg04p1, arg04p2, arg04p3, 125)


def func04q(arg04q1, arg04q2, arg04q3):
    """prog04.cpp:131 比例のカット率（予備125）。"""
    return _cutr("cutb", arg04q1, arg04q2, arg04q3, 125)


def func04r(arg04r1, arg04r2, arg04r3):
    """prog04.cpp:140 基礎のカット率（予備925）。"""
    return _cutr("cuta", arg04r1, arg04r2, arg04r3, 925)


def func04s(arg04s1, arg04s2, arg04s3):
    """prog04.cpp:149 比例のカット率（予備925）。"""
    return _cutr("cutb", arg04s1, arg04s2, arg04s3, 925)


def _bunpu(kind, seido, a1, a2, a3):
    """bunpu_bb / bunpu_g の共通形。原本は func04t〜aa に8回書いている。"""
    return _chk(f"../../emp/rslt/u-rev/bunpu/bunpu_{kind}."
                f"{a2}-{a3}-{a1}_{seido}.csv")


def func04t(a1, a2, a3):
    """prog04.cpp:158 bunpu_bb 厚年。"""
    return _bunpu("bb", "kou", a1, a2, a3)


def func04u(a1, a2, a3):
    """prog04.cpp:167 bunpu_bb 国共済。"""
    return _bunpu("bb", "kok", a1, a2, a3)


def func04v(a1, a2, a3):
    """prog04.cpp:176 bunpu_bb 地共済。"""
    return _bunpu("bb", "ren", a1, a2, a3)


def func04w(a1, a2, a3):
    """prog04.cpp:185 bunpu_bb 私学共済。"""
    return _bunpu("bb", "sig", a1, a2, a3)


def func04x(a1, a2, a3):
    """prog04.cpp:194 bunpu_g 厚年。"""
    return _bunpu("g", "kou", a1, a2, a3)


def func04y(a1, a2, a3):
    """prog04.cpp:203 bunpu_g 国共済。"""
    return _bunpu("g", "kok", a1, a2, a3)


def func04z(a1, a2, a3):
    """prog04.cpp:212 bunpu_g 地共済。"""
    return _bunpu("g", "ren", a1, a2, a3)


def func04aa(a1, a2, a3):
    """prog04.cpp:221 bunpu_g 私学共済。"""
    return _bunpu("g", "sig", a1, a2, a3)
