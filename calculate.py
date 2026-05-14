"""
TRK Experience — Pipeline de Cálculo de Ranking
================================================

Este módulo aplica as regras do manual_v4.md sobre DataFrames extraídos
do Pipefy/Octadesk e retorna a estrutura PESSOAS / IMOVEIS / PROC_RICH
que alimenta o painel.

ARQUITETURA:
    extract_*.py → DataFrames com nomes de coluna idênticos aos XLSX atuais
                ↓
    calculate.py → aplica regras do manual, retorna scores por indicador
                ↓
    validate.py  → compara com baselines.json
                ↓
    run.py       → orquestra tudo, salva dados/atual.json

CONVENÇÕES:
    - Toda função `calc_<colaborador>_<processo>()` retorna:
        {"score": float, "indicadores": [{"nome", "ok", "tot", "pct", "peso", "score"}]}
    - Score de cada indicador = (ok / tot) * peso
    - Nota do processo = sum(scores) / sum(pesos) * 10
    - Nota final do colaborador = média simples das notas de processo não-nulas
    - Bônus: (score_base + N) / (peso_base + N) * 10

CRÍTICO — releia o manual antes de mexer:
    - Cutoff 180d rolando, exceto Caio Cont.ADM (01/03/2026) e DIRF/DARF (29/05/2026)
    - Horas úteis: 08-18 seg-sex
    - Timestamps negativos = 0h (✓), não excluir
    - Rascunhos: excluir cards com "rascunho" em qualquer campo de texto
    - Tickets: excluir Categoria=Cancelado/Spam, Status=Cancelado, Assunto=Tarefa
"""

import json
import zoneinfo
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from typing import Optional

TZ_BSB = zoneinfo.ZoneInfo("America/Sao_Paulo")


# ─────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).resolve().parent / "config"
FEATURE_FLAGS = json.loads((CONFIG_DIR / "feature_flags.json").read_text(encoding="utf-8"))

CUTOFF_DIAS = 180
CUTOFF_CONT_ADM_CAIO_FIXO = datetime(2026, 3, 1)
DIRF_DARF_CUTOFF = datetime(2026, 5, 29)  # prorrogação oficial 2026
DIRF_DARF_ANO_BASE = 2025

NOMES_AGENTE = {
    "caio":      {"whatsapp": "Caio Rodrigues",   "ticket": "Caio Rodrigues"},
    "natalia":   {"whatsapp": "Natália Teixeira", "ticket": "Natália Teixeira"},
    "gardenia":  {"whatsapp": "Gardênia",         "ticket": "Gardênia"},
    "vivianne":  {"whatsapp": None,               "ticket": ["Vivianne Fontes", "VIVIANNE FONTES"]},  # WhatsApp EXCLUÍDO
}


# ─────────────────────────────────────────────────────────────────────
# HELPERS GERAIS
# ─────────────────────────────────────────────────────────────────────

def cutoff(dias: int = CUTOFF_DIAS, ref: Optional[datetime] = None) -> pd.Timestamp:
    """
    Retorna o cutoff (ref - dias) como Timestamp tz-aware UTC.
    `ref` permite reproducibilidade contra baseline (Maio/2026 etc).
    Default: agora em UTC.
    """
    base = pd.Timestamp(ref) if ref is not None else pd.Timestamp.utcnow()
    if base.tzinfo is None:
        base = base.tz_localize("UTC")
    return base - pd.Timedelta(days=dias)


def aplicar_cutoff(df: pd.DataFrame, coluna: str, *, dias: int = CUTOFF_DIAS,
                   ref: Optional[datetime] = None, data_fixa: Optional[datetime] = None) -> pd.DataFrame:
    """
    Filtra df mantendo apenas linhas onde `coluna >= cutoff`.
    Se `data_fixa` fornecida, usa-a como cutoff (ex: Caio Cont.ADM = 01/03/2026).
    """
    if data_fixa is not None:
        limit = pd.Timestamp(data_fixa)
        if limit.tzinfo is None:
            limit = limit.tz_localize("UTC")
    else:
        limit = cutoff(dias=dias, ref=ref)
    if coluna not in df.columns:
        return df.iloc[0:0].copy()
    col = pd.to_datetime(df[coluna], errors="coerce", utc=True)
    return df[col >= limit].copy()


def excluir_rascunhos(df: pd.DataFrame) -> pd.DataFrame:
    """Remove cards onde Título, Imóvel ou Endereço contenham 'rascunho' (case insensitive)."""
    cols_texto = [c for c in ["Título", "Imóvel", "Endereço"] if c in df.columns]
    if not cols_texto:
        return df
    mask = pd.Series([False] * len(df), index=df.index)
    for col in cols_texto:
        mask |= df[col].astype(str).str.contains("rascunho", case=False, na=False)
    return df[~mask].copy()


# ─────────────────────────────────────────────────────────────────────
# Helpers — assignees, IMs, fases
# ─────────────────────────────────────────────────────────────────────

def _as_list(v) -> list[str]:
    """Normaliza valor de assignee_select para list[str], lidando com None/string/lista."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    s = str(v).strip()
    if not s:
        return []
    # tenta JSON
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return [str(x).strip() for x in arr if x]
        except json.JSONDecodeError:
            pass
    return [s]


def contem_assignee(valor, nome: str) -> bool:
    """
    True se `nome` (case-insensitive, ignorando acentos básicos) aparece em algum item de `valor`.
    `valor` pode ser lista, string ou JSON-string.
    """
    target = nome.lower()
    for it in _as_list(valor):
        if target in it.lower():
            return True
    return False


def filtrar_por_assignee(df: pd.DataFrame, coluna: str, nome: str) -> pd.DataFrame:
    """Mantém linhas onde `coluna` contém `nome` (caso-insensível) em algum dos assignees."""
    if coluna not in df.columns:
        return df.iloc[0:0].copy()
    mask = df[coluna].apply(lambda v: contem_assignee(v, nome))
    return df[mask].copy()


IM_REGEX = __import__("re").compile(r"IM\s*(\d+)", __import__("re").IGNORECASE)


def extrair_im(texto) -> Optional[int]:
    """Extrai 'IM 123' ou 'IM123' de uma string. Retorna int ou None."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return None
    # se for lista (connector), tenta cada item
    if isinstance(texto, list):
        for t in texto:
            n = extrair_im(t)
            if n is not None:
                return n
        return None
    s = str(texto)
    # JSON-string de connector vira lista
    if s.startswith("["):
        try:
            return extrair_im(json.loads(s))
        except json.JSONDecodeError:
            pass
    m = IM_REGEX.search(s)
    return int(m.group(1)) if m else None


def _to_bsb_naive(dt) -> Optional[pd.Timestamp]:
    """
    Converte para Brasília naive. Se já naive, assume está em horário de Brasília.
    Retorna None se input for NaT/None.
    """
    if dt is None or pd.isna(dt):
        return None
    ts = pd.Timestamp(dt)
    if ts.tzinfo is None:
        return ts
    return ts.tz_convert(TZ_BSB).tz_localize(None)


def horas_uteis(inicio, fim) -> float:
    """
    Horas úteis (08:00–18:00, seg-sex) entre inicio e fim, em horário de Brasília.

    Regras (manual §3.3):
    - NaT/None em qualquer lado → NaN.
    - fim <= inicio (negativo ou zero) → 0.0 (= cumprido ✓).
    - Sábado e domingo: 0 horas.
    - Fora de 08-18: descontado.
    - 1 dia útil = 10 horas úteis.
    """
    a = _to_bsb_naive(inicio)
    b = _to_bsb_naive(fim)
    if a is None or b is None:
        return float("nan")
    if b <= a:
        return 0.0

    BS, BE = 8, 18  # 8h–18h
    total_seconds = 0.0
    dia = a.normalize()  # 00:00 do dia de início
    fim_dia = b.normalize()
    while dia <= fim_dia:
        if dia.weekday() < 5:  # 0=seg ... 4=sex
            day_start = dia.replace(hour=BS)
            day_end = dia.replace(hour=BE)
            window_start = max(a, day_start)
            window_end = min(b, day_end)
            if window_end > window_start:
                total_seconds += (window_end - window_start).total_seconds()
        dia = dia + timedelta(days=1)
    return total_seconds / 3600.0


