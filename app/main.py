from pathlib import Path
import sqlite3
import joblib
import numpy as np
import math
from functools import lru_cache
from datetime import datetime, timedelta
import time

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "aeromaint.db"
MODEL_PATH = BASE_DIR / "models" / "failure_model.joblib"

app = FastAPI(title="AeroMaint AI - Phase 13")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


@lru_cache(maxsize=1)
def load_model():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def predict_aircraft(row):
    model = load_model()
    if model is None:
        return {"failure_probability": None, "risk_level": "MODEL NOT TRAINED", "predicted_issue": "Train the ML model first", "recommendation": "Run: python train_model.py"}
    features = np.array([[row["engine_temperature"], row["vibration"], row["oil_pressure"], row["flight_hours"], row["component_age"], row["previous_failures"], row["maintenance_count"]]])
    probability = float(model.predict_proba(features)[0][1])
    percentage = round(probability * 100, 1)
    risk = "HIGH" if percentage >= 75 else ("MEDIUM" if percentage >= 45 else "LOW")
    if row["engine_temperature"] >= 95:
        issue = "Engine thermal stress"
    elif row["vibration"] >= 0.90:
        issue = "Vibration-related component degradation"
    elif row["oil_pressure"] <= 32:
        issue = "Low oil-pressure condition"
    elif row["component_age"] >= 75:
        issue = "Aged component / wear risk"
    else:
        issue = "No dominant component anomaly"
    recommendation = {
        "HIGH": "Schedule preventive inspection and maintenance review",
        "MEDIUM": "Increase monitoring frequency and plan preventive inspection",
        "LOW": "Continue routine monitoring",
    }[risk]
    return {"failure_probability": percentage, "risk_level": risk, "predicted_issue": issue, "recommendation": recommendation}



def component_health(row):
    """Build a transparent, synthetic digital-twin health view from current telemetry.
    This is a prototype mapping, not an aircraft-certified diagnostic model.
    """
    temp = float(row["engine_temperature"])
    vib = float(row["vibration"])
    pressure = float(row["oil_pressure"])
    age = float(row["component_age"])
    failures = int(row["previous_failures"])
    hours = float(row["flight_hours"])

    def clamp(v):
        return round(max(0, min(100, v)), 1)

    engine = clamp(100 - max(0, temp - 78) * 1.8 - vib * 14 - failures * 3)
    avionics = clamp(100 - max(0, vib - 0.45) * 48 - max(0, age - 60) * .25)
    hydraulics = clamp(100 - max(0, 38 - pressure) * 2.2 - max(0, age - 65) * .35)
    landing = clamp(100 - max(0, hours - 2500) / 55 - max(0, age - 70) * .55)
    fuel = clamp(100 - max(0, 82 - pressure) * .8 - max(0, hours - 3200) / 90)

    components = [
        ("Engine", engine, "Temperature + vibration"),
        ("Avionics", avionics, "Vibration + component age"),
        ("Hydraulics", hydraulics, "Oil-pressure condition"),
        ("Landing Gear", landing, "Flight-hour wear"),
        ("Fuel System", fuel, "Pressure + usage"),
    ]
    result=[]
    for name, health, basis in components:
        status = "CRITICAL" if health < 45 else ("ATTENTION" if health < 70 else "HEALTHY")
        result.append({"component":name,"health":health,"status":status,"basis":basis})
    overall=round(sum(x["health"] for x in result)/len(result),1)
    return {"overall_health":overall,"components":result}


