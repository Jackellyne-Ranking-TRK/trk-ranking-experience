"""
TRK Experience — Orquestrador principal
=======================================

Roda o pipeline completo:
  1. Extrai os 12 pipes do Pipefy (usa cache em dados/raw/ se disponível).
  2. Carrega XLSX do Octadesk de dados/octadesk/ (LOCAL — quando API entrar, troca o módulo).
  3. Carrega CSVs do Imobiliar de dados/csv/ + calcula N do bônus Inadimplência (LOCAL).
  4. Calcula ranking dos 5 colaboradores via funções calc_* de calculate.py.
  5. Gera painel/dados/atual.json no formato PESSOAS / IMOVEIS / PROC_RICH.
  6. (Opcional) `--validate` compara contra baselines.json.

CLI:
    python pipeline/run.py                    # snapshot completo
    python pipeline/run.py --validate         # roda só a validação
    python pipeline/run.py --no-cache         # força re-extract dos pipes
    python pipeline/run.py --ref 2026-05-14   # data de referência (ISO)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from calculate import (
    calc_caio_comercial_locacao, calc_caio_contrato_locacao, calc_caio_contrato_adm, calc_caio_renovacao,
    calc_caio_whatsapp, calc_caio_ticket,
    calc_vivianne_contrato_adm, calc_vivianne_rescisao_adm, calc_vivianne_contrato_locacao,
    calc_vivianne_rescisao_locacao, calc_vivianne_renovacao, calc_vivianne_inadimplencia,
    calc_vivianne_backoffice, calc_vivianne_ticket,
    calc_assessora_contrato_adm, calc_assessora_rescisao_adm, calc_assessora_rescisao_locacao,
    calc_assessora_reparos, calc_assessora_renovacao, calc_assessora_backoffice, calc_assessora_dirf_darf,
    calc_assessora_whatsapp, calc_assessora_ticket,
    calc_marinho_vistorias, calc_marinho_contestacoes,
    nota_final,
)
from pipeline.extract_pipefy import extract_pipe
from pipeline.extract_octadesk import extract_octadesk
from pipeline.extract_imobiliar import extract_imobiliar, calcular_bonus_inadimplencia

OUT_DIR = ROOT / "painel" / "dados"
OUT_JSON = OUT_DIR / "atual.json"

NOMES = {
    "caio":     ("Caio Rodrigues Lima", "Comercial"),
    "vivianne": ("Vivianne Fontes",      "BackOffice · Inadimplência"),
    "marinho":  ("Albérico Marinho",     "Vistoriador"),
    "natalia":  ("Natália Teixeira",     "Assessora"),
    "gardenia": ("Gardênia",             "Assessora"),
}

# Encurtadores para pontosFort/Aten
SHORT = {
    "Comercial": "Comercial", "Cont. Locação": "Cont.Loc", "Cont. ADM": "Cont.ADM",
    "Rescisão ADM": "RescADM", "Rescisão Loc.": "RescLoc", "Reparos": "Reparos",
    "Renovação": "Renov", "Inadimplência": "Inad", "BackOffice": "BO",
    "DIRF/DARF": "DIRF", "WhatsApp": "WA", "Ticket": "Tkt", "Tickets": "Tkts",
    "Vistorias": "Vist", "Contestações": "Cont", "Laudos": "Laudos",
}


# ────────────────────────────────────────────────────────────────────
# Carregamento de DataFrames
# ────────────────────────────────────────────────────────────────────

def carregar_dataframes(*, use_cache: bool = True, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Retorna dict com todos os DFs (Pipefy + Octadesk + Imobiliar)."""
    pipes = [
        "comercial_locacao", "cont_locacao", "cont_adm", "rescisao_adm", "rescisao_loc",
        "reparos", "renovacao", "inadimplencia", "backoffice", "dirf_darf",
        "vistorias", "contestacoes",
    ]
    dfs = {k: extract_pipe(k, use_cache=use_cache, verbose=verbose) for k in pipes}

    if verbose:
        print("\n[octadesk] carregando arquivos locais…")
    oct_ = extract_octadesk(verbose=verbose)
    dfs.update(oct_)  # adiciona conversas, tickets, aval_tickets

    if verbose:
        print("\n[imobiliar] carregando CSVs locais…")
    imob = extract_imobiliar(verbose=verbose)
    dfs["imobiliar"] = imob   # guarda os 3 sub-DFs sob "imobiliar"
    return dfs


