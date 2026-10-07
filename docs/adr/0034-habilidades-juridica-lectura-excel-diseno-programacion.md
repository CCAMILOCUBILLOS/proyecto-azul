# 0034. Cinco habilidades más: jurídica, lectura, Excel, diseño de interfaces y programación

- Estado: Aprobada (el usuario pidió las cinco y aprobó openpyxl el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 3 (habilidades y herramientas) y 4 (librería openpyxl)
- Tipo: B (reversible): borrar la carpeta de la habilidad en `habilidades/`

## Decisión
Sobre el sistema del ADR 0032:
- **juridica**: derecho colombiano; verifica en fuentes oficiales (Secretaría del Senado, SUIN-Juriscol, Función Pública, altas cortes, ministerios), cita la norma exacta, no inventa artículos ni plazos y dice qué no verificó; recomienda validar con un abogado si hay dinero o plazos en juego.
- **lectura**: resumir, extraer fechas, valores y obligaciones, responder preguntas citando dónde lo dice el documento, comparar documentos.
- **excel**: leer hojas (valores) y crear Excel con encabezado en negrita y fijo, números como números y fórmulas (`=SUM`…); para "modificar", crea una versión nueva.
- **diseno-interfaces**: principios de jerarquía, espacio, color, estados y accesibilidad; entrega páginas como un HTML completo que abre solo en el navegador; crítica con los tres problemas que más pesan primero.
- **programacion**: explicar, revisar y escribir código en lenguaje sencillo; seguro por defecto; dice exactamente cómo ejecutar lo que escribe. No ejecuta programas en el PC.

Herramientas nuevas: `crear_excel` y `guardar_archivo` (html, css, js, ts, py, md, txt, json, csv, sql, xml, yaml), ambas en OneDrive/Azul/Documentos y sin sobrescribir. `leer_documento` ahora lee Excel y código fuente. Las palabras de estas tareas (jurídico, contrato, norma, código, programa…) piden esfuerzo medio.

## Consecuencias
- Prueba real (2026-10-06, Sonnet 5.5): creó el Excel de ventas con la fórmula del total (3,4 ¢) y respondió el plazo del derecho de petición con el artículo 14 de la Ley 1755 de 2015, aclarando lo que no verificó (3,3 ¢).
- Limitaciones: no lee documentos escaneados (imágenes); un Excel "modificado" no conserva colores ni anchos del original; Azul no ejecuta los programas que escribe.

## Cómo revertirla
Borrar la carpeta de la habilidad y reiniciar Azul.
