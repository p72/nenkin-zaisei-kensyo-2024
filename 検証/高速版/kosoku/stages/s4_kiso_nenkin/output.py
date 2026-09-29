# -*- coding: utf-8 -*-
"""④の受け渡しファイルの書き手（移植版の列配置）
====================================================
    KYOSHUTUKIN{V}-{予備}        ⑤へ渡す拠出金（**調整前**。⑤が cuta を掛ける）
    cuta-{V}-1120-{予備}.csv     累積調整率（2005〜2125年度 × 63〜115歳）
    TUMATUMI-…-00.csv            妻積の分配
    kekka{V}-1120-{予備}{a,b}.csv 結果（給付費・拠出金・算定対象者・独自給付・経済前提・収支見通し）
    provide{V}-{予備}.csv        調整期間一致のときだけ
    output.csv                   1行（代替率換算・終了年度）

`kekka_series` は `kekka` の数値ブロックを {ブロック名: {列名: (YEARS.n,)}} で返す
（`KisoOut.kekka` に入れる。比較ツールが読むのも同じ形）。

港: kiso_nenkin/file_write_kakyu.py:file_write_kakyu
港: kiso_nenkin/file_write_cut.py:file_write_cut
港: kiso_nenkin/printout.py:printout
仕様: §12.4
"""
import os

import numpy as np

from ...axis import YEARS, AGES
from .inputs import NS, NA, AGE_LO
from .kyufu import KYO, TOK, kokko_wariai_table

__all__ = ["kekka_series", "to_port_csv", "write_kyoshutukin", "write_cuta", "write_tumatumi",
           "write_kekka", "read_kekka", "read_kyoshutukin", "read_cuta"]

_ASCTIME_FIXED = "Thu Jan  1 00:00:00 1970\n"
_SEIDO_NAMES = ("制度計", "国年", "厚年", "国共", "地共", "私学")
_KUBUN_NAMES = ("合計", "老齢", "障害", "遺族")
_SHUNYU = ("保険料月額", "保険料収入（国年）", "保険料収入（付加年金）", "運用収入",
           "国庫（基礎年金）", "国庫（特別国庫）", "国庫（死亡一時金付加分）", "国庫（付加年金）",
           "国庫（旧法寡婦年金免除分）", "住宅融資債権", "妻積み", "こども子育て特別会計から繰入",
           "収入合計")
_SHISHUTU = ("支出合計", "死亡一時金納付分", "死亡一時金付加分", "新法寡婦年金",
             "旧法寡婦年金免除分以外", "旧法寡婦年金免除分", "付加年金", "基礎年金拠出金",
             "基礎年金拠出金（特別国庫）", "業務勘定への繰入")
_SONOTA = ("年度末積立金", "保険料改定率")
HEAD25 = _SHUNYU + _SHISHUTU + _SONOTA


def _e(v):
    return "%20.14e" % v


# ---------------------------------------------------------------- 系列

def _variant(r, which):
    """a（調整後）/ b（調整前）で使う配列。"""
    D = r.D
    if which == "b":
        return dict(kyufu=r.kyufu_b, kyo=r.kyo_b, kafu=D.kafu, ichi=D.ichijikin,
                    tumitate=r.tumitate_b, kaiteiritu=r.E.kaiteiritu)
    return dict(kyufu=r.kyufu_a, kyo=r.kyo_a, kafu=r.kafu_cut, ichi=D.ichijikin,
                tumitate=r.sol.tumitate, kaiteiritu=r.sol.kaiteiritu_cut)


