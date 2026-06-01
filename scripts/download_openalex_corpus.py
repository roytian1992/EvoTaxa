#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUERIES = [
    "computational social science",
    "computational social science methods",
    "social science computational methods",
    "text as data social science",
    "computational text analysis social science",
    "digital trace data social science",
    "network analysis computational social science",
    "agent-based modeling computational social science",
    "LLM social science annotation",
    "synthetic respondents large language models",
    "computational social science reproducibility",
    "platform data access social science",
]


SELECT_FIELDS = [
    "id",
    "doi",
    "display_name",
    "publication_year",
    "publication_date",
    "type",
    "authorships",
    "primary_location",
    "locations_count",
    "cited_by_count",
    "concepts",
    "keywords",
    "abstract_inverted_index",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download an EvoTaxa-ready OpenAlex corpus.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--from-date", default="1990-01-01")
    parser.add_argument("--to-date", default="2026-12-31")
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--max-results-per-query", type=int, default=400)
    parser.add_argument("--max-total", type=int, default=3000)
    parser.add_argument("--mailto", default="")
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--disable-relevance-filter", action="store_true")
    parser.add_argument("--count-only", action="store_true")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.count_only:
        manifest = count_union(
            output_root=output_root,
            queries=queries,
            from_date=args.from_date,
            to_date=args.to_date,
            per_page=max(1, min(200, args.per_page)),
            mailto=args.mailto,
            sleep_seconds=args.sleep_seconds,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    raw_path = output_root / "openalex_raw.jsonl"
    corpus_path = output_root / "corpus.jsonl"
    manifest_path = output_root / "manifest.json"
    manifest = download_resumable(
        output_root=output_root,
        queries=queries,
        from_date=args.from_date,
        to_date=args.to_date,
        per_page=max(1, min(200, args.per_page)),
        max_results_per_query=max(0, args.max_results_per_query),
        max_total=max(0, args.max_total),
        mailto=args.mailto,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        relevance_filter=not args.disable_relevance_filter,
        resume=args.resume,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def count_union(
    *,
    output_root: Path,
    queries: list[str],
    from_date: str,
    to_date: str,
    per_page: int,
    mailto: str,
    sleep_seconds: float,
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    ids: dict[str, dict[str, Any]] = {}
    query_counts: dict[str, int] = {}
    for query in queries:
        cursor = "*"
        fetched = 0
        while True:
            filters = [
                f"title_and_abstract.search:{query}",
                f"from_publication_date:{from_date}",
                f"to_publication_date:{to_date}",
                "has_abstract:true",
                "is_retracted:false",
            ]
            params = {
                "filter": ",".join(filters),
                "per-page": str(per_page),
                "cursor": cursor,
                "select": "id,publication_year,type",
            }
            if mailto:
                params["mailto"] = mailto
            url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
            response = request_json(url, timeout_seconds=timeout_seconds, max_retries=max_retries)
            meta = response.get("meta") or {}
            query_counts[query] = int(meta.get("count") or 0)
            rows = response.get("results") if isinstance(response.get("results"), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                work_id = str(row.get("id") or "")
                if not work_id:
                    continue
                ids.setdefault(
                    work_id,
                    {
                        "id": work_id,
                        "publication_year": row.get("publication_year"),
                        "type": row.get("type"),
                        "query_buckets": [],
                    },
                )
                ids[work_id]["query_buckets"] = sorted(set(ids[work_id]["query_buckets"]) | {query})
            fetched += len(rows)
            print(f"[openalex-count] query={query!r} api_count={query_counts[query]} fetched={fetched} unique={len(ids)}", file=sys.stderr, flush=True)
            cursor = str(meta.get("next_cursor") or "")
            if not rows or not cursor:
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    records = sorted(ids.values(), key=lambda row: (str(row.get("publication_year") or ""), row["id"]))
    ids_path = output_root / "openalex_union_ids.jsonl"
    write_jsonl(ids_path, records)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenAlex works API",
        "query_mode": "title_and_abstract.search",
        "from_date": from_date,
        "to_date": to_date,
        "queries": queries,
        "query_counts": query_counts,
        "has_abstract_sum": sum(query_counts.values()),
        "deduplicated_union_count": len(records),
        "ids_path": str(ids_path),
        "year_counts": dict(sorted(Counter(str(row.get("publication_year") or "unknown") for row in records).items())),
        "bucket_counts": dict(sorted(Counter(bucket for row in records for bucket in row.get("query_buckets", [])).items())),
        "overlap_distribution": dict(sorted(Counter(str(len(row.get("query_buckets", []))) for row in records).items())),
    }
    manifest_path = output_root / "openalex_union_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def download_resumable(
    *,
    output_root: Path,
    queries: list[str],
    from_date: str,
    to_date: str,
    per_page: int,
    max_results_per_query: int,
    max_total: int,
    mailto: str,
    sleep_seconds: float,
    timeout_seconds: float,
    max_retries: int,
    relevance_filter: bool,
    resume: bool,
) -> dict[str, Any]:
    state_path = output_root / "download_state.json"
    pages_dir = output_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    if not resume:
        for path in pages_dir.glob("*.jsonl"):
            path.unlink()
        if state_path.exists():
            state_path.unlink()

    state = load_state(state_path)
    state.setdefault("queries", {})
    state.setdefault("started_at", datetime.now(timezone.utc).isoformat())
    state.update(
        {
            "source": "OpenAlex works API",
            "api_endpoint": "https://api.openalex.org/works",
            "query_mode": "title_and_abstract.search",
            "from_date": from_date,
            "to_date": to_date,
            "per_page": per_page,
            "max_results_per_query": max_results_per_query,
            "max_total": max_total,
            "relevance_filter": relevance_filter,
        }
    )
    save_json(state_path, state)

    for query_index, query in enumerate(queries):
        query_state = state["queries"].setdefault(
            query,
            {
                "status": "pending",
                "cursor": "*",
                "page_index": 0,
                "fetched": 0,
                "api_count": None,
                "page_files": [],
            },
        )
        if query_state.get("status") == "complete":
            print(f"[openalex-resume] skip complete query={query!r}", file=sys.stderr, flush=True)
            continue
        cursor = str(query_state.get("cursor") or "*")
        page_index = int(query_state.get("page_index") or 0)
        fetched = int(query_state.get("fetched") or 0)
        while True:
            if max_results_per_query > 0 and fetched >= max_results_per_query:
                query_state["status"] = "complete"
                save_json(state_path, state)
                break
            filters = [
                f"title_and_abstract.search:{query}",
                f"from_publication_date:{from_date}",
                f"to_publication_date:{to_date}",
                "has_abstract:true",
                "is_retracted:false",
            ]
            params = {
                "filter": ",".join(filters),
                "per-page": str(per_page),
                "cursor": cursor,
                "select": ",".join(SELECT_FIELDS),
            }
            if mailto:
                params["mailto"] = mailto
            url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
            response = request_json(url, timeout_seconds=timeout_seconds, max_retries=max_retries)
            meta = response.get("meta") or {}
            rows = [row for row in response.get("results", []) if isinstance(row, dict)] if isinstance(response.get("results"), list) else []
            api_count = int(meta.get("count") or 0)
            query_state["api_count"] = api_count
            if max_results_per_query > 0:
                remaining = max(0, max_results_per_query - fetched)
                rows = rows[:remaining]
            page_file = pages_dir / f"query_{query_index:02d}_page_{page_index:05d}.jsonl"
            write_jsonl(page_file, [{**row, "_query_bucket": query} for row in rows])
            page_record = {
                "path": str(page_file),
                "query": query,
                "page_index": page_index,
                "row_count": len(rows),
                "cursor": cursor,
                "next_cursor": str(meta.get("next_cursor") or ""),
                "written_at": datetime.now(timezone.utc).isoformat(),
            }
            query_state.setdefault("page_files", []).append(page_record)
            fetched += len(rows)
            page_index += 1
            query_state["fetched"] = fetched
            query_state["page_index"] = page_index
            query_state["cursor"] = str(meta.get("next_cursor") or "")
            query_state["status"] = "running"
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_json(state_path, state)
            cursor = query_state["cursor"]
            print(
                f"[openalex-download] query={query!r} api_count={api_count} fetched={fetched} page_rows={len(rows)}",
                file=sys.stderr,
                flush=True,
            )
            if not rows or not query_state["cursor"] or (max_results_per_query > 0 and fetched >= max_results_per_query):
                query_state["status"] = "complete"
                save_json(state_path, state)
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    return finalize_download(
        output_root=output_root,
        state=state,
        queries=queries,
        from_date=from_date,
        to_date=to_date,
        max_results_per_query=max_results_per_query,
        max_total=max_total,
        relevance_filter=relevance_filter,
    )


def finalize_download(
    *,
    output_root: Path,
    state: dict[str, Any],
    queries: list[str],
    from_date: str,
    to_date: str,
    max_results_per_query: int,
    max_total: int,
    relevance_filter: bool,
) -> dict[str, Any]:
    records_by_id: dict[str, dict[str, Any]] = {}
    raw_by_id: dict[str, dict[str, Any]] = {}
    query_counts: dict[str, int] = {}
    accepted_by_query: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    for query in queries:
        query_state = (state.get("queries") or {}).get(query) or {}
        if query_state.get("api_count") is not None:
            query_counts[query] = int(query_state.get("api_count") or 0)
        for page in query_state.get("page_files") or []:
            page_path = Path(str(page.get("path") or ""))
            if not page_path.exists():
                continue
            for work in iter_jsonl(page_path):
                bucket = str(work.pop("_query_bucket", query) or query)
                record, reason = normalize_work(work, bucket, from_date=from_date, to_date=to_date, relevance_filter=relevance_filter)
                if record is None:
                    skipped[reason] += 1
                    continue
                work_id = record["doc_id"]
                if work_id in records_by_id:
                    records_by_id[work_id]["query_buckets"] = sorted(set(records_by_id[work_id]["query_buckets"]) | {bucket})
                    raw_by_id[work_id]["query_buckets"] = sorted(set(raw_by_id[work_id].get("query_buckets", [])) | {bucket})
                    continue
                records_by_id[work_id] = record
                raw_by_id[work_id] = {**work, "query_buckets": [bucket]}
                accepted_by_query[bucket] += 1
                if max_total > 0 and len(records_by_id) >= max_total:
                    break
            if max_total > 0 and len(records_by_id) >= max_total:
                break
        if max_total > 0 and len(records_by_id) >= max_total:
            break

    records = sorted(records_by_id.values(), key=lambda row: (row.get("publication_date") or "", row["doc_id"]))
    raw_records = [raw_by_id[row["doc_id"]] for row in records]
    raw_path = output_root / "openalex_raw.jsonl"
    corpus_path = output_root / "corpus.jsonl"
    manifest_path = output_root / "manifest.json"
    write_jsonl(corpus_path, records)
    write_jsonl(raw_path, raw_records)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenAlex works API",
        "api_endpoint": "https://api.openalex.org/works",
        "query_mode": "title_and_abstract.search",
        "from_date": from_date,
        "to_date": to_date,
        "queries": queries,
        "query_counts": query_counts,
        "accepted_by_query": dict(accepted_by_query),
        "skipped": dict(skipped),
        "max_results_per_query": max_results_per_query,
        "max_total": max_total,
        "relevance_filter": relevance_filter,
        "deduplicated_records": len(records),
        "corpus_path": str(corpus_path),
        "raw_path": str(raw_path),
        "state_path": str(output_root / "download_state.json"),
        "pages_dir": str(output_root / "pages"),
        "notes": [
            "Abstracts are reconstructed from OpenAlex abstract_inverted_index.",
            "The corpus JSONL follows docs/input_contract.md and keeps source metadata in raw.",
            "Per-page raw downloads are kept under pages/ so interrupted runs can resume.",
        ],
    }
    manifest["year_counts"] = dict(sorted(Counter(str(row.get("publication_year") or "unknown") for row in records).items()))
    manifest["bucket_counts"] = dict(sorted(Counter(bucket for row in records for bucket in row.get("query_buckets", [])).items()))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def fetch_query(
    *,
    query: str,
    from_date: str,
    to_date: str,
    per_page: int,
    max_results: int,
    mailto: str,
    sleep_seconds: float,
    timeout_seconds: float,
    max_retries: int,
) -> tuple[int, list[dict[str, Any]]]:
    cursor = "*"
    works: list[dict[str, Any]] = []
    count = 0
    while True:
        filters = [
            f"title_and_abstract.search:{query}",
            f"from_publication_date:{from_date}",
            f"to_publication_date:{to_date}",
            "has_abstract:true",
            "is_retracted:false",
        ]
        params = {
            "filter": ",".join(filters),
            "per-page": str(per_page),
            "cursor": cursor,
            "select": ",".join(SELECT_FIELDS),
        }
        if mailto:
            params["mailto"] = mailto
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        response = request_json(url, timeout_seconds=timeout_seconds, max_retries=max_retries)
        meta = response.get("meta") or {}
        count = int(meta.get("count") or 0)
        rows = response.get("results") if isinstance(response.get("results"), list) else []
        works.extend(row for row in rows if isinstance(row, dict))
        if max_results > 0 and len(works) >= max_results:
            works = works[:max_results]
            break
        cursor = str(meta.get("next_cursor") or "")
        if not rows or not cursor:
            break
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return count, works


def request_json(url: str, *, timeout_seconds: float, max_retries: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "EvoTaxa/0.1 OpenAlex downloader"})
    last_error = ""
    for attempt in range(max(1, max_retries)):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt + 1 >= max(1, max_retries):
                raise RuntimeError(f"OpenAlex request failed after {max_retries} attempts: {last_error}") from exc
            time.sleep(min(4.0, 0.5 * (attempt + 1)))
    if not isinstance(value, dict):
        raise ValueError("OpenAlex response was not a JSON object.")
    return value


def normalize_work(
    work: dict[str, Any],
    query: str,
    *,
    from_date: str,
    to_date: str,
    relevance_filter: bool,
) -> tuple[dict[str, Any] | None, str]:
    title = normalize_space(work.get("display_name") or "")
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if not title or not abstract:
        return None, "missing_title_or_abstract"
    publication_date = str(work.get("publication_date") or "")
    year = work.get("publication_year")
    if not publication_date and year:
        publication_date = f"{year}-01-01"
    if not publication_date:
        return None, "missing_publication_date"
    if publication_date < from_date or publication_date > to_date:
        return None, "outside_date_range"
    openalex_id = str(work.get("id") or "")
    if not openalex_id:
        return None, "missing_openalex_id"
    doc_id = openalex_id.rstrip("/").rsplit("/", 1)[-1]
    concepts = concept_names(work)
    keywords = keyword_names(work)
    relevance = relevance_flags(title=title, abstract=abstract, concepts=concepts, keywords=keywords, query=query)
    if relevance_filter and not relevance["keep"]:
        return None, relevance["reason"]
    text = abstract
    return (
        {
            "doc_id": doc_id,
            "openalex_id": openalex_id,
            "doi": work.get("doi") or "",
            "title": title,
            "abstract": abstract,
            "text": text,
            "publication_date": publication_date,
            "publication_year": year,
            "chronology_slice": str(year or publication_date[:4]),
            "role": "core",
            "source_type": "openalex_work",
            "query_buckets": [query],
            "concepts": concepts,
            "keywords": keywords,
            "relevance": relevance,
            "cited_by_count": work.get("cited_by_count") or 0,
            "work_type": work.get("type") or "",
            "raw": {
                "primary_location": work.get("primary_location"),
                "locations_count": work.get("locations_count"),
                "authorships": compact_authorships(work.get("authorships")),
            },
        },
        "",
    )


def reconstruct_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: dict[int, str] = {}
    for token, values in index.items():
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                positions[int(value)] = str(token)
            except (TypeError, ValueError):
                continue
    if not positions:
        return ""
    return normalize_space(" ".join(positions[index] for index in sorted(positions)))


def concept_names(work: dict[str, Any]) -> list[str]:
    rows = work.get("concepts") if isinstance(work.get("concepts"), list) else []
    return [
        normalize_space(row.get("display_name") or "")
        for row in rows
        if isinstance(row, dict) and normalize_space(row.get("display_name") or "")
    ][:20]


def keyword_names(work: dict[str, Any]) -> list[str]:
    rows = work.get("keywords") if isinstance(work.get("keywords"), list) else []
    return [
        normalize_space(row.get("display_name") or row.get("keyword") or "")
        for row in rows
        if isinstance(row, dict) and normalize_space(row.get("display_name") or row.get("keyword") or "")
    ][:20]


def relevance_flags(*, title: str, abstract: str, concepts: list[str], keywords: list[str], query: str) -> dict[str, Any]:
    text = " ".join([title, abstract, " ".join(concepts), " ".join(keywords)]).lower()
    query_low = query.lower()
    social_terms = [
        "social",
        "sociolog",
        "politic",
        "communication",
        "media",
        "public opinion",
        "policy",
        "governance",
        "institution",
        "survey",
        "behavior",
        "behaviour",
        "community",
        "platform",
        "population",
        "human",
        "civic",
        "democracy",
        "misinformation",
    ]
    method_terms = [
        "computational",
        "method",
        "model",
        "analysis",
        "data",
        "network",
        "simulation",
        "agent-based",
        "text",
        "trace",
        "experiment",
        "causal",
        "annotation",
        "classification",
        "embedding",
        "machine learning",
        "large language model",
        "llm",
        "algorithm",
        "reproducib",
    ]
    exact_terms = [
        "computational social science",
        "text as data",
        "digital trace data",
        "computational text analysis",
        "agent-based computational",
        "synthetic respondents",
    ]
    social_hits = [term for term in social_terms if term in text]
    method_hits = [term for term in method_terms if term in text]
    exact_hits = [term for term in exact_terms if term in text]
    query_terms = [term for term in query_low.split() if len(term) >= 4]
    query_hit_count = sum(1 for term in query_terms if term in text)
    keep = bool(exact_hits) or (bool(social_hits) and bool(method_hits) and query_hit_count >= max(1, min(2, len(query_terms))))
    reason = "kept" if keep else "low_relevance"
    return {
        "keep": keep,
        "reason": reason,
        "social_hits": social_hits[:8],
        "method_hits": method_hits[:8],
        "exact_hits": exact_hits,
        "query_hit_count": query_hit_count,
    }


def compact_authorships(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    output = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        author = row.get("author") if isinstance(row.get("author"), dict) else {}
        institutions = row.get("institutions") if isinstance(row.get("institutions"), list) else []
        output.append(
            {
                "author": author.get("display_name") or "",
                "author_id": author.get("id") or "",
                "institutions": [
                    inst.get("display_name")
                    for inst in institutions
                    if isinstance(inst, dict) and inst.get("display_name")
                ],
            }
        )
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def iter_jsonl(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if raw:
                yield json.loads(raw)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


if __name__ == "__main__":
    raise SystemExit(main())
