# Manual demo testing

A ~15-minute walkthrough of every demo flow. Run it before judging, after any merge, and after Vultr restarts.
Each step says what to type, what you should see, and what to do if it doesn't happen.

## 0. Setup

**Against your laptop** (use this to test a branch before merging). Two PowerShell terminals at the repo root, venv active:

```powershell
git fetch
git checkout <branch>
git pull
$env:DATABASE_URL="sqlite:///./agentforge.db"
uvicorn server.main:app --port 8000
```

```powershell
cd web
$env:VITE_API_TARGET="http://localhost:8000"
npm run dev
```

**Against Vultr** (what judges see): only the second terminal, without `VITE_API_TARGET`. If it's still set in that terminal, run `Remove-Item Env:VITE_API_TARGET` first.

```powershell
cd web
npm run dev
```

Open http://localhost:5173.

**Before you start:** `python -m tools.check_keys --latency --write` picks the Gemini model that's answering fastest right now. If it changes, Vultr's `.env` needs the same `GEMINI_MODEL` and a restart.

Gemini calls cost a little on the billed key (well under a cent per chat); the stress test is the expensive one (~25 calls).

## 1. Agents page
- [ ] Smart Spend and News Monitor show **Deployed**.
- [ ] Each agent shows **"Audited · N figures checked in M runs"** (or "No runs yet").
- [ ] **Templates** include Smart Spend, News Monitor, **Quick Quote**, Custom.

## 2. Fact-check: someone else's price (Smart Spend → Open chat)
Type:
```
Someone told me my Logitech MX Master 3S mouse is $59 on Amazon. Is that true?
```
- [ ] Answer in ~10–30 s. Figures **stamp in** one by one; the counter ticks up.
- [ ] Green ✓ chips for real prices (about **$79.99** at Logitech / Best Buy, **$109** paid). Dashed red chips for **$59**.
- [ ] **Hover** a green chip: its "Data used" card lights up, a dashed line connects them, tooltip says the tool and step.
- [ ] **Click** a green chip: evidence card with the listing (title, seller, "Open source" link). **Click** the dashed $59: "came from your message", with your question quoted. Esc closes it.
- [ ] Fact-check list: $59 = "From your message, no tool confirms it".
- [ ] **Verify record** on the Audit receipt → **"Record intact"**.

If no price is verified, Google Shopping probably returned junk this time. Ask again and the agent will retry with a fuller name. Don't use AirPods Pro 2 for the price half of the demo, since its results are resale only.

## 3. Demo account
- [ ] Chat header → **Demo account**: 11 purchases (incl. **Logitech MX Master 3S, Amazon, $109**) and 3 bills ($121.98/mo). Label says Live or Demo data. Esc closes it.

## 4. Bill savings (Smart Spend)
```
How can I save money on my monthly bills?
```
- [ ] Cheaper plan + price for AT&T, Netflix, Spotify, with monthly and yearly savings.
- [ ] (Almost) every figure green. Clicking a saving shows the two prices it came from.

## 5. Self-correction (Quick Quote)
Agents page → Templates → **Quick Quote** → Deploy → Open chat → first suggestion:
```
What do AirPods Pro 2 usually cost, and what's a good Black Friday price to wait for?
```
- [ ] **"Self-corrected · N figures had no tool data…"** strip above the answer. **Show draft** → made-up prices crossed out, each marked "removed" (or "now verified").
- [ ] The final answer has no unbacked prices.

If there's no strip, Gemini didn't guess this time. That isn't a bug. Ask again or rephrase ("roughly what do they cost?"). For the demo, keep a run that worked open in a tab or reachable from Observability.

## 6. Compare (Smart Spend → Compare)
- [ ] Click **"Netflix just raised prices by 40%…"**. Left (no fact-check) answers with unmarked numbers; right (audited) verifies $24.99, flags the 40% as yours, and may show "Self-corrected".
- [ ] First use creates an agent named **"Smart Spend (no fact-check)"**: expected. Delete it before judging if you want a clean agents page.

## 7. Stress test (Smart Spend → Stress test)
- [ ] **Run stress test**: rows run one at a time (~1–2 min total).
- [ ] Scorecard: **"X of X unbacked figures caught"**, plus counts for checked, backed, user's numbers, made up, corrected.
- [ ] "Open run" on a row opens its run page.

## 8. Receipts and audit (Observability)
- [ ] Open any run: answer shows chips; **Audit receipt → Verify record → "Record intact"**; **Show the fingerprint chain** lists every step.
- [ ] Dashboard → **Audit the last 25 runs** → "N of N receipts intact" (older runs from before receipts are counted separately).
- [ ] CLI check of one run: `python -m server.runtime.receipt RUN_ID --api http://144.202.28.129:8000` → `OK Record intact…`

## 9. Builder: describe an agent (experimental)
- [ ] Builder → new agent → "Describe your agent in one sentence": `Finds tennis courts near UT Austin and compares racquet prices` → **Draft it**.
- [ ] Name, instructions, tools (Local places, Shopping…) and fact-check fill in. Deploy and ask it a question.

## 10. News Monitor
```
Brief me on NVIDIA and semiconductor supply chains.
```
- [ ] Story cards with source, date and "Read original" link; any $ figures verified.

## 11. Look and feel
- [ ] Sidebar **Light mode / Dark mode** toggle works and is remembered after reload.
- [ ] On a phone-width window, chat, stress test and compare stack without sideways scrolling.

## If something fails
| Symptom | Likely cause | Fix |
|---|---|---|
| "Gemini quota exceeded … PerDay" | The key's free tier is used up | Use the billed key; check AI Studio shows a paid tier |
| Every step takes ~30–60 s | A Gemini model is overloaded | `python -m tools.check_keys --latency --write`, update Vultr `.env`, restart |
| "Agent not found" on Vultr | Demo agents deleted but server not restarted | `systemctl restart agentforge` (agents re-seed on startup) |
| Old behavior on Vultr | Vultr hasn't pulled | `cd /opt/agent-forge && git pull && systemctl restart agentforge` |
| SerpApi "HTTP 400" | Unsupported location | Already retried automatically; ask again |
| No price verified for a product | Shopping results were resale/other models | Ask again, or use the MX Master 3S |
