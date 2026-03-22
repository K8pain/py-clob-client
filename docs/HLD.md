# HLD — py-clob-client

## 1) Definición de lo que estamos construyendo

### ¿Qué es?
`py-clob-client` es un SDK en Python para interactuar con el Central Limit Order Book (CLOB) de Polymarket. Expone una API de alto nivel para consultar mercado, construir/firmar órdenes, autenticarse por niveles y operar RFQ (Request For Quote). 

### ¿Para quién es?
- Integradores de trading algorítmico en Python.
- Equipos que necesitan automatizar consulta de precios, colocación/cancelación de órdenes y workflows de cartera/allowances.
- Desarrolladores que operan wallets EOA o wallets proxy/funder.

### ¿Qué problema resuelve?
- Oculta complejidad de autenticación multicapa (L0/L1/L2).
- Estandariza firma de mensajes/órdenes y headers para endpoints protegidos.
- Evita duplicar lógica de redondeo de precios/tamaños (tick size) y normalización de payloads.

### ¿Cómo funciona (vista macro)?
1. `ClobClient` centraliza configuración (`host`, `chain_id`, `signer`, credenciales API).
2. Según el modo de auth, genera headers L1 o L2 para cada request.
3. `OrderBuilder` construye órdenes firmadas con reglas de redondeo según `tick_size`.
4. `http_helpers` ejecuta GET/POST/DELETE.
5. `rfq.RfqClient` agrega el flujo RFQ sobre el cliente principal.

### Conceptos principales y relaciones
- **ClobClient**: fachada principal.
- **Signer**: encapsula private key + chain para firma.
- **ApiCreds**: API key/secret/passphrase para auth L2.
- **OrderBuilder**: genera `SignedOrder` y calcula importes maker/taker.
- **RfqClient**: subcliente dependiente de `ClobClient` para RFQ.
- **Tipos (`clob_types`, `rfq_types`)**: contrato de entrada/salida (dataclasses).

**Relación clave:** `ClobClient` compone `Signer` + `OrderBuilder` + `RfqClient`, e inyecta esos componentes en los flows de red y firma.

### Notas de diseño
- **Diseño e implementación en paralelo:** el repo prioriza ejemplos ejecutables y tests unitarios para validar incrementos pequeños.
- **Distilling the model:** el diseño favorece utilidades reutilizables (`http_helpers`, `headers`, `order_builder/helpers`) sobre lógica duplicada.
- **Zoom out / zoom in (MVP):** el MVP es “leer mercado + firmar orden + postear orden”; RFQ y builder trades extienden ese core.

---

## 2) Diseño de experiencia de usuario (DX)

> Este SDK no tiene UI gráfica; su “UX” principal es la API Python y los ejemplos.

### User stories
#### Happy flows
1. Como dev, quiero instanciar `ClobClient` en L0 para consultar `get_ok`, `get_server_time`, orderbooks y mercados.
2. Como trader, quiero crear/derivar API creds y operar en L2 con `post_order`, `cancel`, `get_orders`.
3. Como maker/taker, quiero usar `client.rfq` para crear request, cotizar, aceptar/aprobar.

#### Alternative flows / edge flows
- Wallet proxy: se configura `signature_type` y `funder`.
- Falta de liquidez: market order puede fallar en FOK.
- Tick size dinámico: el cliente debe resolver y cachear tamaño de tick antes de firmar.
- Credenciales inválidas: endpoints L2 deben rechazar antes de request inválida.

### Impacto estructural (navegación del SDK)
- Punto de entrada único: `py_clob_client/client.py`.
- Módulos de soporte claramente aislados:
  - `headers/` para auth.
  - `order_builder/` para cálculo + firma.
  - `rfq/` para feature específica.
  - `http_helpers/` para transporte.

### Wireframe textual (flujo principal)
```text
[Dev Script]
   -> ClobClient(host, key?, chain_id?, creds?)
      -> (opcional) create_or_derive_api_creds()
      -> create_order() / create_market_order()
      -> post_order()
      -> get_orders() / cancel()
```

---

## 3) Necesidades técnicas

### Componentes técnicos críticos
- **Auth por niveles**
  - L0: endpoints públicos.
  - L1: firma de headers con wallet.
  - L2: API key + firma HMAC/EIP para endpoints privados.
