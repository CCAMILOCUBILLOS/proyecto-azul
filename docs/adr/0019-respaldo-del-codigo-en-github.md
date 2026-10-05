# 0019. Respaldo del código en un repositorio privado de GitHub

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 4 (conexiones externas)
- Tipo: B (reversible)

## Contexto
El código solo existía en el portátil: si el equipo fallaba, se perdía todo.

## Opciones consideradas
1. Un repositorio privado en GitHub.
2. Una carpeta sincronizada (OneDrive o Google Drive).
3. Solo en el portátil.

## Decisión
Opción 1: `https://github.com/CCAMILOCUBILLOS/proyecto-azul` (privado). La cuenta la creó el usuario, y la autenticación se guardó en Git Credential Manager de Windows.

## Consecuencias
- El historial completo del código queda respaldado fuera del portátil.
- `.env` (secretos) y `datos/` (memoria personal) **no** se suben; los datos tendrán su propio respaldo (R1, ADR 0016).
- Autor de los commits: `juankmiloalfonso789 <juankmiloalfonso789@gmail.com>`, configurado solo en este repositorio. Se puede cambiar.

## Cómo revertirla
Cambiar el remoto (`git remote set-url`) a otro servicio; el historial viaja completo.
