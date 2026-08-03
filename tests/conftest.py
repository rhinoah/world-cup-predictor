"""Fixtures compartidas de la suite.

Dos problemas de testabilidad que se resuelven aca:
  1. `app_data.BASE` es absoluto y los loaders leen los CSV de produccion.
     -> la fixture `project` apunta BASE a un tmp_path con datasets minusculos.
  2. `app_data._FINISHED` es un cache global entre llamadas.
     -> se limpia automaticamente antes y despues de cada test.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prode.data import app_data  # noqa: E402
from prode.tournament import bracket  # noqa: E402

# Fechas de referencia del Mundial 2026 (para no hardcodearlas en cada test).
GROUPS_DAY = datetime(2026, 6, 15, 16, 0)    # fase de grupos -> ventana de 120'
KO_DAY = datetime(2026, 7, 4, 16, 0)         # eliminacion    -> ventana de 210'
LONG_AGO = datetime(2000, 1, 1, 12, 0)       # siempre "done" contra el reloj real


@pytest.fixture(autouse=True)
def _clean_module_caches():
    """Los modulos cachean en globals; sin esto los tests se contaminan entre si.

    `bracket._THIRDS` ademas se lee de la RAIZ del repo y no del tmp de la
    fixture `project`: es dato versionado (la tabla oficial de FIFA), asi que
    esta bien que no dependa del sandbox, pero el cache si tiene que limpiarse."""
    app_data._FINISHED = None
    bracket._THIRDS = None
    yield
    app_data._FINISHED = None
    bracket._THIRDS = None


class FakeProject:
    """Escribe datasets minusculos en un proyecto de mentira."""

    RESULT_COLS = ["date", "home_team", "away_team", "home_score", "away_score",
                   "tournament", "city", "country", "neutral"]

    def __init__(self, base: Path):
        self.base = base
        (base / "data").mkdir(exist_ok=True)

    def results(self, rows):
        """rows: dicts con al menos home_team/away_team; el resto tiene default."""
        out = []
        for r in rows:
            row = {"date": "2026-06-15", "home_score": 1, "away_score": 0,
                   "tournament": app_data.TOURNAMENT, "city": "X", "country": "Y",
                   "neutral": True}
            row.update(r)
            out.append(row)
        df = pd.DataFrame(out, columns=self.RESULT_COLS)
        df.to_csv(self.base / "data" / "results.csv", index=False)
        return df

    def manual_results(self, rows):
        cols = ["date", "home_team", "away_team", "home_score", "away_score",
                "home_pens", "away_pens"]
        out = []
        for r in rows:
            row = {"date": "2026-06-15", "home_score": 0, "away_score": 0,
                   "home_pens": None, "away_pens": None}
            row.update(r)
            out.append(row)
        pd.DataFrame(out, columns=cols).to_csv(
            self.base / "data" / "manual_results.csv", index=False)

    def finished(self, pairs):
        """pairs: [(home, away), ...] marcados como terminados a mano."""
        pd.DataFrame(list(pairs), columns=["home_team", "away_team"]).to_csv(
            self.base / "data" / "finished.csv", index=False)
        app_data._FINISHED = None

    def horarios(self, rows):
        """rows: dicts con home_team/away_team/kickoff_arg."""
        pd.DataFrame(rows, columns=["home_team", "away_team", "kickoff_arg"]).to_csv(
            self.base / "fixture_horarios.csv", index=False)

    def pronosticos(self, rows):
        out = []
        for r in rows:
            row = {c: "" for c in app_data.PRON_COLS}
            row.update({"date": "2026-06-15", "neutral": True, "model": "manual",
                        "load_gel": 1, "load_meli": 1})
            row.update(r)
            out.append(row)
        pd.DataFrame(out, columns=app_data.PRON_COLS).to_csv(
            self.base / "pronosticos.csv", index=False)


@pytest.fixture
def project(tmp_path, monkeypatch) -> FakeProject:
    """Proyecto aislado: `app_data.BASE` apunta a un tmp con datos de juguete."""
    monkeypatch.setattr(app_data, "BASE", tmp_path)
    app_data._FINISHED = None
    return FakeProject(tmp_path)


def _match(home="Spain", away="Argentina", kickoff=None, real=None, pred=None,
           load=(1, 1), **extra):
    """Dict de partido con la forma que devuelven fixture()/knockout_fixture().

    `state` se calcula igual que en produccion, CON los equipos, para que un
    partido marcado en finished.csv de "done" tambien aca. Los tests que no usan
    la fixture `project` no se ven afectados: sin CSV, el override esta vacio.
    Se puede pisar pasando `state=...` explicitamente."""
    ko = kickoff or GROUPS_DAY
    m = {"home": home, "away": away, "kickoff": ko,
         "state": app_data.match_state(ko, home=home, away=away),
         "real": real, "pred": pred, "load": load, "host": False}
    m.update(extra)
    return m


@pytest.fixture
def match():
    """Factory de partidos para probar scoreboard/needs_pens sin tocar disco."""
    return _match


@pytest.fixture
def ko_match():
    """Igual que `match` pero de eliminacion (stage='ko' y fecha post-grupos)."""
    def _make(**kw):
        kw.setdefault("kickoff", KO_DAY)
        kw.setdefault("stage", "ko")
        return _match(**kw)
    return _make


def _group_rows(spec):
    """spec: {equipo: (pts, dg, gf)} -> filas con la forma de groups.standings."""
    return [dict(team=t, pj=3, g=0, e=0, p=0, gf=gf, gc=gf - dg, dg=dg, pts=pts)
            for t, (pts, dg, gf) in spec.items()]


@pytest.fixture
def group_rows():
    """Arma filas de tabla de grupo sinteticas (para bracket/qualifiers)."""
    return _group_rows
