/* ===========================================================================
 * cntl.py / main.py(set_filenum) の差分テスト用ハーネス
 * ===========================================================================
 * 原本 cntl.c と main.c を **そのままリンクして** init_gval() → cntl() →
 * set_filenum() を呼び、決まったグローバル変数を全部吐く。
 *
 * main.c には main() があるので、コンパイル時に -Dmain=orig_main を付けて
 * 名前を退避させる（main.c の中で識別子 main を使っているのは関数定義
 * だけなので、これで安全に共存できる）。原本のファイルには手を入れない。
 *
 * 標準入力は run_pipeline.sh の emp_stdin() が流すものと同じ形。
 *
 * 出力は 1 行 1 変数。
 *   i <名前> <10進>     int
 *   d <名前> <%a>       double（16進浮動小数＝無損失）
 *   s <名前> [<文字列>] char 配列
 * ======================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "set.h"
/* main.c が glvam.h を include してグローバル変数の実体を定義するので、
 * こちらは extern 宣言だけの glva.h を使う（二重定義を避ける）。 */
#include "glva.h"

void init_gval(void);
void cntl(void);
void set_filenum(void);

/* main.c の orig_main（元の main）が参照する関数のスタブ。orig_main は
 * 呼ばないが、リンカは記号を要求するので空の定義を置く。ここで見たいのは
 * init_gval() → cntl() → set_filenum() までの設定値だけ。 */
void alfopen(void)  { }
void flck(void)     { }
void econ(void)     { }
void rdfl(void)     { }
void shus(void)     { }
void alfclose(void) { }

#define PI(v) printf("i %s %d\n",  #v, (v))
#define PD(v) printf("d %s %a\n",  #v, (v))
#define PS(v) printf("s %s [%s]\n", #v, (v))

int main(void){
	init_gval();
	cntl();
	set_filenum();

	/* --- int --- */
	PI(Cntlset); PI(Seidn); PI(Pseid); PI(Useid); PI(Kijun); PI(Saimu);
	PI(Fpset); PI(Kyoskijun); PI(Ks); PI(Ke);
	PI(Kozai); PI(Flg_Kaisho); PI(Flg_Jimu); PI(Flg_Dmakuro); PI(Dmakuro_Yr);
	PI(Flg_Kmakuro); PI(Kmakuro_Yr); PI(Kmakuro_Yr2); PI(Kkuci); PI(Sienset);
	PI(Nenbeex); PI(Nenbeex2);
	PI(Flg_Rima); PI(Rima_Yr_Str); PI(Rima_Yr_End);
	PI(Flg_Part); PI(Part_Yr1); PI(Part_Yr2); PI(Part_Yr3);
	PI(Flg_Sigo);
	PI(Flg_Houjou); PI(Houjou_Yr);
	PI(Psly); PI(Pslsi); PI(Pslsi2); PI(Kzn); PI(Kzny); PI(Seitaikey);
	PI(Gaisan); PI(zaichou); PI(hiho74); PI(Touitu); PI(Touitu_mode);
	PI(zan_jimu); PI(zan_nof); PI(zan_ave); PI(zan_fund); PI(zan_model);
	PI(Flg_hanei); PI(zan_tobashi);
	PI(kakusa); PI(Flg_shunor); PI(Flg_nendo); PI(Flg_matsu);

	/* --- double --- */
	PD(Shunor); PD(Ca); PD(nendohosei);
	PD(Kmakuro_Min); PD(Drima);
	PD(Cbm_Pt1); PD(Cbm_Pt2);
	PD(Houjou_R1); PD(Houjou_R2);
	PD(Misyu); PD(Tumawake);

	/* --- char 配列 --- */
	PS(Nfile); PS(Nfile2); PS(Nfile3); PS(Nkfile);
	PS(Ecfile); PS(Wcfile); PS(Wcfile2);
	PS(Sifile);
	PS(Cutrfile1); PS(Cutrfile2); PS(Cutrfile3); PS(Cutrfile4); PS(Cutrfile5);
	PS(Tumafile);
	PS(Saimushu); PS(Saimuski); PS(Siencha);

	/* --- init_gval() が 1.0 で埋めた配列の抜き取り確認 --- */
	{
		int k, x;
		double sum_kra = 0., sum_tok = 0.;
		for(k = 0; k <= ECEDY-ECSTY; k++){
			for(x = 0; x < 116-ECXA; x++){
				sum_kra += Kra[k][x] + Krb[k][x];
				sum_tok += Scutrrh[k][x] + Scutrrt[k][x] + Scutrrki[k][x]
				         + Escutrrh[k][x] + Escutrrt[k][x] + Tokutyo[k][x];
			}
		}
		printf("d sum_Kra_Krb %a\n", sum_kra);
		printf("d sum_Scutr_etc %a\n", sum_tok);
	}

	return 0;
}
