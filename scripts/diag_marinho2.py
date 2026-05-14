"""Diagnostica o critério atual (span vfim→lastOut − duração) contra baseline 28/36."""
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
col_prod_in = "Primeira vez que entrou na fase Em produção"
col_prod_dur = "Tempo total na fase Em produção (dias)"

sub = df.dropna(subset=[col_vfim, col_prod_out]).copy()
print(f"baseline denominator: 36; nosso (sem fix): {len(sub)}")

sub["span_dias"] = (sub[col_prod_out] - sub[col_vfim]).dt.total_seconds() / 86400
sub["dur_dias"] = pd.to_numeric(sub[col_prod_dur], errors="coerce").fillna(0)
sub["gap"] = sub["span_dias"] - sub["dur_dias"]
sub["_horas"] = sub.apply(lambda r: horas_uteis(r[col_vfim], r[col_prod_out]), axis=1)

print("\nDistribuição do gap:")
print(f"  gap < 0    : {int((sub['gap'] < 0).sum())}")
print(f"  gap ∈ [0,1]: {int(((sub['gap'] >= 0) & (sub['gap'] <= 1)).sum())}")
print(f"  gap ∈ (1,7]: {int(((sub['gap'] > 1) & (sub['gap'] <= 7)).sum())}")
print(f"  gap > 7    : {int((sub['gap'] > 7).sum())}")

# Cards com gap > 1 (que seriam excluídos pela versão atual)
excluidos = sub[sub["gap"] > 1].sort_values("gap", ascending=False)
print(f"\nCards excluídos pelo fix atual (gap > 1d): {len(excluidos)}")
print(excluidos[["id", col_vfim, col_prod_out, "span_dias", "dur_dias", "gap", "_horas"]].head(25).to_string())

# Tentar com cutoff alternativo: gap > 7 dias (mais conservador)
for thr in [1.0, 2.0, 5.0, 7.0, 14.0, 30.0]:
    sub_f = sub[sub["gap"] <= thr]
    n_ok = int((sub_f["_horas"] <= 24).sum())
    print(f"  gap ≤ {thr:>5}d: {n_ok}/{len(sub_f)}")

# Threshold por _horas (laudo time)
print("\nThreshold por _horas (úteis):")
for thr in [72, 120, 168, 200]:
    sub_f = sub[sub["_horas"] <= thr]
    n_ok = int((sub_f["_horas"] <= 24).sum())
    print(f"  _horas ≤ {thr:>4}: {n_ok}/{len(sub_f)}")

# Investigar cards com _horas > 168 — são todos reabertos?
print("\nCards com _horas > 168 (= 7 dias úteis):")
slow = sub[sub["_horas"] > 168].sort_values("_horas", ascending=False)
print(slow[["id", col_vfim, col_prod_out, "dur_dias", "gap", "_horas"]].to_string())
