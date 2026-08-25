from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urlparse


class Eligibility:
    VERIFIED_PUBLIC_DOMAIN = "verified_public_domain"
    VERIFIED_OPEN_LICENSE = "verified_open_license"
    EXPLICITLY_AUTHORIZED = "explicitly_authorized"
    UNCERTAIN = "uncertain"
    PROHIBITED = "prohibited"

    AUTO_PUBLISH = {
        VERIFIED_PUBLIC_DOMAIN,
        VERIFIED_OPEN_LICENSE,
        EXPLICITLY_AUTHORIZED,
    }


LICENSE_TABLE = {
    "pd": ("public-domain", True, True, False, False, False),
    "cc0": ("cc0-1.0", True, True, False, False, False),
    "cc-by": ("cc-by-4.0", True, True, True, False, False),
    "cc-by-sa": ("cc-by-sa-4.0", True, True, True, True, False),
    "cc-by-sa-3.0": ("cc-by-sa-3.0", True, True, True, True, False),
    "cc-by-nc": ("cc-by-nc-4.0", True, False, True, False, True),
    "cc-by-nc-sa": ("cc-by-nc-sa-4.0", True, False, True, True, True),
    "cc-by-nd": ("cc-by-nd-4.0", True, True, True, False, False),
    "cc-by-nc-nd": ("cc-by-nc-nd-4.0", True, False, True, False, True),
}


@dataclass
class LicenseMatch:
    code: str
    allows_redistribution: bool
    allows_commercial: bool
    requires_attribution: bool
    requires_share_alike: bool
    non_commercial_only: bool
    evidence: Dict[str, Any] = field(default_factory=dict)


def classify_license(url_or_code: Optional[str]) -> Optional[LicenseMatch]:
    if not url_or_code:
        return None
    raw = url_or_code.strip().lower()
    if raw in LICENSE_TABLE:
        t = LICENSE_TABLE[raw]
        return LicenseMatch(*t, evidence={"input": url_or_code})
    if "publicdomain" in raw or "public_domain" in raw or "public-domain" in raw:
        t = LICENSE_TABLE["pd"]
        return LicenseMatch(*t, evidence={"input": url_or_code, "via": "publicdomain"})
    if "creativecommons.org/publicdomain/zero" in raw or "/licenses/cc0" in raw:
        t = LICENSE_TABLE["cc0"]
        return LicenseMatch(*t, evidence={"input": url_or_code})
    if "creativecommons.org" in raw or "creativecommons.org/licenses" in raw:
        if "by-nc-sa" in raw:
            key = "cc-by-nc-sa"
        elif "by-nc-nd" in raw:
            key = "cc-by-nc-nd"
        elif "by-nc" in raw:
            key = "cc-by-nc"
        elif "by-sa/3.0" in raw or "by-sa/3.0/" in raw:
            key = "cc-by-sa-3.0"
        elif "by-sa" in raw:
            key = "cc-by-sa"
        elif "by-nd" in raw:
            key = "cc-by-nd"
        elif "/by/" in raw or "licenses/by" in raw:
            key = "cc-by"
        else:
            return None
        t = LICENSE_TABLE[key]
        return LicenseMatch(*t, evidence={"input": url_or_code})
    return None


def decide_eligibility(
    *,
    source_code: str,
    license_url: Optional[str] = None,
    collections: Optional[list] = None,
    author_death_year_ah: Optional[int] = None,
    in_library_lending: bool = False,
    explicitly_authorized: bool = False,
    trusted_ia_collections: Optional[set] = None,
    max_death_ah: int = 1300,
    copyright_flag: Optional[bool] = None,
) -> Dict[str, Any]:
    collections = collections or []
    death_ah = author_death_year_ah
    evidence: Dict[str, Any] = {
        "source_code": source_code,
        "license_url": license_url,
        "collections": collections,
        "author_death_year_ah": death_ah,
        "in_library_lending": in_library_lending,
    }
    if in_library_lending:
        return {
            "eligibility": Eligibility.PROHIBITED,
            "reason": "controlled_digital_lending",
            "license": None,
            "evidence": evidence,
        }
    if copyright_flag is True:
        return {
            "eligibility": Eligibility.PROHIBITED,
            "reason": "source_marked_copyright",
            "license": None,
            "evidence": evidence,
        }
    if explicitly_authorized:
        return {
            "eligibility": Eligibility.EXPLICITLY_AUTHORIZED,
            "reason": "explicit_authorization",
            "license": classify_license(license_url),
            "evidence": evidence,
        }

    match = classify_license(license_url)

    if source_code == "gutenberg":
        if copyright_flag is False or match:
            return {
                "eligibility": Eligibility.VERIFIED_PUBLIC_DOMAIN,
                "reason": "gutenberg_catalog",
                "license": match or classify_license("pd"),
                "evidence": evidence,
            }
        return {
            "eligibility": Eligibility.UNCERTAIN,
            "reason": "gutenberg_copyright_unknown",
            "license": match,
            "evidence": evidence,
        }

    if source_code == "openiti":
        if author_death_year_ah is None:
            return {
                "eligibility": Eligibility.UNCERTAIN,
                "reason": "missing_death_year",
                "license": match or classify_license("cc-by-nc-sa"),
                "evidence": evidence,
            }
        if author_death_year_ah > max_death_ah:
            return {
                "eligibility": Eligibility.UNCERTAIN,
                "reason": "author_too_recent",
                "license": classify_license("cc-by-nc-sa"),
                "evidence": evidence,
            }
        return {
            "eligibility": Eligibility.VERIFIED_OPEN_LICENSE,
            "reason": "openiti_cc_by_nc_sa_premodern",
            "license": classify_license("cc-by-nc-sa"),
            "evidence": evidence,
        }

    if source_code == "wikisource_ar":
        if match and match.allows_redistribution:
            return {
                "eligibility": Eligibility.VERIFIED_OPEN_LICENSE,
                "reason": "wikisource_cc_by_sa",
                "license": match,
                "evidence": evidence,
            }
        return {
            "eligibility": Eligibility.UNCERTAIN,
            "reason": "wikisource_license_unknown",
            "license": match,
            "evidence": evidence,
        }

    if source_code == "fixture":
        return {
            "eligibility": Eligibility.EXPLICITLY_AUTHORIZED,
            "reason": "test_fixture",
            "license": match or classify_license("cc0"),
            "evidence": evidence,
        }

    if source_code == "internet_archive":
        trusted = trusted_ia_collections or set()
        in_trusted = any(c in trusted for c in collections)
        if not match or not match.allows_redistribution:
            return {
                "eligibility": Eligibility.UNCERTAIN,
                "reason": "ia_no_clear_license",
                "license": match,
                "evidence": evidence,
            }
        if not in_trusted:
            # User-uploaded PD marks are frequently false.
            return {
                "eligibility": Eligibility.UNCERTAIN,
                "reason": "ia_untrusted_collection",
                "license": match,
                "evidence": evidence,
            }
        if match.code.startswith("cc"):
            el = Eligibility.VERIFIED_OPEN_LICENSE
        else:
            el = Eligibility.VERIFIED_PUBLIC_DOMAIN
        return {
            "eligibility": el,
            "reason": "ia_trusted_collection_and_license",
            "license": match,
            "evidence": evidence,
        }

    if match and match.allows_redistribution:
        return {
            "eligibility": Eligibility.VERIFIED_OPEN_LICENSE,
            "reason": "mapped_open_license",
            "license": match,
            "evidence": evidence,
        }
    return {
        "eligibility": Eligibility.UNCERTAIN,
        "reason": "default_uncertain",
        "license": match,
        "evidence": evidence,
    }