@app.get("/api/digital-twin/{aircraft_code}")
def digital_twin(aircraft_code: str):
    conn=get_db()
    row=conn.execute("SELECT * FROM aircraft WHERE aircraft_code=?",(aircraft_code,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404,"Aircraft not found")
    history=conn.execute(
        "SELECT recorded_at,engine_temperature,vibration,oil_pressure FROM health_history "
        "WHERE aircraft_code=? ORDER BY recorded_at DESC LIMIT 1",(aircraft_code,)
    ).fetchone()
    conn.close()
    data=dict(row)
    twin=component_health(data)
    twin["aircraft_code"]=data["aircraft_code"]
    twin["aircraft_type"]=data["aircraft_type"]
    twin["telemetry"]={
        "engine_temperature":data["engine_temperature"],
        "vibration":data["vibration"],
        "oil_pressure":data["oil_pressure"],
        "flight_hours":data["flight_hours"],
        "component_age":data["component_age"],
        "last_recorded": history["recorded_at"] if history else None
    }
    twin["alerts"]=[]
    if data["engine_temperature"] >= 95:
        twin["alerts"].append("Engine temperature above 95 °C threshold")
    if data["vibration"] >= 0.90:
        twin["alerts"].append("High vibration detected")
    if data["oil_pressure"] <= 32:
        twin["alerts"].append("Low oil-pressure condition")
    if twin["overall_health"] < 70 and not twin["alerts"]:
        twin["alerts"].append("Digital-twin health requires maintenance review")
    return twin


@app.get("/api/digital-twin/{aircraft_code}/telemetry")
def digital_twin_telemetry(aircraft_code: str):
    # Phase 7 keeps the original endpoint compatible with the Phase 6 UI.
    return _simulation_telemetry(aircraft_code)


# ---------------------------------------------------------------------------
# PHASE 7 — LIVE DIGITAL TWIN SIMULATION
# ---------------------------------------------------------------------------
# Simulation state is intentionally kept in memory. The prototype never writes
# synthetic live telemetry back to the aircraft source-of-truth table.
SIMULATION_STATES = {}
SIMULATION_SCENARIOS = {
    "NORMAL": {"temp": 0.0, "vibration": 0.0, "pressure": 0.0},
    "THERMAL STRESS": {"temp": 6.0, "vibration": 0.02, "pressure": -0.5},
    "HIGH VIBRATION": {"temp": 1.5, "vibration": 0.28, "pressure": -0.2},
    "LOW OIL PRESSURE": {"temp": 1.0, "vibration": 0.03, "pressure": -6.0},
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _base_aircraft(aircraft_code):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM aircraft WHERE aircraft_code=?", (aircraft_code,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Aircraft not found")
    return dict(row)


def _simulation_telemetry(aircraft_code):
    """Return the current simulated sensor state for an aircraft."""
    data = _base_aircraft(aircraft_code)
    state = SIMULATION_STATES.get(aircraft_code)

    if not state or not state["running"]:
        return {
            "engine_temperature": round(float(data["engine_temperature"]), 1),
            "vibration": round(float(data["vibration"]), 2),
            "oil_pressure": round(float(data["oil_pressure"]), 1),
            "flight_hours": round(float(data["flight_hours"]), 1),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_running": False,
            "scenario": "NORMAL",
        }

    now = time.time()
    elapsed = now - state["started_at"]
    scenario = SIMULATION_SCENARIOS[state["scenario"]]

    # Smooth deterministic oscillation makes the dashboard feel live while
    # remaining reproducible and safe for a prototype.
    wave = math.sin(elapsed * 1.8)
    wave2 = math.sin(elapsed * 0.75 + 1.2)

    temp = (
        float(data["engine_temperature"])
        + scenario["temp"]
        + wave * 0.8
        + wave2 * 0.25
    )
    vibration = (
        float(data["vibration"])
        + scenario["vibration"]
        + wave2 * 0.025
    )
    pressure = (
        float(data["oil_pressure"])
        + scenario["pressure"]
        - wave * 0.45
    )
    hours = float(data["flight_hours"]) + elapsed / 3600.0

    return {
        "engine_temperature": round(_clamp(temp, 40, 125), 1),
        "vibration": round(_clamp(vibration, 0.05, 1.8), 2),
        "oil_pressure": round(_clamp(pressure, 15, 65), 1),
        "flight_hours": round(hours, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "simulation_running": True,
        "scenario": state["scenario"],
    }


def _simulation_prediction(aircraft_code, telemetry):
    """Recalculate AI prediction using simulated sensor values."""
    data = _base_aircraft(aircraft_code)
    data.update({
        "engine_temperature": telemetry["engine_temperature"],
        "vibration": telemetry["vibration"],
        "oil_pressure": telemetry["oil_pressure"],
    })
    prediction = predict_aircraft(data)
    twin = component_health(data)

    # The Phase 6 decision layer can consume the same simulated state.
    probability = prediction["failure_probability"] or 0
    if probability >= 85 or twin["overall_health"] < 45:
        action = "Immediate maintenance review"
        priority = "CRITICAL"
    elif probability >= 65 or twin["overall_health"] < 70:
        action = "Schedule preventive inspection"
        priority = "HIGH"
    elif probability >= 45:
        action = "Increase monitoring frequency"
        priority = "MEDIUM"
    else:
        action = "Continue routine monitoring"
        priority = "LOW"

    return {
        "failure_probability": probability,
        "risk_level": prediction["risk_level"],
        "priority": priority,
        "predicted_issue": prediction["predicted_issue"],
        "recommendation": action,
        "twin_health": twin["overall_health"],
        "components": twin["components"],
    }


@app.post("/api/digital-twin/{aircraft_code}/simulation/start")
def start_digital_twin_simulation(aircraft_code: str, scenario: str = "NORMAL"):
    _base_aircraft(aircraft_code)
    scenario = scenario.strip().upper()
    if scenario not in SIMULATION_SCENARIOS:
        raise HTTPException(
            400,
            "Invalid scenario. Use NORMAL, THERMAL STRESS, HIGH VIBRATION or LOW OIL PRESSURE."
        )

    SIMULATION_STATES[aircraft_code] = {
        "running": True,
        "scenario": scenario,
        "started_at": time.time(),
    }
    telemetry = _simulation_telemetry(aircraft_code)
    prediction = _simulation_prediction(aircraft_code, telemetry)
    return {
        "ok": True,
        "aircraft_code": aircraft_code,
        "scenario": scenario,
        "telemetry": telemetry,
        "prediction": prediction,
    }


@app.post("/api/digital-twin/{aircraft_code}/simulation/stop")
def stop_digital_twin_simulation(aircraft_code: str):
    _base_aircraft(aircraft_code)
    state = SIMULATION_STATES.get(aircraft_code)
    if state:
        state["running"] = False
    telemetry = _simulation_telemetry(aircraft_code)
    prediction = _simulation_prediction(aircraft_code, telemetry)
    return {
        "ok": True,
        "aircraft_code": aircraft_code,
        "scenario": "NORMAL",
        "telemetry": telemetry,
        "prediction": prediction,
    }


@app.post("/api/digital-twin/{aircraft_code}/simulation/reset")
def reset_digital_twin_simulation(aircraft_code: str):
    _base_aircraft(aircraft_code)
    SIMULATION_STATES.pop(aircraft_code, None)
    telemetry = _simulation_telemetry(aircraft_code)
    prediction = _simulation_prediction(aircraft_code, telemetry)
    return {
        "ok": True,
        "aircraft_code": aircraft_code,
        "scenario": "NORMAL",
        "telemetry": telemetry,
        "prediction": prediction,
    }


@app.get("/api/digital-twin/{aircraft_code}/simulation")
def digital_twin_simulation(aircraft_code: str):
    _base_aircraft(aircraft_code)
    telemetry = _simulation_telemetry(aircraft_code)
    prediction = _simulation_prediction(aircraft_code, telemetry)
    state = SIMULATION_STATES.get(aircraft_code)
    return {
        "aircraft_code": aircraft_code,
        "running": bool(state and state["running"]),
        "scenario": telemetry["scenario"],
        "telemetry": telemetry,
        "prediction": prediction,
    }


def ensure_phase4_tables():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS spare_parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, part_code TEXT UNIQUE NOT NULL,
        part_name TEXT NOT NULL, category TEXT NOT NULL, stock INTEGER NOT NULL,
        reorder_level INTEGER NOT NULL, lead_days INTEGER NOT NULL, unit_cost REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, aircraft_code TEXT NOT NULL,
        issue TEXT NOT NULL, priority TEXT NOT NULL, recommendation TEXT NOT NULL,
        assigned_team TEXT NOT NULL, scheduled_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS maintenance_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, aircraft_code TEXT NOT NULL,
        maintenance_type TEXT NOT NULL, due_date TEXT NOT NULL,
        estimated_hours REAL NOT NULL, status TEXT NOT NULL DEFAULT 'PLANNED'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS maintenance_execution (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_id INTEGER UNIQUE NOT NULL,
        aircraft_code TEXT NOT NULL,
        technician TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        actual_hours REAL,
        result TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    if conn.execute("SELECT COUNT(*) FROM spare_parts").fetchone()[0] == 0:
        parts = [
            ("ENG-FLT-01", "Engine Filter", "Engine", 18, 8, 5, 4200),
            ("VIB-SNS-02", "Vibration Sensor", "Avionics", 7, 5, 12, 18500),
            ("OIL-PMP-03", "Oil Pump Assembly", "Engine", 5, 3, 18, 74000),
            ("HYD-SEAL-04", "Hydraulic Seal Kit", "Hydraulic", 22, 10, 7, 6800),
            ("BRG-AXL-05", "Bearing Assembly", "Airframe", 4, 5, 21, 32000),
            ("TEMP-SNS-06", "Thermal Sensor", "Avionics", 12, 6, 9, 11200),
        ]
        conn.executemany("INSERT INTO spare_parts(part_code,part_name,category,stock,reorder_level,lead_days,unit_cost) VALUES (?,?,?,?,?,?,?)", parts)
    if conn.execute("SELECT COUNT(*) FROM maintenance_schedule").fetchone()[0] == 0:
        aircraft = conn.execute("SELECT aircraft_code, risk_score FROM aircraft ORDER BY risk_score DESC").fetchall()
        rows=[]
        for i,a in enumerate(aircraft):
            days = 2 + (i % 18) if a["risk_score"] >= 50 else 15 + (i % 30)
            mtype = "Preventive Inspection" if a["risk_score"] >= 50 else "Routine Service"
            rows.append((a["aircraft_code"],mtype,(datetime.now()+timedelta(days=days)).strftime("%Y-%m-%d"),6 if a["risk_score"]>=50 else 4,"PLANNED"))
        conn.executemany("INSERT INTO maintenance_schedule(aircraft_code,maintenance_type,due_date,estimated_hours,status) VALUES (?,?,?,?,?)", rows)
    conn.commit(); conn.close()


class WorkOrderCreate(BaseModel):
    aircraft_code: str
    assigned_team: str = "Maintenance Team A"
    scheduled_date: str | None = None


def ensure_database_ready():
    """Ensure the synthetic demo database exists before API startup.
    This keeps a fresh Phase 12 ZIP runnable without requiring a manual seed step.
    Existing databases are preserved unless the aircraft source table is missing/empty.
    """
    needs_seed = not DB.exists()
    if not needs_seed:
        try:
            conn = get_db()
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='aircraft'"
            ).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM aircraft").fetchone()[0] if table else 0
            conn.close()
            needs_seed = count == 0
        except sqlite3.Error:
            needs_seed = True
    if needs_seed:
        from seed import seed
        seed()


@app.on_event("startup")
def startup():
    ensure_database_ready()
    ensure_phase4_tables()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"request": request})




