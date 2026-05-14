"""Lista detalhes dos candidatos a bônus para validação manual do usuário."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import re
import pandas as pd
from calculate import (excluir_rascunhos, aplicar_cutoff, filtrar_por_assignee,
                        _nome_assessora_alt, _contem_qualquer, _as_list, extrair_im)
from pipeline.extract_pipefy import extract_pipe

REF = pd.Timestamp.utcnow()

# ─── PONTO 2: 6 IMs Gardenia (sem Assessor + Concluído) ────────────
print("=" * 100)
print("PONTO 2 — 6 cards Gardênia (regra: sem Assessor + Concluído)")
print("=" * 100)

df_cadm = extract_pipe("cont_adm", verbose=False)
df_cadm = excluir_rascunhos(df_cadm)
df_cadm = aplicar_cutoff(df_cadm, "Criado em", ref=REF)

nomes_g = _nome_assessora_alt("gardenia")
col_assess = "Assessor (lista)"
col_vist = "Criar Card de Vistoria Técnica"
col_concl = "Primeira vez que entrou na fase Concluído"

mask_nome_g = df_cadm[col_assess].apply(lambda v: _contem_qualquer(v, nomes_g))
sem_assessor = df_cadm[col_assess].apply(lambda v: not _as_list(v))
concluido = df_cadm[col_concl].notna()

# Total Gardenia (mesma regra do _contar_bonus_assessora)
mask_total_g = (mask_nome_g | (sem_assessor & concluido)) & df_cadm[col_vist].notna()
gard = df_cadm[mask_total_g].copy()

# Subset: sem Assessor + Concluído (a regra defensiva)
mask_extra = sem_assessor & concluido & ~mask_nome_g & df_cadm[col_vist].notna()
extra = df_cadm[mask_extra].copy()

print(f"\nTotal cards Gardênia (com regra): {len(gard)}")
print(f"Destes, cards SEM Assessor preenchido (= captura da regra defensiva): {len(extra)}")
print(f"Cards COM Assessor 'Gardênia' explícito: {len(gard) - len(extra)}\n")

print("--- Cards SEM Assessor preenchido (capturados pela regra) ---")
cols_show = ["id", "Título", "Criado em", "Fase atual", col_vist, col_assess]
candidatos_a_mostrar = [c for c in cols_show if c in extra.columns]
# Add Locador/Locatário se houver
for c in ("Locador", "Locatário", "Imóvel", "Endereço"):
    if c in extra.columns:
        candidatos_a_mostrar.append(c)
for _, row in extra.iterrows():
    print(f"\n  Card id: {row['id']}")
    print(f"    Título           : {row['Título']}")
    print(f"    Criado em        : {row['Criado em']}")
    print(f"    Fase atual       : {row['Fase atual']}")
    cv = row.get(col_vist)
    print(f"    Criar Vistoria   : {cv!r}")
    ca = row.get(col_assess)
    print(f"    Assessor (lista) : {ca!r}")
    for c in ("Locador", "Locatário", "Imóvel", "Endereço"):
        if c in extra.columns:
            print(f"    {c:17}: {row[c]!r}")

# ─── PONTO 3: 18 IMs Caio candidatos a bônus ────────────────
print("\n\n" + "=" * 100)
print("PONTO 3 — 18 IMs candidatos a bônus Caio (cards Cont.Locação · sem anúncio Comercial)")
print("=" * 100)

df_cl = extract_pipe("cont_locacao", verbose=False)
df_com = extract_pipe("comercial_locacao", verbose=False)

col_boleto = "Primeira vez que entrou na fase 1º Boleto"
df_cl_ok = aplicar_cutoff(df_cl, col_boleto, ref=REF).dropna(subset=[col_boleto]).copy()
df_cl_ok["IM"] = df_cl_ok["Título"].apply(extrair_im)
df_cl_ok = df_cl_ok.dropna(subset=["IM"])

df_com_caio = excluir_rascunhos(df_com)
df_com_caio = filtrar_por_assignee(df_com_caio, "Profissional responsável", "Caio")
df_com_caio["IM"] = df_com_caio["Título"].apply(extrair_im)
col_anuncio = "Data publicação Anúncio"
ims_com_anuncio = set(df_com_caio.dropna(subset=[col_anuncio, "IM"])["IM"].astype(int).tolist())

candidatos = []
for _, row in df_cl_ok.iterrows():
    im = int(row["IM"])
    if im in ims_com_anuncio:
        continue
    cards_comerciais = df_com_caio[df_com_caio["IM"] == im]
    candidatos.append({
        "im": im,
        "data_boleto": row[col_boleto],
        "titulo_cl": row["Título"],
        "fase_cl": row["Fase atual"],
        "comercial_qtd": len(cards_comerciais),
        "comercial_fases": cards_comerciais["Fase atual"].tolist() if len(cards_comerciais) else [],
        "comercial_titulos": cards_comerciais["Título"].tolist() if len(cards_comerciais) else [],
        "locatario": row.get("Locatário", row.get("Locatario", "—")),
    })

candidatos.sort(key=lambda c: c["data_boleto"])

for c in candidatos:
    boleto_str = c["data_boleto"].date().isoformat() if pd.notna(c["data_boleto"]) else "—"
    print(f"\n  IM {c['im']:>5}")
    print(f"    Título Cont.Locação      : {c['titulo_cl']}")
    print(f"    Fase atual Cont.Locação  : {c['fase_cl']}")
    print(f"    1º Boleto                : {boleto_str}")
    print(f"    Cards Comercial Caio     : {c['comercial_qtd']} (fases: {c['comercial_fases']})")
    if c["comercial_titulos"]:
        for t in c["comercial_titulos"]:
            print(f"      └─ {t}")
    loc = c['locatario']
    if isinstance(loc, list):
        loc = ", ".join(str(x) for x in loc) if loc else "—"
    print(f"    Locatário                : {loc}")
