# backend/ferramentas/prova_carga.py
# Teste de carga REAL contra o portal simulado (/sim), sem Locust: reproduz em segundos a curva de
# um dia calculada pelo motor (nunca a saída do Gemini) e mede p50/p95 e taxa de 503 em 4 perfis:
#   antes            curva original do dia, sem fila
#   antes_com_fila   mesma curva, fila virtual ligada
#   depois           curva com o plano aprovado + fila
#   controle         dia tranquilo, sem fila
# Carga e capacidade são escaladas pelo mesmo --fator, então a ocupação (carga ÷ capacidade) é a do dia.
#
# Uso (de backend/):
#   uv run python ferramentas/prova_carga.py servir --porta 8765          # sobe só o /sim
#   uv run python ferramentas/prova_carga.py rodar --url http://127.0.0.1:8765 --data 2026-09-10
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# Banco próprio da ferramenta (não mexe no banco da API).
os.environ.setdefault("PICOZERO_DB", str(Path(tempfile.gettempdir()) / "picozero_prova_carga.db"))


def _pct(valores: list[float], q: float) -> float | None:
    if not valores:
        return None
    if len(valores) == 1:
        return round(valores[0])
    return round(statistics.quantiles(valores, n=100, method="inclusive")[int(q) - 1])


def servir(porta: int) -> None:
    import uvicorn
    from fastapi import FastAPI

    from picozero.sim import router

    app = FastAPI(title="PicoZero · portal simulado")
    app.include_router(router)
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


def _perfis(unidade: str, data: str, controle: str | None) -> dict[str, list]:
    from picozero import servico
    from picozero.motor import plano as planos
    from picozero.motor import prova_carga

    m = servico.motor()
    controle = controle or prova_carga.dia_controle(unidade, data)
    antes = m.curva(unidade, data, observado={}).pontos
    aprovado = planos.obter_plano(unidade, data)
    return {
        "antes": [(p.hora, p.carga, False) for p in antes],
        "antes_com_fila": [(p.hora, p.carga, True) for p in antes],
        "depois": [(p.hora, p.carga, True) for p in (aprovado.pontos_com or antes)],
        "controle": [(p.hora, p.carga, False) for p in m.curva(unidade, controle, observado={}).pontos],
        "_controle": controle,
    }


async def _usuario(cli, k: int, fim: float, cap_sim: int, fila: bool, coleta: dict) -> None:
    """Um aluno em laço fechado: pede, mede e, se tomar 503, recarrega 50 ms depois."""
    loop = asyncio.get_running_loop()
    rota = "/sim/prova" if k % 2 else "/sim/login"
    while loop.time() < fim:
        t0 = time.perf_counter()
        try:
            r = await cli.get(rota, params={"cap": cap_sim, "fila": int(fila)})
        except Exception:  # noqa: BLE001 - erro de rede conta como falha da janela
            coleta["status"]["erro_rede"] += 1
            coleta["janela"]["erro_rede"] += 1
            continue
        dt = (time.perf_counter() - t0) * 1000
        coleta["status"][r.status_code] += 1
        coleta["janela"][r.status_code] += 1
        if r.status_code == 200:
            corpo = r.json()
            coleta["total_ms"].append(dt)
            coleta["servico_ms"].append(corpo["servico_ms"])
            coleta["espera_ms"].append(corpo["espera_ms"])
            coleta["amostras"].append(corpo["servico_ms"])
        else:
            await asyncio.sleep(0.05)