def decision_support(row):
    """Explainable maintenance decision layer for the SIH prototype.
    Uses existing AI prediction + digital-twin health + telemetry thresholds.
    """
    data = dict(row)
    prediction = predict_aircraft(data)
    twin = component_health(data)
    factors = []
    if data["engine_temperature"] >= 95:
        factors.append({"factor": "Engine temperature", "value": f'{data["engine_temperature"]:.1f} °C', "severity": "HIGH"})
    elif data["engine_temperature"] >= 90:
        factors.append({"factor": "Engine temperature", "value": f'{data["engine_temperature"]:.1f} °C', "severity": "MEDIUM"})
    if data["oil_pressure"] <= 32:
        factors.append({"factor": "Oil pressure", "value": f'{data["oil_pressure"]:.1f} PSI', "severity": "HIGH"})
    elif data["oil_pressure"] <= 38:
        factors.append({"factor": "Oil pressure", "value": f'{data["oil_pressure"]:.1f} PSI', "severity": "MEDIUM"})
    if data["vibration"] >= 0.90:
        factors.append({"factor": "Vibration", "value": f'{data["vibration"]:.2f}', "severity": "HIGH"})
    elif data["vibration"] >= 0.75:
        factors.append({"factor": "Vibration", "value": f'{data["vibration"]:.2f}', "severity": "MEDIUM"})
    if data["component_age"] >= 75:
        factors.append({"factor": "Component age", "value": f'{data["component_age"]:.1f}', "severity": "MEDIUM"})
    if data["previous_failures"] >= 2:
        factors.append({"factor": "Previous failures", "value": str(data["previous_failures"]), "severity": "MEDIUM"})

    for component in twin["components"]:
        if component["health"] < 55:
            factors.append({"factor": f'{component["component"]} health', "value": f'{component["health"]:.1f}%', "severity": "HIGH"})

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    factors.sort(key=lambda x: severity_order.get(x["severity"], 3))
    factors = factors[:5]

    probability = prediction["failure_probability"] or 0
    if probability >= 85 or twin["overall_health"] < 45:
        decision = "IMMEDIATE MAINTENANCE REVIEW"
        priority = "CRITICAL"
        window = "Within 24 hours"
    elif probability >= 65 or twin["overall_health"] < 70:
        decision = "SCHEDULE PREVENTIVE INSPECTION"
        priority = "HIGH"
        window = "Within 7 days"
    elif probability >= 45:
        decision = "INCREASED MONITORING"
        priority = "MEDIUM"
        window = "Within 14 days"
    else:
        decision = "ROUTINE MONITORING"
        priority = "LOW"
        window = "Normal maintenance cycle"

    issue = prediction["predicted_issue"]

    # Keep the displayed recommendation consistent with the decision priority.
    decision_recommendation = {
        "CRITICAL": "Immediate maintenance review and priority inspection",
        "HIGH": "Schedule preventive inspection and maintenance review",
        "MEDIUM": "Increase monitoring frequency and plan preventive inspection",
        "LOW": "Continue routine monitoring",
    }[priority]

    part_map = {
        "Engine thermal stress": ["TEMP-SNS-06", "ENG-FLT-01"],
        "Vibration-related component degradation": ["VIB-SNS-02", "BRG-AXL-05"],
        "Low oil-pressure condition": ["OIL-PMP-03", "ENG-FLT-01"],
        "Aged component / wear risk": ["BRG-AXL-05"],
    }
    recommended_parts = part_map.get(issue, [])

    conn = get_db()
    part_rows = []
    if recommended_parts:
        placeholders = ",".join("?" for _ in recommended_parts)
        part_rows = conn.execute(
            f"SELECT part_code,part_name,stock,reorder_level,lead_days,unit_cost FROM spare_parts WHERE part_code IN ({placeholders})",
            recommended_parts
        ).fetchall()
    conn.close()

    parts = []
    for part in part_rows:
        status = "REORDER" if part["stock"] <= part["reorder_level"] else "AVAILABLE"
        parts.append({
            **dict(part),
            "status": status
        })

    return {
        "aircraft_code": data["aircraft_code"],
        "aircraft_type": data["aircraft_type"],
        "decision": decision,
        "priority": priority,
        "failure_probability": probability,
        "ai_risk_level": prediction["risk_level"],
        "predicted_issue": issue,
        "recommendation": decision_recommendation,
        "maintenance_window": window,
        "twin_health": twin["overall_health"],
        "current_risk_score": round(float(data["risk_score"]), 1),
        "decision_score": round(
            probability * 0.50
            + float(data["risk_score"]) * 0.30
            + (100 - twin["overall_health"]) * 0.20,
            1,
        ),
        "top_risk_factors": factors,
        "recommended_parts": parts,
    }


@app.get("/api/decision/{aircraft_code}")
def maintenance_decision(aircraft_code: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM aircraft WHERE aircraft_code=?", (aircraft_code,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Aircraft not found")
    return decision_support(row)


@app.get("/api/priority-queue")
def priority_queue():
    conn = get_db()
    rows = conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall()
    conn.close()
    queue = []
    for row in rows:
        item = decision_support(row)
        queue.append({
            "aircraft_code": item["aircraft_code"],
            "aircraft_type": item["aircraft_type"],
            "priority": item["priority"],
            "failure_probability": item["failure_probability"],
            "twin_health": item["twin_health"],
            "current_risk_score": item["current_risk_score"],
            "decision_score": item["decision_score"],
            "predicted_issue": item["predicted_issue"],
            "decision": item["decision"],
        })
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    queue.sort(
        key=lambda x: (
            order.get(x["priority"], 9),
            -float(x["decision_score"] or 0),
            -float(x["failure_probability"] or 0),
        )
    )
    for i, item in enumerate(queue, 1):
        item["rank"] = i
    return queue


@app.get("/api/insights")
def maintenance_insights():
    conn = get_db()
    aircraft = conn.execute("SELECT * FROM aircraft").fetchall()
    low_stock = conn.execute("SELECT * FROM spare_parts WHERE stock<=reorder_level ORDER BY lead_days DESC").fetchall()
    upcoming = conn.execute(
        "SELECT * FROM maintenance_schedule WHERE due_date>=date('now') ORDER BY due_date LIMIT 10"
    ).fetchall()
    open_orders = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE status IN ('OPEN','SCHEDULED','IN PROGRESS')"
    ).fetchone()[0]
    conn.close()

    decisions = [decision_support(row) for row in aircraft]
    critical = [x for x in decisions if x["priority"] == "CRITICAL"]
    high = [x for x in decisions if x["priority"] == "HIGH"]
    medium = [x for x in decisions if x["priority"] == "MEDIUM"]

    # Keep decision-support counts separate from the dashboard's fleet-risk
    # classification so the two metrics never appear to contradict each other.
    high_risk = [x for x in aircraft if x["risk_score"] >= 75]
    medium_risk = [x for x in aircraft if 50 <= x["risk_score"] < 75]
    healthy = [x for x in aircraft if x["risk_score"] < 50]

    return {
        # Decision-support priority counts
        "critical_count": len(critical),
        "high_count": len(high),
        "medium_count": len(medium),
        "low_count": len(decisions) - len(critical) - len(high) - len(medium),

        # Fleet-risk counts use the exact same thresholds as /api/summary.
        "high_risk_count": len(high_risk),
        "medium_risk_count": len(medium_risk),
        "healthy_count": len(healthy),

        "open_orders": open_orders,
        "low_stock_parts": len(low_stock),
        "critical_aircraft": [x["aircraft_code"] for x in critical[:5]],
        "low_stock": [dict(x) for x in low_stock],
        "upcoming": [dict(x) for x in upcoming],
    }


@app.get("/api/summary")
def summary():
    conn=get_db(); total=conn.execute("SELECT COUNT(*) FROM aircraft").fetchone()[0]
    high=conn.execute("SELECT COUNT(*) FROM aircraft WHERE risk_score>=75").fetchone()[0]
    medium=conn.execute("SELECT COUNT(*) FROM aircraft WHERE risk_score>=50 AND risk_score<75").fetchone()[0]
    healthy=conn.execute("SELECT COUNT(*) FROM aircraft WHERE risk_score<50").fetchone()[0]
    available=conn.execute("SELECT COUNT(*) FROM aircraft WHERE status!='HIGH RISK'").fetchone()[0]
    open_orders=conn.execute("SELECT COUNT(*) FROM work_orders WHERE status IN ('OPEN','SCHEDULED')").fetchone()[0]
    low_stock=conn.execute("SELECT COUNT(*) FROM spare_parts WHERE stock<=reorder_level").fetchone()[0]
    avg_temp=conn.execute("SELECT AVG(engine_temperature) FROM aircraft").fetchone()[0]
    avg_v=conn.execute("SELECT AVG(vibration) FROM aircraft").fetchone()[0]
    avg_p=conn.execute("SELECT AVG(oil_pressure) FROM aircraft").fetchone()[0]
    conn.close()
    return {"total":total,"high_risk":high,"medium_risk":medium,"healthy":healthy,"availability":round(available/total*100,1) if total else 0,"avg_temperature":round(avg_temp or 0,1),"avg_vibration":round(avg_v or 0,2),"avg_oil_pressure":round(avg_p or 0,1),"open_work_orders":open_orders,"low_stock_parts":low_stock}


