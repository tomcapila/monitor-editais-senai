"""
Progresso e tempo limite das tarefas longas (coleta e diagnóstico).

O tempo limite é cooperativo: não dá para matar uma thread em Python, então
cada etapa chama verificar() e as operações de rede recebem restante_ms()
como timeout. Assim nenhuma espera passa do limite total.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime


class TempoEsgotado(Exception):
    pass


class Progresso:
    def __init__(self):
        self._lock = threading.Lock()
        self._rodando = False
        self._inicio = 0.0
        self._limite: float | None = None
        self._dados: dict = {}

    def iniciar(self, limite_segundos: float | None, total_fases: int = 1):
        with self._lock:
            self._rodando = True
            self._inicio = time.monotonic()
            self._limite = limite_segundos
            self._dados = {
                "inicio": datetime.now().isoformat(timespec="seconds"),
                "etapa": "Iniciando", "detalhe": "",
                "fase": 0, "total_fases": max(total_fases, 1),
                "atual": 0, "total": 0,
            }

    def fase(self, texto: str, indice: int, total_fases: int | None = None):
        """Início de uma fase (0-based). Zera o subprogresso."""
        self.verificar()
        with self._lock:
            self._dados.update(etapa=texto, detalhe="", fase=indice, atual=0, total=0)
            if total_fases:
                self._dados["total_fases"] = total_fases

    def passo(self, detalhe: str, atual: int = 0, total: int = 0):
        """Subprogresso dentro da fase atual (ex.: página 2 de 4)."""
        self.verificar()
        with self._lock:
            self._dados.update(detalhe=detalhe, atual=atual, total=total)

    def sem_limite(self):
        """Desliga o tempo limite (ex.: enquanto espera o usuário no terminal)."""
        with self._lock:
            self._limite = None

    def finalizar(self):
        with self._lock:
            self._rodando = False

    @property
    def rodando(self) -> bool:
        return self._rodando

    def decorrido(self) -> float:
        return time.monotonic() - self._inicio if self._rodando else 0.0

    def verificar(self):
        if self._rodando and self._limite is not None and self.decorrido() > self._limite:
            raise TempoEsgotado(
                f"Tempo limite de {self._limite:.0f} s esgotado durante: "
                f"{self._dados.get('etapa', '')}"
                + (f" ({self._dados['detalhe']})" if self._dados.get("detalhe") else "")
            )

    def restante_ms(self, maximo_ms: float) -> float:
        """Timeout para uma operação: o menor entre o seu máximo e o que resta do limite."""
        self.verificar()
        if not self._rodando or self._limite is None:
            return maximo_ms
        resta = (self._limite - self.decorrido()) * 1000
        return max(1000, min(maximo_ms, resta))

    def estado(self) -> dict:
        with self._lock:
            if not self._rodando:
                return {"rodando": False}
            d = dict(self._dados)
        sub = d["atual"] / d["total"] if d["total"] else 0
        d["percentual"] = round(min(100, (d["fase"] + sub) / d["total_fases"] * 100))
        d["decorrido_s"] = round(self.decorrido())
        d["limite_s"] = self._limite
        d["rodando"] = True
        return d
