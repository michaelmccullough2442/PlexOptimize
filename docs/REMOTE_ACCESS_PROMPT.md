Paste everything below the line into a Claude session running on the Plex PC (Claude Code, Claude desktop with computer use, or similar). Run it in PowerShell **as Administrator** so it can read and fix firewall and network settings.

---

My Plex server on this PC can't be reached from outside my home network anymore. Remote access worked on 2026-09-26 and has since stopped. Please find the cause and fix it directly on this PC, checking with me before each change.

**My setup**
- Windows 11 PC, server name SEAFAN2014, Plex Media Server 1.43.x. I have Plex Pass, so Plex's 2025 remote-streaming paywall should not apply to me.
- Media is on the F: drive (13 TB Seagate).
- The PlexOptimize toolkit is in `C:\PlexOptimize` (https://github.com/michaelmccullough2442/PlexOptimize). Read its `CLAUDE.md` and the remote-access section of `docs/REBUILD_GUIDE.md` first.
- My Plex token is in the registry: `(Get-ItemProperty "HKCU:\Software\Plex, Inc.\Plex Media Server").PlexOnlineToken`. Keep it in a variable for this session only. Never print it, never write it to a file, and never paste it anywhere.
- SABnzbd also runs on this PC (port 8080). Leave it alone.

**Don't use `plexopt plex-remote --enable` or trust `plexopt plex-check` yet.** A code review found that:
- `plex-remote --enable` forces Plex into manual-port mode. If my router was relying on automatic port mapping (UPnP), that switch alone breaks remote access.
- `plex-check` reports Plex's last saved state without re-testing, so it can say WORKING when it isn't.
- `plex-check`'s CGNAT check can never trigger, because it looks at the wrong IP address.

Use the Plex API and Windows commands below instead.

**Likely causes, most likely first.** Remote access worked before, so look for what changed:
1. This PC's local IP address changed (DHCP), so the router's port forward now points at the wrong device.
2. Windows switched my network to **Public** after an update, which blocks Plex at the firewall.
3. A VPN running on the whole PC (not just inside the browser) is routing Plex's traffic out through the VPN.
4. A new or reset router, a mesh system (double NAT), or my ISP putting me behind CGNAT.
5. Plex settings: Remote Access turned off, a stale "Custom server access URL", the wrong port, or "Secure connections" set to Required.

Work through this in order. Check in with me at each **STOP**.

1. **Gather facts. This step only reads; change nothing yet.**
   - **Plex.** Set headers `@{ 'X-Plex-Token' = $t; Accept = 'application/json' }` against `http://127.0.0.1:32400`.
     - Run `PUT /myplex/refreshReachability` so Plex re-tests remote access, wait about 15 seconds, then read `GET /myplex/account`. Report `signInState`, `subscriptionActive`, `mappingState`, `mappingError`, `mappingErrorMessage`, `publicAddress`, `publicPort`, `privateAddress` and `privatePort`.
     - From `GET /:/prefs`, report `PublishServerOnPlexOnlineKey`, `ManualPortMappingMode`, `ManualPortMappingPort`, `secureConnections`, `customConnections`, and whichever pref controls Relay.
   - **Plex log.** Search `%LOCALAPPDATA%\Plex Media Server\Logs\Plex Media Server.log` for `mapping state set to`, `double NAT`, `NAT: PMP`, `usable IGD` and `mapped port`. Show me the last 15 matching lines.
   - **This PC's network.**
     - `Get-NetIPConfiguration` (local IP and gateway)
     - `Get-NetConnectionProfile` (Private or Public)
     - `Get-NetAdapter | ? Status -eq Up` (look for VPN, TAP, WireGuard, NordLynx or Tailscale adapters)
     - `Get-NetRoute -DestinationPrefix 0.0.0.0/0` (does the default route go through a VPN?)
     - public IP from `https://api.ipify.org`
     - `tracert -d -h 3 8.8.8.8` (two private IPs in a row means double NAT)
   - **Firewall.** List the Windows Firewall rules for `Plex Media Server.exe`: Enabled, Direction, Action and Profile. Then run `Test-NetConnection <this PC's LAN IP> -Port 32400`.
   - **Router.** Ask me to open the router's admin page (usually the gateway address above) and read you its WAN IP, its port-forward list and its UPnP setting. Don't store the router password.
   - **From outside.** Check whether the public port is reachable from the internet: canyouseeme.org, or plex.tv's view of the server.

   **STOP:** explain in plain language what you found and which cause it points to, before fixing anything.

2. **Fix, one change at a time.** Before each change:
   - say exactly what you'll change and why
   - record the current value so it can be put back
   - wait for my OK

   After each change, re-run `PUT /myplex/refreshReachability` and re-read `mappingState`. If the change didn't help, put the old value back before trying the next fix. Typical fixes:
   - **Network set to Public:** `Set-NetConnectionProfile -InterfaceAlias <alias> -NetworkCategory Private`.
   - **Missing or wrong firewall rule:** add or enable one inbound Allow rule for `Plex Media Server.exe` on TCP 32400. Don't open anything wider than that.
   - **The PC's IP changed:** walk me through updating the router's port forward (TCP 32400 → this PC's LAN IP) and adding a DHCP reservation, with steps for my router brand.
   - **Port forward vs. Plex's setting:** set Plex's "Manually specify public port" (`ManualPortMappingMode`/`ManualPortMappingPort`) only if a matching manual forward exists on the router. If the router uses UPnP, turn manual mode off instead.
   - **VPN on the PC:** tell me which app it is, then help me exclude Plex Media Server through split tunneling, or turn the VPN off. Don't uninstall anything.
   - **Double NAT:** explain my options (bridge mode on the ISP gateway, DMZ, or forwarding the port on both routers) and walk me through the one I pick.
   - **CGNAT:** explain my options: ask the ISP for a public IPv4 address, use IPv6, or live with Plex Relay (2 Mbps with Plex Pass).
   - **Plex settings:** fix a stale `customConnections` or a "Secure connections: Required" setting.

3. **Confirm.** Done means `mappingState` is `mapped` after a fresh reachability test, the external port check says open, and Plex Web → Settings → Remote Access shows green and stays green for 2 minutes. **STOP:** have me test from my phone on mobile data with Wi-Fi off, and play something.

4. **Leave it fixed.**
   - Make sure this PC has a DHCP reservation so its IP can't change again.
   - Tell me in one short list what was wrong and what you changed.
   - Optional, ask me first: fix the `plex-check` / `plex-remote` problems in `plexoptimize/plex.py` and `cli.py`, so `plexopt plex-check` catches this kind of problem by itself:
     - force a reachability re-test
     - detect CGNAT from the router's WAN IP, not the public IP
     - check the firewall, the network profile and any VPN adapter
     - stop `--enable` from overriding UPnP
     - handle errors cleanly

     Run `pytest`, then commit and push to the branch.

Ground rules:
- Read freely; change nothing on this PC, in Plex, or on my router without my OK for that specific change.
- Never delete files, libraries or Plex data. Never touch my personal photos and videos.
- Never sign Plex out or remove the server from my account.
- Explain things in plain language. I'm not super technical.
