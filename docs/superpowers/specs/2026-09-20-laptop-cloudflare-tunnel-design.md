# Laptop-hosted hackathon deployment through Cloudflare Tunnel

**Status:** Approved in conversation on 2026-09-20.

## Goal

Publish the existing Education CRM at `https://unicrm.tech` for a hackathon demonstration. The Mac laptop remains the only origin server, all application data is synthetic, and visitors reach the normal CRM and Keycloak login flow without an additional Cloudflare Access prompt.

## Success criteria

- `https://unicrm.tech` opens the CRM from an external network with a valid browser-trusted TLS certificate.
- The application redirects unauthenticated visitors to Keycloak on the same public origin and returns them to the CRM after login.
- The web UI, `/api/`, and `/auth/` continue to use one origin so the existing session and CSRF model remains intact.
- PostgreSQL, Keycloak management ports, the API port, Docker, and the laptop itself are not directly exposed to the Internet.
- The tunnel and CRM recover after an application restart; after a laptop restart they recover once macOS has started Docker Desktop and the user session required by it.
- Local development through `http://localhost:8080` remains available through the existing development configuration.

## Operating boundary

This is a hackathon demonstration deployment, not a production service. Only synthetic accounts, organisations, contacts, files, and communications may be stored. The laptop must remain powered, connected to the Internet, awake, and thermally unobstructed. Closing a Mac laptop may suspend it unless supported clamshell conditions are met, so the safe default is to leave the lid open.

Loss of laptop power, sleep, Docker Desktop, local networking, or the Internet makes the public site temporarily unavailable. Cloudflare will show an upstream or tunnel error and reconnect automatically when the local dependencies return. No high-availability promise is made.

## Architecture

```text
Browser
  -> https://unicrm.tech
  -> Cloudflare edge (public DNS, TLS termination, proxy)
  -> named Cloudflare Tunnel (outbound connection from the laptop)
  -> http://127.0.0.1:8080
  -> existing nginx container
       /        -> React application
       /api/    -> FastAPI
       /auth/   -> Keycloak
  -> PostgreSQL and attachment volumes remain inside the local Docker network
```

Use a persistent named Cloudflare Tunnel, not a temporary quick tunnel. The named tunnel owns the proxied DNS route for the zone apex. No inbound router port forwarding, public origin IP, or local TLS certificate is required. Cloudflare Access is not enabled.

## Application configuration

Keep the current development Compose behaviour unchanged and add an explicit demo/public configuration layer. The public configuration sets:

- `PUBLIC_BASE_URL=https://unicrm.tech`;
- `OIDC_ISSUER=https://unicrm.tech/auth/realms/edu-crm`;
- the existing internal Keycloak base URL remains on the Docker network;
- `COOKIE_SECURE=true`;
- Keycloak's public hostname to `https://unicrm.tech/auth` while retaining HTTP on the internal container connection and forwarded-header processing;
- nginx forwarding information compatible with the local tunnel so FastAPI and Keycloak see HTTPS as the original scheme.

The public web entry point stays bound to `127.0.0.1:8080`. `cloudflared` is the only process that consumes it. Database, API, mail test UI, antivirus, worker, and Keycloak ports are not published publicly.

Because the tunnel is the only remote path into the loopback-bound web service, nginx may use Cloudflare's connection metadata for the original client address. It must not trust a client-supplied address on a separately exposed interface. Audit logs should otherwise continue to record the tunnel endpoint rather than creating a direct origin exposure solely to obtain client IPs.

## Source and data handling

The checkout currently contains active, uncommitted task-board work. Deployment preparation must not discard, overwrite, or silently commit that work. Before building the public image:

1. Record the exact committed revision and dirty-file inventory.
2. Run the existing backend and frontend verification appropriate to the changed snapshot.
3. Deploy that snapshot only if the checks pass; otherwise stop and report the failing boundary.
4. Create a database dump and attachment archive before rebuilding or changing runtime configuration.

The existing Docker volumes remain the source of demo data. Mailpit and logging-only SMS delivery are development aids and are not exposed through the tunnel. No real mail or SMS provider is added for the hackathon deployment.

## Host operation

- Install `cloudflared` from the supported Homebrew package.
- Authenticate it interactively against the existing Cloudflare account and create one named tunnel for this CRM.
- Persist the tunnel credential outside the repository and run the tunnel through macOS launch services so it restarts automatically.
- Configure Docker Desktop to start at user login and retain the Compose services' restart policies.
- Disable system sleep while connected to AC power; display sleep may remain enabled.
- Keep the laptop's macOS account and disk protected. Do not place Cloudflare credentials, application secrets, or SSH/hosting passwords in Git.

Cloudflare authentication and the final demo-account sign-in require the owner at the browser. The deployment agent must not enter user passwords into Keycloak.

## DNS and TLS rollout

The current apex and `www` records point to the REG.RU shared-hosting placeholder. Leave them unchanged until the local public configuration and tunnel ingress pass local checks. Then replace the apex route with the named tunnel's proxied DNS route. Configure `www.unicrm.tech` to redirect to the apex or route it through the same tunnel, with the apex as the canonical URL.

Cloudflare provides the browser-facing certificate and proxies the request over the outbound tunnel. The deployment therefore does not depend on the invalid self-signed certificate currently served by REG.RU. The application must generate only HTTPS public redirects and secure cookies after cutover.

## Verification

Verification is performed in this order:

1. Existing test suites and production frontend build pass for the selected source snapshot.
2. All required Docker services are healthy locally.
3. The public configuration returns the SPA and `/api/v1/health` through `127.0.0.1:8080` with the expected forwarded scheme and host.
4. The named tunnel reports connected before DNS is changed.
5. External DNS resolves through Cloudflare and `https://unicrm.tech` presents a trusted certificate.
6. An unauthenticated browser reaches the CRM and is redirected to Keycloak on `https://unicrm.tech/auth/...` without a mixed-content or redirect-loop failure.
7. The owner signs in with one demo account and checks the landing page, one catalog/workflow journey, and logout.
8. Restart the tunnel and application containers in a controlled order and confirm public recovery.

## Failure handling and rollback

If the tunnel is healthy but the application is not, keep DNS on the old REG.RU placeholder while repairing the local stack. If a problem appears only after cutover, restore the previous apex and `www` DNS records and allow their TTL to expire. The named tunnel and local public configuration can remain for diagnosis without exposing additional laptop ports.

Database or migration failure stops the rollout. Restore only from the pre-deployment backup after identifying the failed migration boundary; do not destroy Docker volumes as a troubleshooting shortcut.

## Out of scope

- Production availability, compliance, or processing of real personal data.
- Cloudflare Access, one-time PINs, or a second authentication layer.
- Router port forwarding or direct exposure of the laptop.
- Moving PostgreSQL, Keycloak, attachments, mail, or SMS to hosted services.
- Replacing the current application authentication architecture.
- Automatic deployment from GitHub.
