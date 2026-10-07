# 0032. Habilidades de Azul y manejo de documentos del PC

- Estado: Aprobada (enfoque, librerías y carpetas aprobados por el usuario el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 3 (orquestación y herramientas) y 4 (archivos del PC, Microsoft Word)
- Tipo: B (reversible): `AZUL_DOCUMENTOS_ACTIVOS=false` y quitar carpetas de `habilidades/`

## Contexto
El usuario quiere habilidades: redacción, consulta jurídica, diseño de interfaces, programación, Excel, Word y lectura. Empezamos por redacción, que para él incluye trabajar con sus archivos: "ubica este Word en mi PC y redacta una carta de despido con estos datos"; si es PDF, convertirlo a Word y modificarlo.

## Decisión
- **Habilidades**: una carpeta por habilidad en `habilidades/<nombre>/SKILL.md` (mismo formato de las habilidades de Claude: `name`, `description` e instrucciones). El cerebro ve solo la lista (nombre y cuándo usarla) y abre las instrucciones con la herramienta `usar_habilidad` cuando las necesita. Así una habilidad no encarece las conversaciones normales. Primera habilidad: `redaccion`.
- **Documentos**: herramientas `buscar_archivos` (por palabras del nombre, en todo el equipo por decisión del usuario, saltando carpetas del sistema, máximo 10 s), `leer_documento` (Word con python-docx, PDF con pypdf, texto), `pdf_a_word` (con el Microsoft Word del usuario, por PowerShell) y `crear_word` (en `OneDrive/Azul/Documentos`; con un modelo, conserva membrete, encabezado y estilos).
- **Seguridad**: nunca borra ni sobrescribe (crea "(2)", "(3)"…); no lee archivos con nombre de claves (.env, key, clave, contraseña, token…).
- Librerías nuevas aprobadas: `python-docx` y `pypdf` (licencias libres).

## Consecuencias
- Prueba real (2026-10-06): con Sonnet 5.5, Azul abrió la habilidad, encontró el formato, lo leyó y creó la carta conservando el membrete; costo 4,6 ¢. La conversión PDF → Word con Word funcionó.
- Riesgo aceptado por el usuario: la clave de acceso de la app quedó visible en una captura y se cambiará después; mientras tanto, quien la tenga podría pedirle a Azul que lea archivos del PC desde la red privada.
- Excel (leer y crear), PowerPoint y las demás habilidades llegan en incrementos siguientes.

## Cómo revertirla
`AZUL_DOCUMENTOS_ACTIVOS=false` en `.env` y reiniciar; borrar la carpeta de la habilidad que no se quiera.
