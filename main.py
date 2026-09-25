#!/usr/bin/env python3
"""
PetaniProxy v1.1.0
Pusat Amunisi Proxy Bersih, Segar & Berputar Otomatis (Local Rotating Gateway & WARP)
"""

import os
import sys
import glob
import time
import json
import argparse
import importlib.util
import subprocess
import requests
from typing import Optional, List

# Force UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = Style = DummyColor()

# ─────────────────────────────────────────────────────────────────────────────
# Self-heal interpreter: paket opsional (mis. cloakbrowser) hanya terpasang di
# venv project. Tanpa ini, `py main.py` / `python main.py` memakai Python global
# dan Decodo Hunter gagal dengan "No module named 'cloakbrowser'".
# ─────────────────────────────────────────────────────────────────────────────
_VENV_REEXEC_FLAG = "PETANIPROXY_VENV_REEXEC"


def _venv_candidates(base_dir: str) -> List[str]:
    """Kandidat interpreter venv project (venv lalu .venv, sama seperti run.bat)."""
    rel = os.path.join("Scripts", "python.exe") if sys.platform == "win32" else os.path.join("bin", "python")
    return [os.path.join(base_dir, name, rel) for name in ("venv", ".venv")]


def _venv_has_package(python_path: str, package: str) -> bool:
    """Cek isi site-packages venv langsung dari disk (tanpa spawn subprocess)."""
    root = os.path.dirname(os.path.dirname(python_path))
    patterns = (
        os.path.join(root, "Lib", "site-packages", package),
        os.path.join(root, "lib", "python*", "site-packages", package),
    )
    return any(glob.glob(p) for p in patterns)


def _ensure_project_venv():
    """
    Re-exec ke venv project HANYA jika keempat syarat ini terpenuhi:
      1. belum pernah re-exec (anti-loop),
      2. tidak dimatikan via PETANIPROXY_NO_VENV,
      3. interpreter aktif TIDAK punya `cloakbrowser`,
      4. ada venv project yang PUNYA `cloakbrowser`.

    Syarat 3+4 sengaja sempit supaya run yang sudah benar tidak pernah diubah.
    """
    if os.environ.get(_VENV_REEXEC_FLAG) or os.environ.get("PETANIPROXY_NO_VENV"):
        return
    try:
        if importlib.util.find_spec("cloakbrowser") is not None:
            return
    except (ImportError, ValueError):
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    current = os.path.abspath(sys.executable)
    script = os.path.abspath(__file__)

    for candidate in _venv_candidates(base_dir):
        if not os.path.isfile(candidate):
            continue
        if os.path.abspath(candidate) == current:
            continue
        if not _venv_has_package(candidate, "cloakbrowser"):
            continue

        print(f"{Fore.YELLOW}[i] Interpreter aktif tidak punya 'cloakbrowser' "
              f"({sys.executable})\n    ↳ beralih ke venv project: {candidate}{Style.RESET_ALL}")
        os.environ[_VENV_REEXEC_FLAG] = "1"
        argv = [candidate, script, *sys.argv[1:]]
        try:
            if sys.platform == "win32":
                # os.execv di Windows menggabung argv jadi satu command line TANPA
                # quoting, sehingga path berspasi ("D:\CODING PROJECT\...") pecah.
                # subprocess meng-quote lewat list2cmdline, jadi aman.
                sys.exit(subprocess.run(argv).returncode)
            os.execv(candidate, argv)
        except OSError as exc:
            print(f"{Fore.RED}[!] Gagal beralih ke venv: {exc}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}    Jalankan manual: '{candidate}' '{script}'{Style.RESET_ALL}")
            return


_ensure_project_venv()

from core.fetcher import fetch_proxies_sync
from core.checker import check_proxies_pool, DEFAULT_TEST_URL
from core.exporter import export_all_formats
from core.server import start_proxy_server
from core.updater import (
    get_local_version_info,
    check_for_updates,
    render_update_banner,
    show_full_announcement,
    perform_update
)

BANNER = f"""{Fore.CYAN}{Style.BRIGHT}
  ██████╗ ███████╗████████╗ █████╗ ███╗   ██╗██╗██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗
  ██╔══██╗██╔════╝╚══██╔══╝██╔══██╗████╗  ██║██║██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝
  ██████╔╝█████╗     ██║   ███████║██╔██╗ ██║██║██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ 
  ██╔═══╝ ██╔══╝     ██║   ██╔══██║██║╚██╗██║██║██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  
  ██║     ███████╗   ██║   ██║  ██║██║ ╚████║██║██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   
  ╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   
{Fore.YELLOW}              🌾 PetaniProxy: Panen Proxy Cepat, Segar & Bergizi 🚜
{Fore.WHITE}          High-Speed Multi-Protocol Scraper, Validator & Local Gateway
{Fore.LIGHTBLACK_EX}                 Created & Maintained by {Fore.CYAN}@itzluthfi{Fore.LIGHTBLACK_EX} (github.com/itzluthfi)
{Style.RESET_ALL}"""

def get_settings_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "config", "settings.json")

def load_settings() -> dict:
    spath = get_settings_path()
    if os.path.exists(spath):
        try:
            with open(spath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(data: dict):
    spath = get_settings_path()
    os.makedirs(os.path.dirname(spath), exist_ok=True)
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def open_in_explorer(target_path: str):
    """Buka folder atau sorot file di File Manager (Windows Explorer, macOS Finder, Linux)."""
    try:
        norm = os.path.normpath(target_path)
        if os.path.isfile(norm):
            if sys.platform == "win32":
                os.system(f'explorer /select,"{norm}"')
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", "-R", norm])
            else:
                import subprocess
                subprocess.run(["xdg-open", os.path.dirname(norm)])
        elif os.path.isdir(norm):
            if sys.platform == "win32":
                os.startfile(norm)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", norm])
            else:
                import subprocess
                subprocess.run(["xdg-open", norm])
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka File Manager: {e}{Style.RESET_ALL}")

def open_in_text_editor(file_path: str):
    """Buka file text menggunakan default editor sistem (Notepad, TextEdit, atau default Linux)."""
    try:
        norm = os.path.normpath(file_path)
        if not os.path.exists(norm):
            return
        if sys.platform == "win32":
            os.system(f'start notepad "{norm}"')
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", "-t", norm])
        else:
            import subprocess
            try:
                subprocess.run(["xdg-open", norm])
            except Exception:
                pass
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka Text Editor: {e}{Style.RESET_ALL}")

def open_url_in_browser(url: str):
    """Buka URL di browser default sistem."""
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka browser: {e}{Style.RESET_ALL}")

def find_9router_db() -> Optional[str]:
    """Smart auto-detection for BansosRouter / 9Router SQLite database."""
    cfg_db = load_settings().get("9router_db_path")
    if cfg_db and os.path.exists(cfg_db):
        return cfg_db

    env_path = os.environ.get("BANSOS_ROUTER_DB") or os.environ.get("NINEROUTER_DB")
    if env_path and os.path.exists(env_path):
        return env_path

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(base_dir, "..", "eLrouter", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router-mibp-version", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "bansos-router", "data", "db", "data.sqlite")),
        "D:/FREELANCE/eLrouter/data/db/data.sqlite",
        "D:/FREELANCE/9router-mibp-version/data/db/data.sqlite",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def install_dependencies(quiet: bool = False) -> bool:
    """Auto-install or repair project dependencies using requirements.txt."""
    import subprocess
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}📦 MEMASANG DEPENDENSI PETANIPROXY...{Style.RESET_ALL}")
    print(f"{Fore.LIGHTBLACK_EX}Menjalankan: {sys.executable} -m pip install -r requirements.txt{Style.RESET_ALL}\n")
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
    if quiet:
        cmd.append("--quiet")
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"\n{Fore.GREEN}✓ Semua dependensi berhasil dipasang! Siap tempur! 🌾🚜{Style.RESET_ALL}")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
        return True
    else:
        print(f"\n{Fore.RED}⚠️ Pemasangan paket selesai dengan beberapa catatan/peringatan.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
        return False

def check_initial_dependencies() -> bool:
    """Smart check on first startup to ensure user has essential packages."""
    missing = []
    checks = [
        ("httpx", "httpx"),
        ("requests", "requests"),
        ("colorama", "colorama"),
        ("DrissionPage", "DrissionPage"),
        ("speech_recognition", "SpeechRecognition"),
        ("pydub", "pydub")
    ]
    for mod, pkg in checks:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n{Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}{Style.BRIGHT}📦 SETUP AWAL PETANIPROXY: Dependensi Belum Lengkap{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTBLACK_EX}Terdeteksi beberapa paket yang belum terpasang di sistem Python kamu:{Style.RESET_ALL}")
        for m in missing:
            print(f"   {Fore.RED}•{Fore.WHITE} {m}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        ans = input(f"\n{Fore.CYAN}👉 Pasang semua dependensi otomatis sekarang (1-Klik via pip)? [Y/n]: {Style.RESET_ALL}").strip().lower()
        if ans in ("", "y", "yes"):
            return install_dependencies()
    return True

def find_grok_python() -> str:
    """Detect python executable for Grok Farm / Webshare Hunter."""
    candidates = [
        r"D:\FREELANCE\grok-register\venv\Scripts\python.exe",
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "grok-register", "venv", "Scripts", "python.exe")),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return sys.executable

def run_webshare_hunter(accounts: int = 1, headless: bool = True) -> bool:
    """Run Webshare Hunter to harvest residential clean proxies that bypass Cloudflare."""
    import subprocess
    grok_dir = r"D:\FREELANCE\grok-register"
    if not os.path.exists(grok_dir):
        grok_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "grok-register"))
    
    ws_script = os.path.join(grok_dir, "webshare_hunter_auto.py")
    if not os.path.exists(ws_script):
        print(f"{Fore.RED}❌ Script Webshare Hunter tidak ditemukan di {ws_script}{Style.RESET_ALL}")
        return False

    py_exec = find_grok_python()
    print(f"\n{Fore.CYAN}{'🏢 Menjalankan Webshare Residential Hunter...' if CURRENT_LANG == 'ID' else '🏢 Launching Webshare Residential Hunter...'}{Style.RESET_ALL}")
    print(f"  • Target: {Fore.YELLOW}{accounts} Akun Webshare ({accounts * 10} IP Residensial AS/Eropa){Style.RESET_ALL}")
    print(f"  • Mode:   {Fore.WHITE}{'Background (Headless)' if headless else 'Tampak Layar'}{Style.RESET_ALL}")
    print(f"  • Hasil:  {Fore.GREEN}Otomatis lolos Cloudflare xAI Grok & disetor ke proxies.txt + BansosRouter{Style.RESET_ALL}\n")

    cmd = [py_exec, ws_script, str(accounts)]
    if headless:
        cmd.append("--headless")

    try:
        res = subprocess.run(cmd, cwd=grok_dir)
        return res.returncode == 0
    except Exception as e:
        print(f"{Fore.RED}❌ Gagal menjalankan Webshare Hunter: {e}{Style.RESET_ALL}")
        return False

def print_live_proxy(proxy_res: dict, current_count: int, target: int):
    proto = proxy_res.get("protocol", "http").upper()
    lat = proxy_res.get("latency_ms", 0)
    proxy = proxy_res.get("proxy", "")
    cc = proxy_res.get("country_code", "??")
    country = proxy_res.get("country", "Unknown")
    isp = proxy_res.get("isp", "-")
    anon = proxy_res.get("anonymity", "Elite")
    
    # Anonymity badge styling
    if anon == "Elite":
        anon_badge = f"{Fore.CYAN}{Style.BRIGHT}[ELITE]{Style.RESET_ALL}"
    elif anon == "Anonymous":
        anon_badge = f"{Fore.MAGENTA}[ANON]{Style.RESET_ALL} "
    else:
        anon_badge = f"{Fore.YELLOW}[TRAN]{Style.RESET_ALL} "

    # Color based on latency
    if lat < 1000:
        lat_color = Fore.GREEN
    elif lat < 2500:
        lat_color = Fore.YELLOW
    else:
        lat_color = Fore.RED

    print(
        f"  {Fore.GREEN}🟢 [LIVE {current_count}/{target}]{Style.RESET_ALL} "
        f"{Fore.CYAN}{proto:<6}{Style.RESET_ALL} "
        f"{Fore.WHITE}{proxy:<21}{Style.RESET_ALL} | "
        f"{anon_badge} | "
        f"{lat_color}{lat:>4}ms{Style.RESET_ALL} | "
        f"{Fore.BLUE}[{cc}] {country:<13}{Style.RESET_ALL} | "
        f"{Fore.LIGHTBLACK_EX}{isp[:22]}{Style.RESET_ALL}"
    )

