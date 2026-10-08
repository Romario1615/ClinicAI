# Recursos visuales

## Identidad de IA (2026-10-08)

La interfaz comparte azul profundo, cobalto y cian. La portada y el panel usan
fondos oscuros; datos, formularios y ventanas conservan vidrio claro. Los
recursos anteriores se conservan para sus módulos y estados complementarios.
`acceso-equipo.png` y `panel-clinicai-dental-network-v1.jpg` ya no se usan en las
portadas: la composición actual es nativa de SVG y CSS, adaptable a toda la ventana.

- `frontend/src/app/compartido/fondo-ia.component.ts`: conexiones y 24 partículas
  con posiciones estables. Sin imágenes, azar, eventos de puntero ni ciclos de
  JavaScript. Decorativo, sin foco y oculto al lector de pantalla. Detiene el
  movimiento con la preferencia del usuario y desaparece al aumentar contraste.
- `grafico-red.component.ts`: núcleo **IA**, seis módulos conectados y pulsos de
  luz con el motor de movimiento existente; pausa sus bucles fuera de pantalla.
- `clinicai-simbolo.svg`: conserva el símbolo original y adapta su paleta al
  azul/cian. Se reutiliza como logo y favicon.

### Fondo anatómico del faciograma

Archivo: `frontend/public/images/faciograma-anatomia-v1.png` (PNG transparente,
2 065 744 bytes). Generado mediante la herramienta integrada **imagegen**,
modo generación; los puntos se dibujan como controles SVG independientes.
Ilustración de una persona anónima, sin fotografías ni datos de pacientes.
No representa puntos de inyección ni prescribe técnicas, dosis o tratamientos.

Prompt utilizado:

```text
Use case: scientific-educational. Asset type: background illustration for ClinicAI aesthetic patient face chart. Primary request: an original elegant frontal facial muscle anatomy illustration, adult anonymous face, perfectly symmetric straight frontal view from crown to neck. Fine anatomical muscle fiber drawing, neutral warm ivory skin edges, pale peach and terracotta muscle fibers, soft gray-blue eyes, natural closed lips, subtle depth and very clean medical atlas illustration finish. Composition: head centered, whole crown at y=35/400, eyes y=157/400, nose tip y=199/400, lips y=238/400, chin y=301/400, narrow neck and shoulders down to y=398/400; face widths correspond to x=83..237 in a 320x400 canvas. Show both ears at eye/nose level. Transparent background, isolated cutout with generous small margins. No printed labels, no markers, no points, no instructions, no injection sites, no lettering, no watermark, no UI. This is a general visual backdrop for manually entered observations; do not include procedure guidance.
```

