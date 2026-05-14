"""
Análise descritiva dos 7 cards de vistoria "lentas" — laudo >168h úteis mas SEM
sinal claro de reabertura (gap pequeno/negativo, duração acumulada longa num único ciclo).

Critério de seleção:
- Em escopo de calc_marinho_vistorias (excluir_rascunhos + cutoff 180d + dropna vfim/prod_out)
- _horas (úteis vfim → lastOut) > 168h
- gap (span − duração) ≤ 1d  ← *exclui* as 3 reaberturas óbvias do diag

Saída: tabela detalhada + seção de padrões. Sem proposta de solução.
"""
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
df = excluir_rascunhos(df)
df = aplicar_cutoff(df, "Criado em", ref=REF)

col_vfim = "Vistoria finalizada em"
col_prod_out = "Última vez que saiu da fase Em produção"
col_prod_dur = "Tempo total na fase Em produção (dias)"
col_vini = next((c for c in df.columns if c.strip().lower() == "vistoria iniciada em"), None)

sub = df.dropna(subset=[col_vfim, col_prod_out]).copy()
sub["_horas"] = sub.apply(lambda r: horas_uteis(r[col_vfim], r[col_prod_out]), axis=1)
sub["span_dias"] = (sub[col_prod_out] - sub[col_vfim]).dt.total_seconds() / 86400
sub["dur_dias"] = pd.to_numeric(sub[col_prod_dur], errors="coerce").fillna(0)
sub["gap"] = sub["span_dias"] - sub["dur_dias"]

# As 7 lentas: _horas > 168 E gap ≤ 1 (sem sinal de reabertura)
lentas = sub[(sub["_horas"] > 168) & (sub["gap"] <= 1)].sort_values("_horas", ascending=False).copy()

print(f"Total cards em escopo: {len(sub)}")
print(f"Cards com _horas > 168h: {int((sub['_horas']>168).sum())}")
print(f"  destes, reaberturas (gap > 1d): {int(((sub['_horas']>168) & (sub['gap']>1)).sum())}")
print(f"  destes, LENTAS (gap ≤ 1d): {len(lentas)}")
print()

# Cols disponíveis no DataFrame para enriquecer
candidatos = ["Tipo de vistoria", "Área útil M²", "IM", "Data da Vistoria",
              "Proprietário:", "Locatário", "Endereço do imóvel:"]
cols_extra = [c for c in candidatos if c in df.columns]
print(f"Campos extras disponíveis: {cols_extra}")
print()

print("=" * 140)
print("OS 7 (ou N) CARDS LENTOS — TABELA DETALHADA")
print("=" * 140)

for _, r in lentas.iterrows():
    print(f"\nCard id: {r['id']}")
    print(f"  Título            : {r['Título']}")
    print(f"  Fase atual        : {r['Fase atual']}")
    print(f"  Criado em         : {r['Criado em']}")
    print(f"  Vistoria finalizada em        : {r[col_vfim]}")
    if col_vini:
        print(f"  Vistoria iniciada em          : {r[col_vini]}")
    print(f"  Última vez saiu Em produção   : {r[col_prod_out]}")
    print(f"  Duração acumulada Em produção : {r['dur_dias']:.2f} dias  (= {r['dur_dias']*24:.1f}h corridos)")
    print(f"  Span vfim → lastOut           : {r['span_dias']:.2f} dias")
    print(f"  Gap (span − dur)              : {r['gap']:.2f} dias  ← ≤1d, sem reabertura clara")
    print(f"  Horas úteis vfim→lastOut      : {r['_horas']:.1f}h ({r['_horas']/24:.1f} dias)")
    for c in cols_extra:
        v = r.get(c)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v) if v else "—"
        print(f"  {c:30}: {v}")

# ─── PADRÕES DETECTADOS ─────────────────────────────────────────────
print()
print("=" * 140)
print("PADRÕES DETECTADOS")
print("=" * 140)

# Distribuição por mês de finalização
print("\n[Distribuição por mês de Vistoria finalizada em]")
mes = lentas[col_vfim].dt.to_period("M").value_counts().sort_index()
for m, n in mes.items():
    print(f"  {m}: {n}")

# Distribuição por mês de Última vez saiu
print("\n[Distribuição por mês de Última vez saiu Em produção]")
mes_out = lentas[col_prod_out].dt.to_period("M").value_counts().sort_index()
for m, n in mes_out.items():
    print(f"  {m}: {n}")

# Tipo de vistoria
if "Tipo de vistoria" in lentas.columns:
    print("\n[Distribuição por Tipo de vistoria]")
    def _norm_tipo(v):
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) if v else "—"
        return v or "—"
    tipos = lentas["Tipo de vistoria"].apply(_norm_tipo).value_counts()
    for t, n in tipos.items():
        print(f"  {t}: {n}")

# Faixa de m²
if "Área útil M²" in lentas.columns:
    print("\n[Distribuição por faixa de Área útil M²]")
    m2 = pd.to_numeric(lentas["Área útil M²"], errors="coerce")
    bins = [0, 50, 100, 200, 500, 10000]
    rotulos = ["≤50", "51-100", "101-200", "201-500", ">500"]
    faixa = pd.cut(m2, bins=bins, labels=rotulos)
    for r, n in faixa.value_counts().sort_index().items():
        print(f"  {r}: {n}")
    print(f"  NaN: {int(m2.isna().sum())}")

# Fase atual
print("\n[Distribuição por Fase atual]")
for f, n in lentas["Fase atual"].value_counts().items():
    print(f"  {f}: {n}")

# Duração — quanto tempo realmente passou em Em produção
print("\n[Distribuição de duração em Em produção (dias)]")
print(f"  min:    {lentas['dur_dias'].min():.1f}d")
print(f"  median: {lentas['dur_dias'].median():.1f}d")
print(f"  mean:   {lentas['dur_dias'].mean():.1f}d")
print(f"  max:    {lentas['dur_dias'].max():.1f}d")

# IM (imóvel) — algum IM repetido?
if "IM" in lentas.columns:
    print("\n[IMs envolvidos]")
    ims = lentas["IM"].astype(str).value_counts()
    print(f"  IMs únicos: {len(ims)} de {len(lentas)} cards")
    repetidos = ims[ims > 1]
    if len(repetidos) > 0:
        print(f"  IMs repetidos: {list(repetidos.index)}")
    else:
        print(f"  Todos os IMs diferentes — nenhum imóvel repete")
