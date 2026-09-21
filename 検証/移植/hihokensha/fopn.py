# -*- coding: utf-8 -*-
"""
①被保険者推計が開くファイルのパス
==================================
原本は `readdata.c` / `fout.c` / `roudfout.c` / `cutout.c` の中に
`sprintf(filename, "/suuri/rev2024/…")` を書き下している（専用のファイルは
無い）。移植では**パスの組み立てだけをここに集めた**。中身は原本の
書式そのままで、先頭の `/suuri` だけ差し替えられるようにしている。

    /suuri/rev2024/wakuc/data/sinj/pop%01d-%01d%01d%01d.csv
    ↓  SUURI_PREFIX=work のとき
    work/suuri/rev2024/wakuc/data/sinj/pop1-110.csv

`検証/実行/run_pipeline.sh` は原本の `/suuri` を実行環境の絶対パスに
書き換えてからビルドしている。移植版は環境変数 `SUURI_PREFIX` で同じ
ことをする（⑤の `emp_shushi/fopn.py` と同じ規則）。

読むファイル（`readdata.c` の順）
---------------------------------
    sinj/pop{sei}-{JIN}{QX}{NC}.csv          人口（性別ごと）
    sinj/wari-2020.csv                       人口割合
    sinj/yuhaigr_suikei-2020.csv             女性有配偶割合（推計）
    roud2024/roudou2024-{ROUDR}.csv          労働力率（ケース毎）
    roud2024/syugyor2024-{ROUDR}.csv         就業率（ケース毎）
    roud2024/koyour2022.csv                  雇用者割合（実績）
    roud2024/seikir2022.csv                  正規雇用者割合（実績）
    roud2024/hiseikifurur2022.csv            非正規フル雇用者割合（実績）
    roud2024/hiseikitanr2022.csv             非正規短時間雇用者割合（実績）
    roud2024/syosettei2022-{ROUDR}.csv       諸設定値（ケース毎）
    map/{yy}map.csv                          被保険者数（実績。年度は2桁）
    map/{yy}map-45.csv                       同・基礎45年化のとき
    prev/ichiyuhaigr2022.csv                 1号有配偶率
    prev/ichisanxend2022.csv                 1・3号の上限年齢（45年化のみ）
    map/cut_jisseki.csv                      調整率の実績
    part/partnin2020-2024.csv                パート（現行）
    part/partnin2020-2027-{MODE}.csv         パート（1段階）
    part/partnin2020-2029-{MODE}.csv         パート（2段階）

書くファイル（全部で 100 本・約 49MB）
--------------------------------------
    waku{BANGO}-err.csv            エラーの記録（readdata.c:25）
    waku{BANGO}-{00..57}.csv       分類別×性×年度×年齢（fout.c:20）      58本
    waku{BANGO}-nenreikei.csv      年度末の年齢計（fout.c:458）
    waku{BANGO}-nenkeikan.csv      年度間の平均（fout.c:495）
    waku{BANGO}-settei.csv         設定値の控え（fout.c:533）
    wakuroud{BANGO}-{00..39}.csv   労働力の分類別（roudfout.c:21）        40本
    waku{BANGO}-roudkei.csv        労働力の年齢計（roudfout.c:177）
    waku{BANGO}-m.csv              調整率（cutout.c:24）

いずれも `rslt/ver_4_1/rslt{BANGO}/` の下。

出力先のディレクトリは原本が `mkdir(pathname, 0755)` で作る
（`readdata.c:21-24`。戻り値は見ていないので、既にあっても進む）。

原本の癖をそのまま残しているところ
----------------------------------
**`char filename[250]` と `char pathname[250]`**（`readdata.c:16,17`）
原本のパスは `/suuri/rev2024/…` で十分収まるが、`run_pipeline.sh` が
長い絶対パスに書き換えると `sprintf` があふれる。そこで同スクリプトは
同時に `250` を `1024` に書き換えている。移植版は Python の str なので
制限が無い。（`検証/原本の不具合.md` C2/C3）
"""
import os

__all__ = ["syspath", "rslt_dir", "P"]


def syspath(rel):
    """原本の `/suuri/...` を `SUURI_PREFIX` で差し替える。

    既定は `/suuri`（原本そのまま）。⑤の `emp_shushi/fopn.py` と同じ規則。
    """
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        return "/suuri/" + rel
    return prefix.rstrip("/") + "/suuri/" + rel


def _w(rel):
    return syspath("rev2024/wakuc/" + rel)