def dias_uteis(inicio: pd.Timestamp, fim: pd.Timestamp) -> float:
    """Wrapper: horas úteis ÷ 10."""
    return horas_uteis(inicio, fim) / 10.0


def horas_corridas(inicio: pd.Timestamp, fim: pd.Timestamp) -> float:
    """Diferença em horas corridas. Negativo → 0."""
    if pd.isna(inicio) or pd.isna(fim):
        return float("nan")
    delta = (fim - inicio).total_seconds() / 3600
    return max(delta, 0.0)


def dias_corridos(inicio: pd.Timestamp, fim: pd.Timestamp) -> float:
    """Diferença em dias corridos. Negativo → 0."""
    return horas_corridas(inicio, fim) / 24.0


def score_indicador(ok: int, tot: int, peso: float) -> dict:
    """Retorna estrutura padrão de um indicador."""
    pct = round(100 * ok / tot, 1) if tot > 0 else None
    score = round((ok / tot) * peso, 3) if tot > 0 else None
    return {"ok": ok, "tot": tot, "pct": pct, "peso": peso, "score": score}


def nota_processo(indicadores: list, bonus_n: int = 0) -> Optional[float]:
    """
    Calcula nota do processo (0-10).

    Fórmula base:    sum(scores) / sum(pesos) * 10
    Fórmula bônus:   (sum(scores) + bonus_n) / (sum(pesos) + bonus_n) * 10

    Indicadores sem dados (tot=0) são excluídos.
    Se todos sem dados, retorna None.
    """
    validos = [i for i in indicadores if i["tot"] > 0]
    if not validos:
        return None
    soma_scores = sum(i["score"] for i in validos)
    soma_pesos = sum(i["peso"] for i in validos)
    return round((soma_scores + bonus_n) / (soma_pesos + bonus_n) * 10, 3)


def nota_final(scores_processos: dict) -> Optional[float]:
    """Média simples das notas de processo não-nulas."""
    validas = [v for v in scores_processos.values() if v is not None]
    if not validas:
        return None
    return round(sum(validas) / len(validas), 2)


# ─────────────────────────────────────────────────────────────────────
# CAIO — COMERCIAL
# ─────────────────────────────────────────────────────────────────────

def _now_ref(ref: Optional[datetime] = None) -> pd.Timestamp:
    """Retorna timestamp tz-aware usado como 'hoje'. UTC."""
    base = pd.Timestamp(ref) if ref is not None else pd.Timestamp.utcnow()
    if base.tzinfo is None:
        base = base.tz_localize("UTC")
    return base


def _expected_phase_desocupacao(days: float) -> Optional[str]:
    """Mapa de intervalo de dias desocupado → fase esperada (manual §4.1)."""
    if days < 0 or pd.isna(days):
        return None
    if days <= 5:
        return "Conferência Final"
    if days <= 29:
        return "15 dias desocupado"
    if days <= 59:
        return "30 Dias desocupado"
    if days <= 89:
        return "60 Dias desocupado"
    if days <= 179:
        return "90 Dias desocupado"
    return "180 Dias desocupado"


def calc_caio_comercial_locacao(df_comercial: pd.DataFrame, bonus_n: int = 0,
                                ref: Optional[datetime] = None) -> dict:
    """
    Caio · Comercial Locação · 3 indicadores · peso 10 · bônus aplicado aqui.

    Indicador 1: Início <24h (peso 2.5) — Criado em → Primeira vez Avaliação Técnica, corrido
    Indicador 2: Anúncio <72h (peso 2.5) — Última saída Aval.Téc OU Cadastro/NIDO → Publicação
    Indicador 3: Coluna correta (peso 5) — fase atual vs intervalo desocupação

    Bônus: imóvel alugado antes de anunciado — passado como bonus_n já calculado.
    """
    # Filtros: cutoff 180d em Criado em, Caio em Profissional responsável, sem rascunho
    df = excluir_rascunhos(df_comercial)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    df = filtrar_por_assignee(df, "Profissional responsável", "Caio")

    # ─── Indicador 1: Início <24h corrido (Criado → Avaliação Técnica) ───
    col_avt_in = "Primeira vez que entrou na fase Avaliação Técnica"
    df1 = df.dropna(subset=[col_avt_in])  # denominator = cards que entraram em Aval.Téc
    delta_h = (df1[col_avt_in] - df1["Criado em"]).dt.total_seconds() / 3600
    delta_h = delta_h.clip(lower=0)       # negativos = 0 (✓)
    ind1 = score_indicador(int((delta_h <= 24).sum()), len(df1), 2.5)
    ind1["nome"] = "Comercial — Início processo <24h"

    # ─── Indicador 2: Anúncio <72h corrido (saída Aval.Téc OU NIDO → Publicação) ───
    col_avt_out = "Última vez que saiu da fase Avaliação Técnica"
    col_nido_out = "Última vez que saiu da fase Cadastro / Reativação no NIDO"
    col_pub = "Data publicação Anúncio"
    # Liberação = saída AvalTec; fallback = saída Cadastro/NIDO
    liberacao = df[col_avt_out].where(df[col_avt_out].notna(), df[col_nido_out])
    # Denominador: cards que saíram da Aval.Téc OU foram publicados
    mask_den = liberacao.notna() | df[col_pub].notna()
    df2 = df[mask_den].copy()
    lib2 = liberacao[mask_den]
    pub2 = df2[col_pub]
    # Numerador: (publicação - liberação) ≤ 72h corrido. Se liberação ou publicação ausente → falha.
    delta_h2 = (pub2 - lib2).dt.total_seconds() / 3600
    delta_h2 = delta_h2.clip(lower=0)
    ok2 = int((delta_h2 <= 72).sum())
    ind2 = score_indicador(ok2, len(df2), 2.5)
    ind2["nome"] = "Comercial — Anúncio publicado <72h"

    # ─── Indicador 3: Coluna correta ───
    col_cf_in = "Primeira vez que entrou na fase Conferência Final"
    now = _now_ref(ref)
    # Denominador: passou por Conferência Final E não está em Concluído
    mask3 = df[col_cf_in].notna() & (df["Fase atual"] != "Concluído")
    df3 = df[mask3].copy()
    dias_desocup = (now - df3[col_pub]).dt.total_seconds() / 86400.0
    expected = dias_desocup.apply(_expected_phase_desocupacao)
    ok3 = int((df3["Fase atual"] == expected).sum())
    ind3 = score_indicador(ok3, len(df3), 5)
    ind3["nome"] = "Comercial — Card na coluna correta"

    indicadores = [ind1, ind2, ind3]
    return {
        "nota": nota_processo(indicadores, bonus_n=bonus_n),
        "indicadores": indicadores,
    }


