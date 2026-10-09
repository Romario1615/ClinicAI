# Evaluación de WhatsApp mediante MCP — 2026-10-09

## Estado comprobado

La búsqueda «WhatsApp» en el directorio de plugins no devolvió conectores.
Las herramientas de esta sesión y los nombres de servidores de la configuración
local tampoco incluyen un MCP de WhatsApp. No se instaló un servidor ni se
conectó una cuenta. Se solicitó al usuario el nombre o enlace del MCP que desea
usar, sin pedir tokens por chat.

ClinicAI ya dispone de bandeja, webhooks, configuración por clínica, agente
operativo y cola de envíos con WhatsApp Business Cloud API. La verificación
actual emplea sandbox. Los detalles están en [whatsapp-integration.md](whatsapp-integration.md).

## Alternativas localizadas

| Proyecto del autor | Interfaz declarada | Datos de cuenta requeridos | Alcance de esta revisión |
| --- | --- | --- | --- |
| [WBMCP](https://github.com/saravanaspar/WBMCP) | MCP y SDK TypeScript sobre Cloud API; herramientas de mensajes, plantillas y recursos | Token Meta, identificador del número y cuenta Business | Lectura del README; no instalación ni auditoría de su código |
| [whatsapp-business-mcp](https://github.com/tkhattar14/whatsapp-business-mcp) | Python, MCP stdio y servicio HTTP sobre Cloud API | Token Meta e identificador del número; parámetros adicionales para la cuenta/webhooks | Lectura del README; no instalación ni auditoría de su código |

Son proyectos de terceros. Sus descripciones permiten inferir compatibilidad
con el proveedor exigido por ClinicAI; no demuestran integración con los
permisos de ClinicAI. WBMCP declara que no proporciona bandeja ni almacenamiento
de conversaciones y ofrece una opción de herramientas de escritura deshabilitadas.
Referencia del proveedor: [colección oficial de Meta](https://www.postman.com/meta/whatsapp-business-platform/overview).

## Encaje propuesto

Primero se identifica el servidor, versión y transporte. Se revisan sus
dependencias, autenticación, herramientas expuestas y tratamiento de secretos.
La primera conexión puede consultar la cuenta y plantillas de prueba; enviar
un mensaje real requiere un destinatario de prueba y autorización explícita.

Conectarlo al asistente de desarrollo permite herramientas en esa sesión.
Incorporarlo al agente de ClinicAI exige además un adaptador del backend.
Ese adaptador debe usar la configuración cifrada de la clínica y pasar por
los controles existentes de permisos, consentimiento, paciente, ventana de
mensajería, idempotencia, outbox y auditoría. Un token global de un cliente
MCP no satisface el aislamiento entre clínicas de la aplicación.

La recepción de mensajes y estados continúa mediante los webhooks con firma
validada. El MCP no cambia la ventana de 24 horas ni la necesidad de plantillas.
Se mantiene la separación entre apoyo operativo y registro clínico humano.
CLAUDE.md, regla 9, exige Cloud API: un MCP que use WhatsApp Web o sesiones QR
no cumple esa regla del proyecto.

## Información pendiente

Nombre/enlace del servidor MCP y ubicación donde se conectará: sesión de
desarrollo o backend ClinicAI. Después, cuenta Meta de prueba, número Business,
permisos y secretos se configuran en el almacén correspondiente, fuera del chat
y de Git. Aún no hay evidencia de autenticación, entrega o recepción real.
