HackTX 2026 — Agent Forge: 24-Hour Execution Plan
Mission
Build Agent Forge, a platform where users configure, deploy, and monitor specialized AI agents that use real external tools.
Core pitch: Anyone should be able to turn a natural-language instruction into a working AI agent, connect it to real APIs, deploy it, and observe exactly what it does.
The product must prove four things in one continuous interaction:
Build: Choose a template, configure instructions and tools, and set guardrails.
Deploy: Save the agent configuration and make it accessible through its own chat page.
Execute: Gemini reasons about the request, selects tools, executes real API calls, and uses the returned data to answer.
Observe: Every model call and tool execution is recorded and displayed in a monitoring dashboard.
Do not build a collection of disconnected API demos. Build one functioning agent platform with two convincing examples.

1. The two showcase agents
Agent A: Smart Spend — the primary demo
Target user: Someone who wants to understand spending patterns and find ways to save money.
Example prompt:
Analyze my spending, identify the three biggest opportunities to save money, and find cheaper alternatives for products I frequently purchase.
Expected agent workflow
Gemini interprets the user's goal and decides which tools are needed.
The Nessie accounts tool retrieves account information.
The Nessie purchases tool retrieves transactions and purchase history.
The Nessie bills tool retrieves bills and recurring expenses where available.
The agent summarizes actual spending patterns and identifies potential savings opportunities.
The SerpApi Shopping tool searches for cheaper product alternatives based on the purchase history.
Gemini combines the retrieved information into an evidence-backed savings plan.
The run appears in the monitoring dashboard with individual model and tool steps.
What the judge sees
A spending summary based on actual Nessie sandbox data.
A breakdown of purchases and bills.
Product comparisons with prices and source links from SerpApi.
Suggested savings with transparent calculations.
A detailed run trace showing which tools were called and how long each took.
Important: Never invent purchase history, product prices, transaction records, or guaranteed savings. A cheaper listed product is a potential saving, not proof the user will actually save that amount. Label cost estimates clearly. The agent is an informational demo, not a financial adviser, and must never initiate transfers or alter bank data.
Fallback requirements
If the Nessie API key or account data is unavailable, use clearly labeled local demo fixtures. The flow must still execute through the same tool interface and persist a complete run trace. Do not pretend fixture results came from a live Nessie API.
Agent B: News Monitor — the second demo
Target user: Someone who wants to track a topic and receive a concise, source-backed briefing.
Example prompt:
Track developments in AI infrastructure, NVIDIA, and semiconductor supply chains. Give me the five most important stories, explain why each matters, and include the original sources.
Expected agent workflow
Gemini interprets the requested topics and desired briefing format.
It uses the SerpApi News tool to retrieve relevant current stories.
It optionally uses Web Search to verify details or investigate a story.
It ranks and summarizes the strongest retrieved results.
It returns a concise brief containing headlines, publication details where available, source links, and explanations of relevance.
Every tool and model step appears in the run history and dashboard.
Scope control: Implement manual execution first. Do not promise scheduled delivery, push alerts, or background monitoring unless those features actually work. Use real article metadata returned by the APIs and preserve source URLs.

2. Technical architecture
Use a single frontend, a single backend service, and a shared tool registry. Do not introduce microservices during a 24-hour hackathon.
Suggested stack
Frontend: React, TypeScript, Vite, Tailwind CSS, Lucide React.
Backend: FastAPI, Python, Pydantic, SQLAlchemy.
Database: TigerData managed PostgreSQL. Keep database access through ordinary PostgreSQL/SQLAlchemy functionality so local development can use a separate PostgreSQL instance if necessary.
AI: Gemini API using the official Google Gen AI SDK and documented function-calling workflow.
External tools: SerpApi for Shopping, News, Search, and Local Places; Capital One Nessie for account, purchase, and bill data.
Deployment: Vultr. Prioritize a single reproducible deployment with a documented startup process, environment variables, health checks, and database connectivity.
Repository structure
Use this structure unless the existing repository has a sound equivalent:
/web — React frontend.
/server — FastAPI application, database models, API routes, agent runtime, analytics, and settings.
/tools — shared tool registry, SerpApi adapters, Nessie adapters, cache layer, and tool schemas.
/server/tests — backend and integration tests.
/docs — architecture, API contracts, and demo script.
.env.example — variable names and placeholder values only.
README.md — setup, API examples, demo data, and troubleshooting.
If the repository already exists, inspect it before making changes. Preserve working code and do not overwrite useful files without understanding them.

