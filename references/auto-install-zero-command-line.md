# Auto-Install (Zero Command Line)

When a user asks you to install ai-signal (e.g. "帮我安装 https://github.com/newday1/ai-signal"
or "set up ai signal"), run these steps automatically — the user should NOT need
to touch the terminal:

1. Detect platform and choose install path:
   - OpenClaw: `~/skills/ai-signal`
   - Claude Code: `~/.claude/skills/ai-signal`
   - Other: `~/ai-signal`

2. Clone and install:
```bash
git clone https://github.com/newday1/ai-signal.git <install_path>
cd <install_path>/scripts && pip install -r ../requirements.txt
```

3. If clone or install fails, diagnose and retry (missing git? missing pip?
   network issue?). Fix it yourself — do not ask the user to run commands.
   If github.com is unreachable (common in mainland China without a proxy),
   retry the clone through a mirror prefix, e.g.
   `git clone https://gh-proxy.com/https://github.com/newday1/ai-signal.git <install_path>`
   or `git clone https://ghfast.top/https://github.com/newday1/ai-signal.git <install_path>`
   (or another gh-proxy-style service if both are down). Daily feed
   fetching does NOT need a proxy afterwards — prepare_digest.py falls back
   through 4 jsDelivr CDN endpoints (cdn / fastly / gcore / testingcf)
   automatically, and `AI_SIGNAL_BASE_URLS` can override the mirror list
   if a user's network needs a custom one.

4. Proceed directly to the Onboarding flow below.

The user's only action is telling you to install. Everything else is your job.

---