## Recursos anteriores

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
| `historia-clinica-integral.jpg` | Banner panorámico de historia clínica con odontograma, formulario y protección del expediente; JPEG de 1600 × 533, optimizado a 62 KB |
| `medicacion-seguimiento.png` | Encabezado de medicación y adherencia |
| `lista-espera.png` | Encabezado de lista de espera |
| `pagos-administrativos.png` | Encabezado de pagos |
| `usuarios-roles.png` | Encabezado de usuarios y roles |
| `conversacion-asistente.png` | Encabezado del asistente conversacional |
| `catalogo-clinica.png` | Encabezado del catálogo de la clínica |
| `automatizaciones-flujo-clinica.svg` | Ilustración vectorial del encabezado de automatizaciones: escudo clínico conectado a agenda, mensajes y documentos; fondo transparente y escalable |
| `conocimiento-aprobado.png` | Ilustración anterior de la base de conocimiento, conservada para estados complementarios |
| `conocimiento-evidencia.jpg` | Portada panorámica de la base de conocimiento: documentos revisados, escudo y motivo dental conectado; 1600 × 533, optimizado a 67 KB |
| `campanas-pacientes.jpg` | Cabecera panorámica de promociones: comunicación y campañas con consentimiento; 1600 × 533, optimizado a 55 KB |
| `fondo-seguimiento-clinicai.png` | Fondo panorámico del encabezado de seguimiento inteligente, con área despejada para el título |
| `fondo-seguimiento-clinicai-v2.jpg` | Fondo panorámico nuevo del panel: arquitectura clínica luminosa con conexiones abstractas; 1600 × 533, optimizado a 64 KB |
| `panel-clinicai-red-clinica.jpg` | Fondo panorámico oscuro para el encabezado del panel, con red de nodos a la derecha; 1600 × 601, optimizado a 53 KB |
| `panel-clinicai-conectado.jpg` | Arte panorámico claro del panel: odontología conectada con indicadores clínicos, área despejada para el título; 2048 × 768, optimizado a 119 KB |
| `panel-clinicai-inteligencia.jpg` | Variante del panel inteligente: consultorio dental luminoso, diente translúcido y tarjetas abstractas; 1600 × 900, optimizado a 145 KB |
| `panel-fondo-clinico-ia-v3.png` | Fondo panorámico nuevo del panel: diente de vidrio y red clínica en el lado derecho, área despejada para el encabezado; 2172 × 724 |
| `panel-red-clinica-abstracta.jpg` | Fondo panorámico oscuro del panel: red clínica abstracta, espacio despejado a la izquierda y geometría luminosa a la derecha; 1672 × 941, optimizado a 109 KB |
| `panel-clinicai-dental-network-v1.jpg` | Variante actual de la cabecera del panel: molar de vidrio conectado por nodos clínicos, con espacio oscuro para el título a la izquierda; JPEG 1672 × 941, 176 KB |
| `integraciones-clinica-seguras.jpg` | Banner panorámico de integraciones seguras: escudo dental translúcido conectado con calendario, mensajería, IA y correo; 1600 px de ancho, optimizado a 120 KB |
| `integraciones-clinicai-banner.png` | Banner nuevo de integraciones: clínica y sistemas conectados con área oscura despejada para el título; 2172 × 724 px, PNG de 1,67 MB |
| `seguimiento-operativo-ia.png` | Arte raster anterior del seguimiento inteligente, conservado como recurso histórico; ya no lo consume la pantalla |
| `seguimiento-inteligente-clinica.svg` | Ilustración vectorial ligera de agenda, odontología, seguridad y métricas conectadas; reemplaza el PNG pesado del estado inicial del panel |
| `usuarios-roles-acceso.jpg` | Banner panorámico de acceso por roles: equipo clínico, escudo de permisos y módulos conectados; 1600 × 600, optimizado a 83 KB |
| `asistente-clinico-banner.jpg` | Cabecera panorámica del asistente: diente translúcido conectado con agenda, documento validado y mensajes; objetos a la derecha y espacio oscuro para el título a la izquierda; 1600 × 534, optimizado a 69 KB |
| `equipo-clinica-colaboracion.jpg` | Encabezado de Equipo clínico: profesionales y control de acceso, con el lado izquierdo despejado; 1536 × 1024, optimizado a 121 KB |
| `sedes-red-clinicas.jpg` | Encabezado de sedes: tres clínicas conectadas, con fondo claro para títulos y contenido; 1600 × 800, optimizado a 105 KB |
| `clinicai-simbolo.svg` | Símbolo vectorial del logo y favicon del sitio |
| `ambiente-clinicai-red-v1.jpg` | Fondo ambiental del área de trabajo: red de vidrio en tonos menta y marfil, 1536 × 1024 px y 96 KB. Desde el 2026‑10‑07 es **estático** (ver «Vidrio líquido»): bajo superficies de vidrio, un fondo en movimiento obliga a recomponer cada panel en cada fotograma |
| `flujo-clinico.svg` | Flujo explicativo que antes cerraba el panel de marca del acceso. Desde el 2026‑10‑07 lo sustituye el gráfico en movimiento de la red clínica; el archivo se conserva sin uso |
| `lista-espera-vacia.svg` | Ilustración vectorial accesible para la cola vacía: calendario confirmado, libreta clínica y planta; transparencia real y trazos que escalan en móvil |

## Iconos de interfaz

