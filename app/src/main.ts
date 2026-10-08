import "./style.css";
import {
  Orbe,
  type Conocimiento,
  type EstadoOrbe,
  type LecturaOrbe,
  type NeuronaSenalada,
} from "./orbe";
import { Voz, type EventoVoz } from "./voz";

type Rol = "user" | "assistant";

interface MensajeGuardado {
  rol: Rol;
  texto: string;
  fecha: string;
}

interface Gasto {
  gastado_mes: number;
  limite: number;
  aviso: number;
}

type EventoChat = Extract<EventoVoz, { tipo: "texto" | "buscando" | "gasto" | "error" | "fin" }>;

const estado = elemento<HTMLParagraphElement>("#estado");
const gastoDelMes = elemento<HTMLParagraphElement>("#gasto");
const conversacion = elemento<HTMLElement>("#conversacion");
const formulario = elemento<HTMLFormElement>("#formulario");
const texto = elemento<HTMLTextAreaElement>("#texto");
const botonEnviar = elemento<HTMLButtonElement>("#enviar");
const botonParar = elemento<HTMLButtonElement>("#parar");
const botonMicrofono = elemento<HTMLButtonElement>("#microfono");

const placeholderNormal = texto.placeholder;

let respuestaEnCurso: AbortController | null = null;
let respondiendoPorVoz = false;
let burbujaEscuchada: HTMLDivElement | null = null;
let burbujaVoz: HTMLDivElement | null = null;

const voz = new Voz(alEventoDeVoz, () => {
  actualizarBotones();
  continuarConversacion();
});

// Modo conversación (ADR 0026): tras cada respuesta, Azul vuelve a escuchar sola
// hasta que el usuario se despide, toca ■ o se queda callado.
let enConversacion = false;
let turnosEnConversacion = 0;
const PAUSA_ANTES_DE_ESCUCHAR_MS = 350; // que no se cuele el final de la voz de Azul

function iniciarConversacion(): void {
  enConversacion = true;
  turnosEnConversacion = 0;
}

function terminarConversacion(aviso?: string): void {
  if (!enConversacion) return;
  enConversacion = false;
  if (aviso) agregarBurbuja("aviso", aviso);
}

function continuarConversacion(): void {
  if (!enConversacion) return;
  setTimeout(() => {
    const ocupada = voz.escuchando || respondiendoPorVoz || voz.sonando || respuestaEnCurso !== null;
    if (enConversacion && !ocupada) void empezarAHablar();
  }, PAUSA_ANTES_DE_ESCUCHAR_MS);
}

function elemento<T extends Element>(selector: string): T {
  const encontrado = document.querySelector<T>(selector);
  if (!encontrado) throw new Error(`Falta el elemento ${selector}`);
  return encontrado;
}

function agregarBurbuja(rol: Rol | "aviso", contenido = ""): HTMLDivElement {
  const burbuja = document.createElement("div");
  burbuja.className = `burbuja ${rol}`;
  burbuja.textContent = contenido;
  conversacion.append(burbuja);
  bajarAlFinal();
  return burbuja;
}

function bajarAlFinal(): void {
  conversacion.scrollTop = conversacion.scrollHeight;
}

function dinero(valor: number): string {
  return `$${valor.toFixed(2)}`;
}

function avisoDeGasto(evento: Extract<EventoVoz, { tipo: "gasto" }>): string {
  return evento.nivel === "bloqueo"
    ? `Llegaste al límite de ${dinero(evento.limite)} de este mes. Azul queda en pausa hasta el próximo mes.`
    : `Ojo: llevas ${dinero(evento.gastado)} de ${dinero(evento.limite)} este mes.`;
}

// --- Estado y gasto ---

async function actualizarGasto(): Promise<void> {
  try {
    const respuesta = await fetch("/api/gasto");
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    const gasto: Gasto = await respuesta.json();
    const resumen = `Gasto del mes: ${dinero(gasto.gastado_mes)} de ${dinero(gasto.limite)}`;
    // Arriba solo aparece si hay que avisar; el dato completo vive en el historial.
    gastoDelMes.textContent = resumen;
    estado.textContent = gasto.gastado_mes >= gasto.aviso ? resumen : "";
    estado.dataset.nivel = gasto.gastado_mes >= gasto.aviso ? "aviso" : "ok";
    // Tras cada respuesta Azul pudo aprender algo: la red se pone al día.
    void actualizarConocimiento();
  } catch {
    estado.textContent = "No encuentro el núcleo de Azul. ¿Está encendido?";
    estado.dataset.nivel = "error";
  }
}

