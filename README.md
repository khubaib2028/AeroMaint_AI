# AeroMaint AI — SIH 2026 Phase 13

**PS 26249 — Air Power: Predictive Maintenance & Fleet Availability**

Phase 13 is the current integrated SIH MVP release. It adds an executive **AI Fleet Command & Decision Center** on top of the existing predictive-maintenance, digital-twin, fleet-optimization, maintenance-execution, analytics and fleet-health layers.

The package is self-contained and includes a synthetic SQLite database plus the trained failure-prediction model. All telemetry, training data and planning records are synthetic demo data.

## Current Phase 13 release

- AI Fleet Command & Decision Center
- Transparent command score combining health, risk and ML failure probability
- Executive priority queue and command recommendation
- Maintenance, logistics and planning recommendations
- Decision lifecycle: detected → AI priority → planned → executing → completed
- Low-stock spare-parts alerts
- Next 7-day maintenance schedule
- Independent loading of Phase 8–13 dashboard panels so one failed API does not blank the entire dashboard

## Phase 7 additions

- Live digital-twin simulation controls: Start, Pause and Reset
- Four synthetic telemetry scenarios:
  - NORMAL
  - THERMAL STRESS
  - HIGH VIBRATION
  - LOW OIL PRESSURE
- Live Engine Temperature, Vibration, Oil Pressure and Flight Hours
- Dynamic component-health recalculation
- Live failure-probability recalculation using the existing ML model
- Dynamic AI risk, maintenance priority and predicted issue
- Active alerts based on simulated telemetry
- 2-second dashboard polling for a live simulation experience
- Simulation state kept in memory so synthetic telemetry does not overwrite the aircraft database
- Existing Phase 1–6 features retained: fleet dashboard, predictive maintenance, Digital Twin, Decision Support, work orders, spare parts and maintenance schedule

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python train_model.py
uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000

> If you are continuing from the Phase 6 database, do **not** run `python seed.py` unless you intentionally want to recreate the synthetic demo fleet and reset work orders.

## Phase 7 demo flow

1. Open the fleet dashboard.
2. Select a high-risk aircraft such as **AC-113**.
3. Click **Twin**.
4. Select **THERMAL STRESS** and click **Start Simulation**.
5. Watch Engine Temperature, Vibration, Oil Pressure and Flight Hours update live.
6. Observe the Digital Twin Health and component-health bars change.
7. Observe the live Failure Probability, AI Risk, Priority and Predicted Issue update.
8. Switch to **HIGH VIBRATION** or **LOW OIL PRESSURE** to demonstrate different telemetry conditions.
9. Click **Pause** to stop changing telemetry.
10. Click **Reset** to return to the aircraft's baseline synthetic telemetry.

## Phase 7 API

- `POST /api/digital-twin/{aircraft_code}/simulation/start?scenario=NORMAL`
- `POST /api/digital-twin/{aircraft_code}/simulation/stop`
- `POST /api/digital-twin/{aircraft_code}/simulation/reset`
- `GET /api/digital-twin/{aircraft_code}/simulation`
- `GET /api/digital-twin/{aircraft_code}/telemetry` — kept compatible with the Phase 6 endpoint

## Prototype note

Aircraft telemetry, health history, component-health mapping, live telemetry fluctuations, ML training data and simulation scenarios are **synthetic demo data** for SIH prototyping. The system is a maintenance analytics and decision-support prototype; it is not an aircraft certification, safety system or operational-control system.


## Phase 8 — Fleet Availability & Maintenance Optimization

Adds a transparent fleet-readiness decision layer on top of Phases 1–7.

### New capabilities
- Fleet readiness score
- Ready vs at-risk aircraft count
- Priority maintenance count
- Availability/readiness by aircraft type
- Optimized maintenance queue
- Recommendation based on risk score, AI failure probability, digital-twin health and open work orders
- New endpoint: `/api/fleet-optimization`

The optimization layer is a synthetic SIH prototype heuristic and does not modify the aircraft source-of-truth telemetry table.