def calc_caio_contrato_locacao(df_comercial: pd.DataFrame, df_cont_loc: pd.DataFrame,
                               ref: Optional[datetime] = None) -> dict:
    """
    Caio · Cont. Locação · 2 indicadores · peso 10.

    Indicador 4: Ocupação <30d (peso 6) — Data pub Anúncio (Comercial) → 1º Boleto (Cont.Loc),
        cruzamento via IM. Pareamento: para cada 1º Boleto, parear com anúncio anterior + próximo.
        Excluir 'alugado antes de re-anunciar' (anúncio posterior ao boleto).
    Indicador 5: Documentação <24h úteis (peso 4) — Criado em → Entrada Confecção do contrato de locação.
    """
    com = excluir_rascunhos(df_comercial)
    com = aplicar_cutoff(com, "Criado em", ref=ref)
    com = filtrar_por_assignee(com, "Profissional responsável", "Caio")

    cl = excluir_rascunhos(df_cont_loc)
    cl = aplicar_cutoff(cl, "Criado em", ref=ref)

    # ── Indicador 4: Ocupação <30d (cross-pipe) ──
    col_pub = "Data publicação Anúncio"
    col_boleto = "Primeira vez que entrou na fase 1º Boleto"
    pub_por_im: dict[int, list[pd.Timestamp]] = {}
    for im_val, pub in com[["IM", col_pub]].dropna(subset=[col_pub]).itertuples(index=False):
        if pd.isna(im_val):
            continue
        pub_por_im.setdefault(int(im_val), []).append(pd.Timestamp(pub))

    bol_por_im: dict[int, list[pd.Timestamp]] = {}
    for imovel_val, bol in cl[["Imóvel", col_boleto]].itertuples(index=False):
        if pd.isna(bol):
            continue
        im = extrair_im(imovel_val)
        if im is None:
            continue
        bol_por_im.setdefault(im, []).append(pd.Timestamp(bol))

    ims_comum = sorted(set(pub_por_im) & set(bol_por_im))
    ok4, tot4 = 0, 0
    for im in ims_comum:
        pubs = sorted(pub_por_im[im])
        for bol in sorted(bol_por_im[im]):
            # parear com publicação ANTERIOR mais próxima
            anteriores = [p for p in pubs if p <= bol]
            posteriores = [p for p in pubs if p > bol]
            if not anteriores:
                if posteriores:
                    continue  # "alugado antes de re-anunciar" → EXCLUIR
                continue      # sem anúncio no período → não medível
            pub_mais_proxima = anteriores[-1]
            dias = (bol - pub_mais_proxima).total_seconds() / 86400.0
            dias = max(dias, 0.0)  # negativos = 0 (✓)
            tot4 += 1
            if dias <= 30:
                ok4 += 1
    ind4 = score_indicador(ok4, tot4, 6)
    ind4["nome"] = "Cont. Locação — Ocupação <30d"

    # ── Indicador 5: Documentação <24h úteis ──
    col_conf_in = "Primeira vez que entrou na fase Confecção do contrato de locação"
    cl5 = cl.dropna(subset=[col_conf_in])
    horas = cl5.apply(lambda r: horas_uteis(r["Criado em"], r[col_conf_in]), axis=1)
    ok5 = int((horas <= 24).sum())
    ind5 = score_indicador(ok5, len(cl5), 4)
    ind5["nome"] = "Cont. Locação — Documentação <24h"

    indicadores = [ind4, ind5]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_caio_contrato_adm(df_cont_adm: pd.DataFrame,
                           ref: Optional[datetime] = None) -> dict:
    """
    Caio · Cont. ADM · 1 indicador · peso 10.

    Indicador 6: Criação → Primeira vez fase 'Contrato assinado - Conferir Nido' <7d corrido.
    Cutoff FIXO 01/03/2026. Pipe compartilhado — sem filtro pessoal (Caio responde pela ponta comercial).
    """
    df = excluir_rascunhos(df_cont_adm)
    df = aplicar_cutoff(df, "Criado em", data_fixa=CUTOFF_CONT_ADM_CAIO_FIXO)

    col_nido = "Primeira vez que entrou na fase Contrato assinado - Conferir Nido"
    df6 = df.dropna(subset=[col_nido]).copy()
    dias = (df6[col_nido] - df6["Criado em"]).dt.total_seconds() / 86400.0
    dias = dias.clip(lower=0)
    ok6 = int((dias < 7).sum())
    ind6 = score_indicador(ok6, len(df6), 10)
    ind6["nome"] = "Cont. ADM — Criação→NIDO <7d"

    return {"nota": nota_processo([ind6]), "indicadores": [ind6]}


def calc_caio_renovacao(df_renov: pd.DataFrame,
                       ref: Optional[datetime] = None) -> dict:
    """
    Caio · Renovação · 1 indicador EXCLUSIVO · peso 10.

    Indicador 7: Avaliação >90d antes vencimento — Data de vencimento − Última saída Avaliação de mercado.
    Sem filtro pessoal (Caio responde pelo lado comercial da renovação).
    """
    df = excluir_rascunhos(df_renov)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_aval_out = "Última vez que saiu da fase Avaliação de mercado"
    col_venc = "Data de vencimento"
    df7 = df.dropna(subset=[col_aval_out, col_venc]).copy()
    dias = (df7[col_venc] - df7[col_aval_out]).dt.total_seconds() / 86400.0
    ok7 = int((dias > 90).sum())
    ind7 = score_indicador(ok7, len(df7), 10)
    ind7["nome"] = "Renovação — Avaliação >90d"

    return {"nota": nota_processo([ind7]), "indicadores": [ind7]}


# ─────────────────────────────────────────────────────────────────────
# OCTADESK — helpers compartilhados (WhatsApp + Tickets)
# ─────────────────────────────────────────────────────────────────────

WA_POS = {"Satisfeito", "Muito satisfeito"}
WA_EXC = {"Não respondeu", "Não enviado"}
TKT_AVAL_POS = {"Bom", "Bom com comentário"}
TKT_AVAL_EXC = {"Não respondeu", "Não enviado"}

COL_WA_RESP   = "Responsável da conversa"
COL_WA_TEMPO  = "Tempo de espera após atribuição"
COL_WA_SAT    = "Pesquisa de satisfação"

COL_TKT_CAT    = "Categoria de assunto do ticket"
COL_TKT_STATUS = "Status do ticket"
COL_TKT_ASSUNTO = "Assunto do ticket"
COL_TKT_RESP   = "Responsável do ticket"
COL_TKT_IN     = "Data de entrada"
COL_TKT_RESP_T = "Data da primeira resposta"
COL_AVAL_RESP  = "Responsável do ticket"
COL_AVAL_TIPO  = "Tipo de avaliação"


def _parse_hms(s) -> Optional[float]:
    """'H:MM:SS' → minutos (float). None se inválido/NaN."""
    if not isinstance(s, str):
        return None
    parts = s.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, ss = int(parts[0]), int(parts[1]), int(parts[2])
        return h * 60 + m + ss / 60.0
    except ValueError:
        return None


def _match_nome(serie: pd.Series, nome) -> pd.Series:
    """
    Mask booleana de match EXATO (case-insensitive), aceitando str ou lista de variantes.

    Match exato evita falsos positivos quando o sistema externo (Octadesk) tem
    homônimos parciais — por exemplo, "Caio Rodrigues" não deve casar com algum
    futuro "Caio Silva". Para Vivianne, a lista contempla "Vivianne Fontes" e
    "VIVIANNE FONTES" (variantes confirmadas em snapshots históricos).
    """
    s = serie.astype(str).str.strip().str.upper()
    if isinstance(nome, list):
        targets = {n.strip().upper() for n in nome}
        return s.isin(targets)
    return s == nome.strip().upper()


def _whatsapp_indicadores(df_conv: pd.DataFrame, nome_responsavel,
                           peso_resposta: int = 4, peso_aval: int = 3) -> list[dict]:
    """Retorna 2 indicadores de WhatsApp para um responsável."""
    if df_conv is None or len(df_conv) == 0 or COL_WA_RESP not in df_conv.columns:
        return []
    df = df_conv[_match_nome(df_conv[COL_WA_RESP], nome_responsavel)].copy()

    # Ind 1: Resposta ≤5min
    tempo_min = df[COL_WA_TEMPO].apply(_parse_hms) if COL_WA_TEMPO in df.columns else pd.Series(dtype=float)
    val = tempo_min.dropna()
    ok1 = int((val <= 5).sum())
    ind1 = score_indicador(ok1, len(val), peso_resposta)
    ind1["nome"] = "WhatsApp — Resposta ≤5min"

    # Ind 2: Avaliações positivas
    if COL_WA_SAT in df.columns:
        sat = df[COL_WA_SAT].astype(str)
        denom = sat[~sat.isin(WA_EXC) & sat.notna() & (sat != "nan")]
        ok2 = int(denom.isin(WA_POS).sum())
    else:
        ok2, denom = 0, []
    ind2 = score_indicador(ok2, len(denom), peso_aval)
    ind2["nome"] = "WhatsApp — Avaliações positivas"

    return [ind1, ind2]


