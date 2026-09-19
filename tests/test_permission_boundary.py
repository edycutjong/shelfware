"""Permission boundary: the key may change what the product DOES, never what it SHOWS.

The other half of this boundary is already pinned in test_client.py — a keyless call never
carries the key even when one is exported, and a keyed call without a key refuses before
touching the network. This is the leak side: with a key exported, the CLI must say a keyed
call was made (so a keyed run can never pass as a keyless one) and must never print or write
the key itself — not on the card, not in the receipt, not in the JSON a judge opens."""

import json
import uuid

from conftest import FakeOpener, envelope
from test_lookup import MS_ASSET, MS_INFO, MS_MAP_ROW, snapshot

from shelfware import cli
from shelfware.client import Client


def noop(_):
    pass


def test_an_exported_key_is_named_as_used_but_never_printed_or_written(
    monkeypatch, capsys, tmp_path
):
    key = str(uuid.uuid4())  # the real shape: a CoinMarketCap key is a UUID
    op = FakeOpener(
        (200, envelope({"rwa_assets": [MS_ASSET]}, credit_count=1)),  # roster, keyed
        (200, envelope([MS_MAP_ROW])),  # state, keyless
        (200, envelope(MS_INFO)),  # listing date, keyless
    )
    monkeypatch.setattr(
        cli, "Client", lambda api_key=None: Client(api_key=key, sleep=noop, opener=op)
    )
    monkeypatch.setattr(cli, "api_key", lambda: key)
    monkeypatch.setattr(cli, "_load_roster_snapshot", snapshot)
    out_json = tmp_path / "ms.json"

    rc = cli.main(["MS", "--json", str(out_json)])
    out = capsys.readouterr().out

    assert rc == 0
    # the keyed call happened, and only on the keyed base
    assert op.requests[0].get_header("X-cmc_pro_api_key") == key
    assert all(r.get_header("X-cmc_pro_api_key") is None for r in op.requests[1:])
    # ...and the run says so, so it can never be mistaken for the keyless path
    assert "roster: live (1 credit)" in out
    assert "keyed" in out and "1 credit" in out
    # ...but the key itself reaches no surface a judge reads
    assert key not in out
    written = out_json.read_text()
    assert key not in written
    receipt = json.loads(written)
    calls = [receipt["roster"]["call"], receipt["status"]["call"], *receipt["status"]["info_calls"]]
    assert [c["keyed"] for c in calls] == [True, False, False]
    assert not any(key in json.dumps(c) for c in calls)
