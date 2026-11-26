; Avslutter kjørende NEXUS-prosesser før filer skrives, så installasjon og oppdatering ikke feiler på låste filer.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /T /IM nexus-backend.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM nexus-ai.exe'
  Pop $0
  Sleep 1500
!macroend

!macro NSIS_HOOK_POSTINSTALL
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /T /IM nexus-backend.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM nexus-ai.exe'
  Pop $0
  Sleep 1000
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
!macroend
