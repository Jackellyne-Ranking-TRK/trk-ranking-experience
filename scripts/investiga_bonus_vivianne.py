"""
Investigação do drift -21 boletos no bônus Vivianne (calc N=103 vs baseline N=124).

NÃO modifica nenhum módulo de produção. Apenas leitura e diagnóstico.
"""
from __future__ import annotations
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pipeline.extract_imobiliar import extract_imobiliar, calcular_bonus_inadimplencia, _data_repasse
from pipeline.extract_pipefy import extract_pipe
from calculate import excluir_rascunhos, aplicar_cutoff

# ──────────────────────────────────────────────────────────────
# 1. PIPE INADIMPLÊNCIA — formato de Título e cobertura
# ──────────────────────────────────────────────────────────────
print("=" * 100)
print("4. PIPE INADIMPLÊNCIA — análise de Títulos (parser de IM)")
print("=" * 100)

df_inad_raw = extract_pipe("inadimplencia", verbose=False)
df_inad_180 = aplicar_cutoff(df_inad_raw, "Criado em")
print(f"Total cards no pipe: {len(df_inad_raw)}")
print(f"Após cutoff 180d:    {len(df_inad_180)}")
print()

# Classificar formatos de Título
def _classify(t):
    s = str(t).strip()
    if s.upper().startswith("P"):
        return "P-prefix (proprietário)"
    if re.match(r"IM\s*\d+", s, re.IGNORECASE):
        return "IM-prefix"
    try:
        int(float(s))
        return "Numérico puro"
    except (ValueError, TypeError):
        return "Outro"

df_inad_180 = df_inad_180.copy()
df_inad_180["_fmt"] = df_inad_180["Título"].apply(_classify)
print("Formatos detectados:")
for f, n in df_inad_180["_fmt"].value_counts().to_dict().items():
    print(f"  {f}: {n}")
print()
print("Sample de 10 títulos:")
for t in df_inad_180["Título"].head(10):
    print(f"  - {t}")
print()