async function cargarHistorial(): Promise<void> {
  try {
    const respuesta = await fetch("/api/historial?limite=50");
    if (!respuesta.ok) return;
    const mensajes: MensajeGuardado[] = await respuesta.json();
    for (const mensaje of mensajes) agregarBurbuja(mensaje.rol, mensaje.texto);
  } catch {
    // Sin núcleo no hay historial; actualizarGasto ya muestra el aviso.
  }
}

type EstadoMicrofono = "inactivo" | "escuchando" | "respondiendo";

function estadoMicrofono(): EstadoMicrofono {
  if (voz.escuchando) return "escuchando";
  if (respondiendoPorVoz || voz.sonando) return "respondiendo";
  return "inactivo";
}

const ETIQUETAS_MICROFONO: Record<EstadoMicrofono, string> = {
  inactivo: "Toca para hablarle a Azul",
  escuchando: "Te escucho. Toca para enviar ya",
  respondiendo: "Toca para callar a Azul",
};

function actualizarBotones(): void {
  // Parar es solo para el chat de texto; en la voz, el mismo micrófono detiene.
  const escribiendoRespuesta = respuestaEnCurso !== null;
  botonEnviar.hidden = escribiendoRespuesta;
  botonParar.hidden = !escribiendoRespuesta;
  texto.disabled = escribiendoRespuesta;

  const estadoActual = estadoMicrofono();
  botonMicrofono.dataset.estado = estadoActual;
  botonMicrofono.setAttribute("aria-label", ETIQUETAS_MICROFONO[estadoActual]);
  botonMicrofono.title = ETIQUETAS_MICROFONO[estadoActual];
  botonMicrofono.dataset.conversacion = String(enConversacion);
  texto.placeholder = enConversacion
    ? "Conversando… di «adiós» o toca ■ para terminar"
    : estadoActual === "escuchando"
      ? "Te escucho… cuando termines, Azul responde solo"
      : placeholderNormal;
}

// --- Chat de texto ---

function mostrarEventoDeChat(evento: EventoChat, burbuja: HTMLDivElement): void {
  switch (evento.tipo) {
    case "texto":
      burbuja.classList.remove("pensando", "buscando");
      burbuja.textContent += evento.texto;
      bajarAlFinal();
      break;
    case "buscando":
      burbuja.classList.add("buscando");
      break;
    case "error":
      agregarBurbuja("aviso", evento.mensaje);
      break;
    case "gasto":
      agregarBurbuja("aviso", avisoDeGasto(evento));
      break;
    case "fin":
      break;
  }
}

async function enviar(mensaje: string): Promise<void> {
  voz.parar();
  terminarConversacion();
  agregarBurbuja("user", mensaje);
  const burbuja = agregarBurbuja("assistant");
  burbuja.classList.add("pensando");
  respuestaEnCurso = new AbortController();
  actualizarBotones();

  try {
    const respuesta = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: mensaje }),
      signal: respuestaEnCurso.signal,
    });
    if (!respuesta.ok || !respuesta.body) throw new Error(`HTTP ${respuesta.status}`);

    const lector = respuesta.body.pipeThrough(new TextDecoderStream()).getReader();
    let pendiente = "";
    for (;;) {
      const { value, done } = await lector.read();
      if (done) break;
      pendiente += value;
      const lineas = pendiente.split("\n");
      pendiente = lineas.pop() ?? "";
      for (const linea of lineas) {
        if (linea.trim()) mostrarEventoDeChat(JSON.parse(linea) as EventoChat, burbuja);
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      burbuja.classList.add("interrumpida");
    } else {
      agregarBurbuja("aviso", "Se perdió la conexión con Azul. Intenta de nuevo.");
    }
  } finally {
    burbuja.classList.remove("pensando", "buscando");
    if (!burbuja.textContent) burbuja.remove();
    respuestaEnCurso = null;
    actualizarBotones();
    if (!formulario.hidden) texto.focus();
    void actualizarGasto();
  }
}

// --- Voz ---

