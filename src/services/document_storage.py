"""
Secure Document Storage & Antivirus Scanning Service
AI Powered Smart Hospital Referral System - Phase 1 Task 1E

Provides:
- Content verification (magic bytes) for PDF, JPEG, PNG
- Maximum file size enforcement (25 MB)
- SHA-256 cryptographic stream hashing
- Server-authoritative storage key generation
- Pluggable storage adapters (LocalStorageAdapter, S3StorageAdapter)
- Pluggable antivirus scanning (ClamAVScanner, SimulatedScanner)
- Safe retrieval, replacement, and deletion
"""

import os
import re
import io
import socket
import secrets
import hashlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from src.services.registration_exceptions import ValidationError

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB (26,214,400 bytes)

# Magic Byte Signatures
MAGIC_BYTES = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}

ALLOWED_MIME_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})
ALLOWED_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".png"})


class DocumentStorageError(Exception):
    """Raised when storage operations fail."""
    pass


class MalwareDetectedError(Exception):
    """Raised when malicious content or virus signatures are detected."""
    pass


class MalwareScanServiceUnavailableError(Exception):
    """Raised when antivirus scanner is unreachable or times out (fail-closed)."""
    pass


class MalwareScanError(Exception):
    """Raised when antivirus scanner returns an unexpected error (fail-closed)."""
    pass


# ============================================================
# CONTENT & MAGIC BYTE VERIFICATION
# ============================================================

