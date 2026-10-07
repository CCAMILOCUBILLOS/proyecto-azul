---
name: excel
description: Trabajar con Excel - leer hojas y datos, calcular totales y resúmenes, crear hojas de cálculo nuevas (listados, cuadros, presupuestos, reportes, tablas dinámicas simples con fórmulas). Úsala cuando te pidan algo con Excel, tablas, cuadros, listados o cálculos sobre datos.
---

# Excel

## Leer y analizar

- Ubica el archivo con `buscar_archivos` (tipos: xlsx) y léelo con `leer_documento`: verás cada hoja con sus filas (valores ya calculados, no fórmulas).
- Si solo vienen las primeras filas, dilo y trabaja con eso o pide filtrar.
- Calcula lo que pidan con los datos leídos (sumas, promedios, conteos por categoría, máximos) y explica de dónde sale cada cifra. No inventes valores que no estén.

## Crear un Excel nuevo

Con `crear_excel`:
- **Una hoja por tema**, con nombres cortos ("Resumen", "Detalle").
- **Primera fila = encabezados** claros y cortos, con unidades si aplica ("Valor (COP)", "Fecha").
- **Números como números**, no como texto (sin "$" ni puntos de miles dentro del valor): 1500000, no "1.500.000".
- **Fechas** como texto AAAA-MM-DD.
- **Fórmulas** en inglés, empezando por "=": `=SUM(C2:C20)`, `=AVERAGE(...)`, `=COUNTIF(A:A,"Cali")`, `=IF(...)`. Úsalas para totales y cálculos, así el usuario puede cambiar datos y todo se actualiza. Pon la fila de totales al final, con "Total" en la primera columna.
- Para resúmenes por categoría, crea una hoja "Resumen" con `SUMIF`/`COUNTIF` sobre la hoja de detalle.
- Título del archivo descriptivo ("Presupuesto octubre 2026").

## Modificar un Excel existente

No se sobrescribe el original: lee el archivo, aplica los cambios a los datos y crea una versión nueva con `crear_excel` (por ejemplo, "Clientes - actualizado"). Avisa que el formato original (colores, anchos) no se conserva en la copia.

## Al terminar

Di por voz qué creaste, dónde quedó (OneDrive, Azul, Documentos) y el dato principal ("el total da 12,4 millones").
