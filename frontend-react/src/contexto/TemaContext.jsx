import { createContext, useCallback, useContext, useEffect, useState } from "react";

/* <html data-tema="oscuro"> activa las variables oscuras de estilos.css. La
   preferencia se guarda en localStorage («tema», la misma clave que la
   ticketera actual); public/tema.js la aplica antes de pintar. */
const TEMA_KEY = "tema";
const TemaContext = createContext({ tema: "claro", alternar: () => {} });

function temaGuardado() {
  try {
    return localStorage.getItem(TEMA_KEY) === "oscuro" ? "oscuro" : "claro";
  } catch {
    return "claro";
  }
}

export function TemaProvider({ children }) {
  const [tema, setTema] = useState(temaGuardado);

  useEffect(() => {
    if (tema === "oscuro") document.documentElement.setAttribute("data-tema", "oscuro");
    else document.documentElement.removeAttribute("data-tema");
  }, [tema]);

  const alternar = useCallback(() => {
    setTema((actual) => {
      const nuevo = actual === "oscuro" ? "claro" : "oscuro";
      try {
        localStorage.setItem(TEMA_KEY, nuevo);
      } catch {
        /* Solo para esta visita. */
      }
      document.dispatchEvent(new CustomEvent("tema-cambiado", { detail: { tema: nuevo } }));
      return nuevo;
    });
  }, []);

  return <TemaContext.Provider value={{ tema, alternar }}>{children}</TemaContext.Provider>;
}

export const useTema = () => useContext(TemaContext);
