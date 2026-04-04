# KORLIC_v2

Este directorio contiene un clon completo del paquete `Korlic` dentro de `KORLIC_v2/Korlic_v2`.

## Lanzador dentro de KORLIC_v2

Ejecuta el lanzador desde esta carpeta (`cd KORLIC_v2`) con:

```bash
python -m Korlic_v2.launcher --all --factory Korlic_v2.factory:build_bot --keep-running
```

Opciones operativas rápidas:

- Añadir una pausa ligera entre pasos del ciclo para bajar picos de CPU/RAM:

```bash
KORLIC_CYCLE_STEP_SLEEP_SECONDS=0.05 python -m Korlic_v2.launcher --all --factory Korlic_v2.factory:build_bot --keep-running
```

- Limpiar estado antes de relanzar (DB + logs + reportes runtime):

```bash
python scripts/reset_runtime_state.py
```

## Contrato funcional solicitado

Se incluye el contrato completo en:

- `KORLIC_v2/btc_5m_polymarket_paper_trading_bot.feature`