def run_harvester(
    protocols: list, 
    max_check: int = 200, 
    target_alive: int = 20, 
    timeout: float = 3.0, 
    workers: int = 50, 
    country: str = None, 
    anonymity: str = None,
    target_url: str = None,
    output_dir: str = None, 
    sync_9router: str = None,
    serve_port: int = None
):
    t_start = time.perf_counter()
    check_url = target_url or DEFAULT_TEST_URL
    print(f"\n{Fore.YELLOW}⚡ [1/3] Scraping raw candidates from open-source feeds...{Style.RESET_ALL}")
    candidates = fetch_proxies_sync(protocols=protocols, country_filter=country)
    
    if not candidates:
        print(f"{Fore.RED}❌ Gagal mengambil kandidat proxy dari feed.{Style.RESET_ALL}")
        return []

    url_hint = f" | Target: {check_url[:35]}" if target_url else ""
    anon_hint = f" | Anonymity: {anonymity.upper()}" if anonymity and anonymity.lower() != 'all' else ""
    print(f"\n{Fore.YELLOW}🔍 [2/3] Validating up to {max_check} candidates (Target alive: {target_alive}, Timeout: {timeout}s{url_hint}{anon_hint})...{Style.RESET_ALL}")
    
    live_proxies = check_proxies_pool(
        candidates=candidates,
        max_check=max_check,
        target_alive=target_alive,
        timeout=timeout,
        max_workers=workers,
        country_filter=country,
        anonymity_filter=anonymity,
        test_url=check_url,
        on_live_callback=print_live_proxy
    )

    elapsed_total = round(time.perf_counter() - t_start, 2)
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🎉 Validation Complete! Found {len(live_proxies)} active proxies in {elapsed_total}s.{Style.RESET_ALL}")

    if not live_proxies:
        print(f"{Fore.YELLOW}⚠️ Tidak ada proxy yang lolos batas timeout {timeout}s. Coba perbesar --timeout atau perbanyak --max.{Style.RESET_ALL}")
        return []

    print(f"\n{Fore.YELLOW}💾 [3/3] Exporting verified proxies to disk...{Style.RESET_ALL}")
    files = export_all_formats(live_proxies, output_dir=output_dir, sync_9router_db=sync_9router)
    
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Plain Text:  {Fore.WHITE}{files.get('all_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} URLs Format: {Fore.WHITE}{files.get('urls_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Elite Only:  {Fore.WHITE}{files.get('elite_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Rich JSON:   {Fore.WHITE}{files.get('json')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} CSV Sheet:   {Fore.WHITE}{files.get('csv')}{Style.RESET_ALL}")
    
    if "9router_db" in files:
        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} BansosRouter DB: {Fore.WHITE}Synced to {files['9router_db']}{Style.RESET_ALL}")

    # Display Top 3 Fastest
    print(f"\n{Fore.CYAN}🏆 TOP FASTEST PROXIES:{Style.RESET_ALL}")
    for idx, p in enumerate(live_proxies[:3], 1):
        proto = p.get('protocol', 'http').upper()
        anon = p.get('anonymity', 'Elite')
        print(f"  {idx}. {Fore.GREEN}{proto}://{p['proxy']}{Style.RESET_ALL} [{anon}] ({p['latency_ms']}ms) - [{p['country_code']}] {p['country']}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")

    if serve_port:
        print(f"{Fore.GREEN}{Style.BRIGHT}🌐 STARTING LOCAL ROTATING GATEWAY & REST API...{Style.RESET_ALL}")
        print(f"  • Forward Proxy Endpoint: {Fore.CYAN}http://127.0.0.1:{serve_port}{Style.RESET_ALL}")
        print(f"  • Random Proxy REST API:  {Fore.CYAN}http://127.0.0.1:{serve_port}/api/random{Style.RESET_ALL}")
        print(f"  • All Proxies REST API:   {Fore.CYAN}http://127.0.0.1:{serve_port}/api/all{Style.RESET_ALL}")
        print(f"  • Health & Status API:    {Fore.CYAN}http://127.0.0.1:{serve_port}/api/status{Style.RESET_ALL}")
        print(f"\n{Fore.WHITE}📋 SNIPPET SIAP PAKAI (COPY-PASTE):{Style.RESET_ALL}")
        print(f"  • {Fore.YELLOW}Python Requests:{Style.RESET_ALL} proxies={{'http': 'http://127.0.0.1:{serve_port}', 'https': 'http://127.0.0.1:{serve_port}'}}")
        print(f"  • {Fore.YELLOW}cURL Command:{Style.RESET_ALL}    curl -x http://127.0.0.1:{serve_port} https://api.ipify.org")
        print(f"  • {Fore.YELLOW}Browser Proxy:{Style.RESET_ALL}   Set Manual Proxy Host -> 127.0.0.1 | Port -> {serve_port}")
        print(f"\n{Fore.LIGHTBLACK_EX}Server running at 127.0.0.1:{serve_port}. Press Ctrl+C to stop.{Style.RESET_ALL}\n")
        start_proxy_server(live_proxies, host="127.0.0.1", port=serve_port, background=False)

    return live_proxies

def view_saved_results(output_dir: str = None):
    if not output_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "output")
    json_file = os.path.join(output_dir, "proxies.json")
    if not os.path.exists(json_file):
        print(f"\n{Fore.YELLOW}Belum ada riwayat hasil proxy tersimpan di {output_dir}. Jalankan harvest dulu!{Style.RESET_ALL}")
        return

    import json
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{Fore.CYAN}📁 HASIL PROXY TERAKHIR DARI {json_file}:{Style.RESET_ALL}")
    print(f"  • Terakhir diperbarui: {Fore.WHITE}{data.get('generated_at', '-')}{Style.RESET_ALL}")
    print(f"  • Total proxy aktif  : {Fore.GREEN}{data.get('total_alive', 0)}{Style.RESET_ALL}")
    print(f"  • Protokol           : {Fore.WHITE}{data.get('protocols', {})}{Style.RESET_ALL}\n")

    proxies = data.get("proxies", [])
    print(f"{Fore.CYAN}DAFTAR 10 PROXY TERCEPAT:{Style.RESET_ALL}")
    for idx, p in enumerate(proxies[:10], 1):
        proto = p.get('protocol', 'http').upper()
        print(f"  {idx:>2}. {Fore.GREEN}{proto:<6}{Style.RESET_ALL} {Fore.WHITE}{p['proxy']:<21}{Style.RESET_ALL} | {Fore.YELLOW}{p['latency_ms']:>4}ms{Style.RESET_ALL} | [{p['country_code']}] {p['country']} ({p.get('isp', '-')[:22]})")

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}PILIH AKSI GUDANG AMUNISI:{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 🚀 Nyalakan Gateway 8888 Memakai Stok Ini")
    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📂 Buka Folder Output di File Explorer")
    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 🧹 Bersihkan / Hapus Stok Lama")
    print(f"  {Fore.GREEN}[4]{Fore.WHITE} 🩺 Cek Kesehatan Stok Ini (Health Check)")
    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    sub = input(f"{Fore.YELLOW}Pilih aksi [1-4, 0=Kembali]: {Style.RESET_ALL}").strip()
    if sub == "1":
        print(f"\n{Fore.GREEN}✓ Menyalakan Gateway 8888 dengan {len(proxies)} proxy dari disk... Tekan Ctrl+C untuk stop.{Style.RESET_ALL}\n")
        start_proxy_server(proxies, port=8888, background=False, enable_health_check=True)
    elif sub == "2":
        open_in_explorer(output_dir)
    elif sub == "3":
        c_del = input(f"{Fore.RED}Yakin ingin menghapus seluruh file cache proxy di {output_dir}? [y/N]: {Style.RESET_ALL}").strip().lower()
        if c_del in ("y", "yes"):
            for fname in os.listdir(output_dir):
                if fname.endswith((".txt", ".json", ".csv")):
                    try:
                        os.remove(os.path.join(output_dir, fname))
                    except Exception:
                        pass
            print(f"\n{Fore.GREEN}✓ Stok gudang amunisi berhasil dibersihkan!{Style.RESET_ALL}")
    elif sub == "4":
        show_health_check_menu(target_file=json_file)

CURRENT_LANG = "ID"

def test_live_masking(port: int = 8888):
    """
    Fitur Pembuktian Langsung [T]:
    Uji apakah IP asli tertutup sempurna lewat Gateway 8888.
    """
    print(f"\n{Fore.CYAN}🧪 MEMERIKSA STATUS ANONIMITAS (LIVE MASKING TEST)...{Style.RESET_ALL}")
    
    # 1. Mendeteksi IP Asli
    print(f"  {Fore.LIGHTBLACK_EX}[1/2] Mendeteksi IP Asli perangkat kamu (Direct Connection)...{Style.RESET_ALL}")
    real_ip = "Unknown"
    real_isp = "Unknown"
    try:
        r = requests.get("https://ipwho.is/", timeout=5.0)
        if r.status_code == 200:
            d = r.json()
            real_ip = d.get("ip", "Unknown")
            real_isp = f"{d.get('connection', {}).get('isp', d.get('isp', '-'))} - {d.get('city', '-')}, {d.get('country', '-')}"
    except Exception:
        try:
            r = requests.get("https://api.ipify.org?format=json", timeout=4.0)
            real_ip = r.json().get("ip", "Unknown")
        except Exception:
            pass

    # 2. Menguji Gateway 127.0.0.1:8888
    print(f"  {Fore.LIGHTBLACK_EX}[2/2] Menguji koneksi lewat Rotating Gateway (127.0.0.1:{port})...{Style.RESET_ALL}")
    proxies = {
        "http": f"http://127.0.0.1:{port}",
        "https": f"http://127.0.0.1:{port}"
    }
    gateway_ip = None
    gateway_info = None
    try:
        r = requests.get("https://ipwho.is/", proxies=proxies, timeout=8.0)
        if r.status_code == 200:
            d = r.json()
            gateway_ip = d.get("ip")
            gateway_info = f"{d.get('connection', {}).get('isp', d.get('isp', '-'))} - {d.get('city', '-')}, {d.get('country', '-')}"
    except Exception:
        try:
            r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=6.0)
            if r.status_code == 200:
                gateway_ip = r.json().get("ip")
        except Exception:
            pass

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}🛡️  HASIL AUDIT IDENTITAS & PRIVASI KONEKSI:{Style.RESET_ALL}")
    print(f"  • IP Asli Kamu     : {Fore.YELLOW}{real_ip}{Style.RESET_ALL} ({real_isp})")
    
    if gateway_ip:
        print(f"  • IP Masked Gateway: {Fore.GREEN}{Style.BRIGHT}{gateway_ip}{Style.RESET_ALL} ({gateway_info or 'Masked Proxy'})")
        if gateway_ip != real_ip:
            print(f"\n  {Fore.GREEN}{Style.BRIGHT}✅ STATUS: 100% AMAN & TERSAMARKAN! (ZERO LEAK){Style.RESET_ALL}")
            print(f"  {Fore.LIGHTBLACK_EX}Identitas asli kamu tertutup sempurna. Website target melihat kamu dari IP proxy.{Style.RESET_ALL}")
        else:
            print(f"\n  {Fore.RED}⚠️ STATUS: IP Gateway sama dengan IP asli. Periksa kembali konfigurasi proxy.{Style.RESET_ALL}")
    else:
        print(f"  • Gateway {port}     : {Fore.RED}Belum Aktif (Offline){Style.RESET_ALL}")
        print(f"\n  {Fore.YELLOW}🚨 Woy, Gateway Petani (127.0.0.1:{port}) belum nyala Bos! 🎭{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTBLACK_EX}Masa mau ngetes topeng tapi belum dipasang topengnya?")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        ask = input(f"{Fore.CYAN}👉 Mau langsung nyalakan Gateway 8888 sekarang (1-Klik)? [Y/n]: {Style.RESET_ALL}").strip().lower()
        if ask in ("", "y", "yes"):
            print(f"\n{Fore.GREEN}🚀 Menyiapkan amunisi awal dan menyalakan Gateway {port}...{Style.RESET_ALL}")
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            initial = run_fast_harvester(max_latency_ms=1200, target_count=8, sync_db=bool(db_target))
            if initial:
                start_proxy_server(initial, port=port, background=True, enable_health_check=True)
                time.sleep(1.5)
                print(f"\n{Fore.GREEN}✓ Gateway berhasil aktif di background! Menguji kembali identitas...{Style.RESET_ALL}\n")
                return test_live_masking(port=port)
            else:
                print(f"{Fore.RED}❌ Gagal mendapatkan proxy hidup untuk mengisi gateway.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")

