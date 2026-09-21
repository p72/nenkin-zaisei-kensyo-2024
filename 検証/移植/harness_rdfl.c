/* ===========================================================================
 * rdfl.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本を init_gval() → cntl() → set_filenum() → alfopen() → flck() →
 * econ() → rdfl() まで通し、rdfl() が埋めた配列を全部突き合わせられる形で
 * 吐く。原本のファイルには手を入れない。
 *
 * 配列が合計 628MB あって %a で全要素を出すと 1GB 近い文字列になるので、
 * **生バイト列の CRC32** を出す。NumPy の float64 配列は C の double 配列と
 * 同じメモリ配置（C 順・8B/要素）なので、Python 側の
 * `zlib.crc32(arr.tobytes())` と厳密に一致するはず。CRC32 は
 * 「1ビットでも違えば（ほぼ確実に）違う値になる」ので、ビット一致の判定に
 * 使える。合わなかったときの切り分け用に、代表的な要素を %a でも出す。
 *
 * main.c は main() を持つので -Dmain=orig_main でコンパイルし、orig_main が
 * 参照する shus/alfclose にはスタブを置く（orig_main は呼ばない）。
 * main.c が glvam.h でグローバルの実体を定義するので、こちらは glva.h。
 * ======================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <zlib.h>

#include "set.h"
#include "glva.h"

void init_gval(void);
void cntl(void);
void set_filenum(void);
void alfopen(void);
void flck(void);
void econ(void);
void rdfl(void);

/* orig_main が参照する記号のスタブ。呼ばない。 */
void shus(void)     { }
void alfclose(void) { }

/* 配列の生バイト列の CRC32 と、バイト数を出す */
#define PC(v) printf("c %s %08lx %zu\n", #v, \
    (unsigned long)crc32(0L, (const Bytef *)(v), (uInt)sizeof(v)), sizeof(v))

#define PI(v) printf("i %s %d\n", #v, (v))
#define PD(v) printf("d %s %a\n", #v, (double)(v))

int main(void){
	init_gval();
	cntl();
	set_filenum();
	alfopen();
	flck();
	econ();
	rdfl();

	/* 出力ファイルを閉じて内容を確定させる（flck が書いたヘッダを
	 * Python 側と byte 比較したいので、flush が必要）。 */
	{
		int i;
		for(i = 0; i <= 4; i++){
			if(ofp01_shushi[i] != NULL) fflush(ofp01_shushi[i]);
		}
		if(ofp_Tokutyo != NULL) fflush(ofp_Tokutyo);
	}

	PI(Ks);
	PI(Ke);

	/* rdfl_u_sys が埋めるもの */
	PC(Ap); PC(Apdum); PC(Ap65); PC(Ap70);
	PC(A); PC(Adum); PC(A60); PC(A65); PC(A70);
	PC(Aiku); PC(Aikudum); PC(Aal);
	PC(Apart); PC(Aikupart); PC(A60part); PC(A65part); PC(A70part);
	PC(An); PC(Aniku); PC(Anpart); PC(Anikupart);
	PC(T4xtp);
	PC(D3bxtp);
	PC(Kfpbxtp);
	PC(Kofbxtp); PC(Kofte); PC(Kofkk);

	/* rdfl_kyos */
	PC(Kyosdx); PC(Kfkyosdx); PC(Tumazumi); PC(Kokusyushi);

	/* rdfl_sien */
	PC(Nofu); PC(Jyutaku);

	/* rdfl_cut */
	PC(Kra); PC(Krb); PC(Scutrk1); PC(Scutrrki); PC(Scutrrh); PC(Scutrrt);

	/* econ が埋めるもの（ここまで通ったことの確認） */
	PC(Ri); PC(H); PC(Ci); PC(Ri2); PC(HCdum);
	PC(Id_Hhd); PC(Id_Cid); PC(Id_Cid_2);

	/* 合わなかったときの切り分け用に代表値を %a で */
	PD(Ap[1][0][22-STTY]);
	PD(A[1][1][30-STTY]);
	PD(An[1][1][30-STTY]);
	PD(Aal[2][0][40-STTY]);
	PD(Apart[0][24-STTY]);
	PD(T4xtp[1][1][0][25-STTY][70]);
	PD(T4xtp[1][0][0][25-STTY][70]);
	PD(D3bxtp[1][0][0][1][25-STTY][70]);
	PD(D3bxtp[0][0][0][1][25-STTY][70]);
	PD(Kfpbxtp[1][0][0][7][25-STTY][70]);
	PD(Kofbxtp[1][0][0][25-STTY][70]);
	PD(Kyosdx[0][0][0][25-STTY][70]);
	PD(Kfkyosdx[0][0][0][25-STTY][70]);
	PD(Tumazumi[1][25-STTY]);
	PD(Nofu[1][25-STTY]);
	PD(Jyutaku[25-STTY]);
	PD(Kra[25-ECSTY][67-ECXA]);
	PD(Krb[25-ECSTY][67-ECXA]);
	PD(Kra[25-ECSTY][60-ECXA]);
	PD(Scutrk1[25-ECSTY]);
	PD(Scutrrki[25-ECSTY][70-ECXA]);

	return 0;
}