# Parser atual (do produto)
def _parse_im(t):
    s = str(t).strip()
    if s.upper().startswith("P"):
        return None
    m = re.match(r"IM\s*(\d+)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None

ims_parsed = df_inad_180["Título"].apply(_parse_im)
print(f"IMs extraídos com sucesso: {ims_parsed.notna().sum()} / {len(df_inad_180)}")
print(f"Títulos onde parser falha: {ims_parsed.isna().sum()}")
falhas = df_inad_180[ims_parsed.isna()]["Título"].tolist()
print(f"  → desses, P-prefix (descarte intencional): {sum(1 for t in falhas if str(t).upper().startswith('P'))}")
outros = [t for t in falhas if not str(t).upper().startswith("P")]
print(f"  → desses, formato 'Outro' (parser falha real): {len(outros)}")
if outros:
    print(f"    samples: {outros[:10]}")
print(f"IMs únicos extraídos: {ims_parsed.dropna().nunique()}")
print()

# ──────────────────────────────────────────────────────────────
# 2. FUNIL DE 4 FONTES
# ──────────────────────────────────────────────────────────────
print("=" * 100)
print("3. SANITY CHECK FUNIL — onde os boletos são perdidos")
print("=" * 100)

dfs = extract_imobiliar(verbose=False)
boletos = dfs["boletos"]
imoveis = dfs["imoveis"]
props = dfs["proprietarios"]

b = boletos.copy()
b["com_encargo"] = (b["multa_adm"] > 0) | (b["juros_adm"] > 0)
b_enc = b[b["com_encargo"]].copy()
n_enc = len(b_enc)
print(f"a) Boletos com encargo (Multa>0 OU Juros>0):           {n_enc}")

def _norm_cd(v):
    try:
        return int(str(v).strip().lstrip("0") or "0")
    except (ValueError, TypeError):
        return None

b_enc["cd"] = b_enc["cd_imovel"].apply(_norm_cd)
imoveis2 = imoveis.copy()
imoveis2["cd"] = imoveis2["cd_imovel"].apply(_norm_cd)
imov_set = set(imoveis2["cd"].dropna().astype(int).tolist())
n_imovel_ok = b_enc["cd"].isin(imov_set).sum()
print(f"b) Desses, com cd_imovel em Imoveis.csv:               {int(n_imovel_ok)}  (perdidos: {n_enc - int(n_imovel_ok)})")

b_enc2 = b_enc.merge(imoveis2[["cd", "id_proprietario"]], on="cd", how="left")
b_enc2["id_p"] = b_enc2["id_proprietario"].apply(_norm_cd)
props2 = props.copy()
props2["id_p"] = props2["id_proprietario"].apply(_norm_cd)
b_enc2 = b_enc2.merge(props2[["id_p", "dia_pag", "nome"]], on="id_p", how="left")
n_diapag = b_enc2["dia_pag"].notna().sum()
print(f"c) Desses, com proprietário em Proprietarios.csv (qualquer): {int((b_enc2['nome'].notna()).sum())}")
print(f"d) Desses, com dia_pag cadastrado:                     {int(n_diapag)}")

ims_inad_set = set(ims_parsed.dropna().astype(int).tolist())
b_enc2_ok = b_enc2.dropna(subset=["dia_pag"]).copy()
b_enc2_ok["tem_card"] = b_enc2_ok["cd"].apply(lambda im: im in ims_inad_set if pd.notna(im) else False)
n_card = b_enc2_ok["tem_card"].sum()
print(f"e) Desses, com card no pipe Inadimplência (qualquer):  {int(n_card)}")

# Calcular data_repasse e antes_repasse
b_enc2_ok["dia_pag"] = b_enc2_ok["dia_pag"].astype(int)
b_enc2_ok["data_repasse"] = [_data_repasse(r.mes_ref, r.dia_pag) for r in b_enc2_ok.itertuples(index=False)]
b_enc2_ok["antes_repasse"] = [
    (r.data_pag is not None and not pd.isna(r.data_pag)
     and r.data_repasse is not None and r.data_pag <= r.data_repasse)
    for r in b_enc2_ok.itertuples(index=False)
]
N_final = int((b_enc2_ok["antes_repasse"] & b_enc2_ok["tem_card"]).sum())
print(f"f) Desses, Data Pag ≤ data_repasse:                    N={N_final}")
print()

# ──────────────────────────────────────────────────────────────
# 1bis. INVESTIGAR OS 6 "PASSARAM BATIDO"
# ──────────────────────────────────────────────────────────────
print("=" * 100)
print("1. OS 6 'PASSARAM BATIDO' — tentar cruzamentos alternativos")
print("=" * 100)

sem_card = b_enc2_ok[b_enc2_ok["antes_repasse"] & ~b_enc2_ok["tem_card"]].copy()
print(f"Total: {len(sem_card)}")
print()

# Para cada um, ver se há card com nome de proprietário no Título
def _has_any_card_by_name(nome, df_inad_180_):
    if not isinstance(nome, str):
        return False
    primeiros = nome.split()[:2]
    if not primeiros:
        return False
    needle = " ".join(primeiros).upper()
    return df_inad_180_["Título"].astype(str).str.upper().str.contains(needle, regex=False, na=False).any()

print(f"{'cd':>5}  {'IM':>5}  {'nome_proprietario':>40}  card_por_nome?")
print("-" * 75)
for _, r in sem_card.iterrows():
    cd = r["cd"]
    nome = r.get("nome") or ""
    hit = _has_any_card_by_name(nome, df_inad_180)
    print(f"  {cd:>5}  {cd:>5}  {nome[:40]:>40}  {hit}")
print()

# ──────────────────────────────────────────────────────────────
# 2. INVESTIGAR OS 33 "DEPOIS DO REPASSE"
# ──────────────────────────────────────────────────────────────
print("=" * 100)
print("2. OS 33 'COBRADOS APÓS REPASSE' — sanity check da data_repasse")
print("=" * 100)
depois = b_enc2_ok[~b_enc2_ok["antes_repasse"]].copy()
print(f"Total: {len(depois)}\n")
print("Sample de 10 (com cálculo passo-a-passo):")
print()
for i, (_, r) in enumerate(depois.head(10).iterrows()):
    cd, mes_ref, dia_pag, data_pag, data_rep = r["cd"], r["mes_ref"], r["dia_pag"], r["data_pag"], r["data_repasse"]
    dp_s = data_pag.date().isoformat() if pd.notna(data_pag) else "—"
    dr_s = data_rep.date().isoformat() if data_rep is not None else "—"
    print(f"  cd_imovel={cd}  mes_ref={mes_ref}  dia_pag={dia_pag}")
    print(f"    → data_repasse = mês seguinte ao mes_ref no dia {dia_pag} = {dr_s}")
    print(f"    → data_pag = {dp_s}")
    delta = (data_pag.date() - data_rep.date()).days if pd.notna(data_pag) and data_rep is not None else None
    print(f"    → diff = {delta} dias  ({'ANTES' if delta is not None and delta<=0 else 'DEPOIS'})")
    print()

# ──────────────────────────────────────────────────────────────
# 5. CONCLUSÃO — funil completo
# ──────────────────────────────────────────────────────────────
print("=" * 100)
print("5. CONCLUSÃO — funil consolidado")
print("=" * 100)
print(f"""
Funil:
  a) Total com encargo:                     {n_enc}
  b) Com cd_imovel em Imoveis.csv:          {int(n_imovel_ok)}  (perdidos: {n_enc - int(n_imovel_ok)})
  c) Com proprietário em Props parser:       {int(b_enc2['nome'].notna().sum())}  (perdidos: {int(n_imovel_ok) - int(b_enc2['nome'].notna().sum())})
  d) Com dia_pag cadastrado:                 {int(n_diapag)}  (perdidos: {int(b_enc2['nome'].notna().sum()) - int(n_diapag)})
  e) Com card no pipe Inadimplência:         {int(n_card)}  (perdidos: {int(n_diapag) - int(n_card)})
  f) Data Pag ≤ data_repasse:                N={N_final}

Baseline 10ª: N=124  /  Calculado: N={N_final}  /  Δ = {N_final - 124}
""")
