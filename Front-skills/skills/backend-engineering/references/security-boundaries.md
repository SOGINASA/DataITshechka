# Security at the changed boundary

Apply the controls relevant to the feature. This is not a request to redesign the whole application's authentication or perform an unrelated security audit.

## Identity and access

Use the existing authentication framework/identity provider. Enforce action, object and tenant scope server-side, including list/search/export, nested IDs, bulk endpoints and background-job entrypoints. Derive the acting identity from trusted authentication, then validate any requested organization against membership/permissions. Never trust a submitted role/owner/tenant simply because input validation accepts its type.

Use deny-by-default policy and check access to each relevant object/relationship; a role alone may not express ownership. Prefer scoped database access and verify affected rows on mutations. Test another user's ID, another tenant's ID and disallowed state transitions, not just anonymous requests. Opaque UUIDs are not access control. [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

For JWT-based access, verify signature with configured algorithms/keys and validate issuer, audience, expiry and required profile claims. A decoded token or TypeScript cast is not validation. Handle key rotation and session invalidation according to the existing protocol. Do not substitute a new home-grown token scheme. [OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

Cookie-authenticated state changes need the framework's appropriate CSRF protections. Secure/HttpOnly and suitable SameSite settings have different roles; `SameSite=Strict` everywhere can break legitimate login/cross-site flows. CORS is a browser access policy, not authorization or a complete CSRF defense. Configure explicit trusted origins where needed and test the real authentication flow. [OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Input, output and external fetches

- Parameterize SQL values and allowlist dynamic identifiers; do not build a query from raw filter/sort strings.
- Validate body size, content type, nesting and field ranges at the boundary. Use explicit update DTOs and response fields to prevent mass assignment and accidental disclosure.
- For file uploads, use bounded streams, independently assessed file type and server-controlled storage paths; do not trust the filename or browser MIME alone. Apply isolation/scanning appropriate to how the file will be consumed.
- For URL fetch/import features, constrain protocols/destinations and network egress. Consider private/loopback/link-local IPv4/IPv6, DNS resolution changes and redirects; disable redirects or revalidate each hop. A regex or checking the initial URL alone is inadequate. Use approved client/network controls. [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- Keep secrets in the project's supported secret/config mechanism. Redact credentials, tokens, cookies and unnecessary private content in logs, traces and error reports. An internal stack trace can still contain secrets.

## Resource abuse

Bound pagination, upload/decompression size, expensive search, job fan-out and concurrent requests. When limits must span replicas, use the platform/gateway or shared limiter and define its outage behavior. Per-process counters implement only a process-local policy. Choose limits from cost and observed traffic; copied “100/min” examples are not capacity planning. Do not trust arbitrary forwarding headers as client identity.

Use least-privilege database/service credentials and existing dependency checks relevant to the change. A scanner result does not prove correct object authorization, and a broad dependency upgrade is not automatically part of fixing an endpoint.
