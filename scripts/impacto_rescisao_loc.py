"""
Compara o cálculo de Rescisão Loc. ANTES (regra antiga) vs DEPOIS (regra refinada 11ª Ed).
Mostra impacto numérico + 3+ casos onde a regra muda o resultado.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from calculate import (excluir_rascunhos, aplicar_cutoff, _nome_assessora_alt,
                        _contem_qualquer, score_indicador, nota_processo)
from pipeline.extract_pipefy import extract_pipe

REF = pd.Timestamp.utcnow()

df_rl = extract_pipe("rescisao_loc", verbose=False)
print(f"Total cards rescisao_loc: {len(df_rl)}")

COL_CHAVES_CAMPO = "Data do recebimento das chaves:"
COL_CHAVES_FASE = "Primeira vez que entrou na fase CHAVES RECEBIDAS"
COL_VIST_OUT = "Última vez que saiu da fase Vistoria recebida"
COL_AGEND_OUT = "Última vez que saiu da fase Agendamento de vistoria"
COL_LEV_PROP = "Primeira vez que entrou na fase Levant. Taxas Proporcionais"
COL_ENV_BOL = "Primeira vez que entrou na fase Envio do boleto final"


def _calc_assessora(assessora: str, regra: str):
    """regra ∈ {'antiga', 'nova'}."""
    df = excluir_rascunhos(df_rl)
    df = aplicar_cutoff(df, "Criado em", ref=REF)
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Assessor (lista)"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    chaves_campo = df[COL_CHAVES_CAMPO]
    if regra == "nova":
        chaves_fase = df.get(COL_CHAVES_FASE, pd.Series(pd.NaT, index=df.index))
        chaves_efetivas = chaves_campo.where(chaves_campo.notna(), chaves_fase)
    else:
        chaves_efetivas = chaves_campo
    sai_vist = df[COL_VIST_OUT]
    sai_agend = df[COL_AGEND_OUT]
    inicio_prop = chaves_efetivas.where(chaves_efetivas.notna(), sai_vist)
    inicio_final = chaves_efetivas.where(chaves_efetivas.notna(), sai_agend)

    # Boleto prop
    mask_4 = inicio_prop.notna() & df[COL_LEV_PROP].notna()
    horas_4 = (df.loc[mask_4, COL_LEV_PROP] - inicio_prop[mask_4]).dt.total_seconds() / 3600
    horas_4 = horas_4.clip(lower=0)
    ok_4 = int((horas_4 <= 24).sum())
    ind_4 = score_indicador(ok_4, int(mask_4.sum()), 2)
    ind_4["nome"] = "Rescisão Loc. — Boleto prop <24h"

    # Boleto final
    mask_5 = inicio_final.notna() & df[COL_ENV_BOL].notna()
    dias_5 = (df.loc[mask_5, COL_ENV_BOL] - inicio_final[mask_5]).dt.total_seconds() / 86400
    dias_5 = dias_5.clip(lower=0)
    ok_5 = int((dias_5 <= 15).sum())
    ind_5 = score_indicador(ok_5, int(mask_5.sum()), 3)
    ind_5["nome"] = "Rescisão Loc. — Boleto final <15d"

    nota = nota_processo([ind_4, ind_5])
    return {"ind_4": ind_4, "ind_5": ind_5, "nota": nota,
            "df": df, "inicio_prop": inicio_prop, "inicio_final": inicio_final,
            "mask_4": mask_4, "mask_5": mask_5}


# ─── Comparar ───
print()
print(f"{'Pessoa':10} {'Regra':6} {'Ind 4 (Boleto prop)':>25} {'Ind 5 (Boleto final)':>25} {'Nota':>6}")
print("-" * 80)
resultados = {}
for pessoa in ("natalia", "gardenia"):
    for regra in ("antiga", "nova"):
        r = _calc_assessora(pessoa, regra)
        resultados[(pessoa, regra)] = r
        i4, i5 = r["ind_4"], r["ind_5"]
        print(f"{pessoa:10} {regra:6} {i4['ok']:>3}/{i4['tot']:<3} ({i4['pct'] or 0:>5.1f}%)       "
              f"{i5['ok']:>3}/{i5['tot']:<3} ({i5['pct'] or 0:>5.1f}%)       {r['nota']}")

# ─── Casos onde mudou o resultado ───
print()
print("=" * 100)
print("Casos onde a regra MUDA o resultado (início diferente entre antiga e nova)")
print("=" * 100)
for pessoa in ("natalia", "gardenia"):
    a = resultados[(pessoa, "antiga")]
    n = resultados[(pessoa, "nova")]
    df = n["df"]
    print(f"\n━━━ {pessoa.upper()} ━━━")
    # Compara inicio_prop e inicio_final card por card
    diff_prop = (a["inicio_prop"] != n["inicio_prop"]) & (a["inicio_prop"].notna() | n["inicio_prop"].notna())
    diff_final = (a["inicio_final"] != n["inicio_final"]) & (a["inicio_final"].notna() | n["inicio_final"].notna())
    diff = diff_prop | diff_final
    casos = df[diff]
    print(f"Cards com início diferente entre regras: {int(diff.sum())}")
    for _, row in casos.head(6).iterrows():
        idx = row.name
        ip_a = a["inicio_prop"].loc[idx]
        ip_n = n["inicio_prop"].loc[idx]
        if_a = a["inicio_final"].loc[idx]
        if_n = n["inicio_final"].loc[idx]
        ch_campo = row[COL_CHAVES_CAMPO]
        ch_fase = row.get(COL_CHAVES_FASE)
        sai_v = row[COL_VIST_OUT]
        lev_p = row[COL_LEV_PROP]
        env_b = row[COL_ENV_BOL]
        print(f"\n  Card id={row['id']}  IM='{row['Título']!s:.60}'")
        print(f"    Data recebimento chaves: (campo)         : {ch_campo}")
        print(f"    Primeira vez fase CHAVES RECEBIDAS       : {ch_fase}")
        print(f"    Última vez saiu Vistoria recebida        : {sai_v}")
        print(f"    Entrou Levant. Taxas Prop                : {lev_p}")
        print(f"    Entrou Envio boleto final                : {env_b}")
        print(f"    --- INÍCIO PROP ---")
        print(f"      antiga: {ip_a}")
        print(f"      nova:   {ip_n}")
        if pd.notna(ip_a) and pd.notna(lev_p) and pd.notna(ip_n):
            h_a = (lev_p - ip_a).total_seconds() / 3600
            h_n = (lev_p - ip_n).total_seconds() / 3600
            print(f"      antiga: {max(h_a, 0):.1f}h  ({'✓' if max(h_a,0) <= 24 else '✗'})")
            print(f"      nova:   {max(h_n, 0):.1f}h  ({'✓' if max(h_n,0) <= 24 else '✗'})")