@app.get("/api/fleet")
def fleet():
    conn=get_db(); rows=conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.get("/api/aircraft/{aircraft_code}")
def aircraft_detail(aircraft_code:str):
    conn=get_db(); row=conn.execute("SELECT * FROM aircraft WHERE aircraft_code=?",(aircraft_code,)).fetchone()
    if not row: conn.close(); raise HTTPException(404,"Aircraft not found")
    history=conn.execute("SELECT recorded_at,engine_temperature,vibration,oil_pressure FROM health_history WHERE aircraft_code=? ORDER BY recorded_at",(aircraft_code,)).fetchall()
    orders=conn.execute("SELECT * FROM work_orders WHERE aircraft_code=? ORDER BY id DESC",(aircraft_code,)).fetchall()
    conn.close(); data=dict(row); data["ai_prediction"]=predict_aircraft(data); data["health_history"]=[dict(x) for x in history]; data["work_orders"]=[dict(x) for x in orders]; return data


@app.get("/api/trends")
def trends():
    conn=get_db(); rows=conn.execute("""SELECT substr(recorded_at,1,10) day, ROUND(AVG(engine_temperature),1) avg_temperature, ROUND(AVG(vibration),2) avg_vibration, ROUND(AVG(oil_pressure),1) avg_oil_pressure FROM health_history GROUP BY substr(recorded_at,1,10) ORDER BY day""").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.get("/api/analytics")
def analytics():
    conn=get_db(); rows=conn.execute("""SELECT aircraft_type,COUNT(*) aircraft_count,ROUND(AVG(risk_score),1) avg_risk,ROUND(AVG(engine_temperature),1) avg_temperature,ROUND(AVG(vibration),2) avg_vibration FROM aircraft GROUP BY aircraft_type ORDER BY avg_risk DESC""").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.get("/api/availability")
def availability():
    conn=get_db(); rows=conn.execute("""SELECT aircraft_type,COUNT(*) total, SUM(CASE WHEN status!='HIGH RISK' THEN 1 ELSE 0 END) available, ROUND(AVG(flight_hours),1) avg_flight_hours FROM aircraft GROUP BY aircraft_type""").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.get("/api/spares")
def spares():
    conn=get_db(); rows=conn.execute("SELECT *, CASE WHEN stock<=reorder_level THEN 'REORDER' ELSE 'OK' END stock_status FROM spare_parts ORDER BY stock_status DESC, stock ASC").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.get("/api/schedule")
def schedule():
    conn=get_db(); rows=conn.execute("SELECT * FROM maintenance_schedule ORDER BY due_date").fetchall(); conn.close(); return [dict(r) for r in rows]




# ---------------------------------------------------------------------------
# PHASE 8 — FLEET AVAILABILITY & MAINTENANCE OPTIMIZATION
# ---------------------------------------------------------------------------
def _optimization_class(risk_score, failure_probability, twin_health, open_order):
    if risk_score >= 75 or failure_probability >= 85 or twin_health < 45:
        return "GROUND / PRIORITY MAINTENANCE", 100
    if risk_score >= 60 or failure_probability >= 65 or twin_health < 70:
        return "SCHEDULE PREVENTIVE MAINTENANCE", 75
    if open_order:
        return "MAINTENANCE IN PROGRESS", 60
    return "OPERATIONAL / MONITOR", 20


@app.get("/api/fleet-optimization")
def fleet_optimization():
    """Phase 8 decision-support layer for fleet readiness.

    This is a transparent SIH prototype heuristic. It optimizes maintenance
    priority around aircraft risk, AI failure probability, digital-twin health,
    open work orders, and upcoming scheduled maintenance.
    """
    conn = get_db()
    aircraft_rows = conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall()
    orders = conn.execute(
        "SELECT aircraft_code, COUNT(*) AS count FROM work_orders "
        "WHERE status IN ('OPEN','SCHEDULED','IN PROGRESS') GROUP BY aircraft_code"
    ).fetchall()
    schedule = conn.execute(
        "SELECT aircraft_code, due_date, estimated_hours, status "
        "FROM maintenance_schedule WHERE status='PLANNED' ORDER BY due_date"
    ).fetchall()
    parts = conn.execute(
        "SELECT part_code, part_name, stock, reorder_level, lead_days "
        "FROM spare_parts WHERE stock<=reorder_level ORDER BY lead_days DESC"
    ).fetchall()
    conn.close()

    order_map = {r["aircraft_code"]: int(r["count"]) for r in orders}
    schedule_map = {}
    for r in schedule:
        schedule_map.setdefault(r["aircraft_code"], []).append(dict(r))

    recommendations = []
    for row in aircraft_rows:
        d = decision_support(row)
        open_order = order_map.get(row["aircraft_code"], 0) > 0
        action, impact = _optimization_class(
            float(row["risk_score"]),
            float(d["failure_probability"] or 0),
            float(d["twin_health"]),
            open_order,
        )

        # Readiness starts at 100 and is reduced by risk/health signals.
        readiness = round(
            max(
                0,
                min(
                    100,
                    100
                    - float(row["risk_score"]) * 0.35
                    - float(d["failure_probability"] or 0) * 0.25
                    + float(d["twin_health"]) * 0.15
                    - (8 if open_order else 0),
                ),
            ),
            1,
        )

        recommendations.append({
            "aircraft_code": row["aircraft_code"],
            "aircraft_type": row["aircraft_type"],
            "risk_score": round(float(row["risk_score"]), 1),
            "failure_probability": float(d["failure_probability"] or 0),
            "twin_health": float(d["twin_health"]),
            "readiness_score": readiness,
            "priority": d["priority"],
            "action": action,
            "predicted_issue": d["predicted_issue"],
            "open_work_orders": order_map.get(row["aircraft_code"], 0),
            "scheduled_maintenance": schedule_map.get(row["aircraft_code"], [])[:1],
        })

    recommendations.sort(
        key=lambda x: (
            -x["risk_score"],
            -x["failure_probability"],
            x["readiness_score"],
        )
    )

    type_groups = {}
    for item in recommendations:
        g = type_groups.setdefault(item["aircraft_type"], {
            "aircraft_type": item["aircraft_type"],
            "total": 0,
            "ready": 0,
            "at_risk": 0,
            "avg_readiness": 0,
        })
        g["total"] += 1
        if item["readiness_score"] >= 70:
            g["ready"] += 1
        else:
            g["at_risk"] += 1

    for g in type_groups.values():
        vals = [x["readiness_score"] for x in recommendations if x["aircraft_type"] == g["aircraft_type"]]
        g["avg_readiness"] = round(sum(vals) / len(vals), 1) if vals else 0
        g["availability"] = round(g["ready"] / g["total"] * 100, 1) if g["total"] else 0

    total = len(recommendations)
    ready = sum(1 for x in recommendations if x["readiness_score"] >= 70)
    constrained = sum(1 for x in recommendations if x["readiness_score"] < 70)

    return {
        "fleet_readiness": round(ready / total * 100, 1) if total else 0,
        "ready_aircraft": ready,
        "at_risk_aircraft": constrained,
        "priority_maintenance": sum(
            1 for x in recommendations if x["action"] == "GROUND / PRIORITY MAINTENANCE"
        ),
        "low_stock_parts": [dict(x) for x in parts],
        "by_type": sorted(type_groups.values(), key=lambda x: x["avg_readiness"]),
        "recommendations": recommendations[:15],
    }



# ---------------------------------------------------------------------------
# PHASE 9 — MAINTENANCE COST & SPARE-PARTS OPTIMIZATION
# ---------------------------------------------------------------------------
PART_COSTS = {
    "BRG-AXL-05": 1800,
    "OIL-PMP-03": 4200,
    "VIB-SNS-02": 950,
    "TEMP-SNS-06": 720,
    "ENG-FLT-01": 380,
    "HYD-SEAL-04": 260,
}
AIRCRAFT_DOWNTIME_COST = {
    "Fighter": 12000,
    "Helicopter": 8000,
    "Transport": 6500,
    "Trainer": 3500,
}
DEFAULT_LABOR_RATE = 85


