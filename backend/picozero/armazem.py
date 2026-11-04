# backend/picozero/armazem.py
# Persistência em SQLite (arquivo local; /tmp na Vercel). Escritas idempotentes:
# reenviar o mesmo arquivo ou o mesmo ponto não duplica nada (upsert por chave natural).
import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .dominio import Alerta, Evento, PontoMetrica, RegistroTrilha, RelatorioIngestao

ESQUEMA = """
CREATE TABLE IF NOT EXISTS metricas (
    unidade TEXT NOT NULL, metrica TEXT NOT NULL, ts TEXT NOT NULL,
    valor REAL NOT NULL, origem TEXT NOT NULL, fonte TEXT,
    PRIMARY KEY (unidade, metrica, ts)
);
CREATE TABLE IF NOT EXISTS eventos (
    id TEXT PRIMARY KEY, unidade TEXT NOT NULL, data TEXT NOT NULL,
    corpo TEXT NOT NULL, origem TEXT NOT NULL, criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_data ON eventos (unidade, data);
CREATE TABLE IF NOT EXISTS ingestoes (id TEXT PRIMARY KEY, quando TEXT NOT NULL, corpo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY, unidade TEXT NOT NULL, data TEXT NOT NULL, corpo TEXT NOT NULL,
    criado_em TEXT NOT NULL, reconhecido_em TEXT, notificado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trilha (seq INTEGER PRIMARY KEY AUTOINCREMENT, corpo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (chave TEXT PRIMARY KEY, valor TEXT NOT NULL, atualizado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversas (
    id TEXT PRIMARY KEY, titulo TEXT NOT NULL, unidade TEXT NOT NULL,
    criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL, corpo TEXT NOT NULL
);
"""


def _ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M")


def id_evento(unidade: str, ev: Evento) -> str:
    chave = f"{unidade}|{ev.data}|{ev.hora_inicio}|{ev.tipo}|{' '.join(ev.descricao.lower().split())}"
    return hashlib.sha1(chave.encode()).hexdigest()[:16]


