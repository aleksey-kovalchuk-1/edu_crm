
## Goal

Let a prospective UniCRM user request access, notify the superadmin inside the CRM, and send the applicant the requested email confirmation. Preserve the existing rule that the superadmin reviews requests and creates CRM accounts manually.

## Product behavior

- Public visitors can open an access-request form from the sign-in page.
- The form asks for the person's name and email. Submitting it creates a pending access request; it does not create a Keycloak account, grant a CRM role, or sign the person in.
- A successful submission receives an in-app notification in the superadmin's CRM bell. Managers and administrators do not receive it. Repeated submissions for the same pending email do not create duplicate requests, notifications, or acknowledgement emails.
- The applicant receives this exact message by email:

  > Администратор получил вашу регистрацию. В ближайшее время он ее рассмотрит. Если вы уже долго ждете, напишите на почту Администратору: alexey.y.kovalchuk@yandex.ru.

- The superadmin can review pending requests in «Настройки → Пользователи и роли» and use the existing account-creation flow to create an account. The request is marked handled after successful account creation. Requests can be declined without creating an account.
- Admin notifications remain in the site bell only. The acknowledgement email goes only to the applicant; it is not sent to CRM staff.
- Public responses do not reveal whether an email already has an account or an outstanding request.

## Architecture

Add a CRM-owned `access_requests` record with an opaque id, normalized email, display name, status (`pending`, `approved`, `declined`), created/updated timestamps, and the superadmin who handled it when applicable. Enforce one pending request per normalized email. Store a notification dedupe key derived from the request id; create the notification in the same database transaction as the request.

Add an unauthenticated `POST /api/v1/access-requests` endpoint with strict request validation and rate limiting. Reuse the configured `app.state.email_sender` through an email outbox/status so a transient provider failure does not lose the request or falsely report the email as sent. Retry delivery safely and never send duplicate acknowledgements for an existing pending request.

Add an admin-only list and status actions under `/api/v1/admin/access-requests`. Only `crm-superadmin` may list or act on requests. Creating an account from a request must use the existing Keycloak account creation code and mark the request approved only after account creation commits successfully.

Extend the in-app notification catalogue with a default-enabled access-request event visible only to active `crm-superadmin` users. The notification links to the admin request queue and contains only the submitted name and email needed to review it.

Add a sign-in-page link and a small Russian form. Show the same generic success confirmation for new and duplicate submissions. Present validation and service errors without exposing account existence.

## Delivery and privacy

- The existing email implementation uses a generic HTTP provider contract and falls back to logging when no provider is configured. The production provider's real API contract and credentials must be confirmed/configured before claiming that live email delivery works. The feature must expose pending/failed delivery state to operators and retry safely; it must not present a log-only fallback as a delivered email.
- Do not store full IP addresses beyond the rate-limit window. Keep only the minimum request data needed for the superadmin to review it, and include request retention/deletion rules in the operational documentation.
- Add basic IP and normalized-email rate limits. CAPTCHA is not included in this first slice unless abuse evidence or an existing CAPTCHA service requires it.
- Do not enable unrestricted Keycloak self-registration. Pending requests are separate from Keycloak accounts; access still requires superadmin account creation.

## Tests and acceptance

- Anonymous visitor can submit a valid request; invalid name/email is rejected.
- A pending request produces one stored request, one superadmin-only in-app notification, and one acknowledgement email; managers/admins do not get that notification.
- Repeated pending-email submissions return the same generic success, with no duplicate notification or email.
- Email provider failure leaves the request and notification intact and the email eligible for retry; log-only local mode is not counted as delivered.
- Only the superadmin can view, decline, or approve requests. Non-superadmins receive `403`.
- Creating an account from a request marks it approved only after successful Keycloak/CRM account creation; a failed account creation leaves it pending.
- Declined requests do not create CRM/Keycloak users. A later new request can be submitted according to the documented re-application rule.
- Frontend tests cover the public form and superadmin review queue; backend tests cover rate limiting, privacy-safe duplicate behavior, permissions, notification dedupe, email retries, and account-creation rollback.
- Existing authentication, account creation, bell notifications, email settings, and the permanently mocked LMS/website continue working.

## Open implementation detail

A declined request may be resubmitted after 30 days. No CRM account is created at public submission time.
