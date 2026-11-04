# backend/tests/test_chat.py
# Copiloto: conferência dos números contra as ferramentas, correção e queda para as regras. Sem rede.
from datetime import datetime

import pytest

from picozero import semente, servico
from picozero.armazem import Armazem
from picozero.dominio import MensagemChat, PedidoChat
from picozero.ia import chat, tarefas
from picozero.ia.conferencia import conferir, montar_base
from picozero.ia.gemini import ClienteGemini, RespostaIA
from picozero.motor.previsao import Motor

AGORA = "2026-11-04T13:00"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        a = Armazem(str(tmp_path_factory.mktemp("chat") / "teste.db"))
        semente.popular(a)
        mp.setattr(servico, "_armazem", a)
        mp.setattr(servico, "_motor", Motor(a))
        mp.setattr(servico, "_ia", ClienteGemini(a))
        yield a


def _pedido(texto: str) -> PedidoChat:
    return PedidoChat(mensagens=[MensagemChat(papel="usuario", texto=texto)], unidade="rj", agora=AGORA)


def test_picos_historicos_acha_o_maior_do_ano(base):
    h = tarefas.picos_historicos("rj", "2026-01-01", "2026-12-31")
    valores = [x["pico_real"] for x in h["maiores"]]
    assert valores == sorted(valores, reverse=True)
    pts = base.serie("rj", "2026-01-01", "2027-01-01")
    assert h["maiores"][0]["pico_real"] == round(max(v for _, v, _ in pts))
    assert h["origem_dados"] == ["modelo"]


def test_conferencia_pega_numero_inventado(base):
    h = tarefas.picos_historicos("rj", "2026-09-24", "2026-09-30")
    topo = h["maiores"][0]
    dd, mm = topo["data"][8:], topo["data"][5:7]
    certa = f"O maior pico da AP1 foi {topo['pico_real']} em {dd}/{mm} às {topo['hora']} ({topo['pct_capacidade']}%)."
    assert conferir(certa, montar_base([h], [], 500)).ok
    errada = f"O maior pico da AP1 foi 912 em {dd}/{mm} às 23:10."
    r = conferir(errada, montar_base([h], [], 500))
    assert not r.ok and "912" in r.suspeitos and "23:10" in r.suspeitos
    # Sem nenhuma ferramenta chamada, qualquer número é suspeito.
    assert not conferir("O maior pico de 2026 foi 542 em 15/06 às 09:00.", montar_base([], ["maior pico de 2026"], 500)).ok


def test_conferencia_ignora_siglas_anos_e_contagens(base):
    assert conferir("A AP1 2026.2 tem 3 turmas e 5ª parcela em 2026.", montar_base([], [], 500)).ok


def test_regras_respondem_periodo_e_ano(base):
    agora = datetime.fromisoformat(AGORA)
    r = chat._por_regras("pico na semana de ap1 de 2026", "rj", agora)
    h = tarefas.picos_historicos("rj", "2026-09-24", "2026-09-30")
    assert "AP1" in r.resposta and str(h["maiores"][0]["pico_real"]) in r.resposta.replace(".", "")
    assert r.ferramentas[0].etapa == "picos_historicos"
    r = chat._por_regras("qual foi o maior pico de 2026?", "rj", agora)
    topo = tarefas.picos_historicos("rj", "2026-01-01", "2026-12-31")["maiores"][0]
    assert f"{topo['pico_real']:,}".replace(",", ".") in r.resposta
    assert "simulado" in r.resposta
    r = chat._por_regras("como fica a AP2?", "rj", agora)
    assert "previsão" in r.resposta and "AP2" in r.resposta


class _Roteiro:
    """Gemini falso: devolve as respostas na ordem e guarda o que recebeu."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.conteudos = []

    def __call__(self, etapa, conteudo, **kw):
        self.conteudos.append(conteudo)
        return self.respostas.pop(0) if self.respostas else None


@pytest.fixture
def gemini_falso(base, monkeypatch):
    monkeypatch.setattr(ClienteGemini, "disponivel", property(lambda self: True))

    def usar(respostas):
        roteiro = _Roteiro(respostas)
        monkeypatch.setattr(servico.ia(), "gerar", roteiro)
        return roteiro

    return usar


def _ano():
    return tarefas.picos_historicos("rj", "2026-01-01", "2026-12-31")


def test_chat_corrige_alucinacao(gemini_falso):
    h = _ano()
    topo = h["maiores"][0]
    certa = f"O maior pico de 2026 foi {topo['pico_real']} às {topo['hora']} em {topo['data'][8:]}/{topo['data'][5:7]}."
    chamada = {"nome": "picos_historicos", "args": {"inicio": "2026-01-01", "fim": "2026-12-31"}}
    roteiro = gemini_falso([
        RespostaIA(texto="O maior pico de 2026 foi 542 em 15/06 às 09:00.", modelo="gemini-3.1-pro-preview"),
        RespostaIA(texto=certa, modelo="gemini-3.1-pro-preview", chamadas=[chamada], resultados=[h]),
    ])
    r = chat.responder(_pedido("qual foi o maior pico de 2026?"))
    assert r.origem == "gemini" and r.resposta == certa
    assert r.dados["conferencia"] == {"ok": True, "conferidos": 3, "correcoes": 1}
    correcao = roteiro.conteudos[1][-1].parts[0].text
    assert "542" in correcao and "picos_historicos" in correcao


def test_chat_exige_ferramenta_de_periodo(gemini_falso):
    # Números batem com o dia consultado, mas o modelo escolheu o dia por palpite.
    dia = tarefas.consultar_historico("rj", "2026-06-15")
    palpite = f"O maior pico de 2026 foi {dia['pico_real']} às {dia['hora_pico_real']} em 15/06."
    gemini_falso([
        RespostaIA(texto=palpite, chamadas=[{"nome": "consultar_historico", "args": {"data": "2026-06-15"}}],
                   resultados=[dia]),
        RespostaIA(texto=palpite, chamadas=[{"nome": "consultar_historico", "args": {"data": "2026-06-15"}}],
                   resultados=[dia]),
    ])
    r = chat.responder(_pedido("qual foi o maior pico de 2026?"))
    assert r.origem == "regras"
    assert f"{_ano()['maiores'][0]['pico_real']:,}".replace(",", ".") in r.resposta


def test_chat_cai_para_regras_se_insistir(gemini_falso):
    gemini_falso([RespostaIA(texto="Amanhã o pico é 999 às 19:00."), RespostaIA(texto="Amanhã o pico é 999 às 19:00.")])
    r = chat.responder(_pedido("qual o pico de amanhã?"))
    assert r.origem == "regras" and "999" not in r.resposta
