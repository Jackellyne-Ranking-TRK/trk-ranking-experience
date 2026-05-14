"""
TRK Experience — Validador contra baselines.json
================================================

Roda o pipeline Pipefy-only e compara cada indicador (ok/tot) e nota_final
contra baselines.json (10ª Edição).

Critérios:
- Tolerância por indicador: ±1 caso (manual + baselines).
- Tolerância nota final: ±0.05.
- Indicadores Octadesk (WhatsApp, Ticket) e Bônus Inadimplência via CSV: marcados como "skip".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from calculate import (
    calc_caio_comercial_locacao, calc_caio_contrato_locacao, calc_caio_contrato_adm, calc_caio_renovacao,
    calc_vivianne_contrato_adm, calc_vivianne_rescisao_adm, calc_vivianne_contrato_locacao,
    calc_vivianne_rescisao_locacao, calc_vivianne_renovacao, calc_vivianne_inadimplencia, calc_vivianne_backoffice,
    calc_assessora_contrato_adm, calc_assessora_rescisao_adm, calc_assessora_rescisao_locacao,
    calc_assessora_reparos, calc_assessora_renovacao, calc_assessora_backoffice, calc_assessora_dirf_darf,
    calc_marinho_vistorias, calc_marinho_contestacoes,
    nota_processo, nota_final,
)
from pipeline.extract_pipefy import extract_pipe

BASELINES_PATH = ROOT / "baselines.json"
TOL_NOTA_FINAL = 0.05
TOL_CASE = 1

# Bônus que vamos passar para reproduzir baseline 10ª.
BONUS_BASELINE_10 = {
    "caio_imovel_alugado": 4,
    "vivianne_boletos": 124,
    "natalia_vistoria": 5,
    "gardenia_vistoria": 4,
}

# Indicadores que dependem de Octadesk / CSV — pulados nesta versão.
SKIP_NAMES = {
    "Tickets — SLA <4h úteis",
    "Tickets — Avaliações positivas",
    "WhatsApp — Resposta ≤5min",
    "WhatsApp — Avaliações positivas",
}


def _calc_pessoa(pessoa: str, dfs: dict, ref: pd.Timestamp) -> dict:
    """Retorna {'indicadores': [...], 'scores_por_processo': {...}}."""
    out_ind, scores = [], {}

    if pessoa == "caio":
        com = calc_caio_comercial_locacao(dfs["comercial_locacao"], bonus_n=BONUS_BASELINE_10["caio_imovel_alugado"], ref=ref)
        cl = calc_caio_contrato_locacao(dfs["comercial_locacao"], dfs["cont_locacao"], ref=ref)
        cadm = calc_caio_contrato_adm(dfs["cont_adm"], ref=ref)
        ren = calc_caio_renovacao(dfs["renovacao"], ref=ref)
        scores["Com. Locação"] = com["nota"]
        scores["Cont. Locação"] = cl["nota"]
        scores["Cont. ADM"] = cadm["nota"]
        scores["Renovação"] = ren["nota"]
        out_ind = com["indicadores"] + cl["indicadores"] + cadm["indicadores"] + ren["indicadores"]

    elif pessoa == "vivianne":
        ca = calc_vivianne_contrato_adm(dfs["cont_adm"], ref=ref)
        ra = calc_vivianne_rescisao_adm(dfs["rescisao_adm"], ref=ref)
        cl = calc_vivianne_contrato_locacao(dfs["cont_locacao"], ref=ref)
        rl = calc_vivianne_rescisao_locacao(dfs["rescisao_loc"], ref=ref)
        rn = calc_vivianne_renovacao(dfs["renovacao"], ref=ref)
        ina = calc_vivianne_inadimplencia(dfs["inadimplencia"], bonus_n=BONUS_BASELINE_10["vivianne_boletos"], ref=ref)
        bo = calc_vivianne_backoffice(dfs["backoffice"], ref=ref)
        scores["Cont. ADM"] = ca["nota"]; scores["Rescisão ADM"] = ra["nota"]; scores["Cont. Locação"] = cl["nota"]
        scores["Rescisão Loc."] = rl["nota"]; scores["Renovação"] = rn["nota"]; scores["Inadimplência"] = ina["nota"]
        scores["BackOffice"] = bo["nota"]
        out_ind = ca["indicadores"] + ra["indicadores"] + cl["indicadores"] + rl["indicadores"] + rn["indicadores"] + ina["indicadores"] + bo["indicadores"]

    elif pessoa in ("natalia", "gardenia"):
        bn = BONUS_BASELINE_10[f"{pessoa}_vistoria"]
        cadm = calc_assessora_contrato_adm(dfs["cont_adm"], pessoa, bonus_n=bn, ref=ref)
        rad = calc_assessora_rescisao_adm(dfs["rescisao_adm"], pessoa, ref=ref)
        rlc = calc_assessora_rescisao_locacao(dfs["rescisao_loc"], pessoa, ref=ref)
        rep = calc_assessora_reparos(dfs["reparos"], pessoa, ref=ref)
        ren = calc_assessora_renovacao(dfs["renovacao"], pessoa, ref=ref)
        bo = calc_assessora_backoffice(dfs["backoffice"], pessoa, ref=ref)
        dirf = calc_assessora_dirf_darf(dfs["dirf_darf"], pessoa, ref=ref)
        scores["Cont. ADM"] = cadm["nota"]; scores["Rescisão ADM"] = rad["nota"]; scores["Rescisão Loc."] = rlc["nota"]
        scores["Reparos"] = rep["nota"]; scores["Renovação"] = ren["nota"]; scores["BackOffice"] = bo["nota"]
        scores["DIRF/DARF"] = dirf["nota"]
        out_ind = cadm["indicadores"] + rad["indicadores"] + rlc["indicadores"] + rep["indicadores"] + ren["indicadores"] + bo["indicadores"] + dirf["indicadores"]

    elif pessoa == "marinho":
        vist = calc_marinho_vistorias(dfs["vistorias"], ref=ref)
        cont = calc_marinho_contestacoes(dfs["contestacoes"], ref=ref)
        # Marinho: 2 processos separados → nota final = média
        scores["Vistorias"] = vist["nota"]
        scores["Contestações"] = cont["nota"]
        out_ind = vist["indicadores"] + cont["indicadores"]

    return {"indicadores": out_ind, "scores_por_processo": scores}


def _match_name(baseline_name: str, computed: list[dict]) -> Optional[dict]:
    """Tenta achar o indicador computado equivalente ao do baseline.

    Indicadores marcados com ★ são metadados de reporting do bônus (Fórmula A do manual v4:
    nota = (score_base + N) / (peso_base + N) × 10). N é aplicado dentro de `nota_processo`
    via `bonus_n`; não há um indicador ranqueado item-a-item correspondente em `calculate.py`.
    Portanto não tentamos casar — retornamos None para sinalizar tratamento especial.
    """
    if "★" in baseline_name:
        return None
    # tenta match exato primeiro
    for c in computed:
        if c["nome"] == baseline_name:
            return c
    # match por palavras-chave (fragmento mais longo)
    bn = baseline_name.lower()
    melhor = None
    melhor_score = 0
    for c in computed:
        cn = c["nome"].lower()
        # comparação simples: número de tokens em comum
        toks_b = set(bn.split())
        toks_c = set(cn.split())
        comum = len(toks_b & toks_c)
        if comum > melhor_score:
            melhor_score = comum
            melhor = c
    return melhor if melhor_score >= 2 else None


def validar(ref: pd.Timestamp, verbose: bool = True) -> dict:
    baseline = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
    dfs = {k: extract_pipe(k, verbose=False) for k in [
        "comercial_locacao", "cont_locacao", "cont_adm", "rescisao_adm", "rescisao_loc",
        "reparos", "renovacao", "inadimplencia", "backoffice", "dirf_darf",
        "vistorias", "contestacoes",
    ]}

    relatorio = {}
    for pessoa in ("caio", "vivianne", "natalia", "gardenia", "marinho"):
        computed = _calc_pessoa(pessoa, dfs, ref)
        ind_base = baseline["colaboradores"][pessoa]["indicadores"]
        nota_base = baseline["colaboradores"][pessoa]["nota_final"]

        diff_indicadores = []
        for ib in ind_base:
            if ib["nome"] in SKIP_NAMES:
                diff_indicadores.append({"nome": ib["nome"], "status": "SKIP-Octadesk",
                                          "ok_b": ib["ok"], "tot_b": ib["tot"]})
                continue
            if "★" in ib["nome"]:
                # Bônus aplicado via fórmula A em nota_processo — não é um indicador ranqueado.
                diff_indicadores.append({"nome": ib["nome"], "status": "BONUS-via-formula",
                                          "ok_b": ib["ok"], "tot_b": ib["tot"]})
                continue
            ic = _match_name(ib["nome"], computed["indicadores"])
            if ic is None:
                diff_indicadores.append({"nome": ib["nome"], "status": "MISS",
                                          "ok_b": ib["ok"], "tot_b": ib["tot"]})
                continue
            d_ok = abs(ic["ok"] - ib["ok"]); d_tot = abs(ic["tot"] - ib["tot"])
            status = "OK" if (d_ok <= TOL_CASE and d_tot <= TOL_CASE) else "OFF"
            diff_indicadores.append({"nome": ib["nome"], "status": status,
                                      "ok": ic["ok"], "tot": ic["tot"],
                                      "ok_b": ib["ok"], "tot_b": ib["tot"],
                                      "d_ok": d_ok, "d_tot": d_tot})

        nota_calc = nota_final(computed["scores_por_processo"])
        relatorio[pessoa] = {
            "nota_calc": nota_calc,
            "nota_baseline": nota_base,
            "diff_nota": (nota_calc - nota_base) if nota_calc is not None else None,
            "indicadores": diff_indicadores,
            "scores_por_processo": computed["scores_por_processo"],
        }

        if verbose:
            print(f"\n=== {pessoa.upper()} ===  nota: calc={nota_calc} baseline={nota_base}  diff={relatorio[pessoa]['diff_nota']}")
            for d in diff_indicadores:
                if d["status"] == "OK":
                    print(f"  [OK ] {d['nome']:45}  {d['ok']:>4}/{d['tot']:>4}  (vs {d['ok_b']:>4}/{d['tot_b']:>4})")
                elif d["status"] == "SKIP-Octadesk":
                    print(f"  [SKIP] {d['nome']:45}  (baseline {d['ok_b']:>4}/{d['tot_b']:>4})")
                elif d["status"] == "BONUS-via-formula":
                    print(f"  [BONUS] {d['nome']:45}  N={d['ok_b']:>4} (aplicado via fórmula A em nota_processo)")
                elif d["status"] == "MISS":
                    print(f"  [MISS] {d['nome']:45}  (baseline {d['ok_b']:>4}/{d['tot_b']:>4})")
                else:
                    print(f"  [OFF] {d['nome']:45}  {d['ok']:>4}/{d['tot']:>4}  (vs {d['ok_b']:>4}/{d['tot_b']:>4})  Δok={d['d_ok']} Δtot={d['d_tot']}")
    return relatorio


if __name__ == "__main__":
    REF = pd.Timestamp("2026-05-11", tz="UTC")
    validar(REF)
