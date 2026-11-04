# backend/tests/test_plano.py
# Evitar / reagir / provar: validador, planejador por regras, comunicado, prova de carga e /sim.
# Banco temporário semeado uma vez; IA forçada indisponível (sem rede, mesmo com chave no .env).
import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from picozero import contexto, semente, servico
from picozero.armazem import Armazem
from picozero.dominio import Acao, Plano
from picozero.ia.gemini import ClienteGemini
from picozero.motor.previsao import Motor

NOTAS_AC = "Divulgação de notas da Avaliação Contínua (AC)"


@pytest.fixture(scope="module", autouse=True)
def servicos(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ClienteGemini, "disponivel", property(lambda self: False))
        a = Armazem(str(tmp_path_factory.mktemp("plano") / "teste.db"))
        semente.popular(a)
        mp.setattr(servico, "_armazem", a)
        mp.setattr(servico, "_motor", Motor(a))
        mp.setattr(servico, "_ia", ClienteGemini(a))
        yield


def _dia_util(iso: str) -> bool:
    return date.fromisoformat(iso).weekday() < 5 and not contexto.feriado(iso)


# ---------- validador ----------


def test_reprova_notas_em_cima_de_prova():
    from picozero.motor.plano import validar

    plano = Plano(acoes=[Acao(tipo="mover_notas", evento=NOTAS_AC, para_data="2026-09-24", para_hora="18:30")])
    t = validar("rj", "2026-09-10", plano)
    assert not t.ok
    assert "prova online" in t.erro and "AP1" in t.erro


def test_reprova_notas_em_feriado():
    from picozero.motor.plano import validar

    plano = Plano(acoes=[Acao(tipo="mover_notas", evento=NOTAS_AC, para_data="2026-09-07", para_hora="10:00")])
    t = validar("rj", "2026-09-10", plano)
    assert not t.ok
    assert "feriado" in t.erro


def test_reprova_vencimento_movido():
    from picozero.motor.plano import validar

    acao = Acao(tipo="mover_notas", evento="Vencimento da 3ª parcela da semestralidade", para_data="2026-09-14")
    t = validar("rj", "2026-09-10", Plano(acoes=[acao]))
    assert not t.ok
    assert "Vencimento e provas não mudam" in t.erro


def test_reprova_carga_empurrada_para_dia_critico():
    from picozero.motor.plano import validar

    # 11/09 (fim da rematrícula) já passa da capacidade: notas não podem ir para lá.
    plano = Plano(acoes=[Acao(tipo="mover_notas", evento=NOTAS_AC, para_data="2026-09-11", para_hora="13:00", lotes=4)])
    t = validar("rj", "2026-09-10", plano)
    assert not t.ok
    assert "dia crítico" in t.erro


def test_aprova_lotes_validos():
    from picozero.motor.plano import validar

    acao = Acao(
        tipo="mover_notas",
        evento="Divulgação de notas finais (AS e Teste de Progresso)",
        para_data="2026-12-04",
        para_hora="09:00",
        lotes=4,
        intervalo_min=90,
    )
    t = validar("rj", "2026-12-03", Plano(acoes=[acao]))
    assert t.ok, t.erro
    assert t.pico.carga <= contexto.unidade("rj").capacidade
    assert any("Nenhuma ação conflita com prova online" in c for c in t.checagens)


def test_fila_virtual_so_vale_na_janela():
    from picozero.motor.plano import validar

    # Fila só à noite não esconde o pico das 9h do Teste de Progresso.
    t = validar("rj", "2026-09-10", Plano(acoes=[Acao(tipo="fila_virtual", inicio="18:00", fim="23:59")]))
    assert not t.ok
    assert "9h" in t.erro


# ---------- planejador ----------


@pytest.mark.parametrize("dia", ["2026-09-10", "2026-11-12"])
def test_planejar_regras_preenche_tres_niveis(dia):
    from picozero.motor.plano import planejar

    r = planejar("rj", dia, usar_ia=False)
    assert 1 <= len(r.tentativas) <= 3
    assert r.tentativas[-1].ok
    assert r.plano is not None
    assert r.plano.calendario and r.plano.comunicacao and r.plano.infra_checklist
    assert len(r.pontos_com) == 96
    assert r.pico_com.carga <= r.capacidade < r.pico_sem.carga
    assert r.origem == "regras"