@app.get("/api/maintenance-optimization")
def maintenance_optimization():
    """Phase 9 transparent prototype for maintenance-cost and inventory planning.

    Costs are illustrative planning assumptions for an SIH MVP, not operational
    procurement data. The endpoint combines open work, planned maintenance,
    aircraft risk and spare-part stock into a simple what-if recommendation.
    """
    conn = get_db()
    parts = conn.execute(
        "SELECT part_code, part_name, stock, reorder_level, lead_days "
        "FROM spare_parts ORDER BY stock ASC"
    ).fetchall()
    aircraft_rows = conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall()
    schedule = conn.execute(
        "SELECT aircraft_code, maintenance_type, due_date, estimated_hours, status "
        "FROM maintenance_schedule ORDER BY due_date"
    ).fetchall()
    orders = conn.execute(
        "SELECT aircraft_code, priority, status FROM work_orders "
        "WHERE status IN ('OPEN','SCHEDULED','IN PROGRESS')"
    ).fetchall()
    conn.close()

    order_map = {}
    for r in orders:
        order_map[r["aircraft_code"]] = order_map.get(r["aircraft_code"], 0) + 1

    schedule_map = {}
    for r in schedule:
        schedule_map.setdefault(r["aircraft_code"], []).append(dict(r))

    part_rows = []
    for r in parts:
        stock = int(r["stock"])
        reorder = int(r["reorder_level"])
        shortage = max(0, reorder - stock)
        unit_cost = PART_COSTS.get(r["part_code"], 500)
        suggested_qty = max(shortage, 1) if stock <= reorder else 0
        estimated_spend = round(suggested_qty * unit_cost, 2)
        part_rows.append({
            "part_code": r["part_code"],
            "part_name": r["part_name"],
            "stock": stock,
            "reorder_level": reorder,
            "lead_days": int(r["lead_days"]),
            "unit_cost": unit_cost,
            "suggested_order_qty": suggested_qty,
            "estimated_spend": estimated_spend,
            "status": "REORDER NOW" if stock <= reorder else "STABLE",
        })

    maintenance_rows = []
    for row in aircraft_rows:
        prediction = decision_support(row)
        hours = 6
        if schedule_map.get(row["aircraft_code"]):
            hours = float(schedule_map[row["aircraft_code"]][0].get("estimated_hours") or 6)
        labor = round(hours * DEFAULT_LABOR_RATE, 2)
        downtime_day = AIRCRAFT_DOWNTIME_COST.get(row["aircraft_type"], 5000)
        urgency = "CRITICAL" if prediction["priority"] == "CRITICAL" else (
            "HIGH" if prediction["priority"] == "HIGH" else "NORMAL"
        )
        planned_cost = labor
        if order_map.get(row["aircraft_code"]):
            planned_cost += 250
        avoided_cost = round(downtime_day * (2 if urgency == "CRITICAL" else 1), 2)
        maintenance_rows.append({
            "aircraft_code": row["aircraft_code"],
            "aircraft_type": row["aircraft_type"],
            "risk_score": round(float(row["risk_score"]), 1),
            "failure_probability": float(prediction["failure_probability"] or 0),
            "priority": prediction["priority"],
            "predicted_issue": prediction["predicted_issue"],
            "estimated_hours": hours,
            "labor_cost": labor,
            "estimated_maintenance_cost": round(planned_cost, 2),
            "estimated_avoided_downtime_cost": avoided_cost,
            "net_value": round(avoided_cost - planned_cost, 2),
            "existing_work_orders": order_map.get(row["aircraft_code"], 0),
            "action": "PLAN NOW" if urgency in ("CRITICAL", "HIGH") else "MONITOR / PLAN",
        })

    maintenance_rows.sort(
        key=lambda x: (-x["net_value"], -x["risk_score"])
    )
    reorder_rows = [x for x in part_rows if x["status"] == "REORDER NOW"]
    inventory_spend = round(sum(x["estimated_spend"] for x in reorder_rows), 2)
    total_maintenance = round(sum(x["estimated_maintenance_cost"] for x in maintenance_rows), 2)
    top_value = round(sum(max(0, x["net_value"]) for x in maintenance_rows[:10]), 2)

    return {
        "assumptions": {
            "labor_rate_per_hour": DEFAULT_LABOR_RATE,
            "currency": "USD",
            "note": "Illustrative SIH MVP planning assumptions; replace with authorized fleet cost data."
        },
        "inventory": {
            "parts_to_reorder": len(reorder_rows),
            "estimated_reorder_spend": inventory_spend,
            "items": part_rows,
        },
        "maintenance": {
            "aircraft_count": len(maintenance_rows),
            "estimated_planned_cost": total_maintenance,
            "top_10_avoided_downtime_value": top_value,
            "items": maintenance_rows[:15],
        },
        "recommendation": (
            f"Prioritize {maintenance_rows[0]['aircraft_code']} for maintenance planning "
            f"and reorder {len(reorder_rows)} low-stock part(s)."
            if maintenance_rows else "No maintenance action required."
        ),
    }



# ---------------------------------------------------------------------------
# PHASE 10 — MAINTENANCE EXECUTION & CLOSURE
# ---------------------------------------------------------------------------
# Phase 9 answers "what should we plan?".
# Phase 12 closes the loop by tracking execution of those maintenance actions.
# Execution data is operational demo metadata and does not overwrite telemetry.

class MaintenanceExecutionComplete(BaseModel):
    technician: str = "Maintenance Team A"
    actual_hours: float
    result: str = "PASS"
    notes: str = ""


def _ensure_execution_for_order(conn, order):
    """Create/reuse an execution record for an in-progress work order."""
    existing = conn.execute(
        "SELECT * FROM maintenance_execution WHERE work_order_id=?",
        (order["id"],)
    ).fetchone()
    if existing:
        return existing
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO maintenance_execution
           (work_order_id, aircraft_code, technician, started_at)
           VALUES (?,?,?,?)""",
        (order["id"], order["aircraft_code"], order["assigned_team"], now)
    )
    return conn.execute(
        "SELECT * FROM maintenance_execution WHERE work_order_id=?",
        (order["id"],)
    ).fetchone()


@app.get("/api/maintenance-execution/summary")
def maintenance_execution_summary():
    conn = get_db()
    counts = {}
    for status in ("OPEN", "SCHEDULED", "IN PROGRESS", "COMPLETED", "CANCELLED"):
        counts[status] = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE status=?", (status,)
        ).fetchone()[0]
    avg_hours = conn.execute(
        "SELECT AVG(actual_hours) FROM maintenance_execution WHERE actual_hours IS NOT NULL"
    ).fetchone()[0]
    completed_hours = conn.execute(
        "SELECT COALESCE(SUM(actual_hours),0) FROM maintenance_execution "
        "WHERE actual_hours IS NOT NULL"
    ).fetchone()[0]
    rows = conn.execute(
        """SELECT e.id, e.work_order_id, e.aircraft_code, w.priority, w.issue,
                  w.assigned_team, w.scheduled_date, w.status,
                  e.technician, e.started_at, e.completed_at,
                  e.actual_hours, e.result, e.notes
           FROM maintenance_execution e
           JOIN work_orders w ON w.id=e.work_order_id
           ORDER BY CASE w.status WHEN 'IN PROGRESS' THEN 1
                                  WHEN 'SCHEDULED' THEN 2
                                  WHEN 'COMPLETED' THEN 3 ELSE 4 END,
                    w.scheduled_date, e.id DESC
           LIMIT 20"""
    ).fetchall()
    conn.close()
    return {
        "counts": counts,
        "scheduled": counts["SCHEDULED"],
        "in_progress": counts["IN PROGRESS"],
        "completed": counts["COMPLETED"],
        "cancelled": counts["CANCELLED"],
        "avg_actual_hours": round(float(avg_hours), 1) if avg_hours is not None else 0,
        "completed_hours": round(float(completed_hours), 1),
        "items": [dict(r) for r in rows],
    }


@app.get("/api/maintenance-execution/{order_id}")
def maintenance_execution(order_id: int):
    conn = get_db()
    row = conn.execute(
        """SELECT e.*, w.issue, w.priority, w.assigned_team,
                  w.scheduled_date, w.status
           FROM maintenance_execution e
           JOIN work_orders w ON w.id=e.work_order_id
           WHERE e.work_order_id=?""",
        (order_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "No execution record for this work order")
    return dict(row)


@app.post("/api/maintenance-execution/{order_id}/start")
def start_maintenance_execution(order_id: int, technician: str = "Maintenance Team A"):
    technician = (technician or "Maintenance Team A").strip()[:100]
    conn = get_db()
    order = conn.execute("SELECT * FROM work_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(404, "Work order not found")
    if order["status"] == "COMPLETED":
        conn.close()
        raise HTTPException(400, "Work order is already completed")
    if order["status"] == "CANCELLED":
        conn.close()
        raise HTTPException(400, "Cancelled work order cannot be started")
    existing = conn.execute(
        "SELECT * FROM maintenance_execution WHERE work_order_id=?", (order_id,)
    ).fetchone()
    if existing and existing["completed_at"]:
        conn.close()
        raise HTTPException(400, "Work order is already completed")
    if existing:
        conn.execute(
            "UPDATE maintenance_execution SET technician=? WHERE work_order_id=?",
            (technician, order_id)
        )
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO maintenance_execution
               (work_order_id, aircraft_code, technician, started_at)
               VALUES (?,?,?,?)""",
            (order_id, order["aircraft_code"], technician, now)
        )
    conn.execute(
        "UPDATE work_orders SET status='IN PROGRESS' WHERE id=?", (order_id,)
    )
    conn.commit()
    row = conn.execute(
        """SELECT e.*, w.issue, w.priority, w.assigned_team,
                  w.scheduled_date, w.status
           FROM maintenance_execution e
           JOIN work_orders w ON w.id=e.work_order_id
           WHERE e.work_order_id=?""",
        (order_id,)
    ).fetchone()
    conn.close()
    return {"ok": True, "execution": dict(row)}


