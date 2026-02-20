Set objShell = CreateObject("Wscript.Shell")
objShell.Run Chr(34) & "C:\Users\user\miniforge3\pythonw.exe" & Chr(34) & " " & Chr(34) & "C:\DEV\cbt\main.py" & Chr(34), 0, False
Set objShell = Nothing
