import unittest
from core.decodo_hunter import generate_random_shipping_info


class TestDecodoShippingInfo(unittest.TestCase):
    def test_random_shipping_info_structure(self):
        for _ in range(50):
            info = generate_random_shipping_info()
            self.assertIn("name", info)
            self.assertIn("street", info)
            self.assertIn("city", info)
            self.assertIn("state", info)
            self.assertIn("state_code", info)
            self.assertIn("zip", info)
            self.assertIn("country", info)
            self.assertIn("country_code", info)

            # Verifikasi keseragaman & keaslian alamat Amerika Serikat
            self.assertEqual(info["country"], "United States")
            self.assertEqual(info["country_code"], "US")
            self.assertEqual(len(info["state_code"]), 2)
            self.assertTrue(info["state_code"].isupper())
            self.assertTrue(info["zip"].isdigit() and len(info["zip"]) == 5)
            self.assertTrue(len(info["name"].split()) >= 2)
            self.assertTrue(len(info["street"]) > 3)
            self.assertTrue(len(info["city"]) > 2)


if __name__ == "__main__":
    unittest.main()
