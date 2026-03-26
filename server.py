#!/usr/bin/env python3
import argparse
import atexit
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DEFAULT_CONFIG_PATH = ROOT / "config" / "default.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "local.json"
STATE_PATH = DATA_DIR / "state.json"
EVENTS_PATH = DATA_DIR / "events.jsonl"
PID_PATH = DATA_DIR / "server.pid"
DEV_PROXY_DIR = Path.home() / ".network-workflow-console"
DEV_PROXY_ENV_PATH = DEV_PROXY_DIR / "dev-proxy.env"
DEV_PROXY_SHELL_PATH = DEV_PROXY_DIR / "open-proxy-shell.sh"
GUI_PROXY_ENABLE_SCRIPT = ROOT / "launch_gui_with_proxy.sh"
GUI_PROXY_DISABLE_SCRIPT = ROOT / "clear_gui_proxy_env.sh"
STOP_CONSOLE_SCRIPT = ROOT / "stop_console.sh"

STATE_LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "profiles": {
        "studio": {
            "miniHost": "",
            "proxy": {
                "type": "http",
                "host": "",
                "port": 6152,
            },
        },
        "travel": {
            "miniHost": "",
            "proxy": {
                "type": "http",
                "host": "",
                "port": 6152,
            },
        },
    },
    "expectedRegion": "JP",
    "expectedCountryName": "Japan",
    "verifyEndpoints": [
        "https://api.ip.sb/geoip",
        "https://ifconfig.co/json",
    ],
    "timeouts": {
        "tcpMs": 1500,
        "httpMs": 5000,
        "verifyTotalMs": 10000,
    },
    "noProxy": [
        "localhost",
        "127.0.0.1",
        "::1",
        ".local",
    ],
    "privateNetworksHint": [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    ],
}

DEFAULT_STATE = {
    "networkMode": "normal",
    "devProxyPolicy": "off",
    "devProxySession": "not_prepared",
    "criticalOpsRecommendation": "caution",
    "lastModeChangeAt": None,
    "lastVerifyAt": None,
    "lastVerifyLevel": "unknown",
    "expectedRegion": "JP",
    "notes": "",
    "lastVerification": None,
}

MODE_PROFILES = {
    "normal": {
        "devProxyPolicy": "off",
        "devProxySession": "not_prepared",
        "criticalOpsRecommendation": "caution",
    },
    "studio": {
        "devProxyPolicy": "recommended",
        "devProxySession": "prepared",
        "criticalOpsRecommendation": "caution",
    },
    "studio_direct": {
        "devProxyPolicy": "off",
        "devProxySession": "not_prepared",
        "criticalOpsRecommendation": "caution",
    },
    "travel": {
        "devProxyPolicy": "required",
        "devProxySession": "prepared",
        "criticalOpsRecommendation": "caution",
    },
    "fallback": {
        "devProxyPolicy": "off",
        "devProxySession": "not_prepared",
        "criticalOpsRecommendation": "avoid",
    },
}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEV_PROXY_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_CONFIG_PATH.exists():
        atomic_write_json(DEFAULT_CONFIG_PATH, DEFAULT_CONFIG)
    if not STATE_PATH.exists():
        atomic_write_json(STATE_PATH, DEFAULT_STATE)
    if not EVENTS_PATH.exists():
        EVENTS_PATH.touch()


def write_pid():
    PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")


def remove_pid():
    try:
        if PID_PATH.exists():
            current = PID_PATH.read_text(encoding="utf-8").strip()
            if current == str(os.getpid()):
                PID_PATH.unlink()
    except OSError:
        pass


