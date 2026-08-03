# ⚽ Prode Mundial 2026 — modelo predictivo + centro de comando

[![tests](https://github.com/rhinoah/world-cup-predictor/actions/workflows/tests.yml/badge.svg)](https://github.com/rhinoah/world-cup-predictor/actions/workflows/tests.yml)

Modelo estadístico que predice marcadores de fútbol de selecciones, y una app de
escritorio que lo acompaña durante el torneo: pronósticos sugeridos con su "por qué",
recordatorios, carga de resultados, llaves de eliminación y puntaje en vivo de dos
prodes con reglas distintas.

Construido íntegramente en sesiones de **vibe coding** con Claude Code, para jugar
dos pools de predicciones del Mundial 2026 con amigos. **No es una herramienta de
apuestas** — es un proyecto por diversión y aprendizaje.

> **El resultado que importa:** el modelo prometía **0.91 puntos/partido** en
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
| baseline | "1-0 al favorito" (favorito por Elo) | 0.825 |
| v1 *(borrado)* | Poisson con fuerzas ataque/defensa crudas + decay temporal + Dixon-Coles | — |
| v2 | fuerzas ajustadas por rival (punto fijo estilo Maher) + localía | 0.827 |
| **v3 — producción** | **v2 blendeado con Elo dinámico (w=0.6)** | **0.912** |

Los tres números salen de `python run.py analisis` sobre los mismos 9 torneos: la
fila `TOTAL` de `backtest.py` (columna `EV` → v2) y la de `backtest_elo.py`
(columna `w=0.6` → v3, columna `1-0fav` → baseline).

> **Lectura honesta: el modelo de fuerzas solo no le gana al baseline tonto.**
> Contra el baseline que imprime su propio script — el favorito por goles
> esperados — v2 **pierde**: 0.827 contra 0.835. El Elo es el que despega, y por
> eso existe v3. `predict_match_v2.py` no quedó como reliquia: es el motor (carga
> de datos, ajuste de fuerzas, matriz de marcadores) que v3 importa; v3 sólo
> agrega el blend, y son 13 líneas.

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
Copa América **2016–2024**), split temporal estricto, puntuando con 3/1/0.

El tope en 2024 (`MAX_YEAR`) es deliberado y vale la pena explicarlo, porque es un
error que este repo llegó a cometer: el dataset se actualiza solo, así que una vez
terminado el torneo **el Mundial 2026 entró al backtest**. La tabla pasó a tener una
fila `FIFA World Cup 2026` y el total subió de 0.827 a 0.847 — un modelo que parecía
mejor porque estaba midiéndose contra el mismo torneo que se usa para validarlo
out-of-sample. Es exactamente el leakage que el resto del proyecto evita en las
features, colado por la puerta de atrás de la validación.

**En vivo — Mundial 2026 (104 partidos):**

| Métrica | Valor |
|---|---|
| Puntos (3 exacto / 1 dirección) | **91** → **0.88/partido** |
| Marcadores exactos | 11 (11%) |
| Dirección acertada | 58 (56%) |
| Fallados | 35 (34%) |
| Backtest esperado | 0.91/partido ✔ |

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

**1354 tests** (pytest) sobre el modelo y la capa de datos, corriendo en CI para
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
python run.py analisis            # backtests (segundos) + real vs esperado (minutos)
```

Suelto, sin pipeline:

```bash
python -m prode.model.predict_match_v3 "Spain" "Argentina" --neutral   # un partido
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

```
prode/                  el paquete: nada de acá se ejecuta solo, se importa
  paths.py              dónde está cada cosa (el único cálculo de rutas)
  model/                el modelo estadístico
    scoring.py          reglas del prode y la decisión por EV (fuente única)
    elo.py              rating Elo dinámico + blend de lambdas
    predict_match_v2.py el motor: carga, fuerzas ajustadas por rival, matriz de marcadores
    predict_match_v3.py el modelo de PRODUCCIÓN: v2 + Elo (w=0.6)
  tournament/           la estructura del Mundial 2026
    teams.py            padrón único de las 48 selecciones
    groups.py           tablas de grupos con el desempate FIFA
    bracket.py          llaves M73–M104 + tabla oficial de mejores terceros
  data/                 la capa de datos (≠ la carpeta data/ de CSV)
    csv_io.py           lectura/escritura tipada (los dtypes, en un solo lugar)
    results.py          resultados del torneo y búsqueda por cruce
    app_data.py         lo que consume la app: fixture, scoreboard, overrides
  ui/                   la app de escritorio (CustomTkinter)
    app.py              la ventana principal
    bracket_window.py   las ventanas de grupos y de llaves
    tray.py             bandeja, bips e instancia única
    theme.py            paleta y tipografía
    single_instance.py  el lock de una sola ventana

scripts/                lo que se corre, no se importa (`python -m scripts.X`)
  build_features.py     baja el dataset de martj42 y arma las features
  build_pronosticos.py  corre el v3 sobre los partidos pendientes
  liquidar.py           cruza pronósticos con resultados y puntúa
  backfill_ev.py        recalcula el EV as-of (real vs esperado)
  backtest.py           validación temporal del modelo de fuerzas
  backtest_elo.py       ídem para el blend con Elo
  predict_matchday.py   predice la jornada del día
  build_horarios.py     fixture en hora argentina
  build_flags.py        banderas · make_icon.py ícono · parse_thirds.py tabla FIFA

tests/                  la suite pytest (1354 tests)
run.py                  el pipeline: setup / update / analisis
prode_app.py            atajo para abrir la app (16 líneas → prode.ui.app)
*.bat                   lanzar la app · ciclo diario · instalar la automatización
```

Los scripts se invocan como módulo (`python -m scripts.liquidar`) para que la raíz
quede en `sys.path`; `run.py` lo hace por vos. Las rutas son absolutas y salen de
`prode/paths.py`, así que no importa desde qué carpeta se los llame.

## 📚 Datos y créditos

- Resultados históricos de selecciones: [martj42/international_results](https://github.com/martj42/international_results) (~50k partidos).
- Tabla de terceros: plantilla de Wikipedia del Annex C de FIFA, parseada por `parse_thirds.py`.
- Banderas: [flagcdn](https://flagcdn.com/), el CDN de [flagpedia.net](https://flagpedia.net/).
  **No se versionan a propósito.** `build_flags.py` baja los 48 PNG (~12 KB en total,
  ~2 s) dentro de `run.py setup`, y `flags/` está en `.gitignore` con el resto de los
  artefactos regenerables. El motivo no es el peso sino la licencia: este repo es MIT
  y las banderas no lo son — flagpedia las publica como dominio público
  ([sus términos](https://flagpedia.net/terms) las exceptúan explícitamente del resto
  del sitio), pero ese respaldo es una oración en una web, no un archivo de licencia
  auditable. Distribuirlas obligaría a poner una excepción en el `LICENSE` para 48
  binarios que cualquiera baja en dos segundos. Si alguna vez hiciera falta
  versionarlas, la salida correcta es [lipis/flag-icons](https://github.com/lipis/flag-icons),
  que es MIT explícito. Si la descarga falla, la app muestra los nombres sin bandera.
- El ícono (`prode.ico` / `prode.png`) **sí** se versiona: es arte original, dibujado
  por `make_icon.py`, que queda como la fuente regenerable.

Los CSV de datos y los pronósticos personales **no se versionan** (ver
`.gitignore`); todo lo pesado se regenera con `run.py setup`.

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
