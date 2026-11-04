# backend/tests/test_api.py
# Fumaça da API inteira (o mesmo app que roda na Vercel) e do MCP por HTTP, sem rede e sem Gemini.
import pytest
from fastapi.testclient import TestClient

from picozero import semente, servico
from picozero.armazem import Armazem
from picozero.ia.gemini import ClienteGemini
from picozero.motor.previsao import Motor

MCP_HEADERS = {"accept": "application/json, text/event-stream", "mcp-protocol-version": "2025-06-18"}


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ClienteGemini, "disponivel", property(lambda self: False))
        a = Armazem(str(tmp_path_factory.mktemp("api") / "teste.db"))
        semente.popular(a)
        mp.setattr(servico, "_armazem", a)
        mp.setattr(servico, "_motor", Motor(a))
        mp.setattr(servico, "_ia", ClienteGemini(a))
        from picozero.api import app

        with TestClient(app) as c:
            yield c


@pytest.mark.parametrize(
    "rota",
    [
        "/api/saude", "/api/contexto?unidade=sp", "/api/unidades", "/api/eventos", "/api/marcos",
        "/api/carga/2026-11-12", "/api/picos", "/api/mapa", "/api/previsao?dias=10&agora=2026-11-04T13:00",
        "/api/riscos", "/api/manutencao/2026-11-12", "/api/alertas?agora=2026-11-11T20:00", "/api/trilha",
        "/api/modelo", "/api/validacao/publica", "/api/fontes", "/api/plano/2026-09-10", "/api/prova-carga",
        "/api/ingestao/formatos", "/api/ingestao/historico",
    ],
)
def test_rotas_de_leitura(cliente, rota):
    r = cliente.get(rota)
    assert r.status_code == 200, r.text
    assert r.json() is not None


def test_formas_que_o_front_usa(cliente):
    c = cliente.get("/api/carga/2026-11-12").json()
    assert len(c["pontos"]) == 96 and {"hora", "carga", "p10", "p90", "real", "base"} <= set(c["pontos"][0])
    risco = cliente.get("/api/riscos").json()[0]
    assert {"data", "gravidade", "eventos", "motivo", "consultados", "pico", "nivel"} <= set(risco)
    mapa = cliente.get("/api/mapa").json()
    assert len(mapa) == 127 and len(mapa[0]["horas"]) == 24


def test_erros_claros(cliente):
    assert cliente.get("/api/carga/2026-13-40").status_code == 422
    assert cliente.get("/api/contexto?unidade=xx").status_code == 404


def test_ingestao_e_chat(cliente):
    r = cliente.post("/api/ingestao/metricas?unidade=rj", json=[{"ts": "2026-11-04T12:31:00-03:00", "valor": 120}])
    assert r.status_code == 200 and r.json()["pontos_inseridos"] == 1
    r = cliente.post("/api/ingestao/texto", json={"texto": "A rematrícula 2027.1 abre em 01/12 às 9h.", "unidade": "rj"})
    assert r.status_code == 200 and r.json()["eventos_inseridos"] >= 1
    r = cliente.post("/api/ingestao/arquivo", files={"arquivo": ("serie.csv", b"timestamp,usuarios_ativos\n2026-11-03T10:00,150\n2026-11-03T10:15,170\n", "text/csv")})
    assert r.status_code == 200 and r.json()["pontos_inseridos"] == 2
    r = cliente.post("/api/chat", json={"mensagens": [{"papel": "usuario", "texto": "alertas?"}], "unidade": "rj"})
    assert r.status_code == 200 and r.json()["origem"] == "regras"


def test_mcp_por_http(cliente):
    ini = cliente.post("/mcp", headers=MCP_HEADERS, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "teste", "version": "0"}},
    })
    assert ini.status_code == 200 and ini.json()["result"]["serverInfo"]["name"] == "PicoZero"
    lista = cliente.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    nomes = {t["name"] for t in lista.json()["result"]["tools"]}
    assert {"previsao_dia", "alertas", "dicas_manutencao", "ingerir_metricas", "perguntar"} <= nomes
    chamada = cliente.post("/mcp", headers=MCP_HEADERS, json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "previsao_dia", "arguments": {"data": "2026-11-12"}},
    })
    assert chamada.status_code == 200 and "1" in str(chamada.json()["result"])
