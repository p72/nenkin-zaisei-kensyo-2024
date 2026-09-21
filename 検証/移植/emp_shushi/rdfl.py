# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/rdfl.c の忠実移植
===============================================
①被保険者推計の結果（shus.*）、④基礎年金の拠出金、納付金、改定率、
カット率を読み込む。⑤の入力の全部がここを通る。

原本の癖をそのまま残しているところ
----------------------------------
1. **`dtemp` は反復をまたいで残る**
   原本の `double dtemp[100]` は関数内のローカル配列で、`rd_drec()` は
   読んだフィールドの分だけを上書きする。**クリアしない**ので、前の行より
   短い行を読むと後ろに前の値が残る。移植でも 1 つのリストを使い回す。
   （C では最初の `rd_drec()` の前は未初期化＝不定値。実際には使う前に
   必ず埋まる位置しか読んでいないので、移植では 0.0 から始める。）

2. **ヘッダ行は fgets で読み捨てるだけ**
   `fgets(rec, MAX_REC_LEN, ifp)` を数だけ合わせて呼ぶ必要がある。1 本
   ずれると以降が全部ずれるので、原本の呼び出しを 1 対 1 で写した。

3. **`if(k<Ks || k>Ke) continue;` は fgets の後に来る**
   範囲外の年度でも行は消費する。読み飛ばしと読み込みの区別が要る。

4. **`T4xtp[ii][0][ui]` と `[0][s][ui]` は足し込み先**
   s=1〜3 を s=0 に、ii=1 を ii=0 に累積する（制度合計）。
   `=` ではなく `+=` なので、初期値ゼロ（BSS）が効いている。

5. **`Ap` から `Ap70` を引いて `Ap70` をゼロにする**（rdfl.c:313-319）
   `if(s==3 && ii>1) break;` が入っているので、共済3制度では s=3 を飛ばす。
   インデントが誤解を誘う書き方だが、波括弧のとおりに写した。
