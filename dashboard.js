let selectedAircraft=null;
function drawLineChart(id,labels,values,suffix=''){const c=document.getElementById(id),ctx=c.getContext('2d'),w=c.width,h=c.height,p=38,min=Math.min(...values),max=Math.max(...values),range=(max-min)||1;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#263650';ctx.lineWidth=1;ctx.font='11px Arial';ctx.fillStyle='#91a0b7';for(let i=0;i<5;i++){let y=p+i*(h-p*2)/4;ctx.beginPath();ctx.moveTo(p,y);ctx.lineTo(w-p,y);ctx.stroke();ctx.fillText((max-i*range/4).toFixed(1)+suffix,4,y+4)}ctx.strokeStyle='#56b4ff';ctx.lineWidth=3;ctx.beginPath();values.forEach((v,i)=>{let x=p+i*(w-p*2)/(values.length-1||1),y=h-p-((v-min)/range)*(h-p*2);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle='#56b4ff';values.forEach((v,i)=>{let x=p+i*(w-p*2)/(values.length-1||1),y=h-p-((v-min)/range)*(h-p*2);ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill()});ctx.fillStyle='#91a0b7';labels.forEach((l,i)=>{if(i%Math.ceil(labels.length/7)===0||i===labels.length-1){let x=p+i*(w-p*2)/(labels.length-1||1);ctx.fillText(l.slice(5),x-15,h-10)}})}

let twinTimer=null;
let twinAircraft=null;
let twinSimulationRunning=false;

async function showDigitalTwin(code){
  twinAircraft=code;
  const panel=document.getElementById('digitalTwinPanel');
  panel.classList.remove('hidden');
  document.getElementById('twinTitle').textContent=code;
  document.getElementById('simulationScenario').value='NORMAL';
  setSimulationUI(false,'IDLE');
  const r=await fetch('/api/digital-twin/'+encodeURIComponent(code)+'/simulation');
  const data=await r.json();
  document.getElementById('twinTitle').textContent=data.aircraft_code+' • '+data.aircraft_type;
  renderTwinSimulation(data);
  panel.scrollIntoView({behavior:'smooth',block:'start'});
  startTwinTelemetry();
}

function renderTwinSimulation(data){
  const p=data.prediction || {};
  const t=data.telemetry || {};
  const health=Number(p.twin_health ?? data.overall_health ?? 0);
  const score=document.getElementById('twinHealth');
  score.textContent=health+'%';

  const state=document.getElementById('twinState');
  state.textContent=health>=70?'HEALTHY':(health>=45?'ATTENTION':'CRITICAL');
  state.className='status '+(health>=70?'healthy':(health>=45?'medium-risk':'high-risk'));

  document.getElementById('twinAlerts').innerHTML=buildTwinAlerts(t,health,p);
  document.getElementById('liveFailureProbability').textContent=(p.failure_probability ?? '—')+'%';
  document.getElementById('liveRiskLevel').textContent=p.risk_level || '—';
  document.getElementById('livePriority').textContent=p.priority || '—';
  document.getElementById('liveIssue').textContent=p.predicted_issue || '—';

  document.getElementById('componentGrid').innerHTML=(p.components || []).map(c=>{
    const cls=c.health>=70?'healthy':(c.health>=45?'medium':'critical');
    return `<article class="component-card">
      <div class="component-head"><b>${c.component}</b><strong>${c.health}%</strong></div>
      <div class="health-track"><span class="${cls}" style="width:${c.health}%"></span></div>
      <small>${c.status} • ${c.basis}</small>
    </article>`;
  }).join('');

  updateTwinTelemetry(t);
}

function buildTwinAlerts(t,health,p){
  const alerts=[];
  if(Number(t.engine_temperature)>=95) alerts.push('Engine temperature above 95 °C');
  if(Number(t.vibration)>=0.90) alerts.push('High vibration detected');
  if(Number(t.oil_pressure)<=32) alerts.push('Low oil-pressure condition');
  if(health<70 && !alerts.length) alerts.push('Digital-twin health requires maintenance review');
  if((p.priority==='CRITICAL' || p.priority==='HIGH') && !alerts.includes('Maintenance priority elevated')){
    alerts.push('Maintenance priority elevated');
  }
  return alerts.length ? alerts.map(a=>`<div class="alert-item">${a}</div>`).join('') : '<div class="muted">No active alerts</div>';
}

function updateTwinTelemetry(t){
  if(!t)return;
  document.getElementById('liveTemp').textContent=t.engine_temperature+' °C';
  document.getElementById('liveVibration').textContent=t.vibration;
  document.getElementById('livePressure').textContent=t.oil_pressure+' PSI';
  document.getElementById('liveHours').textContent=t.flight_hours;
  document.getElementById('twinUpdated').textContent=(t.simulation_running?'Live simulation • ':'Telemetry • ')+(t.timestamp || 'updated');
}

function setSimulationUI(running,state){
  twinSimulationRunning=running;
  const badge=document.getElementById('simulationState');
  badge.textContent=state;
  badge.className='status '+(running?'healthy':'medium-risk')+(running?' simulation-pulse':'');
  document.getElementById('startSimulationBtn').disabled=running;
  document.getElementById('stopSimulationBtn').disabled=!running;
}

async function startTwinSimulation(){
  if(!twinAircraft)return;
  const scenario=document.getElementById('simulationScenario').value;
  const r=await fetch('/api/digital-twin/'+encodeURIComponent(twinAircraft)+'/simulation/start?scenario='+encodeURIComponent(scenario),{method:'POST'});
  if(!r.ok){alert('Could not start the digital twin simulation.');return;}
  const data=await r.json();
  setSimulationUI(true,scenario);
  renderTwinSimulation(data);
  startTwinTelemetry();
}

async function stopTwinSimulation(){
  if(!twinAircraft)return;
  const r=await fetch('/api/digital-twin/'+encodeURIComponent(twinAircraft)+'/simulation/stop',{method:'POST'});
  if(!r.ok)return;
  const data=await r.json();
  setSimulationUI(false,'PAUSED');
  renderTwinSimulation(data);
}

async function resetTwinSimulation(){
  if(!twinAircraft)return;
  const r=await fetch('/api/digital-twin/'+encodeURIComponent(twinAircraft)+'/simulation/reset',{method:'POST'});
  if(!r.ok)return;
  const data=await r.json();
  document.getElementById('simulationScenario').value='NORMAL';
  setSimulationUI(false,'IDLE');
  renderTwinSimulation(data);
}

async function refreshTwinTelemetry(){
  if(!twinAircraft)return;
  const r=await fetch('/api/digital-twin/'+encodeURIComponent(twinAircraft)+'/simulation');
  if(!r.ok)return;
  const data=await r.json();
  renderTwinSimulation(data);
  setSimulationUI(data.running,data.running?data.scenario:'PAUSED');
}

function startTwinTelemetry(){
  if(twinTimer)clearInterval(twinTimer);
  refreshTwinTelemetry();
  twinTimer=setInterval(refreshTwinTelemetry,2000);
}

function closeDigitalTwin(){
  document.getElementById('digitalTwinPanel').classList.add('hidden');
  if(twinTimer){clearInterval(twinTimer);twinTimer=null;}
  twinAircraft=null;
  twinSimulationRunning=false;
}


async function loadMaintenanceOptimization(){
  const r=await fetch('/api/maintenance-optimization');
  if(!r.ok)return;
  const d=await r.json();
  const money=v=>'$'+Number(v||0).toLocaleString(undefined,{maximumFractionDigits:0});
  document.getElementById('phase9ReorderCount').textContent=d.inventory.parts_to_reorder;
  document.getElementById('phase9ReorderSpend').textContent=money(d.inventory.estimated_reorder_spend);
  document.getElementById('phase9MaintenanceCost').textContent=money(d.maintenance.estimated_planned_cost);
  document.getElementById('phase9AvoidedValue').textContent=money(d.maintenance.top_10_avoided_downtime_value);
  document.getElementById('phase9PartsBody').innerHTML=d.inventory.items.map(x=>`<tr>
    <td><b>${x.part_code}</b><br><small>${x.part_name}</small></td>
    <td>${x.stock}</td><td>${x.reorder_level}</td><td>${x.suggested_order_qty}</td>
    <td>${money(x.estimated_spend)}</td>
    <td><span class="status ${x.status==='REORDER NOW'?'high-risk':'healthy'}">${x.status}</span></td>
  </tr>`).join('');
  document.getElementById('phase9MaintenanceBody').innerHTML=d.maintenance.items.slice(0,12).map(x=>`<tr>
    <td><b>${x.aircraft_code}</b><br><small>${x.aircraft_type}</small></td>
    <td><span class="priority ${x.priority.toLowerCase()}">${x.priority}</span></td>
    <td>${money(x.estimated_maintenance_cost)}</td>
    <td>${money(x.estimated_avoided_downtime_cost)}</td>
    <td><b>${money(x.net_value)}</b></td>
    <td>${x.action}</td>
  </tr>`).join('');
  document.getElementById('phase9Recommendation').textContent=d.recommendation;
}

async function showDecision(code){
  const panel=document.getElementById('decisionPanel');
  const d=await (await fetch('/api/decision/'+encodeURIComponent(code))).json();
  document.getElementById('decisionTitle').textContent=d.aircraft_code+' • '+d.aircraft_type;
  document.getElementById('decisionText').textContent=d.decision;
  const p=document.getElementById('decisionPriority');
  p.textContent=d.priority; p.className='priority '+d.priority.toLowerCase();
  document.getElementById('decisionFailure').textContent=(d.failure_probability ?? '—')+'%';
  document.getElementById('decisionTwin').textContent=d.twin_health+'%';
  document.getElementById('decisionWindow').textContent=d.maintenance_window;
  document.getElementById('decisionIssue').textContent=d.predicted_issue;
  document.getElementById('decisionRecommendation').textContent=d.recommendation;
  document.getElementById('riskFactors').innerHTML=d.top_risk_factors.length
    ? d.top_risk_factors.map(x=>`<div class="factor"><div><b>${x.factor}</b><small>${x.value}</small></div><span class="factor-${x.severity.toLowerCase()}">${x.severity}</span></div>`).join('')
    : '<div class="muted">No dominant risk factor detected.</div>';
  document.getElementById('recommendedParts').innerHTML=d.recommended_parts.length
    ? d.recommended_parts.map(x=>`<div class="part-rec"><div><b>${x.part_code}</b><small>${x.part_name} • Stock ${x.stock} / Reorder ${x.reorder_level}</small></div><span class="status ${x.status==='REORDER'?'high-risk':'healthy'}">${x.status}</span></div>`).join('')
    : '<div class="muted">No specific spare part recommendation.</div>';
  panel.classList.remove('hidden');
  panel.scrollIntoView({behavior:'smooth',block:'start'});
}
function closeDecision(){document.getElementById('decisionPanel').classList.add('hidden')}

async function loadPriorityQueue(){
  const rows=await(await fetch('/api/priority-queue')).json();
  document.getElementById('priorityBody').innerHTML=rows.slice(0,12).map(x=>`<tr>
    <td><b>#${x.rank}</b></td><td><b>${x.aircraft_code}</b><br><small>${x.aircraft_type}</small></td>
    <td><span class="priority ${x.priority.toLowerCase()}">${x.priority}</span></td>
    <td>${x.failure_probability}%</td><td>${x.twin_health}%</td><td>${x.predicted_issue}</td>
    <td><button class="decision-btn" onclick="showDecision('${x.aircraft_code}')">View</button></td>
  </tr>`).join('');
}

async function loadInsights(){
  const d=await(await fetch('/api/insights')).json();

  // Fleet-risk cards use the same thresholds as /api/summary:
  // HIGH RISK >= 75, MEDIUM RISK 50-74.9, HEALTHY < 50.
  document.getElementById('riskInsightsGrid').innerHTML=[
    ['HIGH RISK',d.high_risk_count,'critical'],
    ['MEDIUM RISK',d.medium_risk_count,'high'],
    ['HEALTHY',d.healthy_count,'medium'],
  ].map(x=>`<div class="insight-card ${x[2]}"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('');

  // Decision-support priority is a separate AI layer and can legitimately
  // classify an aircraft differently from its raw fleet-risk bucket.
  document.getElementById('insightsGrid').innerHTML=[
    ['CRITICAL DECISION',d.critical_count,'critical'],
    ['HIGH DECISION',d.high_count,'high'],
    ['MEDIUM DECISION',d.medium_count,'medium'],
    ['OPEN ORDERS',d.open_orders,'info']
  ].map(x=>`<div class="insight-card ${x[2]}"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('');
  document.getElementById('insightParts').innerHTML=d.low_stock.length
    ? d.low_stock.map(x=>`<div class="insight-row"><b>${x.part_code}</b><span>${x.stock}/${x.reorder_level} • ${x.lead_days}d lead</span></div>`).join('')
    : '<div class="muted">No parts require reorder.</div>';
}

async function showPrediction(code){selectedAircraft=code;const d=await(await fetch('/api/aircraft/'+code)).json(),p=d.ai_prediction;document.getElementById('predictionPanel').classList.remove('hidden');document.getElementById('aircraftTitle').textContent=d.aircraft_code+' • '+d.aircraft_type;document.getElementById('failureProbability').textContent=p.failure_probability+'%';document.getElementById('aiRisk').textContent=p.risk_level;document.getElementById('predictedIssue').textContent=p.predicted_issue;document.getElementById('recommendation').textContent=p.recommendation;document.getElementById('scheduleDate').value='';drawLineChart('aircraftChart',d.health_history.map(x=>x.recorded_at),d.health_history.map(x=>x.engine_temperature),'°');document.getElementById('predictionPanel').scrollIntoView({behavior:'smooth'})}
function closePrediction(){document.getElementById('predictionPanel').classList.add('hidden')}
async function createWorkOrder(){if(!selectedAircraft)return;const payload={aircraft_code:selectedAircraft,assigned_team:document.getElementById('team').value,scheduled_date:document.getElementById('scheduleDate').value||null};const r=await fetch('/api/work-orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(r.ok){alert('Maintenance work order created successfully.');loadAll()}else alert('Could not create work order.')}
async function loadWorkOrders(){
  const rows=await(await fetch('/api/work-orders')).json();
  document.getElementById('ordersBody').innerHTML=rows.map(x=>{
    const action=x.status==='SCHEDULED'||x.status==='OPEN'
      ? `<button class="execute-btn" onclick="startExecution(${x.id})">Start</button>`
      : x.status==='IN PROGRESS'
        ? `<button class="execute-btn complete" onclick="completeExecution(${x.id})">Complete</button>`
        : `<span class="muted">${x.status==='COMPLETED'?'DONE':'—'}</span>`;
    return `<tr>
      <td>#${x.id}</td><td>${x.aircraft_code}</td>
      <td><span class="priority ${x.priority.toLowerCase()}">${x.priority}</span></td>
      <td>${x.issue}</td><td>${x.assigned_team}</td><td>${x.scheduled_date}</td>
      <td><select onchange="updateOrder(${x.id},this.value)">
        <option ${x.status==='OPEN'?'selected':''}>OPEN</option>
        <option ${x.status==='SCHEDULED'?'selected':''}>SCHEDULED</option>
        <option ${x.status==='IN PROGRESS'?'selected':''}>IN PROGRESS</option>
        <option ${x.status==='COMPLETED'?'selected':''}>COMPLETED</option>
        <option ${x.status==='CANCELLED'?'selected':''}>CANCELLED</option>
      </select></td>
      <td>${action}</td>
    </tr>`;
  }).join('')||'<tr><td colspan="8" class="muted">No work orders yet.</td></tr>';
}
async function updateOrder(id,status){await fetch('/api/work-orders/'+id+'?status='+encodeURIComponent(status),{method:'PATCH'});loadWorkOrders();loadExecution();loadAll()}
async function startExecution(id){
  const technician=prompt('Technician / maintenance team:', 'Maintenance Team A');
  if(technician===null)return;
  const r=await fetch('/api/maintenance-execution/'+id+'/start?technician='+encodeURIComponent(technician||'Maintenance Team A'),{method:'POST'});
  if(!r.ok){alert((await r.json()).detail||'Could not start maintenance execution.');return;}
  loadWorkOrders();loadExecution();loadMaintenanceAnalytics();
}
async function loadMaintenanceAnalytics(){
  const r=await fetch('/api/maintenance-analytics');
  if(!r.ok)return;
  const d=await r.json(), k=d.kpis;
  document.getElementById('analyticsCompletionRate').textContent=k.completion_rate+'%';
  document.getElementById('analyticsCompleted').textContent=k.completed_orders;
  document.getElementById('analyticsAvgHours').textContent=k.avg_actual_hours+' h';
  document.getElementById('analyticsPassRate').textContent=k.pass_rate+'%';
  document.getElementById('analyticsTeamBody').innerHTML=d.team_performance.map(x=>`<tr>
    <td><b>${x.team}</b></td><td>${x.jobs}</td><td>${x.completed}</td><td>${x.avg_actual_hours??'—'}</td><td>${x.pass_count}</td><td>${x.followup_count}</td>
  </tr>`).join('')||'<tr><td colspan="6" class="muted">No execution records yet. Complete a Phase 10 work order to generate analytics.</td></tr>';
  document.getElementById('analyticsSummaryGrid').innerHTML=[
    ['Scheduled / Open',k.scheduled],['In Progress',k.in_progress],['Total Actual Hours',k.total_actual_hours+' h'],
    ['Completed Executions',k.completed_executions],['Conditional',k.conditional_count],['Follow-up',k.followup_count],
    ['Planned Hours',k.estimated_planned_hours+' h'],['Execution Rate',k.execution_rate+'%']
  ].map(x=>`<div class="insight-card info"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('');
  const moneyless=d.history||[];
  document.getElementById('analyticsHistoryBody').innerHTML=moneyless.map(x=>`<tr>
    <td>#${x.work_order_id}</td><td><b>${x.aircraft_code}</b></td><td>${x.issue}</td><td>${x.estimated_hours??'—'}</td>
    <td>${x.actual_hours??'—'}</td><td>${x.variance_hours===null?'—':(x.variance_hours>0?'+':'')+x.variance_hours}</td>
    <td>${x.result?`<span class="execution-result ${x.result==='PASS'?'pass':x.result==='CONDITIONAL'?'conditional':'followup'}">${x.result}</span>`:'<span class="muted">IN PROGRESS</span>'}</td>
    <td>${x.completed_at||'—'}</td>
  </tr>`).join('')||'<tr><td colspan="8" class="muted">No maintenance execution records yet.</td></tr>';
}

async function completeExecution(id){
  const hours=prompt('Actual maintenance hours:', '6');
  if(hours===null)return;
  const actual=parseFloat(hours);
  if(!Number.isFinite(actual)||actual<=0){alert('Enter a valid positive number of hours.');return;}
  const technician=prompt('Technician / maintenance team:', 'Maintenance Team A');
  if(technician===null)return;
  const result=prompt('Completion result: PASS / CONDITIONAL / REQUIRES FOLLOW-UP','PASS');
  if(result===null)return;
  const notes=prompt('Maintenance notes (optional):','Inspection completed and aircraft cleared for monitoring.')||'';
  const r=await fetch('/api/maintenance-execution/'+id+'/complete',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({technician,actual_hours:actual,result,notes})
  });
  if(!r.ok){alert((await r.json()).detail||'Could not complete maintenance execution.');return;}
  alert('Maintenance execution completed and work order closed.');
  loadWorkOrders();loadExecution();loadAll();
}
async function loadExecution(){
  const r=await fetch('/api/maintenance-execution/summary');
  if(!r.ok)return;
  const d=await r.json();
  document.getElementById('execScheduled').textContent=d.scheduled;
  document.getElementById('execInProgress').textContent=d.in_progress;
  document.getElementById('execCompleted').textContent=d.completed;
  document.getElementById('execAvgHours').textContent=d.avg_actual_hours+' h';
  document.getElementById('executionBody').innerHTML=d.items.map(x=>{
    const action=x.status==='SCHEDULED'||x.status==='OPEN'
      ? `<button class="execute-btn" onclick="startExecution(${x.work_order_id})">Start</button>`
      : x.status==='IN PROGRESS'
        ? `<button class="execute-btn complete" onclick="completeExecution(${x.work_order_id})">Complete</button>`
        : `<span class="status healthy">CLOSED</span>`;
    const result=x.result?`<span class="execution-result ${x.result==='PASS'?'pass':x.result==='CONDITIONAL'?'conditional':'followup'}">${x.result}</span>`:'<span class="muted">—</span>';
    return `<tr>
      <td>#${x.work_order_id}</td><td><b>${x.aircraft_code}</b></td>
      <td>${x.issue}</td><td>${x.technician||x.assigned_team}</td>
      <td>${x.started_at||'—'}</td><td>${x.actual_hours??'—'}</td>
      <td>${result}</td><td>${action}</td>
    </tr>`;
  }).join('')||'<tr><td colspan="8" class="muted">No maintenance execution records yet. Start a scheduled work order to begin.</td></tr>';
}

async function updateOrder(id,status){await fetch('/api/work-orders/'+id+'?status='+encodeURIComponent(status),{method:'PATCH'});loadWorkOrders();loadExecution();loadAll()}
async function loadSpares(){const rows=await(await fetch('/api/spares')).json();document.getElementById('sparesBody').innerHTML=rows.map(x=>`<tr><td><b>${x.part_code}</b><br><small>${x.part_name}</small></td><td>${x.stock}</td><td>${x.reorder_level}</td><td>${x.lead_days}d</td><td><span class="status ${x.stock_status==='REORDER'?'high-risk':'healthy'}">${x.stock_status}</span></td></tr>`).join('')}
async function loadSchedule(){const rows=await(await fetch('/api/schedule')).json();document.getElementById('scheduleBody').innerHTML=rows.slice(0,15).map(x=>`<tr><td><b>${x.aircraft_code}</b></td><td>${x.maintenance_type}</td><td>${x.due_date}</td><td>${x.estimated_hours}</td><td><span class="status healthy">${x.status}</span></td></tr>`).join('')}

async function loadOptimization(){
  const r=await fetch('/api/fleet-optimization');
  if(!r.ok)return;
  const d=await r.json();
  document.getElementById('fleetReadiness').textContent=d.fleet_readiness+'%';
  document.getElementById('readyAircraft').textContent=d.ready_aircraft;
  document.getElementById('atRiskAircraft').textContent=d.at_risk_aircraft;
  document.getElementById('priorityMaintenance').textContent=d.priority_maintenance;
  document.getElementById('optimizationTypes').innerHTML=d.by_type.map(x=>`
    <div class="availability-row">
      <div><b>${x.aircraft_type}</b><small>${x.ready}/${x.total} ready • Avg readiness ${x.avg_readiness}%</small></div>
      <strong>${x.availability}%</strong>
    </div>`).join('');
  document.getElementById('optimizationBody').innerHTML=d.recommendations.map(x=>`
    <tr>
      <td><b>${x.aircraft_code}</b><br><small>${x.aircraft_type}</small></td>
      <td>${x.readiness_score}%</td>
      <td><span class="priority ${x.priority.toLowerCase()}">${x.priority}</span></td>
      <td>${x.predicted_issue}</td>
      <td>${x.action}</td>
    </tr>`).join('');
}

async function loadFleetHealthIntelligence(){
  const setText=(id,value)=>{const el=document.getElementById(id); if(el) el.textContent=value;};
  try{
    setText('phase12FleetHealth','Loading…');
    setText('phase12Priority','Loading…');
    setText('phase12Deteriorating','Loading…');
    setText('phase12Recurring','Loading…');

    const r=await fetch('/api/fleet-health-intelligence',{cache:'no-store'});
    if(!r.ok) throw new Error(`Fleet Health API returned ${r.status}`);
    const d=await r.json(), k=d.kpis || {};

    setText('phase12FleetHealth',(k.fleet_health ?? '—')+'%');
    setText('phase12Priority',k.priority_aircraft ?? 0);
    setText('phase12Deteriorating',k.deteriorating_aircraft ?? 0);
    setText('phase12Recurring',k.recurring_issues ?? 0);

    const ranking=d.ranking || [];
    document.getElementById('phase12RankingBody').innerHTML=ranking.map(x=>`<tr>
      <td><b>${x.aircraft_code}</b><br><small>${x.aircraft_type}</small></td>
      <td>${x.health_score}%</td>
      <td><span class="status ${x.trend==='DETERIORATING'?'high-risk':x.trend==='IMPROVING'?'healthy':'info'}">${x.trend}</span></td>
      <td><span class="priority ${(x.priority||'LOW').toLowerCase()}">${x.priority}</span></td>
      <td>${x.predicted_issue}</td><td>${x.recommended_action}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="muted">No fleet health records available.</td></tr>';

    const recurring=d.recurring_issues || [];
    document.getElementById('phase12RecurringList').innerHTML=recurring.map(x=>`<div class="insight-item"><b>${x.issue}</b><span>${x.aircraft_count} aircraft</span></div>`).join('') || '<div class="muted">No recurring issue pattern detected.</div>';

    const upcoming=d.upcoming_maintenance || [];
    document.getElementById('phase12UpcomingList').innerHTML=upcoming.slice(0,8).map(x=>`<div class="insight-item"><b>${x.aircraft_code}</b><span>${x.due_date} • ${x.maintenance_type}</span></div>`).join('') || '<div class="muted">No upcoming maintenance records.</div>';
  }catch(err){
    console.error('Phase 12 load failed:',err);
    setText('phase12FleetHealth','ERR');
    setText('phase12Priority','—');
    setText('phase12Deteriorating','—');
    setText('phase12Recurring','—');
    const body=document.getElementById('phase12RankingBody');
    if(body) body.innerHTML='<tr><td colspan="6" class="muted">Phase 12 data could not be loaded. Check that the FastAPI server is running and refresh.</td></tr>';
  }
}


async function loadFleetCommandCenter(){
  const setText=(id,value)=>{
    const el=document.getElementById(id);
    if(el) el.textContent=value;
  };
  try{
    const r=await fetch('/api/fleet-command-center',{cache:'no-store'});
    if(!r.ok) throw new Error(`Fleet Command API returned ${r.status}`);
    const d=await r.json();
    const k=d.kpis||{}, h=d.headline||{}, lc=d.lifecycle||{}, rec=d.recommendations||{};

    setText('phase13FleetHealth',(k.fleet_health ?? '—')+'%');
    setText('phase13Critical',k.critical_aircraft ?? 0);
    setText('phase13OpenOrders',k.open_work_orders ?? 0);
    setText('phase13Next7',k.next_7_days ?? 0);
    setText('phase13Overdue',k.overdue_orders ?? 0);
    setText('phase13HeadlineText',h.message || 'No command recommendation available.');
    setText('phase13HeadlineType',h.type || 'MONITOR');

    const headlineType=document.getElementById('phase13HeadlineType');
    if(headlineType){
      headlineType.className='priority '+(
        h.type==='URGENT'||h.type==='CRITICAL'?'critical':
        h.type==='LOGISTICS'||h.type==='PLANNING'?'medium':'low'
      );
    }

    setText('phase13MaintenanceRec',rec.maintenance||'—');
    setText('phase13LogisticsRec',rec.logistics||'—');
    setText('phase13PlanningRec',rec.planning||'—');

    const queue=d.queue||[];
    document.getElementById('phase13QueueBody').innerHTML=queue.map(x=>`<tr>
      <td><b>${x.aircraft_code}</b><br><small>${x.aircraft_type}</small></td>
      <td><b>${x.command_score}</b></td>
      <td>${x.health_score}%</td>
      <td>${x.failure_probability==null?'—':x.failure_probability+'%'}</td>
      <td><span class="priority ${(x.priority||'LOW').toLowerCase()}">${x.priority}</span></td>
      <td>${x.issue}</td>
      <td>${x.action}</td>
    </tr>`).join('') || '<tr><td colspan="7" class="muted">No priority aircraft detected.</td></tr>';

    setText('phase13Detected',lc.detected??0);
    setText('phase13AiPriority',lc.ai_priority??0);
    setText('phase13Planned',lc.planned??0);
    setText('phase13Executing',lc.executing??0);
    setText('phase13Completed',lc.completed??0);

    const parts=d.low_stock||[];
    document.getElementById('phase13PartsList').innerHTML=parts.map(x=>
      `<div class="insight-item"><b>${x.part_code}</b><span>${x.stock}/${x.reorder_level} • ${x.lead_days}d lead</span></div>`
    ).join('') || '<div class="muted">No low-stock parts.</div>';

    const schedule=d.next_7_days||[];
    document.getElementById('phase13ScheduleList').innerHTML=schedule.map(x=>
      `<div class="insight-item"><b>${x.aircraft_code}</b><span>${x.due_date} • ${x.maintenance_type}</span></div>`
    ).join('') || '<div class="muted">No maintenance due within 7 days.</div>';
  }catch(err){
    console.error('Phase 13 load failed:',err);
    setText('phase13FleetHealth','ERR');
    setText('phase13Critical','—');
    setText('phase13OpenOrders','—');
    setText('phase13Next7','—');
    setText('phase13Overdue','—');
    setText('phase13HeadlineText','Phase 13 data could not be loaded. Check the FastAPI server and refresh.');
    setText('phase13HeadlineType','ERROR');
    const body=document.getElementById('phase13QueueBody');
    if(body) body.innerHTML='<tr><td colspan="7" class="muted">Fleet Command data unavailable.</td></tr>';
  }
}

async function loadAll(){
  // Phase 13 is loaded independently so executive decision data cannot block other phases.
  loadFleetCommandCenter();
  // Phase 12 is loaded independently so a failure in another dashboard API
  // cannot leave Fleet Health Intelligence blank.
  loadFleetHealthIntelligence();

  try{
    const [s,f,t,a]=await Promise.all([
      fetch('/api/summary'),fetch('/api/fleet'),fetch('/api/trends'),fetch('/api/availability')
    ]);
    const summary=await s.json(),fleet=await f.json(),trend=await t.json(),avail=await a.json();
    document.getElementById('total').textContent=summary.total;
    document.getElementById('healthy').textContent=summary.healthy;
    document.getElementById('medium').textContent=summary.medium_risk;
    document.getElementById('high').textContent=summary.high_risk;
    document.getElementById('availability').textContent=summary.availability+'%';
    document.getElementById('openOrders').textContent=summary.open_work_orders;
    document.getElementById('lowStock').textContent=summary.low_stock_parts;
    document.getElementById('avgTemp').textContent=summary.avg_temperature+' °C';
    document.getElementById('avgVibration').textContent=summary.avg_vibration;
    document.getElementById('avgPressure').textContent=summary.avg_oil_pressure+' PSI';
    document.getElementById('fleetBody').innerHTML=fleet.map(x=>`<tr>
      <td><b>${x.aircraft_code}</b></td><td>${x.aircraft_type}</td><td><b>${x.risk_score}</b></td>
      <td><span class="status ${x.status.replace(' ','-').toLowerCase()}">${x.status}</span></td>
      <td>${x.engine_temperature} °C</td><td>${x.vibration}</td><td>${x.flight_hours}</td>
      <td><div class="action-buttons">
        <button class="ai-btn" onclick="showPrediction('${x.aircraft_code}')">AI / Plan</button>
        <button class="decision-btn" onclick="showDecision('${x.aircraft_code}')">Decision</button>
        <button class="twin-btn" onclick="showDigitalTwin('${x.aircraft_code}')">Twin</button>
      </div></td></tr>`).join('');
    drawLineChart('temperatureChart',trend.map(x=>x.day),trend.map(x=>x.avg_temperature),'°');
    document.getElementById('availabilityList').innerHTML=avail.map(x=>`<div class="avail"><span>${x.aircraft_type}</span><b>${Math.round(x.available/x.total*100)}%</b><small>${x.available}/${x.total} available</small></div>`).join('');
  }catch(err){
    console.error('Core dashboard load failed:',err);
  }

  // Load the remaining panels independently; one failed API must not block others.
  const loaders=[loadWorkOrders,loadSpares,loadSchedule,loadPriorityQueue,loadInsights,loadOptimization,loadMaintenanceOptimization,loadExecution,loadMaintenanceAnalytics];
  await Promise.allSettled(loaders.map(fn=>fn()));
}

loadAll();
