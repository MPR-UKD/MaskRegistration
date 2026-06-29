# MCP server for Claude Code

MaskRegistration exposes its API as MCP tools so an LLM agent like
Claude Code can register knee MRI masks from natural-language commands.

## Install

```bash
pip install "maskregistration[mcp]"
# or with extras:
pip install "maskregistration[elastix,mcp]"
```

## Register the server in Claude Code

Add to `~/.claude/config.json` (Mac/Linux) or the equivalent on Windows:

```json
{
  "mcpServers": {
    "maskreg": {
      "command": "maskregistration-mcp"
    }
  }
}
```

Restart Claude Code. Then ask things like:

> "Use maskreg to register the mask at /data/T0/mask.nii.gz from
> /data/T0/dess to /data/T1/dess, output to /data/T1_mask.nii.gz,
> use the deformable backend with elastix."

## Tools exposed

- `list_backends` — which registration engines are installed
- `check_mask_alignment` — verify mask/DICOM affines line up before running
- `register_affine` — fast affine resample of a mask (sub-second per volume)
- `register_deformable` — deformable registration with displacement field
- `field_transfer_lowres_to_highres` — estimate field on low-res sequence,
  apply to high-res

## Network mode

For remote use (e.g. when Claude runs on another machine):

```bash
maskregistration-mcp --transport sse --port 8765
```

Then point the client at `http://your-host:8765/sse`.