def kekka_series(r, which):
    """`kekka…{a,b}` の数値ブロック。{ブロック名: {列名: (YEARS.n,)}}。"""
    pol, D, E = r.inp.pol, r.D, r.E
    v = _variant(r, which)
    K = v["kyufu"].k.K                                   # (NS, Y, NA, 2, 3, 2, 2)
    kyufu = K.sum(axis=(2, 5, 6))                        # (NS, Y, 新旧, 種類)
    tok = v["kyufu"].k.tokubetu.sum(axis=(1, 3))          # (Y, TOK.n)
    kokko = v["kyufu"].kokko_k.sum(axis=(0, 2, 3, 5))     # (Y, 種類)
    kyo = v["kyo"]
    St = r.inp.santei
    out = {}
    for name, sk in (("基礎年金給付費（新法＋旧法）", None), ("基礎年金給付費（新法）", 0),
                     ("基礎年金交付金", 1)):
        blk = {}
        kk = kyufu if sk is None else kyufu[:, :, sk:sk + 1]
        for kb_i, kb in enumerate(_KUBUN_NAMES):
            per = kk.sum(axis=(2, 3)) if kb_i == 0 else kk[:, :, :, kb_i - 1].sum(axis=2)   # (NS, Y)
            blk[kb + "/制度計"] = per.sum(axis=0)
            for s in range(NS):
                blk[kb + "/" + _SEIDO_NAMES[s + 1]] = per[s]
        out[name] = blk
    blk = {"単価": kyo.tanka[:, 0, 0], "合計": kyo.kyoshutukin[:, :, 0, 0].sum(axis=0)}
    for s in range(NS):
        blk[_SEIDO_NAMES[s + 1]] = kyo.kyoshutukin[s, :, 0, 0]
    out["基礎年金拠出金"] = blk
    blk = {"単価": kyo.tanka_kokko[:, 0, 0], "国庫負担割合(年度末)": kokko_wariai_table(pol),
           "合計": kyo.kyoshutukin_kokko[:, :, 0, 0].sum(axis=0)}
    for s in range(NS):
        blk[_SEIDO_NAMES[s + 1]] = kyo.kyoshutukin_kokko[s, :, 0, 0]
    blk["合計/種類"] = kokko.sum(axis=1)
    for kb_i, kb in enumerate(_KUBUN_NAMES[1:]):
        blk[kb] = kokko[:, kb_i]
    out["基礎年金拠出金（国庫）"] = blk
    blk = {"合計": St.all, "１号": St.by_gou[0, :, 0]}
    for s in range(1, NS):
        blk[_SEIDO_NAMES[s + 1] + "２号"] = St.by_gou[s, :, 1]
        blk[_SEIDO_NAMES[s + 1] + "３号"] = St.by_gou[s, :, 2]
    blk["産休免除者（１号再掲）"] = St.sankyu
    blk["育休免除者（１号再掲）"] = St.ikukyu
    blk["付加納付者（１号再掲）"] = D.fuka_ninzu
    out["拠出金算定対象者"] = blk
    blk = {"合計": tok.sum(axis=1)}
    for name, jp in (("menjo", "免除"), ("kasaage", "嵩上げ（納付）"), ("kasamenjo", "嵩上げ（免除）"),
                     ("shitasasae", "老福下支え"), ("gonen", "５年年金"), ("hatachimae", "２０歳前")):
        blk[jp] = tok[:, getattr(TOK, name)]
    out["特別国庫負担内訳"] = blk
    kafu, ichi = v["kafu"], v["ichi"]
    out["独自給付費等"] = {
        "死亡一時金納付分": ichi[:, 0], "死亡一時金付加分": ichi[:, 1],
        "新法寡婦年金": kafu[:, 0], "旧法寡婦年金免除分以外": kafu[:, 1], "旧法寡婦年金免除分": kafu[:, 2],
        "付加年金": D.fuka_sum, "１号被保険者数": St.hiho_kokunen, "保険料収入（国年）": D.hokenryou_y,
        "保険料収入（付加年金）": D.fuka_hokenryou_y, "住宅融資債権": D.yuushi,
        "業務勘定への繰入": D.fukushi, "こども子育て特別会計から繰入": D.kodomo_noufukin}
    kt = v["kaiteiritu"]
    out["経済前提"] = {
        "物価上昇率": E.cpi_up, "賃金上昇率": E.base_up, "運用利回り": E.interest_rate,
        "改定率（マクロ込み、67歳）": kt[:, AGES.i(67)], "改定率（マクロ込み、68歳）": kt[:, AGES.i(68)],
        "改定率（マクロ込み、88歳）": kt[:, AGES.i(88)],
        "特別調整率（67歳）": E.T[:, AGES.i(67)], "特別調整率（68歳）": E.T[:, AGES.i(68)],
        "特別調整率（88歳）": E.T[:, AGES.i(88)]}
    blk = {}
    for s in range(NS):
        blk[_SEIDO_NAMES[s + 1]] = r.tumatumi[s]
    blk["妻積残額"] = r.tumatumi_zan
    blk["国年積立金"] = v["tumitate"]
    out["妻積（各制度への分配額）"] = blk

    # ---- 収支見通し ----
    tm = v["tumitate"]
    ir = E.interest_rate
    kyo_k = kyo.kyoshutukin[0, :, 0, 0]
    kyo_kk = kyo.kyoshutukin_kokko[0, :, 0, 0]
    tok_all = tok.sum(axis=1)
    tumatumi_k = r.tumatumi[0]
    flow = (D.hokenryou_y + D.fuka_hokenryou_y + kyo_kk + tumatumi_k + D.yuushi + D.kodomo_noufukin
            - kyo_k - D.fuka_sum * 3. / 4. - ichi[:, 0] - ichi[:, 1] * 3. / 4. - kafu[:, 0] - kafu[:, 1]
            - D.fukushi)
    unyou = np.zeros(YEARS.n)
    unyou[1:] = tm[:-1] * (ir[1:] - 1.) + flow[1:] * (np.sqrt(ir[1:]) - 1.)
    unyou[:YEARS.i(pol.get("kiso.years.first_year"))] = 0.
    shunyu = (D.hokenryou_y + D.fuka_hokenryou_y + unyou + kyo_kk + tok_all + ichi[:, 1] / 4.
              + D.fuka_sum / 4. + kafu[:, 2] + D.yuushi + tumatumi_k + D.kodomo_noufukin)
    shishutu = (ichi[:, 0] + ichi[:, 1] + kafu[:, 0] + kafu[:, 1] + kafu[:, 2] + D.fuka_sum
                + kyo_k + tok_all + D.fukushi)
    cols = [r.inp.base.hokenryou_m0, D.hokenryou_y, D.fuka_hokenryou_y, unyou, kyo_kk, tok_all,
            ichi[:, 1] / 4., D.fuka_sum / 4., kafu[:, 2], D.yuushi, tumatumi_k, D.kodomo_noufukin,
            shunyu, shishutu, ichi[:, 0], ichi[:, 1], kafu[:, 0], kafu[:, 1], kafu[:, 2], D.fuka_sum,
            kyo_k, tok_all, D.fukushi, tm, E.kakaku]
    out["収支見通し"] = dict(zip(HEAD25, cols))
    return out