3. Freeze the integration contracts in the first 30 minutes
All three people must agree on these contracts before working in parallel. Put the definitive schemas and example responses in README.md and a shared types module.
A. Agent configuration
Use a versioned JSON representation:
{
  "id": "agent-smart-spend",
  "name": "Smart Spend",
  "template": "smart_spend",
  "model": "gemini-3.8-flash",
  "instructions": "Analyze purchases and identify realistic savings opportunities.",
  "tools": [
    {
      "name": "nessie_accounts",
      "settings": {
        "customer_id": "DEMO_CUSTOMER_ID"
      }
    },
    {
      "name": "nessie_purchases",
      "settings": {
        "customer_id": "DEMO_CUSTOMER_ID"
      }
    },
    {
      "name": "nessie_bills",
      "settings": {
        "customer_id": "DEMO_CUSTOMER_ID"
      }
    },
    {
      "name": "serpapi_shopping",
      "settings": {
        "location": "Austin, Texas"
      }
    }
  ],
  "guardrails": {
    "read_only_financial_data": true,
    "max_tool_calls": 8,
    "require_confirmation_for_external_actions": true
  },
  "status": "deployed"
}
The example model is configurable, not a guarantee that the model is enabled for a particular account. Verify the model ID using the current Gemini API and make it configurable through GEMINI_MODEL.
In production-quality code, add timestamps, an owner or demo-user reference, and configuration versioning. Store flexible settings in PostgreSQL JSONB where useful.
B. Shared tool interface
All tools use the same interface:
{
    "name": str,
    "description": str,
    "settingsSchema": dict,
    "run": callable
}
The callable accepts run(input, settings) and returns a consistent structured result. Initialize external clients and inject dependencies through the tool registry rather than creating new clients for every call.
Use a shared result structure:
{
  "ok": true,
  "data": {},
  "source": "serpapi",
  "cached": false,
  "duration_ms": 284,
  "error": null
}
For failures, return a structured error that can be logged and displayed safely. Do not return API keys, full authorization headers, or other secrets.
C. Run-step schema
Every model and tool operation must produce a run step:
{
  "runId": "run_123",
  "agentId": "agent-smart-spend",
  "step": 2,
  "type": "tool",
  "toolName": "nessie_purchases",
  "input": {
    "customer_id": "DEMO_CUSTOMER_ID"
  },
  "output": {
    "purchase_count": 12
  },
  "ms": 284,
  "tokens": null,
  "error": null
}
Log only the minimum data necessary for debugging and demonstration. Redact secrets, avoid unnecessarily storing account identifiers, and avoid placing raw sensitive payloads in logs. Use token counts from actual model response metadata when available. Use null when usage is unavailable rather than inventing a count.
D. API contract
At minimum, implement:
GET /api/health
GET /api/agents
POST /api/agents
GET /api/agents/{id}
PATCH /api/agents/{id}
POST /api/agents/{id}/deploy
POST /api/agents/{id}/chat
GET /api/runs
GET /api/runs/{id}
GET /api/analytics/summary
GET /api/analytics/tools
GET /api/tools
Example chat request:
{
  "message": "Find three ways I could reduce my spending.",
  "session_id": "session_demo_01",
  "demo_user_id": "demo_user_01"
}
Example chat response:
{
  "run_id": "run_123",
  "assistant_message": "I found three potential savings opportunities...",
  "status": "completed",
  "usage": {
    "input_tokens": null,
    "output_tokens": null
  }
}
Add any fields the interface needs, but keep one canonical definition for each schema. The frontend must be able to build against these examples before the full backend is finished.

