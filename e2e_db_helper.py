"""
E2E Test Database Helper for Browser Tests
Reads only from sih_hospital_phase1_run_test
"""

import sys
import json
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.pg_models import VerificationToken, RegistrationEmailOutbox, RegistrationApplication

DB_URL = "postgresql://localhost:5432/sih_hospital_phase1_run_test"
assert "sih_hospital_dev" not in DB_URL
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def get_otp(target: str) -> str:
    session = Session()
    try:
        tok = (
            session.query(VerificationToken)
            .filter(VerificationToken.contact_target.ilike(target.strip()))
            .order_by(VerificationToken.id.desc())
            .first()
        )
        if not tok:
            print("NOT_FOUND", file=sys.stderr)
            sys.exit(1)
        h = tok.token_hash
        for i in range(100000, 1000000):
            if hashlib.sha256(str(i).encode()).hexdigest() == h:
                return str(i)
        sys.exit(1)
    finally:
        session.close()

def get_activation_token(email: str) -> str:
    session = Session()
    try:
        outbox = (
            session.query(RegistrationEmailOutbox)
            .filter(
                RegistrationEmailOutbox.recipient_email.ilike(email.strip()),
                RegistrationEmailOutbox.event_type == "ACCOUNT_ACTIVATION",
            )
            .order_by(RegistrationEmailOutbox.id.desc())
            .first()
        )
        if not outbox:
            sys.exit(1)
        data = json.loads(outbox.payload)
        return data["raw_token"]
    finally:
        session.close()

def get_reset_token(email: str) -> str:
    session = Session()
    try:
        outbox = (
            session.query(RegistrationEmailOutbox)
            .filter(
                RegistrationEmailOutbox.recipient_email.ilike(email.strip()),
                RegistrationEmailOutbox.event_type == "PASSWORD_RESET",
            )
            .order_by(RegistrationEmailOutbox.id.desc())
            .first()
        )
        if not outbox:
            sys.exit(1)
        data = json.loads(outbox.payload)
        return data["raw_token"]
    finally:
        session.close()

def get_tracking_token(app_number: str) -> str:
    session = Session()
    try:
        app = (
            session.query(RegistrationApplication)
            .filter(RegistrationApplication.application_number == app_number.strip())
            .first()
        )
        if not app or not app.tracking_tokens:
            sys.exit(1)
        # return newest tracking token
        return app.tracking_tokens[-1].token_hash  # Wait, tracking token is stored raw in tracking_token on app or tracking_tokens table
    finally:
        session.close()

if __name__ == "__main__":
    cmd = sys.argv[1]
    arg = sys.argv[2]
    if cmd == "get-otp":
        print(get_otp(arg))
    elif cmd == "get-activation-token":
        print(get_activation_token(arg))
    elif cmd == "get-reset-token":
        print(get_reset_token(arg))
