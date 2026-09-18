"""What changed between two censuses. The only time axis the untracked rows have is the one
this repository records, so the diff is computed from committed snapshots, never estimated."""


def _index(doc):
    return {w["crypto_id"]: w for w in doc["wrappers"] if w.get("crypto_id") is not None}


def delta(before, after):
    a, b = _index(before), _index(after)
    new = sorted(i for i in b if i not in a)
    gone = sorted(i for i in a if i not in b)
    flips = []
    for i in sorted(b):
        if i in a and a[i].get("status") != b[i].get("status"):
            flips.append(
                {
                    "crypto_id": i,
                    "symbol": b[i].get("symbol"),
                    "underlying": b[i].get("underlying"),
                    "issuer_name": b[i].get("issuer_name"),
                    "before": a[i].get("status"),
                    "after": b[i].get("status"),
                }
            )
    return {
        "from": before["generated_utc"],
        "to": after["generated_utc"],
        "new": new,
        "gone": gone,
        "flips": flips,
        # a shelf wrapper coming alive, and the reverse — never a method artefact
        # (unresolved -> active is a resolution, not a market event; it is listed under flips)
        "newly_tracked": sum(
            1 for f in flips if f["before"] == "untracked" and f["after"] == "active"
        ),
        "newly_shelved": sum(
            1 for f in flips if f["before"] == "active" and f["after"] == "untracked"
        ),
        "other_flips": sum(
            1
            for f in flips
            if (f["before"], f["after"]) not in (("untracked", "active"), ("active", "untracked"))
        ),
        "new_wrappers": len(new),
        "gone_wrappers": len(gone),
        "counts_before": {k: before["counts"].get(k) for k in ("wrappers", "active", "untracked")},
        "counts_after": {k: after["counts"].get(k) for k in ("wrappers", "active", "untracked")},
    }
