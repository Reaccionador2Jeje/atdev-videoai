import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import mcp_http_server


class MCPHTTPProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), mcp_http_server.MCPHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:{}/mcp".format(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post(self, payload, headers=None):
        request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        request = Request(self.url, data=json.dumps(payload).encode(), headers=request_headers)
        with urlopen(request, timeout=3) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None, response.headers

    def test_initialize_returns_mcp_server_metadata(self):
        status, payload, headers = self.post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {
                "name": "test-client", "version": "1.0"
            }},
        })
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "atdev-videoai")
        self.assertEqual(headers.get("MCP-Protocol-Version"), "2025-03-26")

    def test_tools_list_exposes_video_tools(self):
        _, payload, _ = self.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in payload["result"]["tools"]}
        self.assertIn("create_video_project", names)
        self.assertIn("render_video_project", names)
        self.assertIn("list_video_projects", names)
        self.assertIn("get_video_download", names)
        tools = payload["result"]["tools"]
        project_tool = next(tool for tool in tools if tool["name"] == "create_video_project")
        self.assertEqual(project_tool["_meta"]["securitySchemes"][0]["scopes"], ["videoai.write"])

    def test_notification_returns_accepted_without_json_body(self):
        request = Request(
            self.url,
            data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 202)
            self.assertEqual(response.read(), b"")

    def test_get_is_not_supported_for_stateless_endpoint(self):
        request = Request(self.url, method="GET")
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 405)

    def test_wrong_content_type_is_rejected(self):
        request = Request(
            self.url, data=b"{}",
            headers={"Content-Type": "text/plain", "Accept": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 415)


    def test_resources_list_exposes_workspace_ui(self):
        _, payload, _ = self.post({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        resources = payload["result"]["resources"]
        self.assertTrue(any(item["uri"] == "ui://atdev-videoai/workspace/v1.html" for item in resources))

    def test_resources_read_returns_mcp_app_html(self):
        _, payload, _ = self.post({
            "jsonrpc": "2.0", "id": 4, "method": "resources/read",
            "params": {"uri": "ui://atdev-videoai/workspace/v1.html"},
        })
        item = payload["result"]["contents"][0]
        self.assertEqual(item["mimeType"], "text/html;profile=mcp-app")
        self.assertIn("AtDev VideoAI", item["text"])
        self.assertIn("Latest tool result", item["text"])

    def test_video_from_code_tool_references_workspace_ui(self):
        _, payload, _ = self.post({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        tool = next(item for item in payload["result"]["tools"] if item["name"] == "create_video_from_code")
        self.assertEqual(tool["_meta"]["ui"]["resourceUri"], "ui://atdev-videoai/workspace/v1.html")
        self.assertEqual(tool["_meta"]["openai/outputTemplate"], "ui://atdev-videoai/workspace/v1.html")


if __name__ == "__main__":
    unittest.main()
