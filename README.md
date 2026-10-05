# Azul

Asistente personal por voz, inspirado en J.A.R.V.I.S. Corre en tu portátil y le hablas desde el celular o el PC.

> **Estado:** esqueleto del proyecto (Fase 5). Todavía no conversa; consulta [docs/estado.md](docs/estado.md).

## Cómo iniciarlo

Haz doble clic en **`Iniciar Azul.cmd`**, o ejecuta lo siguiente desde una terminal en esta carpeta:

```
"Iniciar Azul.cmd"
```

Después abre <http://127.0.0.1:8710> en el navegador del portátil.

La primera vez prepara la app web automáticamente.

## Requisitos del equipo

- [uv](https://docs.astral.sh/uv/), que instala Python 3.13 solo para Azul.
- Node.js y npm, para compilar la app web.
- Un archivo `.env`: copia `.env.example` como `.env` y completa las claves. Nunca lo compartas.

## Cómo correr las pruebas

```
cd nucleo
uv run pytest
uv run ruff check .
```

```
cd app
npm run typecheck
```

## Estructura

| Carpeta | Contenido |
|---|---|
| `nucleo/` | Núcleo en Python: configuración, puertos (`core/ports.py`), servidor y pruebas |
| `app/` | App web instalable (TypeScript + Vite) |
| `docs/adr/` | Registro de decisiones de arquitectura |
| `docs/supuestos.md` | Supuestos y requisitos confirmados |
| `docs/estado.md` | En qué fase está el proyecto |
| `datos/` | Tu información (memoria, gasto). No va a git; respáldala aparte |
| `CLAUDE.md` | Las reglas de trabajo de Claude Code en este proyecto |
