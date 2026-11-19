import { forwardRef } from "react";
import { PASOS_ESTADO } from "../sesion/permisos.js";

/* Avance del estado: hechos, el actual y los que faltan. Cada destino
   permitido es un botón (teclado y lector de pantalla). */
const PasosEstado = forwardRef(function PasosEstado({ estado, destinos, onElegir }, ref) {
  const actual = PASOS_ESTADO.indexOf(estado);
  return (
    <ol id="pasos-estado" className="pasos-estado" aria-label="Avance del ticket" tabIndex={-1} ref={ref}>
      {PASOS_ESTADO.map((nombre, indice) => {
        const clase = actual < 0 ? undefined : indice < actual ? "hecho" : indice === actual ? "actual" : undefined;
        const contenido = (
          <>
            <span className="paso-marca" aria-hidden="true" />
            <span className="paso-nombre">{nombre}</span>
          </>
        );
        return (
          <li key={nombre} data-paso={nombre} className={clase} aria-current={indice === actual ? "step" : undefined}>
            {destinos.includes(nombre) ? (
              <button type="button" className="paso-boton" data-destino={nombre} title={`Pasar a «${nombre}»`}
                aria-label={`Pasar el ticket a «${nombre}»`} onClick={() => onElegir(nombre)}>{contenido}</button>
            ) : contenido}
          </li>
        );
      })}
    </ol>
  );
});

export default PasosEstado;
