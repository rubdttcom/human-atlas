# Revisión profunda por muestreo — RGB / Denver

Fecha: 2026-09-13. Auditor: Codex. Geometría de acbe4dd; estados de identidad del transform en trabajo durante la revisión. No se han modificado archivos del proyecto, ni hecho commit/push.

## Alcance y procedimiento ejecutado

14 fotos originales comprimidas copiadas desde rub-pc, con SHA cotejado contra inventario; cortes de scan_data y label_data del VHF_Full.mat local. SHA de los cortes grises cotejado contra el informe. Muestras k: 7, 500, 1207, 1210, 1550, 1893, 1896, 2259, 2285, 2295, 2315, 2500, 3000, 3532. Selección intencional: tres bloques, extremos, transiciones e identidades débiles; no es muestreo aleatorio representativo.

Aplicación de la geometría entregada sin reajuste; revisión visual de RGB alineado, gris original Denver, contornos originales de etiquetas y diferencia fotométrica. Controles negativos de espejo y desplazamiento de 6 píxeles RGB; comparación con cortes Denver vecinos. Ajuste RGB->gris exclusivamente fotométrico con partición de píxeles para diagnóstico, no evaluación anatómica independiente. Ocho cortes de huecos comprobados con máximo de intensidad cero.

Ejecución reproducible: desde human-atlas, .venv/bin/python /tmp/cryo-audit-ivJcL2/review.py. Entradas RGB, código, paneles y review-results.json están en este directorio temporal.

## Hallazgo prioritario: observabilidad no equivale a identidad ni integridad

En k1210 (avf2328b.raw.Z), una pierna muestra material azul/granular y zonas oscuras en lugar de anatomía visible, mientras las etiquetas Denver conservan regiones musculares y óseas encima. En k2259 (avf1978c.raw.Z), una superficie blanquecina oculta gran parte de una pierna y parte de la otra; también hay etiquetas encima. k1207 (avf2330b.raw.Z) presenta asimismo una extensa alteración superficial. No se determina aquí la causa física.

Las mismas apariencias existen en el gris Denver original. No es evidencia de un fallo del registro RGB. Las correlaciones propias son altas (0.9912 y 0.9925 en los dos ejemplos principales), de modo que NCC, integridad de archivo e identidad resuelta NO protegen de este problema de supervisión.

Acción antes de consumir esos ejemplos como supervisión fiable: registrar en backlog y aplicar exclusión explícita por observabilidad, separada de identidad. Como solución inmediata conservadora, poner en cuarentena los cortes afectados completos; un enmascarado regional posterior puede recuperar tejido observable. Las zonas excluidas son ignore, no background. Inspeccionar las bandas vecinas para delimitar extensión; no inventar su extensión ni usar un simple detector de negro como sustituto. Añadir prueba que asegure que una identidad resuelta no anula la exclusión de calidad. Conservar imágenes, etiquetas, motivo y procedencia; no borrar ni modificar Denver.

Esto condiciona los datos afectados, no bloquea un piloto limpio. No es necesario construir ahora un detector universal de artefactos.

## Resultados favorables y límites

NCC RGB-luminancia contra gris Denver: 0.9781–0.9980 en estas 14 muestras; espejo: 0.0919–0.7253; desplazamiento de 6 píxeles RGB: 0.8782–0.9673. Los controles degradan la concordancia en todos los casos. No se observa un espejo global ni un desajuste grueso de escala en las muestras. Estos números miden reproducción de imágenes del mismo origen, NO exactitud anatómica ni porcentaje de segmentación correcta.

En rodilla k1550 los contornos originales de fémur y rótula siguen las estructuras visibles; en k3000 se aprecia concordancia de contornos musculares seleccionados con la foto. No equivale a comprobar cada etiqueta, nombre o lateralidad de forma independiente.

Los vecinos de k2295 y k2315 también correlacionan alrededor de 0.995. La buena apariencia visual no resuelve por sí sola la identidad exacta de cortes casi iguales: mantener el estado provisional.

k7 y k3532 tienen imagen no negra y ninguna etiqueta original. Ausencia de etiqueta no significa fondo anatómico; conservar ignore fuera de la cobertura de anotación.

No se han revisado las 5.186 imágenes ni medido exactitud de clases nuevas fuera de Denver. Esta es una revisión visual/técnica por muestreo, no una revisión anatómica humana ni una aceptación machine-accepted de la segmentación.

## Evidencias

- panel-1210.png: ejemplo de anatomía no observable con etiquetas encima.
- panel-2259.png: ejemplo de superficie opaca con etiquetas encima.
- panel-1207.png: otra transición afectada.
- panel-1550.png: rodilla con contornos de referencia.
- panel-3000.png: región de tronco con contornos de referencia.
- review-results.json: métricas de todas las muestras.
- review.py: procedimiento ejecutado.