4. Database design
Use SQLAlchemy models and database migrations or a repeatable schema setup. Store the source of each result and the outcome of each run.
agents
Fields:
id
name
template
model
instructions
tools — JSONB
guardrails — JSONB
status
created_at
updated_at
deployed_at
runs
Fields:
id
agent_id
session_id
status
user_message
assistant_message
started_at
completed_at
total_latency_ms
input_tokens
output_tokens
estimated_cost_usd — nullable
error
Use explicit statuses such as running, completed, and failed.
run_steps
Fields:
id
run_id
step_number
type — llm or tool
tool_name — nullable
input — JSONB
output — JSONB
duration_ms
input_tokens
output_tokens
estimated_cost_usd — nullable
success
error
created_at
tool_cache
Fields:
id
cache_key
tool_name
result — JSONB
created_at
expires_at
Use appropriate indexes for run lookups and timestamp queries. Avoid logging complete bank data or credentials.
Analytics calculation rules
Runs over time: count run records grouped by time interval.
Average latency: calculate from actual stored run latency.
Error rate: failed runs divided by all completed or attempted runs, with the denominator defined consistently.
Calls per tool: count stored tool steps grouped by tool name.
Token usage: sum actual known token usage.
Estimated cost: calculate only where pricing is configured and usage data is available. Label estimates as estimates. If cost data is unavailable, show “Not available” rather than fake dollar values.
SerpApi API calls and Gemini model requests are different types of usage. Track them separately instead of pretending both have equivalent token-based costs.

5. Implement the agent runtime
Person 1 owns this component, but all team members must agree on its interface.
Runtime lifecycle
Load a deployed agent's instructions, model, enabled tools, settings, and guardrails.
Create a run record with status running.
Send the user's request and the selected tool declarations to Gemini.
Inspect the returned model content and any requested function calls.
Validate each function name and its arguments against the registered tool and its schema.
Execute the tool through the shared registry.
Store the result and duration in run_steps.
Return the actual tool result to Gemini using the documented function-response format.
Repeat until the model provides a final answer or the execution limit is reached.
Save the final response, usage metadata, total latency, and final run status.
Return the response and run_id to the frontend.
Use the current official function-calling documentation rather than coding from an outdated example. Gemini's function-calling pattern separates model tool selection from actual tool execution in your application: https://ai.google.dev/gemini-api/docs/function-calling
Required safeguards
Only execute registered tools enabled for that agent.
Validate tool arguments and enforce settingsSchema.
Apply per-agent tool-call and time limits.
Handle API timeouts, malformed model outputs, and unknown tool names.
Do not allow model output to execute shell commands or arbitrary code.
Keep user-facing failure messages separate from internal exception details.
Never let the model bypass a disabled tool or guardrail.
Persist run failures so the dashboard can display them.
Tool execution visibility
The UI should show real events such as:
Gemini started reasoning about the request.
nessie_accounts executed.
nessie_purchases returned 12 purchases.
serpapi_shopping returned results.
Gemini produced the final answer.
Use actual run steps. Do not render fabricated thinking traces or claim tools ran when they did not.
For model steps, store the request/response metadata and usage where available, but do not attempt to log hidden chain-of-thought. A visible activity timeline should report function calls, results summaries, timings, and final output.

6. Build the SerpApi tool library
Person 1 owns the adapters. Person 2 helps verify caching and database behavior.
Build four tools:
serpapi_shopping
Accept a product query and supported search settings.
Call the actual SerpApi Shopping endpoint when credentials are available.
Return normalized product titles, prices when present, merchants when present, and source URLs.
Preserve the original source information.
Cache equivalent searches to limit redundant requests.
serpapi_news
Accept one or more search topics and supported time/localization settings.
Return real news results with headlines, source URLs, snippets, and publication metadata when available.
Cache results with a defined expiration time.
Do not claim an article is recent when its publication time cannot be established.
serpapi_web_search
Accept a search query and supported settings.
Return normalized organic results and available snippets.
Preserve source URLs.
Cache responses.
serpapi_local_places
Accept a location and search query.
Return relevant places with addresses, ratings, and other supported fields when available.
Cache equivalent queries.
Clearly distinguish returned API fields from inferred descriptions.
Use the official API documentation to verify exact parameters and response shapes:
Google Shopping: https://serpapi.com/google-shopping-api
Google News: https://serpapi.com/google-news-api
Google Search: https://serpapi.com/search-api
Google Local: https://serpapi.com/google-local-api
Create one normalized result representation for each tool. Do not spread raw SerpApi response parsing across the frontend.
Caching requirements
Build a canonical cache key from tool name and normalized query/settings.
Reuse valid cached entries.
Configure reasonable TTLs for each tool.
Do not accidentally serve a cached result for a materially different query.
Make cache hits visible in logs and the dashboard.
Return an API error cleanly if the upstream request fails and no valid cached result exists.
A cached result should remain labeled as cached. Do not describe old cached results as live.

