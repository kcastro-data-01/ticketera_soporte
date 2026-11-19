import { createElement, useLayoutEffect, useRef } from "react";

/* Un elemento con propiedades de estilo puestas por CSSOM (element.style),
   como hace la app actual: la CSP prohíbe los estilos en línea del HTML,
   pero no cambiar el estilo desde el script. */
export default function ConEstilo({ as = "span", estilos = {}, ...props }) {
  const ref = useRef(null);
  const clave = JSON.stringify(estilos);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    Object.entries(estilos).forEach(([propiedad, valor]) => { el.style[propiedad] = valor; });
  }, [clave]); // eslint-disable-line react-hooks/exhaustive-deps
  return createElement(as, { ...props, ref });
}
