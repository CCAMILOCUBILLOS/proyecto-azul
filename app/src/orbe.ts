// El orbe neuronal: la cara de Azul, en el vacío del espacio. Una esfera de nodos
// y sinapsis dibujada en Canvas 2D (sin dependencias) que refleja el estado de la voz:
// escucha (respira suave), piensa (impulsos hacia el núcleo), busca (la red se tiñe
// de violeta y los impulsos salen) y habla (la luz nace en el núcleo y recorre la red
// al ritmo del volumen real de su voz). Alrededor, un anillo de barras sigue el
// espectro de la voz y dos órbitas finas giran; detrás, estrellas.

export type EstadoOrbe = "reposo" | "atento" | "escuchando" | "pensando" | "buscando" | "hablando";

export interface LecturaOrbe {
  estado: EstadoOrbe;
  /** Volumen de la voz de Azul (RMS, 0 a 1). */
  nivel: number;
  /** Espectro de la voz de Azul (0 a 255 por banda), o null si no habla. */
  espectro: Uint8Array | null;
  /** Alto (px) que ocupan los subtítulos al pie de la escena: el orbe se hace a un lado. */
  reservaInferior: number;
}

/** Lo que Azul sabe y sabe hacer (GET /api/conocimiento). */
export interface Conocimiento {
  recuerdos: number;
  habilidades: string[];
  herramientas: string[];
  mensajes: number;
}

type Grupo = "base" | "memoria" | "habilidad" | "herramienta";

interface Nodo {
  /** Identidad estable: la misma neurona conserva su lugar cuando la red crece. */
  clave: string;
  grupo: Grupo;
  /** Momento en que nació (para el destello); muy negativo si ya estaba. */
  nacimiento: number;
  x: number;
  y: number;
  z: number;
  /** Distancia al centro (0 a 1): la onda de la voz llega antes a los nodos internos. */
  radio: number;
  fase: number;
  tamano: number;
  /** Algunas neuronas son moradas: la paleta de Azul es azul, morado y negro. */
  morada: boolean;
  // Proyección del cuadro actual.
  px: number;
  py: number;
  profundidad: number;
  escala: number;
  energia: number;
}

interface Impulso {
  desde: number;
  hasta: number;
  t: number;
  velocidad: number;
  haciaAfuera: boolean;
  violeta: boolean;
  saltos: number;
}

interface Estrella {
  x: number;
  y: number;
  tamano: number;
  brillo: number;
  fase: number;
  ritmo: number;
  lejania: number;
}

interface Fugaz {
  x: number;
  y: number;
  dx: number;
  dy: number;
  vida: number;
}

interface Parametros {
  giro: number;
  base: number;
  respiracion: number;
  brillo: number;
  impulsos: number;
  violeta: number;
  anillo: number;
}

// Cada estado es un punto de llegada; el orbe se desliza entre ellos sin saltos.
const PARAMETROS: Record<EstadoOrbe, Parametros> = {
  reposo: { giro: 0.05, base: 0.2, respiracion: 0.012, brillo: 0, impulsos: 0.25, violeta: 0.25, anillo: 0.25 },
  atento: { giro: 0.05, base: 0.24, respiracion: 0.012, brillo: 0, impulsos: 0.25, violeta: 0.2, anillo: 0.55 },
  escuchando: { giro: 0.09, base: 0.36, respiracion: 0.028, brillo: 0.12, impulsos: 0, violeta: 0.1, anillo: 0.8 },
  pensando: { giro: 0.16, base: 0.32, respiracion: 0.01, brillo: 0.18, impulsos: 16, violeta: 0.4, anillo: 0.6 },
  buscando: { giro: 0.2, base: 0.3, respiracion: 0.01, brillo: 0.14, impulsos: 20, violeta: 0.85, anillo: 0.7 },
  hablando: { giro: 0.11, base: 0.26, respiracion: 0.006, brillo: 0.1, impulsos: 0, violeta: 0.2, anillo: 1 },
};

const AZUL = [61, 139, 255] as const;
const AZUL_CLARO = [150, 196, 255] as const;
const VIOLETA = [139, 92, 246] as const;
const MORADO = [192, 132, 252] as const;
const DISTANCIA_CAMARA = 4;
const VECINOS = 3;
const MAX_RECUERDOS = 160;
const SEGUNDOS_NACIENDO = 2.4;
const PASOS_DE_ONDA = 24;
const RETARDO_ONDA_S = 0.42; // lo que tarda la luz en ir del núcleo al borde
const BARRAS = 120; // el anillo del espectro, como el del orbe de Jarvis
const RADIO_ANILLO = 1.17;
const RADIO_ORBITA = 1.32;

