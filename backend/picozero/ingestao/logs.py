# backend/picozero/ingestao/logs.py
# Formatos de máquina em texto: access log (nginx/apache, Common/Combined) e o texto de
# exposição do Prometheus (/metrics).
import re
from collections import defaultdict
from datetime import datetime

from ..config import TZ
from ..dominio import ResultadoParse
from . import normalizacao as norm
from .deteccao import RE_LOG_LINHA, RE_PROM_AMOSTRA

SUFIXOS_INTERNOS = ("_bucket", "_sum", "_count", "_created", "_info")
PREFIXOS_INTERNOS = ("go_", "process_", "promhttp_", "python_", "scrape_")


def analisar_log(texto: str) -> ResultadoParse:
    """Carga = IPs distintos por janela de 15 min (proxy de acessos simultâneos)."""
    res = ResultadoParse(formato="log")
    pares, erros_5xx, total = [], 0, 0
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        res.linhas_lidas += 1
        m = RE_LOG_LINHA.match(linha)
        ts = norm.para_datetime(m["ts"]) if m else None
        if ts is None:
            res.linhas_ignoradas += 1
            continue
        total += 1
        erros_5xx += m["status"].startswith("5")
        pares.append((ts, m["ip"]))
    res.pontos = norm.agregar_distintos(pares)
    res.mapeamento.update(
        ts="[data] do log",
        valor="IPs distintos",
        agregacao="distintos",
        metrica_original="ip do cliente",
        requisicoes=str(total),
        fuso="convertido para America/Sao_Paulo",
    )
    if not total:
        res.avisos.append("nenhuma linha no formato Common/Combined Log")
        return res
    res.avisos.append(f"{total} requisições lidas; carga = IPs distintos por janela de 15 min")
    if erros_5xx:
        res.avisos.append(f"{100 * erros_5xx / total:.1f}% das requisições com erro 5xx")
    if res.linhas_ignoradas:
        res.avisos.append(f"{res.linhas_ignoradas} linha(s) fora do formato ignorada(s)")
    return res


def _escolher_metrica(nomes: list[str], tipos: dict[str, str], dica: str | None) -> str | None:
    if dica:
        d = norm.chave(dica)
        for nome in sorted(nomes, key=len, reverse=True):
            if norm.chave(nome) in d:
                return nome
    candidatos = [n for n in nomes if not n.endswith(SUFIXOS_INTERNOS) and not n.startswith(PREFIXOS_INTERNOS)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda n: (norm.prioridade_valor(n), tipos.get(n) == "gauge"))


def analisar_exposicao(texto: str, *, dica: str | None = None) -> ResultadoParse:
    """Texto do /metrics: soma a métrica escolhida entre os labels, no timestamp dado (ou agora)."""
    res = ResultadoParse(formato="prometheus")
    tipos: dict[str, str] = {}
    amostras: dict[str, list[tuple[float, str | None]]] = defaultdict(list)
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("#"):
            if m := re.match(r"#\s*TYPE\s+(\S+)\s+(\S+)", linha):
                tipos[m[1]] = m[2].lower()
            continue
        res.linhas_lidas += 1
        m = RE_PROM_AMOSTRA.match(linha)
        valor = norm.para_numero(m["valor"]) if m else None
        if valor is None:
            res.linhas_ignoradas += 1
            continue
        amostras[m["nome"]].append((valor, m["ts"]))
    nome = _escolher_metrica(list(amostras), tipos, dica)
    if not nome:
        res.avisos.append("nenhuma métrica de carga reconhecida no texto do Prometheus")
        return res
    agora = datetime.now(TZ).replace(tzinfo=None)
    somas: dict[datetime, float] = defaultdict(float)
    sem_ts = 0
    for valor, ts_bruto in amostras[nome]:
        ts = norm.de_epoch(float(ts_bruto)) if ts_bruto else None
        if ts is None:
            ts, sem_ts = agora, sem_ts + 1
        if valor >= 0:
            somas[ts] += valor
    res.pontos = norm.agregar(somas.items(), "max")
    res.mapeamento.update(
        fonte="prometheus /metrics", valor=nome, metrica_original=nome, agregacao="max", tipo=tipos.get(nome, "?")
    )
    if len(amostras[nome]) > 1:
        res.avisos.append(f"{len(amostras[nome])} séries de '{nome}' somadas")
    if sem_ts:
        res.avisos.append("amostras sem timestamp: usei o horário atual")
    if tipos.get(nome) == "counter":
        res.avisos.append(f"'{nome}' é contador acumulado: um snapshot não mede carga; prefira query_range com rate()")
    return res