Los iconos funcionales se dibujan en SVG desde
`frontend/src/app/compartido/icono.component.ts`. El componente comparte
rejilla, trazo y color adaptable; evita imágenes rasterizadas para acciones
pequeñas y navegación. Incluye panel, agenda, espera, pacientes, historia,
medicamentos, conocimiento, catálogo, pagos, agente, usuarios, búsqueda, reloj,
teléfono, confirmación, cierre, añadir, aviso, candado, navegación, carga,
archivo, salida y escudo.
Los iconos `red-ia` y `red-clinica` representan la IA y la coordinación clínica,
respectivamente; `diente` representa el odontograma. Se amplió la biblioteca con iconos SVG de
`calendario-check`, `ubicacion-clinica`, `pulso`, `persona-verificada`,
`historial-clinico`, `sala-clinica` y `corazon-clinico`; el calendario con
confirmación acompaña la acción de abrir agenda y el corazón con pulso identifica
el contexto clínico del panel. Las señales del panel inteligente reutilizan estos SVG
como pictogramas: agenda para tareas, calendario confirmado para la cola al día, pulso
para inasistencia, métricas cuando falta base, y sala o pagos para sus seguimientos.
También incluye `descargar`, que identifica la exportación del resumen CSV desde la agenda, y los pictogramas `conexion-segura` y `llave-api` para protección de integraciones y credenciales.
`radiografia-dental` identifica el odontograma, `balance-clinico` acompaña los pagos y `actividad-inteligente` distingue el seguimiento operativo del panel.
`diente-conectado` acompaña la cabecera del panel y une el motivo odontológico con los nodos de ClinicAI.
El icono `roles` distingue Usuarios y roles de Equipo clínico: dibuja las tres posiciones de una matriz de acceso con la rejilla y el trazo SVG compartidos.
Los pictogramas `formulario-clinico`, `revision-dental` e `historial-versiones` amplían el lenguaje SVG para captura asistencial, examen oral y trazabilidad de correcciones.
`asistente-clinico` identifica el asistente del equipo con un trazo de auriculares y micrófono, conservando el mismo SVG adaptable a color y tamaño.
`revision-operativa` distingue resúmenes calculados localmente; `analisis-ia` identifica análisis generativos. Ambos viven en el componente compartido `IconoComponent` y mantienen el trazo actual de la interfaz.
`automatizaciones` identifica los flujos coordinados con tres nodos conectados; aparece en la cabecera de Automatizaciones. El fondo de esa cabecera suma puntos y conexiones tenues en desplazamiento lento, con movimiento desactivado para `prefers-reduced-motion`.
La cabecera de Automatizaciones usa `automatizaciones-flujo-clinica.svg`: una ilustración vectorial sin texto de un escudo clínico conectado con agenda, mensajería segura y documentos. El PNG anterior se conserva como recurso; la pantalla usa el SVG para mantener el arte nítido y ligero en cualquier densidad.
El menú móvil usa `menu`; las flechas `tendencia-subir` y `tendencia-bajar` y el chevrón `siguiente` forman parte de la misma biblioteca SVG, para evitar glifos de texto que cambian según la plataforma.
Los nuevos símbolos `equipo` y `sedes` mantienen el trazo SVG compartido y distinguen la administración de profesionales de la gestión de sucursales.
En Usuarios y roles, el icono de escudo acompaña la administración de accesos; las pestañas distinguen personal, roles y matriz con símbolos SVG existentes. Su nuevo banner agrupa el equipo y los módulos detrás de un escudo con espacio negativo para el título. El fondo se desplaza lentamente y suma un halo tenue, ambos desactivados con `prefers-reduced-motion`.
El panel presenta los agregados por día, día de semana y hora como barras horizontales con etiqueta y valor textual; conserva títulos, foco y estado vacío comprensibles sin depender del color.
El color acompaña el estado; el texto explica cada alerta.
La cola vacía usa `lista-espera-vacia.svg`, una ilustración SVG original sin texto incrustado. Flota apenas para dar vida al estado y se detiene con `prefers-reduced-motion`; el mensaje sigue siendo el indicador accesible para lectores de pantalla.

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
La pieza `campanas-pacientes.jpg` usa el mismo tratamiento visual, deja espacio
para el título y mantiene los elementos de comunicación a la derecha.
El nuevo `panel-clinicai-red-clinica.jpg` usa un tratamiento panorámico más
profundo: fondo azul petróleo, red de nodos luminosa a la derecha y espacio
vacío a la izquierda. Se generó sin texto, personas, equipo ni datos de interfaz,
y se exportó a JPEG de 1600 × 601 para mantenerlo por debajo de 55 KB.
`panel-clinicai-conectado.jpg` amplía la dirección hacia una escena clara de
odontología conectada: una pieza dental central, arquitectura clínica y paneles
abstractos de indicadores quedan a la derecha; el espacio de la izquierda
mantiene legible el encabezado. La ilustración se optimizó a JPEG de 2048 × 768
y 119 KB. `panel-clinicai-inteligencia.jpg` añade otra escena de analítica dental, con
consultorio luminoso y visualizaciones abstractas; se exportó a JPEG de 1600 × 900 y 145 KB.
`equipo-clinica-colaboracion.jpg` muestra a profesionales alrededor de un escudo
de permisos y módulos; `sedes-red-clinicas.jpg` representa tres clínicas unidas
por una ruta. Ambas mantienen el fondo marfil, las formas 3D suaves y el espacio
izquierdo reservado al texto. Se exportaron a JPEG optimizado para limitar su
peso conjunto a 227 KB.

