# Connect AtDev VideoAI to ChatGPT

AtDev VideoAI is deployed and exposes a remote Model Context Protocol (MCP) endpoint.

- **App name:** AtDev VideoAI
- **MCP server URL:** https://atdev-videoai-production.up.railway.app/mcp
- **Web editor:** https://atdev-videoai-production.up.railway.app/

## Connect

ChatGPT's custom MCP connection is created inside the user's ChatGPT account; a GitHub repository cannot install it automatically.

1. Open ChatGPT **on the web**.
2. Open **Plugins / Apps** and choose **+ → Add custom MCP server** (labels can vary).
3. Name the connection **AtDev VideoAI**.
4. Paste the MCP server URL above.
5. Select **OAuth**, continue through the AtDev sign-in, and approve the requested permissions.
6. Review discovered tools and install/create the connection.
7. In a new conversation, select or mention **AtDev VideoAI** and ask it to create a project or render an MP4.

Custom MCP access depends on ChatGPT plan, workspace, and administrator controls. The creation flow is web-only. Some plans allow only read/fetch tools; write and render actions may not be available on every account.

## What it can do

- Check whether FFmpeg is available.
- Save editable scene-based video projects.
- Convert declarative JSON into an editable project.
- Render projects to MP4.
- Return short-lived signed download links.

The current renderer makes motion graphics from text, images, backgrounds, transitions, animation and audio. It does not synthesize AI footage or voice, and it has no paid credit requirement.

## Security

The app uses OAuth and per-tool scopes. Keep the AtDev account password and download-signing secret private. If a temporary password was shared during setup, rotate it in Railway before connecting.

MP4 links expire after 15 minutes and are bearer links: anyone with a valid link can download the video until expiry. Do not share them publicly.

The built-in OAuth provider is a single-account starter, not an audited multi-user identity system. Public distribution requires a security review and a proper identity provider.
