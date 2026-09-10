"""Minimal synchronous MCP stdio tools server, protocol 2025-11-25."""
import json
import sys

from .github import read_issue
from .tools import definitions, schema


class Server:
    def __init__(self, tools, allow_execution=False):
        self.tools = tools
        self.allow_execution = allow_execution
        self.initialized = False

    def handle(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
        if "id" not in request:
            return None
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method = request["method"]
        params = request.get("params", {})
        if not isinstance(params, dict):
            return {**response, "error": {"code": -32602, "message": "Invalid params"}}
        if method == "initialize":
            self.initialized = True
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "patchpilot", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return {**response, "error": {"code": -32000, "message": "Initialize first"}}
        elif method == "tools/list":
            exposed = definitions()
            if not self.allow_execution:
                exposed = [t for t in exposed if t["name"] in {"search", "read_file"}]
            result = {"tools": exposed + [{"name": "github_read_issue", "description": "Read a GitHub issue using the host gh authentication", "inputSchema": schema(url="")} ]}
        elif method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return {**response, "error": {"code": -32602, "message": "Invalid tool arguments"}}
            if name == "github_read_issue":
                try:
                    if set(arguments) != {"url"} or not isinstance(arguments["url"], str):
                        raise ValueError("Expected a URL string")
                    data = {"ok": True, "issue": read_issue(arguments["url"])}
                except (ValueError, OSError) as exc:
                    data = {"ok": False, "error": str(exc)}
            elif not self.allow_execution and name not in {"search", "read_file"}:
                data = {"ok": False, "error": "Execution disabled. Start server with --allow-execution on a disposable workspace."}
            else:
                data = self.tools.call(name, arguments)
            result = {"content": [{"type": "text", "text": json.dumps(data)}],
                      "structuredContent": data, "isError": not data["ok"]}
        else:
            return {**response, "error": {"code": -32601, "message": "Method not found"}}
        return {**response, "result": result}

    def serve(self):
        for line in sys.stdin:
            try:
                if len(line) > 100000:
                    raise ValueError("Message too large")
                reply = self.handle(json.loads(line))
            except ValueError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            if reply is not None:
                print(json.dumps(reply), flush=True)
