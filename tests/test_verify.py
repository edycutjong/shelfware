"""verify.py — every drift it is built to catch, provoked one at a time on the committed rows."""

import copy

from shelfware import verify


def _drifted(doc, mutate):
    d = copy.deepcopy(doc)
    mutate(d)
    return verify.compare_counts(d)


def test_the_committed_census_verifies_clean(committed_census):
    ok, findings = verify.compare_counts(committed_census)
    assert ok and findings == []


def test_a_wrapper_whose_price_and_status_disagree_is_named(committed_census):
    def mutate(d):
        w = next(w for w in d["wrappers"] if w["status"] == "active")
        w["price"] = None

    ok, findings = _drifted(committed_census, mutate)
    assert not ok and any("price:null and status:untracked disagree" in f for f in findings)


def test_a_drifted_issuer_row_is_named(committed_census):
    def mutate(d):
        d["by_issuer"][0]["untracked"] += 1

    ok, findings = _drifted(committed_census, mutate)
    assert not ok and any(f.startswith("by_issuer[") for f in findings)


def test_a_drifted_type_bar_is_named(committed_census):
    def mutate(d):
        d["by_type"][0]["tracked"] += 1
        d["by_type"][0]["untracked"] -= 1

    ok, findings = _drifted(committed_census, mutate)
    assert not ok and any(f.startswith("by_type[") for f in findings)


def test_issuer_and_type_attached_sums_must_equal_the_wrapper_count(committed_census):
    def mutate(d):
        d["counts"]["wrappers"] += 1

    ok, findings = _drifted(committed_census, mutate)
    assert not ok
    assert any("Σ by_issuer.attached" in f for f in findings)
    assert any("Σ by_type.attached" in f for f in findings)


def test_more_zero_tracked_underlyings_than_underlyings_is_impossible(committed_census):
    def mutate(d):
        d["counts"]["has_tokens"] = d["counts"]["underlyings_zero_tracked"] - 1

    ok, findings = _drifted(committed_census, mutate)
    assert not ok and any("impossible" in f for f in findings)


def test_credits_used_must_be_the_sum_of_keyed_credit_counts(committed_census):
    def mutate(d):
        d["credits_used"] += 1

    ok, findings = _drifted(committed_census, mutate)
    assert not ok and any(f.startswith("credits_used") for f in findings)


def test_a_text_that_prints_a_stale_headline_is_named(committed_census):
    h = verify.headline_numbers(committed_census)
    good = f"{h['zero_tracked']} of {h['has_tokens']} underlyings"
    assert verify.check_text_mentions(good, committed_census, "README") == []
    stale = f"{h['zero_tracked'] - 1} of {h['has_tokens']} underlyings"
    assert verify.check_text_mentions(stale, committed_census, "README") == [
        f"README: does not state '{h['zero_tracked']} of {h['has_tokens']}'"
    ]


def test_the_live_sample_is_seeded_and_skips_unresolved_rows(committed_census):
    a = verify.sample_for_live(committed_census, n=10, seed=7)
    b = verify.sample_for_live(committed_census, n=10, seed=7)
    assert [w["crypto_id"] for w in a] == [w["crypto_id"] for w in b] and len(a) == 10
    assert all(w["status"] != "unresolved" and w["symbol"] for w in a)


class _Client:
    def __init__(self, rows, meta):
        self.rows, self.meta = rows, meta

    def cmc_map(self, symbols):
        return self.rows, self.meta, []


def test_the_live_check_compares_each_committed_status_to_the_fetched_one(committed_census):
    sample = verify.sample_for_live(committed_census, n=3, seed=1)
    rows = {w["crypto_id"]: {"status": w["status"]} for w in sample}
    ok, lines, meta = verify.live_check(committed_census, _Client(rows, {"error": None}), 3, 1)
    assert ok and len(lines) == 3 and all(line.rstrip().endswith("=") for line in lines)

    rows[sample[0]["crypto_id"]] = {}  # dropped from the map -> unresolved now
    ok, lines, _ = verify.live_check(committed_census, _Client(rows, {"error": None}), 3, 1)
    assert not ok and "≠ (the market moved)" in lines[0] and "live unresolved" in lines[0]


def test_a_live_check_the_network_refused_says_so_instead_of_comparing(committed_census):
    ok, lines, meta = verify.live_check(committed_census, _Client({}, {"error": "HTTP 429"}), 2, 1)
    assert ok is None and lines == ["live check could not run: HTTP 429"]
    ok, lines, meta = verify.live_check(committed_census, _Client({}, None), 2, 1)
    assert ok is None and lines == ["live check could not run: None"] and meta is None
