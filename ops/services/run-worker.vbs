' Launch the Talk_To_Ex fine-tune worker HIDDEN, as the logged-in user (so it has
' the SSH keys for WAVE + atlas). A copy of this lives in the user's Startup folder
' so the worker comes up at every logon; running it directly starts it now.
Dim sh, cmd
Set sh = CreateObject("WScript.Shell")
cmd = "cmd /c " & Chr(34) & "B:\Coding\Talk To Ex\ops\services\run-worker.cmd" & Chr(34)
sh.Run cmd, 0, False   ' 0 = hidden window, False = don't wait
