/* Formato de las respuestas del asistente (port de pintarTexto/pintarLinea
   de frontend/js/asistente.js): párrafos, listas («- » o «1. »), títulos,
   «**negrita**», «#N» y los enlaces «[texto](detalle.html?id=N)» que arma el
   servidor. Todo se arma con elementos de React a partir de texto: nada de
   lo que responde el servidor se interpreta como HTML. Los enlaces llevan a
   /tickets/N de React; se aceptan los del servidor y los viejos guardados
   en conversaciones (detalle.html?id=N), y también /tickets/N. */
import { Link } from "react-router-dom";
import { rutaTicket } from "../rutas.js";

const DESTINO = String.raw`(?:detalle\.html\?id=(\d+)(?:&pestana=([a-z]+))?|/tickets/(\d+)(?:\?pestana=([a-z]+))?)`;
const ENLACE = new RegExp(String.raw`(\[[^\]\n]+\]\(${DESTINO.replace(/\((?!\?)/g, "(?:")}\))`);
const ENLACE_EXACTO = new RegExp(String.raw`^\[([^\]\n]+)\]\(${DESTINO}\)$`);
const ENLACE_GLOBAL = new RegExp(String.raw`\[([^\]\n]+)\]\(${DESTINO.replace(/\((?!\?)/g, "(?:")}\)`, "g");

/* «detalle.html?id=5&pestana=ia» o «/tickets/5?pestana=ia» → «/tickets/5?pestana=ia». */
export function destinoDeEnlace(texto) {
  const m = ENLACE_EXACTO.exec(texto);
  if (!m) return null;
  const id = m[2] || m[4];
  const pestana = m[3] || m[5];
  return { texto: m[1], a: `${rutaTicket(id)}${pestana ? `?pestana=${pestana}` : ""}` };
}

function enlace(a, texto, clave) {
  return <Link key={clave} className="chat-enlace" to={a}>{texto}</Link>;
}

/* «**negrita**» y «#N» como enlace al ticket. */
function formato(texto, clave) {
  return String(texto).split(/(\*\*[^*\n]+\*\*)/).flatMap((trozo, i) => {
    const negrita = /^\*\*([^*\n]+)\*\*$/.exec(trozo);
    const partes = (negrita ? negrita[1] : trozo).split(/(#\d+)/).filter(Boolean).map((parte, j) => {
      const numero = /^#(\d+)$/.exec(parte);
      return numero ? enlace(rutaTicket(numero[1]), parte, `${clave}-${i}-${j}`) : parte;
    });
    if (negrita) return [<strong key={`${clave}-${i}`}>{partes}</strong>];
    return partes;
  });
}

export function linea(texto, clave = "l") {
  return String(texto).split(ENLACE).filter(Boolean).flatMap((pedazo, i) => {
    const destino = destinoDeEnlace(pedazo);
    if (destino) return [enlace(destino.a, destino.texto, `${clave}-e${i}`)];
    return formato(pedazo, `${clave}-${i}`);
  });
}

export function tituloDeLinea(l) {
  const markdown = /^#{1,3}\s+(.+)$/.exec(l);
  if (markdown) return markdown[1].replace(/\*\*/g, "");
  const limpia = l.replace(/\*\*/g, "");
  if (/^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñü ]{0,40}:$/.test(limpia) && limpia.split(" ").length <= 4) return limpia;
  return null;
}

/* La respuesta completa en bloques. */
export function Texto({ texto }) {
  const bloques = [];
  let lista = null;
  let parrafo = null;
  String(texto).split("\n").forEach((cruda, n) => {
    const l = cruda.trim();
    const vineta = /^[-*•]\s+(.*)$/.exec(l);
    const numerada = /^\d+[.)]\s+(.*)$/.exec(l);
    if (vineta || numerada) {
      const tipo = vineta ? "ul" : "ol";
      if (!lista || lista.tipo !== tipo) {
        lista = { tipo, items: [], clave: `b${n}` };
        bloques.push(lista);
      }
      lista.items.push(linea((vineta || numerada)[1], `i${n}`));
      parrafo = null;
      return;
    }
    lista = null;
    if (!l) {
      parrafo = null;
      return;
    }
    const titulo = tituloDeLinea(l);
    if (titulo) {
      bloques.push({ tipo: "titulo", texto: titulo, clave: `b${n}` });
      parrafo = null;
      return;
    }
    if (parrafo) parrafo.lineas.push(linea(l, `p${n}`));
    else {
      parrafo = { tipo: "p", lineas: [linea(l, `p${n}`)], clave: `b${n}` };
      bloques.push(parrafo);
    }
  });
  return bloques.map((b) => {
    if (b.tipo === "titulo") return <strong key={b.clave} className="chat-titulo-respuesta">{b.texto}</strong>;
    if (b.tipo === "p") {
      return (
        <p key={b.clave} className="chat-parrafo">
          {b.lineas.flatMap((l, i) => (i ? [<br key={`br${i}`} />, ...l] : l))}
        </p>
      );
    }
    const Lista = b.tipo;
    return <Lista key={b.clave} className="chat-lista-respuesta">{b.items.map((item, i) => <li key={i}>{item}</li>)}</Lista>;
  });
}

/* La respuesta sin el formato, para copiar. */
export function textoParaCopiar(contenido) {
  return String(contenido).replace(ENLACE_GLOBAL, "$1").replace(/\*\*/g, "");
}
