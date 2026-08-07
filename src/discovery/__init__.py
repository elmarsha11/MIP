"""
MIP - Fase 3: Descubrimiento de URLs oficiales por municipio.

Capas:
    Capa 1 - heuristics.py       : URLs probables a partir del nombre (0,5 s)
    Capa 2 - search_provider.py  : 8 queries de busqueda web (1,5 min)  [Ticket 2]
    Capa 3 - validator.py        : HTTP 200 + title match (30 s)        [Ticket 3]

Contratos: decisions/ADR-0009, decisions/ADR-0010, schemas/discovery_schema.md
"""

__version__ = "0.1.0"
