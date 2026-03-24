# Polymarket Autopilot (Paper Trading)

## Ubicación correcta

Este módulo vive en:

`TOTHEMOON/STRATEGIES` (ruta real del repo: `ToTheMoon/strategies/polymarket_autopilot`).

## Qué es

`ToTheMoon.strategies.polymarket_autopilot` es un simulador para Polymarket en **paper trading únicamente**.
No envía órdenes reales ni usa dinero real.

## Qué resuelve

Automatiza un loop de simulación para evaluar estrategias sin riesgo de capital:

1. fetch de mercados,
2. señales,
3. ejecución simulada,
4. resumen operativo.

## Estrategias

- **TAIL**: tendencia (`YES >= 0.60`) + spike de volumen.
- **BONDING**: contrarian en caída fuerte (`<= -10%`) con señal de noticias.
- **SPREAD**: arbitraje cuando `YES + NO > 1.05`.

## Persistencia

- DB SQLite: `ToTheMoon/strategies/polymarket_autopilot/data/paper_trading.db`
- Log: `ToTheMoon/strategies/polymarket_autopilot/logs/polymarket-autopilot.log`

## Ejecución rápida (simulación larga por defecto)

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner
```

Ahora el modo default corre **180 días** de simulación (`--simulation-days 180`) y deja resumen con ventana larga.

## Modos

### 1) Simulación puntual larga (default)

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner --mode once --simulation-days 180
```

También puedes correr trimestre:

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner --mode once --simulation-days 90
```

### 2) Scheduler diario

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner --mode scheduler
```

### 3) Cambiar base de data/logs

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner --base-path /tmp/polymarket-autopilot
```

## Salida esperada

```text
[polymarket-autopilot] simulación completada | days=180 | snapshots=36000 | executed_trades=... | closed_positions=...
[polymarket-autopilot] resumen guardado en: ToTheMoon/strategies/polymarket_autopilot/logs/polymarket-autopilot.log
```

## Nota sobre resultados 0 trades

Si aparece `executed_trades=0` en una corrida, puede ser normal por estado del mercado o umbrales actuales.
Aun así la simulación ya procesa ventana larga (90/180 días) y deja trazabilidad en DB/log.

## Seguridad

- Paper trading only.
- No real-money execution.
- No private-key signing.
