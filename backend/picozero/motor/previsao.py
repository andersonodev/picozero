# backend/picozero/motor/previsao.py
# Previsão de carga = perfil orgânico aprendido do histórico (por tipo de dia)
#                   + Σ fator_aprendido[tipo] × forma do evento (carga.py)
#                   + ajuste ao vivo (nowcast) quando chegam métricas do próprio dia.
# A calibração é refeita quando o histórico muda; o backtest fora da amostra mede o erro.
import math
import statistics
import threading
from dataclasses import dataclass, field
from datetime import datetime

from .. import contexto
from ..armazem import Armazem
from ..dominio import ROTULO_NIVEL, CurvaDia, Evento, Janela, Pico, PontoCurva, ResumoDia
from . import carga

LIMIARES = (("critico", 1.0), ("serio", 0.8), ("alerta", 0.6))
LIMIAR_JANELA = 0.6  # janelas de pico = trechos acima de 60% da capacidade
FATOR_DIA_PADRAO = {"util": 1.0, "sexta": 0.9, "sabado": 0.5, "domingo": 0.4, "feriado": 0.4, "ferias": 0.35}
BANDA_PADRAO = {"normal": (0.85, 1.15), "evento": (0.8, 1.25)}
MIN_DIAS_PROPRIOS = 14  # abaixo disso a unidade usa a calibração da unidade de referência, escalada


def nivel_da_razao(r: float) -> str:
    for nome, limite in LIMIARES:
        if r >= limite:
            return nome
    return "ok"


def _resolver(a: list[list[float]], b: list[float]) -> list[float]:
    """Eliminação de Gauss com pivotamento parcial (sistema pequeno, 5×5)."""
    n = len(b)
    m = [linha[:] + [b[i]] for i, linha in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            continue
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 1.0 for i in range(n)]


def _quantis(valores: list[float], padrao: tuple[float, float]) -> tuple[float, float]:
    if len(valores) < 8:
        return padrao
    q = statistics.quantiles(valores, n=10)
    return (round(q[0], 3), round(q[-1], 3))


@dataclass
class Calibracao:
    unidade: str
    alunos: int
    perfis: dict[str, list[float]]
    fatores: dict[str, float]
    bandas: dict[str, tuple[float, float]]
    dias_usados: int
    dias_com_evento: int
    periodo: tuple[str, str] | None
    origem_dados: dict[str, int] = field(default_factory=dict)


