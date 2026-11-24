# Build the AtDev VideoAI custom GPT

This guide connects a custom GPT to the authenticated REST API. It is separate from the existing MCP endpoint; both interfaces use the same project and FFmpeg renderer.

## What the GPT can do

- Check whether the FFmpeg renderer is online.
- Create editable video projects from a user's description.
- Optionally render a project to MP4 when the user explicitly asks for the exported video.
- Render a previously saved project.
- Retrieve a short-lived MP4 download URL.

The current renderer creates motion-graphics videos from text, imported images, transitions, animation and audio tracks. It does not generate AI footage or synthetic narration.

## 1. Configure a private API key on the server

Create a long random key (at least 32 characters). For example, on a machine with Python:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

In the Railway service that runs `mcp_http_server.py`, add this environment variable:

    ATDEV_GPT_ACTIONS_API_KEY=<your-random-secret>

Do not commit this value, put it in the OpenAPI file, or share it in public issues. Keep the same value available for the GPT Builder's API-key configuration. Restart/redeploy the service after setting it.

If the variable is missing or shorter than 32 characters, GPT Actions routes return HTTP 503. Incorrect keys return HTTP 401.

## 2. Verify the deployed schema

Open:

    https://atdev-videoai-production.up.railway.app/actions/openapi.json

It should return the OpenAPI 3.1.0 document. The same document is versioned at [docs/openapi/gpt-actions.json](openapi/gpt-actions.json).

## 3. Create the GPT

In ChatGPT on the web, open the GPT builder (if GPT creation is enabled for your account/workspace) and create a GPT:

- **Name:** AtDev VideoAI
- **Description:** Creates editable motion-graphics video projects and exports MP4 files using AtDev VideoAI.
- **Instructions:** Use the action to check renderer health before promising a render. Turn the user's brief into a project with a clear sequence of scenes, concise titles and subtitles, a consistent color palette, and durations between 1 and 30 seconds per scene. Use 16:9 for landscape, 9:16 for vertical short-form video, and 1:1 for square video. Create the editable project first. Set render=true only when the user asks for the MP4 now. Report the returned project ID and, when rendering succeeds, provide the returned download URL. Never claim that AI-generated footage or voice is available; this renderer uses FFmpeg to assemble motion graphics, text, images, transitions and audio. Ask before using any external assets that the user has not supplied.
- **Conversation starters:** "Create a 30-second explainer about Linux"; "Make a vertical short about open-source software"; "Render my saved video project".

Add an **Action**, then import the OpenAPI document from the URL above or paste the contents of `docs/openapi/gpt-actions.json`.

## 4. Configure Action authentication

Choose **API Key** authentication:
- Authentication type: API Key
- Auth type: Custom
- Header name: `X-AtDev-API-Key`
- API key: the exact secret stored in Railway as `ATDEV_GPT_ACTIONS_API_KEY`

Save the action. The key must remain private; never add it to GPT instructions or conversation starters.

## 5. Test the action

Try these in order:

1. Ask the GPT to check whether the renderer is online. It should call `checkVideoAIHealth`.
2. Ask it to create an editable project without rendering. It should call `createVideoProject` with `render=false`.
3. Ask it to export the project to MP4. It should call `renderVideoProject` or create the project with `render=true` if the project is new.
4. Confirm that the response includes a temporary `download_url`. Signed download links expire after 15 minutes.

## API operations

| Operation | Purpose |
|---|---|
| `checkVideoAIHealth` | Check renderer status |
| `listVideoProjects` | List saved projects |
| `createVideoProject` | Create a project; optionally render immediately |
| `renderVideoProject` | Render an existing project |
| `getVideoDownload` | Get a fresh temporary download URL |

All `/actions/v1/*` routes require the API key. The OpenAPI document itself is public and contains no secret. The existing MCP endpoint and its OAuth authentication are unchanged.

## Account availability

GPT creation and editing are controlled by ChatGPT plan and workspace settings. If the GPT Builder is unavailable in your account, the API and OpenAPI integration can still be prepared and tested, but this repository cannot enable GPT creation on the account.
