# Step by step: cómo trabajar con las estrategias ToTheMoon

## Objetivo
Esta guía explica **paso a paso** cómo ejecutar, validar y extender las estrategias ubicadas en `ToTheMoon/strategies/automated_paper_v1_web/`.

---

## Paso 1: prepara el entorno
1. Entra al repo:
   ```bash
   cd /workspace/py-clob-client
   ```
2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Verifica import del paquete:
   ```bash
   PYTHONPATH=. python -c "from ToTheMoon import MeanReversionPaperStrategy, StrategyConfig; print('ok')"
   ```

---

## Paso 2: entiende la estructura
- `ToTheMoon/strategies/automated_paper_v1_web/mean_reversion.py`  
  Estrategia principal (paper trading).
- `ToTheMoon/state.json`  
  Estado persistente (posiciones abiertas, pérdidas consecutivas, circuit breaker).
- `ToTheMoon/paper_trades.json`  
  Historial de trades simulados.

---

## Paso 3: ejecución manual (1 ciclo)
Ejecuta un ciclo de evaluación para descubrimiento + señales:

```bash
PYTHONPATH=. python - <<'PY'
from ToTheMoon import MeanReversionPaperStrategy, StrategyConfig

strategy = MeanReversionPaperStrategy(StrategyConfig())
trades = strategy.run_once(page_limit=3)
print(f"Trades generados: {len(trades)}")
for t in trades:
    print(t)
PY
```

> Esto **no** envía órdenes reales. Solo escribe JSON local.

---

## Paso 4: programar cada 15 minutos (cron)
1. Abre cron:
   ```bash
   crontab -e
   ```
2. Agrega una línea como esta (ajustando rutas):
   ```cron
   */15 * * * * cd /workspace/py-clob-client && PYTHONPATH=. python -c "from ToTheMoon import MeanReversionPaperStrategy, StrategyConfig; MeanReversionPaperStrategy(StrategyConfig()).run_once()"
   ```

---

## Paso 5: validar comportamiento
1. Corre tests:
   ```bash
   PYTHONPATH=. pytest -q tests/tothemoon/test_mean_reversion.py
   ```
2. Revisa archivos generados:
   - `ToTheMoon/state.json`
   - `ToTheMoon/paper_trades.json`
3. Verifica circuit breaker:
   - si `consecutive_losses >= 3`, `circuit_breaker_active` debe ser `true`.

---

## Paso 6: extender una estrategia nueva
1. Crea un nuevo módulo dentro de `ToTheMoon/strategies/automated_paper_v1_web/`.
2. Mantén separación clara:
   - descubrimiento
   - señal
   - ejecución paper
   - persistencia
3. Exporta la estrategia en:
   - `ToTheMoon/strategies/automated_paper_v1_web/__init__.py`
   - (opcional) `ToTheMoon/__init__.py`
4. Agrega tests unitarios en `tests/tothemoon/`.

---

## Paso 7: checklist de seguridad antes de evolucionar a real trading
- [ ] Mantener paper trading por defecto.
- [ ] Validar límites de riesgo por mercado/activo.
- [ ] Añadir manejo robusto de errores de red y reintentos.
- [ ] Auditar claves/API creds fuera del código.
- [ ] Revisar impacto regulatorio/compliance según jurisdicción.

---

## Notas de diseño
- Este MVP prioriza simplicidad y trazabilidad.
- Se favorecen componentes pequeños y testeables.
- La lógica de "uptrend" aún es una mejora futura.