def launchctl_getenv(name):
    try:
        result = subprocess.run(
            ["launchctl", "getenv", name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or "").strip()


def app_running(app_name):
    try:
        result = subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to return running'],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return (result.stdout or "").strip().lower() == "true"


def current_service_pid():
    if PID_PATH.exists():
        try:
            pid = PID_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            pid = ""
        if pid and pid.isdigit():
            try:
                os.kill(int(pid), 0)
                return int(pid)
            except OSError:
                return None
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP:8123", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) > 1:
        parts = lines[1].split()
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    return None


def app_control_status_payload():
    http_proxy = launchctl_getenv("HTTP_PROXY")
    https_proxy = launchctl_getenv("HTTPS_PROXY")
    all_proxy = launchctl_getenv("ALL_PROXY")
    no_proxy = launchctl_getenv("NO_PROXY")
    service_pid = current_service_pid()

    return {
        "service": {
            "running": service_pid is not None,
            "pid": service_pid,
            "port": 8123,
        },
        "guiProxy": {
            "enabled": any([http_proxy, https_proxy, all_proxy]),
            "httpProxy": http_proxy,
            "httpsProxy": https_proxy,
            "allProxy": all_proxy,
            "noProxy": no_proxy,
        },
        "apps": {
            "codex": {
                "running": app_running("Codex"),
            },
            "antigravity": {
                "running": app_running("Antigravity"),
            },
        },
        "notes": [
            "GUI 代理开关会重启 Codex 和 Antigravity。",
            "关闭控制台会让当前 localhost 页面停止响应。",
        ],
        "checkedAt": now_iso(),
    }


def run_local_script(script_path, *args):
    result = subprocess.run(
        [str(script_path), *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output


def deep_merge(base, overlay):
    merged = deepcopy(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return deepcopy(default)
    except json.JSONDecodeError:
        return deepcopy(default)


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp_path.replace(path)


def append_event(payload):
    payload = deepcopy(payload)
    payload.setdefault("ts", now_iso())
    with STATE_LOCK:
        with EVENTS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_config():
    stored = deep_merge(
        DEFAULT_CONFIG,
        read_json(DEFAULT_CONFIG_PATH, DEFAULT_CONFIG),
    )
    stored = deep_merge(stored, read_json(LOCAL_CONFIG_PATH, {}))
    return apply_runtime_defaults(stored)


def save_config(config):
    clean = deepcopy(config)
    clean.pop("discovery", None)
    atomic_write_json(LOCAL_CONFIG_PATH, clean)


def load_state():
    state = deep_merge(DEFAULT_STATE, read_json(STATE_PATH, DEFAULT_STATE))
    if state.get("networkMode") not in MODE_PROFILES:
        state["networkMode"] = "normal"
    return state


def save_state(state):
    atomic_write_json(STATE_PATH, state)


def tail_events(limit=50):
    if not EVENTS_PATH.exists():
        return []
    try:
        lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    items = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(items))


def proxy_url_from_config(config):
    proxy = config.get("proxy", {})
    proxy_type = proxy.get("type", "socks5").lower()
    host = proxy.get("host")
    port = proxy.get("port")
    if not host or not port:
        return None
    if proxy_type == "http":
        return f"http://{host}:{port}"
    if proxy_type in {"socks5", "socks5h"}:
        return f"socks5h://{host}:{port}"
    return f"{proxy_type}://{host}:{port}"


def is_private_ipv4(ip):
    octets = ip.split(".")
    if len(octets) != 4:
        return False
    try:
        first = int(octets[0])
        second = int(octets[1])
    except ValueError:
        return False
    if first == 10:
        return True
    if first == 192 and second == 168:
        return True
    if first == 172 and 16 <= second <= 31:
        return True
    return False


def tcp_check(host, port, timeout_ms):
    if not host or not port:
        return False, "missing_host_or_port"
    try:
        timeout_s = max(timeout_ms / 1000.0, 0.1)
        with socket.create_connection((host, int(port)), timeout=timeout_s):
            return True, None
    except OSError as exc:
        return False, str(exc)


def check_tailscale():
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except FileNotFoundError:
        return {"state": "unknown", "reason": "tailscale_not_installed"}
    except subprocess.TimeoutExpired:
        return {"state": "unknown", "reason": "tailscale_timeout"}

    if result.returncode != 0:
        return {
            "state": "disconnected",
            "reason": (result.stderr or result.stdout or "tailscale_failed").strip(),
        }

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"state": "unknown", "reason": "tailscale_invalid_json"}

    backend_state = payload.get("BackendState", "")
    if backend_state == "Running":
        return {"state": "connected", "backendState": backend_state}
    if backend_state in {"Stopped", "NeedsLogin", "NoState", "Starting"}:
        return {"state": "disconnected", "backendState": backend_state}
    return {"state": "unknown", "backendState": backend_state}


def tailscale_status_payload():
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def detect_local_ipv4():
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("inet "):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ip = parts[1]
        if ip.startswith("127."):
            continue
        if is_private_ipv4(ip):
            return ip
    return None


def detect_mini_host():
    payload = tailscale_status_payload()
    if not payload:
        return None
    peers = payload.get("Peer", {})
    for peer in peers.values():
        hostname = (peer.get("HostName") or "").lower()
        dns_name = (peer.get("DNSName") or "").lower()
        if "mini" in hostname or "mini" in dns_name:
            ips = peer.get("TailscaleIPs") or []
            for ip in ips:
                if ":" not in ip:
                    return ip
    return None


def normalize_config_shape(config):
    config = deepcopy(config)
    profiles = deep_merge(DEFAULT_CONFIG["profiles"], config.get("profiles", {}))
    legacy_mini = config.pop("miniHost", None)
    legacy_proxy = config.pop("proxy", None)

    if legacy_mini or legacy_proxy:
        target_profile = "travel"
        legacy_host = None
        if isinstance(legacy_proxy, dict):
            legacy_host = legacy_proxy.get("host")
        if (legacy_host and is_private_ipv4(legacy_host)) or (
            legacy_mini and is_private_ipv4(legacy_mini)
        ):
            target_profile = "studio"

        if legacy_mini and not profiles[target_profile].get("miniHost"):
            profiles[target_profile]["miniHost"] = legacy_mini
        if isinstance(legacy_proxy, dict):
            profiles[target_profile]["proxy"] = deep_merge(
                profiles[target_profile].get("proxy", {}),
                legacy_proxy,
            )

    config["profiles"] = profiles
    return config


def resolve_profile_name(mode):
    if mode == "travel":
        return "travel"
    return "studio"


def resolved_config_for_mode(config, mode):
    profile_name = resolve_profile_name(mode)
    profile = deep_merge(
        DEFAULT_CONFIG["profiles"][profile_name],
        config.get("profiles", {}).get(profile_name, {}),
    )
    resolved = deepcopy(config)
    resolved["miniHost"] = profile.get("miniHost")
    resolved["proxy"] = profile.get("proxy", {})
    resolved["activeProfileName"] = profile_name
    resolved["activeProfile"] = profile
    return resolved


def apply_runtime_defaults(config):
    config = normalize_config_shape(config)
    discovery = {}
    stored_raw = deep_merge(
        read_json(DEFAULT_CONFIG_PATH, DEFAULT_CONFIG),
        read_json(LOCAL_CONFIG_PATH, {}),
    )
    profiles = config.setdefault("profiles", {})
    studio = profiles.setdefault("studio", deepcopy(DEFAULT_CONFIG["profiles"]["studio"]))
    travel = profiles.setdefault("travel", deepcopy(DEFAULT_CONFIG["profiles"]["travel"]))

    studio_proxy = studio.setdefault("proxy", deepcopy(DEFAULT_CONFIG["profiles"]["studio"]["proxy"]))
    travel_proxy = travel.setdefault("proxy", deepcopy(DEFAULT_CONFIG["profiles"]["travel"]["proxy"]))

    if not studio.get("miniHost") and studio_proxy.get("host") and is_private_ipv4(studio_proxy["host"]):
        studio["miniHost"] = studio_proxy["host"]
        discovery["studioMiniHost"] = studio["miniHost"]
    if not studio_proxy.get("host") and studio.get("miniHost"):
        studio_proxy["host"] = studio["miniHost"]
        discovery["studioProxyHost"] = studio_proxy["host"]
    if not studio_proxy.get("port"):
        studio_proxy["port"] = 6152
        discovery["studioProxyPort"] = 6152
    if not studio_proxy.get("type"):
        studio_proxy["type"] = "http"
        discovery["studioProxyType"] = "http"

    if not travel.get("miniHost"):
        mini_host = detect_mini_host()
        if mini_host:
            travel["miniHost"] = mini_host
            discovery["travelMiniHost"] = mini_host
    if not travel_proxy.get("host") and travel.get("miniHost"):
        travel_proxy["host"] = travel["miniHost"]
        discovery["travelProxyHost"] = travel_proxy["host"]
    if not travel_proxy.get("port"):
        travel_proxy["port"] = 6152
        discovery["travelProxyPort"] = 6152
    if not travel_proxy.get("type"):
        travel_proxy["type"] = "http"
        discovery["travelProxyType"] = "http"

    if not studio.get("miniHost") and not studio_proxy.get("host"):
        local_ip = detect_local_ipv4()
        if local_ip:
            studio["miniHost"] = local_ip
            studio_proxy["host"] = local_ip
            discovery["studioProxyHost"] = local_ip

    if not normalize_config_shape(stored_raw).get("profiles", {}).get("travel", {}).get("miniHost") and travel.get("miniHost"):
        travel_proxy["host"] = travel_proxy.get("host") or travel["miniHost"]

    config["discovery"] = discovery
    return config


def run_curl_json(url, timeout_ms, proxy_url=None):
    max_time = max(int(timeout_ms / 1000), 1)
    connect_timeout = max(min(int(timeout_ms / 1000), 5), 1)
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(max_time),
        "--connect-timeout",
        str(connect_timeout),
        "--header",
        "Accept: application/json",
    ]
    if proxy_url:
        command.extend(["--proxy", proxy_url])
    command.append(url)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max_time + 2,
            check=False,
        )
    except FileNotFoundError:
        return None, "curl_not_installed"
    except subprocess.TimeoutExpired:
        return None, "curl_timeout"

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "curl_failed").strip()
        return None, stderr

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "invalid_json_response"
    return payload, None


