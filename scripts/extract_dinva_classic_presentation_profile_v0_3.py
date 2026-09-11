"""Produce only a DRAFT visual successor; no approval or XLSX capability."""

from __future__ import annotations

import argparse
from pathlib import Path

from extract_dinva_classic_presentation_profile_v0_2 import (
    BoundInput,
    ProfileV02ExtractionError,
    extract_profile_v0_3,
    publish_draft_profile,
    sha256_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-v0-2-profile", required=True, type=Path)
    parser.add_argument("--approved-v0-2-profile-sha256", required=True)
    parser.add_argument("--output-profile", required=True, type=Path)
    args = parser.parse_args()
    try:
        profile = extract_profile_v0_3(
            BoundInput(args.approved_v0_2_profile, args.approved_v0_2_profile_sha256)
        )
        output = publish_draft_profile(profile, args.output_profile)
    except (OSError, ProfileV02ExtractionError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_PROFILE_V0_3=DRAFT_UNAPPROVED")
    print(f"FINGERPRINT={profile['presentation_contract_fingerprint']}")
    print(f"SHA256={sha256_bytes(output.read_bytes())}")
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
