# ADR‑0001 — Proyecto independiente del portafolio personal

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

Existía la instrucción explícita de no modificar el portafolio personal estático si el
repositorio de trabajo correspondía a él. La inspección del directorio de trabajo
`D:\Sistema IA de Clinicas` mostró que estaba **completamente vacío y sin repositorio
Git** (0 entradas, ausencia de `.git`). En el mismo disco existen `D:\Portafolio` y
`D:\Proyectos De Portafolio`, que sí son trabajo previo del usuario.

## Decisión

El sistema se desarrolla como repositorio Git independiente, inicializado en
`D:\Sistema IA de Clinicas` con rama `main`. No se lee ni se modifica nada dentro de
`D:\Portafolio`, `D:\Proyectos De Portafolio` ni ningún otro directorio ajeno.

## Consecuencias

* No existe riesgo de contaminar el portafolio: el punto de partida es un directorio
  vacío, no un proyecto existente.
* No se hereda configuración, dependencias ni estilo de ningún proyecto previo, así que
  todas las decisiones de la pila quedan documentadas desde cero en estos ADR.
* No hay remoto configurado. Publicar en GitHub es una decisión posterior del usuario;
  el pipeline de CI se escribe de forma que funcione al añadirlo.
