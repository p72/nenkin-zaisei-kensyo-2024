# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/fileio.cpp の忠実移植（ファイルの開閉）
=============================================================
②は `map<string, FILE*> fp_map` に名前でファイルを登録する。
①④⑤⑥のように配列の添字で持つのではなく**文字列のキー**なので、
どのファイルが何に使われるかが読みやすい。

制度ごとに開き直す
------------------
`fopn()` は `sepsd()` の頭で制度（`pseid` = 0 厚年 / 1 国共 / 4 地共 /
5 私学）ごとに呼ばれ、`fcls()` が最後に全部閉じる。
制度名は `cseid[pseid]` で `"kou"` `"kok"` `"ren"` `"sig"`。

読むファイル（`pseid == 0`・`key == 11`・`flg_part == 0` のとき14本）
--------------------------------------------------------------------
    kisor            emp/data/u-rev/kisor/kisor_{seid}2024.csv
    hou              emp/data/u-rev/kisor/hou_{seid}2024.csv
    sikur            emp/data/u-rev/kisor/sikur_{seid}2024.csv
    yuizor           emp/data/u-rev/kisor/yuizor_{seid}2024.csv
    qx               emp/data/u-sinj/QX-{M,H,L}2023.csv   ← seimei で選ぶ
    kragsg           emp/data/u-rev/kisor/kragsg_2024.csv
    hk-1 / hk-2      emp/data/u-rev/kisos/{seid}/hk2021-{1,2}.csv
    hk-3             同 hk2021-3.csv（**厚年だけ**）
    jk-1 / jk-2      emp/data/u-rev/kisos/{seid}/jk2021-{1,2}.csv
    jk-3             同 jk2021-3.csv（**厚年だけ**）
    waku-population  wakuc/rslt/ver_4_1/rslt{外枠}/waku{外枠}-20.csv
    waku             同 -05（厚年）/ -08（国共）/ -09（地共）/ -10（私学）
    waku-s3          同 -06（**厚年だけ**）
    waku-part-all    同 -07（**厚年だけ**）
    waku-part202410  同 -22（**厚年だけ**）
    waku-part30-op   同 -30（厚年かつ `flg_part >= 1`）
    waku-part20-30-op 同 -31（同）
    waku-part10-20-op 同 -32（厚年かつ `flg_part == 4`）
    econ             emp/data/u-rev/econ/econ-{経済}.csv

書くファイル（`key == 11` のとき）
----------------------------------
    prog        emp/rslt/u-rev/PROG.log         進捗（`-DDEBUG` のときだけ書く）
    sh          .../shus/shus.{試算}_{seid}      収支の素
    shg         .../shus/shusg.{試算}_{seid}
    kiso        .../kiso/kiso.{試算}_{seid}      ④基礎年金へ渡す
    bunpu_bb    .../bunpu/bunpu_bb.{試算}_{seid}.csv   ⑥分布推計へ渡す
    bunpu_g     .../bunpu/bunpu_g.{試算}_{seid}.csv    同
    kaitea/kaiteb .../kaite/kaite{a,b}-{試算}-{経済}e  （**厚年だけ**）
    prtfil      emp/rslt/u-rev/PRTFIL_1_0
    hikaku      .../hikaku/hikaku.{試算}
    ashimoto ほか4本  .../ashimoto/...
    hou_out / hou2_out / kisor_out / sikr_out

`hikaku` と `ashimoto*` は2制度目以降が追記（`"a"`）
----------------------------------------------------
`pstat_written` が `false` のあいだは `"w"`、以降は `"a"`。
制度（厚年→国共→地共→私学）の4回ぶんを1つのファイルに積む。

原本の癖をそのまま残しているところ
----------------------------------
1. **`stringstream` を1つ使い回して3回書き読みする**（`fileio.cpp:21-30`）。

   ```cpp
   stringstream ss;
   ss << setw(4) << setfill('0') << iname << "\n";  ss >> cname;
   ss << setw(4) << setfill('0') << iwname << "\n"; ss >> cwname;
   ss << setw(4) << setfill('0') << iecon << "\n";  ss >> cecon;
   ```

   `>>` が `'\n'` を**読み残す**ので eofbit が立たず、次の `<<` が効く。
   もし `"\n"` を付けずに書いていたら1回目の `>>` で eofbit が立ち、
   2回目以降は**空文字列のまま**になってパスが壊れる。
   紙一重で動いている。（`検証/原本の不具合.md`）

