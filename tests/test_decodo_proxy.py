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

    def test_solver_proxy_forwarding_matches_ip_binding(self):
        from unittest.mock import patch, MagicMock
        from core.decodo_hunter import (
            solve_turnstile_via_sidecar,
            solve_hcaptcha_via_sidecar,
            solve_cloudflare_via_sidecar
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "dummy_tok", "solved": True, "cookies": [{"name": "cf_clearance", "value": "xyz"}]}

        proxy_str = "http://45.38.107.97:6014"

        with patch("requests.post", return_value=mock_resp) as mock_post:
            # 1. Turnstile: solved direct (token tidak IP-bound) -> proxy TIDAK dikirim
            tok1 = solve_turnstile_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", "0x4AAAAAA", proxy_str=proxy_str)
            self.assertEqual(tok1, "dummy_tok")
            payload1 = mock_post.call_args[1]["json"]
            self.assertNotIn("proxy", payload1)
            self.assertEqual(payload1["type"], "turnstile")
            self.assertEqual(payload1["timeout_s"], 60)

            # 2. hCaptcha: token terikat IP penyelesai -> proxy HARUS diteruskan
            tok2 = solve_hcaptcha_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", "10000000-ffff-ffff-ffff-000000000001", proxy_str=proxy_str)
            self.assertEqual(tok2, "dummy_tok")
            payload2 = mock_post.call_args[1]["json"]
            self.assertEqual(payload2["proxy"], proxy_str)
            self.assertEqual(payload2["type"], "hcaptcha")
            self.assertEqual(payload2["timeout_s"], 90)

            # 3. Cloudflare clearance: cf_clearance terikat IP proxy -> proxy HARUS diteruskan
            cf_res = solve_cloudflare_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", proxy_str=proxy_str)
            self.assertIsNotNone(cf_res)
            payload3 = mock_post.call_args[1]["json"]
            self.assertEqual(payload3["proxy"], proxy_str)
            self.assertEqual(payload3["type"], "cloudflare")

            # 4. Tanpa proxy: field "proxy" tidak dikirim sama sekali (bukan null/kosong)
            solve_hcaptcha_via_sidecar("http://127.0.0.1:8877", "https://decodo.com", "10000000-ffff-ffff-ffff-000000000001")
            self.assertNotIn("proxy", mock_post.call_args[1]["json"])

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

    def test_handle_hcaptcha_checkout_challenge_inpage_primary(self):
        """Checkout Decodo memakai hCaptcha enterprise: jalur utama = klik checkbox
        ASLI lalu selesaikan challenge di halaman (token di-mint widget asli)."""
        from unittest.mock import MagicMock
        from core.decodo_hunter import handle_hcaptcha_checkout_challenge

        mock_page = MagicMock()
        mock_page.url = "https://dashboard.decodo.com/checkout"

        # Konfirmasi baru muncul SETELAH challenge diselesaikan in-page.
        state = {"solved": False}
        mock_body = MagicMock()

        def body_text():
            if state["solved"]:
                return "Your purchase was successful! Begin proxy setup"
            return "One more step before you're done. Select the checkbox below"

        mock_body.inner_text.side_effect = body_text
        mock_page.locator.return_value = mock_body

        # Frame checkbox asli + frame challenge.
        mock_cb_frame = MagicMock()
        mock_cb_frame.url = "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html#frame=checkbox&sitekey=10000000-ffff-ffff-ffff-000000000001"
        mock_cb_frame.evaluate.return_value = True
        mock_cb = MagicMock()
        mock_cb.count.return_value = 1
        mock_cb.first.is_visible.return_value = True
        mock_cb.first.bounding_box.return_value = {"x": 10, "y": 10, "width": 20, "height": 20}
        mock_cb_frame.locator.return_value = mock_cb

        mock_ch_frame = MagicMock()
        mock_ch_frame.url = "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html#frame=challenge&sitekey=10000000-ffff-ffff-ffff-000000000001"
        mock_ch_frame.evaluate.return_value = True

        mock_page.frames = [mock_cb_frame, mock_ch_frame]

        def fake_inpage_solve(page, solver_url, max_pages=5):
            state["solved"] = True
            return True

        with patch("core.decodo_hunter.solve_hcaptcha_challenge_in_page", side_effect=fake_inpage_solve) as mock_solve:
            res = handle_hcaptcha_checkout_challenge(mock_page, {}, solver_url="http://127.0.0.1:8877", timeout=5)
            self.assertTrue(res)
            self.assertTrue(mock_solve.called, "Jalur utama harus menyelesaikan challenge in-page")
            self.assertTrue(mock_page.mouse.click.called, "Checkbox hCaptcha harus diklik via mouse humanized (page.mouse.click)")
            self.assertTrue(mock_cb.first.bounding_box.called, "Bounding box checkbox harus dibaca untuk gerakan mouse")

    def test_handle_hcaptcha_checkout_challenge_sidecar_fallback(self):
        """Bila jalur in-page gagal, token sidecar dipakai sebagai cadangan."""
        from unittest.mock import MagicMock
        from core.decodo_hunter import handle_hcaptcha_checkout_challenge

        mock_page = MagicMock()
        mock_page.url = "https://dashboard.decodo.com/checkout"
        mock_page.evaluate.return_value = True

        state = {"confirmed": False}
        mock_body = MagicMock()

        def body_text():
            if state["confirmed"]:
                return "Your purchase was successful! Begin proxy setup"
            return "One more step before you're done. Select the checkbox below"

        mock_body.inner_text.side_effect = body_text
        mock_page.locator.return_value = mock_body

        mock_cb_frame = MagicMock()
        mock_cb_frame.url = "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html#frame=checkbox&sitekey=10000000-ffff-ffff-ffff-000000000001"
        mock_cb_frame.evaluate.return_value = True
        mock_cb = MagicMock()
        mock_cb.count.return_value = 1
        mock_cb.first.is_visible.return_value = True
        mock_cb.first.bounding_box.return_value = {"x": 10, "y": 10, "width": 20, "height": 20}
        mock_cb_frame.locator.return_value = mock_cb

        mock_page.frames = [mock_cb_frame]

        def fake_sidecar_token(*args, **kwargs):
            # Token diterima backend -> tandai terkonfirmasi agar loop berhenti sukses.
            state["confirmed"] = True
            return "mock_token"

        with patch("core.decodo_hunter.solve_hcaptcha_challenge_in_page", return_value=False), \
             patch("core.decodo_hunter._wait_for_hcaptcha_challenge", return_value=False), \
             patch("core.decodo_hunter.check_sidecar_health", return_value=True), \
             patch("core.decodo_hunter.solve_hcaptcha_via_sidecar", side_effect=fake_sidecar_token) as mock_sidecar:
            res = handle_hcaptcha_checkout_challenge(mock_page, {}, solver_url="http://127.0.0.1:8877", timeout=5)
            self.assertTrue(res)
            self.assertTrue(mock_sidecar.called, "Jalur cadangan sidecar harus dicoba")

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

    def test_check_sidecar_health_requires_capable_sidecar(self):
        from core.decodo_hunter import check_sidecar_health

        def resp(status_code=200, payload=None):
            m = MagicMock()
            m.status_code = status_code
            m.json.return_value = payload if payload is not None else {}
            return m

        # Sidecar mampu (schema baru + cloakbrowser True) -> sehat
        with patch("core.decodo_hunter.requests.get",
                   return_value=resp(200, {"status": "ok", "deps": {"cloakbrowser": True, "playwright": True}})):
            self.assertTrue(check_sidecar_health("http://127.0.0.1:8877"))

        # Sidecar basi: 200 tetapi tanpa field deps -> TIDAK sehat (kemampuan tak terverifikasi)
        with patch("core.decodo_hunter.requests.get",
                   return_value=resp(200, {"status": "ok", "supported_types": ["hcaptcha"]})):
            self.assertFalse(check_sidecar_health("http://127.0.0.1:8877"))

        # deps ada tetapi cloakbrowser False (interpreter salah) -> TIDAK sehat
        with patch("core.decodo_hunter.requests.get",
                   return_value=resp(200, {"status": "ok", "deps": {"cloakbrowser": False, "playwright": True}})):
            self.assertFalse(check_sidecar_health("http://127.0.0.1:8877"))

        # Status HTTP non-200 -> TIDAK sehat
        with patch("core.decodo_hunter.requests.get", return_value=resp(500, {})):
            self.assertFalse(check_sidecar_health("http://127.0.0.1:8877"))

        # Koneksi gagal -> TIDAK sehat
        with patch("core.decodo_hunter.requests.get", side_effect=Exception("connection refused")):
            self.assertFalse(check_sidecar_health("http://127.0.0.1:8877"))

    def test_solve_hcaptcha_sends_timeout_s_without_proxy(self):
        from core.decodo_hunter import solve_hcaptcha_via_sidecar

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "tok_abc123456"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            tok = solve_hcaptcha_via_sidecar(
                "http://127.0.0.1:8877", "https://decodo.com",
                "10000000-ffff-ffff-ffff-000000000001", timeout=90
            )
            self.assertEqual(tok, "tok_abc123456")
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["timeout_s"], 90)
            self.assertNotIn("proxy", payload)

    def test_ensure_sidecar_running_true_when_deep_health_ok(self):
        from core.decodo_hunter import ensure_sidecar_running
        with patch("core.decodo_hunter.check_sidecar_health", return_value=True):
            self.assertTrue(ensure_sidecar_running("http://127.0.0.1:8877"))


if __name__ == "__main__":
    unittest.main()



