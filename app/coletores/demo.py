"""Dados fictícios para testar a interface sem acessar a internet."""
from __future__ import annotations

from datetime import date, timedelta

from .base import Coletor, Edital


class ColetorDemo(Coletor):
    def coletar(self) -> list[Edital]:
        hoje = date.today()
        return [
            Edital(
                fonte=self.nome,
                id_externo="demo-1",
                titulo="[EXEMPLO] Credenciamento de pessoas jurídicas para consultoria em gestão",
                objeto="Cadastro de consultores para atendimento às unidades do SENAI em Minas Gerais",
                unidade="SENAI/DRMG - SEDE",
                tipo="Chamamento público",
                url="https://example.com/demo-1",
                prazo=hoje + timedelta(days=2),
            ),
            Edital(
                fonte=self.nome,
                id_externo="demo-2",
                titulo="[EXEMPLO] Chamamento público para instrutoria em segurança do trabalho",
                objeto="Instrutoria para cursos de NR-10 e NR-35",
                unidade="SENAI/DRMG - CFP AFONSO GRECO",
                tipo="Chamamento público",
                url="https://example.com/demo-2",
                prazo=hoje + timedelta(days=21),
            ),
            Edital(
                fonte=self.nome,
                id_externo="demo-3",
                titulo="[EXEMPLO] Aquisição de equipamentos de informática",
                objeto="Registro de preços de notebooks",
                unidade="SESI/DRMG - SEDE",
                tipo="Pregão eletrônico",
                url="https://example.com/demo-3",
                prazo=hoje + timedelta(days=9),
            ),
        ]
