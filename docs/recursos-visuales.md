# Recursos visuales

Las ilustraciones generadas comparten una dirección visual: volúmenes 3D suaves,
paleta verde azulado, marfil y salvia, fondo transparente cuando corresponde y
sin texto incrustado. Se guardan en `frontend/public/images/` y se consumen
desde `/images/`.

| Archivo | Uso |
| --- | --- |
| `acceso-equipo.png` | Fondo de acceso al sistema |
| `inicio-coordinacion.png` | Portada del panel principal |
| `agenda-turnos.png` | Encabezado y estado vacío de agenda |
| `busqueda-pacientes.png` | Encabezado y estado vacío de pacientes |
| `historia-segura.png` | Encabezado de historia clínica |
| `medicacion-seguimiento.png` | Encabezado de medicación y adherencia |
| `lista-espera.png` | Encabezado de lista de espera |
| `pagos-administrativos.png` | Encabezado de pagos |
| `usuarios-roles.png` | Encabezado de usuarios y roles |
| `conversacion-asistente.png` | Encabezado del asistente conversacional |
| `catalogo-clinica.png` | Encabezado del catálogo de la clínica |
| `conocimiento-aprobado.png` | Portada de la base de conocimiento |
| `clinicai-simbolo.svg` | Símbolo vectorial del logo y favicon del sitio |

## Iconos de interfaz

Los iconos funcionales se dibujan en SVG desde
`frontend/src/app/compartido/icono.component.ts`. El componente comparte
rejilla, trazo y color adaptable; evita imágenes rasterizadas para acciones
pequeñas y navegación. Incluye panel, agenda, espera, pacientes, historia,
medicamentos, conocimiento, catálogo, pagos, agente, usuarios, búsqueda, reloj,
teléfono, confirmación, cierre, añadir, aviso, candado, navegación, carga,
archivo, salida y escudo.

La marca ClinicAI combina un símbolo clínico con nodos conectados y el
wordmark del componente `frontend/src/app/compartido/marca.component.ts`.

## Prompts visuales

Las imágenes se generaron con imagegen. Base común: ilustración editorial 3D
mate para una plataforma clínica profesional, formas redondeadas de arcilla y
papel, verde azulado apagado, marfil y salvia, luz suave, composición limpia,
sin letras, números, logotipos ni interfaz legible. Los prompts particulares
adaptaron el objeto al uso de cada archivo: equipo clínico, coordinación,
agenda, búsqueda de pacientes, historia protegida, seguimiento de medicación,
lista de espera, pagos, control de roles, conversación con asistente, catálogo
de clínica y documentos aprobados.