class Armazem:
    def __init__(self, caminho: str):
        self.caminho = caminho
        self._trava = threading.RLock()
        self._con = sqlite3.connect(caminho, check_same_thread=False, isolation_level=None)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._con.executescript(ESQUEMA)
        # Versões dos dados: mudam a cada escrita e invalidam caches do motor.
        self.versao_metricas = 0
        self.versao_eventos = 0

    @property
    def versao(self) -> int:
        return self.versao_metricas + self.versao_eventos

    # ---------- utilidades ----------

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._trava:
            return self._con.execute(sql, tuple(params))

    def _consulta(self, sql: str, params: Iterable[Any] = ()) -> list[tuple]:
        with self._trava:
            return self._con.execute(sql, tuple(params)).fetchall()

    def vazio(self) -> bool:
        return not self._consulta("SELECT 1 FROM metricas LIMIT 1")

    def contagens(self) -> dict[str, int]:
        nomes = ("metricas", "eventos", "ingestoes", "alertas", "trilha")
        return {n: self._consulta(f"SELECT COUNT(*) FROM {n}")[0][0] for n in nomes}

    # ---------- métricas ----------

    def gravar_pontos(self, unidade: str, pontos: Iterable[PontoMetrica], origem: str, fonte: str | None = None) -> int:
        linhas = [(unidade, p.metrica, _ts(p.ts), float(p.valor), origem, fonte) for p in pontos]
        if not linhas:
            return 0
        with self._trava:
            self._con.execute("BEGIN")
            try:
                self._con.executemany(
                    "INSERT INTO metricas (unidade, metrica, ts, valor, origem, fonte) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT (unidade, metrica, ts) DO UPDATE SET valor=excluded.valor, origem=excluded.origem, "
                    "fonte=excluded.fonte",
                    linhas,
                )
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise
            self.versao_metricas += 1
        return len(linhas)

    def serie(self, unidade: str, inicio: str, fim: str, metrica: str = "carga") -> list[tuple[str, float, str]]:
        """Pontos com ts em [inicio, fim) — datas 'AAAA-MM-DD' ou ts 'AAAA-MM-DDTHH:MM'."""
        return self._consulta(
            "SELECT ts, valor, origem FROM metricas WHERE unidade=? AND metrica=? AND ts>=? AND ts<? ORDER BY ts",
            (unidade, metrica, inicio, fim),
        )

    def dias_com_dados(self, unidade: str, metrica: str = "carga") -> list[str]:
        rows = self._consulta(
            "SELECT DISTINCT substr(ts,1,10) FROM metricas WHERE unidade=? AND metrica=? ORDER BY 1", (unidade, metrica)
        )
        return [r[0] for r in rows]

    def fontes_metricas(self) -> list[dict[str, Any]]:
        rows = self._consulta(
            "SELECT unidade, origem, COALESCE(fonte,''), COUNT(*), MIN(ts), MAX(ts) FROM metricas "
            "GROUP BY unidade, origem, fonte ORDER BY unidade, origem"
        )
        return [
            {"unidade": u, "origem": o, "fonte": f or None, "pontos": n, "de": a, "ate": b} for u, o, f, n, a, b in rows
        ]

    def apagar_pontos(self, unidade: str, inicio: str, fim: str, origem: str | None = None) -> int:
        sql = "DELETE FROM metricas WHERE unidade=? AND ts>=? AND ts<?"
        params: list[Any] = [unidade, inicio, fim]
        if origem:
            sql += " AND origem=?"
            params.append(origem)
        n = self._exec(sql, params).rowcount
        self.versao_metricas += 1
        return n

    # ---------- eventos ----------

    def gravar_eventos(self, unidade: str, eventos: Iterable[Evento], origem: str) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        novos = 0
        with self._trava:
            for ev in eventos:
                cur = self._con.execute(
                    "INSERT OR IGNORE INTO eventos (id, unidade, data, corpo, origem, criado_em) VALUES (?,?,?,?,?,?)",
                    (id_evento(unidade, ev), unidade, ev.data, ev.model_dump_json(), origem, agora),
                )
                novos += cur.rowcount
            self.versao_eventos += 1
        return novos

    def eventos(self, unidade: str, inicio: str | None = None, fim: str | None = None) -> list[Evento]:
        sql = "SELECT corpo FROM eventos WHERE unidade=?"
        params: list[Any] = [unidade]
        if inicio:
            sql += " AND data>=?"
            params.append(inicio)
        if fim:
            sql += " AND data<=?"
            params.append(fim)
        sql += " ORDER BY data, corpo"
        evs = [Evento.model_validate_json(r[0]) for r in self._consulta(sql, params)]
        return sorted(evs, key=lambda e: (e.data, e.hora_inicio))

    def apagar_evento(self, unidade: str, ev: Evento) -> bool:
        n = self._exec("DELETE FROM eventos WHERE id=?", (id_evento(unidade, ev),)).rowcount
        self.versao_eventos += 1
        return n > 0

    # ---------- ingestões ----------

    def registrar_ingestao(self, rel: RelatorioIngestao) -> None:
        self._exec("INSERT OR REPLACE INTO ingestoes (id, quando, corpo) VALUES (?,?,?)", (rel.id, rel.quando, rel.model_dump_json()))

    def ingestoes(self, limite: int = 50) -> list[RelatorioIngestao]:
        rows = self._consulta("SELECT corpo FROM ingestoes ORDER BY quando DESC LIMIT ?", (limite,))
        return [RelatorioIngestao.model_validate_json(r[0]) for r in rows]

    # ---------- alertas ----------

    def salvar_alerta(self, a: Alerta) -> bool:
        """Grava ou atualiza; devolve True se o alerta é novo ou mudou de nível/pico."""
        with self._trava:
            antigo = self._con.execute("SELECT corpo, reconhecido_em FROM alertas WHERE id=?", (a.id,)).fetchone()
            if antigo:
                prev = Alerta.model_validate_json(antigo[0])
                a.criado_em = prev.criado_em
                a.reconhecido_em = antigo[1]
                mudou = (prev.nivel, prev.pico, prev.estagio) != (a.nivel, a.pico, a.estagio)
                self._con.execute("UPDATE alertas SET corpo=? WHERE id=?", (a.model_dump_json(), a.id))
                return mudou
            self._con.execute(
                "INSERT INTO alertas (id, unidade, data, corpo, criado_em) VALUES (?,?,?,?,?)",
                (a.id, a.unidade, a.data, a.model_dump_json(), a.criado_em),
            )
            return True

    def reconhecer_alerta(self, id_: str, quando: str) -> Alerta | None:
        with self._trava:
            row = self._con.execute("SELECT corpo FROM alertas WHERE id=?", (id_,)).fetchone()
            if not row:
                return None
            a = Alerta.model_validate_json(row[0])
            a.reconhecido_em = quando
            self._con.execute("UPDATE alertas SET corpo=?, reconhecido_em=? WHERE id=?", (a.model_dump_json(), quando, id_))
            return a

    def reconhecimentos(self, unidade: str) -> dict[str, str]:
        rows = self._consulta("SELECT id, reconhecido_em FROM alertas WHERE unidade=? AND reconhecido_em IS NOT NULL", (unidade,))
        return dict(rows)

    def marcar_notificado(self, id_: str) -> bool:
        """True só na primeira vez (o webhook de saída não repete o mesmo alerta)."""
        return self._exec("UPDATE alertas SET notificado=1 WHERE id=? AND notificado=0", (id_,)).rowcount > 0

    # ---------- trilha do Gemini ----------

    def registrar_trilha(self, r: RegistroTrilha) -> None:
        self._exec("INSERT INTO trilha (corpo) VALUES (?)", (r.model_dump_json(),))

    def trilha(self, limite: int = 120) -> list[RegistroTrilha]:
        rows = self._consulta("SELECT corpo FROM trilha ORDER BY seq DESC LIMIT ?", (limite,))
        return [RegistroTrilha.model_validate_json(r[0]) for r in reversed(rows)]

    # ---------- conversas do assistente (usuário global: o painel não tem login) ----------

    def salvar_conversa(self, id_: str, titulo: str, unidade: str, mensagens: list[dict]) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        self._exec(
            "INSERT INTO conversas (id, titulo, unidade, criada_em, atualizada_em, corpo) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT (id) DO UPDATE SET titulo=excluded.titulo, unidade=excluded.unidade, "
            "atualizada_em=excluded.atualizada_em, corpo=excluded.corpo",
            (id_, titulo, unidade, agora, agora, json.dumps(mensagens, ensure_ascii=False, default=str)),
        )

    def conversa(self, id_: str) -> dict | None:
        rows = self._consulta(
            "SELECT id, titulo, unidade, criada_em, atualizada_em, corpo FROM conversas WHERE id=?", (id_,)
        )
        if not rows:
            return None
        i, titulo, unidade, criada, atualizada, corpo = rows[0]
        return {"id": i, "titulo": titulo, "unidade": unidade, "criada_em": criada, "atualizada_em": atualizada,
                "mensagens": json.loads(corpo)}

    def conversas(self, limite: int = 50) -> list[dict]:
        rows = self._consulta(
            "SELECT id, titulo, unidade, criada_em, atualizada_em, json_array_length(corpo) FROM conversas "
            "ORDER BY atualizada_em DESC LIMIT ?",
            (limite,),
        )
        return [{"id": i, "titulo": t, "unidade": u, "criada_em": c, "atualizada_em": a, "mensagens": n}
                for i, t, u, c, a, n in rows]

    def apagar_conversa(self, id_: str) -> bool:
        return self._exec("DELETE FROM conversas WHERE id=?", (id_,)).rowcount > 0

    # ---------- chave/valor (resultados de IA, cache) ----------

    def kv_get(self, chave: str) -> Any | None:
        row = self._consulta("SELECT valor FROM kv WHERE chave=?", (chave,))
        return json.loads(row[0][0]) if row else None

    def kv_set(self, chave: str, valor: Any) -> None:
        self._exec(
            "INSERT INTO kv (chave, valor, atualizado_em) VALUES (?,?,?) "
            "ON CONFLICT (chave) DO UPDATE SET valor=excluded.valor, atualizado_em=excluded.atualizado_em",
            (chave, json.dumps(valor, ensure_ascii=False, default=str), datetime.now().isoformat(timespec="seconds")),
        )

    def kv_apagar_prefixo(self, prefixo: str) -> None:
        self._exec("DELETE FROM kv WHERE chave LIKE ?", (prefixo + "%",))
