from shelfware.delta import delta


def snap(utc, rows):
    ws = [
        {"crypto_id": i, "symbol": f"S{i}", "underlying": "U", "issuer_name": "X", "status": s}
        for i, s in rows
    ]
    c = {
        "wrappers": len(ws),
        "active": sum(1 for _, s in rows if s == "active"),
        "untracked": sum(1 for _, s in rows if s == "untracked"),
    }
    return {"generated_utc": utc, "counts": c, "wrappers": ws}


def test_newly_tracked_is_a_shelf_wrapper_coming_alive_and_nothing_else():
    """unresolved -> active is a resolution (the paged map omitted the row on day 1), not a
    market event. It is listed under flips and counted apart."""
    before = snap("d1", [(1, "untracked"), (2, "active"), (3, "unresolved"), (4, "untracked")])
    after = snap("d2", [(1, "active"), (2, "untracked"), (3, "active"), (4, "untracked")])
    d = delta(before, after)
    assert d["newly_tracked"] == 1 and d["newly_shelved"] == 1 and d["other_flips"] == 1
    assert [f["crypto_id"] for f in d["flips"]] == [1, 2, 3]


def test_new_and_gone_wrappers_are_listed_by_id():
    d = delta(
        snap("d1", [(1, "active"), (2, "untracked")]),
        snap("d2", [(2, "untracked"), (3, "untracked")]),
    )
    assert d["new"] == [3] and d["gone"] == [1]
    assert d["new_wrappers"] == 1 and d["gone_wrappers"] == 1
    assert d["from"] == "d1" and d["to"] == "d2"


def test_delta_of_identical_snapshots_is_empty():
    s = snap("d1", [(1, "active"), (2, "untracked")])
    d = delta(s, snap("d2", [(1, "active"), (2, "untracked")]))
    assert d["flips"] == [] and d["new"] == [] and d["gone"] == []
    assert d["newly_tracked"] == d["newly_shelved"] == 0
