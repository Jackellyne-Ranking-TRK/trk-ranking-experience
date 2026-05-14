"""Diagnostica as 10 vistorias extras no denominador do Laudo do Marinho."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from calculate import excluir_rascunhos, aplicar_cutoff, horas_uteis
from pipeline.extract_pipefy import extract_pipe

REF = pd.Timestamp("2026-05-11", tz="UTC")
df = extract_pipe("vistorias", verbose=False)
print(f"[raw] total cards no pipe: {len(df)}")

df1 = excluir_rascunhos(df)
print(f"[+ rascunho] {len(df1)}")

df2 = aplicar_cutoff(df1, "Criado em", ref=REF)
print(f"[+ cutoff Criado em 180d] {len(df2)}")

col_vfim = "Vistoria finalizada em"
col_prod_out = "Última vez que saiu da fase Em produção"

df3 = df2.dropna(subset=[col_vfim, col_prod_out])
print(f"[+ dropna vfim+prod_out] {len(df3)}  <-- denom ATUAL ({len(df3)} vs baseline 36)")

# Alternativa A: cutoff sobre Vistoria finalizada em (e não Criado em)
dfA = aplicar_cutoff(df1.dropna(subset=[col_vfim, col_prod_out]), col_vfim, ref=REF)
print(f"[A] cutoff sobre Vistoria finalizada em: {len(dfA)}")

# Alternativa B: cutoff sobre "Última vez que saiu da fase Em produção"
dfB = aplicar_cutoff(df1.dropna(subset=[col_vfim, col_prod_out]), col_prod_out, ref=REF)
print(f"[B] cutoff sobre Última vez saiu Em produção: {len(dfB)}")

# Alternativa C: Fase atual == Concluído
dfC = df3[df3["Fase atual"] == "Concluído"]
print(f"[C] filtrar Fase atual = Concluído: {len(dfC)}")

# Combinações
dfAC = dfA[dfA["Fase atual"] == "Concluído"]
print(f"[A+C] cutoff Vfim + Concluído: {len(dfAC)}")

dfBC = dfB[dfB["Fase atual"] == "Concluído"]
print(f"[B+C] cutoff Prod_out + Concluído: {len(dfBC)}")

# Diferença: quem está no nosso denom mas teria saído com alt A
diff_AvsAtual = set(df3["id"]) - set(dfA["id"])
print(f"\n[diff atual - A] {len(diff_AvsAtual)} cards extras com filtro Criado em vs Vfim")

# Mostra esses 10 cards (se forem 10)
extras = df3[df3["id"].isin(diff_AvsAtual)][["id", "Título", "Criado em", col_vfim, col_prod_out, "Fase atual"]]
print(extras.head(15).to_string())

# Para cada alternativa que dá 36 (baseline), recompute o numerador
def num_ok(d):
    horas = d.apply(lambda r: horas_uteis(r[col_vfim], r[col_prod_out]), axis=1)
    return int((horas <= 24).sum()), len(d)

for name, sub in [("atual", df3), ("A", dfA), ("B", dfB), ("C", dfC), ("A+C", dfAC), ("B+C", dfBC)]:
    n, t = num_ok(sub)
    flag = "  <-- bate baseline 28/36" if (n, t) == (28, 36) else ""
    print(f"  [{name:5}]  {n}/{t}{flag}")

# Mais alternativas
print("\n--- Outros filtros ---")
col_vini = "vistoria iniciada em"
if col_vini not in df3.columns:
    col_vini = "vistoria iniciada em "
print(f"col_vini disponível? {col_vini in df3.columns}")

dfD = df3.dropna(subset=[col_vini]) if col_vini in df3.columns else df3
print(f"[D] +dropna vistoria iniciada em: {len(dfD)}")
print(f"     num/tot: {num_ok(dfD)}")

# Excluir negativos (≠ neg→0)
horas_atual = df3.apply(lambda r: horas_uteis(r[col_vfim], r[col_prod_out]), axis=1)
print(f"\nhoras_uteis stats: min={horas_atual.min():.2f}, max={horas_atual.max():.2f}, neg={int((horas_atual<0).sum())}, zero={int((horas_atual==0).sum())}, >24={int((horas_atual>24).sum())}")

# Top cards com mais horas
df3 = df3.assign(_horas=horas_atual)

# Hipótese: cards reabertos têm Vistoria finalizada em < Primeira vez que entrou Em produção
col_prod_in = "Primeira vez que entrou na fase Em produção"
mask_reaberto = df3[col_vfim] < df3[col_prod_in]
print(f"\n[reaberto] cards com vfim < primeira_entrada Em produção: {int(mask_reaberto.sum())}")
dfE = df3[~mask_reaberto]
print(f"[E] excluir reaberturas: {len(dfE)}  num/tot: {num_ok(dfE)}")

# Alternativa F: usar lastTimeIn como referência implícita — não temos no extract. Skip.

# Alternativa G: filtro por _horas < threshold (ex. 200h ~ 8 dias)
for thr in [72, 96, 120, 168, 200, 240]:
    dfG = df3[df3["_horas"] < thr]
    n, t = num_ok(dfG)
    print(f"[G thr<{thr}h] {n}/{t}")