- **Construcción de órdenes**
  - Rounding por `tick_size` con `ROUNDING_CONFIG`.
  - Conversión a decimales de token y construcción `OrderData`.
- **RFQ**
  - Payloads con `assetIn/assetOut`, `amountIn/amountOut`.
  - Serialización JSON compacta para firma estable.

### DB / tablas
- No hay base de datos local en este repo. Es un cliente SDK puro.

### Diseño de código y patrones
- Predomina enfoque funcional + dataclasses (simple y testeable).
- Clases cuando modelan estado relevante (`ClobClient`, `OrderBuilder`, `RfqClient`).
- Separación de creación vs uso:
  - Se crea `Signer/OrderBuilder` en inicialización.
  - Se usan en métodos de operación sin estado compartido complejo.

### Dependencias relevantes
- `py_order_utils` para firma y estructura de órdenes.
- `py_builder_signing_sdk` para configuración de builder trades.
- Stack estándar de requests/JSON/typing.

### Edge cases a documentar
- Error de red / timeout en helpers HTTP.
- Firma inválida por chain_id incorrecto.
- Tick size fuera de catálogo soportado.
- FOK sin profundidad suficiente en orderbook.

---

## 4) Testing y seguridad

### Cobertura objetivo
- Mantener cobertura sobre:
  - Helpers de headers/signing.
  - Helpers de order_builder (rounding/conversion).
  - Parsing de query params y payloads RFQ.

### Tipos de test
- Unit tests (ya presentes en `tests/`).
- Regression tests para reglas de redondeo y serialización.
- Smoke tests manuales con `examples/` para integración básica.

### Side-effects potenciales
- Cambios en headers pueden romper todos los endpoints autenticados.
- Cambios en rounding impactan precios efectivos y fills.
- Cambios en contratos/config afectan addresses on-chain.

### Seguridad para ship
- Nunca loggear private keys ni secrets.
- Mantener serialización determinística para firmas.
- Validar inputs críticos (`side`, `tick_size`, `chain_id`).

### Impacto de seguridad
- Alto: firma de órdenes y credenciales de API.
- Recomendación: auditoría ligera cuando se modifiquen módulos de firma/auth.

---

## 5) Plan de trabajo (para evolución del SDK)

### Estimación macro
- Iteración pequeña de feature/documentación: 0.5–2 días.
- Cambios de auth/firma o nuevos endpoints: 2–5 días.

### Pasos sugeridos
1. Definir contratos de entrada/salida (dataclasses) — 0.5 día.
2. Implementar método en `ClobClient` o `RfqClient` — 0.5 día.
3. Añadir tests unitarios/regresión — 0.5–1 día.
4. Añadir ejemplo en `examples/` + docs — 0.5 día.

### Milestones
- M1: interfaz pública estable.
- M2: cobertura de tests para paths críticos.
- M3: ejemplo funcional y release.

### Migraciones
- No aplica (sin DB).

### Riesgos y alternativas
- **Riesgo principal:** cambios upstream en API CLOB.
- **Alternativa:** encapsular endpoints/serialización para aislar breaking changes.

### Requerido vs opcional (DoD)
- Requerido: método funcional + test + ejemplo + docs.
- Opcional: optimizaciones de cache y mejoras de ergonomía.

---

## 6) Ripple effects

- Actualizar README y ejemplos cuando cambie la API pública.
- Alinear `CONTRIBUTING.md` si cambia forma de test/release.
- Comunicar breaking changes de firma o tipos.
- Verificar compatibilidad con integraciones externas (bots, backends de trading).

---

## 7) Contexto amplio

### Limitaciones actuales
- Acoplamiento a especificación CLOB actual.
- Poca abstracción multi-exchange (está centrado en Polymarket).
- Errores de red dependen del comportamiento de helpers HTTP.

### Extensiones futuras
- Retries/backoff configurables.
- Tipado más estricto de respuestas API.
- Middleware de observabilidad (tracing/metrics).
- Simulación local de fills para validación pre-trade.

### Moonshot ideas
- Modo “strategy sandbox” para backtesting con snapshots.
- Generación automática de cliente tipado desde spec OpenAPI (si existiera).
