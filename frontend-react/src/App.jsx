import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AvisosProvider } from "./avisos/Avisos.jsx";
import { ConfirmarProvider } from "./componentes/Confirmar.jsx";
import { SesionProvider } from "./contexto/SesionContext.jsx";
import { TemaProvider } from "./contexto/TemaContext.jsx";
import { RequiereSesion } from "./componentes/Rutas.jsx";
import Crear from "./paginas/Crear.jsx";
import Detalle from "./paginas/Detalle.jsx";
import Heredada from "./paginas/Heredada.jsx";
import Login from "./paginas/Login.jsx";
import { NoEncontrada, SinPermiso } from "./paginas/PaginaError.jsx";
import Tickets from "./paginas/Tickets.jsx";
import { BASENAME, RUTAS } from "./rutas.js";

/* Pantallas todavía no migradas: abren la página actual (con el mismo
   permiso que pide hoy cada una). */
const HEREDADAS = [
  ["metricas", "metricas"],
  ["departamentos", "departamentos"],
  ["historial", "historial_global"],
  ["usuarios", "usuarios"],
  ["cuenta", null],
  ["ayuda", null],
];

/* Comportamiento de React Router 7 desde ya (sin avisos). */
export const FUTURO = { v7_startTransition: true, v7_relativeSplatPath: true };

export function Rutas() {
  return (
    <Routes>
      <Route path={RUTAS.login} element={<Login />} />
      <Route path={RUTAS.inicio} element={<RequiereSesion><Tickets /></RequiereSesion>} />
      <Route path={RUTAS.ticket} element={<RequiereSesion><Detalle /></RequiereSesion>} />
      <Route path={RUTAS.crear} element={<RequiereSesion><Crear /></RequiereSesion>} />
      {HEREDADAS.map(([pagina, permiso]) => (
        <Route key={pagina} path={RUTAS[pagina]}
          element={<RequiereSesion sinLayout permiso={permiso}><Heredada pagina={pagina} /></RequiereSesion>} />
      ))}
      <Route path={RUTAS.sinPermiso} element={<SinPermiso />} />
      <Route path="*" element={<NoEncontrada />} />
    </Routes>
  );
}

export function Proveedores({ children }) {
  return (
    <TemaProvider>
      <SesionProvider>
        <AvisosProvider>
          <ConfirmarProvider>{children}</ConfirmarProvider>
        </AvisosProvider>
      </SesionProvider>
    </TemaProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={BASENAME} future={FUTURO}>
      <Proveedores><Rutas /></Proveedores>
    </BrowserRouter>
  );
}
