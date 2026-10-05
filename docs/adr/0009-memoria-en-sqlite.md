# 0009. Memoria en SQLite

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: A (difícil de revertir)

## Contexto
La memoria debe poder migrarse sin pérdidas (R1) y ser liviana para el portátil.

## Opciones consideradas
1. SQLite: un solo archivo, sin servidor.
2. PostgreSQL: un servidor de base de datos.
3. Archivos de texto (JSON o Markdown).

## Decisión
Opción 1. Toda la información vive en la carpeta `datos/`. En el MVP se guardan el historial de conversaciones y los datos importantes sobre el usuario; la búsqueda es por texto.

## Consecuencias
- Migrar o respaldar es copiar la carpeta `datos/`.
- La búsqueda por significado (embeddings) necesitará otro proveedor más adelante.
- La memoria queda **sin cifrar** en el disco (riesgo aceptado para el MVP; el cifrado está en la hoja de ruta).

## Cómo revertirla
Exportar desde SQLite a otro motor es un procedimiento estándar.
