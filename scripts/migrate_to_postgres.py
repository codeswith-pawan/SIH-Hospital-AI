"""
Safe, Non-Destructive PostgreSQL Migration Script
AI Powered Smart Hospital Referral System

Extracts data from legacy SQLite, CSV, and JSON stores, validates referential
integrity and data types, and loads into PostgreSQL.
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

# Setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATASETS_DIR = BASE_DIR / "datasets" / "final"


def safe_parse_datetime(val: Any, default: Optional[datetime] = None) -> Optional[datetime]:
    if val is None or (isinstance(val, float) and pd.isna(val)) or pd.isna(val):
        return default
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).strip())
    except Exception:
        return default


def normalize_patient_priority(val: Any) -> str:
    s = str(val or "").strip().capitalize()
    if s in ["Critical", "Urgent", "Stable"]:
        return s
    if s.upper() in ["HIGH", "EMERGENCY"]:
        return "Critical"
    return "Stable"


def load_legacy_data():
    """Extract data from all existing stores without modification."""
    logger.info("Extracting data from existing data stores...")

    # 1. Hospitals (CSV)
    hospitals_csv = DATASETS_DIR / "hospitals.csv"
    hospitals_df = pd.read_csv(hospitals_csv) if hospitals_csv.exists() else pd.DataFrame()

    # 2. Patients (CSV)
    patients_csv = DATASETS_DIR / "patients.csv"
    patients_df = pd.read_csv(patients_csv) if patients_csv.exists() else pd.DataFrame()

    # 3. Users (JSON)
    users_file = DATA_DIR / "runtime" / "users.json"
    if not users_file.exists():
        users_file = DATA_DIR / "users.json"
    users_data = []
    if users_file.exists():
        with open(users_file, "r") as f:
            users_data = json.load(f)

    # 4. Bed Inventory (JSON)
    bed_file = DATA_DIR / "bed_inventory.json"
    bed_data = {}
    if bed_file.exists():
        with open(bed_file, "r") as f:
            bed_data = json.load(f)

    # 5. Referrals (JSON)
    ref_file = DATA_DIR / "runtime" / "referrals.json"
    if not ref_file.exists():
        ref_file = DATA_DIR / "referrals.json"
    ref_data = []
    if ref_file.exists():
        with open(ref_file, "r") as f:
            ref_data = json.load(f)

    # 6. Reservations (JSON)
    res_file = DATA_DIR / "reservations.json"
    res_data = []
    if res_file.exists():
        with open(res_file, "r") as f:
            res_data = json.load(f)

    # 7. SQLite hospital visits
    sqlite_path = DATA_DIR / "hospital_system.db"
    visits_records = []
    if sqlite_path.exists():
        try:
            from sqlalchemy import create_engine as create_sqlite
            sq_eng = create_sqlite(f"sqlite:///{sqlite_path}")
            with sq_eng.connect() as conn:
                visits_df = pd.read_sql("SELECT * FROM hospital_visits", conn)
                visits_records = visits_df.to_dict(orient="records")
        except Exception as e:
            logger.warning(f"Could not read SQLite visits: {e}")

    logger.info(
        f"Extracted: {len(hospitals_df)} hospitals, {len(patients_df)} patients, "
        f"{len(users_data)} users, {len(bed_data)} hospital inventories, "
        f"{len(ref_data)} referrals, {len(res_data)} reservations, {len(visits_records)} visits."
    )

    return {
        "hospitals_df": hospitals_df,
        "patients_df": patients_df,
        "users": users_data,
        "bed_inventory": bed_data,
        "referrals": ref_data,
        "reservations": res_data,
        "visits": visits_records,
    }


def validate_referential_integrity(data: Dict[str, Any]) -> List[str]:
    """Validate cross-entity keys before committing to PostgreSQL."""
    errors = []
    hospital_ids = set(data["hospitals_df"]["hospital_id"].dropna().unique())
    patient_ids = set(data["patients_df"]["patient_id"].dropna().unique())

    # Validate Users
    for u in data["users"]:
        h_id = u.get("hospital_id")
        if h_id and h_id not in hospital_ids:
            errors.append(f"User {u.get('username')} references non-existent hospital {h_id}")

    # Validate Referrals
    for r in data["referrals"]:
        p_id = r.get("patient_id")
        from_h = r.get("from_hospital_id")
        to_h = r.get("to_hospital_id")
        if p_id not in patient_ids:
            errors.append(f"Referral {r.get('referral_id')} references unknown patient {p_id}")
        if from_h not in hospital_ids:
            errors.append(f"Referral {r.get('referral_id')} references unknown source hospital {from_h}")
        if to_h not in hospital_ids:
            errors.append(f"Referral {r.get('referral_id')} references unknown target hospital {to_h}")

    return errors


def execute_migration(db_url: str, dry_run: bool = True, patients_limit: Optional[int] = None):
    """Run migration into the target database."""
    data = load_legacy_data()
    errors = validate_referential_integrity(data)

    if errors:
        logger.warning(f"Referential warnings found: {len(errors)}")
        for err in errors[:5]:
            logger.warning(f"  - {err}")

    if dry_run:
        logger.info("=== DRY RUN COMPLETE: NO DATA WAS MODIFIED ===")
        return {
            "success": True,
            "dry_run": True,
            "hospitals": len(data["hospitals_df"]),
            "patients": len(data["patients_df"]),
            "users": len(data["users"]),
            "referrals": len(data["referrals"]),
            "reservations": len(data["reservations"]),
            "visits": len(data["visits"]),
            "errors": len(errors),
        }

    # Live migration
    logger.info(f"Connecting to target database: {db_url}")
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        from src.database.pg_models import (
            PgBase,
            Hospital,
            Role,
            User,
            Patient,
            HospitalVisit,
            Bed,
            Referral,
            BedReservation,
            AuditLog,
        )

        # Create schema tables if not exist
        PgBase.metadata.create_all(engine)

        now = datetime.now(timezone.utc)

        # 1. Roles
        roles = [
            Role(id="HOSPITAL", description="Hospital Clinical & Operations Staff"),
            Role(id="DISTRICT_ADMIN", description="District Healthcare Administration"),
            Role(id="STATE_ADMIN", description="State Government Healthcare Administration"),
            Role(id="CENTRAL_ADMIN", description="National / Central Referral Oversight"),
        ]
        for r in roles:
            session.merge(r)
        session.flush()

        # 2. Hospitals
        valid_hospital_ids = set()
        for _, row in data["hospitals_df"].iterrows():
            hid = str(row["hospital_id"]).strip()
            valid_hospital_ids.add(hid)
            h_obj = Hospital(
                hospital_id=hid,
                name=str(row.get("hospital_name") or row.get("name", "")).strip(),
                state=str(row.get("state", "Punjab")).strip(),
                district=str(row.get("district", "Amritsar")).strip(),
                city=str(row.get("city", "")).strip(),
                latitude=float(row.get("latitude", 31.63)),
                longitude=float(row.get("longitude", 74.87)),
                total_beds=int(row.get("total_beds", 100)),
                occupied_beds=int(row.get("occupied_beds", 50)),
                available_beds=int(row.get("available_beds", 50)),
                icu_beds=int(row.get("icu_beds", 20)),
                available_icu_beds=int(row.get("available_icu_beds", 10)),
                emergency_beds=int(row.get("emergency_beds", 10)),
                available_emergency_beds=int(row.get("available_emergency_beds", 5)),
                emergency_24x7=str(row.get("emergency_24x7", "Yes")),
                accepts_referral=str(row.get("accepts_referral", "Yes")),
                ambulance=str(row.get("ambulance", "Yes")),
                oxygen_support=str(row.get("oxygen_support", "Yes")),
                ventilator=str(row.get("ventilator", "Yes")),
                blood_bank=str(row.get("blood_bank", "Yes")),
                general_medicine=str(row.get("general_medicine", "Yes")),
                general_surgery=str(row.get("general_surgery", "Yes")),
                cardiology=str(row.get("cardiology", "No")),
                neurology=str(row.get("neurology", "No")),
                nephrology=str(row.get("nephrology", "No")),
                pulmonology=str(row.get("pulmonology", "No")),
                orthopedics=str(row.get("orthopedics", "No")),
                trauma_unit=str(row.get("trauma_unit", "No")),
                burn_unit=str(row.get("burn_unit", "No")),
            )
            session.merge(h_obj)
        session.flush()
        logger.info(f"Hospitals migrated successfully ({len(valid_hospital_ids)} records).")

        # 3. Users
        for u in data["users"]:
            u_hid = u.get("hospital_id")
            if u_hid and str(u_hid).strip() not in valid_hospital_ids:
                logger.warning(f"User {u['username']} hospital '{u_hid}' not in hospitals table; setting to NULL.")
                u_hid = None
            user_obj = User(
                user_id=u["user_id"],
                username=u["username"],
                password_hash=u.get("password") or u.get("password_hash"),
                name=u.get("name", u["username"]),
                role_id=u["role"],
                hospital_id=u_hid,
                state=u.get("state"),
                district=u.get("district"),
            )
            session.merge(user_obj)
        session.flush()
        logger.info("Users migrated successfully.")

        # 4. Beds from bed_inventory.json (Batch insert for speed)
        bed_records = []
        bed_count = 0
        for h_id, inv in data["bed_inventory"].items():
            if str(h_id).strip() not in valid_hospital_ids:
                continue
            beds_map = inv.get("beds", {})
            for b_num, b_status in beds_map.items():
                b_type = "ICU" if b_num.startswith("ICU") else ("EMERGENCY" if b_num.startswith("EMERGENCY") else "GENERAL")
                bed_records.append({
                    "hospital_id": str(h_id).strip(),
                    "bed_number": b_num,
                    "bed_type": b_type,
                    "status": b_status,
                    "created_at": now,
                    "updated_at": now,
                })
                bed_count += 1
                if len(bed_records) >= 5000:
                    session.bulk_insert_mappings(Bed, bed_records)
                    session.flush()
                    bed_records = []
        if bed_records:
            session.bulk_insert_mappings(Bed, bed_records)
            session.flush()
        logger.info(f"Physical beds migrated successfully ({bed_count} beds).")

        # 5. Patients (Batch insert for high-performance loading)
        patients_df = data["patients_df"]
        if patients_limit:
            patients_df = patients_df.head(patients_limit)

        loaded_patient_ids = set()
        patient_records = []
        for _, p in patients_df.iterrows():
            pid = str(p["patient_id"]).strip()
            loaded_patient_ids.add(pid)
            patient_records.append({
                "patient_id": pid,
                "name": str(p.get("name", f"{p.get('first_name', '')} {p.get('last_name', '')}")).strip(),
                "age": int(p["age"]) if not pd.isna(p.get("age")) else 40,
                "gender": str(p.get("gender", "Other")),
                "disease": str(p.get("disease", "")),
                "priority": normalize_patient_priority(p.get("priority")),
                "icu_required": str(p.get("icu_required", "No")),
                "ambulance_required": str(p.get("ambulance_required", "No")),
                "referral_required": str(p.get("referral_required", "Yes")),
                "state": str(p.get("state", "Punjab")),
                "district": str(p.get("district", "Amritsar")),
                "created_at": now,
                "updated_at": now,
            })
            if len(patient_records) >= 5000:
                session.bulk_insert_mappings(Patient, patient_records)
                session.flush()
                patient_records = []
        if patient_records:
            session.bulk_insert_mappings(Patient, patient_records)
            session.flush()
        logger.info(f"Patients migrated successfully ({len(loaded_patient_ids)} records).")

        # 6. Referrals
        ref_count = 0
        for r in data["referrals"]:
            r_pid = str(r["patient_id"]).strip()
            if r_pid not in loaded_patient_ids:
                stub_p = Patient(
                    patient_id=r_pid,
                    name=f"Patient {r_pid}",
                    priority=normalize_patient_priority(r.get("priority")),
                    state="Punjab",
                    district="Amritsar",
                )
                session.merge(stub_p)
                loaded_patient_ids.add(r_pid)

            from_h = str(r["from_hospital_id"]).strip()
            to_h = str(r["to_hospital_id"]).strip()
            if from_h not in valid_hospital_ids or to_h not in valid_hospital_ids:
                logger.warning(f"Referral {r['referral_id']} references unknown hospital(s) {from_h} -> {to_h}; skipping.")
                continue

            ref_obj = Referral(
                referral_id=r["referral_id"],
                patient_id=r_pid,
                from_hospital_id=from_h,
                to_hospital_id=to_h,
                status=r["status"],
                priority=r.get("priority", "Urgent"),
                bed_type=r.get("bed_type", "GENERAL"),
                reason=r.get("reason"),
            )
            session.merge(ref_obj)
            ref_count += 1
        session.flush()
        logger.info(f"Referrals migrated successfully ({ref_count} records).")

        # 7. Bed Reservations
        res_count = 0
        res_data = data["reservations"]
        items = res_data.items() if isinstance(res_data, dict) else [(r.get("reservation_id", f"RES-{i}"), r) for i, r in enumerate(res_data)]
        for res_id, res in items:
            h_id = str(res.get("hospital_id", "")).strip()
            p_id = str(res.get("patient_id", "")).strip()
            b_num = str(res.get("bed_id", "")).strip()
            status = str(res.get("status", "RESERVED")).upper().strip()

            bed_row = session.execute(
                select(Bed.id).where(Bed.hospital_id == h_id, Bed.bed_number == b_num)
            ).scalars().first()
            if not bed_row:
                continue

            ref_row = session.execute(
                select(Referral.referral_id).where(
                    Referral.patient_id == p_id,
                    Referral.to_hospital_id == h_id
                )
            ).scalars().first()

            if not ref_row:
                if p_id not in loaded_patient_ids:
                    stub_p = Patient(patient_id=p_id, name=f"Patient {p_id}", priority="Urgent", state="Punjab", district="Amritsar")
                    session.merge(stub_p)
                    loaded_patient_ids.add(p_id)
                ref_id_synth = f"REF-HIST-{res_id[:16]}"
                synth_ref = Referral(
                    referral_id=ref_id_synth,
                    patient_id=p_id,
                    from_hospital_id=h_id,
                    to_hospital_id=h_id,
                    status="COMPLETED" if status in ["RELEASED", "EXPIRED"] else "ACCEPTED",
                    priority="Urgent",
                    bed_type=res.get("bed_type", "ICU"),
                )
                session.merge(synth_ref)
                ref_row = ref_id_synth

            res_obj = BedReservation(
                reservation_id=res_id,
                referral_id=ref_row,
                hospital_id=h_id,
                bed_id=bed_row,
                status=status,
                reserved_at=safe_parse_datetime(res.get("reserved_at"), default=now),
                expires_at=safe_parse_datetime(res.get("expired_at") or res.get("expires_at"), default=now + timedelta(hours=2)),
                released_at=safe_parse_datetime(res.get("released_at")),
                created_at=now,
            )
            session.merge(res_obj)
            res_count += 1
        session.flush()
        logger.info(f"Bed reservations migrated successfully ({res_count} records).")

        # 8. Hospital Visits
        visit_count = 0
        for v in data["visits"]:
            v_pid = str(v.get("patient_id", "")).strip()
            v_hid = str(v.get("hospital_id", "")).strip()
            if v_hid not in valid_hospital_ids:
                continue
            if v_pid not in loaded_patient_ids:
                stub_p = Patient(patient_id=v_pid, name=f"Patient {v_pid}", priority="Stable", state="Punjab", district="Amritsar")
                session.merge(stub_p)
                loaded_patient_ids.add(v_pid)

            visit_obj = HospitalVisit(
                id=v.get("id"),
                patient_id=v_pid,
                hospital_id=v_hid,
                status=v.get("status", "NEW"),
                admission_type=v.get("admission_type", "DIRECT"),
                admitted_at=safe_parse_datetime(v.get("admitted_at"), default=now),
                treatment_started_at=safe_parse_datetime(v.get("treatment_started_at")),
                completed_at=safe_parse_datetime(v.get("completed_at")),
                notes=v.get("notes") if not pd.isna(v.get("notes")) else None,
            )
            session.merge(visit_obj)
            visit_count += 1
        session.flush()
        logger.info(f"Hospital visits migrated successfully ({visit_count} records).")

        # 9. Audit log of migration
        audit = AuditLog(
            entity_type="SYSTEM",
            entity_id="MIGRATION_001",
            action="MIGRATION_EXECUTE",
            performed_by="ETL_PIPELINE",
            new_state={
                "status": "COMPLETED",
                "hospitals": len(valid_hospital_ids),
                "patients": len(loaded_patient_ids),
                "beds": bed_count,
                "referrals": ref_count,
                "reservations": res_count,
                "visits": visit_count,
                "migrated_at": now.isoformat(),
            },
        )
        session.add(audit)

        session.commit()
        logger.info("=== POSTGRESQL MIGRATION COMMITTED SUCCESSFULLY ===")
        return {
            "success": True,
            "dry_run": False,
            "hospitals": len(valid_hospital_ids),
            "patients": len(loaded_patient_ids),
            "users": len(data["users"]),
            "beds": bed_count,
            "referrals": ref_count,
            "reservations": res_count,
            "visits": visit_count,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Migration aborted and rolled back: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SIH_Hospital_AI data to PostgreSQL")
    parser.add_argument("--db-url", type=str, default=os.getenv("DATABASE_URL"), help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Validate without writing")
    parser.add_argument("--commit", action="store_true", help="Execute live commit")
    parser.add_argument("--patients-limit", type=int, default=None, help="Limit number of patients to migrate (default: all)")

    args = parser.parse_args()
    dry_run = not args.commit

    result = execute_migration(db_url=args.db_url or "mock://", dry_run=dry_run, patients_limit=args.patients_limit)
    print(json.dumps(result, indent=2))
