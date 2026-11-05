# Deployment guide

## Which platform? (recommendation for the CU Transport Department)

**1st choice: the transport office's own Windows PC (no hosting needed).**
Cards use **offline QR codes** by default, which any phone reads with no internet and no server.
So the app only needs to run where passes are made. It's free and needs no account, and student data
(addresses, phone numbers) never leaves the university. Use `python serve.py` (Option A below),
start it automatically with Task Scheduler, and back up daily.

**2nd choice: the university's own server (ask CU IT).** Best if several offices need access, or for
online QR codes. Student data stays on university infrastructure, which is the safest option under
India's DPDP Act. Follow Option C1 on their Linux server.

**If you need a cloud host: PythonAnywhere** (pythonanywhere.com, paid "Developer" plan, about US$5–10/month).
It runs Flask apps directly, keeps the SQLite database and photo uploads on a **persistent disk**,
includes HTTPS, and needs no server administration. See *Option D* below.
A VPS in an Indian region (AWS Lightsail Mumbai, DigitalOcean Bangalore) is the alternative if you
want full control (Option C1).

**Netlify:** use the separate Netlify + Supabase version in `netlify-site/` (see `netlify-site/SETUP.md`). This Flask app itself can't run on Netlify.

**Avoid** running *this Flask app* on Render/Railway/Heroku free tiers or Vercel/Netlify: their disks are wiped on redeploy,
so the database and student photos would be lost.

> **Online = login on.** Before the app is reachable from any other computer, set `REQUIRE_LOGIN=1`
> and create an account (`flask --app run create-admin`). In no-login mode the app refuses
> every connection that doesn't come from its own PC.

---

The app runs the same way everywhere: `python serve.py` (Waitress) reads its settings from `.env`.
Choose the option below that matches where it will run.

