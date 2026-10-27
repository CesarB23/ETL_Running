import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity as ActivityIcon, ArrowDownRight, ArrowUpRight, AlertTriangle, Bike,
  CalendarDays, ChevronDown, Clock3, Footprints, Gauge, Heart, MapPin,
  Minus, Mountain, Plus, RotateCcw, Search, ShieldCheck,
} from 'lucide-react'
import {
  Area, AreaChart, CartesianGrid, ComposedChart, Legend, Line, LineChart,
  ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

type Activity = {
  activity_id: number
  activity_date: string
  distance_m: number
  duration_s: number
  pace_min_km: number | null
  avg_hr: number | null
  has_gps: boolean
  planned_workout_id: string | null
  planned_title: string | null
  plan_confidence: string | null
}
type Lap = {
  lap_index: number; distance_m: number; duration_s: number; elapsed_s:number|null; avg_hr: number | null
  intensity: string | null; lap_trigger: string | null; wkt_step_index: number | null
  pace_min_km: number | null
}
type TrackPoint = { ts_utc: string; distance_m: number; lat: number; lon: number; speed_mps: number|null; altitude_m:number|null; heart_rate:number|null; timer_running:boolean }
type PlanStep = {
  step_seq: number; kind: string; repetition: number | null; target_distance_m: number | null
  target_duration_s: number | null; pace_fast_s_km: number | null; pace_slow_s_km: number | null
  actual_pace_s_km: number | null; matched_lap_index: number | null; confidence: string
}
type Summary = { snapshot: Record<string, number | string | boolean | null>; weekly: Array<{week_start: string; distance_km: number}> }
type ProgressRow = { activity_date: string; pace_min_km: number | null; aerobic_efficiency: number | null; cardiac_drift_pct: number | null; avg_hr: number | null }
type LoadRow = { activity_date: string; training_load: number; acute_7d: number; chronic_28d: number; acwr: number | null; is_reliable: boolean }
type HealthData = { quality: Array<{dataset:string; row_count:number; distinct_keys:number; max_activity_date:string|null; rejected_count:number|null}>; alerts:string[]; snapshot:Summary['snapshot'] }
type Tab = 'activities' | 'progress' | 'load' | 'health'

const get = async <T,>(path: string): Promise<T> => {
  const response = await fetch(`/api${path}`)
  const result = await response.json()
  if (!response.ok) throw new Error(result.error ?? 'No se pudieron cargar los datos')
  return result as T
}
const fmtDate = (date: string) => new Intl.DateTimeFormat('es-MX', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(`${date.slice(0, 10)}T12:00:00`))
const fmtDuration = (seconds: number) => `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
const fmtPace = (pace: number | null | undefined) => pace == null ? '—' : `${Math.floor(pace)}:${String(Math.round((pace % 1) * 60)).padStart(2, '0')}`
const fmtDistance = (meters: number) => `${(meters / 1000).toFixed(2)}`

function RouteMap({ points }: { points: TrackPoint[] }) {
  const route = useMemo(() => {
    if (points.length < 2) return null
    const project = (point: TrackPoint, zoom: number) => {
      const n = 2 ** zoom
      const lat = Math.max(-85.0511, Math.min(85.0511, point.lat)) * Math.PI / 180
      return {
        x: (point.lon + 180) / 360 * n * 256,
        y: (1 - Math.asinh(Math.tan(lat)) / Math.PI) / 2 * n * 256,
      }
    }
    let zoom = 17
    let projected = points.map(point => project(point, zoom))
    while (zoom > 1) {
      const extent = projected.reduce((result, point) => ({
        minX:Math.min(result.minX,point.x), maxX:Math.max(result.maxX,point.x),
        minY:Math.min(result.minY,point.y), maxY:Math.max(result.maxY,point.y),
      }), {minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity})
      if (extent.maxX - extent.minX < 340 && extent.maxY - extent.minY < 210) break
      zoom -= 1
      projected = points.map(point => project(point, zoom))
    }
    const bounds = projected.reduce((result, point) => ({
      minX: Math.min(result.minX, point.x), maxX: Math.max(result.maxX, point.x),
      minY: Math.min(result.minY, point.y), maxY: Math.max(result.maxY, point.y),
    }), {minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity})
    const {minX,maxX,minY,maxY} = bounds
    const offsetX = (400 - (maxX - minX)) / 2 - minX
    const offsetY = (280 - (maxY - minY)) / 2 - minY
    const coords = projected.map(point => `${(point.x + offsetX).toFixed(1)},${(point.y + offsetY).toFixed(1)}`)
    const n = 2 ** zoom
    const tiles = []
    for (let tileY = Math.max(0, Math.floor(minY / 256) - 1); tileY <= Math.min(n - 1, Math.floor(maxY / 256) + 1); tileY++) {
      for (let tileX = Math.floor(minX / 256) - 1; tileX <= Math.floor(maxX / 256) + 1; tileX++) {
        const wrappedX = ((tileX % n) + n) % n
        tiles.push({ url: `https://tile.openstreetmap.org/${zoom}/${wrappedX}/${tileY}.png`, x: tileX * 256 + offsetX, y: tileY * 256 + offsetY })
      }
    }
    return { line: coords.join(' '), start: coords[0].split(',').map(Number), end: coords.at(-1)!.split(',').map(Number), tiles }
  }, [points])

  return <div className="route-map">
    <svg viewBox="0 0 400 280" role="img" aria-label="Mapa local del recorrido de la actividad">
      <defs>
      </defs>
      <rect width="400" height="280" fill="#edf0ea" />
      {route?.tiles.map(tile => <image key={tile.url} href={tile.url} x={tile.x} y={tile.y} width="256" height="256" preserveAspectRatio="none" />)}
      {route && <>
        <polyline points={route.line} fill="none" stroke="#fff" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points={route.line} fill="none" stroke="#fc4c02" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={route.start[0]} cy={route.start[1]} r="7" fill="#fff" stroke="#fc4c02" strokeWidth="4" />
        <circle cx={route.end[0]} cy={route.end[1]} r="8" fill="#fc4c02" stroke="#fff" strokeWidth="3" />
      </>}
    </svg>
    <div className="map-note"><MapPin size={13} /> {points.length ? 'Recorrido GPS' : 'Sin puntos GPS para esta actividad'}</div>
    {points.length > 0 && <a className="map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a>}
  </div>
}

