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

    def test_fill_shipping_address_frame_priority(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import fill_shipping_address

        mock_page = MagicMock()
        mock_page.frames = []

        mock_frame = MagicMock()
        mock_page.frames = [mock_frame]

        # Simulasikan mock_page memiliki element lain, tetapi mock_frame memiliki Field-addressLine1Input
        def page_loc(sel):
            m = MagicMock()
            m.count.return_value = 0
            return m
        mock_page.locator.side_effect = page_loc

        def frame_loc(sel):
            m = MagicMock()
            m.count.return_value = 1
            m.first.is_visible.return_value = True
            m.first.input_value.return_value = "ID"
            return m
        mock_frame.locator.side_effect = frame_loc
        mock_frame.evaluate.return_value = True

        addr = generate_random_shipping_info()
        res = fill_shipping_address(mock_page, addr)
        self.assertTrue(res)
        # Pastikan mock_frame (bukan page) yang dipanggil fill
        self.assertTrue(mock_frame.locator.called)


if __name__ == "__main__":
    unittest.main()