@app.post("/api/maintenance-execution/{order_id}/complete")
def complete_maintenance_execution(order_id: int, payload: MaintenanceExecutionComplete):
    if payload.actual_hours <= 0 or payload.actual_hours > 1000:
        raise HTTPException(400, "actual_hours must be between 0 and 1000")
    result = (payload.result or "PASS").strip().upper()
    if result not in {"PASS", "CONDITIONAL", "REQUIRES FOLLOW-UP"}:
        raise HTTPException(400, "Invalid completion result")
    technician = (payload.technician or "Maintenance Team A").strip()[:100]
    notes = (payload.notes or "").strip()[:1000]

    conn = get_db()
    order = conn.execute("SELECT * FROM work_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(404, "Work order not found")
    if order["status"] == "CANCELLED":
        conn.close()
        raise HTTPException(400, "Cancelled work order cannot be completed")
    existing = conn.execute(
        "SELECT * FROM maintenance_execution WHERE work_order_id=?", (order_id,)
    ).fetchone()
    if existing and existing["completed_at"]:
        conn.close()
        raise HTTPException(400, "Work order is already completed")

    if not existing:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO maintenance_execution
               (work_order_id, aircraft_code, technician, started_at)
               VALUES (?,?,?,?)""",
            (order_id, order["aircraft_code"], technician, now)
        )
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE maintenance_execution
           SET technician=?, completed_at=?, actual_hours=?, result=?, notes=?
           WHERE work_order_id=?""",
        (technician, completed_at, round(payload.actual_hours, 1), result, notes, order_id)
    )
    conn.execute(
        "UPDATE work_orders SET status='COMPLETED' WHERE id=?", (order_id,)
    )
    # Maintenance count is execution history, not a telemetry overwrite.
    conn.execute(
        "UPDATE aircraft SET maintenance_count=maintenance_count+1 WHERE aircraft_code=?",
        (order["aircraft_code"],)
    )
    conn.commit()
    row = conn.execute(
        """SELECT e.*, w.issue, w.priority, w.assigned_team,
                  w.scheduled_date, w.status
           FROM maintenance_execution e
           JOIN work_orders w ON w.id=e.work_order_id
           WHERE e.work_order_id=?""",
        (order_id,)
    ).fetchone()
    conn.close()
    return {"ok": True, "execution": dict(row)}




# ---------------------------------------------------------------------------
# PHASE 13 — AI FLEET COMMAND & DECISION CENTER
# ---------------------------------------------------------------------------
@app.get("/api/fleet-command-center")
def fleet_command_center():
    """Phase 13 executive decision layer built from existing fleet intelligence.

    This endpoint combines current telemetry/risk, maintenance planning,
    execution state and spare-parts status into one transparent command view.
    It is a synthetic SIH MVP decision-support layer and does not modify
    aircraft telemetry or maintenance source-of-truth records.
    """
    conn = get_db()
    aircraft = conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall()
    orders = conn.execute("""
        SELECT * FROM work_orders
        ORDER BY CASE priority
            WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3 ELSE 4 END, scheduled_date, id
    """).fetchall()
    schedules = conn.execute("""
        SELECT * FROM maintenance_schedule
        ORDER BY due_date, id
    """).fetchall()
    parts = conn.execute("SELECT * FROM spare_parts ORDER BY part_code").fetchall()
    executions = conn.execute("""
        SELECT * FROM maintenance_execution
        WHERE completed_at IS NOT NULL
        ORDER BY completed_at DESC
    """).fetchall()
    conn.close()

    today = datetime.now().date()
    horizon = today + timedelta(days=7)

    # Reuse the Phase 12 transparent health calculation so Phase 13 remains
    # consistent with the existing fleet-health intelligence.
    command_rows = []
    for row in aircraft:
        prediction = predict_aircraft(dict(row))
        health = _phase12_health_score(row)
        issue = _phase12_issue(
            row["engine_temperature"],
            row["vibration"],
            row["oil_pressure"],
            row["component_age"],
            row["previous_failures"],
        )
        failure = prediction.get("failure_probability")
        failure_value = float(failure) if failure is not None else 0.0

        if health < 45 or row["risk_score"] >= 75 or failure_value >= 90:
            priority = "CRITICAL"
            action = "GROUND / PRIORITY MAINTENANCE"
        elif health < 70 or row["risk_score"] >= 60 or failure_value >= 75:
            priority = "HIGH"
            action = "SCHEDULE PREVENTIVE REVIEW"
        elif issue != "No dominant component anomaly" or failure_value >= 45:
            priority = "MEDIUM"
            action = "TARGETED MONITORING"
        else:
            priority = "LOW"
            action = "ROUTINE MONITORING"

        command_rows.append({
            "aircraft_code": row["aircraft_code"],
            "aircraft_type": row["aircraft_type"],
            "health_score": health,
            "risk_score": round(float(row["risk_score"]), 1),
            "failure_probability": failure,
            "priority": priority,
            "issue": issue if issue != "No dominant component anomaly" else prediction["predicted_issue"],
            "action": action,
            "flight_hours": round(float(row["flight_hours"]), 1),
        })

    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    command_rows.sort(
        key=lambda x: (
            priority_order[x["priority"]],
            -(float(x["failure_probability"]) if x["failure_probability"] is not None else 0),
            x["health_score"],
        )
    )

    scheduled_orders = [x for x in orders if x["status"] in ("OPEN", "SCHEDULED")]
    in_progress_orders = [x for x in orders if x["status"] == "IN PROGRESS"]
    completed_orders = [x for x in orders if x["status"] == "COMPLETED"]
    overdue_orders = []
    for x in scheduled_orders:
        try:
            due = datetime.strptime(x["scheduled_date"], "%Y-%m-%d").date()
            if due < today:
                overdue_orders.append(x)
        except (TypeError, ValueError):
            pass

    next_7_days = []
    for x in schedules:
        try:
            due = datetime.strptime(x["due_date"], "%Y-%m-%d").date()
            if today <= due <= horizon and x["status"] != "COMPLETED":
                next_7_days.append(dict(x))
        except (TypeError, ValueError):
            continue

    low_stock = [
        {
            "part_code": x["part_code"],
            "part_name": x["part_name"],
            "stock": int(x["stock"]),
            "reorder_level": int(x["reorder_level"]),
            "lead_days": int(x["lead_days"]),
            "status": "REORDER NOW" if x["stock"] <= x["reorder_level"] else "STABLE",
        }
        for x in parts
        if x["stock"] <= x["reorder_level"]
    ]

    critical = [x for x in command_rows if x["priority"] == "CRITICAL"]
    high = [x for x in command_rows if x["priority"] == "HIGH"]
    avg_health = round(
        sum(x["health_score"] for x in command_rows) / len(command_rows), 1
    ) if command_rows else 0

    # A simple transparent command score: lower health and higher failure/risk
    # move an aircraft upward in the decision queue.
    def command_score(x):
        failure = float(x["failure_probability"] or 0)
        return round(
            min(
                100,
                (100 - x["health_score"]) * 0.45
                + x["risk_score"] * 0.25
                + failure * 0.30,
            ),
            1,
        )

    for x in command_rows:
        x["command_score"] = command_score(x)

    command_rows.sort(
        key=lambda x: (-x["command_score"], priority_order[x["priority"]])
    )

    top = command_rows[:10]
    top_aircraft = top[0] if top else None

    if overdue_orders:
        headline = f"Clear {len(overdue_orders)} overdue maintenance order(s) first."
        headline_type = "URGENT"
    elif top_aircraft and top_aircraft["priority"] == "CRITICAL":
        headline = (
            f"Prioritize {top_aircraft['aircraft_code']} — highest command score; "
            f"{len(critical)} critical aircraft require attention."
        )
        headline_type = "CRITICAL"
    elif low_stock:
        headline = f"Reorder {len(low_stock)} low-stock spare part(s) before planned work."
        headline_type = "LOGISTICS"
    elif next_7_days:
        headline = f"Review {len(next_7_days)} maintenance event(s) due within 7 days."
        headline_type = "PLANNING"
    else:
        headline = "Fleet is stable; continue routine monitoring."
        headline_type = "MONITOR"

    lifecycle = {
        "detected": len([x for x in command_rows if x["risk_score"] >= 50]),
        "ai_priority": len(critical) + len(high),
        "planned": len(scheduled_orders),
        "executing": len(in_progress_orders),
        "completed": len(completed_orders),
    }

    return {
        "kpis": {
            "fleet_health": avg_health,
            "critical_aircraft": len(critical),
            "high_risk_aircraft": len(high),
            "open_work_orders": len(scheduled_orders) + len(in_progress_orders),
            "overdue_orders": len(overdue_orders),
            "next_7_days": len(next_7_days),
        },
        "headline": {
            "type": headline_type,
            "message": headline,
        },
        "top_aircraft": top_aircraft,
        "queue": top,
        "lifecycle": lifecycle,
        "recommendations": {
            "maintenance": (
                f"Prioritize {top_aircraft['aircraft_code']} — "
                f"{top_aircraft['issue']}."
                if top_aircraft else "No priority maintenance action required."
            ),
            "logistics": (
                f"Reorder {low_stock[0]['part_code']} — "
                f"{low_stock[0]['stock']}/{low_stock[0]['reorder_level']} in stock."
                if low_stock else "No spare-part reorder is currently required."
            ),
            "planning": (
                f"{len(next_7_days)} maintenance event(s) are due within the next 7 days."
                if next_7_days else "No maintenance event is due within the next 7 days."
            ),
        },
        "low_stock": low_stock,
        "next_7_days": next_7_days[:10],
    }


