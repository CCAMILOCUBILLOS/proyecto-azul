# 0001. El núcleo de Azul corre en el portátil

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 1 (entorno de despliegue)
- Tipo: A (difícil de revertir)

## Contexto
Equipo del usuario: Dell Inspiron 3442, Intel Core i3-4005U (2 núcleos), 7,9 GB de RAM, gráficos Intel HD integrados, Windows 10 Home. Azul debe usarse por voz desde el celular. Presupuesto de 20 a 50 USD al mes.

## Opciones consideradas
1. En el portátil, con acceso remoto por un túnel seguro.
2. En la nube, en un servicio gestionado (~5–10 USD/mes).
3. Híbrido: núcleo en la nube + agente local en el PC (era la recomendación).

## Decisión
Opción 1, **por el momento**. El usuario exige además que Azul pueda migrarse después a otro PC, a un servidor o a la nube **sin perder información** (requisito R1).

## Consecuencias
- Sin costo de infraestructura.
- Azul solo está disponible con el portátil encendido y despierto.
- El núcleo debe ser liviano (poca RAM libre).
- R1 obliga a: datos en una sola carpeta y en formatos estándar, configuración fuera del código y nada exclusivo de Windows en el núcleo.

## Cómo revertirla
Copiar el código y la carpeta `datos/` al nuevo equipo o servidor, y ajustar `.env`. Al migrar a la nube habrá que revisar la ADR 0003 (acceso).
