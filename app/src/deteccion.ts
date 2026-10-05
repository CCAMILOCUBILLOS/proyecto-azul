// Detector de voz local para "Oye Azul" (ADR 0025). Corre en el propio celular:
// mide el volumen cada 0,1 s, aprende el ruido de fondo y avisa cuándo empieza
// y termina alguien de hablar. Solo esos fragmentos se envían a Azul.

export interface AccionesDetector {
  /** Empezó una voz; incluye el audio inmediatamente anterior para no cortar el "Oye". */
  empezar(previos: Float32Array[]): void;
  audio(bloque: Float32Array): void;
  terminar(): void;
}

const BLOQUE_SEGUNDOS = 0.1;
const BLOQUES_PREVIOS = 5; // 0,5 s antes de detectar la voz
const BLOQUES_CON_VOZ_PARA_EMPEZAR = 2; // 0,2 s seguidos de voz
const BLOQUES_DE_SILENCIO_PARA_TERMINAR = 12; // 1,2 s de silencio
const MAXIMO_BLOQUES = 300; // 30 s por fragmento
// El iPhone entrega niveles bajos al cancelar eco y ruido: el umbral debe ser bajo.
// (Con 0,012 la voz real del usuario nunca se detectó.)
const VOLUMEN_MINIMO = 0.005;
const VECES_SOBRE_EL_RUIDO = 3;

export class DetectorDeVoz {
  private acumulado: Float32Array[] = [];
  private muestrasAcumuladas = 0;
  private ruidoDeFondo = 0.002;
  /** Último volumen medido, relativo al umbral (1 = justo en el umbral). Para mostrarlo. */
  nivelRelativo = 0;
  private previos: Float32Array[] = [];
  private bloquesConVoz = 0;
  private enFragmento = false;
  private silencio = 0;
  private largo = 0;

  constructor(private readonly acciones: AccionesDetector) {}

  get escuchandoFragmento(): boolean {
    return this.enFragmento;
  }

  /** Recibe muestras del micrófono; `puedeEmpezar` es falso mientras Azul responde. */
  agregar(muestras: Float32Array, tasa: number, puedeEmpezar: boolean): void {
    this.acumulado.push(muestras);
    this.muestrasAcumuladas += muestras.length;
    if (this.muestrasAcumuladas < tasa * BLOQUE_SEGUNDOS) return;
    const bloque = new Float32Array(this.muestrasAcumuladas);
    let posicion = 0;
    for (const parte of this.acumulado) {
      bloque.set(parte, posicion);
      posicion += parte.length;
    }
    this.acumulado = [];
    this.muestrasAcumuladas = 0;
    this.procesar(bloque, puedeEmpezar);
  }

  /** Olvida el fragmento en curso (p. ej. si el usuario tocó el micrófono). */
  reiniciar(): void {
    this.enFragmento = false;
    this.bloquesConVoz = 0;
    this.previos = [];
    this.acumulado = [];
    this.muestrasAcumuladas = 0;
  }

  private procesar(bloque: Float32Array, puedeEmpezar: boolean): void {
    const nivel = volumen(bloque);
    const umbral = Math.max(VOLUMEN_MINIMO, this.ruidoDeFondo * VECES_SOBRE_EL_RUIDO);
    const hayVoz = nivel > umbral;
    this.nivelRelativo = nivel / umbral;

    if (!this.enFragmento) {
      // Se aprende el ruido de fondo solo cuando nadie habla.
      if (!hayVoz) this.ruidoDeFondo = this.ruidoDeFondo * 0.95 + nivel * 0.05;
      this.previos.push(bloque);
      if (this.previos.length > BLOQUES_PREVIOS) this.previos.shift();
      this.bloquesConVoz = hayVoz ? this.bloquesConVoz + 1 : 0;
      if (this.bloquesConVoz >= BLOQUES_CON_VOZ_PARA_EMPEZAR && puedeEmpezar) {
        this.enFragmento = true;
        this.silencio = 0;
        this.largo = 0;
        this.acciones.empezar(this.previos);
        this.previos = [];
      }
      return;
    }

    this.acciones.audio(bloque);
    this.largo++;
    this.silencio = hayVoz ? 0 : this.silencio + 1;
    if (this.silencio >= BLOQUES_DE_SILENCIO_PARA_TERMINAR || this.largo >= MAXIMO_BLOQUES) {
      this.enFragmento = false;
      this.bloquesConVoz = 0;
      this.acciones.terminar();
    }
  }
}

function volumen(bloque: Float32Array): number {
  let suma = 0;
  for (const muestra of bloque) suma += muestra * muestra;
  return Math.sqrt(suma / Math.max(1, bloque.length));
}
