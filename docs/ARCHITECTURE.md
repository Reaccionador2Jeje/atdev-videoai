# Architecture

## Product surfaces
1. **Web Studio:** independent interface for creating and managing video projects.
2. **Render Engine:** local or self-hosted service that converts declarative project data into video files.
3. **ChatGPT Bridge:** MCP-compatible integration for drafting projects, inspecting scenes, and requesting renders.

## Design rules
- Core workflows do not require an account, credits, or a paid AI provider.
- AI-assisted features are adapters; the editor and renderer work without them.
- Projects use portable, versioned JSON and user-owned assets.
- User media is not silently uploaded to external services.
- YouTube analytics is optional and respects API quotas.
- Zero credits means no artificial in-product credit meter, not infinite hosted compute.

## Initial stack
- Frontend: semantic HTML, CSS, and vanilla JavaScript for the first prototype.
- Video output: FFmpeg in a future rendering service.
- Project format: versioned JSON.
- Backend: Python service when rendering endpoints are introduced.
- ChatGPT integration: separate MCP server adapter.

## Milestones
### M0 — Repository foundation
Project identity, principles, web studio shell, contribution workflow.
### M1 — Code-driven video prototype
Versioned scene/timeline JSON, text, shapes, images, audio, preview, FFmpeg export.
### M2 — Creator research
Idea organizer, keyword workspace, optional YouTube Data API adapter.
### M3 — ChatGPT integration
MCP tools for project creation, scene editing, inspection, and render requests.
### M4 — Community and portability
Import/export bundles, templates, reusable components, self-hosting documentation.
