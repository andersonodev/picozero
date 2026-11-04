# backend/picozero/ia/crise.py
# Reagir: comunicado de crise aos alunos. O código decide o prazo novo (dia útil) e as regras
# de tolerância possíveis; o Gemini só escreve o texto. Sem Gemini, sai pelo template.
import json
import re
from datetime import date

from pydantic import BaseModel, Field

from .. import contexto, servico
from ..dominio import Comunicado, Evento
from ..motor.plano import SEMANA, dm, eh_dia_util, proximo_dia_util


class ComunicadoIA(BaseModel):
    titulo: str = Field(description="Até 70 caracteres")
    mensagem: str = Field(description="Até 600 caracteres, tom humano, assume a falha")
    nova_data_prazo: str = Field(description="AAAA-MM-DD — use a data dos FATOS")
    regras_tolerancia: list[str] = Field(description="2 a 5 regras curtas, só as dos FATOS")


SISTEMA_CRISE = """Você escreve o comunicado oficial aos alunos depois de uma falha do portal acadêmico.
Tom humano e direto: reconhece a falha sem rodeios, sem jargão técnico, sem culpar fornecedor, sem pedir desculpas
em excesso. Diga o que aconteceu (horário), o que já está garantido e o que muda nos prazos. Não prometa nada que não
esteja nas REGRAS_POSSIVEIS dos FATOS e use exatamente a nova_data_prazo informada. PT-BR, frases curtas."""


def _regras(eventos: list[Evento], data: str, prazo: str) -> list[str]:
    regras: list[str] = []
    janela = proximo_dia_util(data)
    tipos = {e.tipo for e in eventos}
    for ev in eventos:
        if ev.tipo == "vencimento":
            regras.append(f"Pagamentos com vencimento em {dm(data)} feitos até {dm(prazo)} não terão multa nem juros.")
        elif ev.tipo == "prova_online":
            regras.append(
                f"Quem não concluiu “{ev.descricao}” fará a prova em nova janela em {dm(janela)}, das 10h às 12h."
            )
        elif ev.tipo == "notas":
            regras.append(
                f"As notas de “{ev.descricao}” seguem publicadas; quem não conseguiu consultar acessa normalmente a partir de {dm(janela)}."
            )
        elif ev.tipo == "rematricula":
            regras.append(f"O prazo de “{ev.descricao}” foi estendido até {dm(prazo)}.")
    if tipos & {"prova_online", "vencimento"}:
        regras.append("Respostas e pagamentos enviados antes da falha foram registrados e não precisam ser refeitos.")
    if not regras:
        regras.append(f"Solicitações com prazo em {dm(data)} serão aceitas até {dm(prazo)}.")
    regras.append("Não é preciso abrir chamado: a tolerância é aplicada automaticamente.")
    return regras


def _horario_da_falha(falha: str) -> str | None:
    m = re.search(r"(\d{1,2}h\d{0,2}|\d{1,2}:\d{2})\s*(?:às|as|a|até|e|-|–)\s*(\d{1,2}h\d{0,2}|\d{1,2}:\d{2})", falha)
    return f"Entre {m.group(1)} e {m.group(2)}" if m else None


def _template(unidade: str, data: str, falha: str, eventos: list[Evento], prazo: str) -> Comunicado:
    horario = _horario_da_falha(falha)
    abertura = (
        f"{horario} de {dm(data)}, o portal do aluno ficou instável."
        if horario
        else f"Em {dm(data)}, o portal do aluno ficou instável."
    )
    momentos = [e.descricao for e in eventos if e.tipo != "outro"]
    contexto_txt = ""
    if momentos:
        lista = ", ".join(momentos[:-1]) + (" e " if len(momentos) > 1 else "") + momentos[-1]
        contexto_txt = f" Sabemos que isso aconteceu num momento importante, com {_minusculo(lista)} no mesmo dia."
    mensagem = f"{abertura}{contexto_txt} Ninguém será prejudicado: o que já foi enviado está salvo e os prazos abaixo foram ajustados."
    return Comunicado(
        titulo=f"Instabilidade no portal em {dm(data)}: prazos estendidos",
        mensagem=mensagem,
        nova_data_prazo=prazo,
        regras_tolerancia=_regras(eventos, data, prazo),
        origem="regras",
    )


def _minusculo(texto: str) -> str:
    return texto[:1].lower() + texto[1:] if texto[:2] != texto[:2].upper() else texto


def _corrigir_prazo(sugerido: str, data: str, calculado: str) -> str:
    """Prazo do Gemini só vale se for data válida, depois do dia da falha e em dia útil."""
    try:
        date.fromisoformat(sugerido)
    except ValueError:
        return calculado
    if sugerido <= data:
        return calculado
    return sugerido if eh_dia_util(sugerido) else proximo_dia_util(sugerido)


def gerar_comunicado(unidade: str, data: str, falha: str) -> Comunicado:
    eventos = servico.motor().eventos_do_dia(unidade, data)
    prazo = proximo_dia_util(proximo_dia_util(data))  # próximo dia útil + 1
    ia = servico.ia()
    if ia.disponivel:
        fatos = {
            "instituicao": contexto.instituicao(),
            "unidade": contexto.unidade(unidade).nome,
            "dia": data,
            "dia_semana": SEMANA[date.fromisoformat(data).weekday()],
            "falha_descrita_pela_operacao": falha,
            "eventos_do_dia": [
                {"descricao": e.descricao, "tipo": e.tipo, "hora_inicio": e.hora_inicio, "hora_fim": e.hora_fim}
                for e in eventos
            ],
            "nova_data_prazo": prazo,
            "REGRAS_POSSIVEIS": _regras(eventos, data, prazo),
        }
        resp = ia.gerar(
            "gerar_crise",
            "FATOS:\n" + json.dumps(fatos, ensure_ascii=False) + "\n\nEscreva o comunicado.",
            schema=ComunicadoIA,
            sistema=SISTEMA_CRISE,
            temperatura=0.2,
            detalhe="response_schema Comunicado · temperature 0.2",
        )
        if resp is not None and resp.objeto is not None:
            c: ComunicadoIA = resp.objeto
            regras = [r.strip() for r in c.regras_tolerancia if r.strip()][:6]
            if c.titulo.strip() and c.mensagem.strip() and regras:
                return Comunicado(
                    titulo=c.titulo.strip()[:120],
                    mensagem=c.mensagem.strip(),
                    nova_data_prazo=_corrigir_prazo(c.nova_data_prazo.strip(), data, prazo),
                    regras_tolerancia=regras,
                    origem="gemini",
                )
    ia.registrar("gerar_crise", f"comunicado de {dm(data)} por template (sem Gemini)", modelo="regras")
    return _template(unidade, data, falha, eventos, prazo)
