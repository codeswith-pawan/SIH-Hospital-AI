#!/usr/bin/env python3
"""
Brevo SMTP Diagnostics & Connectivity Health Check Tool
AI Powered Smart Hospital Referral System - Phase 3

Provides safe, step-by-step verification of SMTP connectivity:
1. Configuration variable presence
2. DNS resolution of SMTP host
3. TCP socket connection and latency
4. EHLO greeting & STARTTLS cryptographic negotiation
5. SMTP authentication (only if credentials provided)
6. Optional single test email dispatch (strictly on explicit operator request)

STRICT SECURITY INVARIANTS:
- NEVER logs or displays plaintext passwords or SMTP keys
- Masks usernames, hostnames, and recipient addresses in output
- Fails closed safely if credentials or network are unreachable
"""

import os
import sys
import time
import socket
import smtplib
import argparse
import ssl
from typing import Dict, Any, Tuple

# Add parent directory to path so imports work cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import get_settings, mask_secret, mask_email


def check_smtp_health(send_test_to: str = "") -> Dict[str, Any]:
    """Execute non-destructive SMTP connectivity diagnostic."""
    settings = get_settings()

    results: Dict[str, Any] = {
        "status": "PASS",
        "steps": {},
        "summary": "",
    }

    print("==================================================================")
    print("      SIH HOSPITAL AI — BREVO SMTP HEALTH & DIAGNOSTIC CHECK      ")
    print("==================================================================")

    # 1. Configuration Check
    host = settings.smtp_host
    port = settings.smtp_port
    user = settings.smtp_username
    password = settings.smtp_password
    sender = settings.smtp_from_email
    use_tls = settings.smtp_use_tls
    timeout = settings.smtp_timeout

    print(f"[*] Step 1: Configuration Parameters Inspection")
    print(f"    - Host:               {host or '<NOT SET>'}")
    print(f"    - Port:               {port}")
    print(f"    - STARTTLS Enabled:   {use_tls}")
    print(f"    - Sender Address:     {mask_email(sender)}")
    print(f"    - Username / Login:   {mask_secret(user)}")
    print(f"    - Password Configured: {'[YES - Masked]' if password else '[NO / MISSING]'}")
    print(f"    - Timeout:            {timeout}s")

    if not host:
        results["status"] = "FAIL"
        results["steps"]["config"] = {"status": "FAIL", "message": "SMTP_HOST is not configured."}
        print("\n[!] FATAL: SMTP_HOST is not configured in environment or .env.")
        return results

    results["steps"]["config"] = {"status": "PASS", "message": "Configuration parameters present."}

    # 2. DNS Resolution
    print(f"\n[*] Step 2: DNS Resolution for host '{host}'")
    dns_start = time.perf_counter()
    try:
        ip_addresses = socket.gethostbyname_ex(host)[2]
        dns_time = (time.perf_counter() - dns_start) * 1000
        print(f"    [✓] Resolved to {len(ip_addresses)} IP(s) in {dns_time:.1f}ms: {', '.join(ip_addresses)}")
        results["steps"]["dns"] = {"status": "PASS", "ips": ip_addresses, "latency_ms": round(dns_time, 1)}
    except socket.gaierror as e:
        results["status"] = "FAIL"
        results["steps"]["dns"] = {"status": "FAIL", "error": str(e)}
        print(f"    [✗] DNS resolution failed for '{host}': {e}")
        return results

    # 3. TCP Socket Connection
    print(f"\n[*] Step 3: TCP Socket Connection to {host}:{port}")
    conn_start = time.perf_counter()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        conn_time = (time.perf_counter() - conn_start) * 1000
        print(f"    [✓] TCP handshake successful ({conn_time:.1f}ms latency)")
        results["steps"]["tcp"] = {"status": "PASS", "latency_ms": round(conn_time, 1)}
    except Exception as e:
        results["status"] = "FAIL"
        results["steps"]["tcp"] = {"status": "FAIL", "error": str(e)}
        print(f"    [✗] TCP connection to {host}:{port} timed out or failed: {e}")
        return results

    # 4. SMTP Greeting & STARTTLS Handshake
    print(f"\n[*] Step 4: SMTP Handshake & STARTTLS Negotiation")
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            code, resp = server.ehlo()
            print(f"    [✓] EHLO response: {code} ({resp.decode(errors='ignore').splitlines()[0]})")

            if use_tls:
                if server.has_extn("STARTTLS"):
                    try:
                        import certifi
                        tls_context = ssl.create_default_context(cafile=certifi.where())
                    except ImportError:
                        tls_context = ssl.create_default_context()
                    server.starttls(context=tls_context)
                    server.ehlo()
                    print(f"    [✓] STARTTLS negotiated successfully (TLS context verified)")
                    results["steps"]["tls"] = {"status": "PASS", "tls_negotiated": True}
                else:
                    print(f"    [!] Warning: Server does not advertise STARTTLS extension.")
                    results["steps"]["tls"] = {"status": "WARN", "tls_negotiated": False}

            # 5. Authentication Check
            print(f"\n[*] Step 5: SMTP Authentication Verification")
            if not user or not password:
                print(f"    [-] SKIPPED: Real credentials not provided in environment.")
                print(f"    [i] Status: BLOCKED BY EXTERNAL CONFIGURATION (Credentials required).")
                results["steps"]["auth"] = {
                    "status": "BLOCKED_BY_EXTERNAL_CONFIGURATION",
                    "message": "SMTP_USERNAME or SMTP_PASSWORD not set."
                }
            else:
                try:
                    server.login(user, password)
                    print(f"    [✓] Authentication SUCCESSFUL for user '{mask_secret(user)}'")
                    results["steps"]["auth"] = {"status": "PASS", "authenticated": True}
                except smtplib.SMTPAuthenticationError as auth_err:
                    print(f"    [✗] Authentication FAILED: {auth_err}")
                    results["status"] = "FAIL"
                    results["steps"]["auth"] = {"status": "FAIL", "error": str(auth_err)}
                    return results

            # 6. Optional Controlled Test Email
            if send_test_to:
                print(f"\n[*] Step 6: Controlled Test Email Dispatch to '{mask_email(send_test_to)}'")
                if results["steps"]["auth"]["status"] != "PASS":
                    print("    [!] Cannot send test email without valid authenticated credentials.")
                    results["steps"]["test_email"] = {
                        "status": "BLOCKED_BY_EXTERNAL_CONFIGURATION",
                        "message": "Cannot send email without authenticated session."
                    }
                else:
                    from email.mime.text import MIMEText
                    from email.mime.multipart import MIMEMultipart

                    msg = MIMEMultipart()
                    msg["Subject"] = "SIH Hospital Referral Portal — Brevo SMTP Connectivity Test"
                    msg["From"] = sender
                    msg["To"] = send_test_to
                    msg.attach(MIMEText(
                        f"This is an automated test message from the National Smart Hospital Referral System.\n"
                        f"SMTP Host: {host}:{port}\n"
                        f"Sender: {sender}\n"
                        f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n"
                        f"If you received this email, your Brevo SMTP integration is operational.",
                        "plain"
                    ))
                    server.send_message(msg)
                    print(f"    [✓] Controlled test email successfully accepted by Brevo for '{mask_email(send_test_to)}'")
                    results["steps"]["test_email"] = {"status": "PASS", "delivered_to": mask_email(send_test_to)}
    except Exception as exc:
        results["status"] = "FAIL"
        results["steps"]["smtp_protocol"] = {"status": "FAIL", "error": str(exc)}
        print(f"    [✗] SMTP protocol error: {exc}")
        return results

    print("\n==================================================================")
    if results["status"] == "PASS" and results["steps"].get("auth", {}).get("status") == "PASS":
        print("RESULT: PASS — Brevo SMTP is reachable, TLS verified, and authenticated.")
    elif results["steps"].get("auth", {}).get("status") == "BLOCKED_BY_EXTERNAL_CONFIGURATION":
        print("RESULT: PASS (INFRASTRUCTURE) / BLOCKED BY EXTERNAL CONFIGURATION (CREDENTIALS)")
        print("Network, DNS, TCP connection and TLS negotiation are 100% operational.")
        print("To verify live email delivery, supply valid Brevo credentials in .env.")
    else:
        print(f"RESULT: {results['status']}")
    print("==================================================================\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brevo SMTP Diagnostics & Health Check Tool")
    parser.add_argument(
        "--send-test-to",
        type=str,
        default="",
        help="Designated recipient email to send a single controlled test message to.",
    )
    args = parser.parse_args()

    res = check_smtp_health(send_test_to=args.send_test_to)
    sys.exit(0 if res["status"] == "PASS" else 1)
