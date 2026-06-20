"""Pydantic DTOs shared across layers."""
from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel

Periodicidade = Literal["mensal", "trimestral", "anual", "diaria"]
Eixo = Literal["macro", "fiscal", "social"]
MetodoAnual = Literal["fim_periodo", "media", "acumulado_12m"]


class Observacao(BaseModel):
    serie_id: str
    data: datetime.date
    valor: float


class Indicador(BaseModel):
    id: str
    fonte: str
    codigo_fonte: str
    nome: str
    unidade: str
    periodicidade: Periodicidade
    eixo: Eixo
    metodo_anual: MetodoAnual


class Mandato(BaseModel):
    nome: str
    inicio: datetime.date
    fim: datetime.date


class ValorIndicador(BaseModel):
    nome: str
    valor: float | None
    unidade: str
    fonte: str
    data_ref: datetime.date | None


class PayloadAno(BaseModel):
    ano: int
    indicadores: list[ValorIndicador]
    faltantes: list[str]


class DeltaIndicador(BaseModel):
    nome: str
    valor_a: float | None
    valor_b: float | None
    delta: float | None
    unidade: str
    fonte: str


class PayloadComparacao(BaseModel):
    mandato_a: str
    mandato_b: str
    deltas: list[DeltaIndicador]


class Afirmacao(BaseModel):
    texto: str
    valor_citado: float
    fonte: str


class ResumoFactual(BaseModel):
    paragrafos_por_eixo: dict[str, str]
    afirmacoes: list[Afirmacao]