# ---------------------------------------------------------------- 書き手

def write_kyoshutukin(out, path, tougou=0, asctime=_ASCTIME_FIXED, first_row_year=2010,
                      data_from=2020):
    """⑤へ渡す拠出金（年度末値。調整前）。制度の並びは港のまま（2・3・6 は空）。"""
    KY = out.kyoshutukin
    zeros = ",".join([_e(0.)] * (NA + 1))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(asctime + "#99-0000-0000\n")
        for kt in (1, 2):
            fp.write("shikyu_keitai:%d\n" % kt)

            def block(seido_out, kubun, arr, s, shift):
                zero_end = data_from if shift else data_from - 1
                for y in range(first_row_year, zero_end + 1):
                    fp.write("%d,%d,%d,%s\n" % (YEARS.i(y), seido_out, kubun, zeros))
                for y in range(zero_end + 1, YEARS.last + 1):
                    if arr is None:
                        fp.write("%d,%d,%d,%s\n" % (YEARS.i(y), seido_out, kubun, zeros))
                    else:
                        row = arr[s, YEARS.i(y) - shift, :, kt] if arr.ndim == 4 else arr[YEARS.i(y) - shift, :, kt]
                        # tokubetu（3 次元）は with_totals 済みなので形態 0 = 計、1 基本、2 加給（4 次元と同じ並び）
                        fp.write("%d,%d,%d,%s\n" % (YEARS.i(y), seido_out, kubun,
                                                    ",".join(_e(x) for x in row)))

            def four(seido_out, s):
                block(seido_out, 1, KY["nendomatu_P"], s, 1)
                block(seido_out, 2, KY["nendomatu"], s, 0)
                block(seido_out, 3, KY["kokko_nendomatu_P"], s, 1)
                block(seido_out, 4, KY["kokko_nendomatu"], s, 0)

            def empty(seido_out):
                block(seido_out, 1, None, 0, 1)
                block(seido_out, 2, None, 0, 0)
                block(seido_out, 3, None, 0, 1)
                block(seido_out, 4, None, 0, 0)

            four(0, 1)            # 厚年
            four(1, 2)            # 国共
            empty(2)
            empty(3)
            four(4, 3)            # 地共
            four(5, 4)            # 私学
            empty(6)
            if tougou:
                four(7, 0)        # 国年
                block(8, 1, KY["tokubetu_nendomatu_P"], 0, 1)
                block(8, 2, KY["tokubetu_nendomatu"], 0, 0)
                block(8, 3, KY["tokubetu_nendomatu_P"], 0, 1)
                block(8, 4, KY["tokubetu_nendomatu"], 0, 0)


