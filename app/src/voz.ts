// Voz de Azul en la app: captura el micrófono (PCM 16 kHz), habla con el
// núcleo por WebSocket y reproduce las frases de respuesta en orden.

export type EventoVoz =
  | { tipo: "turno" }
  | { tipo: "escuchado"; texto: string; final: boolean }
  | { tipo: "texto"; texto: string }
  | { tipo: "buscando" }
  | { tipo: "gasto"; nivel: "aviso" | "bloqueo"; gastado: number; limite: number }
  | { tipo: "error"; mensaje: string }
  | { tipo: "nada_escuchado" }
  | { tipo: "parado" }
  | { tipo: "fin" };

const TASA_DESTINO = 16_000;
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

  constructor(
    private readonly alEvento: (evento: EventoVoz) => void,
    private readonly alCambiarReproduccion: (sonando: boolean) => void,
  ) {}

  get sonando(): boolean {
    return this.reproduciendo.size > 0;
  }

  /** Se llama al presionar el botón: interrumpe a Azul y empieza a escuchar. */
  async empezar(): Promise<void> {
    // El AudioContext debe crearse dentro del gesto del usuario (iPhone lo exige).
    const contexto = this.asegurarContexto();
    void contexto.resume();
    this.callar();
    const socket = await this.conectar();
    await this.prepararMicrofono();
    this.pendientes = [];
    this.muestrasPendientes = 0;
    socket.send(JSON.stringify({ tipo: "hablar_inicio" }));
    this.grabando = true;
  }

  /** Se llama al soltar el botón. */
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
        resolver(socket);
      };
      socket.onerror = () => {
        this.conectando = null;
        rechazar(new Error("No pude conectarme con Azul."));
      };
      socket.onclose = () => {
        if (this.socket === socket) this.socket = null;
      };
      socket.onmessage = (mensaje) => {
        if (mensaje.data instanceof ArrayBuffer) {
          if (this.aceptarAudio) this.reproducir(mensaje.data);
          return;
        }
        const evento = JSON.parse(mensaje.data as string) as EventoVoz;
        if (evento.tipo === "turno") this.aceptarAudio = true;
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

  private recibirMuestras(muestras: Float32Array): void {
    if (!this.grabando || !this.contexto) return;
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
        fuente.connect(contexto.destination);
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
