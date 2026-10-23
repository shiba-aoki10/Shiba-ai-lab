"""Construtores de objetos fictícios para os testes."""
from shiba.config import Cliente, Fato, Limite, Plataforma


def cliente(minimo=3, maximo=5, hashtags_proibidas=("sigam",), palavras=("garantido",)):
    return Cliente(
        id="teste", nome="Cliente Teste (fictício)", ficticio=True,
        hashtags_minimo=minimo, hashtags_maximo=maximo,
        hashtags_proibidas=tuple(hashtags_proibidas), palavras_proibidas=tuple(palavras),
    )


def plataforma(valor=100, status="a_verificar"):
    fonte, data = ("https://exemplo.invalid/doc", "2026-10-23") if status == "verificado" else ("", "")
    return Plataforma("teste", "Plataforma Teste", Limite(valor, status, fonte, data))


def fato(id="F-1", valores=("2015",), status="verificado"):
    return Fato(id=id, texto="fato fictício", valores=tuple(valores), status=status)
