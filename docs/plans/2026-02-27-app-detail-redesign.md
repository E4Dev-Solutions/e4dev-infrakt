# App Detail Page Redesign

Date: 2026-02-27

## Problem

The App Detail page has several design flaws:
- No overview — lands directly on logs, no at-a-glance app state
- Cluttered header — name, status, server, domain, port, type, branch, CPU, memory all on one line
- Unsafe action buttons — Deploy and Destroy have equal visual weight
- Edit modal shows all fields regardless of app type (template apps see git repo / image fields)
- Fixed 480px log viewer height regardless of screen size
- Health tab is underused and feels like filler

## Design

### Header

Three-line subtitle instead of one crammed line:

```
┌────┐  my-app                    [Deploy]  [Restart][Stop]  ⋮
│ 📦 │  ● running  ·  prod-1                          ↳ [Destroy]
└────┘  https://app.example.com → :3000
        template:n8n  ·  main branch
```

- Line 1: Status badge + server name
- Line 2: Domain (clickable external link) + port
- Line 3: App type + branch
- Resource limits (CPU/Mem) move to Settings tab
- Action buttons: Deploy (green CTA), Restart+Stop (secondary zinc), Destroy inside `⋮` kebab dropdown

### Tab Structure

5 tabs replacing the current 4:

| Tab | Content | Notes |
|-----|---------|-------|
| **Overview** (default) | Stat cards, container metrics, quick info, recent deploys, HTTP health | New — replaces Health tab |
| **Logs** | Container log viewer | Responsive height: `h-[calc(100vh-300px)]` |
| **Environment** | Unified compose + override env var table | No changes |
| **Deployments** | Deploy history table with expandable logs + rollback | No changes |
| **Settings** | Inline form replacing Edit modal | New — replaces Edit modal |

### Overview Tab

Default landing view with four sections:

**1. Stat Cards (top row, 3 cards)**
- Status: badge showing running/stopped/error
- Last Deploy: relative time + commit hash (e.g. "3 min ago · abc1234")
- App Type: template:n8n / image / git

**2. Container Metrics**
- Fetched from existing health API (`GET /api/apps/{name}/health`)
- Table: Container name, State, CPU %, Memory used/limit
- Manual refresh button (no auto-polling — avoids unnecessary SSH calls)

**3. Recent Deploys (mini-list)**
- Last 5 deployments: status indicator (green/red dot), relative time, commit ref
- Links to full Deployments tab

**4. Quick Info**
- Key-value list: Server, Domain (external link), Port, Branch, Replicas, Deploy Strategy

**5. HTTP Health Check** (conditional — only if `health_check_url` is configured)
- Status badge, HTTP code, response time

### Settings Tab

Replaces the Edit modal with organized collapsible sections:

**General** — Domain, Port
**Source** — Git repo, Branch, Image (hidden for template apps)
**Resources** — CPU limit, Memory limit, Replicas, Deploy strategy (dropdown)
**Health Check** — URL, Interval

**Danger Zone** (collapsed by default):
- Destroy app with clear warning text and confirmation
- This is the ONLY place Destroy lives — removed from header

**UX details:**
- Save button at top-right, sticky
- Grayed out when clean, orange when dirty (unsaved changes)
- Source section hidden when `app_type` starts with `template:`

### Logs Tab

Only change: responsive height using `h-[calc(100vh-300px)]` instead of fixed `h-[480px]`.

### Environment & Deployments Tabs

No changes to functionality or layout.