function alEventoDeVoz(evento: EventoVoz): void {
  switch (evento.tipo) {
    case "turno":
      burbujaVoz = null;
      // En modo "Oye Azul" no se muestra nada hasta saber que le hablan a Azul.
      burbujaEscuchada = null;
      if (!voz.turnoDeActivacion) {
        burbujaEscuchada = agregarBurbuja("user");
        burbujaEscuchada.classList.add("escuchando");
      }
      break;
    case "escuchado":
      if (!burbujaEscuchada) {
        burbujaEscuchada = agregarBurbuja("user");
        burbujaEscuchada.classList.add("escuchando");
      }
      burbujaEscuchada.textContent = evento.texto;
      if (evento.final) burbujaEscuchada.classList.remove("escuchando");
      if (evento.final) {
        // Apenas termina de escuchar, Azul muestra que está pensando.
        respondiendoPorVoz = true;
        burbujaVoz = agregarBurbuja("assistant");
        burbujaVoz.classList.add("pensando");
      }
      break;
    case "escucha_terminada":
      // Ya no escucha; mientras llega la respuesta, el botón sirve para callar a Azul.
      respondiendoPorVoz = true;
      break;
    case "ignorado":
      // La voz captada no era para Azul: no se muestra ni se guarda nada.
      burbujaEscuchada?.remove();
      burbujaEscuchada = null;
      break;
    case "activado":
      // Dijeron solo "Oye Azul": suena un tono y Azul queda escuchando la pregunta.
      burbujaEscuchada?.remove();
      burbujaEscuchada = null;
      voz.tono();
      iniciarConversacion();
      void empezarAHablar();
      break;
    case "otro_dispositivo":
      // Otro dispositivo (p. ej. el portátil) ya responde lo mismo: aquí no se responde.
      respondiendoPorVoz = false;
      burbujaEscuchada?.remove();
      burbujaEscuchada = null;
      terminarConversacion();
      break;
    case "nada_escuchado":
      respondiendoPorVoz = false;
      burbujaEscuchada?.remove();
      if (enConversacion && turnosEnConversacion > 0) {
        terminarConversacion("Terminé la conversación. Toca el micrófono cuando quieras seguir.");
      } else {
        terminarConversacion();
        agregarBurbuja("aviso", "No te escuché. Toca el micrófono y habla cuando se ilumine.");
      }
      break;
    case "texto":
    case "buscando":
      burbujaVoz ??= agregarBurbuja("assistant");
      mostrarEventoDeChat(evento, burbujaVoz);
      break;
    case "gasto":
    case "error":
      if (burbujaEscuchada && !burbujaEscuchada.textContent) burbujaEscuchada.remove();
      agregarBurbuja("aviso", evento.tipo === "gasto" ? avisoDeGasto(evento) : evento.mensaje);
      break;
    case "interrumpido":
      // El usuario habló encima de Azul y era su voz (ADR 0036): ella se calla, lo que
      // dijo queda a medias en el historial y lo que él dice es el siguiente mensaje.
      terminarBurbujaDeVoz(true);
      break;
    case "no_eres_tu":
      break;
    case "interrupcion_no_disponible":
      // Sin huella, nadie puede interrumpir (ADR 0036): se explica una sola vez.
      if (evento.motivo === "sin_huella" && !avisoSinHuella) {
        avisoSinHuella = true;
        agregarBurbuja(
          "aviso",
          "Para interrumpirme hablando, primero enséñame tu voz: abre la conversación, «Tu voz» y «Enseñarle mi voz».",
        );
      }
      break;
    case "parado":
      // Si ya estamos escuchando, es solo la confirmación de que nuestro turno nuevo
      // interrumpió al anterior (p. ej. tras "Oye Azul"): la conversación sigue.
      if (voz.escuchando) break;
      // "Para", "adiós", "eso es todo"… o ■: se termina la conversación.
      terminarBurbujaDeVoz(true);
      terminarConversacion();
      void actualizarGasto();
      break;
    case "fin":
      burbujaEscuchada?.classList.remove("escuchando");
      if (burbujaVoz) turnosEnConversacion++;
      terminarBurbujaDeVoz(false);
      void actualizarGasto();
      continuarConversacion();
      break;
  }
  // Ante un error o el límite de gasto, no se insiste en bucle.
  if (evento.tipo === "error" || (evento.tipo === "gasto" && evento.nivel === "bloqueo")) {
    terminarConversacion();
  }
  actualizarBotones();
}

function terminarBurbujaDeVoz(interrumpida: boolean): void {
  respondiendoPorVoz = false;
  if (!burbujaVoz) return;
  burbujaVoz.classList.remove("pensando", "buscando");
  if (!burbujaVoz.textContent) burbujaVoz.remove();
  else if (interrumpida) burbujaVoz.classList.add("interrumpida");
  burbujaVoz = null;
}

async function empezarAHablar(): Promise<void> {
  try {
    await voz.empezar();
  } catch (error) {
    const permisoNegado = error instanceof DOMException && error.name === "NotAllowedError";
    agregarBurbuja(
      "aviso",
      permisoNegado
        ? "Necesito permiso para usar el micrófono. Actívalo en la configuración del navegador."
        : "No pude activar el micrófono ni conectarme con Azul.",
    );
  }
  actualizarBotones();
}

// Un solo botón (ADR 0011): toca para hablar; Azul detecta solo cuando terminas.
// Mientras Azul escucha, tocar envía ya; mientras responde, tocar lo calla.
botonMicrofono.addEventListener("click", () => {
  switch (estadoMicrofono()) {
    case "inactivo":
      // Un toque empieza una conversación: Azul seguirá escuchando tras cada respuesta.
      iniciarConversacion();
      void empezarAHablar();
      break;
    case "escuchando":
      voz.terminar();
      break;
    case "respondiendo":
      voz.parar();
      terminarBurbujaDeVoz(true);
      terminarConversacion();
      break;
  }
  actualizarBotones();
});

