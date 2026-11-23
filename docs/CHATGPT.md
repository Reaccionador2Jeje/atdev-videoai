# AtDev VideoAI for ChatGPT

AtDev VideoAI exposes video-project tools through the Model Context Protocol (MCP). A compatible ChatGPT workspace can discover these tools and call them from a conversation.

## Capabilities

- Check whether the local FFmpeg rendering engine is online.
- Create and save editable video projects.
- Generate projects from declarative JSON (the JSON is data, never executed as code).
- List saved projects.
- Render saved projects to MP4.
- Retrieve a temporary, signed HTTPS download URL for a rendered MP4.

The renderer is local-first and does not require a paid AI provider or credit balance. It assembles scenes, imported images, text, motion, transitions and audio; it does not synthesize AI footage.

## ChatGPT connection

The MCP endpoint is:

    https://YOUR-HOST/mcp

ChatGPT custom MCP apps support remote MCP servers over streaming HTTP and OAuth. In a workspace that permits custom MCP connections:

1. Open ChatGPT on the web and go to **Plugins / Apps**.
2. Choose **Add custom MCP server**.
3. Enter a name such as **AtDev VideoAI** and the HTTPS MCP endpoint above.
4. Choose **OAuth** authentication.
5. Complete the AtDev VideoAI sign-in and approve the requested scopes.
6. Review the discovered tools and their permissions before enabling the connection.

Custom MCP app availability and workspace controls are determined by ChatGPT. This repository cannot enable account features or create a connection inside a user's ChatGPT account.

## OAuth 2.1 provider

The repository includes a lightweight, single-account OAuth 2.1 authorization-code provider with PKCE S256, dynamic client registration, protected-resource metadata, authorization-server metadata, opaque access tokens, rotating refresh tokens and scope checks.

Configure these environment variables on the MCP service:

| Variable | Purpose |
|---|---|
| `ATDEV_PUBLIC_BASE_URL` | Public HTTPS origin, for example `https://videoai.example.com` |
| `ATDEV_OAUTH_USERNAME` | Account name used on the AtDev authorization page |
| `ATDEV_OAUTH_PASSWORD` | Strong, unique password for the AtDev authorization page (minimum 16 characters) |
| `ATDEV_OAUTH_DB` | Optional path for persistent OAuth SQLite state; defaults to `oauth.sqlite3` |
| `ATDEV_MCP_HOST` | Bind address; public binds require HTTPS base URL and OAuth credentials |
| `ATDEV_MCP_PORT` | MCP HTTP port; defaults to `8766` |

The provider uses DCR and PKCE S256, publishes `authorization_response_iss_parameter_supported: true`, includes the issuer (`iss`) in successful and error authorization redirects, and preserves the requested `resource` as the token audience. It advertises `offline_access` and rotates refresh tokens.

The provider publishes:

- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-authorization-server`
- `/oauth/register`
- `/oauth/authorize`
- `/oauth/token`
- `/mcp`

It supports public OAuth clients using `token_endpoint_auth_method=none`, authorization code with PKCE S256, refresh tokens, and these scopes:

- `videoai.read` — list projects and retrieve download links.
- `videoai.write` — create editable projects.
- `videoai.render` — render MP4 videos.
- `offline_access` — allow refresh-token continuity.

The HTTP MCP transport leaves initialization and tool discovery public, then checks the bearer token, audience, expiry and required scope for each protected tool call. The health tool is anonymous.

**Important deployment note:** this built-in provider is a self-hosted starter for one account, not a reviewed multi-user identity platform. OpenAI recommends an established identity provider for production deployments. For a public multi-user service, integrate a managed provider and have it issue tokens for this MCP resource instead of sharing one server login.

## Signed MP4 delivery

Set these variables on both the MCP process and the FFmpeg engine:

| Variable | Purpose |
|---|---|
| `ATDEV_PUBLIC_BASE_URL` | Public HTTPS origin used to create download URLs |
| `ATDEV_DOWNLOAD_SECRET` | Random secret of at least 32 characters used to sign and verify URLs; configure the same value on both processes |

After a render, AtDev returns a URL like:

    https://YOUR-HOST/download/video-....mp4?expires=...&sig=...

The link expires after 15 minutes. The renderer verifies the HMAC signature, filename and expiry before serving the file. Treat the link as a temporary bearer link: anyone who receives it can download the video until it expires.

## Reverse proxy routing

The MCP process listens on loopback port 8766. The FFmpeg engine listens on loopback port 8765. Configure your HTTPS reverse proxy so these paths reach the correct local service:

| Public path | Local service |
|---|---|
| `/mcp` | `127.0.0.1:8766` |
| `/.well-known/*` | `127.0.0.1:8766` |
| `/oauth/*` | `127.0.0.1:8766` |
| `/download/*` | `127.0.0.1:8765` |

Keep the renderer port private; do not expose `/api/render` publicly. Persist the OAuth database and rendered files across restarts.

## Local development

For the local editor and renderer:

    python engine/server.py

For the MCP HTTP process, set a public HTTPS base URL only when you have a real HTTPS reverse proxy or secure tunnel. The OAuth endpoints require that public origin to match the deployed URL.

    python mcp_http_server.py

The stdio MCP bridge remains available for local MCP clients:

    python mcp_server.py

## Security and operational limits

- Use HTTPS for any public connection.
- Use a strong unique OAuth password and keep it out of source control.
- Keep `oauth.sqlite3`, token material and rendered media on persistent private storage.
- Do not expose the FFmpeg engine's `/api/render` route to the public Internet.
- Temporary download URLs are bearer links and should not be posted publicly.
- This implementation is a single-account starter, not a substitute for an audited identity provider, production account management, rate limiting or a security review.
- The Python HTTP server does not terminate TLS; TLS must be provided by a trusted reverse proxy or secure tunnel.

## Tests

Run:

    python -m unittest discover -s tests -v

GitHub Actions runs syntax checks and the test suite on pushes and pull requests.
