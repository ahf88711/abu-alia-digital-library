from abu_alia.connectors.oapen import is_arabic, license_url_of
from abu_alia.connectors.registry import get_connector
from abu_alia.rights.eligibility import classify_license


def test_oapen_connector_registered():
    assert get_connector("oapen").source_code == "oapen"


def test_oapen_arabic_and_license_gate():
    meta = {
        "dc.language": ["Arabic"],
        "dc.rights.uri": ["https://creativecommons.org/licenses/by-sa/4.0/"],
    }
    assert is_arabic(meta)
    url = license_url_of(meta)
    match = classify_license(url)
    assert match is not None
    assert match.allows_redistribution


def test_oapen_skips_unlicensed():
    meta = {"dc.language": ["Arabic"], "dc.rights": ["All rights reserved"]}
    assert license_url_of(meta) is None
