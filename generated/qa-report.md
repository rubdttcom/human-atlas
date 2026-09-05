# Geometry QA

| Atlas | Meshes | Open boundaries | Nonmanifold edges | Degenerate triangles | Self-intersecting meshes | Meshes with outlier components |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bodyparts3d | 2234 | 2059 | 43 | 10 | 2060 of 2234 | 59 |
| composed | 1015 | 402 | 80 | 84 | 175 of 1015 | 5 |
| denver-vhf | 128 | 0 | 3 | 0 | 1 of 128 | 0 |
| hra-female | 888 | 449 | 43 | 0 | 89 of 888 | 4 |
| nlm-vhf-ct | 114 | 0 | 41 | 95 | 101 of 114 | 1 |
| tcia | 36 | 0 | 9 | 35 | 36 of 36 | 16 |

Issue columns count meshes affected. Individual values are in `qa-report.json` and `anatomy-qa.json` (self-intersecting triangle pairs by edge-triangle tests,
connected components farther than 60.0 mm from the main component). Open boundaries can be intentional for anatomical surfaces.
Composite continuity (bounding boxes, canonical stage): HRA head bottom minus CT vertebral column top -3.7 mm; HRA brain inside CT skull box: True; CT vertebral column bottom minus Denver sacrum top -39.1 mm. Bounding-box gaps only. A negative head-bottom minus spine-top value means the HRA head structures overlap the top of the CT spine vertically; it does not establish cervical continuity, which needs anatomical review.
Anatomical review remains pending for every mesh (registry/review-status.json).
