# Beta model readiness

September 12, 2026. The beta health endpoint now reflects terminal state in an existing model instance. It remains a lightweight process-readiness check and does not construct the lazy model, load a credential, initialize a transport, contact Tinker, or submit generation.

A fresh process with no model instance returns HTTP 200 and `ready: true`; this preserves the launch behavior that lets the service start before the first reader request. This is not a provider, credential, checkpoint-expiry, or inference preflight. Those checks still occur on first model use.

After a model instance exists, the endpoint reads its local status. A model marked `blocked` after an uncertain provider request, a closed model, or an otherwise explicitly unready model makes `/health` return HTTP 503 with `ready: false`. The response exposes no provider exception or private operational detail. Busy generation remains healthy and is reported separately; concurrent submissions continue to receive the existing busy response.

New chat submissions check an existing model's `blocked`, `closed`, and explicit readiness state while holding the application lock and before creating a request ID or reserving cost and question quota. A blocked response is therefore not a new billable attempt and does not consume another question. It also does not retry the uncertain request. An invalid or unreadable status fails closed as locally unavailable rather than creating a reservation.

When the model is blocked, restart the application through the normal deployment process. The restart closes the old local transport and creates a fresh lazy application state. Preserve the existing usage ledger: an earlier uncertain request remains conservatively accounted, and readiness recovery is not authorization to reset billing, replenish quota, retry the old request, replace retained B, or add a queue. Review the provider separately if the original uncertain outcome needs reconciliation.

## Bounded worker-pool follow-up

The concurrent beta evaluates readiness across independent model slots. A blocked/closed slot retires; healthy or lazy slots can continue serving. When all slots are unavailable, health returns 503 and new questions reject before reservation. Waiting requests that cannot be submitted are released, while submitted uncertain requests are never automatically reassigned or retried. See [the concurrency record](CONCURRENT-BETA.md) for capacity and validation. The deployment remains a single process and replica.