def show_health_check_menu(target_file: str = None, timeout: float = 3.5):
    """
    Fitur Cek Kesehatan Hasil Proxy [H]:
    Menguji file proxy (.txt / .json), mengukur latency, mendeteksi node mati,
    dan menyediakan opsi simpan file bersih atau langsung nyalakan gateway 8888.
    """
    global CURRENT_LANG
    from core.health_checker import check_file_health, save_healthy_proxies, load_proxies_from_file

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    selected_file = target_file
    if not selected_file:
        available_files = []
        for fname in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath) and fname.endswith((".txt", ".json")) and not fname.startswith("."):
                available_files.append((fname, fpath))

        # Prioritize webshare_residential.txt
        available_files.sort(key=lambda x: (0 if "webshare" in x[0] else 1, x[0]))

        print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        if CURRENT_LANG == "ID":
            print(f"{Fore.WHITE}{Style.BRIGHT}🩺  PETANIPROXY HEALTH CHECKER (CEK KESEHATAN AMUNISI){Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Uji konektivitas & latency riil dari file hasil proxy di disk.{Style.RESET_ALL}\n")
        else:
            print(f"{Fore.WHITE}{Style.BRIGHT}🩺  PETANIPROXY HEALTH CHECKER (AMMO PROBE ENGINE){Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Verify real-time connectivity & latency of proxy lists on disk.{Style.RESET_ALL}\n")

        if not available_files:
            msg = "⚠️ Tidak ditemukan file proxy di folder output/." if CURRENT_LANG == "ID" else "⚠️ No proxy files found in output/."
            print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")
            p_custom = "Masukkan path file proxy (.txt / .json): " if CURRENT_LANG == "ID" else "Enter custom proxy file path (.txt / .json): "
            manual_path = input(f"{Fore.CYAN}{p_custom}{Style.RESET_ALL}").strip(' "\'')
            if not manual_path or not os.path.exists(manual_path):
                print(f"{Fore.RED}{'File tidak ditemukan.' if CURRENT_LANG == 'ID' else 'File not found.'}{Style.RESET_ALL}")
                return
            selected_file = manual_path
        else:
            header_lbl = "PILIH FILE PROXY YANG INGIN DICEK:" if CURRENT_LANG == "ID" else "SELECT PROXY FILE TO PROBE:"
            print(f"{Fore.WHITE}{header_lbl}{Style.RESET_ALL}")
            for idx, (fname, fpath) in enumerate(available_files, 1):
                try:
                    count = len(load_proxies_from_file(fpath))
                except Exception:
                    count = "?"
                badge = f"{Fore.YELLOW}[RESIDENTIAL] " if "webshare" in fname else ""
                print(f"  {Fore.GREEN}[{idx}]{Fore.WHITE} {badge}{fname:<26} {Fore.LIGHTBLACK_EX}({count} proxy){Style.RESET_ALL}")

            custom_lbl = "Masukkan path file sendiri / custom" if CURRENT_LANG == "ID" else "Specify custom file path"
            cancel_lbl = "Kembali ke Menu Utama" if CURRENT_LANG == "ID" else "Back to Main Menu"
            print(f"  {Fore.CYAN}[C]{Fore.WHITE} 📁 {custom_lbl}")
            print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 {cancel_lbl}")
            print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")

            prompt_f = f"Pilih file [1-{len(available_files)}, C, 0=Kembali, default=1]: " if CURRENT_LANG == "ID" else f"Choose file [1-{len(available_files)}, C, 0=Back, default=1]: "
            f_choice = input(f"{Fore.YELLOW}{prompt_f}{Style.RESET_ALL}").strip()
            if f_choice == "0":
                return
            elif f_choice.lower() == "c":
                p_in = "Masukkan path file: " if CURRENT_LANG == "ID" else "Enter file path: "
                manual_path = input(f"{Fore.CYAN}{p_in}{Style.RESET_ALL}").strip(' "\'')
                if not manual_path or not os.path.exists(manual_path):
                    print(f"{Fore.RED}{'File tidak ditemukan!' if CURRENT_LANG == 'ID' else 'File not found!'}{Style.RESET_ALL}")
                    return
                selected_file = manual_path
            elif f_choice.isdigit() and 1 <= int(f_choice) <= len(available_files):
                selected_file = available_files[int(f_choice) - 1][1]
            elif f_choice == "":
                selected_file = available_files[0][1]
            else:
                print(f"{Fore.RED}{'Pilihan tidak valid.' if CURRENT_LANG == 'ID' else 'Invalid option.'}{Style.RESET_ALL}")
                return

    fname_display = os.path.basename(selected_file)
    print(f"\n{Fore.GREEN}✓ {'Target file pengujian:' if CURRENT_LANG == 'ID' else 'Target file for probe:'} {Fore.WHITE}{fname_display}{Style.RESET_ALL}")

    try:
        t_prompt = f"Batas timeout per proxy dalam detik [default: {timeout}s]: " if CURRENT_LANG == "ID" else f"Timeout per proxy in seconds [default: {timeout}s]: "
        t_in = input(f"{Fore.LIGHTBLACK_EX}{t_prompt}{Style.RESET_ALL}").strip()
        if t_in:
            timeout = float(t_in)
    except ValueError:
        pass

    start_msg = f"🚀 MEMULAI HEALTH PROBE (Timeout: {timeout}s)..." if CURRENT_LANG == "ID" else f"🚀 STARTING HEALTH PROBE (Timeout: {timeout}s)..."
    print(f"\n{Fore.CYAN}{start_msg}{Style.RESET_ALL}\n")

    def on_probe_progress(curr: int, total: int, res: dict):
        p = res["proxy"]
        disp = p["display"]
        proto = p["protocol"].upper()
        loc = res.get("location_str") or f"[{res.get('country_code', '??')}] {res.get('country', 'Unknown')}"
        if res["alive"]:
            lat = res["latency_ms"]
            color = Fore.GREEN if lat < 600 else (Fore.YELLOW if lat < 1500 else Fore.MAGENTA)
            print(f"  [{curr:>2}/{total}] {Fore.GREEN}✓ ALIVE{Style.RESET_ALL}  {Fore.WHITE}[{proto:<5}]{Style.RESET_ALL} {disp:<30} | {color}{lat:>4}ms{Style.RESET_ALL} | {Fore.CYAN}{loc}{Style.RESET_ALL}")
        else:
            err = res.get("error", "Failed")
            print(f"  [{curr:>2}/{total}] {Fore.RED}✗ DEAD {Style.RESET_ALL}  {Fore.WHITE}[{proto:<5}]{Style.RESET_ALL} {disp:<30} | {Fore.RED}{err:<18}{Style.RESET_ALL} | {Fore.LIGHTBLACK_EX}{loc}{Style.RESET_ALL}")

    results = check_file_health(
        file_path=selected_file,
        timeout=timeout,
        max_workers=35,
        on_progress=on_probe_progress
    )

    total = results["total"]
    alive = results["alive"]
    dead = results["dead"]
    alive_count = len(alive)
    dead_count = len(dead)
    pct = round((alive_count / total * 100), 1) if total > 0 else 0

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    sum_title = f"📊 RINGKASAN HASIL HEALTH CHECK ({fname_display}):" if CURRENT_LANG == "ID" else f"📊 HEALTH CHECK SUMMARY ({fname_display}):"
    print(f"{Fore.WHITE}{Style.BRIGHT}{sum_title}{Style.RESET_ALL}")
    print(f"  • {'Total Diuji' if CURRENT_LANG == 'ID' else 'Total Tested'}       : {Fore.WHITE}{total} node{Style.RESET_ALL}")
    print(f"  • {'Kondisi Sehat' if CURRENT_LANG == 'ID' else 'Healthy Nodes'}     : {Fore.GREEN}{Style.BRIGHT}{alive_count} aktif ({pct}%){Style.RESET_ALL}")
    print(f"  • {'Kondisi Mati/RTO' if CURRENT_LANG == 'ID' else 'Dead / Timeout'}  : {Fore.RED}{dead_count} mati ({round(100 - pct, 1)}%){Style.RESET_ALL}")
    print(f"  • {'Rata-rata Latency' if CURRENT_LANG == 'ID' else 'Average Latency'} : {Fore.YELLOW}{results['avg_latency_ms']} ms{Style.RESET_ALL}")
    dist = results.get("country_distribution", {})
    if dist:
        dist_str = ", ".join(f"{c} ({cnt})" for c, cnt in list(dist.items())[:5])
        print(f"  • {'Sebaran Lokasi' if CURRENT_LANG == 'ID' else 'Locations'}        : {Fore.WHITE}{dist_str}{Style.RESET_ALL}")
    print(f"  • {'Durasi Pengujian' if CURRENT_LANG == 'ID' else 'Duration'}        : {Fore.LIGHTBLACK_EX}{results['duration_sec']}s{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")

    if alive_count == 0:
        err_zero = "⚠️ Seluruh proxy di file ini tidak merespons (mati)." if CURRENT_LANG == "ID" else "⚠️ All proxies in this file are unreachable (dead)."
        print(f"{Fore.RED}{err_zero}{Style.RESET_ALL}\n")
        return

    print(f"\n{Fore.WHITE}{Style.BRIGHT}{'PILIH AKSI TINDAK LANJUT:' if CURRENT_LANG == 'ID' else 'CHOOSE NEXT ACTION:'}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 💾 {'Simpan File Bersih (Hanya Simpan' if CURRENT_LANG == 'ID' else 'Save Clean File (Save only'} {alive_count} {'IP Hidup)' if CURRENT_LANG == 'ID' else 'Alive IPs)'}")
    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 🚀 {'Nyalakan Local Gateway 8888 Langsung dengan' if CURRENT_LANG == 'ID' else 'Launch Gateway 8888 with'} {alive_count} {'IP Ini' if CURRENT_LANG == 'ID' else 'Alive IPs'}")
    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 🔄 {'Sync IP Hidup ke Database BansosRouter (9Router)' if CURRENT_LANG == 'ID' else 'Sync Alive IPs to BansosRouter DB'}")
    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 {'Kembali ke Menu Utama' if CURRENT_LANG == 'ID' else 'Return to Main Menu'}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")

    p_act = "Pilih aksi [1-3, 0=Kembali]: " if CURRENT_LANG == "ID" else "Select action [1-3, 0=Back]: "
    act = input(f"{Fore.YELLOW}{p_act}{Style.RESET_ALL}").strip()
    if act == "1":
        ov_prompt = f"Timpa file asli '{fname_display}'? [Y = Timpa / n = Simpan sebagai file baru _healthy]: " if CURRENT_LANG == "ID" else f"Overwrite original '{fname_display}'? [Y = Overwrite / n = New _healthy file]: "
        ov = input(f"{Fore.YELLOW}{ov_prompt}{Style.RESET_ALL}").strip().lower()
        overwrite = ov in ("", "y", "yes")
        saved_file = save_healthy_proxies(selected_file, alive, overwrite=overwrite)
        ok_msg = f"✓ File proxy sehat berhasil disimpan ke: {saved_file}" if CURRENT_LANG == "ID" else f"✓ Healthy proxies successfully saved to: {saved_file}"
        print(f"\n{Fore.GREEN}{ok_msg}{Style.RESET_ALL}\n")
    elif act == "2":
        live_for_server = [r["proxy"] for r in alive]
        gw_msg = f"✓ Menyalakan Gateway 8888 dengan {len(live_for_server)} proxy sehat... Tekan Ctrl+C untuk stop." if CURRENT_LANG == "ID" else f"✓ Launching Gateway 8888 with {len(live_for_server)} healthy proxies... Press Ctrl+C to stop."
        print(f"\n{Fore.GREEN}{gw_msg}{Style.RESET_ALL}\n")
        start_proxy_server(live_for_server, port=8888, background=False, enable_health_check=True)
    elif act == "3":
        router_db = find_9router_db()
        if router_db:
            from core.exporter import sync_to_9router_sqlite
            live_for_server = [r["proxy"] for r in alive]
            cnt = sync_to_9router_sqlite(live_for_server, router_db)
            print(f"\n{Fore.GREEN}✓ Berhasil menyinkronkan {cnt} proxy hidup ke {router_db}!{Style.RESET_ALL}\n")
        else:
            print(f"\n{Fore.RED}❌ Database 9Router (data.sqlite) tidak ditemukan.{Style.RESET_ALL}\n")



