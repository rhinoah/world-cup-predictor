#!/usr/bin/env python3
"""
teams.py
========
Padron UNICO de las 48 selecciones del Mundial 2026: nombre canonico, nombre en
castellano, sigla, bandera y grupo, todo en una sola fila por equipo.

Antes esto vivia en cinco estructuras paralelas repartidas en cuatro modulos
(`GROUPS` en groups.py, `FLAG_ISO` y `ABBR` en app_data.py, `ES` en prode_app.py
y `ALIAS` en build_horarios.py): sumar un equipo obligaba a editar las cinco y
era facil desincronizarlas sin que nada fallara hasta que la UI mostraba un
hueco.

El **nombre canonico** es el de martj42 (el dataset de resultados) y es la clave
de todo el proyecto. Los nombres que llegan de otras fuentes se normalizan con
`canonical()` antes de cruzar nada -- ver ALIASES.

Modulo hoja a proposito: no importa nada del proyecto (ni pandas ni la GUI), asi
que cualquiera puede importarlo sin arrastrar dependencias ni ciclos.
"""
from __future__ import annotations

from typing import NamedTuple


class Team(NamedTuple):
    """Una seleccion. `name` es la clave canonica (martj42)."""
    name: str     # nombre canonico, como viene en el dataset de resultados
    es: str       # nombre en castellano, para la UI
    abbr: str     # sigla de 3 letras, para el bracket (espacio chico)
    iso: str      # codigo de bandera (flagcdn / ISO 3166-1; casos UK aparte)
    group: str    # grupo A..L


TEAMS: list[Team] = [
    # --- Grupo A ---
    Team('Mexico'                , 'México'         , 'MEX', 'mx', 'A'),
    Team('South Africa'          , 'Sudáfrica'      , 'RSA', 'za', 'A'),
    Team('South Korea'           , 'Corea del Sur'  , 'KOR', 'kr', 'A'),
    Team('Czech Republic'        , 'Chequia'        , 'CZE', 'cz', 'A'),
    # --- Grupo B ---
    Team('Canada'                , 'Canadá'         , 'CAN', 'ca', 'B'),
    Team('Bosnia and Herzegovina', 'Bosnia'         , 'BIH', 'ba', 'B'),
    Team('Switzerland'           , 'Suiza'          , 'SUI', 'ch', 'B'),
    Team('Qatar'                 , 'Catar'          , 'QAT', 'qa', 'B'),
    # --- Grupo C ---
    Team('Brazil'                , 'Brasil'         , 'BRA', 'br', 'C'),
    Team('Morocco'               , 'Marruecos'      , 'MAR', 'ma', 'C'),
    Team('Scotland'              , 'Escocia'        , 'SCO', 'gb-sct', 'C'),
    Team('Haiti'                 , 'Haití'          , 'HAI', 'ht', 'C'),
    # --- Grupo D ---
    Team('United States'         , 'Estados Unidos' , 'USA', 'us', 'D'),
    Team('Paraguay'              , 'Paraguay'       , 'PAR', 'py', 'D'),
    Team('Turkey'                , 'Turquía'        , 'TUR', 'tr', 'D'),
    Team('Australia'             , 'Australia'      , 'AUS', 'au', 'D'),
    # --- Grupo E ---
    Team('Germany'               , 'Alemania'       , 'GER', 'de', 'E'),
    Team('Ivory Coast'           , 'Costa de Marfil', 'CIV', 'ci', 'E'),
    Team('Ecuador'               , 'Ecuador'        , 'ECU', 'ec', 'E'),
    Team('Curaçao'               , 'Curazao'        , 'CUW', 'cw', 'E'),
    # --- Grupo F ---
    Team('Netherlands'           , 'Países Bajos'   , 'NED', 'nl', 'F'),
    Team('Japan'                 , 'Japón'          , 'JPN', 'jp', 'F'),
    Team('Sweden'                , 'Suecia'         , 'SWE', 'se', 'F'),
    Team('Tunisia'               , 'Túnez'          , 'TUN', 'tn', 'F'),
    # --- Grupo G ---
    Team('Belgium'               , 'Bélgica'        , 'BEL', 'be', 'G'),
    Team('Egypt'                 , 'Egipto'         , 'EGY', 'eg', 'G'),
    Team('Iran'                  , 'Irán'           , 'IRN', 'ir', 'G'),
    Team('New Zealand'           , 'Nueva Zelanda'  , 'NZL', 'nz', 'G'),
    # --- Grupo H ---
    Team('Spain'                 , 'España'         , 'ESP', 'es', 'H'),
    Team('Uruguay'               , 'Uruguay'        , 'URU', 'uy', 'H'),
    Team('Saudi Arabia'          , 'Arabia Saudita' , 'KSA', 'sa', 'H'),
    Team('Cape Verde'            , 'Cabo Verde'     , 'CPV', 'cv', 'H'),
    # --- Grupo I ---
    Team('France'                , 'Francia'        , 'FRA', 'fr', 'I'),
    Team('Senegal'               , 'Senegal'        , 'SEN', 'sn', 'I'),
    Team('Norway'                , 'Noruega'        , 'NOR', 'no', 'I'),
    Team('Iraq'                  , 'Irak'           , 'IRQ', 'iq', 'I'),
    # --- Grupo J ---
    Team('Argentina'             , 'Argentina'      , 'ARG', 'ar', 'J'),
    Team('Algeria'               , 'Argelia'        , 'ALG', 'dz', 'J'),
    Team('Austria'               , 'Austria'        , 'AUT', 'at', 'J'),
    Team('Jordan'                , 'Jordania'       , 'JOR', 'jo', 'J'),
    # --- Grupo K ---
    Team('Portugal'              , 'Portugal'       , 'POR', 'pt', 'K'),
    Team('Colombia'              , 'Colombia'       , 'COL', 'co', 'K'),
    Team('Uzbekistan'            , 'Uzbekistán'     , 'UZB', 'uz', 'K'),
    Team('DR Congo'              , 'RD Congo'       , 'COD', 'cd', 'K'),
    # --- Grupo L ---
    Team('England'               , 'Inglaterra'     , 'ENG', 'gb-eng', 'L'),
    Team('Croatia'               , 'Croacia'        , 'CRO', 'hr', 'L'),
    Team('Ghana'                 , 'Ghana'          , 'GHA', 'gh', 'L'),
    Team('Panama'                , 'Panamá'         , 'PAN', 'pa', 'L'),
]