# ---------------------------------------------------------------------------
# PHASE 12 — FLEET HEALTH INTELLIGENCE
# ---------------------------------------------------------------------------
def _phase12_issue(temp, vibration, pressure, age, failures):
    if temp >= 95:
        return "Engine thermal stress"
    if vibration >= 0.90:
        return "Vibration-related component degradation"
    if pressure <= 32:
        return "Low oil-pressure condition"
    if age >= 75:
        return "Aged component / wear risk"
    if failures >= 2:
        return "Repeated failure history"
    return "No dominant component anomaly"


def _phase12_health_score(row):
    """Transparent fleet-health score using the existing prototype telemetry."""
    temp = float(row["engine_temperature"])
    vib = float(row["vibration"])
    pressure = float(row["oil_pressure"])
    age = float(row["component_age"])
    failures = int(row["previous_failures"])
    risk = float(row["risk_score"])
    score = 100.0
    score -= max(0.0, temp - 80.0) * 1.15
    score -= max(0.0, vib - 0.45) * 18.0
    score -= max(0.0, 38.0 - pressure) * 1.6
    score -= max(0.0, age - 60.0) * 0.22
    score -= failures * 3.0
    score -= max(0.0, risk - 40.0) * 0.18
    return round(max(0.0, min(100.0, score)), 1)


@app.get("/api/fleet-health-intelligence")
def fleet_health_intelligence():
    """Phase 12 fleet-health intelligence from current telemetry and history.

    The score is a transparent SIH MVP heuristic, not an aviation-certified
    diagnostic model. Historical telemetry is used to identify recurring
    component conditions and trend direction without modifying source data.
    """
    conn = get_db()
    aircraft = conn.execute("SELECT * FROM aircraft ORDER BY risk_score DESC").fetchall()
    history_rows = conn.execute("""
        SELECT aircraft_code, recorded_at, engine_temperature, vibration, oil_pressure
        FROM health_history ORDER BY recorded_at
    """).fetchall()
    upcoming = conn.execute("""
        SELECT aircraft_code, maintenance_type, due_date, estimated_hours, status
        FROM maintenance_schedule
        WHERE due_date >= date('now') ORDER BY due_date LIMIT 30
    """).fetchall()
    executions = conn.execute("""
        SELECT aircraft_code, result, actual_hours, completed_at
        FROM maintenance_execution
        WHERE completed_at IS NOT NULL ORDER BY completed_at DESC
    """).fetchall()
    conn.close()

    history_by_aircraft = {}
    for h in history_rows:
        history_by_aircraft.setdefault(h["aircraft_code"], []).append(dict(h))

    completed_by_aircraft = {}
    for e in executions:
        completed_by_aircraft.setdefault(e["aircraft_code"], []).append(dict(e))

    ranking = []
    issue_counts = {}
    for row in aircraft:
        d = dict(row)
        health = _phase12_health_score(row)
        issue = _phase12_issue(row["engine_temperature"], row["vibration"], row["oil_pressure"], row["component_age"], row["previous_failures"])
        issue_counts[issue] = issue_counts.get(issue, 0) + 1
        hist = history_by_aircraft.get(row["aircraft_code"], [])
        trend = "STABLE"
        if len(hist) >= 4:
            recent = hist[-3:]
            older = hist[:3]
            recent_temp = sum(float(x["engine_temperature"]) for x in recent) / len(recent)
            older_temp = sum(float(x["engine_temperature"]) for x in older) / len(older)
            recent_vib = sum(float(x["vibration"]) for x in recent) / len(recent)
            older_vib = sum(float(x["vibration"]) for x in older) / len(older)
            delta = (recent_temp - older_temp) * 0.7 + (recent_vib - older_vib) * 12
            trend = "DETERIORATING" if delta > 1.5 else ("IMPROVING" if delta < -1.5 else "STABLE")
        maintenance_count = len(completed_by_aircraft.get(row["aircraft_code"], []))
        if health < 45 or row["risk_score"] >= 75:
            action = "PRIORITY MAINTENANCE"
            priority = "CRITICAL"
        elif health < 70 or trend == "DETERIORATING":
            action = "SCHEDULE PREVENTIVE REVIEW"
            priority = "HIGH"
        elif issue != "No dominant component anomaly":
            action = "TARGETED MONITORING"
            priority = "MEDIUM"
        else:
            action = "ROUTINE MONITORING"
            priority = "LOW"
        ranking.append({
            "aircraft_code": row["aircraft_code"],
            "aircraft_type": row["aircraft_type"],
            "health_score": health,
            "risk_score": round(float(row["risk_score"]), 1),
            "trend": trend,
            "priority": priority,
            "predicted_issue": issue,
            "recommended_action": action,
            "maintenance_count": int(row["maintenance_count"]) + maintenance_count,
            "failure_history": int(row["previous_failures"]),
        })

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    ranking.sort(key=lambda x: (order[x["priority"]], x["health_score"]))

    recurring = [
        {"issue": issue, "aircraft_count": count}
        for issue, count in sorted(issue_counts.items(), key=lambda x: (-x[1], x[0]))
        if issue != "No dominant component anomaly"
    ]

    deteriorating = [x for x in ranking if x["trend"] == "DETERIORATING"]
    priority = [x for x in ranking if x["priority"] in {"CRITICAL", "HIGH"}]
    avg_health = round(sum(x["health_score"] for x in ranking) / len(ranking), 1) if ranking else 0

    return {
        "kpis": {
            "fleet_health": avg_health,
            "priority_aircraft": len(priority),
            "deteriorating_aircraft": len(deteriorating),
            "recurring_issues": len(recurring),
        },
        "ranking": ranking,
        "recurring_issues": recurring,
        "upcoming_maintenance": [dict(x) for x in upcoming],
    }