2. **局所の `string cseid[8]` がグローバルの `cseid[8]` を隠す**
   （`fileio.cpp:18-19` と `common/_variables.h:62`）。
   グローバルの方は**1回も代入されない**（34本の .cpp を `grep` した）。
   デッドコード。

3. **`cseid[2]` `cseid[3]` `cseid[6]` `cseid[7]` が空文字列。**
   `pseid` は 0・1・4・5 しか回らない（`main.cpp:41` が 2・3 を
   `continue` する）ので届かない。

4. **`base_dir` が絶対パスの決め打ち**（`fileio.cpp:39`）。
   原本は `/suuri/rev2024`。`run_pipeline.sh` が書き換える。
   移植版は環境変数 `SUURI_PREFIX` で差し替える（①⑤と同じ）。

5. **`fcls()` が `fp_map` の全要素を無条件に閉じる。**
   `econ.cpp:519-520` が `fp_map["kaitea"]` を `operator[]` で引くため、
   厚年以外では **NULL 要素が挿入される**。`fclose(NULL)` は glibc で
   SEGV になるので移植パッチでガードしてある
   （`検証/原本の不具合.md` A2）。

6. **`readpath_map` は `flck()` が使うだけ。**読み込み用に開いた
   ファイルのパスを控えておき、`flck()` が行数を数え直す。