// --- "Oye Azul" (ADR 0025) ---

const botonOyeAzul = elemento<HTMLButtonElement>("#oye-azul");
let bloqueoDePantalla: WakeLockSentinel | null = null;

async function mantenerPantallaEncendida(activa: boolean): Promise<void> {
  // En el celular, "Oye Azul" solo funciona con la pantalla encendida.
  try {
    if (activa && "wakeLock" in navigator) {
      bloqueoDePantalla = await navigator.wakeLock.request("screen");
    } else {
      await bloqueoDePantalla?.release();
      bloqueoDePantalla = null;
    }
  } catch {
    // Si el navegador no lo permite, sigue funcionando mientras la pantalla esté encendida.
  }
}

function mostrarOyeAzul(): void {
  const activo = voz.oyeAzulActivo;
  botonOyeAzul.setAttribute("aria-pressed", String(activo));
  botonOyeAzul.title = activo
    ? "Escuchando \"Oye Azul\". Toca para desactivar"
    : "Escuchar \"Oye Azul\" con la app abierta";
  if (activo) requestAnimationFrame(animarNivel);
}

// Barra de nivel dentro del botón: muestra que el micrófono te oye. Se llena al
// hablar y se pone verde cuando cuenta como voz y se envía a Azul.
function animarNivel(): void {
  if (!voz.oyeAzulActivo) {
    botonOyeAzul.style.removeProperty("--nivel");
    delete botonOyeAzul.dataset.enviando;
    return;
  }
  botonOyeAzul.style.setProperty("--nivel", String(Math.min(1, voz.nivelDeVoz / 2)));
  botonOyeAzul.dataset.enviando = String(voz.fragmentoEnCurso);
  requestAnimationFrame(animarNivel);
}

botonOyeAzul.addEventListener("click", async () => {
  if (voz.oyeAzulActivo) {
    voz.desactivarOyeAzul();
    void mantenerPantallaEncendida(false);
  } else {
    try {
      await voz.activarOyeAzul(() => estadoMicrofono() === "inactivo" && respuestaEnCurso === null);
      void mantenerPantallaEncendida(true);
      agregarBurbuja("aviso", "Te escucho: di \"Oye Azul\" y lo que necesites. Deja la app abierta y la pantalla encendida.");
    } catch {
      agregarBurbuja("aviso", "No pude activar el micrófono para \"Oye Azul\".");
    }
  }
  mostrarOyeAzul();
});

// Al volver a la app, el navegador suelta el bloqueo de pantalla: se pide de nuevo.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && voz.oyeAzulActivo) {
    void mantenerPantallaEncendida(true);
  }
});

// --- Formulario ---

formulario.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const mensaje = texto.value.trim();
  if (!mensaje || respuestaEnCurso) return;
  texto.value = "";
  void enviar(mensaje);
});

texto.addEventListener("keydown", (evento) => {
  // Enter envía; Shift+Enter hace un salto de línea.
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    formulario.requestSubmit();
  }
});

// Al empezar a escribir, Azul prepara su caché (solo si hace falta) para responder antes.
let ultimoPrecalentamiento = 0;
texto.addEventListener("input", () => {
  if (Date.now() - ultimoPrecalentamiento < 60_000) return;
  ultimoPrecalentamiento = Date.now();
  void fetch("/api/precalentar", { method: "POST" }).catch(() => undefined);
});

botonParar.title = "Interrumpe la respuesta de Azul";
botonParar.addEventListener("click", () => {
  respuestaEnCurso?.abort();
  actualizarBotones();
});

// --- Orbe y subtítulos: la voz domina la pantalla; el texto acompaña ---

const escena = elemento<HTMLElement>("#escena");
const subtitulos = elemento<HTMLElement>("#subtitulos");
const estadoVoz = elemento<HTMLParagraphElement>("#estado-voz");
const subtituloUsuario = elemento<HTMLParagraphElement>("#subtitulo-usuario");
const subtituloAzul = elemento<HTMLParagraphElement>("#subtitulo-azul");

function estadoVisual(): EstadoOrbe {
  if (voz.sonando) return "hablando";
  if (conversacion.querySelector(".burbuja.buscando")) return "buscando";
  if (voz.escuchando) return "escuchando";
  if (respondiendoPorVoz || respuestaEnCurso) return "pensando";
  if (voz.oyeAzulActivo) return "atento";
  return "reposo";
}