def normalize_egress(payload, source):
    country_code = payload.get("countryCode") or payload.get("country_code")
    country_name = payload.get("countryName") or payload.get("country_name")
    city = payload.get("city")
    asn = payload.get("asn") or payload.get("asn_org") or payload.get("org")
    org = payload.get("org") or payload.get("organization")

    if source in {"ipinfo", "ipinfo.io"}:
        country_code = payload.get("country")
        country_name = country_name or payload.get("country_name") or payload.get("country")
        city = payload.get("city")
        asn = payload.get("org") or asn
        org = payload.get("org") or org

    if source in {"ifconfig.co", "ifconfig.co."}:
        country_code = payload.get("country_iso") or country_code
        country_name = payload.get("country") or country_name
        city = payload.get("city") or payload.get("region_name") or city
        asn = payload.get("asn") or asn
        org = payload.get("asn_org") or org

    if source in {"api.ip.sb", "ip.sb"}:
        country_code = payload.get("country_code") or country_code
        country_name = payload.get("country") or country_name
        city = payload.get("city") or payload.get("region") or city
        asn = payload.get("asn") or asn
        org = payload.get("asn_organization") or payload.get("organization") or org

    return {
        "ip": payload.get("ip"),
        "countryCode": country_code,
        "country": country_name or payload.get("country_name") or payload.get("country"),
        "city": city,
        "asn": asn,
        "org": org,
        "source": source,
    }