export class Orbe {
  private readonly contexto: CanvasRenderingContext2D;
  private nodos: Nodo[] = [];
  private saber: Conocimiento = { recuerdos: 0, habilidades: [], herramientas: [], mensajes: 0 };
  private baseCantidad = 0;
  private conocido = false;
  private enlaces: Array<[number, number]> = [];
  private vecinos: number[][] = [];
  private impulsos: Impulso[] = [];
  private estrellas: Estrella[] = [];
  private fugaz: Fugaz | null = null;
  private proximaFugaz = 12;
  private barras = new Float32Array(BARRAS);
  private anchoCss = 0;
  private altoCss = 0;
  private escalaPixel = 1;
  private angulo = 0;
  private tiempo = 0;
  private ultimo = 0;
  private pendienteDeImpulso = 0;
  private nivel = 0;
  private historial: Array<{ t: number; nivel: number }> = [];
  private onda = new Float32Array(PASOS_DE_ONDA);
  private actual: Parametros = { ...PARAMETROS.reposo };
  private cuadro = 0;
  // Posición y tamaño del orbe: se deslizan cuando aparecen o se van los subtítulos.
  private centroX = 0;
  private centroY = 0;
  private radioBase = 0;
  private readonly sprites: Record<"azul" | "violeta" | "blanco", HTMLCanvasElement>;
  private readonly movimientoReducido = matchMedia("(prefers-reduced-motion: reduce)");

