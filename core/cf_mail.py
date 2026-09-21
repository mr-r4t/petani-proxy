"""
Cloudflare Email Routing & Worker Inbox Client
----------------------------------------------
Menghubungkan PetaniProxy ke Cloudflare Email Worker untuk menerima
dan mengekstrak tautan aktivasi / kode verifikasi email secara otomatis.

Arsitektur mengadopsi pola Cloudflare Email Routing + KV Worker dari github-farm.
"""

from __future__ import annotations

import json
import os
import random
import re
import string
import time
from typing import Callable, Optional
import requests

_LOCALPART_CHARS = string.ascii_lowercase + string.digits
_LOCALPART_MIN = 8
_LOCALPART_MAX = 12


class CloudflareMailError(RuntimeError):
    pass


def extract_verification_link(text: str) -> Optional[str]:
    """
    Ekstrak tautan verifikasi email Webshare dari teks atau HTML body email.
    Mendukung format tautan proxy.webshare.io / dashboard.webshare.io.
    """
    if not text:
        return None

    # Pola 1: Tautan eksplisit Webshare & Decodo dengan kata verify / confirm / token / activate
    patterns = [
        r'https?://(?:[a-zA-Z0-9-]+\.)*decodo\.com/verify/[^\s"\'<>]*',
        r'https?://(?:[a-zA-Z0-9-]+\.)*decodo\.com/[^\s"\'<>]*(?:verify|confirm|token|activate)[^\s"\'<>]*',
        r'https?://(?:[a-zA-Z0-9-]+\.)*webshare\.io/(?:user/)?verify[^\s"\'<>]*',
        r'https?://(?:[a-zA-Z0-9-]+\.)*webshare\.io/(?:user/)?confirm[^\s"\'<>]*',
        r'https?://(?:[a-zA-Z0-9-]+\.)*webshare\.io/[^\s"\'<>]*(?:verify|confirm|token|activate)[^\s"\'<>]*',
        # Pola 2: URL umum yang memiliki parameter token atau verify-email
        r'https?://[^\s"\'<>]+(?:verify-email|email-verification|confirm-email)[^\s"\'<>]*',
    ]

    for pat in patterns:
        matches = re.findall(pat, text, re.IGNORECASE)
        if matches:
            # Ambil tautan terbersih (tanpa trailing titik atau kurung)
            clean = matches[0].rstrip(").,;")
            return clean

    # Pola 3: Fallback ke URL apapun yang mengarah ke decodo.com atau webshare.io selain homepage/login/terms
    fallback_matches = re.findall(r'https?://(?:[a-zA-Z0-9-]+\.)*(?:webshare\.io|decodo\.com)/[^\s"\'<>]+', text, re.IGNORECASE)
    for url in fallback_matches:
        u_clean = url.rstrip(").,;")
        u_lower = u_clean.lower()
        if not any(skip in u_lower for skip in ["terms", "privacy", "unsubscribe", "login", "register", "help", "support"]):
            return u_clean

    return None


def extract_otp_code(text: str) -> Optional[str]:
    """Ekstrak kode verifikasi angka (4-8 digit) jika ada."""
    if not text:
        return None
    m = re.search(r'\b(?:code|kode|pin|otp)\s*(?:is|adalah|:)?\s*([0-9]{4,8})\b', text, re.IGNORECASE)
    if m:
        return m.group(1)
    
    # Cari 6 digit angka yang berdiri sendiri
    m6 = re.search(r'\b([0-9]{6})\b', text)
    if m6:
        return m6.group(1)
    return None


