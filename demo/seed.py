#!/usr/bin/env python3
"""
Demo seeder — replays demo/payment_outage.json into API transcript + cognition path.
Usage:
  python demo/seed.py --incident payment-001 --api-url http://localhost:8000 --replay-rate 1.5
  python demo/seed.py --incident payment-001 --dry-run   # print without POST

Verification assertions (mirrors pytest e2e):
  4 facts, 1 hypothesis, 1 conflict, 1 overdue, timeline length, approval gate.
"""
import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

DEMO_JSON = Path(__file__).parent / "payment_outage.json"

def load_fixture(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def post_transcript(api_url: str, incident_id: str, utterance: dict) -> bool:
    # lazy import to avoid hard dep for --dry-run
    try:
        import httpx
    except ImportError:
        print("httpx not installed — pip install httpx", file=sys.stderr)
        return False
    payload = {
        "segment": {
            "id": utterance["id"],
            "incidentId": incident_id,
            "speakerId": utterance.get("speakerId"),
            "speakerName": utterance.get("speakerName"),
            "role": utterance.get("role"),
            "text": utterance["text"],
            "isFinal": utterance.get("isFinal", True),
            "startMs": utterance["startMs"],
            "endMs": utterance["endMs"],
            "confidence": 0.92,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    }
    try:
        r = httpx.post(f"{api_url}/incidents/{incident_id}/transcript", json=payload, timeout=10)
        print(f"POST {utterance['id']}: {r.status_code} {r.text[:120]}")
        return r.status_code < 400
    except Exception as e:
        print(f"POST {utterance['id']} failed: {e}", file=sys.stderr)
        return False

def ensure_incident(api_url: str, fixture: dict, incident_id: str) -> str:
    """Create (or reuse) the incident under the requested id — NOT the fixture's own baked-in
    id — so `--incident my-custom-id` actually targets that id. Safe to reuse the same fixture's
    utterance ids (u-001..u-012) across different incident ids: transcript segment uniqueness is
    scoped per-incident (see apps/api/models.py TranscriptSegmentModel), and the deterministic
    cognition fixture-map keys off the utterance id content, not the incident id."""
    try:
        import httpx
    except ImportError:
        return incident_id
    inc = fixture["incident"]
    try:
        r = httpx.post(f"{api_url}/incidents", json={"id": incident_id, "title": inc["title"], "severity": inc["severity"]}, timeout=10)
        if r.status_code < 400:
            j = r.json()
            print(f"Created incident {j.get('id')}")
            return j.get("id", incident_id)
    except Exception as e:
        print(f"ensure_incident skipped: {e}")
    return incident_id

def main():
    parser = argparse.ArgumentParser(description="Agora demo seeder")
    parser.add_argument("--incident", default="payment-001", help="incident id to seed into")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--replay-rate", type=float, default=1.5, help="speed multiplier (1.0 = real-time ms gaps)")
    parser.add_argument("--dry-run", action="store_true", help="print utterances without POST")
    parser.add_argument("--fixture", default=str(DEMO_JSON), help="path to payment_outage.json")
    args = parser.parse_args()

    fixture = load_fixture(Path(args.fixture))
    incident_id = args.incident
    utterances = fixture.get("utterances", [])

    if not args.dry_run:
        incident_id = ensure_incident(args.api_url, fixture, incident_id)
        print(f"Seeding to {args.api_url} incident={incident_id} rate={args.replay_rate}x")

    prev_start = None
    for u in utterances:
        if not args.dry_run and prev_start is not None:
            gap_ms = max(0, u["startMs"] - prev_start)
            sleep_s = (gap_ms / 1000.0) / max(0.1, args.replay_rate)
            time.sleep(sleep_s)
        prev_start = u["startMs"]
        ts = datetime.now(timezone.utc).isoformat()
        print(f"[{ts}] {u['speakerName']} ({u['role']}): {u['text']}")
        if not args.dry_run:
            post_transcript(args.api_url, incident_id, u)

    print(f"\nDone — replayed {len(utterances)} segments.")
    print(f"Expected: {json.dumps(fixture.get('expectedExtractions'), indent=2)}")

if __name__ == "__main__":
    main()
