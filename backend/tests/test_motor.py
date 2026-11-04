# backend/tests/test_motor.py
# Motor: calibração recupera a "realidade" do histórico modelado, backtest, nowcast, alertas antecipados,
# dicas de manutenção, validação com dado público e roteador do chat sem IA.
from datetime import datetime

import pytest

from picozero import semente, servico
from picozero.armazem import Armazem
from picozero.dominio import PontoMetrica
from picozero.ia import chat, tarefas
from picozero.ia.gemini import ClienteGemini
from picozero.motor import alertas, manutencao, validacao
from picozero.motor.previsao import Motor


@pytest.fixture(scope="module", autouse=True)
def servicos(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ClienteGemini, "disponivel", property(lambda self: False))
        a = Armazem(str(tmp_path_factory.mktemp("motor") / "teste.db"))
        semente.popular(a)
        mp.setattr(servico, "_armazem", a)
        mp.setattr(servico, "_motor", Motor(a))
        mp.setattr(servico, "_ia", ClienteGemini(a))
        yield


def test_calibracao_recupera_fatores_ocultos():
    fatores = servico.motor().calibracao("rj").fatores
    for tipo, verdade in semente.VERDADE.items():
        assert abs(fatores[tipo] - verdade) < 0.15, (tipo, fatores[tipo], verdade)


def test_backtest_fora_da_amostra():
    b = servico.motor().backtest("rj")
    assert b["dias_avaliados"] > 60
    assert b["mape_pico"] < 15
    assert b["dias_criticos"]["perdidos"] == 0


def test_curva_do_dia_critico():
    c = servico.motor().curva("rj", "2026-11-12")
    assert len(c.pontos) == 96
    assert c.nivel == "critico" and c.pico.hora == "19:00"
    assert c.pico.carga == max(p.carga for p in c.pontos)
    assert all(p.p10 <= p.carga <= p.p90 for p in c.pontos)
    assert c.janelas and c.janelas[0].inicio == "19:00"


def test_unidade_sem_historico_escala_pela_referencia():
    rj = servico.motor().curva("rj", "2026-11-12")
    sp = servico.motor().curva("sp", "2026-11-12")
    assert sp.capacidade == 420
    assert abs(sp.pico.carga / rj.pico.carga - 6500 / 8000) < 0.02


def test_nowcast_corrige_o_resto_do_dia():
    m = servico.motor()
    base = m.curva("rj", "2026-11-12")
    observado = {i: base.pontos[i].carga * 1.4 for i in range(68, 74)}  # 17:00–18:15, 40% acima
    agora = datetime(2026, 11, 12, 18, 15)
    c = m.curva("rj", "2026-11-12", agora=agora, observado=observado)
    assert c.ajuste_ao_vivo and c.ajuste_ao_vivo > 1.15
    assert c.observado_ate == "18:15"
    assert c.pontos[76].carga > base.pontos[76].carga  # 19:00 sobe antes de acontecer


def test_alertas_por_estagio():
    m = servico.motor()
    vespera = alertas.avaliar(m, "rj", datetime(2026, 11, 11, 20, 0))
    critico = [a for a in vespera if a.data == "2026-11-12" and a.nivel == "critico"]
    assert critico and critico[0].estagio == "vespera" and critico[0].acoes
    iminente = alertas.avaliar(m, "rj", datetime(2026, 11, 12, 17, 30), horizonte=0)
    assert any(a.estagio == "iminente" for a in iminente)


def test_alerta_ao_vivo_quando_a_carga_foge_da_previsao():
    m = servico.motor()
    a = servico.armazem()
    base = m.curva("rj", "2026-11-12")
    pontos = [PontoMetrica(ts=datetime(2026, 11, 12, i // 4, (i % 4) * 15), valor=base.pontos[i].carga * 1.4)
              for i in range(68, 74)]
    a.gravar_pontos("rj", pontos, origem="simulado")
    try:
        lista = alertas.avaliar(m, "rj", datetime(2026, 11, 12, 18, 15), horizonte=0)
        ao_vivo = [x for x in lista if x.origem == "ao_vivo"]
        assert ao_vivo and ao_vivo[0].hora_pico == "19:00" and ao_vivo[0].antecedencia_min > 0
    finally:
        a.apagar_pontos("rj", "2026-11-12", "2026-11-12~", "simulado")


def test_dicas_de_manutencao():
    c = servico.motor().curva("rj", "2026-11-12")
    d = manutencao.gerar(c)
    assert d.janela_manutencao.inicio < "07:00"
    assert d.escalar_ate and d.escalar_ate < "19:00"
    assert any(z.inicio <= "19:00" <= z.fim for z in d.congelamento)
    assert any("provas" in t.titulo for t in d.tarefas)
    assert d.nao_fazer and d.origem == "regras"
    tranquilo = manutencao.gerar(servico.motor().curva("rj", "2026-11-07"))
    assert not tranquilo.congelamento and tranquilo.escalar_ate is None


def test_riscos_por_regras_com_historico_consultado():
    rs = tarefas.riscos("rj")
    topo = rs[0]
    assert topo.gravidade == 5 and topo.pico and topo.consultados
    assert all(r.origem == "regras" for r in rs)


def test_validacao_com_dado_publico():
    v = validacao.validar(servico.motor(), servico.armazem(), "rj")
    assert len(v["meses"]) == 13
    assert v["correlacao"] > 0.6
    assert "estudante.ibmec.br" in v["leitura"]


def test_chat_sem_ia_e_datas_relativas():
    agora = datetime(2026, 11, 4, 13, 0)
    assert chat._data_citada("qual o pior dia do semestre?", agora) is None
    assert chat._data_citada("e na quarta?", agora) == "2026-11-11"
    assert chat._data_citada("dia 12/11", agora) == "2026-11-12"
    r = chat._por_regras("qual o pior dia do semestre?", "rj", agora)
    assert r.origem == "regras" and "10/09" in r.resposta
