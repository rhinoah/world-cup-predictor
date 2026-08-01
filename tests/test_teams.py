"""Tests de teams.py: invariantes del padron unico de las 48 selecciones.

teams.py nacio de fusionar cuatro estructuras paralelas (GROUPS, FLAG_ISO, ABBR,
ES) en una sola fila por equipo. Eso mata la clase de bug "desincronizadas",
pero NO las que siguen siendo posibles con una unica fuente:

  * una fila con un campo vacio o una sigla repetida,
  * un ALIAS que apunta a un nombre inexistente (rompe joins EN SILENCIO),
  * un TYPO en un nombre canonico -- el mas peligroso: la fila queda coherente
    consigo misma y ningun invariante interno lo nota, pero el equipo desaparece
    de todo cruce contra martj42. Se ataja contra un testigo EXTERNO (ver (n)),
  * y que el modulo deje de ser hoja (si alguien le mete un import del proyecto
    vuelven los ciclos y build_flags.py se come pandas de nuevo).

`teams` es un modulo hoja: se importa directo, sin la fixture `project` (esa es
para los tests que tocan disco).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import teams
from teams import (ABBR, ALIASES, BY_NAME, ES, FLAG_ISO, GROUPS, HOSTS, TEAMS,
                   abbr, canonical, es, team_group)

GROUP_KEYS = list("ABCDEFGHIJKL")
IDS = [t.name for t in TEAMS]            # ids legibles en la salida de pytest
ALIAS_ITEMS = sorted(ALIASES.items())


# --------------------------------------------------------------------------
# (a) el padron: 48 filas, sin repetidos, sin campos vacios
# --------------------------------------------------------------------------
def test_el_padron_tiene_48_selecciones():
    assert len(TEAMS) == 48


def test_los_nombres_canonicos_no_se_repiten():
    """Un nombre duplicado se comeria una fila entera en todas las vistas dict."""
    nombres = [t.name for t in TEAMS]
    assert len(set(nombres)) == 48, "hay nombres canonicos duplicados en TEAMS"


@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_ninguna_fila_tiene_campos_vacios(t):
    """Un campo vacio no explota: aparece como hueco mudo en la UI o el bracket."""
    for campo, valor in t._asdict().items():
        assert isinstance(valor, str), f"{t.name}.{campo} no es str"
        assert valor.strip(), f"{t.name}.{campo} esta vacio"


@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_ningun_campo_tiene_espacios_al_borde(t):
    """El nombre canonico es clave de join contra martj42: un espacio de mas no matchea."""
    for campo, valor in t._asdict().items():
        assert valor == valor.strip(), f"{t.name}.{campo} tiene espacios de sobra"


# --------------------------------------------------------------------------
# (b) grupos: 12 de 4, claves A..L, y el orden de declaracion importa
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_el_grupo_de_cada_fila_es_una_letra_valida(t):
    assert t.group in GROUP_KEYS, f"{t.name} tiene grupo {t.group!r}"


def test_groups_tiene_12_grupos_con_llaves_A_a_L_en_orden():
    """GROUPS se arma con setdefault: el orden de las llaves sale de TEAMS."""
    assert list(GROUPS) == GROUP_KEYS


def test_groups_tiene_4_equipos_por_grupo():
    for g, nombres in GROUPS.items():
        assert len(nombres) == 4, f"grupo {g} no tiene 4 equipos"


def test_groups_cubre_a_los_48_sin_repetir():
    todos = [n for nombres in GROUPS.values() for n in nombres]
    assert len(todos) == 48
    assert len(set(todos)) == 48, "hay selecciones duplicadas entre grupos"
    assert set(todos) == set(BY_NAME)


def test_groups_respeta_el_orden_de_declaracion_de_teams():
    """La vista GROUPS conserva el orden en que se declararon las filas."""
    for g in GROUP_KEYS:
        assert GROUPS[g] == [t.name for t in TEAMS if t.group == g]


def test_teams_esta_declarado_en_bloques_de_grupo_contiguos():
    """El orden es el del sorteo (cabeza de serie primero). Produccion no depende
    de el -- quien clasifica sale de la tabla de posiciones, no del indice -- pero
    fijarlo obliga a que un reordenamiento sea un cambio explicito y no un
    resultado colateral de editar una fila."""
    assert [t.group for t in TEAMS] == [g for g in GROUP_KEYS for _ in range(4)]


# --------------------------------------------------------------------------
# (c) siglas: 3 mayusculas y unicas entre las 48
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_la_sigla_es_de_tres_mayusculas(t):
    """El bracket dibuja siglas en cajas fijas: 2 o 4 caracteres desalinean todo."""
    assert len(t.abbr) == 3, f"{t.name}: sigla {t.abbr!r}"
    assert t.abbr.isascii() and t.abbr.isalpha(), f"{t.name}: sigla {t.abbr!r}"
    assert t.abbr == t.abbr.upper(), f"{t.name}: sigla {t.abbr!r} no esta en mayusculas"


def test_las_siglas_no_se_repiten():
    """Dos equipos con la misma sigla son indistinguibles en el bracket."""
    siglas = [t.abbr for t in TEAMS]
    assert len(set(siglas)) == 48, "hay siglas repetidas en el padron"


# --------------------------------------------------------------------------
# (d) banderas: iso en minusculas, con los casos UK aparte
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_el_iso_esta_en_minusculas(t):
    """build_flags.py arma la URL de flagcdn tal cual: en mayusculas da 404."""
    assert t.iso == t.iso.lower(), f"{t.name}: iso {t.iso!r}"
    assert t.iso.isascii(), f"{t.name}: iso {t.iso!r}"


@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_el_iso_tiene_forma_de_codigo_de_bandera(t):
    """O ISO 3166-1 de dos letras, o subdivision tipo 'gb-sct'."""
    partes = t.iso.split("-")
    assert len(partes) in (1, 2), f"{t.name}: iso {t.iso!r}"
    assert len(partes[0]) == 2 and partes[0].isalpha(), f"{t.name}: iso {t.iso!r}"
    if len(partes) == 2:
        assert 2 <= len(partes[1]) <= 3 and partes[1].isalpha(), f"{t.name}: iso {t.iso!r}"


@pytest.mark.parametrize("team,iso", [("Scotland", "gb-sct"), ("England", "gb-eng")])
def test_las_britanicas_usan_el_iso_de_subdivision(team, iso):
    """Escocia e Inglaterra no tienen ISO propio: con 'gb' saldria la Union Jack en las dos."""
    assert BY_NAME[team].iso == iso
    assert FLAG_ISO[team] == iso


def test_los_iso_no_se_repiten():
    """Dos selecciones con la misma bandera es un typo, no un caso real."""
    isos = [t.iso for t in TEAMS]
    assert len(set(isos)) == 48, "hay codigos de bandera repetidos en el padron"


# --------------------------------------------------------------------------
# (e) nombres en castellano
# --------------------------------------------------------------------------
def test_los_nombres_en_castellano_no_se_repiten():
    """Dos equipos con el mismo texto en pantalla es un bug de UI imposible de leer."""
    nombres = [t.es for t in TEAMS]
    assert len(set(nombres)) == 48, "hay nombres en castellano duplicados"


# --------------------------------------------------------------------------
# (f) ALIASES: el test mas valioso del archivo
# --------------------------------------------------------------------------
@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_cada_alias_apunta_a_un_equipo_del_padron(alias, canon):
    """Un typo en el valor ('Cape Verd') no falla: canonical() devuelve el typo,
    el join contra martj42 no matchea y el equipo desaparece sin ruido."""
    assert canon in BY_NAME, f"el alias {alias!r} apunta a {canon!r}, que no existe"


def test_ningun_alias_pisa_un_nombre_canonico():
    """Si una clave de ALIASES fuera un nombre real, canonical() lo renombraria."""
    assert set(ALIASES) & set(BY_NAME) == set()


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_las_claves_de_alias_no_tienen_espacios_al_borde(alias, canon):
    """canonical() hace strip ANTES de buscar: una clave con espacios nunca matchea."""
    assert alias == alias.strip(), f"clave de alias {alias!r} con espacios"


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_canonical_es_idempotente_sobre_los_alias(alias, canon):
    """Aplicar canonical() dos veces tiene que dar lo mismo (no hay cadenas de alias)."""
    assert canonical(canonical(alias)) == canonical(alias) == canon


# --------------------------------------------------------------------------
# (g) HOSTS
# --------------------------------------------------------------------------
def test_hosts_son_los_tres_organizadores():
    assert HOSTS == {"Canada", "Mexico", "United States"}


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_cada_host_existe_en_el_padron(host):
    """El feature de localia se decide por pertenencia a HOSTS: un typo lo apaga."""
    assert host in BY_NAME


# --------------------------------------------------------------------------
# (h) vistas derivadas: mismas claves que TEAMS y mismos valores que la fila
# --------------------------------------------------------------------------
@pytest.mark.parametrize("vista,nombre", [
    (BY_NAME, "BY_NAME"), (ES, "ES"), (ABBR, "ABBR"), (FLAG_ISO, "FLAG_ISO"),
])
def test_las_vistas_derivadas_tienen_las_48_claves(vista, nombre):
    assert len(vista) == 48, f"{nombre} no tiene 48 entradas"
    assert set(vista) == {t.name for t in TEAMS}, f"{nombre} no cubre exactamente el padron"


@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_cada_vista_derivada_coincide_con_su_fila(t):
    assert BY_NAME[t.name] is t
    assert ES[t.name] == t.es
    assert ABBR[t.name] == t.abbr
    assert FLAG_ISO[t.name] == t.iso


@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_groups_ubica_a_cada_equipo_en_su_grupo(t):
    assert t.name in GROUPS[t.group]


# --------------------------------------------------------------------------
# (i) canonical()
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_canonical_deja_pasar_los_nombres_del_padron(t):
    assert canonical(t.name) == t.name


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_canonical_traduce_los_alias(alias, canon):
    assert canonical(alias) == canon


@pytest.mark.parametrize("crudo,esperado", [
    ("  Argentina", "Argentina"),
    ("Argentina  ", "Argentina"),
    (" USA ", "United States"),      # strip primero, alias despues
    ("\tCzechia\n", "Czech Republic"),
])
def test_canonical_recorta_espacios_antes_de_buscar(crudo, esperado):
    """Los nombres que llegan de scraping vienen con espacios pegados."""
    assert canonical(crudo) == esperado


@pytest.mark.parametrize("desconocido", ["Italy", "MEX", "united states", "México"])
def test_canonical_devuelve_el_original_si_no_lo_conoce(desconocido):
    """No inventa: si no hay alias, pasa el nombre tal cual (case sensitive)."""
    assert canonical(desconocido) == desconocido


@pytest.mark.parametrize("vacio", ["", "   ", None])
def test_canonical_tolera_vacio_y_none(vacio):
    assert canonical(vacio) == ""


# --------------------------------------------------------------------------
# (j) team_group()
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_team_group_coincide_con_la_fila(t):
    assert team_group(t.name) == t.group


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_team_group_acepta_alias(alias, canon):
    """El fixture de horarios trae 'USA'/'Czechia': tienen que caer en su grupo."""
    assert team_group(alias) == BY_NAME[canon].group


@pytest.mark.parametrize("desconocido", ["Italy", "", "   ", "MEX", "curaçao", None])
def test_team_group_devuelve_none_para_desconocidos(desconocido):
    assert team_group(desconocido) is None


# --------------------------------------------------------------------------
# (k) es()
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_es_traduce_a_los_48(t):
    assert es(t.name) == t.es


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_es_acepta_alias(alias, canon):
    assert es(alias) == BY_NAME[canon].es


def test_es_recorta_espacios():
    assert es("  Argentina ") == "Argentina"


@pytest.mark.parametrize("desconocido", ["Italy", "MEX"])
def test_es_devuelve_el_original_si_no_lo_conoce(desconocido):
    """La UI prefiere mostrar el nombre crudo antes que un hueco vacio."""
    assert es(desconocido) == desconocido


@pytest.mark.parametrize("vacio", ["", None])
def test_es_devuelve_string_vacio_para_vacio_y_none(vacio):
    """Los labels de la app concatenan el resultado: None romperia el render."""
    assert es(vacio) == ""


# --------------------------------------------------------------------------
# (l) abbr()
# --------------------------------------------------------------------------
@pytest.mark.parametrize("t", TEAMS, ids=IDS)
def test_abbr_devuelve_la_sigla_de_los_48(t):
    assert abbr(t.name) == t.abbr


@pytest.mark.parametrize("alias,canon", ALIAS_ITEMS)
def test_abbr_acepta_alias(alias, canon):
    assert abbr(alias) == BY_NAME[canon].abbr


def test_abbr_recorta_espacios():
    assert abbr(" Czechia ") == "CZE"


@pytest.mark.parametrize("desconocido", ["Italy", "MEX"])
def test_abbr_cae_a_es_si_no_conoce_al_equipo(desconocido):
    """Fallback documentado: sin sigla usa es(), que para un desconocido es el
    nombre original (mejor un texto largo en el bracket que un vacio)."""
    assert abbr(desconocido) == es(desconocido) == desconocido


@pytest.mark.parametrize("vacio", ["", None])
def test_abbr_devuelve_string_vacio_para_vacio_y_none(vacio):
    assert abbr(vacio) == ""


# --------------------------------------------------------------------------
# (m) modulo hoja: teams.py no puede importar nada del proyecto
# --------------------------------------------------------------------------
MODULE_PATH = Path(teams.__file__).resolve()
REPO = MODULE_PATH.parent
PROJECT_MODULES = {p.stem for p in REPO.glob("*.py")} - {"teams"}
STDLIB_PERMITIDA = {"__future__", "typing"}


def _imports_de_teams() -> set[str]:
    """Modulos top-level que importa teams.py, leidos del AST (sin ejecutarlo)."""
    arbol = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            mods |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:                      # import relativo
                mods.add("." * nodo.level + (nodo.module or ""))
            else:
                mods.add((nodo.module or "").split(".")[0])
    return mods


def test_teams_no_importa_ningun_modulo_del_proyecto():
    """Es hoja a proposito: build_flags.py lo importa para NO cargar pandas, y
    si teams.py importara app_data/groups volverian los ciclos de import."""
    intrusos = _imports_de_teams() & PROJECT_MODULES
    assert intrusos == set(), f"teams.py importa modulos del proyecto: {sorted(intrusos)}"


def test_teams_solo_importa_la_stdlib_minima():
    """Tampoco terceros (pandas/numpy): importarlo tiene que ser instantaneo."""
    assert _imports_de_teams() <= STDLIB_PERMITIDA


def test_el_test_de_modulo_hoja_esta_mirando_el_repo_de_verdad():
    """Si PROJECT_MODULES quedara vacio, el test de arriba pasaria siempre."""
    assert {"app_data", "groups", "prode_app"} <= PROJECT_MODULES


def test_teams_no_deja_la_variable_del_loop_en_el_namespace():
    """El `for _t in TEAMS` que arma GROUPS hace `del _t`: sin eso queda basura
    exportada y un `from teams import *` la arrastra."""
    assert not hasattr(teams, "_t")


# --------------------------------------------------------------------------
# (n) el padron contra un TESTIGO EXTERNO
# --------------------------------------------------------------------------
# Todo lo de arriba mira a teams.py contra si mismo, asi que un TYPO en un nombre
# canonico (fila coherente, solo el nombre mal escrito) pasa limpio: se probo
# inyectando 'Ghana' -> 'Gana' y la suite entera quedo en verde. Antes del padron
# unico ese typo rompia 4 asserts, porque el equipo faltaba en ABBR y FLAG_ISO.
#
# El testigo es `build_horarios.RAW`: el fixture crudo de worldcuppass, 72 lineas
# "fecha|local|visitante|hora" escritas a mano desde OTRA fuente y que no derivan
# de teams.py. Se lee del AST para no importar pandas.
HORARIOS_PATH = REPO / "build_horarios.py"


def _fixture_de_grupos() -> list[tuple[str, str]]:
    """Los 72 partidos de fase de grupos, ya normalizados a nombres canonicos."""
    arbol = ast.parse(HORARIOS_PATH.read_text(encoding="utf-8"))
    crudo = next(
        ast.literal_eval(n.value)
        for n in arbol.body
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", None) == "RAW" for t in n.targets)
    )
    partidos = []
    for linea in crudo.strip().splitlines():
        _, local, visita, _ = [x.strip() for x in linea.split("|")]
        partidos.append((canonical(local), canonical(visita)))
    return partidos


def test_el_testigo_externo_tiene_los_72_partidos_de_grupos():
    """Meta-test: si RAW dejara de parsearse, los dos de abajo pasarian vacios."""
    assert len(_fixture_de_grupos()) == 72


def test_los_equipos_del_fixture_son_exactamente_los_del_padron():
    """Ataja el typo en un nombre canonico. Los nombres de RAW vienen de otra
    fuente: si el padron escribe 'Gana', deja de matchear y salta aca."""
    del_fixture = {t for par in _fixture_de_grupos() for t in par}
    faltan = set(BY_NAME) - del_fixture
    sobran = del_fixture - set(BY_NAME)
    assert not faltan, f"en el padron pero no juegan: {sorted(faltan)}"
    assert not sobran, f"juegan pero no estan en el padron: {sorted(sobran)}"


def test_los_grupos_coinciden_con_quien_juega_contra_quien():
    """En la fase de grupos cada equipo enfrenta a los otros 3 de SU grupo y a
    nadie mas: eso reconstruye los 12 grupos sin mirar el campo `group`."""
    rivales: dict[str, set[str]] = {n: set() for n in BY_NAME}
    for local, visita in _fixture_de_grupos():
        rivales[local].add(visita)
        rivales[visita].add(local)
    for equipo, rr in rivales.items():
        esperado = set(GROUPS[BY_NAME[equipo].group]) - {equipo}
        assert rr == esperado, f"{equipo} juega contra {sorted(rr)}, no {sorted(esperado)}"
