# backend/picozero/ingestao/estruturado.py
# JSON e NDJSON de qualquer formato: Prometheus (query API), Elasticsearch (hits e date_histogram),
# Datadog, Grafana/Graphite, listas de objetos, pares [ts, valor] e objeto único. O que não é
# formato conhecido é achatado ('metrics.sessions') e segue a mesma lógica das tabelas.
import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..dominio import ResultadoParse
from . import normalizacao as norm
from .tabular import analisar_tabela

CHAVES_LISTA = (
    "data", "items", "rows", "results", "result", "records", "docs", "documents", "values", "series", "buckets",
    "hits", "eventos", "events", "pontos", "points", "metricas", "metrics", "entries", "dados", "registros", "list",
)  # fmt: skip
ACOES_BULK = ("index", "create", "update", "delete")


def _achatar(obj: dict, prefixo: str = "", profundidade: int = 0) -> dict[str, Any]:
    """{'user': {'id': 1}} → {'user.id': 1}; listas de escalares viram 'a;b;c'."""
    plano: dict[str, Any] = {}
    for k, v in obj.items():
        nome = f"{prefixo}{k}"
        if isinstance(v, dict) and profundidade < 3:
            plano.update(_achatar(v, f"{nome}.", profundidade + 1))
        elif isinstance(v, list):
            if all(not isinstance(x, (dict, list)) for x in v):
                plano[nome] = ";".join(str(x) for x in v)
        else:
            plano[nome] = v
    return plano


def _resultado_de_pares(
    somas: dict[datetime, float], formato: str, fonte: str, nome: str, lidas: int, ignoradas: int, series: int
) -> ResultadoParse:
    modo = "soma" if norm.tipo_metrica(nome) == "contador" else "max"
    res = ResultadoParse(formato=formato, linhas_lidas=lidas, linhas_ignoradas=ignoradas)
    res.pontos = norm.agregar(somas.items(), modo)
    res.mapeamento.update(
        fonte=fonte, agregacao=modo, metrica_original=nome or "valor", fuso="epoch UTC → America/Sao_Paulo"
    )
    if series > 1:
        res.avisos.append(f"{series} séries somadas a cada instante")
    if modo == "soma":
        res.avisos.append(f"'{nome}' é contagem: somei por janela de 15 min; confira a escala da capacidade")
    if not res.pontos:
        res.avisos.append(f"resposta {fonte} sem pontos válidos")
    res.avisos.extend(norm.avisos_de_resolucao(list(somas), modo))
    return res


def _somar_series(series: list[tuple[str, list[tuple[Any, Any]]]]) -> tuple[dict[datetime, float], int, int, str]:
    somas: dict[datetime, float] = defaultdict(float)
    lidas = ignoradas = 0
    nome = next((n for n, _ in series if n), "")
    for _, pares in series:
        for ts_bruto, v_bruto in pares:
            lidas += 1
            ts = norm.para_datetime(ts_bruto)
            v = norm.para_numero(v_bruto)
            if ts is None or v is None or v < 0:
                ignoradas += 1
                continue
            somas[ts] += v
    return somas, lidas, ignoradas, nome


# ---------- formatos conhecidos ----------


def _prometheus(obj: dict, formato: str) -> ResultadoParse | None:
    dados = obj.get("data") if "status" in obj else obj
    if not isinstance(dados, dict) or "resultType" not in dados:
        return None
    if obj.get("status") == "error":
        return ResultadoParse(formato=formato, avisos=[f"Prometheus devolveu erro: {obj.get('error', '?')}"])
    tipo, resultado = dados["resultType"], dados.get("result") or []
    series: list[tuple[str, list]] = []
    if tipo == "matrix":
        series = [(r.get("metric", {}).get("__name__", ""), r.get("values") or []) for r in resultado]
    elif tipo == "vector":
        series = [(r.get("metric", {}).get("__name__", ""), [r.get("value")]) for r in resultado if r.get("value")]
    elif tipo == "scalar" and isinstance(resultado, list):
        series = [("", [resultado])]
    pares = [(n, [(p[0], p[1]) for p in ps if isinstance(p, (list, tuple)) and len(p) == 2]) for n, ps in series]
    somas, lidas, ign, nome = _somar_series(pares)
    return _resultado_de_pares(somas, formato, "prometheus", nome, lidas, ign, len(pares))


def _achar_buckets(no: Any, nome: str = "") -> tuple[list[dict], str] | None:
    if isinstance(no, dict):
        buckets = no.get("buckets")
        if isinstance(buckets, list) and buckets and isinstance(buckets[0], dict) and "key" in buckets[0]:
            primeiro = buckets[0]
            if norm.para_datetime(primeiro.get("key_as_string")) or norm.para_datetime(primeiro.get("key")):
                return buckets, nome
        for k, v in no.items():
            if isinstance(v, (dict, list)) and (achado := _achar_buckets(v, k)):
                return achado
    elif isinstance(no, list):
        for item in no:
            if isinstance(item, dict) and (achado := _achar_buckets(item, nome)):
                return achado
    return None