const TEXTO_DE_ESTADO: Record<EstadoOrbe, string> = {
  reposo: "",
  atento: "Di «Oye Azul»",
  escuchando: "Te escucho…",
  pensando: "Pensando…",
  buscando: "Buscando en internet…",
  hablando: "",
};

let estadoMostrado: EstadoOrbe | null = null;

// Solo en desarrollo: ?estado=hablando muestra un estado sin hablar con Azul.
const estadoDePrueba = import.meta.env.DEV
  ? (new URLSearchParams(location.search).get("estado") as EstadoOrbe | null)
  : null;

// Los subtítulos acompañan la conversación y se desvanecen cuando Azul queda en calma.
const SEGUNDOS_ANTES_DE_OCULTAR = 7;
let ocultarSubtitulos: number | undefined;

function mostrarFrases(visibles: boolean): void {
  window.clearTimeout(ocultarSubtitulos);
  subtitulos.dataset.frases = String(visibles);
}

function ocultarFrasesLuego(): void {
  window.clearTimeout(ocultarSubtitulos);
  ocultarSubtitulos = window.setTimeout(() => mostrarFrases(false), SEGUNDOS_ANTES_DE_OCULTAR * 1000);
}

function enCalma(estadoActual: EstadoOrbe): boolean {
  return estadoActual === "reposo" || estadoActual === "atento";
}

let espectroDePrueba: Uint8Array | null = null;

function leerOrbe(): LecturaOrbe {
  if (cursor) mostrarNeurona(cursor.x, cursor.y);
  const estadoActual = estadoDePrueba ?? estadoVisual();
  if (estadoActual !== estadoMostrado) {
    estadoMostrado = estadoActual;
    document.body.dataset.voz = estadoActual;
    estadoVoz.textContent = TEXTO_DE_ESTADO[estadoActual];
    if (enCalma(estadoActual)) ocultarFrasesLuego();
    else if (subtituloUsuario.textContent || subtituloAzul.textContent) mostrarFrases(true);
  }
  const reservaInferior = subtitulos.dataset.frases === "true" ? subtitulos.offsetHeight : estadoVoz.offsetHeight;
  if (estadoDePrueba === "hablando") {
    // Un volumen y un espectro sintéticos que suben y bajan como sílabas.
    const t = performance.now() / 1000;
    const nivel = Math.max(0.03, Math.sin(t * 9) * Math.sin(t * 2.3)) * 0.14;
    espectroDePrueba ??= new Uint8Array(512);
    for (let i = 0; i < espectroDePrueba.length; i++) {
      espectroDePrueba[i] = Math.max(0, 255 * nivel * 6 * Math.exp(-i / 40) * (0.6 + 0.4 * Math.sin(i * 0.7 + t * 11)));
    }
    return { estado: estadoActual, nivel, espectro: espectroDePrueba, reservaInferior };
  }
  return { estado: estadoActual, nivel: voz.nivelDeSalida, espectro: voz.espectroDeSalida, reservaInferior };
}

const orbe = new Orbe(elemento<HTMLCanvasElement>("#orbe"), escena, leerOrbe);
const saber = elemento<HTMLParagraphElement>("#saber");
let conocimientoActual: Conocimiento | null = null;

// --- Qué sabe cada neurona: al pasar el cursor (o tocarla en el celular) ---

const neurona = elemento<HTMLDivElement>("#neurona");
let ocultarNeurona: number | undefined;
// Donde está el cursor sobre el orbe: como la red gira, se vuelve a mirar en cada cuadro.
let cursor: { x: number; y: number } | null = null;
// El aviso de que falta la huella de voz sale una sola vez por sesión.
let avisoSinHuella = false;
let claveMostrada = "";

function etiquetaDe(senalada: NeuronaSenalada): [string, string] | null {
  const datos = conocimientoActual;
  if (!datos) return null;
  const nombre = senalada.clave.slice(senalada.grupo.length + 1, senalada.clave.lastIndexOf(":"));
  switch (senalada.grupo) {
    case "memoria": {
      const texto = datos.etiquetas?.recuerdos[Number(senalada.clave.slice(1))];
      return texto ? ["Recuerdo", texto] : null;
    }
    case "habilidad":
      return ["Habilidad", datos.etiquetas?.habilidades[nombre] ?? nombre];
    case "herramienta":
      return ["Herramienta", datos.etiquetas?.herramientas[nombre] ?? nombre];
    default:
      return ["Lo conversado", cantidad(datos.mensajes, "mensaje", "mensajes")];
  }
}

