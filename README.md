# Azul

Asistente personal por voz, inspirado en J.A.R.V.I.S. Corre en tu portátil y le hablas desde el celular o el PC.

> **Estado:** MVP v0.1. Conversa por voz y texto, recuerda, busca en internet y funciona desde el celular. Detalles en [docs/estado.md](docs/estado.md).

## Uso diario

| Para… | Haz esto |
|---|---|
| **Encender Azul** | Doble clic en **`Iniciar Azul.cmd`**. Deja esa ventana abierta. |
| **Hablarle desde el portátil** | Abre <http://127.0.0.1:8710>, toca 🎤 y habla. |
| **Hablarle desde el celular** | Con Tailscale conectado, abre `https://dell.tailc78da3.ts.net` (o el ícono de Azul en la pantalla de inicio). |
| **Callarlo** | Toca el botón ■ mientras habla. |
| **Respaldar la memoria** | Doble clic en **`Respaldar Azul.cmd`**. Además se respalda solo una vez al día al encenderlo. |
| **Restaurar la memoria** | Cierra Azul y haz doble clic en **`Restaurar Azul.cmd`** (usa el respaldo más reciente, o arrastra un `.zip` sobre el ícono). |

El portátil debe estar encendido y despierto para que Azul responda.

## Requisitos del equipo

- [uv](https://docs.astral.sh/uv/), que instala Python 3.13 solo para Azul.
- Node.js y npm, para compilar la app web.
- [Tailscale](https://tailscale.com), para el acceso desde el celular.
- Un archivo `.env`: copia `.env.example` como `.env` y completa las claves. Nunca lo compartas.

## Cómo migrar a otro equipo

1. Clona el repositorio de GitHub, o copia la carpeta del proyecto.
2. Crea `.env` con tus claves.
3. Copia el último respaldo (`OneDrive\Azul\respaldos`) y haz doble clic en `Restaurar Azul.cmd` arrastrando ese `.zip` encima.
4. Doble clic en `Iniciar Azul.cmd`.

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
| `nucleo/` | Núcleo en Python: puertos (`core/ports.py`), conversación, voz, adaptadores (Anthropic, Deepgram, SQLite), acceso y respaldos |
| `app/` | App web instalable (TypeScript + Vite) |
| `docs/adr/` | Registro de decisiones de arquitectura |
| `docs/supuestos.md` | Supuestos y requisitos confirmados |
| `docs/estado.md` | En qué fase está el proyecto |
| `datos/` | Tu memoria y tu gasto. No va a git |
| `respaldos/` | Respaldos locales de la memoria. No va a git |
| `CLAUDE.md` | Las reglas de trabajo de Claude Code en este proyecto |
