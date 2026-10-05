# 0018. Convenciones del repositorio

- Estado: Aprobada (decisión de tipo B tomada por Claude Code dentro del marco aprobado)
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: B (reversible)

## Decisión
- **Estructura:** `nucleo/` (Python), `app/` (app web), `docs/` (decisiones, supuestos y estado) y `datos/` (información del usuario, fuera de git).
- **Idioma:** los identificadores del código van en inglés, por compatibilidad con librerías y herramientas; los comentarios, la documentación y todo lo que ve el usuario van en español.
- **Herramientas del núcleo:** `uv` (Python 3.13 y dependencias), `pytest` (pruebas), `ruff` (estilo y errores comunes), FastAPI y Uvicorn (servidor) y `pydantic-settings` (configuración).
- **Herramientas de la app:** Vite y TypeScript en modo estricto, sin framework de interfaz por ahora.
- **Puerto local:** 8710.

## Cómo revertirla
Son convenciones; se cambian con un ajuste en el repositorio.
