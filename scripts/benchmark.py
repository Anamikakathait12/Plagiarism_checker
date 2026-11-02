"""Measure real internet-scan and offline comparison performance."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.datastructures import FileStorage

from app import create_app
from app.db import get_db_connection
from app.services.internet_scan import check_internet_similarity
from app.services.semantic import calculate_similarity
from app.services.text_extraction import extract_text
from app.services.winnowing import generate_fingerprints

BENCHMARK_DOCS = Path(__file__).resolve().parent / "benchmark_docs"
RESULTS_CSV = Path(__file__).resolve().parent / "benchmark_results.csv"
CSV_FIELDS = [
    "filename", "words", "scan_seconds", "queries", "urls_found",
    "pages_fetched_ok", "pages_blocked", "sources_scored", "overall_pct",
]
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-docs",
        type=_positive_int,
        help="Limit internet scans to the first N documents (offline tests still use all documents).",
    )
    parser.add_argument(
        "--skip-internet",
        action="store_true",
        help="Skip Tavily scans and run only offline benchmarks.",
    )
    return parser.parse_args()


def _load_documents() -> list[tuple[Path, str]]:
    if not BENCHMARK_DOCS.is_dir():
        raise FileNotFoundError(f"Document folder does not exist: {BENCHMARK_DOCS}")

    paths = sorted(
        path for path in BENCHMARK_DOCS.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not paths:
        raise FileNotFoundError(
            f"No PDF, DOCX, or TXT documents found in {BENCHMARK_DOCS}"
        )

    documents = []
    for path in paths:
        with path.open("rb") as stream:
            uploaded_file = FileStorage(stream=stream, filename=path.name)
            text = extract_text(uploaded_file)
        documents.append((path, text))
    return documents


def _print_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> None:
    rows = [[str(value) for value in row] for row in rows]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _benchmark_peer_comparisons(documents: list[tuple[Path, str]]) -> None:
    print("\nPeer-to-peer semantic comparison (warm-up excluded; matrix + pair scores):")
    rows = []
    texts = [text for _, text in documents]
    calculate_similarity(texts[:2])
    for count in (2, 5, 10):
        # Repeat the loaded corpus when fewer than N documents are available.
        batch = [texts[index % len(texts)] for index in range(count)]
        started = time.perf_counter()
        matrix = calculate_similarity(batch)
        pair_count = 0
        for first in range(count):
            for second in range(first + 1, count):
                _ = float(matrix[first][second] * 100)
                pair_count += 1
        elapsed = time.perf_counter() - started
        rows.append((count, pair_count, f"{elapsed:.6f}"))
    _print_table(["documents", "pairs", "seconds"], rows)


def _benchmark_fingerprints(documents: list[tuple[Path, str]]) -> None:
    print("\nWinnowing fingerprint generation:")
    rows = []
    for path, text in documents:
        started = time.perf_counter()
        fingerprints = generate_fingerprints(text)
        elapsed = time.perf_counter() - started
        rows.append((path.name, len(fingerprints), f"{elapsed:.6f}"))
    _print_table(["filename", "fingerprints", "seconds"], rows)


def _benchmark_global_scan() -> None:
    connection = get_db_connection()
    try:
        target = connection.execute(
            "SELECT assignment_id FROM document_fingerprints "
            "GROUP BY assignment_id ORDER BY assignment_id LIMIT 1"
        ).fetchone()
        if target is None:
            print("\nGlobal Winnowing scan: skipped (no stored fingerprints in the database).")
            return

        target_id = target["assignment_id"]
        target_hashes = {
            row["hash_value"]
            for row in connection.execute(
                "SELECT hash_value FROM document_fingerprints WHERE assignment_id = ?",
                (target_id,),
            )
        }
        if not target_hashes:
            print("\nGlobal Winnowing scan: skipped (no target fingerprints were found).")
            return

        placeholders = ",".join("?" for _ in target_hashes)
        query = f"""
            SELECT df.assignment_id AS matched_doc_id,
                   COUNT(df.hash_value) AS shared_count,
                   a.filename AS match_filename,
                   COALESCE(u.username, 'Unknown') AS match_student,
                   COALESCE(c.name, 'No Course') AS match_course,
                   a.course_id AS match_course_id
            FROM document_fingerprints df
            JOIN assignments a ON a.id = df.assignment_id
            LEFT JOIN users u ON u.id = a.student_id
            LEFT JOIN courses c ON c.id = a.course_id
            WHERE df.hash_value IN ({placeholders})
              AND df.assignment_id != ?
            GROUP BY df.assignment_id
            HAVING shared_count > 0
            ORDER BY shared_count DESC
        """
        started = time.perf_counter()
        matches = connection.execute(
            query, list(target_hashes) + [target_id]
        ).fetchall()
        elapsed = time.perf_counter() - started
        print(
            "\nGlobal Winnowing scan: "
            f"{elapsed:.6f} seconds, {len(matches)} matching documents "
            f"(using stored assignment {target_id})."
        )
    finally:
        connection.close()


def main() -> int:
    args = _parse_args()
    documents = _load_documents()
    words_by_doc = [len(text.split()) for _, text in documents]
    scan_limit = len(documents) if args.max_docs is None else min(args.max_docs, len(documents))
    app = create_app()
    csv_rows = []
    scan_metrics = []

    with app.app_context():
        if not args.skip_internet and not app.config.get("TAVILY_API_KEY"):
            raise RuntimeError(
                "TAVILY_API_KEY is not configured. Set it in .env/environment "
                "or use --skip-internet."
            )

        print(f"Loaded {len(documents)} document(s) from {BENCHMARK_DOCS}.")
        if args.skip_internet:
            print("Internet scans skipped; running offline benchmarks only.")
        elif scan_limit:
            # Each internet scan uses Tavily credits.
            print(f"Running {scan_limit} internet scan(s); each uses Tavily credits.")

        for index, (path, text) in enumerate(documents):
            row: dict[str, Any] = {
                "filename": path.name,
                "words": words_by_doc[index],
                "scan_seconds": "",
                "queries": "",
                "urls_found": "",
                "pages_fetched_ok": "",
                "pages_blocked": "",
                "sources_scored": "",
                "overall_pct": "",
            }
            if not args.skip_internet and index < scan_limit:
                result = check_internet_similarity(text)
                metrics = result["metrics"]
                scan_metrics.append(metrics)
                row.update({
                    "scan_seconds": metrics["total_scan_seconds"],
                    "queries": metrics["search_queries_fired"],
                    "urls_found": metrics["unique_urls_returned"],
                    "pages_fetched_ok": metrics["pages_fetched_ok"],
                    "pages_blocked": metrics["pages_blocked_or_failed"],
                    "sources_scored": metrics["sources_scored"],
                    "overall_pct": result["overall_pct"],
                })
            csv_rows.append(row)

        print("\nPer-document internet scan results:")
        _print_table(
            CSV_FIELDS,
            [[row[field] for field in CSV_FIELDS] for row in csv_rows],
        )
        _benchmark_peer_comparisons(documents)
        _benchmark_fingerprints(documents)
        _benchmark_global_scan()

    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nInternet scan results saved to {RESULTS_CSV}.")
    print("\nSummary:")
    print(f"  Average words per document: {sum(words_by_doc) / len(words_by_doc):.1f}")
    print(f"  Total documents tested: {len(documents)}")
    score_groups = {"copied": [], "partly_copied": [], "original": []}
    for row in csv_rows:
        if row["overall_pct"] == "":
            continue
        filename = row["filename"].lower()
        for group in score_groups:
            if filename.startswith(group):
                score_groups[group].append(float(row["overall_pct"]))

    def average_score(group: str) -> str:
        scores = score_groups[group]
        return f"{sum(scores) / len(scores):.1f}%" if scores else "n/a"

    copied_scores = score_groups["copied"]
    original_scores = score_groups["original"]
    gap = (
        f"{sum(copied_scores) / len(copied_scores) - sum(original_scores) / len(original_scores):+.1f} pp"
        if copied_scores and original_scores else "n/a"
    )
    print(
        "  Average score (copied / partly_copied / original): "
        f"{average_score('copied')} / {average_score('partly_copied')} / "
        f"{average_score('original')}; copied-original gap: {gap}"
    )
    if scan_metrics:
        scan_times = [metric["total_scan_seconds"] for metric in scan_metrics]
        sources = [metric["sources_scored"] for metric in scan_metrics]
        pages_ok = sum(metric["pages_fetched_ok"] for metric in scan_metrics)
        pages_failed = sum(metric["pages_blocked_or_failed"] for metric in scan_metrics)
        fetch_total = pages_ok + pages_failed
        success_rate = f"{pages_ok / fetch_total * 100:.1f}%" if fetch_total else "n/a"
        print(
            f"  Scan time (average / min / max): "
            f"{sum(scan_times) / len(scan_times):.6f} / "
            f"{min(scan_times):.6f} / {max(scan_times):.6f} seconds"
        )
        print(f"  Average sources scored: {sum(sources) / len(sources):.1f}")
        print(f"  Page fetch success rate: {success_rate}")
        print(f"  Internet scans completed: {len(scan_metrics)}")
    else:
        print("  Internet scan statistics: unavailable (internet scans were skipped).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
