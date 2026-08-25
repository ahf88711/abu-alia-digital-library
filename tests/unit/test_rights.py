from abu_alia.rights.eligibility import Eligibility, decide_eligibility


def test_gutenberg_pd():
    d = decide_eligibility(source_code="gutenberg", copyright_flag=False)
    assert d["eligibility"] == Eligibility.VERIFIED_PUBLIC_DOMAIN


def test_openiti_premodern():
    d = decide_eligibility(source_code="openiti", author_death_year_ah=505)
    assert d["eligibility"] == Eligibility.VERIFIED_OPEN_LICENSE


def test_openiti_recent_quarantine():
    d = decide_eligibility(source_code="openiti", author_death_year_ah=1400)
    assert d["eligibility"] == Eligibility.UNCERTAIN


def test_ia_untrusted_quarantine():
    d = decide_eligibility(
        source_code="internet_archive",
        license_url="https://creativecommons.org/publicdomain/mark/1.0/",
        collections=["opensource"],
        trusted_ia_collections={"gutenberg"},
    )
    assert d["eligibility"] == Eligibility.UNCERTAIN


def test_ia_trusted():
    d = decide_eligibility(
        source_code="internet_archive",
        license_url="https://creativecommons.org/publicdomain/mark/1.0/",
        collections=["gutenberg"],
        trusted_ia_collections={"gutenberg"},
    )
    assert d["eligibility"] == Eligibility.VERIFIED_PUBLIC_DOMAIN


def test_inlibrary_prohibited():
    d = decide_eligibility(source_code="internet_archive", in_library_lending=True)
    assert d["eligibility"] == Eligibility.PROHIBITED
