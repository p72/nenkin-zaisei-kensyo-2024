/* ===========================================================================
 * econ.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本 プログラム/厚生年金/収支計算/econ.c と stdfun.c を **そのまま
 * リンクして** 呼び出し、計算後のグローバル配列を %a（16進浮動小数）で出す。
 * %a は double を無損失で文字列化するので、Python 側とビット単位で
 * 突き合わせられる。原本には一切手を入れない。
 *
 * glvam.h がグローバル変数の実体を定義する（econ.c 側は glva.h で extern
 * 宣言しているだけ）。なのでこのハーネスだけが glvam.h を include する。
 *
 * init_gval() は main.c にあり main() ごと持ってこられないが、econ() が
 * 触る配列（Ri, H, Ci, Ri2, HCdum, Id_Hhd, Id_Cid, Id_Cid_2）はどれも
 * econ() 自身が埋めるか BSS のゼロのままなので、呼ばなくても結果は同じ。
 * Python 側も init_gval() を呼ばずに揃えてある。
 *
 * 使い方:
 *   ./harness_econ <econ-XXXX.csv> <zan_jimu>
 * ======================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "set.h"
#include "glvam.h"

void econ(void);

static void dump(const char *name, double *a, int n){
	int i;
	for(i = 0; i < n; i++){
		printf("%s %d %a\n", name, i, a[i]);
	}
}

int main(int ac, char **av){
	if(ac < 3){
		fprintf(stderr, "使い方: %s <econ-XXXX.csv> <zan_jimu>\n", av[0]);
		return 2;
	}

	ifp_econ = fopen(av[1], "r");
	if(ifp_econ == NULL){
		fprintf(stderr, "econ ファイルが開けません: %s\n", av[1]);
		return 2;
	}
	zan_jimu = atoi(av[2]);

	econ();

	fclose(ifp_econ);

	dump("Ri",       Ri,       ECEDY-ECSTY+1);
	dump("H",        H,        ECEDY-ECSTY+1);
	dump("Ci",       Ci,       ECEDY-ECSTY+1);
	dump("Ri2",      Ri2,      ECEDY-ECSTY+1);
	dump("HCdum",    HCdum,    ECEDY-ECSTY+1);
	dump("Id_Hhd",   Id_Hhd,   ECEDY-ECSTY+1);
	dump("Id_Cid",   Id_Cid,   ECEDY-ECSTY+1);
	dump("Id_Cid_2", Id_Cid_2, ECEDY-ECSTY+1);

	return 0;
}