def _tickets_filtrados(df_tickets: pd.DataFrame, nome_responsavel) -> pd.DataFrame:
    """Aplica exclusões obrigatórias (manual §3.8) + filtro por responsável."""
    if df_tickets is None or len(df_tickets) == 0:
        return df_tickets if df_tickets is not None else pd.DataFrame()
    df = df_tickets.copy()
    # Exclusões
    if COL_TKT_CAT in df.columns:
        df = df[df[COL_TKT_CAT].astype(str) != "Cancelado / Spam"]
    if COL_TKT_STATUS in df.columns:
        df = df[df[COL_TKT_STATUS].astype(str) != "Cancelado"]
    if COL_TKT_ASSUNTO in df.columns:
        df = df[df[COL_TKT_ASSUNTO].astype(str).str.lower() != "tarefa"]
    # Filtro responsável
    if COL_TKT_RESP in df.columns:
        df = df[_match_nome(df[COL_TKT_RESP], nome_responsavel)]
    else:
        df = df.iloc[0:0]
    return df.copy()


def _ticket_sla_ind(df_filtrado: pd.DataFrame, peso: int) -> dict:
    """SLA ≤4h úteis (Data de entrada → Data da primeira resposta)."""
    if len(df_filtrado) == 0 or COL_TKT_IN not in df_filtrado.columns or COL_TKT_RESP_T not in df_filtrado.columns:
        ind = score_indicador(0, 0, peso)
    else:
        sub = df_filtrado.dropna(subset=[COL_TKT_IN, COL_TKT_RESP_T]).copy()
        h = sub.apply(lambda r: horas_uteis(r[COL_TKT_IN], r[COL_TKT_RESP_T]), axis=1) if len(sub) else pd.Series(dtype=float)
        ok = int((h <= 4).sum()) if len(sub) else 0
        ind = score_indicador(ok, len(sub), peso)
    ind["nome"] = "Tickets — SLA <4h úteis"
    return ind


def _ticket_aval_ind(df_aval: pd.DataFrame, nome_responsavel, peso: int) -> dict:
    """Avaliações positivas — "Bom" + "Bom com comentário"."""
    if df_aval is None or len(df_aval) == 0 or COL_AVAL_RESP not in df_aval.columns:
        ind = score_indicador(0, 0, peso)
    else:
        df = df_aval[_match_nome(df_aval[COL_AVAL_RESP], nome_responsavel)].copy()
        tipos = df[COL_AVAL_TIPO].astype(str) if COL_AVAL_TIPO in df.columns else pd.Series(dtype=str)
        denom = tipos[~tipos.isin(TKT_AVAL_EXC) & tipos.notna() & (tipos != "nan")]
        ok = int(denom.isin(TKT_AVAL_POS).sum())
        ind = score_indicador(ok, len(denom), peso)
    ind["nome"] = "Tickets — Avaliações positivas"
    return ind


# ─────────────────────────────────────────────────────────────────────
# CAIO — Octadesk
# ─────────────────────────────────────────────────────────────────────

def calc_caio_whatsapp(df_conv: pd.DataFrame) -> dict:
    """
    Caio · WhatsApp · 2 indicadores · peso 7.
    Filtro: Responsável da conversa = "Caio Rodrigues"
    """
    if df_conv is None or len(df_conv) == 0:
        return {"nota": None, "indicadores": []}
    indicadores = _whatsapp_indicadores(df_conv, NOMES_AGENTE["caio"]["whatsapp"],
                                         peso_resposta=4, peso_aval=3)
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_caio_ticket(df_tickets: pd.DataFrame, df_aval: pd.DataFrame) -> dict:
    """
    Caio · Ticket · 2 indicadores · peso 7.
    Filtro: Responsável do ticket contém "Caio"
    Exclusões: Categoria=Cancelado/Spam, Status=Cancelado, Assunto=Tarefa
    """
    if (df_tickets is None or len(df_tickets) == 0) and (df_aval is None or len(df_aval) == 0):
        return {"nota": None, "indicadores": []}
    nome = NOMES_AGENTE["caio"]["ticket"]
    df_t = _tickets_filtrados(df_tickets, nome)
    ind1 = _ticket_sla_ind(df_t, peso=4)
    ind2 = _ticket_aval_ind(df_aval, nome, peso=3)
    return {"nota": nota_processo([ind1, ind2]), "indicadores": [ind1, ind2]}


# ─────────────────────────────────────────────────────────────────────
# VIVIANNE — BackOffice + Inadimplência
# ─────────────────────────────────────────────────────────────────────

def calc_vivianne_contrato_adm(df_cont_adm: pd.DataFrame,
                               ref: Optional[datetime] = None) -> dict:
    """Vivianne · Cont. ADM · Confecção <2h úteis (peso 10)."""
    df = excluir_rascunhos(df_cont_adm)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    col_in = "Primeira vez que entrou na fase Confecção do contrato"
    col_out = "Última vez que saiu da fase Confecção do contrato"
    sub = df.dropna(subset=[col_in, col_out]).copy()
    horas = sub.apply(lambda r: horas_uteis(r[col_in], r[col_out]), axis=1)
    ok = int((horas <= 2).sum())
    ind = score_indicador(ok, len(sub), 10)
    ind["nome"] = "Cont. ADM — Confecção <2h"
    return {"nota": nota_processo([ind]), "indicadores": [ind]}


def calc_vivianne_rescisao_adm(df_resc_adm: pd.DataFrame,
                               ref: Optional[datetime] = None) -> dict:
    """Vivianne · Rescisão ADM · Encerramento <4h corrido (peso 10)."""
    df = excluir_rascunhos(df_resc_adm)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    col_in = "Primeira vez que entrou na fase Encerramento"
    col_out = "Última vez que saiu da fase Encerramento"
    sub = df.dropna(subset=[col_in, col_out]).copy()
    horas = (sub[col_out] - sub[col_in]).dt.total_seconds() / 3600
    horas = horas.clip(lower=0)
    ok = int((horas <= 4).sum())
    ind = score_indicador(ok, len(sub), 10)
    ind["nome"] = "Rescisão ADM — Encerramento <4h"
    return {"nota": nota_processo([ind]), "indicadores": [ind]}


