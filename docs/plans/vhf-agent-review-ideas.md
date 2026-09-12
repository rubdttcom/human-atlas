# Ideas para Fable: revisión especializada de futuras segmentaciones

Fecha: 10 de septiembre de 2026. Encargo del usuario: incorporar estas ideas como posibles ampliaciones o mejoras de las fases futuras ya planificadas. Es una propuesta experimental, no una técnica validada ni una instrucción para iniciar entrenamiento ahora.

## Origen y evidencia disponible

Ryan Peters describe un Qwen3-VL-2B ajustado para segmentar instancias de células usando una aplicación de etiquetado sin interfaz visible: recibe capturas y emite acciones para dibujar polígonos, ampliar y navegar. La idea transferible es un agente especializado que inspecciona y actúa de forma iterativa.

- Publicación: https://x.com/ryanpirl/status/2097734029080694963 (9 de septiembre de 2026). El texto se recuperó mediante https://api.fxtwitter.com/status/2097734029080694963 porque X devolvía 403.
- Modelo base: https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct . Su ficha describe manejo de interfaces y localización visual; declara Apache-2.0. Esto no determina la licencia de un ajuste de terceros.
- Repositorios públicos del autor revisados: https://github.com/ryanirl?tab=repositories . No se localizó la implementación ni los pesos de esta demostración.
- SAM3 ya incluye integración con agentes: https://github.com/facebookresearch/sam3 y su ejemplo sam3_agent.ipynb.

La publicación no aporta métricas, comparación con SAM3, evaluación anatómica ni prueba en criosecciones. No asumir transferencia desde células ni que el modelo base reproduce el ajuste mostrado. No se ha ejecutado ninguna comparación en este proyecto.

## Encaje con el plan B

Referencia: vhf-cryosection-machine-driven-plan.md. Mantener la distinción entre geometría, identidad anatómica y colocación. El núcleo previsto es nnU-Net con antecedentes del CT; SAM3 ya es una segunda opinión. El agente sería una inspección adicional dirigida, condicionada a demostrar valor incremental.

- Fase 0, datos y alineación: conservar transformaciones exactas entre coordenadas de pantalla, recorte, imagen y espacio físico. El zoom no debe introducir errores de medida. Verificar primero fotografía RGB frente a etiquetas Denver; sus DICOM alineados son grises.
- Fase 2, entrenamiento: adaptación opcional con etiquetas Denver y bloques de entrenamiento autorizados de esta donante. Las máscaras permiten generar trayectorias de dibujo sintéticas, pero estas serían una propuesta nuestra, no el método documentado del autor. Respetar la regla de fuentes femeninas y mantener fuera los bloques de prueba, sus buffers y sus ejemplos.
- Fase 3, instancias y nombres: probar detección de fugas, omisiones, fusiones, divisiones y discontinuidad entre cortes. Permitir ampliar zonas y consultar cortes vecinos. Emitir incidencias localizadas y abstención. Una máscara correcta no demuestra el nombre; nombres provisionales deben seguir pendientes cuando falte evidencia.
- Fase 4, autoentrenamiento: el acuerdo SAM3-agente no basta para admitir pseudoetiquetas. No entrenar el verificador con respuestas de SAM3 y presentar después su acuerdo como validación independiente. Mantener procedencia y separación entre corrección y evaluación.
- Fase 5, comprobaciones: medir qué errores adicionales detecta frente a los controles existentes y cuántos errores aceptan ambos. Incluir controles deliberados y errores reales. No usar una explicación verbal convincente o confianza declarada como prueba.
- Fase 6, revisión: aprovechar las incidencias para preparar dosieres dirigidos; preservar el muestreo aleatorio de la auditoría prevista para que la selección del agente no oculte errores. No conceder inspected o batch-audited por aprobación de un modelo.
- Fase 7, integración: guardar versión, entradas, acciones, coordenadas, decisiones, abstenciones y procedencia. Generar colores de forma determinista desde el identificador anatómico; el color no es una segunda evidencia.

No es necesario reproducir una interfaz completa para el piloto. Una API pequeña para pedir recortes, consultar cortes vecinos, devolver polígonos e incidencias puede reducir complejidad. El valor de actuar sobre una interfaz frente a esta alternativa debe comprobarse, no darse por supuesto.

## Dos funciones que deben evaluarse por separado

1. Agente que dirige SAM3: selecciona recortes o prompts y pide nuevas máscaras. Puede mejorar la segmentación, pero sus resultados dependen de SAM3.
2. Revisor con propuesta propia: primera lectura de la fotografía original y cortes vecinos sin máscara ni nombre de SAM3; registra observaciones, contornos o puntos y abstenciones. Después compara contra la propuesta SAM3 y localiza discrepancias. Mantener congelada la primera lectura para evaluar el anclaje.

La segunda opción reduce circularidad, pero no crea independencia estadística: ambos observan las mismas fotografías y pueden compartir sesgos. El CT aporta otra modalidad solo donde hay cobertura y registro suficiente. El antebrazo derecho parcialmente fuera del CT sigue teniendo esa limitación. Si el agente recibe los mismos antecedentes del CT, registrar también esa dependencia.

## Piloto propuesto y decisión de adopción

Ampliar el piloto de 50 secciones Denver ya previsto para SAM3, distribuido en bloques espaciales y clases relevantes. Es una prueba inicial de viabilidad, no una certificación estadística de todo el cuerpo. Si esas secciones se usan para seleccionar o ajustar el método, reservar otras para la evaluación final. Mantener los buffers definidos en el plan.

Comparaciones sobre los mismos casos:

- SAM3 con los controles actuales.
- El mismo sistema más el agente revisor.
- Correcciones del agente, si se ensayan, puntuadas separadamente contra la referencia.

Incluir máscaras sin alterar, errores reales y controles deliberados: desplazamientos, dilatación/erosión, omisiones, fusiones, divisiones e intercambio de nombres con contorno correcto. Para nombres, aportar contexto anatómico suficiente y admitir abstención.

Medir por clase y por bloque: sensibilidad a errores, falsas alarmas, errores aceptados por ambos, cobertura de decisiones y abstenciones, Dice donde sea útil, distancia de contorno p95 en milímetros y tiempo por estructura. Medir también correcciones que estropean casos inicialmente correctos. No tratar cortes contiguos como muestras independientes; informar incertidumbre por bloques y tamaños de muestra.

El criterio de adopción es reducción de errores que pasan los controles a una carga de revisión asumible, con umbrales fijados antes de la evaluación final. No basta aumentar el acuerdo entre modelos. Empezar por localizar y señalar fallos; habilitar correcciones automáticas solo tras medir beneficio neto.

Después explorar antebrazo, mano y tronco. Sin referencia allí, las métricas Denver no prueban precisión en esas regiones. Conservar los estados de incertidumbre y las reglas de consulta dirigida ya previstas.

## Encargo a Fable

Incorporar estas posibilidades a las fases futuras pertinentes del plan, como experimentos opcionales con dependencias, métricas y puerta de adopción. Mantener el trabajo actual y su orden salvo justificación explícita. No presentar la demostración como evidencia anatómica, no sustituir los criterios existentes de aceptación y no iniciar descargas, ajuste de modelos o ejecución a gran escala por esta nota. Resolver cualquier discrepancia con el estado más reciente del plan y explicar qué ideas se incorporan y cuáles quedan aplazadas.