# ────────────────────────────────────────────────────────────────────
# Pontos fortes / atenção
# ────────────────────────────────────────────────────────────────────

def _curto(nome_ind: str) -> str:
    """Encurta 'Comercial — Início processo <24h' → 'Comercial Início'."""
    parte = nome_ind.split("—")[0].strip() if "—" in nome_ind else nome_ind
    return SHORT.get(parte, parte)[:14]


def pontos_fort_aten(indicadores: list[dict]) -> tuple[list[str], list[str]]:
    """Top 4 maiores pct (fortes) e top 4 menores pct (atenção). Ignora bônus."""
    validos = [i for i in indicadores if i.get("pct") is not None and "★" not in i["nome"]]
    if not validos:
        return [], []
    ord_desc = sorted(validos, key=lambda i: i["pct"], reverse=True)
    ord_asc = sorted(validos, key=lambda i: i["pct"])
    fort = [f"{_curto(i['nome'])}: {i['pct']:.1f}%" for i in ord_desc[:4]]
    aten = [f"{_curto(i['nome'])}: {i['pct']:.1f}%" for i in ord_asc[:4]]
    return fort, aten


# ────────────────────────────────────────────────────────────────────
# Cálculo por colaborador (devolve dict no formato PESSOAS)
# ────────────────────────────────────────────────────────────────────

