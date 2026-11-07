import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apk_extractor.mcp_server import create_mcp_server


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = create_mcp_server()

    def test_registered_tools(self):
        async def run_check():
            tools = await self.server.list_tools()
            tool_names = [t.name for t in tools]
            expected = [
                "apkx_list_devices",
                "apkx_list_apps",
                "apkx_get_app_info",
                "apkx_pull_and_extract",
                "apkx_get_manifest",
                "apkx_get_endpoints",
                "apkx_get_class_skeleton",
                "apkx_inspect_class",
                "apkx_find_classes",
                "apkx_search_endpoints",
            ]
            for exp in expected:
                self.assertIn(exp, tool_names)

        asyncio.run(run_check())

    def test_get_manifest_readable(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            readable = p / "AndroidManifest_readable.xml"
            readable.write_text("<manifest package='com.test'></manifest>", encoding="utf-8")

            async def run_call():
                # Call tool directly or via call_tool
                res = await self.server.call_tool("apkx_get_manifest", {"target_path": str(p)})
                self.assertIn("com.test", str(res))

            asyncio.run(run_call())

    def test_get_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            ep_file = p / "endpoints.json"
            ep_file.write_text('{"total_urls": 1, "domains": ["api.test.com"]}', encoding="utf-8")

            async def run_call():
                res = await self.server.call_tool("apkx_get_endpoints", {"target_path": str(p)})
                self.assertIn("api.test.com", str(res))

            asyncio.run(run_call())

    def test_find_classes(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            skeleton_file = p / "class_skeleton.json"
            skeleton_file.write_text(
                '{"app_classes": ["com.example.AuthService", "com.example.UserRepository"], "all_classes": []}',
                encoding="utf-8",
            )

            async def run_call():
                res = await self.server.call_tool(
                    "apkx_find_classes", {"target_path": str(p), "query": "auth"}
                )
                self.assertIn("com.example.AuthService", str(res))
                self.assertNotIn("com.example.UserRepository", str(res))

            asyncio.run(run_call())

    def test_search_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            ep_file = p / "endpoints.json"
            ep_file.write_text(
                '{"domains": ["auth.example.com", "cdn.example.com"], "all_endpoints": ["https://auth.example.com/v1/login", "https://cdn.example.com/img.png"]}',
                encoding="utf-8",
            )

            async def run_call():
                res = await self.server.call_tool(
                    "apkx_search_endpoints", {"target_path": str(p), "query": "login"}
                )
                self.assertIn("https://auth.example.com/v1/login", str(res))
                self.assertNotIn("https://cdn.example.com/img.png", str(res))

            asyncio.run(run_call())


if __name__ == "__main__":
    unittest.main()
