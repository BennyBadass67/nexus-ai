# 2.5.0 - Provenedtelling

Legg inn prover og eksamener, og se hvor mange dager det er igjen, rett pa Hjem-siden.

## Nytt
- Nytt kort "Provenedtelling" pa Hjem: neste prove i stort (f.eks. "9 dager til Matte"), liste over kommende prover, og gamle prover vises tonet ned.
- Legg til prove med fag og dato. Duplikater (samme fag og dato) avvises med tydelig melding.
- Fjern prover med soppelbotte-knappen. Alt lagres lokalt i databasen.

## Teknisk
- Nye endepunkter: GET/POST /api/school/exams, DELETE /api/school/exams/{id}. Server regner ut dager igjen (kan overstyres med ?date= for tester).
- 2 nye backend-tester (160 totalt). Nettlesertest: legge til, duplikatfeil, slette og at dataene overlever omstart.