def calc_vivianne_contrato_locacao(df_cont_loc: pd.DataFrame,
                                   ref: Optional[datetime] = None) -> dict:
    """
    Vivianne · Cont. Locação · 2 indicadores · peso 10.
    3a: NIDO→Concluído <24h corrido (peso 5)
    3b: Confecção <2h corrido (Pipefy: Tempo total na fase × 24h) (peso 5)
    """
    df = excluir_rascunhos(df_cont_loc)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    # 3a: NIDO→Concluído <24h corrido
    col_nido = "Primeira vez que entrou na fase Fechamento NIDO"
    col_concl = "Primeira vez que entrou na fase Concluído"
    sub_a = df.dropna(subset=[col_nido, col_concl]).copy()
    horas_a = (sub_a[col_concl] - sub_a[col_nido]).dt.total_seconds() / 3600
    horas_a = horas_a.clip(lower=0)
    ok_a = int((horas_a <= 24).sum())
    ind_a = score_indicador(ok_a, len(sub_a), 5)
    ind_a["nome"] = "Cont. Locação — NIDO→Concluído <24h"

    # 3b: Confecção <2h CORRIDO via Tempo total na fase × 24
    col_tempo_conf = "Tempo total na fase Confecção do contrato de locação (dias)"
    sub_b = df.dropna(subset=[col_tempo_conf]).copy()
    horas_b = sub_b[col_tempo_conf].astype(float) * 24
    ok_b = int((horas_b <= 2).sum())
    ind_b = score_indicador(ok_b, len(sub_b), 5)
    ind_b["nome"] = "Cont. Locação — Confecção <2h"

    indicadores = [ind_a, ind_b]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_vivianne_rescisao_locacao(df_resc_loc: pd.DataFrame,
                                   ref: Optional[datetime] = None) -> dict:
    """
    Vivianne · Rescisão Loc. · 2 indicadores BackOffice · peso 10.
    4a: Levant. Taxas Proporcionais <2h corrido (Pipefy col tempo × 24) (peso 5)
    4b: Levantamento de taxas <2h corrido (Pipefy col tempo × 24) (peso 5)
    """
    df = excluir_rascunhos(df_resc_loc)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_prop = "Tempo total na fase Levant. Taxas Proporcionais (dias)"
    col_final = "Tempo total na fase Levantamento de taxas (dias)"

    sub_a = df.dropna(subset=[col_prop]).copy()
    horas_a = sub_a[col_prop].astype(float) * 24
    ok_a = int((horas_a <= 2).sum())
    ind_a = score_indicador(ok_a, len(sub_a), 5)
    ind_a["nome"] = "Rescisão Loc. — Levant. Taxas Prop <2h"

    sub_b = df.dropna(subset=[col_final]).copy()
    horas_b = sub_b[col_final].astype(float) * 24
    ok_b = int((horas_b <= 2).sum())
    ind_b = score_indicador(ok_b, len(sub_b), 5)
    ind_b["nome"] = "Rescisão Loc. — Levant. Taxas Final <2h"

    indicadores = [ind_a, ind_b]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_vivianne_renovacao(df_renov: pd.DataFrame,
                            ref: Optional[datetime] = None) -> dict:
    """
    Vivianne · Renovação · 2 indicadores · peso 10.
    5: Confecção <4h CORRIDO (Pipefy col tempo × 24) (peso 5)
    6: Finalização <16h ÚTEIS — entrada Contrato assinado/Finalizar → entrada Processo concluído (peso 5)
    """
    df = excluir_rascunhos(df_renov)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_tempo_conf = "Tempo total na fase Confecção do contrato (dias)"
    sub_5 = df.dropna(subset=[col_tempo_conf]).copy()
    horas_5 = sub_5[col_tempo_conf].astype(float) * 24
    ok_5 = int((horas_5 <= 4).sum())
    ind_5 = score_indicador(ok_5, len(sub_5), 5)
    ind_5["nome"] = "Renovação — Confecção <4h"

    col_fin_in = "Primeira vez que entrou na fase Contrato assinado / Finalizar"
    col_proc_concl = "Primeira vez que entrou na fase Processo concluído"
    sub_6 = df.dropna(subset=[col_fin_in, col_proc_concl]).copy()
    horas_6 = sub_6.apply(lambda r: horas_uteis(r[col_fin_in], r[col_proc_concl]), axis=1)
    ok_6 = int((horas_6 <= 16).sum())
    ind_6 = score_indicador(ok_6, len(sub_6), 5)
    ind_6["nome"] = "Renovação — Finalização <16h"

    indicadores = [ind_5, ind_6]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_vivianne_inadimplencia(df_inad: pd.DataFrame, bonus_n: int = 0,
                                ref: Optional[datetime] = None) -> dict:
    """
    Vivianne · Inadimplência · 3 indicadores Pipefy + bônus.
    7: Cobrança <24h corrido (Criado em → entrada Cobrança inicial) (peso 2)
    8: CredPago ≤15d corrido (Vencimento 1º Boleto: → entrada CredPago: Acionar) (peso 1)
    9: Negativação 7-9d corrido (Vencimento 1º Boleto: → entrada Negativação) (peso 1)

    Bônus N: boletos em atraso recebidos antes do repasse — passado como bonus_n.
    """
    df = excluir_rascunhos(df_inad)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    # 7: Cobrança <24h corrido
    col_cob = "Primeira vez que entrou na fase Cobrança (inicial)"  # nome no manual / fields_map (com parênteses)
    sub_7 = df.dropna(subset=[col_cob]).copy()
    horas_7 = (sub_7[col_cob] - sub_7["Criado em"]).dt.total_seconds() / 3600
    horas_7 = horas_7.clip(lower=0)
    ok_7 = int((horas_7 <= 24).sum())
    ind_7 = score_indicador(ok_7, len(sub_7), 2)
    ind_7["nome"] = "Inadimplência — Cobrança <24h"

    # 8: CredPago ≤15d corrido a partir de Vencimento 1º Boleto:
    col_venc = "Vencimento 1º Boleto:"
    col_credpago = "Primeira vez que entrou na fase CredPago: Acionar"
    sub_8 = df.dropna(subset=[col_venc, col_credpago]).copy()
    dias_8 = (sub_8[col_credpago] - sub_8[col_venc]).dt.total_seconds() / 86400
    dias_8 = dias_8.clip(lower=0)
    ok_8 = int((dias_8 <= 15).sum())
    ind_8 = score_indicador(ok_8, len(sub_8), 1)
    ind_8["nome"] = "Inadimplência — CredPago ≤15d"

    # 9: Negativação 7-9d corrido a partir de Vencimento 1º Boleto:
    col_neg = "Primeira vez que entrou na fase Negativação (No 8º dia de atraso)"
    sub_9 = df.dropna(subset=[col_venc, col_neg]).copy()
    dias_9 = (sub_9[col_neg] - sub_9[col_venc]).dt.total_seconds() / 86400
    ok_9 = int(((dias_9 >= 7) & (dias_9 <= 9)).sum())
    ind_9 = score_indicador(ok_9, len(sub_9), 1)
    ind_9["nome"] = "Inadimplência — Negativação 7-9d"

    indicadores = [ind_7, ind_8, ind_9]
    return {"nota": nota_processo(indicadores, bonus_n=bonus_n), "indicadores": indicadores}


def calc_vivianne_backoffice(df_bo: pd.DataFrame,
                             ref: Optional[datetime] = None) -> dict:
    """
    Vivianne · BackOffice · 2 indicadores · peso 10.
    Separar cards por 'Primeira vez fase ↪️ Troca de Titularidade':
    - SEM troca → Indicador 10: Concluído <24h corrido (peso 5)
    - COM troca → Indicador 11: Troca <5d úteis = 50h úteis (peso 5)
    """
    df = excluir_rascunhos(df_bo)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_troca = "Primeira vez que entrou na fase ↪️ Troca de Titularidade"
    col_concl = "Primeira vez que entrou na fase Concluído"

    com_troca = df[df[col_troca].notna()].copy()
    sem_troca = df[df[col_troca].isna()].copy()

    # 10: SEM troca, Concluído <24h corrido
    sub_10 = sem_troca.dropna(subset=[col_concl]).copy()
    horas_10 = (sub_10[col_concl] - sub_10["Criado em"]).dt.total_seconds() / 3600
    horas_10 = horas_10.clip(lower=0)
    ok_10 = int((horas_10 <= 24).sum())
    ind_10 = score_indicador(ok_10, len(sub_10), 5)
    ind_10["nome"] = "BackOffice — Concluído <24h"

    # 11: COM troca, Concluído <50h úteis (= 5d úteis)
    sub_11 = com_troca.dropna(subset=[col_concl]).copy()
    horas_11 = sub_11.apply(lambda r: horas_uteis(r["Criado em"], r[col_concl]), axis=1)
    ok_11 = int((horas_11 <= 50).sum())
    ind_11 = score_indicador(ok_11, len(sub_11), 5)
    ind_11["nome"] = "BackOffice — Troca Titularidade <5d"

    indicadores = [ind_10, ind_11]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_vivianne_ticket(df_tickets: pd.DataFrame) -> dict:
    """
    Vivianne · Ticket · 1 indicador · peso 4.
    Filtro: Responsável contém "Vivianne Fontes" ou "VIVIANNE FONTES"
    Indicador: SLA ≤4h úteis (peso 4).
    Avaliações EXCLUÍDAS (manual: 0 registros — não entra no cálculo).
    """
    if df_tickets is None or len(df_tickets) == 0:
        return {"nota": None, "indicadores": []}
    nome = NOMES_AGENTE["vivianne"]["ticket"]
    df_t = _tickets_filtrados(df_tickets, nome)
    ind1 = _ticket_sla_ind(df_t, peso=4)
    return {"nota": nota_processo([ind1]), "indicadores": [ind1]}


