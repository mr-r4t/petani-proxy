import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
from core.decodo_hunter import parse_proxy_for_camoufox, format_proxy_display, load_proxy_pool

class TestDecodoProxyParser(unittest.TestCase):
    def test_parse_http_with_auth(self):
        res = parse_proxy_for_camoufox("http://user123:pass123@198.51.100.1:8080")
        self.assertEqual(res, {
            "server": "http://198.51.100.1:8080",
            "username": "user123",
            "password": "pass123"
        })

    def test_parse_socks5_with_auth(self):
        res = parse_proxy_for_camoufox("socks5://user123:pass123@198.51.100.2:1080")
        self.assertEqual(res, {
            "server": "socks5://198.51.100.2:1080",
            "username": "user123",
            "password": "pass123"
        })

    def test_parse_colon_format(self):
        res = parse_proxy_for_camoufox("203.0.113.10:8000:myuser:mypass")
        self.assertEqual(res, {
            "server": "http://203.0.113.10:8000",
            "username": "myuser",
            "password": "mypass"
        })

    def test_parse_simple_ip_port(self):
        res = parse_proxy_for_camoufox("198.51.100.5:8080")
        self.assertEqual(res, {
            "server": "http://198.51.100.5:8080"
        })

    def test_parse_comment_or_empty(self):
        self.assertIsNone(parse_proxy_for_camoufox("# this is comment"))
        self.assertIsNone(parse_proxy_for_camoufox("   "))

    def test_format_proxy_display(self):
        display = format_proxy_display({"server": "http://1.2.3.4:80", "username": "admin", "password": "xyz"})
        self.assertEqual(display, "http://1.2.3.4:80 (Auth: admin:****)")

    def test_load_proxy_pool_from_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("# comment\nhttp://user:pass@1.1.1.1:8080\n\n1.2.3.4:80\n")
            temp_name = f.name

        try:
            pool = load_proxy_pool(temp_name)
            self.assertEqual(len(pool), 2)
            self.assertEqual(pool[0]["server"], "http://1.1.1.1:8080")
            self.assertEqual(pool[1]["server"], "http://1.2.3.4:80")
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_get_decodo_headless_config(self):
        from core.decodo_hunter import get_decodo_headless_config
        # Override should win
        self.assertTrue(get_decodo_headless_config(override=True))
        self.assertFalse(get_decodo_headless_config(override=False))
        # From current config (which is set to False)
        self.assertFalse(get_decodo_headless_config())

    def test_click_start_trial_button_playwright(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import click_start_trial_button

        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_element.is_visible.return_value = True

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_element

        def locator_side_effect(selector):
            if "Start with a trial" in selector:
                return mock_locator
            empty = MagicMock()
            empty.count.return_value = 0
            return empty

        mock_page.locator.side_effect = locator_side_effect
        res = click_start_trial_button(mock_page, timeout=1)
        self.assertTrue(res)
        mock_element.click.assert_called_with(force=True)

    def test_click_start_trial_button_js_fallback(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import click_start_trial_button

        mock_page = MagicMock()
        empty = MagicMock()
        empty.count.return_value = 0
        mock_page.locator.return_value = empty
        mock_page.evaluate.return_value = True

        res = click_start_trial_button(mock_page, timeout=1)
        self.assertTrue(res)
        self.assertTrue(mock_page.evaluate.called)

    def test_generate_random_shipping_info(self):
        from core.decodo_hunter import generate_random_shipping_info
        info = generate_random_shipping_info()
        self.assertIn("name", info)
        self.assertIn("street", info)
        self.assertIn("city", info)
        self.assertIn("state", info)
        self.assertIn("zip", info)
        self.assertIn("country", info)
        self.assertTrue(len(info["name"].split()) >= 2)

    def test_load_solver_url(self):
        from core.decodo_hunter import load_solver_url
        url = load_solver_url()
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("http"))

    def test_fill_shipping_address(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import fill_shipping_address
        mock_page = MagicMock()
        mock_input = MagicMock()
        mock_input.count.return_value = 1
        mock_page.locator.return_value = mock_input

        addr = {
            "name": "Alex Brock",
            "street": "123 Test St",
            "city": "Buffalo",
            "state": "New York",
            "state_code": "NY",
            "zip": "14201",
            "country": "United States",
            "country_code": "US"
        }
        res = fill_shipping_address(mock_page, addr)
        self.assertTrue(res)

    def test_wait_for_checkout_page(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import wait_for_checkout_page

        mock_page = MagicMock()
        mock_el = MagicMock()
        mock_el.is_visible.return_value = True

        mock_loc = MagicMock()
        mock_loc.count.return_value = 1
        mock_loc.first = mock_el

        def locator_effect(sel):
            if "Save shipping information" in sel or "shippingAddress" in sel:
                return mock_loc
            empty = MagicMock()
            empty.count.return_value = 0
            return empty

        mock_page.locator.side_effect = locator_effect
        mock_page.frames = []
        res = wait_for_checkout_page(mock_page, timeout=2)
        self.assertTrue(res)

    def test_solver_functions_never_send_proxy(self):
        from unittest.mock import patch, MagicMock
        from core.decodo_hunter import (
            solve_turnstile_via_sidecar,
            solve_hcaptcha_via_sidecar,
            solve_cloudflare_via_sidecar
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "dummy_tok", "solved": True, "cookies": [{"name": "cf_clearance", "value": "xyz"}]}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            # 1. Turnstile: kirim proxy_str tapi pastikan TIDAK ada di json payload
            tok1 = solve_turnstile_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", "0x4AAAAAA", proxy_str="http://45.38.107.97:6014")
            self.assertEqual(tok1, "dummy_tok")
            call_kwargs1 = mock_post.call_args[1]
            self.assertNotIn("proxy", call_kwargs1["json"])
            self.assertEqual(call_kwargs1["json"]["type"], "turnstile")

            # 2. hCaptcha: kirim proxy_str tapi pastikan TIDAK ada di json payload
            tok2 = solve_hcaptcha_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", "10000000-ffff-ffff-ffff-000000000001", proxy_str="http://45.38.107.97:6014")
            self.assertEqual(tok2, "dummy_tok")
            call_kwargs2 = mock_post.call_args[1]
            self.assertNotIn("proxy", call_kwargs2["json"])
            self.assertEqual(call_kwargs2["json"]["type"], "hcaptcha")

            # 3. Cloudflare clearance: kirim proxy_str tapi pastikan TIDAK ada di json payload
            cf_res = solve_cloudflare_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", proxy_str="http://45.38.107.97:6014")
            self.assertIsNotNone(cf_res)
            call_kwargs3 = mock_post.call_args[1]
            self.assertNotIn("proxy", call_kwargs3["json"])
            self.assertEqual(call_kwargs3["json"]["type"], "cloudflare")

    def test_inject_hcaptcha_token_multiframe(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import inject_hcaptcha_token

        mock_page = MagicMock()
        mock_page.evaluate.return_value = True
        mock_frame = MagicMock()
        mock_frame.evaluate.return_value = True
        mock_page.frames = [mock_frame]

        res = inject_hcaptcha_token(mock_page, "test_token_123")
        self.assertTrue(res)
        self.assertTrue(mock_page.evaluate.called)
        self.assertTrue(mock_frame.evaluate.called)

    def test_handle_hcaptcha_checkout_challenge_success(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import handle_hcaptcha_checkout_challenge

        mock_page = MagicMock()
        mock_page.url = "https://dashboard.decodo.com"
        mock_body = MagicMock()
        # Returns successful message on check
        mock_body.inner_text.side_effect = [
            "Select the checkbox below",
            "Your purchase was successful! Begin proxy setup"
        ]
        mock_page.locator.return_value = mock_body

        mock_frame = MagicMock()
        mock_frame.url = "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html#frame=checkbox&sitekey=10000000-ffff-ffff-ffff-000000000001"
        mock_frame.evaluate.return_value = True
        mock_cb = MagicMock()
        mock_cb.count.return_value = 1
        mock_cb.first.is_visible.return_value = True
        mock_cb.first.bounding_box.return_value = {"x": 10, "y": 10, "width": 20, "height": 20}
        mock_frame.locator.return_value = mock_cb
        mock_fr_el = MagicMock()
        mock_fr_el.bounding_box.return_value = {"x": 100, "y": 200, "width": 300, "height": 80}
        mock_frame.frame_element.return_value = mock_fr_el

        mock_page.frames = [mock_frame]

        with patch("core.decodo_hunter.solve_hcaptcha_via_sidecar", return_value="mock_token"):
            res = handle_hcaptcha_checkout_challenge(mock_page, {}, solver_url="http://127.0.0.1:8877", timeout=5)
            self.assertTrue(res)

    def test_select_http_protocol(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import select_http_protocol

        mock_page = MagicMock()
        mock_page.evaluate.return_value = "HTTP"
        res = select_http_protocol(mock_page)
        self.assertTrue(res)

    def test_copy_all_proxies_via_download_menu(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import copy_all_proxies_via_download_menu

        mock_page = MagicMock()
        mock_dl_btn = MagicMock()
        mock_dl_btn.count.return_value = 1
        mock_dl_btn.nth.return_value.is_visible.return_value = True

        mock_copy_btn = MagicMock()
        mock_copy_btn.count.return_value = 1
        mock_copy_btn.first.is_visible.return_value = True

        def loc_side_effect(sel):
            if "download" in sel or "1/1" in sel or "Export" in sel:
                return mock_dl_btn
            if "Copy" in sel:
                return mock_copy_btn
            m = MagicMock()
            m.count.return_value = 0
            return m

        def eval_side_effect(script):
            if "__decodo_copied_proxies" in script:
                return "http://spfunssurn:pass1@gate.decodo.com:10001\nhttp://spfunssurn:pass1@gate.decodo.com:10002\nhttp://spfunssurn:pass1@gate.decodo.com:10003"
            return True

        mock_page.evaluate.side_effect = eval_side_effect

        proxies = copy_all_proxies_via_download_menu(mock_page)
        self.assertEqual(len(proxies), 3)
        self.assertIn("http://spfunssurn:pass1@gate.decodo.com:10001", proxies)
        self.assertIn("http://spfunssurn:pass1@gate.decodo.com:10002", proxies)
        self.assertIn("http://spfunssurn:pass1@gate.decodo.com:10003", proxies)

    def test_extract_proxies_from_dashboard_multi_line(self):
        from unittest.mock import MagicMock
        from core.decodo_hunter import extract_proxies_from_dashboard

        mock_page = MagicMock()
        # Mock copy_all_proxies_via_download_menu to return 10 proxies
        ten_proxies = [f"http://user:pass@gate.decodo.com:{10000+i}" for i in range(1, 11)]
        with patch("core.decodo_hunter.select_http_protocol", return_value=True):
            with patch("core.decodo_hunter.copy_all_proxies_via_download_menu", return_value=ten_proxies):
                res = extract_proxies_from_dashboard(mock_page)
                self.assertEqual(len(res), 10)
                self.assertEqual(res[0], "http://user:pass@gate.decodo.com:10001")
                self.assertEqual(res[-1], "http://user:pass@gate.decodo.com:10010")


if __name__ == "__main__":
    unittest.main()



