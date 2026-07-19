# CLAUDE.md — Modelo predictivo para prode Mundial 2026

## Objetivo del proyecto

Armar un modelo basado en datos para participar de un **prode (pool de predicciones) del Mundial 2026**. La idea no es solo "tirar un pronóstico", sino estimar probabilidades de resultados de forma fundamentada y, después, **optimizar las predicciones según el sistema de puntaje del prode** (ver sección "Reglas del prode" — está pendiente de definir).

Trabajo en español rioplatense (voseo). El código y los comentarios pueden estar en inglés o español indistintamente; preferí nombres de variables en inglés.

## Estado actual

Ya existe `build_features.py`, que:

1. Descarga los CSV del dataset de selecciones de **martj42** (`results.csv`, `goalscorers.csv`, `shootouts.csv`, `former_names.csv`) a `./data/`.
2. Construye una **tabla larga** (`output/team_matches.csv`): una fila por equipo por partido, con `gf`, `ga`, `gd`, `result` (W/D/L), `points`, `venue` (home/away/neutral), `is_competitive`.
3. Genera un **resumen por selección** (`output/team_features.csv`): partidos, win rate, puntos por partido, promedio de goles a favor/en contra, y forma de los últimos 10 partidos.
4. Tiene helpers ya escritos: `recent_form(...)` (sin data leakage) y `head_to_head(...)`.

## Fuentes de datos

| Dataset | Qué trae | Link |
|---|---|---|
| martj42 international_results | ~50k partidos de selecciones, goleadores, penales | https://github.com/martj42/international_results |
| FIFA Ranking (Kaggle) | ranking histórico por fecha — **feature clave a sumar** | buscar "FIFA ranking" en Kaggle |
| StatsBomb Open Data | eventos jugada a jugada (tiros, tarjetas, xG); cobertura selectiva, incluye Mundiales 2018/2022 | https://github.com/statsbomb/open-data |
| FBref vía soccerdata | stats a nivel partido (tarjetas, tiros, xG) | https://github.com/probberechts/soccerdata |

### Esquema de `results.csv`
`date, home_team, away_team, home_score, away_score, tournament, city, country, neutral`

## Reglas que el modelo TIENE que respetar

- **Nada de data leakage.** Cualquier feature para predecir un partido se calcula únicamente con datos *anteriores* a la fecha de ese partido. El helper `recent_form()` ya está diseñado así (`date < as_of`); seguí ese patrón para todo lo demás (Elo, ranking, h2h, etc.).
- **Nombres de selecciones.** El dataset usa el nombre *actual* de cada equipo. Si hace falta cruzar con otras fuentes, usar `former_names.csv` para mapear. Cuidado con casos tipo "United States" vs "USA", "South Korea" vs "Korea Republic", etc. — normalizar nombres entre datasets antes de joinear.
- **Cancha neutral.** En el Mundial casi todos los partidos son en sede neutral para ambos (salvo anfitriones: USA, México, Canadá). El feature de localía tiene que contemplar `venue == "neutral"`, no asumir home/away.
- **Amistosos vs oficiales.** `is_competitive` ya distingue. Considerar ponderar distinto (los amistosos pesan menos) o filtrarlos según el caso.

## Enfoques de modelado sugeridos (a discutir antes de codear)

Prefiero **discutir el approach punto por punto antes de escribir el código final.** Algunas opciones, de menor a mayor complejidad:

1. **Elo / rating dinámico** como baseline. Simple, interpretable, buen predictor por sí solo. Sirve además como feature para los modelos siguientes.
2. **Poisson / Dixon-Coles** para predecir el marcador exacto (cuenta de goles por equipo). Permite derivar probabilidades de 1X2, over/under, y resultado exacto — útil si el prode puntúa marcadores.
3. **Clasificador (1X2)** con gradient boosting (XGBoost/LightGBM) sobre las features: forma reciente, Elo, ranking FIFA, h2h, promedio de goles, etc.
4. **Simulación Monte Carlo del cuadro completo** una vez que tengo probabilidades por partido: simular el bracket N veces para estimar probabilidad de avance/campeón. Esto es lo que al final maximiza el puntaje esperado del prode.

La elección final depende de **cómo puntúa el prode** (ver abajo). El modelo debería optimizar el puntaje esperado bajo esas reglas, no la accuracy cruda.

## Reglas del prode — PENDIENTE DE COMPLETAR

> ⚠️ Esto define qué tiene que optimizar el modelo. Antes de modelar en serio, preguntame por:
> - ¿Se predice resultado exacto (marcador) o solo 1X2 / ganador?
> - ¿Puntos por fase de grupos vs eliminatorias?
> - ¿Bonus por acertar el campeón / goleador / etc.?
> - ¿Se predice todo el bracket de una o partido a partido por fecha?

## Stack y convenciones

- **Python + pandas** para datos; **scikit-learn / XGBoost** para modelado; **matplotlib** para visualización.
- Para validación temporal usar split por fecha (entrenar con pasado, validar con futuro), nunca shuffle aleatorio.
- Mantener el pipeline reproducible: `data/` (crudo) → `output/` (procesado) → notebooks/modelos. No commitear los CSV pesados si esto va a un repo.
- Código claro y comentado; funciones chicas y testeables. Antes de generar documentación final o specs grandes, charlamos el diseño punto por punto.

## Cómo correr lo que ya existe

```bash
pip install pandas
python build_features.py              # baja datos + genera features
python build_features.py --since 2018 # ventana de relevancia más corta
python build_features.py --no-download # usa cache local
```