def test_obter_plano_usa_cache():
    from picozero.motor.plano import obter_plano

    a = obter_plano("rj", "2026-09-10")
    assert servico.armazem().kv_get("plano:rj:2026-09-10") is not None
    assert obter_plano("rj", "2026-09-10") == a


# ---------- reagir ----------


def test_comunicado_template_com_prazo_em_dia_util():
    from picozero.ia.crise import gerar_comunicado

    c = gerar_comunicado("rj", "2026-09-10", "Portal fora do ar das 10h05 às 10h50, durante o Teste de Progresso.")
    assert c.origem == "regras"
    assert c.nova_data_prazo > "2026-09-10" and _dia_util(c.nova_data_prazo)
    assert "10h05" in c.mensagem
    assert any("multa" in r for r in c.regras_tolerancia)
    assert any("nova janela" in r for r in c.regras_tolerancia)


def test_prazo_do_gemini_e_corrigido():
    from picozero.ia.crise import _corrigir_prazo

    assert _corrigir_prazo("2026-09-12", "2026-09-10", "2026-09-14") == "2026-09-14"  # sábado → segunda
    assert _corrigir_prazo("lixo", "2026-09-10", "2026-09-14") == "2026-09-14"
    assert _corrigir_prazo("2026-09-08", "2026-09-10", "2026-09-14") == "2026-09-14"  # antes da falha


# ---------- provar ----------


def test_prova_de_carga():
    from picozero.motor.prova_carga import resumo_latencia, series_latencia

    serie = series_latencia("rj", "2026-09-10")
    assert len(serie) == 96
    assert set(serie[0]) == {"hora", "antes", "depois", "controle", "erroAntes"}
    resumo = {r["chave"]: r for r in resumo_latencia("rj", "2026-09-10", serie=serie)}
    assert resumo["antes"]["p95"] > resumo["depois"]["p95"]
    assert resumo["antes"]["erros"] > 0 and resumo["depois"]["erros"] == 0


def test_sim_503_sem_fila_e_zero_com_fila():
    from picozero.sim import _estado, router

    app = FastAPI()
    app.include_router(router)

    async def rajada(fila: int) -> list[int]:
        _estado.zerar()
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://sim") as cli:
            rs = await asyncio.gather(*(cli.get("/sim/login", params={"cap": 10, "fila": fila}) for _ in range(40)))
        return [r.status_code for r in rs]

    sem_fila = asyncio.run(rajada(0))
    com_fila = asyncio.run(rajada(1))
    assert 503 in sem_fila
    assert set(com_fila) == {200}


# ---------- rotas ----------


@pytest.fixture(scope="module")
def cliente():
    from picozero.api.rotas_plano import router as rotas
    from picozero.sim import router as sim

    app = FastAPI()
    app.include_router(rotas)
    app.include_router(sim)
    return TestClient(app)


def test_rotas(cliente):
    r = cliente.get("/api/plano/2026-09-10")
    assert r.status_code == 200 and r.json()["plano"]["infra_checklist"]
    r = cliente.get("/api/plano/2026-13-40")
    assert r.status_code == 422 and "inválida" in r.json()["detail"]
    r = cliente.get("/api/plano/2026-09-10", params={"unidade": "xx"})
    assert r.status_code == 404
    r = cliente.post("/api/plano/2026-11-12/gerar")
    assert r.status_code == 200 and r.json()["tentativas"]
    r = cliente.post("/api/crise", json={"data": "2026-09-10", "falha": "Portal fora do ar das 10h05 às 10h50."})
    assert r.status_code == 200 and r.json()["regras_tolerancia"]
    r = cliente.post("/api/crise", json={"data": "10/09/2026", "falha": "Portal fora do ar."})
    assert r.status_code == 422
    r = cliente.get("/api/prova-carga", params={"data": "2026-09-10"})
    corpo = r.json()
    assert r.status_code == 200 and len(corpo["series"]) == 96 and len(corpo["resumo"]) == 3
    r = cliente.get("/sim/estado")
    assert r.status_code == 200 and "recusados_503" in r.json()
