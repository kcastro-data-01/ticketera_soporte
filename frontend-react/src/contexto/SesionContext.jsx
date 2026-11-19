import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { USER_KEY, TOKEN_KEY, cerrarSesion, getToken, getUser, saveSession } from "../sesion/almacen.js";
import { puede as puedeRol } from "../sesion/permisos.js";

/* Usuario y token de la sesión (de localStorage, compartidos con la
   ticketera actual y con las demás pestañas). */
const SesionContext = createContext(null);

export function SesionProvider({ children }) {
  const [estado, setEstado] = useState(() => ({ token: getToken(), user: getUser() }));
  const releer = useCallback(() => setEstado({ token: getToken(), user: getUser() }), []);

  useEffect(() => {
    const alAlmacenar = (event) => {
      if (!event || event.key === null || event.key === TOKEN_KEY || event.key === USER_KEY) releer();
    };
    window.addEventListener("storage", alAlmacenar);
    return () => window.removeEventListener("storage", alAlmacenar);
  }, [releer]);

  const iniciar = useCallback((token, user) => {
    saveSession(token, user);
    releer();
  }, [releer]);

  const salir = useCallback(() => cerrarSesion("manual"), []);
  const puede = useCallback((permiso) => puedeRol(estado.user, permiso), [estado.user]);

  return (
    <SesionContext.Provider value={{ ...estado, iniciar, salir, puede, releer }}>
      {children}
    </SesionContext.Provider>
  );
}

export function useSesion() {
  const valor = useContext(SesionContext);
  if (!valor) throw new Error("useSesion fuera de SesionProvider");
  return valor;
}
