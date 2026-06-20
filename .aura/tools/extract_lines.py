"""Extract specific line ranges from a text file."""
from pathlib import Path


def extract_lines(file_path: str, ranges: list[str]) -> dict[str, str]:
    """Extract line ranges from a file.

    Args:
        file_path: Path to the text file.
        ranges: Strings like '955-982' or '1009-1030' for line ranges (1-based inclusive).

    Returns:
        Dictionary mapping range string to the extracted text.
    """
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    result: dict[str, str] = {}
    for r in ranges:
        parts = r.split("-")
        start = int(parts[0]) - 1
        end = int(parts[1])
        result[r] = "".join(lines[start:end])
    return result
