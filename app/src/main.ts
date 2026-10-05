import "./style.css";
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
const conversacion = elemento<HTMLElement>("#conversacion");
const formulario = elemento<HTMLFormElement>("#formulario");
const texto = elemento<HTMLTextAreaElement>("#texto");
const botonEnviar = elemento<HTMLButtonElement>("#enviar");
const botonParar = elemento<HTMLButtonElement>("#parar");
const botonMicrofono = elemento<HTMLButtonElement>("#microfono");

let respuestaEnCurso: AbortController | null = null;
let respondiendoPorVoz = false;
let burbujaEscuchada: HTMLDivElement | null = null;
let burbujaVoz: HTMLDivElement | null = null;

const voz = new Voz(alEventoDeVoz, () => actualizarBotones());

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
    estado.textContent = `Gasto del mes: ${dinero(gasto.gastado_mes)} de ${dinero(gasto.limite)}`;
    estado.dataset.nivel = gasto.gastado_mes >= gasto.aviso ? "aviso" : "ok";
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

function actualizarBotones(): void {
  const ocupado = respuestaEnCurso !== null || respondiendoPorVoz || voz.sonando;
  botonEnviar.hidden = ocupado;
  botonParar.hidden = !ocupado;
  texto.disabled = respuestaEnCurso !== null;
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
    texto.focus();
    void actualizarGasto();
  }
}

// --- Voz ---

function alEventoDeVoz(evento: EventoVoz): void {
  switch (evento.tipo) {
    case "turno":
      respondiendoPorVoz = true;
      burbujaEscuchada = agregarBurbuja("user");
      burbujaEscuchada.classList.add("escuchando");
      burbujaVoz = null;
      break;
    case "escuchado":
      if (burbujaEscuchada) {
        burbujaEscuchada.textContent = evento.texto;
        if (evento.final) burbujaEscuchada.classList.remove("escuchando");
      }
      break;
    case "nada_escuchado":
      burbujaEscuchada?.remove();
      agregarBurbuja("aviso", "No te escuché. Mantén presionado el micrófono mientras hablas.");
      break;
    case "texto":
    case "buscando":
      burbujaVoz ??= agregarBurbuja("assistant");
      mostrarEventoDeChat(evento, burbujaVoz);
      break;
    case "gasto":
    case "error":
      if (burbujaEscuchada && !burbujaEscuchada.textContent) burbujaEscuchada.remove();
      mostrarEventoDeChat(evento, burbujaVoz ?? agregarBurbuja("aviso"));
      break;
    case "parado":
      burbujaVoz?.classList.add("interrumpida");
      burbujaVoz?.classList.remove("buscando");
      respondiendoPorVoz = false;
      break;
    case "fin":
      burbujaEscuchada?.classList.remove("escuchando");
      burbujaVoz?.classList.remove("buscando");
      respondiendoPorVoz = false;
      void actualizarGasto();
      break;
  }
  actualizarBotones();
}

async function empezarAHablar(): Promise<void> {
  botonMicrofono.classList.add("activo");
  try {
    await voz.empezar();
    // Si el usuario soltó el botón mientras se preparaba el micrófono, se termina ya.
    if (!botonMicrofono.classList.contains("activo")) voz.terminar();
  } catch (error) {
    botonMicrofono.classList.remove("activo");
    const permisoNegado = error instanceof DOMException && error.name === "NotAllowedError";
    agregarBurbuja(
      "aviso",
      permisoNegado
        ? "Necesito permiso para usar el micrófono. Actívalo en la configuración del navegador."
        : "No pude activar el micrófono ni conectarme con Azul.",
    );
  }
}

function dejarDeHablar(): void {
  if (!botonMicrofono.classList.contains("activo")) return;
  botonMicrofono.classList.remove("activo");
  voz.terminar();
}

botonMicrofono.addEventListener("pointerdown", (evento) => {
  evento.preventDefault();
  botonMicrofono.setPointerCapture(evento.pointerId);
  void empezarAHablar();
});
botonMicrofono.addEventListener("pointerup", dejarDeHablar);
botonMicrofono.addEventListener("pointercancel", dejarDeHablar);
// Accesible con teclado: mantener la barra espaciadora o Enter sobre el botón.
botonMicrofono.addEventListener("keydown", (evento) => {
  if ((evento.key === " " || evento.key === "Enter") && !evento.repeat) {
    evento.preventDefault();
    void empezarAHablar();
  }
});
botonMicrofono.addEventListener("keyup", (evento) => {
  if (evento.key === " " || evento.key === "Enter") dejarDeHablar();
});
botonMicrofono.addEventListener("contextmenu", (evento) => evento.preventDefault());

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

botonParar.addEventListener("click", () => {
  respuestaEnCurso?.abort();
  voz.parar();
  respondiendoPorVoz = false;
  actualizarBotones();
});

void cargarHistorial();
void actualizarGasto();
texto.focus();
