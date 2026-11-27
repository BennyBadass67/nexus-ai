# NEXUS AI 2.4.1

Oppdateringsfunksjonen fikset (funnet ved gjennomgang av koden, ikke reprodusert på Windows):

- Installeren startes nå frikoblet fra appen (via WMI). Før var den et barn av NEXUS, og installerens egen "taskkill /T" mot NEXUS kunne drepe selve installeren midt i, så appen lukket seg uten at noe ble installert.
- Installer-skriptet dreper nexus-ai.exe og nexus-backend.exe på navn, uten å ta hele prosesstreet.
- Etter "Installer": appen sjekker at ny versjon faktisk svarer. Hvis gammel versjon fortsatt kjører etter 90 sek, vises en feilmelding med filen du kan kjøre selv, i stedet for en evig "Starter på nytt".
- Feil under automatisk nedlasting i bakgrunnen vises nå (de var stille før), med "Prøv igjen".
- Ny versjon som kommer mens en eldre ligger klar lastes nå ned.

Viktig: selve oppdateringen TIL 2.4.1 bruker fortsatt gammel flyt. Fiksen virker fra og med oppdateringer FRA 2.4.1. Kjør gjerne 2.4.1-filen manuelt én gang.
