# Chapter Of Life: zero-subscription cloud auto-publisher

**What it does:** GitHub Actions starts each day, Gemini generates original Hindi writing and an English caption, Pillow generates a branded 4:5 image. Optionally FFmpeg creates a simple 9-second silent 9:16 Reel (cropped from the image; not AI cinematic animation). Cloudinary serves the media at a public URL, and Instagram's official API publishes it. The job marks successfully posted dates in `history/` to discourage duplicates.

## 1. Accounts
- Instagram account `chapteroflife.__` must be **Creator or Business** (Professional).
- Create a Meta developer app with **Instagram API with Instagram Login**, authorize **your own Instagram account** with `instagram_business_basic` and `instagram_business_content_publish`, obtain an applicable long-lived account token and Instagram professional account ID. Follow Meta's onboarding and permission / token-lifetime requirements. Access / app review conditions differ for apps publishing for other users.
- Create a Google AI Studio API key and enable a free-tier text-generation model supported in your project.
- Create a free Cloudinary account; get cloud name, API key and secret.
- Create a **public** GitHub repository named `chapteroflife-automation`; don't put tokens in code.

## 2. Upload the files
Upload `main.py`, `requirements.txt`, and `.github/workflows/daily.yml` (preserve the nested directory). On GitHub, `Add file > Upload files`. The default branch should be `main`.

## 3. Add GitHub secret values
Repository -> Settings -> Secrets and variables -> Actions -> New repository secret:
- `GEMINI_API_KEY`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `IG_USER_ID` (numeric IG Professional account ID from the API, not username)
- `IG_ACCESS_TOKEN` (authorized publishing token, NOT your Instagram password)

Under **Variables** you may set:
- `POST_FORMAT` = `image` (or `reel`)
- `GEMINI_MODEL` = an enabled Gemini free-tier text model, initial default `gemini-2.5-flash`
- `IG_GRAPH_VERSION` = a currently supported Meta version, initial default `v24.0`; check Meta dashboard/docs when deploying.
- `IG_API_HOST` = `graph.instagram.com` for Instagram Login. If using Facebook Login instead you must set `graph.facebook.com`, and use that route's proper Page token, IG ID and permissions.

## 4. Test first
Actions -> Chapter Of Life - Daily AI Post -> Run workflow -> `dry_run=true` -> `image` -> Run. Download the `chapteroflife-preview` artifact to inspect the output. If Hindi rendering looks wrong, inspect your runner's Noto font availability.

Once ready, use Run workflow with `dry_run=false`, and then the scheduled job handles future runs. IMPORTANT: `dry_run=false` publishes to your real Instagram account immediately.

## 5. Scheduling
The example cron is `17 14 * * *` (14:17 UTC = **7:47 PM IST**). GitHub schedules can be delayed/missed at busy times, and scheduled public-repo workflows are automatically disabled after 60 days of repository inactivity. Re-enable / keep the repository maintained. GitHub runners are on-demand, not a persistent 24/7 server.

## 6. Safety and reliability
- Public GitHub repo: **never** commit keys, tokens, personal data, customer data, or private drafts. Actions secrets are injected at runtime.
- Free Gemini/Cloudinary limits and eligibility can change; check current pricing and free tier before use. Video CDN credits may be spent faster.
- Instagram media needs to be reachable by Meta at the public URL.
- Access tokens expire or may be revoked; configure renewal / refresh for long-term unattended operation. This starter does **not** automatically refresh tokens or alert you on failure.
- GitHub action can re-run on a failed push after Instagram published but before marker was saved; in that edge case duplicates are possible. Monitor Actions/email notifications.
- Completely hands-off creative quality is not assured. The system blocks extremely long designs, but it cannot guarantee originality, typography and factual accuracy. Preview manually before enabling unattended publishing.
- API onboarding may involve Meta dashboard setup and verification. Code cannot bypass those requirements.
- Without an external duplicate-history API, topics may eventually repeat despite day-of-week theme changes.
- Reels here are **silent motionless image-based video**; for motion, music, cinematic sequences or voiceovers, extend the renderer later.

## Official references
- https://www.postman.com/meta/instagram/overview
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://ai.google.dev/gemini-api/docs/pricing
- https://cloudinary.com/pricing
