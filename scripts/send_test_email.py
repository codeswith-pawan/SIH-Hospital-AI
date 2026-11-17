#!/usr/bin/env python3
"""
Controlled Operator Test Email Dispatch Tool
AI Powered Smart Hospital Referral System - Phase 3

Sends a single, explicitly requested test notification message via the
configured email provider (SMTPEmailProvider or SimulatedEmailProvider).

STRICT RULES:
- Requires explicit destination email flag (--to <email>)
- Refuses to run without a valid email syntax
- Never sends unsolicited or batch messages
- Masks email addresses and secrets in logs
"""

import os
import sys
import re
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.email_service import get_email_provider, EmailDeliveryError
from src.config import get_settings, mask_email


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_controlled_test_email(to_email: str) -> bool:
    if not to_email or not EMAIL_REGEX.match(to_email.strip()):
        print(f"[!] Invalid destination email address: '{to_email}'")
        return False

    target = to_email.strip()
    settings = get_settings()
    provider = get_email_provider()

    masked_target = mask_email(target)
    print(f"[*] Initiating controlled test email...")
    print(f"    - Recipient: {masked_target}")
    print(f"    - Provider:  {type(provider).__name__}")
    print(f"    - Backend:   {settings.email_backend}")

    subject = "National Smart Hospital Referral System — Operational Email Verification"
    body_text = f"""Dear Operator,

This is a controlled operational test message sent from the SIH Hospital AI platform.

Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
Backend: {settings.email_backend}
SMTP Host: {settings.smtp_host or 'N/A (Simulated)'}

If you received this message, the email subsystem is operating correctly.

Regards,
National Smart Hospital Referral System
Government of India
"""

    try:
        success = provider.send_email(
            to_email=target,
            subject=subject,
            body_text=body_text,
        )
        if success:
            print(f"[✓] SUCCESS: Test email accepted for delivery to {masked_target}.")
            return True
        else:
            print(f"[✗] FAILURE: Provider returned False for {masked_target}.")
            return False
    except EmailDeliveryError as exc:
        print(f"[✗] DELIVERY ERROR: {exc}")
        return False
    except Exception as exc:
        print(f"[✗] UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send single controlled test email")
    parser.add_argument("--to", required=True, type=str, help="Recipient email address")
    args = parser.parse_args()

    ok = send_controlled_test_email(args.to)
    sys.exit(0 if ok else 1)