class _Paths:
    """`readdata.c` ほかの `sprintf(filename, …)` をそのまま関数にしたもの。"""

    # ---- 読む ----
    @staticmethod
    def pop(sei, jin, qx, nc):
        """readdata.c:32"""
        return _w(f"data/sinj/pop{sei:01d}-{jin:01d}{qx:01d}{nc:01d}.csv")

    @staticmethod
    def wari():
        """readdata.c:59"""
        return _w("data/sinj/wari-2020.csv")

    @staticmethod
    def yuhaigr():
        """readdata.c:79"""
        return _w("data/sinj/yuhaigr_suikei-2020.csv")

    @staticmethod
    def roudou(roudr):
        """readdata.c:111"""
        return _w(f"data/roud2024/roudou2024-{roudr:01d}.csv")

    @staticmethod
    def syugyor(roudr):
        """readdata.c:133"""
        return _w(f"data/roud2024/syugyor2024-{roudr:01d}.csv")

    @staticmethod
    def koyour():
        """readdata.c:155"""
        return _w("data/roud2024/koyour2022.csv")

    @staticmethod
    def seikir():
        """readdata.c:177"""
        return _w("data/roud2024/seikir2022.csv")

    @staticmethod
    def hiseikifurur():
        """readdata.c:199"""
        return _w("data/roud2024/hiseikifurur2022.csv")

    @staticmethod
    def hiseikitanr():
        """readdata.c:220"""
        return _w("data/roud2024/hiseikitanr2022.csv")

    @staticmethod
    def syosettei(roudr):
        """readdata.c:235"""
        return _w(f"data/roud2024/syosettei2022-{roudr:01d}.csv")

    @staticmethod
    def map_(nendo, mode45=0):
        """readdata.c:274,283,286。年度は **2桁**（`%02d`）。

        西暦2023なら `"2023"` の下2桁ではなく `%02d` に 2023 を流すので
        `"2023map.csv"` になる（`%02d` は最小桁数なので切り詰めない）。
        """
        if mode45 == 1:
            return _w(f"data/map/{nendo:02d}map-45.csv")
        return _w(f"data/map/{nendo:02d}map.csv")

    @staticmethod
    def ichiyuhaigr():
        """readdata.c:295"""
        return _w("data/prev/ichiyuhaigr2022.csv")

    @staticmethod
    def ichisanxend():
        """readdata.c:309"""
        return _w("data/prev/ichisanxend2022.csv")

    @staticmethod
    def cut_jisseki():
        """readdata.c:331"""
        return _w("data/map/cut_jisseki.csv")

    @staticmethod
    def part0():
        """readdata.c:343。現行制度のパート"""
        return _w("data/part/partnin2020-2024.csv")

    @staticmethod
    def part1(mode):
        """readdata.c:374。1段階"""
        return _w(f"data/part/partnin2020-2027-{mode:01d}.csv")

    @staticmethod
    def part2(mode):
        """readdata.c:406。2段階"""
        return _w(f"data/part/partnin2020-2029-{mode:01d}.csv")

    # ---- 書く ----
    @staticmethod
    def err(bango):
        """readdata.c:25"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}/waku{bango:04d}-err.csv")

    @staticmethod
    def waku(bango, bunrui):
        """fout.c:20。分類別の本体（58本）"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/waku{bango:04d}-{bunrui:02d}.csv")

    @staticmethod
    def nenreikei(bango):
        """fout.c:458"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/waku{bango:04d}-nenreikei.csv")

    @staticmethod
    def nenkeikan(bango):
        """fout.c:495"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/waku{bango:04d}-nenkeikan.csv")

    @staticmethod
    def settei(bango):
        """fout.c:533"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/waku{bango:04d}-settei.csv")

    @staticmethod
    def wakuroud(bango, bunrui):
        """roudfout.c:21。労働力の分類別（40本）"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/wakuroud{bango:04d}-{bunrui:02d}.csv")

    @staticmethod
    def roudkei(bango):
        """roudfout.c:177"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}"
                  f"/waku{bango:04d}-roudkei.csv")

    @staticmethod
    def cutm(bango):
        """cutout.c:24"""
        return _w(f"rslt/ver_4_1/rslt{bango:04d}/waku{bango:04d}-m.csv")

    # ---- 共済からのデータ（simlkyos.c:27,30,33）----
    @staticmethod
    def kyos(seido, jin, qx, nc):
        """simlkyos.c:27,30,33。seido 4→kok, 5→ren, 6→sig"""
        name = {4: "kok", 5: "ren", 6: "sig"}[seido]
        return _w(f"data/kyos/{name}2022-{jin:01d}{qx:01d}{nc:01d}.csv")


P = _Paths()


def rslt_dir(bango):
    """readdata.c:21-24 の `mkdir` を2段。戻り値は見ない（原本どおり）。"""
    d1 = _w("rslt/ver_4_1/")
    d2 = _w(f"rslt/ver_4_1/rslt{bango:04d}")
    for d in (d1, d2):
        try:
            os.mkdir(d, 0o755)
        except OSError:
            pass          # 原本も mkdir の戻り値を見ていない
    return d2
