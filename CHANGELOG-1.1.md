# NEXUS AI 1.1: skole og smartere chat

- Studie: lim inn pensum og få øvingskort (spørsmål og svar) laget av den lokale modellen. Repetisjon med SM-2 (Igjen, Vanskelig, Bra, Lett), fremdrift og "å øve på i dag" på Home.
- Skriveverktøy: oppsummer, punkter, rett feil, forenkle, formell tone, til engelsk/norsk, forklar, lag spørsmål. Strømmer svaret.
- Spør dokumentene dine (Workspace, Kunnskap): svar kun fra egne filer, med kildehenvisning. Finner den ingenting, sier den det uten å gjette.
- Smart chat: samtaler får automatisk kort tittel, og en lyspære-knapp foreslår oppfølgingsspørsmål.
- Bevegelse: trinnvis inngang for kort og lister, hover-løft, trykk-respons, nav-ikoner som reagerer, myk fokusring, innglidende chat-bobler, pustende online-prikk.
- Feil funnet i test med ekte modell: qwen2.5:1.5b kopierte setninger som både spørsmål og svar. Filter og bedre prompt, pluss ett ekstra forsøk. Ollama som ikke svarer ga 500, gir nå en tydelig melding.
- Testet: 120 backend-tester, nettleser-QA uten feil, kontrast 0 feil.
- Utestet: ekte Windows, 3B-modell. Kvaliteten på kort og titler avhenger av modellen.