"""
from cnum import nround
from glva import G
from setconst import (ECEDY, ECSTY, ECXA, ENDY, FLKE, FLKS, MAX, MAX_REC_LEN,
                      STTY, XA, XB)
from stdfun import rd_drec


def _fgets(ifp):
    """`fgets(rec, MAX_REC_LEN, ifp)` 相当。EOF なら None。"""
    return ifp.fgets(MAX_REC_LEN)


def rdfl():
    """rdfl.c:13 void rdfl(void) の忠実移植。"""
    rdfl_u_sys()
    rdfl_kyos()
    rdfl_sien()
    rdfl_cut()


def rdfl_u_sys():
    """rdfl.c:25 ①被保険者推計の結果（shus.*）を読む。"""
    num_dtemp = 100                      # sizeof dtemp / sizeof dtemp[0]
    dtemp = [0.0] * num_dtemp            # 反復をまたいで残る（原本と同じ）
    snc = [0.0] * (ENDY - STTY + 1)      # double snc[ENDY-STTY+1]={0.}

    is_ = 1
    ie = 4

    for ii in range(is_, ie + 1):
        ifp = G.ifp10_usys[ii]

        rec = _fgets(ifp)
        rd_drec(rec, dtemp, num_dtemp)
        if ii == is_:
            G.Ks = int(dtemp[0])
            G.Ke = int(dtemp[1])
            if G.Ks < STTY or ENDY < G.Ke:
                print("KsがSTTYより小さい、又は、KeがENDYより大きいです。")
                raise SystemExit(1)
        else:
            if G.Ks != int(dtemp[0]) or G.Ke != int(dtemp[1]):
                print("u-sysの出力ファイル間でKs,Keの整合性がありません"
                      f"Ks={G.Ks},{int(dtemp[0])}, Ke={G.Ke},{int(dtemp[1])}")
                raise SystemExit(1)

        # ---- 経済前提の整合チェック（rdfl.c:61） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(1, G.Ke + 1):
            rec = _fgets(ifp)
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違います(rdfl_u_sys:経済前提), K={k}")
                raise SystemExit(1)
            if k >= G.Ks and (nround(dtemp[1], 12) != nround(G.Ri[k - ECSTY], 5)
                              or nround(dtemp[2], 12) != nround(G.H[k - ECSTY], 5)):
                print("u-sysファイルと設定したeconファイルの経済前提"
                      f"（賃金、利回り）が一致しません。K={k} ")
                print(f"Ri:{dtemp[1]:.14f} ?= {float(G.Ri[k - ECSTY]):.14f}, "
                      f"H:{dtemp[2]:.14f} ?= {float(G.H[k - ECSTY]):.14f}")
                raise SystemExit(1)

        # ---- Ap / Apdum（rdfl.c:79） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(FLKS, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますAp, K={k}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.Ap[ii, s, k - STTY] = dtemp[s + 1]
            for s in range(1, 4):
                G.Apdum[ii, s, k - STTY] = dtemp[s + 4]

        # ---- Ap65 / Ap70（rdfl.c:99） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(FLKS, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますAp65, K={k}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.Ap65[ii, s, k - STTY] = dtemp[s + 1]
                G.Ap70[ii, s, k - STTY] = dtemp[s + 5]

        # ---- A / Adum / A60 / A65 / A70（rdfl.c:118） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(FLKS, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますA60, K={k}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.A[ii, s, k - STTY] = dtemp[s + 1]
            for s in range(1, 4):
                G.Adum[ii, s, k - STTY] = dtemp[s + 4]
            for s in range(0, 4):
                G.A60[ii, s, k - STTY] = dtemp[s + 8]
                G.A65[ii, s, k - STTY] = dtemp[s + 12]
                G.A70[ii, s, k - STTY] = dtemp[s + 16]

        # ---- Aiku / Aikudum（rdfl.c:143） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(FLKS, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますAiku, K={k}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.Aiku[ii, s, k - STTY] = dtemp[s + 1]
            for s in range(1, 4):
                G.Aikudum[ii, s, k - STTY] = dtemp[s + 4]

        # ---- Aal（rdfl.c:163） ----
        _fgets(ifp)
        _fgets(ifp)
        for k in range(FLKS, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますAal, K={k}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.Aal[ii, s, k - STTY] = dtemp[s + 1]

        # ---- 適用拡大分（rdfl.c:180、第1号厚生年金だけ） ----
        if ii == 1:
            _fgets(ifp)
            _fgets(ifp)
            k = G.Part_Yr2
            rec = _fgets(ifp)
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"年度が違いますPart, K={k} <> {int(dtemp[0])}")
                raise SystemExit(1)
            for s in range(0, 4):
                G.Apart[s, k - STTY] = dtemp[s + 1] * G.Cbm_Pt1 / 12.0
                G.Aikupart[s, k - STTY] = dtemp[s + 5] * G.Cbm_Pt1 / 12.0
                G.A60part[s, k - STTY] = dtemp[s + 9] * G.Cbm_Pt1 / 12.0
                G.A65part[s, k - STTY] = dtemp[s + 13] * G.Cbm_Pt1 / 12.0
                G.A70part[s, k - STTY] = dtemp[s + 17] * G.Cbm_Pt1 / 12.0
            if G.Flg_Part >= 1:
                k = G.Part_Yr3
                rec = _fgets(ifp)
                rd_drec(rec, dtemp, num_dtemp)
                if int(dtemp[0]) != k:
                    print(f"年度が違いますPart, K={k} <> {int(dtemp[0])}")
                    raise SystemExit(1)
                for s in range(0, 4):
                    G.Apart[s, k - STTY] = dtemp[s + 1] * G.Cbm_Pt1 / 12.0
                    G.Aikupart[s, k - STTY] = dtemp[s + 5] * G.Cbm_Pt1 / 12.0
                    G.A60part[s, k - STTY] = dtemp[s + 9] * G.Cbm_Pt1 / 12.0
                    G.A65part[s, k - STTY] = dtemp[s + 13] * G.Cbm_Pt1 / 12.0
                    G.A70part[s, k - STTY] = dtemp[s + 17] * G.Cbm_Pt1 / 12.0

        # ---- An / Aniku（春季の補正 Shunor を掛ける。rdfl.c:215） ----
        for s in range(0, 4):
            for k in range(G.Ks, G.Ke + 1):
                if ii == 1:
                    snc[k - STTY] = G.Shunor
                else:
                    snc[k - STTY] = 1.0

                G.An[ii, s, k - STTY] = G.A[ii, s, k - STTY] * snc[k - STTY]
                G.Aniku[ii, s, k - STTY] = G.Aiku[ii, s, k - STTY] * snc[k - STTY]
                if ii == 1:
                    G.Anpart[s, k - STTY] = G.Apart[s, k - STTY] * snc[k - STTY]
                    G.Anikupart[s, k - STTY] = G.Aikupart[s, k - STTY] * snc[k - STTY]

        # ---- T4xtp（rdfl.c:231）s=0 は s=1〜3 の合計 ----
        for x in range(XA - 1, XB + 1):
            for s in range(1, 4):
                _fgets(ifp)
                _fgets(ifp)
                for k in range(FLKS, FLKE + 1):
                    rec = _fgets(ifp)
                    if k < G.Ks or k > G.Ke:
                        continue
                    rd_drec(rec, dtemp, num_dtemp)
                    if int(dtemp[0]) != k:
                        print(f"年度が違いますT4X, K={k}")
                        raise SystemExit(1)
                    for ui in range(0, 7):
                        G.T4xtp[ii, s, ui, k - STTY, x] = dtemp[ui + 1]
                        G.T4xtp[ii, 0, ui, k - STTY, x] += dtemp[ui + 1]

        # ---- D3bxtp / Kfpbxtp / Kofbxtp / Kofte / Kofkk（rdfl.c:252） ----
        #      ii==1 のときは ii=0（4制度合計）にも足し込む
        for x in range(XA - 1, XB + 1):
            for s in range(0, 4):
                for ui in range(0, 14):
                    _fgets(ifp)
                    _fgets(ifp)
                    for k in range(FLKS, FLKE + 1):
                        rec = _fgets(ifp)
                        if k < G.Ks or k > G.Ke:
                            continue
                        rd_drec(rec, dtemp, num_dtemp)
                        if int(dtemp[0]) != k:
                            print(f"年度が違いますD3BX, K={k}")
                            raise SystemExit(1)
                        G.Kfpbxtp[ii, s, ui, 7, k - STTY, x] = dtemp[1]
                        G.D3bxtp[ii, s, ui, 1, k - STTY, x] = dtemp[2]
                        for uj in range(3, 8):
                            G.D3bxtp[ii, s, ui, uj, k - STTY, x] = dtemp[uj]
                        G.Kofbxtp[ii, s, ui, k - STTY, x] = dtemp[8]
                        G.Kofte[ii, s, ui, k - STTY, x] = dtemp[9]
                        G.Kofkk[ii, s, ui, k - STTY, x] = dtemp[10]

                        if ii == 1:
                            G.Kfpbxtp[0, s, ui, 7, k - STTY, x] += dtemp[1]
                            G.D3bxtp[0, s, ui, 1, k - STTY, x] += dtemp[2]
                            for uj in range(3, 8):
                                G.D3bxtp[0, s, ui, uj, k - STTY, x] += dtemp[uj]
                            G.Kofbxtp[0, s, ui, k - STTY, x] += dtemp[8]
                            G.Kofte[0, s, ui, k - STTY, x] += dtemp[9]
                            G.Kofkk[0, s, ui, k - STTY, x] += dtemp[10]

        # ---- Kfpbxtp の uj=1,2（rdfl.c:290） ----
        for x in range(XA - 1, XB + 1):
            for ui in range(0, 14):
                _fgets(ifp)
                _fgets(ifp)
                for k in range(FLKS, FLKE + 1):
                    rec = _fgets(ifp)
                    if k < G.Ks or k > G.Ke:
                        continue
                    rd_drec(rec, dtemp, num_dtemp)
                    if int(dtemp[0]) != k:
                        print(f"年度が違いますKFPBX, K={k} <> {int(dtemp[0])}")
                        raise SystemExit(1)
                    for s in range(0, 4):
                        for uj in range(1, 3):
                            G.Kfpbxtp[ii, s, ui, uj, k - STTY, x] = dtemp[s * 2 + uj]
                            if ii == 1:
                                G.Kfpbxtp[0, s, ui, uj, k - STTY, x] += dtemp[s * 2 + uj]

        # ---- Ap から Ap70 を引いて Ap70 をゼロに（rdfl.c:313） ----
        for s in range(0, 4):
            if s == 3 and ii > 1:
                break
            for k in range(G.Ks, G.Ke + 1):
                G.Ap[ii, s, k - STTY] -= G.Ap70[ii, s, k - STTY]
                G.Ap70[ii, s, k - STTY] = 0.


def rdfl_kyos():
    """rdfl.c:325 ④基礎年金の拠出金と妻積を読む。"""
    num_dtemp = 100
    dtemp = [0.0] * num_dtemp

    ifp = G.ifp_kyos

    if G.Touitu == 0:
        ss_end = 6                       # rdfl.c:341 for(ss=0; ss<=6; ss++)
    else:
        ss_end = 8                       # rdfl.c:368 for(ss=0; ss<=8; ss++)

    for sh in range(0, 2):
        _fgets(ifp)
        for ss in range(0, ss_end + 1):
            for ii in range(1, 5):
                for k in range(FLKS - 5, FLKE + 1):
                    rec = _fgets(ifp)
                    if k < G.Ks or k > G.Ke:
                        continue
                    rd_drec(rec, dtemp, num_dtemp)
                    if (int(dtemp[0]) != k or int(dtemp[1]) != ss
                            or int(dtemp[2]) != ii):
                        print(f"基礎年金拠出金の読ませ方が違います。, K={k}")
                        print(rec, end="")
                        raise SystemExit(1)
                    for x in range(XA - 1, XB + 1):
                        if ii <= 2:
                            G.Kyosdx[sh, ss, ii - 1, k - STTY, x] = \
                                dtemp[4 + x - (XA - 1)]
                        else:
                            G.Kfkyosdx[sh, ss, ii - 3, k - STTY, x] = \
                                dtemp[4 + x - (XA - 1)]

    # ---- 妻積（rdfl.c:393） ----
    ifp = G.ifp27_tuma
    _fgets(ifp)
    for k in range(15, FLKE + 1):
        rec = _fgets(ifp)
        if k < G.Ks or k > G.Ke:
            continue
        rd_drec(rec, dtemp, num_dtemp)
        if int(dtemp[0]) != k:
            print(f"妻積ファイルの読ませ方が違います k={k}, {int(dtemp[0])}")
            raise SystemExit(1)
        for ii in range(1, 5):
            G.Tumazumi[ii, k - STTY] = dtemp[ii + 1]

    # ---- provide（調整期間の一致のときだけ。rdfl.c:410） ----
    if G.Touitu >= 1:
        ifp = G.ifp_Touitu
        _fgets(ifp)
        for k in range(20, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"provideファイルの読ませ方が違います k={k}, "
                      f"{int(dtemp[0])}")
                raise SystemExit(1)
            for ii in range(0, 5):
                G.Kokusyushi[ii, k - STTY] = dtemp[ii + 1]

        _fgets(ifp)
        _fgets(ifp)
        _fgets(ifp)
        for k in range(20, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"provideファイルの読ませ方が違います k={k}, "
                      f"{int(dtemp[0])}")
                raise SystemExit(1)
            for ii in range(0, 4):
                G.Kokusyushi[ii + 5, k - STTY] = dtemp[ii + 1]

        _fgets(ifp)
        _fgets(ifp)
        _fgets(ifp)
        for k in range(20, FLKE + 1):
            rec = _fgets(ifp)
            if k < G.Ks or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"provideファイルの読ませ方が違います k={k}, "
                      f"{int(dtemp[0])}")
                raise SystemExit(1)
            G.Kokusyushi[9, k - STTY] = dtemp[1]


def rdfl_sien():
    """rdfl.c:463 納付金（と住宅）を読む。"""
    num_dtemp = 100
    dtemp = [0.0] * num_dtemp

    ifp = G.ifp_nofu

    _fgets(ifp)
    _fgets(ifp)

    for k in range(22, 56):              # for(k=22; k<=55; k++)
        rec = _fgets(ifp)
        if k < STTY or k > ENDY:
            continue
        rd_drec(rec, dtemp, num_dtemp)
        if int(dtemp[0]) != k:
            print(f"納付金の読ませ方が違います。, K={k} <> {int(dtemp[0])}")
            raise SystemExit(1)

        G.Nofu[1, k - STTY] = dtemp[1]
        G.Jyutaku[k - STTY] = dtemp[2]
        G.Nofu[0, k - STTY] = dtemp[1]


def rdfl_cut():
    """rdfl.c:494 改定率とカット率を読む。"""
    num_dtemp = 100
    dtemp = [0.0] * num_dtemp

    # ---- 厚年比例の改定率 → Krb ----
    ifp = G.ifp_kaiteb
    for k in range(5, FLKE + 1):
        rec = _fgets(ifp)
        if k < ECSTY or k > G.Ke:
            continue
        rd_drec(rec, dtemp, num_dtemp)
        if int(dtemp[0]) != k:
            print("厚年比例改定率ファイルの読ませ方が違います。, "
                  f"K={k} <> {int(dtemp[0])}")
            raise SystemExit(1)
        for x in range(67, XB + 1):
            G.Krb[k - ECSTY, x - ECXA] = dtemp[1 + (x - 67)]

    # ---- 厚年定額 or 国年の改定率 → Kra ----
    if G.Cutrfile1[:1] == "0":
        ifp = G.ifp_kaitea
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print("厚年定額改定率ファイルの読ませ方が違います。, "
                      f"K={k} <> {int(dtemp[0])}")
                raise SystemExit(1)
            for x in range(67, XB + 1):
                G.Kra[k - ECSTY, x - ECXA] = dtemp[1 + (x - 67)]
    elif G.Cutrfile1[:1] == "1":
        ifp = G.ifp_kokukaite
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > G.Ke:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print(f"国年改定率ファイルの読ませ方が違います。, K={k}")
                raise SystemExit(1)
            for x in range(67, XB + 1):
                G.Kra[k - ECSTY, x - ECXA] = dtemp[1 + (x - 67)]
    else:
        print("Cutrfile1(厚年先決めor国年先決め)がうまく設定されていません。")
        raise SystemExit(1)

    # ---- 67歳未満は67歳の値で埋める（rdfl.c:555） ----
    for k in range(MAX(5, ECSTY), G.Ke + 1):
        for x in range(ECXA, 67):
            G.Kra[k - ECSTY, x - ECXA] = G.Kra[k - ECSTY, 67 - ECXA]
            G.Krb[k - ECSTY, x - ECXA] = G.Krb[k - ECSTY, 67 - ECXA]

    # ---- 毎年のスライド調整率 → Scutrk1 ----
    if G.Fpset != 9:
        ifp = G.ifp_wakum
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > ECEDY:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k + 2000:      # このファイルだけ西暦
                print("調整率ファイルの読ませ方が違います。, "
                      f"K={k} <> {int(dtemp[0]) - 2000}")
                raise SystemExit(1)
            G.Scutrk1[k - ECSTY] = dtemp[1]

    # ---- 国年のカット率 → Scutrrki ----
    if G.Fpset == 8 and G.Cutrfile1[:1] == "1":
        ifp = G.ifp_bas_cuta
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > ECEDY:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print("国年カット率ファイルの読ませ方が違います。, "
                      f"K={k} <> {int(dtemp[0])}")
                raise SystemExit(1)
            for x in range(XA - 1, 116):
                G.Scutrrki[k - ECSTY, x - ECXA] = dtemp[1 + (x - (XA - 1))]

    # ---- カット率ファイル指定のとき（Fpset==9） ----
    if G.Fpset == 9:
        ifp = G.ifp_asys_cutb
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > ECEDY:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print("厚年比例カット率ファイルの読ませ方が違います。, "
                      f"K={k} <> {int(dtemp[0])}")
                raise SystemExit(1)
            for x in range(XA - 1, 116):
                G.Scutrrh[k - ECSTY, x - ECXA] = dtemp[1 + (x - (XA - 1))]

        ifp = G.ifp_asys_cuta
        for k in range(5, FLKE + 1):
            rec = _fgets(ifp)
            if k < ECSTY or k > ECEDY:
                continue
            rd_drec(rec, dtemp, num_dtemp)
            if int(dtemp[0]) != k:
                print("厚年定額カット率ファイルの読ませ方が違います。, "
                      f"K={k} <> {int(dtemp[0])}")
                raise SystemExit(1)
            for x in range(XA - 1, 116):
                G.Scutrrt[k - ECSTY, x - ECXA] = dtemp[1 + (x - (XA - 1))]
