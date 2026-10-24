# repent.wtf is fork of [cheddlatron selfbot](https://github.com/Cheddlar/Cheddlatron-Source)

# Honorable mention
[Keira](https://github.com/KeiraOMG0): sponsoring claude code,cdn server and make this project doable\
[Grabify](https://github.com/Gr4bify/): retired developer of cheddlatron & helped me fix the bot\
[Cheddlar](https://github.com/Cheddlar): retired developer of cheddlatron\
Wraith: retired developer of cheddlatron

> **Disclaimer:** Selfbots (automating a normal user account instead of a proper bot account) violate [Discord's Terms of Service](https://discord.com/terms) and can get the account banned. This project is provided for educational purposes. Use it on an account you're willing to lose, and never on your primary account.

## Features

- **500+ commands** across `account`, `utility`, `fun`, `meme`, `moderation`, `ai`, `hacking`, `codeblock`, `raid`, `dumping`, `spotify`, and `music`
- **YouTube music playback** - `mplay`, `mskip`, `mstop`, `mqueue`, `mnowplaying`, `mloop`, `mautoplay`, `mvolume` stream real audio into a voice channel via [ytqueue](https://github.com/KeiraOMG0/ytqueue), with automatic cookie refresh via the [musicbot-cookie-sync](https://github.com/KeiraOMG0/musicbot-cookie-sync) Chrome extension
- **Music whitelist** - run repent on an alt and let your main (or friends) use the music commands, see [Music on an alt](#music-on-an-alt)
- **Dashboard** - opens in your browser at `http://localhost:7320`:
  - **Overview** - profile, session stats (uptime, latency, commands loaded), now playing, quick toggles and the latest console lines on one screen
  - **Console** - the full live console
  - **Rich Presence** - standard, console and Spotify presences with a live preview; changes apply instantly, no restart needed
  - **Commands** - searchable list of every command
  - **Settings** - general, embed editor, snipers, loggers, webhooks and music
- **Keyboard shortcuts** - `1`-`4` switch pages, `,` opens settings, `Ctrl+K` searches commands
- **First-run setup** - a step-by-step setup page that checks your token and webhooks before saving anything
- **Customization** - customize every thing you want with repent
- **Custom badges** - extra stuff i added because i have a lot of free time
- **Safe** - its an open sourced project ofc its gonna be safe

## Getting started

1. Install Python 3.10+ and run `pip install -r req.txt`
2. Run `python repent.py`
3. The first time, a setup page opens in your browser. Paste your token and go through the steps; everything except the token can be skipped and changed later in **Settings**
4. When setup finishes, the dashboard opens at `http://localhost:7320` and shows each startup step while it connects

When an update adds new settings, setup opens once more on the next start and only asks for the new ones.

## Remote dashboard and setup (VPS / Tailscale)

By default both the setup page and the dashboard listen on `127.0.0.1:7320`, so only the machine running repent can reach them. To use them from another machine or over Tailscale, bind to all interfaces:

```bash
# Linux / macOS
REPENT_REMOTE=1 python repent.py

# Windows (PowerShell)
$env:REPENT_REMOTE=1; python repent.py
```

Then open `http://<tailscale-ip>:7320` (or any other IP the machine prints at startup). The same port serves first-run setup, so you can complete setup from your laptop and the page takes you to the dashboard when it is done.

You can also set the details explicitly:

| Variable | Default | Purpose |
| --- | --- | --- |
| `REPENT_HOST` | `127.0.0.1` | Interface to bind (`0.0.0.0` for all interfaces) |
| `REPENT_PORT` | `7320` | Port for setup and the dashboard |
| `REPENT_REMOTE` | off | Same as `REPENT_HOST=0.0.0.0` |
| `REPENT_PASSWORD` | off | Enables HTTP Basic auth (user `repent`, your password) |
| `REPENT_ALLOWED_HOSTS` | empty | Extra comma-separated hostnames allowed in the `Host` header (e.g. a reverse proxy) |
| `REPENT_NO_BROWSER` | off | Never try to open a browser (useful on a headless VPS) |

Access by raw IP, `localhost`, the machine's hostname and Tailscale MagicDNS names (`.ts.net`) is allowed automatically. Other hostnames (like a domain in front of a reverse proxy) must be listed in `REPENT_ALLOWED_HOSTS`.

> **Keep it private.** The dashboard can control your account and displays your token. A `REPENT_PASSWORD` is strongly recommended, keep the port off the public internet (tailnet-only or behind a reverse proxy with auth), and use Tailscale ACLs to limit who can reach it.

## Requirements

- Python 3.10+ (tested on 3.11)
- Windows, macOS, or Linux (some conveniences — console font/codepage handling, `chcp`-equivalent fixes — are Windows-specific)
- A Discord account token
- [ffmpeg](https://ffmpeg.org/download.html) on your `PATH` (only needed for music playback)

## Music setup

Music commands (`mplay`, `mskip`, `mstop`, `mqueue`, `mnowplaying`, `mloop`, `mautoplay`, `mvolume`) need a couple of one-time setup steps:

1. Install [ffmpeg](https://ffmpeg.org/download.html) and make sure it's on your system `PATH`.
2. `pip install -r req.txt` (this pulls in `ytqueue` and `PyNaCl`, both required for voice audio).
3. (Optional, recommended) Load the cookie-sync Chrome extension so age/sign-in-gated YouTube videos keep working without manually re-exporting cookies:
   - Open `chrome://extensions`, enable **Developer mode**
   - Click **Load unpacked** and select `extras/musicbot-cookie-sync/extension/`
   - In the extension's options, set **Server origin** to `http://127.0.0.1:8999` and **Cookie domain** to `youtube.com`
   - Leave Chrome open (any window in the same profile keeps the poll loop alive)

Default volume and autoplay can be set under **Settings → Music**.

## Music on your PC's speakers

You don't need a voice call to listen. Run `<prefix>moutput speakers` (or turn on **Play On This PC** under **Settings → Music**) and `mplay` plays straight to this computer's speakers. All the other music commands work the same way.

- `<prefix>mdevice` lists your outputs. `<prefix>mdevice <number>` (or part of a name, e.g. `mdevice headphones`) picks one, and `mdevice default` follows the Windows default
- `<prefix>moutput vc` switches back to voice channels

## Music on an alt

Discord only allows one voice connection per account, so repent can't play music to you on the same account you're listening with. To use it as a music bot:

1. Run repent on an alt account
2. In the alt's dashboard, open **Settings → Music** and add your main account's user ID to the **Music Whitelist** (comma separated for more than one)
3. Join a voice channel on your main and type `<prefix>mplay <song or url>` in a server the alt is in

The alt joins your voice channel and plays. Whitelisted users can only use the music commands (`mplay`, `mskip`, `mstop`, `mqueue`, `mnowplaying`, `mloop`, `mautoplay`, `mvolume`), nothing else on the alt.

## Previews
> sample account, not real data

> overview
<img width="1366" height="768" alt="Overview page with profile, session stats, now playing, quick toggles and console" src="docs/previews/overview.png" />

> loading screen
<img width="1366" height="768" alt="Loading screen showing each startup step with timings" src="docs/previews/loading.png" />

> rich presence
<img width="1366" height="768" alt="Rich Presence editor with live preview" src="docs/previews/rich-presence.png" />

> console
<img width="1366" height="768" alt="Live console page" src="docs/previews/console.png" />

> commands
<img width="1366" height="768" alt="Searchable command list" src="docs/previews/commands.png" />

> settings
<img width="1366" height="768" alt="Settings page, general tab" src="docs/previews/settings.png" />

> first-run setup
<img width="1366" height="768" alt="First-run setup, token step" src="docs/previews/setup.png" />