def show_settings_menu():
    """Pusat Pengaturan Cepat [K] - Interactive paste & persist config."""
    global CURRENT_LANG
    while True:
        cfg = load_settings()
        cs_key = cfg.get("capsolver_api_key", "").strip()
        custom_dom = cfg.get("cf_domains", "").strip() or cfg.get("custom_email_domain", "").strip()
        cf_url = cfg.get("cf_worker_url", "").strip()
        cf_sec = cfg.get("cf_worker_secret", "").strip()
        custom_db = cfg.get("9router_db_path", "").strip()
        
        from core.webshare_hunter import check_capsolver_balance
        cs_info = check_capsolver_balance()
        
        if cs_info.get("can_headless"):
            cs_status = f"{Fore.GREEN}Aktif (Saldo: ${cs_info['balance']:.3f}){Style.RESET_ALL}"
        elif cs_info.get("has_key"):
            cs_status = f"{Fore.YELLOW}Saldo Habis (${cs_info['balance']:.3f}){Style.RESET_ALL}"
        else:
            cs_status = f"{Fore.CYAN}Belum Diisi (Mode AI Audio Gratisan Aktif){Style.RESET_ALL}"

        from core.cf_mail import CloudflareMailClient
        cf_cli = CloudflareMailClient(domains=custom_dom, worker_url=cf_url, worker_secret=cf_sec)
        if cf_cli.is_configured():
            cf_status = f"{Fore.GREEN}Aktif ✓ Auto Verifikasi Webshare ({custom_dom}){Style.RESET_ALL}"
        elif custom_dom:
            cf_status = f"{Fore.YELLOW}Domain: @{custom_dom} (Worker URL Belum Diisi){Style.RESET_ALL}"
        else:
            cf_status = f"{Fore.CYAN}Otomatis / Fallback Pool (0-Modal Tanpa Verifikasi){Style.RESET_ALL}"

        db_detected = find_9router_db()
        db_status = f"{Fore.GREEN}{custom_db or db_detected}{Style.RESET_ALL}" if (custom_db or db_detected) else f"{Fore.LIGHTBLACK_EX}Tidak Terdeteksi (Mode Standalone){Style.RESET_ALL}"

        print(BANNER)
        print(f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}⚙️  PUSAT PENGATURAN CEPAT (INTERAKTIF — PASTE & GO)
  {Fore.LIGHTBLACK_EX}Tanpa perlu repot buka file JSON manual — tinggal paste di terminal!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} 🔑 Setup API Key CapSolver
      {Fore.LIGHTBLACK_EX}Status : {cs_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Biar Webshare Hunter bisa jalan 100% di background (Headless).
               {Fore.YELLOW}*CATATAN: Tidak wajib! Versi gratisan audio bawaan tetap aktif tanpa saldo.{Fore.LIGHTBLACK_EX}

  {Fore.GREEN}[2]{Fore.WHITE} 📧 Setup Cloudflare Email Worker & Domain (Auto Verifikasi Webshare)
      {Fore.LIGHTBLACK_EX}Status : {cf_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Verifikasi otomatis email Webshare via Cloudflare Email Routing + Worker
               (sama persis seperti arsitektur github-farm). Bebas banned & akun lebih awet!

  {Fore.GREEN}[3]{Fore.WHITE} 🔌 Setup Lokasi Database 9Router
      {Fore.LIGHTBLACK_EX}Status : {db_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Tentukan path file data.sqlite jika tidak otomatis terdeteksi.

  {Fore.GREEN}[4]{Fore.WHITE} 🧹 Reset Pengaturan ke Default Pabrik (Bersihkan Config)
  {Fore.RED}[0]{Fore.WHITE} 🔙 Kembali ke Menu Utama

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}""")

        choice = input(f"{Fore.YELLOW}Pilih opsi pengaturan [1-4, 0=Kembali]: {Style.RESET_ALL}").strip()
        if choice in ("0", "b", "back", "q"):
            break
        elif choice == "1":
            print(f"\n{Fore.CYAN}🔑 PENGATURAN API KEY CAPSOLVER{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Tekan Enter tanpa ketik apa pun jika ingin menghapus key (kembali ke gratisan).{Style.RESET_ALL}")
            new_key = input(f"{Fore.YELLOW}Paste / Masukkan API Key CapSolver Anda: {Style.RESET_ALL}").strip()
            cfg["capsolver_api_key"] = new_key
            save_settings(cfg)
            if new_key:
                from core.webshare_hunter import check_capsolver_balance
                check_res = check_capsolver_balance(new_key)
                if check_res.get("can_headless"):
                    print(f"\n{Fore.GREEN}✅ API Key berhasil disimpan & diverifikasi! Saldo: ${check_res['balance']:.3f}. Mode Headless siap digunakan!{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.YELLOW}⚠️ API Key disimpan, tapi saldo kosong atau tidak valid (${check_res.get('balance', 0):.3f}). Audio solver gratisan tetap siap.{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.GREEN}✅ API Key dikosongkan. PetaniProxy kembali ke mode AI Audio Solver 100% gratisan bawaan.{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "2":
            print(f"\n{Fore.CYAN}📧 PENGATURAN CLOUDFLARE EMAIL ROUTING & WORKER{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Pola verifikasi otomatis mengadopsi repositori github-farm.{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Tekan Enter tanpa isi jika ingin mempertahankan nilai saat ini / mengosongkan.{Style.RESET_ALL}\n")
            
            curr_dom = cfg.get("cf_domains") or cfg.get("custom_email_domain") or ""
            curr_url = cfg.get("cf_worker_url") or ""
            curr_sec = cfg.get("cf_worker_secret") or ""

            new_dom = input(f"{Fore.YELLOW}1. Domain Email (contoh: domainku.com) [Saat ini: {curr_dom or 'Kosong'}]: {Style.RESET_ALL}").strip().lstrip("@")
            if new_dom:
                cfg["cf_domains"] = new_dom
                cfg["custom_email_domain"] = new_dom

            new_url = input(f"{Fore.YELLOW}2. URL Cloudflare Worker /inbox [Saat ini: {curr_url or 'Kosong'}]: {Style.RESET_ALL}").strip()
            if new_url:
                cfg["cf_worker_url"] = new_url

            new_sec = input(f"{Fore.YELLOW}3. Cloudflare Worker Secret (X-Worker-Secret) [Saat ini: {'***' if curr_sec else 'Kosong'}]: {Style.RESET_ALL}").strip()
            if new_sec:
                cfg["cf_worker_secret"] = new_sec

            save_settings(cfg)

            from core.cf_mail import CloudflareMailClient
            test_cli = CloudflareMailClient.from_config()
            if test_cli.is_configured():
                print(f"\n{Fore.GREEN}✅ Cloudflare Email Worker BERHASIL DIKONFIGURASI!{Style.RESET_ALL}")
                print(f"   • Domain: {test_cli.domains}")
                print(f"   • Worker URL: {test_cli.worker_url}")
                print(f"   • Auto-Verifikasi Webshare: {Fore.GREEN}AKTIF ✓{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}ℹ️ Pengaturan disimpan. Cloudflare Worker membutuhkan Domain & URL Worker untuk aktif.{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "3":
            print(f"\n{Fore.CYAN}🔌 PENGATURAN DATABASE 9ROUTER{Style.RESET_ALL}")
            new_path = input(f"{Fore.YELLOW}Paste path lengkap ke data.sqlite 9Router: {Style.RESET_ALL}").strip()
            if new_path and os.path.exists(new_path):
                cfg["9router_db_path"] = new_path
                save_settings(cfg)
                print(f"\n{Fore.GREEN}✅ Database 9Router berhasil dihubungkan ke: {new_path}{Style.RESET_ALL}")
            elif not new_path:
                cfg.pop("9router_db_path", None)
                save_settings(cfg)
                print(f"\n{Fore.GREEN}✅ Menggunakan auto-detection bawaan.{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ File tidak ditemukan di path tersebut: {new_path}{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "4":
            if os.path.exists(get_settings_path()):
                os.remove(get_settings_path())
            print(f"\n{Fore.GREEN}✅ Pengaturan berhasil di-reset ke default pabrik!{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")

def show_manual_menu():
    """Sub-menu [M] Bengkel Oprek Manual untuk power user."""

    global CURRENT_LANG
    while True:
        print(BANNER)
        if CURRENT_LANG == "ID":
            m_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🛠️  BENGKEL OPREK MANUAL (PETANIPROXY)
  {Fore.LIGHTBLACK_EX}Buat yang paham jeroan teknis — bebas atur protokol, filter & hook database
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} ⚡ Quick Harvest Standar   {Fore.LIGHTBLACK_EX}Ambil 15 proxy tercepat dari semua tipe
  {Fore.GREEN}[2]{Fore.WHITE} 🔒 Khusus SOCKS5          {Fore.LIGHTBLACK_EX}Protokol tercepat & stabil (HTTP diskip)
  {Fore.GREEN}[3]{Fore.WHITE} 🌐 Khusus HTTP / HTTPS    {Fore.LIGHTBLACK_EX}Proxy klasik untuk web traffic biasa
  {Fore.GREEN}[4]{Fore.WHITE} 🌍 Filter Negara Tertentu {Fore.LIGHTBLACK_EX}Bebas ketik kode ISO (ID, SG, US, JP, dll)
  {Fore.GREEN}[5]{Fore.WHITE} 🛡️ Khusus Elite Proxies   {Fore.LIGHTBLACK_EX}High Anonymity Only — anti bocor header
  {Fore.GREEN}[6]{Fore.WHITE} 🎯 Tembak Target URL      {Fore.LIGHTBLACK_EX}Uji tembus domain incaran (contoh: x.ai)
  {Fore.GREEN}[7]{Fore.WHITE} 🏠 Nyalakan Gateway 8888  {Fore.LIGHTBLACK_EX}Host forward proxy & REST API lokal
  {Fore.GREEN}[8]{Fore.WHITE} 🔌 Setor ke BansosRouter  {Fore.LIGHTBLACK_EX}Inject proxy langsung ke database SQLite
  {Fore.GREEN}[9]{Fore.WHITE} 📦 Perbaiki Dependensi   {Fore.LIGHTBLACK_EX}Self-healing pip install requirements.txt
  {Fore.RED}[0]{Fore.WHITE} 🔙 Balik ke Menu Racikan  {Fore.LIGHTBLACK_EX}Kembali ke beranda utama

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Pilih opsi Bengkel [1-9, 0=Kembali]: {Style.RESET_ALL}"
        else:
            m_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🛠️  MANUAL TUNING WORKSHOP (PETANIPROXY)
  {Fore.LIGHTBLACK_EX}For power users who need custom protocols, filters & database hooks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} ⚡ Standard Quick Sweep   {Fore.LIGHTBLACK_EX}Grab 15 fastest random live proxies
  {Fore.GREEN}[2]{Fore.WHITE} 🔒 Pure SOCKS5 Only       {Fore.LIGHTBLACK_EX}Ultra-fast SOCKS5 sockets only
  {Fore.GREEN}[3]{Fore.WHITE} 🌐 Classic HTTP / HTTPS   {Fore.LIGHTBLACK_EX}Standard HTTP browsing nodes
  {Fore.GREEN}[4]{Fore.WHITE} 🌍 Custom Country Filter  {Fore.LIGHTBLACK_EX}Filter by country ISO code (ID, SG, US...)
  {Fore.GREEN}[5]{Fore.WHITE} 🛡️ Elite Proxies Only     {Fore.LIGHTBLACK_EX}Strict ghost mode — zero header leaks
  {Fore.GREEN}[6]{Fore.WHITE} 🎯 Target-Specific Snipe  {Fore.LIGHTBLACK_EX}Probe directly against custom website/API
  {Fore.GREEN}[7]{Fore.WHITE} 🏠 Launch Local Gateway   {Fore.LIGHTBLACK_EX}Start rotating forward proxy on port 8888
  {Fore.GREEN}[8]{Fore.WHITE} 🔌 Sync BansosRouter DB   {Fore.LIGHTBLACK_EX}Feed live proxies into SQLite database pool
  {Fore.GREEN}[9]{Fore.WHITE} 📦 Repair Dependencies    {Fore.LIGHTBLACK_EX}Self-healing pip install requirements.txt
  {Fore.RED}[0]{Fore.WHITE} 🔙 Back to Presets Menu   {Fore.LIGHTBLACK_EX}Return to primary launcher

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Select workshop option [1-9, 0=Back]: {Style.RESET_ALL}"

        print(m_box)
        try:
            choice = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice in ("0", "b", "back", "q"):
            break
        elif choice == "1":
            q_str = f"{Fore.CYAN}{'Target proxy hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "2":
            q_str = f"{Fore.CYAN}{'Target SOCKS5 hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target SOCKS5 count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "3":
            q_str = f"{Fore.CYAN}{'Target HTTP hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target HTTP count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "4":
            cc_prompt = f"{Fore.CYAN}{'Kode negara ISO 2 huruf (contoh: ID, SG, US) [default: ID]: ' if CURRENT_LANG == 'ID' else 'Enter 2-letter Country Code [default: ID]: '}{Style.RESET_ALL}"
            cc = input(cc_prompt).strip() or "ID"
            t_prompt = f"{Fore.CYAN}{'Target proxy hidup [default: 5]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 5]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 5
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(350, target_val * 35), target_alive=target_val, country=cc, timeout=3.5)
        elif choice == "5":
            q_str = f"{Fore.CYAN}{'Target Elite proxy [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target Elite count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(350, target_val * 20), target_alive=target_val, anonymity="elite", timeout=3.0)
        elif choice == "6":
            u_prompt = f"{Fore.CYAN}{'URL target uji [default: https://google.com]: ' if CURRENT_LANG == 'ID' else 'Target URL [default: https://google.com]: '}{Style.RESET_ALL}"
            t_url = input(u_prompt).strip() or "https://google.com"
            t_prompt = f"{Fore.CYAN}{'Target proxy lolos [default: 10]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 10]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 10
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(400, target_val * 25), target_alive=target_val, target_url=t_url, timeout=3.5)
        elif choice == "7":
            port_prompt = f"{Fore.CYAN}{'Port gateway lokal [default: 8888]: ' if CURRENT_LANG == 'ID' else 'Local gateway port [default: 8888]: '}{Style.RESET_ALL}"
            port_input = input(port_prompt).strip()
            port_val = int(port_input) if port_input.isdigit() else 8888
            t_prompt = f"{Fore.CYAN}{'Jumlah proxy hidup di pool [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target alive pool size [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(300, target_val * 15), target_alive=target_val, timeout=3.0, serve_port=port_val)
        elif choice == "8":
            detected_db = find_9router_db()
            hint = f" [Terdeteksi: {detected_db}]" if detected_db else ""
            custom_path = input(f"{Fore.CYAN}{'Path ke data.sqlite BansosRouter' + hint + ' [Enter untuk default]: ' if CURRENT_LANG == 'ID' else 'Enter BansosRouter data.sqlite path' + hint + ' [Enter for default]: '}{Style.RESET_ALL}").strip()
            db_target = custom_path if custom_path else detected_db
            if db_target and os.path.exists(db_target):
                run_harvester(protocols=["http", "socks4", "socks5"], max_check=250, target_alive=15, sync_9router=db_target)
            else:
                print(f"{Fore.RED}{'Database tidak ditemukan. Pastikan path benar.' if CURRENT_LANG == 'ID' else 'Database not found. Please verify path.'}{Style.RESET_ALL}")
        elif choice == "9":
            install_dependencies()
        else:
            print(f"{Fore.RED}{'Pilihan tidak valid.' if CURRENT_LANG == 'ID' else 'Invalid option.'}{Style.RESET_ALL}")

        try:
            pause_msg = "[Tekan Enter untuk kembali ke menu bengkel...]" if CURRENT_LANG == "ID" else "[Press Enter to return to workshop...]"
            input(f"\n{Fore.LIGHTBLACK_EX}{pause_msg}{Style.RESET_ALL}")
        except (KeyboardInterrupt, EOFError):
            break

def get_features_readiness(lang: str = "ID") -> dict:
    """Check readiness status of features, CapSolver balance, and compute system readiness progress bar."""
    import importlib.util
    import socket
    from core.webshare_hunter import check_capsolver_balance

    status = {}
    score = 0

    # 1. Dependensi Inti
    pkgs = ["httpx", "requests", "colorama", "DrissionPage", "speech_recognition", "pydub"]
    missing = [p for p in pkgs if importlib.util.find_spec(p) is None]
    if not missing:
        status["deps_badge"] = f"{Fore.GREEN}[OK ✓]{Style.RESET_ALL}"
        status["deps_desc"] = "DrissionPage, httpx, pydub, speech_recognition"
        score += 25
    else:
        status["deps_badge"] = f"{Fore.YELLOW}[KURANG: {len(missing)}]{Style.RESET_ALL}"
        status["deps_desc"] = f"Missing: {', '.join(missing)}"

    # 2. Webshare Hunter Audio Solver
    dp_found = importlib.util.find_spec("DrissionPage") is not None
    sr_found = importlib.util.find_spec("speech_recognition") is not None
    if dp_found and sr_found:
        status["webshare"] = f"{Fore.GREEN}[SIAP TEMPUR ✓]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[READY ✓]{Style.RESET_ALL}"
        status["webshare_desc"] = "Free AI Audio Solver Aktif (Mode Jendela Tampak)" if lang == "ID" else "Free AI Audio Solver Active (Visible Window)"
        score += 25
    else:
        status["webshare"] = f"{Fore.YELLOW}[PERLU INSTALL]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.YELLOW}[SETUP NEEDED]{Style.RESET_ALL}"
        status["webshare_desc"] = "Paket DrissionPage / speech_rec belum lengkap" if lang == "ID" else "Packages missing"

    # 3. CapSolver Engine (Headless capability)
    cs_info = check_capsolver_balance()
    status["capsolver_info"] = cs_info
    if cs_info.get("can_headless"):
        status["capsolver_badge"] = f"{Fore.GREEN}[SIAP ✓]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[READY ✓]{Style.RESET_ALL}"
        status["capsolver_desc"] = f"Saldo: ${cs_info['balance']:.3f} (Headless Didukung Penuh)" if lang == "ID" else f"Balance: ${cs_info['balance']:.3f} (Headless Ready)"
        score += 20
    elif cs_info.get("has_key"):
        status["capsolver_badge"] = f"{Fore.YELLOW}[SALDO HABIS]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.YELLOW}[EMPTY BALANCE]{Style.RESET_ALL}"
        status["capsolver_desc"] = f"Saldo ${cs_info['balance']:.3f} (Headless Off, Gunakan Free Audio)" if lang == "ID" else f"Balance ${cs_info['balance']:.3f} (Use Free Audio)"
        score += 10
    else:
        status["capsolver_badge"] = f"{Fore.CYAN}[OPSIONAL / OFF]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.CYAN}[OPTIONAL / OFF]{Style.RESET_ALL}"
        status["capsolver_desc"] = "Mode AI Audio Gratisan 100% Aktif & Siap Tempur ✓" if lang == "ID" else "100% Free AI Audio Solver Active & Ready ✓"
        score += 20


    # 3.5. Cloudflare Email Worker
    from core.cf_mail import CloudflareMailClient
    cf_cli = CloudflareMailClient.from_config()
    if cf_cli.is_configured():
        status["cf_mail"] = f"{Fore.GREEN}[AKTIF ✓]{Style.RESET_ALL}"
        status["cf_desc"] = f"Auto Verifikasi ({cf_cli.domains[0]})" if lang == "ID" else f"Auto Verify ({cf_cli.domains[0]})"
        score += 15
    elif cf_cli.domains:
        status["cf_mail"] = f"{Fore.YELLOW}[DOMAIN Sedia]{Style.RESET_ALL}"
        status["cf_desc"] = f"Domain @{cf_cli.domains[0]} (Worker Off)" if lang == "ID" else f"Domain @{cf_cli.domains[0]} (No Worker)"
        score += 5
    else:
        status["cf_mail"] = f"{Fore.LIGHTBLACK_EX}[0-MODAL / OFF]{Style.RESET_ALL}"
        status["cf_desc"] = "Tanpa Verifikasi / Default Pool" if lang == "ID" else "No Verification / Default Pool"
        score += 5

    # 4. 9Router DB sync
    db_path = find_9router_db()
    if db_path:
        status["sync"] = f"{Fore.GREEN}[9ROUTER LINKED]{Style.RESET_ALL}"
        status["db_desc"] = f"Terhubung ({os.path.basename(db_path)})" if lang == "ID" else f"Connected ({os.path.basename(db_path)})"
        score += 15
    else:
        status["sync"] = f"{Fore.CYAN}[STANDALONE]{Style.RESET_ALL}"
        status["db_desc"] = "Mode Mandiri (Database 9Router tidak terdeteksi)" if lang == "ID" else "Standalone mode"
        score += 10

    # 5. Gateway 8888 live port status
    gw_active = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            gw_active = (s.connect_ex(('127.0.0.1', 8888)) == 0)
    except Exception:
        gw_active = False

    if gw_active:
        status["gateway"] = f"{Fore.GREEN}[PORT 8888 AKTIF 🟢]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[PORT 8888 ONLINE 🟢]{Style.RESET_ALL}"
    else:
        status["gateway"] = f"{Fore.CYAN}[CEK LIVE]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.CYAN}[LIVE TEST]{Style.RESET_ALL}"


    # 6. Storage count
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "output", "proxies.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                count = d.get("total_alive", 0)
                status["storage"] = f"{Fore.GREEN}[{count} PROXY TERSEDIA]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[{count} PROXIES READY]{Style.RESET_ALL}"
                status["storage_desc"] = f"{count} Proxy Aktif Tersimpan di Disk" if lang == "ID" else f"{count} Active Proxies Stored"
                score += 15
        except Exception:
            status["storage"] = f"{Fore.GREEN}[READY]{Style.RESET_ALL}"
            status["storage_desc"] = "File penyimpanan siap"
            score += 10
    else:
        status["storage"] = f"{Fore.LIGHTBLACK_EX}[KOSONG]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.LIGHTBLACK_EX}[EMPTY]{Style.RESET_ALL}"
        status["storage_desc"] = "Belum ada riwayat panen tersimpan" if lang == "ID" else "No saved proxies yet"
        score += 5

    pct = min(100, score)
    bar_len = 10
    filled = int(bar_len * pct / 100)
    bar_str = "█" * filled + "░" * (bar_len - filled)
    status["percent"] = pct
    status["bar"] = bar_str

    if pct >= 85:
        bar_color = Fore.GREEN
        state_txt = "Amunisi Siap Tempur!" if lang == "ID" else "Battle-Ready!"
    elif pct >= 60:
        bar_color = Fore.YELLOW
        state_txt = "Sebagian Siap" if lang == "ID" else "Partially Ready"
    else:
        bar_color = Fore.RED
        state_txt = "Perlu Setup" if lang == "ID" else "Setup Needed"

    status["progress_line"] = f"{bar_color}[{bar_str}] {pct}%{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}({state_txt}){Style.RESET_ALL}"
    return status

def show_interactive_menu():
    global CURRENT_LANG
    check_initial_dependencies()
    update_checked = False
    cached_update_info = None

    while True:
        # Check update once per app session (cached)
        if not update_checked:
            update_checked = True
            try:
                cached_update_info = check_for_updates(timeout=2.0)
            except Exception:
                cached_update_info = None

        print(BANNER)

        # Show update banner if new version is available!
        if cached_update_info and cached_update_info.get("has_update"):
            print(render_update_banner(cached_update_info, lang=CURRENT_LANG))
            print()

        local_info = get_local_version_info()
        local_ver = local_info.get("version", "1.0.0")
        st = get_features_readiness(lang=CURRENT_LANG)
        ready_label = f"{Fore.GREEN}[SIAP PAKAI]{Style.RESET_ALL}" if CURRENT_LANG == "ID" else f"{Fore.GREEN}[READY]{Style.RESET_ALL}"

        if CURRENT_LANG == "ID":
            u_line = f"  {Fore.YELLOW}{Style.BRIGHT}[U]{Fore.WHITE}{Style.BRIGHT} 🚀 Update Tersedia!       {Fore.GREEN}v{cached_update_info.get('remote_version')} [PILIH UNTUK UPDATE]\n" if (cached_update_info and cached_update_info.get("has_update")) else f"  {Fore.GREEN}[U]{Fore.WHITE} 🔄 Cek & Update Versi     {Fore.GREEN}[v{local_ver} TERBARU]{Style.RESET_ALL}\n"
            menu_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🌾 PETANIPROXY v{local_ver} (PUSAT AMUNISI PROXY)
  {Fore.LIGHTBLACK_EX}Amunisi Proxy Anti-Tumbang, Siap Diajak Tempur 24/7 Gaspol!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.WHITE}{Style.BRIGHT}📊 KESIAPAN AMUNISI : {st['progress_line']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Dependensi Inti : {st['deps_badge']} {Fore.LIGHTBLACK_EX}{st['deps_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Webshare Hunter : {st['webshare']} {Fore.LIGHTBLACK_EX}{st['webshare_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}CapSolver Engine: {st['capsolver_badge']} {Fore.LIGHTBLACK_EX}{st['capsolver_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Cloudflare Mail : {st.get('cf_mail', '')} {Fore.LIGHTBLACK_EX}{st.get('cf_desc', '')}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}BansosRouter DB : {st['sync']} {Fore.LIGHTBLACK_EX}{st['db_desc']}
  {Fore.LIGHTBLACK_EX}└─ {Fore.WHITE}Stok di Gudang  : {st['storage']} {Fore.LIGHTBLACK_EX}{st['storage_desc']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.YELLOW}{Style.BRIGHT}⭐ [MVP] AMUNISI SULTAN: IP RESIDENTIAL & CLOUDFLARE WARP
  {Fore.YELLOW}{Style.BRIGHT}[W]{Fore.WHITE}{Style.BRIGHT} 🏢 Webshare Hunter Gacor   {st['webshare']} {Fore.YELLOW}(RESIDENTIAL MVP ⭐⭐⭐)
     {Fore.GREEN}└─ Auto-Solve Captcha Suara • IP Rumah Asli • 10-30 Proxy/Akun
  {Fore.MAGENTA}{Style.BRIGHT}[D]{Fore.WHITE}{Style.BRIGHT} 🦊 Decodo Residential Hunt {Fore.GREEN}[CLOAKBROWSER]{Style.RESET_ALL} {Fore.YELLOW}(AUTO CF MAIL & CC TRIAL)
     {Fore.GREEN}└─ CloakBrowser Headless • Auto-Register & Verify • Klaim Trial Resi HTTP
  {Fore.CYAN}{Style.BRIGHT}[C]{Fore.WHITE}{Style.BRIGHT} 🚀 Cloudflare WARP Local    {Fore.GREEN}[ULTRA FAST]{Style.RESET_ALL} {Fore.CYAN}(BEBAS CAPTCHA, UNLIMITED)
     {Fore.GREEN}└─ Akun WireGuard Resmi • Mixed SOCKS5/HTTP • Latency <100ms
  {Fore.LIGHTCYAN_EX}{Style.BRIGHT}[F]{Fore.WHITE}{Style.BRIGHT} ⚡ aiohttp Fast Harvester   {Fore.GREEN}[KENCANG]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Filter <350ms dalam 1 detik)
     {Fore.GREEN}└─ Sedot ribuan kandidat secara asinkron • Auto-sync 9Router

  {Fore.MAGENTA}RACIKAN PROXY & GATEWAY LOKAL (PORT 8888)
  {Fore.GREEN}[G]{Fore.WHITE} 🚜 Mode Petani AFK 24/7   {ready_label} {Fore.LIGHTBLACK_EX}Tinggal tidur, auto-prune IP busuk & refill non-stop
  {Fore.GREEN}[1]{Fore.WHITE} 🐔 Racikan Ternak Akun    {st['sync']} {Fore.LIGHTBLACK_EX}Anti-limit buat Grok/Qoder (Sync 9Router + Port 8888)
  {Fore.GREEN}[2]{Fore.WHITE} 🕷️ Racikan Scraper Barbar {ready_label} {Fore.LIGHTBLACK_EX}Pool 30+ IP, ganti IP tiap request
  {Fore.GREEN}[3]{Fore.WHITE} ⚡ Racikan Ngacir Anti-Lag {ready_label} {Fore.LIGHTBLACK_EX}Ping <350ms, Node SG/ID/US

  {Fore.MAGENTA}BUNGKUS HASIL PANEN & TES IDENTITAS
  {Fore.CYAN}[E]{Fore.WHITE} 📥 Bungkus File Mentah    {Fore.GREEN}[SIAP EKSPOR]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Sedot TXT, JSON, CSV buat bot lu
  {Fore.CYAN}[T]{Fore.WHITE} 🧪 Uji Kesaktian Topeng   {st['gateway']} {Fore.LIGHTBLACK_EX}Tes live: Adu IP asli lu vs IP Gateway (Anti-Bocor)
  {Fore.CYAN}[H]{Fore.WHITE} 🩺 Cek Kesehatan Hasil    {Fore.GREEN}[HEALTH CHECK]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Uji ulang stok proxy di output (Webshare/TXT/JSON)

  {Fore.MAGENTA}PEMBARUAN & PUSAT PENGATURAN
  {Fore.YELLOW}{Style.BRIGHT}[K]{Fore.WHITE}{Style.BRIGHT} ⚙️ Pengaturan Cepat       {Fore.GREEN}[PASTE & GO]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Setup API CapSolver & Domain Email tanpa ngoding
{u_line}  {Fore.YELLOW}[M]{Fore.WHITE} 🛠️ Oprek Suka-Suka        {ready_label} {Fore.LIGHTBLACK_EX}Racik protokol sendiri, pilih negara
  {Fore.YELLOW}[S]{Fore.WHITE} 📂 Gudang Amunisi         {st['storage']} {Fore.LIGHTBLACK_EX}Stok proxy segar tersimpan di disk
  {Fore.BLUE}[L]{Fore.WHITE} 🌐 Ganti Bahasa (EN/ID)   {Fore.LIGHTBLACK_EX}Currently: Bahasa Indonesia
  {Fore.RED}[0]{Fore.WHITE} 💀 Cabut Dulu (Rebahan)   {Fore.LIGHTBLACK_EX}Tutup laptop, ngopi dulu atau sentuh rumput

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.LIGHTBLACK_EX}Maintainer: {Fore.YELLOW}@itzluthfi{Fore.LIGHTBLACK_EX}          Repository: {Fore.WHITE}github.com/itzluthfi
{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Pilih Opsi [W, D, C, F, G, 1-3, E, T, H, K, U, M, S, L, 0] (Saran: W atau D untuk residential): {Style.RESET_ALL}"
        else:
            u_line = f"  {Fore.YELLOW}{Style.BRIGHT}[U]{Fore.WHITE}{Style.BRIGHT} 🚀 New Update Available!  {Fore.GREEN}v{cached_update_info.get('remote_version')} [SELECT TO UPDATE]\n" if (cached_update_info and cached_update_info.get("has_update")) else f"  {Fore.GREEN}[U]{Fore.WHITE} 🔄 Check & Update Version {Fore.GREEN}[v{local_ver} LATEST]{Style.RESET_ALL}\n"
            menu_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🌾 PETANIPROXY v{local_ver} (ROTATING PROXY ARSENAL)
  {Fore.LIGHTBLACK_EX}Battle-Tested Rotating Proxy Ammo — Zero BS, 100% Free!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.WHITE}{Style.BRIGHT}📊 SYSTEM READINESS : {st['progress_line']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Core Dependencies: {st['deps_badge']} {Fore.LIGHTBLACK_EX}{st['deps_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Webshare Hunter  : {st['webshare']} {Fore.LIGHTBLACK_EX}{st['webshare_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}CapSolver Engine : {st['capsolver_badge']} {Fore.LIGHTBLACK_EX}{st['capsolver_desc']}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}Cloudflare Mail  : {st.get('cf_mail', '')} {Fore.LIGHTBLACK_EX}{st.get('cf_desc', '')}
  {Fore.LIGHTBLACK_EX}├─ {Fore.WHITE}BansosRouter DB  : {st['sync']} {Fore.LIGHTBLACK_EX}{st['db_desc']}
  {Fore.LIGHTBLACK_EX}└─ {Fore.WHITE}Ammo in Storage  : {st['storage']} {Fore.LIGHTBLACK_EX}{st['storage_desc']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.YELLOW}{Style.BRIGHT}⭐ [MVP] S-TIER ARSENAL: RESIDENTIAL & CLOUDFLARE WARP
  {Fore.YELLOW}{Style.BRIGHT}[W]{Fore.WHITE}{Style.BRIGHT} 🏢 Webshare Hunter Elite   {st['webshare']} {Fore.YELLOW}(RESIDENTIAL MVP ⭐⭐⭐)
     {Fore.GREEN}└─ Audio Captcha Solver • Real Residential IPs • 10-30 Nodes/Acc
  {Fore.MAGENTA}{Style.BRIGHT}[D]{Fore.WHITE}{Style.BRIGHT} 🦊 Decodo Residential Hunt {Fore.GREEN}[CLOAKBROWSER]{Style.RESET_ALL} {Fore.YELLOW}(AUTO CF MAIL & CC TRIAL)
     {Fore.GREEN}└─ CloakBrowser Headless • Auto-Register & Verify • Claim Resi Trial HTTP
  {Fore.CYAN}{Style.BRIGHT}[C]{Fore.WHITE}{Style.BRIGHT} 🚀 Cloudflare WARP Local    {Fore.GREEN}[ULTRA FAST]{Style.RESET_ALL} {Fore.CYAN}(ZERO CAPTCHA, UNLIMITED)
     {Fore.GREEN}└─ Official WireGuard Profile • Mixed SOCKS5/HTTP • Latency <100ms
  {Fore.LIGHTCYAN_EX}{Style.BRIGHT}[F]{Fore.WHITE}{Style.BRIGHT} ⚡ aiohttp Fast Harvester   {Fore.GREEN}[FAST]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Sub-350ms filter in 1 second)
     {Fore.GREEN}└─ Concurrent async scraping • Auto-syncs 9Router DB

  {Fore.MAGENTA}FREE PUBLIC ROTATING GATEWAY (LOCAL PORT 8888)
  {Fore.GREEN}[G]{Fore.WHITE} 🚜 24/7 AFK Farmer Daemon {ready_label} {Fore.LIGHTBLACK_EX}Auto-prune dead nodes & refill non-stop
  {Fore.GREEN}[1]{Fore.WHITE} 🐔 Bot Breeder Rig        {st['sync']} {Fore.LIGHTBLACK_EX}Anti-ban tuned for Grok/Qoder (Sync 9Router + Port 8888)
  {Fore.GREEN}[2]{Fore.WHITE} 🕷️ Barbaric Web Scraper   {ready_label} {Fore.LIGHTBLACK_EX}30+ pool, fresh IP every request
  {Fore.GREEN}[3]{Fore.WHITE} ⚡ Ludicrous Speed Mode   {ready_label} {Fore.LIGHTBLACK_EX}Ping <350ms, Node SG/ID/US

  {Fore.MAGENTA}DUMP RAW AMMO & STEALTH TEST
  {Fore.CYAN}[E]{Fore.WHITE} 📥 Dump Raw Ammo Files    {Fore.GREEN}[READY TO DUMP]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Export TXT, JSON, CSV for bots
  {Fore.CYAN}[T]{Fore.WHITE} 🧪 Stealth Mask Check     {st['gateway']} {Fore.LIGHTBLACK_EX}Live test: Real IP vs Gateway IP (Zero Leak)
  {Fore.CYAN}[H]{Fore.WHITE} 🩺 Ammo Health Checker     {Fore.GREEN}[HEALTH CHECK]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Re-probe proxies in output/ (Webshare/TXT/JSON)
 
  {Fore.MAGENTA}UPDATES & QUICK SETTINGS
  {Fore.YELLOW}{Style.BRIGHT}[K]{Fore.WHITE}{Style.BRIGHT} ⚙️ Quick Settings Lab      {Fore.GREEN}[PASTE & GO]{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}Setup CapSolver Key & Custom Domain with zero coding
{u_line}  {Fore.YELLOW}[M]{Fore.WHITE} 🛠️ Custom Lab Workshop    {ready_label} {Fore.LIGHTBLACK_EX}Tweak protocols, filter ISO countries
  {Fore.YELLOW}[S]{Fore.WHITE} 📂 Ammo Storage Vault     {st['storage']} {Fore.LIGHTBLACK_EX}Check active proxies sitting on disk
  {Fore.BLUE}[L]{Fore.WHITE} 🌐 Switch Language (EN/ID){Fore.LIGHTBLACK_EX}Currently: English
  {Fore.RED}[0]{Fore.WHITE} 💀 Rage Quit              {Fore.LIGHTBLACK_EX}Close terminal, sip coffee & go touch grass

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.LIGHTBLACK_EX}Maintainer: {Fore.YELLOW}@itzluthfi{Fore.LIGHTBLACK_EX}          Repository: {Fore.WHITE}github.com/itzluthfi
{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Select Option [W, D, C, F, G, 1-3, E, T, H, K, U, M, S, L, 0] (Pro-tip: Press W or D for residential): {Style.RESET_ALL}"



        print(menu_box)
        try:
            choice = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
            break

        if choice.lower() == "u":
            print(f"\n{Fore.CYAN}{'Memeriksa pembaruan ke GitHub...' if CURRENT_LANG == 'ID' else 'Checking GitHub for updates...'}{Style.RESET_ALL}")
            info = check_for_updates(timeout=3.5)
            if info.get("has_update"):
                print(render_update_banner(info, lang=CURRENT_LANG))
                show_full_announcement(info, lang=CURRENT_LANG)
                c_up = input(f"\n{Fore.YELLOW}{'Lakukan update sekarang? [Y/n]: ' if CURRENT_LANG == 'ID' else 'Perform update now? [Y/n]: '}{Style.RESET_ALL}").strip().lower()
                if c_up in ("", "y", "yes"):
                    perform_update(restart=True, lang=CURRENT_LANG)
            else:
                curr_ver = info.get("current_version", "1.0.0")
                print(f"\n{Fore.GREEN}✅ {'PetaniProxy sudah dalam versi paling baru' if CURRENT_LANG == 'ID' else 'PetaniProxy is up to date'} (v{curr_ver})!{Style.RESET_ALL}")
                show_full_announcement(info, lang=CURRENT_LANG)
            
            try:
                p_msg = "[Tekan Enter untuk kembali ke menu...]" if CURRENT_LANG == "ID" else "[Press Enter to return to main menu...]"
                input(f"\n{Fore.LIGHTBLACK_EX}{p_msg}{Style.RESET_ALL}")
            except (KeyboardInterrupt, EOFError):
                break
            continue

        if choice.lower() == "l":
            CURRENT_LANG = "EN" if CURRENT_LANG == "ID" else "ID"
            new_lang_name = "Bahasa Indonesia" if CURRENT_LANG == "ID" else "English"
            print(f"\n{Fore.GREEN}🌐 Bahasa antarmuka diubah ke: {new_lang_name}{Style.RESET_ALL}")
            continue

        if choice.lower() == "m":
            show_manual_menu()
            continue

        if choice.lower() == "k":
            show_settings_menu()
            continue

        if choice.lower() == "t":
            test_live_masking(port=8888)
        elif choice.lower() == "h":
            show_health_check_menu()
            continue
        elif choice.lower() == "e":
            q_str = f"{Fore.CYAN}{'Target jumlah proxy hidup yang mau diekspor [default: 20]: ' if CURRENT_LANG == 'ID' else 'Target alive proxies to export [default: 20]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 20
            res = run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
            if res:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                out_dir = os.path.join(base_dir, "output")
                fm_name = "File Explorer" if sys.platform == "win32" else "Finder" if sys.platform == "darwin" else "File Manager"
                ed_name = "Notepad" if sys.platform == "win32" else "TextEdit" if sys.platform == "darwin" else "Text Editor"
                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}💾 FILE MENTAH SEGAR BERHASIL DIBUNGKUS!{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📂 Buka Folder Output ({fm_name})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📝 Buka File live_all.txt ({ed_name})")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-2, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_explorer(out_dir)
                    elif sub == "2":
                        open_in_text_editor(os.path.join(out_dir, "live_all.txt"))
                    else:
                        break
            continue
        elif choice == "" or choice == "1":
            print(f"\n{Fore.GREEN}{'🐔 Menjalankan Racikan Ternak Akun (Grok, Qoder & Bot AI)...' if CURRENT_LANG == 'ID' else '🐔 Launching Account Farming Preset (Grok, Qoder & AI)...'}{Style.RESET_ALL}")
            db_target = find_9router_db()
            if db_target:
                print(f"  {Fore.CYAN}✓ BansosRouter SQLite terdeteksi di: {Fore.WHITE}{db_target}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks5"], 
                max_check=350, 
                target_alive=20, 
                anonymity="elite", 
                timeout=2.5, 
                serve_port=8888, 
                sync_9router=db_target
            )
        elif choice == "2":
            print(f"\n{Fore.GREEN}{'🕷️ Menjalankan Racikan Scraper Brutal (Shopee, Tokopedia, Web Data)...' if CURRENT_LANG == 'ID' else '🕷️ Launching Mass Web Scraper Preset...'}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks4", "socks5"], 
                max_check=500, 
                target_alive=30, 
                anonymity="elite", 
                timeout=3.5, 
                serve_port=8888
            )
        elif choice == "3":
            print(f"\n{Fore.GREEN}{'⚡ Menjalankan Racikan Turbo Surfing (Ping Terendah, SG/ID/US)...' if CURRENT_LANG == 'ID' else '⚡ Launching Lightning Turbo Surfing Preset...'}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks5"], 
                max_check=350, 
                target_alive=15, 
                timeout=2.0, 
                serve_port=8888
            )
        elif choice.lower() == "w":
            try:
                from core.webshare_hunter import run_webshare_hunter
            except ImportError as e:
                print(f"\n{Fore.RED}⚠️ Dependensi Webshare Hunter belum lengkap: {e}{Style.RESET_ALL}")
                ask_inst = input(f"{Fore.YELLOW}{'👉 Pasang otomatis sekarang (1-Klik via pip)? [Y/n]: ' if CURRENT_LANG == 'ID' else '👉 Auto-install dependencies now (1-Click via pip)? [Y/n]: '}{Style.RESET_ALL}").strip().lower()
                if ask_inst in ("", "y", "yes"):
                    if install_dependencies():
                        try:
                            from core.webshare_hunter import run_webshare_hunter
                        except ImportError:
                            print(f"{Fore.RED}{'Gagal memuat Webshare Hunter setelah instalasi.' if CURRENT_LANG == 'ID' else 'Failed to load Webshare Hunter after installation.'}{Style.RESET_ALL}")
                            continue
                    else:
                        continue
                else:
                    continue

            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'⭐ MEMBUKA WEBSHARE RESIDENTIAL HUNTER (FITUR MVP)...' if CURRENT_LANG == 'ID' else '⭐ LAUNCHING WEBSHARE RESIDENTIAL HUNTER (MVP FEATURE)...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: 1 Akun Webshare menghasilkan 10 IP Residential asli dengan username:password pribadi.' if CURRENT_LANG == 'ID' else '💡 Info: 1 Webshare account generates 10 genuine Residential IPs with private credentials.'}{Style.RESET_ALL}")
            acc_prompt = f"{Fore.CYAN}{'Berapa akun Webshare yang ingin dipanen? [Default: 1]: ' if CURRENT_LANG == 'ID' else 'How many Webshare accounts to hunt? [Default: 1]: '}{Style.RESET_ALL}"
            a_input = input(acc_prompt).strip()
            total_acc = int(a_input) if a_input.isdigit() and int(a_input) > 0 else 1

            from core.webshare_hunter import check_capsolver_balance
            cs_info = check_capsolver_balance()
            is_headless = False

            if cs_info.get("can_headless"):
                print(f"\n  {Fore.GREEN}✓ CapSolver API Aktif! Saldo: ${cs_info['balance']:.3f} (Mode Headless siap tempur){Style.RESET_ALL}")
                head_prompt = f"{Fore.CYAN}{'Jalankan di background tanpa jendela (Headless)? [Y/n]: ' if CURRENT_LANG == 'ID' else 'Run in background (Headless)? [Y/n]: '}{Style.RESET_ALL}"
                h_input = input(head_prompt).strip().lower()
                is_headless = h_input in ("", "y", "yes")
            else:
                print(f"\n{Fore.CYAN}ℹ️  STATUS ENGINE CAPTCHA & MODE TAMPILAN:{Style.RESET_ALL}")
                print(f"  • Solver Aktif   : {Fore.GREEN}Free AI Audio Solver (SpeechRecognition, Tanpa Saldo Token){Style.RESET_ALL}")
                print(f"  • Status Headless: {Fore.CYAN}Opsional / Dimatikan{Style.RESET_ALL} ({cs_info.get('message')})")
                print(f"  {Fore.LIGHTBLACK_EX}💡 Penjelasan: Audio Solver gratisan WAJIB menggunakan jendela tampak agar bot")
                print(f"     bergerak alami & tidak diblokir 'Automated queries' oleh Google reCAPTCHA.{Style.RESET_ALL}")
                print(f"  {Fore.GREEN}👉 Otomatis menggunakan Mode Jendela Tampak (Mode Paling Stabil & Gacor)...{Style.RESET_ALL}\n")
                is_headless = False

            db_target = find_9router_db()
            run_webshare_hunter(total=total_acc, headless=is_headless, sync_9router_db=db_target)
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ws_file = os.path.join(base_dir, "output", "webshare_residential.txt")
            if os.path.exists(ws_file) and os.path.getsize(ws_file) > 0:
                fm_name = "File Explorer" if sys.platform == "win32" else "Finder" if sys.platform == "darwin" else "File Manager"
                ed_name = "Notepad" if sys.platform == "win32" else "TextEdit" if sys.platform == "darwin" else "Text Editor"
                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}🏢 AMUNISI RESIDENTIAL SIAP! PILIH AKSI:{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📝 Buka File Daftar IP di {ed_name} ({Fore.YELLOW}webshare_residential.txt{Fore.WHITE})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📂 Buka Folder Output di {fm_name}")
                    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📋 Tampilkan Contoh Kode Python Requests Siap Pakai")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-3, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_text_editor(ws_file)
                    elif sub == "2":
                        open_in_explorer(os.path.dirname(ws_file))
                    elif sub == "3":
                        with open(ws_file, "r", encoding="utf-8") as f:
                            first_proxy = f.readline().strip()
                        print(f"\n{Fore.CYAN}📋 CONTOH KODE PYTHON REQUESTS:{Style.RESET_ALL}")
                        print(f"""{Fore.WHITE}import requests

proxies = {{
    "http": "{first_proxy or 'http://user:pass@ip:port'}",
    "https": "{first_proxy or 'http://user:pass@ip:port'}"
}}

resp = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
print("IP Aktif Residential:", resp.json()["ip"])
{Style.RESET_ALL}""")
                    else:
                        break
            continue
        elif choice.lower() == "d":
            try:
                from core.decodo_hunter import run_decodo_hunter, get_decodo_headless_config
            except ImportError as e:
                print(f"\n{Fore.RED}⚠️ Dependensi CloakBrowser / Decodo Hunter belum lengkap: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}👉 Jalankan: pip install cloakbrowser{Style.RESET_ALL}\n")
                continue

            is_hl = get_decodo_headless_config()
            mode_desc = "HEADLESS" if is_hl else "HEADFUL"
            print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{f'🦊 MEMBUKA DECODO RESIDENTIAL HUNTER ({mode_desc})...' if CURRENT_LANG == 'ID' else f'🦊 LAUNCHING DECODO RESIDENTIAL HUNTER ({mode_desc})...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: Auto register & verifikasi email Cloudflare, klaim trial kartu kredit, dan ekspor proxy HTTP.' if CURRENT_LANG == 'ID' else '💡 Info: Auto register & Cloudflare email verify, credit card trial claim, and HTTP proxy export.'}{Style.RESET_ALL}")
            acc_prompt = f"{Fore.CYAN}{'Berapa akun Decodo yang ingin dipanen? [Default: 1]: ' if CURRENT_LANG == 'ID' else 'How many Decodo accounts to hunt? [Default: 1]: '}{Style.RESET_ALL}"
            a_input = input(acc_prompt).strip()
            total_acc = int(a_input) if a_input.isdigit() and int(a_input) > 0 else 1

            db_target = find_9router_db()
            run_decodo_hunter(total=total_acc, headless=None, sync_9router_db=db_target)

            base_dir = os.path.dirname(os.path.abspath(__file__))
            decodo_file = os.path.join(base_dir, "output", "decodo_residential.txt")
            acc_file = os.path.join(base_dir, "output", "decodo_accounts.txt")
            fm_name = "File Explorer" if sys.platform == "win32" else "Finder" if sys.platform == "darwin" else "File Manager"
            ed_name = "Notepad" if sys.platform == "win32" else "TextEdit" if sys.platform == "darwin" else "Text Editor"

            while True:
                print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                print(f"{Fore.WHITE}{Style.BRIGHT}🦊 AMUNISI DECODO RESIDENTIAL SELESAI DIPROSES! PILIH AKSI:{Style.RESET_ALL}")
                print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📝 Buka File Daftar Akun di {ed_name} ({Fore.YELLOW}decodo_accounts.txt{Fore.WHITE})")
                print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📋 Buka File Proxy HTTP di {ed_name} ({Fore.YELLOW}decodo_residential.txt{Fore.WHITE})")
                print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📂 Buka Folder Output di {fm_name}")
                print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                sub = input(f"{Fore.YELLOW}Pilih aksi [1-3, 0=Kembali]: {Style.RESET_ALL}").strip()
                if sub == "1":
                    open_in_text_editor(acc_file)
                elif sub == "2":
                    open_in_text_editor(decodo_file)
                elif sub == "3":
                    open_in_explorer(os.path.join(base_dir, "output"))
                else:
                    break
            continue
        elif choice.lower() == "c":
            print(f"\n{Fore.CYAN}{Style.BRIGHT}{'🚀 MEMBUAT PROFIL CLOUDFLARE WARP (WIREGUARD / SING-BOX)...' if CURRENT_LANG == 'ID' else '🚀 GENERATING CLOUDFLARE WARP PROFILE...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: Registrasi resmi via Cloudflare REST API (100% legal, tanpa captcha, unlimited).' if CURRENT_LANG == 'ID' else '💡 Info: Official registration via Cloudflare REST API (zero captcha, unlimited).'}{Style.RESET_ALL}\n")
            from core.warp_generator import generate_and_save_warp
            db_target = find_9router_db()
            profile = generate_and_save_warp(sync_db=bool(db_target))
            if profile:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                warp_conf = os.path.join(base_dir, "output", "warp", "warp.conf")
                warp_folder = os.path.join(base_dir, "output", "warp")
                is_win = sys.platform == "win32"
                is_mac = sys.platform == "darwin"
                is_linux = sys.platform.startswith("linux")
                fm_name = "File Explorer" if is_win else "Finder" if is_mac else "File Manager"

                if is_win:
                    platform_label = "Windows (.exe)"
                    download_url = "https://download.wireguard.com/windows-client/wireguard-installer.exe"
                elif is_mac:
                    platform_label = "macOS (Mac App Store)"
                    download_url = "https://apps.apple.com/us/app/wireguard/id1451685025"
                elif is_linux:
                    platform_label = "Linux (apt / pacman)"
                    download_url = "https://www.wireguard.com/install/"
                else:
                    platform_label = "Perangkat Anda"
                    download_url = "https://www.wireguard.com/install/"

                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}🎉 AMUNISI CLOUDFLARE WARP SIAP DIGUNAKAN! PILIH AKSI:{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📂 Buka Folder File ({Fore.YELLOW}warp.conf{Fore.WHITE} di {fm_name})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 🌐 Download / Install Resmi WireGuard untuk {Fore.YELLOW}{platform_label}{Fore.WHITE}")
                    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📋 Panduan Kilat Cara Pakai di WireGuard ({'Windows' if is_win else 'macOS' if is_mac else 'Linux'})")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-3, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_explorer(warp_conf if os.path.exists(warp_conf) else warp_folder)
                    elif sub == "2":
                        if is_linux:
                            print(f"\n{Fore.CYAN}🐧 CARA INSTALL WIREGUARD DI LINUX:{Style.RESET_ALL}")
                            print(f"  • Ubuntu / Debian / Mint : {Fore.GREEN}sudo apt update && sudo apt install -y wireguard{Style.RESET_ALL}")
                            print(f"  • Arch Linux / Manjaro   : {Fore.GREEN}sudo pacman -S wireguard-tools{Style.RESET_ALL}")
                            print(f"  • Fedora / RHEL          : {Fore.GREEN}sudo dnf install wireguard-tools{Style.RESET_ALL}")
                            print(f"\n  🚀 Cara Konek Cepat via Terminal:")
                            print(f"    {Fore.YELLOW}sudo wg-quick up \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  🛑 Cara Matikan Tunnel:")
                            print(f"    {Fore.YELLOW}sudo wg-quick down \"{warp_conf}\"{Style.RESET_ALL}\n")
                            open_url_in_browser(download_url)
                        else:
                            print(f"  {Fore.GREEN}🌐 Membuka link download resmi WireGuard {platform_label}...{Style.RESET_ALL}")
                            open_url_in_browser(download_url)
                    elif sub == "3":
                        print(f"\n{Fore.CYAN}📖 PANDUAN KILAT CARA PAKAI (1 MENIT LANGSUNG KONEK):{Style.RESET_ALL}")
                        if is_win:
                            print(f"  1. Buka aplikasi WireGuard di Windows.")
                            print(f"  2. Klik tombol {Fore.YELLOW}'Add Tunnel'{Style.RESET_ALL} (atau tekan {Fore.YELLOW}Ctrl + O{Style.RESET_ALL}).")
                            print(f"  3. Pilih file: {Fore.GREEN}{warp_conf}{Style.RESET_ALL}")
                            print(f"  4. Klik tombol {Fore.YELLOW}'Activate'{Style.RESET_ALL}.")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh koneksi PC kamu otomatis berkecepatan monster via Cloudflare!{Style.RESET_ALL}")
                        elif is_mac:
                            print(f"  1. Buka aplikasi WireGuard dari Mac App Store / Applications.")
                            print(f"  2. Klik menu bar WireGuard -> {Fore.YELLOW}'Import tunnel(s) from file'{Style.RESET_ALL} (atau tekan {Fore.YELLOW}Cmd + O{Style.RESET_ALL}).")
                            print(f"  3. Pilih file: {Fore.GREEN}{warp_conf}{Style.RESET_ALL}")
                            print(f"  4. Klik tombol {Fore.YELLOW}'Activate'{Style.RESET_ALL}.")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh koneksi Mac kamu otomatis lewat Cloudflare WARP!{Style.RESET_ALL}")
                        else:
                            print(f"  1. Buka terminal Linux.")
                            print(f"  2. Jalankan perintah: {Fore.YELLOW}sudo wg-quick up \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  3. Cek IP aktif:      {Fore.GREEN}curl https://api.ipify.org{Style.RESET_ALL}")
                            print(f"  4. Matikan tunnel:    {Fore.YELLOW}sudo wg-quick down \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh network Linux kamu aman terlindungi Anycast Cloudflare!{Style.RESET_ALL}")
                    else:
                        break
            continue
        elif choice.lower() == "f":
            print(f"\n{Fore.CYAN}{Style.BRIGHT}{'⚡ MEMULAI AIOHTTP FAST PROXY HARVESTER...' if CURRENT_LANG == 'ID' else '⚡ LAUNCHING AIOHTTP FAST HARVESTER...'}{Style.RESET_ALL}")
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            run_fast_harvester(max_latency_ms=1200, target_count=15, sync_db=bool(db_target))
        elif choice.lower() == "g" or choice == "4":
            print(f"\n{Fore.GREEN}{Style.BRIGHT}{'🚜 MENJALANKAN MODE PETANI AFK 24/7 (RESILIENT GATEWAY + AUTO-HEALER)...' if CURRENT_LANG == 'ID' else '🚜 STARTING 24/7 AFK FARMER DAEMON (RESILIENT GATEWAY + AUTO-HEALER)...'}{Style.RESET_ALL}")
            from core.server import start_proxy_server
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            print(f"  {Fore.LIGHTBLACK_EX}• Menyiapkan amunisi awal dari feed cepat...{Style.RESET_ALL}")
            initial = run_fast_harvester(max_latency_ms=1200, target_count=10, sync_db=bool(db_target))
            print(f"\n{Fore.GREEN}✓ Gateway aktif di http://127.0.0.1:8888 (Auto-prune & refill aktif non-stop). Tekan Ctrl+C untuk berhenti.{Style.RESET_ALL}\n")
            start_proxy_server(initial, port=8888, background=False, enable_health_check=True, health_check_interval=90, min_healthy_count=5)
        elif choice.lower() in ("s", "saved"):
            view_saved_results()
        elif choice == "0" or choice.lower() == "q":
            goodbye_msg = "💀 Capek panen, cabut dulu ah... Jangan lupa sentuh rumput bos! 👋" if CURRENT_LANG == "ID" else "💀 Session terminated — go touch some grass! 👋"
            print(f"\n{Fore.YELLOW}{goodbye_msg}{Style.RESET_ALL}\n")
            break
        else:
            invalid_msg = "Pilihan tidak valid. Silakan pilih W, C, F, G, 1-3, E, T, K, U, M, S, L, atau 0." if CURRENT_LANG == "ID" else "Invalid option. Please choose W, C, F, G, 1-3, E, T, K, U, M, S, L, or 0."
            print(f"{Fore.RED}{invalid_msg}{Style.RESET_ALL}")



        try:
            pause_msg = "[Tekan Enter untuk kembali ke menu utama...]" if CURRENT_LANG == "ID" else "[Press Enter to return to main menu...]"
            input(f"\n{Fore.LIGHTBLACK_EX}{pause_msg}{Style.RESET_ALL}")
        except (KeyboardInterrupt, EOFError):
            break

def main():
    if len(sys.argv) == 1:
        show_interactive_menu()
        return

    parser = argparse.ArgumentParser(description="PetaniProxy v1.1.0 - High-Speed Multi-Protocol Proxy Harvester, Cloudflare WARP & Resilient Gateway")

    parser.add_argument("--protocol", "-p", choices=["all", "http", "socks4", "socks5"], default="all", help="Target proxy protocol (default: all)")
    parser.add_argument("--max", "-m", type=int, default=250, help="Maximum candidate proxies to validate (default: 250)")
    parser.add_argument("--target", "-t", type=int, default=15, help="Target number of alive proxies to collect (default: 15)")
    parser.add_argument("--timeout", type=float, default=3.0, help="Connection timeout in seconds (default: 3.0)")
    parser.add_argument("--workers", "-w", type=int, default=50, help="Concurrent testing workers (default: 50)")
    parser.add_argument("--country", "-c", type=str, default=None, help="Filter by country ISO code (e.g. US, SG, ID, DE)")
    parser.add_argument("--anonymity", choices=["all", "elite", "anonymous", "transparent"], default="all", help="Filter by anonymity level (default: all)")
    parser.add_argument("--target-url", type=str, default=None, help="Validate proxies against specific website (e.g. https://google.com)")
    parser.add_argument("--serve", nargs="?", const=8888, type=int, default=None, help="Start local rotating forward proxy & REST API on port (default: 8888)")
    parser.add_argument("--loop", "-l", type=int, default=0, help="Auto-refresh loop interval in minutes (0 = single run)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Custom output directory")
    parser.add_argument("--sync-9router", type=str, default=None, help="Path to BansosRouter/9Router data.sqlite for direct database sync (or 'auto')")
    parser.add_argument("--warp", "-C", action="store_true", help="Generate Cloudflare WARP WireGuard & Sing-box profile (zero captcha, unlimited)")
    parser.add_argument("--fast-harvest", "-F", type=int, nargs="?", const=15, default=None, help="Run ultra-fast aiohttp proxy harvester for N targets")
    parser.add_argument("--max-latency", type=int, default=1200, help="Maximum latency in ms for fast harvester (default: 1200)")
    parser.add_argument("--daemon-gateway", "-G", action="store_true", help="Run 24/7 resilient local gateway on port 8888 with auto-healer")
    parser.add_argument("--webshare", "-W", type=int, nargs="?", const=1, default=None, help="Trigger Webshare Residential Hunter for N accounts (default: 1)")
    parser.add_argument("--decodo", "-D", type=int, nargs="?", const=1, default=None, help="Trigger Decodo Residential Hunter for N accounts (CloakBrowser stealth Chromium)")
    parser.add_argument("--headless", action="store_true", help="Force headless mode (run browser in background)")
    parser.add_argument("--headful", action="store_true", help="Force headful mode (display browser GUI)")
    parser.add_argument("--health-check", "-H", nargs="?", const="auto", default=None, help="Check health of saved proxy file (.txt or .json)")
    parser.add_argument("--update", action="store_true", help="Perform 1-click update via git pull and exit")
    parser.add_argument("--check-update", action="store_true", help="Check for available updates on GitHub and display patch notes")
    parser.add_argument("--install-deps", action="store_true", help="Auto-install all dependencies from requirements.txt")
    parser.add_argument("--version", "-v", action="store_true", help="Show current version, announcement and exit")

    args = parser.parse_args()

    if args.version:
        v_info = get_local_version_info()
        print(BANNER)
        show_full_announcement(v_info)
        return

    if args.install_deps:
        print(BANNER)
        install_dependencies()
        return

    if args.check_update:
        print(BANNER)
        print(f"{Fore.CYAN}Memeriksa pembaruan ke GitHub...{Style.RESET_ALL}\n")
        info = check_for_updates(timeout=3.5)
        if info.get("has_update"):
            print(render_update_banner(info))
            show_full_announcement(info)
        else:
            print(f"{Fore.GREEN}✅ PetaniProxy sudah versi terbaru (v{info.get('current_version')})!{Style.RESET_ALL}")
            show_full_announcement(info)
        return

    if args.update:
        print(BANNER)
        perform_update(restart=False)
        return

    print(BANNER)

    router_db = args.sync_9router
    if router_db == "auto" or router_db is None:
        router_db = find_9router_db()

    if args.health_check is not None:
        target_f = None if args.health_check == "auto" else args.health_check
        show_health_check_menu(target_file=target_f, timeout=args.timeout)
        return

    if args.warp:
        from core.warp_generator import generate_and_save_warp
        generate_and_save_warp(output_dir=args.output, sync_db=bool(router_db))
        return

    if args.fast_harvest is not None:
        from core.fast_validator import run_fast_harvester
        run_fast_harvester(max_latency_ms=args.max_latency, target_count=args.fast_harvest, sync_db=bool(router_db))
        return

    if args.daemon_gateway:
        from core.server import start_proxy_server
        from core.fast_validator import run_fast_harvester
        print(f"\n{Fore.GREEN}🛡️ Menyiapkan amunisi awal untuk 24/7 Resilient Gateway...{Style.RESET_ALL}")
        initial = run_fast_harvester(max_latency_ms=args.max_latency, target_count=10, sync_db=bool(router_db))
        print(f"\n{Fore.GREEN}✓ Meluncurkan Gateway di http://127.0.0.1:8888 dengan auto-healer...{Style.RESET_ALL}\n")
        start_proxy_server(initial, port=8888, background=False, enable_health_check=True, health_check_interval=90, min_healthy_count=5)
        return

    if args.webshare is not None:
        try:
            from core.webshare_hunter import run_webshare_hunter, check_capsolver_balance
        except ImportError as e:
            print(f"{Fore.RED}⚠️ Dependensi Webshare Hunter belum lengkap: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Silakan jalankan: python main.py --install-deps{Style.RESET_ALL}\n")
            sys.exit(1)

        if args.headless:
            cs = check_capsolver_balance()
            if not cs.get("can_headless"):
                print(f"\n{Fore.YELLOW}⚠️ PERINGATAN HEADLESS:{Style.RESET_ALL} {cs.get('message')}")
                print(f"{Fore.LIGHTBLACK_EX}Menjalankan Audio Solver gratisan di mode headless berisiko tinggi memicu blokir 'Automated queries' dari Google.")
                print(f"Disarankan menjalankan tanpa flag --headless atau sediakan CAPSOLVER_API_KEY.{Style.RESET_ALL}\n")

        run_webshare_hunter(total=args.webshare, headless=args.headless, sync_9router_db=router_db, output_dir=args.output)
        return

    if args.decodo is not None:
        try:
            from core.decodo_hunter import run_decodo_hunter
        except ImportError as e:
            print(f"{Fore.RED}⚠️ Dependensi CloakBrowser / Decodo Hunter belum lengkap: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Silakan jalankan: pip install cloakbrowser{Style.RESET_ALL}\n")
            sys.exit(1)

        hl_override = True if args.headless else False if args.headful else None
        run_decodo_hunter(total=args.decodo, headless=hl_override, sync_9router_db=router_db, output_dir=args.output)
        return

    proto_list = [args.protocol] if args.protocol != "all" else ["http", "socks4", "socks5"]

    if args.loop > 0:
        print(f"{Fore.MAGENTA}🔄 Auto-refresh loop active: Running every {args.loop} minutes... (Press Ctrl+C to stop){Style.RESET_ALL}")
        while True:
            try:
                run_harvester(
                    protocols=proto_list,
                    max_check=args.max,
                    target_alive=args.target,
                    timeout=args.timeout,
                    workers=args.workers,
                    country=args.country,
                    anonymity=args.anonymity,
                    target_url=args.target_url,
                    output_dir=args.output,
                    sync_9router=router_db,
                    serve_port=args.serve
                )
                print(f"{Fore.LIGHTBLACK_EX}Sleeping for {args.loop} minutes before next sweep...{Style.RESET_ALL}")
                time.sleep(args.loop * 60)
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}🛑 Harvester stopped by user.{Style.RESET_ALL}")
                break
    else:
        run_harvester(
            protocols=proto_list,
            max_check=args.max,
            target_alive=args.target,
            timeout=args.timeout,
            workers=args.workers,
            country=args.country,
            anonymity=args.anonymity,
            target_url=args.target_url,
            output_dir=args.output,
            sync_9router=router_db,
            serve_port=args.serve
        )

if __name__ == "__main__":
    main()
