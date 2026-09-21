# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/fopn.c の忠実移植
===============================================
入出力ファイルを全部開く。ファイル名の組み立て（sprintf）を1つずつ写す。
ここを間違えると「別のケースの入力を読んで、それらしい数字が出る」という
一番たちの悪い失敗をするので、原本の書式文字列をコメントに残してある。

SYSPATH の扱い
--------------
原本は `/suuri/rev2024` という絶対パス（専用UNIXサーバの固定構成が前提
だった名残。仕様書 §12.1）。ルート直下に書けない環境でも動くように、
`検証/suuri_env.py` と同じ規則でプレフィックスを付け替える。

    SUURI_PREFIX 未設定  →  <リポジトリ>/work/suuri/rev2024   （既定）
    SUURI_PREFIX=/       →  /suuri/rev2024                    （従来どおり）

`検証/実行/run_pipeline.sh` もビルド時に同じ置き換えをしているので、
C 版と Python 版が同じ場所を読み書きする。
"""
import os

from cfile import copen
from glva import G

# fopn.c:11-14 の配列。C の char[..][..] は寸法も意味を持つのでコメントに残す。
pseid_name = ["tou", "kou", "kok", "ren", "sig"]      # char pseid_name[5][4]
useid_name = ["kou", "kok", "jnr", "tob", "ren", "sig", "nou", "oku"]
kaisho_nm = ["", "d", "e"]                            # char kaisho_nm[3][2]
nenbe = ["", "-ex"]                                   # char nenbe[2][4]


def syspath():
    """原本の SYSPATH（"/suuri/rev2024"）に対応する実際の場所。"""
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        prefix = os.path.join(repo, "work")
    prefix = prefix.rstrip("/")
    return prefix + "/suuri/rev2024"


def _die(msg):
    print(msg)
    raise SystemExit(1)


def alfopen():
    """fopn.c:8 void alfopen(void) の忠実移植。"""
    SYSPATH = syspath()

    # fopn.c:17
    flname = f"{SYSPATH}/emp/data/u-rev/econ/econ-{G.Ecfile}.csv"
    G.ifp_econ = copen(flname, "r")
    if G.ifp_econ is None:
        _die(f"econ-{G.Ecfile}ファイルのオープンに失敗しました。")

    # fopn.c:24
    if G.Saimu == 0:
        for i in range(1, 5):
            # "%s/emp/rslt/u-rev/shus/shus.%s-%s-%s_%s%s"
            flname = (f"{SYSPATH}/emp/rslt/u-rev/shus/shus."
                      f"{G.Nfile}-{G.Ecfile}-{G.Wcfile}"
                      f"_{pseid_name[i]}{nenbe[G.Nenbeex]}")
            G.ifp10_usys[i] = copen(flname, "r")
            if G.ifp10_usys[i] is None:
                _die(f"U-sysファイルのオープンに失敗しました。({flname})")
    elif G.Saimu == 1 or G.Saimu == 2:
        for i in range(1, 5):
            flname = (f"{SYSPATH}/emp/rslt/u-rev/shus/shus."
                      f"{G.Saimushu}{G.Nfile}-{G.Ecfile}-{G.Wcfile}"
                      f"_{pseid_name[i]}")
            G.ifp10_usys[i] = copen(flname, "r")
            if G.ifp10_usys[i] is None:
                _die(f"U-sysファイルのオープンに失敗しました。({flname})")

    # fopn.c:44 基礎年金拠出金
    if G.Saimu == 0:
        flname = (f"{SYSPATH}/bas/data/KYOSHUTUKIN{G.Nfile2}-{G.Nkfile}"
                  f"-{G.Ecfile}-{G.Wcfile}-{G.Cutrfile4}")
    else:
        flname = (f"{SYSPATH}/bas/data/KYOSHUTUKIN{G.Saimuski}{G.Nfile2}"
                  f"-{G.Nkfile}{G.Saimuski}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile4}")
    G.ifp_kyos = copen(flname, "r")
    if G.ifp_kyos is None:
        _die(f"基礎年金拠出金ファイルのオープンに失敗しました。({flname})")

    # fopn.c:57 妻積
    if G.Saimu == 0:
        flname = (f"{SYSPATH}/bas/rslt/TUMATUMI-{G.Nkfile}-{G.Ecfile}"
                  f"-{G.Wcfile}-{G.Cutrfile4}-{G.Tumafile}.csv")
    else:
        flname = (f"{SYSPATH}/bas/rslt/TUMATUMI-{G.Nkfile}{G.Saimuski}"
                  f"-{G.Ecfile}-{G.Wcfile}-{G.Cutrfile4}-{G.Tumafile}.csv")
    G.ifp27_tuma = copen(flname, "r")
    if G.ifp27_tuma is None:
        _die(f"妻積ファイルのオープンに失敗しました。({flname})")

    # fopn.c:69 調整期間の一致のときだけ
    if G.Touitu >= 1:
        flname = (f"{SYSPATH}/bas/data/provide{G.Nfile2}-{G.Nkfile}"
                  f"-{G.Ecfile}-{G.Wcfile}-{G.Cutrfile4}.csv")
        G.ifp_Touitu = copen(flname, "r")
        if G.ifp_Touitu is None:
            _die(f"provideのオープンに失敗しました。({flname})")

    # fopn.c:80 納付金
    flname = f"{SYSPATH}/emp/data/ez-arev/nof2024.csv"
    G.ifp_nofu = copen(flname, "r")
    if G.ifp_nofu is None:
        _die(f"納付金ファイルのオープンに失敗しました。({flname})")

    # fopn.c:88 厚年比例の改定率
    flname = (f"{SYSPATH}/emp/rslt/u-rev/kaite/kaiteb-{G.Nfile}"
              f"-{G.Ecfile}{kaisho_nm[G.Flg_Kaisho]}")
    G.ifp_kaiteb = copen(flname, "r")
    if G.ifp_kaiteb is None:
        _die(f"厚年比例の改定率ファイルのオープンに失敗しました。({flname})")

    if G.Cutrfile1[:1] == "0":
        # fopn.c:96 Saimu==6 の枝は cntl() が 0〜2 しか許さないので通らない
        if G.Saimu != 6:
            flname = (f"{SYSPATH}/emp/rslt/u-rev/kaite/kaitea-{G.Nfile}"
                      f"-{G.Ecfile}{kaisho_nm[G.Flg_Kaisho]}")
        else:
            flname = (f"{SYSPATH}/emp/rslt/u-rev/kaite/kaitea-{G.Nfile}"
                      f"{G.Saimushu}-{G.Ecfile}{kaisho_nm[G.Flg_Kaisho]}")
        G.ifp_kaitea = copen(flname, "r")
        if G.ifp_kaitea is None:
            _die(f"厚年定額の改定率ファイルのオープンに失敗しました。({flname})")
    elif G.Cutrfile1[:1] == "1":
        # fopn.c:107 国年の改定率
        if G.Flg_Kaisho == 2:
            flname = f"{SYSPATH}/nat/data/KOKUKAITE-{G.Nfile}-{G.Ecfile}E.csv"
        elif G.Flg_Kaisho == 1:
            flname = f"{SYSPATH}/nat/data/KOKUKAITE-{G.Nfile}-{G.Ecfile}D.csv"
        else:
            flname = f"{SYSPATH}/nat/data/KOKUKAITE-{G.Nfile}-{G.Ecfile}.csv"
        G.ifp_kokukaite = copen(flname, "r")
        if G.ifp_kokukaite is None:
            _die(f"国年の改定率ファイルのオープンに失敗しました。({flname})")

    # fopn.c:122 毎年のスライド調整率
    if G.Fpset != 9:
        if G.Flg_Sigo == 0:
            flname = (f"{SYSPATH}/wakuc/rslt/ver_4_1/rslt{G.Wcfile}"
                      f"/waku{G.Wcfile}-m.csv")
        elif G.Flg_Sigo == 1:
            flname = (f"{SYSPATH}/wakuc/rslt/ver_4_1/rslt{G.Wcfile2}"
                      f"/waku{G.Wcfile2}-m.csv")
        G.ifp_wakum = copen(flname, "r")
        if G.ifp_wakum is None:
            _die("毎年のスライド調整率ファイルのオープンに失敗しました。"
                 f"({flname})")

    # fopn.c:134 カット率の入力
    if G.Cutrfile1[:1] == "1" and G.Fpset == 8:
        flname = (f"{SYSPATH}/bas/rslt/cuta-{G.Nfile2}-{G.Nkfile}"
                  f"-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}.csv")
        G.ifp_bas_cuta = copen(flname, "r")
        if G.ifp_bas_cuta is None:
            _die(f"国年のカット率ファイルのオープンに失敗しました。({flname})")
    elif G.Fpset == 9:
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cutb-{G.Nfile3}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}.csv")
        G.ifp_asys_cutb = copen(flname, "r")
        if G.ifp_asys_cutb is None:
            _die(f"厚年比例のカット率ファイルのオープンに失敗しました。({flname})")
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cuta-{G.Nfile3}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}.csv")
        G.ifp_asys_cuta = copen(flname, "r")
        if G.ifp_asys_cuta is None:
            _die(f"厚年定額のカット率ファイルのオープンに失敗しました。({flname})")

    # fopn.c:159 カット率の出力
    if G.Fpset != 9:
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cuta-{G.Nfile}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}.csv")
        G.ofp_cuta = copen(flname, "w")
        if G.ofp_cuta is None:
            _die(f"カット率ファイルのオープンに失敗しました。({flname})")
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cutb-{G.Nfile}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}.csv")
        G.ofp_cutb = copen(flname, "w")
        if G.ofp_cutb is None:
            _die(f"カット率ファイルのオープンに失敗しました。({flname})")

    # fopn.c:176 調整期間の一致のときの2本目
    if G.Touitu >= 1:
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cuta-{G.Nfile}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile5}.csv")
        G.ofp_cuta2 = copen(flname, "w")
        if G.ofp_cuta2 is None:
            _die(f"カット率ファイルのオープンに失敗しました。({flname})")
        flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/cutb-{G.Nfile}"
                  f"-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile5}.csv")
        G.ofp_cutb2 = copen(flname, "w")
        if G.ofp_cutb2 is None:
            _die(f"カット率ファイルのオープンに失敗しました。({flname})")

    is_ = 0                              # 原本の変数名は is（Python では予約語）

    if G.Saimu == 0:
        for i in range(is_, 5):
            # "01shushi.%s-%s-%s-%s-%s%s%s-%s%s_%02d%s.csv"
            flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/01shushi."
                      f"{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                      f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}"
                      f"{kaisho_nm[G.Flg_Kaisho]}_{G.Fpset:02d}"
                      f"{pseid_name[i]}.csv")
            G.ofp01_shushi[i] = copen(flname, "w")
            if G.ofp01_shushi[i] is None:
                _die(f"収支出力用ファイルのオープンに失敗しました。({flname})")

        flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/03summary."
                  f"{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}"
                  f"_{G.Fpset:02d}sum.csv")
        G.ofp03_summary = copen(flname, "w")
        if G.ofp03_summary is None:
            _die(f"収支サマリファイル03のオープンに失敗しました。({flname})")

        if G.Nenbeex2 == 1:
            for i in range(is_, 5):
                flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/90nenbe."
                          f"{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                          f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}"
                          f"-{G.Cutrfile4}{kaisho_nm[G.Flg_Kaisho]}"
                          f"_{G.Fpset:02d}{pseid_name[i]}.csv")
                G.ofp90_nenbe[i] = copen(flname, "w")
                if G.ofp90_nenbe[i] is None:
                    _die("年齢別収支出力用ファイルのオープンに失敗しました。"
                         f"({flname})")

    elif G.Saimu == 1 or G.Saimu == 2:
        for i in range(is_, 5):
            flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/01shushi."
                      f"{G.Saimushu}{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                      f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}"
                      f"{kaisho_nm[G.Flg_Kaisho]}_{G.Fpset:02d}"
                      f"{pseid_name[i]}.csv")
            G.ofp01_shushi[i] = copen(flname, "w")
            if G.ofp01_shushi[i] is None:
                _die(f"収支出力用ファイルのオープンに失敗しました。({flname})")

        flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/03summary."
                  f"{G.Saimushu}{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
                  f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}-{G.Cutrfile4}"
                  f"_{G.Fpset:02d}sum.csv")
        G.ofp03_summary = copen(flname, "w")
        if G.ofp03_summary is None:
            _die(f"収支サマリファイル03のオープンに失敗しました。({flname})")

        if G.Nenbeex2 == 1:
            for i in range(is_, 5):
                flname = (f"{SYSPATH}/emp/rslt/ez_arev/shushi/90nenbe."
                          f"{G.Saimushu}{G.Nfile}-{G.Nkfile}-{G.Ecfile}"
                          f"-{G.Wcfile}"
                          f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}"
                          f"-{G.Cutrfile4}{kaisho_nm[G.Flg_Kaisho]}"
                          f"_{G.Fpset:02d}{pseid_name[i]}.csv")
                G.ofp90_nenbe[i] = copen(flname, "w")
                if G.ofp90_nenbe[i] is None:
                    _die("年齢別収支出力用ファイルのオープンに失敗しました。"
                         f"({flname})")

    # fopn.c:261 特別調整率
    flname = (f"{SYSPATH}/emp/rslt/ez_arev/cutr/Tokutyo."
              f"{G.Nfile}-{G.Nkfile}-{G.Ecfile}-{G.Wcfile}"
              f"-{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}_{G.Cutrfile4}.csv")
    G.ofp_Tokutyo = copen(flname, "w")
    if G.ofp_Tokutyo is None:
        _die(f"特別調整率のオープンに失敗しました。({flname})")
