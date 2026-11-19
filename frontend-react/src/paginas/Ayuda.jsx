/* Ayuda (port de frontend/ayuda.html + js/ayuda.js): los temas son
   pestañas; al entrar se ve «Crear un ticket» y /ayuda#correo abre ese tema
   (también desde el chat). Al cambiar de pestaña la dirección se actualiza. */
import { useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Cabecera from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { PANELES, TEMAS } from "../ayuda/contenido.jsx";

const TEMA_INICIAL = "crear";
const PASOS_TECLADO = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

export function temaDeDireccion(hash) {
  let tema = "";
  try {
    tema = decodeURIComponent(String(hash || "").replace(/^#/, ""));
  } catch {
    tema = "";
  }
  return TEMAS.some(([clave]) => clave === tema) ? tema : TEMA_INICIAL;
}

export default function Ayuda() {
  useTitulo("Ayuda");
  const location = useLocation();
  const navigate = useNavigate();
  const activo = temaDeDireccion(location.hash);
  const botones = useRef({});

  const mostrar = (clave, { enfocar = false } = {}) => {
    navigate({ hash: `#${clave}` }, { replace: true });
    if (enfocar && botones.current[clave]) botones.current[clave].focus();
  };

  const tecla = (evento, indice) => {
    let destino = null;
    if (evento.key in PASOS_TECLADO) destino = (indice + PASOS_TECLADO[evento.key] + TEMAS.length) % TEMAS.length;
    else if (evento.key === "Home") destino = 0;
    else if (evento.key === "End") destino = TEMAS.length - 1;
    if (destino === null) return;
    evento.preventDefault();
    mostrar(TEMAS[destino][0], { enfocar: true });
  };

  return (
    <>
      <Cabecera claseTitulo="" titulo="Ayuda" subtitulo="Resumen rápido del sistema de gestión de tickets" />
      <main className="contenido">
        <section className="ayuda-contenido">
          <nav className="ayuda-indice" aria-labelledby="ayuda-temas-titulo">
            <h2 id="ayuda-temas-titulo">Temas</h2>
            <div className="ayuda-temas" role="tablist" aria-labelledby="ayuda-temas-titulo">
              {TEMAS.map(([clave, texto], indice) => (
                <button key={clave} type="button" role="tab" className="ayuda-tema-boton" id={`pestana-${clave}`} data-tema={clave}
                  aria-controls={`tema-${clave}`} aria-selected={String(activo === clave)} tabIndex={activo === clave ? 0 : -1}
                  ref={(el) => { botones.current[clave] = el; }}
                  onClick={() => mostrar(clave)} onKeyDown={(e) => tecla(e, indice)}>{texto}</button>
              ))}
            </div>
          </nav>
          {TEMAS.map(([clave]) => (
            <section key={clave} className="ayuda-tema" id={`tema-${clave}`} role="tabpanel" aria-labelledby={`pestana-${clave}`}
              tabIndex={0} hidden={activo !== clave}>
              {PANELES[clave]}
            </section>
          ))}
        </section>
      </main>
    </>
  );
}