function App() {
  const [tab, setTab] = useState<Tab>('activities')
  const [chartMetric, setChartMetric] = useState<'pace'|'heart'|'elevation'>('pace')
  const [chartAxis, setChartAxis] = useState<'distance'|'time'>('distance')
  const [showPlan, setShowPlan] = useState(true)
  const [zoomDomain, setZoomDomain] = useState<[number,number] | null>(null)
  const [dragRange, setDragRange] = useState<[number,number] | null>(null)
  const dragStart = useRef<number|null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [laps, setLaps] = useState<Lap[]>([])
  const [track, setTrack] = useState<TrackPoint[]>([])
  const [plan, setPlan] = useState<PlanStep[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([get<Activity[]>('/activities'), get<Summary>('/summary')])
      .then(([rows, overview]) => { setActivities(rows); setSummary(overview); setSelectedId(rows[0]?.activity_id ?? null) })
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Error al abrir el warehouse local'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    Promise.all([
      get<Lap[]>(`/activities/${selectedId}/laps`),
      get<TrackPoint[]>(`/activities/${selectedId}/track`),
      get<PlanStep[]>(`/activities/${selectedId}/plan`),
    ]).then(([lapRows, trackRows, planRows]) => { setLaps(lapRows); setTrack(trackRows); setPlan(planRows) })
      .catch(reason => setError(reason instanceof Error ? reason.message : 'No se pudo cargar la actividad'))
  }, [selectedId])

  useEffect(() => {
    setZoomDomain(null)
    setDragRange(null)
    dragStart.current = null
  }, [selectedId, chartAxis, chartMetric])

  const selected = activities.find(activity => activity.activity_id === selectedId)
  const filtered = activities.filter(activity => {
    const text = `${activity.planned_title ?? ''} ${activity.activity_date}`.toLowerCase()
    return text.includes(query.toLowerCase())
  })
  const chart = useMemo(() => {
    const rows: Array<{x:number; track?:number; lap?:number; plan?:number}> = []
    const firstTime = track.length ? new Date(track[0].ts_utc).getTime() : 0
    const xOf = (distance:number, elapsed:number) => chartAxis === 'distance' ? distance / 1000 : elapsed / 60
    const metricValue = (point:TrackPoint) => {
      if (chartMetric === 'heart') return point.heart_rate && point.heart_rate >= 30 ? point.heart_rate : null
      if (chartMetric === 'elevation') return point.altitude_m
      if (!point.timer_running || !point.speed_mps || point.speed_mps <= 0) return null
      const pace = 1000 / point.speed_mps / 60
      return pace >= 2.3 && pace <= 20 ? pace : null
    }
    const stride = Math.max(1, Math.ceil(track.length / 900))
    track.forEach((point,index) => {
      if (index % stride !== 0 && index !== track.length-1) return
      const elapsed = (new Date(point.ts_utc).getTime() - firstTime) / 1000
      const value = metricValue(point)
      if (value != null && Number.isFinite(value)) rows.push({x:xOf(point.distance_m,elapsed),track:value})
    })
    let distance = 0, elapsed = 0
    laps.forEach(lap => {
      const d = Number(lap.distance_m) || 0, duration = Number(lap.elapsed_s ?? lap.duration_s) || 0
      const from = xOf(distance,elapsed), to = xOf(distance+d,elapsed+duration)
      const value = chartMetric === 'pace' ? lap.pace_min_km : chartMetric === 'heart' ? lap.avg_hr : null
      if (value != null && Number.isFinite(value)) rows.push({x:from,lap:value},{x:to,lap:value})
      distance += d; elapsed += duration
    })
    if (chartMetric === 'pace' && showPlan) {
      let plannedDistance = 0, plannedElapsed = 0
      plan.slice().sort((a,b)=>a.step_seq-b.step_seq).forEach(step => {
        const target = step.pace_fast_s_km != null && step.pace_slow_s_km != null
          ? (step.pace_fast_s_km + step.pace_slow_s_km) / 120
          : null
        let d = step.target_distance_m ?? 0
        let seconds = step.target_duration_s ?? 0
        if (!d && seconds && target) d = seconds / (target * 60) * 1000
        if (!seconds && d && target) seconds = d / 1000 * target * 60
        if (target != null) rows.push({x:xOf(plannedDistance,plannedElapsed),plan:target},{x:xOf(plannedDistance+d,plannedElapsed+seconds),plan:target})
        plannedDistance += d; plannedElapsed += seconds
      })
    }
    const grouped = new Map<number,{x:number;track?:number;lap?:number;plan?:number}>()
    rows.forEach(row => grouped.set(row.x,{...grouped.get(row.x),...row}))
    return [...grouped.values()].sort((a,b)=>a.x-b.x)
  }, [chartAxis, chartMetric, laps, plan, showPlan, track])
  const runCount = Number(summary?.snapshot.runs_7d ?? 0)
  const weekKm = Number(summary?.snapshot.km_7d ?? 0)
  const chartMetricLabel = chartMetric === 'pace' ? 'Ritmo' : chartMetric === 'heart' ? 'Frecuencia cardiaca' : 'Altitud'
  const chartUnit = chartMetric === 'pace' ? 'min/km' : chartMetric === 'heart' ? 'lpm' : 'm'
  const chartMin = chart[0]?.x ?? 0
  const chartMax = chart.at(-1)?.x ?? 0
  const chartExtent = Math.max(0, chartMax - chartMin)
  const activeDomain = (zoomDomain ?? [chartMin, chartMax]) as [number,number]
  const zoomBy = (factor:number) => {
    const [left,right] = activeDomain
    const center = (left + right) / 2
    const half = Math.min(chartExtent, (right-left) * factor) / 2
    const min = Math.max(chartMin, center-half), max = Math.min(chartMax, center+half)
    setZoomDomain(max-min > 0 ? [min,max] : null)
  }
  const chartPointerX = (event: {activeLabel?: string|number}) => {
    if (event?.activeLabel == null) return null
    const value = Number(event.activeLabel)
    return Number.isFinite(value) ? value : null
  }
  const weeklyBars = [...(summary?.weekly ?? [])].slice(-8)
  const weeklyMax = Math.max(1, ...weeklyBars.map(week => week.distance_km))

  if (loading) return <main className="loading-screen"><span className="brand-mark">r</span><p>Abriendo tu entrenamiento…</p></main>
  if (error && !activities.length) return <main className="error-screen"><span className="brand-mark">r</span><h1>No se pudo abrir el dashboard</h1><p>{error}</p><code>Ejecuta <b>make app</b> desde la raíz del proyecto.</code></main>

  return <div className="app-shell">
    <header className="topbar">
      <a className="wordmark" href="#inicio" aria-label="Ritmo, inicio"><span className="brand-mark">r</span><span>ritmo</span></a>
      <nav className="main-nav">
        <button className={`nav-item ${tab === 'activities' ? 'active' : ''}`} onClick={() => setTab('activities')}><ActivityIcon size={17} /> Actividades</button>
        <button className={`nav-item ${tab === 'progress' ? 'active' : ''}`} onClick={() => setTab('progress')}><Gauge size={17} /> Progreso</button>
        <button className={`nav-item ${tab === 'load' ? 'active' : ''}`} onClick={() => setTab('load')}><ActivityIcon size={17} /> Carga</button>
        <button className={`nav-item ${tab === 'health' ? 'active' : ''}`} onClick={() => setTab('health')}><ShieldCheck size={17} /> Salud</button>
      </nav>
      <div className="local-badge"><span className="local-dot" /> Datos deportivos locales</div>
    </header>

    <main className={`workspace ${tab !== 'activities' ? 'workspace-wide' : ''}`}>
      {tab === 'activities' && <aside className="activity-rail">
        <div className="rail-heading"><div><p className="eyebrow">Tu entrenamiento</p><h1>Actividades</h1></div><button className="round-action" aria-label="Calendario"><CalendarDays size={17} /></button></div>
        <label className="search-box"><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Buscar actividad" /></label>
        <div className="activity-list">
          {filtered.map(activity => <button key={activity.activity_id} className={`activity-row ${activity.activity_id === selectedId ? 'selected' : ''}`} onClick={() => setSelectedId(activity.activity_id)}>
            <span className="sport-icon"><Footprints size={18} /></span><span className="activity-row-copy"><span className="activity-row-date">{fmtDate(activity.activity_date)}</span><strong>{activity.planned_title || 'Carrera'}</strong><span className="activity-row-meta">{fmtDistance(activity.distance_m)} km <i /> {fmtPace(activity.pace_min_km)} /km</span></span><ChevronDown className="row-chevron" size={15} />
          </button>)}
          {!filtered.length && <p className="empty-list">No hay actividades con ese nombre.</p>}
        </div>
        <section id="weekly" className="weekly-card"><div className="weekly-title"><span>Volumen semanal</span><ArrowUpRight size={16} /></div><div className="weekly-km">{weekKm.toFixed(1)} <small>km</small></div><div className="weekly-caption">{runCount} {runCount === 1 ? 'salida' : 'salidas'} · últimos 7 días</div><div className="week-bars" aria-label="Distancia por semana">{weeklyBars.map((week, index) => <span key={week.week_start} className={index === weeklyBars.length - 1 ? 'current' : ''} title={`${week.week_start}: ${week.distance_km.toFixed(1)} km`} style={{height:`${Math.max(5, week.distance_km / weeklyMax * 100)}%`}}/>)}</div><div className="week-days">{weeklyBars.map(week => <span key={week.week_start}>{new Intl.DateTimeFormat('es-MX',{day:'numeric',month:'numeric'}).format(new Date(`${week.week_start.slice(0,10)}T12:00:00`))}</span>)}</div></section>
      </aside>}

      <section className="activity-detail">
        {tab === 'progress' ? <ProgressPage /> : tab === 'load' ? <LoadPage /> : tab === 'health' ? <HealthPage /> : <>
        {selected ? <>
          <div className="detail-header"><div><div className="detail-date"><Footprints size={15} /> Carrera <span className="date-divider">/</span> {fmtDate(selected.activity_date)}</div><h2>{selected.planned_title || 'Carrera al aire libre'}</h2></div><button className="more-button">•••</button></div>
          <div className="metrics-strip">
            <Metric label="Distancia" value={fmtDistance(selected.distance_m)} unit="km" icon={<ArrowDownRight size={15}/>} />
            <Metric label="Ritmo medio" value={fmtPace(selected.pace_min_km)} unit="/km" icon={<Gauge size={15}/>} />
            <Metric label="Tiempo" value={fmtDuration(selected.duration_s)} unit="" icon={<Clock3 size={15}/>} />
            <Metric label="FC media" value={selected.avg_hr ? String(Math.round(selected.avg_hr)) : '—'} unit="bpm" icon={<Heart size={15}/>} />
          </div>

          <div className="map-section"><div className="section-head"><div><h3>Recorrido</h3><p>El trazo GPS original de tu sesión</p></div><span className="map-distance"><MapPin size={14}/>{fmtDistance(selected.distance_m)} km</span></div><RouteMap points={track}/></div>

      <section className="performance-section"><div className="section-head chart-section-head"><div><h3>{chartMetricLabel}</h3><p>Detalle por registro y promedio de cada vuelta</p></div><div className="chart-controls"><label className="chart-select"><span>Métrica</span><select value={chartMetric} onChange={event => setChartMetric(event.target.value as 'pace'|'heart'|'elevation')}><option value="pace">Ritmo</option><option value="heart">Frecuencia cardiaca</option><option value="elevation">Altitud</option></select></label><label className="chart-select"><span>Superposición</span><select value={showPlan && plan.some(step=>step.pace_fast_s_km != null) ? 'plan' : 'none'} onChange={event => setShowPlan(event.target.value === 'plan')}><option value="none">Sin superposiciones</option><option value="plan" disabled={!plan.some(step=>step.pace_fast_s_km != null)}>Plan del coach</option></select></label></div></div>
            <div className="chart-toolbar"><div className="chart-legend"><span><i className="legend-record"/> {chartMetricLabel} por registro</span><span><i className="legend-real"/> Promedio de vuelta</span>{chartMetric === 'pace' && showPlan && plan.length > 0 && <span><i className="legend-plan"/> Planificado</span>}</div><div className="zoom-controls"><button onClick={()=>zoomBy(.62)} disabled={!chart.length} aria-label="Acercar" title="Acercar"><Plus size={14}/></button><button onClick={()=>zoomBy(1.6)} disabled={!zoomDomain} aria-label="Alejar" title="Alejar"><Minus size={14}/></button><button onClick={()=>setZoomDomain(null)} disabled={!zoomDomain} aria-label="Restablecer zoom" title="Restablecer zoom"><RotateCcw size={13}/></button></div></div>
            {chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chart} margin={{top:10,right:20,left:2,bottom:10}}
              onMouseDown={state=>{const x=chartPointerX(state);if(x!=null){dragStart.current=x;setDragRange([x,x])}}}
              onMouseMove={state=>{const x=chartPointerX(state);if(dragStart.current!=null&&x!=null)setDragRange([dragStart.current,x])}}
              onMouseUp={state=>{const x=chartPointerX(state);if(dragStart.current!=null&&x!=null){const min=Math.min(dragStart.current,x),max=Math.max(dragStart.current,x);if(max-min>chartExtent*.015)setZoomDomain([min,max])}dragStart.current=null;setDragRange(null)}}>
              <CartesianGrid vertical={false} stroke="#e9ece8" strokeDasharray="3 5" />
              <XAxis dataKey="x" type="number" domain={zoomDomain ?? [chartMin,chartMax]} allowDataOverflow tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:11}} tickFormatter={v => Number(v).toFixed(chartAxis === 'distance' ? 1 : 0)} label={{value:chartAxis === 'distance' ? 'Distancia (km)' : 'Tiempo (min)',position:'insideBottomRight',offset:-5,fill:'#89918c',fontSize:10}} />
              <YAxis reversed={chartMetric === 'pace'} domain={chartMetric === 'pace' ? ['dataMin - .5','dataMax + .5'] : ['auto','auto']} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:11}} tickFormatter={v => chartMetric === 'pace' ? fmtPace(Number(v)) : `${Math.round(Number(v))}`} width={48} />
              <Tooltip labelFormatter={v => `${Number(v).toFixed(2)} ${chartAxis === 'distance' ? 'km' : 'min'}`} formatter={(value,name) => [`${chartMetric === 'pace' ? fmtPace(Number(value)) : Number(value).toFixed(0)} ${chartUnit}`, name === 'track' ? 'Por registro' : name === 'lap' ? 'Promedio de vuelta' : 'Plan del coach']} contentStyle={{border:'1px solid #e5e8e4',borderRadius:8,boxShadow:'0 8px 24px #17231b12',fontSize:12}} />
              {dragRange && <ReferenceArea x1={dragRange[0]} x2={dragRange[1]} strokeOpacity={.3} fill="#fc4c02" fillOpacity={.14}/>}
              <Area dataKey="track" name="Ritmo por registro" type="monotone" stroke="#aab0b1" strokeWidth={1.5} fill="#aab0b1" fillOpacity={.13} dot={false} connectNulls />
              <Line dataKey="lap" name="Ritmo medio de la vuelta" type="stepAfter" stroke="#3195ed" strokeWidth={2.5} dot={false} activeDot={{r:4}} connectNulls />
              {chartMetric === 'pace' && showPlan && <Line dataKey="plan" name="Plan del coach" type="stepAfter" stroke="#fc4c02" strokeWidth={2.5} strokeDasharray="7 5" dot={false} connectNulls />}
            </ComposedChart></ResponsiveContainer></div> : <div className="chart-empty"><ActivityIcon size={21}/><span>No hay registros FIT suficientes para mostrar esta métrica.</span></div>}
            {zoomDomain && <p className="zoom-hint">Vista ampliada · {zoomDomain[0].toFixed(2)}–{zoomDomain[1].toFixed(2)} {chartAxis === 'distance' ? 'km' : 'min'}</p>}
            <div className="chart-axis-toggle"><button className={chartAxis === 'time' ? 'selected' : ''} onClick={() => setChartAxis('time')}>Por tiempo</button><button className={chartAxis === 'distance' ? 'selected' : ''} onClick={() => setChartAxis('distance')}>Por distancia</button></div>
            {plan.length > 0 && chartMetric === 'pace' && showPlan && <p className="plan-note">El trazo naranja muestra el ritmo objetivo por bloque. Solo se dibujan pasos con ritmo definido y vínculo explícito.</p>}
          </section>

          <section className="splits-section"><div className="section-head"><div><h3>Desglose de la sesión</h3><p>{laps.length} laps registrados por Garmin</p></div><span className="splits-icon"><ActivityIcon size={16}/></span></div>
            {laps.length ? <div className="split-table"><div className="split-head"><span>Lap</span><span>Tipo</span><span>Distancia</span><span>Ritmo</span><span>FC media</span></div>{laps.map((lap,index) => <div className="split-row" key={lap.lap_index}><span className="lap-number">{String(index+1).padStart(2,'0')}</span><span className="split-type">{lap.wkt_step_index != null ? `Paso ${lap.wkt_step_index}` : lap.intensity || 'Carrera'}</span><span>{lap.distance_m ? `${Math.round(lap.distance_m)} m` : '—'}</span><span className="split-pace">{fmtPace(lap.pace_min_km)} <small>/km</small></span><span className="split-hr">{lap.avg_hr ? `${Math.round(lap.avg_hr)} bpm` : '—'}</span></div>)}</div> : <div className="no-splits"><span className="no-splits-icon"><ActivityIcon size={17}/></span><div><strong>Sin laps disponibles</strong><p>Procesa el archivo FIT de esta actividad para mostrar sus intervalos.</p></div></div>}
          </section>
          {error && <p className="inline-error">{error}</p>}
        </> : <div className="empty-detail"><Footprints size={32}/><h2>Selecciona una actividad</h2><p>Elige una salida de la lista para explorar su recorrido y ritmo.</p></div>}
        <footer className="footer-note"><span><span className="local-dot"/> Warehouse local</span><span>OpenStreetMap recibe solicitudes de teselas de la zona visible; no recibe tu archivo FIT.</span></footer>
        </>}
      </section>

      {tab === 'activities' && <aside className="context-rail">
        <div className="context-heading"><Mountain size={17}/><span>Tu semana</span></div>
        <div className="context-stat"><span>Distancia · últimos 7 días</span><strong>{weekKm.toFixed(1)} <small>km</small></strong></div>
        <div className="context-stat"><span>Salidas</span><strong>{runCount} <small>{runCount === 1 ? 'actividad' : 'actividades'}</small></strong><small>en los últimos 7 días</small></div>
        <div className="context-divider"/>
        <div className="context-heading"><Bike size={17}/><span>Sobre esta actividad</span></div>
        <div className="context-line"><span>Tipo</span><strong>Carrera</strong></div>
        <div className="context-line"><span>Plan del coach</span><strong>{selected?.planned_title || 'Sin vincular'}</strong></div>
        {selected?.plan_confidence && <div className="confidence-chip">Vínculo {selected.plan_confidence === 'high' ? 'confirmado' : selected.plan_confidence}</div>}
        <div className="privacy-card"><div className="privacy-icon"><MapPin size={16}/></div><div><strong>Mapa de OpenStreetMap</strong><p>Las teselas públicas permiten ver las calles. El proveedor puede inferir la zona que estás consultando.</p></div></div>
      </aside>}
    </main>
  </div>
}

