// Voz de Azul en la app: captura el micrófono (PCM 16 kHz), habla con el
// núcleo por WebSocket y reproduce las frases de respuesta en orden.

import { DetectorDeVoz } from "./deteccion";

export type EventoVoz =
  | { tipo: "turno" }
  | { tipo: "escucha_terminada" }
  | { tipo: "ignorado"; con_palabras?: boolean }
  | { tipo: "activado" }
  | { tipo: "escuchado"; texto: string; final: boolean }
  | { tipo: "texto"; texto: string }
  | { tipo: "buscando" }
  | { tipo: "gasto"; nivel: "aviso" | "bloqueo"; gastado: number; limite: number }
  | { tipo: "error"; mensaje: string }
  | { tipo: "nada_escuchado" }
  | { tipo: "otro_dispositivo" }
  | { tipo: "parado" }
  | { tipo: "interrumpido" }
  | { tipo: "no_eres_tu" }
  | { tipo: "interrupcion_no_disponible"; motivo?: string }
  | { tipo: "fin" };

const TASA_DESTINO = 16_000;
const VOLUMEN_VERIFICANDO = 0.2;
// Se envía audio cada ~100 ms para no saturar la conexión con mensajes diminutos.
const MUESTRAS_POR_ENVIO = 0.1;

export class Voz {
  private contexto: AudioContext | null = null;
  private socket: WebSocket | null = null;
  private conectando: Promise<WebSocket> | null = null;
  private microfono: Promise<void> | null = null;
  private grabando = false;
  private pendientes: Float32Array[] = [];
  private muestrasPendientes = 0;
  private reproduciendo = new Set<AudioBufferSourceNode>();
  private siguienteInicio = 0;
  private colaDecodificacion: Promise<void> = Promise.resolve();
  // Solo se acepta audio del turno actual; cambia al interrumpir.
  private aceptarAudio = false;
  private generacion = 0;
  // Modo "Oye Azul" (ADR 0025).
  private detector: DetectorDeVoz | null = null;
  private puedeActivarse: () => boolean = () => false;
  private turnoActivacion = false;
  private reintentos = 0;
  private reconexionPendiente = false;
  // Interrumpir con la voz (ADR 0036): mientras Azul responde, si alguien habla se
  // envía para que el núcleo verifique si es el usuario.
  private interrupcion: DetectorDeVoz | null = null;
  private puedeInterrumpir: () => boolean = () => false;
  // Grabación de una muestra para la huella de voz.
  private grabacion: Float32Array[] | null = null;
  // Mide el volumen de la voz de Azul para que el orbe se ilumine con ella.
  private analizador: AnalyserNode | null = null;
  // Mientras se verifica una posible interrupción, Azul baja la voz (ADR 0036).
  private volumen: GainNode | null = null;
  private muestrasSalida: Float32Array<ArrayBuffer> | null = null;
  private bandasSalida: Uint8Array<ArrayBuffer> | null = null;

  constructor(
    private readonly alEvento: (evento: EventoVoz) => void,
    private readonly alCambiarReproduccion: (sonando: boolean) => void,
  ) {}

  get sonando(): boolean {
    return this.reproduciendo.size > 0;
  }

  get escuchando(): boolean {
    return this.grabando;
  }

  get oyeAzulActivo(): boolean {
    return this.detector !== null;
  }

  /** Volumen actual relativo al umbral de detección (≥ 1 cuenta como voz). */
  get nivelDeVoz(): number {
    return this.detector?.nivelRelativo ?? 0;
  }

  /** Volumen (RMS, 0 a 1) de la voz de Azul en este instante; 0 si no habla. */
  get nivelDeSalida(): number {
    if (!this.analizador || !this.muestrasSalida || !this.sonando) return 0;
    this.analizador.getFloatTimeDomainData(this.muestrasSalida);
    let suma = 0;
    for (const muestra of this.muestrasSalida) suma += muestra * muestra;
    return Math.sqrt(suma / this.muestrasSalida.length);
  }

  /** Espectro de la voz de Azul (0 a 255 por banda), o null si no habla. */
  get espectroDeSalida(): Uint8Array | null {
    if (!this.analizador || !this.bandasSalida || !this.sonando) return null;
    this.analizador.getByteFrequencyData(this.bandasSalida);
    return this.bandasSalida;
  }

  get fragmentoEnCurso(): boolean {
    return this.detector?.escuchandoFragmento ?? false;
  }

