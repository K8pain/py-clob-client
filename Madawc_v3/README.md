# Madawc_v3 (MVP) — Market Maker Paper Trading Simulator

Madawc_v3 es un simulador **paper trading** orientado a validar una operativa de **market making en mercados binarios** (YES/NO) antes de conectar datos reales o ejecución live.

> Ejecuta así:
>
> ```bash
> python -m Madawc_v3.launcher --all --factory Madawc_v3.factory:build_bot
> ```

---

## 1) Qué es, para quién y qué problema resuelve

### Qué es
Un motor de simulación determinista que cotiza dos lados (YES/NO), evalúa PnL por componentes y exporta reportes.

### Para quién
Para operador/quant/dev que quiere validar si el modelo de maker está capturando edge por:
- spread,
- full-set (merge / split-sell),
- rebates / rewards,
- control de inventario.

### Problema que resuelve
Evita tomar decisiones con PnL “mezclado”. Separa explícitamente:
- `spread_pnl`
- `merge_pnl`
- `split_sell_pnl`
- `taker_fees`
- `rebate_income`
- `reward_income`
- `directional_mtm`

Así puedes distinguir PnL de **proveer liquidez** versus PnL **direccional residual**.

---

## 2) Flujo de uso (step by step)

## Paso 0 — Requisitos
No requiere APIs privadas ni llaves. Solo Python.

## Paso 1 — Ejecutar simulación completa
```bash
python -m Madawc_v3.launcher --all --factory Madawc_v3.factory:build_bot
```

## Paso 2 — Revisar salida en consola
El launcher imprime un JSON con métricas agregadas.

## Paso 3 — Revisar artefactos
Se generan en `var/madawc_v3/reports/`:
- `ticks.csv`: trazabilidad ciclo a ciclo (mids, quotes, inventario neto)
- `simulation_summary.json`: resumen final de PnL por componente

## Paso 4 — Ajustar configuración
Todos los parámetros de la versión 3.0 están hardcodeados en `Madawc_v3/config.py`.

## Paso 5 — Re-ejecutar y comparar
Repetir corrida después de ajustes para evaluar sensibilidad de resultados.

---

## 3) Parámetros más importantes de configuración (prioridad de tuning)

> Todos viven en `Madawc_v3/config.py`.

## P0 — Economics core (impacto directo en rentabilidad)

### `FEE_RATE_BPS`
Fee base usada en `fee_equivalent = notional * feeRate * p * (1-p)`.
- Si sube, aumenta coste esperado de salidas taker.
- Afecta también estimación de rebates/rewards (vía mismo equivalente económico).

### `ADVERSE_SELECTION_BUFFER`
Margen extra para protegerte contra quotes viejos y flujo informado.
- Alto = menos fills, potencialmente mayor calidad.
- Bajo = más fills, mayor riesgo de edge negativo.

### `LATENCY_BUFFER`
Protección por riesgo de latencia/cancelación tardía.
- Útil cuando hay micro-movimientos más rápidos que la reposición.

### `REBATE_EXPECTED` y `REWARD_EXPECTED`
Se restan del spread mínimo neto requerido.
- Mayor valor esperado permite cotizar más tight manteniendo break-even.

### `MIN_SPREAD_FLOOR`
Piso absoluto de spread aunque el cálculo neto resulte menor.
- Evita “sobre-ajuste” por supuestos optimistas.

## P0 — Inventario y sesgo

### `INVENTORY_SKEW_FACTOR`
Controla cuánto mueve el reservation price ante desbalance inventario.
- Alto: rebalancea más agresivo.
- Bajo: inventario puede desviarse más tiempo.

### `MAX_ABS_INVENTORY`
Guardrail conceptual de riesgo inventario (en MVP aún no bloquea ejecución).
- Recomendado mantenerlo coherente con `SIMULATION_SIZE`.

## P0 — Full-set logic

### `ENABLE_PAIR_MERGE` + `MERGE_EDGE_MIN`
Activa captura de edge cuando `YES + NO < 1`.
- Umbral define cuándo considerar “mergeable edge”.

### `ENABLE_SPLIT_SELL` + `SPLIT_SELL_EDGE_MIN`
Activa lógica espejo cuando `YES + NO > 1` para inventario pre-split.

## P1 — Dinámica de simulación

### `SIMULATION_CYCLES`
Cantidad de ciclos simulados.
- Más ciclos = mayor robustez de la muestra.

### `SIMULATION_VOLATILITY`
Rango de shock por ciclo.
- Subirlo incrementa stress de quotes y sensibilidad de inventario.

### `SIMULATION_SIZE`
Tamaño nocional por simulación de fill.
- Escala directamente el impacto monetario por trade.

### `TAKER_FRACTION`
Fracción probabilística de salidas con coste taker.
- Mayor valor castiga más el PnL neto.

---

## 4) Funcionamiento detallado (internals)

## 4.1 Launcher y factory
- `launcher.py` parsea flags, exige `--all`, carga `factory` y ejecuta simulación.
- `factory.py` retorna `MadawcV3Bot` (contrato simple compatible con launcher).

## 4.2 Estado y modelos
- `Inventory`: posiciones YES/NO + cash
- `BotMetrics`: acumuladores de PnL por fuente
- `MarketTick`: snapshot por ciclo

## 4.3 Quoting engine (`strategy.py`)
1. Calcula fee equivalente en función de precio binario.
2. Calcula `minimum_net_spread`:
   - coste esperado de salida taker
   - + adverse buffer
   - + latency buffer
   - - rebate esperado
   - - reward esperada
   - con piso `MIN_SPREAD_FLOOR`
3. Calcula `reservation_price` con skew por inventario.
4. Construye quotes two-sided para YES/NO.

## 4.4 Simulación (`bot.py`)
Por ciclo:
1. Genera nuevo `mid` con shock controlado por volatilidad.
2. Construye quotes con estrategia.
3. Suma PnL por spread maker round-trip simulado.
4. Suma rebates/rewards esperados.
5. Aplica penalización de taker según `TAKER_FRACTION`.
6. Evalúa edge de merge/split y acumula cuando supera umbral.
7. Exporta tracking en `ticks.csv`.

Al final:
- calcula `directional_mtm` residual,
- arma `simulation_summary.json`.

---

## 5) Seguridad, testing y validación operativa

- No envía órdenes reales.
- No usa credenciales privadas.
- Suite de tests en `tests/madawc_v3/test_madawc_v3.py` cubre:
  - fórmulas core,
  - launcher,
  - flujo principal,
  - umbral de coverage >85% (módulos core).

Comandos recomendados:
```bash
pytest -q tests/madawc_v3
python -m Madawc_v3.launcher --all --factory Madawc_v3.factory:build_bot
```

---

## 6) Limitaciones actuales (MVP)

1. Los precios son sintéticos (no conectados a book real).
2. No hay matching real ni partial fills realistas de microestructura.
3. `MAX_ABS_INVENTORY` está definido pero no fuerza hard-stop aún.

---

## 7) Próximos pasos recomendados

1. Conectar book/trades reales (paper mode) manteniendo la contabilidad actual.
2. Activar guardas duras de inventario y emergency exit basado en riesgo.
3. Calibrar `INVENTORY_SKEW_FACTOR` y buffers con data real.
4. Añadir benchmark por mercado (rebate/reward efficiency por unidad de riesgo).