class Motor:
    def __init__(self, armazem: Armazem):
        self.armazem = armazem
        self._trava = threading.RLock()
        self._cal: dict[str, Calibracao] = {}
        self._eventos: dict[str, tuple[int, dict[str, list[Evento]]]] = {}
        self._backtest: dict[str, dict] = {}

    # ---------- dados ----------

    def invalidar(self) -> None:
        with self._trava:
            self._cal.clear()
            self._backtest.clear()

    def _unidade_eventos(self, unidade: str) -> str:
        padrao = contexto.unidade_padrao().id
        if unidade == padrao:
            return padrao
        return unidade if self.armazem.eventos(unidade) else padrao

    def eventos_por_dia(self, unidade: str) -> dict[str, list[Evento]]:
        u = self._unidade_eventos(unidade)
        with self._trava:
            cache = self._eventos.get(u)
            if cache and cache[0] == self.armazem.versao_eventos:
                return cache[1]
            por_dia: dict[str, list[Evento]] = {}
            for ev in self.armazem.eventos(u):
                por_dia.setdefault(ev.data, []).append(ev)
            self._eventos[u] = (self.armazem.versao_eventos, por_dia)
            return por_dia

    def eventos_do_dia(self, unidade: str, iso: str) -> list[Evento]:
        return list(self.eventos_por_dia(unidade).get(iso, []))

    def _observado(self, unidade: str, inicio: str, fim: str) -> dict[str, dict[int, float]]:
        """{dia: {janela: valor}} a partir do armazém (fim exclusivo, 'AAAA-MM-DD')."""
        por_dia: dict[str, dict[int, float]] = {}
        for ts, valor, _origem in self.armazem.serie(unidade, inicio, fim):
            dia, hhmm = ts[:10], ts[11:16]
            por_dia.setdefault(dia, {})[carga.janela_da_hora(hhmm)] = valor
        return por_dia

    def unidade_de_calibracao(self, unidade: str) -> str:
        if unidade == contexto.unidade_padrao().id:
            return unidade
        proprios = len(self.armazem.dias_com_dados(unidade))
        return unidade if proprios >= MIN_DIAS_PROPRIOS else contexto.unidade_padrao().id

    # ---------- calibração ----------

    def calibracao(self, unidade: str) -> Calibracao:
        ref = self.unidade_de_calibracao(unidade)
        with self._trava:
            if ref not in self._cal:
                self._cal[ref] = self._calibrar(ref)
            return self._cal[ref]

    def _calibrar(self, ref: str, ate: str | None = None) -> Calibracao:
        """Aprende perfis por tipo de dia e a amplitude de cada tipo de evento (mínimos quadrados com prior 1)."""
        uni = contexto.unidade(ref)
        obs = self._observado(ref, "0000-00-00", ate or "9999-99-99")
        completos = {d: v for d, v in obs.items() if len(v) >= 88}
        evs = self.eventos_por_dia(ref)
        base_param = carga.curva_base(uni.alunos)

        # 1) Perfil orgânico: mediana por janela dos dias SEM evento, por tipo de dia.
        grupos: dict[str, list[dict[int, float]]] = {}
        for d, serie in completos.items():
            if not evs.get(d) and not contexto.periodo(d):
                grupos.setdefault(contexto.tipo_dia(d), []).append(serie)
        perfis: dict[str, list[float]] = {}
        for tipo, fator in FATOR_DIA_PADRAO.items():
            dias = grupos.get(tipo, [])
            if len(dias) >= 3:
                bruto = [statistics.median(s.get(i, base_param[i] * fator) for s in dias) for i in range(carga.JANELAS)]
                perfis[tipo] = [
                    (bruto[max(i - 1, 0)] + bruto[i] + bruto[min(i + 1, carga.JANELAS - 1)]) / 3
                    for i in range(carga.JANELAS)
                ]
            else:
                perfis[tipo] = [v * fator for v in base_param]

        # 2) Amplitudes por tipo de evento + efeito de período: (XᵀX + λI) k = Xᵀr + λ·prior.
        #    "periodo" = carga sustentada em semanas de rematrícula/provas (proporcional ao perfil orgânico);
        #    entrou depois do teste com a série pública do Domsilo (correlação mensal 0,73 → 0,88).
        tipos = (*carga.TIPOS_EVENTO, "periodo")
        prior = [1.0] * len(carga.TIPOS_EVENTO) + [0.0]
        n = len(tipos)
        xtx = [[0.0] * n for _ in range(n)]
        xtr = [0.0] * n
        dias_evento = 0
        for d, serie in completos.items():
            lista = evs.get(d, [])
            em_periodo = contexto.periodo(d) is not None
            if not lista and not em_periodo:
                continue
            dias_evento += 1
            comp = carga.componentes(lista, uni.alunos)
            perfil = perfis[contexto.tipo_dia(d)]
            comp["periodo"] = perfil if em_periodo else [0.0] * carga.JANELAS
            for i, v in serie.items():
                r = v - perfil[i]
                x = [comp[t][i] for t in tipos]
                for a in range(n):
                    if x[a]:
                        xtr[a] += x[a] * r
                        for b in range(n):
                            xtx[a][b] += x[a] * x[b]
        traco = sum(xtx[i][i] for i in range(n)) or 1.0
        lam = 0.02 * traco / n
        a = [[xtx[i][j] + (lam if i == j else 0.0) for j in range(n)] for i in range(n)]
        b = [xtr[i] + lam * prior[i] for i in range(n)]
        k = _resolver(a, b)
        fatores = {t: round(min(3.0, max(0.3, k[i])), 3) for i, t in enumerate(carga.TIPOS_EVENTO)}
        fatores["periodo"] = round(min(2.0, max(0.0, k[-1])), 3)

        # 3) Bandas: razão observado/previsto no pico de cada dia.
        razoes: dict[str, list[float]] = {"normal": [], "evento": []}
        for d, serie in completos.items():
            prev = self._prever_bruto(perfis, fatores, evs.get(d, []), d, uni.alunos)
            i_pico = max(range(carga.JANELAS), key=lambda i: prev[i])
            if prev[i_pico] > 0 and i_pico in serie:
                razoes["evento" if evs.get(d) else "normal"].append(serie[i_pico] / prev[i_pico])
        bandas = {c: _quantis(v, BANDA_PADRAO[c]) for c, v in razoes.items()}
        origem: dict[str, int] = {}
        for f in self.armazem.fontes_metricas():
            if f["unidade"] == ref:
                origem[f["origem"]] = origem.get(f["origem"], 0) + f["pontos"]
        periodo = (min(completos), max(completos)) if completos else None
        return Calibracao(ref, uni.alunos, perfis, fatores, bandas, len(completos), dias_evento, periodo, origem)

    @staticmethod
    def _prever_bruto(perfis, fatores, eventos, iso, alunos, opcoes=None) -> list[float]:
        perfil = perfis[contexto.tipo_dia(iso)]
        comp = carga.componentes(eventos, alunos, opcoes)
        sustentado = 1 + (fatores.get("periodo", 0.0) if contexto.periodo(iso) else 0.0)
        return [
            perfil[i] * sustentado + sum(fatores[t] * comp[t][i] for t in carga.TIPOS_EVENTO)
            for i in range(carga.JANELAS)
        ]

    # ---------- curva do dia ----------

    def curva(
        self,
        unidade: str,
        iso: str,
        *,
        agora: datetime | None = None,
        eventos: list[Evento] | None = None,
        opcoes: dict | None = None,
        observado: dict[int, float] | None = None,
        teto: int | None = None,
    ) -> CurvaDia:
        """Curva prevista do dia em 96 janelas. `eventos` substitui os do calendário (usado pelo
        validador de planos); `teto` limita a carga (fila virtual segura a concorrência)."""
        uni = contexto.unidade(unidade)
        cal = self.calibracao(unidade)
        escala = uni.alunos / cal.alunos
        evs = self.eventos_do_dia(unidade, iso) if eventos is None else eventos
        prev = self._prever_bruto(cal.perfis, cal.fatores, evs, iso, cal.alunos, opcoes)
        base = cal.perfis[contexto.tipo_dia(iso)]
        q10, q90 = cal.bandas["evento" if evs else "normal"]
        if observado is None:
            observado = self._observado(unidade, iso, iso + "~").get(iso, {})

        # Nowcast: se o dia está em curso e há métricas reais, corrige o resto do dia.
        ajuste = None
        observado_ate = None
        if agora is not None and agora.date().isoformat() == iso and observado:
            i_agora = (agora.hour * 60 + agora.minute) // 15
            passados = sorted(i for i in observado if i <= i_agora)
            if passados:
                ultimos = passados[-4:]
                soma_prev = sum(prev[i] * escala for i in ultimos)
                razao = sum(observado[i] for i in ultimos) / max(soma_prev, 1.0)
                peso = len(ultimos) / (len(ultimos) + 2)
                ajuste = min(3.0, max(0.4, 1 + peso * (razao - 1)))
                i_ult = passados[-1]
                observado_ate = carga.hora_da_janela(i_ult)
                for i in range(i_ult + 1, carga.JANELAS):
                    prev[i] *= 1 + (ajuste - 1) * math.exp(-(i - i_ult) / 24)

        pontos: list[PontoCurva] = []
        for i in range(carga.JANELAS):
            c = prev[i] * escala
            if teto is not None:
                c = min(c, teto)
            real = observado.get(i)
            pontos.append(
                PontoCurva(
                    hora=carga.hora_da_janela(i),
                    carga=round(c),
                    p10=round(c * q10),
                    p90=round(min(c * q90, teto) if teto is not None else c * q90),
                    real=round(real) if real is not None else None,
                    base=round(base[i] * escala),
                )
            )
        pico_pt = max(pontos, key=lambda p: p.carga)
        reais = [p for p in pontos if p.real is not None]
        pico_real = max(reais, key=lambda p: p.real) if reais else None
        cap = uni.capacidade
        razao = pico_pt.carga / cap
        nivel = nivel_da_razao(razao)
        return CurvaDia(
            data=iso,
            unidade=uni.id,
            capacidade=cap,
            pontos=pontos,
            pico=Pico(hora=pico_pt.hora, carga=pico_pt.carga),
            pico_real=Pico(hora=pico_real.hora, carga=pico_real.real) if pico_real else None,
            janelas=janelas(pontos, cap),
            nivel=nivel,
            rotulo=ROTULO_NIVEL[nivel],
            razao=round(razao, 2),
            eventos=evs,
            feriado=contexto.feriado(iso),
            periodo=(p.nome if (p := contexto.periodo(iso)) else None),
            tipo_dia=contexto.tipo_dia(iso),
            fatores=cal.fatores,
            observado_ate=observado_ate,
            ajuste_ao_vivo=round(ajuste, 3) if ajuste is not None else None,
            plano_aplicado=bool(opcoes) or teto is not None,
        )

    def resumo(self, unidade: str, inicio: str, fim: str, agora: datetime | None = None) -> list[ResumoDia]:
        obs = self._observado(unidade, inicio, fim + "~")
        saida = []
        for iso in contexto.dias(inicio, fim):
            c = self.curva(unidade, iso, agora=agora, observado=obs.get(iso, {}))
            p90 = max(p.p90 or p.carga for p in c.pontos)
            saida.append(
                ResumoDia(
                    data=iso,
                    pico=c.pico.carga,
                    hora=c.pico.hora,
                    p90=p90,
                    nivel=c.nivel,
                    razao=c.razao,
                    eventos=[e.descricao for e in c.eventos],
                    feriado=c.feriado,
                    real=c.pico_real.carga if c.pico_real else None,
                )
            )
        return saida

    # ---------- validação fora da amostra ----------

    def backtest(self, unidade: str | None = None) -> dict:
        """Calibra só com o que veio ANTES do semestre atual e mede o erro nos dias já ocorridos dele."""
        ref = self.unidade_de_calibracao(unidade or contexto.unidade_padrao().id)
        with self._trava:
            if ref in self._backtest:
                return self._backtest[ref]
        sem = contexto.semestre()
        hoje = contexto.agora().date().isoformat()
        treino = self._calibrar(ref, ate=sem["inicio"])
        uni = contexto.unidade(ref)
        obs = self._observado(ref, sem["inicio"], hoje)
        evs = self.eventos_por_dia(ref)
        erros, abs_err, desloc = [], [], []
        vp = fp = fn = 0
        for d, serie in sorted(obs.items()):
            if len(serie) < 88:
                continue
            prev = self._prever_bruto(treino.perfis, treino.fatores, evs.get(d, []), d, uni.alunos)
            ip = max(range(carga.JANELAS), key=lambda i: prev[i])
            io = max(serie, key=lambda i: serie[i])
            po, pp = serie[io], prev[ip]
            erros.append(abs(pp - po) / max(po, 1))
            abs_err.append(abs(pp - po))
            desloc.append(abs(ip - io) * 15)
            prev_crit, obs_crit = pp >= uni.capacidade, po >= uni.capacidade
            vp += prev_crit and obs_crit
            fp += prev_crit and not obs_crit
            fn += obs_crit and not prev_crit
        res = {
            "unidade": ref,
            "treino_ate": sem["inicio"],
            "avaliado": [sem["inicio"], hoje],
            "dias_avaliados": len(erros),
            "mape_pico": round(statistics.mean(erros) * 100, 1) if erros else None,
            "erro_medio_pico": round(statistics.mean(abs_err)) if abs_err else None,
            "erro_mediano_hora_min": statistics.median(desloc) if desloc else None,
            "dias_criticos": {"acertos": vp, "falsos_alarmes": fp, "perdidos": fn},
            "fatores_treino": treino.fatores,
            "observacao": "histórico modelado (seed fixa) até ter o export real; mesma conta roda no dado real",
        }
        with self._trava:
            self._backtest[ref] = res
        return res


def janelas(pontos: list[PontoCurva], capacidade: int, limiar: float = LIMIAR_JANELA) -> list[Janela]:
    """Trechos contíguos acima de limiar × capacidade, com o nível do pior ponto."""
    saida: list[Janela] = []
    atual: list[PontoCurva] = []
    for p in pontos + [None]:
        if p is not None and p.carga >= limiar * capacidade:
            atual.append(p)
            continue
        if atual:
            topo = max(atual, key=lambda x: x.carga)
            fim_min = carga.minutos(atual[-1].hora) + 15
            fim = "23:59" if fim_min >= 24 * 60 else f"{fim_min // 60:02d}:{fim_min % 60:02d}"
            saida.append(
                Janela(
                    inicio=atual[0].hora,
                    fim=fim,
                    max=topo.carga,
                    hora_max=topo.hora,
                    nivel=nivel_da_razao(topo.carga / capacidade),
                )
            )
            atual = []
    return saida
