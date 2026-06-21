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
    ano_inicio_a: int
    ano_fim_a: int
    ano_inicio_b: int
    ano_fim_b: int
    deltas: list[DeltaIndicador]


class ValorIndicadorMandato(BaseModel):
    nome: str
    valor_inicio: float | None
    valor_fim: float | None
    variacao: float | None
    unidade: str
    fonte: str


class PayloadMandato(BaseModel):
    mandato: str
    ano_inicio: int
    ano_fim: int
    indicadores: list[ValorIndicadorMandato]
    faltantes: list[str]


class Afirmacao(BaseModel):
    texto: str
    valor_citado: float
    fonte: str


class ResumoFactual(BaseModel):
    paragrafos_por_eixo: dict[str, str]
    afirmacoes: list[Afirmacao]


class ResumoRegistro(BaseModel):
    id: int
    tipo: str
    identificador: str
    payload_hash: str
    resumo: ResumoFactual
    veredito: dict | None
    modelo: str
    criado_em: str


class Ministro(BaseModel):
    governo: str
    pasta: str
    nome: str
    inicio: datetime.date
    fim: datetime.date | None
    fonte: str


class Medida(BaseModel):
    id: int | None = None
    governo: str
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str
    status: str   # 'rascunho' | 'aprovada'
    origem: str   # 'curada' | 'ia'
    criado_em: str | None = None


class MedidaResumo(BaseModel):
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str


class PayloadMinisterialGoverno(BaseModel):
    governo: str
    ano_inicio: int
    ano_fim: int
    ministros: list[str]
    medidas: list[MedidaResumo]


class Lei(BaseModel):
    id: str
    tipo: str            # LO | LC | MP | EC
    numero: str
    ano: int
    data: datetime.date
    ementa: str
    url: str


class Veto(BaseModel):
    id: str
    data: datetime.date
    tipo: str            # total | parcial
    descricao: str
    materia: str
    url: str


class PayloadLegislativoMandato(BaseModel):
    mandato: str
    ano_inicio: int
    ano_fim: int
    total_leis: int
    por_tipo: dict[str, int]
    por_tema: dict[str, int]
    total_vetos: int
    vetos_por_tipo: dict[str, int]
