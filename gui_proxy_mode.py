#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "default.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "local.json"
STATE_PATH = ROOT / "data" / "state.json"


def read_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def deep_merge(base, overlay):
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_profile(mode):
    return "travel" if mode == "travel" else "studio"


def proxy_url(profile):
    proxy = profile.get("proxy", {})
    proxy_type = proxy.get("type", "http")
    host = proxy.get("host")
    port = proxy.get("port")
    if not host or not port:
        raise SystemExit("proxy host/port missing")
    if proxy_type == "http":
        return f"http://{host}:{port}"
    if proxy_type in {"socks5", "socks5h"}:
        return f"socks5h://{host}:{port}"
    return f"{proxy_type}://{host}:{port}"


def main():
    forced_profile = sys.argv[1] if len(sys.argv) > 1 else ""
    config = deep_merge(read_json(DEFAULT_CONFIG_PATH), read_json(LOCAL_CONFIG_PATH))
    state = read_json(STATE_PATH)
    active_mode = state.get("networkMode", "studio")
    profile_name = forced_profile or resolve_profile(active_mode)
    profiles = config.get("profiles", {})
    profile = profiles.get(profile_name)
    if not profile:
        raise SystemExit(f"profile not found: {profile_name}")

    proxy = proxy_url(profile)
    no_proxy = ",".join(config.get("noProxy", ["localhost", "127.0.0.1", "::1", ".local"]))

    print(proxy)
    print(no_proxy)


if __name__ == "__main__":
    main()
