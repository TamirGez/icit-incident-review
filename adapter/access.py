"""Read-only, assigned-host-only Tailscale checks. Never reconfigure networking."""
import json
import socket
import subprocess


def lab_access():
    result = {"reachable": False, "assigned_host": "p042"}
    try:
        proc = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                              text=True, timeout=10)
        if proc.returncode:
            result["blocker"] = "tailscale_status_unavailable"
            return result
        state = json.loads(proc.stdout)
        result["backend"] = state.get("BackendState")
        result["tailnet"] = (state.get("CurrentTailnet") or {}).get("Name")
        peers = [p for p in (state.get("Peer") or {}).values()
                 if p.get("HostName", "").lower() == "p042"]
        if len(peers) != 1 or state.get("BackendState") != "Running":
            result["blocker"] = "assigned_peer_not_visible"
            return result
        peer = peers[0]
        result["peer_online"] = peer.get("Online", False)
        if not result["peer_online"]:
            result["blocker"] = "assigned_peer_offline"
            return result
        resolved = {r[4][0] for r in socket.getaddrinfo("p042", None)}
        if not resolved or not resolved.issubset(set(peer.get("TailscaleIPs", []))):
            result["blocker"] = "assigned_peer_dns_mismatch"
            return result
        result["reachable"] = True
        return result
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        result["blocker"] = "local_access_check_failed"
        return result