# ─────────────────────────────────────────────────────────────────────
# NATÁLIA / GARDÊNIA — Assessoras (helpers reaproveitáveis)
# ─────────────────────────────────────────────────────────────────────

def _nome_assessora(assessora: str) -> str:
    """Converte chave interna → nome usado para filtro de assignee/select."""
    return {"natalia": "Natália", "gardenia": "Gardênia"}.get(assessora, assessora)


def _nome_assessora_alt(assessora: str) -> list[str]:
    """Variantes para casar em campos do tipo select (texto plano), evita falhar por acento."""
    if assessora == "natalia":
        return ["Natália", "Natalia"]
    if assessora == "gardenia":
        return ["Gardênia", "Gardenia"]
    return [assessora]


def _contem_qualquer(valor, nomes: list[str]) -> bool:
    for n in nomes:
        if contem_assignee(valor, n):
            return True
    return False


def calc_assessora_contrato_adm(df_cont_adm: pd.DataFrame, assessora: str, bonus_n: int = 0,
                                ref: Optional[datetime] = None) -> dict:
    """
    Assessora · Cont. ADM · 1 indicador · peso 10 + bônus vistoria de entrada.
    Indicador 1: Conferência ≤2h úteis — entrada/saída fase Conferência do contrato.
    Bônus N: cards onde 'Criar Card de Vistoria Técnica' está preenchido, filtrado por Assessor (lista).
    """
    df = excluir_rascunhos(df_cont_adm)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    nomes = _nome_assessora_alt(assessora)
    mask = df["Assessor (lista)"].apply(lambda v: _contem_qualquer(v, nomes))
    # Manual §4.3: cards sem Assessor (lista) mas concluídos → atribuídos à Gardênia.
    if assessora == "gardenia":
        sem_assessor = df["Assessor (lista)"].apply(lambda v: not _as_list(v))
        concluido = df["Primeira vez que entrou na fase Concluído"].notna()
        mask = mask | (sem_assessor & concluido)
    df_assess = df[mask].copy()

    col_in = "Primeira vez que entrou na fase Conferência do contrato"
    col_out = "Última vez que saiu da fase Conferência do contrato"
    sub = df_assess.dropna(subset=[col_in, col_out]).copy()
    horas = sub.apply(lambda r: horas_uteis(r[col_in], r[col_out]), axis=1)
    ok = int((horas <= 2).sum())
    ind = score_indicador(ok, len(sub), 10)
    ind["nome"] = "Cont. ADM — Conferência ≤2h"

    return {"nota": nota_processo([ind], bonus_n=bonus_n), "indicadores": [ind]}


