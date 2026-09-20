"""Shelfware — which tokenised stocks on CoinMarketCap actually have a market.

Stdlib only. Four CoinMarketCap ledgers, one join, three counting rules:

    A  /v5/real-world-assets/map             every underlying, has_tokens      keyed, 0 credits
    B  /v5/real-world-assets/quotes/latest   tokens[] per underlying           keyed, 1 credit/250
    C  /v5/real-world-assets/issuers/list    num_tokens each issuer declares   keyed, 1 credit
    D  /public-api/v1/cryptocurrency/map     status per crypto_id              keyless, 0 credits

    shelf(wrapper)            = D.status == "untracked"
    zero_tracked(underlying)  = every wrapper of it is on the shelf   (unresolved ids never count)
    shelf_rate(issuer)        = shelf wrappers / attached wrappers
"""

from shelfware.client import Client, api_key
from shelfware.delta import delta
from shelfware.join import census, hero, recount
from shelfware.lookup import lookup

__all__ = ["Client", "api_key", "census", "delta", "hero", "lookup", "recount"]
__version__ = "1.0.1"
