import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from patchpilot.mcp import Server
from patchpilot.providers import Budget, OpenAIProvider
from patchpilot.tools import Toolset


class ProtocolTests(unittest.TestCase):
    def test_mcp_initialization_discovery_and_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hello.py").write_text("hello = 'world'")
            server = Server(Toolset(root))
            def send(method, params=None):
                return server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
            self.assertIn("error", send("tools/list"))
            self.assertEqual(send("initialize")["result"]["protocolVersion"], "2025-11-25")
            names = [t["name"] for t in send("tools/list")["result"]["tools"]]
            self.assertIn("read_file", names)
            self.assertNotIn("replace_text", names)
            result = send("tools/call", {"name": "read_file", "arguments": {"path": "hello.py"}})["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
            self.assertTrue(send("tools/call", {"name": "run_tests"})["result"]["isError"])
            self.assertEqual(send("no-such-method")["error"]["code"], -32601)
            self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            self.assertIn("error", server.handle([]))

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake-test-key"})
    def test_responses_loop_preserves_reasoning_and_tool_call_output(self):
        output = [{"type": "reasoning", "id": "rs_1", "summary": []},
                  {"type": "function_call", "call_id": "call_1", "name": "search", "arguments": '{"query":"bug"}'}]
        response = {"output": output, "usage": {"input_tokens": 100, "output_tokens": 20}}
        bodies = []
        def request(req, **kwargs):
            bodies.append(json.loads(req.data))
            return io.BytesIO(json.dumps(response).encode())
        with patch("urllib.request.urlopen", side_effect=request):
            provider = OpenAIProvider("Fix bug", "test-model")
            budget = Budget()
            self.assertEqual(provider.next(None, budget)["name"], "search")
            provider.next({"ok": True}, budget)
        self.assertEqual(bodies[1]["input"][1:3], output)
        self.assertEqual(bodies[1]["input"][-1]["type"], "function_call_output")
        self.assertFalse(bodies[0]["parallel_tool_calls"])
        self.assertEqual(budget.input_tokens, 200)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake-test-key"})
    def test_only_rate_limit_rejections_retried(self):
        rejected = urllib.error.HTTPError("url", 429, "rate limited", {}, None)
        valid = {"output": [{"type": "function_call", "call_id": "c", "name": "run_tests", "arguments": "{}"}]}
        with patch("urllib.request.urlopen", side_effect=[rejected, io.BytesIO(json.dumps(valid).encode())]) as request:
            with patch("time.sleep"):
                provider = OpenAIProvider("issue", "test-model")
                provider.next(None, Budget())
                self.assertEqual(provider.retries, 1)
                self.assertEqual(request.call_count, 2)
        with patch("urllib.request.urlopen", side_effect=TimeoutError) as request:
            with self.assertRaises(RuntimeError):
                OpenAIProvider("issue", "test-model").next(None, Budget())
            self.assertEqual(request.call_count, 1)
