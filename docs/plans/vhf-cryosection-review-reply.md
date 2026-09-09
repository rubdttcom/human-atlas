# Respuesta a la revisión externa del plan de segmentación de criosecciones

Fecha: 9 de septiembre de 2026. Revisión recibida el 8 de septiembre sobre `docs/plans/vhf-cryosection-segmentation-plan.md` (plan A) y `generated/nlm-ct-registration.json`.

Gracias por la revisión. Es precisa y la aceptamos casi entera. Abajo va lo que cambia, lo que ya estaba resuelto en un documento que no habías visto, y datos nuevos que obtuvimos ayer.

## 1. Existe un plan B que no viste

Desde el 6 de septiembre trabajamos sobre `docs/plans/vhf-cryosection-machine-driven-plan.md` (rama `female-open-atlas`, mismo repositorio). Cambia el papel del anatomista: no etiqueta, audita a ciegas paneles muestreados por estratos (regla de tres: 0 rechazos en 60 implica menos del 5 % de error al 95 %). Los nombres de las estructuras salen de priors, no de una persona. Tu revisión se ha incorporado en su sección 10, punto por punto.

Dos restricciones del proyecto que tampoco tenías:

- **Regla de sexo.** Ningún dato de entrenamiento, prior de forma ni grafo de adyacencia proviene de un cuerpo masculino. Esto excluye Voxel-Man SIO (Visible Human Male, CC BY 4.0), Denver masculino y BodyParts3D. Los modelos genéricos de CT entrenados con pacientes de ambos sexos se admiten como herramientas de nombrado sobre el CT de la propia donante.
- **Regla de licencia.** Un modelo cuyos pesos sean Apache, MIT, CC BY o licencia SAM puede tocar etiquetas publicadas. Pesos NC o SA solo sirven para métricas internas. Por eso MedSAM2 (pesos CC BY-SA, "solo investigación") y nnInteractive (CC BY-NC-SA) quedan fuera del camino de etiquetas. Tu punto 5 sobre el 85 % de ahorro queda así sin objeto, pero tu métrica (minutos humanos por estructura aceptada) la adoptamos.

## 2. Qué aceptamos de tus siete puntos

| Punto | Cambio en el plan B |
|---|---|
| 1. El registro rígido pélvico no demuestra alineamiento global; p95 < 2 mm no está respaldado | Aceptado. La concordancia con el CT pasa a ser un ajuste rígido **por hueso** con umbral relativo: el hueso de criosección obtenido por máquina debe igualar o mejorar lo que los huesos de Denver alcanzan contra el mismo CT (fémures: 3,4 y 4,4 mm p95). Error de alineamiento y de segmentación se reportan por separado. Encima de la pelvis no hay fotografías alineadas de referencia; el residuo fotografía-CT se publica como incertidumbre. |
| 2. La validación por cortes filtra información | Aceptado. Bandas espaciales de 50 mm reservadas. Además, conjunto de prueba **sellado** en antebrazo y tronco (10 estructuras, unas 4 h de anatomista, con hash), evaluado una vez por versión. Mide la transferencia a regiones sin etiquetas. |
| 3. Clases de tejido explícitas; etiquetas compuestas de Denver; no etiquetado no es fondo | Aceptado. Mapa de etiquetas versionado (`registry/cryo-tissue-map.json`), clases compuestas explícitas, etiqueta "ignorar" para anatomía sin anotar. Solo bloque, aire y mesa son fondo conocido. |
| 4. Entrenar con las máscaras originales; `femors` no alinea; máscara frente a malla no valida alineamiento | Aceptado. Entrenamiento solo con mapas originales. La diferencia original-final se mantiene como **cota inferior** de variabilidad humana, no como acuerdo entre anotadores. El plan B nunca atribuyó el alineamiento a `femors`: el artículo de Denver describe alineamiento manual y automático en ScanIP sin métrica publicada. La comprobación de alineamiento es imagen a imagen contra las fotografías alineadas de Denver. |
| 5. Ahorro de MedSAM2 no probado; métrica de tiempo humano | Aceptado en la métrica. MedSAM2 ya estaba fuera por licencia. |
| 6. Reentrenar invalida la revisión | Aceptado. Cada decisión de auditoría se liga al SHA-256 del volumen y la malla, versión del modelo y semilla. Una predicción nueva es una propuesta sin estado heredado. |
| 7. 24 GB no es requisito; faltan presupuestos de RAM y disco | Aceptado. Trabajamos con una RTX 3080 de 10 GB. RGB en `uint8` (39 GB), etiquetas `uint16` (26 GB), inferencia por bloques, sin materializar probabilidades de cuerpo entero. |