def write_cuta(out, path, first_year=2005):
    cr = out.cuta
    with open(path, "w", encoding="utf-8") as fp:
        for y in range(first_year, YEARS.last + 1):
            fp.write("%4d," % YEARS.i(y) + ",".join(_e(x) for x in cr[YEARS.i(y)]) + "\n")


def write_tumatumi(r, path):
    pol = r.inp.pol
    y0 = pol.get("kiso.years.tumatumi_nendo")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("%d," % YEARS.i(y0 - 1) + ",".join([_e(0.)] * NS) + "," + _e(pol.get("kiso.tumatumi_2014")) + "\n")
        for y in range(y0, YEARS.last + 1):
            i = YEARS.i(y)
            fp.write("%d," % i + ",".join(_e(r.tumatumi[s, i]) for s in range(NS))
                     + "," + _e(r.tumatumi_zan[i]) + "\n")


def write_kekka(r, which, version, path, first_year=2020):
    """`kekka…{a,b}.csv`。列の並びと書式は港と同じ。"""
    S = r.out.kekka[which]
    pol = r.inp.pol
    with open(path, "w", encoding="utf-8") as fp:
        w = fp.write
        w("試算番号,%s%s\n" % (version, which))
        w("カット終了年度,")
        if which == "a":
            k = r.kokatu_nendo
            w("%d\n" % r.sol.s_c_nendo if k == -1 else "国年が%d年度に枯渇しました\n" % k)
        else:
            w("\n")
        w("最終カット率,")
        if which == "a":
            n = r.sol.s_c_nendo if r.kokatu_nendo == -1 else r.kokatu_nendo
            w(_e(r.E.cut_ruiseki[YEARS.i(n), YEARS.i(n), 0] if n != r.sol.s_c_nendo
                 else r.sol.saisyu_cut) + "\n")
        else:
            w("\n")
        w("\n\n")
        years = range(first_year, YEARS.last + 1)
        for name in ("基礎年金給付費（新法＋旧法）", "基礎年金給付費（新法）", "基礎年金交付金"):
            w(name + "\n")
            w(",合計,,,,,,老齢,,,,,,障害,,,,,,遺族,,,,,\n")
            w(",制度計,国年,厚年,国共,地共,私学" * 4 + "\n")
            blk = S[name]
            for y in years:
                i = YEARS.i(y)
                w("%15d" % y + "".join("," + _e(blk[kb + "/" + sn][i]) for kb in _KUBUN_NAMES
                                       for sn in _SEIDO_NAMES) + "\n")
        w("基礎年金拠出金\n,単価,合計,国年,厚年,国共,地共,私学\n")
        blk = S["基礎年金拠出金"]
        for y in years:
            i = YEARS.i(y)
            w("%15d," % y + "".join(_e(blk[c][i]) + "," for c in ("単価", "合計") + _SEIDO_NAMES[1:]) + "\n")
        w("基礎年金拠出金（国庫）\n,単価,国庫負担割合(年度末),合計,国年,厚年,国共,地共,私学,合計,老齢,障害,遺族\n")
        blk = S["基礎年金拠出金（国庫）"]
        for y in years:
            i = YEARS.i(y)
            w("%15d," % y + "".join(_e(blk[c][i]) + "," for c in
                                    ("単価", "国庫負担割合(年度末)", "合計") + _SEIDO_NAMES[1:]
                                    + ("合計/種類", "老齢", "障害", "遺族")) + "\n")
        w("拠出金算定対象者\n,合計,１号,厚年２号,厚年３号,国共２号,国共３号,地共２号,地共３号,私学２号,私学３号,"
          "産休免除者（１号再掲）,育休免除者（１号再掲）,付加納付者（１号再掲）\n")
        blk = S["拠出金算定対象者"]
        cols = ["合計", "１号"] + [sn + g for sn in _SEIDO_NAMES[2:] for g in ("２号", "３号")] \
            + ["産休免除者（１号再掲）", "育休免除者（１号再掲）", "付加納付者（１号再掲）"]
        for y in years:
            i = YEARS.i(y)
            w("%15d," % y + "".join(_e(blk[c][i]) + "," for c in cols) + "\n")
        w("特別国庫負担内訳\n,合計,免除,嵩上げ（納付）,嵩上げ（免除）,老福下支え,５年年金,２０歳前\n")
        blk = S["特別国庫負担内訳"]
        for y in years:
            i = YEARS.i(y)
            w("%15d," % y + "".join(_e(blk[c][i]) + "," for c in
                                    ("合計", "免除", "嵩上げ（納付）", "嵩上げ（免除）", "老福下支え", "５年年金", "２０歳前")) + "\n")
        w("独自給付費等\n,死亡一時金納付分,死亡一時金付加分,新法寡婦年金,旧法寡婦年金免除分以外,旧法寡婦年金免除分,付加年金,"
          "１号被保険者数,保険料収入（国年）,保険料収入（付加年金）,住宅融資債権,業務勘定への繰入,こども子育て特別会計から繰入\n")
        blk = S["独自給付費等"]
        cols = list(blk)
        for y in years:
            i = YEARS.i(y)
            w("%d," % y + ",".join(_e(blk[c][i]) for c in cols) + "\n")
        w("経済前提\n,物価上昇率,賃金上昇率,運用利回り,改定率（マクロ込み、67歳）,改定率（マクロ込み、68歳）,"
          "改定率（マクロ込み、88歳）,特別調整率（67歳）,特別調整率（68歳）,特別調整率（88歳）\n")
        blk = S["経済前提"]
        cols = list(blk)
        for y in range(YEARS.first + 1, YEARS.last + 1):
            i = YEARS.i(y)
            w("%d," % y + ",".join(_e(blk[c][i]) for c in cols) + "\n")
        w("妻積（各制度への分配額）\n,国年,厚年,国共,地共,私学,妻積残額,国年積立金\n")
        y0 = pol.get("kiso.years.tumatumi_nendo")
        w("%d（原価）," % (y0 - 1) + ",".join([_e(0.)] * NS) + "," + _e(pol.get("kiso.tumatumi_2014")) + "\n")
        blk = S["妻積（各制度への分配額）"]
        cols = list(blk)
        for y in years:
            i = YEARS.i(y)
            w("%d," % y + ",".join(_e(blk[c][i]) for c in cols) + "\n")
        w("\n\n収支見通し\n")
        w("," + "".join(("収入" if k == 0 else "支出" if k == len(_SHUNYU) else
                         "その他" if k == len(_SHUNYU) + len(_SHISHUTU) else "") + ","
                        for k in range(len(HEAD25))) + "\n")
        w("年度," + "".join(h + "," for h in HEAD25) + "\n")
        blk = S["収支見通し"]
        for y in years:
            i = YEARS.i(y)
            w("%d," % y + "".join(_e(blk[h][i]) + "," for h in HEAD25) + ",\n")


