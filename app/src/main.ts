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
    texto.focus();
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
    case "nada_escuchado":
      respondiendoPorVoz = false;
      burbujaEscuchada?.remove();
      if (enConversacion && turnosEnConversacion > 0) {
        terminarConversacion("Terminé la conversación. Toca 🎤 cuando quieras seguir.");
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
  await actualizarGasto();
  texto.focus();
}

void iniciar();