  /** Verdadero si el turno en curso empezó por la detección de voz, no por un toque. */
  get turnoDeActivacion(): boolean {
    return this.turnoActivacion;
  }

  /** Se llama al tocar el micrófono: interrumpe a Azul y empieza a escuchar. */
  async empezar(): Promise<void> {
    // El AudioContext debe crearse dentro del gesto del usuario (iPhone lo exige).
    const contexto = this.asegurarContexto();
    void contexto.resume();
    this.callar();
    this.detector?.reiniciar();
    const socket = await this.conectar();
    await this.prepararMicrofono();
    this.pendientes = [];
    this.muestrasPendientes = 0;
    this.turnoActivacion = false;
    socket.send(JSON.stringify({ tipo: "hablar_inicio" }));
    this.grabando = true;
  }

  /**
   * Activa la escucha de "Oye Azul". Debe llamarse desde un toque del usuario.
   * `puedeActivarse` devuelve falso mientras Azul piensa o habla, para que no se
   * escuche a sí mismo.
   */
  async activarOyeAzul(puedeActivarse: () => boolean): Promise<void> {
    const contexto = this.asegurarContexto();
    await contexto.resume();
    await this.conectar();
    await this.prepararMicrofono();
    this.puedeActivarse = puedeActivarse;
    this.detector = new DetectorDeVoz({
      empezar: (previos) => {
        this.turnoActivacion = true;
        this.enviar({ tipo: "activacion_inicio" });
        for (const bloque of previos) this.enviarAudio(bloque);
      },
      audio: (bloque) => this.enviarAudio(bloque),
      terminar: () => this.enviar({ tipo: "activacion_fin" }),
    });
  }

  /**
   * Activa interrumpir con la voz. `puedeInterrumpir` dice si Azul está respondiendo.
   * Debe llamarse con la huella del usuario ya inscrita en el núcleo.
   */
  async activarInterrupcion(puedeInterrumpir: () => boolean): Promise<void> {
    this.puedeInterrumpir = puedeInterrumpir;
    this.interrupcion ??= new DetectorDeVoz({
      empezar: (previos) => {
        this.cambiarVolumen(VOLUMEN_VERIFICANDO);
        this.enviar({ tipo: "interrupcion_inicio" });
        for (const bloque of previos) this.enviarAudio(bloque);
      },
      audio: (bloque) => this.enviarAudio(bloque),
      terminar: () => this.enviar({ tipo: "interrupcion_fin" }),
    });
  }

  desactivarInterrupcion(): void {
    if (this.interrupcion?.escuchandoFragmento) this.enviar({ tipo: "interrupcion_fin" });
    this.interrupcion = null;
  }

  /** Graba unos segundos del micrófono (PCM 16 kHz) para enseñarle la voz a Azul. */
  async grabarMuestra(segundos: number): Promise<Int16Array<ArrayBuffer>> {
    const contexto = this.asegurarContexto();
    await contexto.resume();
    await this.prepararMicrofono();
    this.grabacion = [];
    await new Promise((listo) => setTimeout(listo, segundos * 1000));
    const bloques = this.grabacion;
    this.grabacion = null;
    const total = bloques.reduce((suma, b) => suma + b.length, 0);
    const juntas = new Float32Array(total);
    let posicion = 0;
    for (const bloque of bloques) {
      juntas.set(bloque, posicion);
      posicion += bloque.length;
    }
    return aPcm16(juntas, contexto.sampleRate);
  }

  desactivarOyeAzul(): void {
    if (this.detector?.escuchandoFragmento) this.enviar({ tipo: "activacion_fin" });
    this.detector = null;
  }

  /** Tono corto que confirma que Azul escuchó "Oye Azul". */
  tono(): void {
    const contexto = this.asegurarContexto();
    const oscilador = contexto.createOscillator();
    const volumen = contexto.createGain();
    oscilador.frequency.value = 880;
    volumen.gain.setValueAtTime(0.0001, contexto.currentTime);
    volumen.gain.exponentialRampToValueAtTime(0.2, contexto.currentTime + 0.02);
    volumen.gain.exponentialRampToValueAtTime(0.0001, contexto.currentTime + 0.18);
    oscilador.connect(volumen).connect(contexto.destination);
    oscilador.start();
    oscilador.stop(contexto.currentTime + 0.2);
  }