def _subagregacao(bucket: dict, dica: str | None) -> tuple[str, float] | None:
    """Sub-agregação métrica do bucket (cardinality, max, sum…) com o nome mais parecido com carga."""
    metricas = [
        (k, v["value"]) for k, v in bucket.items()
        if isinstance(v, dict) and isinstance(v.get("value"), (int, float)) and not isinstance(v.get("value"), bool)
    ]  # fmt: skip
    if not metricas:
        return None
    if dica:
        for k, v in metricas:
            if norm.chave(k) in norm.chave(dica):
                return k, float(v)
    k, v = max(metricas, key=lambda kv: norm.prioridade_valor(kv[0]))
    return k, float(v)


def _elastic(obj: dict, formato: str, dica: str | None, ia: Any) -> ResultadoParse | None:
    aggs = obj.get("aggregations")
    if isinstance(aggs, dict) and (achado := _achar_buckets(aggs)):
        buckets, nome_agg = achado
        # A métrica é escolhida uma vez (1º bucket com sub-agregação); sem ela, conta documentos.
        nome_valor = next((sub[0] for b in buckets if (sub := _subagregacao(b, dica))), "doc_count")
        pares, lidas, ign = [], 0, 0
        for b in buckets:
            lidas += 1
            ts = norm.para_datetime(b.get("key_as_string")) or norm.para_datetime(b.get("key"))
            bruto = b.get("doc_count") if nome_valor == "doc_count" else (b.get(nome_valor) or {}).get("value")
            v = norm.para_numero(bruto)
            if ts is None or v is None or v < 0:
                ign += 1
                continue
            pares.append((ts, v))
        modo = "soma" if norm.tipo_metrica(nome_valor) == "contador" else "max"
        res = ResultadoParse(formato=formato, linhas_lidas=lidas, linhas_ignoradas=ign)
        res.pontos = norm.agregar(pares, modo)
        res.mapeamento.update(
            fonte="elasticsearch",
            agregacao=modo,
            metrica_original=f"{nome_agg}.{nome_valor}",
            ts="key_as_string/key",
            valor=nome_valor,
            fuso="convertido para America/Sao_Paulo",
        )
        if modo == "soma":
            res.avisos.append(f"'{nome_valor}' é contagem de documentos: somei por janela de 15 min; confira a escala")
        res.avisos.extend(norm.avisos_de_resolucao([ts for ts, _ in pares], modo))
        return res
    hits = obj.get("hits")
    if isinstance(hits, dict) and isinstance(hits.get("hits"), list):
        docs = []
        for h in hits["hits"]:
            if isinstance(h, dict):
                fonte = h.get("_source") if isinstance(h.get("_source"), dict) else h.get("fields", h)
                docs.append(fonte if isinstance(fonte, dict) else h)
        res = tabela_de_objetos(docs, formato=formato, dica=dica, ia=ia)
        res.mapeamento.setdefault("fonte", "elasticsearch")
        return res
    return None


def _datadog(obj: dict, formato: str) -> ResultadoParse | None:
    series = obj.get("series")
    if isinstance(series, list) and series and isinstance(series[0], dict) and "pointlist" in series[0]:
        pares = [
            (
                s.get("metric", "") or s.get("expression", ""),
                [tuple(p[:2]) for p in s.get("pointlist") or [] if isinstance(p, list) and len(p) >= 2],
            )
            for s in series
        ]
        somas, lidas, ign, nome = _somar_series(pares)
        return _resultado_de_pares(somas, formato, "datadog", nome, lidas, ign, len(pares))
    atributos = (obj.get("data") or {}).get("attributes") if isinstance(obj.get("data"), dict) else None
    if (
        isinstance(atributos, dict)
        and isinstance(atributos.get("times"), list)
        and isinstance(atributos.get("values"), list)
    ):
        tempos = atributos["times"]
        pares = [("", list(zip(tempos, valores))) for valores in atributos["values"] if isinstance(valores, list)]
        somas, lidas, ign, nome = _somar_series(pares)
        return _resultado_de_pares(somas, formato, "datadog", nome, lidas, ign, len(pares))
    return None


def _graphite(obj: list, formato: str) -> ResultadoParse | None:
    if not (obj and all(isinstance(x, dict) and isinstance(x.get("datapoints"), list) for x in obj)):
        return None
    # Graphite/Grafana: datapoints = [[valor, ts], ...]
    pares = [
        (s.get("target", ""), [(p[1], p[0]) for p in s["datapoints"] if isinstance(p, list) and len(p) >= 2])
        for s in obj
    ]
    somas, lidas, ign, nome = _somar_series(pares)
    return _resultado_de_pares(somas, formato, "grafana", nome, lidas, ign, len(pares))


