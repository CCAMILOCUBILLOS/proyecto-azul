# 0022. Respaldos de la memoria

- Estado: Aprobada (destinos y respaldo automático elegidos por el usuario el 2026-10-05)
- Fecha: 2026-10-05
- Capa: 3 y 4
- Tipo: B (reversible), con implicaciones de privacidad

## Contexto
R1 exige poder migrar Azul sin perder información, y el MVP incluye un comando de respaldo (ADR 0016, criterio 6). La memoria vive en `datos/azul.db` (ADR 0009). En el equipo hay OneDrive instalado y activo.

## Opciones consideradas
1. Solo en OneDrive.
2. Solo en el portátil.
3. En ambos.

Respaldo automático: diario, o solo manual.

## Decisión
- **En ambos:** `Proyecto Azul\respaldos` y `OneDrive\Azul\respaldos`, elegido por el usuario, sabiendo que la memoria queda en la nube de la cuenta dueña de ese OneDrive. Configurable con `AZUL_BACKUP_DIR` y `AZUL_BACKUP_CLOUD_DIR`.
- **Automático diario:** al iniciar Azul, si no hay respaldo del día, se crea uno y se conservan los últimos 14 (`AZUL_BACKUPS_TO_KEEP`). Si falla, Azul arranca igual y lo anota en el registro.
- **Formato:** `.zip` con `azul.db` (copia consistente hecha con la API de respaldo de SQLite, válida con Azul abierto) y `manifiesto.json` (fecha, versión del esquema y conteos). **Nunca incluye `.env`.**
- **Manual:** doble clic en `Respaldar Azul.cmd`.
- **Restauración:** doble clic en `Restaurar Azul.cmd`, que toma el respaldo más reciente o el `.zip` que se arrastre sobre el ícono. Exige que Azul esté cerrado y pide confirmación. Valida el archivo, la integridad de la base y la versión del esquema, y antes de reemplazar guarda la memoria actual como `azul-antes-de-restaurar-*.zip`.
- Si un destino falla (por ejemplo, OneDrive desconectado), se guarda en los demás.

## Consecuencias
- Criterio 6 del MVP verificado el 2026-10-05: el respaldo de OneDrive, restaurado en otra carpeta, coincide exactamente con la memoria (9 mensajes, 1 dato y 29 registros de gasto).
- Para migrar a otro equipo: copiar el proyecto (o clonarlo desde GitHub), crear `.env` con las claves y restaurar el último respaldo.

## Cómo revertirla
Cambiar las variables de configuración, o borrar la carpeta de OneDrive.
