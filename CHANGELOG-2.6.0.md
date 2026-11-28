# 2.6.0 - Fokus-logg

Fokus-timeren husker na oktene dine.

## Nytt
- Hver fullforte fokusokt (25 min) logges lokalt i databasen.
- Fokus-kortet pa Hjem viser minutter fokusert i dag, minutter denne uken, og dagrekken din (dager pa rad med minst en okt).
- Tallene overlever omstart av appen - de lagres ikke lenger bare i dagens minne.

## Teknisk
- Nye endepunkter: POST /api/school/focus og GET /api/school/focus/stats.
- 1 ny backend-test (161 totalt). Nettlesertest: en fullfort okt logges, vises og overlever omstart.
