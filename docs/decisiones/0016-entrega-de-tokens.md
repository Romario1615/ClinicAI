# ADR‑0016 — El token de refresco viaja en el cuerpo, no en una cookie

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

La API la consume una PWA de Angular. Hay dos formas habituales de entregar el token de
refresco, y cada una traslada el riesgo a un sitio distinto:

**Cookie `HttpOnly`.** JavaScript no puede leerla, así que un XSS no se lleva el refresco
directamente. A cambio, el navegador la adjunta sola a cada petición al origen, lo que
abre CSRF: un sitio de terceros puede provocar una rotación. Con `SameSite=Strict` el
riesgo baja mucho, pero la rotación provocada desde fuera seguiría invalidando la sesión
del usuario legítimo — una denegación de servicio barata —, y `SameSite` no está
disponible de forma uniforme en todos los clientes que una PWA puede tener (aplicación
envuelta, WebView, cliente móvil nativo futuro).

**Cuerpo de la respuesta.** El cliente lo guarda y lo envía explícitamente. No hay CSRF
porque nada se adjunta solo. A cambio, un XSS que se ejecute en la aplicación puede
leerlo si el cliente lo guarda en un sitio accesible.

Conviene ser explícito sobre lo que ninguna de las dos resuelve: **con XSS ejecutándose
dentro de la aplicación, la cookie `HttpOnly` tampoco protege la sesión**. El atacante no
necesita leer el token; le basta con hacer peticiones desde la propia página, que el
navegador autentica por él. La cookie protege contra la *exfiltración* del token, no
contra su *uso*.

## Decisión

El par de tokens se devuelve en el cuerpo de la respuesta de
`POST /api/v1/autenticacion/sesion` y de `.../refresco`.

La defensa principal contra un refresco robado **no es ocultarlo, sino detectar que se
duplicó**:

* Cada refresco es de un solo uso y se almacena con hash (`jti_refresco_hash`).
* El JWT de acceso solo se acepta mientras exista un refresco actual no usado y no
  revocado para su familia. Cerrar sesión, reasignar la clínica o desactivar la cuenta
  invalida inmediatamente también los JWT de acceso ya emitidos.
* Si un refresco ya usado vuelve a presentarse, existen dos copias en circulación. No se
  puede saber cuál es la legítima, así que se revoca **la familia completa** de sesiones
  y se registra `token.reutilizado`, que está en la lista de acciones que generan alerta.
* El token de acceso dura 15 minutos, de modo que la ventana de uso sin rotar es corta.

Se acompaña de:

* `Content-Security-Policy: default-src 'none'` en las respuestas de la API y una CSP
  estricta en el frontend, para reducir la probabilidad del XSS que hace falta primero.
* CORS con lista explícita de orígenes; nunca comodín con credenciales.
* `Cache-Control: no-store` en todas las respuestas.

**Indicación para el frontend:** el refresco se guarda en memoria del proceso de la
aplicación, no en `localStorage` ni en `sessionStorage`. El coste es que recargar la
pestaña obliga a volver a iniciar sesión; se acepta a cambio de que un XSS no encuentre
el token en un almacén persistente.

## Consecuencias

* No hay superficie de CSRF en los endpoints de autenticación, y no hace falta un
  mecanismo de doble envío de token.
* El robo de refresco es **detectable** y su explotación revoca la sesión del atacante y
  la del usuario. No es evitable: es detectable y acotado.
* **Riesgo residual declarado:** un XSS en el frontend compromete la sesión activa, con
  cookie o sin ella. La mitigación real está en el frontend (CSP, evitar
  `innerHTML` con datos del servidor, revisión de dependencias) y se verifica en la
  Fase 10; no en el mecanismo de transporte del token.
* Recargar la página cierra la sesión mientras el refresco viva solo en memoria. Si la
  clínica pide persistencia entre recargas, la decisión se revisa y se documenta el
  cambio de riesgo — no se añade `localStorage` en silencio.
