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
import threading
import collections
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

# Comprehensive ISO 3166-1 alpha-2 country mapping
COUNTRY_MAP: Dict[str, str] = {
    "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra", "AO": "Angola",
    "AR": "Argentina", "AM": "Armenia", "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan",
    "BD": "Bangladesh", "BY": "Belarus", "BE": "Belgium", "BO": "Bolivia", "BA": "Bosnia",
    "BR": "Brazil", "BG": "Bulgaria", "KH": "Cambodia", "CA": "Canada", "CL": "Chile",
    "CN": "China", "CO": "Colombia", "CR": "Costa Rica", "HR": "Croatia", "CY": "Cyprus",
    "CZ": "Czech Republic", "DK": "Denmark", "DO": "Dominican Republic", "EC": "Ecuador",
    "EG": "Egypt", "EE": "Estonia", "FI": "Finland", "FR": "France", "GE": "Georgia",
    "DE": "Germany", "GR": "Greece", "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland",
    "IN": "India", "ID": "Indonesia", "IR": "Iran", "IQ": "Iraq", "IE": "Ireland",
    "IL": "Israel", "IT": "Italy", "JP": "Japan", "JO": "Jordan", "KZ": "Kazakhstan",
    "KE": "Kenya", "KR": "South Korea", "KW": "Kuwait", "LV": "Latvia", "LB": "Lebanon",
    "LT": "Lithuania", "LU": "Luxembourg", "MY": "Malaysia", "MX": "Mexico", "MD": "Moldova",
    "MA": "Morocco", "NL": "Netherlands", "NZ": "New Zealand", "NG": "Nigeria", "NO": "Norway",
    "PK": "Pakistan", "PA": "Panama", "PE": "Peru", "PH": "Philippines", "PL": "Poland",
    "PT": "Portugal", "QA": "Qatar", "RO": "Romania", "RU": "Russia", "SA": "Saudi Arabia",
    "RS": "Serbia", "SG": "Singapore", "SK": "Slovakia", "SI": "Slovenia", "ZA": "South Africa",
    "ES": "Spain", "LK": "Sri Lanka", "SE": "Sweden", "CH": "Switzerland", "TW": "Taiwan",
    "TH": "Thailand", "TR": "Turkey", "UA": "Ukraine", "AE": "United Arab Emirates",
    "GB": "United Kingdom", "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan",
    "VE": "Venezuela", "VN": "Vietnam"
}

# Major Cloudflare Edge Airport (COLO) locations
CF_COLO_CITIES: Dict[str, str] = {
    "CGK": "Jakarta", "SUB": "Surabaya", "SIN": "Singapore", "KUL": "Kuala Lumpur",
    "BKK": "Bangkok", "MNL": "Manila", "HKG": "Hong Kong", "TPE": "Taipei",
    "NRT": "Tokyo", "HND": "Tokyo", "KIX": "Osaka", "ICN": "Seoul",
    "SYD": "Sydney", "MEL": "Melbourne", "BNE": "Brisbane", "AKL": "Auckland",
    "LHR": "London", "LGW": "London", "MAN": "Manchester", "EDI": "Edinburgh",
    "CDG": "Paris", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "MXP": "Milan", "FCO": "Rome", "ZRH": "Zurich", "VIE": "Vienna",
    "WAW": "Warsaw", "ARN": "Stockholm", "OSL": "Oslo", "CPH": "Copenhagen",
    "HEL": "Helsinki", "SJC": "San Jose", "SFO": "San Francisco", "LAX": "Los Angeles",
    "SEA": "Seattle", "PDX": "Portland", "DEN": "Denver", "DFW": "Dallas",
    "IAH": "Houston", "ORD": "Chicago", "ATL": "Atlanta", "MIA": "Miami",
    "IAD": "Washington DC", "EWR": "Newark", "JFK": "New York", "BOS": "Boston",
    "YYZ": "Toronto", "YVR": "Vancouver", "YUL": "Montreal", "GRU": "Sao Paulo",
    "GIG": "Rio de Janeiro", "EZE": "Buenos Aires", "SCL": "Santiago", "BOG": "Bogota",
    "DXB": "Dubai", "DOH": "Doha", "JNB": "Johannesburg", "BOM": "Mumbai", "DEL": "Delhi"
}

