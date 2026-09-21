/* ===========================================================================
 * cnum.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本 プログラム/厚生年金/収支計算/stdfun.c の nround() と、C の round()・
 * atof() を呼んで、結果を %a（16進浮動小数）で出す。%a は double を無損失で
 * 文字列化するので、Python 側とビット単位で突き合わせられる。
 *
 * nround() は stdfun.c からそのまま写している（原本を書き換えないため）。
 *
 * 使い方:
 *   round   <値を %a か 10進で>   → round(x)
 *   nround  <値> <桁>             → nround(x, n)
 *   atof    <文字列>              → atof(s)
 * を1行ずつ標準入力から読み、1行1結果で標準出力に出す。
 * ======================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* --- 原本 stdfun.c:124 をそのまま --- */
double nround(double x, int n){
	double dtemp;

	dtemp = pow(10.0, (double)n);

	x *= dtemp;

	x = round(x) / dtemp;

	return(x);
}

int main(void){
	char line[4096];

	while(fgets(line, sizeof line, stdin) != NULL){
		char op[32];
		/* 行末の改行を落とす */
		size_t L = strlen(line);
		while(L > 0 && (line[L-1] == '\n' || line[L-1] == '\r')) line[--L] = '\0';

		if(sscanf(line, "%31s", op) != 1) continue;

		if(strcmp(op, "round") == 0){
			double x;
			sscanf(line, "%*s %lf", &x);
			printf("%a\n", round(x));

		}else if(strcmp(op, "nround") == 0){
			double x; int n;
			sscanf(line, "%*s %lf %d", &x, &n);
			printf("%a\n", nround(x, n));

		}else if(strcmp(op, "atof") == 0){
			/* op のあとの1個の空白を挟んだ残り全部を文字列として渡す。
			 * 空文字列や空白のみも試したいので sscanf では切らない。 */
			char *p = line + strlen(op);
			if(*p == ' ') p++;
			printf("%a\n", atof(p));

		}else{
			printf("?unknown op\n");
		}
	}
	return 0;
}
