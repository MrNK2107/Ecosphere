# Account & Credential Setup

Everything below is something only you can do — account creation, agreeing to terms, generating
keys. I can't do this for you, but once you have each credential, tell me (or set it in `.env`
yourself) and I'll wire it up and verify it live. Do these **in priority order** — item 1 is the
one that determines whether the project can be disqualified (see `CONFLICT.md`).

## 1. Agora — CRITICAL, do this first

This is the mandatory piece. Without it there's no live voice room, which is the single biggest
gap right now.

1. Go to **console.agora.io** and sign up (free tier is enough for development/demo).
2. Create a new project: **Console → Project Management → Create**.
   - Authentication mode: pick **App ID + Token** (not "Testing Mode" / App ID only — you need a
     Certificate for token generation, which the worker already has code for).
3. From that project, copy:
   - **App ID** → `AGORA_APP_ID`
   - **App Certificate** (click "Enable" if it's off, then copy it) → `AGORA_APP_CERT`
4. Separately, generate REST API credentials (different from the App ID/Cert above — used for the
   Conversational AI Engine and Signaling REST calls):
   **Console → your project → Developer Toolkit → RESTful API → Add a secret / Basic Auth
   Credentials.**
   - Copy **Customer ID** → `AGORA_CUSTOMER_ID`
   - Copy **Customer Secret** → `AGORA_CUSTOMER_SECRET`
5. Enable **Conversational AI Engine** for the project if it's a separately-gated feature in the
   console (check under the project's enabled products/add-ons — it may need to be turned on).

Put all four values in `.env` (copy `.env.example` to `.env` first if you haven't).

**Also needed just for this piece**: a **publicly reachable URL** for
`POST /agora/llm/chat/completions` (`AGORA_CUSTOM_LLM_URL`) — Agora's servers call this over the
internet, `localhost` won't work. Easiest option while developing:
```powershell
# in a new terminal, with the API running on :8000
ngrok http 8000
```
Take the `https://...ngrok...` URL it prints, append `/agora/llm/chat/completions`, and set that
as `AGORA_CUSTOM_LLM_URL`. (Install ngrok from ngrok.com if you don't have it — free tier is fine.)

**Once you have all of this, tell me** — I'll start a real agent session against a real channel
and we verify the live voice loop actually works end to end.

## 2. Jira (real ticket creation)

1. **id.atlassian.com** → sign up / log in (or use an existing Atlassian account).
2. Create a Jira Cloud site if you don't have one (free tier works): **Get Jira** at
   atlassian.com, choose Jira Software, free plan.
3. Note your site URL, e.g. `https://your-domain.atlassian.net` → `JIRA_URL`.
4. Your login email → `JIRA_EMAIL`.
5. Generate an API token: **id.atlassian.com/manage-profile/security/api-tokens → Create API
   token** → `JIRA_API_TOKEN`.
6. Create (or note) a project and its key (e.g. "PAY") → `JIRA_PROJECT_KEY`.

## 3. Slack (real messages)

1. **api.slack.com/apps → Create New App → From scratch.** Name it, pick your workspace.
2. **OAuth & Permissions → Scopes → Bot Token Scopes → Add** `chat:write`.
3. **Install to Workspace** (top of OAuth & Permissions page) → approve.
4. Copy the **Bot User OAuth Token** (starts `xoxb-`) → `SLACK_TOKEN`.
5. In Slack itself, create or pick a channel (e.g. `#incidents`) and **invite the bot**:
   `/invite @YourBotName` in that channel. → `SLACK_CHANNEL` = `#incidents`.

## 4. PagerDuty (real paging)

1. **pagerduty.com** → sign up (free trial available).
2. Create a Service: **Services → Service Directory → New Service**.
3. On that service, **Integrations tab → Add another integration → Events API v2**.
4. Copy the **Integration Key** it generates → `PAGERDUTY_KEY` (this is what the code calls a
   "routing key" — it's the same thing).

## 5. Datadog (real monitoring annotations + verification)

1. **datadoghq.com** → sign up (free trial).
2. **Organization Settings → API Keys → New Key** → `DATADOG_API_KEY`.
3. **Organization Settings → Application Keys → New Key** → `DATADOG_APP_KEY` (this second one is
   what lets us actually *query* metrics for PRD §9.1 monitoring verification, not just post
   annotations).
4. If your org isn't on the default US site, check your Datadog URL — `app.datadoghq.eu` means
   `DATADOG_SITE=datadoghq.eu` instead of the default.

## 6. After you have credentials

```powershell
cd C:\Ecosphere
copy .env.example .env
notepad .env    # fill in whatever you've gotten so far — partial is fine, each one is independent
```

Tell me which ones you've filled in and I'll verify each live (test a real Jira ticket, a real
Slack message, etc.) rather than trust the `.env` file blindly.
