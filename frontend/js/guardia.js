/* Guarda de la página: se carga sin defer, antes que los scripts diferidos,
   para que su listener de DOMContentLoaded corra primero.
   - Con data-permiso="x": sin ese permiso se redirige y se corta la
     inicialización de la página (stopImmediatePropagation).
   - Sin data-permiso: exige sesión (requireAuth).
   Va en un archivo aparte porque la CSP no permite scripts inline. */
(function () {
  var script = document.currentScript;
  var permiso = script && script.dataset ? script.dataset.permiso : "";
  document.addEventListener("DOMContentLoaded", function (event) {
    if (permiso) {
      if (!requirePermiso(permiso)) event.stopImmediatePropagation();
    } else {
      requireAuth();
    }
  });
})();
