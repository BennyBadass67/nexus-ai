# NEXUS AI 1.2: sky-KI (gratis) og modellduell

- Sky-KI (Settings > Sky-KI), AV som standard. Leverandører: Cloudflare Workers AI (anbefalt, gratis 10 000 neuroner/dag), OpenRouter (bare :free-modeller), Groq, Google AI Studio (Gemini), og egendefinert OpenAI-kompatibel URL.
- Skymodeller vises i modellvelgeren under "Sky (sendes ut av PC-en)" og virker i chat, agenter og team-chat, også verktøykall.
- Regler bygget inn: bare gratisnivå, ingen betaling, ingen omgåelse av kvoter (429 og 402 stopper med tydelig melding, ett forsøk, ingen retry). OpenRouter-modeller uten :free nektes. Nøkkelen lagres bare lokalt, vises aldri igjen i UI, kan slettes. Du må krysse av for samtykke før noe sendes ut. Tydelig advarsel i chatten når en skymodell er valgt.
- Ærlig: ingen seriøs leverandør fungerer helt uten konto og nøkkel. Nøkkelen er gratis. Cloudflare trenger Account ID og et API-token med Workers AI-tilgang.
- Modellduell (Studie): samme spørsmål til to modeller etter hverandre, med tid og tempo.
- Fikset: kontrast på "på"-merker (hvit tekst på grønn ble gjort mørk av glass-temaet).
- Testet: 134 backend-tester (mot falsk OpenAI-kompatibel server: strømming, verktøykall, JSON-modus, 401/402/429, samtykke, nøkkel aldri i svar, URL-regler), nettleser-QA uten feil, kontrast 0 feil i alle 4 temaer.
- Utestet: ekte kall mot Cloudflare, OpenRouter, Groq og Google (ingen nøkler brukt, ingen kontakt med tredjeparter). Modellnavn og grenser kan endre seg hos leverandørene; modellisten hentes live der det er mulig.
