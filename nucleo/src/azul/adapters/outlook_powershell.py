"""Los guiones de PowerShell que manejan Outlook clásico por COM (ADR 0037, 0040).

Solo usa la biblioteca estándar de Python (3.8 o más nueva): así este mismo archivo
lo usa Azul en el portátil y el ayudante de Outlook en el PC de Optometría, que no
tiene instaladas las dependencias de Azul.

Ningún guion llama a Send: enviar siempre lo hace el usuario. Los datos viajan por
archivos JSON temporales (nunca dentro del comando), así ningún texto de un correo
puede romper el guion.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SEGUNDOS_OUTLOOK = 120  # si Outlook estaba cerrado, abrirlo "en frío" tarda


class OutlookError(Exception):
    """Fallo de Outlook, con un mensaje apto para el usuario."""


_PRELUDIO = r"""
$ErrorActionPreference = 'Stop'
$e = [IO.File]::ReadAllText($env:AZUL_ENTRADA, [Text.Encoding]::UTF8) | ConvertFrom-Json
$o = New-Object -ComObject Outlook.Application
$ns = $o.GetNamespace('MAPI')
function Guardar($r) {
  $json = ConvertTo-Json -InputObject $r -Depth 5 -Compress
  [IO.File]::WriteAllText($env:AZUL_SALIDA, $json, (New-Object Text.UTF8Encoding $false))
}
function Direccion($m) {
  try {
    if ($m.SenderEmailType -eq 'EX') {
      $u = $m.Sender.GetExchangeUser(); if ($u) { return [string]$u.PrimarySmtpAddress }
    }
  } catch {}
  return [string]$m.SenderEmailAddress
}
function Buscar-Por-Id($id) {
  try { return $ns.GetItemFromID([string]$id) } catch { throw 'NO_ENCONTRADO' }
}
function Poner-Cuerpo($m, $html) {
  # Abrir el inspector (sin mostrarlo) hace que Outlook ponga la firma del usuario.
  $null = $m.GetInspector
  $h = [string]$m.HTMLBody
  $b = [regex]::Match($h, '(?is)<body[^>]*>')
  if ($b.Success) { $m.HTMLBody = $h.Insert($b.Index + $b.Length, $html) }
  else { $m.HTMLBody = $html + $h }
}
function Adjuntar($m) {
  foreach ($a in $e.adjuntos) { $null = $m.Attachments.Add([string]$a) }
}
function Destinatarios($m) {
  $lista = New-Object System.Collections.ArrayList
  foreach ($r in $m.Recipients) {
    $dir = [string]$r.Address
    try {
      $u = $r.AddressEntry.GetExchangeUser(); if ($u) { $dir = [string]$u.PrimarySmtpAddress }
    } catch {}
    $null = $lista.Add(@{ nombre = [string]$r.Name; correo = $dir; reconocido = [bool]$r.Resolved })
  }
  return ,$lista
}
"""

ACCIONES = {
    # Una "tabla" de Outlook lee muchos correos de una vez (correo por correo tarda
    # ~0,15 s cada uno), y el filtro con el índice de búsqueda de Outlook encuentra las
    # palabras en menos de un segundo. Sin índice, el respaldo revisa solo asunto y nombres.
    "buscar": r"""
$enviados = $e.carpeta -eq 'enviados'
$f = $ns.GetDefaultFolder($(if ($enviados) { 5 } else { 6 }))
$fecha = $(if ($enviados) { 'SentOn' } else { 'ReceivedTime' })
try { $t = $f.GetTable([string]$e.filtro); $null = $t.EndOfTable }
catch { $t = $f.GetTable([string]$e.respaldo) }
$smtp = 'http://schemas.microsoft.com/mapi/proptag/0x5D01001F'
$vista = 'urn:schemas:httpmail:textdescription'
$adj = 'urn:schemas:httpmail:hasattachment'
$columnas = 'SenderName', 'SenderEmailAddress', $fecha, 'UnRead', 'To', $smtp, $vista, $adj
foreach ($c in $columnas) {
  $null = $t.Columns.Add($c)
}
$t.Sort("[$fecha]", $true)
$lista = New-Object System.Collections.ArrayList
while (-not $t.EndOfTable -and $lista.Count -lt [int]$e.maximo) {
  $r = $t.GetNextRow()
  if (-not ([string]$r.Item('MessageClass')).StartsWith('IPM.Note')) { continue }
  $correo = [string]$r.Item($smtp)
  if (-not $correo) { $correo = [string]$r.Item('SenderEmailAddress') }
  $null = $lista.Add(@{
    id = [string]$r.Item('EntryID'); de = [string]$r.Item('SenderName'); correo = $correo
    para = [string]$r.Item('To'); asunto = [string]$r.Item('Subject')
    fecha = ([datetime]$r.Item($fecha)).ToString('yyyy-MM-dd HH:mm')
    vista = [string]$r.Item($vista); leido = -not $r.Item('UnRead')
    adjuntos = [bool]$r.Item($adj)
  })
}
Guardar @{ correos = $lista }
""",
    # Categorías de color de Azul (ADR 0039): solo cambia esa marca; no mueve ni borra.
    "categorizar": r"""
