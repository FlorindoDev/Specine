import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import Path

from benchmarks import (
    BENCHMARKS,
    ZENODO_ARCHIVE_MD5,
    ZENODO_ARCHIVE_SIZE,
    ZENODO_ARCHIVE_URL,
    Benchmark,
    get_benchmark,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_DIR = PROJECT_ROOT / "Datasets"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
TEMPORARY_ARCHIVE_NAME = ".Datasets.zip.part"


def _format_size(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MiB"


def _calculate_crc32(path: Path) -> int:
    checksum = 0
    with path.open("rb") as dataset_file:
        while chunk := dataset_file.read(DOWNLOAD_CHUNK_SIZE):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def _is_valid_dataset(path: Path, benchmark: Benchmark) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == benchmark.dataset_size
        and _calculate_crc32(path) == benchmark.dataset_crc32
    )


def _print_progress(transferred: int, total: int) -> None:
    percentage = transferred / total * 100
    print(
        f"\r{_format_size(transferred)}  {percentage:5.1f}%",
        end="",
        flush=True,
    )


def _download_archive(destination: Path) -> None:
    request = urllib.request.Request(
        ZENODO_ARCHIVE_URL,
        headers={"User-Agent": "Specine-dataset-downloader/1.0"},
    )
    checksum = hashlib.md5()
    downloaded = 0

    print(f"Download archivio: {_format_size(ZENODO_ARCHIVE_SIZE)}")
    with urllib.request.urlopen(
        request,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    ) as response:
        with destination.open("wb") as archive_file:
            while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                archive_file.write(chunk)
                checksum.update(chunk)
                downloaded += len(chunk)
                _print_progress(downloaded, ZENODO_ARCHIVE_SIZE)
    print()

    if downloaded != ZENODO_ARCHIVE_SIZE:
        raise RuntimeError(
            f"Dimensione archivio errata: {downloaded}, "
            f"attesa {ZENODO_ARCHIVE_SIZE}"
        )
    if checksum.hexdigest() != ZENODO_ARCHIVE_MD5:
        raise RuntimeError(
            f"MD5 archivio errato: {checksum.hexdigest()}, "
            f"atteso {ZENODO_ARCHIVE_MD5}"
        )


def _find_dataset_member(
    archive: zipfile.ZipFile,
    benchmark: Benchmark,
) -> zipfile.ZipInfo:
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir()
        and Path(member.filename).name == benchmark.dataset_file
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Impossibile individuare {benchmark.dataset_file} nell'archivio"
        )

    member = matches[0]
    if member.file_size != benchmark.dataset_size:
        raise RuntimeError(
            f"Dimensione di {benchmark.dataset_file} errata: "
            f"{member.file_size}, attesa {benchmark.dataset_size}"
        )
    if member.CRC != benchmark.dataset_crc32:
        raise RuntimeError(
            f"CRC32 di {benchmark.dataset_file} errato: {member.CRC:08x}, "
            f"atteso {benchmark.dataset_crc32:08x}"
        )
    return member


def _extract_dataset(
    archive_path: Path,
    destination: Path,
    benchmark: Benchmark,
) -> None:
    print(
        f"Estrazione {benchmark.display_name}: "
        f"{_format_size(benchmark.dataset_size)}"
    )
    checksum = 0
    extracted = 0

    with zipfile.ZipFile(archive_path) as archive:
        member = _find_dataset_member(archive, benchmark)
        with archive.open(member) as source, destination.open("wb") as output:
            while chunk := source.read(DOWNLOAD_CHUNK_SIZE):
                output.write(chunk)
                checksum = zlib.crc32(chunk, checksum)
                extracted += len(chunk)
                _print_progress(extracted, benchmark.dataset_size)
    print()

    checksum &= 0xFFFFFFFF
    if extracted != benchmark.dataset_size:
        raise RuntimeError(
            f"Dimensione estratta errata: {extracted}, "
            f"attesa {benchmark.dataset_size}"
        )
    if checksum != benchmark.dataset_crc32:
        raise RuntimeError(
            f"CRC32 estratto errato: {checksum:08x}, "
            f"atteso {benchmark.dataset_crc32:08x}"
        )


def download_dataset(benchmark_name: str, force: bool = False) -> Path:
    benchmark = get_benchmark(benchmark_name)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    destination = DATASET_DIR / benchmark.dataset_file
    partial_destination = destination.with_suffix(destination.suffix + ".part")
    archive_path = DATASET_DIR / TEMPORARY_ARCHIVE_NAME

    if destination.exists() and not force:
        if _is_valid_dataset(destination, benchmark):
            print(f"{benchmark.display_name}: dataset già presente e valido")
            print(destination)
            return destination
        raise RuntimeError(
            f"{destination} esiste ma non supera la verifica. "
            "Usa --force per riscaricarlo."
        )

    try:
        _download_archive(archive_path)
        _extract_dataset(archive_path, partial_destination, benchmark)
        os.replace(partial_destination, destination)
    finally:
        archive_path.unlink(missing_ok=True)
        partial_destination.unlink(missing_ok=True)

    print(f"Salvato in {destination}")
    return destination


def _select_benchmark() -> str:
    benchmark_names = tuple(BENCHMARKS)
    print("Scegli il benchmark da scaricare")
    for index, name in enumerate(benchmark_names, start=1):
        print(f"{index}. {BENCHMARKS[name].display_name}")

    try:
        selection = int(input("Numero: "))
        if not 1 <= selection <= len(benchmark_names):
            raise ValueError
        return benchmark_names[selection - 1]
    except (EOFError, ValueError):
        raise ValueError("Selezione non valida") from None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scarica uno dei benchmark supportati da Specine."
    )
    parser.add_argument(
        "--benchmark",
        choices=tuple(BENCHMARKS),
        help="Se omesso, viene mostrato un menu interattivo.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Riscarica e sostituisce un dataset già presente.",
    )
    args = parser.parse_args()

    benchmark_name = args.benchmark or _select_benchmark()
    try:
        download_dataset(benchmark_name, force=args.force)
    except (
        OSError,
        urllib.error.URLError,
        RuntimeError,
        ValueError,
        zipfile.BadZipFile,
    ) as error:
        print(f"Errore: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
