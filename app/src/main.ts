import "./style.css";

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

type Evento =
  | { tipo: "texto"; texto: string }
  | { tipo: "gasto"; nivel: "aviso" | "bloqueo"; gastado: number; limite: number }
  | { tipo: "error"; mensaje: string }
  | { tipo: "fin" };

const estado = elemento<HTMLParagraphElement>("#estado");
const conversacion = elemento<HTMLElement>("#conversacion");
const formulario = elemento<HTMLFormElement>("#formulario");
const texto = elemento<HTMLTextAreaElement>("#texto");
const botonEnviar = elemento<HTMLButtonElement>("#enviar");
const botonParar = elemento<HTMLButtonElement>("#parar");

let respuestaEnCurso: AbortController | null = null;

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

function mostrarEvento(evento: Evento, burbuja: HTMLDivElement): void {
  switch (evento.tipo) {
    case "texto":
      burbuja.textContent += evento.texto;
      bajarAlFinal();
      break;
    case "error":
      agregarBurbuja("aviso", evento.mensaje);
      break;
    case "gasto":
      agregarBurbuja(
        "aviso",
        evento.nivel === "bloqueo"
          ? `Llegaste al límite de ${dinero(evento.limite)} de este mes. Azul queda en pausa hasta el próximo mes.`
          : `Ojo: llevas ${dinero(evento.gastado)} de ${dinero(evento.limite)} este mes.`,
      );
      break;
    case "fin":
      break;
  }
}

async function enviar(mensaje: string): Promise<void> {
  agregarBurbuja("user", mensaje);
  const burbuja = agregarBurbuja("assistant");
  burbuja.classList.add("pensando");
  respuestaEnCurso = new AbortController();
  modoRespondiendo(true);

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
        if (!linea.trim()) continue;
        burbuja.classList.remove("pensando");
        mostrarEvento(JSON.parse(linea) as Evento, burbuja);
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      burbuja.classList.add("interrumpida");
    } else {
      agregarBurbuja("aviso", "Se perdió la conexión con Azul. Intenta de nuevo.");
    }
  } finally {
    burbuja.classList.remove("pensando");
    if (!burbuja.textContent) burbuja.remove();
    respuestaEnCurso = null;
    modoRespondiendo(false);
    void actualizarGasto();
  }
}

function modoRespondiendo(activo: boolean): void {
  botonEnviar.hidden = activo;
  botonParar.hidden = !activo;
  texto.disabled = activo;
  if (!activo) texto.focus();
}

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

botonParar.addEventListener("click", () => respuestaEnCurso?.abort());

void cargarHistorial();
void actualizarGasto();
texto.focus();
