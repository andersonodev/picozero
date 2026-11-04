# backend/tests/test_ingestao.py
# Ingestão multi-formato: cada formato vira pontos de 15 min (horário local) ou eventos,
# sem rede e sem chave do Gemini (a IA entra por um stub).
import io
import json
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

# Permite `uv run pytest` sem instalar o pacote (sem efeito se pyproject já tiver pythonpath).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from picozero.dominio import Evento
from picozero.ingestao import analisar_arquivo, analisar_json, analisar_texto, detectar_formato, normalizacao

FIXTURES = Path(__file__).parent / "fixtures" / "ingestao"
PDF_REAL = Path(__file__).resolve().parents[2] / "dados_referencia_calendario_26-2_ibmec-rj.pdf"


@pytest.fixture(autouse=True)
def hoje_fixo(monkeypatch):
    monkeypatch.setattr(normalizacao, "hoje", lambda: date(2026, 11, 4))


def pontos(res):
    return {p.ts.strftime("%Y-%m-%d %H:%M"): p.valor for p in res.pontos}


class IAFalsa:
    disponivel = True

    def __init__(self, mapa=None, eventos=None):
        self.mapa, self.eventos, self.chamadas = mapa, eventos, []

    def mapear_colunas(self, cabecalho, amostra, dica):
        self.chamadas.append(("mapear_colunas", cabecalho))
        return self.mapa

    def extrair_eventos(self, conteudo, mime, dica):
        self.chamadas.append(("extrair_eventos", mime))
        return self.eventos


# ---------- tabelas ----------


def test_csv_iso_utc_converte_e_agrega_pelo_maximo():
    csv = (
        b"timestamp,sessoes_ativas\n"
        b"2026-09-10T22:00:00Z,100\n2026-09-10T22:05:00Z,140\n2026-09-10T22:14:59Z,120\n2026-09-10T22:15:00Z,90\n"
    )
    res = analisar_arquivo(csv, "sessoes.csv", "text/csv")
    assert res.formato == "csv"
    assert pontos(res) == {"2026-09-10 19:00": 140.0, "2026-09-10 19:15": 90.0}
    assert all(p.ts.tzinfo is None and p.metrica == "carga" for p in res.pontos)
    assert res.mapeamento["agregacao"] == "max"
    assert res.mapeamento["valor"] == "sessoes_ativas"


def test_csv_ponto_e_virgula_cp1252_virgula_decimal_e_data_br():
    csv = "Data;Hora;Usuários simultâneos\n10/09/2026;22:45;1.234,5\n10/09/2026;22:50;987,0\n11/09/2026;00:05;10,5\n"
    res = analisar_arquivo(csv.encode("cp1252"), "relatorio.csv", "application/vnd.ms-excel")
    assert res.formato == "csv"
    assert res.mapeamento["encoding"] == "cp1252"
    assert res.mapeamento["decimal"] == ","
    assert pontos(res) == {"2026-09-10 22:45": 1234.5, "2026-09-11 00:00": 10.5}


def test_kibana_count_soma_e_avisa_escala():
    res = analisar_arquivo((FIXTURES / "kibana_count.csv").read_bytes(), "kibana.csv")
    assert pontos(res) == {"2026-09-10 22:45": 2221.0, "2026-09-10 23:00": 500.0}
    assert res.mapeamento["agregacao"] == "soma"
    assert any("contagem" in a for a in res.avisos)


def test_xlsx_escolhe_aba_e_coluna_de_sessoes():
    openpyxl = pytest.importorskip("openpyxl")
    livro = openpyxl.Workbook()
    resumo = livro.active
    resumo.title = "Resumo"
    resumo.append(["Relatório de acessos"])
    dados = livro.create_sheet("Dados")
    dados.append(["Horário", "Requisições", "Sessões ativas"])
    for minuto, req, sess in [(45, 900, 300), (50, 950, 340), (0, 400, 120)]:
        hora = 22 if minuto else 23
        dados.append([datetime(2026, 9, 10, hora, minuto), req, sess])
    buffer = io.BytesIO()
    livro.save(buffer)
    res = analisar_arquivo(buffer.getvalue(), "acessos.xlsx")
    assert res.formato == "xlsx"
    assert res.mapeamento["planilha"] == "Dados"
    assert res.mapeamento["valor"] == "Sessões ativas"
    assert pontos(res) == {"2026-09-10 22:45": 340.0, "2026-09-10 23:00": 120.0}


