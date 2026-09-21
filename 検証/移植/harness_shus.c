/* ===========================================================================
 * shus.py / shus_calc.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本を init_gval → cntl → set_filenum → alfopen → flck → econ → rdfl →
 * （shus の計算部分）まで通し、計算後の配列を CRC32 と %a で吐く。
 *
 * shus() の本体そのものではなく、出力を伴わない部分だけを同じ順序で呼ぶ。
 *
 *     shus_init(); init_premium(); shus_smodel();
 *     shus_premium(); shus_fukkjn();
 *     shus_calc0();
 *     if(Fpset==8) shus_calc8();
 *
 * 出力関数（shus_econ_out / shus_nin_out / shus_shushiout / shus_fullout）を
 * 飛ばしているが、それらが書き換えるのは Cc[21][26][27][28] と Ukyu で、
 * shus_calc8 が読むのは Cc[20] と Cc[11] だけなので、ここまでの結果は
 * 変わらない（shus_out.c:223-244 と shus_calc.c:265 を確認した）。
 *
 * main.c は main() を持つので -Dmain=orig_main でコンパイルし、orig_main が
 * 参照する shus/alfclose にはスタブを置く。shus_calc.c が print_number() を
 * 呼ぶので main.c は必ずリンクする。
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

void shus_init(void);
void init_premium(void);
void shus_premium(void);
void shus_fukkjn(void);
void shus_smodel(void);
void shus_calc0(void);
int  shus_calc8(void);
void shus_calc9(void);

/* リンクのためのスタブ。shus.c の shus() と main.c の orig_main が参照するが、
 * どちらも呼ばないので中身は空でよい。出力関数を実体で持ってこないのは、
 * 誤って走らせて Cc[21][26][27][28] や Ukyu を書き換えないため。 */
void alfclose(void)       { }
void shus_econ_out(void)  { }
void shus_nin_out(void)   { }
void shus_shushiout(int m){ (void)m; }
void shus_cutout(void)    { }
void shus_summary(void)   { }
void shus_Tokutyoout(void){ }
void shus_fullout(int m)  { (void)m; }

#define PC(v) printf("c %s %08lx %zu\n", #v, \
    (unsigned long)crc32(0L, (const Bytef *)(v), (uInt)sizeof(v)), sizeof(v))
#define PI(v) printf("i %s %d\n", #v, (v))
#define PD(v) printf("d %s %a\n", #v, (double)(v))

int main(void){
	int rc8 = -1;

	init_gval();
	cntl();
	set_filenum();
	alfopen();
	flck();
	econ();
	rdfl();

	shus_init();
	init_premium();
	shus_smodel();

	shus_premium();
	shus_fukkjn();

	shus_calc0();

	if(Fpset == 8) rc8 = shus_calc8();
	if(Fpset == 9) shus_calc9();

	printf("i rc8 %d\n", rc8);
	PI(Ks); PI(Ke);

	/* shus_init / shus_premium / shus_fukkjn */
	PC(E3dxb);
	PC(Cc);
	PC(Prema); PC(Premb);
	PC(A); PC(Aiku); PC(An); PC(Aniku);
	PC(A60); PC(A65); PC(A70);
	PC(Apart); PC(Aikupart); PC(Anpart); PC(Anikupart);
	PC(Np);

	/* shus_smodel（所得代替率の分母） */
	PC(W); PC(Kw); PC(Mkiso); PC(Mhirei);

	/* shus_calc8（調整率） */
	PC(Escutrrh); PC(Escutrrt); PC(Tokutyo);

	/* 切り分け用の代表値 */
	PD(Kw[Ke-STTY][0]);
	PD(Mkiso[Ke-STTY]);
	PD(Mhirei[Ke-STTY][0]);
	PD(Escutrrh[Ke-ECSTY][67-ECXA]);
	PD(Escutrrt[Ke-ECSTY][67-ECXA]);
	PD(Cc[0][20][Ke-STTY]);
	PD(Cc[0][11][Ke-STTY]);
	PD(Cc[0][1][Ke-STTY]);
	PD(Cc[1][20][100-STTY]);
	PD(Cc[0][19][100-STTY]);
	PD(E3dxb[0][0][100-STTY][80]);
	PD(E3dxb[0][2][100-STTY][66]);

	/* 所得代替率（看板の数字） */
	{
		double a = (Mhirei[Ke-STTY][0]*Escutrrh[Ke-ECSTY][67-ECXA]
		          + Mkiso[Ke-STTY]   *Escutrrt[Ke-ECSTY][67-ECXA])
		          / Kw[Ke-STTY][0] * 100.;
		printf("d shotoku_daitairitsu %a\n", a);
	}

	return 0;
}