function mostrarNeurona(x: number, y: number, duracionMs?: number): void {
  window.clearTimeout(ocultarNeurona);
  const senalada = orbe.neuronaEn(x, y);
  const etiqueta = senalada ? etiquetaDe(senalada) : null;
  if (!etiqueta) {
    neurona.hidden = true;
    return;
  }
  const [tipo, texto] = etiqueta;
  if (senalada && senalada.clave !== claveMostrada) {
    claveMostrada = senalada.clave;
    neurona.dataset.tipo = senalada.grupo;
    neurona.replaceChildren(
      Object.assign(document.createElement("span"), { className: "neurona-tipo", textContent: tipo }),
      Object.assign(document.createElement("span"), { textContent: texto }),
    );
  }
  neurona.hidden = false;
  // Junto al cursor, sin salirse de la pantalla.
  const ancho = neurona.offsetWidth;
  const alto = neurona.offsetHeight;
  neurona.style.left = `${Math.min(window.innerWidth - ancho - 12, x + 16)}px`;
  neurona.style.top = `${Math.max(12, y - alto - 12)}px`;
  if (duracionMs) ocultarNeurona = window.setTimeout(() => (neurona.hidden = true), duracionMs);
}

function sobreLaInterfaz(objetivo: EventTarget | null): boolean {
  return objetivo instanceof Element && objetivo.closest("button, .top, .pie, .entrada, .historial, dialog, .subtitulos") !== null;
}

document.addEventListener("pointermove", (evento) => {
  if (evento.pointerType !== "mouse") return;
  if (sobreLaInterfaz(evento.target)) {
    cursor = null;
    neurona.hidden = true;
    orbe.neuronaEn(-1000, -1000);
    return;
  }
  cursor = { x: evento.clientX, y: evento.clientY };
  mostrarNeurona(cursor.x, cursor.y);
});

document.addEventListener("pointerdown", (evento) => {
  if (evento.pointerType === "mouse" || sobreLaInterfaz(evento.target)) return;
  mostrarNeurona(evento.clientX, evento.clientY, 2500);
});

document.addEventListener("pointerleave", () => {
  cursor = null;
  neurona.hidden = true;
  orbe.neuronaEn(-1000, -1000);
});

function cantidad(numero: number, singular: string, plural: string): string {
  return `${numero} ${numero === 1 ? singular : plural}`;
}

// La red neuronal crece con lo que Azul sabe: recuerdos, habilidades y herramientas.
async function actualizarConocimiento(): Promise<void> {
  try {
    const respuesta = await fetch("/api/conocimiento");
    if (!respuesta.ok) return;
    const conocimiento = (await respuesta.json()) as Conocimiento;
    conocimientoActual = conocimiento;
    orbe.conocer(conocimiento);
    saber.textContent =
      `Azul recuerda ${cantidad(conocimiento.recuerdos, "cosa", "cosas")} de ti · ` +
      `${cantidad(conocimiento.habilidades.length, "habilidad", "habilidades")} · ` +
      `${cantidad(conocimiento.herramientas.length, "herramienta", "herramientas")}`;
  } catch {
    // Sin núcleo, la red se queda como está.
  }
}

const LARGO_SUBTITULO = 200;

/** Lo último de un texto largo, empezando en una frase: así se lee como subtítulo. */
function finalDe(textoCompleto: string): string {
  const limpio = textoCompleto.trim();
  if (limpio.length <= LARGO_SUBTITULO) return limpio;
  const cola = limpio.slice(-LARGO_SUBTITULO);
  const inicioDeFrase = cola.search(/[.!?…]\s+\S/);
  return inicioDeFrase >= 0 ? cola.slice(inicioDeFrase + 1).trimStart() : `…${cola.trimStart()}`;
}

// Los subtítulos reflejan las dos últimas intervenciones del historial.
function actualizarSubtitulos(): void {
  const burbujas = conversacion.querySelectorAll<HTMLDivElement>(".burbuja");
  const ultima = burbujas[burbujas.length - 1];
  let deUsuario: HTMLDivElement | undefined;
  let deAzul: HTMLDivElement | undefined;
  if (ultima?.classList.contains("user")) {
    deUsuario = ultima;
  } else if (ultima) {
    deAzul = ultima;
    const anterior = burbujas[burbujas.length - 2];
    if (anterior?.classList.contains("user")) deUsuario = anterior;
  }
  subtituloUsuario.textContent = deUsuario ? finalDe(deUsuario.textContent ?? "") : "";
  subtituloAzul.textContent = deAzul ? finalDe(deAzul.textContent ?? "") : "";
  subtituloAzul.dataset.tipo = deAzul?.classList.contains("aviso") ? "aviso" : "azul";
  if (subtituloUsuario.textContent || subtituloAzul.textContent) {
    mostrarFrases(true);
    // Un aviso o una respuesta escrita también se van solos si Azul ya está en calma.
    if (estadoMostrado && enCalma(estadoMostrado)) ocultarFrasesLuego();
  }
}

const observadorDeSubtitulos = new MutationObserver(actualizarSubtitulos);

