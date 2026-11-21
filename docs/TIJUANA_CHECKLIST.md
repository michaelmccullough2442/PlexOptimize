# Tijuana remote-access checklist

Home PC Tailscale IP: **100.102.16.5**. Plex `:32400`, Moonlight/Sunshine `:47989`, ROM share
`\\100.102.16.5\Emulators`. The thesis drive (`E:\MAIN`) is never part of any of this.

## Before you leave (at home, ~30 min)

These matter more than anything else: once you're away, nobody can press a button on the PC.

- [ ] **Tailscale runs without you logged in.** Tailscale tray icon > Preferences > *Run unattended*.
      Otherwise a Windows sign-out cuts you off.
- [ ] **Turn off key expiry for the home PC.** login.tailscale.com > Machines > home PC > ... >
      *Disable key expiry*. Otherwise it drops off the tailnet when its key expires.
- [ ] **The PC never sleeps.** `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0`.
- [ ] **Windows Update can't reboot it.** Settings > Windows Update > *Pause updates* (up to 5 weeks).
      Plex starts only after you sign in to Windows, so a surprise reboot takes Plex down.
- [ ] **It comes back after a power cut.** Optional but worth it: BIOS setting *Restore on AC power
      loss = Power On*, plus Windows auto sign-in (`netplwiz`) so Plex and Sunshine start on their own.
- [ ] **Leave the monitor on (or plug in a dummy HDMI plug).** With no active display, Sunshine has
      nothing to capture and Moonlight shows a black screen.
- [ ] **Pair Moonlight at home.** Pairing is one-time and is easiest with the PC in front of you.
- [ ] Run `scripts\windows\Test-RemoteReadiness.ps1` on the PC and `-FromLaptop` on the laptop.
      All green = ready.
- [ ] Download a couple of movies to the laptop in Plex at home, in case the hotel Wi-Fi is bad.

## 1. "I can't reach anything" (Tailscale)

1. On the laptop: Tailscale icon shows **Connected**? If not, sign in again with the same account.
2. Hotel/hospital Wi-Fi often has a sign-in page. Open any website first (e.g. `http://neverssl.com`),
   accept the terms, then reconnect Tailscale.
3. PowerShell: `tailscale ping 100.102.16.5`
   - `pong ... via DERP(lax)` or similar: it works, but relayed (see section 2).
   - `pong ... via <ip>:<port>`: direct, best case.
   - no pong: the home PC is off, asleep, signed out of Tailscale, or its key expired. Check
     login.tailscale.com > Machines: the home PC's "Last seen". If it's offline, someone at home
     has to wake or restart it.
4. Still stuck: switch the laptop to your phone's hotspot. A different network often fixes it.

## 2. Slow or choppy (double NAT and Tailscale DERP)

Your home internet is behind two routers (ISP box + your router), so Tailscale usually can't make
a direct connection and relays traffic through its DERP servers (the nearest is Los Angeles, close
to Tijuana). That works anywhere but gives roughly **5-10 Mbps**.

- Run `tailscale netcheck` on the laptop. `MappingVariesByDestIP: true` means the network you're
  on has strict NAT too; a direct path is unlikely, so stick with the low settings below.
- Settings that fit a relayed connection:
  - **Plex:** while playing, Settings (gear) > Quality > **720p 2-4 Mbps**. Plex transcodes on the PC.
  - **Moonlight:** 1280x720, 30 FPS, 3-4 Mbps. Turn on *Optimize game settings*.
- **Getting a direct connection (needs someone at home, or do it before you leave):**
  - Best fix: put the ISP box in **bridge mode** (or "IP passthrough"), so only your router does NAT.
  - Or forward **UDP 41641** to the home PC on both routers (ISP box -> your router -> PC).
  - If the ISP box's WAN address starts with `100.64`-`100.127` or `10.`, the ISP itself uses CGNAT
    and port forwarding can't work. DERP is then the ceiling; ask the ISP for a public IP.
- Upload at home is ~40 Mbps, so even a direct connection tops out around 25-30 Mbps for one stream.

## 3. Plex: streams or downloads fail remotely

The Plex setting fix is `Set-PlexLibraryPaths.ps1 -Apply -ConfigureTailscale` (done at home). It
adds `http://100.102.16.5:32400` as a custom server URL and marks Tailscale (`100.64.0.0/10`) as a
LAN network, so the laptop connects directly instead of through Plex's 2 Mbps relay.

- **Plex says "Indirect" / quality capped at 2 Mbps / downloads unavailable:** the app isn't using the
  Tailscale address. Check Tailscale is connected, then sign out of the Plex app and back in. In a
  browser, `http://100.102.16.5:32400/web` always goes straight to the server.
- **Server not found but Tailscale is up:** hotel DNS can block Plex's `plex.direct` addresses. Fix
  for every network at once: login.tailscale.com > DNS > add nameserver `1.1.1.1` and turn on
  *Override local DNS*. Or just use `http://100.102.16.5:32400/web`.
- **Download button missing:** downloads need Plex Pass on the account that owns the server (you
  have it) and the Plex Windows app (Microsoft Store) or mobile app; the web app downloads the
  original file instead (item > ... > Download).
- **Download stalls:** big files over a relayed connection take a while (a 4 GB movie at 6 Mbps is
  about 1.5 hours). Choose a lower download quality (Plex converts it on the PC) or download at night.
- **A library is empty:** the I: drive isn't mounted on the PC (USB drive asleep or unplugged).
  Plex keeps the entries, just greyed out; they come back when the drive does.

## 4. Moonlight / Sunshine

- **Pairing:** Moonlight > + (Add host) > `100.102.16.5` > Moonlight shows a PIN. On the home PC,
  open `https://localhost:47990` > PIN, enter it and a name. Done once; it stays paired.
  From the laptop, `https://100.102.16.5:47990` may refuse ("access denied") because Sunshine's
  web UI only trusts the local network. That's why pairing at home is easier.
- **Host shows as offline:** check `tailscale ping 100.102.16.5`, then that Sunshine is running on the
  PC (`Test-RemoteReadiness.ps1` on the PC, if you can reach it over SMB/Plex, or ask someone at home).
- **Black screen:** the PC's monitor is off/unplugged or Windows is on the lock screen with the display
  asleep. A dummy HDMI plug fixes this for good.
- **Stutter / artifacts:** lower bitrate to 2-3 Mbps and FPS to 30, and use Wi-Fi 5 GHz or a cable on
  the laptop. "Network connection is poor" warnings on DERP are normal; lower settings until they stop.
- **Controller doesn't work:** Sunshine's gamepad driver needs a reboot after install. Do that at home.

## 5. ROM share (`\\100.102.16.5\Emulators`)

- **Asks for a login:** use the home PC's account. Microsoft account = email + password (not the
  PIN); local account = `PCNAME\username` + password. Tick *Remember my credentials*.
- **"Network path not found":** Tailscale isn't connected, or the share/firewall rule is missing
  (`New-EmulatorShare.ps1 -Apply` on the PC).
- **Can browse but not save:** the account lacks write permission on the folder. On the PC:
  `I:\Games\Emulators` > Properties > Security > Edit > add your account with *Modify*.
- SMB over a relayed connection is slow for big ROMs. Edit configs remotely; copy large games to the
  laptop ahead of time if you want to play them there.

## What not to do from the road

- Don't run `plexopt apply --execute`, `plexopt purge` or the duplicate cleanup remotely; review
  those at home.
- Don't add `E:\MAIN` to Plex or the share. Nothing in these scripts will, and they refuse if asked.
