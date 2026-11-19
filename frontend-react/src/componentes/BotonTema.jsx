import { useTema } from "../contexto/TemaContext.jsx";
import { IconoLuna, IconoSol } from "./iconos.jsx";

/* Luna/sol: muestra el ícono del modo al que se cambia. */
export default function BotonTema() {
  const { tema, alternar } = useTema();
  const oscuro = tema === "oscuro";
  const etiqueta = oscuro ? "Activar modo claro" : "Activar modo oscuro";
  return (
    <button type="button" className="boton-tema" aria-label={etiqueta} aria-pressed={String(oscuro)}
      title={etiqueta} onClick={alternar}>
      {oscuro ? <IconoSol /> : <IconoLuna />}
    </button>
  );
}
