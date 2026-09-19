# Security Policy

## Supported versions
| Version | Supported |
|---|---|
| latest (`main`) | ✅ |

## Reporting a vulnerability
Please do not open a public issue for anything exploitable. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) (Security → Report a
vulnerability) or email **edy.cu@live.com**. You will get an acknowledgment within 48 hours.

## Secrets posture
**The repository, the CI and the judged path carry no secret.** The state leg of the ticker
question is CoinMarketCap's keyless `/public-api` surface; the wrapper roster is a committed
snapshot of a keyed run. The one credential in the wider workflow — a free CoinMarketCap key that
takes the daily snapshot and serves the site's `/api/roster` — lives in `~/.config/coinmarketcap/`
and in the Vercel deployment's environment, never in this tree.

## The boundary is tested, not asserted
| Claim | Test |
|---|---|
| A keyless call never carries the key, even when one is exported | `tests/test_client.py::test_keyless_call_never_sends_the_key_even_when_one_is_exported` |
| A keyed call without a key refuses before touching the network | `tests/test_client.py::test_keyed_call_without_a_key_refuses_before_touching_the_network` |
| With a key exported, the run says a keyed call was made and the key reaches no output — card, receipt or JSON | `tests/test_permission_boundary.py::test_an_exported_key_is_named_as_used_but_never_printed_or_written` |
| `/api/health` reports only a boolean about the key | `tests/api.test.mjs` — "health: reports the census date and only a boolean about the key" |
| A UUID-shaped string in any tracked file fails the readiness gate | `tests/test_readiness.py::test_a_key_shaped_string_in_a_tracked_file_is_caught` |
| The RWA family still refuses keyless calls (403 error 1005), so the roster can never silently go live without a key | `tests/test_live.py::test_live_rwa_family_is_keyed_by_coinmarketcap` |

## Scanning
`gitleaks` on every push over the full history with a project rule for the CoinMarketCap key
shape (`.gitleaks.toml`), CodeQL weekly and on pull requests for Python and JavaScript,
`pip-audit` in CI, Dependabot monthly. The site's proxy functions have no dependencies.
