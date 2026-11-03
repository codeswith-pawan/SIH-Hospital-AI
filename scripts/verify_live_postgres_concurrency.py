"""
Multi-Process Live PostgreSQL Concurrency Verification
AI Powered Smart Hospital Referral System - Phase 16

Executes true multi-process concurrency tests against live PostgreSQL:
1. 10 independent OS processes competing simultaneously for 1 available ICU bed (5 rounds).
2. 5 independent OS processes competing to accept the same referral concurrently.

Validates:
- Exactly 1 reservation succeeds per round.
- 9 requests fail safely with NO_BEDS_AVAILABLE.
- Hospital inventory counter never drops below 0 (no negative inventory).
- Partial unique indexes prevent double booking.
- ACID guarantees hold under extreme process contention.
"""

import os
import sys
import time
import uuid
import logging
from datetime import datetime, timezone
import multiprocessing as mp
from typing import List, Dict, Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.database.pg_models import (
    PgBase,
    Hospital,
    Patient,
    Bed,
    Referral,
    BedReservation,
    AuditLog,
)
from src.database.pg_repository import PgReferralRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("concurrency_test")

DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/sih_hospital_test")


def worker_book_bed(
    process_idx: int,
    db_url: str,
    referral_id: str,
    barrier: mp.Barrier,
    results_queue: mp.Queue,
):
    """
    Worker process running on its own independent OS process and PostgreSQL connection.
    Synchronizes at barrier, then executes atomic_accept_and_reserve.
    """
    # Create isolated engine with NullPool so this process has its own connection
    engine = create_engine(db_url, poolclass=NullPool)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        repo = PgReferralRepository(session)
        # Wait until all 10 processes are ready
        barrier.wait()
        start_time = time.perf_counter()

        result = repo.atomic_accept_and_reserve(
            referral_id=referral_id,
            user_id=f"PROCESS_WORKER_{process_idx}",
            ttl_hours=2,
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        results_queue.put({
            "process_idx": process_idx,
            "referral_id": referral_id,
            "success": result.get("success", False),
            "status": result.get("status"),
            "reason": result.get("reason"),
            "duration_ms": duration_ms,
        })
    except Exception as e:
        results_queue.put({
            "process_idx": process_idx,
            "referral_id": referral_id,
            "success": False,
            "error": str(e),
        })
    finally:
        session.close()
        engine.dispose()


def setup_contention_environment(engine, round_num: int) -> Dict[str, Any]:
    """Create test hospital with exactly 1 available ICU bed and 10 pending referrals."""
    Session = sessionmaker(bind=engine)
    session = Session()

    hosp_id = f"GH_CONCUR_R{round_num}"
    bed_num = f"ICU-HOT-{round_num}"

    # Clean existing
    session.execute(text(f"DELETE FROM bed_reservations WHERE hospital_id = '{hosp_id}'"))
    session.execute(text(f"DELETE FROM referrals WHERE to_hospital_id = '{hosp_id}'"))
    session.execute(text(f"DELETE FROM beds WHERE hospital_id = '{hosp_id}'"))
    session.execute(text(f"DELETE FROM hospitals WHERE hospital_id = '{hosp_id}'"))
    session.commit()

    # 1. Hospital with 1 available ICU bed
    hosp = Hospital(
        hospital_id=hosp_id,
        name=f"Contention Hospital Round {round_num}",
        state="Punjab",
        district="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=10,
        available_beds=5,
        icu_beds=1,
        available_icu_beds=1,
    )
    session.add(hosp)

    # 2. Exactly 1 physical available ICU bed
    bed = Bed(
        hospital_id=hosp_id,
        bed_number=bed_num,
        bed_type="ICU",
        status="AVAILABLE",
    )
    session.add(bed)

    # 3. 10 Patients and 10 Pending referrals
    referral_ids = []
    for i in range(10):
        pat_id = f"PAT_CONCUR_R{round_num}_{i}"
        ref_id = f"REF_CONCUR_R{round_num}_{i}"
        referral_ids.append(ref_id)

        # Upsert patient
        p = Patient(
            patient_id=pat_id,
            name=f"Contention Patient {round_num}-{i}",
            priority="Critical",
            icu_required="Yes",
            state="Punjab",
            district="Amritsar",
        )
        session.merge(p)

        ref = Referral(
            referral_id=ref_id,
            patient_id=pat_id,
            from_hospital_id=hosp_id,
            to_hospital_id=hosp_id,
            status="PENDING",
            priority="Critical",
            bed_type="ICU",
            reason=f"Emergency ICU referral round {round_num} index {i}",
        )
        session.add(ref)

    session.commit()
    session.close()

    return {
        "hospital_id": hosp_id,
        "bed_number": bed_num,
        "referral_ids": referral_ids,
    }


def verify_database_state(engine, hosp_id: str, bed_num: str, referral_ids: List[str]) -> Dict[str, Any]:
    """Query PostgreSQL directly to verify inventory, reservations, and referral statuses."""
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        hosp = session.execute(select(Hospital).where(Hospital.hospital_id == hosp_id)).scalar_one()
        bed = session.execute(select(Bed).where(Bed.hospital_id == hosp_id, Bed.bed_number == bed_num)).scalar_one()

        reservations = session.execute(
            select(BedReservation).where(
                BedReservation.hospital_id == hosp_id,
                BedReservation.status.in_(["RESERVED", "CONFIRMED", "OCCUPIED"]),
            )
        ).scalars().all()

        refs = session.execute(select(Referral).where(Referral.referral_id.in_(referral_ids))).scalars().all()
        accepted_refs = [r for r in refs if r.status == "ACCEPTED"]
        pending_refs = [r for r in refs if r.status == "PENDING"]

        return {
            "hospital_available_icu": hosp.available_icu_beds,
            "bed_status": bed.status,
            "active_reservations_count": len(reservations),
            "accepted_referrals_count": len(accepted_refs),
            "pending_referrals_count": len(pending_refs),
            "winner_referral_id": accepted_refs[0].referral_id if accepted_refs else None,
        }
    finally:
        session.close()


def run_10_process_contention_round(round_num: int) -> Dict[str, Any]:
    """Execute a single round of 10 concurrent OS processes competing for 1 bed."""
    engine = create_engine(DB_URL, poolclass=NullPool)
    setup = setup_contention_environment(engine, round_num)
    hosp_id = setup["hospital_id"]
    bed_num = setup["bed_number"]
    referral_ids = setup["referral_ids"]

    num_processes = 10
    barrier = mp.Barrier(num_processes)
    results_queue = mp.Queue()

    processes = []
    for i in range(num_processes):
        p = mp.Process(
            target=worker_book_bed,
            args=(i, DB_URL, referral_ids[i], barrier, results_queue),
        )
        processes.append(p)
        p.start()

    for p in processes:
        p.join(timeout=10.0)

    # Collect results
    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    successes = [r for r in results if r.get("success") is True]
    failures = [r for r in results if r.get("success") is False]

    db_state = verify_database_state(engine, hosp_id, bed_num, referral_ids)
    engine.dispose()

    # Invariants verification
    assert len(successes) == 1, f"Round {round_num}: Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 9, f"Round {round_num}: Expected exactly 9 failures, got {len(failures)}"
    assert db_state["active_reservations_count"] == 1, "Expected exactly 1 active reservation in PostgreSQL"
    assert db_state["hospital_available_icu"] == 0, f"Expected 0 available ICU beds, got {db_state['hospital_available_icu']}"
    assert db_state["bed_status"] == "RESERVED", f"Expected bed status RESERVED, got {db_state['bed_status']}"
    assert db_state["accepted_referrals_count"] == 1, "Expected exactly 1 accepted referral"
    assert db_state["pending_referrals_count"] == 9, "Expected 9 pending referrals"

    winner = successes[0]
    avg_latency = sum(r.get("duration_ms", 0) for r in results) / len(results)

    logger.info(
        f"Round {round_num} PASSED: Winner={winner['referral_id']} (proc {winner['process_idx']}) "
        f"in {winner.get('duration_ms', 0):.2f}ms | 9 safely rejected | Counter=0 (No negative inventory)"
    )

    return {
        "round": round_num,
        "successes": len(successes),
        "failures": len(failures),
        "db_state": db_state,
        "avg_latency_ms": avg_latency,
        "winner_duration_ms": winner.get("duration_ms", 0),
    }


def worker_duplicate_accept(
    process_idx: int,
    db_url: str,
    referral_id: str,
    barrier: mp.Barrier,
    results_queue: mp.Queue,
):
    """Worker trying to accept the EXACT SAME referral concurrently."""
    engine = create_engine(db_url, poolclass=NullPool)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        repo = PgReferralRepository(session)
        barrier.wait()
        res = repo.atomic_accept_and_reserve(referral_id, user_id=f"DUP_WORKER_{process_idx}")
        results_queue.put({"process_idx": process_idx, "result": res})
    except Exception as e:
        results_queue.put({"process_idx": process_idx, "error": str(e), "success": False})
    finally:
        session.close()
        engine.dispose()


def test_concurrent_duplicate_referral_acceptance() -> Dict[str, Any]:
    """Test 5 concurrent processes attempting to accept the identical referral."""
    engine = create_engine(DB_URL, poolclass=NullPool)
    Session = sessionmaker(bind=engine)
    session = Session()

    hosp_id = "GH_DUP_ACCEPT"
    ref_id = "REF_DUP_CONCURRENT"
    pat_id = "PAT_DUP_CONCURRENT"

    session.execute(text(f"DELETE FROM bed_reservations WHERE referral_id = '{ref_id}'"))
    session.execute(text(f"DELETE FROM referrals WHERE referral_id = '{ref_id}'"))
    session.execute(text(f"DELETE FROM beds WHERE hospital_id = '{hosp_id}'"))
    session.execute(text(f"DELETE FROM hospitals WHERE hospital_id = '{hosp_id}'"))
    session.commit()

    hosp = Hospital(
        hospital_id=hosp_id,
        name="Dup Test Hospital",
        state="Punjab",
        district="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=10,
        available_beds=5,
        icu_beds=5,
        available_icu_beds=5,
    )
    session.add(hosp)
    session.flush()

    # Add 5 available ICU beds
    for i in range(5):
        session.add(Bed(hospital_id=hosp_id, bed_number=f"ICU-DUP-{i}", bed_type="ICU", status="AVAILABLE"))
    
    session.merge(Patient(patient_id=pat_id, name="Dup Patient", priority="Critical"))
    session.add(Referral(
        referral_id=ref_id,
        patient_id=pat_id,
        from_hospital_id=hosp_id,
        to_hospital_id=hosp_id,
        status="PENDING",
        priority="Critical",
        bed_type="ICU",
    ))
    session.commit()
    session.close()

    # Spawn 5 processes all trying to accept this same referral
    num_procs = 5
    barrier = mp.Barrier(num_procs)
    q = mp.Queue()

    procs = []
    for i in range(num_procs):
        p = mp.Process(target=worker_duplicate_accept, args=(i, DB_URL, ref_id, barrier, q))
        procs.append(p)
        p.start()

    for p in procs:
        p.join(timeout=10.0)

    results = []
    while not q.empty():
        results.append(q.get())

    successes = [r for r in results if r.get("result", {}).get("success") is True]
    failures = [r for r in results if r.get("result", {}).get("success") is False or r.get("success") is False]

    # Verify database state
    session = Session()
    res_count = session.execute(
        select(text("COUNT(*)")).select_from(text("bed_reservations")).where(text(f"referral_id = '{ref_id}'"))
    ).scalar()
    ref_obj = session.execute(select(Referral).where(Referral.referral_id == ref_id)).scalar_one()
    session.close()
    engine.dispose()

    assert len(successes) == 1, f"Expected exactly 1 process to accept referral, got {len(successes)}"
    assert len(failures) == 4, f"Expected 4 processes to be rejected, got {len(failures)}"
    assert res_count == 1, f"Expected exactly 1 reservation for referral, got {res_count}"
    assert ref_obj.status == "ACCEPTED"

    logger.info("Concurrent Duplicate Acceptance PASSED: Exactly 1 acceptance succeeded; 4 safely rejected.")
    return {
        "success": True,
        "successes": len(successes),
        "rejections": len(failures),
        "reservations_created": res_count,
    }


def main():
    logger.info("=== STARTING MULTI-PROCESS LIVE POSTGRESQL CONCURRENCY SUITE ===")
    logger.info(f"Connecting to live PostgreSQL at: {DB_URL}")

    # Verify PostgreSQL connectivity
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version();")).scalar()
        logger.info(f"Target Database Engine: {ver}")

    # 1. Five rounds of 10-process contention for 1 ICU bed
    rounds_summary = []
    for r in range(1, 6):
        summary = run_10_process_contention_round(r)
        rounds_summary.append(summary)

    # 2. Duplicate acceptance race condition test
    dup_summary = test_concurrent_duplicate_referral_acceptance()

    print("\n" + "=" * 70)
    print("LIVE POSTGRESQL MULTI-PROCESS CONCURRENCY VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"Rounds executed: 5 rounds x 10 processes = 50 concurrent transactions")
    for s in rounds_summary:
        print(f"  - Round {s['round']}: 1 Winner ({s['winner_duration_ms']:.2f}ms), 9 Safely Rejected, Inventory=0, ActiveHolds=1")
    print(f"Duplicate Acceptance Race: 5 processes -> 1 Winner, 4 Safely Blocked, ActiveHolds=1")
    print("Zero double-bookings detected. Zero negative inventory states. Engine ACID locks verified.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
