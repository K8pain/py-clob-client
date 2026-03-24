# ToTheMoon MVP (paper trading)

## 1) Qué se construyó
- **Feature**: prototipo de estrategia automática de paper trading para Polymarket.
- **Usuario objetivo**: traders cuantitativos que quieren validar lógica antes de arriesgar capital real.
- **Problema**: probar hipótesis de mean reversion en mercados "Up or Down" sin ejecutar órdenes reales.
- **Cómo funciona**:
  1. Descubre mercados activos de crypto (Bitcoin, Ethereum, Solana) desde CLOB.
  2. Filtra mercados "UP/DOWN" y extrae token `YES`.
  3. Si precio `YES < 0.40`, simula compra de $10.
  4. Si precio `YES > 0.60`, simula venta y calcula P/L.
  5. Activa circuit breaker tras 3 pérdidas consecutivas.
  6. Persiste estado y trades en JSON.

## 2) UX / flujo de uso
- **Happy flow**: ejecutar `run_once()` cada 15 min (cron), revisar `ToTheMoon/paper_trades.json` y `ToTheMoon/state.json`.
- **Alternative flow**: si no hay mercados elegibles o no hay señal, no se genera trade.
- **MVP**: sin UI visual todavía; salida en archivos JSON para inspección rápida.

## 3) Necesidades técnicas
- Reutiliza `py_clob_client.ClobClient` para descubrimiento y precio midpoint.
- No introduce DB ni servicios externos adicionales.
- Diseño simple orientado a funciones/métodos pequeños:
  - descubrimiento de mercado
  - normalización de token YES
  - evaluación de señal
  - persistencia de estado/trades

## 4) Testing y seguridad
- Unit tests para:
  - filtro de mercados
  - extracción de token YES
  - circuit breaker por pérdidas
- Seguridad:
  - no usa API keys ni firma órdenes
  - no ejecuta trading real

## 5) Plan y DoD
- **MVP completado**:
  - Estructura `ToTheMoon/strategies`
  - Estrategia base mean reversion en paper trading
  - Persistencia local JSON
- **Siguiente milestone**:
  - scheduler CLI para cron
  - dashboard HTML con P/L total, win rate y últimos trades

## 6) Ripple effects
- Documentación nueva en este folder.
- No afecta módulos de trading real existentes.

## 7) Contexto más amplio
- Limitación: heurística de "uptrend" todavía pendiente (se puede estimar con ventana de precios).
- Extensiones futuras:
  - gestión multi-posiciones
  - métricas por activo
  - integración de dashboard web


## Operación y rate limits

Para el inventario completo de programas de `ToTheMoon`, la guía de ejecución sin API key y la estrategia de cumplimiento de rate limits públicos/privados, ver `ToTheMoon/RATE_LIMITING_AND_OPERATIONS.md`.