// Al abrir la app, la conversación anterior queda en el historial, no en pantalla.
function seguirSubtitulos(): void {
  observadorDeSubtitulos.observe(conversacion, { childList: true, characterData: true, subtree: true });
  if (estadoDePrueba) actualizarSubtitulos();
}

// --- Teclado e historial ---

const botonTeclado = elemento<HTMLButtonElement>("#teclado");
const historial = elemento<HTMLElement>("#historial");
const botonHistorial = elemento<HTMLButtonElement>("#abrir-historial");
const botonCerrarHistorial = elemento<HTMLButtonElement>("#cerrar-historial");

botonTeclado.addEventListener("click", () => {
  formulario.hidden = !formulario.hidden;
  botonTeclado.setAttribute("aria-expanded", String(!formulario.hidden));
  if (!formulario.hidden) texto.focus();
});

function mostrarHistorial(abierto: boolean): void {
  historial.hidden = !abierto;
  botonHistorial.setAttribute("aria-expanded", String(abierto));
  if (abierto) {
    bajarAlFinal();
    botonCerrarHistorial.focus();
  } else {
    botonHistorial.focus();
  }
}

botonHistorial.addEventListener("click", () => mostrarHistorial(historial.hasAttribute("hidden")));
botonCerrarHistorial.addEventListener("click", () => mostrarHistorial(false));
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape" && !historial.hidden) mostrarHistorial(false);
});

// --- Clave de acceso (solo desde otros dispositivos, como el celular) ---

const dialogoEntrada = elemento<HTMLDialogElement>("#entrada");
const formularioClave = elemento<HTMLFormElement>("#formulario-clave");
const campoClave = elemento<HTMLInputElement>("#clave");
const errorClave = elemento<HTMLParagraphElement>("#error-clave");

interface Sesion {
  local: boolean;
  autorizado: boolean;
  clave_configurada: boolean;
}

function pedirClave(claveConfigurada: boolean): void {
  errorClave.textContent = claveConfigurada
    ? ""
    : "Azul aún no tiene clave de acceso. Configúrala en el portátil (AZUL_ACCESS_KEY en .env).";
  if (!dialogoEntrada.open) dialogoEntrada.showModal();
  campoClave.focus();
}

formularioClave.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  try {
    const respuesta = await fetch("/api/entrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clave: campoClave.value }),
    });
    if (respuesta.status === 204) {
      campoClave.value = "";
      dialogoEntrada.close();
      void iniciar();
      return;
    }
    const detalle = (await respuesta.json().catch(() => ({}))) as { detail?: string };
    errorClave.textContent =
      respuesta.status === 401 ? "Clave incorrecta. Intenta de nuevo." : (detalle.detail ?? "No pude verificar la clave.");
  } catch {
    errorClave.textContent = "No encuentro a Azul. ¿Está encendido el portátil?";
  }
});

// La pantalla de entrada no se puede cerrar sin la clave.
dialogoEntrada.addEventListener("cancel", (evento) => evento.preventDefault());

async function iniciar(): Promise<void> {
  try {
    const respuesta = await fetch("/api/sesion");
    const sesion = (await respuesta.json()) as Sesion;
    if (!sesion.autorizado) {
      pedirClave(sesion.clave_configurada);
      return;
    }
  } catch {
    // Sin núcleo: actualizarGasto mostrará el aviso.
  }
  await cargarHistorial();
  seguirSubtitulos();
  await actualizarGasto();
  await actualizarHuella();
  if (pideConversar) {
    pideConversar = false;
    prepararConversacionRapida();
  }
}

// --- Tu voz: interrumpir a Azul hablándole, solo con tu voz (ADR 0036) ---

interface EstadoHuella {
  disponible: boolean;
  inscrita: boolean;
}

const estadoTuVoz = elemento<HTMLParagraphElement>("#estado-tu-voz");
const botonEnsenarVoz = elemento<HTMLButtonElement>("#ensenar-voz");
const botonOlvidarVoz = elemento<HTMLButtonElement>("#olvidar-voz");
const dialogoVoz = elemento<HTMLDialogElement>("#dialogo-voz");
const pasoVoz = elemento<HTMLParagraphElement>("#paso-voz");
const fraseVoz = elemento<HTMLParagraphElement>("#frase-voz");
const avisoVoz = elemento<HTMLParagraphElement>("#aviso-voz");
const botonGrabarVoz = elemento<HTMLButtonElement>("#grabar-voz");

const FRASES_PARA_TU_VOZ = [
  "Hola Azul, esta es mi voz y quiero que la reconozcas.",
  "Hoy quiero revisar las órdenes y los pendientes de la semana.",
  "Por favor, recuérdame llamar a la IPS de Cali mañana temprano.",
  "Espera, eso no es lo que te pedí, déjame explicarte otra vez.",
  "Gracias, con eso es suficiente por ahora.",
];
const SEGUNDOS_POR_FRASE = 5;
let fraseActual = 0;