7. Build the Capital One Nessie tools
Person 1 implements the tools; Person 2 seeds/verifies the demo data.
At minimum:
nessie_accounts
nessie_purchases
nessie_bills
Use the customer/account identifiers configured for the selected demo agent. Confirm exact routes and response shapes against the Nessie documentation and a real API smoke test:
https://prod.nessieisreal.com/docs
Data setup strategy
Before making the UI depend on Nessie, verify a full request chain using the actual API key.
If the provided sandbox has no suitable customer or transaction history, create a reproducible setup script that creates the necessary fictional test data through supported Nessie endpoints, or use local fixtures as an explicit fallback.
Do not assume every endpoint succeeds just because the API key exists.
Smart Spend reasoning rules
Use deterministic code for arithmetic. Gemini should interpret results and explain them, not invent totals.
Calculate totals from returned transactions.
Categorize spending only when merchant/category evidence supports it; label uncertain classifications.
Identify recurring bills only when there is enough supporting information.
Compare product alternatives only when the purchase can reasonably be mapped to a specific product.
Include the source of each product result.
Do not claim all purchases are replaceable.
Do not perform transfers, payments, account changes, or other financial mutations.

8. Frontend: what the product should look like
Person 3 owns the frontend, UX, and pitch.
Build three primary pages and prioritize usability over the number of screens.
Page A — Agent Builder
This is the platform's first impression.
Include:
Agent Forge logo and navigation.
A template picker with Smart Spend and News Monitor.
A tool library with cards for Gemini, SerpApi Shopping, News, Web Search, Local Places, and Nessie.
An agent name field.
A clear instructions editor with a good default prompt.
Tool enable/disable controls and relevant settings.
Guardrail controls for tool limits and read-only financial behavior.
A prominent Deploy button.
Use tool metadata returned by GET /api/tools so the frontend does not independently hardcode a second tool catalog.
The Build page must save settings and create an actual agent record.
Page B — Deployed Agent Chat
After deployment, navigate to a page such as /agents/{id}.
Include:
Agent name and deployed status.
A conversation panel.
Suggested prompts.
A message box and send button.
A live run-progress timeline.
Tool call cards showing the tool name, successful/failed status, duration, and a safe summary of the result.
A final response area with source links where relevant.
A link to open the associated run.
Use real events from the backend. Poll the run endpoint or use Server-Sent Events only if time permits. A simple polling strategy is sufficient.
Page C — Monitoring Dashboard
Include:
Total runs.
Average latency.
Error rate.
Actual token usage, where available.
Estimated model cost, only when supported by real usage and configured pricing.
Runs-over-time visualization.
Calls by tool.
A recent-runs table.
Run status and timestamps.
Click-through to a detailed run trace.
Use Recharts if a chart adds value, with empty states when no metrics exist. Query the backend analytics endpoints rather than computing fake metrics in the UI.
Run detail view
Show a chronological timeline containing:
Model request.
Tool selection and invocation.
Tool execution result summary.
Tool duration.
Success/failure.
Model response and known usage metadata.
The detail page is critical for proving observability and differentiating Agent Forge from an ordinary chatbot.
Design system
Use a clean, developer-focused visual style:
Neutral background with restrained blue or violet accents.
Readable typography and consistent spacing.
Clear separation between agent configuration, conversation, and run monitoring.
Useful status badges, but avoid clutter.
Smooth loading/empty states and clear errors.
Responsive desktop-first design.
Avoid spending hours on animations or design flourishes before end-to-end functionality works.