def _colunar(colunas: dict[str, list], formato: str, dica: str | None, ia: Any) -> ResultadoParse:
    nomes = list(colunas)
    tamanho = max(len(v) for v in colunas.values())
    linhas = [[colunas[n][i] if i < len(colunas[n]) else None for n in nomes] for i in range(tamanho)]
    return analisar_tabela(nomes, linhas, formato=formato, dica=dica, ia=ia)


def _grafana_frames(obj: dict, formato: str, dica: str | None, ia: Any) -> ResultadoParse | None:
    resultados = obj.get("results")
    if not isinstance(resultados, dict):
        return None
    for resultado in resultados.values():
        for frame in (resultado or {}).get("frames") or []:
            campos = ((frame.get("schema") or {}).get("fields")) or []
            valores = ((frame.get("data") or {}).get("values")) or []
            if campos and len(campos) == len(valores):
                res = _colunar(
                    {c.get("name") or f"campo_{i}": v for i, (c, v) in enumerate(zip(campos, valores))},
                    formato,
                    dica,
                    ia,
                )
                res.mapeamento.setdefault("fonte", "grafana")
                return res
    return None


def _e_colunar(obj: dict) -> bool:
    listas = [v for v in obj.values() if isinstance(v, list)]
    return (
        len(listas) >= 2
        and len(listas) == len(obj)
        and len({len(v) for v in listas}) == 1
        and len(listas[0]) >= 2
        and all(not isinstance(x, (dict, list)) for v in listas for x in v[:20])
    )


# ---------- genérico ----------


def _localizar(obj: Any, profundidade: int = 0) -> list | None:
    """Acha a lista de registros (objetos ou pares) dentro do JSON."""
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:50]):
            return obj
        if obj and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in obj[:50]):
            return obj
        return None
    if not isinstance(obj, dict) or profundidade > 4:
        return None
    minusculas = {str(k).lower(): k for k in obj}
    for k in CHAVES_LISTA:
        if k in minusculas and (achado := _localizar(obj[minusculas[k]], profundidade + 1)):
            return achado
    for v in obj.values():
        if isinstance(v, (list, dict)) and (achado := _localizar(v, profundidade + 1)):
            return achado
    plano = _achatar(obj)
    if any(norm.nome_de_tempo(k) for k in plano):
        return [obj]
    return None


def _de_pares(pares: list, formato: str) -> ResultadoParse:
    primeiro = pares[0]
    invertido = norm.para_datetime(primeiro[0]) is None and norm.para_datetime(primeiro[1]) is not None
    serie = [(p[1], p[0]) if invertido else (p[0], p[1]) for p in pares]
    somas, lidas, ign, _ = _somar_series([("", serie)])
    return _resultado_de_pares(somas, formato, "pares [ts, valor]", "valor", lidas, ign, 1)


def tabela_de_objetos(objetos: list[dict], *, formato: str, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    planos = [_achatar(o) for o in objetos if isinstance(o, dict)]
    if not planos:
        return ResultadoParse(formato=formato, avisos=["nenhum objeto para ler"])
    nomes: list[str] = []
    for p in planos:
        nomes.extend(k for k in p if k not in nomes)
    linhas = [[p.get(n) for n in nomes] for p in planos]
    return analisar_tabela(nomes, linhas, formato=formato, dica=dica, ia=ia)


def analisar_objeto(obj: Any, *, formato: str = "json", dica: str | None = None, ia: Any = None) -> ResultadoParse:
    if isinstance(obj, dict):
        for leitor in (
            lambda: _prometheus(obj, formato),
            lambda: _elastic(obj, formato, dica, ia),
            lambda: _datadog(obj, formato),
            lambda: _grafana_frames(obj, formato, dica, ia),
        ):
            if (res := leitor()) is not None:
                return res
        if _e_colunar(obj):
            return _colunar(obj, formato, dica, ia)
    if isinstance(obj, list) and (res := _graphite(obj, formato)) is not None:
        return res
    registros = _localizar(obj)
    if not registros:
        return ResultadoParse(formato=formato, avisos=["JSON sem lista de pontos ou de eventos reconhecível"])
    if isinstance(registros[0], (list, tuple)):
        return _de_pares(registros, formato)
    return tabela_de_objetos(registros, formato=formato, dica=dica, ia=ia)


def analisar_ndjson(texto: str, *, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    docs, ruins = [], 0
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError:
            ruins += 1
            continue
        if not isinstance(obj, dict):
            ruins += 1
            continue
        if len(obj) == 1 and next(iter(obj)) in ACOES_BULK and isinstance(next(iter(obj.values())), dict):
            continue  # linha de ação do bulk do Elasticsearch
        docs.append(obj["_source"] if isinstance(obj.get("_source"), dict) else obj)
    res = tabela_de_objetos(docs, formato="ndjson", dica=dica, ia=ia)
    res.linhas_ignoradas += ruins
    if ruins:
        res.avisos.append(f"{ruins} linha(s) que não são objeto JSON ignorada(s)")
    return res