$existentes = @(foreach ($c in $ns.Categories) { [string]$c.Name })
foreach ($c in $e.categorias) {
  if ($existentes -notcontains [string]$c.nombre) {
    $null = $ns.Categories.Add([string]$c.nombre, [int]$c.color)
  }
}
$fallos = 0
foreach ($x in $e.items) {
  try {
    $m = $ns.GetItemFromID([string]$x.id)
    $otras = @(([string]$m.Categories) -split ',' | ForEach-Object { $_.Trim() } |
      Where-Object { $_ -and -not $_.StartsWith('Azul: ') })
    $m.Categories = (@($otras) + [string]$x.categoria) -join ', '
    $m.Save()
  } catch { $fallos++ }
}
Guardar @{ fallos = $fallos }
""",
    "leer": r"""
$m = Buscar-Por-Id $e.id
$adjuntos = New-Object System.Collections.ArrayList
foreach ($a in $m.Attachments) { $null = $adjuntos.Add([string]$a.FileName) }
Guardar @{
  de = [string]$m.SenderName; correo = (Direccion $m); para = [string]$m.To; cc = [string]$m.CC
  asunto = [string]$m.Subject; fecha = $m.ReceivedTime.ToString('yyyy-MM-dd HH:mm')
  cuerpo = [string]$m.Body; adjuntos = $adjuntos
}
""",
    # Como agendar.py de Red Nacional: dentro de Borradores (con CreateItem de respaldo).
    "borrador": r"""
try { $m = $ns.GetDefaultFolder(16).Items.Add(0) } catch { $m = $o.CreateItem(0) }
$m.BodyFormat = 2
$m.To = [string]$e.para; $m.CC = [string]$e.cc; $m.Subject = [string]$e.asunto
$null = $m.GetInspector
$firma = ([string]$m.Body).Trim().Length -gt 0
Poner-Cuerpo $m ([string]$e.html)
Adjuntar $m
$null = $m.Recipients.ResolveAll()
$m.Save()
Guardar @{ id = [string]$m.EntryID; destinatarios = (Destinatarios $m); firma = $firma }
""",
    "responder": r"""
$original = Buscar-Por-Id $e.id
$m = $(if ($e.a_todos) { $original.ReplyAll() } else { $original.Reply() })
Poner-Cuerpo $m ([string]$e.html)
Adjuntar $m
$m.Save()
Guardar @{
  id = [string]$m.EntryID; destinatarios = (Destinatarios $m); asunto = [string]$m.Subject
}
""",
}

# Lo más común (visto en la prueba real): una ventana de Office esperando respuesta,
# como el asistente de activación; mientras tanto Outlook lee pero no crea correos.
_VENTANA_ESPERANDO = (
    "Puede que Outlook u Office tengan una ventana abierta esperando respuesta (por ejemplo, "
    "la activación de Office o la contraseña). Ciérrala o complétala y vuelve a intentarlo."
)


def _error_de_powershell(stderr: bytes) -> str:
    """El texto del error, sin el envoltorio XML con que PowerShell lo entrega."""
    texto = stderr.decode("utf-8", "replace")
    partes = re.findall(r'<S S="Error">(.*?)</S>', texto)
    if partes:
        texto = " ".join(p.replace("_x000D__x000A_", " ") for p in partes)
    return " ".join(texto.split())


def ejecutar(accion: str, entrada: dict[str, Any]) -> dict[str, Any]:
    guion = _PRELUDIO + ACCIONES[accion]
    codificado = base64.b64encode(guion.encode("utf-16-le")).decode("ascii")
    with tempfile.TemporaryDirectory(prefix="azul-correo-") as carpeta:
        ruta_entrada = Path(carpeta, "entrada.json")
        ruta_salida = Path(carpeta, "salida.json")
        ruta_entrada.write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                env={
                    **os.environ,
                    "AZUL_ENTRADA": str(ruta_entrada),
                    "AZUL_SALIDA": str(ruta_salida),
                },
                capture_output=True,
                timeout=SEGUNDOS_OUTLOOK,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as error:
            log.warning("Outlook no respondió a tiempo (%s)", accion)
            raise OutlookError(f"Outlook no respondió a tiempo. {_VENTANA_ESPERANDO}") from error
        except subprocess.CalledProcessError as error:
            detalle = _error_de_powershell(error.stderr or b"")
            if "NO_ENCONTRADO" in detalle:
                raise OutlookError("No encuentro ese correo; búscalo de nuevo.") from error
            # Solo el comienzo del error de Outlook, sin el contenido de ningún correo.
            log.warning("Outlook falló (%s): %s", accion, detalle[:200])
            raise OutlookError(f"Outlook no pudo hacerlo. {_VENTANA_ESPERANDO}") from error
        except OSError as error:
            raise OutlookError("No pude abrir Outlook en este equipo.") from error
        return json.loads(ruta_salida.read_text(encoding="utf-8-sig"))