## Phase 9 — Maintenance Cost & Spare-Parts Optimization

Phase 9 adds a transparent planning layer on top of the Phase 8 fleet optimizer.

### Added
- Maintenance cost estimation using illustrative SIH MVP assumptions.
- Spare-parts reorder quantity and estimated spend.
- Maintenance value queue with estimated maintenance cost, avoided downtime value and net value.
- New API: `GET /api/maintenance-optimization`
- Dashboard section: **Maintenance Cost & Spare-Parts Planning**.

### Important
The cost values are illustrative prototype assumptions only. Replace them with authorized fleet/lifecycle cost data for any real deployment.


## Phase 10 — Maintenance Execution & Closure

Phase 10 closes the maintenance planning loop from Phase 9 by turning work orders into traceable execution records.

### Added
- Maintenance Execution & Closure control panel.
- Scheduled / In Progress / Completed execution KPIs.
- Start maintenance execution with technician/team assignment.
- Capture actual maintenance hours.
- Capture completion result: PASS, CONDITIONAL, or REQUIRES FOLLOW-UP.
- Capture maintenance notes and completion timestamp.
- Execution history linked to the original work order.
- Completing a work order increments the aircraft maintenance count without overwriting telemetry.
- Existing Phase 1–9 features remain available.

### Phase 10 demo flow
1. Open the dashboard and scroll to **Execution & Closure Control**.
2. Find a scheduled work order.
3. Click **Start** and enter the technician/team.
4. The work order moves to **IN PROGRESS**.
5. Click **Complete** and enter actual hours, technician, result and notes.
6. The work order moves to **COMPLETED** and the execution record is stored.
7. Use the execution KPIs and history table to demonstrate traceability.

### Phase 10 APIs
- `GET /api/maintenance-execution/summary`
- `GET /api/maintenance-execution/{order_id}`
- `POST /api/maintenance-execution/{order_id}/start`
- `POST /api/maintenance-execution/{order_id}/complete`

### Prototype note
Maintenance execution records are synthetic SIH MVP workflow data. They are intended to demonstrate traceability and maintenance-control workflow, not to certify aircraft maintenance or replace authorized maintenance procedures.


### Fresh ZIP behavior
The Phase 10 package includes a ready-to-run synthetic `aeromaint.db` and trained model.
On first application startup, if the core aircraft database is missing or empty, the app
automatically recreates the synthetic demo database. A scheduled AC-113 Phase 10 work
order is included so the execution workflow can be tested immediately.


## Phase 11 • Maintenance Analytics
- `/api/maintenance-analytics` derives completion, execution, effort variance, team performance and history from actual maintenance execution records.
- Dashboard includes Maintenance Performance & History with completion rate, PASS rate, actual hours, team performance and execution history.
- Phase 10 execution workflow remains unchanged.


## Phase 12 — Fleet Health Intelligence
- Transparent fleet health scoring from current telemetry and risk data
- Aircraft health ranking with deterioration trend classification
- Recurring issue detection across the fleet
- Upcoming maintenance risk view
- API: `/api/fleet-health-intelligence`
- Phase 12 does not modify telemetry source-of-truth data.


## Phase 12 package fix
- Fixed a JavaScript function-scope error in the dashboard that caused the Phase 11 analytics loader to be unavailable.
- Removed a duplicate `loadAll()` implementation.
- The remaining dashboard panels now load independently, so Phase 8/9/10/11 failures do not block the other sections.
- Phase 12 Fleet Health Intelligence remains independently loaded with a visible fallback message on API failure.


## Phase 13 — AI Fleet Command & Decision Center

Phase 13 adds an executive command layer that combines the existing Phase 8–12 intelligence without replacing the underlying telemetry, maintenance or inventory records.

### Added
- Fleet Health, critical-aircraft, open-work-order and 7-day maintenance KPIs.
- AI priority queue using a transparent command score derived from health, risk and failure probability.
- Executive command recommendation for the most urgent current action.
- Maintenance, logistics and planning recommendations.
- Decision lifecycle view: detected → AI priority → planned → executing → completed.
- Low-stock spare-parts alerts.
- Next 7-day maintenance schedule view.
- New API: `GET /api/fleet-command-center`.

