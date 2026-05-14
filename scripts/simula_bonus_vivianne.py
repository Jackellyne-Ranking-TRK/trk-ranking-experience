"""
Simulação dos 4 cenários de cálculo do bônus Vivianne para a gestora decidir.

NÃO salva nada em config/. Apenas análise comparativa.

Cenários:
  1. Atual   — lógica antiga (qualquer card do IM, data_pag ≤ data_repasse derivada de mes_ref+1)
  2. Só R1   — Atual + filtro de multa proporcional (multa/valor entre 0% e 15%)
  3. Só R2   — match por mês exato + card.criado_em < boleto.data_pag
  4. R1+R2   — ambos os filtros
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import re
import pandas as pd
from pipeline.extract_imobiliar import (
    extract_imobiliar, _data_repasse, _data_repasse_from_card,
    _mes_seguinte, _parse_im_titulo,
)
from pipeline.extract_pipefy import extract_pipe

BASELINE_10 = 124

# ─── Carregar dados ─────────────────────────────────────────
dfs = extract_imobiliar(verbose=False)
df_inad = extract_pipe("inadimplencia", verbose=False)

def _norm_cd(v):
    try: return int(str(v).strip().lstrip("0") or "0")
    except (ValueError, TypeError): return None

# ─── Boletos com encargo + dia_pag ─────────────────────────
b = dfs["boletos"].copy()
b["com_encargo"] = (b["multa_adm"] > 0) | (b["juros_adm"] > 0)
b_enc = b[b["com_encargo"]].copy()
b_enc["cd_imovel"] = b_enc["cd_imovel"].apply(_norm_cd)
b_enc = b_enc.dropna(subset=["cd_imovel"])
imov = dfs["imoveis"].copy()
imov["cd_imovel"] = imov["cd_imovel"].apply(_norm_cd)
b_enc = b_enc.merge(imov[["cd_imovel", "id_proprietario", "endereco"]], on="cd_imovel", how="left")
b_enc["id_proprietario"] = b_enc["id_proprietario"].apply(_norm_cd)
props = dfs["proprietarios"].copy()
props["id_proprietario"] = props["id_proprietario"].apply(_norm_cd)
b_enc = b_enc.merge(
    props[["id_proprietario", "dia_pag", "nome"]].rename(columns={"nome": "nome_prop"}),
    on="id_proprietario", how="left"
)
b_enc = b_enc.dropna(subset=["dia_pag"]).copy()
b_enc["dia_pag"] = b_enc["dia_pag"].astype(int)
b_enc["multa_ratio"] = b_enc["multa_adm"] / b_enc["valor"].where(b_enc["valor"] > 0)

denom = len(b_enc)
print(f"Denominador (boletos com encargo + dia_pag): {denom}\n")

# ─── Index dos cards ───────────────────────────────────────
c = df_inad.copy()
c["im_titulo"] = c["Título"].apply(_parse_im_titulo)
c["venc"] = pd.to_datetime(c["Vencimento 1º Boleto:"], errors="coerce", utc=True)
c["criado_em"] = pd.to_datetime(c["Criado em"], errors="coerce", utc=True)
c_ok = c.dropna(subset=["venc", "im_titulo"]).copy()
c_ok["im_titulo"] = c_ok["im_titulo"].astype(int)

# Mapas de cards para os matchings
ims_inad_set = set(c_ok["im_titulo"].unique().tolist())
cards_por_mes: dict[tuple[int,int,int], list[pd.Series]] = {}
for _, row in c_ok.iterrows():
    key = (int(row["im_titulo"]), row["venc"].year, row["venc"].month)
    cards_por_mes.setdefault(key, []).append(row)


# ─── Helpers de cenário ────────────────────────────────────
def _data_pag(row):
    return pd.to_datetime(row.data_pag, utc=True)

def antes_repasse_legacy(row) -> bool:
    """Regra 3 legacy: data_repasse de mes_ref+1 no dia_pag."""
    dr = _data_repasse(row.mes_ref, int(row.dia_pag))
    if dr is None: return False
    dp = _data_pag(row)
    return pd.notna(dp) and dp <= dr

def match_card_per_month(row):
    """Retorna o card do mes_ref+1 (mais recente se múltiplos), ou None."""
    ms = _mes_seguinte(row.mes_ref)
    if ms is None: return None
    mes_t, ano_t = ms
    cards = cards_por_mes.get((int(row.cd_imovel), ano_t, mes_t), [])
    if not cards: return None
    return sorted(cards, key=lambda x: x["venc"], reverse=True)[0]

def antes_repasse_from_card(row, card) -> bool:
    """Regra 3 nova: data_repasse derivada do Venc do card."""
    dr = _data_repasse_from_card(card["venc"], int(row.dia_pag))
    dp = _data_pag(row)
    return pd.notna(dp) and dp <= dr


# ─── Cenário 1: Atual (legacy) ─────────────────────────────
def cenario_atual(b_enc):
    """Match: qualquer card do IM. data_repasse: mes_ref+1 no dia_pag."""
    rows_in, rows_out = [], []
    for r in b_enc.itertuples(index=False):
        tem_card = int(r.cd_imovel) in ims_inad_set
        if tem_card and antes_repasse_legacy(r):
            rows_in.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                            "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                            "motivo_exc": None})
        else:
            motivo = ("sem card no pipe" if not tem_card else "data_pag > data_repasse")
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                              "motivo_exc": motivo})
    return rows_in, rows_out


# ─── Cenário 2: Só R1 (atual + filtro multa) ───────────────
def cenario_r1(b_enc):
    rows_in, rows_out = [], []
    for r in b_enc.itertuples(index=False):
        ratio = r.multa_ratio
        if pd.isna(ratio):
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": "valor=0 ou nulo"})
            continue
        if ratio > 0.15:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": f"multa_ratio={ratio*100:.1f}% > 15% (rescisão/outro)"})
            continue
        tem_card = int(r.cd_imovel) in ims_inad_set
        if tem_card and antes_repasse_legacy(r):
            rows_in.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                            "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                            "motivo_exc": None})
        else:
            motivo = ("sem card no pipe" if not tem_card else "data_pag > data_repasse")
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": motivo})
    return rows_in, rows_out


# ─── Cenário 3: Só R2 (match por mês + criado < pago) ──────
def cenario_r2(b_enc):
    rows_in, rows_out = [], []
    for r in b_enc.itertuples(index=False):
        card = match_card_per_month(r)
        if card is None:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                              "motivo_exc": "nenhum card no mês_ref+1"})
            continue
        if card["criado_em"] >= _data_pag(r):
            dias = (card["criado_em"] - _data_pag(r)).days
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                              "motivo_exc": f"reativa: card criado {card['criado_em'].date()} ≥ pago {_data_pag(r).date()} ({dias}d)"})
            continue
        if antes_repasse_from_card(r, card):
            rows_in.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                            "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                            "motivo_exc": None})
        else:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": r.multa_ratio,
                              "motivo_exc": "data_pag > data_repasse_do_card"})
    return rows_in, rows_out


# ─── Cenário 4: R1 + R2 ────────────────────────────────────
def cenario_r1_r2(b_enc):
    rows_in, rows_out = [], []
    for r in b_enc.itertuples(index=False):
        ratio = r.multa_ratio
        if pd.isna(ratio):
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": "valor=0 ou nulo"})
            continue
        if ratio > 0.15:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": f"multa_ratio={ratio*100:.1f}% > 15% (rescisão/outro)"})
            continue
        card = match_card_per_month(r)
        if card is None:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": "nenhum card no mês_ref+1"})
            continue
        if card["criado_em"] >= _data_pag(r):
            dias = (card["criado_em"] - _data_pag(r)).days
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": f"reativa: card criado {card['criado_em'].date()} ≥ pago {_data_pag(r).date()} ({dias}d)"})
            continue
        if antes_repasse_from_card(r, card):
            rows_in.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                            "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                            "motivo_exc": None})
        else:
            rows_out.append({"cd": r.cd_imovel, "mes_ref": r.mes_ref, "data_pag": r.data_pag,
                              "valor": r.valor, "multa": r.multa_adm, "ratio": ratio,
                              "motivo_exc": "data_pag > data_repasse_do_card"})
    return rows_in, rows_out


# ─── Rodar todos ────────────────────────────────────────────
cenarios = [
    ("Atual (sem filtro novo)", cenario_atual),
    ("Só Regra 1 (multa ≤15%)", cenario_r1),
    ("Só Regra 2 (card antes pag.)", cenario_r2),
    ("Regras 1+2 (FINAL)", cenario_r1_r2),
]

print(f"{'Cenário':40} {'N':>5} {'Drift vs 124':>14}")
print("-" * 70)
resultados = []
for nome, fn in cenarios:
    ins, outs = fn(b_enc)
    N = len(ins)
    drift = N - BASELINE_10
    resultados.append((nome, N, drift, ins, outs))
    print(f"{nome:40} {N:>5} {drift:>+14}")
print()

# Detalhe por cenário
for nome, N, drift, ins, outs in resultados:
    if "Atual" in nome:
        continue
    print(f"\n━━━ {nome} ━━━")
    # Excluídos pelos filtros novos (vs Atual)
    print(f"Total avaliados: {denom}  ·  N={N}  ·  excluídos: {denom - N}")
    # Quebra de motivos
    motivos = pd.Series([o["motivo_exc"] for o in outs]).value_counts()
    print(f"Motivos de exclusão (top):")
    for m, c in motivos.head(8).items():
        print(f"  {c:>3}  {m}")
    # Sample 3 excluídos por filtro novo (não por motivos legacy)
    novos_filtros = [
        o for o in outs
        if o["motivo_exc"] and (("multa_ratio" in o["motivo_exc"]) or ("reativa" in o["motivo_exc"]) or ("nenhum card no mês" in o["motivo_exc"]) or ("valor=0" in o["motivo_exc"]))
    ]
    print(f"Sample 3 excluídos pelos filtros novos:")
    for o in novos_filtros[:3]:
        ratio_s = f"{o['ratio']*100:.1f}%" if pd.notna(o['ratio']) else "—"
        dp = o['data_pag'].date() if pd.notna(o['data_pag']) else "—"
        print(f"  IM {o['cd']:>5}  mes_ref={o['mes_ref']}  pago={dp}  valor=R$ {o['valor']:>9.2f}  multa=R$ {o['multa']:>7.2f}  ratio={ratio_s}")
        print(f"    → {o['motivo_exc']}")
