# Plan: facturación electrónica con el SRI (Ecuador)

> **Estado:** plan, sin código · **Fecha:** 2026‑10‑09
>
> Nada de esto está construido. No hay credenciales del SRI y no se inventan
> (CLAUDE.md, regla 3): todo se desarrolla contra un adaptador sandbox y el
> ambiente de **pruebas** del SRI, nunca contra producción desde desarrollo.

---

## 1. Qué se quiere

Que cada pago confirmado en ClinicAI pueda emitir su **factura electrónica**
autorizada por el SRI, con su RIDE (representación impresa) disponible para el
paciente, y que las anulaciones se hagan con **nota de crédito**.

Fuera de alcance de la primera fase: retenciones, guías de remisión,
liquidaciones de compra y la contabilidad de la clínica.

## 2. Cómo funciona el SRI (esquema off‑line)

Fuente: *Ficha técnica de comprobantes electrónicos, esquema off‑line*, versión
vigente **2.34** (julio de 2026), en [sri.gob.ec](https://www.sri.gob.ec/facturacion-electronica).
Toda cifra y código de este documento se **verifica contra esa ficha** antes de
implementarlo.

1. El emisor genera el XML del comprobante según el XSD del SRI.
2. Lo firma con **XAdES‑BES** usando su certificado de firma electrónica
   (archivo `.p12` emitido por una entidad acreditada).
3. Calcula la **clave de acceso** de 49 dígitos (fecha, tipo de comprobante,
   RUC, ambiente, serie, secuencial, código numérico, tipo de emisión y dígito
   verificador módulo 11).
4. Envía el XML firmado al servicio web de **recepción** (SOAP). El SRI
   responde `RECIBIDA` o `DEVUELTA` con mensajes de error.
5. Consulta el servicio de **autorización** con la clave de acceso hasta obtener
   `AUTORIZADO` o `NO AUTORIZADO`.
6. Entrega el comprobante autorizado al comprador.

Ambientes:

| Ambiente | Código | Servicios |
|---|---|---|
| Pruebas | 1 | `https://celcer.sri.gob.ec/comprobantes-electronicos-ws/...` |
| Producción | 2 | `https://cel.sri.gob.ec/comprobantes-electronicos-ws/...` |

## 3. Impuestos: una decisión que no toma el sistema

Los servicios de salud humana gravan **IVA 0 %** (Ley de Régimen Tributario
Interno, art. 56); la tarifa general en 2026 es **15 %**. El SRI controla que
los tratamientos **puramente estéticos** (sin fin terapéutico o
reconstructivo) se facturen con la tarifa general.

Por eso la tarifa de IVA **se configura por servicio** en el catálogo y la
decide la clínica con su contador. ClinicAI no clasifica un tratamiento como
terapéutico o estético (sería una decisión clínica y tributaria). Por omisión:
servicios odontológicos 0 %; «Estética facial» queda **sin tarifa** hasta que la
clínica la elija, y no se puede facturar sin ella.

## 4. Diseño propuesto

### Módulo `backend/app/modulos/facturacion/`

Mismas capas que el resto (`rutas → servicios → repositorio`):

* **Modelo `comprobante_electronico`**: tipo (`01` factura, `04` nota de
  crédito), clínica, establecimiento y punto de emisión, secuencial, clave de
  acceso (única), pago o cargo de origen, comprador, totales, estado,
  XML firmado (cifrado en reposo), número y fecha de autorización, mensajes
  del SRI, intentos.
* **Estados**: `BORRADOR → FIRMADO → ENVIADO → RECIBIDO | DEVUELTO →
  AUTORIZADO | NO_AUTORIZADO`, más `ANULADO_CON_NOTA`. Un comprobante
  autorizado no se edita ni se borra: se anula con nota de crédito.
* **Secuencial** por clínica + establecimiento + punto de emisión con
  restricción única en la base y bloqueo de fila: dos facturas no pueden tomar
  el mismo número, igual que la agenda no admite dos citas solapadas.
* **Idempotencia**: un pago confirmado produce como mucho una factura; la
  emisión lleva clave de idempotencia.

### Piezas sin red (fase 1, todas con pruebas unitarias)

* Generador de **clave de acceso** + dígito verificador módulo 11.
* Constructor del **XML** de factura y nota de crédito, validado contra los
  **XSD oficiales** dentro de las pruebas.
* **Firma XAdES‑BES** con el `.p12` y verificación de la firma en las pruebas
  (con un certificado de pruebas generado localmente, nunca uno real en el
  repositorio).

### Cliente del SRI

* `AdaptadorSri` con dos implementaciones, como WhatsApp: **sandbox** (responde
  RECIBIDA/AUTORIZADO o errores programados) y **SOAP** contra el ambiente que
  diga la configuración de la clínica.
* El envío y la consulta de autorización van por el **worker** con reintentos y
  retroceso: un SRI caído no pierde la factura ni bloquea el cobro (mismo
  patrón que el outbox).

### Configuración por clínica (Configuración › Integraciones)

Integración nueva `sri`, cifrada como las demás: RUC, razón social, nombre
comercial, dirección de la matriz, establecimiento y punto de emisión,
obligado a llevar contabilidad, contribuyente especial, régimen, ambiente
(`pruebas`/`produccion`), certificado `.p12` y su contraseña. Pasar a
producción exige permiso de administración y queda auditado.

### Entrega al paciente y datos clínicos

La factura **no es una notificación**, pero su detalle describe el servicio, y
el nombre de un servicio puede revelar la especialidad (CLAUDE.md, regla 10).
Propuesta, a decidir con el usuario y revisión legal:

* descripción por omisión genérica («Servicios odontológicos») con opción de
  detalle por servicio;
* el RIDE y el XML se entregan por **enlace privado con caducidad** (como los
  documentos privados), no como adjunto de WhatsApp; por correo, solo si el
  paciente lo pide.

## 5. Fases

| Fase | Entrega | Necesita del usuario |
|---|---|---|
| 0 | Decisiones de §3 y §4 (IVA por servicio, descripción, entrega) y ADR | Contador / revisión legal |
| 1 | Clave de acceso, XML, validación XSD y firma, todo sin red | — |
| 2 | Cliente SOAP + worker contra el ambiente de **pruebas** del SRI | Certificado de pruebas y RUC de la clínica |
| 3 | Emisión desde Pagos, RIDE en PDF, entrega privada, bandeja de comprobantes con estados y reintentos | — |
| 4 | Notas de crédito (anulación) y conciliación con pagos | — |
| 5 | Producción: checklist, cambio de ambiente auditado, monitoreo | Firma electrónica real, autorización de emisión electrónica en SRI en línea |

Cada fase se cierra con las reglas de CLAUDE.md §10: pruebas en verde,
migraciones reversibles, sin secretos, documentación y matriz de permisos.

## 6. Credenciales y datos que faltan (no se inventan)

* RUC y razón social de la clínica, dirección de la matriz.
* Establecimiento y punto de emisión asignados.
* Certificado de firma electrónica `.p12` y su contraseña (uno de pruebas para
  la fase 2 y el real para producción).
* Alta como emisor electrónico en el portal del SRI.
* Tarifa de IVA de cada servicio, validada por el contador.

## 7. Riesgos

* **Clasificación del IVA** de tratamientos estéticos: error tributario si se
  automatiza. Mitigación: lo decide la clínica por servicio.
* **Caída del SRI**: el cobro no puede depender de la autorización inmediata.
  Mitigación: emisión asíncrona con reintentos y estado visible.
* **Secuenciales**: huecos o duplicados. Mitigación: restricción única y
  bloqueo en base de datos, pruebas de concurrencia como las de la agenda.
* **Cambios de la ficha técnica** (2.34 en julio de 2026): versión del XSD
  fijada en la configuración y pruebas que validan contra el XSD vigente.
