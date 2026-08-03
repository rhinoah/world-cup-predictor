#!/usr/bin/env python3
"""
app_data.py
===========
Capa de datos del Centro de Comando. Lee el fixture con horarios (hora
Argentina), los resultados (con overrides manuales) y los pronosticos, y expone
lo que la GUI necesita: proximo partido, partidos del dia, puntos de cada prode,
estado de carga en cada prode y escritura de pronosticos.
Rutas absolutas: se puede correr desde cualquier lado.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import csv_io
import scoring
from teams import ABBR, FLAG_ISO, HOSTS  # noqa: F401  (padron unico; se re-exportan)

BASE = Path(__file__).resolve().parent
# --- constantes del torneo (fuente unica; el resto de los scripts las importan) ---
# HOSTS/ABBR/FLAG_ISO viven en teams.py (padron unico de las 48 selecciones) y se
# re-exportan aca por comodidad: app_data es lo que importa la GUI.
TOURNAMENT = "FIFA World Cup"
WC_START = "2026-06-11"                         # filtro para aislar el Mundial 2026


def wc_matches(res):
    """Subconjunto del dataset que corresponde al Mundial 2026."""
    return res[(res["tournament"] == TOURNAMENT) & (res["date"] >= pd.Timestamp(WC_START))]
# Los prodes en los que se participa: nombre, etiqueta corta para la UI y puntaje
# (exacto, direccion). Personalizable SIN tocar codigo via prodes.json (no versionado):
#   {"prodes": [{"name": "Mi prode", "short": "Prode", "exact": 3, "dir": 1}, ...]}
_DEFAULT_PRODES = [
    {"name": "Prode A", "short": "A", "exact": 3, "dir": 1},
    {"name": "Prode B", "short": "B", "exact": 6, "dir": 3},
]


def _load_prodes():
    import json
    pj = BASE / "prodes.json"
    try:
        return json.loads(pj.read_text(encoding="utf-8"))["prodes"] if pj.exists() else _DEFAULT_PRODES
    except Exception:
        return _DEFAULT_PRODES


PRODE_CFG = _load_prodes()
PRODES = {p["name"]: (p["exact"], p["dir"]) for p in PRODE_CFG}
PRODE_NAMES = [p["name"] for p in PRODE_CFG]
PRODE_SHORT = [p["short"] for p in PRODE_CFG]

CHANGE_LIMIT_MIN = 70             # se puede cambiar el pronostico hasta 1h10 antes
GROUPS_END = pd.Timestamp("2026-06-27")   # ultimo dia de fase de grupos
DAY_ROLLOVER_HOUR = 4             # el "dia" cambia a las 4 AM (cubre partidos nocturnos)


def logical_date(dt):
    """Dia 'logico': los partidos de la madrugada (antes de las 4 AM) cuentan
    como del dia anterior, asi no se cambia de dia mientras todavia se juega."""
    if dt.hour < DAY_ROLLOVER_HOUR:
        return (dt - timedelta(days=1)).date()
    return dt.date()


def logical_today(now=None):
    return logical_date(now or datetime.now())


MATCH_MINUTES = 120      # grupos: "terminado" 2 h despues del kickoff
MATCH_MINUTES_KO = 210   # eliminacion: 3.5 h (alargue + penales; el partido no
                         # termina hasta los penales, aunque el prode puntue los 120')


_FINISHED = None


def _finished_set():
    """Partidos marcados a mano como 'ya terminó' (override del reloj). Cacheado."""
    global _FINISHED
    if _FINISHED is None:
        df = csv_io.read(BASE / "data" / "finished.csv", csv_io.FINISHED, missing_ok=True)
        _FINISHED = set(zip(df["home_team"], df["away_team"]))
    return _FINISHED


def set_finished(home, away, val=True):
    """Marca/desmarca un partido como terminado a mano (data/finished.csv)."""
    global _FINISHED
    mp = BASE / "data" / "finished.csv"
    df = csv_io.read(mp, csv_io.FINISHED, missing_ok=True)
    mask = (df["home_team"] == home) & (df["away_team"] == away)
    if val and not mask.any():
        df = pd.concat([df, pd.DataFrame([{"home_team": home, "away_team": away}])], ignore_index=True)
    elif not val:
        df = df[~mask]
    csv_io.write(df, mp, csv_io.FINISHED)
    _FINISHED = None                      # invalida cache


def match_state(kickoff, now=None, home=None, away=None):
    """pre (no empezo) / live (en curso) / done (termino, ya suma puntaje).
    En eliminacion la ventana se extiende por el tiempo suplementario y penales.
    Si el partido se marco terminado a mano, es 'done' aunque el reloj no llegue."""
    if home is not None and away is not None and (home, away) in _finished_set():
        return "done"
    now = now or datetime.now()
    if now < kickoff:
        return "pre"
    dur = MATCH_MINUTES_KO if is_knockout(kickoff.date()) else MATCH_MINUTES
    if now < kickoff + timedelta(minutes=dur):
        return "live"
    return "done"

PRON_COLS = list(csv_io.PRONOSTICOS)      # el esquema manda el orden de columnas


def _apply_override(res: pd.DataFrame) -> pd.DataFrame:
    mp = BASE / "data" / "manual_results.csv"
    man = csv_io.read(mp, csv_io.MANUAL_RESULTS, missing_ok=True).dropna(
        subset=["date", "home_team", "away_team", "home_score", "away_score"])
    if man.empty:
        return res
    key = ["date", "home_team", "away_team"]
    res = res.merge(man[key + ["home_score", "away_score"]], on=key,
                    how="left", suffixes=("", "_m"))
    for c in ("home_score", "away_score"):
        res[c] = res[c].where(res[c].notna(), res[f"{c}_m"])
    return res.drop(columns=["home_score_m", "away_score_m"])


def _pens_index():
    """Penales cargados a mano: {(home, away): (hp, ap)} (solo definiciones por
    penales en eliminacion). Vacio si no hay overrides con penales."""
    man = csv_io.read(BASE / "data" / "manual_results.csv", csv_io.MANUAL_RESULTS,
                     missing_ok=True)
    con_pens = man.dropna(subset=["home_pens", "away_pens"])
    return {(r["home_team"], r["away_team"]): (int(r["home_pens"]), int(r["away_pens"]))
            for _, r in con_pens.iterrows()}


def _load():
    res = csv_io.read(BASE / "data" / "results.csv", csv_io.RESULTS)
    res = _apply_override(res)
    hor = csv_io.read(BASE / "fixture_horarios.csv", csv_io.HORARIOS)
    pron = csv_io.read(BASE / "pronosticos.csv", csv_io.PRONOSTICOS, missing_ok=True)
    return res, hor, pron


def _int_or0(v):
    """Casteo de las columnas de carga: 'sin marcar' es lo mismo que 'no cargado'.

    Ya no tiene que defenderse del "" que escribia el codigo viejo (csv_io lee
    esas columnas como Int64 y el faltante llega como pd.NA), pero sigue siendo
    la politica de la app: si no hay dato, el pronostico no se cargo."""
    try:
        if v == "" or pd.isna(v):
            return 0
        return int(v)
    except Exception:
        return 0


def _index_pronosticos(pron):
    """Indexa los pronosticos por (local, visitante): {clave: (ph, pa)} y
    {clave: (cargado_en_prode_1, cargado_en_prode_2)}.

    Antes cada llamador chequeaba `"load_gel" in pron.columns` porque el CSV
    podia no traer la columna; hoy csv_io la crea siempre desde el esquema, asi
    que alcanza con `_int_or0` para el caso de la celda vacia."""
    pred_idx, load_idx = {}, {}
    for _, r in pron.iterrows():
        clave = (r["home_team"], r["away_team"])
        if pd.notna(r["pred_home"]):
            pred_idx[clave] = (int(r["pred_home"]), int(r["pred_away"]))
        load_idx[clave] = (_int_or0(r["load_gel"]), _int_or0(r["load_meli"]))
    return pred_idx, load_idx


def fixture():
    """Partidos de grupos (dicts) ordenados por hora, con resultado, pred y carga."""
    res, hor, pron = _load()
    wc = wc_matches(res)
    played = wc.dropna(subset=["home_score", "away_score"])
    res_idx = played.set_index(["home_team", "away_team"])[["home_score", "away_score"]].sort_index()

    pred_idx, load_idx = _index_pronosticos(pron)

    out = []
    for _, h in hor.sort_values("kickoff_arg").iterrows():
        ht, at = h["home_team"], h["away_team"]
        real = None
        if (ht, at) in res_idx.index:
            rec = res_idx.loc[(ht, at)]
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            real = (int(rec["home_score"]), int(rec["away_score"]))
        out.append({"home": ht, "away": at,
                    "kickoff": h["kickoff_arg"].to_pydatetime(),
                    "host": ht in HOSTS, "real": real,
                    "pred": pred_idx.get((ht, at)),
                    "load": load_idx.get((ht, at), (0, 0))})
    return out


def knockout_fixture():
    """Partidos de eliminacion (M73-M104) con equipos proyectados (resolve_r32 +
    arbol) o placeholder, fecha de bracket.MATCH_DT, resultado real (override/
    martj42) y pred/load del usuario. 'defined' = ambos equipos ya se conocen."""
    import bracket
    import groups
    res, _, pron = _load()
    wc = wc_matches(res)
    res_idx = wc.dropna(subset=["home_score", "away_score"]).set_index(
        ["home_team", "away_team"])[["home_score", "away_score"]].sort_index()

    pred_idx, load_idx = _index_pronosticos(pron)

    def real_of(ht, at):
        if ht and at and (ht, at) in res_idx.index:
            rec = res_idx.loc[(ht, at)]
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            return (int(rec["home_score"]), int(rec["away_score"]))
        return None

    fx_g = fixture()
    done_groups = set()
    for g, teams in groups.GROUPS.items():
        ts = set(teams)
        if sum(1 for m in fx_g if m["home"] in ts and m["away"] in ts and m["real"] is not None
               and match_state(m["kickoff"]) == "done") >= 6:
            done_groups.add(g)
    all_done = len(done_groups) == len(groups.GROUPS)

    def sealed(code):
        if not code:
            return False
        if code.startswith("3:"):
            return all_done            # el mejor 3ro depende de TODOS los grupos
        return code[1] in done_groups  # '1A'/'2A' -> grupo A ya terminado

    r32 = {x["match"]: x for x in bracket.resolve_r32(groups.standings(fx_g))}
    pens_idx = _pens_index()
    winners, losers, out = {}, {}, []
    for mnum in sorted(bracket.MATCH_DT):
        if mnum <= 88:
            info = r32.get(mnum, {})
            ac, bc = info.get("a_code", ""), info.get("b_code", "")
            ht = info.get("a") if sealed(ac) else None
            at = info.get("b") if sealed(bc) else None
            al = ht or bracket.slot_label(ac)
            bl = at or bracket.slot_label(bc)
        elif mnum == bracket.THIRD_PLACE:
            ht, at = losers.get(101), losers.get(102)   # el 3er puesto lo juegan los perdedores de las semis
            al = ht or "Perd. M101"
            bl = at or "Perd. M102"
        else:
            sa, sb = bracket.TREE[mnum]
            ht, at = winners.get(sa), winners.get(sb)
            al = ht or f"Gan. M{sa}"
            bl = at or f"Gan. M{sb}"
        real = real_of(ht, at)
        pens = pens_idx.get((ht, at)) if ht and at else None
        if real:
            if real[0] != real[1]:
                winners[mnum], losers[mnum] = (ht, at) if real[0] > real[1] else (at, ht)
            elif pens:                              # empate en 120' -> avanza el de mas penales
                winners[mnum], losers[mnum] = (ht, at) if pens[0] > pens[1] else (at, ht)
        out.append({"match": mnum, "home": ht, "away": at, "a_label": al, "b_label": bl,
                    "kickoff": pd.to_datetime(bracket.MATCH_DT[mnum]).to_pydatetime(),
                    "host": False, "real": real, "pens": pens, "winner": winners.get(mnum),
                    "defined": bool(ht and at), "stage": "ko",
                    "pred": pred_idx.get((ht, at)) if ht and at else None,
                    "load": load_idx.get((ht, at), (0, 0)) if ht and at else (0, 0)})
    return out


def next_match(now=None, fx=None):
    now = now or datetime.now()
    fx = fx or fixture()
    upcoming = sorted((m for m in fx if m["kickoff"] > now), key=lambda m: m["kickoff"])
    return upcoming[0] if upcoming else None


def first_match_on(day, fx=None):
    fx = fx or fixture()
    todays = [m for m in fx if logical_date(m["kickoff"]) == day]
    return min(todays, key=lambda m: m["kickoff"]) if todays else None


def is_knockout(day) -> bool:
    """True si el partido es de eliminacion (despues del fin de la fase de grupos)."""
    return pd.Timestamp(day) > GROUPS_END


# El acierto (exact/dir/miss) y el puntaje viven en scoring.py, compartidos con
# liquidar.py y los backtests; aca solo se re-exportan con los nombres de la app.
outcome_type = scoring.outcome


def needs_pens(m):
    """Partido de eliminacion terminado en empate y SIN penales cargados: falta definir la
    tanda para saber quien avanza (el dataset trae el marcador de 120', no los penales)."""
    real = m.get("real")
    return bool(m.get("stage") == "ko" and real is not None and real[0] == real[1]
                and not m.get("pens")
                and match_state(m["kickoff"], home=m.get("home"), away=m.get("away")) == "done")


def _points(ph, pa, rh, ra, pe, pdir):
    return scoring.points((ph, pa), (rh, ra), pe, pdir)


def scoreboard(fx=None, now=None):
    """Puntos por prode sobre los partidos TERMINADOS con pronostico + resultado.
    Devuelve por prode los sub-totales por etapa ('grupos'/'elim') y ademas el
    total combinado; la UI decide si muestra las tablas separadas (primer prode)
    o la tabla continua (segundo)."""
    fx = fx or fixture()
    now = now or datetime.now()
    board = {}
    for li, (name, (pe, pdir)) in enumerate(PRODES.items()):   # li: indice del prode en m["load"]
        st = {"grupos": {"total": 0, "n": 0, "exact": 0, "dir": 0, "fail": 0},
              "elim": {"total": 0, "n": 0, "exact": 0, "dir": 0, "fail": 0}}
        for m in fx:
            if m["real"] is None:
                continue
            if match_state(m["kickoff"], now, m.get("home"), m.get("away")) != "done":
                continue
            s = st["elim"] if is_knockout(m["kickoff"].date()) else st["grupos"]
            # Sin pronostico, o no cargado en ESTE prode: el partido se jugo igual -> cuenta 0 (fallado),
            # no desaparece del conteo (asi el "jugados" refleja la realidad del prode).
            if m["pred"] is None or not m["load"][li]:
                s["n"] += 1
                s["fail"] += 1
                continue
            pts = _points(*m["pred"], *m["real"], pe, pdir)
            s["total"] += pts
            s["n"] += 1
            if pts == pe:
                s["exact"] += 1
            elif pts == pdir:
                s["dir"] += 1
            else:
                s["fail"] += 1
        g, e = st["grupos"], st["elim"]
        board[name] = {"scoring": (pe, pdir), "grupos": g, "elim": e,
                       "total": g["total"] + e["total"], "n": g["n"] + e["n"],
                       "exact": g["exact"] + e["exact"], "dir": g["dir"] + e["dir"],
                       "fail": g["fail"] + e["fail"]}
    return board


def _read_pron():
    path = BASE / "pronosticos.csv"
    pron = csv_io.read(path, csv_io.PRONOSTICOS, missing_ok=True)
    # "sin marcar" es lo mismo que "no cargado": se persiste 0 y no vacio, para
    # que el CSV diga explicitamente que el pronostico no se cargo en ese prode.
    for c in ("load_gel", "load_meli"):
        pron[c] = pron[c].fillna(0)
    return pron, path


def _match_date(home, away):
    res = csv_io.read(BASE / "data" / "results.csv", csv_io.RESULTS)
    m = res[(res["home_team"] == home) & (res["away_team"] == away)
            & (res["tournament"] == TOURNAMENT) & (res["date"] >= pd.Timestamp(WC_START))]
    return m.iloc[0]["date"] if len(m) else pd.NA


def set_prediction(home, away, ph, pa):
    """Crea o actualiza el pronostico de un partido en pronosticos.csv."""
    pron, path = _read_pron()
    mask = (pron["home_team"] == home) & (pron["away_team"] == away)
    if mask.any():
        pron.loc[mask, "pred_home"] = int(ph)
        pron.loc[mask, "pred_away"] = int(pa)
        pron.loc[mask, "model"] = "manual"
        pron.loc[mask, "load_gel"] = 0      # cambio el pronostico -> hay que recargarlo
        pron.loc[mask, "load_meli"] = 0
    else:
        # pd.NA y no "": el "" es lo que rompia el dtype de las columnas
        # numericas al releer el CSV (ver csv_io).
        row = {c: pd.NA for c in PRON_COLS}
        row.update({"date": _match_date(home, away), "home_team": home, "away_team": away,
                    "pred_home": int(ph), "pred_away": int(pa),
                    "neutral": home not in HOSTS, "model": "manual",
                    "load_gel": 0, "load_meli": 0})
        pron = pd.concat([pron, pd.DataFrame([row])], ignore_index=True)
    csv_io.write(pron, path, csv_io.PRONOSTICOS)


def set_confirmation(home, away, gel=None, meli=None, pred=None):
    """Marca si el pronostico ya se cargo en cada prode. gel/meli: bool o None
    (None = no tocar). Si no hay fila y pred dado, la crea con ese marcador."""
    pron, path = _read_pron()
    mask = (pron["home_team"] == home) & (pron["away_team"] == away)
    if not mask.any() and pred is not None:
        set_prediction(home, away, pred[0], pred[1])
        pron, path = _read_pron()
        mask = (pron["home_team"] == home) & (pron["away_team"] == away)
    if not mask.any():
        return
    if gel is not None:
        pron.loc[mask, "load_gel"] = int(bool(gel))
    if meli is not None:
        pron.loc[mask, "load_meli"] = int(bool(meli))
    csv_io.write(pron, path, csv_io.PRONOSTICOS)


def set_result(home, away, rh, ra, pens=None):
    """Carga/edita el resultado final en data/manual_results.csv (override).
    pens = (penales_local, penales_visita) si el partido se definio por penales
    (eliminacion). El override solo completa lo que el dataset oficial no tiene."""
    mp = BASE / "data" / "manual_results.csv"
    # Las columnas de penales quedan enteras con faltantes (Int64) por esquema:
    # antes habia que re-castearlas a mano en cada guardado o se degradaban.
    man = csv_io.read(mp, csv_io.MANUAL_RESULTS, missing_ok=True)
    ph, pa = (int(pens[0]), int(pens[1])) if pens else (pd.NA, pd.NA)
    mask = (man["home_team"] == home) & (man["away_team"] == away)
    if mask.any():
        man.loc[mask, "home_score"] = int(rh)
        man.loc[mask, "away_score"] = int(ra)
        man.loc[mask, "home_pens"] = ph
        man.loc[mask, "away_pens"] = pa
    else:
        man = pd.concat([man, pd.DataFrame([{"date": _match_date(home, away), "home_team": home,
                                             "away_team": away, "home_score": int(rh), "away_score": int(ra),
                                             "home_pens": ph, "away_pens": pa}])], ignore_index=True)
    csv_io.write(man, mp, csv_io.MANUAL_RESULTS)


if __name__ == "__main__":
    fx = fixture()
    nm = next_match(fx=fx)
    print("PROXIMO PARTIDO:")
    if nm:
        flag = "  [LOCAL]" if nm["host"] else ""
        print(f"  {nm['home']} vs {nm['away']}  ->  {nm['kickoff']:%a %d/%m %H:%M} (Arg){flag}")
        print(f"  pred {nm['pred']}  carga {nm['load']}")
    print("\nTABLERO:")
    for name, s in scoreboard(fx).items():
        print(f"  {name:<16} {s['total']:>3} pts   "
              f"[{s['n']} jugados: {s['exact']} exactos, {s['dir']} direccion, {s['fail']} fallados]")
