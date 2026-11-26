; Avslutter kjørende NEXUS-prosesser før filer skrives, så installasjon og oppdatering ikke feiler på låste filer.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /T /IM nexus-backend.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM nexus-ai.exe'
  Pop $0
  Sleep 1500
  FileOpen $1 "$TEMP\nexus-installer-hook.log" a
  FileSeek $1 0 END
  FileWrite $1 "PREINSTALL: avsluttet nexus-prosesser$\r$\n"
  FileClose $1
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Tøm Windows sin ikon-cache og si fra til Utforsker (SHCNE_ASSOCCHANGED), så oppgavelinje og snarveier får det nye ikonet.
  nsExec::Exec '"$SYSDIR\ie4uinit.exe" -ClearIconCache'
  Pop $0
  nsExec::Exec '"$SYSDIR\ie4uinit.exe" -show'
  Pop $0
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
  FileOpen $1 "$TEMP\nexus-installer-hook.log" a
  FileSeek $1 0 END
  FileWrite $1 "POSTINSTALL: ikon-cache oppdatert$\r$\n"
  FileClose $1
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