  constructor(
    private readonly lienzo: HTMLCanvasElement,
    /** La zona de la pantalla donde vive el orbe; el lienzo cubre toda la ventana. */
    private readonly escena: HTMLElement,
    private readonly leer: () => LecturaOrbe,
  ) {
    const contexto = lienzo.getContext("2d");
    if (!contexto) throw new Error("Este navegador no puede dibujar el orbe.");
    this.contexto = contexto;
    this.sprites = {
      azul: brillo(AZUL_CLARO, AZUL),
      violeta: brillo(MORADO, VIOLETA),
      blanco: brillo([255, 255, 255], AZUL_CLARO),
    };
    new ResizeObserver(() => this.ajustarTamano()).observe(lienzo);
    this.ajustarTamano();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") this.arrancar();
    });
    this.arrancar();
  }

  private arrancar(): void {
    cancelAnimationFrame(this.cuadro);
    this.ultimo = performance.now();
    this.cuadro = requestAnimationFrame((ahora) => this.dibujar(ahora));
  }

  private ajustarTamano(): void {
    const caja = this.lienzo.getBoundingClientRect();
    if (caja.width === 0 || caja.height === 0) return;
    // Cubre toda la ventana: se limita la densidad para no gastar batería de más.
    this.escalaPixel = Math.min(window.devicePixelRatio || 1, 1.75);
    this.anchoCss = caja.width;
    this.altoCss = caja.height;
    this.lienzo.width = Math.round(caja.width * this.escalaPixel);
    this.lienzo.height = Math.round(caja.height * this.escalaPixel);
    this.crearEstrellas();
    // El tejido base según la pantalla; lo aprendido se suma encima (ver plan).
    const base = Math.min(300, Math.max(200, Math.round(Math.min(caja.width, caja.height) * 0.45)));
    if (Math.abs(base - this.baseCantidad) > 30) {
      this.baseCantidad = base;
      this.construir(false);
    }
  }

  private crearEstrellas(): void {
    const azar = semilla(29);
    const cantidad = Math.round((this.anchoCss * this.altoCss) / 2600);
    this.estrellas = Array.from({ length: cantidad }, () => {
      const lejania = azar();
      return {
        x: azar() * this.anchoCss,
        y: azar() * this.altoCss,
        // La mayoría, polvo apenas visible; unas pocas, estrellas de verdad.
        tamano: lejania > 0.97 ? 1.4 + azar() * 1.2 : 0.4 + azar() * 0.8,
        brillo: lejania > 0.97 ? 0.85 : 0.15 + azar() * 0.5,
        fase: azar() * Math.PI * 2,
        ritmo: 0.3 + azar() * 1.4,
        lejania,
      };
    });
  }

  /** Lo que Azul sabe: la red crece con ello (ver construir). */
  conocer(saber: Conocimiento): void {
    const antes = this.saber;
    this.saber = saber;
    const cambio =
      saber.recuerdos !== antes.recuerdos ||
      saber.mensajes !== antes.mensajes ||
      saber.habilidades.join() !== antes.habilidades.join() ||
      saber.herramientas.join() !== antes.herramientas.join();
    // La primera vez no hay destellos: es lo que Azul ya sabía al abrir la app.
    if (cambio) this.construir(this.conocido);
    this.conocido = true;
  }

  /**
   * Arma la red a partir de lo que Azul sabe. Cada neurona tiene una clave y una
   * posición que dependen solo de esa clave: al aprender algo nuevo, las de antes
   * quedan donde estaban y solo nacen las nuevas (con un destello).
   *   - base: el tejido de la red; se hace más denso con las conversaciones.
   *   - memoria: una neurona morada por cada cosa que Azul recuerda del usuario.
   *   - habilidad / herramienta: un racimo por cada una, alrededor de su centro.
   */
  private construir(animar: boolean): void {
    if (this.baseCantidad === 0) return;
    const plan = this.plan();
    const previas = new Map(this.nodos.map((nodo) => [nodo.clave, nodo]));
    const nace = animar && this.nodos.length > 0 ? this.tiempo : -100;
    this.nodos = plan.map((nodo) => previas.get(nodo.clave) ?? { ...nodo, nacimiento: nace });
    this.enlazar();
    this.impulsos = [];
  }

  private plan(): Nodo[] {
    const saber = this.saber;
    const nodos: Nodo[] = [];
    // El tejido base: según la pantalla, más lo conversado (crece despacio).
    const base = this.baseCantidad + Math.min(140, Math.round(Math.log2(1 + saber.mensajes) * 14));
    for (let i = 0; i < base; i++) {
      const azar = semilla(1000 + i * 7);
      const [x, y, z] = azar() < 0.68 ? enSuperficie(azar, 0.78, 0.22) : enInterior(azar);
      nodos.push(nuevoNodo(`b${i}`, "base", x, y, z, azar));
    }
    for (let i = 0; i < Math.min(saber.recuerdos, MAX_RECUERDOS); i++) {
      const azar = semilla(50_000 + i * 13);
      const [x, y, z] = enSuperficie(azar, 0.84, 0.16);
      nodos.push(nuevoNodo(`m${i}`, "memoria", x, y, z, azar));
    }
    const racimos: Array<[string, Grupo, number, number]> = [
      ...saber.habilidades.map((n): [string, Grupo, number, number] => [n, "habilidad", 16, 0.72]),
      ...saber.herramientas.map((n): [string, Grupo, number, number] => [n, "herramienta", 9, 0.6]),
    ];
    for (const [nombre, grupo, cantidad, distancia] of racimos) {
      const centro = semilla(numeroDe(nombre));
      const [cx, cy, cz] = enSuperficie(centro, 1, 0);
      for (let j = 0; j < cantidad; j++) {
        const azar = semilla(numeroDe(`${nombre}:${j}`));
        const desvio = j === 0 ? 0 : 0.22;
        let [x, y, z] = [cx * distancia, cy * distancia, cz * distancia].map(
          (v) => v + (azar() - 0.5) * 2 * desvio,
        );
        const largo = Math.hypot(x, y, z);
        if (largo > 0.97) [x, y, z] = [x, y, z].map((v) => (v / largo) * 0.97);
        nodos.push(nuevoNodo(`${grupo}:${nombre}:${j}`, grupo, x, y, z, azar));
      }
    }
    return nodos;
  }

  private enlazar(): void {
    const nodos = this.nodos;
    const vecinos: number[][] = nodos.map(() => []);
    const enlaces: Array<[number, number]> = [];
    const existe = new Set<number>();
    const unir = (i: number, j: number) => {
      const clave = Math.min(i, j) * 100_000 + Math.max(i, j);
      if (i === j || existe.has(clave)) return;
      existe.add(clave);
      enlaces.push([i, j]);
      vecinos[i].push(j);
      vecinos[j].push(i);
    };
    for (let i = 0; i < nodos.length; i++) {
      const cercanos = nodos
        .map((otro, j) => ({ j, d: j === i ? Infinity : distancia2(nodos[i], otro) }))
        .sort((a, b) => a.d - b.d)
        .slice(0, VECINOS);
      for (const { j } of cercanos) unir(i, j);
    }
    // Cada racimo se une a su centro: se lee como un "lóbulo" de la red.
    const centros = new Map<string, number>();
    nodos.forEach((nodo, i) => {
      if (nodo.grupo === "habilidad" || nodo.grupo === "herramienta") {
        const racimo = nodo.clave.slice(0, nodo.clave.lastIndexOf(":"));
        const centro = centros.get(racimo);
        if (centro === undefined) centros.set(racimo, i);
        else unir(i, centro);
      }
    });
    // Axones largos: unen la superficie con el interior y le dan forma de cerebro en red.
    const azar = semilla(7);
    const superficie = nodos.map((n, i) => (n.radio > 0.75 ? i : -1)).filter((i) => i >= 0);
    const interior = nodos.map((n, i) => (n.radio <= 0.75 ? i : -1)).filter((i) => i >= 0);
    if (interior.length && superficie.length) {
      for (let k = 0; k < nodos.length * 0.12; k++) {
        unir(
          superficie[Math.floor(azar() * superficie.length)],
          interior[Math.floor(azar() * interior.length)],
        );
      }
    }
    this.enlaces = enlaces;
    this.vecinos = vecinos;
  }

  private dibujar(ahora: number): void {
    if (document.visibilityState !== "visible") return;
    const dt = Math.min(0.05, (ahora - this.ultimo) / 1000);
    this.ultimo = ahora;
    this.tiempo += dt;
    const lectura = this.leer();
    const reducido = this.movimientoReducido.matches;
    this.avanzar(lectura, dt, reducido);
    this.pintar(reducido);
    this.cuadro = requestAnimationFrame((siguiente) => this.dibujar(siguiente));
  }

  private avanzar(lectura: LecturaOrbe, dt: number, reducido: boolean): void {
    const meta = PARAMETROS[lectura.estado];
    // El primer cuadro llega directo al estado actual; después, se desliza entre estados.
    const primero = this.tiempo <= dt;
    const suavidad = primero ? 1 : 1 - Math.exp(-dt * 2.4);
    for (const clave of Object.keys(meta) as Array<keyof Parametros>) {
      this.actual[clave] += (meta[clave] - this.actual[clave]) * suavidad;
    }

    // Dónde va el orbe: centrado en la escena, y más arriba y algo menor si hay subtítulos.
    const caja = this.escena.getBoundingClientRect();
    const disponible = Math.max(caja.height * 0.5, caja.height - lectura.reservaInferior);
    const radioMeta = Math.min(caja.width * 0.38, disponible * 0.34);
    const centroMeta = caja.top + disponible / 2;
    const deslizar = primero ? 1 : 1 - Math.exp(-dt * 3);
    this.radioBase += (radioMeta - this.radioBase) * deslizar;
    this.centroY += (centroMeta - this.centroY) * deslizar;
    this.centroX = caja.left + caja.width / 2;

    // El volumen de la voz se percibe mejor comprimido; sube rápido y baja con calma.
    // Mientras habla hay un piso: en las pausas entre palabras no vuelve a parecer en reposo.
    const objetivo =
      lectura.estado === "hablando" ? Math.max(0.24, Math.min(1, Math.pow(lectura.nivel * 6, 0.75))) : 0;
    const respuesta = objetivo > this.nivel ? 0.55 : 0.08;
    this.nivel += (objetivo - this.nivel) * respuesta;
    this.historial.push({ t: this.tiempo, nivel: this.nivel });
    while (this.historial.length > 2 && this.tiempo - this.historial[1].t > RETARDO_ONDA_S + 0.1) {
      this.historial.shift();
    }
    for (let paso = 0; paso < PASOS_DE_ONDA; paso++) {
      this.onda[paso] = this.nivelHace((paso / (PASOS_DE_ONDA - 1)) * RETARDO_ONDA_S);
    }

    this.avanzarBarras(lectura, dt, reducido);
    this.angulo += dt * this.actual.giro * (reducido ? 0.15 : 1);
    this.avanzarFugaz(dt, reducido);

    // Impulsos: piensa hacia el núcleo, busca hacia afuera; al hablar nacen con el volumen.
    const porSegundo = this.actual.impulsos + this.nivel * 26;
    this.pendienteDeImpulso += porSegundo * dt * (reducido ? 0.3 : 1);
    while (this.pendienteDeImpulso >= 1) {
      this.pendienteDeImpulso -= 1;
      this.lanzarImpulso(lectura.estado);
    }
    for (const impulso of this.impulsos) impulso.t += impulso.velocidad * dt;
    const vivos: Impulso[] = [];
    for (const impulso of this.impulsos) {
      if (impulso.t < 1) {
        vivos.push(impulso);
        continue;
      }
      const siguiente = this.siguienteNodo(impulso);
      if (siguiente !== null && impulso.saltos < 5) {
        vivos.push({ ...impulso, desde: impulso.hasta, hasta: siguiente, t: 0, saltos: impulso.saltos + 1 });
      }
    }
    this.impulsos = vivos.slice(-160);
  }

  /** Alto de cada barra del anillo (0 a 1) según el estado y, al hablar, el espectro real. */
  private avanzarBarras(lectura: LecturaOrbe, dt: number, reducido: boolean): void {
    const mitad = BARRAS / 2;
    for (let i = 0; i < BARRAS; i++) {
      // Simétrico: la mitad derecha refleja la izquierda, graves arriba.
      const posicion = i < mitad ? i / mitad : (BARRAS - i) / mitad;
      let meta: number;
      if (lectura.estado === "hablando" && lectura.espectro) {
        const banda = Math.floor(2 + posicion * 70);
        meta = Math.pow((lectura.espectro[banda] ?? 0) / 255, 1.4) * 1.1 + this.nivel * 0.12;
      } else if (lectura.estado === "escuchando") {
        // Una ola lenta que da la vuelta: Azul está atenta, sin sobresaltos.
        meta = 0.1 + 0.07 * Math.sin(this.tiempo * 1.6 - (i / BARRAS) * Math.PI * 4);
      } else if (lectura.estado === "pensando" || lectura.estado === "buscando") {
        // Un barrido que gira, como un radar.
        const barrido = (((this.tiempo * 0.55) % 1) + 1) % 1;
        const distancia = Math.min(Math.abs(i / BARRAS - barrido), 1 - Math.abs(i / BARRAS - barrido));
        meta = 0.05 + Math.max(0, 0.32 - distancia * 2.4);
      } else {
        meta = 0.04;
      }
      if (reducido && lectura.estado !== "hablando") meta = 0.06;
      const sube = meta > this.barras[i];
      this.barras[i] += (meta - this.barras[i]) * (1 - Math.exp(-dt * (sube ? 22 : 7)));
    }
  }

  private avanzarFugaz(dt: number, reducido: boolean): void {
    if (reducido) {
      this.fugaz = null;
      return;
    }
    if (this.fugaz) {
      this.fugaz.x += this.fugaz.dx * dt;
      this.fugaz.y += this.fugaz.dy * dt;
      this.fugaz.vida -= dt;
      if (this.fugaz.vida <= 0) this.fugaz = null;
      return;
    }
    this.proximaFugaz -= dt;
    if (this.proximaFugaz > 0) return;
    // De vez en cuando, una estrella fugaz cruza lejos del orbe.
    this.proximaFugaz = 18 + Math.random() * 30;
    const desdeIzquierda = Math.random() < 0.5;
    const velocidad = Math.max(this.anchoCss, 500) * 0.9;
    this.fugaz = {
      x: desdeIzquierda ? this.anchoCss * Math.random() * 0.3 : this.anchoCss * (0.7 + Math.random() * 0.3),
      y: this.altoCss * Math.random() * 0.25,
      dx: (desdeIzquierda ? 1 : -1) * velocidad,
      dy: velocidad * 0.32,
      vida: 0.7,
    };
  }

  private nivelHace(segundos: number): number {
    const buscado = this.tiempo - segundos;
    for (let i = this.historial.length - 1; i >= 0; i--) {
      if (this.historial[i].t <= buscado) return this.historial[i].nivel;
    }
    return this.historial[0]?.nivel ?? 0;
  }

  private lanzarImpulso(estado: EstadoOrbe): void {
    if (this.enlaces.length === 0) return;
    const haciaAfuera = estado !== "pensando";
    const [a, b] = this.enlaces[Math.floor(Math.random() * this.enlaces.length)];
    const [desde, hasta] =
      (this.nodos[a].radio < this.nodos[b].radio) === haciaAfuera ? [a, b] : [b, a];
    this.impulsos.push({
      desde,
      hasta,
      t: 0,
      velocidad: 1.4 + Math.random() * 1.6,
      haciaAfuera,
      violeta: estado === "buscando" || (estado === "pensando" && Math.random() < 0.3),
      saltos: 0,
    });
  }

  private siguienteNodo(impulso: Impulso): number | null {
    const origen = this.nodos[impulso.hasta];
    const opciones = this.vecinos[impulso.hasta].filter((j) =>
      impulso.haciaAfuera ? this.nodos[j].radio > origen.radio : this.nodos[j].radio < origen.radio,
    );
    if (opciones.length === 0 || Math.random() < 0.3) return null;
    return opciones[Math.floor(Math.random() * opciones.length)];
  }

  private pintar(reducido: boolean): void {
    const g = this.contexto;
    const ancho = this.anchoCss;
    const alto = this.altoCss;
    g.setTransform(this.escalaPixel, 0, 0, this.escalaPixel, 0, 0);
    g.clearRect(0, 0, ancho, alto);
    this.pintarEstrellas(g, reducido);
    if (this.nodos.length === 0) return;

    const respira = reducido ? 0 : Math.sin(this.tiempo * Math.PI * 2 * 0.22) * this.actual.respiracion;
    const radio = this.radioBase * (1 + respira + this.nivel * 0.035);
    const cx = this.centroX;
    const cy = this.centroY;
    const giroY = this.angulo;
    const giroX = 0.38 + Math.sin(this.tiempo * 0.07) * 0.1;
    const [senY, cosY, senX, cosX] = [Math.sin(giroY), Math.cos(giroY), Math.sin(giroX), Math.cos(giroX)];

    for (const nodo of this.nodos) {
      const x1 = nodo.x * cosY + nodo.z * senY;
      const z1 = -nodo.x * senY + nodo.z * cosY;
      const y2 = nodo.y * cosX - z1 * senX;
      const z2 = nodo.y * senX + z1 * cosX;
      const escala = DISTANCIA_CAMARA / (DISTANCIA_CAMARA - z2);
      nodo.px = cx + x1 * radio * escala;
      nodo.py = cy + y2 * radio * escala;
      nodo.profundidad = (z2 + 1) / 2;
      nodo.escala = escala;
      const onda = this.onda[Math.round(nodo.radio * (PASOS_DE_ONDA - 1))];
      const destello = reducido ? 0 : Math.sin(this.tiempo * 1.3 + nodo.fase) * 0.06;
      nodo.energia = Math.min(1.6, this.actual.base + this.actual.brillo + destello + onda * (1.6 - nodo.radio * 0.6));
    }

    // Halo: un resplandor azul y violeta en el vacío que crece cuando Azul habla.
    const halo = g.createRadialGradient(cx, cy, radio * 0.1, cx, cy, radio * 1.9);
    halo.addColorStop(0, `rgba(60, 90, 255, ${0.14 + this.nivel * 0.32})`);
    halo.addColorStop(0.5, `rgba(100, 60, 230, ${0.05 + this.nivel * 0.14})`);
    halo.addColorStop(1, "rgba(0, 0, 0, 0)");
    g.fillStyle = halo;
    g.beginPath();
    g.arc(cx, cy, radio * 1.9, 0, Math.PI * 2);
    g.fill();

    g.globalCompositeOperation = "lighter";
    this.pintarOrbitas(g, cx, cy, radio, "atras");
    this.pintarEnlaces(g, cx, cy);
    this.pintarNucleo(g, cx, cy, radio);
    this.pintarNodos(g);
    this.pintarImpulsos(g);
    this.pintarAnillo(g, cx, cy, radio);
    this.pintarOrbitas(g, cx, cy, radio, "adelante");
    g.globalCompositeOperation = "source-over";
  }

  private pintarEstrellas(g: CanvasRenderingContext2D, reducido: boolean): void {
    // Deriva lentísima: el espacio se mueve, apenas.
    const deriva = reducido ? 0 : this.tiempo * 2.5;
    for (const estrella of this.estrellas) {
      const parpadeo = reducido ? 1 : 0.65 + 0.35 * Math.sin(this.tiempo * estrella.ritmo + estrella.fase);
      const x = (((estrella.x + deriva * (0.3 + estrella.lejania)) % this.anchoCss) + this.anchoCss) % this.anchoCss;
      g.globalAlpha = estrella.brillo * parpadeo;
      if (estrella.tamano > 1.3) {
        g.drawImage(this.sprites.blanco, x - estrella.tamano * 2.5, estrella.y - estrella.tamano * 2.5, estrella.tamano * 5, estrella.tamano * 5);
      } else {
        g.fillStyle = estrella.lejania > 0.6 ? "#dfe6ff" : "#b9b2ff";
        g.fillRect(x, estrella.y, estrella.tamano, estrella.tamano);
      }
    }
    if (this.fugaz) {
      const { x, y, dx, dy, vida } = this.fugaz;
      const largo = 0.16;
      const estela = g.createLinearGradient(x, y, x - dx * largo, y - dy * largo);
      estela.addColorStop(0, `rgba(220, 230, 255, ${Math.min(1, vida * 1.6)})`);
      estela.addColorStop(1, "rgba(150, 120, 255, 0)");
      g.globalAlpha = 1;
      g.strokeStyle = estela;
      g.lineWidth = 1.2;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x - dx * largo, y - dy * largo);
      g.stroke();
    }
    g.globalAlpha = 1;
  }

  private pintarOrbitas(g: CanvasRenderingContext2D, cx: number, cy: number, radio: number, mitad: "atras" | "adelante"): void {
    // Dos órbitas finas e inclinadas; la mitad de atrás pasa detrás de la red.
    const orbitas = [
      { inclinacion: -0.42, achatado: 0.3, velocidad: 0.12, color: AZUL_CLARO },
      { inclinacion: 0.9, achatado: 0.22, velocidad: -0.08, color: MORADO },
    ];
    const brillo = 0.12 + this.nivel * 0.35 + this.actual.brillo * 0.4;
    for (const orbita of orbitas) {
      const giro = orbita.inclinacion + Math.sin(this.tiempo * orbita.velocidad) * 0.25;
      const [inicio, fin] = mitad === "atras" ? [Math.PI, Math.PI * 2] : [0, Math.PI];
      g.save();
      g.translate(cx, cy);
      g.rotate(giro);
      g.strokeStyle = `rgba(${orbita.color[0]}, ${orbita.color[1]}, ${orbita.color[2]}, ${brillo * (mitad === "atras" ? 0.45 : 1)})`;
      g.lineWidth = 1;
      g.beginPath();
      g.ellipse(0, 0, radio * RADIO_ORBITA, radio * RADIO_ORBITA * orbita.achatado, 0, inicio, fin);
      g.stroke();
      // Un punto viaja por cada órbita.
      if (mitad === "adelante") {
        const a = this.tiempo * orbita.velocidad * 6;
        const px = Math.cos(a) * radio * RADIO_ORBITA;
        const py = Math.sin(a) * radio * RADIO_ORBITA * orbita.achatado;
        const tamano = 3 + this.nivel * 4;
        g.globalAlpha = Math.sin(a) > 0 ? 0.9 : 0.35;
        g.drawImage(orbita.color === MORADO ? this.sprites.violeta : this.sprites.blanco, px - tamano, py - tamano, tamano * 2, tamano * 2);
        g.globalAlpha = 1;
      }
      g.restore();
    }
  }

  private pintarEnlaces(g: CanvasRenderingContext2D, cx: number, cy: number): void {
    // Se agrupan por profundidad y energía: pocas pinceladas, aunque haya cientos de enlaces.
    const grupos = 4;
    const caminos: Path2D[][] = Array.from({ length: grupos }, () =>
      Array.from({ length: grupos }, () => new Path2D()),
    );
    for (const [a, b] of this.enlaces) {
      const na = this.nodos[a];
      const nb = this.nodos[b];
      const profundidad = Math.min(grupos - 1, Math.floor(((na.profundidad + nb.profundidad) / 2) * grupos));
      const energia = Math.min(grupos - 1, Math.floor(((na.energia + nb.energia) / 2 / 1.2) * grupos));
      const camino = caminos[profundidad][energia];
      // Sinapsis curvas, combadas hacia el núcleo: se ven orgánicas.
      const mx = (na.px + nb.px) / 2;
      const my = (na.py + nb.py) / 2;
      camino.moveTo(na.px, na.py);
      camino.quadraticCurveTo(mx + (cx - mx) * 0.04, my + (cy - my) * 0.04, nb.px, nb.py);
    }
    g.lineCap = "round";
    for (let p = 0; p < grupos; p++) {
      const frente = (p + 0.5) / grupos;
      // Atrás violeta, adelante azul; buscar tiñe toda la red de violeta.
      const v = this.actual.violeta;
      const mezcla = Math.min(1, (1 - frente) * 1.1 * (1 - v) + v);
      const color = mezclar(AZUL, VIOLETA, mezcla);
      for (let e = 0; e < grupos; e++) {
        const energia = (e + 0.5) / grupos;
        g.strokeStyle = `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${(0.08 + energia * 0.5) * (0.35 + frente * 0.65)})`;
        g.lineWidth = 0.6 + frente * 0.6 + energia * 0.7;
        g.stroke(caminos[p][e]);
      }
    }
  }

  private pintarNucleo(g: CanvasRenderingContext2D, cx: number, cy: number, radio: number): void {
    const intensidad = 0.35 + this.actual.brillo * 1.5 + this.nivel * 0.9;
    const tamano = radio * (0.16 + this.nivel * 0.3 + this.actual.brillo * 0.2);
    const nucleo = g.createRadialGradient(cx, cy, 0, cx, cy, tamano * 2.2);
    nucleo.addColorStop(0, `rgba(235, 244, 255, ${Math.min(1, intensidad)})`);
    nucleo.addColorStop(0.18, `rgba(150, 196, 255, ${Math.min(1, intensidad * 0.75)})`);
    nucleo.addColorStop(0.5, `rgba(61, 139, 255, ${intensidad * 0.28})`);
    nucleo.addColorStop(1, "rgba(139, 92, 246, 0)");
    g.fillStyle = nucleo;
    g.beginPath();
    g.arc(cx, cy, tamano * 2.2, 0, Math.PI * 2);
    g.fill();
    // El punto blanco azulado del núcleo: siempre encendido, también en reposo.
    const punto = radio * 0.07;
    const v = this.actual.violeta;
    const brillo = g.createRadialGradient(cx, cy, 0, cx, cy, punto);
    brillo.addColorStop(0, "rgba(245, 249, 255, 0.95)");
    brillo.addColorStop(0.35, `rgba(${Math.round(170 + v * 30)}, ${Math.round(205 - v * 60)}, 255, 0.6)`);
    brillo.addColorStop(1, `rgba(${Math.round(61 + v * 78)}, ${Math.round(139 - v * 47)}, ${Math.round(255 - v * 9)}, 0)`);
    g.fillStyle = brillo;
    g.beginPath();
    g.arc(cx, cy, punto, 0, Math.PI * 2);
    g.fill();
  }

  private pintarNodos(g: CanvasRenderingContext2D): void {
    for (const nodo of this.nodos) {
      // Lo aprendido brilla un poco más que el tejido base.
      const realce = nodo.grupo === "memoria" ? 1.25 : nodo.grupo === "habilidad" ? 1.1 : 1;
      const alfa = Math.min(1, (0.12 + nodo.profundidad * 0.88) * (0.35 + nodo.energia) * realce);
      if (alfa < 0.04) continue;
      // Una neurona recién nacida crece desde cero.
      const edad = this.tiempo - nodo.nacimiento;
      const crecer = edad < SEGUNDOS_NACIENDO ? 1 - Math.pow(1 - Math.min(1, edad / 1.2), 3) : 1;
      const tamano =
        (2.2 + nodo.energia * 4.5) * nodo.tamano * nodo.escala * (0.55 + nodo.profundidad * 0.6) * realce * crecer;
      const sprite =
        nodo.energia > 0.9
          ? this.sprites.blanco
          : nodo.morada || nodo.profundidad < 0.35 || this.actual.violeta > 0.7
            ? this.sprites.violeta
            : this.sprites.azul;
      g.globalAlpha = alfa;
      g.drawImage(sprite, nodo.px - tamano, nodo.py - tamano, tamano * 2, tamano * 2);
      if (edad < SEGUNDOS_NACIENDO) this.pintarNacimiento(g, nodo, edad);
    }
    g.globalAlpha = 1;
  }

  /** El destello de una neurona nueva: un anillo que se abre y se apaga. */
  private pintarNacimiento(g: CanvasRenderingContext2D, nodo: Nodo, edad: number): void {
    const avance = edad / SEGUNDOS_NACIENDO;
    const color = nodo.grupo === "memoria" ? MORADO : AZUL_CLARO;
    g.globalAlpha = (1 - avance) * 0.9;
    g.strokeStyle = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
    g.lineWidth = 1.5;
    g.beginPath();
    g.arc(nodo.px, nodo.py, 4 + avance * 28, 0, Math.PI * 2);
    g.stroke();
    const brillo = 26 * (1 - avance);
    g.drawImage(this.sprites.blanco, nodo.px - brillo, nodo.py - brillo, brillo * 2, brillo * 2);
  }

  private pintarImpulsos(g: CanvasRenderingContext2D): void {
    for (const impulso of this.impulsos) {
      const a = this.nodos[impulso.desde];
      const b = this.nodos[impulso.hasta];
      if (!a || !b) continue;
      const t = impulso.t;
      const x = a.px + (b.px - a.px) * t;
      const y = a.py + (b.py - a.py) * t;
      const profundidad = a.profundidad + (b.profundidad - a.profundidad) * t;
      const tamano = 5 + profundidad * 5;
      const desvanecer = Math.sin(Math.PI * Math.min(1, t)) * 0.6 + 0.4;
      // Estela corta: el tramo recién recorrido del enlace.
      const atras = Math.max(0, t - 0.35);
      g.strokeStyle = impulso.violeta ? "rgba(192, 132, 252, 0.55)" : "rgba(170, 210, 255, 0.55)";
      g.lineWidth = 1.4;
      g.globalAlpha = desvanecer * (0.4 + profundidad * 0.6);
      g.beginPath();
      g.moveTo(a.px + (b.px - a.px) * atras, a.py + (b.py - a.py) * atras);
      g.lineTo(x, y);
      g.stroke();
      g.drawImage(impulso.violeta ? this.sprites.violeta : this.sprites.blanco, x - tamano, y - tamano, tamano * 2, tamano * 2);
    }
    g.globalAlpha = 1;
  }

  private pintarAnillo(g: CanvasRenderingContext2D, cx: number, cy: number, radio: number): void {
    // El anillo de barras: marcas finas en reposo; al hablar, el espectro de la voz.
    const presencia = this.actual.anillo;
    if (presencia < 0.02) return;
    const interior = radio * RADIO_ANILLO;
    const largoMaximo = radio * 0.26;
    const v = this.actual.violeta;
    const grupos: Path2D[] = [new Path2D(), new Path2D(), new Path2D()];
    for (let i = 0; i < BARRAS; i++) {
      const angulo = (i / BARRAS) * Math.PI * 2 - Math.PI / 2;
      const largo = 2 + this.barras[i] * largoMaximo;
      const coseno = Math.cos(angulo);
      const seno = Math.sin(angulo);
      const grupo = this.barras[i] > 0.45 ? 2 : this.barras[i] > 0.15 ? 1 : 0;
      grupos[grupo].moveTo(cx + coseno * interior, cy + seno * interior);
      grupos[grupo].lineTo(cx + coseno * (interior + largo), cy + seno * (interior + largo));
    }
    const ancho = Math.max(1.2, ((Math.PI * 2 * interior) / BARRAS) * 0.42);
    g.lineCap = "round";
    g.lineWidth = ancho;
    const colores = [mezclar(AZUL, VIOLETA, 0.35 + v * 0.6), mezclar(AZUL, VIOLETA, v), mezclar(AZUL_CLARO, MORADO, v)];
    const alfas = [0.28, 0.6, 0.95];
    for (let i = 0; i < grupos.length; i++) {
      const [r, gr, b] = colores[i];
      g.strokeStyle = `rgba(${r}, ${gr}, ${b}, ${alfas[i] * presencia})`;
      g.stroke(grupos[i]);
    }
  }
}