## Vidrio líquido y movimiento (2026‑10‑07)

La interfaz usa un sistema de **vidrio líquido**: superficies translúcidas sobre un
fondo de luz suave, con canto iluminado, sombra que las separa y un reflejo que sigue
al puntero. Los tokens viven en `frontend/src/styles.scss` (`--aurora`,
`--vidrio-cuerpo`, `--vidrio-canto`, `--vidrio-sombra`, `--vidrio-desenfoque`…).

| Pieza | Cómo es | Por qué |
| --- | --- | --- |
| Aurora de fondo | Cuatro degradados radiales (menta, cielo, lila, melocotón) en una capa fija `body::before`, **estática** | El vidrio necesita algo que refractar; quieta, no obliga a recomponer los paneles en cada fotograma |
| Tarjetas, tablas, cabeceras de módulo | Vidrio esmerilado (62–88 % de blanco) sin `backdrop-filter` | `backdrop-filter` crea un bloque contenedor: atraparía los visores `position: fixed` (galería, diálogos) que viven dentro de una tarjeta. Sobre una aurora ya difusa, el resultado visual es el mismo |
| Cabecera, navegación, velo de ventanas, desplegables | Vidrio con desenfoque real (`blur(18–28px) saturate`) | Son lo que flota sobre contenido en movimiento. El desenfoque de la cabecera va en `::before` para que sus desplegables (avisos, buscador) desenfoquen la página y no solo la cabecera |
| Barra lateral | Vidrio oscuro de marca al 92 %, placa flotante con radio 24 px | Mantiene el texto secundario por encima de 5:1 |
| Botones | Vidrio claro con canto; el principal, vidrio teñido con brillo limitado al tercio superior | Blanco sobre `#0b6e6a` con el brillo conserva 5,3:1 |

**Contraste.** Se calculó sobre el peor caso: el tinte más intenso de la aurora bajo el
vidrio más transparente que lleva texto. El texto tenue pasó de `#5b7378` (4,4:1 en ese
caso) a `#506a6f` (más de 5,2:1). La cabecera usa `--texto-suave` para los roles porque
bajo ella puede pasar un banner oscuro.

**Preferencias del sistema.** `prefers-reduced-transparency: reduce` vuelve opacas las
superficies, quita la aurora y el desenfoque; `prefers-contrast: more` usa cuerpos
opacos y bordes firmes; sin soporte de `backdrop-filter`, el velo se oscurece más.

