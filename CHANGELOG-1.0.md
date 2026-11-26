# NEXUS AI 1.0

## Nytt
- Søk overalt (Ctrl+K): samtaler, minner, agenter, notater, team-chat, aktivitet
- Notater og oppgaver (agentene kan legge til og lese dem)
- Maler: lagrede startprompter, satt inn fra Assistent
- Eksporter samtale som Markdown
- Sikkerhetskopi og gjenoppretting (med sikkerhetskopi av dagens data først)
- Systemmonitor på Home (CPU, minne, hvilke modeller som er lastet)
- Kunnskapsbase: indekser mappene dine og søk i dem; agentene bruker search_knowledge
- Legg ved tekstfiler i chat
- Skjermkontroll (0.9.0) og ny oppdateringsflyt (0.9.2)

## Feil funnet og fikset
- Prompt kunne bli større enn 4096 kontekst, og Ollama kuttet i starten (systemprompten kunne forsvinne). Nå trimmes den.
- SQLite manglet WAL og hadde 5 s ventetid. Nå WAL og 15 s.
- Team-chat: leder kunne avslutte før første svar. Fikset.
- Team-chat: agenter svarte om rollen sin i stedet for spørsmålet ditt. Fikset.
- Oppdateringsknappen later bare som den virker. Fikset i 0.8.1.
- 644 kontrastfeil i 4 temaer, nå 0 (sjekket på 2432 tekstelementer).

## Testet
- 106 backend-tester, API-fuzzing uten 5xx, nettleser-QA uten konsollfeil og uten sideveis scroll, kontrastsjekk 0 feil i alle 4 temaer.

## Ikke testet på ekte Windows
- Skjermkontroll (Win32), installer-hooks, oppstart via ShellExecute, ekte 3B-modell.