class CloudflareMailClient:
    """Klien untuk membaca inbox dari Cloudflare Email Worker."""

    def __init__(self, domains: str = "", worker_url: str = "", worker_secret: str = ""):
        self.domains = [d.strip().lower().lstrip("@") for d in (domains or "").split(",") if d.strip()]
        self.worker_url = (worker_url or "").strip().rstrip("/")
        self.worker_secret = (worker_secret or "").strip()
        self._last_email: str = ""

    @classmethod
    def from_config(cls) -> CloudflareMailClient:
        """Membuat instance client dari file konfigurasi settings.json atau environment variables."""
        cf_domains = os.environ.get("CF_DOMAINS") or os.environ.get("WEBSHARE_EMAIL_DOMAIN") or ""
        cf_worker_url = os.environ.get("CF_WORKER_URL") or ""
        cf_worker_secret = os.environ.get("CF_WORKER_SECRET") or ""

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_paths = [
            os.path.join(base_dir, "config", "settings.json"),
            os.path.join(base_dir, "config.json"),
            os.path.join(base_dir, "local_config.json"),
        ]
        for cpath in config_paths:
            if os.path.exists(cpath):
                try:
                    with open(cpath, "r", encoding="utf-8") as f:
                        c = json.load(f)
                        if not cf_domains:
                            cf_domains = c.get("cf_domains") or c.get("custom_email_domain") or ""
                        if not cf_worker_url:
                            cf_worker_url = c.get("cf_worker_url") or ""
                        if not cf_worker_secret:
                            cf_worker_secret = c.get("cf_worker_secret") or ""
                except Exception:
                    pass

        return cls(domains=cf_domains, worker_url=cf_worker_url, worker_secret=cf_worker_secret)

    def is_configured(self) -> bool:
        """Periksa apakah konfigurasi Cloudflare Worker sudah terisi lengkap."""
        return bool(self.domains and self.worker_url.startswith("http"))

    def _check_config(self) -> None:
        if not self.domains:
            raise CloudflareMailError("cf_domains belum diatur (masukkan domain di config/settings.json)")
        if not self.worker_url.startswith("http"):
            raise CloudflareMailError("cf_worker_url belum diatur (URL worker /inbox dibutuhkan)")

    @staticmethod
    def _random_localpart() -> str:
        length = random.randint(_LOCALPART_MIN, _LOCALPART_MAX)
        return "".join(random.choices(_LOCALPART_CHARS, k=length))

    def create_mailbox(self) -> tuple[str, str]:
        """
        Membuat alamat email acak dengan domain Cloudflare yang tersedia.
        Email Routing catch-all otomatis menerima email tanpa registrasi mailbox terlebih dahulu.
        """
        self._check_config()
        domain = random.choice(self.domains)
        email = f"ws{self._random_localpart()}@{domain}"
        self._last_email = email
        return email, domain

    def get_messages(self, address: str) -> list[dict]:
        """Mengambil pesan inbox dari Cloudflare Worker."""
        if not self.worker_url.startswith("http"):
            raise CloudflareMailError("cf_worker_url belum diatur")

        headers = {
            "Accept": "application/json"
        }
        if self.worker_secret:
            headers["X-Worker-Secret"] = self.worker_secret

        try:
            resp = requests.get(
                f"{self.worker_url}/inbox",
                params={"address": address.lower().strip()},
                headers=headers,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise CloudflareMailError(f"Gagal menghubungi Cloudflare Worker: {exc}")

        if resp.status_code == 401:
            raise CloudflareMailError("Cloudflare Worker menolak Secret (401 Unauthorized) — periksa cf_worker_secret")
        if resp.status_code != 200:
            raise CloudflareMailError(f"Cloudflare Worker error HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise CloudflareMailError(f"Response worker bukan format JSON: {exc}")

        if not data.get("ok"):
            raise CloudflareMailError(f"Worker merespon error: {data.get('error', 'unknown')}")

        return data.get("messages") or []

    def wait_for_verification(
        self,
        address: str,
        timeout: int = 120,
        poll_interval: int = 4,
        log: Optional[Callable[[str], None]] = None,
        service_name: str = "Webshare / Decodo",
    ) -> dict:
        """
        Polling Cloudflare Worker sampai email verifikasi tiba.
        Mengembalikan dict:
          {"type": "link", "value": "https://..."} atau
          {"type": "code", "value": "123456"}
        """
        started = time.time()
        attempts = 0

        while time.time() - started < timeout:
            messages = self.get_messages(address)
            attempts += 1

            for msg in messages:
                subject = msg.get("subject", "")
                from_addr = msg.get("from", "")
                body = msg.get("body", "")

                if log:
                    log(f"[*] Cloudflare Mail masuk: dari={from_addr} subjek={subject[:50]}")

                # Cek tautan verifikasi
                link = extract_verification_link(body)
                if link:
                    if log:
                        log(f"[+] Ditemukan tautan aktivasi: {link}")
                    return {"type": "link", "value": link, "message": msg}

                # Cek kode OTP jika link tidak ada
                code = extract_otp_code(body)
                if code:
                    if log:
                        log(f"[+] Ditemukan kode OTP: {code}")
                    return {"type": "code", "value": code, "message": msg}

            elapsed = int(time.time() - started)
            if log and attempts % 2 == 0:
                log(f"[*] Menunggu email verifikasi {service_name} (#{attempts}, {elapsed}s/{timeout}s)...")
            time.sleep(poll_interval)

        raise CloudflareMailError(f"Waktu tunggu email verifikasi {service_name} habis ({timeout}s) untuk {address}")
