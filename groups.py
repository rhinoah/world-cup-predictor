#!/usr/bin/env python3
"""
groups.py
=========
Estructura de la fase de grupos del Mundial 2026 (12 grupos de 4), tablas de
posiciones y clasificados a la fase de eliminacion segun el formato 2026:
los 2 primeros de cada grupo + los 8 mejores terceros -> Round of 32.

Desempate (FIFA 2026): puntos -> diferencia de gol -> goles a favor (los
criterios siguientes -conducta, ranking- no se modelan aca).

Solo cuentan los partidos TERMINADOS (los que traen `state == "done"`).

Este modulo es COMPUTO PURO: recibe la lista de partidos y devuelve tablas, sin
leer nada de disco. Antes importaba `app_data` para dos cosas -- resolver el
fixture por defecto y preguntar si un partido habia terminado -- y eso cerraba
un ciclo de imports (app_data -> groups -> app_data) que habia que parchear con
imports perezosos adentro de las funciones. Hoy el estado del partido viaja en
el propio dict, asi que la dependencia desaparecio y la direccion quedo en un
solo sentido: la capa de datos arma los partidos, este modulo los cuenta.
"""
from __future__ import annotations

from teams import GROUPS, team_group  # noqa: F401  (padron unico; se re-exportan)

# GROUPS (12 grupos x 4) y team_group() salen de teams.py, el padron unico de las
# 48 selecciones; se re-exportan aca porque este es el modulo de la fase de grupos.


def standings(fx):
    """Tabla de cada grupo (lista ordenada de dicts) con los partidos terminados.

    `fx` son los partidos tal como los arma `app_data.fixture()`."""
    rows = {t: dict(team=t, pj=0, g=0, e=0, p=0, gf=0, gc=0, dg=0, pts=0)
            for teams in GROUPS.values() for t in teams}
    games = []   # partidos jugados, para el desempate por enfrentamiento directo
    for m in fx:
        if m["real"] is None or m["state"] != "done":
            continue
        h, a = m["home"], m["away"]
        if h not in rows or a not in rows:
            continue
        rh, ra = m["real"]
        games.append((h, a, rh, ra))
        for t, gf, gc in ((h, rh, ra), (a, ra, rh)):
            r = rows[t]
            r["pj"] += 1; r["gf"] += gf; r["gc"] += gc; r["dg"] = r["gf"] - r["gc"]
            if gf > gc:
                r["g"] += 1; r["pts"] += 3
            elif gf == gc:
                r["e"] += 1; r["pts"] += 1
            else:
                r["p"] += 1
    return {g: _rank_group([rows[t] for t in teams], games) for g, teams in GROUPS.items()}


def _rank_group(team_rows, games):
    """Orden FIFA: pts -> dg -> gf en TODOS los partidos; si siguen empatados,
    desempate por enfrentamiento directo entre los igualados (pts -> dg -> gf)."""
    base = sorted(team_rows, key=lambda r: (r["pts"], r["dg"], r["gf"]), reverse=True)
    out, i = [], 0
    while i < len(base):
        j = i
        while (j < len(base) and (base[j]["pts"], base[j]["dg"], base[j]["gf"])
               == (base[i]["pts"], base[i]["dg"], base[i]["gf"])):
            j += 1
        block = base[i:j]
        out.extend(_h2h(block, games) if len(block) > 1 else block)
        i = j
    return out


def _h2h(block, games):
    """Desempata equipos igualados por la mini-tabla de sus partidos entre si."""
    names = {r["team"] for r in block}
    h = {t: {"pts": 0, "dg": 0, "gf": 0} for t in names}
    for ht, at, rh, ra in games:
        if ht in names and at in names:
            for t, gf, gc in ((ht, rh, ra), (at, ra, rh)):
                h[t]["gf"] += gf; h[t]["dg"] += gf - gc
                h[t]["pts"] += 3 if gf > gc else (1 if gf == gc else 0)
    return sorted(block, key=lambda r: (h[r["team"]]["pts"], h[r["team"]]["dg"],
                                        h[r["team"]]["gf"], r["dg"], r["gf"]), reverse=True)


def qualifiers(tables):
    """(set de clasificados directos 1ro/2do, set de los 8 mejores 3ros)."""
    direct, thirds = set(), []
    for g, tt in tables.items():
        direct.add(tt[0]["team"])
        direct.add(tt[1]["team"])
        thirds.append(tt[2])
    thirds.sort(key=lambda r: (r["pts"], r["dg"], r["gf"]), reverse=True)
    best = {r["team"] for r in thirds[:8]}
    return direct, best


def qualification_status(tables):
    """team -> 'direct' (1ro/2do) / 'third' (mejor 3ro) / 'out'."""
    direct, best = qualifiers(tables)
    status = {}
    for tt in tables.values():
        for r in tt:
            t = r["team"]
            status[t] = "direct" if t in direct else ("third" if t in best else "out")
    return status


def group_matches(g, fx):
    teams = set(GROUPS[g])
    return sorted((m for m in fx if m["home"] in teams and m["away"] in teams),
                  key=lambda m: m["kickoff"])


if __name__ == "__main__":
    # El unico lugar del modulo que toca la capa de datos, y solo al correrlo a
    # mano: importarlo arriba volveria a crear el ciclo que este modulo evita.
    import app_data

    fx = app_data.fixture()
    tb = standings(fx)
    direct, best = qualifiers(tb)
    print("Grupo A:")
    for r in tb["A"]:
        print(f"  {r['team']:<16} PJ{r['pj']} {r['pts']}pts DG{r['dg']:+d} GF{r['gf']}")
    print(f"\nclasifican directo: {len(direct)} | mejores terceros: {len(best)} (de 12)")
    print("Mexico ->", qualification_status(tb).get("Mexico"))
