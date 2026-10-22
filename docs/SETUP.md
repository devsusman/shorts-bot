# Setup, step by step

Total time: about 2 to 3 hours the first time, mostly waiting for developer-account pages. **Do the steps in order. Get YouTube working first, then add TikTok and Instagram one at a time.**

Cost: $0. The only thing that can cost money is GitHub Actions minutes on a **private** repo (2,000 free minutes a month). Each of the 4 daily runs includes a wait until the exact publish time, so a private repo will probably run out. **Use a public repo** (unlimited minutes) or set `LEAD_MINUTES` to 0 (see Part 9).

---

## Part 1. Accounts and keys you need (all free)

| What | Where | Used for |
|---|---|---|
| GitHub account | github.com | runs everything |
| Gemini API key | aistudio.google.com/apikey | writes the scripts (first choice) |
| Groq API key | console.groq.com/keys | script fallback (optional but recommended) |
| Pixabay API key | pixabay.com, sign up, then open pixabay.com/api/docs and copy the key shown | stock footage (required) |
| Healthchecks.io | healthchecks.io | dashboard + "it didn't run" email alerts |
| Gmail app password or Slack webhook | see Part 7 | failure alerts |

Pexels is not used: ShortSmash's own notes say Pexels paused new API keys on 2026-09-30, and Pixabay is its default.

---

## Part 2. Put the code on GitHub

1. Create an empty **public** repository on github.com (example name `shorts-bot`). Do not add a README.
2. Unzip this project. In a terminal inside the folder:
   ```
   git init
   git add .
   git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_NAME/shorts-bot.git
   git push -u origin main
   ```
3. On GitHub open **Settings, Actions, General, Workflow permissions**, choose **Read and write permissions**, click Save. (The bot commits its status page.)

---

## Part 3. Add the keys that make video generation work

Open your repo, **Settings, Secrets and variables, Actions, New repository secret**. Add:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | key from Google AI Studio |
| `GROQ_API_KEY` | key from Groq (optional) |
| `PIXABAY_API_KEY` | key from Pixabay |

Then open the **Variables** tab and add one variable: `PLATFORMS` = `youtube` (so only YouTube is attempted until you finish the other two).

Shortcut for later: fill `.env.secrets.example` (copy to `.env.secrets`) and run `python tools/set_secrets.py YOUR_NAME/shorts-bot`. It needs the GitHub CLI (`gh auth login` first).

---

## Part 4. YouTube (required)

1. Go to console.cloud.google.com, sign in with the Google account that owns your YouTube channel.
2. Top bar, project dropdown, **New project**, name it, Create.
3. Menu, **APIs & Services, Library**, search **YouTube Data API v3**, click **Enable**.
4. **APIs & Services, OAuth consent screen** (may be called "Google Auth Platform"). Choose **External**. Fill the app name and your email. Add your own Gmail as a **test user**.
5. **Important:** on the same screen click **Publish app** so the status is **In production**. If you leave it in Testing, the login expires after 7 days and uploads stop. (Google will warn the app is unverified; that is fine for your own account.)
6. **Credentials, Create credentials, OAuth client ID**, type **Desktop app**, Create, then **Download JSON**. Rename it `client_secret.json` and put it in the project folder.
7. On your computer: `pip install google-auth-oauthlib` then `python tools/youtube_auth.py`. A browser opens. Choose your channel account, click **Advanced, Go to app (unsafe)**, allow. The terminal prints one line of JSON.
8. Copy that whole line into a GitHub secret named `YT_OAUTH_JSON`.