function Metric({ label, value, unit, icon }: {label:string; value:string; unit:string; icon:React.ReactNode}) {
  return <div className="metric"><div className="metric-label">{icon}<span>{label}</span></div><div className="metric-value">{value}<small>{unit}</small></div></div>
}

function PageHeading({eyebrow, title, description}:{eyebrow:string;title:string;description:string}) {
  return <div className="report-heading"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div>
}

function ProgressPage() {
  const [rows, setRows] = useState<ProgressRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => { get<ProgressRow[]>('/progress').then(setRows).catch(e => setError(String(e))) }, [])
  const usable = rows.filter(row => row.pace_min_km != null)
  const latest = usable.at(-1)
  const efficiency = rows.filter(row => row.aerobic_efficiency != null).at(-1)?.aerobic_efficiency
  const drift = rows.filter(row => row.cardiac_drift_pct != null).at(-1)?.cardiac_drift_pct
  return <div className="report-page">
    <PageHeading eyebrow="Tendencia · últimos 180 días" title="Progreso" description="El contexto detrás de cada carrera: ritmo, eficiencia y respuesta cardíaca." />
    {error && <p className="inline-error">{error}</p>}
    <div className="report-metrics">
      <Metric label="Último ritmo válido" value={fmtPace(latest?.pace_min_km)} unit="/km" icon={<Gauge size={15}/>} />
      <Metric label="Eficiencia aeróbica" value={efficiency?.toFixed(3) ?? '—'} unit="m/s · bpm" icon={<ArrowUpRight size={15}/>} />
      <Metric label="Deriva cardíaca" value={drift != null ? `${drift.toFixed(1)}` : '—'} unit="%" icon={<Heart size={15}/>} />
    </div>
    <section className="report-panel"><div className="section-head"><div><h3>Ritmo por actividad</h3><p>Minutos por kilómetro · un punto por carrera</p></div></div>
      {usable.length ? <div className="report-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={usable} margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid vertical={false} stroke="#e9ece8" strokeDasharray="3 5"/><XAxis dataKey="activity_date" tickFormatter={date => new Date(`${String(date).slice(0,10)}T12:00:00`).toLocaleDateString('es-MX',{day:'numeric',month:'short'})} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} minTickGap={28}/><YAxis reversed domain={['dataMin - .4','dataMax + .4']} tickFormatter={fmtPace} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} width={45}/><Tooltip labelFormatter={date => fmtDate(String(date))} formatter={value => [`${fmtPace(Number(value))} /km`, 'Ritmo']} contentStyle={{border:'1px solid #e5e8e4',borderRadius:6,fontSize:11}}/><Line dataKey="pace_min_km" type="monotone" stroke="#fc4c02" strokeWidth={2.5} dot={{r:3,fill:'#fc4c02',strokeWidth:0}} activeDot={{r:5}}/></LineChart></ResponsiveContainer></div> : <EmptyReport message="Aún no hay ritmos válidos para mostrar."/>}
    </section>
    <section className="report-panel"><div className="section-head"><div><h3>Eficiencia y deriva</h3><p>Señales de cómo responde tu cuerpo en el tiempo</p></div></div>
      {rows.some(row => row.aerobic_efficiency != null || row.cardiac_drift_pct != null) ? <div className="report-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows} margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid vertical={false} stroke="#e9ece8" strokeDasharray="3 5"/><XAxis dataKey="activity_date" tickFormatter={date => new Date(`${String(date).slice(0,10)}T12:00:00`).toLocaleDateString('es-MX',{day:'numeric',month:'short'})} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} minTickGap={28}/><YAxis tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} width={45}/><Tooltip labelFormatter={date => fmtDate(String(date))} contentStyle={{border:'1px solid #e5e8e4',borderRadius:6,fontSize:11}}/><Legend/><Line name="Eficiencia aeróbica" dataKey="aerobic_efficiency" type="monotone" stroke="#2878b5" strokeWidth={2} dot={false} connectNulls/><Line name="Deriva cardíaca (%)" dataKey="cardiac_drift_pct" type="monotone" stroke="#56a174" strokeWidth={2} dot={false} connectNulls/></LineChart></ResponsiveContainer></div> : <EmptyReport message="Se necesitan registros FIT válidos para calcular estas señales."/>}
    </section>
    <p className="report-footnote">La eficiencia y la deriva son indicadores de entrenamiento, no diagnósticos médicos.</p>
  </div>
}

function LoadPage() {
  const [rows, setRows] = useState<LoadRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => { get<LoadRow[]>('/load').then(setRows).catch(e => setError(String(e))) }, [])
  const reliable = rows.filter(row => row.is_reliable && row.acwr != null)
  const latest = rows.at(-1)
  return <div className="report-page">
    <PageHeading eyebrow="Carga de entrenamiento · últimos 120 días" title="Carga" description="Volumen agudo y crónico para interpretar la carga reciente en contexto." />
    {error && <p className="inline-error">{error}</p>}
    <div className="report-metrics">
      <Metric label="Carga hoy" value={latest?.training_load?.toFixed(0) ?? '—'} unit="u.a." icon={<ActivityIcon size={15}/>} />
      <Metric label="Aguda · 7 días" value={latest?.acute_7d?.toFixed(0) ?? '—'} unit="u.a." icon={<ArrowUpRight size={15}/>} />
      <Metric label="Crónica · 28 días" value={latest?.chronic_28d?.toFixed(0) ?? '—'} unit="u.a." icon={<ArrowDownRight size={15}/>} />
      <Metric label="ACWR" value={latest?.is_reliable && latest.acwr != null ? latest.acwr.toFixed(2) : '—'} unit={latest?.is_reliable ? '' : 'en desarrollo'} icon={<Gauge size={15}/>} />
    </div>
    <section className="report-panel"><div className="section-head"><div><h3>Carga aguda y crónica</h3><p>Promedio diario de carga calculado por dbt</p></div><div className="chart-legend"><span><i className="legend-real"/> Aguda</span><span><i className="legend-plan"/> Crónica</span></div></div>
      {rows.length ? <div className="report-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={rows} margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid vertical={false} stroke="#e9ece8" strokeDasharray="3 5"/><XAxis dataKey="activity_date" tickFormatter={date => new Date(`${String(date).slice(0,10)}T12:00:00`).toLocaleDateString('es-MX',{day:'numeric',month:'short'})} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} minTickGap={28}/><YAxis tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} width={45}/><Tooltip labelFormatter={date => fmtDate(String(date))} contentStyle={{border:'1px solid #e5e8e4',borderRadius:6,fontSize:11}}/><Area name="Aguda · 7 d" dataKey="acute_7d" type="monotone" stroke="#fc4c02" fill="#fc4c02" fillOpacity={.09} strokeWidth={2}/><Area name="Crónica · 28 d" dataKey="chronic_28d" type="monotone" stroke="#2878b5" fill="#2878b5" fillOpacity={.07} strokeWidth={2}/></AreaChart></ResponsiveContainer></div> : <EmptyReport message="Aún no hay datos de carga."/>}
    </section>
    <section className="report-panel"><div className="section-head"><div><h3>Relación aguda / crónica</h3><p>Solo se interpreta cuando hay al menos 28 días de historial</p></div></div>
      {reliable.length ? <div className="report-chart short"><ResponsiveContainer width="100%" height="100%"><LineChart data={reliable} margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid vertical={false} stroke="#e9ece8" strokeDasharray="3 5"/><XAxis dataKey="activity_date" tickFormatter={date => new Date(`${String(date).slice(0,10)}T12:00:00`).toLocaleDateString('es-MX',{day:'numeric',month:'short'})} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} minTickGap={28}/><YAxis domain={[0,'auto']} tickLine={false} axisLine={false} tick={{fill:'#89918c',fontSize:10}} width={35}/><Tooltip labelFormatter={date => fmtDate(String(date))} formatter={value => [Number(value).toFixed(2),'ACWR']} contentStyle={{border:'1px solid #e5e8e4',borderRadius:6,fontSize:11}}/><Line dataKey="acwr" type="monotone" stroke="#fc4c02" strokeWidth={2.5} dot={false}/></LineChart></ResponsiveContainer></div> : <EmptyReport message="El ACWR aparecerá cuando el historial alcance cuatro semanas fiables."/>}
    </section>
    <p className="report-footnote">El ACWR es una referencia descriptiva de carga, no una recomendación médica.</p>
  </div>
}