def fetch_egress(config, proxy_url=None, budget_ms=None):
    endpoints = list(config.get("verifyEndpoints", []))
    if not endpoints:
        return None, "no_verify_endpoint"

    timeout_ms = config.get("timeouts", {}).get("httpMs", 5000)
    budget_ms = budget_ms or timeout_ms
    per_endpoint_budget = max(int(budget_ms / max(len(endpoints), 1)), 1000)
    started_at = time.monotonic()
    last_error = "no_verify_endpoint"

    for endpoint in endpoints:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        remaining_ms = budget_ms - elapsed_ms
        if remaining_ms <= 0:
            return None, "verify_budget_exhausted"
        attempt_timeout_ms = max(min(timeout_ms, remaining_ms, per_endpoint_budget), 1000)
        payload, error = run_curl_json(endpoint, attempt_timeout_ms, proxy_url=proxy_url)
        if error:
            last_error = error
            continue
        source = urlparse(endpoint).netloc.split(":")[0]
        normalized = normalize_egress(payload, source)
        if normalized.get("ip"):
            return normalized, None
        last_error = "missing_ip_field"
    return None, last_error


def proxy_command_hint():
    return f"source {DEV_PROXY_ENV_PATH}"


def write_dev_proxy_files(config):
    proxy_url = proxy_url_from_config(config)
    env_lines = [
        "# Generated by Network Workflow Console",
        "# This is a recommended proxy template for new shells.",
    ]
    if proxy_url:
        env_lines.extend(
            [
                f"export HTTP_PROXY='{proxy_url}'",
                f"export HTTPS_PROXY='{proxy_url}'",
                f"export ALL_PROXY='{proxy_url}'",
            ]
        )
    no_proxy_values = list(config.get("noProxy", []))
    private_hints = config.get("privateNetworksHint", [])
    if no_proxy_values:
        env_lines.append(f"export NO_PROXY='{','.join(no_proxy_values)}'")
    if private_hints:
        env_lines.append(
            "# Private network CIDR compatibility varies across tools: "
            + ", ".join(private_hints)
        )
    env_lines.append("")
    DEV_PROXY_DIR.mkdir(parents=True, exist_ok=True)
    DEV_PROXY_ENV_PATH.write_text("\n".join(env_lines), encoding="utf-8")

    shell_lines = [
        "#!/bin/zsh",
        f"source '{DEV_PROXY_ENV_PATH}'",
        'exec "${SHELL:-/bin/zsh}" -i',
        "",
    ]
    DEV_PROXY_SHELL_PATH.write_text("\n".join(shell_lines), encoding="utf-8")
    DEV_PROXY_SHELL_PATH.chmod(0o755)
    return {
        "envPath": str(DEV_PROXY_ENV_PATH),
        "shellPath": str(DEV_PROXY_SHELL_PATH),
        "command": proxy_command_hint(),
    }


