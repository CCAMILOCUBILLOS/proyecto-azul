// Corre en el hilo de audio del navegador: entrega las muestras del micrófono
// a la app, que las convierte a PCM de 16 kHz y las envía a Azul.
class Captura extends AudioWorkletProcessor {
  process(inputs) {
    const canal = inputs[0] && inputs[0][0];
    if (canal) this.port.postMessage(canal.slice(0));
    return true;
  }
}

registerProcessor("captura", Captura);
