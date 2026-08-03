# CLAUDE.md — Modelo predictivo para prode Mundial 2026

Instrucciones para Claude Code al trabajar en este repo. Se dejó versionado a
propósito: el README cuenta que el proyecto se construyó íntegramente en sesiones
de *vibe coding*, y este archivo es la mitad que normalmente no se ve.

## Objetivo del proyecto

Modelo basado en datos para participar de un **prode (pool de predicciones) del
Mundial 2026**. No sólo "tirar un pronóstico": estimar probabilidades de forma
fundamentada y **optimizar las predicciones según el sistema de puntaje del
prode**, que no es lo mismo.

Trabajo en español rioplatense (voseo). Código y comentarios pueden estar en
inglés o español; los nombres de variables, preferentemente en inglés.

## Estado: el torneo terminó

El Mundial 2026 se jugó (España campeón, 19/07/2026) y el proyecto está completo.
El modelo prometía **0.91 puntos/partido** en backtest y rindió **0.88** sobre los
104 partidos reales, completamente out-of-sample.

Lo que existe hoy, con el detalle en el README:

- **`prode/model/`** — Poisson con fuerzas de ataque/defensa ajustadas por rival
  (punto fijo estilo Maher), corrección Dixon-Coles, Elo dinámico propio y la
  regla de decisión por EV. `predict_match_v3` es producción.
- **`prode/tournament/`** — las 48 selecciones, los 12 grupos con el desempate
  FIFA y las llaves M73–M104 con la tabla oficial de mejores terceros.
- **`prode/data/`** — lectura/escritura tipada de los CSV y la capa que consume la app.
- **`prode/ui/`** — la app de escritorio (CustomTkinter).
- **`scripts/`** + **`run.py`** — el pipeline (`setup` / `update` / `analisis`).
- **`tests/`** — 395 tests (1354 casos con parametrización), corriendo en CI.

## Fuentes de datos

| Dataset | Qué trae | Link |
|---|---|---|
| martj42 international_results | ~50k partidos de selecciones | https://github.com/martj42/international_results |
| flagcdn | las banderas de las 48 | https://flagcdn.com/ |
| Wikipedia (Annex C de FIFA) | tabla oficial de mejores terceros (495 combos) | parseada por `scripts/parse_thirds.py` |

Esquema de `results.csv`:
`date, home_team, away_team, home_score, away_score, tournament, city, country, neutral`

## Reglas que el modelo TIENE que respetar

- **Nada de data leakage.** Cualquier feature de un partido se calcula únicamente
  con datos *anteriores* a su fecha (`date < as_of`). Vale también para la
  validación: los backtests tienen `MAX_YEAR = 2024` justamente porque el dataset
  se actualiza solo y el Mundial 2026 se les había colado adentro.
- **Nombres de selecciones.** Hay un padrón único en `prode/tournament/teams.py`
  con `canonical()` para normalizar entre fuentes. No agregar diccionarios
  paralelos: ya pasó una vez y costó un refactor.
- **Cancha neutral.** En el Mundial casi todo es sede neutral salvo los
  anfitriones (USA, México, Canadá).
- **Amistosos vs oficiales.** Los amistosos pesan la mitad.

## Reglas del prode

Dos pools con reglas distintas, que es lo que hace interesante la optimización:

| | exacto | dirección | fallado |
|---|---|---|---|
| Prode A | 3 | 1 | 0 |
| Prode B | 6 | 3 | 0 |

Se predice **el marcador**, partido a partido. De ahí sale la regla de decisión:
no se carga el marcador *más probable* sino el que maximiza el puntaje esperado,
`EV = ratio·P(exacto) + P(dirección)` con `ratio = exact/direction − 1`. Ese
ratio vale **2.0 para 3/1 pero 1.0 para 6/3**, así que en teoría cada prode tiene
un marcador óptimo distinto (hoy se sugiere uno solo, con el puntaje por defecto).

Los nombres y puntajes reales viven en `prodes.json`, que no se versiona.

## Stack y convenciones

- **Python + pandas**; **matplotlib** sólo para el gráfico de `backfill_ev`.
  No hay scikit-learn ni XGBoost: el modelo es Poisson + Elo escritos a mano.
- Validación temporal por fecha, nunca shuffle aleatorio.
- Pipeline reproducible: `data/` (crudo) → `output/` (procesado) → modelo.
  Nada pesado versionado; se regenera con `python run.py setup`.
- Funciones chicas y testeables. Antes de un refactor grande, charlamos el diseño.

## Cómo correr

```bash
python run.py --list       # los pasos de cada flujo
python run.py setup        # clon nuevo: dataset, fixture, banderas, ícono
python prode_app.py        # la app de escritorio
pytest                     # la suite
```

Los scripts se invocan como módulo: `python -m scripts.liquidar`.

## Lecciones que dejó el proyecto

Vale la pena tenerlas presentes al seguir tocando esto:

- **Un refactor de unificación debilita los tests sin avisar.** Al fusionar cinco
  estructuras en `teams.py`, ~49 tests quedaron tautológicos. Se detectó con
  mutation testing y se repuso la red con un testigo externo.
- **La validación también sufre leakage.** Un filtro `year >= 2016` sin tope
  superior metió el Mundial 2026 dentro de su propio backtest.
- **Vacío no es lo mismo que ilegible.** Tolerar basura en una columna que
  sostiene el resto convierte "la app no arranca" en "la app miente".
- **Medir antes de afirmar.** El README decía que el Elo "discrimina mejor al
  favorito"; al medirlo resultó falso (acierta la dirección exactamente igual).
  Lo que aporta es la escala de goles.
- Para refactors grandes conviene un **arnés de equivalencia**: capturar N
  magnitudes observables antes y después, y diffear.
