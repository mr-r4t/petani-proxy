"""
DECODO RESIDENTIAL PROXY HUNTER (CLOAKBROWSER HEADLESS VERSION)
------------------------------------------------------------
Automasi pendaftaran akun Decodo (dahulu Smartproxy) menggunakan
CloakBrowser Stealth Anti-Detect Chromium, verifikasi email via Cloudflare
Worker Inbox, auto-claim free trial Residential Proxy dengan kartu kredit,
serta ekspor proxy HTTP & akun ke folder output.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import random
import re
import requests
import sqlite3
import string
import sys
import time
import uuid
from typing import Optional, List, Dict, Any
from urllib.parse import urlsplit

# Force UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from colorama import Fore, Style
except ImportError:
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = Style = DummyColor()

from core.cf_mail import CloudflareMailClient, CloudflareMailError

# Decodo URLs
DECODO_REGISTER_URL = "https://dashboard.decodo.com/register?page=residential-proxies/pricing"
DECODO_LOGIN_URL = "https://dashboard.decodo.com/login"
DECODO_RESI_URL = "https://dashboard.decodo.com/residential-proxies"
DECODO_PRICING_URL = "https://dashboard.decodo.com/residential-proxies/pricing"
DECODO_BILLING_URL = "https://dashboard.decodo.com/billing"


def find_default_db() -> Optional[str]:
    """Cari lokasi BansosRouter / 9router SQLite database jika ada."""
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(os.path.dirname(current_dir), "eLrouter", "data", "db", "data.sqlite"),
        os.path.join(os.path.dirname(current_dir), "9router-mibp-version", "data", "db", "data.sqlite"),
        os.path.join(current_dir, "..", "eLrouter", "data", "db", "data.sqlite"),
        os.path.join(current_dir, "..", "9router-mibp-version", "data", "db", "data.sqlite"),
        r"d:\FREELANCE\eLrouter\data\db\data.sqlite",
        r"d:\FREELANCE\9router-mibp-version\data\db\data.sqlite"
    ]
    for c in candidates:
        norm = os.path.abspath(c)
        if os.path.exists(norm):
            return norm
    return None


def sync_to_9router(proxy_list: List[str], db_path: Optional[str] = None) -> int:
    """Sinkronisasi proxy HTTP ke database SQLite BansosRouter."""
    target_db = db_path or find_default_db()
    if not target_db or not os.path.exists(target_db):
        return 0
    try:
        conn = sqlite3.connect(target_db)
        cur = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        cur.execute('SELECT data FROM proxyPools')
        existing_urls = set()
        for r in cur.fetchall():
            try:
                d = json.loads(r[0])
                existing_urls.add(d.get('proxyUrl'))
            except Exception:
                pass

        added = 0
        for p in proxy_list:
            if p in existing_urls:
                continue
            m = re.match(r'http://([^:]+):([^@]+)@([^:]+):(\d+)', p)
            if m:
                u, pw, host, port = m.groups()
                p_id = str(uuid.uuid4())
                data_json = json.dumps({
                    'name': f'Decodo Resi ({host}:{port})',
                    'proxyUrl': p,
                    'noProxy': '',
                    'type': 'http',
                    'strictProxy': False,
                    'lastTestedAt': None,
                    'lastError': None
                })
                cur.execute(
                    'INSERT INTO proxyPools (id, isActive, testStatus, data, createdAt, updatedAt) VALUES (?, 1, "unknown", ?, ?, ?)',
                    (p_id, data_json, now, now)
                )
                existing_urls.add(p)
                added += 1
        conn.commit()
        conn.close()
        if added > 0:
            print(f'{Fore.GREEN}[+] {added} Decodo Residential Proxy disinkronkan ke BansosRouter ({target_db})!{Style.RESET_ALL}')
        return added
    except Exception as e:
        print(f'{Fore.RED}[!] Gagal sinkron ke BansosRouter: {e}{Style.RESET_ALL}')
        return 0


def append_to_file(filepath: str, lines: List[str]) -> int:
    """Menambahkan entri baru ke file text secara aman tanpa duplikasi."""
    if not lines:
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    existing = set()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        existing.add(l.strip())
        except Exception:
            pass

    added = 0
    with open(filepath, "a", encoding="utf-8") as f:
        for item in lines:
            item_clean = item.strip()
            if item_clean and item_clean not in existing:
                f.write(item_clean + "\n")
                existing.add(item_clean)
                added += 1
    return added


def parse_proxy_for_camoufox(proxy_str: str) -> Optional[Dict[str, str]]:
    """
    Mengubah format proxy string ke dictionary yang didukung Playwright / Camoufox.
    Format didukung:
    - http://user:pass@host:port
    - socks5://user:pass@host:port
    - host:port:user:pass
    - host:port
    - http://host:port
    - socks5://host:port
    """
    p_str = proxy_str.strip()
    if not p_str or p_str.startswith("#"):
        return None

    try:
        if "://" in p_str:
            parsed = urlsplit(p_str)
            scheme = parsed.scheme or "http"
            server = f"{scheme}://{parsed.hostname}:{parsed.port}"
            res = {"server": server}
            if parsed.username:
                res["username"] = parsed.username
            if parsed.password:
                res["password"] = parsed.password
            return res

        if "@" in p_str:
            return parse_proxy_for_camoufox("http://" + p_str)

        parts = p_str.split(":")
        if len(parts) == 4:
            host, port, u, pw = parts
            return {"server": f"http://{host}:{port}", "username": u, "password": pw}
        elif len(parts) == 2:
            host, port = parts
            return {"server": f"http://{host}:{port}"}
    except Exception:
        pass
    return None


def format_proxy_display(proxy_dict: Dict[str, Any]) -> str:
    """Format proxy untuk tampilan terminal dengan masking credential."""
    server = proxy_dict.get("server", "")
    user = proxy_dict.get("username")
    if user:
        return f"{server} (Auth: {user}:****)"
    return server


def format_proxy_string(proxy_dict: Dict[str, Any]) -> Optional[str]:
    """Format dict proxy ke URL string (scheme://user:pass@host:port).

    Dipakai untuk meneruskan proxy yang SAMA ke sidecar captcha-solver, agar
    cf_clearance yang dipanen terikat ke IP proxy (replayable), bukan IP lokal.
    """
    server = proxy_dict.get("server")
    if not server:
        return None
    user = proxy_dict.get("username")
    pw = proxy_dict.get("password")
    if user and pw:
        scheme, _, host = server.partition("://")
        return f"{scheme or 'http'}://{user}:{pw}@{host}"
    return server


def load_proxy_pool(filepath: Optional[str] = None) -> List[Dict[str, Any]]:
    """Muat daftar proxy dari proxies.txt di root project dan parse untuk Camoufox."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = filepath or os.path.join(base_dir, "proxies.txt")

    if not os.path.exists(target_path):
        return []

    valid_proxies = []
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                parsed = parse_proxy_for_camoufox(line)
                if parsed:
                    valid_proxies.append(parsed)
    except Exception as e:
        print(f"{Fore.RED}[!] Gagal membaca {target_path}: {e}{Style.RESET_ALL}")

    return valid_proxies


def load_decodo_settings() -> Dict[str, Any]:
    """Muat seluruh konfigurasi dari settings.json."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spath = os.path.join(base_dir, "config", "settings.json")
    if os.path.exists(spath):
        try:
            with open(spath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_decodo_headless_config(override: Optional[bool] = None) -> bool:
    """
    Ambil preferensi headless dari config/settings.json (decodo_headless).
    Jika override bernilai boolean (bukan None), gunakan nilai override.
    Default: True (headless).
    """
    if override is not None:
        return bool(override)
    cfg = load_decodo_settings()
    val = cfg.get("decodo_headless")
    if val is not None:
        return bool(val)
    return True


def load_card_config() -> Dict[str, str]:
    """Muat konfigurasi kartu kredit dari settings.json."""
    return load_decodo_settings().get("decodo_card") or {}


def load_solver_url() -> Optional[str]:
    """Muat URL sidecar captcha solver (waguriagentic/captcha-solver) dari config atau env."""
    cfg = load_decodo_settings()
    url = cfg.get("captcha_solver_url") or os.environ.get("CAPTCHA_SOLVER_URL") or "http://127.0.0.1:8877"
    return url.strip().rstrip("/") if url else None


def generate_random_shipping_info() -> Dict[str, str]:
    """Menghasilkan data alamat acak yang asli, seragam, dan valid (United States) untuk formulir checkout Decodo."""
    first_names = [
        "James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Alex",
        "Brock", "Liam", "Noah", "Lucas", "Mason", "Ethan", "Oliver", "Benjamin", "Henry", "Alexander",
        "Samuel", "Daniel", "Matthew", "Jackson", "Sebastian", "Elijah", "Aiden", "Gabriel", "Carter", "Owen"
    ]
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Anderson", "Taylor",
        "Thomas", "Moore", "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Robinson",
        "Clark", "Rodriguez", "Lewis", "Lee", "Walker", "Hall", "Allen", "Young", "Hernandez", "King"
    ]
    first = random.choice(first_names)
    last = random.choice(last_names)

    # 35 Alamat nyata, seragam, dan terverifikasi di Amerika Serikat (US)
    addresses = [
        {"street": "350 5th Ave", "line2": "Ste 100", "city": "New York", "state": "New York", "state_code": "NY", "zip": "10118", "country": "United States", "country_code": "US", "phone": "+12125550143"},
        {"street": "123 Main Street", "line2": "Apt 4B", "city": "Buffalo", "state": "New York", "state_code": "NY", "zip": "14201", "country": "United States", "country_code": "US", "phone": "+17165550182"},
        {"street": "888 Broadway", "line2": "", "city": "New York", "state": "New York", "state_code": "NY", "zip": "10003", "country": "United States", "country_code": "US", "phone": "+12125550199"},
        {"street": "1355 Market St", "line2": "Suite 900", "city": "San Francisco", "state": "California", "state_code": "CA", "zip": "94103", "country": "United States", "country_code": "US", "phone": "+14155550134"},
        {"street": "100 Pine Street", "line2": "Fl 10", "city": "San Francisco", "state": "California", "state_code": "CA", "zip": "94111", "country": "United States", "country_code": "US", "phone": "+14155550167"},
        {"street": "1111 S Figueroa St", "line2": "", "city": "Los Angeles", "state": "California", "state_code": "CA", "zip": "90015", "country": "United States", "country_code": "US", "phone": "+12135550155"},
        {"street": "200 E Santa Clara St", "line2": "", "city": "San Jose", "state": "California", "state_code": "CA", "zip": "95113", "country": "United States", "country_code": "US", "phone": "+14085550122"},
        {"street": "400 Broad St", "line2": "", "city": "Seattle", "state": "Washington", "state_code": "WA", "zip": "98109", "country": "United States", "country_code": "US", "phone": "+12065550176"},
        {"street": "456 Oak Avenue", "line2": "Suite 200", "city": "Seattle", "state": "Washington", "state_code": "WA", "zip": "98101", "country": "United States", "country_code": "US", "phone": "+12065550148"},
        {"street": "742 Evergreen Terrace", "line2": "", "city": "Springfield", "state": "Oregon", "state_code": "OR", "zip": "97477", "country": "United States", "country_code": "US", "phone": "+15415550119"},
        {"street": "233 S Wacker Dr", "line2": "Fl 20", "city": "Chicago", "state": "Illinois", "state_code": "IL", "zip": "60606", "country": "United States", "country_code": "US", "phone": "+13125550162"},
        {"street": "250 Michigan Ave", "line2": "", "city": "Chicago", "state": "Illinois", "state_code": "IL", "zip": "60601", "country": "United States", "country_code": "US", "phone": "+13125550187"},
        {"street": "1001 Avenida De Las Americas", "line2": "", "city": "Houston", "state": "Texas", "state_code": "TX", "zip": "77010", "country": "United States", "country_code": "US", "phone": "+17135550190"},
        {"street": "1500 Marilla St", "line2": "Ste 400", "city": "Dallas", "state": "Texas", "state_code": "TX", "zip": "75201", "country": "United States", "country_code": "US", "phone": "+12145550173"},
        {"street": "301 W 2nd St", "line2": "", "city": "Austin", "state": "Texas", "state_code": "TX", "zip": "78701", "country": "United States", "country_code": "US", "phone": "+15125550188"},
        {"street": "1103 Biscayne Blvd", "line2": "", "city": "Miami", "state": "Florida", "state_code": "FL", "zip": "33132", "country": "United States", "country_code": "US", "phone": "+13055550131"},
        {"street": "400 W Church St", "line2": "Ste 200", "city": "Orlando", "state": "Florida", "state_code": "FL", "zip": "32801", "country": "United States", "country_code": "US", "phone": "+14075550193"},
        {"street": "100 Legends Way", "line2": "", "city": "Boston", "state": "Massachusetts", "state_code": "MA", "zip": "02114", "country": "United States", "country_code": "US", "phone": "+16175550166"},
        {"street": "100 S Independence Mall W", "line2": "", "city": "Philadelphia", "state": "Pennsylvania", "state_code": "PA", "zip": "19106", "country": "United States", "country_code": "US", "phone": "+12155550141"},
        {"street": "100 N 3rd St", "line2": "", "city": "Phoenix", "state": "Arizona", "state_code": "AZ", "zip": "85004", "country": "United States", "country_code": "US", "phone": "+16025550125"},
        {"street": "1701 Mile High Stadium Cir", "line2": "", "city": "Denver", "state": "Colorado", "state_code": "CO", "zip": "80204", "country": "United States", "country_code": "US", "phone": "+13035550159"},
        {"street": "100 Tech Pkwy NW", "line2": "", "city": "Atlanta", "state": "Georgia", "state_code": "GA", "zip": "30313", "country": "United States", "country_code": "US", "phone": "+14045550184"},
        {"street": "3131 Las Vegas Blvd S", "line2": "", "city": "Las Vegas", "state": "Nevada", "state_code": "NV", "zip": "89109", "country": "United States", "country_code": "US", "phone": "+17025550117"},
        {"street": "501 Broadway", "line2": "Ste 100", "city": "Nashville", "state": "Tennessee", "state_code": "TN", "zip": "37203", "country": "United States", "country_code": "US", "phone": "+16155550152"},
        {"street": "400 S Tryon St", "line2": "", "city": "Charlotte", "state": "North Carolina", "state_code": "NC", "zip": "28285", "country": "United States", "country_code": "US", "phone": "+17045550191"},
        {"street": "100 N High St", "line2": "", "city": "Columbus", "state": "Ohio", "state_code": "OH", "zip": "43215", "country": "United States", "country_code": "US", "phone": "+16145550137"},
        {"street": "500 Woodward Ave", "line2": "", "city": "Detroit", "state": "Michigan", "state_code": "MI", "zip": "48226", "country": "United States", "country_code": "US", "phone": "+13135550129"},
        {"street": "100 Washington Ave S", "line2": "Ste 300", "city": "Minneapolis", "state": "Minnesota", "state_code": "MN", "zip": "55401", "country": "United States", "country_code": "US", "phone": "+16125550186"},
        {"street": "111 SW 5th Ave", "line2": "", "city": "Portland", "state": "Oregon", "state_code": "OR", "zip": "97204", "country": "United States", "country_code": "US", "phone": "+15035550144"},
        {"street": "100 S Main St", "line2": "", "city": "Salt Lake City", "state": "Utah", "state_code": "UT", "zip": "84101", "country": "United States", "country_code": "US", "phone": "+18015550170"},
        {"street": "100 E Pratt St", "line2": "", "city": "Baltimore", "state": "Maryland", "state_code": "MD", "zip": "21202", "country": "United States", "country_code": "US", "phone": "+14105550198"},
        {"street": "100 E Wisconsin Ave", "line2": "", "city": "Milwaukee", "state": "Wisconsin", "state_code": "WI", "zip": "53202", "country": "United States", "country_code": "US", "phone": "+14145550163"},
        {"street": "100 N Broadway", "line2": "", "city": "Saint Louis", "state": "Missouri", "state_code": "MO", "zip": "63102", "country": "United States", "country_code": "US", "phone": "+13145550156"},
        {"street": "100 E Main St", "line2": "", "city": "Louisville", "state": "Kentucky", "state_code": "KY", "zip": "40202", "country": "United States", "country_code": "US", "phone": "+15025550123"},
        {"street": "2425 Kalakaua Ave", "line2": "", "city": "Honolulu", "state": "Hawaii", "state_code": "HI", "zip": "96815", "country": "United States", "country_code": "US", "phone": "+18085550180"}
    ]
    addr = random.choice(addresses).copy()
    addr["name"] = f"{first} {last}"
    return addr


def fill_shipping_address(page, addr: Dict[str, str], timeout: int = 15) -> bool:
    """
    Mengisi seluruh bagian formulir 'Save shipping information' pada checkout Decodo.
    1. Mengidentifikasi frame Stripe Address Element secara presisi (berbasis addressLine1).
    2. Mengubah dropdown Negara (Country) -> US terlebih dahulu dengan multi-metode (klik interaktif, select, dan React setter).
    3. Mengisi Full Name secara tangguh (click, fill, keyboard type, dan React native setter).
    4. Mengisi Street, Line2, City, State, dan ZIP dengan timeout singkat dan perlindungan React.
    """
    started = time.time()
    shipping_target = None

    # 1. Deteksi target frame yang memuat input baris alamat (hanya ada di Stripe Address Element)
    while time.time() - started < timeout:
        for t in list(page.frames) + [page]:
            try:
                for sel in [
                    'input#Field-addressLine1Input',
                    'input[placeholder*="Address line 1" i]',
                    'input[name="shippingAddress.line1"]',
                    'input[name="addressLine1"]'
                ]:
                    loc = t.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        shipping_target = t
                        break
                if shipping_target:
                    break
            except Exception:
                pass
        if shipping_target:
            break
        time.sleep(0.1)

    if not shipping_target:
        shipping_target = page

    # Target utama yang diprioritaskan, diikuti fallback target lainnya jika diperlukan
    candidate_targets = [shipping_target]
    for t in list(page.frames) + [page]:
        if t != shipping_target and t not in candidate_targets:
            candidate_targets.append(t)

    try:
        target_country = addr.get("country_code", "US").upper()
        target_country_name = addr.get("country", "United States")

        # 2. PILIH NEGARA (COUNTRY) -> 'United States' ('US')
        # Terapkan multi-strategi berbasis DOM selector-agnostic, leaf-node click, dan verifikasi State options
        country_changed = False

        # Strategi 1: Scan seluruh elemen <select> via JS tanpa mengasumsikan ID/name tertentu
        for t in [shipping_target] + candidate_targets:
            try:
                res = t.evaluate("""(code) => {
                    const allSelects = Array.from(document.querySelectorAll('select'));
                    for (const sel of allSelects) {
                        let usIdx = -1;
                        if (!sel.options) continue;
                        for (let i = 0; i < sel.options.length; i++) {
                            const opt = sel.options[i];
                            const val = (opt.value || '').toUpperCase();
                            const txt = (opt.text || opt.innerText || '').toLowerCase();
                            if (val === code.toUpperCase() || txt.includes('united states')) {
                                usIdx = i;
                                break;
                            }
                        }
                        if (usIdx >= 0) {
                            sel.focus();
                            sel.selectedIndex = usIdx;
                            const targetVal = sel.options[usIdx].value;
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
                            if (setter) {
                                setter.call(sel, targetVal);
                            } else {
                                sel.value = targetVal;
                            }
                            const tracker = sel._valueTracker;
                            if (tracker) {
                                tracker.setValue('__force_diff__');
                            }
                            sel.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                            sel.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                            sel.dispatchEvent(new UIEvent('change', { bubbles: true, composed: true }));
                            sel.blur();
                            return true;
                        }
                    }
                    return false;
                }""", target_country)
                if res:
                    country_changed = True
                    break
            except Exception:
                pass

        # Strategi 2: Playwright native select_option pada elemen select
        for t in [shipping_target] + candidate_targets:
            try:
                c_sels = t.locator('select#Field-countryInput, select[name*="country" i], select[autocomplete*="country" i], select')
                if c_sels.count() > 0:
                    for s_idx in range(min(c_sels.count(), 3)):
                        sel_elem = c_sels.nth(s_idx)
                        try:
                            sel_elem.select_option(value=target_country, timeout=1000)
                            country_changed = True
                            break
                        except Exception:
                            try:
                                sel_elem.select_option(label=target_country_name, timeout=1000)
                                country_changed = True
                                break
                            except Exception:
                                pass
                if country_changed:
                    break
            except Exception:
                pass

        # Strategi 3: Leaf-node click pada elemen teks 'Indonesia' (jika custom combobox / dropdown UI)
        for t in [shipping_target] + candidate_targets:
            try:
                clicked = t.evaluate("""() => {
                    const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
                        if (['OPTION', 'SCRIPT', 'STYLE', 'HEAD', 'BODY', 'HTML'].includes(el.tagName)) return false;
                        const txt = (el.innerText || el.value || '').trim();
                        if (txt === 'Indonesia' || (txt.startsWith('Indonesia') && txt.length < 25)) {
                            const hasMatchingChild = Array.from(el.children).some(child => {
                                const ctxt = (child.innerText || child.value || '').trim();
                                return ctxt === 'Indonesia' || (ctxt.startsWith('Indonesia') && ctxt.length < 25);
                            });
                            return !hasMatchingChild;
                        }
                        return false;
                    });
                    if (candidates.length > 0) {
                        candidates[0].scrollIntoView({ block: 'center', inline: 'center' });
                        candidates[0].click();
                        return true;
                    }
                    return false;
                }""")
                if clicked:
                    time.sleep(0.3)
                    us_opts = t.locator(':is([role="option"], option, li, button, div, span):has-text("United States")')
                    if us_opts.count() > 0:
                        for u_idx in range(us_opts.count()):
                            u_el = us_opts.nth(u_idx)
                            if u_el.is_visible():
                                u_el.click(force=True)
                                country_changed = True
                                time.sleep(0.3)
                                break
                    if not country_changed:
                        srch = t.locator('input[placeholder*="Search" i], input[type="search"]')
                        if srch.count() > 0 and srch.first.is_visible():
                            srch.first.fill(target_country_name, timeout=800)
                            time.sleep(0.2)
                            t.keyboard.press("Enter")
                            country_changed = True
                    if country_changed:
                        break
            except Exception:
                pass

        # Strategi 4: Autocomplete input jika country dirender sebagai input
        if not country_changed:
            for t in [shipping_target] + candidate_targets:
                try:
                    c_inp = t.locator('input#Field-countryInput, input[name*="country" i], input[placeholder*="Country" i], input[role="combobox"]')
                    if c_inp.count() > 0 and c_inp.first.is_visible():
                        c_inp.first.click(force=True)
                        t.keyboard.press("Control+A")
                        t.keyboard.press("Backspace")
                        t.keyboard.type(target_country_name, delay=20)
                        time.sleep(0.2)
                        t.keyboard.press("Enter")
                        country_changed = True
                        break
                except Exception:
                    pass

        # Verifikasi & Tunggu Stripe me-render ulang field alamat (State & ZIP US)
        # Settle check: periksa opsi administrativeArea (apakah sudah memuat State US seperti California/Ohio/CA/OH)
        for _ in range(20):
            time.sleep(0.1)
            try:
                is_settled = shipping_target.evaluate("""() => {
                    const adminSel = document.querySelector('select#Field-administrativeAreaInput') ||
                                     document.querySelector('select[name="administrativeArea"]') ||
                                     document.querySelector('select[name="state"]');
                    if (adminSel && adminSel.options) {
                        for (let i = 0; i < adminSel.options.length; i++) {
                            const txt = (adminSel.options[i].text || '').toLowerCase();
                            const val = (adminSel.options[i].value || '').toUpperCase();
                            if (txt.includes('california') || txt.includes('ohio') || val === 'CA' || val === 'OH' || val === 'NY') {
                                return true;
                            }
                        }
                    }
                    const cSel = document.querySelector('select#Field-countryInput');
                    if (cSel && (cSel.value === 'US' || (cSel.selectedOptions && cSel.selectedOptions[0]?.value === 'US'))) {
                        return true;
                    }
                    return false;
                }""")
                if is_settled:
                    break
            except Exception:
                pass

        # 3. FULL NAME
        # Isi langsung di shipping_target dengan click, fill, type, dan React native setter
        name_filled = False
        name_val = addr["name"]

        for t in [shipping_target] + candidate_targets:
            try:
                name_loc = t.locator('input[placeholder*="Full name" i], input#Field-nameInput, input[name="shippingAddress.name"], input[autocomplete="name"]')
                if name_loc.count() > 0 and name_loc.first.is_visible():
                    name_loc.first.scroll_into_view_if_needed(timeout=500)
                    name_loc.first.click(force=True)
                    time.sleep(0.1)
                    name_loc.first.fill(name_val, timeout=2000)

                    # Jika value belum tercermin (React controlled component), gunakan keyboard typing
                    try:
                        curr_name = name_loc.first.input_value()
                    except Exception:
                        curr_name = ""
                    if not curr_name:
                        name_loc.first.click(force=True)
                        t.keyboard.press("Control+A")
                        t.keyboard.press("Backspace")
                        t.keyboard.type(name_val, delay=15)
                        try:
                            curr_name = name_loc.first.input_value()
                        except Exception:
                            curr_name = ""

                    # Gunakan React native setter untuk menjamin state React ter-update
                    try:
                        t.evaluate("""([val]) => {
                            const el = document.querySelector('input[placeholder*="Full name" i]') || 
                                       document.querySelector('input#Field-nameInput') || 
                                       document.querySelector('input[name="shippingAddress.name"]');
                            if (el) {
                                el.focus();
                                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                if (setter) {
                                    setter.call(el, val);
                                } else {
                                    el.value = val;
                                }
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.blur();
                                return true;
                            }
                            return false;
                        }""", [name_val])
                    except Exception:
                        pass

                    name_filled = True
                    break
            except Exception:
                pass

        # 4. STREET ADDRESS (ADDRESS LINE 1)
        street_filled = False
        for t in [shipping_target] + candidate_targets:
            try:
                st_loc = t.locator('input#Field-addressLine1Input, input[placeholder*="Address line 1" i], input[placeholder*="Street address" i], input[name="addressLine1"], input[name="shippingAddress.line1"]')
                if st_loc.count() > 0 and st_loc.first.is_visible():
                    st_loc.first.scroll_into_view_if_needed(timeout=500)
                    st_loc.first.click(force=True)
                    st_loc.first.fill(addr["street"], timeout=2000)
                    street_filled = True
                    break
            except Exception:
                pass

        # 5. ADDRESS LINE 2 (OPSIONAL)
        if addr.get("line2"):
            for t in [shipping_target] + candidate_targets:
                try:
                    l2_loc = t.locator('input#Field-addressLine2Input, input[placeholder*="Address line 2" i], input[name="addressLine2"]')
                    if l2_loc.count() > 0 and l2_loc.first.is_visible():
                        l2_loc.first.fill(addr["line2"], timeout=2000)
                        break
                except Exception:
                    pass

        # 6. CITY
        city_filled = False
        for t in [shipping_target] + candidate_targets:
            try:
                ct_loc = t.locator('input#Field-localityInput, input[placeholder*="City" i], input[name="city"], input[name="shippingAddress.city"]')
                if ct_loc.count() > 0 and ct_loc.first.is_visible():
                    ct_loc.first.scroll_into_view_if_needed(timeout=500)
                    ct_loc.first.click(force=True)
                    ct_loc.first.fill(addr["city"], timeout=2000)
                    city_filled = True
                    break
            except Exception:
                pass

        # 7. STATE / PROVINCE
        state_filled = False
        target_state_code = addr.get("state_code", "OH")
        target_state_name = addr.get("state", "Ohio")

        for t in [shipping_target] + candidate_targets:
            try:
                s_loc = t.locator('select#Field-administrativeAreaInput, select[name="administrativeArea"], select[name="shippingAddress.state"], select[name="state"], select[name="province"]')
                if s_loc.count() > 0 and s_loc.first.is_visible():
                    try:
                        s_loc.first.select_option(value=target_state_code, timeout=1200)
                        state_filled = True
                    except Exception:
                        try:
                            s_loc.first.select_option(label=target_state_name, timeout=1200)
                            state_filled = True
                        except Exception:
                            pass

                    # Fallback JS React setter untuk dropdown State / Province
                    if not state_filled:
                        try:
                            res = t.evaluate("""([code, name]) => {
                                const el = document.querySelector('select#Field-administrativeAreaInput') || 
                                           document.querySelector('select[name="administrativeArea"]') ||
                                           document.querySelector('select[name="province"]');
                                if (!el || !el.options || el.options.length <= 1) return false;
                                let chosenIdx = -1;
                                for (let i = 0; i < el.options.length; i++) {
                                    const opt = el.options[i];
                                    if (opt.value.toUpperCase() === code.toUpperCase() || 
                                        opt.text.toLowerCase().includes(name.toLowerCase())) {
                                        chosenIdx = i;
                                        break;
                                    }
                                }
                                if (chosenIdx === -1 && el.options.length > 1) {
                                    chosenIdx = 1; // Fallback ke opsi pertama jika mode dropdown non-US
                                }
                                if (chosenIdx >= 0) {
                                    el.selectedIndex = chosenIdx;
                                    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
                                    if (setter) {
                                        setter.call(el, el.options[chosenIdx].value);
                                    } else {
                                        el.value = el.options[chosenIdx].value;
                                    }
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    return true;
                                }
                                return false;
                            }""", [target_state_code, target_state_name])
                            if res:
                                state_filled = True
                        except Exception:
                            pass

                if state_filled:
                    break
            except Exception:
                pass

        # Fallback jika State berupa text input
        if not state_filled:
            for t in [shipping_target] + candidate_targets:
                try:
                    s_inp = t.locator('input#Field-administrativeAreaInput, input[name="administrativeArea"], input[placeholder*="State" i], input[placeholder*="Province" i]')
                    if s_inp.count() > 0 and s_inp.first.is_visible():
                        s_inp.first.fill(addr["state"], timeout=2000)
                        state_filled = True
                        break
                except Exception:
                    pass

        # 8. POSTAL CODE / ZIP
        zip_filled = False
        target_zip = addr.get("zip", "43215")

        for t in [shipping_target] + candidate_targets:
            try:
                z_loc = t.locator('input#Field-postalCodeInput, input[placeholder*="ZIP" i], input[placeholder*="Postal" i], input[name="postalCode"]')
                if z_loc.count() > 0 and z_loc.first.is_visible():
                    z_loc.first.scroll_into_view_if_needed(timeout=500)
                    z_loc.first.click(force=True)
                    z_loc.first.fill(target_zip, timeout=2000)
                    zip_filled = True
                    break
            except Exception:
                pass

        # Fallback JS React setter untuk ZIP
        if not zip_filled:
            try:
                res = shipping_target.evaluate("""(val) => {
                    const el = document.querySelector('input#Field-postalCodeInput') ||
                               document.querySelector('input[placeholder*="ZIP" i]') ||
                               document.querySelector('input[placeholder*="Postal" i]');
                    if (el) {
                        el.focus();
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                        if (setter) {
                            setter.call(el, val);
                        } else {
                            el.value = val;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.blur();
                        return true;
                    }
                    return false;
                }""", target_zip)
                if res:
                    zip_filled = True
            except Exception:
                pass

        # 9. PHONE (OPSIONAL)
        if addr.get("phone"):
            for t in [shipping_target] + candidate_targets:
                try:
                    p_loc = t.locator('input#Field-phoneInput, input[placeholder*="Phone" i], input[name="phone"]')
                    if p_loc.count() > 0 and p_loc.first.is_visible():
                        p_loc.first.fill(addr["phone"], timeout=2000)
                        break
                except Exception:
                    pass

        valid = bool(name_filled and street_filled)
        if not valid:
            valid = bool(name_filled or street_filled or state_filled or city_filled)
        return valid
    except Exception as e:
        print(f"  {Fore.YELLOW}[!] Peringatan isi shipping address: {e}{Style.RESET_ALL}")
        return False


def check_sidecar_health(solver_url: str) -> bool:
    """Periksa apakah sidecar aktif DAN mampu menyelesaikan captcha (bukan sekadar hidup).

    Health check dangkal (status_code == 200) berbahaya: sidecar basi yang dijalankan
    dengan interpreter tanpa cloakbrowser tetap membalas 200, tetapi tidak akan pernah
    bisa menyelesaikan captcha -> hunt macet diam-diam tanpa error. Karena itu payload
    /health diverifikasi: status == ok dan deps.cloakbrowser == True. Build lama yang
    tidak mengirim field `deps` dianggap TIDAK sehat karena kemampuannya tak terverifikasi.
    """
    try:
        resp = requests.get(f"{solver_url.rstrip('/')}/health", timeout=3.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if not isinstance(data, dict) or data.get("status") != "ok":
            return False
        deps = data.get("deps")
        if not isinstance(deps, dict):
            # Schema lama tanpa `deps` -> sidecar build basi, treat as down.
            return False
        return bool(deps.get("cloakbrowser"))
    except Exception:
        return False


def sidecar_supports_grid_pick(solver_url: str) -> bool:
    """True bila sidecar mengekspos endpoint vision grid-pick untuk hCaptcha in-page.

    Dipakai untuk mendeteksi build sidecar BASI yang sudah hidup di port lokal:
    build lama lolos health-check cloakbrowser tetapi tidak punya /hcaptcha/grid_pick,
    sehingga puzzle checkout akan diam-diam jatuh ke penyelesaian manual (=> 0 proxy
    pada run tanpa pengawasan). Caller harus restart sidecar lokal semacam itu.
    """
    try:
        resp = requests.get(f"{solver_url.rstrip('/')}/health", timeout=3.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if not isinstance(data, dict):
            return False
        return "hcaptcha_grid_pick" in (data.get("features") or [])
    except Exception:
        return False


def _sidecar_python() -> str:
    """Pilih interpreter yang memiliki dependensi sidecar: venv project > sys.executable."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in (
        os.path.join(".venv", "Scripts", "python.exe"),   # Windows
        os.path.join(".venv", "bin", "python"),           # POSIX
    ):
        cand = os.path.join(base_dir, rel)
        if os.path.exists(cand):
            return cand
    return sys.executable