def test_csv_de_eventos_vira_calendario():
    csv = b"data,descricao,turmas\n12/11/2026,Abertura da AP2 online,ADM-2A;ECO-2A\n10/12/2026,Vencimento da 6a parcela,\n"
    res = analisar_arquivo(csv, "eventos.csv")
    assert not res.pontos
    tipos = {e.data: (e.tipo, e.hora_inicio, e.turmas) for e in res.eventos}
    assert tipos["2026-11-12"] == ("prova_online", "19:00", ["ADM-2A", "ECO-2A"])
    assert tipos["2026-12-10"][0] == "vencimento"


def test_csv_ambiguo_pede_mapa_ao_gemini():
    csv = b"quando,a,b\n2026-09-10 22:45,1,300\n2026-09-10 22:50,2,350\n2026-09-10 23:00,3,100\n"
    ia = IAFalsa(mapa={"ts": "quando", "valor": "b", "agregacao": "max"})
    res = analisar_arquivo(csv, "x.csv", ia=ia)
    assert ia.chamadas == [("mapear_colunas", ["quando", "a", "b"])]
    assert res.origem == "gemini"
    assert pontos(res) == {"2026-09-10 22:45": 350.0, "2026-09-10 23:00": 100.0}


def test_csv_ambiguo_sem_ia_escolhe_pela_variancia_e_avisa():
    csv = b"quando,a,b\n2026-09-10 22:45,1,300\n2026-09-10 22:50,2,350\n2026-09-10 23:00,3,100\n"
    res = analisar_arquivo(csv, "x.csv")
    assert res.mapeamento["valor"] == "b"
    assert any("variância" in a for a in res.avisos)


# ---------- JSON / NDJSON ----------


def test_elasticsearch_date_histogram_usa_subagregacao():
    res = analisar_arquivo((FIXTURES / "elastic_date_histogram.json").read_bytes(), "busca.json")
    assert res.formato == "json"
    assert res.mapeamento["fonte"] == "elasticsearch"
    assert res.mapeamento["agregacao"] == "max"
    assert pontos(res) == {"2026-09-10 22:45": 321.0, "2026-09-10 23:00": 290.0}
    assert res.linhas_ignoradas == 1


def test_elasticsearch_so_doc_count_soma():
    obj = {
        "aggregations": {
            "h": {"buckets": [{"key": 1789091100000, "doc_count": 10}, {"key": 1789091400000, "doc_count": 5}]}
        }
    }
    res = analisar_json(obj)
    assert pontos(res) == {"2026-09-10 22:45": 15.0}
    assert res.mapeamento["agregacao"] == "soma"


def test_prometheus_query_range_soma_instancias():
    res = analisar_arquivo((FIXTURES / "prometheus_query_range.json").read_bytes(), "prom.json")
    assert res.mapeamento["fonte"] == "prometheus"
    assert pontos(res) == {"2026-09-10 22:45": 205.0, "2026-09-10 23:00": 100.0}
    assert any("séries somadas" in a for a in res.avisos)


def test_ndjson_rum_conta_usuarios_distintos():
    res = analisar_arquivo((FIXTURES / "rum.ndjson").read_bytes(), "rum.ndjson")
    assert res.formato == "ndjson"
    assert res.mapeamento["agregacao"] == "distintos"
    assert res.mapeamento["metrica_original"] == "user.id"
    assert pontos(res) == {"2026-09-10 22:45": 2.0, "2026-09-10 23:00": 1.0}
    assert res.linhas_ignoradas >= 1