function HealthPage() {
  const [data, setData] = useState<HealthData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { get<HealthData>('/health').then(setData).catch(e => setError(String(e))) }, [])
  return <div className="report-page">
    <PageHeading eyebrow="Datos y orquestación" title="Salud del pipeline" description="Una lectura rápida de la frescura, el volumen y los avisos locales." />
    {error && <p className="inline-error">{error}</p>}
    <div className="health-status"><span className="health-check"><ShieldCheck size={19}/></span><div><strong>{data?.alerts.length ? `${data.alerts.length} avisos recientes` : 'Sin avisos recientes'}</strong><p>Los avisos se escriben únicamente en el log local.</p></div><span className="health-local"><i className="local-dot"/> Local</span></div>
    <section className="report-panel health-panel"><div className="section-head"><div><h3>Calidad de datos</h3><p>Tablas de origen que alimentan Gold</p></div></div>
      {data?.quality.length ? <div className="quality-table"><div className="quality-head"><span>Dataset</span><span>Filas</span><span>Claves únicas</span><span>Fecha reciente</span><span>Rechazos</span></div>{data.quality.map(row => <div className="quality-row" key={row.dataset}><span><i className="quality-dot"/>{row.dataset.replace('silver/','')}</span><strong>{row.row_count.toLocaleString('es-MX')}</strong><strong>{row.distinct_keys.toLocaleString('es-MX')}</strong><span>{row.max_activity_date ? String(row.max_activity_date).slice(0,10) : '—'}</span><span>{row.rejected_count ?? '—'}</span></div>)}</div> : <EmptyReport message="Todavía no hay métricas de calidad en Gold."/>}
    </section>
    <section className="report-panel health-panel"><div className="section-head"><div><h3>Alertas locales</h3><p>Últimos mensajes de lake/alerts.log</p></div></div>
      {data?.alerts.length ? <div className="alert-list">{data.alerts.slice().reverse().map((alert,index) => <div className="alert-row" key={`${index}-${alert}`}><AlertTriangle size={16}/><span>{alert}</span></div>)}</div> : <div className="health-clear"><ShieldCheck size={20}/><span>No hay alertas registradas.</span></div>}
    </section>
    <p className="report-footnote">Última actividad en Gold: {data?.snapshot.last_run_date ? String(data.snapshot.last_run_date).slice(0,10) : '—'} · Ningún aviso sale de este equipo.</p>
  </div>
}

function EmptyReport({message}:{message:string}) {
  return <div className="report-empty"><ActivityIcon size={20}/><span>{message}</span></div>
}

export default App