**Big caveat (my understanding of YouTube's rules, please verify):** videos uploaded through the API by an *unaudited* API project are forced to **private**. You can still open YouTube Studio and set them public by hand, or apply for YouTube's "API Services audit" to lift it. The bot reports `privacy=private` in the log and in `STATUS.md` when this happens.

---

## Part 5. Healthchecks.io (your dashboard and missed-run alerts)

1. Sign up at healthchecks.io (free plan, up to 20 checks).
2. Create **4 checks**, one per slot. For each: set the **Schedule** to **Cron**, the time zone to **Asia/Karachi**, and the expression:
   - 10am check: `0 10 * * *`
   - 11am check: `0 11 * * *`
   - 10pm check: `0 22 * * *`
   - 11pm check: `0 23 * * *`
   Set **Grace time** to **40 minutes**.
3. Under Integrations, make sure **Email** is on (it is by default).
4. Open each check and copy its **ping URL** (looks like `https://hc-ping.com/xxxxxxxx-...`).
5. Add four GitHub secrets: `HC_URL_10AM`, `HC_URL_11AM`, `HC_URL_10PM`, `HC_URL_11PM`.

If a slot is skipped (GitHub delay), crashes, or never starts, Healthchecks emails you when the grace time runs out.

---

## Part 6. Test before going live

1. Repo, **Actions** tab, left side **video-10am**, **Run workflow**, tick **dry_run**, run it.
2. Open the run and watch the steps. A dry run writes a script, builds the full video, and publishes nothing.
3. If it is green: check `STATUS.md` in the repo (a new row should appear) and Healthchecks (the check turns green).
4. Now run it again with **dry_run unticked**. This posts one real video to YouTube.
5. Check the video on YouTube (and its privacy, see the caveat in Part 4).

If a step fails, click it, read the red lines, and tell me the error text.

---

## Part 7. Failure and reminder alerts (pick email or Slack, or both)

**Email through Gmail**
1. Turn on 2-Step Verification for the Gmail account. Then at myaccount.google.com/apppasswords create an **app password** (16 characters).
2. Add secrets: `SMTP_SERVER` = `smtp.gmail.com`, `SMTP_PORT` = `465`, `SMTP_USERNAME` = your Gmail address, `SMTP_PASSWORD` = the app password, `ALERT_EMAIL_TO` = where to send alerts.

**Slack**
1. api.slack.com/apps, Create app, From scratch, **Incoming Webhooks**, turn on, **Add New Webhook to Workspace**, pick a channel, copy the URL.
2. Add secret `SLACK_WEBHOOK_URL`.

Every alert contains the time slot, the failing step name and a link to the run log.

---

## Part 8. TikTok (add after YouTube works)

**Reality check first**
- TikTok's rules (as I understand them): an unaudited app can only send videos to your **inbox/drafts**; you open TikTok once a day and tap **Post**. Direct publishing needs app review, which takes roughly 2 to 4 weeks. The bot defaults to inbox mode.
- Until your app passes review it may only work for accounts you add as sandbox/test users.

**Steps**
1. Go to developers.tiktok.com, log in, **Manage apps, Connect an app** (organization or individual).
2. Fill name, icon, description. Under **Products** add **Login Kit** and **Content Posting API**.
3. Under Login Kit set a **Redirect URI**. It must be `https`. Easy option: enable GitHub Pages on your repo and use `https://YOUR_NAME.github.io/shorts-bot/` (it can be a 404 page; you only need the address bar).
4. Under **Scopes** add `user.info.basic`, `video.upload`, `video.publish`.
5. In the app's **Sandbox** tab, add your TikTok account as a target user if TikTok asks for it.
6. Copy the **Client key** and **Client secret**.
7. On your computer run `python tools/tiktok_auth.py`. It prints a URL; open it, log in, approve. Your browser lands on your redirect address. **Copy the full address from the address bar** and paste it into the terminal.
8. The script prints your refresh token. Add GitHub secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`.
9. Set the repository variable `PLATFORMS` to `youtube,tiktok`. Leave `TIKTOK_MODE` unset (inbox).
10. After approval of your app by TikTok, you can set variable `TIKTOK_MODE` = `publish` and `TIKTOK_PRIVACY` = `PUBLIC_TO_EVERYONE`. Before approval keep inbox.

TikTok may rotate your refresh token. For the bot to save the new one automatically, create a GitHub **fine-grained personal access token** (repo access: this repo; permissions: Secrets read/write, Variables read/write) and store it as secret `GH_PAT`. Without it, if TikTok starts rejecting the token, re-run `tools/tiktok_auth.py`.

---

## Part 9. Instagram (add last)

**Requirements:** an Instagram **Business or Creator** account (Settings, Account type and tools, Switch to professional account).

1. developers.facebook.com, **My apps, Create app**, choose **Business** (or the option that includes the Instagram API), name it.
2. In the app dashboard add the product **Instagram**, then choose **API setup with Instagram login**.
3. In **App roles, Roles**, add your Instagram account as an **Instagram Tester**, then accept the invite inside Instagram (Settings, Website permissions, Apps and websites, Tester invites).
4. Back on the Instagram API setup page, **Generate token** for your account with permissions `instagram_business_basic` and `instagram_business_content_publish`. Copy the short-lived token.
5. Make it last 60 days: `python tools/ig_token.py exchange` (needs the **Instagram app secret** from the same page). It prints a long-lived token and today's date.
6. Find your id: `python tools/ig_token.py whoami` and note the `user_id`.
7. GitHub secrets: `IG_USER_ID`, `IG_ACCESS_TOKEN`. GitHub **variable**: `IG_TOKEN_ISSUED` = the date printed (YYYY-MM-DD).
8. Variable `PLATFORMS` = `youtube,tiktok,instagram`.

**How video reaches Instagram:** Instagram can only fetch from a public web address, so the bot first uploads the MP4 to **catbox.moe** (free, no account) and gives Instagram that URL. Catbox files are public. If catbox is unreachable it falls back to litterbox (72-hour temporary link).

**Token reminders:** every run checks `IG_TOKEN_ISSUED`. At fewer than 7 days left it tries to refresh the token itself (needs `GH_PAT`) or sends you an email or Slack reminder with what to do. Manual refresh: `python tools/ig_token.py refresh`, then update `IG_ACCESS_TOKEN` and `IG_TOKEN_ISSUED`.

If Instagram says an API version is retired, set the repository variable `IG_API_VERSION` to a current one (the default is `v23.0`).

---

## Part 10. Timing: what to expect and how to change it

- Your four times (Asia/Karachi): 10:00, 11:00, 22:00, 23:00. In UTC that is 05:00, 06:00, 17:00, 18:00.
- The workflows start **20 minutes earlier** (04:40, 05:40, 16:40, 17:40 UTC) so the video is finished by the target time, and the bot then waits and publishes at the target time. It also avoids GitHub's busiest moment (top of the hour).
- GitHub says scheduled runs can be delayed. If a run starts more than **15 minutes** late, the time-verification job **skips it** and notifies you ("delayed skip").
- To change timezone or lead time: `python tools/gen_workflows.py --tz Asia/Karachi --lead 20`, commit and push. Timezones with daylight saving need this re-run twice a year.
- If the render plus upload takes longer than the lead time, posts will land late. After your first few real runs, check the run duration and raise `--lead`.
- For exact-to-the-minute timing, use cron-job.org (free) to call GitHub's workflow_dispatch API at the exact time and set `--lead 0`.
- Public repos: GitHub pauses scheduled workflows after 60 days with no repo activity. The status commits count as activity, so it keeps itself alive while runs succeed.

---

## Part 11. Daily life

- **Dashboard:** `STATUS.md` in your repo (a table of every run with links and errors) plus the Healthchecks page.
- **TikTok in inbox mode:** once a day open TikTok, go to your inbox/drafts and tap Post on the new videos.
- **Instagram token:** keep `IG_TOKEN_ISSUED` right.
- **No secrets in code:** everything sensitive lives in GitHub Secrets. Never commit `client_secret.json` or `.env.secrets` (they are in `.gitignore`).

---

## What I tested and what I could not

Tested here with real code (19 automated tests, `pytest`): UTC cron conversion, the late-run skip logic, script JSON validation with retries and provider fallback, scene building, a **real ShortSmash render to 1080x1920 with burned-in captions** (voice replaced by a test tone, placeholder footage), the memory fix, the TikTok and Instagram request sequences against mocked servers, token-expiry logic, status page and alert text.

**Not tested** (needs your accounts or internet access this environment did not have): Gemini and Groq calls, Edge-TTS voice, Pixabay downloads, faster-whisper's model download, catbox, and the real YouTube, TikTok and Instagram APIs. The GitHub Actions workflows were only checked as valid YAML and logic, never run on GitHub. Expect to fix a small thing or two on the first dry run; send me the error text.

Known risks: platform rules change (TikTok review, YouTube audit lock, Instagram API versions), the free Gemini tier limits can change, and four near-identical AI-voiced stock-footage videos a day can run into YouTube's "inauthentic content" monetization policy.