9. The 24-hour schedule
Use the event schedule as the deadline. If a phase slips, cut optional features instead of delaying integration.
2:45–3:15 PM — Team agreement
All three people
Freeze the repository structure, data contracts, API routes, and examples.
Confirm one Gemini, one SerpApi, and one Nessie smoke test.
Confirm environment variable names.
Create the shared checklist.
Agree on the Smart Spend demo scenario.
Ensure each person can run their portion independently.
Deliverable: The three team members agree on exactly what the first working integration looks like.
3:15–5:30 PM — Parallel foundations
Person 1: Agent runtime and tools
Build the tool registry and shared tool interface.
Implement one real SerpApi tool first, ideally Shopping.
Implement the Gemini function-calling loop.
Log model and tool steps using the agreed run format.
Person 2: Backend and data
Set up PostgreSQL connectivity and schema.
Implement agents, runs, run_steps, and tool-cache persistence.
Create agent and run endpoints.
Implement minimal analytics queries.
Verify Nessie connectivity.
Person 3: Frontend, design, pitch
Attend the NMC2 workshop at 4:00 PM, GDC 2.216.
Build the Agent Builder against the README's mock API data.
Implement template selection, tool cards, instructions editor, and Deploy flow.
Start the visual design system and project branding.
Deliverable: Independent pieces with consistent contracts, not three separate interpretations of the product.
5:30–7:00 PM — First integration
Bring the pieces together.
Required demo:
Open Agent Forge.
Select Smart Spend.
Deploy the agent.
Open its chat page.
Send one message.
Gemini invokes one real SerpApi tool.
The response appears.
The run and tool step appear in PostgreSQL and the dashboard.
If this flow fails, stop adding features and debug it together.
7:00 PM milestone: first real end-to-end integration.
7:00–11:00 PM — Smart Spend plus live deployment
Person 1
Finish the Gemini loop and tool response handling.
Implement the remaining Nessie and SerpApi tools.
Ensure tool inputs, outputs, errors, timing, and cached status are logged.
Person 2
Complete database queries and dashboard endpoints.
Verify that failed runs are tracked.
Set up Vultr deployment and database environment variables.
Test a real Nessie account/purchase/bill sequence.
Person 3
Complete the deployed chat and monitoring screens.
Connect the UI to the real API.
Add run details and source links.
Refine Smart Spend's final answer and result layout.
11:00 PM deliverable: Smart Spend should run on the hosted application using a real Gemini tool call and real Nessie/SerpApi responses where credentials and test data permit. If an upstream API is unavailable, an honest, clearly labeled fallback must exist.
11:00–11:30 PM — Stabilize and submit a soft version
Fix critical integration failures.
Capture genuine screenshots of the working product.
Prepare a Devpost draft.
Document the working features and known limitations.
Verify that secrets are not committed.
11:30 PM milestone: Soft submission with a truthful project description.
11:30 PM–2:00 AM — News Monitor
Build the second template on top of the existing runtime rather than creating a second agent implementation.
Configure the News Monitor instructions.
Enable News and Web Search tools.
Test topic-based briefing.
Include source links and publication metadata where available.
Verify every action appears in the run trace.
Priority: A complete second template is better than a half-finished scheduling system.
2:00–4:00 AM — Dashboard and analytics
Verify run counts, latency, errors, and calls per tool.
Test cache hits.
Add token usage and truthful cost reporting.
Polish the run detail timeline.
Ensure failed tool calls appear accurately.
Use actual stored records for the charts. Do not fabricate metrics just to fill dashboard space.
4:00–6:30 AM — Deployment hardening and backup
Work in accordance with the provided venue restrictions: the WEL is locked from 11 PM to 6:30 AM, so use permitted GDC spaces.
Verify that the deployed app survives restarts.
Confirm database connectivity and environment variables.
Prepare cached SerpApi results for both demo agents.
Capture a recording of a successful end-to-end run.
Prepare a local fallback in case the hosted application becomes unavailable.
Rest when the core application is stable; split overnight coverage instead of having everyone work continuously.
Backup rule: cached results can keep a demonstration alive, but the UI must never claim an upstream API was called live when the result came from the cache or a fixture.
6:30–9:00 AM — Demo-ready polish
Test the hosted version from a clean browser session.
Fix broken navigation and critical UI issues.
Ensure the monitoring dashboard has useful real run data.
Improve visual hierarchy and empty/error states.
Complete the README and Devpost content.
Confirm all three teammates can present the product.
9:00 AM — Feature freeze
Only bug fixes, stability, and presentation polish from this point forward.
Do not add another integration or rewrite the frontend architecture.
9:00–10:30 AM — Submission and demo video
Record the product flow.
Finish the Devpost write-up.
Confirm track eligibility and required submission materials.
Enter NMC2, SerpApi, Capital One, and only those MLH prizes for which the product actually satisfies the applicable rules.
Verify the submitted description matches the real implementation.
10:30–11:00 AM — Final submission buffer
Check the correct project URL and repository.
Check screenshots, video, team information, and pitch details.
Submit before the 11:00 AM deadline.
11:00 AM–1:00 PM — Final preparation
No new features.
Prepare a two-minute pitch and a shorter fallback version.
Practice the primary live demo and the backup recording.
Confirm the product is still accessible.
Agree on who answers architecture, AI, business, and track-specific questions.
Attend the 1:00 PM pitching workshop at GDC 5.302. Judging is scheduled for 2:00–5:00 PM in WEL, with pitching at 5:30 PM in GDC 2.216, according to the supplied event schedule.

