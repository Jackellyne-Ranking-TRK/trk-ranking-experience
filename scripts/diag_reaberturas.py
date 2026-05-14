"""Detecta reaberturas em cada (pipe, fase) usada em calculate.py com lastTimeOut.

Sinal de reabertura: (lastTimeOut - firstTimeIn) significativamente > duration acumulada.
Se um card entrou só uma vez na fase, span ≈ duration. Se entrou múltiplas vezes,
span >> duration (a soma das durações ignora os gaps entre saídas e re-entradas).

Cards "suspeitos de reabertura": (span_dias - tempo_total_dias) > 1 dia.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from calculate import excluir_rascunhos, aplicar_cutoff
from pipeline.extract_pipefy import extract_pipe

REF = pd.Timestamp("2026-05-11", tz="UTC")

# (pipe_key, fase_name, funcao_que_usa)
CHECKS = [
    ("comercial_locacao", "Avaliação Técnica", "calc_caio_comercial_locacao"),
    ("comercial_locacao", "Cadastro / Reativação no NIDO", "calc_caio_comercial_locacao"),
    ("renovacao",         "Avaliação de mercado",          "calc_caio_renovacao"),
    ("cont_adm",          "Confecção do contrato",         "calc_vivianne_contrato_adm"),
    ("rescisao_adm",      "Encerramento",                  "calc_vivianne_rescisao_adm"),
    ("cont_adm",          "Conferência do contrato",       "calc_assessora_contrato_adm"),
    ("rescisao_loc",      "Vistoria recebida",             "calc_assessora_rescisao_locacao"),
    ("rescisao_loc",      "Agendamento de vistoria",       "calc_assessora_rescisao_locacao"),
    ("renovacao",         "Contato com proprietário",      "calc_assessora_renovacao"),
    ("backoffice",        "🚩 Pendência Assessor",         "calc_assessora_backoffice"),
    ("vistorias",         "Em produção",                   "calc_marinho_vistorias [KNOWN]"),
]

# pré-carrega DFs
pipes = sorted(set(p for p, _, _ in CHECKS))
dfs = {p: extract_pipe(p, verbose=False) for p in pipes}

print(f"{'função':45} {'fase':32} {'em_escopo':>10} {'reaberto':>9} {'%':>5}")
print("-" * 105)
for pipe, fase, func in CHECKS:
    df = excluir_rascunhos(dfs[pipe])
    df = aplicar_cutoff(df, "Criado em", ref=REF)

    col_in = f"Primeira vez que entrou na fase {fase}"
    col_out = f"Última vez que saiu da fase {fase}"
    col_dur = f"Tempo total na fase {fase} (dias)"

    # cards que efetivamente entraram E saíram da fase
    sub = df.dropna(subset=[col_in, col_out]).copy()
    if len(sub) == 0:
        print(f"{func:45} {fase:32} {'—':>10} {'—':>9} {'—':>5}")
        continue

    span_dias = (sub[col_out] - sub[col_in]).dt.total_seconds() / 86400.0
    dur_dias = sub[col_dur].astype(float)
    gap = span_dias - dur_dias
    mask_reaberto = gap > 1.0   # > 1 dia de gap = re-entrou

    n_reaberto = int(mask_reaberto.sum())
    pct = (100 * n_reaberto / len(sub)) if len(sub) else 0
    print(f"{func:45} {fase:32} {len(sub):>10} {n_reaberto:>9} {pct:>4.1f}%")

    # exemplos top 3 (maiores gaps)
    if n_reaberto > 0:
        top = sub[mask_reaberto].assign(_gap=gap[mask_reaberto]).nlargest(3, "_gap")
        for _, row in top.iterrows():
            print(f"    ex: id={row['id']}  in={row[col_in].date()}  out={row[col_out].date()}  "
                  f"span={span_dias[row.name]:.1f}d  dur={dur_dias[row.name]:.1f}d  gap={row['_gap']:.1f}d")