def test_webhook_lista_generica_e_objeto_unico():
    res = analisar_json(
        [{"ts": "2026-09-10T22:45:00-03:00", "valor": 300}, {"ts": "2026-09-10T22:50:00-03:00", "valor": 410}]
    )
    assert pontos(res) == {"2026-09-10 22:45": 410.0}
    unico = analisar_json({"timestamp": 1789091100000, "metrics": {"sessions": 5}})
    assert pontos(unico) == {"2026-09-10 22:45": 5.0}
    assert unico.mapeamento["valor"] == "metrics.sessions"


def test_grafana_datapoints_valor_antes_do_ts():
    res = analisar_json([{"target": "sessoes", "datapoints": [[120, 1789091100000], [130, 1789091400000]]}])
    assert pontos(res) == {"2026-09-10 22:45": 130.0}


# ---------- textos de máquina ----------


def test_access_log_conta_ips_distintos_e_5xx():
    res = analisar_arquivo((FIXTURES / "access.log").read_bytes(), "access.log")
    assert res.formato == "log"
    assert pontos(res) == {"2026-09-10 22:45": 3.0, "2026-09-10 23:00": 1.0}
    assert any("5xx" in a for a in res.avisos)


def test_prometheus_exposicao_soma_labels():
    texto = (
        b"# HELP portal_sessoes_ativas Sessoes ativas no portal\n# TYPE portal_sessoes_ativas gauge\n"
        b'portal_sessoes_ativas{instancia="a"} 120 1789091100000\nportal_sessoes_ativas{instancia="b"} 80 1789091100000\n'
        b"# TYPE http_requests_total counter\nhttp_requests_total 99999 1789091100000\n"
    )
    assert detectar_formato(texto, "metrics.txt", "text/plain") == "prometheus"
    res = analisar_arquivo(texto, "metrics.txt")
    assert res.mapeamento["valor"] == "portal_sessoes_ativas"
    assert pontos(res) == {"2026-09-10 22:45": 200.0}


# ---------- calendários ----------


def test_ics_dia_inteiro_tzid_utc_e_dobra_de_linha():
    res = analisar_arquivo((FIXTURES / "calendario.ics").read_bytes(), "calendario.ics")
    assert res.formato == "ics"
    por_data = {(e.data, e.tipo): e for e in res.eventos}
    venc = por_data[("2026-12-10", "vencimento")]
    assert (venc.hora_inicio, venc.hora_fim) == ("00:00", "23:59")
    ap2 = por_data[("2026-11-12", "prova_online")]
    assert ap2.descricao in ("Abertura da AP2 online", "Avaliações Parciais AP2 (até 18/11)")
    abertura = next(e for e in res.eventos if e.descricao == "Abertura da AP2 online")
    assert (abertura.hora_inicio, abertura.hora_fim, abertura.turmas) == ("19:00", "21:00", ["ADM-2A", "ECO-2A"])
    notas = por_data[("2026-12-03", "notas")]
    assert (notas.hora_inicio, notas.hora_fim) == ("14:00", "23:59")
    assert any("(até 18/11)" in e.descricao for e in res.eventos)
    assert any("RRULE" in a for a in res.avisos)


def test_texto_livre_duas_datas_numa_frase():
    res = analisar_texto("As notas da AP2 serão divulgadas em 20/11 às 18h e o vencimento da 6ª parcela é 10/12")
    assert [(e.data, e.tipo, e.hora_inicio) for e in res.eventos] == [
        ("2026-11-20", "notas", "18:00"),
        ("2026-12-10", "vencimento", "00:00"),
    ]
    assert res.eventos[1].descricao == "Vencimento da 6ª parcela"


def test_texto_intervalo_e_data_por_extenso():
    texto = "Período de aplicação da AP2: de 12/11 a 18/11.\nResultado do vestibular em 4 de dezembro às 10h"
    res = analisar_texto(texto)
    eventos = {e.data: e for e in res.eventos}
    assert eventos["2026-11-12"].tipo == "prova_online"
    assert "(de 12/11 a 18/11)" in eventos["2026-11-12"].descricao
    assert (eventos["2026-12-04"].tipo, eventos["2026-12-04"].hora_inicio) == ("notas", "10:00")


