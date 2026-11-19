/* Ventana de confirmación propia (port de confirmarAccion, auth.js):
   mismas clases, foco en «Cancelar» (o en el texto), Escape y clic afuera
   cancelan, Tab queda dentro. Con ``campo`` agrega un texto opcional y
   resuelve { valor }; si no, true / false. */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const ConfirmarContext = createContext(() => Promise.resolve(false));

function Dialogo({ pedido, onFin }) {
  const { titulo, mensaje, aceptar = "Aceptar", cancelar = "Cancelar", peligro = false, campo = null } = pedido;
  const [valor, setValor] = useState("");
  const no = useRef(null);
  const si = useRef(null);
  const texto = useRef(null);

  useEffect(() => {
    const anterior = document.activeElement;
    (texto.current || no.current).focus();
    const teclas = (event) => {
      const enfocables = [texto.current, no.current, si.current].filter(Boolean);
      if (event.key === "Escape") {
        event.preventDefault();
        onFin(false);
      } else if (event.key === "Tab") {
        event.preventDefault();
        const i = enfocables.indexOf(document.activeElement);
        const paso = event.shiftKey ? -1 : 1;
        enfocables[(i + paso + enfocables.length) % enfocables.length].focus();
      }
    };
    document.addEventListener("keydown", teclas, true);
    return () => {
      document.removeEventListener("keydown", teclas, true);
      if (anterior && typeof anterior.focus === "function" && document.contains(anterior)) anterior.focus();
    };
  }, [onFin]);

  return createPortal(
    <div className="dialogo-fondo" onClick={(event) => { if (event.target === event.currentTarget) onFin(false); }}>
      <div className="dialogo" role="alertdialog" aria-modal="true" aria-labelledby="dialogo-titulo" aria-describedby="dialogo-mensaje">
        <h2 className="dialogo-titulo" id="dialogo-titulo">{titulo || "Confirmar"}</h2>
        <p className="dialogo-mensaje" id="dialogo-mensaje">{mensaje || ""}</p>
        {campo && (
          <label className="campo dialogo-campo">
            <span>{campo.etiqueta || "Detalle (opcional)"}</span>
            <textarea id="dialogo-campo" rows={3} maxLength={2000} ref={texto}
              value={valor} onChange={(e) => setValor(e.target.value)} />
          </label>
        )}
        <div className="dialogo-acciones">
          <button type="button" className="secundario" ref={no} onClick={() => onFin(false)}>{cancelar}</button>
          <button type="button" className={peligro ? "boton-peligro" : undefined} ref={si}
            onClick={() => onFin(campo ? { valor: valor.trim() } : true)}>{aceptar}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmarProvider({ children }) {
  const [pedido, setPedido] = useState(null);
  const resolver = useRef(null);
  const confirmar = useCallback((opciones = {}) => new Promise((resolve) => {
    resolver.current = resolve;
    setPedido(opciones);
  }), []);
  const fin = useCallback((resultado) => {
    setPedido(null);
    if (resolver.current) resolver.current(resultado);
    resolver.current = null;
  }, []);
  return (
    <ConfirmarContext.Provider value={confirmar}>
      {children}
      {pedido && <Dialogo pedido={pedido} onFin={fin} />}
    </ConfirmarContext.Provider>
  );
}

export const useConfirmar = () => useContext(ConfirmarContext);