def _safe(fn, *args, **kwargs) -> dict:
    """Chama uma função calc_*; converte NotImplementedError em resultado vazio."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError as e:
        print(f"  [skip] {fn.__name__}: {e}")
        return {"nota": None, "indicadores": []}


def calc_caio(dfs: dict, bonus_n: int, ref: pd.Timestamp) -> dict:
    com  = calc_caio_comercial_locacao(dfs["comercial_locacao"], bonus_n=bonus_n, ref=ref)
    cl   = calc_caio_contrato_locacao(dfs["comercial_locacao"], dfs["cont_locacao"], ref=ref)
    cadm = calc_caio_contrato_adm(dfs["cont_adm"], ref=ref)
    ren  = calc_caio_renovacao(dfs["renovacao"], ref=ref)
    wa   = _safe(calc_caio_whatsapp, dfs["conversas"])
    tkt  = _safe(calc_caio_ticket, dfs["tickets"], dfs["aval_tickets"])
    scores = {
        "Com. Locação": com["nota"], "Cont. Locação": cl["nota"], "Cont. ADM": cadm["nota"],
        "Renovação": ren["nota"], "WhatsApp": wa["nota"], "Ticket": tkt["nota"],
    }
    detalhes = (com["indicadores"] + cl["indicadores"] + cadm["indicadores"]
                + ren["indicadores"] + wa["indicadores"] + tkt["indicadores"])
    return _montar_pessoa("caio", scores, detalhes, bonus_n, "Com. Locação")


def calc_vivianne(dfs: dict, bonus_n: int, ref: pd.Timestamp) -> dict:
    cadm = calc_vivianne_contrato_adm(dfs["cont_adm"], ref=ref)
    radm = calc_vivianne_rescisao_adm(dfs["rescisao_adm"], ref=ref)
    cloc = calc_vivianne_contrato_locacao(dfs["cont_locacao"], ref=ref)
    rloc = calc_vivianne_rescisao_locacao(dfs["rescisao_loc"], ref=ref)
    ren  = calc_vivianne_renovacao(dfs["renovacao"], ref=ref)
    ina  = calc_vivianne_inadimplencia(dfs["inadimplencia"], bonus_n=bonus_n, ref=ref)
    bo   = calc_vivianne_backoffice(dfs["backoffice"], ref=ref)
    tkt  = _safe(calc_vivianne_ticket, dfs["tickets"])
    scores = {
        "Cont. ADM": cadm["nota"], "Rescisão ADM": radm["nota"], "Cont. Locação": cloc["nota"],
        "Rescisão Loc.": rloc["nota"], "Renovação": ren["nota"], "Inadimplência": ina["nota"],
        "BackOffice": bo["nota"], "Ticket": tkt["nota"],
    }
    detalhes = (cadm["indicadores"] + radm["indicadores"] + cloc["indicadores"] + rloc["indicadores"]
                + ren["indicadores"] + ina["indicadores"] + bo["indicadores"] + tkt["indicadores"])
    return _montar_pessoa("vivianne", scores, detalhes, bonus_n, "Inadimplência")


def calc_assessora(pid: str, dfs: dict, bonus_n: int, ref: pd.Timestamp) -> dict:
    cadm = calc_assessora_contrato_adm(dfs["cont_adm"], pid, bonus_n=bonus_n, ref=ref)
    radm = calc_assessora_rescisao_adm(dfs["rescisao_adm"], pid, ref=ref)
    rloc = calc_assessora_rescisao_locacao(dfs["rescisao_loc"], pid, ref=ref)
    rep  = calc_assessora_reparos(dfs["reparos"], pid, ref=ref)
    ren  = calc_assessora_renovacao(dfs["renovacao"], pid, ref=ref)
    bo   = calc_assessora_backoffice(dfs["backoffice"], pid, ref=ref)
    dirf = calc_assessora_dirf_darf(dfs["dirf_darf"], pid, ref=ref)
    wa   = _safe(calc_assessora_whatsapp, dfs["conversas"], pid)
    tkt  = _safe(calc_assessora_ticket, dfs["tickets"], dfs["aval_tickets"], pid)
    scores = {
        "Cont. ADM": cadm["nota"], "Rescisão ADM": radm["nota"], "Rescisão Loc.": rloc["nota"],
        "Reparos": rep["nota"], "Renovação": ren["nota"], "BackOffice": bo["nota"],
        "DIRF/DARF": dirf["nota"], "WhatsApp": wa["nota"], "Ticket": tkt["nota"],
    }
    detalhes = (cadm["indicadores"] + radm["indicadores"] + rloc["indicadores"] + rep["indicadores"]
                + ren["indicadores"] + bo["indicadores"] + dirf["indicadores"]
                + wa["indicadores"] + tkt["indicadores"])
    return _montar_pessoa(pid, scores, detalhes, bonus_n, "Cont. ADM")


def calc_marinho(dfs: dict, ref: pd.Timestamp) -> dict:
    vist = calc_marinho_vistorias(dfs["vistorias"], ref=ref)
    cont = calc_marinho_contestacoes(dfs["contestacoes"], ref=ref)
    # Marinho: 2 processos separados, nota final = média
    nota = nota_final({"v": vist["nota"], "c": cont["nota"]})
    scores = {"Vistorias": nota}   # painel mostra 1 coluna só
    detalhes = vist["indicadores"] + cont["indicadores"]
    p = _montar_pessoa("marinho", scores, detalhes, bonus_n=0, bonus_proc=None)
    p["nota"] = nota
    return p


def _montar_pessoa(pid: str, scores: dict, detalhes: list, bonus_n: int,
                   bonus_proc: Optional[str]) -> dict:
    nome, cargo = NOMES[pid]
    nota = nota_final(scores)
    fort, aten = pontos_fort_aten(detalhes)
    # 13 colunas-padrão do painel (preserva chaves nulas para alinhar visualmente)
    cols_padrao = ["Cont. ADM", "Rescisão ADM", "Com. Locação", "Cont. Locação", "Rescisão Loc.",
                   "Reparos", "Renovação", "Inadimplência", "Vistorias", "BackOffice",
                   "DIRF/DARF", "WhatsApp", "Ticket"]
    scores_full = {c: scores.get(c) for c in cols_padrao}
    return {
        "id": pid, "nome": nome, "cargo": cargo,
        "nota": nota, "bonus": bonus_n, "bonus_proc": bonus_proc,
        "inds": len(detalhes),
        "pts": round(sum((d.get("peso") or 0) for d in detalhes), 1),
        "scores": scores_full,
        "detalhes": detalhes,
        "pontosFort": fort, "pontosAten": aten,
    }


# ────────────────────────────────────────────────────────────────────
# Build atual.json
# ────────────────────────────────────────────────────────────────────

def build_atual(dfs: dict, *, ref: pd.Timestamp, bonus_n_vivianne: int,
                verbose: bool = True) -> dict:
    # Bônus de assessora/Caio: derivados do Pipefy (já estão sendo aplicados nas funções).
    # Por enquanto usamos os mesmos valores empíricos da 10ª Ed para Caio/Natália/Gardênia
    # — calc_assessora_contrato_adm aplica bonus_n no nota_processo; o N efetivo da edição
    # atual deveria vir do cruzamento de Pipefy (campo "Criar Card de Vistoria Técnica").
    # TODO: contar dinamicamente N a partir do df_cont_adm filtrado por Assessor.
    bonus_caio = _contar_bonus_caio(dfs, ref=ref)
    bonus_natalia = _contar_bonus_assessora(dfs, "natalia", ref=ref)
    bonus_gardenia = _contar_bonus_assessora(dfs, "gardenia", ref=ref)

    if verbose:
        print(f"\n[bonus] caio_imovel_alugado={bonus_caio}  vivianne_boletos={bonus_n_vivianne}  "
              f"natalia_vistoria={bonus_natalia}  gardenia_vistoria={bonus_gardenia}")

    pessoas = [
        calc_caio(dfs, bonus_caio, ref),
        calc_vivianne(dfs, bonus_n_vivianne, ref),
        calc_assessora("natalia", dfs, bonus_natalia, ref),
        calc_assessora("gardenia", dfs, bonus_gardenia, ref),
        calc_marinho(dfs, ref),
    ]
    pessoas.sort(key=lambda p: (p["nota"] or 0), reverse=True)
    for pos, p in enumerate(pessoas, 1):
        p["pos"] = pos

    return {
        "_meta": {
            "geradoEm": datetime.utcnow().isoformat() + "Z",
            "ref": ref.isoformat(),
            "octadesk_disponivel": bool(len(dfs.get("conversas", pd.DataFrame()))) or
                                    bool(len(dfs.get("tickets", pd.DataFrame()))),
            "imobiliar_disponivel": bool(len(dfs.get("imobiliar", {}).get("boletos", pd.DataFrame()))),
        },
        "PESSOAS": pessoas,
        "IMOVEIS": {},     # drilldown property-level — a preencher em iteração futura
        "PROC_RICH": {},   # paineis por processo — a preencher em iteração futura
        "BASELINE_9": {"caio": 5.54, "vivianne": 5.26, "marinho": 2.73,
                       "natalia": 3.89, "gardenia": 3.91},
    }


def _contar_bonus_caio(dfs: dict, ref: Optional[pd.Timestamp] = None,
                        validated_ims: Optional[set[int]] = None) -> int:
    """
    Bônus Caio · imóveis alugados ANTES de serem anunciados (manual v4 §4.1).

    Critério (validado 8ª/10ª Ed):
      1. Existe card no pipe Cont.Locação com "Primeira vez fase 1º Boleto" preenchida.
      2. NENHUM card do Comercial Caio para esse IM tem "Data publicação Anúncio" preenchida.

    ⚠️ O pipe Comercial só mostra cards do recorte 180d. IMs com anúncio anterior NÃO
       aparecem mas TAMBÉM não são elegíveis ao bônus. Por isso a função LOGA candidatos
       para validação manual e retorna 0 (ou len(candidates ∩ validated_ims) se passado).
    """
    from calculate import excluir_rascunhos, filtrar_por_assignee, extrair_im

    df_cl = dfs.get("cont_locacao", pd.DataFrame())
    df_com = dfs.get("comercial_locacao", pd.DataFrame())
    if len(df_cl) == 0 or len(df_com) == 0:
        return 0

    col_boleto = "Primeira vez que entrou na fase 1º Boleto"
    if col_boleto not in df_cl.columns:
        print(f"[bonus_caio] coluna '{col_boleto}' ausente no Cont.Locação — bonus_n=0")
        return 0

    # Cutoff 180d aplicado ao 1º Boleto: bônus refere-se à edição corrente, não histórico.
    from calculate import aplicar_cutoff as _cutoff
    df_cl_ok = _cutoff(df_cl, col_boleto, ref=ref).dropna(subset=[col_boleto]).copy()
    df_cl_ok["IM"] = df_cl_ok["Título"].apply(extrair_im)
    df_cl_ok = df_cl_ok.dropna(subset=["IM"])

    # Comercial Caio (filtrado por Profissional responsável)
    df_com_caio = excluir_rascunhos(df_com)
    df_com_caio = filtrar_por_assignee(df_com_caio, "Profissional responsável", "Caio")
    df_com_caio["IM"] = df_com_caio["Título"].apply(extrair_im)
    col_anuncio = "Data publicação Anúncio"
    if col_anuncio not in df_com_caio.columns:
        print(f"[bonus_caio] coluna '{col_anuncio}' ausente no Comercial — bonus_n=0")
        return 0
    # IMs do Comercial Caio com anúncio preenchido (em qualquer momento dentro do recorte)
    ims_com_anuncio = set(
        df_com_caio.dropna(subset=[col_anuncio, "IM"])["IM"].astype(int).tolist()
    )

    candidatos = []
    for _, row in df_cl_ok.iterrows():
        im = int(row["IM"])
        if im in ims_com_anuncio:
            continue  # tem anúncio → não elegível
        cards_com_im = df_com_caio[df_com_caio["IM"] == im]
        candidatos.append({
            "im": im,
            "data_1o_boleto": row[col_boleto],
            "card_cl_id": row.get("id"),
            "qtd_cards_comercial": len(cards_com_im),
            "fases_comercial": cards_com_im["Fase atual"].tolist() if len(cards_com_im) else [],
        })

    print(f"\n[bonus_caio] {len(candidatos)} candidato(s) ao bônus — precisam validação manual:")
    for c in candidatos[:50]:
        boleto_str = c["data_1o_boleto"].date().isoformat() if pd.notna(c["data_1o_boleto"]) else "—"
        print(f"  IM{c['im']:>5}  1º Boleto={boleto_str}  comercial_cards={c['qtd_cards_comercial']}  "
              f"fases={c['fases_comercial']}")

    # Carrega lista de IMs validados de config/bonus_caio.json se não passada explicitamente
    if validated_ims is None:
        cfg_path = ROOT / "config" / "bonus_caio.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            # Cobertura: continuação da 10ª + IMs validados na 11ª
            validated_ims = set(cfg.get("edicao_11_continuacao", []) + cfg.get("edicao_11_validados", []))
            print(f"[bonus_caio] carregada config/bonus_caio.json: continuação={cfg.get('edicao_11_continuacao')}  "
                  f"validados_11={cfg.get('edicao_11_validados')}")
        else:
            print(f"[bonus_caio] config/bonus_caio.json não encontrado — N=0")
            return 0

    cand_ims = {c["im"] for c in candidatos}
    validos = validated_ims & cand_ims
    invalidos_da_config = validated_ims - cand_ims  # IMs validados mas que não estão entre os candidatos (drift)
    pendentes = cand_ims - validated_ims
    print(f"[bonus_caio] N={len(validos)}  validados∩candidatos={sorted(validos)}")
    if invalidos_da_config:
        print(f"[bonus_caio] AVISO: validados na config mas fora dos candidatos atuais (drift): "
              f"{sorted(invalidos_da_config)}")
    if pendentes:
        print(f"[bonus_caio] pendentes (precisam validação): {sorted(pendentes)}")
    return len(validos)


def _contar_bonus_assessora(dfs: dict, assessora: str, ref: Optional[pd.Timestamp] = None) -> int:
    """
    Bônus assessora · "Vistoria de entrada realizada" (Cont. ADM, manual v4 §4.3).

    N = cards no pipe Cont.ADM (cutoff 180d) onde:
      - "Criar Card de Vistoria Técnica" preenchido
      - "Assessor (lista)" contém o nome da assessora
      - Para GARDÊNIA: cards SEM Assessor preenchido mas CONCLUÍDOS também contam (regra 8ª Ed).
    """
    from calculate import (excluir_rascunhos, aplicar_cutoff, _nome_assessora_alt,
                            _contem_qualquer, _as_list)

    df = dfs.get("cont_adm", pd.DataFrame())
    if len(df) == 0:
        return 0
    df = excluir_rascunhos(df)
    df = aplicar_cutoff(df, "Criado em", ref=ref)

    col_vist = "Criar Card de Vistoria Técnica"
    col_assess = "Assessor (lista)"
    if col_vist not in df.columns or col_assess not in df.columns:
        return 0

    # Critério "vistoria efetivamente criada": campo precisa ter conteúdo NÃO-VAZIO.
    # Pipefy retorna lista; quando o card não tem vistoria, vem como '[]' (string), [] (lista
    # vazia), null, "" ou whitespace. Tudo isso conta como NÃO preenchido.
    def _vist_preenchida(v) -> bool:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return False
        if isinstance(v, list):
            return len(v) > 0
        s = str(v).strip()
        return s not in ("", "[]", "null", "None")

    nomes = _nome_assessora_alt(assessora)
    mask_nome = df[col_assess].apply(lambda v: _contem_qualquer(v, nomes))
    if assessora == "gardenia":
        sem_assessor = df[col_assess].apply(lambda v: not _as_list(v))
        concluido = df.get("Primeira vez que entrou na fase Concluído", pd.Series([pd.NaT]*len(df))).notna()
        mask_nome = mask_nome | (sem_assessor & concluido)

    mask_final = mask_nome & df[col_vist].apply(_vist_preenchida)
    sub = df[mask_final]
    n = int(len(sub))

    ims = sub["Título"].apply(lambda t: __import__("re").search(r"IM\s*(\d+)", str(t), __import__("re").IGNORECASE))
    ims_list = [int(m.group(1)) for m in ims if m]
    print(f"[bonus_{assessora}] N={n} cards  IMs={ims_list[:15]}{'…' if len(ims_list)>15 else ''}")
    return n


# ────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> None:
    use_cache = "--no-cache" not in argv
    validate = "--validate" in argv
    ref = pd.Timestamp.utcnow()
    if "--ref" in argv:
        ref = pd.Timestamp(argv[argv.index("--ref") + 1], tz="UTC")

    print(f"[run] use_cache={use_cache}  validate={validate}  ref={ref.isoformat()}")
    dfs = carregar_dataframes(use_cache=use_cache, verbose=True)

    if validate:
        from pipeline.validate import validar
        validar(ref)
        return

    bonus_viv = calcular_bonus_inadimplencia(
        dfs["imobiliar"], df_inadimplencia=dfs["inadimplencia"], ref=ref
    )
    # Persiste resultado em config/bonus_vivianne.json para auditoria e drilldown.
    cfg_viv = ROOT / "config" / "bonus_vivianne.json"
    cfg_viv.parent.mkdir(parents=True, exist_ok=True)
    cfg_viv.write_text(json.dumps({
        "edicao_11": {
            "N": bonus_viv["N"],
            "denominador_R1": bonus_viv["denominador_R1"],
            "taxa": round(bonus_viv["taxa"], 4),
            "regra_aplicada": "R1 (multa ≤15%) + R2 (card.criado ≤ data_pag) + R3 (data_pag ≤ data_repasse)",
            "data_calculo": datetime.utcnow().date().isoformat(),
            "antes_count": int(len(bonus_viv["antes"])),
            "sem_card_count": int(len(bonus_viv["sem_card"])),
            "reativos_count": int(len(bonus_viv["reativos"])),
            "depois_count": int(len(bonus_viv["depois"])),
            "excluidos_rescisao_count": int(len(bonus_viv["excluidos_rescisao"])),
            "excluidos_valor0_count": int(len(bonus_viv["excluidos_valor0"])),
            "multiplos_count": int(len(bonus_viv["multiplos"])),
            "_aviso_drift_vs_baseline": (
                f"Drift de {bonus_viv['N'] - 124:+d} vs baseline 10ª (N=124) é INTENCIONAL. "
                "A 10ª Edição usava regra mais permissiva (sem checar temporalidade do card). "
                "A regra correta foi confirmada pela gestora em 14/05/2026: bônus só conta se "
                "Vivianne abriu card ANTES ou NO MESMO DIA do pagamento, excluindo casos onde "
                "card foi criado dias/semanas depois (cobrança reativa, não proativa)."
            ),
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    atual = build_atual(dfs, ref=ref, bonus_n_vivianne=bonus_viv["N"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(atual, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[run] gravado: {OUT_JSON.relative_to(ROOT)}")
    print(f"[run] pessoas (pos, id, nota):")
    for p in atual["PESSOAS"]:
        print(f"       {p['pos']}. {p['id']:9} nota={p['nota']}  inds={p['inds']}  "
              f"pts={p['pts']}  bonus={p['bonus']}")


if __name__ == "__main__":
    main(sys.argv[1:])
