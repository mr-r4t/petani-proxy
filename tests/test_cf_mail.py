import unittest
from unittest.mock import patch, MagicMock
from core.cf_mail import (
    CloudflareMailClient,
    CloudflareMailError,
    extract_verification_link,
    extract_otp_code,
)


class TestCloudflareMail(unittest.TestCase):
    def test_extract_verification_link(self):
        sample_email = """
        Hello from Webshare!
        Please verify your email address by clicking on the link below:
        https://proxy.webshare.io/user/verify-email/abcdef1234567890/
        If you did not create an account, please ignore this email.
        """
        link = extract_verification_link(sample_email)
        self.assertEqual(link, "https://proxy.webshare.io/user/verify-email/abcdef1234567890/")

    def test_extract_verification_link_with_punctuation(self):
        sample_text = "Verify now at (https://dashboard.webshare.io/auth/verify?token=xyz123)."
        link = extract_verification_link(sample_text)
        self.assertEqual(link, "https://dashboard.webshare.io/auth/verify?token=xyz123")

    def test_extract_otp_code(self):
        sample_text = "Your Webshare verification code is 482910. It expires in 10 minutes."
        code = extract_otp_code(sample_text)
        self.assertEqual(code, "482910")

    def test_is_configured(self):
        client = CloudflareMailClient(domains="", worker_url="")
        self.assertFalse(client.is_configured())

        client_configured = CloudflareMailClient(
            domains="domain1.com, domain2.com",
            worker_url="https://inbox.example.workers.dev",
            worker_secret="secret123",
        )
        self.assertTrue(client_configured.is_configured())
        self.assertEqual(client_configured.domains, ["domain1.com", "domain2.com"])

    def test_create_mailbox(self):
        client = CloudflareMailClient(
            domains="mycustom.com",
            worker_url="https://inbox.example.workers.dev",
        )
        email, domain = client.create_mailbox()
        self.assertEqual(domain, "mycustom.com")
        self.assertTrue(email.startswith("ws"))
        self.assertTrue(email.endswith("@mycustom.com"))

    @patch("requests.get")
    def test_get_messages_and_wait_verification(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "address": "ws123@mycustom.com",
            "messages": [
                {
                    "from": "noreply@webshare.io",
                    "subject": "Verify your Webshare account",
                    "body": "Welcome! Verify your email at https://proxy.webshare.io/user/verify-email/tokenABC123",
                    "date": "2026-09-17T15:00:00Z",
                }
            ],
        }
        mock_get.return_value = mock_resp

        client = CloudflareMailClient(
            domains="mycustom.com",
            worker_url="https://inbox.example.workers.dev",
            worker_secret="secret_abc",
        )
        result = client.wait_for_verification("ws123@mycustom.com", timeout=5, poll_interval=1)
        self.assertEqual(result["type"], "link")
        self.assertEqual(result["value"], "https://proxy.webshare.io/user/verify-email/tokenABC123")


if __name__ == "__main__":
    unittest.main()
