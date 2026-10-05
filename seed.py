import sqlite3, random
from pathlib import Path
from datetime import datetime, timedelta
DB=Path(__file__).parent/'aeromaint.db'
def seed():
    conn=sqlite3.connect(DB); cur=conn.cursor()
    cur.execute('DROP TABLE IF EXISTS health_history'); cur.execute('DROP TABLE IF EXISTS aircraft'); cur.execute('DROP TABLE IF EXISTS spare_parts'); cur.execute('DROP TABLE IF EXISTS maintenance_execution'); cur.execute('DROP TABLE IF EXISTS work_orders'); cur.execute('DROP TABLE IF EXISTS maintenance_schedule')
    cur.execute('''CREATE TABLE aircraft(id INTEGER PRIMARY KEY AUTOINCREMENT,aircraft_code TEXT UNIQUE NOT NULL,aircraft_type TEXT NOT NULL,engine_temperature REAL NOT NULL,vibration REAL NOT NULL,oil_pressure REAL NOT NULL,flight_hours REAL NOT NULL,component_age REAL NOT NULL,previous_failures INTEGER NOT NULL,maintenance_count INTEGER NOT NULL,status TEXT NOT NULL,risk_score REAL NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE health_history(id INTEGER PRIMARY KEY AUTOINCREMENT,aircraft_code TEXT NOT NULL,recorded_at TEXT NOT NULL,engine_temperature REAL NOT NULL,vibration REAL NOT NULL,oil_pressure REAL NOT NULL)''')
    cur.execute('''CREATE TABLE spare_parts(id INTEGER PRIMARY KEY AUTOINCREMENT,part_code TEXT UNIQUE NOT NULL,part_name TEXT NOT NULL,category TEXT NOT NULL,stock INTEGER NOT NULL,reorder_level INTEGER NOT NULL,lead_days INTEGER NOT NULL,unit_cost REAL NOT NULL)''')
    cur.execute('''CREATE TABLE work_orders(id INTEGER PRIMARY KEY AUTOINCREMENT,aircraft_code TEXT NOT NULL,issue TEXT NOT NULL,priority TEXT NOT NULL,recommendation TEXT NOT NULL,assigned_team TEXT NOT NULL,scheduled_date TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'OPEN',created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE maintenance_execution(id INTEGER PRIMARY KEY AUTOINCREMENT,work_order_id INTEGER UNIQUE NOT NULL,aircraft_code TEXT NOT NULL,technician TEXT NOT NULL,started_at TEXT,completed_at TEXT,actual_hours REAL,result TEXT,notes TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE maintenance_schedule(id INTEGER PRIMARY KEY AUTOINCREMENT,aircraft_code TEXT NOT NULL,maintenance_type TEXT NOT NULL,due_date TEXT NOT NULL,estimated_hours REAL NOT NULL,status TEXT NOT NULL DEFAULT 'PLANNED')''')
    types=['Fighter','Transport','Helicopter','Trainer']; random.seed(42); aircraft=[]
    for i in range(1,31):
        temp=round(random.uniform(65,105),1); vibration=round(random.uniform(.15,1.15),2); pressure=round(random.uniform(28,55),1); hours=round(random.uniform(200,4200),1); age=round(random.uniform(5,95),1); failures=random.randint(0,4); maintenance=random.randint(1,12)
        score=round(min(100,max(0,temp-70)+vibration*28+max(0,40-pressure)*.9+max(0,age-50)*.35+failures*5),1); status='HIGH RISK' if score>=75 else ('MEDIUM RISK' if score>=50 else 'HEALTHY'); code=f'AC-{100+i}'
        cur.execute('INSERT INTO aircraft(aircraft_code,aircraft_type,engine_temperature,vibration,oil_pressure,flight_hours,component_age,previous_failures,maintenance_count,status,risk_score) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(code,random.choice(types),temp,vibration,pressure,hours,age,failures,maintenance,status,score)); aircraft.append((code,temp,vibration,pressure,score))
    now=datetime.now()
    for code,ct,cv,cp,score in aircraft:
        for day in range(14,0,-1):
            trend=(14-day)/14; temp=ct-random.uniform(0,8)+trend*random.uniform(0,3); vib=cv-random.uniform(0,.25)+trend*random.uniform(0,.1); pres=cp+random.uniform(-3,3)-trend*random.uniform(0,1.5); ts=now-timedelta(days=day)
            cur.execute('INSERT INTO health_history(aircraft_code,recorded_at,engine_temperature,vibration,oil_pressure) VALUES(?,?,?,?,?)',(code,ts.strftime('%Y-%m-%d %H:%M:%S'),round(max(50,temp),1),round(max(.05,vib),2),round(max(20,pres),1)))
    parts=[('ENG-FLT-01','Engine Filter','Engine',18,8,5,4200),('VIB-SNS-02','Vibration Sensor','Avionics',7,5,12,18500),('OIL-PMP-03','Oil Pump Assembly','Engine',5,3,18,74000),('HYD-SEAL-04','Hydraulic Seal Kit','Hydraulic',22,10,7,6800),('BRG-AXL-05','Bearing Assembly','Airframe',4,5,21,32000),('TEMP-SNS-06','Thermal Sensor','Avionics',12,6,9,11200)]
    cur.executemany('INSERT INTO spare_parts(part_code,part_name,category,stock,reorder_level,lead_days,unit_cost) VALUES(?,?,?,?,?,?,?)',parts)
    for i,(code,ct,cv,cp,score) in enumerate(sorted(aircraft,key=lambda x:x[4],reverse=True)):
        due=(now+timedelta(days=(2+i%18 if score>=50 else 15+i%30))).strftime('%Y-%m-%d'); mtype='Preventive Inspection' if score>=50 else 'Routine Service'; hours=6 if score>=50 else 4
        cur.execute('INSERT INTO maintenance_schedule(aircraft_code,maintenance_type,due_date,estimated_hours,status) VALUES(?,?,?,?,?)',(code,mtype,due,hours,'PLANNED'))

    # Phase 10 demo work order: keeps the execution workflow immediately testable
    # on a fresh synthetic SIH installation.
    cur.execute('''
        INSERT INTO work_orders(
            aircraft_code, issue, priority, recommendation, assigned_team,
            scheduled_date, status
        ) VALUES(?,?,?,?,?,?,?)
    ''',(
        'AC-113',
        'Engine thermal stress',
        'CRITICAL',
        'Immediate maintenance review and priority inspection',
        'Maintenance Team A',
        (now + timedelta(days=2)).strftime('%Y-%m-%d'),
        'SCHEDULED'
    ))

    conn.commit(); conn.close(); print('Phase 10 seed complete: fleet + history + spares + work orders + maintenance schedule + execution tracking.')
if __name__=='__main__': seed()
