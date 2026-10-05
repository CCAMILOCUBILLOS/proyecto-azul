import "./style.css";

interface Salud {
  estado: string;
  version: string;
}

const estado = document.querySelector<HTMLParagraphElement>("#estado")!;

async function comprobarNucleo(): Promise<void> {
  try {
    const respuesta = await fetch("/api/salud");
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    const salud: Salud = await respuesta.json();
    estado.textContent = `Núcleo en línea · v${salud.version}`;
    estado.dataset.ok = "true";
  } catch {
    estado.textContent = "No encuentro el núcleo de Azul. ¿Está encendido?";
    estado.dataset.ok = "false";
  }
}

void comprobarNucleo();
