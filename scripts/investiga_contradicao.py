"""Identifica boletos onde data_pag < venc_card mas tem multa (contradição)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pipeline.extract_imobiliar import extract_imobiliar, calcular_bonus_inadimplencia
from pipeline.extract_pipefy import extract_pipe

dfs = extract_imobiliar(verbose=False)
df_inad = extract_pipe("inadimplencia", verbose=False)
res = calcular_bonus_inadimplencia(dfs, df_inadimplencia=df_inad, verbose=False)

# Concat antes+depois (todos com match)
antes = res["antes"].assign(_status="antes_repasse")
depois = res["depois"].assign(_status="apos_repasse")
todos = pd.concat([antes, depois], ignore_index=True) if len(antes) and len(depois) else \
        (antes if len(antes) else depois)

# Cases of contradiction: data_pag < venc_card (boleto pago antes do venc do card)
# Para esses, multa não faria sentido (pago antes do venc, sem atraso).
todos["data_pag"] = pd.to_datetime(todos["data_pag"], utc=True)
todos["venc_card"] = pd.to_datetime(todos["venc_card"], utc=True)
todos["dias_pag_vs_venc"] = (todos["data_pag"] - todos["venc_card"]).dt.days

# Buscar boletos do CSV original (que têm multa > 0) para anexar dados extras
b = dfs["boletos"]
b["cd_imovel_int"] = b["cd_imovel"].apply(lambda v: int(str(v).strip().lstrip("0") or "0"))
b["data_pag"] = pd.to_datetime(b["data_pag"], utc=True)

# Casos suspeitos
suspeitos = todos[todos["dias_pag_vs_venc"] < 0].copy()
print(f"Casos onde data_pag < venc_card (potencial contradição): {len(suspeitos)}")
print()

# Anexar info adicional do CSV original (num_boleto, valor, juros_adm)
suspeitos = suspeitos.merge(
    b[["cd_imovel_int", "data_pag", "mes_ref", "num_boleto", "valor", "multa_adm", "juros_adm"]]
        .rename(columns={"cd_imovel_int": "cd_imovel", "multa_adm": "_multa_raw", "juros_adm": "_juros_raw"}),
    on=["cd_imovel", "data_pag", "mes_ref"], how="left", suffixes=("", "_csv")
)

# Anexar Imoveis (proprietário, endereço)
imov = dfs["imoveis"].copy()
imov["cd_imovel_int"] = imov["cd_imovel"].apply(lambda v: int(str(v).strip().lstrip("0") or "0"))
suspeitos = suspeitos.merge(
    imov[["cd_imovel_int", "id_proprietario", "endereco"]].rename(columns={"cd_imovel_int": "cd_imovel"}),
    on="cd_imovel", how="left"
)

# Anexar Proprietarios (nome)
props = dfs["proprietarios"].copy()
props["id_p_norm"] = props["id_proprietario"].apply(
    lambda v: int(str(v).strip().lstrip("0") or "0")
)
suspeitos["id_p_norm"] = suspeitos["id_proprietario"].apply(
    lambda v: int(str(v).strip().lstrip("0") or "0") if pd.notna(v) else None
)
suspeitos = suspeitos.merge(
    props[["id_p_norm", "nome"]].rename(columns={"nome": "nome_proprietario_imobiliar"}),
    on="id_p_norm", how="left"
)

# Anexar info do card via id
df_inad_full = df_inad.copy()
df_inad_full["card_id"] = df_inad_full["id"]
suspeitos = suspeitos.merge(
    df_inad_full[["card_id", "Título", "Vencimento 1º Boleto:", "Fase atual", "Criado em", "Responsáveis"]]
        .rename(columns={
            "Título": "card_titulo_full",
            "Vencimento 1º Boleto:": "card_venc_full",
            "Fase atual": "card_fase",
            "Criado em": "card_criado",
            "Responsáveis": "card_responsaveis",
        }),
    on="card_id", how="left"
)

# Mostrar todos os casos (ou primeiros 5)
print(f"Mostrando {min(5, len(suspeitos))} casos:\n")
for i, (_, row) in enumerate(suspeitos.head(5).iterrows(), 1):
    print(f"━━━ Caso {i} ━━━")
    print(f"BOLETO:")
    print(f"  cd_imovel    : {row['cd_imovel']}")
    print(f"  num_boleto   : {row.get('num_boleto', '—')!r}")
    print(f"  mes_ref      : {row['mes_ref']}")
    print(f"  valor        : R$ {row.get('valor', '—')}")
    print(f"  multa_adm    : R$ {row.get('_multa_raw', row.get('multa_adm', '—'))}")
    print(f"  juros_adm    : R$ {row.get('_juros_raw', row.get('juros_adm', '—'))}")
    print(f"  data_pag     : {row['data_pag'].date()}")
    print(f"CARD DE INADIMPLÊNCIA (casado):")
    print(f"  card_id          : {row['card_id']}")
    print(f"  Título           : {row.get('card_titulo_full', row.get('card_titulo', '—'))}")
    print(f"  Vencimento 1º    : {row['card_venc_full'].date() if pd.notna(row.get('card_venc_full')) else '—'}")
    print(f"  Fase atual       : {row.get('card_fase', '—')}")
    print(f"  Criado em        : {row.get('card_criado', '—')}")
    print(f"  Responsáveis     : {row.get('card_responsaveis', '—')}")
    print(f"IMÓVEL / PROPRIETÁRIO (Imobiliar):")
    print(f"  IM (cd_imovel)      : {row['cd_imovel']}")
    print(f"  Endereço            : {row.get('endereco', '—')}")
    print(f"  id_proprietario     : {row.get('id_p_norm', '—')}")
    print(f"  Nome proprietário   : {row.get('nome_proprietario_imobiliar', '—')}")
    print(f"DIFF:")
    print(f"  data_pag - venc_card = {row['dias_pag_vs_venc']} dias  (negativo = pagamento ANTES do venc do card)")
    print()
