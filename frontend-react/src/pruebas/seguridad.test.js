/* La CSP no permite código ni estilos en línea: nada de style=, innerHTML
   ni dangerouslySetInnerHTML en la app. */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const RAIZ = path.resolve(__dirname, "..");
const archivos = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
  const ruta = path.join(dir, e.name);
  if (e.isDirectory()) return archivos(ruta);
  return /\.(jsx?|html)$/.test(e.name) && !/\.test\./.test(e.name) && !ruta.includes(`${path.sep}pruebas${path.sep}`) ? [ruta] : [];
});

describe("seguridad del código", () => {
  const fuentes = [...archivos(RAIZ), path.resolve(RAIZ, "..", "index.html")];

  it.each(["dangerouslySetInnerHTML", "innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"])("sin %s", (patron) => {
    const con = fuentes.filter((f) => fs.readFileSync(f, "utf8").includes(patron));
    expect(con).toEqual([]);
  });

  it("sin estilos en línea", () => {
    const con = fuentes.filter((f) => /\sstyle=|<style/.test(fs.readFileSync(f, "utf8")));
    expect(con).toEqual([]);
  });

  it("index.html sin scripts en línea", () => {
    const html = fs.readFileSync(path.resolve(RAIZ, "..", "index.html"), "utf8");
    const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
    expect(scripts.length).toBeGreaterThan(0);
    scripts.forEach(([, atributos, cuerpo]) => {
      expect(atributos).toMatch(/src=/);
      expect(cuerpo.trim()).toBe("");
    });
  });
});