async function actualizarHuella(): Promise<void> {
  try {
    const respuesta = await fetch("/api/huella");
    if (!respuesta.ok) return;
    const huella = (await respuesta.json()) as EstadoHuella;
    botonEnsenarVoz.hidden = !huella.disponible;
    botonOlvidarVoz.hidden = !huella.inscrita;
    botonEnsenarVoz.textContent = huella.inscrita ? "Volver a enseñarle mi voz" : "Enseñarle mi voz";
    estadoTuVoz.textContent = !huella.disponible
      ? "Interrumpir a Azul con la voz no está disponible en este equipo."
      : huella.inscrita
        ? "Azul conoce tu voz: puedes interrumpirla hablándole mientras responde."
        : "Enséñale tu voz para poder interrumpirla hablándole mientras responde.";
    if (huella.inscrita) {
      void voz.activarInterrupcion(() => estadoMicrofono() === "respondiendo");
    } else {
      voz.desactivarInterrupcion();
    }
  } catch {
    // Sin núcleo no hay huella.
  }
}

function mostrarFraseDeVoz(): void {
  pasoVoz.textContent = `Frase ${fraseActual + 1} de ${FRASES_PARA_TU_VOZ.length}`;
  fraseVoz.textContent = FRASES_PARA_TU_VOZ[fraseActual];
  botonGrabarVoz.textContent = "Grabar";
  botonGrabarVoz.disabled = false;
}

botonEnsenarVoz.addEventListener("click", async () => {
  // Se empieza de cero: las muestras viejas no se mezclan con las nuevas.
  await fetch("/api/huella", { method: "DELETE" }).catch(() => undefined);
  fraseActual = 0;
  avisoVoz.textContent = "Lee la frase en voz alta, con tu tono normal, cuando toques Grabar.";
  mostrarFraseDeVoz();
  dialogoVoz.showModal();
});

botonOlvidarVoz.addEventListener("click", async () => {
  await fetch("/api/huella", { method: "DELETE" }).catch(() => undefined);
  await actualizarHuella();
});

botonGrabarVoz.addEventListener("click", async () => {
  botonGrabarVoz.disabled = true;
  botonGrabarVoz.textContent = "Escuchando…";
  avisoVoz.textContent = `Lee la frase ahora (${SEGUNDOS_POR_FRASE} segundos).`;
  try {
    const muestra = await voz.grabarMuestra(SEGUNDOS_POR_FRASE);
    const respuesta = await fetch("/api/huella/muestra", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: muestra,
    });
    if (!respuesta.ok) {
      const detalle = (await respuesta.json().catch(() => ({}))) as { detail?: string };
      avisoVoz.textContent = detalle.detail ?? "No pude guardar esa frase. Intenta de nuevo.";
      mostrarFraseDeVoz();
      return;
    }
    fraseActual++;
    if (fraseActual < FRASES_PARA_TU_VOZ.length) {
      avisoVoz.textContent = "Bien. Sigue con la próxima.";
      mostrarFraseDeVoz();
      return;
    }
    botonGrabarVoz.textContent = "Aprendiendo tu voz…";
    const listo = await fetch("/api/huella/listo", { method: "POST" });
    if (!listo.ok) throw new Error(`HTTP ${listo.status}`);
    dialogoVoz.close();
    await actualizarHuella();
    agregarBurbuja("aviso", "Listo: ya conozco tu voz. Puedes interrumpirme hablándome mientras respondo.");
  } catch (error) {
    const permisoNegado = error instanceof DOMException && error.name === "NotAllowedError";
    avisoVoz.textContent = permisoNegado
      ? "Necesito permiso para usar el micrófono."
      : "Algo falló al grabar. Intenta de nuevo.";
    mostrarFraseDeVoz();
  }
});

// --- Toque atrás del iPhone (ADR 0033) ---
// El atajo abre Azul con ?conversar. iOS solo deja encender el audio de una página
// tras un toque del usuario, así que basta tocar en cualquier parte de la pantalla.

let pideConversar = new URLSearchParams(location.search).has("conversar");
if (pideConversar) history.replaceState(null, "", location.pathname);

const tocarParaHablar = elemento<HTMLButtonElement>("#tocar-para-hablar");

function prepararConversacionRapida(): void {
  if (estadoMicrofono() !== "inactivo") return;
  tocarParaHablar.hidden = false;
  tocarParaHablar.focus();
}

tocarParaHablar.addEventListener("click", () => {
  tocarParaHablar.hidden = true;
  iniciarConversacion();
  void empezarAHablar();
});

void iniciar();
