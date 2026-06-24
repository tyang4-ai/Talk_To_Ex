# Cloudflare Tunnel as a Windows service

Goal: a persistent named tunnel so `https://ex.yang9ru.online` reaches the local
FastAPI app (`localhost:8080`) and Twilio's inbound SMS webhook works even after
reboots — without leaving a terminal open.

> **Never expose Ollama.** The tunnel only routes to `localhost:8080`. The local
> model on `127.0.0.1:11434` stays private. Do not add an ingress rule for it,
> and do not run a second tunnel that points at it.

There are two equivalent ways to run cloudflared as a service. **Pick one.**

---

## Install cloudflared

```powershell
winget install --id Cloudflare.cloudflared
cloudflared --version
```

---

## Option A — token-based service (simplest; managed in the Cloudflare dashboard)

Use this if you created the tunnel in the **Zero Trust dashboard**
(Networks -> Tunnels) and have its connector **token**. The dashboard holds the
ingress config (point `ex.yang9ru.online` -> `http://localhost:8080` there).

```powershell
# Installs cloudflared as an auto-start Windows service bound to this tunnel.
cloudflared service install <YOUR_TUNNEL_TOKEN>
```

`<YOUR_TUNNEL_TOKEN>` is the long string the dashboard shows under "Install and run
a connector". It's the same value as `CLOUDFLARE_TUNNEL_TOKEN` in `backend/.env` —
keep it secret.

Manage it:

```powershell
Get-Service cloudflared
Restart-Service cloudflared
Get-Content "$env:USERPROFILE\.cloudflared\*.log" -Tail 50   # if it logs to file
```

With the token path, ingress lives in the dashboard, so `config.example.yml` is
only a reference. (You can still keep a local `config.yml`; the token config wins.)

---

## Option B — config-file service (ingress lives in `config.yml`, in this repo)

Use this if you created the tunnel from the CLI and want the ingress rules version-
controlled alongside the code (`ops/cloudflared/config.example.yml`).

```powershell
cloudflared tunnel login
cloudflared tunnel create talk-to-ex
cloudflared tunnel route dns talk-to-ex ex.yang9ru.online
```

Copy the example config and fill in your UUID + credentials path:

```powershell
Copy-Item ops\cloudflared\config.example.yml ops\cloudflared\config.yml
notepad ops\cloudflared\config.yml
```

cloudflared's `service install` looks for the config at the default OS path. The
cleanest approach is to put the finished config there, then install:

```powershell
# Default config location cloudflared reads on Windows:
#   C:\Windows\System32\config\systemprofile\.cloudflared\config.yml   (LocalSystem)
#   or %USERPROFILE%\.cloudflared\config.yml
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cloudflared" | Out-Null
Copy-Item ops\cloudflared\config.yml "$env:USERPROFILE\.cloudflared\config.yml"

cloudflared service install
Start-Service cloudflared
```

Quick foreground test before installing the service:

```powershell
cloudflared tunnel --config ops\cloudflared\config.yml run
```

---

## Verify end-to-end

1. Start the backend (`uvicorn app.main:app --port 8080` from `backend/`).
2. Start / restart the cloudflared service.
3. From any network, hit the public health route:

   ```powershell
   curl https://ex.yang9ru.online/api/health    # -> {"ok":true}
   ```

4. Point the Twilio number's **A MESSAGE COMES IN** webhook at
   `https://ex.yang9ru.online/sms` (POST). An inbound text should reach the app.

If `/api/health` works locally but not through the domain, check: the service is
running (`Get-Service cloudflared`), the DNS route exists
(`cloudflared tunnel route dns ...`), and the ingress hostname exactly matches
`ex.yang9ru.online`.

## Uninstall / reinstall

```powershell
Stop-Service cloudflared
cloudflared service uninstall
# then re-run the install for the option you want
```
