# michaelbesaw.com

Photography portfolio site. Node.js/Express app running on a Linode VPS, proxied through nginx.

## Editing files

The source of truth lives on the Linode server. There is no local copy here — use SSH to read and edit files.

- **SSH server alias:** `linode` (host: 45.79.140.251, user: mdbe, port: 2233)
- **Working directory on server:** `/var/www/michaelbesaw.com`
- **GitHub remote:** `github.com/mkdbe/michaelbesaw.com`

Read and edit files via `mcp__ssh-manager__ssh_execute` with server `linode`. After changes, commit and push from the server: `cd /var/www/michaelbesaw.com && git add -A && git commit -m "..." && git push origin main`.

## Running the app

Managed by systemd — never run `node server.js` manually.

```bash
sudo systemctl restart michaelbesaw.service   # restart
sudo journalctl -u michaelbesaw.service -f    # tail logs
systemctl status michaelbesaw.service         # check status
```

## Architecture

| Layer | Detail |
|---|---|
| Runtime | Node.js, Express |
| Entry point | `/var/www/michaelbesaw.com/server.js` |
| Port | 3000 (internal) |
| Reverse proxy | nginx → `/etc/nginx/conf.d/michaelbesaw.com.conf` |
| SSL | Let's Encrypt, covers `michaelbesaw.com` and `www.michaelbesaw.com` |
| DNS | Cloudflare — DNS only (not proxied) |

## Key files on server

```
/var/www/michaelbesaw.com/
├── server.js                        # Express app
├── index.html                       # Main portfolio page
├── analytics-dashboard.html         # Analytics dashboard
├── analytics.json                   # Visit log (auto-written by server, max 10k entries)
├── robots.txt
├── sitemap.xml                      # Only lists https://michaelbesaw.com/
├── site.webmanifest                 # PWA manifest (Android/iOS)
├── favicon.svg                      # 01-rule mark — light bg, dark text
├── favicon-16.png
├── favicon-32.png
├── favicon-48.png
├── favicon-192.png
├── favicon-512.png
├── apple-touch-icon.png             # Dark bg version (iOS dark mode safe)
├── analytics-favicon.svg            # Analytics page icon — same mark + chart line
├── analytics-favicon-16.png
├── analytics-favicon-32.png
├── analytics-apple-touch-icon.png   # Dark bg version (iOS dark mode safe)
├── photos/                          # Full-res portfolio images (read by /api/images)
├── photos-mobile/                   # Mobile variants
└── content/
    ├── about.txt                    # About section HTML content (editable)
    └── GoogleTag.md
```

## Routes

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Serves `index.html` with visit logging |
| GET | `/api/images` | Returns image list with EXIF metadata |
| GET | `/api/about` | Returns `content/about.txt` as HTML |
| POST | `/api/track` | Client-side analytics ping |
| POST | `/api/track-nav` | Page navigation tracking |
| POST | `/api/heartbeat` | Session heartbeat |
| GET | `/api/analytics` | Raw analytics JSON (no auth — internal use) |
| GET | `/analytics` | Analytics dashboard HTML |
| * | catch-all | 404 plain text |

## Dependencies

- `express` — HTTP server
- `exifr` — EXIF metadata from photos
- `geoip-lite` — IP → location lookup
- `resend` — Email notifications (visitor alerts to mbesaw@gmail.com)

## Analytics & notifications

Visits are logged to `analytics.json`. Bots are filtered. A 2-minute idle timer fires an email via Resend if the visitor looks human (duration ≥ 30s and ≥ 1 navigation, or Rochester-area geo). 1-hour cooldown per IP.

Your own IP `38.49.72.41` is excluded from analytics.

## nginx config

`/etc/nginx/conf.d/michaelbesaw.com.conf` — three server blocks:
1. HTTP (80) → HTTPS redirect
2. HTTPS www → HTTPS non-www (301)
3. HTTPS non-www → proxy to `localhost:3000`

Always run `sudo nginx -t` before `sudo systemctl reload nginx`.

## SEO meta tags (index.html)

- `<title>` — `michael besaw photography — rochester, ny`
- `<meta description>` — `photography by michael besaw — rochester, ny — landscape, nature, and candid photography`
- `<meta author>` — `michael besaw`
- `og:title` / `og:site_name` — `michael besaw photography`
- All tags use lowercase including the name, by preference.

## Icons

Two separate icon sets — one for the main site, one for `/analytics`.

**Main site** (`01-rule` mark): `favicon.svg` + PNG sizes + `apple-touch-icon.png`
**Analytics page** (`01-rule-analytics` mark): `analytics-favicon.svg` + PNG sizes + `analytics-apple-touch-icon.png` (adds an orange chart polyline)

Both `apple-touch-icon.png` files use a **dark background (`#1a1814`) with cream text (`#f3efe8`)** — intentionally inverted from the export kit's light originals. iOS 18 dark mode mangles light icons; dark-background icons render correctly in both modes.

To regenerate an apple-touch-icon on the server (ImageMagick is available):
```bash
convert -background none -size 180x180 /tmp/icon.svg /var/www/michaelbesaw.com/apple-touch-icon.png
```

Source SVG colors: bg `#1a1814`, text `#f3efe8`, analytics chart line `#d2502a`.

## Before making changes

1. Confirm the port (3000) and service name (`michaelbesaw.service`) haven't changed
2. `nginx -t` before any nginx reload
3. SELinux is enforcing — new service files need `sudo restorecon -v`