def remove_dev_proxy_files():
    for path in (DEV_PROXY_ENV_PATH, DEV_PROXY_SHELL_PATH):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def summary_for_level(level, context=None):
    if level == "green":
        return "稳定模式：日本（mini）"
    if level == "yellow":
        return "可用，但未完全确认"
    if level == "fallback":
        return "当前为 fallback 模式，请避免关键账号操作"
    if level == "red" and context:
        return f"链路异常：{context}"
    if level == "red":
        return "链路异常"
    return "未验证"


def summary_for_direct_mode(direct_egress, expected_region):
    if not direct_egress:
        return "链路异常：直连出口探测失败"
    country_code = direct_egress.get("countryCode") or "unknown"
    if country_code == expected_region:
        return f"直连模式：出口 {country_code}"
    return f"直连模式：出口 {country_code}（非预期地区）"


def build_verify_result(state, config):
    mode = state.get("networkMode", "normal")
    resolved = resolved_config_for_mode(config, mode)
    timeout_ms = config.get("timeouts", {}).get("tcpMs", 1500)
    verify_total_ms = config.get("timeouts", {}).get("verifyTotalMs", 10000)

    tailscale = check_tailscale()
    mini_host = resolved.get("miniHost")
    proxy = resolved.get("proxy", {})
    proxy_host = proxy.get("host")
    proxy_port = proxy.get("port")
    proxy_type = proxy.get("type", "socks5")
    proxy_url = proxy_url_from_config(resolved)

    mini_ok, mini_error = tcp_check(mini_host, proxy_port or 22, timeout_ms) if mini_host else (False, "missing_mini_host")
    proxy_ok, proxy_error = tcp_check(proxy_host, proxy_port, timeout_ms)

    direct_budget = verify_total_ms if not proxy_url else max(int(verify_total_ms / 2), 1000)
    proxy_budget = max(verify_total_ms - direct_budget, 1000) if proxy_url else 0

    direct_egress, direct_error = fetch_egress(
        resolved,
        proxy_url=None,
        budget_ms=direct_budget,
    )
    proxied_egress = None
    proxied_error = None
    if proxy_url and mode != "studio_direct":
        proxied_egress, proxied_error = fetch_egress(
            resolved,
            proxy_url=proxy_url,
            budget_ms=proxy_budget,
        )
    elif mode != "studio_direct":
        proxied_error = "missing_proxy_config"

    upstream_ok = proxied_egress is not None
    expected_region = config.get("expectedRegion")
    expected_region_ok = bool(
        proxied_egress and proxied_egress.get("countryCode") == expected_region
    )

    if mode == "studio_direct":
        direct_region_ok = bool(
            direct_egress and direct_egress.get("countryCode") == expected_region
        )
        checks = [
            {"key": "directEgressAvailable", "ok": direct_egress is not None},
            {"key": "directRegionMatched", "ok": direct_region_ok},
            {"key": "proxyBypassed", "ok": True},
        ]
    else:
        checks = [
            {"key": "tailscaleConnected", "ok": tailscale.get("state") == "connected"},
            {"key": "miniReachable", "ok": mini_ok},
            {"key": "proxyReachable", "ok": proxy_ok},
            {"key": "upstreamReachableViaProxy", "ok": upstream_ok},
            {"key": "expectedRegionMatched", "ok": expected_region_ok},
        ]

    level = "unknown"
    context = None
    if mode == "fallback":
        level = "fallback"
    elif mode == "studio_direct":
        if direct_egress:
            level = "yellow"
        else:
            level = "red"
            context = "直连出口探测失败"
    elif mode in {"studio", "travel"}:
        if mode == "travel" and tailscale.get("state") != "connected":
            level = "red"
            context = "Tailscale 未连接"
        elif not mini_ok:
            level = "red"
            context = "mini 不可达"
        elif not proxy_ok:
            level = "red"
            context = "代理端口不可用"
        elif not upstream_ok:
            level = "red"
            context = "代理上游探测失败"
        elif not expected_region_ok:
            level = "red"
            context = f"当前出口地区不是 {expected_region}"
        else:
            level = "green"
    elif mode == "normal":
        if direct_egress:
            level = "yellow"
        else:
            level = "unknown"

    critical_ops = "avoid"
    if level == "green":
        critical_ops = "allow"
    elif level == "yellow":
        critical_ops = "caution"
    elif level == "unknown" and mode == "normal":
        critical_ops = "caution"

    errors = {}
    if mini_error and mode in {"studio", "travel"}:
        errors["mini"] = mini_error
    if proxy_error and mode in {"studio", "travel"}:
        errors["proxy"] = proxy_error
    if direct_error:
        errors["directEgress"] = direct_error
    if proxied_error and mode in {"studio", "travel"}:
        errors["proxiedEgress"] = proxied_error

    summary = summary_for_level(level, context=context)
    if mode == "studio_direct":
        summary = summary_for_direct_mode(direct_egress, expected_region)

    return {
        "ok": level in {"green", "yellow", "fallback"},
        "level": level,
        "summary": summary,
        "networkMode": mode,
        "connectionProfile": resolved.get("activeProfileName"),
        "criticalOpsRecommendation": critical_ops,
        "tailscale": tailscale,
        "mini": {
            "reachable": mini_ok,
            "host": mini_host,
            "error": mini_error,
        },
        "proxy": {
            "reachable": proxy_ok,
            "type": proxy_type,
            "host": proxy_host,
            "port": proxy_port,
            "error": proxy_error,
        },
        "directEgress": direct_egress,
        "proxiedEgress": proxied_egress,
        "checks": checks,
        "errors": errors,
        "lastVerifiedAt": now_iso(),
    }


