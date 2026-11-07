'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const colors = ['#65e2ca','#b297fb','#e8b97b','#8fb5d6','#e58dba','#649ad3'];
let defaults, result, config, currentTab='overview', currentGroup='speed', busy=false, scopeUpdating=false;
let chartGeneration=0, scopeGeneration=0, changed=false;
const groupsByTab = {
  overview:['speed','torque','currents','emf'],
  electric:['currents','voltages','line_voltages','emf','dq_current'],
  transforms:['clarke_current','dq_current','clarke_voltage','dq_voltage','inverse_park','inverse_clarke'],
  inverter:['gates','pwm','voltages','line_voltages'],
  energy:['power','energy','speed','torque','rotor']
};
const motorFields = [
  ['resistance','R · фазное','Ω',1,0.001],['ld','L_d','µH',1e6,.01],['lq','L_q','µH',1e6,.01],
  ['flux','Поток ψ_m','mWb',1e3,.001],['inertia','J · 10⁻¹⁰ kg·m²','',1e10,.01],
  ['friction','B · 10⁻⁹ N·m·s','',1e9,.01],['pole_pairs','Пары полюсов','p',1,1],
  ['vdc','DC-шина','V',1,.1],['current_limit','Предел i_peak','A',1,.001],
  ['continuous_rms','Длительный ток','A rms',1,.001],['max_rpm','Предел скорости','rpm',1,1000]
];
const controlFields = [
  ['foc.current_bandwidth_hz','Полоса тока','Hz',1,100],['foc.speed_bandwidth_hz','Полоса скорости','Hz',1,10],
  ['foc.damping','Демпфирование','ζ',1,.1],['foc.id_reference','Задание i_d','A',1,.01],
  ['pwm_hz','Частота ШИМ','kHz',.001,1],['substeps','Подшаги / ШИМ','N',1,10],
  ['initial_rpm','Начальная скорость','rpm',1,100],['initial_angle','Начальный θₑ','rad',1,.1]
];
function format(x, digits=0) { return Number(x).toLocaleString('ru-RU',{maximumFractionDigits:digits,minimumFractionDigits:digits}); }
function numberText(x) { return Number(Number(x).toPrecision(10)).toString(); }
function notify(message) { $('#toast').textContent=message; $('#toast').hidden=false; setTimeout(()=>$('#toast').hidden=true,3500); }
function showError(e) { $('#error').textContent=String(e.message||e); $('#error').hidden=false; $('#error').scrollIntoView({block:'nearest',behavior:'smooth'}); }
async function api(url,options) {
  const r=await fetch(url,options);
  if(!r.ok){ let body; try {body=await r.json();} catch {throw new Error(`Ошибка сервера ${r.status}`);}
    const detail=body.detail;
    throw new Error(Array.isArray(detail)?detail.map(x=>`${x.loc?.slice(1).join('.')}: ${x.msg}`).join(' · '):detail||`Ошибка ${r.status}`);
  } return r.json();
}
function fieldHtml(key,label,unit,value,step,group) {
  const id=`f-${group}-${key}`;
  return `<div class="field"><label for="${id}">${label}</label><div class="input-unit"><input id="${id}" data-key="${key}" data-group="${group}" type="number" step="${step}" value="${numberText(value)}" required><span>${unit}</span></div></div>`;
}
function renderFields() {
  $('#motor-fields').innerHTML=motorFields.map(([k,l,u,s,step])=>fieldHtml(k,l,u,config.motor[k]*s,step,'motor')).join('');
  $('#control-fields').innerHTML=controlFields.map(([k,l,u,s,step])=>fieldHtml(k,l,u,(k.startsWith('foc.')?config.foc[k.slice(4)]:config[k])*s,step,'control')).join('');
  $('#control-fields').insertAdjacentHTML('beforeend',`<div class="field"><label for="decoupling">Перекрёстная развязка</label><select id="decoupling"><option value="yes">Включена</option><option value="no">Отключена</option></select></div>`);
  $('#decoupling').value=config.foc.decoupling?'yes':'no';
  $('#duration').value=numberText(config.duration*1000);
  $('#interpolation').value=config.interpolation;
  $('#preset').value=config.preset;
  renderEvents('speed');renderEvents('load');
}
function renderEvents(kind) {
  const host=$(`#${kind}-events`); host.replaceChildren();
  config[kind].forEach((e,i)=>{
    const row=document.createElement('div');row.className='event-row';
    const t=document.createElement('input');t.type='number';t.step='1';t.min='0';t.value=numberText(e.time*1000);t.readOnly=i===0;
    t.setAttribute('aria-label',`${kind==='speed'?'Скорость':'Нагрузка'}: время точки ${i+1}, ms`);
    const v=document.createElement('input');v.type='number';v.step=kind==='speed'?'100':'0.01';v.value=numberText(e.value*(kind==='load'?1000:1));
    v.setAttribute('aria-label',`${kind==='speed'?'Скорость, rpm':'Нагрузка, mN·m'}: точка ${i+1}`);
    const b=document.createElement('button');b.textContent='×';b.disabled=i===0;b.setAttribute('aria-label','Удалить точку');
    b.onclick=()=>{readEvents(kind);config[kind].splice(i,1);renderEvents(kind);markDirty();};
    row.append(t,v,b);host.append(row);
  });
}
function readEvents(kind) {
  config[kind]=$$('.event-row',$(`#${kind}-events`)).map(row=>{const xs=$$('input',row);return {time:parseFloat(xs[0].value)/1000,value:parseFloat(xs[1].value)/(kind==='load'?1000:1)};});
}
function readConfig() {
  for(const [k,,,scale] of motorFields) config.motor[k]=parseFloat($(`[data-group="motor"][data-key="${k}"]`).value)/scale;
  for(const [k,,,scale] of controlFields) {
    const value=parseFloat($(`[data-group="control"][data-key="${k}"]`).value)/scale;
    if(k.startsWith('foc.'))config.foc[k.slice(4)]=value;else config[k]=value;
  }
  config.duration=parseFloat($('#duration').value)/1000;
  config.interpolation=$('#interpolation').value;config.preset=$('#preset').value;
  config.foc.decoupling=$('#decoupling').value==='yes';
  readEvents('speed');readEvents('load');
  if(JSON.stringify(config).includes('null'))throw new Error('Заполните все числовые параметры. Пустые значения недопустимы.');
  return structuredClone(config);
}
function markDirty() {
  if(!result)return;
  changed=true;document.body.classList.add('dirty');
  $('#run-status').textContent='ПАРАМЕТРЫ ИЗМЕНЕНЫ · НУЖЕН РАСЧЁТ';
}
function chooseScenario(kind) {
  config.duration=.12;config.initial_rpm=0;
  if(kind==='steps'){config.speed=[{time:0,value:12000},{time:.04,value:22000},{time:.08,value:16000}];config.load=[{time:0,value:0},{time:.06,value:.00008},{time:.10,value:.00014}];}
  if(kind==='load'){config.speed=[{time:0,value:16000}];config.load=[{time:0,value:0},{time:.04,value:.00015},{time:.08,value:.00005}];}
  if(kind==='reverse'){config.speed=[{time:0,value:12000},{time:.04,value:-12000},{time:.08,value:8000}];config.load=[{time:0,value:0}];}
  $$('.scenario-shortcuts button').forEach(b=>b.classList.toggle('active',b.dataset.scenario===kind));
  $('#duration').value='120';$('[data-key="initial_rpm"]').value=0;
  renderEvents('speed');renderEvents('load');markDirty();
}
async function run() {
  if(busy)return;
  let input;try{input=readConfig();}catch(e){showError(e);return;}
  busy=true;$('#error').hidden=true;document.body.classList.add('busy','running');
  $('#run').disabled=true;$('#run').innerHTML='<span class="play">◌</span> Расчёт модели…';
  $('#run-status').textContent='ИНТЕГРИРОВАНИЕ · RK4 / PWM';
  // Freeze editor controls so displayed inputs always correspond to this run.
  const locked=$$('input,select,button', $('.settings'));const disabled=locked.map(el=>el.disabled);
  locked.forEach(el=>el.disabled=true);
  try{
    result=await api('/api/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});
    changed=false;document.body.classList.remove('dirty');
    const m=result.metrics;
    $('#metric-speed').textContent=format(m.mean_tail_rpm);
    $('#metric-target').textContent=`Задание ${format(m.final_reference_rpm)} rpm · среднее 5 ms`;
    $('#metric-torque').textContent=format(m.mean_tail_torque_Nm*1000,3);
    $('#metric-current').textContent=format(m.rms_current_A,3);
    $('#metric-dt').textContent=format(m.dt*1e6,2);
    $('#metric-samples').textContent=`${format(m.samples)} точек · RK4 + PWM`;
    $('#run-status').innerHTML=`<span class="status-dot"></span> РАСЧЁТ ЗАВЕРШЁН / ${format(m.runtime_s,2)} s`;
    $('#pwm-label').textContent=`${format(input.pwm_hz/1000)} kHz · center-aligned`;
    $('#bus-label').textContent=`Vdc = ${format(input.motor.vdc,2)} V`;
    $('#warnings').replaceChildren(...result.warnings.slice(1).map(w=>{let p=document.createElement('p');p.style.color='var(--amber)';p.textContent=w;return p;}));
    $('#export-top').disabled=false;
    for(const ext of ['csv','npz','json'])$(`#export-${ext}`).href=`/api/results/${result.id}/${ext==='json'?'config':ext}`;
    await renderCharts();
  }catch(e){showError(e);$('#run-status').textContent='РАСЧЁТ НЕ ВЫПОЛНЕН';}
  finally{busy=false;document.body.classList.remove('busy','running');$('#run').disabled=false;$('#run').innerHTML='<span class="play">▶</span> Запустить расчёт';locked.forEach((el,i)=>el.disabled=disabled[i]);}
}
const groupNames = g=>Object.keys(defaults.signals).filter(k=>defaults.signals[k].group===g);
const unitFor = g=>g==='torque'?'mN·m':defaults.signals[groupNames(g)[0]].unit;
function defaultRange(g) {
  const end=result.metrics.duration;
  if(['gates','pwm','voltages','line_voltages'].includes(g))return [Math.max(0,end-.0001),end];
  if(['currents','emf','clarke_current','clarke_voltage','inverse_park','inverse_clarke','dq_voltage'].includes(g))return [Math.max(0,end-.005),end];
  return [0,end];
}
function traces(g,data) {
  return Object.keys(data.signals).map((n,i)=>({
    x:data.time.map(t=>t*1000),y:data.signals[n].map(v=>g==='torque'?v*1000:g==='gates'?v+i*1.5:v),
    customdata:data.signals[n],name:defaults.signals[n].label,yaxis:n==='omega_e'?'y2':'y',
    type:'scatter',mode:'lines',line:{color:colors[i%colors.length],width:n.includes('ref')?1.2:1.4,
      dash:n.includes('ref')?'dot':'solid',shape:['gates','pwm','voltages','line_voltages'].includes(g)?'hv':'linear'},
    hovertemplate:`%{x:.5f} ms<br>${defaults.signals[n].label}: %{${g==='gates'?'customdata':'y'}:.5g} ${g==='torque'?'mN·m':defaults.signals[n].unit}<extra></extra>`
  }));
}
function plotLayout(g,small=false,range) {
  const decimals=range?Math.min(8,Math.max(0,Math.ceil(-Math.log10((range[1]-range[0])*1000/8)))):1;
  return {paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Consolas, monospace',size:small?9:11,color:'#7d98ae'},
    margin:small?{l:51,r:g==='rotor'?60:17,t:27,b:38}:{l:77,r:g==='rotor'?77:32,t:45,b:55},
    xaxis:{title:{text:small?'':'Время, ms',standoff:12},gridcolor:'#1f3041',zeroline:false,color:'#657f96',
      tickformat:`.${decimals}f`,nticks:small?5:10,range:range?.map(x=>x*1000)},
    yaxis:{title:{text:unitFor(g),standoff:5,font:{size:small?8:11}},gridcolor:'#1f3041',zerolinecolor:'#304357',nticks:small?4:7,
      ...(g==='gates'?{tickvals:groupNames(g).map((_,i)=>i*1.5+.5),ticktext:groupNames(g).map(n=>defaults.signals[n].label),range:[-.3,9]}:{})},
    ...(g==='rotor'?{yaxis2:{overlaying:'y',side:'right',title:{text:'rad/s'},showgrid:false,zeroline:false,color:'#b297fb'}}:{}),
    legend:{orientation:'h',x:0,y:1.2,font:{size:small?8:11},tracegroupgap:0,bgcolor:'transparent',itemwidth:30},
    hovermode:'x unified',hoverlabel:{bgcolor:'#162637',bordercolor:'#35516a',font:{family:'Consolas',size:11}},
    showlegend:true,dragmode:small?false:'zoom',autosize:true
  };
}
async function signalData(g,range,limit) {
  const params=new URLSearchParams({names:groupNames(g).join(','),start:range[0],end:range[1],limit});
  return api(`/api/results/${result.id}/signals?${params}`);
}
async function renderCharts() {
  const generation=++chartGeneration;
  for(const p of $$('.mini-plot'))Plotly.purge(p);
  const host=$('#charts');host.replaceChildren();
  const gs=currentTab==='all'?Object.keys(defaults.groups):groupsByTab[currentTab];
  gs.forEach((g,i)=>{
    const card=document.createElement('article');card.className='chart-card';
    card.innerHTML=`<div class="chart-heading"><h3><span class="channel-dot"></span>${defaults.groups[g]}</h3><button aria-label="Открыть: ${defaults.groups[g]}"><svg><use href="#i-expand"/></svg></button></div><div class="mini-plot" id="mini-${g}"></div><div class="chart-footer"><span>${groupNames(g).length} CHANNELS / ${unitFor(g)}</span><span class="range-label">РАСЧЁТ…</span></div>`;
    $('button',card).onclick=()=>openGraph(g);host.append(card);
  });
  if(!result)return;
  // Limit concurrent conversions of large signal arrays in the API.
  for(const g of gs){
    if(generation!==chartGeneration)return;
    const range=defaultRange(g),data=await signalData(g,range,1400);
    if(generation!==chartGeneration)return;
    const plot=$(`#mini-${g}`);if(!plot)return;
    await Plotly.newPlot(plot,traces(g,data),plotLayout(g,true,range),{displayModeBar:false,responsive:true,scrollZoom:false});
    $('.range-label',plot.parentElement).textContent=`${format(range[0]*1000,1)}–${format(range[1]*1000,1)} ms · ${data.reduced?'обзор':'исходная сетка'}`;
  }
}
async function setTab(tab) {
  currentTab=tab;
  $$('.graph-tabs button').forEach(b=>{const on=b.dataset.tab===tab;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));});
  try{await renderCharts();}catch(e){showError(e);}
}
async function openGraph(g) {
  if(!result){notify('Сначала выполните расчёт модели.');return;}
  currentGroup=g;$('#scope-group').value=g;$('#graph-title').textContent=defaults.groups[g];
  if(!$('#graph-dialog').open)$('#graph-dialog').showModal();
  try{await renderScope(defaultRange(g));}catch(e){notify(e.message);}
}
async function renderScope(range) {
  const generation=++scopeGeneration,g=currentGroup;
  const data=await signalData(g,range,16000);
  if(generation!==scopeGeneration)return;
  scopeUpdating=true;
  const plot=$('#scope-plot');Plotly.purge(plot);
  await Plotly.newPlot(plot,traces(g,data),plotLayout(g,false,range),{responsive:true,displaylogo:false,scrollZoom:true,modeBarButtonsToRemove:['select2d','lasso2d','autoScale2d','toImage']});
  $('#scope-resolution').textContent=`Δt = ${format(data.dt*1e6,3)} µs · ${format(data.returned_count)} / ${format(data.raw_count)} точек${data.reduced?' · обзор, приблизьте для полной сетки':' · полная временная сетка'}`;
  scopeUpdating=false;
  plot.on('plotly_relayout',async ev=>{
    if(scopeUpdating)return;
    let next;
    if(ev['xaxis.autorange'])next=[0,result.metrics.duration];
    else if(ev['xaxis.range[0]']!==undefined)next=[Math.max(0,ev['xaxis.range[0]']/1000),Math.min(result.metrics.duration,ev['xaxis.range[1]']/1000)];
    if(next&&next[1]>next[0])try{await renderScope(next);}catch(e){notify(e.message);}
  });
}
async function openDocs(){
  $('#docs-dialog').showModal();
  try{const r=await fetch('/api/model');if(!r.ok)throw new Error('Описание модели недоступно');$('#model-docs').textContent=await r.text();}
  catch(e){$('#model-docs').textContent=e.message;}
}
function wireEvents(){
  $('#run').onclick=run;
  $('.settings').addEventListener('input',e=>{if(e.target.dataset.group==='motor'){$('#preset').value='custom';config.preset='custom';}markDirty();});
  $('.settings').addEventListener('change',markDirty);
  $('#preset').onchange=()=>{
    const name=$('#preset').value;if(name==='custom')return;
    try{readConfig();}catch{}
    config.motor=structuredClone(defaults.presets[name]);config.preset=name;renderFields();markDirty();
    notify(`Параметры обмотки ${name} загружены`);
  };
  $$('[data-settings]').forEach(b=>b.onclick=()=>{
    $$('[data-settings]').forEach(x=>{const on=x===b;x.classList.toggle('active',on);x.setAttribute('aria-selected',String(on));});
    $('#motor-fields').hidden=b.dataset.settings!=='motor';$('#control-fields').hidden=b.dataset.settings!=='control';
  });
  $$('[data-add]').forEach(b=>b.onclick=()=>{const k=b.dataset.add;readEvents(k);const last=config[k].at(-1);config[k].push({time:last.time+.01,value:last.value});renderEvents(k);markDirty();});
  $$('[data-scenario]').forEach(b=>b.onclick=()=>chooseScenario(b.dataset.scenario));
  $$('[data-graph]').forEach(b=>b.onclick=()=>openGraph(b.dataset.graph));
  $$('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
  $$('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  $$('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
  $('#scope-group').onchange=e=>openGraph(e.target.value);
  $$('[data-range]').forEach(b=>b.onclick=()=>{const end=result.metrics.duration;const start=b.dataset.range==='all'?0:Math.max(0,end-Number(b.dataset.range));renderScope([start,end]).catch(e=>notify(e.message));});
  $('#save-png').onclick=()=>Plotly.downloadImage($('#scope-plot'),{format:'png',filename:`pmsm-${currentGroup}`,width:1600,height:800,scale:2});
  ['#nav-docs','#theory-top','#theory-note'].forEach(id=>$(id).onclick=openDocs);
  $('#nav-signals').onclick=()=>{setTab('all');$('#signal-section').scrollIntoView({behavior:'smooth'});};
  $('#nav-model').onclick=()=>$('.settings').scrollIntoView({behavior:'smooth'});
  $('#nav-lab').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
  $('#export-top').onclick=()=>$('#export-dialog').showModal();
  $('#import-config').onclick=()=>$('#import-file').click();
  $('#import-file').onchange=async e=>{
    const file=e.target.files[0];if(!file)return;
    try{
      if(file.size>100000)throw new Error('Конфигурация должна быть меньше 100 KB.');
      const parsed=JSON.parse(await file.text());
      // Validate through FastAPI schema without starting a simulation.
      const validated=await api('/api/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(parsed)});
      config=validated;renderFields();markDirty();notify('Конфигурация загружена. Запустите расчёт.');
    }catch(err){showError(err);}finally{e.target.value='';}
  };
}
async function init(){
  try{
    defaults=await api('/api/defaults');config=structuredClone(defaults.config);
    $('#signal-count').textContent=`${Object.keys(defaults.signals).length} каналов`;
    $('#scope-group').innerHTML=Object.entries(defaults.groups).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
    renderFields();wireEvents();await run();
  }catch(e){showError(e);}
}
init();