def calc_assessora_rescisao_adm(df_resc_adm: pd.DataFrame, assessora: str,
                                ref: Optional[datetime] = None) -> dict:
    """
    Assessora · Rescisão ADM · 2 indicadores · peso 10.
    Indicador 2: Repasse <12h úteis (peso 5).
    Indicador 3: Distrato assinado (peso 5) — denominador: cards concluídos.

    Filtro: 'Assessor (lista)' contém nome (validado contra baseline 10ª — manual diz
    'sem filtro' mas baseline mostra denominadores diferentes por assessora).
    """
    df = excluir_rascunhos(df_resc_adm)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Assessor (lista)"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    col_repasse = "Primeira vez que entrou na fase Repasse final / Distrato (FINANCEIRO)"
    sub_2 = df.dropna(subset=[col_repasse]).copy()
    horas_2 = sub_2.apply(lambda r: horas_uteis(r["Criado em"], r[col_repasse]), axis=1)
    ok_2 = int((horas_2 <= 12).sum())
    ind_2 = score_indicador(ok_2, len(sub_2), 5)
    ind_2["nome"] = "Rescisão ADM — Repasse <12h"

    col_concl = "Primeira vez que entrou na fase Concluído"
    sub_3 = df.dropna(subset=[col_concl]).copy()
    # Indicador 3: campo Termo de Distrato assinado = "Sim" (radio_horizontal).
    val = sub_3["Termo de Distrato assinado"].astype(str).str.strip().str.lower()
    ok_3 = int((val == "sim").sum())
    ind_3 = score_indicador(ok_3, len(sub_3), 5)
    ind_3["nome"] = "Rescisão ADM — Distrato assinado"

    indicadores = [ind_2, ind_3]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_assessora_rescisao_locacao(df_resc_loc: pd.DataFrame, assessora: str,
                                    ref: Optional[datetime] = None) -> dict:
    """
    Assessora · Rescisão Loc. · 2 indicadores · peso 5.

    REGRA DE INÍCIO (refinada na 11ª Ed — decisão da gestora 14/05/2026):
        Ordem de prioridade para identificar quando a assessora assumiu o caso:
          1ª) "Data do recebimento das chaves:" (campo COM dois-pontos, fase CHAVES RECEBIDAS)
          2ª) "Primeira vez que entrou na fase CHAVES RECEBIDAS" (firstTimeIn)
          3ª) Fallback antigo:
              - Boleto prop : "Última vez que saiu da fase Vistoria recebida"
              - Boleto final: "Última vez que saiu da fase Agendamento de vistoria"

        Justificativa: o locatário pode receber a vistoria com pendências e levar
        dias/semanas para reparar antes de entregar as chaves. Esse intervalo NÃO
        é responsabilidade da assessora — a contagem começa quando as chaves são
        efetivamente entregues.

    Indicadores:
      4: Boleto prop <24h corrido (peso 2)
          Fim: Primeira vez que entrou na fase Levant. Taxas Proporcionais
      5: Boleto final <15d corrido (peso 3)
          Fim: Primeira vez que entrou na fase Envio do boleto final

    Filtro: 'Assessor (lista)' contém nome (validado contra baseline 10ª).
    """
    df = excluir_rascunhos(df_resc_loc)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Assessor (lista)"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    chaves_campo = df["Data do recebimento das chaves:"]
    chaves_fase = df.get("Primeira vez que entrou na fase CHAVES RECEBIDAS",
                          pd.Series(pd.NaT, index=df.index))
    sai_vist = df["Última vez que saiu da fase Vistoria recebida"]
    sai_agend = df["Última vez que saiu da fase Agendamento de vistoria"]

    # 1ª prioridade: campo Data do recebimento das chaves: (com dois-pontos)
    # 2ª prioridade: firstTimeIn da fase CHAVES RECEBIDAS
    # 3ª prioridade: fallback específico por indicador (Vistoria recebida / Agendamento)
    chaves_efetivas = chaves_campo.where(chaves_campo.notna(), chaves_fase)
    inicio_prop = chaves_efetivas.where(chaves_efetivas.notna(), sai_vist)
    inicio_final = chaves_efetivas.where(chaves_efetivas.notna(), sai_agend)
    col_lev_prop = "Primeira vez que entrou na fase Levant. Taxas Proporcionais"
    col_env_bol = "Primeira vez que entrou na fase Envio do boleto final"

    # 4: Boleto prop <24h
    mask_4 = inicio_prop.notna() & df[col_lev_prop].notna()
    sub_4 = df[mask_4].copy()
    horas_4 = (df.loc[mask_4, col_lev_prop] - inicio_prop[mask_4]).dt.total_seconds() / 3600
    horas_4 = horas_4.clip(lower=0)
    ok_4 = int((horas_4 <= 24).sum())
    ind_4 = score_indicador(ok_4, len(sub_4), 2)
    ind_4["nome"] = "Rescisão Loc. — Boleto prop <24h"

    # 5: Boleto final <15d
    mask_5 = inicio_final.notna() & df[col_env_bol].notna()
    sub_5 = df[mask_5].copy()
    dias_5 = (df.loc[mask_5, col_env_bol] - inicio_final[mask_5]).dt.total_seconds() / 86400
    dias_5 = dias_5.clip(lower=0)
    ok_5 = int((dias_5 <= 15).sum())
    ind_5 = score_indicador(ok_5, len(sub_5), 3)
    ind_5["nome"] = "Rescisão Loc. — Boleto final <15d"

    indicadores = [ind_4, ind_5]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_assessora_reparos(df_rep: pd.DataFrame, assessora: str,
                           ref: Optional[datetime] = None) -> dict:
    """
    Assessora · Reparos · 2 indicadores · peso 10.
    Filtro: 'Selecionar o assessor' contém nome.
    6: Orçamento <4h úteis (Criado em → entrada Orçamento|Prestador) (peso 4).
    7: Pós-venda ≤7d corrido (Criado em → entrada Pós-venda) (peso 6).
    """
    df = excluir_rascunhos(df_rep)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Selecionar o assessor"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    col_orc = "Primeira vez que entrou na fase Orçamento | Prestador"
    sub_6 = df.dropna(subset=[col_orc]).copy()
    horas_6 = sub_6.apply(lambda r: horas_uteis(r["Criado em"], r[col_orc]), axis=1)
    ok_6 = int((horas_6 <= 4).sum())
    ind_6 = score_indicador(ok_6, len(sub_6), 4)
    ind_6["nome"] = "Reparos — Orçamento <4h"

    col_pos = "Primeira vez que entrou na fase Pós-venda"
    sub_7 = df.dropna(subset=[col_pos]).copy()
    dias_7 = (sub_7[col_pos] - sub_7["Criado em"]).dt.total_seconds() / 86400
    dias_7 = dias_7.clip(lower=0)
    ok_7 = int((dias_7 <= 7).sum())
    ind_7 = score_indicador(ok_7, len(sub_7), 6)
    ind_7["nome"] = "Reparos — Pós-venda ≤7d"

    indicadores = [ind_6, ind_7]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_assessora_renovacao(df_renov: pd.DataFrame, assessora: str,
                             ref: Optional[datetime] = None) -> dict:
    """
    Assessora · Renovação · 2 indicadores · peso 10.
    Filtro: 'Assessor (lista)' contém nome.
    8: Contato >60d antes vencimento (Data venc - última saída Contato com proprietário) (peso 4).
    9: Assinado antes vencimento (Primeira vez Contrato assinado/Finalizar < Data venc) (peso 6).
    """
    df = excluir_rascunhos(df_renov)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Assessor (lista)"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    col_contato_out = "Última vez que saiu da fase Contato com proprietário"
    col_venc = "Data de vencimento"
    sub_8 = df.dropna(subset=[col_contato_out, col_venc]).copy()
    dias_8 = (sub_8[col_venc] - sub_8[col_contato_out]).dt.total_seconds() / 86400
    ok_8 = int((dias_8 > 60).sum())
    ind_8 = score_indicador(ok_8, len(sub_8), 4)
    ind_8["nome"] = "Renovação — Contato >60d"

    col_assinado = "Primeira vez que entrou na fase Contrato assinado / Finalizar"
    sub_9 = df.dropna(subset=[col_assinado, col_venc]).copy()
    ok_9 = int((sub_9[col_assinado] < sub_9[col_venc]).sum())
    ind_9 = score_indicador(ok_9, len(sub_9), 6)
    ind_9["nome"] = "Renovação — Assinado antes vencimento"

    indicadores = [ind_8, ind_9]
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_assessora_backoffice(df_bo: pd.DataFrame, assessora: str,
                              ref: Optional[datetime] = None) -> dict:
    """
    Assessora · BackOffice · 1 indicador · peso 10.
    Filtro: 'Responsável' contém nome (NÃO 'Criador').
    10: Pendência Assessor <24h corrido (entrada/saída fase 🚩 Pendência Assessor).
    """
    df = excluir_rascunhos(df_bo)
    df = aplicar_cutoff(df, "Criado em", ref=ref)
    nomes = _nome_assessora_alt(assessora)
    # Filtro por `Responsáveis` (card.assignees Card-level — bate com export XLSX),
    # NÃO pelo field-form `Responsável` (que tem só Vivianne na maioria dos cards).
    df = df[df["Responsáveis"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    col_in = "Primeira vez que entrou na fase 🚩 Pendência Assessor"
    col_out = "Última vez que saiu da fase 🚩 Pendência Assessor"
    sub = df.dropna(subset=[col_in, col_out]).copy()
    horas = (sub[col_out] - sub[col_in]).dt.total_seconds() / 3600
    horas = horas.clip(lower=0)
    ok = int((horas <= 24).sum())
    ind = score_indicador(ok, len(sub), 10)
    ind["nome"] = "BackOffice — Pendência <24h"

    return {"nota": nota_processo([ind]), "indicadores": [ind]}


def calc_assessora_dirf_darf(df_dirf: pd.DataFrame, assessora: str,
                             ref: Optional[datetime] = None) -> dict:
    """
    Assessora · DIRF/DARF · 1 indicador · peso 10.
    Filtros: Ano: = '2025' + 'Responsável' contém nome.
    11: Concluído antes 29/05/2026 (PRORROGAÇÃO OFICIAL).
    Denominador: TODOS os cards do ano-base da assessora (concluídos ou não).
    """
    df = excluir_rascunhos(df_dirf)
    # Filtro Ano = 2025  (campo number — pode vir como float 2025.0)
    ano_int = pd.to_numeric(df["Ano:"], errors="coerce").astype("Int64")
    df = df[ano_int == DIRF_DARF_ANO_BASE]
    nomes = _nome_assessora_alt(assessora)
    df = df[df["Responsável"].apply(lambda v: _contem_qualquer(v, nomes))].copy()

    col_concl = "Primeira vez que entrou na fase Concluído"
    deadline = pd.Timestamp(DIRF_DARF_CUTOFF).tz_localize("UTC")
    ok = int(((df[col_concl].notna()) & (df[col_concl] < deadline)).sum())
    ind = score_indicador(ok, len(df), 10)
    ind["nome"] = "DIRF/DARF — Concluído antes 29/05"

    return {"nota": nota_processo([ind]), "indicadores": [ind]}


def calc_assessora_whatsapp(df_conv: pd.DataFrame, assessora: str) -> dict:
    """
    Assessora · WhatsApp · 2 indicadores · peso 7.
    Filtro: Responsável da conversa = nome exato (Natália Teixeira / Gardênia).
    """
    if df_conv is None or len(df_conv) == 0:
        return {"nota": None, "indicadores": []}
    nome = NOMES_AGENTE[assessora]["whatsapp"]
    indicadores = _whatsapp_indicadores(df_conv, nome, peso_resposta=4, peso_aval=3)
    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_assessora_ticket(df_tickets: pd.DataFrame, df_aval: pd.DataFrame, assessora: str) -> dict:
    """
    Assessora · Ticket · 2 indicadores · peso 6.
    Filtro: Responsável do ticket contém nome (Natália / Gardênia).
    Exclusões: Categoria=Cancelado/Spam, Status=Cancelado, Assunto=Tarefa.
    """
    if (df_tickets is None or len(df_tickets) == 0) and (df_aval is None or len(df_aval) == 0):
        return {"nota": None, "indicadores": []}
    nome = NOMES_AGENTE[assessora]["ticket"]
    df_t = _tickets_filtrados(df_tickets, nome)
    ind1 = _ticket_sla_ind(df_t, peso=3)
    ind2 = _ticket_aval_ind(df_aval, nome, peso=3)
    return {"nota": nota_processo([ind1, ind2]), "indicadores": [ind1, ind2]}


# ─────────────────────────────────────────────────────────────────────
# MARINHO — Vistorias + Contestações
# ─────────────────────────────────────────────────────────────────────

def calc_marinho_vistorias(df_vist: pd.DataFrame, ref: Optional[datetime] = None) -> dict:
    """
    Marinho — Laudo <24h úteis

    Fonte: Vistoria finalizada em → Última saída fase Em produção
    Peso: 10 (Produtividade m²/h temporariamente desativada, peso consolidado no Laudo)

    NOTA SOBRE A MÉTRICA:
    A métrica usa o tempo até o card sair da fase "Em produção" no Pipefy,
    NÃO o tempo de entrega do laudo ao cliente. Card parado em "Em produção"
    depois do laudo entregue conta como atraso.

    REGRA DE OPERAÇÃO (decidida na 11ª Edição):
    O Marinho deve fechar o card no Pipefy imediatamente após entregar o laudo.
    Cards que permanecem em "Em produção" por dias após a entrega física do
    laudo são considerados atraso operacional e contam contra a nota. A métrica
    é educativa: força disciplina de uso do Pipefy.

    REABERTURAS (re-entradas na fase "Em produção" para conferência de reparo do
    prestador): NÃO são excluídas pela lógica. A métrica usa lastTimeOut (última
    saída), o que naturalmente captura o ciclo completo. Caso seja necessário
    isolar reaberturas no futuro, revisitar com base nos dados (referência:
    scripts/diag_marinho.py).
    """
    df = excluir_rascunhos(df_vist)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    indicadores = []
    produtividade_ativa = FEATURE_FLAGS.get("marinho_produtividade_ativa", False)
    peso_laudo = 4 if produtividade_ativa else 10

    col_vfim = "Vistoria finalizada em"
    col_prod_out = "Última vez que saiu da fase Em produção"
    sub_l = df.dropna(subset=[col_vfim, col_prod_out]).copy()
    horas_l = sub_l.apply(lambda r: horas_uteis(r[col_vfim], r[col_prod_out]), axis=1)
    ok_l = int((horas_l <= 24).sum())
    ind_l = score_indicador(ok_l, len(sub_l), peso_laudo)
    ind_l["nome"] = "Laudos entregues ≤24h após vistoria"
    indicadores.append(ind_l)

    if produtividade_ativa:
        col_vini = "vistoria iniciada em"  # label tem trailing space
        if col_vini not in df.columns:
            col_vini = "vistoria iniciada em "
        sub_p = df.dropna(subset=[col_vini, col_vfim, "Área útil M²"]).copy()
        horas_p = (sub_p[col_vfim] - sub_p[col_vini]).dt.total_seconds() / 3600
        sub_p = sub_p[horas_p > 0].copy()
        m2h = sub_p["Área útil M²"].astype(float) / ((sub_p[col_vfim] - sub_p[col_vini]).dt.total_seconds() / 3600)
        ok_p = int((m2h >= 32).sum())
        ind_p = score_indicador(ok_p, len(sub_p), 6)
        ind_p["nome"] = "Vistorias — Produtividade ≥32 m²/h"
        indicadores.append(ind_p)

    return {"nota": nota_processo(indicadores), "indicadores": indicadores}


def calc_marinho_contestacoes(df_cont: pd.DataFrame, ref: Optional[datetime] = None) -> dict:
    """
    Marinho · Contestações · 1 indicador · peso 10 · PROCESSO SEPARADO.
    Respondida <24h corrido: Criado em → Primeira vez fase Concluído.
    Denominador: cards que chegaram a Concluído.
    """
    df = excluir_rascunhos(df_cont)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_concl = "Primeira vez que entrou na fase Concluído"
    sub = df.dropna(subset=[col_concl]).copy()
    horas = (sub[col_concl] - sub["Criado em"]).dt.total_seconds() / 3600
    horas = horas.clip(lower=0)
    ok = int((horas <= 24).sum())
    ind = score_indicador(ok, len(sub), 10)
    ind["nome"] = "Contestações respondidas <24h"
    return {"nota": nota_processo([ind]), "indicadores": [ind]}


# ─────────────────────────────────────────────────────────────────────
# ORQUESTRAÇÃO POR COLABORADOR
# ─────────────────────────────────────────────────────────────────────

def calcular_caio(dataframes: dict, bonus_imovel_alugado: int) -> dict:
    """Retorna estrutura completa do Caio para o painel."""
    com_loc = calc_caio_comercial_locacao(dataframes["comercial"], bonus_imovel_alugado)
    cont_loc = calc_caio_contrato_locacao(dataframes["comercial"], dataframes["cont_loc"])
    cont_adm = calc_caio_contrato_adm(dataframes["cont_adm"])
    renov = calc_caio_renovacao(dataframes["renov"])
    wa = calc_caio_whatsapp(dataframes["conversas"])
    tkt = calc_caio_ticket(dataframes["tickets"], dataframes["aval_tickets"])

    scores = {
        "Com. Locação": com_loc["nota"],
        "Cont. Locação": cont_loc["nota"],
        "Cont. ADM": cont_adm["nota"],
        "Renovação": renov["nota"],
        "WhatsApp": wa["nota"],
        "Ticket": tkt["nota"],
    }

    return {
        "id": "caio",
        "nome": "Caio Rodrigues Lima",
        "cargo": "Comercial",
        "nota": nota_final(scores),
        "scores": scores,
        "detalhes": com_loc["indicadores"] + cont_loc["indicadores"] + cont_adm["indicadores"]
                  + renov["indicadores"] + wa["indicadores"] + tkt["indicadores"],
        "bonus_proc": "Com. Locação",
        "bonus": bonus_imovel_alugado,
    }


def calcular_vivianne(dataframes: dict, bonus_boletos: int) -> dict:
    """TODO Claude Code: análogo a calcular_caio para Vivianne."""
    raise NotImplementedError


def calcular_assessora(assessora: str, dataframes: dict, bonus_vistoria: int) -> dict:
    """TODO Claude Code: análogo para Natália/Gardênia."""
    raise NotImplementedError


def calcular_marinho(dataframes: dict) -> dict:
    """TODO Claude Code: estrutura especial — 2 processos, 1 coluna no painel."""
    vist = calc_marinho_vistorias(dataframes["vistorias"])
    cont = calc_marinho_contestacoes(dataframes["contestacoes"])

    nota_marinho = nota_final({"vistorias": vist["nota"], "contestacoes": cont["nota"]})

    return {
        "id": "marinho",
        "nome": "Albérico Marinho",
        "cargo": "Vistoriador",
        "nota": nota_marinho,
        "scores": {"Vistorias": nota_marinho},  # exibição: 1 coluna apenas
        "detalhes": vist["indicadores"] + cont["indicadores"],
    }


# ─────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

def calcular_ranking(dataframes: dict, bonus: dict) -> list:
    """
    Calcula o ranking completo dos 5 colaboradores.

    Args:
        dataframes: dict com todos os DataFrames extraídos das APIs
        bonus: dict com os valores N de bônus já calculados
            - "caio_imovel_alugado": int
            - "vivianne_boletos": int
            - "natalia_vistoria": int
            - "gardenia_vistoria": int

    Returns:
        Lista de 5 dicts (PESSOAS), ordenada por nota decrescente.
    """
    pessoas = [
        calcular_caio(dataframes, bonus["caio_imovel_alugado"]),
        calcular_vivianne(dataframes, bonus["vivianne_boletos"]),
        calcular_assessora("natalia", dataframes, bonus["natalia_vistoria"]),
        calcular_assessora("gardenia", dataframes, bonus["gardenia_vistoria"]),
        calcular_marinho(dataframes),
    ]
    pessoas.sort(key=lambda p: p["nota"] or 0, reverse=True)
    for pos, p in enumerate(pessoas, 1):
        p["pos"] = pos
    return pessoas


if __name__ == "__main__":
    # Para testes: rodar com dados mock ou cache local
    print("Use run.py para execução completa.")