"""
import os
import sys

from csvio import Reader
from glva import G

__all__ = ["fopn", "fcls", "syspath", "SEID_NAME"]

# `cseid[pseid]`（`fileio.cpp:33-36`）。2・3・6・7 は空のまま（癖 3.）
SEID_NAME = ["kou", "kok", "", "", "ren", "sig", "", ""]

def syspath(rel):
    """原本の絶対パスを `SUURI_PREFIX` で差し替える（癖 4.）。

        SUURI_PREFIX 未設定  →  <リポジトリ>/work/suuri/rev2024   （既定）
        SUURI_PREFIX=/tmp/x  →  /tmp/x/suuri/rev2024

    ①⑤の `fopn.py` と同じ規則。
    """
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        return os.path.join(repo, "work", "suuri", "rev2024", rel)
    return os.path.join(prefix, "suuri", "rev2024", rel)


def _open_and_add_map(rel, mode, keystr):
    """fileio.cpp:310 の `open_and_add_map`。"""
    fullpath = syspath(rel)
    if mode == "r":
        if not os.path.isfile(fullpath):
            print("%s を開くのに失敗しました。" % fullpath, file=sys.stderr)
            raise ValueError("fopen did not succeed.")
        fp = Reader(fullpath, mode)
    else:
        d = os.path.dirname(fullpath)
        if not os.path.isdir(d):
            print("%s を開くのに失敗しました。" % fullpath, file=sys.stderr)
            raise ValueError("fopen did not succeed.")
        # 原本（UTF-8 に変換した木）と同じバイト列を書くので UTF-8
        fp = open(fullpath, mode[0] + "t", encoding="utf-8", newline="\n")

    if keystr in G.fp_map:
        print('fp_map["%s"] は既に存在します。' % keystr, file=sys.stderr)
        raise ValueError("std::map key already exists. keystr = " + keystr)
    G.fp_map[keystr] = fp
    if mode == "r":
        G.readpath_map[keystr] = fullpath


def fopn():
    """fileio.cpp:12 の忠実移植。"""
    # 癖 1. `stringstream` の使い回し。結果は「4桁ゼロ詰め」と同じ
    cname = "%04d" % G.iname
    cwname = "%04d" % G.iwname
    cecon = "%04d" % G.iecon

    cseid = list(SEID_NAME)        # 癖 2. 局所がグローバルを隠す
    seid = cseid[G.pseid]

    _open_and_add_map("emp/rslt/u-rev/PROG.log", "w", "prog")

    _open_and_add_map("emp/data/u-rev/kisor/kisor_%s2024.csv" % seid,
                      "r", "kisor")
    _open_and_add_map("emp/data/u-rev/kisor/hou_%s2024.csv" % seid,
                      "r", "hou")
    _open_and_add_map("emp/data/u-rev/kisor/sikur_%s2024.csv" % seid,
                      "r", "sikur")
    _open_and_add_map("emp/data/u-rev/kisor/yuizor_%s2024.csv" % seid,
                      "r", "yuizor")

    if G.seimei == 4:
        qx = "emp/data/u-sinj/QX-M2023.csv"
    elif G.seimei == 5:
        qx = "emp/data/u-sinj/QX-H2023.csv"
    elif G.seimei == 6:
        qx = "emp/data/u-sinj/QX-L2023.csv"
    else:
        # 原本は `fullpath` が前の値のまま残る（`assert` で先に止まる）
        raise ValueError("seimei = %d（cntl の assert で止まるはず）" % G.seimei)
    _open_and_add_map(qx, "r", "qx")

    _open_and_add_map("emp/data/u-rev/kisor/kragsg_2024.csv", "r", "kragsg")

    _open_and_add_map("emp/data/u-rev/kisos/%s/hk2021-1.csv" % seid,
                      "r", "hk-1")
    _open_and_add_map("emp/data/u-rev/kisos/%s/hk2021-2.csv" % seid,
                      "r", "hk-2")
    if G.pseid == 0:
        _open_and_add_map("emp/data/u-rev/kisos/%s/hk2021-3.csv" % seid,
                          "r", "hk-3")

    _open_and_add_map("emp/data/u-rev/kisos/%s/jk2021-1.csv" % seid,
                      "r", "jk-1")
    _open_and_add_map("emp/data/u-rev/kisos/%s/jk2021-2.csv" % seid,
                      "r", "jk-2")
    if G.pseid == 0:
        _open_and_add_map("emp/data/u-rev/kisos/%s/jk2021-3.csv" % seid,
                          "r", "jk-3")

    wdir = "wakuc/rslt/ver_4_1/rslt%s/waku%s" % (cwname, cwname)
    _open_and_add_map(wdir + "-20.csv", "r", "waku-population")

    _WAKU = {0: "-05.csv", 1: "-08.csv", 4: "-09.csv", 5: "-10.csv"}
    _open_and_add_map(wdir + _WAKU[G.pseid], "r", "waku")

    if G.pseid == 0:
        _open_and_add_map(wdir + "-06.csv", "r", "waku-s3")
        _open_and_add_map(wdir + "-07.csv", "r", "waku-part-all")
        _open_and_add_map(wdir + "-22.csv", "r", "waku-part202410")

        if G.flg_part >= 1:
            _open_and_add_map(wdir + "-30.csv", "r", "waku-part30-op")
            _open_and_add_map(wdir + "-31.csv", "r", "waku-part20-30-op")
            if G.flg_part == 4:
                _open_and_add_map(wdir + "-32.csv", "r",
                                  "waku-part10-20-op")

    _open_and_add_map("emp/data/u-rev/econ/econ-%s.csv" % cecon, "r", "econ")

    # ---- 過去分・受給者分の組み合わせの検査 ----
    syutsuerr = 0
    saimushu = ""

    if G.key == 12:
        if G.pslsi == 2 and G.pslsi2 == 1:
            if G.psly == 25:
                saimushu = "AK"
            else:
                syutsuerr = 1
        else:
            syutsuerr = 1

    if G.key == 13:
        if G.pslsi == 0 and G.pslsi2 == 1:
            if G.psly == 22:
                saimushu = "CJ"
            else:
                syutsuerr = 1
        elif G.pslsi == 2 and G.pslsi2 == 1:
            if G.psly == 25:
                saimushu = "AJ"
            else:
                syutsuerr = 1
        else:
            syutsuerr = 1

    if syutsuerr == 1:
        print("現在設定外の組み合わせです。 psly = %d, kzn = %d, "
              % (G.psly, G.kzn), file=sys.stderr)
        raise ValueError("syutsuerr")

    # ---- 書き出すファイル ----
    u_dir = "emp/rslt/u-rev"
    shisan_id = "%s-%s-%s" % (cname, cecon, cwname)
    shisan_id_seid = "%s_%s" % (shisan_id, seid)

    fullpath = ""
    if G.key == 11:
        fullpath = u_dir + "/shus/shus." + shisan_id_seid
    elif G.key == 12 or G.key == 13:
        fullpath = u_dir + "/shus/shus." + saimushu + shisan_id_seid
    if fullpath:
        _open_and_add_map(fullpath, "w", "sh")

    if G.key == 11:
        _open_and_add_map(u_dir + "/shus/shusg." + shisan_id_seid,
                          "w", "shg")

    if G.pseid == 0 or G.konen != 1:
        if G.key == 11:
            fullpath = u_dir + "/kiso/kiso." + shisan_id_seid
        elif G.key == 12 or G.key == 13:
            fullpath = u_dir + "/kiso/kiso." + saimushu + shisan_id_seid
        _open_and_add_map(fullpath, "w", "kiso")

    if G.key == 11:
        _open_and_add_map(u_dir + "/bunpu/bunpu_bb." + shisan_id_seid
                          + ".csv", "w", "bunpu_bb")
        _open_and_add_map(u_dir + "/bunpu/bunpu_g." + shisan_id_seid
                          + ".csv", "w", "bunpu_g")

    if G.kaite == 1:
        if G.pseid == 0:
            _open_and_add_map(
                u_dir + "/kaite/kaitea-" + cname + "-" + cecon + "e",
                "w", "kaitea")
            _open_and_add_map(
                u_dir + "/kaite/kaiteb-" + cname + "-" + cecon + "e",
                "w", "kaiteb")

    _open_and_add_map("emp/rslt/u-rev/PRTFIL_1_0", "w", "prtfil")

    pstat_write_mode = "a" if G.pstat_written else "w"

    if G.key == 11 and G.nenbeex == 0:
        _open_and_add_map(u_dir + "/hikaku/hikaku." + shisan_id,
                          pstat_write_mode, "hikaku")
        _open_and_add_map(u_dir + "/ashimoto/ashimoto." + shisan_id,
                          pstat_write_mode, "ashimoto")
        _open_and_add_map(u_dir + "/ashimoto/ashimotos." + shisan_id,
                          pstat_write_mode, "ashimotos")
        _open_and_add_map(u_dir + "/ashimoto/ashimotosum." + shisan_id,
                          pstat_write_mode, "ashimotosum")
        _open_and_add_map(u_dir + "/ashimoto/ashimotossum." + shisan_id,
                          pstat_write_mode, "ashimotossum")
    elif G.key == 13 and G.nenbeex == 0:
        _open_and_add_map(u_dir + "/hikaku/hikaku." + saimushu + shisan_id,
                          pstat_write_mode, "hikaku")

    G.pstat_written = True

    if G.key == 11:
        if G.nenbeex == 0:
            _open_and_add_map(u_dir + "/hou/hou." + shisan_id_seid + ".csv",
                              "w", "hou_out")
            _open_and_add_map(u_dir + "/hou/hou2." + shisan_id_seid + ".csv",
                              "w", "hou2_out")
            _open_and_add_map(
                u_dir + "/kisor/kisor." + shisan_id_seid + ".csv",
                "w", "kisor_out")
            _open_and_add_map(u_dir + "/kisor/sikr." + shisan_id_seid + ".csv",
                              "w", "sikr_out")


def fcls():
    """fileio.cpp:329 の忠実移植。

    癖 5. `None`（原本の NULL）は飛ばす。移植パッチと同じふるまい。
    """
    for _key, fp in sorted(G.fp_map.items()):
        if fp is None:
            continue
        fp.close()
    G.fp_map.clear()
    G.readpath_map.clear()
