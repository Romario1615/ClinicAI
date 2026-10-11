# ADR-0029 — PDF fiel e identidad obligatoria en entregas privadas

Fecha: 2026-10-10. Estado: aceptado e implementado en `main` local.

## Contexto

Un enlace preexistente podía aceptar una fecha cualquiera cuando el paciente
no tenía nacimiento ni documento: comparaba dos cadenas vacías. El PDF usaba
cp1252 y sustituía caracteres por «?», perdía saltos de línea y mostraba fechas
UTC ISO y valores `None`. La conversión de un plan podía lanzar una excepción
de validación sin traducirla a un error de usuario.

## Decisión

1. Verificar nacimiento cuando está registrado; en su ausencia, comparar en
   tiempo constante los cuatro caracteres alfanuméricos finales de un documento
   registrado. La ausencia de ambas referencias siempre falla, también para
   enlaces antiguos. No encolar enlaces nuevos sin una referencia verificable.
2. Mantener los límites por IP y cinco intentos. Auditar IP y contador sin
   nacimiento, documento, token ni contenido clínico. La invalidez de un enlace
   usa una respuesta genérica; la suspensión de una receta se comprueba después
   de verificar identidad, sin revelar su naturaleza en el mensaje público.
3. Incorporar DejaVu Sans desde la distribución oficial fijada de Matplotlib,
   con licencia y SHA-256. Usar CIDFontType2, UTF-16BE, mapa de glifos y ToUnicode
   en pypdf. Las métricas se regeneran con fontTools 4.66.1 fuera de la API;
   no se añaden dependencias de ejecución, Pillow, HTML ni fuentes remotas.
4. Dividir párrafos y ajustar filas por ancho de glifos. Conservar el texto en
   hexadecimal, sin interpretarlo como operadores PDF. Normalizar NFC. Rechazar
   glifos ausentes, marcas combinadas restantes, controles invisibles y escritura
   que necesite composición bidireccional; mostrar sus códigos Unicode al personal.
   Rechazar también categorías Unicode M, Zl y Zp aunque la fuente las incluya;
   conservar los saltos ordinarios LF de párrafo. La fuente no compone esas marcas.
   No transliterar ni reemplazar dosis o unidades. Validar la representación antes
   de encolar y generar antes de registrar una descarga exitosa.
5. Conservar la zona sede/clínica en las nuevas instantáneas y mostrar fecha local,
   offset e identificador de zona. Los registros anteriores usan la zona vigente
   de su sede o clínica: no se inventa un historial de configuración inexistente.
   Una zona inválida bloquea la exportación con error 422.
6. Explicar ausencias de documento/duración sin fabricar datos. Traducir los límites
   del presupuesto a 422, sin truncar conceptos ni crear registros parciales.
   El cliente interpreta cuerpos JSON pequeños de errores de descarga Blob.
7. Ocultar tokens de rutas privadas y consultas de URL en la cadena compartida
   de logging, también cuando una librería escribe la URL dentro de texto libre.
   Se reproduce con el registro de acceso de Uvicorn; no se afirma haber saneado
   registros históricos o configurado proxies externos.

## Consecuencias y límites

El PDF incluye una fuente completa comprimida: el ejemplo de una página pesa
aproximadamente 489 kB. La API solo guarda en caché fuente y métricas propias,
nunca texto o archivos de pacientes. No hay cambios de esquema, permisos o pauta
confirmada, ni firma electrónica certificada. No se declara soporte para todo
Unicode: emojis fuera de la fuente, escrituras complejas y glifos no incluidos
producen error explícito.

El enlace permanece en claro en la carga útil saliente del outbox. La copia en
`entrega_documento` sí usa hash y cifrado. Se documenta esta diferencia y se mantiene
pendiente resolver el enlace al enviar desde su referencia; el PDF nunca se entrega
solo con el token. WhatsApp real conserva sus requisitos de cuenta y consentimiento.

## Fuentes de implementación

- [Distribución fijada de DejaVu Sans](https://github.com/matplotlib/matplotlib/tree/v3.10.7/lib/matplotlib/mpl-data/fonts/ttf)
- [Licencia del archivo distribuido](https://raw.githubusercontent.com/matplotlib/matplotlib/v3.10.7/lib/matplotlib/mpl-data/fonts/ttf/LICENSE_DEJAVU)
- [Documentación de TTFont](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html)
- [Mapas de caracteres en pypdf](https://pypdf.readthedocs.io/en/stable/dev/cmaps.html)

Pruebas, resultados y pendientes: [informe de verificación](../verificacion-documentos-2026-10-10.md).