### Phase 13 demo flow
1. Start the application and scroll to **AI Fleet Command & Decision Center**.
2. Review Fleet Health and Critical Aircraft KPIs.
3. Review the **Current Command Recommendation**.
4. Use the **AI Priority Queue** to identify which aircraft should be handled first.
5. Review Maintenance, Logistics and Planning recommendations.
6. Use the Decision Lifecycle to explain the flow from detection through execution and closure.
7. Complete a Phase 10 work order and refresh to see the command layer update from the underlying records.

### Prototype note
Phase 13 is a transparent SIH MVP decision-support layer. It uses synthetic fleet data and heuristic scoring; it is not an aviation-certified safety, dispatch or maintenance-control system.
## Development Phases

### Phase 1 — Project Setup & Architecture
Initial project structure, application architecture and development environment setup.

### Phase 2 — Database & Synthetic Fleet Data
Implemented SQLite database and synthetic aircraft fleet data for the SIH MVP.

### Phase 3 — Backend APIs & Fleet Management
Implemented Python + FastAPI backend and APIs for aircraft, fleet monitoring, telemetry and maintenance operations.

### Phase 4 — Predictive Maintenance / ML Model
Implemented machine-learning based aircraft failure prediction using synthetic aircraft telemetry.

### Phase 5 — Digital Twin & Fleet Intelligence
Added aircraft health monitoring, Digital Twin capabilities and fleet intelligence.

### Phase 6 — Maintenance & Decision Support
Added maintenance prioritization and decision-support capabilities for identifying high-risk aircraft and maintenance requirements.

### Phase 7 — Live Digital Twin Simulation
Added live Digital Twin simulation with NORMAL, THERMAL STRESS, HIGH VIBRATION and LOW OIL PRESSURE scenarios, live telemetry updates, dynamic health recalculation and ML failure-probability prediction.

### Phase 8 — Fleet Availability & Maintenance Optimization
Added fleet readiness scoring, ready vs at-risk aircraft analysis, priority maintenance queue and maintenance optimization recommendations.

**API:** `/api/fleet-optimization`

### Phase 9 — Maintenance Cost & Spare-Parts Optimization
Added maintenance cost estimation, spare-parts reorder quantity, estimated spend and maintenance value analysis.

**API:** `/api/maintenance-optimization`

### Phase 10 — Maintenance Execution & Closure
Added maintenance execution tracking, technician/team assignment, actual maintenance hours, completion results, notes and execution history.

**APIs:**
- `/api/maintenance-execution/summary`
- `/api/maintenance-execution/{order_id}`
- `/api/maintenance-execution/{order_id}/start`
- `/api/maintenance-execution/{order_id}/complete`

### Phase 11 — Maintenance Analytics
Added maintenance performance analytics including completion rate, PASS rate, actual hours, effort variance, team performance and execution history.

**API:** `/api/maintenance-analytics`

### Phase 12 — Fleet Health Intelligence
Added transparent fleet health scoring, aircraft health ranking, deterioration trends, recurring issue detection and upcoming maintenance risk analysis.

**API:** `/api/fleet-health-intelligence`

### Phase 13 — AI Fleet Command & Decision Center
Added an executive AI Fleet Command & Decision Center combining fleet health, risk, failure probability, maintenance and planning intelligence.

Key capabilities:
- Fleet Health and Critical Aircraft KPIs
- AI Priority Queue
- Transparent command score
- Executive command recommendation
- Maintenance, logistics and planning recommendations
- Low-stock spare-parts alerts
- Next 7-day maintenance schedule
- Decision lifecycle:
  **Detected → AI Priority → Planned → Executing → Completed**

**API:** `/api/fleet-command-center`

> AeroMaint AI is an SIH MVP decision-support prototype using synthetic fleet data and heuristic scoring. It is not an aviation-certified safety, dispatch or maintenance-control system.