function brillo(centro: readonly number[], borde: readonly number[]): HTMLCanvasElement {
  const lado = 64;
  const lienzo = document.createElement("canvas");
  lienzo.width = lado;
  lienzo.height = lado;
  const g = lienzo.getContext("2d");
  if (g) {
    const degradado = g.createRadialGradient(lado / 2, lado / 2, 0, lado / 2, lado / 2, lado / 2);
    degradado.addColorStop(0, `rgba(${centro[0]}, ${centro[1]}, ${centro[2]}, 1)`);
    degradado.addColorStop(0.18, `rgba(${centro[0]}, ${centro[1]}, ${centro[2]}, 0.9)`);
    degradado.addColorStop(0.42, `rgba(${borde[0]}, ${borde[1]}, ${borde[2]}, 0.35)`);
    degradado.addColorStop(1, `rgba(${borde[0]}, ${borde[1]}, ${borde[2]}, 0)`);
    g.fillStyle = degradado;
    g.fillRect(0, 0, lado, lado);
  }
  return lienzo;
}

function mezclar(a: readonly number[], b: readonly number[], t: number): number[] {
  return a.map((valor, i) => Math.round(valor + (b[i] - valor) * t));
}

function distancia2(a: Nodo, b: Nodo): number {
  return (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2;
}

/** Números al azar repetibles: el orbe y las estrellas tienen siempre la misma forma. */
function semilla(valor: number): () => number {
  let estado = valor;
  return () => {
    estado = (estado * 1_664_525 + 1_013_904_223) % 4_294_967_296;
    return estado / 4_294_967_296;
  };
}

function nuevoNodo(
  clave: string,
  grupo: Grupo,
  x: number,
  y: number,
  z: number,
  azar: () => number,
): Nodo {
  return {
    clave,
    grupo,
    nacimiento: -100,
    x,
    y,
    z,
    radio: Math.min(1, Math.hypot(x, y, z)),
    fase: azar() * Math.PI * 2,
    tamano: grupo === "memoria" ? 1.2 + azar() * 0.6 : 0.7 + azar() * 0.9,
    morada: grupo === "memoria" || (grupo === "base" && azar() < 0.3),
    px: 0,
    py: 0,
    profundidad: 0,
    escala: 1,
    energia: 0,
  };
}

/** Un punto al azar en una cáscara de radio [desde, desde + grosor]. */
function enSuperficie(azar: () => number, desde: number, grosor: number): [number, number, number] {
  const theta = azar() * Math.PI * 2;
  const phi = Math.acos(2 * azar() - 1);
  const radio = desde + Math.sqrt(azar()) * grosor;
  return [
    radio * Math.sin(phi) * Math.cos(theta),
    radio * Math.cos(phi),
    radio * Math.sin(phi) * Math.sin(theta),
  ];
}

/** Un punto del interior, más denso cerca del núcleo. */
function enInterior(azar: () => number): [number, number, number] {
  return enSuperficie(azar, 0.18, 0.66 * azar());
}

/** Convierte un nombre en una semilla estable. */
function numeroDe(texto: string): number {
  let numero = 2166136261;
  for (let i = 0; i < texto.length; i++) {
    numero = Math.imul(numero ^ texto.charCodeAt(i), 16777619) >>> 0;
  }
  return numero;
}