def verify_file_content(
    file_bytes: bytes,
    declared_mime: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strict content and signature verification:
    1. Enforces <= 25 MB file size limit.
    2. Inspects initial magic bytes to determine genuine MIME type.
    3. Rejects MIME spoofing where declared MIME does not match magic bytes.
    4. Validates original_filename against path traversal and forbidden characters.
    5. Computes SHA-256 checksum.

    Returns dict containing verified_mime, file_size_bytes, checksum_sha256, clean_filename.
    """
    file_size = len(file_bytes)
    if file_size == 0:
        raise ValidationError("Uploaded file is empty (0 bytes).")

    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"File size ({file_size} bytes) exceeds maximum allowable limit of 25 MB ({MAX_FILE_SIZE_BYTES} bytes)."
        )

    # Magic byte inspection
    detected_mime = None
    if file_bytes.startswith(MAGIC_BYTES["application/pdf"]):
        detected_mime = "application/pdf"
    elif file_bytes.startswith(MAGIC_BYTES["image/jpeg"]):
        detected_mime = "image/jpeg"
    elif file_bytes.startswith(MAGIC_BYTES["image/png"]):
        detected_mime = "image/png"
    else:
        raise ValidationError(
            "File content signature does not match allowed types (PDF, JPEG, PNG). Spoofed or unsupported file rejected."
        )

    # Disallow MIME spoofing if client declared a different MIME
    if declared_mime:
        norm_declared = declared_mime.strip().lower()
        if norm_declared in ("image/jpg", "image/pjpeg"):
            norm_declared = "image/jpeg"
        if norm_declared != detected_mime:
            raise ValidationError(
                f"MIME type spoofing detected: client declared '{declared_mime}', but magic bytes identify '{detected_mime}'."
            )

    # Filename validation and sanitization
    clean_filename = "document"
    if original_filename:
        # Check traversal and forbidden characters
        if any(seq in original_filename for seq in ("..", "/", "\\", "\x00")):
            raise ValidationError("Invalid filename: directory traversal sequences and separators are forbidden.")
        
        base_name = os.path.basename(original_filename.strip())
        # Strip non-alphanumeric except safe symbols
        sanitized = re.sub(r"[^a-zA-Z0-9_\-\. ]", "", base_name)
        if not sanitized:
            sanitized = "document"
        clean_filename = sanitized[:200]

    # Check extension aligns with detected MIME
    ext = os.path.splitext(clean_filename)[1].lower()
    expected_exts = {
        "application/pdf": [".pdf"],
        "image/jpeg": [".jpg", ".jpeg"],
        "image/png": [".png"],
    }.get(detected_mime, [])

    if ext not in expected_exts:
        # Append appropriate extension
        clean_filename = f"{clean_filename}{expected_exts[0]}"

    # SHA-256 calculation
    checksum = hashlib.sha256(file_bytes).hexdigest()

    return {
        "verified_mime": detected_mime,
        "file_size_bytes": file_size,
        "checksum_sha256": checksum,
        "clean_filename": clean_filename,
    }


def generate_storage_key(application_id: str, clean_filename: str) -> str:
    """Generate server-authoritative storage key preventing client-controlled object paths."""
    slug = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", clean_filename)
    return f"documents/{application_id}/{secrets.token_hex(16)}_{slug}"


# ============================================================
# MALWARE SCANNING ABSTRACTION
# ============================================================

class BaseMalwareScanner(ABC):
    """Abstract interface for antivirus / malware scanning."""

    @abstractmethod
    def scan_bytes(self, file_bytes: bytes, filename: str) -> bool:
        """
        Scan bytes for viruses or malicious payloads.
        Returns True if clean.
        Raises MalwareDetectedError if infected.
        """
        pass


class SimulatedScanner(BaseMalwareScanner):
    """
    In-memory test scanner detecting standard test malware signatures:
    - EICAR test string
    - Custom marker 'MALWARE_TEST_VIRUS'
    """

    EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    TEST_VIRUS_SIGNATURE = b"MALWARE_TEST_VIRUS"

    def __init__(self):
        self.simulate_unavailable: bool = False
        self.simulate_timeout: bool = False
        self.simulate_error: bool = False

    def scan_bytes(self, file_bytes: bytes, filename: str) -> bool:
        if self.simulate_unavailable:
            logger.error("SimulatedScanner: Simulating scanner daemon unavailable for '%s'.", filename)
            raise MalwareScanServiceUnavailableError(
                f"Antivirus service unavailable: connection refused for '{filename}'. Fail-closed: upload rejected."
            )
        if self.simulate_timeout:
            logger.error("SimulatedScanner: Simulating scanner timeout for '%s'.", filename)
            raise MalwareScanServiceUnavailableError(
                f"Antivirus service unavailable: scan timed out for '{filename}'. Fail-closed: upload rejected."
            )
        if self.simulate_error:
            logger.error("SimulatedScanner: Simulating internal scan error for '%s'.", filename)
            raise MalwareScanError(
                f"Antivirus service returned internal scanner error for '{filename}'. Fail-closed: upload rejected."
            )

        if self.EICAR_SIGNATURE in file_bytes or self.TEST_VIRUS_SIGNATURE in file_bytes:
            logger.warning("SimulatedScanner: Malware signature detected in file '%s'.", filename)
            raise MalwareDetectedError(
                f"Malware scan failure: EICAR or malicious payload detected in '{filename}'."
            )
        return True


class ClamAVScanner(BaseMalwareScanner):
    """
    Production ClamAV daemon integration using TCP or UNIX domain socket.
    Streams bytes using INSTREAM protocol to clamd.
    Strictly fail-closed: if ClamAV is unavailable, times out, or returns an error,
    the upload is rejected immediately.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 3310, timeout: int = 10):
        self.host = host
        self.port = port
        self.timeout = timeout

    def scan_bytes(self, file_bytes: bytes, filename: str) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                # INSTREAM command
                sock.sendall(b"zINSTREAM\0")
                chunk_size = 2048
                stream = io.BytesIO(file_bytes)
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    size_header = len(chunk).to_bytes(4, byteorder="big")
                    sock.sendall(size_header + chunk)
                # Terminate stream with 4 zero bytes
                sock.sendall((0).to_bytes(4, byteorder="big"))

                # Read response
                response = b""
                while True:
                    data = sock.recv(1024)
                    if not data:
                        break
                    response += data

                resp_text = response.decode("utf-8", errors="ignore").strip()
                if "FOUND" in resp_text:
                    virus_name = resp_text.split(":")[-1].replace("FOUND", "").strip()
                    logger.error("ClamAV: Virus '%s' detected in '%s'.", virus_name, filename)
                    raise MalwareDetectedError(f"Malware detected by ClamAV in '{filename}': {virus_name}")
                elif "OK" in resp_text:
                    logger.info("ClamAV: File '%s' verified clean.", filename)
                    return True
                else:
                    logger.error("ClamAV returned unexpected response for '%s': %s", filename, resp_text)
                    raise MalwareScanError(
                        f"ClamAV scanner returned an unexpected or error response: '{resp_text}'. Fail-closed: upload rejected."
                    )
        except socket.timeout as e:
            logger.error("ClamAV connection timed out (%s:%s): %s", self.host, self.port, e)
            raise MalwareScanServiceUnavailableError(
                f"ClamAV antivirus daemon connection timed out after {self.timeout}s for file '{filename}'. Fail-closed: upload rejected."
            )
        except socket.error as e:
            logger.error("ClamAV daemon unreachable (%s:%s): %s", self.host, self.port, e)
            raise MalwareScanServiceUnavailableError(
                f"ClamAV antivirus daemon unreachable at {self.host}:{self.port} for file '{filename}'. Fail-closed: upload rejected."
            )


