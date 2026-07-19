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

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
HOSTS = {"United States", "Mexico", "Canada"}
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

# seleccion -> codigo de bandera (flagcdn / ISO 3166-1, con casos UK especiales)
FLAG_ISO = {
    "Mexico": "mx", "South Africa": "za", "South Korea": "kr", "Czech Republic": "cz",
    "Canada": "ca", "Bosnia and Herzegovina": "ba", "United States": "us", "Paraguay": "py",
    "Qatar": "qa", "Switzerland": "ch", "Brazil": "br", "Morocco": "ma", "Haiti": "ht",
    "Scotland": "gb-sct", "Australia": "au", "Turkey": "tr", "Germany": "de", "Curaçao": "cw",
    "Netherlands": "nl", "Japan": "jp", "Ivory Coast": "ci", "Ecuador": "ec", "Sweden": "se",
    "Tunisia": "tn", "Spain": "es", "Cape Verde": "cv", "Belgium": "be", "Egypt": "eg",
    "Saudi Arabia": "sa", "Uruguay": "uy", "Iran": "ir", "New Zealand": "nz", "France": "fr",
    "Senegal": "sn", "Iraq": "iq", "Norway": "no", "Argentina": "ar", "Algeria": "dz",
    "Austria": "at", "Jordan": "jo", "Portugal": "pt", "DR Congo": "cd", "England": "gb-eng",
    "Croatia": "hr", "Ghana": "gh", "Panama": "pa", "Uzbekistan": "uz", "Colombia": "co",
}

# siglas de 3 letras (para el bracket, donde el espacio es chico)
ABBR = {
    "Mexico": "MEX", "South Africa": "RSA", "South Korea": "KOR", "Czech Republic": "CZE",
    "Canada": "CAN", "Bosnia and Herzegovina": "BIH", "Switzerland": "SUI", "Qatar": "QAT",
    "United States": "USA", "Paraguay": "PAR", "Turkey": "TUR", "Australia": "AUS",
    "Brazil": "BRA", "Morocco": "MAR", "Scotland": "SCO", "Haiti": "HAI",
    "Germany": "GER", "Ivory Coast": "CIV", "Ecuador": "ECU", "Curaçao": "CUW",
    "Netherlands": "NED", "Japan": "JPN", "Sweden": "SWE", "Tunisia": "TUN",
    "Belgium": "BEL", "Egypt": "EGY", "Iran": "IRN", "New Zealand": "NZL",
    "Spain": "ESP", "Uruguay": "URU", "Saudi Arabia": "KSA", "Cape Verde": "CPV",
    "France": "FRA", "Senegal": "SEN", "Norway": "NOR", "Iraq": "IRQ",
    "Argentina": "ARG", "Algeria": "ALG", "Austria": "AUT", "Jordan": "JOR",
    "Portugal": "POR", "Colombia": "COL", "Uzbekistan": "UZB", "DR Congo": "COD",
    "England": "ENG", "Croatia": "CRO", "Ghana": "GHA", "Panama": "PAN",
}

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
        mp = BASE / "data" / "finished.csv"
        if mp.exists():
            df = pd.read_csv(mp)
            _FINISHED = set(zip(df["home_team"], df["away_team"]))
        else:
            _FINISHED = set()
    return _FINISHED


def set_finished(home, away, val=True):
    """Marca/desmarca un partido como terminado a mano (data/finished.csv)."""
    global _FINISHED
    mp = BASE / "data" / "finished.csv"
    df = pd.read_csv(mp) if mp.exists() else pd.DataFrame(columns=["home_team", "away_team"])
    mask = (df["home_team"] == home) & (df["away_team"] == away)
    if val and not mask.any():
        df = pd.concat([df, pd.DataFrame([{"home_team": home, "away_team": away}])], ignore_index=True)
    elif not val:
        df = df[~mask]
    df.to_csv(mp, index=False)
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

PRON_COLS = ["date", "home_team", "away_team", "pred_home", "pred_away", "neutral",
             "model", "ev_v3", "actual_home", "actual_away", "points", "notes",
             "load_gel", "load_meli"]


def _apply_override(res: pd.DataFrame) -> pd.DataFrame:
    mp = BASE / "data" / "manual_results.csv"
    if not mp.exists():
        return res
    man = pd.read_csv(mp).dropna(subset=["date", "home_team", "away_team",
                                         "home_score", "away_score"])
    if man.empty:
        return res
    man["date"] = pd.to_datetime(man["date"], errors="coerce")
    key = ["date", "home_team", "away_team"]
    res = res.merge(man[key + ["home_score", "away_score"]], on=key,
                    how="left", suffixes=("", "_m"))
    for c in ("home_score", "away_score"):
        res[c] = res[c].where(res[c].notna(), res[f"{c}_m"])
    return res.drop(columns=["home_score_m", "away_score_m"])


def _pens_index():
    """Penales cargados a mano: {(home, away): (hp, ap)} (solo definiciones por
    penales en eliminacion). Vacio si no hay overrides con penales."""
    mp = BASE / "data" / "manual_results.csv"
    if not mp.exists():
        return {}
    man = pd.read_csv(mp)
    idx = {}
    for _, r in man.iterrows():
        hp = pd.to_numeric(r.get("home_pens"), errors="coerce")
        ap = pd.to_numeric(r.get("away_pens"), errors="coerce")
        if pd.notna(hp) and pd.notna(ap):
            idx[(r["home_team"], r["away_team"])] = (int(hp), int(ap))
    return idx


