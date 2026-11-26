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
  ; Egen .ico-fil i installasjonsmappa, og snarveiene peker direkte på den (for docker/launchere som leser snarveiens ikon).
  IfFileExists "$INSTDIR\nexus-ai.ico" +2 0
  CopyFiles /SILENT "$INSTDIR\resources\nexus-ai.ico" "$INSTDIR\nexus-ai.ico"
  IfFileExists "$DESKTOP\NEXUS AI.lnk" 0 +2
  CreateShortCut "$DESKTOP\NEXUS AI.lnk" "$INSTDIR\nexus-ai.exe" "" "$INSTDIR\nexus-ai.ico" 0
  IfFileExists "$SMPROGRAMS\NEXUS AI.lnk" 0 +2
  CreateShortCut "$SMPROGRAMS\NEXUS AI.lnk" "$INSTDIR\nexus-ai.exe" "" "$INSTDIR\nexus-ai.ico" 0
  IfFileExists "$SMPROGRAMS\NEXUS AI\NEXUS AI.lnk" 0 +2
  CreateShortCut "$SMPROGRAMS\NEXUS AI\NEXUS AI.lnk" "$INSTDIR\nexus-ai.exe" "" "$INSTDIR\nexus-ai.ico" 0
  FileOpen $1 "$TEMP\nexus-installer-hook.log" a
  FileSeek $1 0 END
  FileWrite $1 "POSTINSTALL: snarveier peker til $INSTDIR\nexus-ai.ico (finnes: $\"$INSTDIR\nexus-ai.ico$\")$\r$\n"
  FileClose $1
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
