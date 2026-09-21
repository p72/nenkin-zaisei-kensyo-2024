# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/flck.c の忠実移植
===============================================
入力ファイル（①の shus.* と ④の拠出金）の**ヘッダ部分をそのまま出力に
写し取り**、続きを読む位置をデータの先頭に合わせる。要するに
「どの入力を使ったか」を出力ファイルの先頭に記録する役目。

ここがバイト単位の再現で一番効く場所
------------------------------------
`flck.c:49` の

    fprintf(ofp01_shushi[i], "%s", char_buffer);

は入力から fgets した**生のバイト列**をそのまま流す。入力は EUC-JP なので、
出力ファイルの先頭は EUC-JP になる。一方 `flck.c:85` の「予備:」は
**ソースの文字コード**（run_pipeline.sh がビルド前に UTF-8 へ変換するので
UTF-8）で出る。つまり1つのファイルに2つの文字コードが混ざる。
だから cfile.py はバイト透過（latin-1）で扱っている。

`fgets(char_buffer, 499, ifp)` なので **1行 498 バイトで切られる**。
ヘッダ行はそれより短いので通常は影響しないが、忠実に size を渡している。
"""
from cfile import u
from glva import G
from stdfun import _sscanf_head_int


def flck():
    """flck.c:10 void flck(void) の忠実移植。"""
    if G.Seidn != 0:
        is_ = ie = 0
    else:
        if G.Cntlset == 1:
            is_ = 0
        else:
            is_ = 1
        ie = 4

    for i in range(0, 6):            # for(i=0; i<=5; i++)
        if G.Seidn != 0 and 1 <= i <= 4:
            continue
        if G.Seidn == 0 and i == 0:
            continue

        if 0 <= i <= 4:
            ifp = G.ifp10_usys[i]
        elif i == 5:
            ifp = G.ifp_kyos
        else:
            print("想定外のループです(flck.c)")
            raise SystemExit(1)

        Done = 0
        while Done == 0:
            char_buffer = ifp.fgets(499)
            if char_buffer is None:
                break
            if char_buffer[:1] == "#":
                # sscanf(char_buffer, "#%d-%d-%d", &seido, &system, &jouhou)
                seido = _sscanf_head_int(char_buffer)
                if seido == 99:
                    Done += 1
            if Done == 0:
                if i != 5:
                    G.ofp01_shushi[i].fprintf(char_buffer)
                    if G.Cntlset == 1:
                        G.ofp01_shushi[0].fprintf(char_buffer)
                else:
                    for j in range(is_, ie + 1):
                        G.ofp01_shushi[j].fprintf(char_buffer)
        if Done == 0:
            print("うまくファイルが読み込めていません。")
            raise SystemExit(1)

    for i in range(is_, ie + 1):
        fp = G.ofp01_shushi[i]
        fp.fprintf("#03-0002-0001\n")
        fp.fprintf("#03-0002-0002\n")
        fp.fprintf("#03-0002-0003\n")
        fp.fprintf("#99-0000-0000\n")

        if G.Saimu == 0:
            fp.fprintf(f"{G.Nfile}, {G.Nfile2}, {G.Nfile3}\n")
        else:
            fp.fprintf(f"{G.Saimushu}, {G.Nfile}, {G.Nfile2}, {G.Nfile3}\n")

        fp.fprintf(f"{G.Ecfile}, {G.Wcfile}\n")

        if G.Saimu == 0:
            fp.fprintf(f"{G.Nkfile}\n")
        else:
            fp.fprintf(f"{G.Saimuski}, {G.Nkfile}\n")

        # 「予備:」はソース由来なので u() でビルド時の文字コードに直す
        fp.fprintf(f"{G.Sifile}, " + u("予備:") + f", {G.Cutrfile4}, "
                   f"Cntlset:, {G.Cntlset}, Seidn:, {G.Seidn},  ii:, {i}\n")

        fp.fprintf("\n")
