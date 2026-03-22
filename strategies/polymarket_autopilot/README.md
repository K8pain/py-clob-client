# Polymarket Autopilot

## Qué es

Un simulador de estrategias para Polymarket que hace **paper trading únicamente**.

## Para quién es

Para developers u operadores que quieren evaluar ideas de trading sin arriesgar dinero real.

## Qué problema resuelve

Permite probar tres heurísticas simples sobre mercados activos:

- **TAIL**: seguir tendencias fuertes cuando `YES > 60%` y hay spike de volumen.
- **BONDING**: buscar reversión tras caídas abruptas `>10%` ligadas a noticias.
- **SPREAD**: detectar desalineación cuando `YES + NO > 1.05`.

## Cómo funciona

1. Lee mercados desde la API de Polymarket.
2. Normaliza snapshots del mercado.
3. Genera señales de paper trading.
4. Guarda portfolio, posiciones, trades e historial en SQLite.
5. Escribe un resumen diario a las 8:00 AM en el log `#polymarket-autopilot`.

## Persistencia

- Base de datos: `strategies/polymarket_autopilot/data/paper_trading.db`
- Log diario: `strategies/polymarket_autopilot/logs/polymarket-autopilot.log`

## Seguridad

- Nunca envía órdenes reales.
- Nunca usa dinero real.
- Toda ejecución es simulada.

## Ejecución rápida

```bash
python -m strategies.polymarket_autopilot.runner
```