_ACTIVE_SCANNER: Optional[BaseMalwareScanner] = None

def get_malware_scanner() -> BaseMalwareScanner:
    """Retrieve configured malware scanner singleton."""
    global _ACTIVE_SCANNER
    if _ACTIVE_SCANNER is not None:
        return _ACTIVE_SCANNER

    clamav_host = os.getenv("SIH_CLAMAV_HOST")
    enable_clamav = os.getenv("SIH_ENABLE_CLAMAV", "").lower() in ("true", "1")

    if enable_clamav and clamav_host:
        port = int(os.getenv("SIH_CLAMAV_PORT", "3310"))
        _ACTIVE_SCANNER = ClamAVScanner(host=clamav_host, port=port)
    else:
        _ACTIVE_SCANNER = SimulatedScanner()

    return _ACTIVE_SCANNER


def set_malware_scanner(scanner: BaseMalwareScanner) -> None:
    """Override malware scanner (used for testing)."""
    global _ACTIVE_SCANNER
    _ACTIVE_SCANNER = scanner


# ============================================================
# STORAGE ADAPTER ABSTRACTION
# ============================================================

class BaseStorageAdapter(ABC):
    """Abstract storage adapter for document blob persistence."""

    @abstractmethod
    def put_object(self, storage_key: str, data: bytes, content_type: str) -> str:
        """Store binary bytes at storage_key. Returns authoritative storage_key."""
        pass

    @abstractmethod
    def get_object(self, storage_key: str) -> bytes:
        """Retrieve binary bytes for storage_key. Raises DocumentStorageError if not found."""
        pass

    @abstractmethod
    def delete_object(self, storage_key: str) -> bool:
        """Delete stored object. Returns True if deleted or did not exist."""
        pass

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check if object exists."""
        pass


class LocalStorageAdapter(BaseStorageAdapter):
    """
    Secure local filesystem storage adapter:
    - Normalizes and resolves all paths against base_dir.
    - Prevents directory traversal and symlink escapes.
    - Writes files atomically using temporary files.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            base_dir = os.getenv("STORAGE_BASE_DIR") or os.getenv("SIH_STORAGE_LOCAL_DIR", "data/storage/documents")
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        """Ensure storage_key resolves strictly inside base_dir."""
        # Strip leading slashes to prevent root-relative path resolution
        clean_key = storage_key.lstrip("/\\")
        target_path = (self.base_dir / clean_key).resolve()
        try:
            target_path.relative_to(self.base_dir)
        except ValueError:
            raise DocumentStorageError(f"Directory traversal attack detected in storage key '{storage_key}'.")
        return target_path

    def put_object(self, storage_key: str, data: bytes, content_type: str) -> str:
        target_path = self._resolve_safe_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temp file
        temp_path = target_path.with_suffix(f".tmp_{secrets.token_hex(8)}")
        try:
            with open(temp_path, "wb") as f:
                f.write(data)
            os.replace(temp_path, target_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise DocumentStorageError(f"Failed to persist document to local storage: {e}")

        return storage_key

    def get_object(self, storage_key: str) -> bytes:
        target_path = self._resolve_safe_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise DocumentStorageError(f"Document object '{storage_key}' not found in storage.")
        try:
            with open(target_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise DocumentStorageError(f"Failed to read document from storage: {e}")

    def delete_object(self, storage_key: str) -> bool:
        target_path = self._resolve_safe_path(storage_key)
        if target_path.exists() and target_path.is_file():
            try:
                target_path.unlink()
                return True
            except Exception as e:
                logger.error("Failed to delete local object '%s': %s", storage_key, e)
                return False
        return True

    def exists(self, storage_key: str) -> bool:
        target_path = self._resolve_safe_path(storage_key)
        return target_path.exists() and target_path.is_file()


class S3StorageAdapter(BaseStorageAdapter):
    """
    S3 / MinIO compatible storage adapter.
    Uses boto3 client when available; otherwise provides an in-memory simulation for testing.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.bucket = bucket_name or os.getenv("SIH_S3_BUCKET", "sih-documents")
        self.endpoint_url = endpoint_url or os.getenv("SIH_S3_ENDPOINT_URL")
        self.access_key = access_key or os.getenv("SIH_S3_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("SIH_S3_SECRET_KEY")

        self._in_memory_store: Dict[str, Tuple[bytes, str]] = {}
        self._s3_client = None

        try:
            import boto3
            if self.access_key and self.secret_key:
                self._s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                )
        except ImportError:
            pass

    def put_object(self, storage_key: str, data: bytes, content_type: str) -> str:
        if self._s3_client is not None:
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket,
                    Key=storage_key,
                    Body=data,
                    ContentType=content_type,
                )
                return storage_key
            except Exception as e:
                raise DocumentStorageError(f"Failed to put object in S3: {e}")
        
        # In-memory fallback
        self._in_memory_store[storage_key] = (data, content_type)
        return storage_key

    def get_object(self, storage_key: str) -> bytes:
        if self._s3_client is not None:
            try:
                resp = self._s3_client.get_object(Bucket=self.bucket, Key=storage_key)
                return resp["Body"].read()
            except Exception as e:
                raise DocumentStorageError(f"Failed to get object from S3: {e}")

        if storage_key not in self._in_memory_store:
            raise DocumentStorageError(f"Document object '{storage_key}' not found in S3 store.")
        return self._in_memory_store[storage_key][0]

    def delete_object(self, storage_key: str) -> bool:
        if self._s3_client is not None:
            try:
                self._s3_client.delete_object(Bucket=self.bucket, Key=storage_key)
                return True
            except Exception as e:
                logger.error("Failed to delete S3 object '%s': %s", storage_key, e)
                return False

        self._in_memory_store.pop(storage_key, None)
        return True

    def exists(self, storage_key: str) -> bool:
        if self._s3_client is not None:
            try:
                self._s3_client.head_object(Bucket=self.bucket, Key=storage_key)
                return True
            except Exception:
                return False

        return storage_key in self._in_memory_store


_ACTIVE_STORAGE_ADAPTER: Optional[BaseStorageAdapter] = None

def get_storage_adapter() -> BaseStorageAdapter:
    """Retrieve the active document storage adapter singleton."""
    global _ACTIVE_STORAGE_ADAPTER
    if _ACTIVE_STORAGE_ADAPTER is not None:
        return _ACTIVE_STORAGE_ADAPTER

    backend = os.getenv("SIH_STORAGE_BACKEND", "local").strip().lower()
    if backend == "s3":
        _ACTIVE_STORAGE_ADAPTER = S3StorageAdapter()
    else:
        _ACTIVE_STORAGE_ADAPTER = LocalStorageAdapter()

    return _ACTIVE_STORAGE_ADAPTER


def set_storage_adapter(adapter: BaseStorageAdapter) -> None:
    """Override active storage adapter (used in tests)."""
    global _ACTIVE_STORAGE_ADAPTER
    _ACTIVE_STORAGE_ADAPTER = adapter