Tu primer hito coincide en lo esencial con el nuestro. La diferencia: tú asumes un anatomista que anota con asistencia; nosotros mantenemos al anatomista como auditor más las 4 horas del conjunto sellado.

## 3. Datos nuevos (9 de septiembre)

Ejecutamos MOOSE 3.2.2 (código Apache-2.0, pesos CC BY 4.0) sobre el CT fresco de la donante, cuatro modelos, 4,4 minutos en la RTX 3080. Es el sustituto abierto de la tarea licenciada `appendicular_bones` de TotalSegmentator. Resultados en `data/derived/nlm-vhf/moose/` y `generated/moose-vs-totalseg.json`.

**Cobertura.** 31 de 31 etiquetas periféricas (húmeros, radios, cúbitos, carpos, metacarpos, falanges, escápulas, clavículas, cráneo, patelas, tibias, peronés, tarsos, metatarsos, dedos), 24 vértebras, caderas, sacro, 24 costillas y esternón. Los huesos de la mano vienen agrupados por lado; la separación individual es tarea de la fase 3 del plan B.

**Acuerdo entre dos modelos independientes (Dice MOOSE frente a TotalSegmentator `total`, mismo CT):**

| Grupo | Dice |
|---|---|
| Fémures | 0,96 |
| Húmeros, caderas | 0,92 |
| Esternón, cráneo, clavículas | 0,83 a 0,88 |
| Sacro, escápulas | 0,73 a 0,78 |
| Vértebras T10 a L5 (salvo L1 a L3) | 0,81 a 0,87 |
| Costillas | 0,68 a 0,75 |
| Vértebras cervicales y torácicas altas | 0,55 a 0,79 |
| L1, L2, L3 | 0,65, 0,39, 0,60 |

Lectura. En huesos largos los dos modelos coinciden. En estructuras finas (costillas, cervicales) los volúmenes casi coinciden pero el Dice cae: es desacuerdo de borde a 1 mm, no de nombre. En L1 a L3 hay un desacuerdo real de frontera: TotalSegmentator da L1 77 y L2 86 mL; MOOSE da L1 51, L2 62 y L3 112 mL. La suma coincide (231 frente a 225 mL); el reparto no. Los centroides lo confirman: de C1 a T12 el desfase entre modelos es sistemático y pequeño (2,5 a 4,6 mm, siempre MOOSE más caudal), es sesgo de borde; en L1, L2 y L3 el desfase salta a 17 a 21 mm, media vértebra, y en L4 y L5 vuelve a 5,7 y 1,9 mm. Uno de los dos modelos desplaza los nombres lumbares; MOOSE además fragmenta L2 en 18 componentes. Ninguno de los dos es fiable ahí. Esto es exactamente lo que el plan B resuelve con votación de tres modelos y desacuerdo como incertidumbre, y donde la fotografía a 0,33 mm debe arbitrar. Hasta entonces, L1 a L3 no entran en el atlas desde el CT.

**Hallazgo que cambia la prioridad del antebrazo derecho.** El cúbito derecho de MOOSE mide 23 mL frente a 51 mL el izquierdo. No es error del modelo: el cúbito y el radio derechos tocan el borde del campo de visión del CT (índice x = 0; 10 806 vóxeles óseos en las tres primeras columnas del rango del antebrazo). El CT fresco de 1993 corta el antebrazo derecho. Por tanto **el antebrazo derecho de la donante solo puede salir de las criosecciones**. Es un argumento directo a favor de tu propuesta de probar primero en antebrazo, y lo adoptamos como región del conjunto sellado.

## 4. Lo que te pedimos

1. Revisa la sección 2.2 del plan B (criterios de aceptación) y la 2.4 (conjunto sellado). Dinos si el umbral relativo por hueso te parece defendible.
2. Si conoces etiquetas abiertas de criosecciones **femeninas** con órganos, dínoslo. No hemos encontrado ninguna con licencia compatible con CC BY 4.0 (Visible Korean femenino existe pero es no comercial con permiso de KISTI; CVH femenino no tiene acceso público).
3. Cualquier objeción a la regla de licencia sobre pesos NC o SA en el camino de etiquetas.

Enlaces (rama `female-open-atlas`): plan B `docs/plans/vhf-cryosection-machine-driven-plan.md`; comparación `generated/moose-vs-totalseg.json`; centroides `generated/moose-vs-totalseg-vertebra-centroids.json`; estado del proyecto `docs/PROGRESS.md`.
