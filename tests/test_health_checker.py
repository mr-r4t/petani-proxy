import os
import unittest
from core.health_checker import parse_proxy_string, load_proxies_from_file

class TestHealthChecker(unittest.TestCase):
    def test_parse_formats(self):
        # 1. Standard protocol with user:pass
        p1 = parse_proxy_string("http://user1:pass1@1.2.3.4:8080")
        self.assertIsNotNone(p1)
        self.assertEqual(p1["ip"], "1.2.3.4")
        self.assertEqual(p1["port"], 8080)
        self.assertEqual(p1["username"], "user1")
        self.assertEqual(p1["password"], "pass1")
        self.assertEqual(p1["protocol"], "http")

        # 2. Plain ip:port
        p2 = parse_proxy_string("10.0.0.1:3128")
        self.assertIsNotNone(p2)
        self.assertEqual(p2["ip"], "10.0.0.1")
        self.assertEqual(p2["port"], 3128)
        self.assertIsNone(p2["username"])

        # 3. ip:port:user:pass format
        p3 = parse_proxy_string("192.168.1.1:8000:admin:secret")
        self.assertIsNotNone(p3)
        self.assertEqual(p3["ip"], "192.168.1.1")
        self.assertEqual(p3["port"], 8000)
        self.assertEqual(p3["username"], "admin")
        self.assertEqual(p3["password"], "secret")

    def test_load_file(self):
        sample_path = "output/webshare_residential.txt"
        if os.path.exists(sample_path):
            proxies = load_proxies_from_file(sample_path)
            self.assertGreater(len(proxies), 0)
            self.assertIn("ip", proxies[0])
            self.assertIn("port", proxies[0])

if __name__ == "__main__":
    unittest.main()