def to_port_csv(r, case, directory, yobi="000", tougou=0, asctime=_ASCTIME_FIXED):
    """港と同じ名前で `directory/{data,rslt}` に書く。"""
    version = "%s-%s-%s-%s" % (case, case, case, case)
    vcut = "1120-%s" % yobi
    data = os.path.join(directory, "data")
    rslt = os.path.join(directory, "rslt")
    os.makedirs(data, exist_ok=True)
    os.makedirs(rslt, exist_ok=True)
    paths = {
        "kyoshutukin": os.path.join(data, "KYOSHUTUKIN%s-%s" % (version, yobi)),
        "cuta": os.path.join(rslt, "cuta-%s-%s.csv" % (version, vcut)),
        "tumatumi": os.path.join(rslt, "TUMATUMI-%s-%s-%s-%s-00.csv" % (case, case, case, yobi)),
        "kekka_a": os.path.join(rslt, "kekka%s-%sa.csv" % (version, vcut)),
        "kekka_b": os.path.join(rslt, "kekka%s-%sb.csv" % (version, vcut)),
        "output": os.path.join(rslt, "output.csv"),
    }
    write_kyoshutukin(r.out, paths["kyoshutukin"], tougou, asctime)
    write_cuta(r.out, paths["cuta"])
    write_tumatumi(r, paths["tumatumi"])
    write_kekka(r, "b", "%s-%s" % (version, vcut), paths["kekka_b"])
    write_kekka(r, "a", "%s-%s" % (version, vcut), paths["kekka_a"])
    with open(paths["output"], "a", encoding="utf-8") as fp:
        fp.write("%s-%s,%f,%d,\n" % (version, vcut, r.sol.daitai, r.sol.s_c_nendo))
    return paths


