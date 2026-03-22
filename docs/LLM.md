# LLM Document — Guía para asistentes sobre `py-clob-client`

## Objetivo
Este documento condensa el contexto mínimo para que un LLM contribuya al repo con cambios consistentes, pequeños y seguros.

---

## 1) Definir lo que se está construyendo

### Qué es la aplicación/feature
`py-clob-client` es un SDK Python para consumir la API CLOB de Polymarket con soporte de:
- lectura de mercado,
- autenticación L0/L1/L2,
- creación/firma/publicación de órdenes,
- flujos RFQ.

### Para quién es
- Desarrolladores de bots y automatización de trading.
- Equipos backend que requieren integración programática con CLOB.

### Problema que resuelve
- Simplifica auth+firma+payloads para operar en CLOB sin reimplementar criptografía ni contratos de endpoints.

### Cómo debe funcionar (modelo mental rápido)
- Instancia `ClobClient`.
- Resuelve modo de auth según parámetros disponibles.
- Llama métodos de lectura o trading.
- Para trading, construye órdenes con `OrderBuilder` y firma headers según nivel.

### Conceptos y relaciones
- `client.py`: fachada principal.
- `headers/headers.py`: headers L1/L2.
- `signing/`: primitives de firma.
- `order_builder/`: redondeo + signed order.
- `rfq/`: operaciones RFQ.
- `clob_types.py`: dataclasses y tipos compartidos.

**Principio operativo:** si puedes resolver algo en una función/helper existente, evita introducir nueva clase.

---

## 2) UX (DX) esperada para contribuciones

### User stories de contribución (happy path)
1. Como usuario del SDK, quiero nuevos métodos con la misma convención de nombres y argumentos existentes.
2. Como mantenedor, quiero tests unitarios para cada regla nueva (rounding, params, headers).
3. Como integrador, quiero ejemplos simples en `examples/` para copiar/pegar.

### Flujos alternativos
- Si un endpoint requiere auth nueva, mantener compatibilidad con L0/L1/L2 sin romper métodos existentes.
- Si hay cambios de serialización, mantener orden/canonicalización para firmas.

### Estructura de API pública
- Preferir ampliar `ClobClient` o `client.rfq` antes de crear un nuevo entry point.
- Evitar renombrados de métodos públicos salvo breaking release explícito.

---

## 3) Necesidades técnicas para implementar bien

### Reglas de diseño
- Funciones pequeñas y enfocadas.
- Inyección de dependencias vía argumentos cuando aplique.
- Usar dataclasses/tipos existentes antes de crear nuevos objetos.
- Reusar `http_helpers` y `headers` para evitar divergencia.

### Detalles importantes
- Tick sizes válidos: `"0.1"`, `"0.01"`, `"0.001"`, `"0.0001"`.
- `BUY/SELL` impacta cálculo maker/taker y assets RFQ.
- L2 depende de `ApiCreds` + firma de request.

### Dependencias externas
- `py_order_utils` (firmas/modelos de orden).
- `py_builder_signing_sdk` (builder config).

### Edge cases obligatorios
- Inputs inválidos (`side`, `tick_size`, ids vacíos).
- Sin liquidez en market order (`FOK` no matchea).
- Fail de red/timeouts.
- Credenciales ausentes para endpoint autenticado.

---

## 4) Testing y seguridad

### Checklist mínimo por cambio
- [ ] Test unitario del comportamiento nuevo.
- [ ] Test de no-regresión si se toca rounding/auth.
- [ ] Actualización de ejemplo o doc pública.

### Seguridad
- No imprimir secretos (private key, api_secret).
- Preservar serialización determinística en payloads firmados.
- Mantener validaciones tempranas de auth por nivel.

---

## 5) Plan de trabajo recomendado para el LLM

1. Leer método análogo existente.
2. Implementar cambio mínimo en módulo correcto.
3. Añadir/ajustar tests en `tests/`.
4. Ejecutar suite relevante.
5. Actualizar docs/examples.
6. Verificar diff corto y coherente.

### Riesgos principales
- Breaking changes en API externa.
- Cambios silenciosos de precisión numérica.

### Ruta alternativa
- Si endpoint nuevo es incierto, introducir helper aislado + feature flag simple y documentar limitaciones.

### DoD
- Código consistente con estilo actual.
- Tests verdes relevantes.
- Documentación actualizada.

---

## 6) Ripple effects de cambios

Si cambias API pública del cliente, también revisar:
- `README.md` (usage snippets).
- `examples/*.py` relacionados.
- tests de headers/signing/order_builder/rfq.
- notas de release (si aplica).

---

## 7) Contexto ampliado

### Limitaciones conocidas
- SDK especializado en Polymarket CLOB.
- Tipado parcial de respuestas remotas (dicts heterogéneos).

### Extensiones futuras
- Cliente más estrictamente tipado para respuestas.
- Retries configurables por endpoint.
- Mejoras de observabilidad (logs estructurados, métricas).

### Moonshots
- Generación de SDK desde especificación API.
- Simulador offline de ejecución para validar estrategias.