def _kill_stale_sidecar_on_port(solver_url: str) -> bool:
    """Bebaskan port sidecar lokal dari proses Python basi (sidecar build lama).

    Sidecar lama yang masih memegang port membuat proses baru gagal bind -> hunt
    berjalan tanpa solver. Hanya proses bernama python/pythonw yang dimatikan agar
    proses lain di port tersebut tidak tersentuh.
    """
    if sys.platform != "win32":
        return False
    try:
        port = urlsplit(solver_url).port or 8877
    except Exception:
        port = 8877
    try:
        import subprocess
        flags = subprocess.CREATE_NO_WINDOW
        net = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10, creationflags=flags
        )
        pids = set()
        for line in (net.stdout or "").splitlines():
            parts = line.split()
            if (len(parts) >= 5 and parts[0].upper() == "TCP"
                    and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING"):
                pids.add(parts[4])
        killed = False
        for pid in pids:
            tl = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10, creationflags=flags
            )
            name = (tl.stdout or "").strip().strip('"').split('","')[0].strip('"').lower()
            if "python" in name:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, text=True, timeout=10, creationflags=flags
                )
                print(f"  {Fore.YELLOW}[!] Sidecar basi (PID {pid}, {name}) dibersihkan dari port {port}.{Style.RESET_ALL}")
                killed = True
        return killed
    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info bersihkan port sidecar: {e}{Style.RESET_ALL}")
        return False