# Anfitriones: los unicos que juegan de local (el resto, siempre en sede neutral).
HOSTS = {'Canada', 'Mexico', 'United States'}

# Nombres de otras fuentes -> nombre canonico (martj42). Sumar aca cuando se
# integre una fuente nueva, no en el modulo que la consume.
ALIASES = {
    'USA': 'United States',
    'Czechia': 'Czech Republic',
    'Türkiye': 'Turkey',
    'Cabo Verde': 'Cape Verde',
}

# --- vistas derivadas (mismas claves que los dicts que reemplazan) ---
BY_NAME: dict[str, Team] = {t.name: t for t in TEAMS}
ES: dict[str, str] = {t.name: t.es for t in TEAMS}
ABBR: dict[str, str] = {t.name: t.abbr for t in TEAMS}
FLAG_ISO: dict[str, str] = {t.name: t.iso for t in TEAMS}

GROUPS: dict[str, list[str]] = {}
for _t in TEAMS:
    GROUPS.setdefault(_t.group, []).append(_t.name)
del _t


def canonical(name: str) -> str:
    """Nombre canonico de una seleccion venga de la fuente que venga."""
    n = (name or "").strip()
    return ALIASES.get(n, n)


def team_group(name: str) -> str | None:
    """Grupo (A..L) de una seleccion, o None si no juega el Mundial."""
    t = BY_NAME.get(canonical(name))
    return t.group if t else None


def es(name: str) -> str:
    """Nombre en castellano; si no esta en el padron, devuelve el original."""
    if not name:
        return ""
    return ES.get(name) or ES.get(canonical(name), name)


def abbr(name: str) -> str:
    """Sigla de 3 letras; cae al nombre en castellano si no esta."""
    if not name:
        return ""
    return ABBR.get(name) or ABBR.get(canonical(name)) or es(name)


if __name__ == "__main__":
    print(f"{len(TEAMS)} selecciones en {len(GROUPS)} grupos")
    for g, teams in GROUPS.items():
        print(f"  {g}: " + ", ".join(f"{ABBR[t]} ({ES[t]})" for t in teams))