def test_texto_com_csv_colado_e_detectado():
    res = analisar_texto("ts;sessoes\n10/09/2026 22:45;300\n10/09/2026 22:50;320\n10/09/2026 23:00;100\n")
    assert pontos(res) == {"2026-09-10 22:45": 320.0, "2026-09-10 23:00": 100.0}


def test_docx_minimo_vira_eventos():
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>Comunicado da secretaria</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Divulgação das notas da AP1 em 13/10 às 14h.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("[Content_Types].xml", "<Types/>")
        pacote.writestr("word/document.xml", xml)
    res = analisar_arquivo(buffer.getvalue(), "comunicado.docx")
    assert res.formato == "docx"
    assert [(e.data, e.tipo, e.hora_inicio) for e in res.eventos] == [("2026-10-13", "notas", "14:00")]


def test_pdf_chama_gemini_quando_disponivel():
    ia = IAFalsa(
        eventos=[
            Evento(
                data="2026-11-12",
                hora_inicio="19:00",
                hora_fim="21:00",
                tipo="prova_online",
                descricao="Abertura da AP2 online",
                turmas=["ADM-2A"],
            )
        ]
    )
    res = analisar_arquivo(b"%PDF-1.4 conteudo qualquer", "calendario.pdf", ia=ia)
    assert ia.chamadas == [("extrair_eventos", "application/pdf")]
    assert res.origem == "gemini"
    assert res.eventos[0].descricao == "Abertura da AP2 online"


def test_imagem_sem_gemini_avisa():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    res = analisar_arquivo(png, "foto.png")
    assert res.formato == "imagem"
    assert not res.eventos
    assert any("VERTEX_API_KEY" in a for a in res.avisos)


@pytest.mark.skipif(not PDF_REAL.exists(), reason="PDF de referência fora do repositório")
def test_pdf_real_sem_ia_extrai_datas_explicitas():
    res = analisar_arquivo(PDF_REAL.read_bytes(), PDF_REAL.name)
    assert res.formato == "pdf"
    datas = {e.data: e for e in res.eventos}
    assert len(datas) >= 2
    assert all(d.startswith("2026-") for d in datas)
    assert datas["2026-09-24"].tipo == "prova_online"
    assert "AS" in datas["2026-11-25"].descricao


# ---------- entradas ruins ----------


@pytest.mark.parametrize(
    ("conteudo", "nome", "formato"),
    [
        (b"", "vazio.csv", "vazio"),
        (b"   \n\n", None, "vazio"),
        (bytes(range(256)) * 4, "lixo.bin", "binario"),
        (b"\xd0\xcf\x11\xe0" + b"\x00" * 100, "antigo.xls", "xls"),
        (b"{nao e json", "x.json", "json"),
        (b"data,sessoes\n", "so_cabecalho.csv", "csv"),
        (b"PK\x03\x04quebrado", "planilha.xlsx", "xlsx"),
        (b"%PDF-1.4 sem estrutura", "quebrado.pdf", "pdf"),
    ],
)
def test_entradas_ruins_voltam_com_aviso_sem_excecao(conteudo, nome, formato):
    res = analisar_arquivo(conteudo, nome)
    assert res.formato == formato
    assert res.avisos
    assert not res.pontos and not res.eventos


def test_texto_e_json_vazios():
    assert analisar_texto("   ").avisos == ["texto vazio"]
    assert analisar_json({"nada": "aqui"}).avisos


def test_detectar_formato_por_conteudo_nao_pela_extensao():
    assert detectar_formato(b'{"a": 1}', "dados.txt", None) == "json"
    assert detectar_formato(b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", "x.txt", None) == "ics"
    assert detectar_formato(b"a,b\n1,2\n3,4\n", "x.dat", "application/vnd.ms-excel") == "csv"
    assert detectar_formato(b"a\tb\n1\t2\n3\t4\n", None, None) == "tsv"
    assert detectar_formato((FIXTURES / "rum.ndjson").read_bytes(), None, None) == "ndjson"
    assert detectar_formato("Olá, as provas começam dia 12/11.".encode(), None, None) == "texto"
    assert json.loads((FIXTURES / "prometheus_query_range.json").read_text())["status"] == "success"
