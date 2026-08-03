# ⚽ Prode Mundial 2026 — modelo predictivo + centro de comando

[![tests](https://github.com/rhinoah/world-cup-predictor/actions/workflows/tests.yml/badge.svg)](https://github.com/rhinoah/world-cup-predictor/actions/workflows/tests.yml)

Modelo estadístico que predice marcadores de fútbol de selecciones, y una app de
escritorio que lo acompaña durante el torneo: pronósticos sugeridos con su "por qué",
recordatorios, carga de resultados, llaves de eliminación y puntaje en vivo de dos
prodes con reglas distintas.

Construido íntegramente en sesiones de **vibe coding** con Claude Code, para jugar
dos pools de predicciones del Mundial 2026 con amigos. **No es una herramienta de
apuestas** — es un proyecto por diversión y aprendizaje.

> **El resultado que importa:** el modelo prometía ~**0.90 puntos/partido** en
> backtest histórico (9 torneos 2016–2024) y rindió **0.88** en el Mundial 2026
> real — 104 partidos completamente *out-of-sample*. No estaba sobreajustado.

---

## 🖥️ La app

*Centro de comando de escritorio (CustomTkinter, tema oscuro):*

<!-- TODO: capturas en docs/ — grilla principal, llaves, popup de carga -->

- **Próximo partido** con cuenta regresiva, banderas y tu pronóstico cargado.
- **Partidos de hoy / mañana** con el marcador sugerido por el modelo y su
  explicación: probabilidades 1X2, goles esperados, Elo y marcadores más probables.
- **Carga de resultados** con steppers, penales en eliminación, botón "terminó el
  partido" y avisos ⚠ cuando un cruce quedó empatado sin tanda cargada.
- **Llaves de eliminación** con la asignación **oficial FIFA de mejores terceros**
  (las 495 combinaciones del Annex C, parseadas de Wikipedia), ganadores que
  avanzan solos, marcadores con penales y semáforo de acierto por partido.
- **Dos prodes en paralelo** con reglas distintas (3/1/0 y 6/3/0), cada uno
  contando solo lo que cargaste en él — nombres y puntajes configurables vía
  `prodes.json` (no versionado).
- Ícono en bandeja, recordatorios sonoros, instancia única, autostart opcional y
  actualización diaria del dataset por tarea programada.

## 🧠 El modelo

La evolución (cada versión validada por backtest antes de reemplazar a la anterior):

| Versión | Idea | Backtest (pts/partido) |
|---|---|---|
| baseline | "1-0 al favorito" | 0.825 |
| v1 | Poisson con fuerzas ataque/defensa crudas + decay temporal + Dixon-Coles | — |
| v2 | fuerzas ajustadas por rival (punto fijo estilo Maher) + localía | 0.827 |
| **v3** | **v2 blendeado con Elo dinámico (w=0.6)** | **~0.90** |

Piezas clave:

- **Poisson bivariado con corrección Dixon-Coles** (ρ=−0.10) para la matriz de
  probabilidad de cada marcador.
- **Elo dinámico** propio: discrimina al favorito mejor que las fuerzas solas —
  es el componente que despega del baseline.
- **Regla de decisión por EV**: no se carga el marcador *más probable*, sino el
  que **maximiza el puntaje esperado del prode**: `EV = 2·P(exacto) + P(dirección)`.
  Solo hay 3 candidatos (el modal de cada dirección 1X2).
- **Cero data leakage**: toda feature de un partido se calcula únicamente con
  datos **anteriores** a su fecha (`date < as_of`), tanto en backtest como en vivo.
- Amistosos pesan la mitad; decay temporal; cancha neutral contemplada (en el
  Mundial solo los anfitriones juegan de local).

## 📊 Validación

**Backtest** (`backtest.py`, `backtest_elo.py`): 9 torneos grandes (Mundial, Euro,
Copa América 2016–2024), split temporal estricto, puntuando con 3/1/0.

**En vivo — Mundial 2026 (104 partidos):**

| Métrica | Valor |
|---|---|
| Puntos (3 exacto / 1 dirección) | **91** → **0.88/partido** |
| Marcadores exactos | 11 (11%) |
| Dirección acertada | 58 (56%) |
| Fallados | 35 (34%) |
| Backtest esperado | ~0.90/partido ✔ |

### Real vs esperado (EV)

`backfill_ev.py` re-ajusta el modelo *as-of* cada fecha del torneo (sin leakage)
y compara los puntos obtenidos contra el EV que el propio modelo le asignaba a
cada pronóstico cargado:

![Puntaje real vs esperado](docs/ev_vs_real.png)

| | Real | Esperado (EV) |
|---|---|---|
| **Total (104 partidos)** | **91** | 86.9 |
| Fase de grupos (72) | 58 | 62.0 |
| Eliminación (32) | **33** | 24.9 |

Lectura honesta: el resultado quedó **dentro del rango que el propio modelo
esperaba** (+4 puntos sobre su esperanza — varianza normal): algo por debajo en
grupos (los favoritos gigantes que empataron 0-0), bastante por encima en la
eliminación. El marcador sugerido óptimo se siguió en 100 de 104 partidos.

### 🆚 Bonus: contra el mercado de predicciones

Durante las rondas finales comparamos el modelo contra **Kalshi** (mercado de
predicciones con dinero real): en la semifinal discreparon de lleno (el mercado
favorecía a Inglaterra; el modelo, a Argentina — **ganó Argentina**), y en la
final ambos favorecían a España pero el mercado con más convicción (**ganó
España**). Saldo honesto: **1 a 1** — un modelo casero le peleó de igual a igual
a un mercado real durante un Mundial.

## 🧪 Tests

**1353 tests** (pytest) sobre el modelo y la capa de datos, corriendo en CI para
Python 3.11 y 3.13:

```bash
pip install -r requirements-dev.txt
pytest
```

Cubren la regla de puntaje y la decisión por EV, el scoreboard por prode, los
estados de un partido (incluida la ventana extendida de eliminación y el
override manual), el desempate FIFA de los grupos (con enfrentamiento directo),
las invariantes del bracket y la tabla oficial de terceros, el padrón de
selecciones, el Elo (invariante de suma cero y ausencia de leakage) y la
lectura/escritura tipada de los CSV.

Los refactors grandes se validaron además con un **arnés de equivalencia**: un
script que captura ~40 magnitudes observables (salida del modelo, Elo,
probabilidades de partidos concretos, los 104 partidos con todos sus campos,
posiciones, puntajes) antes y después del cambio, y las compara una por una.
Es lo que permite refactorizar la capa de datos y afirmar que el modelo devuelve
exactamente lo mismo, en vez de suponerlo.

Se validaron con **mutation testing**: se inyectaron bugs a propósito (anular
los puntos por dirección, acortar la ventana de eliminación, romper el desempate
head-to-head, escribir mal el nombre de una selección) y la suite los detectó
en todos los casos.

El caso del nombre mal escrito es el más interesante, porque **el primer intento
no lo detectó**. Al unificar las selecciones en un padrón único, los tests que
verificaban que cuatro tablas paralelas estuvieran sincronizadas dejaron de
poder fallar: ahora todo deriva de la misma fila. Un `'Ghana'` → `'Gana'` pasaba
en verde y hacía desaparecer al equipo de todo cruce contra el dataset. La
solución fue validar el padrón contra un **testigo externo** — el fixture crudo
de horarios, escrito a mano desde otra fuente — que además reconstruye los 12
grupos a partir de quién juega contra quién.

### Vacío no es lo mismo que ilegible

`csv_io.py` distingue las dos cosas, y la distinción salió de una revisión
adversarial del propio módulo. La primera versión hacía la lectura tolerante en
todas las columnas: lo que no se entendía quedaba en nulo, para que un CSV
editado a mano nunca dejara la app sin arrancar. Suena razonable hasta que se ve
la consecuencia: un `2-1` tipeado en la columna de goles se convertía en nulo,
la fila se caía en el `dropna` del override, y **el partido pasaba a figurar
como no jugado** — el tablero mostraba un número equivocado sin dejar rastro.

Hoy cada columna declara si tolera basura. Que un partido no tenga marcador es
normal (todavía no se jugó); que tenga escrito algo que no se entiende, no:
`home_score` avisa con el archivo, la columna y la fila. `home_pens`, que está
vacía en el 96% de los partidos, sigue siendo tolerante.

## 🚀 Cómo correrlo

```bash
pip install -r requirements.txt

python run.py setup               # clon nuevo: dataset, fixture, banderas, ícono
python prode_app.py               # la app de escritorio (Windows)
```

El pipeline está en `run.py`, que es la única definición de en qué orden va cada
cosa — la tarea programada y este README lo invocan a él en vez de repetir la
secuencia:

```bash
python run.py --list              # qué hace cada paso y qué produce
python run.py update              # ciclo diario: dataset → liquidar → jornada → detalle
python run.py analisis            # backtests + real vs esperado (tarda varios minutos)
```

Suelto, sin pipeline:

```bash
python predict_match_v3.py "Spain" "Argentina" --neutral   # un partido puntual
pytest                                                     # la suite de tests
```

Y opcionalmente, en Windows, dejarlo andando solo (tarea diaria + arranque
minimizado en la bandeja). Es reversible y no necesita permisos de administrador:

```bash
setup_windows.bat install 10:00   # o "status" / "uninstall"
```

La GUI usa `winsound`/`pystray` y está pensada para **Windows**; el modelo y los
scripts de análisis corren en cualquier plataforma.

## 🗂️ Estructura

| Archivo | Qué hace |
|---|---|
| `run.py` | el pipeline: `setup` / `update` / `analisis` (única definición del orden) |
| `Prode.bat` / `update_dataset.bat` / `setup_windows.bat` | lanzar la app / correr el ciclo diario / instalar la automatización |
| `build_features.py` | descarga el dataset y construye la tabla de features |
| `elo.py` | rating Elo dinámico + blend de lambdas |
| `predict_match_v2.py` / `_v3.py` | modelo de fuerzas / blend con Elo (**producción**) |
| `backtest.py` / `backtest_elo.py` | validación temporal sobre torneos 2016–2024 |
| `build_pronosticos.py` | corre el v3 sobre los partidos pendientes (grupos + llaves) |
| `liquidar.py` | cruza pronósticos con resultados y calcula el puntaje |
| `backfill_ev.py` | recalcula el EV as-of de cada pronóstico (real vs esperado) |
| `app_data.py` | capa de datos de la app (fixture, scoreboard, overrides, penales) |
| `prode_app.py` | la app de escritorio (CustomTkinter): ventana principal |
| `ui_bracket.py` / `ui_tray.py` | ventanas de grupos y llaves / bandeja, bips e instancia única |
| `theme.py` / `single_instance.py` | paleta y tipografía / lock de una sola ventana |
| `scoring.py` | reglas de puntaje del prode y la decisión por EV (fuente única) |
| `teams.py` | padrón único de las 48 selecciones (nombre, castellano, sigla, bandera, grupo) |
| `csv_io.py` | lectura/escritura tipada de los CSV (dtypes en un solo lugar) |
| `results.py` | resultados del torneo (dataset + cargados a mano) y búsqueda por cruce |
| `groups.py` / `bracket.py` | tablas de grupos (desempate FIFA) y llaves M73–M104 |
| `tests/` | suite pytest (1353 tests) |
| `parse_thirds.py` / `thirds_table.json` | tabla oficial de asignación de terceros (495 combos) |
| `build_horarios.py` / `build_flags.py` / `make_icon.py` | fixture en hora ARG, banderas, ícono |

## 📚 Datos y créditos

- Resultados históricos de selecciones: [martj42/international_results](https://github.com/martj42/international_results) (~50k partidos).
- Banderas: [flagcdn](https://flagcdn.com/) (generadas por `build_flags.py`, no versionadas).
- Tabla de terceros: plantilla de Wikipedia del Annex C de FIFA, parseada por `parse_thirds.py`.

Los CSV de datos y los pronósticos personales **no se versionan** (ver
`.gitignore`); todo lo pesado se regenera con `build_features.py`.

## 🧭 Roadmap

- De la auditoría interna post-torneo ya salieron la regla de puntaje unificada
  (`scoring.py`), el padrón único de selecciones (`teams.py`), el loader de CSV
  tipado (`csv_io.py`), la separación de la GUI en módulos y la suite de tests.
  Queda reestructurar el repo en carpetas y sumar capturas de la app.
- **Visión v2**: generalizar a un framework multi-deporte/multi-competencia —
  fuentes de datos intercambiables (con modo manual-first), formatos de torneo
  configurables (partido único / llaves / liga) y predictor pluggable por deporte.

## ⚖️ Licencia

[MIT](LICENSE). Proyecto recreativo y educativo: no constituye consejo de
apuestas ni está afiliado a FIFA.
