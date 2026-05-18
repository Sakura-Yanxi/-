Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "C:\Users\Sakura\Desktop\demo"
shell.Run Chr(34) & "C:\Users\Sakura\Desktop\demo\run_server.bat" & Chr(34), 0, False
