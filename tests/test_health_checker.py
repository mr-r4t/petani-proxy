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
        import tempfile
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            tf.write("http://usr:pwd@1.2.3.4:8080\n")
            tf_name = tf.name
        try:
            proxies = load_proxies_from_file(tf_name)
            self.assertEqual(len(proxies), 1)
            self.assertEqual(proxies[0]["ip"], "1.2.3.4")
            self.assertEqual(proxies[0]["port"], 8080)
        finally:
            if os.path.exists(tf_name):
                os.remove(tf_name)

    def test_location_resolution(self):
        from core.health_checker import resolve_location
        # 1. Cloudflare loc and colo code
        geo1 = resolve_location(loc_code="GB", colo_code="LHR")
        self.assertEqual(geo1["country_code"], "GB")
        self.assertEqual(geo1["country"], "United Kingdom")
        self.assertEqual(geo1["city"], "London")
        self.assertIn("[GB] United Kingdom (London)", geo1["location_str"])

        # 2. Indonesian datacenter
        geo2 = resolve_location(loc_code="ID", colo_code="CGK")
        self.assertEqual(geo2["country_code"], "ID")
        self.assertEqual(geo2["country"], "Indonesia")
        self.assertEqual(geo2["city"], "Jakarta")

if __name__ == "__main__":
    unittest.main()