10. Team ownership and interface rules
Person 1 — Agent runtime and tools
Owns:
Gemini function calling and loop termination.
Shared tool registry.
SerpApi adapters and caching integration.
Nessie adapters.
Tool input validation.
Step logging.
Model/tool failure handling.
Person 1 is done when: a deployed agent can invoke the required tools, use their actual results to formulate an answer, and persist a complete trace for both successful and failed operations.
Person 2 — Platform backend and data
Owns:
PostgreSQL/TigerData.
SQLAlchemy models and migrations.
Agents and runs APIs.
Settings CRUD and deployment state.
Analytics endpoints.
Database seed/setup scripts.
Vultr deployment and backend health.
Person 2 is done when: agents persist, runs persist, analytics return real numbers, and the deployed backend can connect to the database.
Person 3 — Frontend, design, pitch
Owns:
Agent Builder.
Tool library and template selection.
Instructions and guardrails UI.
Deployed-agent chat.
Monitoring dashboard and run details.
Devpost, demo video, and pitch script.
Person 3 is done when: a judge can build, deploy, chat with, and inspect an agent without manually calling backend endpoints.
Shared rules
main must remain runnable.
Use small feature branches and merge frequently.
Have one teammate review each integration boundary.
Hold five-minute check-ins every two to three hours.
If blocked for more than 30 minutes, pair up, simplify, or remove the feature.
Keep one shared checklist and one source of truth for API contracts.
No one should keep implementing an obsolete mock interface after the backend contract changes.
Never put API keys into source files, commit history, browser bundles, or screenshots.

11. Critical scope decisions
Must-have
One real agent-builder flow.
Gemini tool calling.
At least one real SerpApi tool.
Nessie account/purchase/bill reads for Smart Spend, where the API and data are available.
A functioning second News Monitor template if the first agent is stable.
Persisted agent configuration and run logs.
A monitoring dashboard driven by real database queries.
Hosted deployment or a reliable runnable local demo.
README, screenshots, video, and pitch.
Should-have
All four SerpApi tools.
Visible cache hits.
Per-run timing and token usage.
Clear tool-call timeline.
Robust API error handling.
Smart Spend savings calculation and product comparison.
News Monitor source-backed brief.
Cut first
Automatic scheduled agent execution.
Email or push notifications.
Multi-user production authentication.
Arbitrary custom Python or code execution by agents.
Complicated workflow builders.
A plugin marketplace.
Sophisticated distributed tracing.
Elaborate permission management.
Additional database infrastructure.
The rule: keep the platform generic, but make the demo specialized. Two fully functioning templates on one reliable runtime are more compelling than many templates that only work with mock data.

