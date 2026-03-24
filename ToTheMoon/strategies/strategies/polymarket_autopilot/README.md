# Polymarket Autopilot (Paper Trading)

## Qué es

`ToTheMoon.strategies.strategies.polymarket_autopilot` es un simulador de estrategias para Polymarket que opera **solo en paper trading**.
No envía órdenes reales ni usa dinero real.

## Para quién es

- Developers que quieren experimentar reglas de trading.
- Operadores que quieren observar performance antes de considerar una implementación productiva.

## Problema que resuelve

Permite automatizar un loop simple de:

1. lectura de mercados,
2. generación de señales,
3. ejecución simulada,
4. reporte diario.

Esto evita riesgos financieros durante la iteración de estrategias.

## Estrategias incluidas

- **TAIL**: sigue tendencia cuando `YES >= 0.60` y el volumen muestra spike.
- **BONDING**: contrarian si hay caída abrupta (`<= -10%`) y señal de noticias.
- **SPREAD**: arbitraje si `YES + NO > 1.05`.

## Flujo técnico (MVP)

1. `service.PolymarketAutopilot.fetch_market_data()` consulta Polymarket.
2. `generate_signals()` construye señales TAIL/BONDING/SPREAD.
3. `storage.PaperTradingStore.execute_paper_trade()` registra compras simuladas.
4. `rebalance_take_profit()` cierra ganadores con take-profit.
5. `publish_daily_summary()` escribe reporte para `#polymarket-autopilot`.

## Persistencia

SQLite local con estas tablas:

- `portfolio`
- `positions`
- `trades`
- `market_history`

Rutas por defecto:

- DB: `ToTheMoon/strategies/strategies/polymarket_autopilot/data/paper_trading.db`
- Log: `ToTheMoon/strategies/strategies/polymarket_autopilot/logs/polymarket-autopilot.log`

## Ejecución rápida (ahora con salida visible)

```bash
python -m ToTheMoon.strategies.strategies.polymarket_autopilot.runner
```

Salida esperada (ejemplo):

```text
[polymarket-autopilot] ciclo completado | snapshots=200 | executed_trades=4 | closed_positions=1
[polymarket-autopilot] resumen guardado en: ToTheMoon/strategies/strategies/polymarket_autopilot/logs/polymarket-autopilot.log
```

## Modos de ejecución

### 1) Un ciclo único (default)

```bash
python -m ToTheMoon.strategies.strategies.polymarket_autopilot.runner --mode once
```

### 2) Scheduler diario (08:00)

```bash
python -m ToTheMoon.strategies.strategies.polymarket_autopilot.runner --mode scheduler
```

### 3) Cambiar carpeta base (data/logs)

```bash
python -m ToTheMoon.strategies.strategies.polymarket_autopilot.runner --base-path /tmp/polymarket-autopilot
```

## Troubleshooting

- Si parece que “no hace nada”, revisa stdout: el runner ahora imprime estado al finalizar.
- Si falla la red/API, el comando termina con exit code `1` y muestra el error.
- Verifica que exista escritura en el `--base-path` configurado.

## Seguridad

- Paper trading únicamente.
- Sin órdenes reales.
- Sin uso de capital real.
