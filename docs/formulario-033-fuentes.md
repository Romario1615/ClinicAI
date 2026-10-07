# Formulario SNS‑MSP/HCU‑form.033/2021

## Estado de investigación — 2026-10-06

La versión que debe guiar la implementación se identifica como **SNS‑MSP/HCU‑form.033/2021**.
Una ficha de contratación pública del Ecuador lista el formulario de odontología con ese código,
en A4, a color y por las dos caras; otra ficha pública describe la misma especificación de
impresión. Estas fuentes acreditan el código y uso administrativo reciente, pero no sustituyen
la copia matriz ni una revisión institucional de contenido.

* [Servicio Nacional de Contratación Pública — ficha de formularios HCU](https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe?id=BEOeoBa-oKid0OYG-WqiP9pbgoMMN9fCqlHX0iJTVFk%2C&op=0), fila del Formulario 033/2021.
* [Servicio Nacional de Contratación Pública — especificación de impresión](https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe?id=Xd7SVaVbTTwLdv4H6WAIcyQZ4jX_F5YAVlNQRLefXnU), fila del Formulario 033/2021.
* [Ministerio de Salud Pública — Acuerdo 00115‑2021](https://enlace.17d07.mspz9.gob.ec/biblioteca/estad/AC-00115-2021%20ENE%2010.pdf), reglamento de Historia Clínica Única. El PDF abierto contiene el acuerdo principal; no se debe inferir que incluye todos sus anexos.
* [Registro Oficial — Acuerdo Ministerial 0091 (2017)](https://www.salud.gob.ec/wp-content/uploads/2014/05/Acuerdo-0091.pdf), referencia histórica de un anexo 033 anterior. **No reproducir esa versión como si fuera la 033/2021.**
* [Repositorio universitario — instructivo 2021 atribuido al MSP](https://dspace.uniandes.edu.ec/handle/123456789/19216), copia secundaria útil para inspeccionar la estructura; el archivo directo requiere inicio de sesión.
* [Secretaría de Salud de Quito — lineamiento operativo, anexo de Odontología 033](https://salud.quito.gob.ec/wp-content/uploads/2025/07/17-Lineamiento_Operativo_Unidades_Moviles_De_La_Red_Municipal_De_Servicios-_de_Salud.pdf), fuente institucional secundaria que reproduce las secciones.
* [UNIANDES — anverso/reverso del Formulario 033/2021](https://dspace.uniandes.edu.ec/bitstream/123456789/17234/1/USD-ADNL-EXC-004-2023.pdf), transcripción de la copia del formulario, no matriz normativa.

La copia 2021 atribuida al MSP y la transcripción municipal reproducen estos bloques:

| Sección | Contenido contrastado |
| --- | --- |
| A | Establecimiento y paciente: institución, unicódigo, establecimiento, historia clínica, archivo, hoja, nombres, sexo y edad. |
| B–C | Motivo de consulta, condición de embarazo y enfermedad actual. |
| D–E | Antecedentes patológicos personales y familiares; el bloque personal enumera alergias a antibiótico/anestesia, hemorragia, VIH/SIDA, tuberculosis, asma, diabetes, hipertensión, cardiopatía y otros. |
| F–G | Temperatura, pulso, frecuencia respiratoria, presión arterial y examen del sistema estomatognático por región. |
| H–K | Odontograma, indicadores de salud bucal, índices CPO‑ceo y simbología del odontograma. |
| L–M | Pedido e informe de exámenes complementarios. |
| N–P | Diagnósticos presuntivos/definitivos con código CIE, datos del profesional responsable y sesiones de tratamiento con diagnóstico/complicaciones, procedimiento, prescripción y firma/sello. |

La transcripción muestra seis registros diagnósticos y seis filas de sesión en el reverso; se debe
confirmar capacidad y disposición en el anexo matriz antes de presentarlo como reproducción fiel.
La impresión referenciada es A4 a doble cara. El PDF del Acuerdo MSP 00115‑2021 que se pudo abrir
contiene el acuerdo principal, no el anexo matriz. Esta investigación guía campos y secciones, pero
no certifica el contenido normativo ni la validez jurídica del formato implementado.

## Criterios de implementación

* Reutilizar los datos maestros de clínica, sede, paciente y profesional; no crear duplicados editables.
* Vincular cada registro a una atención y mantener autor, fecha, clínica, sede y versiones anteriores.
* Mantener el odontograma y el índice de placa O'Leary como registros clínicos propios. El indicador
  de higiene oral simplificada del Formulario 033 es otra medición: no sustituirlo por el porcentaje
  O'Leary. Enlazar las fuentes o congelar sus versiones sin duplicar datos editables.
* Capturar las secciones que faltan (examen estomatognático, higiene oral simplificada, CPO‑ceo y
  exámenes) y conectar las existentes (paciente, clínica, profesional, antecedentes, nota/diagnóstico,
  odontograma y tratamiento). Nunca inferir valores clínicos no registrados.
* Generar la salida A4 a doble cara con código de versión visible, después de contrastar la maqueta
  con el anexo matriz completo.
* El campo de firma manuscrita debe quedar disponible para impresión. Una impresión con el nombre del
  profesional no se debe presentar como firma electrónica ni como documento firmado.
* Registrar la generación y descarga en auditoría bajo el permiso clínico y la relación asistencial.
* Antes de etiquetarlo como formulario oficial o documento con validez jurídica, cotejar campos,
  símbolos, colores, instrucciones de llenado y reglas de conservación contra el anexo oficial completo
  y obtener revisión institucional competente.

## Estado de ClinicAI

El odontograma, el índice de placa O'Leary, las notas de evolución, los antecedentes/alergias,
las plantillas propias de anamnesis y los planes de tratamiento tienen modelos independientes.
La API persiste capturas 033 inmutables por versión, con contexto de identidad congelado,
fuentes opcionales enlazadas y alcance por profesional, sede y relación asistencial. Como el formulario
incluye campos de alta sensibilidad como VIH/SIDA, lectura y escritura requieren el permiso clínico
correspondiente **y** `historia_clinica.leer_sensible`; sus operaciones se auditan como N3. La pantalla
permite crear, consultar y corregir mediante una versión nueva, y consultar su historial. La copia
imprimible presenta anverso y reverso A4 con identidad congelada, secciones capturadas, fuentes
vinculadas existentes, autor, fecha y versión. Antes de abrirla, el servidor vuelve a validar el
permiso clínico N3 y la relación asistencial, y registra la versión en auditoría. El navegador permite
imprimir o guardar la copia en PDF; el personal elige impresión dúplex si el equipo la ofrece. El
diseño aún no se ha cotejado con la matriz oficial: se identifica como transcripción clínica y no como
documento oficial ni con validez jurídica. La pantalla permite asociar cita, nota, odontograma e
índice de placa según permisos y módulo disponibles. Las citas se limitan al paciente y profesional
actuales y se excluyen las canceladas y las inasistencias. La nota solo completa, por acción explícita,
el motivo y relato subjetivo que estén vacíos; no se sobrescribe contenido y las demás fuentes quedan
enlazadas sin conversión automática. Al corregir se preservan las referencias, que se muestran en el
detalle y en la impresión. La suite frontend pasó 427/427. Dieciséis pruebas API/esquema verificaron
el flujo en PostgreSQL aislado en migración 020, incluida la asociación de fuentes del paciente y el
rechazo de fuentes pertenecientes a otra persona. Esa base se retiró al terminar la prueba. La base
local compartida permanece en 019 y no se modificó.
Las plantillas configurables de anamnesis no representan ni reemplazan este formulario.