### Movimiento con Motion

El movimiento lo pone [Motion](https://motion.dev) (el motor de Framer Motion,
publicado también como API de JavaScript sin React). Angular no puede usar los
componentes `<motion.div>`, pero sí el mismo motor: `animate` sobre WAAPI con resortes
calculados por su generador `spring`. Vive en `frontend/src/app/nucleo/movimiento/`:

* `movimiento.service.ts` — fachada del paquete inicial: decide si se anima
  (`prefers-reduced-motion`, soporte de WAAPI) y carga el motor de forma diferida.
* `motor.ts` — todo lo que importa Motion (`motion/mini` + `spring` + `stagger`). Se
  carga después del arranque: Motion no cuenta en el paquete inicial (450 kB, antes
  498 kB, con el buscador global diferido con `@defer`).
* `coreografia.ts` — comportamientos por delegación para las 60+ pantallas sin tocar
  cada una: entrada escalonada de cabeceras, tarjetas, tablas y filas (también lo que
  llega tarde de la API y la pantalla entera al cambiar de ruta), presión de botones,
  reflejo que sigue al puntero (solo con ratón o lápiz) y barras que crecen.

Reglas: con movimiento reducido no se anima nada; al terminar se borran los estilos en
línea (`opacity`, `translate`, `scale`, `filter`) para no dejar bloques contenedores; el
interior de las ventanas flotantes no se anima aparte. Las ventanas flotantes entran con
resorte y **salen animadas antes de cerrar** (equivalente a `AnimatePresence`).

### Gráficos en movimiento (motion graphics)

| Pieza | Dónde | Qué hace |
| --- | --- | --- |
| `app-grafico-red` | Panel de marca del acceso (tono oscuro) y cabecera de Ayuda (tono claro) | Red clínica en SVG: núcleo de vidrio con escudo, seis nodos (agenda, pacientes, mensajes, conocimiento, pagos, historia). Las conexiones se dibujan, los nodos se posan con resorte, un pulso de luz recorre cada conexión, los nodos respiran, el anillo gira y flotan partículas. Decorativo (`aria-hidden`); se pausa fuera de pantalla |
| `[appContador]` | Fichas de indicadores (panel, módulos, Gastos y caja) | La cifra cuenta con un resorte desde el valor anterior. El texto final es exactamente el recibido; lo que no es una cifra inequívoca se pinta tal cual |
| Barras que crecen | Tendencias del panel, reparto por estado, carga por profesional, Gastos y caja | Escala horizontal desde su origen al llegar; la anchura real no cambia |

## Fondo y movimiento del panel

`panel-clinicai-dental-network-v1.jpg` es el fondo actual del panel. Usa un
molar translúcido conectado a una red clínica sobre azul petróleo y deja una
zona oscura despejada a la izquierda para el encabezado. El fondo se desplaza lentamente mientras un halo
y un reflejo recorren la superficie; el icono clínico tiene un pulso tenue. El
título y el contexto usan texto claro para mantener contraste. Todos los
efectos se desactivan cuando el sistema solicita movimiento reducido. El arte
se generó con imagegen y se exportó a JPEG de 1672 × 941 px y 176 KB.
`usuarios-roles-acceso.jpg` extiende ese lenguaje al encabezado de Usuarios y roles:
una composición 3D panorámica sitúa el equipo clínico y las áreas con permisos a la derecha;
el título queda sobre una zona despejada. El desplazamiento y el halo ambiental se detienen
cuando el sistema pide movimiento reducido. La imagen se exportó a JPEG de 1600 × 600 y 83 KB.
El área de trabajo combina una imagen ambiental de 96 KB con halos verde azulado y la
aurora del vidrio líquido; desde el 2026‑10‑07 ambos son estáticos y la imagen baja su
opacidad en móvil. La cabecera de
Promociones tiene su ilustración panorámica y adapta su contraste en móvil.
La pestaña Integraciones usa `integraciones-clinicai-banner.png`: deja el texto
despejado a la izquierda y sitúa a la derecha la clínica y sus conexiones de
equipo, agenda, IA, datos y mensajería. El halo del banner y el desplazamiento
de la ilustración son lentos y se desactivan con movimiento reducido. La imagen
PNG mide 2172 × 724 px; por su tamaño se carga con prioridad baja. El pictograma
SVG `conexiones` comparte el trazo adaptable de los iconos del producto. La
ilustración previa `integraciones-clinica-seguras.jpg` se conserva como recurso
histórico.
Las nuevas cabeceras de Equipo clínico y Sedes aplican el mismo desplazamiento
suave de ilustración y halo ambiental, con ajuste en móvil y apagado bajo
`prefers-reduced-motion`.
`panel-fondo-clinico-ia-v3.png` queda como variante visual disponible para
futuras pantallas; el panel de seguimiento usa ahora `panel-clinicai-dental-network-v1.jpg`.

