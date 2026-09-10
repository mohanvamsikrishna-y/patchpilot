# MCP connection

Launch the server from the cloned repository. A client configuration can use the following structure, substituting absolute paths for your machine.

```json
{
  "mcpServers": {
    "patchpilot": {
      "command": "/absolute/path/to/python3",
      "args": ["-m", "patchpilot", "mcp", "--repo", "/absolute/path/to/target"],
      "cwd": "/absolute/path/to/patchpilot"
    }
  }
}
```

Client configuration fields vary. If a client does not support `cwd`, install the project in a virtual environment with `python3 -m pip install -e .` and point `command` at that environment's Python.

The transport reads and writes newline-delimited JSON-RPC messages. Standard output contains protocol messages only. Supported methods are `initialize`, `ping`, `tools/list`, and `tools/call`. Notifications receive no response. Protocol version is `2025-11-25`.

Default tools are `search`, `read_file`, and `github_read_issue`. Add `--allow-execution` to expose planning, replacements, tests, and review requests. Mutation occurs directly in the provided directory, so use a disposable copy. The MCP server does not apply the controller's step or model cost budget and does not publish PRs.

This prototype is synchronous. It does not implement cancellation, resources, prompts, streaming HTTP transport, or authorization over a network endpoint.
