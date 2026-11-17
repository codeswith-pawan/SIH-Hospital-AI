-- Migration 004: Category-Specific Occupancy Counters
-- Adds dedicated occupied counters for ICU and Emergency departments.
-- Preserves existing general occupancy in occupied_beds.

ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS occupied_icu_beds INTEGER NOT NULL DEFAULT 0;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS occupied_emergency_beds INTEGER NOT NULL DEFAULT 0;

-- Backfill occupied_icu_beds from detailed physical beds where available
UPDATE hospitals h
SET occupied_icu_beds = COALESCE(sub.cnt, 0)
FROM (
    SELECT hospital_id, COUNT(*) as cnt
    FROM beds
    WHERE bed_type = 'ICU' AND status = 'OCCUPIED'
    GROUP BY hospital_id
) sub
WHERE h.hospital_id = sub.hospital_id;

-- Backfill occupied_emergency_beds from detailed physical beds where available
UPDATE hospitals h
SET occupied_emergency_beds = COALESCE(sub.cnt, 0)
FROM (
    SELECT hospital_id, COUNT(*) as cnt
    FROM beds
    WHERE bed_type = 'EMERGENCY' AND status = 'OCCUPIED'
    GROUP BY hospital_id
) sub
WHERE h.hospital_id = sub.hospital_id;

-- Reconcile general occupied_beds for facilities with detailed beds
UPDATE hospitals h
SET occupied_beds = COALESCE(sub.cnt, 0)
FROM (
    SELECT hospital_id, COUNT(*) as cnt
    FROM beds
    WHERE bed_type = 'GENERAL' AND status = 'OCCUPIED'
    GROUP BY hospital_id
) sub
WHERE h.hospital_id = sub.hospital_id;
