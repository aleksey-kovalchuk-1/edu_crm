# Laptop-Hosted Hackathon Deployment (Cloudflare Tunnel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing Education CRM at `https://unicrm.tech` from the Mac laptop that already runs the Docker Compose stack, using a named Cloudflare Tunnel, without exposing any port beyond loopback and without disturbing local development.

**Architecture:** A public/demo Compose overlay (`compose.public.yaml`) changes only the three environment values that must reflect the public origin (`PUBLIC_BASE_URL`, `OIDC_ISSUER`, `COOKIE_SECURE` on `api`; `KC_HOSTNAME` on `keycloak`) and swaps `web`'s nginx config for a variant that reports `X-Forwarded-Proto: https` (the loopback connection from `cloudflared` is always plain HTTP, so nginx cannot infer the scheme from the connection itself). `cloudflared`, run as a macOS LaunchAgent, is the only process that talks to `web` on `127.0.0.1:8080` and the only thing that ever touches the public Internet; nothing in `compose.yaml` changes its port bindings. DNS is cut over only after every local check passes.

**Tech Stack:** Docker Compose v2, nginx (existing `frontend/Dockerfile`/`nginx.conf`), FastAPI (`backend/app/settings.py`), Keycloak 26 (`quay.io/keycloak/keycloak`, realm import + `kcadm.sh`), `cloudflared` (Homebrew), macOS `launchd`.

**Spec:** [docs/superpowers/specs/2026-09-20-laptop-cloudflare-tunnel-design.md](../specs/2026-09-20-laptop-cloudflare-tunnel-design.md) — the plan argues from this spec; read both.

## Global Constraints

- Only synthetic demo data may ever be reachable through this deployment (spec "Operating boundary").
- `web`, `api`, `keycloak`, `db` keep their current loopback-only bindings (`127.0.0.1:PORT:PORT`) in `compose.yaml` — nothing in this plan changes a `ports:` entry there. The tunnel is the only path out.
- `http://localhost:8080` must keep working for local development throughout and after this work — every public-only change is additive (new file, new overlay, new array entries alongside existing ones), never a destructive edit of the dev-only path.
- No Cloudflare Access / second auth layer. No router port forwarding. No moving Postgres/Keycloak/attachments/mail/SMS to a hosted service. No GitHub-triggered auto-deploy.
- The deployment agent must never enter a password into the Keycloak login form or the Cloudflare login flow — both are owner-only steps, called out explicitly below.
- Never commit `deploy/local/*.env`, `~/.cloudflared/*`, or any tunnel credential — all already outside git or explicitly kept outside it.

## Task ↔ Owner Map

| Task | Agent-executable | Requires the owner at the keyboard |
|---|---|---|
| 1. Safety snapshot & backups | ✅ full task | — |
| 2. Public config layer + local verification | ✅ full task | — |
| 3. Install & configure `cloudflared` | brew install, tunnel create, config file, connectivity check | **`cloudflared tunnel login`** (browser OAuth) |
| 4. Host resilience (LaunchAgent, sleep, autostart) | LaunchAgent plist, `pmset` | Docker Desktop "Open at Login" toggle (System Settings, no reliable CLI) |
| 5. DNS cutover | route-dns commands, once given the go-ahead | **Explicit go-ahead before the command runs** (live public domain) |
| 6. External verification & sign-in | DNS/TLS/redirect checks, restart-resilience test | **Signing in through Keycloak in a real browser** |
| 7. Documentation | ✅ full task | — |

Stop and hand off at every bolded item above; do not attempt to script around them.

---

### Task 1: Pre-deployment safety snapshot and backups

**Files:**
- Create: none (this task only reads state and writes timestamped backups outside the repo)

**Interfaces:**
- Produces: a `../edu-crm-backups/*.dump` and `../edu-crm-backups/*.tar.gz` pair (from the existing scripts below), and a recorded git revision, that Task 2 onward assumes exist before touching runtime config.

- [x] **Step 1: Record the exact revision and working-tree state**

