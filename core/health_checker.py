"""
PetaniProxy v1.1 - Proxy Health Checker & File Probe Engine
Validates existing proxy files (.txt, .json), tests latency, handles
authenticated residential proxies (Webshare), and filters live nodes.
"""
import os
import sys
import time
import json
import socket
import base64
import urllib.request
import urllib.parse
import concurrent.futures
from typing import List, Dict, Any, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DEFAULT_PROBE_URL = "https://cloudflare.com/cdn-cgi/trace"
FALLBACK_PROBE_URL = "https://api.ipify.org?format=json"

def parse_proxy_string(raw_line: str, default_proto: str = "http") -> Optional[Dict[str, Any]]:
    """
    Parse various proxy line formats into a standardized dictionary:
    1. http://user:pass@ip:port
    2. socks5://user:pass@ip:port
    3. http://ip:port
    4. ip:port
    5. ip:port:user:pass
    """
    clean = raw_line.strip()
    if not clean or clean.startswith("#"):
        return None

    proto = default_proto
    username = None
    password = None
    host = None
    port = None

    # Format 1 & 2 & 3: protocol://...
    if "://" in clean:
        try:
            parsed = urllib.parse.urlparse(clean)
            proto = (parsed.scheme or default_proto).lower()
            host = parsed.hostname
            port = parsed.port
            username = parsed.username
            password = parsed.password
        except Exception:
            return None
    else:
        # Format 5: ip:port:user:pass
        parts = clean.split(":")
        if len(parts) == 4:
            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                return None
            username = parts[2].strip()
            password = parts[3].strip()
        elif len(parts) == 2:
            # Format 4: ip:port
            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                return None
        elif "@" in clean:
            # user:pass@ip:port without scheme
            return parse_proxy_string(f"http://{clean}")
        else:
            return None

    if not host or not port:
        return None

    # Construct clean raw url
    if username and password:
        raw_url = f"{proto}://{username}:{password}@{host}:{port}"
    else:
        raw_url = f"{proto}://{host}:{port}"

    display_str = f"{host}:{port}"
    if username:
        display_str = f"{username}:***@{host}:{port}"

    return {
        "ip": host,
        "port": int(port),
        "proxy": f"{host}:{port}",
        "protocol": proto,
        "username": username,
        "password": password,
        "raw_url": raw_url,
        "original_line": clean,
        "display": display_str
    }

