# 2.7.0 - Hurtigkort og ukemaal for fokus

## Hurtigkort
- Har du fasiten klar? Lim inn ferdige par i Studie, ett per linje: «hovedstaden i Norge = Oslo».
- Virker med =, -, | og ; som skille. Tomme linjer og kommentarer (#) hoppes over.
- Stokken lages med en gang - helt uten modell, sa det virker selv om Ollama er av.
- Kan ogsaa fylle paa en stokk du har fra foer.

## Ukemaal for fokus
- Sett et ukemaal i Fokus-kortet pa Hjem: 2, 5 eller 10 timer (eller av).
- En fremdriftslinje viser hvor langt du har kommet siste 7 dager, i minutter og prosent.

## Teknisk
- Nytt endepunkt POST /api/study/decks/quick med ren parseloggikk (parse_pairs).
- Ny innstilling focus_goal (av/120/300/600) via /api/settings.
- 4 nye backend-tester (164 totalt). Nettlesertest: hurtigkort lager stokk og kort, ukemaal settes, lagres og vises.