## Historia clínica y formulario asistencial

`historia-clinica-integral.jpg` extiende las cabeceras de la historia con un
formulario clínico visual, exploración dental y protección del expediente. Se
usa como fondo panorámico de la cabecera; el degradado mantiene el texto legible
y deja ver la ilustración en escritorio y móvil. La posición del fondo se anima
lentamente y se detiene con `prefers-reduced-motion`. El recurso fue generado
con imagegen y optimizado a JPEG de 1600 × 533 px y 62 KB. No contiene datos,
texto clínico ni instrucciones médicas.

Prompt de la cabecera dental: ilustración 3D panorámica para panel clínico, molar
translúcido de vidrio teal conectado con nodos clínicos, atmósfera azul petróleo,
45 % izquierdo vacío y oscuro para texto, luz menta suave, sin personas, texto,
logotipos ni interfaz. Se exportó a JPEG de 1672 × 941 px para su uso como fondo.

## Cabecera del asistente

`asistente-clinico-banner.jpg` añade una escena dental conectada con agenda,
documento y mensajería. El título queda sobre el área oscura despejada de la
izquierda, mientras que los elementos ilustrados ocupan la derecha. La cabecera
usa un desplazamiento de fondo y un halo lentos; ambos se desactivan con
`prefers-reduced-motion`. El recurso se generó con imagegen para esta pantalla,
sin texto incrustado ni interfaz legible. Se exportó a JPEG de 1600 × 534 y
69 KB para reducir la descarga de la cabecera.

La bandeja de Atención de mensajes usa `bandeja-sin-pendientes.png` cuando no hay conversaciones que revisar. Es una ilustración 3D con fondo transparente, reducida a 512 × 512 y 174 KB para conservar detalle sin cargar una escena grande. Su flotación de cinco píxeles se desactiva con `prefers-reduced-motion`. El pictograma SVG `mensajes-seguros` acompaña el encabezado de comunicación y mantiene el trazo común del sistema.
El seguimiento inteligente muestra `seguimiento-inteligente-clinica.svg` antes de que el equipo solicite un resumen o análisis. Esta pieza vectorial original agrupa agenda, odontología, permisos y métricas alrededor del panel. Mantiene el fondo ambiental animado y la flotación sutil existentes, con movimiento detenido mediante `prefers-reduced-motion`; el SVG no incrusta texto clínico ni datos de pacientes. `seguimiento-operativo-ia.png` queda conservado como recurso histórico, pero ya no lo consume la pantalla.

## Base de conocimiento

`conocimiento-evidencia.jpg` renueva la portada de la base de conocimiento con
documentos clínicos verificados, protección y un motivo dental conectado. El
degradado deja el texto legible sobre la parte izquierda. La imagen se generó
con imagegen, se exportó a JPEG de 1600 × 533 px y pesa 67 KB. El halo del
encabezado se mueve lentamente y se detiene con `prefers-reduced-motion`.
El flujo de carga, revisión, aprobación y respuesta ahora combina número e
icono SVG. La biblioteca compartida suma `revision-documental` y
`respuesta-documentada`; ambos conservan el trazo y el color adaptable de
ClinicAI.