_IP_GEO_CACHE: Dict[str, Dict[str, str]] = {}
_GEO_LOCK = threading.Lock()

def lookup_ip_geoip(ip: str, timeout: float = 2.5) -> Dict[str, str]:
    """Lookup IP GeoIP via cache or ipwho.is with fallback."""
    if not ip or ip.startswith(("127.", "192.168.", "10.")):
        return {}

    with _GEO_LOCK:
        if ip in _IP_GEO_CACHE:
            return _IP_GEO_CACHE[ip]

    res = {}
    try:
        url = f"https://ipwho.is/{ip}"
        if HAS_REQUESTS:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                d = r.json()
                if d.get("success", True):
                    c_code = (d.get("country_code") or "??").upper()
                    c_name = d.get("country") or COUNTRY_MAP.get(c_code, "Unknown")
                    res = {
                        "country": c_name,
                        "country_code": c_code,
                        "city": d.get("city", "-"),
                        "isp": d.get("connection", {}).get("isp", "-")
                    }
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status == 200:
                    d = json.loads(r.read().decode("utf-8"))
                    if d.get("success", True):
                        c_code = (d.get("country_code") or "??").upper()
                        c_name = d.get("country") or COUNTRY_MAP.get(c_code, "Unknown")
                        res = {
                            "country": c_name,
                            "country_code": c_code,
                            "city": d.get("city", "-"),
                            "isp": d.get("connection", {}).get("isp", "-")
                        }
    except Exception:
        pass

    with _GEO_LOCK:
        if res:
            _IP_GEO_CACHE[ip] = res
    return res

