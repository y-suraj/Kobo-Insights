Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c launch_analytics.bat", 0, False
Set WshShell = Nothing