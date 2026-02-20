Dim objShell
Set objShell = CreateObject("Wscript.Shell")
objShell.CurrentDirectory = "C:\DEV\cbt"
objShell.Run """C:\Users\user\miniforge3\pythonw.exe"" ""C:\DEV\cbt\main.py""", 0, False
Set objShell = Nothing