async def _rodar_perfil(url: str, janelas: list[tuple[str, int, bool]], cap_sim: int, seg: float) -> dict:
    import httpx

    coleta: dict = {"total_ms": [], "servico_ms": [], "espera_ms": [], "status": Counter()}
    por_janela = []
    limites = httpx.Limits(max_connections=4000, max_keepalive_connections=4000)
    async with httpx.AsyncClient(base_url=url, timeout=60, limits=limites) as cli:
        await cli.post("/sim/zerar")
        loop = asyncio.get_running_loop()
        for hora, usuarios, fila in janelas:
            coleta["amostras"], coleta["janela"] = [], Counter()
            fim = loop.time() + seg
            await asyncio.gather(*(_usuario(cli, k, fim, cap_sim, fila, coleta) for k in range(usuarios)))
            n = sum(coleta["janela"].values()) or 1
            por_janela.append(
                {
                    "hora": hora,
                    "usuarios": usuarios,
                    "p95_servico_ms": _pct(coleta["amostras"], 95),
                    "taxa_503": round(coleta["janela"][503] / n, 4),
                }
            )
    status = coleta["status"]
    total = sum(status.values()) or 1
    return {
        "requisicoes": sum(status.values()),
        "status": {str(k): v for k, v in status.items()},
        "taxa_503": round(status[503] / total, 4),
        "p50_servico_ms": _pct(coleta["servico_ms"], 50),
        "p95_servico_ms": _pct(coleta["servico_ms"], 95),
        "p50_total_ms": _pct(coleta["total_ms"], 50),
        "p95_total_ms": _pct(coleta["total_ms"], 95),
        "p95_espera_fila_ms": _pct(coleta["espera_ms"], 95),
        "por_janela": por_janela,
    }


async def rodar(args: argparse.Namespace) -> dict:
    from picozero import contexto

    cap = contexto.unidade(args.unidade).capacidade
    cap_sim = max(1, round(cap * args.fator))
    perfis = _perfis(args.unidade, args.data, args.controle)
    controle = perfis.pop("_controle")
    resultado = {
        "parametros": {
            "data": args.data,
            "controle": controle,
            "unidade": args.unidade,
            "capacidade": cap,
            "fator": args.fator,
            "capacidade_simulada": cap_sim,
            "segundos_por_janela": args.segundos_por_janela,
            "janelas": f"{args.inicio}–{args.fim} a cada {args.passo * 15} min",
            "url": args.url,
            "quando": datetime.now().isoformat(timespec="seconds"),
        },
        "perfis": {},
    }
    for nome, pontos in perfis.items():
        janelas = [
            (h, max(1, round(c * args.fator)), fila)
            for i, (h, c, fila) in enumerate(pontos)
            if args.inicio <= h <= args.fim and i % args.passo == 0
        ]
        t0 = time.perf_counter()
        r = await _rodar_perfil(args.url, janelas, cap_sim, args.segundos_por_janela)
        r["duracao_s"] = round(time.perf_counter() - t0, 1)
        r["pico_usuarios"] = max(u for _, u, _ in janelas)
        resultado["perfis"][nome] = r
        print(
            f"{nome:15} pico {r['pico_usuarios']:4} usuários (cap {cap_sim}) · p50 {r['p50_servico_ms']} ms · "
            f"p95 {r['p95_servico_ms']} ms · espera p95 {r['p95_espera_fila_ms']} ms · 503 {r['taxa_503']:.1%} · "
            f"{r['requisicoes']} req em {r['duracao_s']} s"
        )
    saida = RAIZ / "ferramentas" / "saida"
    saida.mkdir(parents=True, exist_ok=True)
    arquivo = saida / f"prova_carga_{args.data}_{datetime.now():%Y%m%d-%H%M%S}.json"
    arquivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gravado em {arquivo.relative_to(RAIZ)}")
    return resultado


def main() -> None:
    p = argparse.ArgumentParser(description="Teste de carga do PicoZero contra o portal simulado (/sim)")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("servir", help="sobe só o router /sim")
    s.add_argument("--porta", type=int, default=8765)
    r = sub.add_parser("rodar", help="reproduz a curva do dia contra /sim")
    r.add_argument("--url", default="http://127.0.0.1:8765")
    r.add_argument("--data", default="2026-09-10")
    r.add_argument("--controle", default=None)
    r.add_argument("--unidade", default="rj")
    r.add_argument("--fator", type=float, default=0.12, help="escala de carga e capacidade (ocupação preservada)")
    r.add_argument("--segundos-por-janela", type=float, default=0.3)
    r.add_argument("--inicio", default="08:00")
    r.add_argument("--fim", default="23:45")
    r.add_argument("--passo", type=int, default=4, help="usa 1 a cada N janelas de 15 min")
    args = p.parse_args()
    if args.comando == "servir":
        servir(args.porta)
    else:
        asyncio.run(rodar(args))


if __name__ == "__main__":
    main()