def _load():
    res = pd.read_csv(BASE / "data" / "results.csv")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    res = _apply_override(res)
    hor = pd.read_csv(BASE / "fixture_horarios.csv")
    hor["kickoff_arg"] = pd.to_datetime(hor["kickoff_arg"])
    pron_path = BASE / "pronosticos.csv"
    pron = pd.read_csv(pron_path) if pron_path.exists() else pd.DataFrame()
    return res, hor, pron


def _int_or0(v):
    try:
        if v == "" or pd.isna(v):
            return 0
        return int(v)
    except Exception:
        return 0


def fixture():
    """Partidos de grupos (dicts) ordenados por hora, con resultado, pred y carga."""
    res, hor, pron = _load()
    wc = res[(res["tournament"] == "FIFA World Cup") & (res["date"] >= pd.Timestamp("2026-06-11"))]
    played = wc.dropna(subset=["home_score", "away_score"])
    res_idx = played.set_index(["home_team", "away_team"])[["home_score", "away_score"]].sort_index()

    pred_idx, load_idx = {}, {}
    has_gel = "load_gel" in pron.columns
    has_meli = "load_meli" in pron.columns
    for _, r in pron.iterrows():
        if pd.notna(r.get("pred_home")):
            pred_idx[(r["home_team"], r["away_team"])] = (int(r["pred_home"]), int(r["pred_away"]))
        load_idx[(r["home_team"], r["away_team"])] = (
            _int_or0(r.get("load_gel")) if has_gel else 0,
            _int_or0(r.get("load_meli")) if has_meli else 0)

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
    wc = res[(res["tournament"] == "FIFA World Cup") & (res["date"] >= pd.Timestamp("2026-06-11"))]
    res_idx = wc.dropna(subset=["home_score", "away_score"]).set_index(
        ["home_team", "away_team"])[["home_score", "away_score"]].sort_index()

    pred_idx, load_idx = {}, {}
    hg, hm = "load_gel" in pron.columns, "load_meli" in pron.columns
    for _, r in pron.iterrows():
        if pd.notna(r.get("pred_home")):
            pred_idx[(r["home_team"], r["away_team"])] = (int(r["pred_home"]), int(r["pred_away"]))
        load_idx[(r["home_team"], r["away_team"])] = (
            _int_or0(r.get("load_gel")) if hg else 0, _int_or0(r.get("load_meli")) if hm else 0)

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


def outcome_type(pred, real):
    """exact / dir / miss segun el acierto (igual para los dos prodes)."""
    if pred is None or real is None:
        return None
    ph, pa = pred
    rh, ra = real
    if ph == rh and pa == ra:
        return "exact"
    if np.sign(ph - pa) == np.sign(rh - ra):
        return "dir"
    return "miss"


def needs_pens(m):
    """Partido de eliminacion terminado en empate y SIN penales cargados: falta definir la
    tanda para saber quien avanza (el dataset trae el marcador de 120', no los penales)."""
    real = m.get("real")
    return bool(m.get("stage") == "ko" and real is not None and real[0] == real[1]
                and not m.get("pens")
                and match_state(m["kickoff"], home=m.get("home"), away=m.get("away")) == "done")


def _points(ph, pa, rh, ra, pe, pdir):
    if ph == rh and pa == ra:
        return pe
    if np.sign(ph - pa) == np.sign(rh - ra):
        return pdir
    return 0


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
    pron = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=PRON_COLS)
    for c in ("load_gel", "load_meli"):
        if c not in pron.columns:
            pron[c] = 0
    return pron, path


def _match_date(home, away):
    res = pd.read_csv(BASE / "data" / "results.csv")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    m = res[(res["home_team"] == home) & (res["away_team"] == away)
            & (res["tournament"] == "FIFA World Cup") & (res["date"] >= pd.Timestamp("2026-06-11"))]
    return m.iloc[0]["date"].strftime("%Y-%m-%d") if len(m) else ""


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
        row = {c: "" for c in PRON_COLS}
        row.update({"date": _match_date(home, away), "home_team": home, "away_team": away,
                    "pred_home": int(ph), "pred_away": int(pa),
                    "neutral": home not in HOSTS, "model": "manual",
                    "load_gel": 0, "load_meli": 0})
        pron = pd.concat([pron, pd.DataFrame([row])], ignore_index=True)
    pron.to_csv(path, index=False)


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
    pron.to_csv(path, index=False)


def set_result(home, away, rh, ra, pens=None):
    """Carga/edita el resultado final en data/manual_results.csv (override).
    pens = (penales_local, penales_visita) si el partido se definio por penales
    (eliminacion). El override solo completa lo que el dataset oficial no tiene."""
    cols = ["date", "home_team", "away_team", "home_score", "away_score", "home_pens", "away_pens"]
    mp = BASE / "data" / "manual_results.csv"
    man = pd.read_csv(mp) if mp.exists() else pd.DataFrame(columns=cols)
    # penales SIEMPRE numericas (numero o NaN); nunca "" para no romper el dtype float
    for c in ("home_pens", "away_pens"):
        man[c] = pd.to_numeric(man[c], errors="coerce") if c in man.columns else np.nan
    ph, pa = (int(pens[0]), int(pens[1])) if pens else (np.nan, np.nan)
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
    man.to_csv(mp, index=False)


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