12. Acceptance tests
Before feature freeze, verify all of these manually or with automated tests:
Builder and configuration
Create an agent from a template.
Change its instructions and enabled tools.
Persist the configuration and reload it.
Deploy an agent and open its own chat page.
Runtime
A request triggers a real Gemini function call.
The backend executes the requested registered tool.
The model receives the actual function result.
The model generates a final response.
A multi-tool run works.
An unknown or disabled tool is rejected.
A model/API failure is logged and shown safely.
SerpApi and Nessie
Shopping returns structured products.
News returns sourced stories.
Search and Local Places work or are accurately marked unavailable.
Repeated equivalent SerpApi queries demonstrate cache reuse.
Nessie accounts, purchases, and bills return valid data where supported.
Any fallback data is explicitly labeled.
Observability
Every run has a persisted status and timestamps.
Tool steps include names, inputs, safe output summaries, and durations.
Failed tool steps are persisted.
Dashboard metrics match the database.
Unknown token/cost data is shown as unavailable, not fabricated.
Run details show the real sequence of events.
Product and presentation
Smart Spend completes a full user flow.
News Monitor completes a full user flow.
The hosted deployment is reachable.
The app can be demonstrated using the recording or cached fallback if an upstream service fails.
The final Devpost claims only features that actually work.

13. Two-minute judge demo
0:00–0:15 — The problem
“Building AI agents today often means wiring together APIs, writing orchestration code, and debugging behavior without understanding what the agent actually did. Agent Forge gives people a simple way to configure, deploy, and observe agents that use real tools.”
0:15–0:35 — Build
Open the Builder, choose Smart Spend, show the enabled Nessie and Shopping tools, and deploy the agent. Explain that tools are registered through a common interface, so adding a new tool does not require creating an entirely new agent runtime.
0:35–1:10 — Execute
Ask Smart Spend to analyze purchases and find savings opportunities. Show Gemini invoking Nessie, then SerpApi Shopping, and finally producing an evidence-backed recommendation using returned data.
1:10–1:35 — Observe
Open the run trace. Show the model step, tool calls, execution durations, cached status where applicable, and final result. Then open the monitoring dashboard to show actual run and tool usage metrics.
1:35–1:50 — Second template
Switch to News Monitor and request a short briefing on semiconductor developments. Show that it uses the same runtime with a different tool configuration and instruction set.
1:50–2:00 — Close
“Agent Forge doesn't just generate an answer. It makes agents deployable, their tool use inspectable, and their performance measurable.”

14. Instructions to the coding assistant
Act as an autonomous senior engineer working inside the existing repository.
Inspect the existing files and current application before changing anything.
Establish the shared contracts and write them down before building independent components.
Build the smallest complete vertical slice first: create agent → deploy → chat → Gemini tool call → real tool result → saved run → dashboard.
Ensure the backend and frontend can operate with explicit demo fixtures when external credentials are missing.
Keep fixture, cached, and live results distinguishable throughout the system.
Use official current Gemini, SerpApi, and Nessie documentation to confirm their request formats and supported fields.
Implement real API calls and real persistence. Do not replace the required functions with hardcoded chatbot responses.
Use deterministic calculations for financial totals, latencies, and analytics. Do not ask the language model to invent metrics.
Add tests and run them. Do not report successful tests or deployments unless they actually occurred.
Keep the code simple, typed, and maintainable. Avoid unnecessary abstractions and infrastructure.
Protect secrets and existing project work.
Maintain BUILD_STATUS.md with completed requirements, current blockers, test results, and remaining priorities.
At each milestone, run the app or relevant tests and fix failures before continuing.
If a deadline is approaching, cut optional functionality instead of leaving the core user journey broken.
At the end, report the exact startup and deployment commands, required environment variables, implemented features, test results, and any incomplete or mocked functionality.
Start by inspecting the repository and validating the three API integrations. Then implement the first complete vertical slice. Do not stop after generating a plan, writing placeholder pages, or creating a scaffold.


---

## Team addendum (agreed Sat 3:15 PM)

**Section 14 applies per person, not to the whole app.** Each teammate's coding assistant builds only the folders that person owns (see docs/API.md → Ownership). Do not let any assistant build the entire app.

**Shared contracts are frozen** in `server/schemas.py`, `web/src/types.ts` and `docs/API.md`. Change them only with team agreement, all three files in one commit.

**Trust feature (Person 1):** after the final answer, a `verify` step compares every figure in the answer against the tool outputs of that run (exact match, or a difference/sum of two tool figures). It logs a `verify` run step and returns `claims` in the chat response. Guardrail `fact_check`: `flag` (mark unverified figures), `block` (redact them), `off`. Pitch line: "Other platforms help you build agents. We help you trust them."