def resolve_location(
    loc_code: Optional[str] = None,
    colo_code: Optional[str] = None,
    json_data: Optional[Dict[str, Any]] = None,
    default_item: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None
) -> Dict[str, str]:
    """
    Resolves country code, country name, city and a compact location string.
    Checks memory cache, Cloudflare loc/colo, and JSON data.
    """
    default = default_item or {}
    target_ip = ip or default.get("ip")

    with _GEO_LOCK:
        cached = dict(_IP_GEO_CACHE.get(target_ip, {})) if target_ip else {}

    c_code = (loc_code or cached.get("country_code") or default.get("country_code") or "??").upper()
    c_name = cached.get("country") or COUNTRY_MAP.get(c_code) or default.get("country") or "Unknown"
    city = cached.get("city") or CF_COLO_CITIES.get((colo_code or "").upper()) or default.get("city") or "-"

    if json_data:
        c_code = str(json_data.get("country_code") or json_data.get("countryCode") or c_code).upper()
        c_name = str(json_data.get("country") or json_data.get("country_name") or COUNTRY_MAP.get(c_code, c_name))
        city = str(json_data.get("city") or city)

    loc_str = f"[{c_code}] {c_name}"
    if city and city != "-":
        loc_str += f" ({city})"

    return {
        "country_code": c_code,
        "country": c_name,
        "city": city,
        "location_str": loc_str
    }


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
                loc_code = None
                colo_code = None
                json_data = None
                text = resp.text
                if "ip=" in text:
                    for line in text.splitlines():
                        if line.startswith("loc="):
                            loc_code = line.split("=", 1)[1].strip().upper()
                        elif line.startswith("colo="):
                            colo_code = line.split("=", 1)[1].strip().upper()
                        elif line.startswith("ip="):
                            egress_ip = line.split("=", 1)[1].strip()
                elif "{" in text:
                    try:
                        json_data = resp.json()
                        egress_ip = json_data.get("ip")
                    except Exception:
                        pass

                geo = resolve_location(loc_code=loc_code, colo_code=colo_code, json_data=json_data, default_item=proxy_item)
                proxy_item["country"] = geo["country"]
                proxy_item["country_code"] = geo["country_code"]
                proxy_item["city"] = geo["city"]

                return {
                    "alive": True,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed,
                    "egress_ip": egress_ip or proxy_item["ip"],
                    "country": geo["country"],
                    "country_code": geo["country_code"],
                    "city": geo["city"],
                    "location_str": geo["location_str"],
                    "error": None,
                    "proxy": proxy_item
                }
            else:
                geo = resolve_location(default_item=proxy_item)
                return {
                    "alive": False,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed,
                    "egress_ip": None,
                    "country": geo["country"],
                    "country_code": geo["country_code"],
                    "city": geo["city"],
                    "location_str": geo["location_str"],
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
            geo = resolve_location(default_item=proxy_item)
            return {
                "alive": False,
                "status_code": 0,
                "latency_ms": elapsed,
                "egress_ip": None,
                "country": geo["country"],
                "country_code": geo["country_code"],
                "city": geo["city"],
                "location_str": geo["location_str"],
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
                loc_code = None
                colo_code = None
                json_data = None
                raw_body = resp.read().decode("utf-8", errors="ignore")
                if "ip=" in raw_body:
                    for line in raw_body.splitlines():
                        if line.startswith("loc="):
                            loc_code = line.split("=", 1)[1].strip().upper()
                        elif line.startswith("colo="):
                            colo_code = line.split("=", 1)[1].strip().upper()
                        elif line.startswith("ip="):
                            egress_ip = line.split("=", 1)[1].strip()
                elif "{" in raw_body:
                    try:
                        json_data = json.loads(raw_body)
                        egress_ip = json_data.get("ip")
                    except Exception:
                        pass

                geo = resolve_location(loc_code=loc_code, colo_code=colo_code, json_data=json_data, default_item=proxy_item)
                proxy_item["country"] = geo["country"]
                proxy_item["country_code"] = geo["country_code"]
                proxy_item["city"] = geo["city"]

                return {
                    "alive": True,
                    "status_code": resp.status,
                    "latency_ms": elapsed,
                    "egress_ip": egress_ip or proxy_item["ip"],
                    "country": geo["country"],
                    "country_code": geo["country_code"],
                    "city": geo["city"],
                    "location_str": geo["location_str"],
                    "error": None,
                    "proxy": proxy_item
                }
            else:
                geo = resolve_location(default_item=proxy_item)
                return {
                    "alive": False,
                    "status_code": resp.status,
                    "latency_ms": elapsed,
                    "egress_ip": None,
                    "country": geo["country"],
                    "country_code": geo["country_code"],
                    "city": geo["city"],
                    "location_str": geo["location_str"],
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
        geo = resolve_location(default_item=proxy_item)
        return {
            "alive": False,
            "status_code": 0,
            "latency_ms": elapsed,
            "egress_ip": None,
            "country": geo["country"],
            "country_code": geo["country_code"],
            "city": geo["city"],
            "location_str": geo["location_str"],
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
            "avg_latency_ms": 0,
            "country_distribution": {}
        }

    alive_results = []
    dead_results = []
    t_start = time.perf_counter()

    workers = min(max_workers, max(1, len(proxies)))
    completed_count = 0

    # Pre-warm GeoIP cache asynchronously so locations resolve fast for all nodes
    unique_ips = list({p["ip"] for p in proxies if p.get("ip")})[:60]
    if unique_ips:
        def prewarm():
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(unique_ips))) as ex:
                list(ex.map(lookup_ip_geoip, unique_ips))
        threading.Thread(target=prewarm, daemon=True).start()

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
                res["proxy"]["country"] = res["country"]
                res["proxy"]["country_code"] = res["country_code"]
                res["proxy"]["city"] = res["city"]
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

    import collections
    country_counts = collections.Counter(r["country"] for r in alive_results if r.get("country") and r["country"] != "Unknown")

    return {
        "file_path": file_path,
        "total": len(proxies),
        "alive": alive_results,
        "dead": dead_results,
        "duration_sec": duration,
        "avg_latency_ms": avg_latency,
        "country_distribution": dict(country_counts.most_common(10))
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
