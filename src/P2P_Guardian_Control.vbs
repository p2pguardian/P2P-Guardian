Option Explicit
Dim shell, scriptPath
Set shell = CreateObject("WScript.Shell")
scriptPath = Replace(WScript.ScriptFullName, "P2P_Guardian_Control.vbs", "P2P_Guardian_Control.ps1")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptPath & """", 0, False
Set shell = Nothing