def ensure_sidecar_running(solver_url: str = "http://127.0.0.1:8877") -> bool:
    """Pastikan sidecar lokal aktif & mampu solve; bersihkan yang basi lalu spawn bila perlu."""
    is_local = ("127.0.0.1" in solver_url) or ("localhost" in solver_url)

    if check_sidecar_health(solver_url):
        # Sidecar lokal yang HIDUP tetapi tidak punya grid-pick = build basi: restart
        # agar hCaptcha checkout tidak diam-diam jatuh ke penyelesaian manual.
        if not is_local or sidecar_supports_grid_pick(solver_url):
            return True
        print(f"  {Fore.YELLOW}[!] Sidecar lokal basi (tanpa grid-pick) — me-restart...{Style.RESET_ALL}")
        _kill_stale_sidecar_on_port(solver_url)
        time.sleep(1)

    if is_local:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        server_py = os.path.join(base_dir, "captcha-solver", "server.py")
        if os.path.exists(server_py):
            # Sidecar basi (mis. build lama tanpa cloakbrowser) sering masih memegang
            # port -> proses baru gagal bind. Bersihkan dulu sebelum spawn.
            _kill_stale_sidecar_on_port(solver_url)
            try:
                print(f"  {Fore.CYAN}[*] Memulai sidecar captcha-solver lokal ({solver_url}) di background...{Style.RESET_ALL}")
                import subprocess
                py = _sidecar_python()
                subprocess.Popen(
                    [py, server_py],
                    cwd=os.path.join(base_dir, "captcha-solver"),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                for _ in range(25):
                    time.sleep(1)
                    if check_sidecar_health(solver_url):
                        print(f"  {Fore.GREEN}✓ Sidecar captcha-solver siap & mampu solve ({solver_url})!{Style.RESET_ALL}")
                        return True
                print(f"  {Fore.YELLOW}[!] Sidecar belum siap setelah 25 detik — hunt lanjut TANPA solver sidecar.{Style.RESET_ALL}")
            except Exception as e:
                print(f"  {Fore.YELLOW}[!] Gagal auto-start sidecar: {e}{Style.RESET_ALL}")
    return False


def solve_turnstile_via_sidecar(
    solver_url: str,
    page_url: str,
    sitekey: str,
    proxy_str: Optional[str] = None,
    timeout: int = 60
) -> Optional[str]:
    """Mengirim request penyelesaian Cloudflare Turnstile ke HTTP sidecar waguriagentic/captcha-solver (direct tanpa proxy).

    `timeout_s` dikirim eksplisit agar deadline di server sidecar sama dengan timeout
    klien — tanpa itu sidecar memakai default-nya sendiri dan solve lambat bisa
    melewati batas waktu klien sehingga hunt menggantung tanpa token.
    """
    try:
        endpoint = f"{solver_url.rstrip('/')}/solve"
        # Sesuai instruksi: Solver dijalankan langsung (direct local), TIDAK melalui proxy
        payload = {
            "type": "turnstile",
            "url": page_url,
            "sitekey": sitekey,
            "timeout_s": int(timeout)
        }

        resp = requests.post(endpoint, json=payload, timeout=timeout + 20)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token") or data.get("response") or data.get("solution")
    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info sidecar turnstile solver: {e}{Style.RESET_ALL}")
    return None


def inject_turnstile_token(page, token: str) -> bool:
    """Injeksi token Turnstile hasil sidecar ke dalam form DOM."""
    try:
        return page.evaluate('''(token) => {
            let injected = false;
            const els = document.querySelectorAll('input[name="cf-turnstile-response"]');
            els.forEach(el => {
                el.value = token;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                injected = true;
            });
            return injected;
        }''', token)
    except Exception:
        return False


def solve_hcaptcha_via_sidecar(
    solver_url: str,
    page_url: str,
    sitekey: str,
    proxy_str: Optional[str] = None,
    timeout: int = 90
) -> Optional[str]:
    """Mengirim request penyelesaian hCaptcha ke HTTP sidecar waguriagentic/captcha-solver.

    `timeout_s` dikirim eksplisit agar deadline global di server sidecar sama dengan
    timeout klien — puzzle gambar yang butuh vision tidak diputus dini oleh default 60s.

    `proxy_str` diteruskan agar token hCaptcha dicetak dari IP proxy yang SAMA dengan
    browser yang memakainya. hCaptcha mengikat token ke IP penyelesai, sehingga token
    yang dibuat dari IP lokal akan DITOLAK oleh Decodo (IP-bound mismatch).
    """
    try:
        endpoint = f"{solver_url.rstrip('/')}/solve"
        payload = {
            "type": "hcaptcha",
            "url": page_url,
            "sitekey": sitekey,
            "timeout_s": int(timeout)
        }
        # Token hCaptcha terikat ke IP penyelesai: teruskan proxy yang sama dengan browser
        # agar token tetap valid saat dipakai submit dari browser ber-proxy itu.
        if proxy_str:
            payload["proxy"] = proxy_str

        resp = requests.post(endpoint, json=payload, timeout=timeout + 20)
        if resp.status_code == 200:
            data = resp.json()
            cand = data.get("token") or data.get("response") or data.get("solution")
            if cand and isinstance(cand, str) and cand != "[object Object]" and not cand.startswith("{") and len(cand) > 5:
                return cand
    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info sidecar captcha solver: {e}{Style.RESET_ALL}")
    return None


def inject_hcaptcha_token(page, token: str) -> bool:
    """Injeksi token hasil solver ke dalam elemen respons hCaptcha di DOM, trigger callback, dan kirim postMessage ke semua frames."""
    injected_any = False
    targets = [page] + list(page.frames)
    for target in targets:
        try:
            inj = target.evaluate('''(token) => {
                let injected = false;
                // 1. Isi elemen form response (pakai native setter agar React onChange terpicu)
                const selectors = ['[name="h-captcha-response"]', '[name="g-recaptcha-response"]', 'textarea[name*="h-captcha"]', 'textarea[name*="hcaptcha"]'];
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(el => {
                        try {
                            const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                            setter.call(el, token);
                        } catch(e) { el.value = token; }
                        try { el.innerHTML = token; } catch(e) {}
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        injected = true;
                    });
                }

                // 2. Tandai checkbox iframe jika ada
                const cb = document.getElementById("checkbox") || document.querySelector('[role="checkbox"]');
                if (cb) {
                    cb.setAttribute("aria-checked", "true");
                    cb.classList.add("checked");
                    injected = true;
                }

                // 3. Paksa API runtime hcaptcha mengembalikan token (banyak SPA membaca via ini)
                if (window.hcaptcha) {
                    try { window.hcaptcha.getResponse = function() { return token; }; injected = true; } catch(e){}
                    if (typeof window.hcaptcha.setResponse === 'function') {
                        try { window.hcaptcha.setResponse(token); injected = true; } catch(e){}
                    }
                    if (typeof window.hcaptcha.setData === 'function') {
                        try { window.hcaptcha.setData({ response: token }); injected = true; } catch(e){}
                    }
                }

                // 4. Trigger callback via data-callback
                const containers = document.querySelectorAll('[data-callback], [data-sitekey], .h-captcha');
                containers.forEach(c => {
                    const cbName = c.getAttribute('data-callback');
                    if (cbName && typeof window[cbName] === 'function') {
                        try { window[cbName](token); injected = true; } catch(e){}
                    }
                });

                // 5. Trigger postMessage untuk Stripe Radar / parent listeners
                try {
                    const msgData = { source: "hcaptcha", label: "challenge-closed", token: token };
                    window.postMessage(msgData, "*");
                    window.postMessage(JSON.stringify(msgData), "*");
                    if (window.parent && window.parent !== window) {
                        window.parent.postMessage(msgData, "*");
                        window.parent.postMessage(JSON.stringify(msgData), "*");
                    }
                } catch(e){}

                return injected;
            }''', token)
            if inj:
                injected_any = True
        except Exception:
            pass
    return injected_any


# ── In-page hCaptcha challenge solver (enterprise sitekeys) ──────────
# Decodo's checkout uses an enterprise hCaptcha whose token is bound to the page's
# signed `rqdata` + session, so a token minted by the sidecar's OWN browser is rejected
# by Decodo's backend and the modal hangs forever (=> 0 proxies). We therefore solve
# the challenge INSIDE the real page: capture the canvas, ask the sidecar's vision
# backend for numbered-grid picks, click those cells with real OS-level mouse events,
# and let the REAL widget mint the token. Falls back to human solving in headful mode.

_HCAP_GRID = 3

_HCAP_META_JS = """() => {
    const promptEl = document.querySelector('.prompt-text, .challenge-header, h2, .task-prompt');
    let task = promptEl ? (promptEl.innerText || '').trim() : '';
    if (!task) {
        const txt = document.body.innerText || '';
        const lines = txt.split('\\n').map(l => l.trim()).filter(l => l.length > 5);
        task = lines.find(l =>
            !l.includes('try again') && !l.match(/^(Skip|Verify|Next|EN)$/i)
        ) || '';
    }
    const taskImages = Array.from(document.querySelectorAll('.task-image, [aria-label*="Image"], .cell'));
    const canvas = document.querySelector('canvas');
    let gridCount = taskImages.length;
    let gridDim = 3;
    if (gridCount === 16) {
        gridDim = 4;
    } else if (gridCount === 9) {
        gridDim = 3;
    } else if (canvas) {
        const hasDrag = /^drag\\b/i.test(task) || /help the (creature|monkey|robot|character)/i.test(task);
        gridDim = hasDrag ? 4 : 3;
    }
    const btn = document.querySelector('.button-submit, [data-cy="button-submit"], button[title*="Next"], button[title*="Verify"]');
    const isDrag = /^drag\\b/i.test(task) || /help the (creature|monkey|robot|character)/i.test(task);
    return {
        target: task,
        hasTiles: taskImages.length > 0,
        hasCanvas: !!canvas,
        tileCount: taskImages.length,
        gridDim: gridDim,
        isDrag: isDrag,
        buttonText: btn ? (btn.innerText || '').trim() : '',
    };
}"""

_HCAP_CANVAS_JS = """() => {
    const c = document.querySelector('canvas');
    if (!c) return '';
    try { return c.toDataURL('image/png').split(',')[1]; } catch(e) { return ''; }
}"""


def _find_hcaptcha_challenge_frame(page):
    """Frame hosting the hCaptcha image challenge (#frame=challenge), or None."""
    for f in page.frames:
        u = f.url or ""
        if "#frame=challenge" in u and "hcaptcha" in u:
            return f
    return None


def _hcap_meta(fr) -> Dict[str, Any]:
    try:
        return fr.evaluate(_HCAP_META_JS) or {}
    except Exception:
        return {}


def _hcap_canvas_b64(page) -> str:
    """Base64 PNG of the challenge grid, supporting both DOM image tiles and canvas."""
    fr = _find_hcaptcha_challenge_frame(page)
    ordered = []
    if fr:
        ordered += [fr, *fr.child_frames]
    ordered += [f for f in page.frames if f not in ordered]
    for f in ordered:
        try:
            # 1. Prioritaskan screenshot elemen grid tantangan (bekerja untuk DOM tiles .task-image maupun canvas)
            for sel in ['.task-grid', '.challenge-view', '.challenge-container', 'canvas', 'body']:
                loc = f.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    img_bytes = loc.first.screenshot(type="png", timeout=3000)
                    if img_bytes and len(img_bytes) > 500:
                        return base64.b64encode(img_bytes).decode("ascii")
        except Exception:
            pass
        try:
            b64 = f.evaluate(_HCAP_CANVAS_JS)
            if b64:
                return b64
        except Exception:
            continue
    return ""


def _hcap_canvas_box(page) -> Optional[Dict[str, float]]:
    """Bounding box of the challenge canvas or grid, preferring the challenge frame."""
    fr = _find_hcaptcha_challenge_frame(page)
    ordered = []
    if fr:
        ordered += [fr, *fr.child_frames]
    ordered += [f for f in page.frames if f not in ordered]
    for f in ordered:
        for sel in ["canvas", ".task-grid", ".challenge-view"]:
            try:
                loc = f.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    box = loc.first.bounding_box()
                    if box:
                        return box
            except Exception:
                continue
    return None


def _sidecar_grid_pick(solver_url: str, image_b64: str, target: str,
                       mode: str = "click", grid: int = _HCAP_GRID,
                       timeout: int = 60) -> List[int]:
    """Ask the sidecar's vision backend which numbered-grid cells satisfy the task."""
    try:
        endpoint = f"{solver_url.rstrip('/')}/hcaptcha/grid_pick"
        payload = {"image_b64": image_b64, "target": target or "",
                   "grid": grid, "mode": mode}
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        if resp.status_code == 200:
            out = []
            for c in (resp.json().get("cells") or []):
                try:
                    out.append(int(c))
                except (TypeError, ValueError):
                    continue
            return out
    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info grid_pick: {e}{Style.RESET_ALL}")
    return []


def _hcap_click_cells(page, indices: List[int], grid: int = 3) -> bool:
    """Click grid cells on the real canvas or DOM .task-image tiles."""
    fr = _find_hcaptcha_challenge_frame(page)
    if fr:
        # Cek jika ada elemen .task-image langsung di frame tantangan
        try:
            tiles = fr.locator('.task-image, [aria-label*="Image"]')
            t_count = tiles.count()
            if t_count > 0:
                for idx in indices:
                    if idx < t_count:
                        tiles.nth(idx).click(force=True)
                        time.sleep(0.3)
                return True
        except Exception:
            pass

    box = _hcap_canvas_box(page)
    if not box:
        return False

    tw = box["width"] / grid
    th = box["height"] / grid
    for idx in indices:
        x = box["x"] + (idx % grid + 0.5) * tw
        y = box["y"] + (idx // grid + 0.5) * th
        try:
            page.mouse.click(x, y)
            time.sleep(0.3)
        except Exception:
            pass
    return True


def _hcap_drag_cells(page, src: int, tgt: int, grid: int = _HCAP_GRID) -> bool:
    """Execute a programmatic drag from cell `src` to cell `tgt`."""
    box = _hcap_canvas_box(page)
    if not box:
        return False
    tw = box["width"] / grid
    th = box["height"] / grid

    def _center(idx):
        return (box["x"] + (idx % grid + 0.5) * tw,
                box["y"] + (idx // grid + 0.5) * th)

    sx, sy = _center(src)
    tx, ty = _center(tgt)
    try:
        page.mouse.move(sx, sy)
        time.sleep(0.2)
        page.mouse.down()
        steps = 10
        for i in range(1, steps + 1):
            page.mouse.move(sx + (tx - sx) * i / steps,
                            sy + (ty - sy) * i / steps)
            time.sleep(0.05)
        page.mouse.up()
        time.sleep(1)
        return True
    except Exception:
        return False


def _hcap_click_submit(page) -> str:
    """Click the challenge's submit button (Skip/Next/Verify). Returns its text."""
    fr = _find_hcaptcha_challenge_frame(page)
    if not fr:
        return ""
    for sel in [
        ".button-submit",
        "[data-cy='button-submit']",
        "button:has-text('Verify')",
        "button:has-text('Next')",
        "button:has-text('Skip')",
        ".button-submit.button-blue",
    ]:
        try:
            btn = fr.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                text = (btn.first.inner_text() or "").strip()
                btn.first.click(force=True, timeout=5000)
                time.sleep(1.5)
                return text
        except Exception:
            pass
    return ""


def solve_hcaptcha_challenge_in_page(page, solver_url: str,
                                     max_pages: int = 5) -> bool:
    """Drive the live hCaptcha challenge to completion inside the real page.

    Uses the sidecar's vision backend for the numbered-grid pick but performs all
    clicks in THIS browser, so the widget mints a session-bound token Decodo accepts.
    """
    fr = _find_hcaptcha_challenge_frame(page)
    if not fr:
        return False

    # The challenge UI animates in — wait for challenge elements (tiles, canvas, or prompt).
    meta = _hcap_meta(fr)
    deadline = time.time() + 15
    while not (meta.get("hasTiles") or meta.get("hasCanvas") or meta.get("target")) and time.time() < deadline:
        time.sleep(0.5)
        fr = _find_hcaptcha_challenge_frame(page) or fr
        meta = _hcap_meta(fr)
    if not (meta.get("hasTiles") or meta.get("hasCanvas") or meta.get("target")):
        return False

    for page_num in range(1, max_pages + 1):
        fr = _find_hcaptcha_challenge_frame(page)
        if not fr:
            return True
        meta = _hcap_meta(fr)
        btn_text = (meta.get("buttonText") or "").lower()
        if btn_text in ("verify", "verifizieren", "verificar", "vahvista") and not meta.get("hasTiles"):
            _hcap_click_submit(page)
            time.sleep(1.5)
            if not _find_hcaptcha_challenge_frame(page):
                return True

        target = meta.get("target") or ""
        grid_dim = meta.get("gridDim") or 3
        mode = "drag" if meta.get("isDrag") else "click"
        b64 = _hcap_canvas_b64(page)
        if not b64:
            break
        cells = _sidecar_grid_pick(solver_url, b64, target, mode=mode, grid=grid_dim, timeout=45)
        print(f"  {Fore.CYAN}[*] hCaptcha in-page (hal {page_num}): target={target[:45]!r} (grid {grid_dim}x{grid_dim}) cells={cells}{Style.RESET_ALL}")

        if mode == "drag" and len(cells) >= 2:
            _hcap_drag_cells(page, cells[0], cells[1], grid=grid_dim)
        elif cells:
            _hcap_click_cells(page, cells, grid=grid_dim)
        else:
            # Tidak ada sel yang cocok atau ragu — klik baris pertama jika canvas drag
            if mode == "drag":
                _hcap_click_cells(page, list(range(grid_dim)), grid=grid_dim)

        time.sleep(1.0)
        clicked_txt = _hcap_click_submit(page)
        time.sleep(2.0)

        # Cek apakah challenge frame sudah tertutup (sukses)
        if not _find_hcaptcha_challenge_frame(page):
            print(f"  {Fore.GREEN}✓ Challenge hCaptcha berhasil terselesaikan dan tertutup!{Style.RESET_ALL}")
            return True

    fr = _find_hcaptcha_challenge_frame(page)
    if fr:
        meta = _hcap_meta(fr)
        if (meta.get("buttonText") or "").lower() in ("verify", "verifizieren", "verificar", "next"):
            _hcap_click_submit(page)
            time.sleep(2.0)
    return not bool(_find_hcaptcha_challenge_frame(page))


def handle_hcaptcha_checkout_challenge(
    page,
    proxy_config: Dict[str, Any],
    solver_url: Optional[str] = None,
    timeout: int = 75
) -> bool:
    """
    Menangani modal hCaptcha ('One more step before you're done') pada checkout Decodo:
    1. Deteksi kemunculan modal hCaptcha secara responsif.
    2. Ekstrak sitekey dari frame URL atau DOM di semua level frame.
    3. Hubungi sidecar captcha-solver (direct tanpa proxy).
    4. Jika token didapat dari sidecar: injeksi token, dispatch postMessage/callback, dan tunggu konfirmasi (JANGAN klik checkbox lagi agar tidak memicu puzzle baru).
    5. Jika token tidak tersedia: lakukan satu klik humanized pada checkbox 'I am human'.
    6. Jika muncul puzzle visual: selesaikan OTOMATIS di dalam halaman asli (grid vision
       sidecar + klik kanvas nyata, sehingga token di-mint oleh widget asli dan lolos
       binding rqdata/sesi enterprise). Bila gagal, baru minta pengguna menyelesaikan manual.
    7. Verifikasi konfirmasi sukses 'Your purchase was successful'.
    """
    time.sleep(2)

    # 1. Deteksi apakah modal hCaptcha muncul
    is_hcaptcha = False
    for _ in range(12):
        body_text = ""
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            pass
        if "One more step before you're done" in body_text or "Select the checkbox below" in body_text:
            is_hcaptcha = True
            break
        for f in page.frames:
            if "hcaptcha.com" in (f.url or ""):
                is_hcaptcha = True
                break
        if is_hcaptcha:
            break
        if "Your purchase was successful" in body_text or "Begin proxy setup" in body_text:
            return True
        time.sleep(1)

    if not is_hcaptcha:
        return True

    print(f"  {Fore.YELLOW}[*] Modal hCaptcha terdeteksi ('One more step before you're done'). Menyelesaikan...{Style.RESET_ALL}")

    # 2. Ekstrak sitekey dari seluruh frames
    target_solver = solver_url or load_solver_url()
    # Proxy yang sama dengan browser: hCaptcha mengikat token ke IP penyelesai,
    # jadi sidecar WAJIB menyelesaikan lewat proxy ini agar token tidak ditolak Decodo.
    hcaptcha_proxy_str = format_proxy_string(proxy_config) if proxy_config else None
    sitekey = None
    for f in page.frames:
        u = f.url or ""
        m = re.search(r"sitekey=([a-f0-9-]+)", u, re.I)
        if m:
            sitekey = m.group(1)
            break
        try:
            sk = f.evaluate('''() => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : null;
            }''')
            if sk:
                sitekey = sk
                break
        except Exception:
            pass

    if not sitekey:
        try:
            sitekey = page.evaluate('''() => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : null;
            }''')
        except Exception:
            pass

    token_injected = False
    if target_solver and sitekey and check_sidecar_health(target_solver):
        try:
            _via = "via proxy" if hcaptcha_proxy_str else "direct"
            print(f"  {Fore.CYAN}[*] Menghubungi captcha-solver sidecar ({target_solver}) untuk sitekey {sitekey[:8]} ({_via})...{Style.RESET_ALL}")
            token = solve_hcaptcha_via_sidecar(target_solver, page.url, sitekey, proxy_str=hcaptcha_proxy_str)
            if token and isinstance(token, str) and len(token) > 10:
                print(f"  {Fore.GREEN}✓ Token hCaptcha didapat dari solver sidecar! Menginjeksi token & memvalidasi respons...{Style.RESET_ALL}")
                inject_hcaptcha_token(page, token)
                token_injected = True

                # Coba submit / klik tombol save jika aktif
                for btn_sel in ['button:has-text("Save")', 'button:has-text("Save payment information")', 'button[type="submit"]']:
                    try:
                        s_btn = page.locator(btn_sel)
                        if s_btn.count() > 0 and s_btn.first.is_visible() and s_btn.first.is_enabled():
                            s_btn.first.click(force=True)
                            break
                    except Exception:
                        pass

                # Tunggu konfirmasi apakah token langsung diterima backend (tanpa perlu klik checkbox)
                for _ in range(8):
                    time.sleep(1)
                    body_check = ""
                    try:
                        body_check = page.locator("body").inner_text()
                    except Exception:
                        pass
                    if "Your purchase was successful" in body_check or "Begin proxy setup" in body_check:
                        print(f"  {Fore.GREEN}✓ Konfirmasi checkout berhasil via token hCaptcha sidecar!{Style.RESET_ALL}")
                        return True
        except Exception as e:
            print(f"  {Fore.LIGHTBLACK_EX}Info sidecar: {e}{Style.RESET_ALL}")

    # 3. Fallback: klik checkbox 'I am human' di browser bila modal BELUM terkonfirmasi.
    #    PENTING: jangan hanya bergantung pada `token_injected`. Sitekey Decodo bergaya
    #    enterprise (butuh rqdata yang ditandatangani halaman), sehingga token yang dicetak
    #    sidecar dari widget generik bisa DITOLAK backend -> modal menggantung tanpa fallback.
    #    Jadi selalu klik checkbox asli sekali (natural) agar challenge bisa dilanjutkan
    #    oleh solver vision / diselesaikan manusia di jendela headful.
    body_check = ""
    try:
        body_check = page.locator("body").inner_text()
    except Exception:
        pass
    if "Your purchase was successful" in body_check or "Begin proxy setup" in body_check:
        return True

    for f in page.frames:
        if "hcaptcha.com" in (f.url or "") and ("checkbox" in (f.url or "") or "#frame=checkbox" in (f.url or "")):
            try:
                cb = f.locator('#checkbox, div#checkbox, [role="checkbox"], #anchor')
                if cb.count() > 0 and cb.first.is_visible():
                    print(f"  {Fore.CYAN}[*] Mengklik checkbox 'I am human' hCaptcha secara natural...{Style.RESET_ALL}")
                    try:
                        cb.first.hover(timeout=3000)
                        time.sleep(0.3)
                        cb.first.click(timeout=3000)
                    except Exception:
                        try:
                            cb.first.click(force=True)
                        except Exception:
                            pass
                    time.sleep(2)
                    break
            except Exception:
                pass

    # 4. Pantau penyelesaian checkout
    has_prompted_challenge = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        body_now = ""
        try:
            body_now = page.locator("body").inner_text()
        except Exception:
            pass
        if "Your purchase was successful" in body_now or "Begin proxy setup" in body_now:
            print(f"  {Fore.GREEN}✓ Verifikasi checkout sukses ('Your purchase was successful')!{Style.RESET_ALL}")
            return True

        # Deteksi apakah hCaptcha menampilkan puzzle gambar visual
        has_challenge = any("frame=challenge" in (f.url or "") for f in page.frames)
        if has_challenge:
            solved_inpage = False
            # Coba selesaikan OTOMATIS di dalam halaman asli (token di-mint widget asli,
            # sehingga lolos binding rqdata/sesi enterprise). Jika gagal, baru minta manusia.
            if target_solver and solve_hcaptcha_challenge_in_page(page, target_solver):
                print(f"  {Fore.CYAN}[*] Puzzle hCaptcha diselesaikan otomatis (in-page). Menunggu konfirmasi...{Style.RESET_ALL}")
                for _ in range(20):
                    time.sleep(1)
                    chk = ""
                    try:
                        chk = page.locator("body").inner_text()
                    except Exception:
                        pass
                    if "Your purchase was successful" in chk or "Begin proxy setup" in chk:
                        print(f"  {Fore.GREEN}✓ Konfirmasi checkout sukses setelah solve in-page!{Style.RESET_ALL}")
                        return True
                    if not any("frame=challenge" in (f.url or "") for f in page.frames):
                        solved_inpage = True
                        break

            if not solved_inpage and not has_prompted_challenge:
                has_prompted_challenge = True
                print(f"\n  {Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                print(f"  {Fore.YELLOW}{Style.BRIGHT}⚠️ HCAPTCHA CHALLENGE TERDETEKSI DI BROWSER!{Style.RESET_ALL}")
                print(f"  {Fore.CYAN}👉 Silakan selesaikan puzzle gambar hCaptcha di jendela browser yang terbuka.{Style.RESET_ALL}")
                print(f"  {Fore.CYAN}   Bot akan otomatis mendeteksi konfirmasi pembelian saat Anda selesai.{Style.RESET_ALL}")
                print(f"  {Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")

        time.sleep(1)

    return False


def generate_strong_password() -> str:
    """Bikin password acak yang memenuhi standar Decodo (huruf besar, kecil, angka, simbol)."""
    chars = string.ascii_letters + string.digits
    rand_part = "".join(random.choices(chars, k=10))
    return f"Decodo{rand_part}!9"


def check_geoip_support() -> bool:
    """Cek ketersediaan geoip2 ekstra (dipakai Camoufox & CloakBrowser)."""
    try:
        import geoip2
        return True
    except ImportError:
        return False


def solve_cloudflare_via_sidecar(
    solver_url: str,
    page_url: str,
    proxy_str: Optional[str] = None,
    timeout: int = 45
) -> Optional[Dict[str, Any]]:
    """Meminta cf_clearance cookie dari HTTP sidecar waguriagentic/captcha-solver (direct tanpa proxy)."""
    try:
        endpoint = f"{solver_url.rstrip('/')}/solve"
        # Sesuai instruksi: Solver dijalankan langsung (direct local), TIDAK melalui proxy
        payload = {
            "type": "cloudflare",
            "url": page_url,
            "timeout_s": timeout
        }
        # Teruskan proxy yang sama: cf_clearance terikat ke IP proxy, sehingga
        # hasil panen tetap valid saat di-replay dari browser yang memakai proxy itu.
        if proxy_str:
            payload["proxy"] = proxy_str

        resp = requests.post(endpoint, json=payload, timeout=timeout + 10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("solved") or data.get("success") or data.get("cf_clearance"):
                return data
    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info sidecar cloudflare solver: {e}{Style.RESET_ALL}")
    return None


def wait_for_cloudflare_and_form(
    page,
    selector: str = "#newEmail",
    timeout: int = 60,
    solver_url: Optional[str] = None,
    proxy_str: Optional[str] = None
) -> bool:
    """Tunggu CloakBrowser melewati challenge Cloudflare hingga elemen form muncul, auto-solve Turnstile/Cloudflare jika muncul (solver direct tanpa proxy)."""
    started = time.time()
    last_click_time = 0.0
    sidecar_attempted = False

    while time.time() - started < timeout:
        elapsed = time.time() - started
        # Cek selector form pendaftaran terlebih dahulu
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                return True
        except Exception:
            pass

        title = page.title()
        # Jika halaman masih di challenge Cloudflare Turnstile / Managed Challenge
        is_cf = any(kw in title for kw in ["Just a moment", "Un momento", "Moment", "Cloudflare", "Security", "Verificando"])
        if not is_cf:
            try:
                is_cf = page.locator('input[name="cf-turnstile-response"], iframe[src*="challenges.cloudflare.com"]').count() > 0
            except Exception:
                pass

        if is_cf:
            # 1. In-browser click: Mengklik Turnstile checkbox
            if (time.time() - last_click_time) >= 2.5:
                clicked = False
                for f in page.frames:
                    if "challenges.cloudflare.com" in (f.url or ""):
                        # 1a. Resolusi koordinat mutlak iframe di viewport halaman
                        try:
                            fr_el = f.frame_element()
                            box = fr_el.bounding_box()
                            if box and box["width"] > 20:
                                click_x = box["x"] + 30
                                click_y = box["y"] + box["height"] / 2
                                print(f"  {Fore.YELLOW}[*] Mengklik Turnstile checkbox Cloudflare di ({int(click_x)}, {int(click_y)})...{Style.RESET_ALL}")
                                page.mouse.click(click_x, click_y)
                                clicked = True
                                last_click_time = time.time()
                                break
                        except Exception:
                            pass

                        # 1b. Fallback klik selector langsung di subframe
                        for cb_sel in ['input[type="checkbox"]', '#challenge-stage', 'div#checkbox', 'span.mark', 'label.ctp-checkbox-label', 'body']:
                            try:
                                loc = f.locator(cb_sel)
                                if loc.count() > 0 and loc.first.is_visible():
                                    loc.first.click(force=True)
                                    clicked = True
                                    last_click_time = time.time()
                                    break
                            except Exception:
                                pass
                        if clicked:
                            break

            # 2. Sidecar solver (direct tanpa proxy)
            target_solver = solver_url or load_solver_url()
            if target_solver and elapsed >= 30 and not sidecar_attempted:
                if check_sidecar_health(target_solver):
                    sidecar_attempted = True

                    # 2a. Cek apakah ada sitekey Turnstile di form
                    sitekey = None
                    try:
                        sitekey = page.evaluate(r'''() => {
                            const el = document.querySelector('[data-sitekey]');
                            if (el) return el.getAttribute('data-sitekey');
                            for (const iframe of document.querySelectorAll('iframe[src*="challenges.cloudflare.com"]')) {
                                const m = iframe.src.match(/turnstile\/[^\/]+\/[^\/]+\/[^\/]+\/[^\/]+\/([a-zA-Z0-9_-]+)/) || iframe.src.match(/sitekey=([a-zA-Z0-9_-]+)/);
                                if (m) return m[1];
                            }
                            return null;
                        }''')
                    except Exception:
                        pass

                    if sitekey:
                        print(f"  {Fore.CYAN}[*] Turnstile sitekey terdeteksi ({sitekey[:8]}...). Meminta token ke sidecar (direct tanpa proxy)...{Style.RESET_ALL}")
                        token = solve_turnstile_via_sidecar(target_solver, page.url, sitekey, timeout=40)
                        if token:
                            print(f"  {Fore.GREEN}✓ Token Turnstile didapat dari sidecar! Menginjeksi token...{Style.RESET_ALL}")
                            inject_turnstile_token(page, token)
                            time.sleep(2)

                    # 2b. Minta cf_clearance cookie dari sidecar (proxy yang sama agar replayable)
                    print(f"  {Fore.CYAN}[*] Cloudflare challenge terdeteksi ({int(elapsed)}s). Meminta cf_clearance ke sidecar (via proxy yang sama)...{Style.RESET_ALL}")
                    cf_data = solve_cloudflare_via_sidecar(target_solver, page.url, proxy_str=proxy_str, timeout=120)
                    if cf_data and cf_data.get("cookies"):
                        print(f"  {Fore.GREEN}✓ cf_clearance berhasil dipanen dari sidecar! Menginjeksi cookie ke browser...{Style.RESET_ALL}")
                        # cf_clearance terikat ke User-Agent: selaraskan UA browser lokal dengan UA sidecar.
                        try:
                            sidecar_ua = cf_data.get("user_agent")
                            if sidecar_ua:
                                page.context.set_extra_http_headers({"User-Agent": sidecar_ua})
                        except Exception:
                            pass
                        cookies_to_add = []
                        for c in cf_data["cookies"]:
                            c_dict = {
                                "name": c["name"],
                                "value": c["value"],
                                "domain": c.get("domain", ".decodo.com"),
                                "path": c.get("path", "/"),
                            }
                            if "secure" in c:
                                c_dict["secure"] = bool(c["secure"])
                            cookies_to_add.append(c_dict)
                        try:
                            page.context.add_cookies(cookies_to_add)
                        except Exception:
                            pass
                        time.sleep(1)
                        print(f"  {Fore.CYAN}[*] Me-reload halaman pendaftaran dengan cookie clearance...{Style.RESET_ALL}")
                        page.reload(wait_until="commit")
                        time.sleep(3)
                        continue

        time.sleep(1)

    return False


def click_start_trial_button(page, timeout: int = 15) -> bool:
    """
    Mencari dan mengklik tombol 'Start with a trial' pada dashboard Decodo (halaman pricing).
    Mendukung scroll into view, Playwright selector, dan evaluate JavaScript fallback.
    """
    started = time.time()

    # Tutup popup / modal onboarding jika menghalangi
    for dismiss_sel in [
        'button:has-text("Next")',
        'button:has-text("Got it")',
        'button:has-text("Dismiss")',
        'div[role="dialog"] button[aria-label="Close"]',
        'button[aria-label="Close"]',
    ]:
        try:
            d_btn = page.locator(dismiss_sel)
            if d_btn.count() > 0 and d_btn.first.is_visible():
                d_btn.first.click(force=True)
                time.sleep(1)
        except Exception:
            pass

    trial_selectors = [
        'button:has-text("Start with a trial")',
        'a:has-text("Start with a trial")',
        ':is(button, a, div[role="button"]):has-text("Start with a trial")',
        'button:has-text("Start trial")',
        'a:has-text("Start trial")',
        ':is(button, a, div[role="button"]):has-text("Start trial")',
    ]

    while time.time() - started < timeout:
        # 1. Coba lewat Playwright selector
        for sel in trial_selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    for i in range(loc.count()):
                        item = loc.nth(i)
                        if item.is_visible():
                            try:
                                item.scroll_into_view_if_needed(timeout=2000)
                            except Exception:
                                pass
                            item.click(force=True)
                            return True
            except Exception:
                pass

        # 2. Coba lewat evaluate JavaScript fleksibel
        try:
            clicked = page.evaluate('''() => {
                const elements = Array.from(document.querySelectorAll('button, a, div[role="button"], span, p'));
                for (const el of elements) {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (text.includes('start with a trial') || text === 'start with a trial' || text.includes('start trial')) {
                        const target = el.closest('button, a, div[role="button"]') || el;
                        target.scrollIntoView({behavior: 'instant', block: 'center'});
                        target.click();
                        return true;
                    }
                }
                return false;
            }''')
            if clicked:
                return True
        except Exception:
            pass

        time.sleep(1)

    return False


def wait_for_checkout_page(page, timeout: int = 90) -> bool:
    """
    Tunggu sampai formulir checkout (Shipping / Payment) benar-benar muncul dan terlihat di DOM.
    Jika dalam beberapa detik belum muncul, lakukan re-click pada tombol 'Start with a trial',
    atau buka accordion 'Card / PayPal / Google Pay' jika masih tertutup.
    """
    started = time.time()
    last_reclick = time.time()
    accordion_clicked = False

    while time.time() - started < timeout:
        elapsed = int(time.time() - started)

        # 1. Cek apakah elemen input formulir checkout sudah benar-benar terlihat di main page atau iframe
        targets = [page] + list(page.frames)
        for t in targets:
            try:
                for txt in ["Save shipping information", "Shipping address", "Save payment information"]:
                    loc = t.locator(f'text="{txt}"')
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
            except Exception:
                pass

            try:
                for sel in [
                    'input#Field-nameInput',
                    'input#Field-addressLine1Input',
                    'select#Field-countryInput',
                    'input[placeholder*="Full name" i]',
                    'input[placeholder*="Name" i]',
                    'input[name="shippingAddress.name"]',
                    'input[name="name"]',
                    'input[placeholder*="Address line" i]',
                    'input[name="cardnumber"]',
                    'input[autocomplete="cc-number"]',
                    '#cardNumber'
                ]:
                    loc = t.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
            except Exception:
                pass

        # Cek apakah ada frame Stripe yang aktif dan memiliki input yang terlihat
        try:
            for f in page.frames:
                if any(k in f.url for k in ["stripe.com", "stripe.network", "elements"]):
                    c = f.locator('input:not([type="hidden"]), select, [role="combobox"]')
                    if c.count() > 0 and c.first.is_visible():
                        return True
        except Exception:
            pass

        # 2. Jika sudah di UI checkout namun form belum tampak setelah 3 detik, klik accordion satu kali
        try:
            is_checkout_ui = (
                "checkout" in page.url
                or page.locator('text="Select your payment method"').count() > 0
                or page.locator('text="Your order"').count() > 0
            )
            if is_checkout_ui and elapsed >= 3 and not accordion_clicked:
                collapsed = page.locator(':is(button, div)[aria-expanded="false"]:has-text("Card / PayPal / Google Pay")')
                if collapsed.count() > 0:
                    print(f"  {Fore.CYAN}[*] Membuka accordion 'Card / PayPal / Google Pay'...{Style.RESET_ALL}")
                    collapsed.first.click(force=True)
                    accordion_clicked = True
                    time.sleep(0.3)
                elif page.locator('input[placeholder*="Name"], input[name="name"], text="Save shipping information"').count() == 0:
                    btn = page.locator('button:has-text("Card / PayPal / Google Pay"), div[role="button"]:has-text("Card / PayPal / Google Pay")')
                    if btn.count() > 0 and btn.first.is_visible():
                        print(f"  {Fore.CYAN}[*] Mengklik header 'Card / PayPal / Google Pay'...{Style.RESET_ALL}")
                        btn.first.click(force=True)
                        accordion_clicked = True
                        time.sleep(0.3)
        except Exception:
            pass

        # 3. Jika sudah 6 detik sejak klik terakhir dan checkout belum muncul, coba re-click atau dismiss blocker
        if time.time() - last_reclick >= 6 and "checkout" not in page.url:
            # Cek modal blocker onboarding
            for dismiss_sel in [
                'button:has-text("Next")',
                'button:has-text("Got it")',
                'button:has-text("Continue")',
                'button[aria-label="Close"]',
            ]:
                try:
                    d_btn = page.locator(dismiss_sel)
                    if d_btn.count() > 0 and d_btn.first.is_visible():
                        d_btn.first.click(force=True)
                        time.sleep(0.3)
                except Exception:
                    pass

            # Cek apakah tombol 'Start with a trial' masih terlihat di halaman pricing
            try:
                trial_btn = page.locator(':is(button, a, div[role="button"]):has-text("Start with a trial")')
                if trial_btn.count() > 0 and trial_btn.first.is_visible():
                    print(f"  {Fore.YELLOW}[*] Formulir belum muncul ({elapsed}s). Mencoba klik ulang 'Start with a trial'...{Style.RESET_ALL}")
                    try:
                        trial_btn.first.scroll_into_view_if_needed(timeout=500)
                    except Exception:
                        pass
                    trial_btn.first.click(force=True)
                    last_reclick = time.time()
            except Exception:
                pass

            # Cek Cloudflare Turnstile jika muncul di tengah proses
            try:
                wait_for_cloudflare_and_form(page, selector='text="Select your payment method"', timeout=2)
            except Exception:
                pass

        if elapsed > 0 and elapsed % 10 == 0:
            print(f"  {Fore.CYAN}[*] Menunggu formulir checkout Decodo termuat ({elapsed}s/{timeout}s)...{Style.RESET_ALL}")

        time.sleep(0.1)

    return False


def fill_card_in_page_or_frames(page, card: Dict[str, str]) -> bool:
    """Coba mengisi form kartu kredit baik di main page maupun di dalam Stripe Elements iframe."""
    card_num = card.get("card_number", "").replace(" ", "").strip()
    exp_month = card.get("exp_month", "").strip()
    exp_year = card.get("exp_year", "").strip()
    cvv = card.get("cvv", "").strip()
    holder = card.get("cardholder_name", "").strip()

    if not card_num:
        return False

    targets = [page] + list(page.frames)

    # Scroll ke bawah agar area pembayaran dan tombol Save tampak
    try:
        page.evaluate("window.scrollBy(0, 500)")
    except Exception:
        pass

    # Pastikan opsi 'Card' terpilih pada pilihan metode pembayaran
    for t in targets:
        try:
            card_radio = t.locator('input[type="radio"][value*="card"], label:has-text("Card"), div[role="radio"]:has-text("Card")')
            if card_radio.count() > 0 and card_radio.first.is_visible():
                card_radio.first.click(force=True)
                time.sleep(0.3)
                break
        except Exception:
            pass

    filled = False
    card_selectors = ['input[name="cardnumber"]', 'input[name="cardNumber"]', 'input[autocomplete="cc-number"]', '#cardNumber', 'input[placeholder*="Card number" i]']
    exp_selectors = ['input[name="exp-date"]', 'input[autocomplete="cc-exp"]', '#cardExpiry', 'input[placeholder*="MM / YY" i]', 'input[placeholder*="MM/YY" i]', 'input[name="expMonth"]']
    cvc_selectors = ['input[name="cvc"]', 'input[name="cvv"]', 'input[autocomplete="cc-csc"]', '#cardCvc', 'input[placeholder*="CVC" i]', 'input[placeholder*="CVV" i]']

    for t in targets:
        try:
            # 1. Card number
            for sel in card_selectors:
                c_inp = t.locator(sel)
                if c_inp.count() > 0 and c_inp.first.is_visible():
                    c_inp.first.scroll_into_view_if_needed()
                    c_inp.first.fill(card_num)
                    filled = True
                    break

            # 2. Exp date
            for sel in exp_selectors:
                e_inp = t.locator(sel)
                if e_inp.count() > 0 and e_inp.first.is_visible():
                    exp_combined = f"{exp_month}/{exp_year[-2:]}" if len(exp_year) >= 2 else f"{exp_month}/{exp_year}"
                    e_inp.first.fill(exp_combined)
                    break

            # 3. CVC
            for sel in cvc_selectors:
                cv_inp = t.locator(sel)
                if cv_inp.count() > 0 and cv_inp.first.is_visible():
                    cv_inp.first.fill(cvv)
                    break

            # 4. Card holder
            if holder:
                holder_selectors = ['input[name="cardholder-name"]', 'input[name="name"]', 'input[placeholder*="Cardholder" i]', 'input[placeholder*="Name on card" i]', '#cardholderName']
                for sel in holder_selectors:
                    h_inp = t.locator(sel)
                    if h_inp.count() > 0 and h_inp.first.is_visible():
                        h_inp.first.fill(holder)
                        break

            if filled:
                return True
        except Exception:
            continue
    return filled


def select_http_protocol(page) -> bool:
    """
    Pada tab 'Proxy setup', pilih dropdown PROTOCOL dan ubah menjadi 'HTTP'.
    Mengubah format dari 'endpoint:port' ke 'HTTP' sehingga tabel memuat format proxy lengkap.
    """
    try:
        print(f"  {Fore.CYAN}[*] Memeriksa & memilih opsi Protocol -> 'HTTP' pada dashboard Decodo...{Style.RESET_ALL}")
        # 1. Tutup popover / dialog yang mungkin menghalangi (seperti SELECT TEAM)
        try:
            page.keyboard.press("Escape")
            time.sleep(0.3)
        except Exception:
            pass

        # Pastikan scroll berada di bagian atas agar kontrol Protocol terlihat
        try:
            page.evaluate("() => window.scrollTo(0, 0)")
            time.sleep(0.3)
        except Exception:
            pass

        # Pastikan tab 'Proxy setup' aktif jika ada
        try:
            tab = page.locator('button:has-text("Proxy setup"), [role="tab"]:has-text("Proxy setup"), a:has-text("Proxy setup")')
            if tab.count() > 0 and tab.first.is_visible():
                tab.first.click()
                time.sleep(0.8)
        except Exception:
            pass

        # 2. Buka dropdown PROTOCOL
        opened = page.evaluate(r'''() => {
            const all = Array.from(document.querySelectorAll('*'));

            // A. Cek apakah dropdown PROTOCOL sudah bernilai HTTP
            const protoLabel = all.find(e => e.children.length === 0 && e.textContent.trim().toUpperCase() === 'PROTOCOL');
            if (protoLabel) {
                let p = protoLabel.parentElement;
                for (let i = 0; i < 3 && p; i++) {
                    const txt = p.textContent.trim();
                    if (txt.includes('HTTP') && !txt.includes('endpoint:port')) {
                        return { already_http: true };
                    }
                    p = p.parentElement;
                }
            }

            // B. Cari leaf element yang memuat teks 'endpoint:port'
            const epLeaf = all.find(e => {
                const t = e.textContent.trim().toLowerCase();
                return t.includes('endpoint:port') && 
                       !Array.from(e.children).some(c => c.textContent.trim().toLowerCase().includes('endpoint:port'));
            });

            if (epLeaf) {
                let target = epLeaf.closest('button, [role="combobox"], [role="button"]') || epLeaf.parentElement || epLeaf;
                const r = target.getBoundingClientRect();
                if (r.width > 350 || r.height > 80) target = epLeaf;
                target.scrollIntoView({ block: 'center' });
                target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                target.click();
                const tr = target.getBoundingClientRect();
                return { clicked: true, x: tr.left + tr.width/2, y: tr.top + tr.height/2 };
            }

            // C. Fallback: Elemen yang terletak tepat di bawah label PROTOCOL
            if (protoLabel) {
                const pRect = protoLabel.getBoundingClientRect();
                const below = all.filter(e => {
                    const r = e.getBoundingClientRect();
                    return r.width > 40 && r.width < 300 && r.height > 20 && r.height < 60 &&
                           Math.abs(r.left - pRect.left) < 60 &&
                           r.top >= pRect.top && r.top <= pRect.bottom + 60;
                });
                if (below.length > 0) {
                    const target = below[0];
                    target.scrollIntoView({ block: 'center' });
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                    const tr = target.getBoundingClientRect();
                    return { clicked: true, x: tr.left + tr.width/2, y: tr.top + tr.height/2 };
                }
            }

            return { clicked: false };
        }''')

        if (isinstance(opened, dict) and opened.get("already_http")) or opened in ("ALREADY_HTTP", "HTTP"):
            print(f"  {Fore.GREEN}✓ Protocol sudah terpilih sebagai HTTP.{Style.RESET_ALL}")
            return True

        if isinstance(opened, dict) and opened.get("clicked"):
            try:
                page.mouse.click(opened["x"], opened["y"])
            except Exception:
                pass
        elif opened is True:
            pass
        else:
            for ep_sel in [
                'button:has-text("endpoint:port")',
                '[role="combobox"]:has-text("endpoint:port")',
                'text="endpoint:port"',
            ]:
                try:
                    ep_loc = page.locator(ep_sel)
                    if ep_loc.count() > 0 and ep_loc.first.is_visible():
                        ep_loc.first.click(force=True)
                        break
                except Exception:
                    pass

        time.sleep(0.6)

        # 3. Klik pilihan 'HTTP' di dropdown yang terbuka
        selected = page.evaluate(r'''() => {
            const all = Array.from(document.querySelectorAll('*'));
            
            // Cari elemen opsi yang memuat kata 'HTTP' (misal: 'HTTP', 'HTTP/HTTPS', 'HTTP / HTTPS')
            const httpCandidates = all.filter(e => {
                const t = e.textContent.trim();
                const r = e.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return false;
                // Abaikan container besar (seperti form atau seluruh layout)
                if (r.height > 80 || r.width > 500) return false;
                // Harus memuat kata HTTP
                return /\bHTTP\b/i.test(t) || t.toUpperCase().startsWith('HTTP');
            });

            if (httpCandidates.length > 0) {
                // Urutkan elemen paling spesifik (luas area terkecil)
                httpCandidates.sort((a, b) => {
                    const ra = a.getBoundingClientRect();
                    const rb = b.getBoundingClientRect();
                    return (ra.width * ra.height) - (rb.width * rb.height);
                });

                const target = httpCandidates[0];
                const r = target.getBoundingClientRect();
                target.scrollIntoView({ block: 'center' });

                const cx = r.left + r.width / 2;
                const cy = r.top + r.height / 2;

                const evInit = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy };
                try { target.dispatchEvent(new PointerEvent('pointerdown', evInit)); } catch(e){}
                try { target.dispatchEvent(new MouseEvent('mousedown', evInit)); } catch(e){}
                try { target.dispatchEvent(new PointerEvent('pointerup', evInit)); } catch(e){}
                try { target.dispatchEvent(new MouseEvent('mouseup', evInit)); } catch(e){}
                target.click();

                return { clicked: true, x: cx, y: cy, text: target.textContent.trim() };
            }

            return { clicked: false };
        }''')

        is_selected = False
        if isinstance(selected, dict) and selected.get("clicked"):
            is_selected = True
            opt_text = selected.get("text", "HTTP")
            print(f"  {Fore.CYAN}[*] Opsi '{opt_text}' terdeteksi dan diklik via pointer/mouse event.{Style.RESET_ALL}")
            try:
                page.mouse.click(selected["x"], selected["y"])
            except Exception:
                pass
        elif selected is True or selected in ("HTTP", "ALREADY_HTTP"):
            is_selected = True

        if not is_selected:
            # Coba locator Playwright dengan regex fleksibel
            for loc in [
                page.locator('[role="option"]').filter(has_text=re.compile(r"HTTP", re.I)),
                page.locator('[role="menuitem"]').filter(has_text=re.compile(r"HTTP", re.I)),
                page.locator('li').filter(has_text=re.compile(r"HTTP", re.I)),
                page.locator('button').filter(has_text=re.compile(r"HTTP", re.I)),
                page.get_by_text(re.compile(r"^\s*HTTP", re.I)),
                page.locator('text=/HTTP/i'),
            ]:
                try:
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(force=True)
                        is_selected = True
                        break
                except Exception:
                    pass

        # Fallback keyboard navigation: tekan ArrowDown + Enter jika dropdown combobox dalam keadaan terbuka
        if not is_selected:
            try:
                page.keyboard.press("ArrowDown")
                time.sleep(0.2)
                page.keyboard.press("Enter")
                is_selected = True
            except Exception:
                pass

        if is_selected:
            print(f"  {Fore.GREEN}✓ Protocol 'HTTP' berhasil dipilih! Menunggu tabel memperbarui format...{Style.RESET_ALL}")
            time.sleep(2)
            return True

    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info pilih protocol HTTP: {e}{Style.RESET_ALL}")
    return False


def copy_all_proxies_via_download_menu(page) -> List[str]:
    """
    Klik icon unduh (terletak persis di samping pagination '1/1' pada footer tabel),
    pilih menu 'Copy' untuk menyalin seluruh 10 baris proxy (bukan hanya 1 baris).
    """
    proxies = []
    try:
        # 1. Tutup popover / dialog yang mungkin menghalangi (seperti SELECT TEAM)
        try:
            page.keyboard.press("Escape")
            time.sleep(0.2)
        except Exception:
            pass

        # 2. Pasang penangkap clipboard di window sebelum klik
        page.evaluate(r'''() => {
            window.__decodo_copied_proxies = "";
            if (navigator.clipboard) {
                const _ow = navigator.clipboard.writeText;
                navigator.clipboard.writeText = async function(text) {
                    window.__decodo_copied_proxies = text;
                    if (_ow) {
                        try { await _ow.call(navigator.clipboard, text); } catch(e){}
                    }
                    return Promise.resolve();
                };
            }
            document.addEventListener("copy", (e) => {
                try {
                    if (e.clipboardData) {
                        const t = e.clipboardData.getData("text/plain");
                        if (t) window.__decodo_copied_proxies = t;
                    }
                } catch(e){}
            }, true);
        }''')

        print(f"  {Fore.CYAN}[*] Mencari dan mengklik icon unduh di samping pagination tabel...{Style.RESET_ALL}")

        # Scroll ke bawah halaman agar pagination dan footer tabel terlihat di viewport
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
        except Exception:
            pass

        # 3. Cari dan klik tombol icon unduh (tepat di kanan tombol '>' / teks '1/1', HANYA di area pagination tabel)
        download_icon_info = page.evaluate(r'''() => {
            const all = Array.from(document.querySelectorAll('*'));
            
            // Cari leaf element pagination: '1/1' atau 'of 10' atau 'Endpoints per page'
            const pagLeaf = all.find(e => {
                const t = e.textContent.trim();
                return (t === '1/1' || /^\d+-\d+\s+of\s+\d+$/i.test(t) || t === 'Endpoints per page' || t.includes('of 10')) &&
                       !Array.from(e.children).some(c => c.textContent.trim() === t);
            });

            let targetBtn = null;

            if (pagLeaf) {
                const pagRect = pagLeaf.getBoundingClientRect();
                const pagY = pagRect.top;
                // Cari elemen tombol/svg yang berada di baris horizontal yang sama (beda Y < 35px, X > pagLeaf.left)
                const candidates = all.filter(e => {
                    const r = e.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0 || r.width > 60 || r.height > 60) return false;
                    if (Math.abs(r.top - pagY) > 35) return false;
                    if (r.left <= pagRect.left) return false;
                    if (r.top < 150) return false; // Abaikan header atas
                    return e.tagName === 'BUTTON' || e.getAttribute('role') === 'button' ||
                           e.tagName === 'SVG' || e.querySelector('svg') !== null ||
                           e.getAttribute('tabindex') !== null;
                });

                if (candidates.length > 0) {
                    // Yang paling kanan adalah icon unduh
                    candidates.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                    targetBtn = candidates[0];
                }
            }

            // Fallback: tombol unduh / export di bawah tabel (exclude header atas)
            if (!targetBtn) {
                const table = document.querySelector('table, [role="table"]');
                const tableBottom = table ? table.getBoundingClientRect().bottom : 300;
                const btns = all.filter(e => {
                    const r = e.getBoundingClientRect();
                    if (r.top < Math.max(200, tableBottom - 40) || r.top > tableBottom + 120) return false;
                    if (r.left < window.innerWidth * 0.5) return false;
                    const aria = (e.getAttribute('aria-label') || '').toLowerCase();
                    const title = (e.getAttribute('title') || '').toLowerCase();
                    return aria.includes('download') || aria.includes('export') || title.includes('download') || title.includes('export') || e.tagName === 'BUTTON';
                });
                if (btns.length > 0) {
                    btns.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                    targetBtn = btns[0];
                }
            }

            if (targetBtn) {
                targetBtn.scrollIntoView({ block: 'center' });
                targetBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                targetBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                targetBtn.click();
                const r = targetBtn.getBoundingClientRect();
                return { clicked: true, x: r.left + r.width/2, y: r.top + r.height/2 };
            }

            return { clicked: false };
        }''')

        download_icon_clicked = False
        if isinstance(download_icon_info, dict) and download_icon_info.get("clicked"):
            download_icon_clicked = True
            if "x" in download_icon_info and "y" in download_icon_info:
                try:
                    page.mouse.click(download_icon_info["x"], download_icon_info["y"])
                except Exception:
                    pass
        elif download_icon_info is True:
            download_icon_clicked = True

        if download_icon_clicked:
            print(f"  {Fore.GREEN}✓ Icon unduh berhasil diklik! Menu Copy / .txt terbuka.{Style.RESET_ALL}")
            time.sleep(1)

            # 4. Klik tombol 'Copy' di menu unduh yang muncul
            copy_info = page.evaluate(r'''() => {
                const all = Array.from(document.querySelectorAll('*'));
                const leafMatch = (e, needle, exact) => {
                    const t = (e.textContent || '').trim().toLowerCase();
                    const r = e.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0 || r.height >= 60 || r.width >= 300) return false;
                    const ok = exact ? (t === needle) : t.includes(needle);
                    if (!ok) return false;
                    return !Array.from(e.children).some(c => {
                        const ct = (c.textContent || '').trim().toLowerCase();
                        return exact ? (ct === needle) : ct.includes(needle);
                    });
                };
                let copyLeaf = all.find(e => leafMatch(e, 'copy', true));
                if (!copyLeaf) copyLeaf = all.find(e => leafMatch(e, 'copy', false));
                if (copyLeaf) {
                    const target = copyLeaf.closest('button, [role="menuitem"], [role="option"], li, div') || copyLeaf;
                    target.scrollIntoView({ block: 'center' });
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                    const r = target.getBoundingClientRect();
                    return { clicked: true, x: r.left + r.width/2, y: r.top + r.height/2 };
                }
                return { clicked: false };
            }''')

            copy_clicked = False
            if isinstance(copy_info, dict) and copy_info.get("clicked"):
                copy_clicked = True
                if "x" in copy_info and "y" in copy_info:
                    try:
                        page.mouse.click(copy_info["x"], copy_info["y"])
                    except Exception:
                        pass
            elif copy_info is True:
                copy_clicked = True

            if not copy_clicked:
                for copy_sel in [
                    '[role="menuitem"]:has-text("Copy")',
                    'button:has-text("Copy")',
                    'div[role="menuitem"]:has-text("Copy")',
                    'text="Copy"',
                ]:
                    try:
                        c_btn = page.locator(copy_sel)
                        if c_btn.count() > 0 and c_btn.first.is_visible():
                            c_btn.first.click()
                            copy_clicked = True
                            break
                    except Exception:
                        pass

            if copy_clicked:
                print(f"  {Fore.GREEN}✓ Opsi 'Copy' berhasil dipilih! Memanen seluruh baris proxy...{Style.RESET_ALL}")
                time.sleep(1)

            # 5. Ambil teks hasil copy dari window hook atau clipboard
            copied_text = page.evaluate("() => window.__decodo_copied_proxies || ''")
            if not copied_text:
                try:
                    # Race terhadap timeout: page.evaluate menunggu promise yang dikembalikan,
                    # jadi readText() yang terblokir prompt izin akan menggantung selamanya.
                    copied_text = page.evaluate('''() => Promise.race([
                        (navigator.clipboard ? navigator.clipboard.readText() : Promise.resolve('')).catch(() => ''),
                        new Promise(r => setTimeout(() => r(''), 2500))
                    ])''')
                except Exception:
                    pass

            if copied_text and isinstance(copied_text, str) and ("decodo" in copied_text or ":" in copied_text):
                lines = [ln.strip() for ln in copied_text.splitlines() if ln.strip()]
                for ln in lines:
                    if "decodo.com" in ln or ("@" in ln and ":" in ln):
                        proxies.append(ln if ln.startswith("http") else f"http://{ln}")
                if proxies:
                    print(f"  {Fore.GREEN}✓ Berhasil menyalin {len(proxies)} baris proxy via menu Copy!{Style.RESET_ALL}")
                    return list(dict.fromkeys(proxies))

            # 6. Fallback unduhan berkas .txt dari menu unduh
            #    PENTING: JANGAN gabung engine Playwright 'text="..."' ke dalam daftar CSS
            #    (page.locator menerima satu engine per string) -> dulu memicu
            #    "Unexpected token =" yang membatalkan SELURUH panen. Coba satu per satu.
            txt_btn = None
            for _txt_sel in [
                '[role="menuitem"]:has-text(".txt")',
                '[role="menuitem"]:has-text("txt")',
                'button:has-text(".txt")',
                'button:has-text("txt")',
                'a:has-text(".txt")',
                'a:has-text("txt")',
            ]:
                try:
                    _tl = page.locator(_txt_sel)
                    if _tl.count() > 0 and _tl.first.is_visible():
                        txt_btn = _tl.first
                        break
                except Exception:
                    continue
            if txt_btn is not None:
                print(f"  {Fore.CYAN}[*] Menggunakan opsi unduhan .txt untuk memanen seluruh proxy...{Style.RESET_ALL}")
                try:
                    with page.expect_download(timeout=5000) as dl_info:
                        txt_btn.click(force=True)
                    dl = dl_info.value
                    dl_path = dl.path()
                    if dl_path and os.path.exists(dl_path):
                        with open(dl_path, "r", encoding="utf-8") as f:
                            for ln in f:
                                p = ln.strip()
                                if p and not p.startswith("#"):
                                    proxies.append(p if p.startswith("http") else f"http://{p}")
                    if proxies:
                        print(f"  {Fore.GREEN}✓ Berhasil mengunduh {len(proxies)} baris proxy via berkas .txt!{Style.RESET_ALL}")
                        return list(dict.fromkeys(proxies))
                except Exception:
                    pass

    except Exception as e:
        print(f"  {Fore.LIGHTBLACK_EX}Info menu unduh copy: {e}{Style.RESET_ALL}")

    return proxies


def extract_proxies_from_dashboard(page) -> List[str]:
    """
    Ekstrak seluruh daftar proxy HTTP residential dari dashboard Decodo:
    1. Pastikan protocol HTTP terpilih di dashboard.
    2. Klik icon unduh di tabel & klik menu 'Copy' (seluruh 10 baris proxy disalin sekaligus).
    3. Fallback unduhan berkas .txt dari menu unduh.
    4. Fallback ekstraksi dari blok kode cURL di dashboard (kredensial asli tanpa sensor).
    5. Fallback unmask password & parse seluruh baris tabel.
    6. Fallback ekstraksi endpoint + header autentikasi.
    """
    proxies = []

    # 1. Pilih opsi Protocol -> 'HTTP'
    select_http_protocol(page)
    time.sleep(1)

    # 2. Klik icon unduh & pilih 'Copy' (menyalin seluruh 10 baris proxy)
    copied_list = copy_all_proxies_via_download_menu(page)
    if copied_list and len(copied_list) >= 2:
        return list(dict.fromkeys(copied_list))

    # Scroll ke bawah agar blok cURL & tabel lengkap termuat di DOM
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
    except Exception:
        pass

    # 3. Ekstraksi dari blok kode cURL di dashboard (terdapat kredensial asli lengkap)
    try:
        content = page.content()
        curl_match = re.search(r'curl\s+-U\s+["\']([^:"\']+):([^"\']+)["\']\s+-x\s+["\']([^:"\']+):(\d+)["\']', content)
        if not curl_match:
            try:
                body_txt = page.locator('body').inner_text()
                curl_match = re.search(r'curl\s+-U\s+["\']?([^:"\'\s]+):([^"\'\s]+)["\']?\s+-x\s+["\']?([^:"\'\s]+):(\d+)["\']?', body_txt)
            except Exception:
                pass

        if curl_match:
            u = curl_match.group(1)
            pw = curl_match.group(2)
            host = curl_match.group(3)
            # Ambil seluruh port yang terdaftar di tabel (10001 s/d 10010)
            table_ports = []
            try:
                for r in page.locator('table tbody tr').all():
                    for td in r.locator('td').all():
                        t = td.inner_text().strip()
                        if re.match(r'^1\d{4}$', t) and t not in table_ports:
                            table_ports.append(t)
            except Exception:
                pass

            if not table_ports:
                try:
                    all_text = page.locator('body').inner_text()
                    for pt in re.findall(r'\b(100\d{2})\b', all_text):
                        if pt not in table_ports and 10001 <= int(pt) <= 10050:
                            table_ports.append(pt)
                except Exception:
                    pass

            if not table_ports:
                table_ports = [str(10000 + i) for i in range(1, 11)]

            table_ports = sorted(list(dict.fromkeys(table_ports)), key=lambda x: int(x))
            curl_proxies = [f"http://{u}:{pw}@{host}:{pt}" for pt in table_ports]
            if curl_proxies:
                print(f"  {Fore.GREEN}✓ Berhasil mengekstrak {len(curl_proxies)} baris proxy via cURL credentials & endpoint list!{Style.RESET_ALL}")
                return list(dict.fromkeys(curl_proxies))
    except Exception:
        pass

    # 4. Fallback unduh berkas .txt jika tombol .txt tampak
    try:
        txt_btn = page.locator('button:has-text(".txt")')
        if txt_btn.count() > 0 and txt_btn.first.is_visible():
            try:
                with page.expect_download(timeout=4000) as d_info:
                    txt_btn.first.click(force=True)
                download = d_info.value
                dl_path = download.path()
                if dl_path and os.path.exists(dl_path):
                    with open(dl_path, "r", encoding="utf-8") as f:
                        for line in f:
                            p = line.strip()
                            if p and not p.startswith("#"):
                                proxies.append(p if p.startswith("http") else f"http://{p}")
                if proxies:
                    return list(dict.fromkeys(proxies))
            except Exception:
                pass
    except Exception:
        pass

    # 5. Fallback unmask password & parse seluruh baris tabel
    try:
        try:
            eye_icons = page.locator('th:has-text("PASSWORD") svg, [aria-label*="password" i] svg, button:has-text("PASSWORD")')
            if eye_icons.count() > 0 and eye_icons.first.is_visible():
                eye_icons.first.click()
                time.sleep(0.5)
        except Exception:
            pass

        rows = page.locator('table tbody tr').all()
        for row in rows:
            cells = [c.inner_text().strip() for c in row.locator('td').all()]
            if len(cells) >= 5 and "decodo.com" in cells[3]:
                proto = cells[0].replace("//", "").rstrip(":") or "http"
                u = cells[1]
                pw = cells[2]
                host = cells[3]
                port = cells[4]
                if u and pw and host and port and "..." not in pw:
                    proxies.append(f"{proto}://{u}:{pw}@{host}:{port}")
    except Exception:
        pass

    # 6. Fallback ekstraksi endpoint + header autentikasi
    try:
        content = page.content()
        endpoints = re.findall(r'([a-zA-Z0-9.-]*decodo\.com):(\d{4,5})', content, re.I)

        user_match = re.search(r'username[:\s=]+([a-zA-Z0-9_-]+)', content, re.I)
        pass_match = re.search(r'password[:\s=]+([a-zA-Z0-9_-]+)', content, re.I)

        if not user_match:
            auth_div = page.locator('div:has-text("AUTHENTICATION") + div, div:has-text("AUTHENTICATION")')
            if auth_div.count() > 0:
                m_u = re.search(r'([a-zA-Z0-9_-]{6,})', auth_div.first.inner_text())
                if m_u:
                    user_match = m_u

        if endpoints and user_match:
            u = user_match.group(1) if hasattr(user_match, "group") else user_match
            pw = pass_match.group(1) if pass_match else "DecodoPass123"
            for host, port in endpoints:
                p_url = f"http://{u}:{pw}@{host}:{port}"
                if p_url not in proxies:
                    proxies.append(p_url)

        found_full = re.findall(r'https?://[a-zA-Z0-9._-]+:[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+:\d+', content)
        for p in found_full:
            proxies.append(p if p.startswith("http") else f"http://{p}")
    except Exception:
        pass

    return list(dict.fromkeys(proxies))


def hunt_single_decodo(
    index: int,
    total: int,
    proxy_config: Dict[str, Any],
    headless: bool = True,
    card_config: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Eksekusi alur pendaftaran 1 akun Decodo menggunakan proxy:
    1. Buat email Cloudflare
    2. Register via CloakBrowser dengan proxy
    3. Verifikasi email via inbox worker
    4. Navigasi aktivasi / klaim trial dengan kartu kredit
    5. Ambil proxy HTTP
    """
    try:
        import cloakbrowser
    except ImportError:
        raise RuntimeError("CloakBrowser belum terpasang. Jalankan: pip install cloakbrowser")

    cf_client = CloudflareMailClient.from_config()
    if not cf_client.is_configured():
        raise RuntimeError("Konfigurasi Cloudflare Mail belum lengkap di config/settings.json")

    email, domain = cf_client.create_mailbox()
    password = generate_strong_password()
    card = card_config or load_card_config()
    proxy_display = format_proxy_display(proxy_config)

    solver_url = load_solver_url()
    if solver_url:
        if not ensure_sidecar_running(solver_url):
            print(f"  {Fore.YELLOW}[!] Captcha-solver sidecar tidak siap di {solver_url} — hunt tetap berjalan, "
                  f"tetapi challenge captcha mungkin tidak terselesaikan otomatis.{Style.RESET_ALL}")

    result = {
        "email": email,
        "password": password,
        "proxy": proxy_display,
        "status": "FAILED",
        "proxies": [],
        "verified": False,
        "notes": ""
    }

    print(f"\n{Fore.CYAN}┌────────────────────────────────────────────────────────────────────────┐{Style.RESET_ALL}")
    print(f"{Fore.CYAN}│{Style.RESET_ALL} 🦊 {Fore.YELLOW}Akun Decodo [{index}/{total}]{Style.RESET_ALL}: {Fore.WHITE}{email}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}│{Style.RESET_ALL} 🔑 Password   : {Fore.WHITE}{password}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}│{Style.RESET_ALL} 🌐 Proxy      : {Fore.GREEN}{proxy_display}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}└────────────────────────────────────────────────────────────────────────┘{Style.RESET_ALL}")

    proxy_for_browser = proxy_config.copy()
    proxy_for_browser["bypass"] = "localhost,127.0.0.1,*.stripe.com,*.stripe.network,stripe.com,stripe.network,*.paypal.com,paypal.com,*.paypalobjects.com"

    # CloakBrowser = stealth Chromium (Playwright). Camoufox (Firefox) TIDAK bisa
    # melewati Cloudflare Decodo: iframe cross-origin tak bisa diklik (url=''), dan
    # cf_clearance Chrome tak bisa di-replay ke Firefox (TLS/JA3 berbeda). Chromium
    # memakai teknik klik humanized yang sama dan lolos challenge dalam ~30 detik.
    browser_opts = {
        "headless": headless,
        "proxy": proxy_for_browser,
        "humanize": True,
    }
    if check_geoip_support():
        browser_opts["geoip"] = True

    try:
        with cloakbrowser.launch(**browser_opts) as browser:
            page = browser.new_page()

            # Izinkan baca/tulis clipboard: panen proxy via menu 'Copy' memakai
            # navigator.clipboard. Di headful Chromium, readText() tanpa izin akan
            # memunculkan prompt dan MENGGANTUNG page.evaluate tanpa batas waktu.
            try:
                page.context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass

            # Step 1: Navigasi ke halaman pendaftaran Decodo
            print(f"  {Fore.CYAN}[1/5] Membuka formulir pendaftaran Decodo via CloakBrowser & Proxy...{Style.RESET_ALL}")
            try:
                page.goto(DECODO_REGISTER_URL, wait_until="commit", timeout=45000)
            except Exception as e:
                print(f"  {Fore.RED}[!] Gagal membuka formulir (Proxy error/timeout): {e}{Style.RESET_ALL}")
                result["notes"] = f"Proxy error: {e}"
                return result

            # Tunggu Cloudflare turnstile dan form muncul (solver auto-solve direct tanpa proxy)
            if not wait_for_cloudflare_and_form(page, selector="#newEmail", timeout=180, solver_url=solver_url, proxy_str=format_proxy_string(proxy_config)):
                print(f"  {Fore.RED}[!] Timeout menunggu form pendaftaran Decodo (Cloudflare challenge / Proxy blocked).{Style.RESET_ALL}")
                result["notes"] = "Timeout form register (Cloudflare Turnstile / Proxy blocked)"
                return result

            # Step 2: Isi formulir registrasi
            print(f"  {Fore.CYAN}[2/5] Mengisi data akun dan menyetujui ketentuan...{Style.RESET_ALL}")
            time.sleep(1)
            page.fill("#newEmail", email)
            time.sleep(0.5)
            page.fill("#newPassword", password)
            time.sleep(0.5)

            # Centang acceptTerms via evaluate JavaScript
            page.evaluate('''() => {
                const cb = document.getElementById("acceptTerms");
                if (cb) {
                    cb.click();
                    cb.checked = true;
                    cb.dispatchEvent(new Event("change", {bubbles: true}));
                }
            }''')
            time.sleep(0.5)

            # Klik tombol Continue
            continue_btn = page.locator('button:has-text("Continue")')
            continue_btn.click(force=True)
            print(f"  {Fore.GREEN}[+] Formulir terkirim! Menunggu konfirmasi backend Decodo...{Style.RESET_ALL}")
            time.sleep(6)

            # Step 3: Tunggu email verifikasi via Cloudflare Worker
            print(f"  {Fore.CYAN}[3/5] Memeriksa kotak masuk Cloudflare Worker ({email})...{Style.RESET_ALL}")
            try:
                verif_data = cf_client.wait_for_verification(
                    address=email,
                    timeout=180,
                    poll_interval=4,
                    log=lambda m: print(f"    {Fore.LIGHTBLACK_EX}{m}{Style.RESET_ALL}"),
                    service_name="Decodo"
                )
                verif_link = verif_data.get("value")
                if not verif_link:
                    raise CloudflareMailError("Tautan verifikasi kosong")
                result["verified"] = True
                print(f"  {Fore.GREEN}✓ Tautan aktivasi ditemukan: {verif_link}{Style.RESET_ALL}")
            except Exception as e:
                print(f"  {Fore.RED}[!] Gagal verifikasi email: {e}{Style.RESET_ALL}")
                result["notes"] = f"Gagal email verif: {e}"
                return result

            # Step 4: Buka tautan verifikasi
            print(f"  {Fore.CYAN}[4/5] Memvalidasi tautan aktivasi Decodo...{Style.RESET_ALL}")
            try:
                page.goto(verif_link, wait_until="commit", timeout=60000)
            except Exception as e:
                print(f"  {Fore.RED}[!] Gagal membuka link verifikasi via proxy: {e}{Style.RESET_ALL}")
                result["notes"] = f"Link verif error: {e}"
                return result

            # Tunggu sampai diarahkan ke dashboard
            for _ in range(20):
                time.sleep(1)
                t = page.title()
                if "Just a moment" not in t and "Loading" not in t and "Verify" not in t:
                    break

            time.sleep(3)
            current_url = page.url
            print(f"  {Fore.GREEN}✓ Akun terverifikasi! URL: {current_url}{Style.RESET_ALL}")

            # Step 5: Klik 'Start with a trial' & proses checkout pembayaran trial
            print(f"  {Fore.CYAN}[5/5] Mengklaim Free Trial Residential Decodo...{Style.RESET_ALL}")

            # Pastikan browser berada di halaman pricing atau checkout
            if "residential-proxies/pricing" not in page.url and "payment" not in page.url and "checkout" not in page.url:
                print(f"  {Fore.CYAN}[*] Mengarahkan ke halaman pricing Decodo...{Style.RESET_ALL}")
                try:
                    page.goto(DECODO_PRICING_URL, wait_until="commit", timeout=45000)
                    time.sleep(3)
                except Exception as e:
                    print(f"  {Fore.YELLOW}[!] Peringatan navigasi pricing: {e}{Style.RESET_ALL}")

            # Refresh jika banner verifikasi email masih tersisa di browser
            try:
                if page.locator('text="Verify your email"').count() > 0:
                    print(f"  {Fore.CYAN}[*] Me-refresh halaman agar status verifikasi aktif...{Style.RESET_ALL}")
                    time.sleep(2)
                    page.reload(wait_until="commit")
                    time.sleep(3)
            except Exception:
                pass

            # Klik tombol 'Start with a trial' jika belum di halaman checkout
            if "payment" not in page.url and page.locator('text="Select your payment method"').count() == 0:
                print(f"  {Fore.CYAN}[*] Mencari dan mengklik tombol 'Start with a trial'...{Style.RESET_ALL}")
                trial_clicked = click_start_trial_button(page, timeout=15)
                if trial_clicked:
                    print(f"  {Fore.GREEN}✓ Tombol 'Start with a trial' berhasil diklik!{Style.RESET_ALL}")
                    time.sleep(0.2)
                else:
                    print(f"  {Fore.YELLOW}[!] Tombol 'Start with a trial' tidak ditemukan atau checkout sudah aktif.{Style.RESET_ALL}")

            # Tunggu sampai formulir checkout (Shipping / Payment) benar-benar terlihat di DOM
            print(f"  {Fore.CYAN}[*] Menunggu formulir checkout Decodo termuat...{Style.RESET_ALL}")
            checkout_ready = wait_for_checkout_page(page, timeout=90)
            if not checkout_ready:
                print(f"  {Fore.RED}[!] Timeout: Formulir checkout Decodo tidak muncul setelah 90 detik.{Style.RESET_ALL}")
                try:
                    base_out = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    page.screenshot(path=os.path.join(base_out, "output", "checkout_timeout_debug.png"))
                except Exception:
                    pass
                if not headless:
                    print(f"  {Fore.YELLOW}[*] Mode headful: Menahan browser selama 15 detik agar pengguna dapat melihat status halaman...{Style.RESET_ALL}")
                    time.sleep(15)
                result["notes"] = "Timeout formulir checkout"
                return result

            print(f"  {Fore.GREEN}✓ Formulir checkout Decodo berhasil termuat dan terlihat!{Style.RESET_ALL}")

            # Cek status KYC jika terdeteksi awal
            body_text = ""
            try:
                body_text = page.locator("body").inner_text()
            except Exception:
                pass
            current_url = page.url

            if "ID verification" in body_text or "proxy-activation" in current_url:
                print(f"  {Fore.YELLOW}⚠️ Decodo mendeteksi akun baru membutuhkan verifikasi ID (Stripe Identity KYC).{Style.RESET_ALL}")
                result["status"] = "PENDING_KYC"
                result["notes"] = "Email terverifikasi, menunggu ID KYC Decodo"
            else:
                # 1. Isi formulir Shipping Address secara instan (<100ms) begitu form muncul
                print(f"  {Fore.CYAN}[*] Mengisi data alamat pengiriman secara instan...{Style.RESET_ALL}")
                shipping_addr = generate_random_shipping_info()
                shipping_filled = False
                for fill_attempt in range(3):
                    shipping_filled = fill_shipping_address(page, shipping_addr)
                    if shipping_filled:
                        break
                    time.sleep(0.2)

                if shipping_filled:
                    print(f"  {Fore.GREEN}✓ Alamat pengiriman terisi: {shipping_addr['name']} | {shipping_addr['street']}, {shipping_addr['city']}, {shipping_addr['state']} ({shipping_addr['state_code']}) {shipping_addr['zip']}, {shipping_addr['country']}{Style.RESET_ALL}")
                else:
                    print(f"  {Fore.YELLOW}[!] Form shipping terisi sebagian: {shipping_addr['name']} | {shipping_addr['city']}, {shipping_addr['state']} ({shipping_addr['country']}){Style.RESET_ALL}")

                # 2. Isi data Kartu Kredit & verifikasi terisi
                has_card = bool(card.get("card_number"))
                if has_card:
                    print(f"  {Fore.CYAN}[*] Memasukkan data kartu kredit untuk klaim trial...{Style.RESET_ALL}")
                    card_filled = False
                    for card_attempt in range(15):
                        card_filled = fill_card_in_page_or_frames(page, card)
                        if card_filled:
                            break
                        time.sleep(1)

                    if card_filled:
                        print(f"  {Fore.GREEN}✓ Data kartu kredit berhasil dimasukkan!{Style.RESET_ALL}")
                    else:
                        print(f"  {Fore.YELLOW}[!] Peringatan: Iframe/field kartu kredit belum terdeteksi penuh.{Style.RESET_ALL}")

                    time.sleep(1)

                    # 3. Klik tombol 'Save' / 'Start trial'
                    save_btn = None
                    for t in [page] + list(page.frames):
                        try:
                            s = t.locator('button:has-text("Save"), button:has-text("Save payment information"), button:has-text("Save shipping information"), button:has-text("Start free trial"), button:has-text("Start trial"), button:has-text("Continue"), button:has-text("Subscribe"), button[type="submit"], button.SubmitButton')
                            if s.count() > 0:
                                for idx in range(s.count()):
                                    candidate = s.nth(idx)
                                    if candidate.is_visible():
                                        txt = (candidate.inner_text() or "").strip().lower()
                                        if any(k in txt for k in ["save", "start", "continue", "subscribe", "pay"]) or candidate.get_attribute("type") == "submit":
                                            save_btn = candidate
                                            break
                            if save_btn:
                                break
                        except Exception:
                            pass

                    if save_btn:
                        print(f"  {Fore.CYAN}[*] Mengklik tombol 'Save' pembayaran...{Style.RESET_ALL}")
                        try:
                            save_btn.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        save_btn.click(force=True)
                        time.sleep(3)
                    else:
                        print(f"  {Fore.YELLOW}[!] Tombol 'Save' belum ditemukan, mencoba submit form...{Style.RESET_ALL}")

                    # 4. Tangani modal hCaptcha ('One more step before you're done')
                    # Headful: beri waktu lebih panjang agar manusia/vision solver bisa
                    # menyelesaikan puzzle setelah checkbox fallback memunculkannya.
                    _hcap_timeout = 180 if not headless else 75
                    hcap_ok = handle_hcaptcha_checkout_challenge(page, proxy_config, timeout=_hcap_timeout)

                    # 5. Cek konfirmasi sukses ('Your purchase was successful') & klik 'Begin proxy setup'
                    time.sleep(2)
                    begin_btn = page.locator('button:has-text("Begin proxy setup"), a:has-text("Begin proxy setup")')
                    if begin_btn.count() > 0 and begin_btn.first.is_visible():
                        print(f"  {Fore.GREEN}✓ Pembelian trial sukses! Mengklik 'Begin proxy setup'...{Style.RESET_ALL}")
                        begin_btn.first.click(force=True)
                        time.sleep(6)
                        result["status"] = "ACTIVE"
                    elif "Your purchase was successful" in (page.locator("body").inner_text() or "") or "residential-proxies" in page.url or "proxy-setup" in page.url:
                        print(f"  {Fore.GREEN}✓ Pembelian trial sukses terkonfirmasi!{Style.RESET_ALL}")
                        result["status"] = "ACTIVE"
                    else:
                        print(f"  {Fore.YELLOW}[!] Peringatan: Konfirmasi checkout belum selesai atau hCaptcha belum terselesaikan.{Style.RESET_ALL}")
                        result["status"] = "PENDING_CAPTCHA"
                        result["notes"] = "hCaptcha checkout belum terselesaikan"
                else:
                    print(f"  {Fore.LIGHTBLACK_EX}ℹ️ Kartu kredit belum diisi di settings.json (decodo_card). Lewati pengisian kartu.{Style.RESET_ALL}")
                    result["status"] = "ACTIVE"

            # 6. Ekstrak proxy residential dari dashboard
            proxies = extract_proxies_from_dashboard(page)
            if not proxies:
                try:
                    page.goto(DECODO_RESI_URL, wait_until="commit", timeout=30000)
                    time.sleep(4)
                    proxies = extract_proxies_from_dashboard(page)
                except Exception:
                    pass

            if proxies:
                result["proxies"] = proxies
                print(f"  {Fore.GREEN}✓ Berhasil mengekstrak {len(proxies)} Residential Proxy Decodo!{Style.RESET_ALL}")

    except Exception as e:
        err_msg = str(e)
        print(f"  {Fore.RED}[!] Error browser / proxy: {err_msg}{Style.RESET_ALL}")
        result["notes"] = f"Browser error: {err_msg[:60]}"

    return result


def run_decodo_hunter(
    total: int = 1,
    headless: Optional[bool] = None,
    sync_9router_db: Optional[str] = None,
    output_dir: Optional[str] = None
) -> List[str]:
    """Menjalankan hunter Decodo untuk sejumlah akun tertentu (wajib menggunakan proxy)."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = output_dir or os.path.join(base_dir, "output")
    os.makedirs(out_dir, exist_ok=True)

    is_headless = get_decodo_headless_config(headless)

    proxy_pool = load_proxy_pool()
    if not proxy_pool:
        print(f"\n{Fore.RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        print(f"{Fore.RED}{Style.BRIGHT}❌ REGISTRASI DECODO WAJIB MENGGUNAKAN PROXY!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}• File 'proxies.txt' kosong atau belum diisi proxy yang valid.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}• Silakan tambahkan minimal 1 proxy ke file: {Fore.CYAN}proxies.txt{Style.RESET_ALL}")
        print(f"{Fore.WHITE}• Format contoh dapat dilihat pada: {Fore.CYAN}proxies.example.txt{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}  Format didukung: http://user:pass@ip:port, socks5://..., ip:port:user:pass, ip:port{Style.RESET_ALL}")
        print(f"{Fore.RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
        return []

    db_path = sync_9router_db or find_default_db()
    card_cfg = load_card_config()

    output_accounts_txt = os.path.join(out_dir, "decodo_accounts.txt")
    output_decodo_txt = os.path.join(out_dir, "decodo_residential.txt")
    output_elite_txt = os.path.join(out_dir, "live_elite.txt")

    cf_checker = CloudflareMailClient.from_config()
    cf_status_str = f"{Fore.GREEN}[Cloudflare Worker Aktif ✓]{Style.RESET_ALL}" if cf_checker.is_configured() else f"{Fore.RED}[Belum Dikonfigurasi ❌]{Style.RESET_ALL}"
    card_status_str = f"{Fore.GREEN}[Tersedia ✓ ({card_cfg.get('card_number', '')[-4:]})]{Style.RESET_ALL}" if card_cfg.get("card_number") else f"{Fore.YELLOW}[Kosong (Hanya Register & Verif)]{Style.RESET_ALL}"

    mode_label = f"{Fore.CYAN}Headless (Latar Belakang){Style.RESET_ALL}" if is_headless else f"{Fore.GREEN}{Style.BRIGHT}Headful (Tampil Jendela Browser){Style.RESET_ALL}"

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🌾 PETANIPROXY x DECODO RESIDENTIAL HUNTER (CLOAKBROWSER){Style.RESET_ALL}")
    print(f"  • Target Akun       : {Fore.YELLOW}{total}{Style.RESET_ALL} Akun")
    print(f"  • Engine Browser    : CloakBrowser Stealth Anti-Detect Chromium ({mode_label})")
    print(f"  • Pool Proxy        : {Fore.GREEN}{len(proxy_pool)} Proxy Aktif di proxies.txt ✓{Style.RESET_ALL}")
    print(f"  • Verifikasi Email  : {cf_status_str}")
    print(f"  • Data Kartu Kredit : {card_status_str}")
    print(f"  • BansosRouter SQLite: {Fore.WHITE}{db_path or 'Tidak Terdeteksi (Skip)'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")

    all_gathered_proxies = []
    successful_accounts = 0

    proxy_index = 0

    for i in range(1, total + 1):
        # Auto-failover rotasi proxy jika proxy timeout / terblokir Cloudflare
        max_proxy_retries = min(3, len(proxy_pool))
        res = None
        for attempt in range(max_proxy_retries):
            curr_proxy = proxy_pool[proxy_index % len(proxy_pool)]
            proxy_index += 1
            if attempt > 0:
                print(f"  {Fore.YELLOW}🔄 Mengalihkan ke proxy cadangan ({attempt+1}/{max_proxy_retries}): {format_proxy_display(curr_proxy)}...{Style.RESET_ALL}")
            res = hunt_single_decodo(i, total, proxy_config=curr_proxy, headless=is_headless, card_config=card_cfg)

            # Jika lolos atau tidak timeout form registrasi, jangan rotasi lagi
            if res.get("status") != "FAILED" or "Timeout form register" not in res.get("notes", ""):
                break
            if attempt < max_proxy_retries - 1:
                print(f"  {Fore.YELLOW}⚠️ Proxy {res.get('proxy')} tidak lolos verifikasi Cloudflare. Merotasi ke proxy berikutnya...{Style.RESET_ALL}")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Catat akun ke decodo_accounts.txt
        account_line = f"{res['email']}:{res['password']} | {res['status']} | Proxy: {res.get('proxy', '-')} | {now_str} | {res['notes']}"
        append_to_file(output_accounts_txt, [account_line])

        if res.get("verified"):
            successful_accounts += 1

        # Catat proxy jika ada
        if res.get("proxies"):
            append_to_file(output_decodo_txt, res["proxies"])
            append_to_file(output_elite_txt, res["proxies"])
            if db_path:
                sync_to_9router(res["proxies"], db_path)
            all_gathered_proxies.extend(res["proxies"])

        if i < total:
            print(f"  {Fore.LIGHTBLACK_EX}Istirahat 3 detik sebelum akun berikutnya...{Style.RESET_ALL}")
            time.sleep(3)

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🎉 PANEN DECODO SELESAI!{Style.RESET_ALL}")
    print(f"  • Akun Berhasil Terverifikasi: {Fore.YELLOW}{successful_accounts}/{total}{Style.RESET_ALL}")
    print(f"  • Total Proxy Dikumpulkan    : {Fore.YELLOW}{len(all_gathered_proxies)}{Style.RESET_ALL}")
    print(f"  • Berkas Daftar Akun         : {Fore.WHITE}{output_accounts_txt}{Style.RESET_ALL}")
    print(f"  • Berkas Proxy HTTP          : {Fore.WHITE}{output_decodo_txt}{Style.RESET_ALL}")
    if db_path:
        print(f"  • DB BansosRouter            : {Fore.WHITE}{db_path}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")

    return all_gathered_proxies


def main():
    total = 1
    headless = True
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        total = int(sys.argv[1])
    run_decodo_hunter(total=total, headless=headless)


if __name__ == "__main__":
    main()
