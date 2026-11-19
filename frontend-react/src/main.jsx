import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
/* Los mismos estilos de la ticketera actual (una sola copia en frontend/css). */
import "../../frontend/css/estilos.css";
import App from "./App.jsx";

createRoot(document.getElementById("raiz")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
