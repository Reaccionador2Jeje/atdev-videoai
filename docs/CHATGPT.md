# AtDev VideoAI for ChatGPT

AtDev VideoAI exposes its video-project tools through the Model Context Protocol (MCP). ChatGPT can discover the tools and call them from a conversation when the account and workspace allow custom MCP apps.

## What the integration can do

- Check whether the local FFmpeg rendering engine is online.
- Create and save an editable video project from structured scene data.
- Create a project from declarative JSON (JSON data only; it never executes supplied code).
- List saved projects.
- Render a saved project to MP4 through FFmpeg.

The renderer is local-first and does not require a paid AI provider or a credit balance. It is not a replacement for a full YouTube analytics service, and it does not generate photorealistic AI footage: the current renderer assembles scenes, imported images, text, motion, transitions, and audio.

## MCP transport

The ChatGPT-facing endpoint is:

    https://YOUR-HOST/mcp

The server implements stateless Streamable HTTP request/response over JSON. It supports MCP initialization, ping, tool discovery, tool calls, and notifications. It does not provide server-initiated SSE streams or resumable sessions; GET and DELETE return HTTP 405.

For local development, run the HTTP MCP service:

    python mcp_http_server.py

It listens on:

    http://127.0.0.1:8766/mcp

Start the FFmpeg engine separately if you want to render:

    python engine/server.py

## Connecting from ChatGPT

1. Deploy the MCP service at a stable HTTPS address, or use a supported Secure MCP Tunnel for a private/local server.
2. In a ChatGPT account/workspace that permits custom MCP apps, open the Apps/Plugins connection settings and choose the option to add a custom MCP server.
3. Enter the HTTPS endpoint ending in `/mcp`.
4. Select the authentication mode supported by the workspace and server, then review the tools and permissions before enabling it.
5. Refresh the app after changing tool names or descriptions.

**Account availability:** custom MCP app creation and write-capable tools are controlled by ChatGPT plan and workspace settings. OpenAI's current help documentation lists full custom MCP support for Business and Enterprise/Edu workspaces; Pro access is more limited, and Free availability is not listed. This repository cannot enable those account features.

## Security notes

- Keep the service bound to loopback for local use.
- Do not publish an unauthenticated instance that can create projects or render files.
- A non-loopback bind is refused unless `ATDEV_MCP_TOKEN` contains at least 24 characters.
- The optional bearer-token guard is intended for compatible MCP clients. ChatGPT authentication choices can vary by workspace; do not assume a manually entered bearer token is accepted. If the ChatGPT connection requires OAuth, add an OAuth authorization server before exposing this service publicly.
- Put TLS in front of the service using a trusted HTTPS reverse proxy or supported secure tunnel. The Python server itself does not terminate TLS.
- Review tool permissions before allowing write/render actions.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ATDEV_MCP_HOST` | `127.0.0.1` | Bind address |
| `ATDEV_MCP_PORT` | `8766` | HTTP MCP port |
| `ATDEV_MCP_TOKEN` | empty | Optional bearer token; required for non-loopback binding |

## Protocol test

Run all tests, including the MCP transport tests:

    python -m unittest discover -s tests -v

The GitHub Actions workflow runs this test suite on pushes and pull requests.
