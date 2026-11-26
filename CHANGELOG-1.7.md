# 1.7.0
- Assistant: legg ved bilder (opptil 3, PNG/JPEG/WebP/GIF) og spør om dem. Virker med lokale synsmodeller i Ollama (f.eks. moondream, 1,7 GB). Bildene krympes til maks 1280 px, sendes bare lokalt, og lagres ikke. Ikke-synsmodeller og skymodeller gir en tydelig melding i stedet for å sende bildet.
- Kontrastfiks: feilmelding for nedlasting i Bygg team.
- 146 tester, kontrast 0 feil i alle 4 temaer.
- Ikke testet med ekte synsmodell (utviklingsmaskinen har for lite minne). Selve Ollama-kallet er testet mot dokumentert format og mock.
