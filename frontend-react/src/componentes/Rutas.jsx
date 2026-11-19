import { useEffect } from "react";
import { Navigate } from "react-router-dom";
import { useSesion } from "../contexto/SesionContext.jsx";
import { cerrarSesion, estadoToken } from "../sesion/almacen.js";
import Layout from "./Layout.jsx";

/* Exige sesión (como requireAuth): sin token va al login; con el token
   vencido cierra la sesión (el login intenta volver a entrar en silencio). */
export function RequiereSesion({ children, permiso = null, sinLayout = false }) {
  const { token, puede } = useSesion();
  const estado = token ? estadoToken(token) : null;

  useEffect(() => {
    if (token && estado) cerrarSesion(estado);
  }, [token, estado]);

  if (!token) return <Navigate to="/login" replace />;
  if (estado) return null;
  /* Sin el permiso de la pantalla: «Acceso restringido» (requirePermiso). */
  if (permiso && !puede(permiso)) return <Navigate to="/sin-permiso" replace />;
  return sinLayout ? children : <Layout>{children}</Layout>;
}
