# 0008. Un solo programa modular, con puertos y adaptadores

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: A (difícil de revertir)

## Contexto
Un solo usuario, un portátil con poca RAM, y la necesidad de cambiar de proveedor sin reescribir nada (R1, ADR 0005, 0006).

## Opciones consideradas
1. Un solo programa organizado en módulos conectados por interfaces.
2. Microservicios.

## Decisión
Opción 1. El núcleo define **puertos** (`nucleo/src/azul/core/ports.py`): `Brain`, `SpeechToText`, `TextToSpeech`, `MemoryStore` y `UsageMeter`. Cada proveedor se conecta mediante un **adaptador**. El mismo programa sirve la app web compilada.

## Consecuencias
- Liviano, y arranca con un solo comando.
- El núcleo no importa ningún SDK de proveedor directamente.
- Si algún día hiciera falta escalar por separado, habría que dividirlo (poco probable con un solo usuario).

## Cómo revertirla
Los módulos ya están separados por interfaces, así que podrían convertirse en servicios.
