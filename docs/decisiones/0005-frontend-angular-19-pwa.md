# ADR‑0005 — Angular 19 PWA con versión fijada

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

La especificación exige Angular como PWA, TypeScript en modo estricto, componentes
reutilizables, guards de autenticación y autorización, diseño responsive y accesibilidad
WCAG 2.2 AA. El entorno tiene Angular CLI **19.2.26** instalado de forma global y Node
22.23.1.

## Decisión

* Se crea el proyecto con `npx @angular/cli@19 new`, de modo que la versión del proyecto
  coincida con el CLI global ya instalado, y se **fija** en `package.json` sin rangos
  abiertos para los paquetes de Angular.
* Componentes **standalone** (sin `NgModule`) y estado con **signals**: es el modelo
  recomendado desde Angular 17 y reduce el código repetido de los módulos.
* `@angular/pwa` para el service worker y el manifiesto.
* `tsconfig.json` con `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`,
  `noFallthroughCasesInSwitch` y `strictTemplates` de Angular.
* La instalación en CI se hace con `npm ci` contra `package-lock.json` versionado.

## Consecuencias

* Se evita la deriva de versiones y los fallos de esquemas por desalineación entre el
  CLI global y el proyecto.
* Angular 19 no está en la última versión mayor disponible. Se acepta a cambio de
  estabilidad; la actualización se registrará como tarea de mantenimiento en
  [`../backlog.md`](../backlog.md) y no afecta a ningún requisito funcional.
* `noUncheckedIndexedAccess` obliga a comprobar los accesos por índice, lo que genera
  algo más de código pero elimina una clase de errores en la manipulación de horarios y
  listas de turnos.
