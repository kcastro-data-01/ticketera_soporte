/* Aplica el tema oscuro guardado antes de pintar la página (evita el
   destello claro). Se carga sin defer en el <head>: la CSP no permite
   scripts inline. */
try{if(localStorage.getItem("tema")==="oscuro")document.documentElement.setAttribute("data-tema","oscuro")}catch(e){}