  /** Deja de escuchar: lo pide Azul al detectar silencio, o el usuario al tocar de nuevo. */
  terminar(): void {
    if (!this.grabando) return;
    this.enviarPendientes();
    this.grabando = false;
    this.socket?.send(JSON.stringify({ tipo: "hablar_fin" }));
  }

  /** Corta la respuesta en curso: la voz y lo que Azul esté pensando. */
  parar(): void {
    this.grabando = false;
    this.callar();
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ tipo: "parar" }));
    }
  }

  private salida(contexto: AudioContext): AudioNode {
    if (!this.analizador) {
      this.analizador = contexto.createAnalyser();
      this.analizador.fftSize = 1024;
      this.muestrasSalida = new Float32Array(this.analizador.fftSize);
      this.bandasSalida = new Uint8Array(this.analizador.frequencyBinCount);
      this.volumen = contexto.createGain();
      this.analizador.connect(this.volumen).connect(contexto.destination);
    }
    return this.analizador;
  }

  private cambiarVolumen(valor: number): void {
    if (!this.volumen || !this.contexto) return;
    // Un cambio suave (0,15 s), sin chasquidos.
    this.volumen.gain.setTargetAtTime(valor, this.contexto.currentTime, 0.05);
  }

  private asegurarContexto(): AudioContext {
    this.contexto ??= new AudioContext();
    return this.contexto;
  }

  private conectar(): Promise<WebSocket> {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve(this.socket);
    this.conectando ??= new Promise<WebSocket>((resolver, rechazar) => {
      const protocolo = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocolo}://${location.host}/api/voz`);
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        this.socket = socket;
        this.conectando = null;
        this.reintentos = 0;
        resolver(socket);
      };
      socket.onerror = () => {
        this.conectando = null;
        rechazar(new Error("No pude conectarme con Azul."));
      };
      socket.onclose = () => {
        if (this.socket === socket) this.socket = null;
        // Si se corta (Azul se reinició, el celular cambió de red…), "Oye Azul" se
        // reconecta solo para seguir escuchando.
        this.detector?.reiniciar();
        this.programarReconexion();
      };
      socket.onmessage = (mensaje) => {
        if (mensaje.data instanceof ArrayBuffer) {
          if (this.aceptarAudio) this.reproducir(mensaje.data);
          return;
        }
        const evento = JSON.parse(mensaje.data as string) as EventoVoz;
        if (evento.tipo === "turno") this.aceptarAudio = true;
        // Era la voz del usuario: Azul se calla y lo que sigue diciendo es su nuevo mensaje.
        if (evento.tipo === "no_eres_tu" || evento.tipo === "interrupcion_no_disponible") {
          this.cambiarVolumen(1);
        }
        if (evento.tipo === "interrumpido") {
          this.callar();
          this.cambiarVolumen(1);
          this.interrupcion?.reiniciar();
          this.pendientes = [];
          this.muestrasPendientes = 0;
          this.turnoActivacion = false;
          this.grabando = true;
        }
        // Ruido sin palabras: el detector aprende su nivel (nunca de una conversación ajena).
        if (evento.tipo === "ignorado" && evento.con_palabras === false) this.detector?.aprenderRuido();
        // Azul detectó que terminaste de hablar: se apaga el micrófono (o se cierra el
        // fragmento de "Oye Azul" sin esperar a que el detector oiga el silencio).
        if (evento.tipo === "escucha_terminada") {
          if (this.detector?.escuchandoFragmento) {
            this.detector.reiniciar();
            this.enviar({ tipo: "activacion_fin" });
          }
          this.terminar();
        }
        this.alEvento(evento);
      };
    });
    return this.conectando;
  }

  private prepararMicrofono(): Promise<void> {
    this.microfono ??= (async () => {
      const contexto = this.asegurarContexto();
      const flujo = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      await contexto.audioWorklet.addModule("/captura-worklet.js");
      const fuente = contexto.createMediaStreamSource(flujo);
      const captura = new AudioWorkletNode(contexto, "captura");
      captura.port.onmessage = (mensaje: MessageEvent<Float32Array>) => this.recibirMuestras(mensaje.data);
      fuente.connect(captura);
    })().catch((error: unknown) => {
      this.microfono = null; // permite reintentar si el usuario negó el permiso
      throw error;
    });
    return this.microfono;
  }

  private programarReconexion(): void {
    if (!this.detector || this.reconexionPendiente) return;
    this.reconexionPendiente = true;
    // Espera creciente: 1 s, 2 s, 4 s… hasta 15 s entre intentos.
    const espera = Math.min(15_000, 1000 * 2 ** this.reintentos);
    setTimeout(() => {
      this.reconexionPendiente = false;
      if (!this.detector) return;
      this.conectar().catch(() => {
        this.reintentos++;
        this.programarReconexion();
      });
    }, espera);
  }

  private enviar(mensaje: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(mensaje));
  }

  private enviarAudio(bloque: Float32Array): void {
    if (this.contexto && this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(aPcm16(bloque, this.contexto.sampleRate));
    }
  }

  private recibirMuestras(muestras: Float32Array): void {
    if (!this.contexto) return;
    if (this.grabacion) {
      this.grabacion.push(muestras);
      return;
    }
    if (!this.grabando && this.interrupcion) {
      if (this.puedeInterrumpir()) {
        this.interrupcion.agregar(muestras, this.contexto.sampleRate, true);
        return;
      }
      if (this.interrupcion.escuchandoFragmento) {
        // Azul terminó de responder a mitad de la posible interrupción.
        this.interrupcion.reiniciar();
        this.enviar({ tipo: "interrupcion_fin" });
      }
    }
    if (!this.grabando) {
      const puedeEmpezar = this.puedeActivarse() && !this.sonando;
      this.detector?.agregar(muestras, this.contexto.sampleRate, puedeEmpezar);
      return;
    }
    this.pendientes.push(muestras);
    this.muestrasPendientes += muestras.length;
    if (this.muestrasPendientes >= this.contexto.sampleRate * MUESTRAS_POR_ENVIO) {
      this.enviarPendientes();
    }
  }

  private enviarPendientes(): void {
    if (!this.contexto || this.muestrasPendientes === 0) return;
    const juntas = new Float32Array(this.muestrasPendientes);
    let posicion = 0;
    for (const bloque of this.pendientes) {
      juntas.set(bloque, posicion);
      posicion += bloque.length;
    }
    this.pendientes = [];
    this.muestrasPendientes = 0;
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(aPcm16(juntas, this.contexto.sampleRate));
    }
  }

  private reproducir(mp3: ArrayBuffer): void {
    const contexto = this.asegurarContexto();
    const generacion = this.generacion;
    // Se decodifica en orden para que las frases suenen en el orden correcto.
    this.colaDecodificacion = this.colaDecodificacion.then(async () => {
      try {
        const audio = await contexto.decodeAudioData(mp3);
        if (generacion !== this.generacion) return; // llegó tarde: Azul ya fue interrumpido
        const fuente = contexto.createBufferSource();
        fuente.buffer = audio;
        fuente.connect(this.salida(contexto));
        const inicio = Math.max(contexto.currentTime, this.siguienteInicio);
        fuente.start(inicio);
        this.siguienteInicio = inicio + audio.duration;
        this.reproduciendo.add(fuente);
        this.alCambiarReproduccion(true);
        fuente.onended = () => {
          this.reproduciendo.delete(fuente);
          if (!this.sonando) this.alCambiarReproduccion(false);
        };
      } catch {
        this.alEvento({ tipo: "error", mensaje: "No pude reproducir una frase." });
      }
    });
  }

  private callar(): void {
    this.aceptarAudio = false;
    this.generacion++;
    for (const fuente of this.reproduciendo) {
      fuente.onended = null;
      fuente.stop();
    }
    this.reproduciendo.clear();
    this.siguienteInicio = 0;
    this.colaDecodificacion = Promise.resolve();
    this.alCambiarReproduccion(false);
  }
}

/** Convierte audio en coma flotante a PCM de 16 bits a 16 kHz (promediando muestras). */
function aPcm16(muestras: Float32Array, tasaOrigen: number): Int16Array<ArrayBuffer> {
  const proporcion = tasaOrigen / TASA_DESTINO;
  const largo = Math.floor(muestras.length / proporcion);
  const salida = new Int16Array(largo);
  for (let i = 0; i < largo; i++) {
    const inicio = Math.floor(i * proporcion);
    const fin = Math.min(muestras.length, Math.floor((i + 1) * proporcion));
    let suma = 0;
    for (let j = inicio; j < fin; j++) suma += muestras[j];
    const valor = Math.max(-1, Math.min(1, suma / Math.max(1, fin - inicio)));
    salida[i] = valor < 0 ? valor * 0x8000 : valor * 0x7fff;
  }
  return salida;
}
