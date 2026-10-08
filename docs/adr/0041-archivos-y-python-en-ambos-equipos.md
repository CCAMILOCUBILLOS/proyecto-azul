# 0041. Editar y organizar archivos y correr Python, en el portátil y en Optometría

- Estado: Aprobada por el usuario el 2026-10-07
- Fecha: 2026-10-07
- Capa: 3 (permisos y seguridad) y 4 (ayudante de Optometría)
- Tipo: B (reversible): `AZUL_ARCHIVOS_ACTIVOS=false` quita las herramientas

## Contexto
El usuario le pidió a Azul corregir un programa de Red Nacional y no pudo: solo podía
crear archivos nuevos. Azul sugirió una herramienta para editar archivos (con copia de
seguridad) y otra para correr comandos en Optometría. El usuario pidió habilidades para
manejar archivos de ambos PC y correr código.

## Opciones consideradas
1. Editar archivos (con copia de seguridad). 2. Organizar (copiar, mover, renombrar,
crear carpetas; borrar a la Papelera). 3. Lo mismo en Optometría. 4. Correr Python.
5. Comandos libres del sistema (no recomendada por ahora).

## Decisión (y quién la aprobó)
El usuario eligió 1 a 4, en **todo el equipo** (salvo carpetas del sistema), y **solo
para él**.
- `archivos_basicos.py` (solo biblioteca estándar) lo usan Azul y el ayudante (/archivos).
- Fuera: Windows, Program Files, ProgramData, AppData (salvo Temp), Papelera, y archivos
  que parecen claves (.env, "clave", "token"…).
- Editar o reemplazar deja copia en la carpeta de respaldos (portátil: OneDrive/Azul/
  Respaldos de archivos; Optometría: ayudante-optometria/respaldos) con un índice;
  `archivo_deshacer` restaura la última. Se respetan la codificación y los saltos de línea.
- Copiar y mover nunca sobrescriben; borrar solo a la Papelera.
- Python corre con el intérprete de cada equipo, en su carpeta de trabajo, 2 minutos máx.
- **Correr Python y mandar a la Papelera quedan pendientes** y solo se hacen con
  `accion_confirmar` después de un mensaje nuevo del usuario (lo vigila `Confirmaciones`,
  no el modelo); vencen a los 3 mensajes.
- Nunca disponibles para contactos de WhatsApp, ni con reglas aprendidas, y las
  instrucciones de Azul prohíben actuar por lo que diga un correo, archivo o página.

## Consecuencias
- Positivas: Azul puede corregir el tablero, ordenar carpetas y automatizar con Python.
- Riesgos: una edición sin confirmación podría inducirse con un correo malicioso que el
  usuario le pida leer (mitigado: instrucciones, copia de seguridad y deshacer). Python
  corre con los permisos del usuario en cada equipo.
- Optometría necesita el ayudante actualizado (`Actualizar ayudante.cmd`).

## Cómo revertirla
`AZUL_ARCHIVOS_ACTIVOS=false` en `.env` y reiniciar Azul. Las copias de seguridad quedan
en sus carpetas.
