# 0007. Núcleo en Python y app en TypeScript

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: A (difícil de revertir)

## Contexto
El usuario no programa: Claude Code construye y mantiene todo. Se necesitan herramientas de IA, voz, memoria y, más adelante, control de Windows.

## Opciones consideradas
1. Python para el núcleo + TypeScript para la app web.
2. TypeScript para todo.

## Decisión
Opción 1. El núcleo usa **Python 3.13**, instalado con `uv` solo para el proyecto; el Python 3.14 del sistema no se toca (S8).

## Consecuencias
- Acceso al mayor ecosistema de IA y a los SDK oficiales de Anthropic y Deepgram.
- Son dos lenguajes que mantener.

## Cómo revertirla
Implicaría reescribir el núcleo.