def apply_mode(mode, state, config):
    profile = MODE_PROFILES[mode]
    state["networkMode"] = mode
    state["devProxyPolicy"] = profile["devProxyPolicy"]
    state["devProxySession"] = profile["devProxySession"]
    state["criticalOpsRecommendation"] = profile["criticalOpsRecommendation"]
    state["expectedRegion"] = config.get("expectedRegion", state.get("expectedRegion"))
    state["lastModeChangeAt"] = now_iso()

    dev_proxy_files = None
    if mode in {"studio", "travel"}:
        dev_proxy_files = write_dev_proxy_files(resolved_config_for_mode(config, mode))
    else:
        remove_dev_proxy_files()
    return state, dev_proxy_files


def current_status_payload():
    config = load_config()
    state = load_state()
    resolved = resolved_config_for_mode(config, state.get("networkMode", "normal"))
    tailscale = check_tailscale()
    proxy = resolved.get("proxy", {})
    route_mode = "proxy" if state.get("networkMode") in {"studio", "travel"} else "direct"
    proxy_ok, _ = tcp_check(proxy.get("host"), proxy.get("port"), config.get("timeouts", {}).get("tcpMs", 1500))
    mini_port = proxy.get("port") or 22
    mini_ok, _ = tcp_check(resolved.get("miniHost"), mini_port, config.get("timeouts", {}).get("tcpMs", 1500)) if resolved.get("miniHost") else (False, "missing_mini_host")
    verification = state.get("lastVerification")
    level = state.get("lastVerifyLevel", "unknown")
    summary = summary_for_level(level)
    if verification and verification.get("summary"):
        summary = verification["summary"]

    return {
        "networkMode": state.get("networkMode"),
        "summary": summary,
        "devProxyPolicy": state.get("devProxyPolicy"),
        "devProxySession": state.get("devProxySession"),
        "criticalOpsRecommendation": state.get("criticalOpsRecommendation"),
        "routeMode": route_mode,
        "browserNotice": "浏览器代理不由本系统直接管理",
        "connectionProfile": resolved.get("activeProfileName"),
        "tailscale": tailscale,
        "mini": {
            "reachable": mini_ok if route_mode == "proxy" else None,
            "host": resolved.get("miniHost"),
        },
        "proxy": {
            "reachable": proxy_ok if route_mode == "proxy" else None,
            "type": proxy.get("type"),
            "host": proxy.get("host"),
            "port": proxy.get("port"),
            "active": route_mode == "proxy",
        },
        "profiles": config.get("profiles", {}),
        "devProxyFiles": {
            "envPath": str(DEV_PROXY_ENV_PATH),
            "shellPath": str(DEV_PROXY_SHELL_PATH),
            "command": proxy_command_hint(),
            "available": DEV_PROXY_ENV_PATH.exists() and DEV_PROXY_SHELL_PATH.exists(),
        },
        "lastVerification": verification,
        "lastModeChangeAt": state.get("lastModeChangeAt"),
        "lastVerifyAt": state.get("lastVerifyAt"),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "NetworkWorkflowConsole/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/status":
            return self.send_json(HTTPStatus.OK, current_status_payload())
        if path == "/api/app-control/status":
            return self.send_json(HTTPStatus.OK, app_control_status_payload())
        if path == "/api/logs":
            return self.send_json(HTTPStatus.OK, {"items": tail_events(50)})
        if path == "/api/config":
            return self.send_json(HTTPStatus.OK, load_config())
        if path == "/" or path == "/index.html":
            return self.serve_file(WEB_DIR / "index.html")
        if path == "/app.css":
            return self.serve_file(WEB_DIR / "app.css")
        if path == "/app.js":
            return self.serve_file(WEB_DIR / "app.js")
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self.is_local_request():
            return self.send_json(
                HTTPStatus.FORBIDDEN,
                {
                    "ok": False,
                    "error": "forbidden_origin",
                    "message": "请求来源不被允许",
                },
            )

        payload = self.read_json_body()
        if payload is None and self.headers.get("Content-Length") not in (None, "0"):
            return self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "invalid_json", "message": "请求体不是合法 JSON"},
            )

        if path == "/api/verify":
            return self.handle_verify()
        if path == "/api/app-control/action":
            return self.handle_app_control_action(payload or {})
        if path.startswith("/api/mode/"):
            return self.handle_mode_change(path.rsplit("/", 1)[-1])
        if path == "/api/config":
            return self.handle_config_update(payload or {})
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def serve_file(self, path):
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def is_local_request(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        allowed_hosts = {
            f"127.0.0.1:{self.server.server_address[1]}",
            f"localhost:{self.server.server_address[1]}",
        }
        host_ok = not host or host in allowed_hosts
        origin_ok = True
        if origin:
            origin_ok = origin in {
                f"http://127.0.0.1:{self.server.server_address[1]}",
                f"http://localhost:{self.server.server_address[1]}",
            }
        return host_ok and origin_ok

    def handle_verify(self):
        with STATE_LOCK:
            state = load_state()
            config = load_config()
            result = build_verify_result(state, config)
            state["lastVerifyAt"] = result["lastVerifiedAt"]
            state["lastVerifyLevel"] = result["level"]
            state["criticalOpsRecommendation"] = result["criticalOpsRecommendation"]
            state["lastVerification"] = result
            save_state(state)
        append_event(
            {
                "type": "verify",
                "networkMode": state.get("networkMode"),
                "ok": result["ok"],
                "result": result["level"],
                "summary": result["summary"],
            }
        )
        return self.send_json(HTTPStatus.OK, result)

    def handle_mode_change(self, mode):
        if mode not in MODE_PROFILES:
            return self.send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "invalid_mode",
                    "message": "不支持的模式",
                },
            )

        config = load_config()
        if mode == "travel":
            tailscale = check_tailscale()
            if tailscale.get("state") != "connected":
                return self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": "tailscale_not_connected",
                        "message": "Tailscale 未连接，无法进入外出模式",
                    },
                )
            resolved = resolved_config_for_mode(config, mode)
            proxy = resolved.get("proxy", {})
            mini_ok, _ = tcp_check(
                resolved.get("miniHost"),
                proxy.get("port") or 22,
                config.get("timeouts", {}).get("tcpMs", 1500),
            )
            if not mini_ok:
                return self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": "mini_unreachable",
                        "message": "已检测到 Tailscale，但无法连接到 mini",
                    },
                )
            proxy_ok, _ = tcp_check(
                proxy.get("host"),
                proxy.get("port"),
                config.get("timeouts", {}).get("tcpMs", 1500),
            )
            if not proxy_ok:
                return self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": "proxy_unreachable",
                        "message": "mini 在线，但代理端口不可用",
                    },
                )

        with STATE_LOCK:
            state = load_state()
            state, dev_proxy_files = apply_mode(mode, state, config)
            save_state(state)

        append_event(
            {
                "type": "mode_change",
                "networkMode": mode,
                "ok": True,
                "summary": f"模式已切换到 {mode}",
            }
        )
        if dev_proxy_files:
            append_event(
                {
                    "type": "dev_proxy_prepare",
                    "networkMode": mode,
                    "ok": True,
                    "summary": "开发代理模板已生成",
                }
            )
        return self.send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "networkMode": mode,
                "devProxyFiles": dev_proxy_files,
                "status": current_status_payload(),
            },
        )

    def handle_app_control_action(self, payload):
        action = payload.get("action")
        if action not in {"gui_proxy_enable", "gui_proxy_disable", "console_stop"}:
            return self.send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "invalid_action",
                    "message": "不支持的应用控制动作",
                },
            )

        if action == "gui_proxy_enable":
            profile = payload.get("profile", "")
            ok, output = run_local_script(GUI_PROXY_ENABLE_SCRIPT, profile)
            status = app_control_status_payload()
            append_event(
                {
                    "type": "app_control",
                    "ok": ok,
                    "summary": "GUI 代理已注入并请求重启应用" if ok else "GUI 代理注入失败",
                }
            )
            return self.send_json(
                HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                {
                    "ok": ok,
                    "message": "GUI 代理已注入，Codex 和 Antigravity 正在重启" if ok else "GUI 代理注入失败",
                    "output": output,
                    "status": status,
                },
            )

        if action == "gui_proxy_disable":
            ok, output = run_local_script(GUI_PROXY_DISABLE_SCRIPT)
            status = app_control_status_payload()
            append_event(
                {
                    "type": "app_control",
                    "ok": ok,
                    "summary": "GUI 代理环境已清理并请求重启应用" if ok else "GUI 代理环境清理失败",
                }
            )
            return self.send_json(
                HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                {
                    "ok": ok,
                    "message": "GUI 代理环境已清理，Codex 和 Antigravity 正在重启" if ok else "GUI 代理环境清理失败",
                    "output": output,
                    "status": status,
                },
            )

        def delayed_stop():
            time.sleep(0.8)
            subprocess.run([str(STOP_CONSOLE_SCRIPT)], capture_output=True, text=True, timeout=10, check=False)

        threading.Thread(target=delayed_stop, daemon=True).start()
        append_event(
            {
                "type": "app_control",
                "ok": True,
                "summary": "控制台服务即将停止",
            }
        )
        return self.send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "message": "控制台服务即将停止，请用桌面启动器重新打开",
                "status": app_control_status_payload(),
            },
        )

    def handle_config_update(self, payload):
        config = load_config()
        try:
            merged = normalize_config_shape(deep_merge(config, payload))
            for profile_name in ("studio", "travel"):
                profile = merged.get("profiles", {}).get(profile_name, {})
                proxy = profile.get("proxy", {})
                proxy_port = int(proxy.get("port", 0))
                if proxy_port <= 0:
                    raise ValueError(f"{profile_name}.proxy.port must be positive")
                proxy["port"] = proxy_port
                if proxy.get("type") not in {"http", "socks5", "socks5h"}:
                    raise ValueError(f"{profile_name}.proxy.type invalid")
                merged["profiles"][profile_name]["proxy"] = proxy
        except (ValueError, TypeError, KeyError):
            return self.send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "config_invalid",
                    "message": "配置不合法，请检查代理端口和字段格式",
                },
            )

        with STATE_LOCK:
            save_config(merged)
            state = load_state()
            state["expectedRegion"] = merged.get("expectedRegion", state.get("expectedRegion"))
            save_state(state)

        append_event(
            {
                "type": "config_update",
                "ok": True,
                "summary": "配置已更新",
            }
        )
        return self.send_json(HTTPStatus.OK, {"ok": True, "config": merged})

    def log_message(self, format, *args):
        sys.stdout.write(
            "%s - - [%s] %s\n"
            % (
                self.address_string(),
                self.log_date_time_string(),
                format % args,
            )
        )


def main():
    parser = argparse.ArgumentParser(description="Network Workflow Console local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()

    ensure_dirs()
    write_pid()
    atexit.register(remove_pid)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Network Workflow Console running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