| Option | Who can reach it | Online QR works on phones? | Camera scanner? |
|---|---|---|---|
| A. This PC only | Only this computer | No (phones can't reach it) | Yes (on `localhost`) |
| B. Campus LAN | Devices on the same network | Yes, on that network | Only with HTTPS (see B2) |
| C. Internet (VPS or PaaS) | Anyone with the link | Yes | Yes |

Offline QR codes work in every option, because they never need a network to be read.

---

## Required settings (all options)

Create `.env` from `.env.example` and set at least:

```ini
SECRET_KEY=<64 random hex chars>
QR_SIGNING_KEY=<a different 64 random hex chars>
PUBLIC_BASE_URL=<the address phones will open, e.g. https://pass.example.edu>
UNIVERSITY_NAME=...
UNIVERSITY_SHORT=...
```

Generate each key with `python -c "import secrets; print(secrets.token_hex(32))"`.
`serve.py` refuses to start until both keys are set.

> **Decide `PUBLIC_BASE_URL` before printing cards.** It is printed inside every online QR code.
> If it changes later, reissue the passes (the old QR codes would point to the old address).
> Keep `QR_SIGNING_KEY` the same for the life of the cards. Changing it makes every offline QR code fail the check.

Then create an admin: `flask --app run create-admin`.

---

## A. This PC only (Windows)

```powershell
.\venv\Scripts\Activate.ps1
python serve.py
```

Open http://127.0.0.1:8000. To start it automatically at login, create a Task Scheduler task with
action `C:\path\to\venv\Scripts\python.exe`, argument `serve.py` and "Start in" set to the project folder.

## B. Campus LAN (Windows PC as server)

1. In `.env`: `HOST=0.0.0.0`, `PORT=8000`, and `PUBLIC_BASE_URL=http://<this PC's IP>:8000`.
   Find the IP with `ipconfig` (IPv4 Address), and ask IT to give the PC a fixed (reserved) IP.
2. Allow the port through Windows Firewall (run PowerShell **as Administrator**):
   ```powershell
   New-NetFirewallRule -DisplayName "University Pass Generator" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Domain
   ```
3. `python serve.py`. Phones on the same Wi-Fi can now open online QR links.

**B2. Camera scanner on other devices:** browsers allow the camera only on HTTPS. Put **Caddy** in front
(it can issue a certificate from its own internal CA for LAN names):
```
pass.campus.local {
    tls internal
    reverse_proxy 127.0.0.1:8000
}
```
Set `TRUST_PROXY=1`, `SESSION_COOKIE_SECURE=1`, `PUBLIC_BASE_URL=https://pass.campus.local`, and install Caddy's
root certificate on the scanning devices. If that is too much, guards can scan with the phone's normal camera
app (online QR), or admins can paste text at **Check QR Text**.

## C. Internet

Always use HTTPS. Admin logins and student data must never travel over plain HTTP.

### C1. Linux VPS (recommended for control and cost)

```bash
sudo apt install python3-venv caddy
sudo useradd -r -m -d /srv/pass passapp
sudo -u passapp git clone <your repo> /srv/pass/app     # or copy the files
cd /srv/pass/app && sudo -u passapp python3 -m venv venv
sudo -u passapp venv/bin/pip install -r requirements.txt
sudo -u passapp cp .env.example .env && sudo -u passapp nano .env
#   HOST=127.0.0.1  PORT=8000  TRUST_PROXY=1  SESSION_COOKIE_SECURE=1
#   PUBLIC_BASE_URL=https://pass.example.edu
sudo -u passapp chmod 600 .env
sudo -u passapp venv/bin/flask --app run create-admin
```

`/etc/systemd/system/pass.service`:
```ini
[Unit]
Description=University Pass Generator
After=network.target

[Service]
User=passapp
WorkingDirectory=/srv/pass/app
ExecStart=/srv/pass/app/venv/bin/python serve.py
Restart=always
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`/etc/caddy/Caddyfile` (Caddy gets and renews the Let's Encrypt certificate automatically):
```
pass.example.edu {
    reverse_proxy 127.0.0.1:8000
    request_body max_size 6MB
}
```

```bash
sudo systemctl enable --now pass caddy
```
Point the domain's DNS A record at the server first. Open only ports 80 and 443 (`ufw allow 80,443/tcp`).

### C2. PaaS (Render, Railway, PythonAnywhere…)

- Start command: `python serve.py` with `HOST=0.0.0.0` and `PORT` set to the platform's port. Set `TRUST_PROXY=1` and `SESSION_COOKIE_SECURE=1`.
- Put the secrets in the platform's **environment variables** screen, not in files.
- **SQLite and photos need a persistent disk.** Point `DATABASE_PATH` and `UPLOAD_FOLDER` to the mounted
  disk path. Without one, data is lost on every redeploy.
- Run one instance only (SQLite and the login throttle are single-server).

---

## D. PythonAnywhere (step by step)

1. Create an account and choose a paid plan (Developer). Open a **Bash console**:
   ```bash
   git clone <your repo> ~/buspass      # or upload the project folder via the Files tab (skip venv/)
   cd ~/buspass && python3.12 -m venv venv && venv/bin/pip install -r requirements.txt
   cp .env.example .env && nano .env      # set SECRET_KEY, QR_SIGNING_KEY (copy the SAME QR key as the office PC
                                          # if cards were already printed), REQUIRE_LOGIN=1, SESSION_COOKIE_SECURE=1,
                                          # TRUST_PROXY=1, PUBLIC_BASE_URL=https://<you>.pythonanywhere.com,
                                          # UNIVERSITY_NAME=Chandigarh University, UNIVERSITY_SHORT=CU, PASS_PREFIX=CU
   venv/bin/flask --app run create-admin
   ```
2. **Web** tab → *Add a new web app* → *Manual configuration* → Python 3.12.
   - *Virtualenv*: `/home/<you>/buspass/venv`
   - *WSGI configuration file*: replace its contents with
     ```python
     import sys; sys.path.insert(0, "/home/<you>/buspass")
     from run import app as application
     ```
   - *Static files*: URL `/static/` → directory `/home/<you>/buspass/app/static`
   - Turn on **Force HTTPS**, then **Reload**.
3. To move existing data from the office PC, upload `instance/university_pass.db` and the `uploads/` folder
   (or a `flask --app run backup` zip) into the same paths, then Reload.
4. Schedule the daily backup on the **Tasks** tab: `cd ~/buspass && venv/bin/flask --app run backup`.

## Backups

```powershell
flask --app run backup              # → backups\backup-YYYYMMDD-HHMMSS.zip
```
The zip holds a consistent snapshot of the database plus all photos, and it is safe to run while the app is up.
Schedule it daily (Task Scheduler, or `cron` on Linux), copy the zips **off the server**, and protect them,
because they contain student data. To restore, stop the app, put `university_pass.db` back at `DATABASE_PATH`
and `uploads/` back at `UPLOAD_FOLDER`, then start the app.

## Production checklist

- [ ] `SECRET_KEY` and `QR_SIGNING_KEY` set, different from each other, and not committed anywhere
- [ ] `PUBLIC_BASE_URL` is final and uses HTTPS (Option C)
- [ ] `SESSION_COOKIE_SECURE=1` and `TRUST_PROXY=1` behind a proxy
- [ ] `FLASK_DEBUG=0`. Never use `run.py` in production; use `serve.py`
- [ ] Admin accounts use strong, unique passwords
- [ ] `.env` readable only by the service user
- [ ] Daily off-server backups, with a restore you have tested once
- [ ] Official university logo and name set (replace the placeholder branding)
