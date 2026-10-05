# 0013. Estrategia de pruebas

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: B (reversible)

## Decisión
- **Pruebas automáticas** (`pytest` en el núcleo y verificación de tipos en la app) en cada cambio, con los proveedores *simulados*. Son gratis.
- **Pruebas reales** contra Anthropic y Deepgram: tienen costo (centavos), así que se corren **solo avisando antes al usuario**.
- **Lista manual** de pruebas de voz en Android y en iPhone.

## Consecuencias
Cada adaptador tendrá pruebas contra su puerto con dobles de prueba (mocks).