# ---------------------------------------------------------------- 読み手（比較用）

def read_kekka(path):
    """`kekka…csv` の数値ブロック → {ブロック名: {年度: [値…]}}。見出しは無視して列の位置で持つ。"""
    from ...io_port import lines_of
    out, cur = {}, None
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if not f:
            continue
        if f[0] and not f[0].lstrip("-").replace("（原価）", "").isdigit() and len(f) <= 2 and f[0] not in ("試算番号", "カット終了年度", "最終カット率", "年度"):
            cur = f[0]
            out[cur] = {}
            continue
        if cur is None or not f[0].lstrip("-").isdigit():
            continue
        vals = [float(x) for x in f[1:] if x != ""]
        out[cur][int(f[0])] = np.array(vals)
    return out


def read_kyoshutukin(path):
    """→ {(年度, 制度, 種別, 形態): (54,)}。"""
    from ...io_port import lines_of
    out, kt = {}, None
    for l in lines_of(path):
        if l.startswith("shikyu_keitai:"):
            kt = int(l.split(":")[1])
            continue
        f = [x.strip() for x in l.split(",")]
        if len(f) < 4 or not f[0].isdigit() or kt is None:
            continue
        y = YEARS.label(int(f[0]))                       # 港のラベル（西暦−2000）＝ 軸の添字
        out[(y, int(f[1]), int(f[2]), kt)] = np.array([float(x) for x in f[3:] if x != ""])
    return out


def read_cuta(path):
    from ...io_port import read_year_rows
    return read_year_rows(path, 2000)
