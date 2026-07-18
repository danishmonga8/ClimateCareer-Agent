"""Secure document validation and fingerprinting services."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
DEFAULT_MAXIMUM_SIZE_MB = 10


class DocumentValidationError(ValueError):
    """Raised when an uploaded document fails validation."""


@dataclass(frozen=True, slots=True)
class ValidatedDocument:
    """Metadata for a successfully validated document."""

    path: Path
    filename: str
    extension: str
    size_bytes: int
    sha256_digest: str


def _calculate_sha256(path: Path) -> str:
    """Calculate a document fingerprint without loading the whole file."""
    digest = sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _validate_file_signature(path: Path, extension: str) -> None:
    """Check whether the file content matches its stated extension."""
    with path.open("rb") as file:
        signature = file.read(8)

    if extension == ".pdf" and not signature.startswith(b"%PDF-"):
        raise DocumentValidationError("The file does not contain a valid PDF signature.")

    if extension == ".docx" and not signature.startswith(b"PK"):
        raise DocumentValidationError("The file does not contain a valid DOCX signature.")


def validate_document(
    document_path: str | Path,
    maximum_size_mb: int = DEFAULT_MAXIMUM_SIZE_MB,
) -> ValidatedDocument:
    """Validate an uploaded CV or supporting document."""
    path = Path(document_path).expanduser().resolve()

    if not path.exists():
        raise DocumentValidationError(f"Document does not exist: {path}")

    if not path.is_file():
        raise DocumentValidationError(f"Document path is not a file: {path}")

    extension = path.suffix.lower()

    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise DocumentValidationError(
            f"Unsupported document type: {extension}. Only PDF and DOCX are allowed."
        )

    size_bytes = path.stat().st_size

    if size_bytes == 0:
        raise DocumentValidationError("The document is empty.")

    maximum_size_bytes = maximum_size_mb * 1024 * 1024

    if size_bytes > maximum_size_bytes:
        raise DocumentValidationError(
            f"Document exceeds the {maximum_size_mb} MB size limit."
        )

    _validate_file_signature(path, extension)

    return ValidatedDocument(
        path=path,
        filename=path.name,
        extension=extension,
        size_bytes=size_bytes,
        sha256_digest=_calculate_sha256(path),
    )