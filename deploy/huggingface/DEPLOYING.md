# Moving the API to Hugging Face Spaces

## Why

Render's free tier gives this service **0.15 of a CPU core and 512 MB**, and
spins it down after about fifteen minutes of inactivity. Hugging Face Spaces'
free CPU tier gives **2 vCPU and 16 GB**, and sleeps after 48 hours rather than
fifteen minutes.

Two caveats worth reading before moving:

* **Most of the latency was ours, not Render's.** Scoring an observation costs
  about 7.5 CPU-seconds — seven neural forward passes — and it used to happen
  on the request path, which at 0.15 cores was close to fifty seconds. That is
  now precomputed as each observation lands (see `service.precompute`), so a
  request costs ~0.05 CPU-seconds. The CPU cap is no longer the bottleneck.
* **What Spaces still buys you** is the 48-hour sleep instead of fifteen
  minutes, and enough headroom that the transformer never contends for the cap.
  A cold start on Render is ~50 s; that is the remaining reason to move.

## Steps

The Space builds from a git repo containing a `Dockerfile` and a `README.md`
with Spaces front matter, both of which are in this repository.

1. Create the Space: <https://huggingface.co/new-space>
   * **Owner** — your account
   * **Space name** — `rainshield-api`
   * **License** — as you prefer
   * **SDK** — **Docker**, blank template
   * **Hardware** — CPU basic (free)
   * **Visibility** — Public

2. Add it as a remote and push this repository to it:

   ```bash
   git remote add hf https://huggingface.co/spaces/<your-username>/rainshield-api
   git push hf main
   ```

   Authenticate with a **write** access token from
   <https://huggingface.co/settings/tokens> (username = your HF username,
   password = the token).

3. Replace the Space's `README.md` with `deploy/huggingface/README.md` from
   this repo — Spaces reads the YAML front matter at the top of the root
   `README.md` to learn it is a Docker Space on port 7860. Without it the
   build is ignored.

   ```bash
   cp deploy/huggingface/README.md README.md
   git commit -am "Space front matter" && git push hf main
   ```

   Keep this on a branch you push only to `hf`, so the project README on
   GitHub stays as it is.

4. Watch the build in the Space's **Logs** tab. It should end with
   `Application startup complete` and a warm-up line per region.

5. Point the dashboard at it. In Vercel → Settings → Environment Variables set

   ```
   VITE_API_BASE = https://<your-username>-rainshield-api.hf.space
   ```

   then **redeploy** — Vite inlines `VITE_*` at build time, so the variable
   alone does nothing to an existing bundle. That value overrides the
   `.env.production` default committed in this repo.

6. Check it directly before switching anyone over:

   ```bash
   curl https://<your-username>-rainshield-api.hf.space/health
   ```

## Environment variables

Set these under the Space's **Settings → Variables and secrets**. None are
secret; all have working defaults.

| Variable | Suggested | Why |
| --- | --- | --- |
| `RAINSHIELD_PROVIDER` | `auto` | no preferred upstream; the whole chain is tried |
| `RAINSHIELD_USER_AGENT` | `RainShield/1.0 (you@example.com)` | **MET Norway's terms require a contact address.** Without it met.no may start refusing, and it is the source carrying the feed while Open-Meteo is rate-limited |
| `RAINSHIELD_CORS_ORIGINS` | `*` | public read-only API, no credentials sent |
| `RAINSHIELD_CACHE_TTL` | `600` | seconds an observation is reused |

`PORT` is set by the Dockerfile and Spaces; leave it alone.

## What does not carry over

* **Render's `render.yaml` does not apply here** and the two can drift, which
  has already caused one outage. If the Space becomes the real backend, point
  `.env.production` at it and retire the Render service rather than leaving
  both running against the same branch.
* Open-Meteo will still return `HTTP 429` — its free tier is capped per IP and
  cloud egress addresses are shared. That is expected, and MET Norway carries
  the feed. `degraded=False` in the logs means the data is live.
