from abu_alia.duplicates.score import score_duplicate


def test_identical_hash():
    r = score_duplicate(left_sha="abc", right_sha="abc")
    assert r["auto_merge"] is True
    assert r["kind"] == "identical_file"


def test_isbn():
    r = score_duplicate(left_isbn="9781111111111", right_isbn="9781111111111")
    assert r["auto_merge"] is True


def test_similar_title_different_author_not_merged():
    r = score_duplicate(
        left_title="تاريخ الرسل والملوك",
        right_title="تاريخ الرسل والملوك",
        left_author="الطبري",
        right_author="مؤلف آخر مختلف تماما",
    )
    assert r["auto_merge"] is False
    assert r["score"] < 0.7