```bash
cd /Users/alex/dev/edu-crm
git rev-parse HEAD
git status --porcelain
```
Keep this output — it is the exact snapshot being deployed. If `git status --porcelain` is non-empty, stop and ask the owner whether to commit, stash, or deploy the dirty tree intentionally; do not silently discard anything (per the repo's own standing git-safety rules).

- [x] **Step 2: Run full backend and frontend verification**

```bash
cd /Users/alex/dev/edu-crm/backend && /Users/alex/dev/edu-crm/.venv/bin/python -m pytest -q
cd /Users/alex/dev/edu-crm/frontend && npm run test -- --run && npm run lint && npm run build
```
Expected: all pass (317 backend / 230 frontend as of this plan's writing — re-check the current counts, they will have moved). If anything fails, stop; do not deploy a red snapshot.

- [x] **Step 3: Confirm the running stack is healthy before backing it up**

```bash
cd /Users/alex/dev/edu-crm && docker compose ps
```
Expected: `db`, `keycloak`, `api`, `web` all `healthy`/`running`. If the stack isn't up yet, start it first (`docker compose up -d`) and wait for health.

- [x] **Step 4: Back up the database and attachments**

```bash
cd /Users/alex/dev/edu-crm
./scripts/db-backup.sh pre-public-deploy
./scripts/attachments-backup.sh pre-public-deploy
```
Both scripts already validate their own archive (`pg_restore --list`, `tar -tzf`) before naming the file — expect two file paths printed, no error. These land in `../edu-crm-backups/`, outside the repo, per the scripts' existing `BACKUP_DIR` default.

- [x] **Step 5: Report the snapshot**

No commit in this task — report to the owner: the git revision from Step 1, the test results from Step 2, and the two backup file paths from Step 4. This is the checkpoint the spec's "Source and data handling" section requires before any rebuild.

---

### Task 2: Public configuration layer + local verification

**Files:**
- Create: `frontend/nginx.public.conf`
- Create: `compose.public.yaml`
- Create: `scripts/keycloak-add-public-origin.sh`
- Modify: `deploy/keycloak/realm-edu-crm.json:69-79` (add the public origin to `redirectUris`/`webOrigins`/`post.logout.redirect.uris`, alongside the existing `localhost` entries — for any *future* fresh import; it does not affect the already-imported realm, which is why Step 4 below also runs the new script live)

**Interfaces:**
- Consumes: nothing from Task 1 besides "tests are green and a backup exists."
- Produces: `docker compose -f compose.yaml -f compose.public.yaml up -d` as the standing public bring-up command every later task assumes; `PUBLIC_ORIGIN=https://unicrm.tech` as the value threaded through Steps 2–5.

- [x] **Step 1: Create the public nginx config**

`frontend/nginx.conf` is mounted (not rebuilt) by the override in Step 2, so local dev's image and `nginx.conf` are untouched. Create `frontend/nginx.public.conf` as an exact copy of `frontend/nginx.conf` with only the four `proxy_set_header X-Forwarded-Proto $scheme;` lines changed to `proxy_set_header X-Forwarded-Proto https;` — because `cloudflared` always connects to nginx over plain loopback HTTP, so `$scheme` is always `http` here regardless of what the real client used; TLS ends at the Cloudflare edge, not at this container. Everything else (rate-limit zones, `/api/`, `/auth/`, error pages, SPA fallback) stays byte-for-byte identical to `nginx.conf`.

```nginx
# Public/demo variant of nginx.conf for the Cloudflare Tunnel deployment (see
# docs/superpowers/specs/2026-09-20-laptop-cloudflare-tunnel-design.md).
# Mounted over /etc/nginx/conf.d/default.conf by compose.public.yaml — never baked into the image.
# Keep every line except the four `X-Forwarded-Proto` values in sync with nginx.conf by hand;
# cloudflared always reaches this container over plain HTTP on loopback, so nginx cannot infer
# the original scheme from $scheme the way it can locally — it is hardcoded here instead.
limit_req_zone $binary_remote_addr zone=login_start:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=phone_code:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=phone_verify:10m rate=20r/m;

server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    add_header X-Content-Type-Options nosniff always;

    location = /api/v1/auth/login {
        limit_req zone=login_start burst=20 nodelay;
        limit_req_status 429;
        error_page 429 = @rate_limited;
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = /api/v1/profile/phone {
        limit_req zone=phone_code burst=5 nodelay;
        limit_req_status 429;
        error_page 429 = @rate_limited;
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = /api/v1/profile/phone/verify {
        limit_req zone=phone_verify burst=10 nodelay;
        limit_req_status 429;
        error_page 429 = @rate_limited;
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /api/ {
        client_max_body_size 105m;
        error_page 413 = @too_large;
        proxy_request_buffering off;
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location @too_large {
        default_type application/json;
        return 413 '{"code":"PAYLOAD_TOO_LARGE","message":"Слишком большой объём данных","details":null}';
    }

    location @rate_limited {
        default_type application/json;
        return 429 '{"code":"RATE_LIMITED","message":"Слишком много запросов, повторите позже","details":null}';
    }

    location /auth/ {
        resolver 127.0.0.11 valid=30s;
        set $keycloak_upstream http://keycloak:8080;
        proxy_pass $keycloak_upstream;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    location / { try_files $uri $uri/ /index.html; }
}
```

- [x] **Step 2: Validate the nginx config in isolation**

```bash
cd /Users/alex/dev/edu-crm
diff <(grep -v 'X-Forwarded-Proto' frontend/nginx.conf) <(grep -v 'X-Forwarded-Proto' frontend/nginx.public.conf)
```
Expected: empty diff — proves the only intentional difference is the four `X-Forwarded-Proto` lines, catching accidental drift right away.

- [x] **Step 3: Create the public Compose overlay**

`compose.yaml` merges `environment:` maps key-by-key across `-f` files, so only the changed keys need to appear here — everything else (image, volumes, healthchecks, loopback port bindings) is inherited unchanged from `compose.yaml`.

```yaml
# Public/demo overlay for the Cloudflare Tunnel deployment. Use together with the base file:
#   docker compose -f compose.yaml -f compose.public.yaml up -d
# Never used alone — it only overrides the handful of values that must reflect the public origin.
# See docs/superpowers/specs/2026-09-20-laptop-cloudflare-tunnel-design.md.
services:
  api:
    environment:
      PUBLIC_BASE_URL: https://unicrm.tech
      OIDC_ISSUER: https://unicrm.tech/auth/realms/edu-crm
      COOKIE_SECURE: 'true'

  keycloak:
    environment:
      KC_HOSTNAME: https://unicrm.tech/auth

  web:
    volumes:
      - ./frontend/nginx.public.conf:/etc/nginx/conf.d/default.conf:ro
```

- [x] **Step 4: Add the public origin to Keycloak's client, both for future imports and for the already-running realm**

Edit `deploy/keycloak/realm-edu-crm.json:69-79` to add the public origin *alongside* the existing `localhost` ones (never remove `localhost` — local dev must keep working):

```json
      "redirectUris": [
        "http://localhost:8080/api/v1/auth/callback",
        "http://localhost:5173/api/v1/auth/callback",
        "https://unicrm.tech/api/v1/auth/callback"
      ],
      "webOrigins": [
        "http://localhost:8080",
        "http://localhost:5173",
        "https://unicrm.tech"
      ],
```
and in the `attributes` block a few lines below:
```json
        "post.logout.redirect.uris": "http://localhost:8080/*##http://localhost:5173/*##https://unicrm.tech/*",
```

This only affects realms imported from scratch. The realm on this laptop already exists in the `postgres_data` volume, and Keycloak's `--import-realm` skips an already-present realm — so also create `scripts/keycloak-add-public-origin.sh` to apply the same change live, the same way `scripts/db-backup.sh` already wraps a `docker compose exec` operation:

```bash
#!/usr/bin/env bash
# Idempotently adds a public origin to the edu-crm-api Keycloak client's redirect URIs / web
# origins / post-logout redirect URIs, alongside the existing localhost ones (never removes them,
# so local dev keeps working). Needed because Keycloak's --import-realm only imports a realm that
# does not yet exist yet; an already-running realm must be updated live via kcadm.
set -euo pipefail
cd "$(dirname "$0")/.."

public_origin="${1:?Usage: scripts/keycloak-add-public-origin.sh https://unicrm.tech}"

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password"

client_uuid=$(docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients \
  -r edu-crm --query clientId=edu-crm-api --fields id --format csv --noquotes | tail -n1 | tr -d '\r')

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh update "clients/$client_uuid" -r edu-crm \
  --set "redirectUris=[\"http://localhost:8080/api/v1/auth/callback\",\"http://localhost:5173/api/v1/auth/callback\",\"$public_origin/api/v1/auth/callback\"]" \
  --set "webOrigins=[\"http://localhost:8080\",\"http://localhost:5173\",\"$public_origin\"]" \
  --set "attributes.\"post.logout.redirect.uris\"=http://localhost:8080/*##http://localhost:5173/*##$public_origin/*"

echo "Added $public_origin to the edu-crm-api client's redirect/web origins (localhost entries kept)."
```

```bash
chmod +x scripts/keycloak-add-public-origin.sh
```

- [x] **Step 5: Bring up the public overlay locally (still loopback-only — nothing external changes yet) and verify the merged config**

```bash
cd /Users/alex/dev/edu-crm
docker compose -f compose.yaml -f compose.public.yaml config --services
docker compose -f compose.yaml -f compose.public.yaml up -d
docker compose ps
```
Expected: all four services healthy, same as Task 1 Step 3 — this overlay only changes environment/volume content, not exposure.

- [x] **Step 6: Run the new Keycloak script against the live realm**

```bash
cd /Users/alex/dev/edu-crm
./scripts/keycloak-add-public-origin.sh https://unicrm.tech
```
Expected: the success line above, no error from `kcadm.sh`.

- [x] **Step 7: Verify locally, on 127.0.0.1:8080, before anything is public**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/            # expect 200
curl -s http://127.0.0.1:8080/api/v1/health                                 # expect a healthy JSON body
curl -s http://127.0.0.1:8080/auth/realms/edu-crm/.well-known/openid-configuration \
  | grep -o '"issuer":"[^"]*"'                                              # expect https://unicrm.tech/auth/realms/edu-crm
```
This exercises spec Verification steps 1–3 (SPA, `/api/v1/health`, and the forwarded scheme reaching Keycloak's own issuer claim) without touching DNS.

- [x] **Step 8: Confirm local dev on the plain compose file still works untouched**

```bash
cd /Users/alex/dev/edu-crm
docker compose -f compose.yaml up -d
curl -s http://127.0.0.1:8080/api/v1/health
```
Expected: still works, unaffected — proves the overlay is additive, not a replacement.

- [x] **Step 9: Commit**

```bash
cd /Users/alex/dev/edu-crm
git add frontend/nginx.public.conf compose.public.yaml deploy/keycloak/realm-edu-crm.json scripts/keycloak-add-public-origin.sh
git commit -m "feat(deploy): add public Cloudflare Tunnel configuration layer"
```

---

### Task 3: Install and configure `cloudflared`

**Files:** none tracked in the repo (tunnel credentials and config live under `~/.cloudflared/`, outside git, per the spec's "Host operation" section)

**Interfaces:**
- Consumes: `PUBLIC_ORIGIN=https://unicrm.tech` from Task 2.
- Produces: a named tunnel (record its name and UUID) and `~/.cloudflared/config.yml` that Task 4's LaunchAgent plist references by tunnel name.

- [x] **Step 1: Install `cloudflared`**

```bash
brew install cloudflared
cloudflared --version
```

- [x] **Step 2 (OWNER): Authenticate**

Hand off to the owner — this opens a browser against the owner's own Cloudflare account and cannot be done by the agent:

```bash
cloudflared tunnel login
```
Wait for the owner to confirm this completed (`~/.cloudflared/cert.pem` now exists) before continuing.

- [x] **Step 3: Confirm the zone is on Cloudflare before creating anything**

```bash
cloudflared tunnel login   # re-running after Step 2 lists the zone picker again, or:
```
Check with the owner that `unicrm.tech` is already added as a zone in the same Cloudflare account used for Step 2 (Cloudflare dashboard → the zone's nameservers show as active). This is a prerequisite the spec assumes but does not itself walk through — `cloudflared tunnel route dns` in Task 5 fails without it. If the zone isn't there yet, stop and have the owner add it (and, if the registrar — currently REG.RU per the spec — isn't already delegated to Cloudflare's nameservers, update that at the registrar) before Task 5.

- [x] **Step 4: Create the named tunnel**

```bash
cloudflared tunnel create edu-crm-hackathon
```
Expected output includes the tunnel's UUID and the path to its credentials JSON under `~/.cloudflared/`. Record the UUID — it is referenced by name (`edu-crm-hackathon`) everywhere else in this plan, but appears literally in `config.yml` below.

- [x] **Step 5: Write the ingress config**

Create `~/.cloudflared/config.yml` (not in the repo):

```yaml
tunnel: edu-crm-hackathon
credentials-file: /Users/alex/.cloudflared/<UUID-from-Step-4>.json
ingress:
  - hostname: unicrm.tech
    service: http://127.0.0.1:8080
  - hostname: www.unicrm.tech
    service: http://127.0.0.1:8080
  - service: http_status:404
```
Replace `<UUID-from-Step-4>` with the real value.

- [x] **Step 6: Validate ingress and a one-shot connection, still without touching DNS**

```bash
cloudflared tunnel ingress validate
cloudflared tunnel run edu-crm-hackathon &
sleep 5
cloudflared tunnel info edu-crm-hackathon
kill %1
```
Expected: `ingress validate` reports OK; `tunnel info` shows at least one connected edge location. Stop the foreground run — Task 4 wires the permanent, auto-restarting version.

---

### Task 4: Host resilience — LaunchAgent, sleep, autostart

**Files:**
- Create: `~/Library/LaunchAgents/tech.unicrm.cloudflared.plist` (not in the repo — host-specific, like the tunnel credentials it launches)

**Interfaces:**
- Consumes: the tunnel name `edu-crm-hackathon` from Task 3.
- Produces: an always-running `cloudflared tunnel run edu-crm-hackathon` process that Task 5 depends on being connected before DNS is cut over, and that Task 6's restart-resilience check exercises directly.

- [x] **Step 1: Find the installed `cloudflared` path (Homebrew's path differs between Intel and Apple Silicon)**

```bash
which cloudflared
```

- [x] **Step 2: Write the LaunchAgent plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>tech.unicrm.cloudflared</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>run</string>
        <string>edu-crm-hackathon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/alex/Library/Logs/cloudflared.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/alex/Library/Logs/cloudflared.err.log</string>
</dict>
</plist>
```
Use the real `cloudflared` path from Step 1 for `ProgramArguments`' first entry if it differs from `/opt/homebrew/bin/cloudflared`.

- [x] **Step 3: Load it and verify it restarts the tunnel**

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/tech.unicrm.cloudflared.plist
launchctl print gui/$(id -u)/tech.unicrm.cloudflared | head -20
cloudflared tunnel info edu-crm-hackathon
```
Expected: the service shows as running under `launchctl`, and `tunnel info` again shows a connected edge — now via the LaunchAgent, not a foreground shell.

- [x] **Step 4: Disable sleep while on AC power (display sleep may stay on)**

```bash
sudo pmset -c sleep 0
pmset -g | grep -A1 'AC Power'
```
This is a real, host-wide setting change — confirm with the owner before running `sudo pmset` if they haven't already agreed to it explicitly (the spec calls it out as required, but it is still a system-wide change worth a explicit nod in the moment).

- [x] **Step 5 (OWNER): Docker Desktop autostart**

No reliable CLI toggle for this — ask the owner to open Docker Desktop → Settings → General → enable "Start Docker Desktop when you log in." Confirm verbally rather than scripting it.

---

### Task 5: DNS cutover

**Files:** none

**Interfaces:**
- Consumes: the connected tunnel from Task 4 Step 3, and the passing local verification from Task 2 Step 7 — the spec's own verification ordering requires both before this step.

- [x] **Step 1: Confirm every prerequisite before asking for the go-ahead**

```bash
cloudflared tunnel info edu-crm-hackathon   # expect: connected
curl -s http://127.0.0.1:8080/api/v1/health  # expect: healthy
```

- [x] **Step 2 (STOP — explicit owner go-ahead required):**

This changes DNS for a live public domain currently pointed at REG.RU. State plainly what is about to happen (apex and `www` will start resolving through Cloudflare to this laptop) and wait for explicit confirmation before running Step 3. Do not treat an earlier general approval of the design doc as covering this specific, hard-to-reverse action.

- [x] **Step 3: Route DNS through the named tunnel**

```bash
cloudflared tunnel route dns edu-crm-hackathon unicrm.tech
cloudflared tunnel route dns edu-crm-hackathon www.unicrm.tech
```
Expected: each prints a confirmation that a proxied CNAME now points at the tunnel. This is additive routing through Cloudflare — it only works if `unicrm.tech`'s zone is already on Cloudflare's nameservers (checked in Task 3 Step 3); it replaces whatever record previously lived at that name in the zone.

---

### Task 6: External verification, demo sign-in, restart resilience

**Files:** none

- [ ] **Step 1: External DNS and TLS**

```bash
dig +short unicrm.tech
curl -vI https://unicrm.tech/ 2>&1 | grep -E 'HTTP/|subject:|issuer:'
```
Expected: resolves to Cloudflare's anycast IPs, and the certificate is Cloudflare-issued and trusted (no `-k`/`--insecure` needed).

- [ ] **Step 2: Unauthenticated redirect to Keycloak on the same origin**

```bash
curl -sIL https://unicrm.tech/ | grep -i location
```
Expected: eventually redirects to `https://unicrm.tech/auth/realms/edu-crm/...` — same origin, no mixed-content, no redirect loop (no more than the app's normal one or two hops).

- [ ] **Step 3 (OWNER): Sign in and click through**

Hand off to the owner: open `https://unicrm.tech` in a real browser, sign in with one demo account (`anna.demo`, `pavel.demo`, or `irina.demo` — passwords in `deploy/local/keycloak.env`), check the landing page, one catalog/workflow journey, and log out. The agent must not perform this step (Keycloak login is owner-only).

- [ ] **Step 4: Restart resilience**

```bash
launchctl kickstart -k gui/$(id -u)/tech.unicrm.cloudflared
cd /Users/alex/dev/edu-crm && docker compose -f compose.yaml -f compose.public.yaml restart
sleep 15
curl -s -o /dev/null -w '%{http_code}\n' https://unicrm.tech/api/v1/health
```
Expected: `200` after both restarts settle, confirming the recovery behavior the spec's success criteria require.

---

### Task 7: Documentation

**Files:**
- Modify: `README.md` (new section after "## Запуск через Docker")
- Create: `docs/deploy/public-demo.md` (rollback/runbook detail that doesn't belong in the top-level README)

- [ ] **Step 1: Add a short README section**

Insert after the existing `## Запуск через Docker` section (README.md:38, right before `## Локальная разработка без Docker`):

```markdown
## Публичная демонстрация (хакатон)

Для показа CRM снаружи используется отдельный конфигурационный слой поверх обычного Compose —
не меняет локальную разработку. Подробности и откат: [docs/deploy/public-demo.md](docs/deploy/public-demo.md).

```bash
docker compose -f compose.yaml -f compose.public.yaml up -d
./scripts/keycloak-add-public-origin.sh https://unicrm.tech   # один раз на уже существующей установке
```
```

- [ ] **Step 2: Write the runbook**

Create `docs/deploy/public-demo.md` covering, in the operator's own words matching the spec's "Failure handling and rollback" section:
- What `compose.public.yaml` overrides and why (link to the design spec).
- How to check tunnel health (`cloudflared tunnel info edu-crm-hackathon`) and LaunchAgent status (`launchctl print gui/$(id -u)/tech.unicrm.cloudflared`).
- Rollback: if the app breaks after cutover, restore the previous apex/`www` DNS records at the registrar/Cloudflare dashboard and let TTL expire; the tunnel and public compose layer can stay for diagnosis without exposing more.
- Database/migration failure: stop the rollout, restore only from the `../edu-crm-backups/` dump created in Task 1, never drop volumes as a shortcut.
- How to reverse this deployment entirely: `launchctl bootout gui/$(id -u)/tech.unicrm.cloudflared`, `cloudflared tunnel route dns` removal or DNS record deletion, `docker compose -f compose.yaml -f compose.public.yaml down` (falls back to `docker compose -f compose.yaml up -d` for local-only again).

- [ ] **Step 3: Commit**

```bash
cd /Users/alex/dev/edu-crm
git add README.md docs/deploy/public-demo.md
git commit -m "docs(deploy): document the public hackathon demo and its rollback"
```

## Self-Review Notes

- **Spec coverage:** Goal/success criteria → Tasks 2, 5, 6. Operating boundary → Global Constraints + Task 4 Step 4/5. Architecture → Task 2. Application configuration → Task 2 Steps 1–4 (the Keycloak client-origin gap was not named explicitly in the spec's "Application configuration" list but is required for login to work post-cutover; added as Task 2 Step 4). Source and data handling → Task 1. Host operation → Tasks 3–4. DNS and TLS rollout → Task 5. Verification → Tasks 2 Step 7, 3 Step 6, 5 Step 1, 6 Steps 1–4 (spec's 8-step order preserved). Failure handling/rollback → Task 7 Step 2. Out of scope items → deliberately absent from every task.
- **Placeholder scan:** no TBD/"add error handling"/"similar to Task N" left in any step; every config file and script above is complete, runnable content.
- **Type/name consistency:** tunnel name `edu-crm-hackathon` and LaunchAgent label `tech.unicrm.cloudflared` are the same literal strings everywhere they appear across Tasks 3, 4, 5, 6, 7.