@app.get("/api/maintenance-analytics")
def maintenance_analytics():
    """Phase 12 analytics derived from actual maintenance execution records."""
    conn = get_db()
    total_orders = conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    completed_orders = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='COMPLETED'").fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='IN PROGRESS'").fetchone()[0]
    scheduled = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status IN ('SCHEDULED','OPEN')").fetchone()[0]
    avg_actual = conn.execute("SELECT AVG(actual_hours) FROM maintenance_execution WHERE actual_hours IS NOT NULL").fetchone()[0] or 0
    total_actual = conn.execute("SELECT COALESCE(SUM(actual_hours),0) FROM maintenance_execution WHERE actual_hours IS NOT NULL").fetchone()[0] or 0
    completed_exec = conn.execute("SELECT COUNT(*) FROM maintenance_execution WHERE completed_at IS NOT NULL").fetchone()[0]
    pass_count = conn.execute("SELECT COUNT(*) FROM maintenance_execution WHERE result='PASS'").fetchone()[0]
    conditional_count = conn.execute("SELECT COUNT(*) FROM maintenance_execution WHERE result='CONDITIONAL'").fetchone()[0]
    followup_count = conn.execute("SELECT COUNT(*) FROM maintenance_execution WHERE result='REQUIRES FOLLOW-UP'").fetchone()[0]
    estimated_hours = conn.execute("SELECT COALESCE(SUM(estimated_hours),0) FROM maintenance_schedule WHERE status='PLANNED'").fetchone()[0] or 0
    variance_rows = conn.execute("""
        SELECT e.aircraft_code, w.id AS work_order_id, w.issue, w.assigned_team,
               COALESCE(ms.estimated_hours,0) AS estimated_hours,
               e.actual_hours, e.result, e.started_at, e.completed_at
        FROM maintenance_execution e
        JOIN work_orders w ON w.id=e.work_order_id
        LEFT JOIN maintenance_schedule ms ON ms.aircraft_code=e.aircraft_code
        ORDER BY COALESCE(e.completed_at,e.started_at,e.created_at) DESC
    """).fetchall()
    history = [dict(r) for r in variance_rows]
    for x in history:
        est=float(x.get('estimated_hours') or 0); actual=float(x.get('actual_hours') or 0)
        x['variance_hours']=round(actual-est,2) if actual_hours_present(x) else None
    team_rows = conn.execute("""
        SELECT COALESCE(NULLIF(e.technician,''),w.assigned_team) AS team,
               COUNT(*) AS jobs,
               SUM(CASE WHEN e.completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed,
               ROUND(AVG(e.actual_hours),2) AS avg_actual_hours,
               SUM(CASE WHEN e.result='PASS' THEN 1 ELSE 0 END) AS pass_count,
               SUM(CASE WHEN e.result='CONDITIONAL' THEN 1 ELSE 0 END) AS conditional_count,
               SUM(CASE WHEN e.result='REQUIRES FOLLOW-UP' THEN 1 ELSE 0 END) AS followup_count
        FROM maintenance_execution e JOIN work_orders w ON w.id=e.work_order_id
        GROUP BY team ORDER BY completed DESC, jobs DESC
    """).fetchall()
    recent = conn.execute("""
        SELECT e.id, e.work_order_id, e.aircraft_code, w.issue, w.priority,
               COALESCE(NULLIF(e.technician,''),w.assigned_team) AS team,
               e.started_at,e.completed_at,e.actual_hours,e.result,e.notes
        FROM maintenance_execution e JOIN work_orders w ON w.id=e.work_order_id
        ORDER BY COALESCE(e.completed_at,e.started_at,e.created_at) DESC LIMIT 20
    """).fetchall()
    conn.close()
    completion_rate=round(completed_orders/total_orders*100,1) if total_orders else 0
    execution_rate=round(completed_exec/total_orders*100,1) if total_orders else 0
    pass_rate=round(pass_count/completed_exec*100,1) if completed_exec else 0
    return {
        'kpis': {'total_orders':total_orders,'completed_orders':completed_orders,'in_progress':in_progress,
                 'scheduled':scheduled,'completion_rate':completion_rate,'execution_rate':execution_rate,
                 'avg_actual_hours':round(avg_actual,2),'total_actual_hours':round(total_actual,2),
                 'pass_rate':pass_rate,'estimated_planned_hours':round(estimated_hours,2),
                 'completed_executions':completed_exec,'conditional_count':conditional_count,'followup_count':followup_count},
        'team_performance':[dict(r) for r in team_rows],
        'history':history,
        'recent':[dict(r) for r in recent]
    }

def actual_hours_present(row):
    return row.get('actual_hours') is not None

@app.get("/api/work-orders")
def work_orders():
    conn=get_db(); rows=conn.execute("SELECT * FROM work_orders ORDER BY CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, scheduled_date").fetchall(); conn.close(); return [dict(r) for r in rows]


@app.post("/api/work-orders")
def create_work_order(payload: WorkOrderCreate):
    conn=get_db(); row=conn.execute("SELECT * FROM aircraft WHERE aircraft_code=?",(payload.aircraft_code,)).fetchone()
    if not row: conn.close(); raise HTTPException(404,"Aircraft not found")
    prediction=predict_aircraft(dict(row)); priority="CRITICAL" if row["risk_score"]>=85 or prediction["risk_level"]=="HIGH" else ("HIGH" if row["risk_score"]>=60 else "MEDIUM")
    date=payload.scheduled_date or (datetime.now()+timedelta(days=2 if priority in ('CRITICAL','HIGH') else 7)).strftime("%Y-%m-%d")
    cur=conn.execute("INSERT INTO work_orders(aircraft_code,issue,priority,recommendation,assigned_team,scheduled_date,status) VALUES(?,?,?,?,?,?,?)",(row["aircraft_code"],prediction["predicted_issue"],priority,prediction["recommendation"],payload.assigned_team,date,"SCHEDULED"))
    conn.commit(); result=conn.execute("SELECT * FROM work_orders WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return dict(result)


@app.patch("/api/work-orders/{order_id}")
def update_work_order(order_id:int, status:str):
    allowed={"OPEN","SCHEDULED","IN PROGRESS","COMPLETED","CANCELLED"}
    if status not in allowed: raise HTTPException(400,"Invalid status")
    conn=get_db()
    order=conn.execute("SELECT * FROM work_orders WHERE id=?",(order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(404,"Work order not found")
    if status=="IN PROGRESS":
        _ensure_execution_for_order(conn, order)
    if status=="COMPLETED":
        existing=conn.execute(
            "SELECT * FROM maintenance_execution WHERE work_order_id=?",(order_id,)
        ).fetchone()
        if not existing:
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """INSERT INTO maintenance_execution
                   (work_order_id, aircraft_code, technician, started_at, completed_at,
                    actual_hours, result, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (order_id,order["aircraft_code"],order["assigned_team"],now,now,
                 0,"PASS","Completed from work-order status control.")
            )
        elif not existing["completed_at"]:
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """UPDATE maintenance_execution
                   SET completed_at=?, result='PASS', notes='Completed from work-order status control.'
                   WHERE work_order_id=?""",
                (now,order_id)
            )
    cur=conn.execute("UPDATE work_orders SET status=? WHERE id=?",(status,order_id))
    if status=="COMPLETED" and order["status"]!="COMPLETED":
        conn.execute(
            "UPDATE aircraft SET maintenance_count=maintenance_count+1 WHERE aircraft_code=?",
            (order["aircraft_code"],)
        )
    conn.commit(); conn.close()
    return {"ok":True,"status":status}