def load_proxies_from_file(file_path: str) -> List[Dict[str, Any]]:
    """Load proxy items from a .txt or .json file."""
    if not os.path.exists(file_path):
        return []

    proxies = []
    seen = set()

    if file_path.endswith(".json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("proxies", []) if isinstance(data, dict) else data
            for item in items:
                if isinstance(item, dict):
                    raw = item.get("raw_url") or item.get("proxy") or f"{item.get('ip')}:{item.get('port')}"
                    p = parse_proxy_string(str(raw), default_proto=item.get("protocol", "http"))
                    if p:
                        # Copy existing metadata if present
                        p["country"] = item.get("country", "Unknown")
                        p["country_code"] = item.get("country_code", "??")
                        p["anonymity"] = item.get("anonymity", "Elite")
                        key = (p["ip"], p["port"], p["username"])
                        if key not in seen:
                            seen.add(key)
                            proxies.append(p)
        except Exception:
            return []
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = parse_proxy_string(line)
                if p:
                    key = (p["ip"], p["port"], p["username"])
                    if key not in seen:
                        seen.add(key)
                        proxies.append(p)

    return proxies

def probe_single_proxy(
    proxy_item: Dict[str, Any],
    test_url: str = DEFAULT_PROBE_URL,
    timeout: float = 3.5
) -> Dict[str, Any]:
    """
    Tests connectivity and measures response latency of a single proxy.
    Returns result dictionary with alive status, latency_ms, and response details.
    """
    raw_url = proxy_item["raw_url"]
    t0 = time.perf_counter()
    egress_ip = None

    # 1. Try via requests if available
    if HAS_REQUESTS:
        try:
            proxies = {"http": raw_url, "https": raw_url}
            resp = requests.get(
                test_url,
                proxies=proxies,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            elapsed = round((time.perf_counter() - t0) * 1000)
            if 200 <= resp.status_code < 400:
                # Extract egress IP if possible
                text = resp.text
                if "ip=" in text:
                    for line in text.splitlines():
                        if line.startswith("ip="):
                            egress_ip = line.split("=", 1)[1].strip()
                            break
                elif "{" in text:
                    try:
                        egress_ip = resp.json().get("ip")
                    except Exception:
                        pass

                return {
                    "alive": True,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed,
                    "egress_ip": egress_ip or proxy_item["ip"],
                    "error": None,
                    "proxy": proxy_item
                }
            else:
                return {
                    "alive": False,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed,
                    "egress_ip": None,
                    "error": f"HTTP {resp.status_code}",
                    "proxy": proxy_item
                }
        except Exception as e:
            elapsed = round((time.perf_counter() - t0) * 1000)
            err_msg = str(e)
            if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                err_clean = f"Timeout (> {int(timeout * 1000)}ms)"
            elif "407" in err_msg:
                err_clean = "Proxy Auth Failed (407)"
            elif "refused" in err_msg.lower():
                err_clean = "Connection Refused"
            else:
                err_clean = "Connection Failed"
            return {
                "alive": False,
                "status_code": 0,
                "latency_ms": elapsed,
                "egress_ip": None,
                "error": err_clean,
                "proxy": proxy_item
            }

    # 2. Fallback to standard library urllib
    try:
        handler = urllib.request.ProxyHandler({"http": raw_url, "https": raw_url})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request(
            test_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with opener.open(req, timeout=timeout) as resp:
            elapsed = round((time.perf_counter() - t0) * 1000)
            if 200 <= resp.status < 400:
                raw_body = resp.read().decode("utf-8", errors="ignore")
                if "ip=" in raw_body:
                    for line in raw_body.splitlines():
                        if line.startswith("ip="):
                            egress_ip = line.split("=", 1)[1].strip()
                            break
                elif "{" in raw_body:
                    try:
                        egress_ip = json.loads(raw_body).get("ip")
                    except Exception:
                        pass

                return {
                    "alive": True,
                    "status_code": resp.status,
                    "latency_ms": elapsed,
                    "egress_ip": egress_ip or proxy_item["ip"],
                    "error": None,
                    "proxy": proxy_item
                }
            else:
                return {
                    "alive": False,
                    "status_code": resp.status,
                    "latency_ms": elapsed,
                    "egress_ip": None,
                    "error": f"HTTP {resp.status}",
                    "proxy": proxy_item
                }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
            err_clean = f"Timeout (> {int(timeout * 1000)}ms)"
        elif "407" in err_msg:
            err_clean = "Proxy Auth Failed (407)"
        elif "refused" in err_msg.lower():
            err_clean = "Connection Refused"
        else:
            err_clean = "Connection Failed"
        return {
            "alive": False,
            "status_code": 0,
            "latency_ms": elapsed,
            "egress_ip": None,
            "error": err_clean,
            "proxy": proxy_item
        }

def check_file_health(
    file_path: str,
    timeout: float = 3.5,
    max_workers: int = 30,
    test_url: str = DEFAULT_PROBE_URL,
    on_progress = None
) -> Dict[str, Any]:
    """
    Check health of all proxies inside a file using concurrent workers.
    Calls on_progress(idx, total, result) upon each completed check.
    """
    proxies = load_proxies_from_file(file_path)
    if not proxies:
        return {
            "file_path": file_path,
            "total": 0,
            "alive": [],
            "dead": [],
            "duration_sec": 0.0,
            "avg_latency_ms": 0
        }

    alive_results = []
    dead_results = []
    t_start = time.perf_counter()

    workers = min(max_workers, max(1, len(proxies)))
    completed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(probe_single_proxy, p, test_url, timeout): p
            for p in proxies
        }

        for future in concurrent.futures.as_completed(future_map):
            completed_count += 1
            res = future.result()
            if res["alive"]:
                # Enrich proxy item with health metrics
                res["proxy"]["latency_ms"] = res["latency_ms"]
                res["proxy"]["egress_ip"] = res["egress_ip"]
                alive_results.append(res)
            else:
                dead_results.append(res)

            if on_progress:
                on_progress(completed_count, len(proxies), res)

    duration = round(time.perf_counter() - t_start, 2)
    alive_results.sort(key=lambda x: x["latency_ms"])

    avg_latency = 0
    if alive_results:
        avg_latency = int(sum(x["latency_ms"] for x in alive_results) / len(alive_results))

    return {
        "file_path": file_path,
        "total": len(proxies),
        "alive": alive_results,
        "dead": dead_results,
        "duration_sec": duration,
        "avg_latency_ms": avg_latency
    }

def save_healthy_proxies(
    source_path: str,
    healthy_results: List[Dict[str, Any]],
    overwrite: bool = False
) -> str:
    """
    Saves verified alive proxies back to file or to a new '_healthy' file.
    Preserves original formatting per line.
    """
    if overwrite:
        target_path = source_path
    else:
        base, ext = os.path.splitext(source_path)
        target_path = f"{base}_healthy{ext}"

    if source_path.endswith(".json"):
        export_data = {
            "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_alive": len(healthy_results),
            "proxies": [r["proxy"] for r in healthy_results]
        }
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
    else:
        lines = []
        for r in healthy_results:
            p = r["proxy"]
            lines.append(p.get("original_line") or p["raw_url"])
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    return target_path
