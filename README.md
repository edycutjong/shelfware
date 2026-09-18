# Shelfware

**Six in ten tokenised stocks on CoinMarketCap have no wrapper with a tracked market.**

CoinMarketCap's RWA surface says whether an asset is tokenised (`has_tokens: true`). It does not
say whether any wrapper of it has a market. Shelfware joins the wrapper roster
(`/v5/real-world-assets/quotes/latest` → `tokens[]`, including the `price: null` rows every
price-based tool filters out) to each wrapper's listing state
(`/public-api/v1/cryptocurrency/map`, keyless) and counts what the boolean hides.

```bash
python3 -m shelfware MS        # does Morgan Stanley have a wrapper that trades, and whose? no key, no install
```

Endpoints used (all named explicitly, see `ARCHITECTURE.md`):

```
/v5/real-world-assets/map              universe: every underlying + has_tokens         keyed · 0 credits
/v5/real-world-assets/quotes/latest    tokens[] wrapper roster incl. price:null rows   keyed · 1 credit / 250 assets
/v5/real-world-assets/issuers/list     issuer registry, num_tokens declared            keyed · 1 credit
/public-api/v1/cryptocurrency/map      listing state, birth date, chain per wrapper    keyless · 0 credits
/v1/key/info                           credit accounting in the receipt               keyed · 0 credits
/v5/real-world-assets/market-pairs/list   NOT USED — 403 error 1006 on the Startup plan (docs say Basic)
```

Built for the Build with CMC: API Hackathon (DoraHacks), Real World Assets track. MIT.
