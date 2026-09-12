// Concept D post-hero runtime, ported from the standalone page for exact parity.
// Desk and case loops start when their sections scroll into view; rules and the
// share demo animate once on intersection. Reduced motion settles everything.

interface DeskMsg {
  status: string;
  text: string;
  typeMs?: number;
  listenMs?: number;
  bars?: number[];
}

interface DeskScript {
  ticker: string;
  activity: string[];
  msgs: DeskMsg[];
}

interface RuleState {
  started: boolean;
  phase: number;
}

interface GLLayer {
  gl: WebGLRenderingContext;
  prog: WebGLProgram;
  canvas: HTMLCanvasElement;
  visible: boolean;
  uTime: WebGLUniformLocation | null;
  uRes: WebGLUniformLocation | null;
}

(() => {
  const root = document.querySelector<HTMLElement>('[data-cd-posthero]');
  if (!root) return;
  const rm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Mobile swipe rails: role and labels live in the markup so the no-JS path
  // stays accessible; tab reach is added only while the <=620px rail layout
  // is active. Desktop tab order is untouched.
  const railMq = window.matchMedia('(max-width:620px)');
  const stageMq = window.matchMedia('(max-width:920px)');
  const rails = Array.from(root.querySelectorAll<HTMLElement>('.cd-rail'));
  const stageRows = Array.from(root.querySelectorAll<HTMLElement>('.hn-stage-row'));
  const syncRails = (): void => {
    rails.forEach((el) => {
      if (railMq.matches) el.setAttribute('tabindex', '0');
      else el.removeAttribute('tabindex');
    });
  };
  const syncStageRows = (): void => {
    stageRows.forEach((el) => {
      if (stageMq.matches) el.setAttribute('tabindex', '0');
      else el.removeAttribute('tabindex');
    });
  };
  syncRails();
  syncStageRows();
  railMq.addEventListener('change', syncRails);
  stageMq.addEventListener('change', syncStageRows);

  const railStep = (rail: HTMLElement): number => {
    const card = Array.from(rail.children).find((child) => window.getComputedStyle(child).display !== 'none') as HTMLElement | undefined;
    if (!card) return Math.max(1, rail.clientWidth);
    const styles = window.getComputedStyle(rail);
    const gap = parseFloat(styles.columnGap || styles.gap) || 0;
    return Math.max(1, card.getBoundingClientRect().width + gap);
  };
  const onRailKeydown = (e: KeyboardEvent): void => {
    if (!railMq.matches) return;
    const rail = e.currentTarget as HTMLElement;
    const max = Math.max(0, rail.scrollWidth - rail.clientWidth);
    const step = railStep(rail);
    let left: number | null = null;
    if (e.key === 'ArrowRight') left = Math.min(max, rail.scrollLeft + step);
    else if (e.key === 'ArrowLeft') left = Math.max(0, rail.scrollLeft - step);
    else if (e.key === 'Home') left = 0;
    else if (e.key === 'End') left = max;
    if (left === null) return;
    e.preventDefault();
    rail.scrollTo({ left, behavior: rm ? 'auto' : 'smooth' });
  };
  rails.forEach((rail) => rail.addEventListener('keydown', onRailKeydown));

  const deskScripts: DeskScript[] = [
    {
      ticker: 'OGDC',
      activity: ['Refreshing macro…', 'Checking earnings…', 'Reading filings…'],
      msgs: [
        { status: 'Thinking…', text: 'Demo feed — the live desk types the real screen result here.', typeMs: 1500, bars: [82, 68, 74] },
        { status: 'Reviewing…', text: 'Every published line traces back to the data layer, never memory.', typeMs: 1700 },
        { status: 'Reviewing…', text: 'This sample debate is staged; no current research is being shown.', typeMs: 900 },
        { status: 'Listening…', text: 'Both sides hold. What resolves it: the next data refresh — you decide.', typeMs: 1600, listenMs: 1800 }
      ]
    },
    {
      ticker: 'MCB',
      activity: ['Updating estimates…', 'Refreshing macro…', 'Waiting for catalyst…'],
      msgs: [
        { status: 'Thinking…', text: 'Demo feed — momentum and volume panels animate exactly like this.', typeMs: 1500, bars: [54, 61, 46] },
        { status: 'Reviewing…', text: 'No prices, payouts, or yields are ever quoted from memory.', typeMs: 1700 },
        { status: 'Reviewing…', text: 'The live desk runs one register: research, never advice.', typeMs: 1000 },
        { status: 'Listening…', text: 'Both sides hold. What resolves it: the next edition — you decide.', typeMs: 1700, listenMs: 1800 }
      ]
    },
    {
      ticker: 'MARI',
      activity: ['Reading filings…', 'Checking earnings…', 'Updating estimates…'],
      msgs: [
        { status: 'Thinking…', text: 'Demo feed — signal cards rank screens, they never print tips.', typeMs: 1500, bars: [91, 72, 88] },
        { status: 'Reviewing…', text: 'Valuation working ships expandable, input by input.', typeMs: 1600 },
        { status: 'Reviewing…', text: 'No advice language survives the desk review step.', typeMs: 950 },
        { status: 'Listening…', text: 'Momentum and value disagree. What resolves it: the next refresh — you decide.', typeMs: 1700, listenMs: 1800 }
      ]
    }
  ];

  const state = { filter: 'all', whoOpen: 0, faqOpen: 0 };

  const deskState = {
    scriptIdx: 0,
    activityIdx: 0,
    cardOp: 1,
    status: ['Idle…', 'Idle…', 'Idle…', 'Idle…'],
    typing: [false, false, false, false],
    revealed: [false, false, false, false],
    text: ['', '', '', ''],
    bars: [0, 0, 0],
    evidenceOn: false
  };

  const caseState = {
    verifiedOp: 0,
    resultPct: '+9.4%',
    ringOffset: 6,
    hitRate: '100',
    missBg: 'transparent',
    astroCount: 2589,
    edge: '0 edge',
    archiveShift: 0,
    newBlockBg: 'var(--hair)'
  };

  const ruleState: RuleState[] = [
    { started: false, phase: 0 },
    { started: false, phase: 0 },
    { started: false, phase: 0 },
    { started: false, phase: 0 }
  ];
  const shareState: RuleState = { started: false, phase: 0 };

  const parallaxEls: Array<{ el: HTMLElement; amp: number }> = [];
  const glLayers: GLLayer[] = [];
  const deskTimers: number[] = [];
  const caseTimers: number[] = [];
  let deskCycleToken = 0;
  let whoLocked = false;
  let glObserver: IntersectionObserver | null = null;
  let glRaf = 0;
  let revealObs: IntersectionObserver | null = null;
  let ruleObs: IntersectionObserver | null = null;
  let shareObs: IntersectionObserver | null = null;
  let loopObs: IntersectionObserver | null = null;

  function ruleStatus(i: number): { text: string; color: string } {
    const p = ruleState[i].phase;
    if (p === 0) return { text: '', color: 'var(--ink3)' };
    if (p === 1) return { text: 'Checking…', color: 'var(--ink3)' };
    if (p === 2) return { text: '✓ Verified', color: 'var(--up)' };
    return { text: 'Locked', color: 'var(--ink3)' };
  }

  function vals(): Record<string, string | number> {
    const f = state.filter;
    const show = (cat: string): string => (f === 'all' || f === cat ? 'block' : 'none');
    const r = show('research');
    const a = show('astro');
    const t = show('tools');
    const tab = (name: string): { bg: string; fg: string } => ({
      bg: name === state.filter ? '#0a0a0a' : '#fff',
      fg: name === state.filter ? '#f4f4f0' : '#0a0a0a'
    });
    const all = tab('all');
    const res = tab('research');
    const ast = tab('astro');
    const tool = tab('tools');
    const v: Record<string, string | number> = {
      dBoard: r, dValue: r, dDesk: r, dGlobal: r,
      dAstro: a, dCast: a, dSizer: t, dScores: t,
      allBg: all.bg, allFg: all.fg,
      resBg: res.bg, resFg: res.fg,
      astBg: ast.bg, astFg: ast.fg,
      toolBg: tool.bg, toolFg: tool.fg,
      drTicker: deskScripts[deskState.scriptIdx % deskScripts.length].ticker,
      drTimer: '2 min 44 sec',
      drCardOp: deskState.cardOp,
      drActivity: deskScripts[deskState.scriptIdx % deskScripts.length].activity[deskState.activityIdx],
      drActivityOp: 1,
      drEvidenceOp: deskState.evidenceOn ? 1 : 0,
      drBar0: deskState.bars[0],
      drBar1: deskState.bars[1],
      drBar2: deskState.bars[2],
      drIconGlow0: deskState.typing[0] ? 'box-shadow:0 0 6px rgba(34,201,155,.5)' : '',
      drIconGlow1: deskState.typing[1] ? 'box-shadow:0 0 6px rgba(34,201,155,.5)' : '',
      drIconGlow2: deskState.typing[2] ? 'box-shadow:0 0 6px rgba(239,107,72,.5)' : '',
      drIconGlow3: (deskState.status[3] === 'Listening…' || deskState.typing[3]) ? 'box-shadow:0 0 7px rgba(184,134,11,.6)' : '',
      caseVerifiedOp: caseState.verifiedOp,
      caseResultPct: caseState.resultPct,
      caseRingOffset: caseState.ringOffset,
      caseHitRate: caseState.hitRate,
      caseMissBg: caseState.missBg,
      caseAstroCount: caseState.astroCount.toLocaleString(),
      caseEdge: caseState.edge,
      caseArchiveShift: caseState.archiveShift,
      caseNewBlockBg: caseState.newBlockBg,
      shareValue: shareState.phase >= 2 ? '████████' : '12,843',
      shareTextColor: shareState.phase >= 2 ? 'rgba(242,242,238,.3)' : '#f2f2ee',
      shareStrike: shareState.phase === 1 ? 'line-through' : 'none',
      shareArrowOp: shareState.phase >= 1 ? 1 : 0,
      shareCalcOp: shareState.phase >= 3 ? 1 : 0
    };
    for (let i = 0; i < 4; i++) {
      v['drStatus' + i] = deskState.status[i];
      v['drTypingOp' + i] = deskState.typing[i] ? 1 : 0;
      v['drTypingH' + i] = deskState.typing[i] ? '15px' : '0px';
      v['drOpacity' + i] = deskState.revealed[i] ? 1 : 0;
      v['drTranslate' + i] = deskState.revealed[i] ? 0 : 6;
      v['drText' + i] = deskState.text[i];
    }
    for (let i = 0; i < 4; i++) {
      const on = state.whoOpen === i;
      v['whoRowBg' + i] = on ? 'rgba(242,242,238,.055)' : 'transparent';
      v['whoRows' + i] = on ? '1fr' : '0fr';
      v['whoRot' + i] = on ? 135 : 0;
      v['whoOpacity' + i] = on ? 1 : 0;
      v['whoTranslate' + i] = on ? 0 : -6;
      v['whoDelay' + i] = on ? '.12s' : '0s';
    }
    for (let i = 0; i < 5; i++) {
      const on = state.faqOpen === i;
      v['faqRows' + i] = on ? '1fr' : '0fr';
      v['faqRot' + i] = on ? 135 : 0;
      v['faqOpacity' + i] = on ? 1 : 0;
      v['faqTranslate' + i] = on ? 0 : -6;
      v['faqDelay' + i] = on ? '.12s' : '0s';
    }
    for (let i = 0; i < 4; i++) {
      const p = ruleState[i].phase;
      v['rule' + i + 'Op'] = p > 0 ? 1 : 0;
      v['rule' + i + 'Y'] = p > 0 ? 0 : 18;
      v['rule' + i + 'Status'] = ruleStatus(i).text;
      v['rule' + i + 'StatusColor'] = ruleStatus(i).color;
      v['rule' + i + 'BorderColor'] = p >= 3 ? 'border-color:var(--ink1)' : '';
      v['rule' + i + 'BgColor'] = p >= 3 ? 'background:var(--ink1)' : '';
    }
    return v;
  }

  const TOKEN_RE = /\{\{\s*(\w+)\s*\}\}/g;
  // Tracks which declarations apply() last set per element, so a token that
  // resolves away (e.g. an icon glow turning off) clears its property instead
  // of leaving a stale value behind.
  const tplPrev = new WeakMap<HTMLElement, string[]>();

  function apply(): void {
    if (!root) return;
    const v = vals();
    root.querySelectorAll<HTMLElement>('[data-tpl-style]').forEach((el) => {
      const tpl = el.getAttribute('data-tpl-style') || '';
      const merged = tpl.replace(TOKEN_RE, (m: string, k: string) => (k in v ? String(v[k]) : m));
      const props: string[] = [];
      merged.split(';').forEach((decl) => {
        const ci = decl.indexOf(':');
        if (ci < 0) return;
        const prop = decl.slice(0, ci).trim();
        if (!prop) return;
        props.push(prop);
        el.style.setProperty(prop, decl.slice(ci + 1).trim());
      });
      const prev = tplPrev.get(el);
      if (prev) prev.forEach((p) => { if (props.indexOf(p) < 0) el.style.removeProperty(p); });
      tplPrev.set(el, props);
    });
    root.querySelectorAll<HTMLElement>('[data-dyn-attr]').forEach((el) => {
      const spec = el.getAttribute('data-dyn-attr') || '';
      const ci = spec.indexOf(':');
      if (ci < 0) return;
      const tok = spec.slice(0, ci).trim();
      const attr = spec.slice(ci + 1).trim();
      if (tok && attr && tok in v) el.setAttribute(attr, String(v[tok]));
    });
    root.querySelectorAll<HTMLElement>('[data-dyn]').forEach((el) => {
      const tok = el.getAttribute('data-dyn') || '';
      if (tok && tok in v) el.textContent = String(v[tok]);
    });
    root.querySelectorAll<HTMLElement>('[data-filter-btn]').forEach((el) => {
      el.setAttribute('aria-pressed', String((el.getAttribute('data-filter-btn') || '') === state.filter));
    });
    root.querySelectorAll<HTMLElement>('[data-who-row]').forEach((el) => {
      el.setAttribute('aria-expanded', String(Number(el.getAttribute('data-who-row')) === state.whoOpen));
    });
    root.querySelectorAll<HTMLElement>('[data-faq]').forEach((el) => {
      el.setAttribute('aria-expanded', String(Number(el.getAttribute('data-faq')) === state.faqOpen));
    });
  }

  function setState(patch: Partial<typeof state>): void {
    Object.assign(state, patch);
    apply();
  }

  function deskAt(ms: number, token: number, fn: () => void): void {
    deskTimers.push(window.setTimeout(() => { if (token === deskCycleToken) fn(); }, ms));
  }

  function runDeskCycle(): void {
    const token = deskCycleToken;
    const script = deskScripts[deskState.scriptIdx % deskScripts.length];
    deskState.status = ['Idle…', 'Idle…', 'Idle…', 'Idle…'];
    deskState.typing = [false, false, false, false];
    deskState.revealed = [false, false, false, false];
    deskState.text = ['', '', '', ''];
    deskState.bars = [0, 0, 0];
    deskState.evidenceOn = false;
    apply();

    let t = 300;
    script.msgs.forEach((m, i) => {
      deskAt(t, token, () => {
        deskState.status[i] = m.status;
        deskState.typing[i] = !!m.typeMs;
        apply();
      });
      t += m.listenMs || 0;
      t += m.typeMs || 600;
      deskAt(t, token, () => {
        deskState.typing[i] = false;
        deskState.revealed[i] = true;
        deskState.text[i] = m.text;
        deskState.status[i] = 'Online';
        apply();
        const mb = m.bars;
        if (mb) {
          deskAt(200, token, () => { deskState.bars = mb; deskState.evidenceOn = true; apply(); });
        }
      });
      t += 900 + i * 250;
    });

    // hold, then fade and restart with the next ticker
    t += 4200;
    deskAt(t, token, () => { deskState.cardOp = 0; apply(); });
    t += 650;
    deskAt(t, token, () => {
      deskState.scriptIdx = (deskState.scriptIdx + 1) % deskScripts.length;
      deskState.cardOp = 1;
      runDeskCycle();
    });
  }

  function runDeskActivity(): void {
    const token = deskCycleToken;
    const tick = (): void => {
      const script = deskScripts[deskState.scriptIdx % deskScripts.length];
      deskState.activityIdx = (deskState.activityIdx + 1) % script.activity.length;
      apply();
      deskAt(2600, token, tick);
    };
    deskAt(2600, token, tick);
  }

  function caseAt(ms: number, fn: () => void): void {
    caseTimers.push(window.setTimeout(fn, ms));
  }

  function runCaseLoop(): void {
    // prediction "locks", verified stamp flashes
    caseAt(1200, () => { caseState.verifiedOp = 1; apply(); });
    caseAt(2600, () => { caseState.verifiedOp = 0; apply(); });
    // result counts up through intermediate values
    caseAt(1800, () => { caseState.resultPct = '+6.2%'; apply(); });
    caseAt(2400, () => { caseState.resultPct = '+9.4%'; apply(); });
    // hit-rate ring breathes
    caseAt(3000, () => { caseState.ringOffset = 0; caseState.hitRate = '100'; apply(); });
    caseAt(4600, () => { caseState.ringOffset = 6; caseState.hitRate = '100'; apply(); });
    // "Misses" word highlights briefly
    caseAt(3600, () => { caseState.missBg = 'rgba(190,65,38,.15)'; apply(); });
    caseAt(4100, () => { caseState.missBg = 'transparent'; apply(); });
    // astro counter increments, edge flickers, archive shifts
    caseAt(3800, () => { caseState.astroCount = 2590; apply(); });
    caseAt(5200, () => { caseState.edge = '+0.1'; apply(); });
    caseAt(5700, () => { caseState.edge = '0 edge'; apply(); });
    caseAt(4400, () => { caseState.archiveShift = -14; caseState.newBlockBg = '#b8860b'; apply(); });
    caseAt(6800, () => { caseState.archiveShift = 0; caseState.newBlockBg = 'var(--hair)'; caseState.astroCount = 2589; apply(); });
    caseAt(9000, runCaseLoop);
  }

  function startRule(i: number): void {
    const r = ruleState[i];
    if (r.started) return;
    r.started = true;
    r.phase = 1;
    apply();
    caseAt(700 + i * 80, () => { r.phase = 2; apply(); });
    caseAt(1400 + i * 80, () => { r.phase = 3; apply(); });
  }

  function startShare(): void {
    if (shareState.started) return;
    shareState.started = true;
    apply();
    caseAt(900, () => { shareState.phase = 1; apply(); });
    caseAt(1900, () => { shareState.phase = 2; apply(); });
    caseAt(2700, () => { shareState.phase = 3; apply(); });
  }

  const GL_VS = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}';
  const GL_PREFIX = 'precision mediump float;\nuniform float uTime; uniform vec2 uRes;\nfloat hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}\nfloat noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);\n float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));\n return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}\nfloat fbm(vec2 p){float v=0.0,a=0.5;for(int i=0;i<5;i++){v+=a*noise(p);p*=2.02;a*=0.5;}return v;}\n';
  const GL_FS: Record<string, string> = {
    // Source-accurate hero shader (reference glHero -> mountGL(el, 'hero')).
    hero: 'void main(){vec2 uv=gl_FragCoord.xy/uRes;vec2 q=uv*3.0;q.x+=uTime*0.05;\n        float n=fbm(q+fbm(q*1.5+uTime*0.035));float band=smoothstep(0.32,0.88,n);\n        vec3 col=mix(vec3(0.058,0.058,0.051),vec3(0.043,0.30,0.24),band*0.5);\n        col+=vec3(0.72,0.53,0.043)*pow(band,3.0)*0.33;\n        col+=step(0.988,fract(uv.x*70.0))*0.022+step(0.988,fract(uv.y*34.0))*0.018;\n        gl_FragColor=vec4(col,1.0);}',
    immersive: 'void main(){vec2 uv=gl_FragCoord.xy/uRes;vec2 p=uv*2.0-1.0;p.x*=uRes.x/max(uRes.y,1.0);\n        float t=uTime*0.07;\n        vec2 w=vec2(fbm(p*1.1+t),fbm(p*1.1-t+5.2));\n        float n=fbm(p*1.7+w*2.3);float v=smoothstep(0.28,0.92,n);\n        vec3 col=mix(vec3(0.055,0.055,0.05),vec3(0.10,0.10,0.093),v);\n        col+=vec3(0.72,0.53,0.043)*pow(v,4.0)*0.45;\n        col+=vec3(0.13,0.79,0.61)*pow(smoothstep(0.62,1.0,n),6.0)*0.22;\n        gl_FragColor=vec4(col,1.0);}',
    breadth: 'void main(){vec2 uv=gl_FragCoord.xy/uRes;float cols=30.0;\n        float i=floor(uv.x*cols);float seed=hash(vec2(i,1.0));\n        float wave=sin(uTime*0.45-i*0.19)*0.5+0.5;\n        float spread=smoothstep(0.0,1.0,uv.x*0.55+0.45);\n        float hgt=(0.16+seed*0.22)+wave*0.52*spread;\n        float bar=step(uv.y,hgt);\n        float edge=smoothstep(hgt,hgt-0.012,uv.y);\n        vec3 col=vec3(0.09,0.09,0.084);\n        col=mix(col,vec3(0.043,0.42,0.33)*(0.65+0.6*seed),bar*0.85);\n        col+=vec3(0.13,0.79,0.61)*edge*bar*0.55;\n        float dotY=fract(uTime*0.22+seed);\n        col+=vec3(0.72,0.53,0.043)*smoothstep(0.018,0.0,abs(uv.y-dotY))*step(0.66,hash(vec2(i,3.0)))*0.55;\n        col+=step(0.992,fract(uv.x*cols))*0.03;\n        gl_FragColor=vec4(col,1.0);}'
  };

  function mountGL(canvas: HTMLCanvasElement, key: string): void {
    if (canvas.dataset.glMounted) return;
    const src = GL_FS[key];
    if (!src) return;
    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' });
    if (!gl) return;
    canvas.dataset.glMounted = '1';
    const vs = gl.createShader(gl.VERTEX_SHADER);
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    const prog = gl.createProgram();
    if (!vs || !fs || !prog) return;
    gl.shaderSource(vs, GL_VS);
    gl.compileShader(vs);
    gl.shaderSource(fs, GL_PREFIX + src);
    gl.compileShader(fs);
    if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) {
      console.warn('shader', key, gl.getShaderInfoLog(fs));
      return;
    }
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const layer: GLLayer = { gl, prog, canvas, visible: true, uTime: gl.getUniformLocation(prog, 'uTime'), uRes: gl.getUniformLocation(prog, 'uRes') };
    glLayers.push(layer);
    if (glObserver) glObserver.observe(canvas);
    resizeGL(layer);
  }

  function resizeGL(layer: GLLayer): void {
    const { canvas, gl } = layer;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, canvas.width, canvas.height);
  }

  function renderFrame(layer: GLLayer, t: number): void {
    resizeGL(layer);
    const { gl, prog } = layer;
    gl.useProgram(prog);
    gl.uniform1f(layer.uTime, t);
    gl.uniform2f(layer.uRes, layer.canvas.width, layer.canvas.height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function startGL(): void {
    const ro = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        const layer = glLayers.find((l) => l.canvas === e.target);
        if (layer) layer.visible = e.isIntersecting;
      });
    }, { rootMargin: '120px' });
    glObserver = ro;
    glLayers.forEach((l) => ro.observe(l.canvas));
    const t0 = performance.now();
    const tick = (now: number): void => {
      glRaf = requestAnimationFrame(tick);
      const t = (now - t0) / 1000;
      glLayers.forEach((layer) => {
        if (!layer.visible) return;
        renderFrame(layer, t);
      });
    };
    glRaf = requestAnimationFrame(tick);
  }

  function mountAllGL(): void {
    // Document-level: the hero card canvas sits outside the posthero root.
    document.querySelectorAll<HTMLCanvasElement>('canvas[data-gl]').forEach((c) => {
      mountGL(c, c.getAttribute('data-gl') || '');
    });
  }

  // Interactions run in both motion modes.
  root.querySelectorAll<HTMLElement>('[data-filter-btn]').forEach((el) => {
    el.addEventListener('click', () => {
      setState({ filter: el.getAttribute('data-filter-btn') || 'all' });
      // Filtering hides rail children; clamp any rail scrolled past its new end.
      root.querySelectorAll<HTMLElement>('.cd-rail').forEach((rail) => {
        const max = rail.scrollWidth - rail.clientWidth;
        if (rail.scrollLeft > max) rail.scrollLeft = max;
      });
    });
  });
  root.querySelectorAll<HTMLElement>('[data-who-row]').forEach((el) => {
    el.addEventListener('click', () => {
      whoLocked = true;
      const i = Number(el.getAttribute('data-who-row'));
      setState({ whoOpen: state.whoOpen === i ? -1 : i });
    });
  });
  root.querySelectorAll<HTMLElement>('[data-faq]').forEach((el) => {
    el.addEventListener('click', () => {
      const i = Number(el.getAttribute('data-faq'));
      setState({ faqOpen: state.faqOpen === i ? -1 : i });
    });
  });
  root.querySelectorAll<HTMLElement>('[data-hover]').forEach((el) => {
    const spec = el.getAttribute('data-hover') || '';
    const ci = spec.indexOf(':');
    if (ci < 0) return;
    const prop = spec.slice(0, ci).trim();
    const val = spec.slice(ci + 1).trim();
    el.addEventListener('mouseenter', () => el.style.setProperty(prop, val));
    el.addEventListener('mouseleave', () => el.style.removeProperty(prop));
  });

  const heading = root.querySelector<HTMLElement>('[data-statement-heading]');
  const whoSection = root.querySelector<HTMLElement>('[data-who-section]');
  root.querySelectorAll<HTMLElement>('[data-parallax]').forEach((el) => {
    parallaxEls.push({ el, amp: Number(el.getAttribute('data-parallax')) || 0 });
  });

  function onScroll(): void {
    const vh = window.innerHeight || 1;
    if (whoSection && !whoLocked) {
      const r = whoSection.getBoundingClientRect();
      const span = r.height + vh * 0.55;
      const p = Math.max(0, Math.min(0.999, (vh * 0.82 - r.top) / span));
      const idx = Math.min(3, Math.floor(p * 4.2));
      if (p > 0.02 && idx !== state.whoOpen) setState({ whoOpen: idx });
    }
    if (heading) {
      const rect = heading.getBoundingClientRect();
      const start = vh * 0.9;
      const end = vh * 0.35;
      const p = Math.max(0, Math.min(1, (start - rect.top) / (start - end)));
      const words = heading.querySelectorAll<HTMLElement>('.hn-hword');
      const steps = words.length;
      words.forEach((w, i) => {
        const on = p >= i / steps + 0.05;
        w.style.color = on ? 'var(--ink1)' : 'var(--ink3)';
      });
    }
    parallaxEls.forEach(({ el, amp }) => {
      const rect = el.getBoundingClientRect();
      const center = rect.top + rect.height / 2 - vh / 2;
      const t = Math.max(-1, Math.min(1, center / vh));
      el.style.transform = 'translateY(' + (t * amp).toFixed(1) + 'px)';
    });
  }

  function cleanup(): void {
    window.removeEventListener('scroll', onScroll);
    railMq.removeEventListener('change', syncRails);
    stageMq.removeEventListener('change', syncStageRows);
    rails.forEach((rail) => rail.removeEventListener('keydown', onRailKeydown));
    if (glRaf) cancelAnimationFrame(glRaf);
    if (glObserver) glObserver.disconnect();
    if (loopObs) loopObs.disconnect();
    if (revealObs) revealObs.disconnect();
    if (ruleObs) ruleObs.disconnect();
    if (shareObs) shareObs.disconnect();
    deskCycleToken++;
    deskTimers.forEach((id) => clearTimeout(id));
    caseTimers.forEach((id) => clearTimeout(id));
  }

  if (rm) {
    // Settled end-state: no loops, observers, scroll effects or parallax.
    const s0 = deskScripts[0];
    deskState.status = s0.msgs.map((): string => 'Online');
    deskState.revealed = [true, true, true, true];
    deskState.text = s0.msgs.map((m) => m.text);
    deskState.bars = s0.msgs[0].bars ? s0.msgs[0].bars.slice() : [0, 0, 0];
    deskState.evidenceOn = true;
    ruleState.forEach((r) => { r.phase = 3; });
    shareState.phase = 3;
    root.querySelectorAll<HTMLElement>('.hn-rv').forEach((el) => el.classList.add('hn-in'));
    mountAllGL();
    glLayers.forEach((layer) => renderFrame(layer, 0));
  } else {
    mountAllGL();
    startGL();

    const rlo = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('hn-in');
          rlo.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });
    revealObs = rlo;
    root.querySelectorAll<HTMLElement>('.hn-rv').forEach((el) => rlo.observe(el));

    const ruleEls = Array.from(root.querySelectorAll<HTMLElement>('[data-rule]'));
    const ro = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          const i = ruleEls.indexOf(e.target as HTMLElement);
          if (i >= 0) startRule(i);
          ro.unobserve(e.target);
        }
      });
    }, { threshold: 0.4 });
    ruleObs = ro;
    ruleEls.forEach((el) => ro.observe(el));

    const shareEl = root.querySelector<HTMLElement>('[data-share-demo]');
    if (shareEl) {
      const so = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            startShare();
            so.unobserve(e.target);
          }
        });
      }, { threshold: 0.3 });
      shareObs = so;
      so.observe(shareEl);
    }

    const deskVis = root.querySelector<HTMLElement>('[data-desk-visibility]');
    const caseVis = root.querySelector<HTMLElement>('[data-case-visibility]');
    const lo = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        if (e.target === deskVis) {
          runDeskCycle();
          runDeskActivity();
        } else if (e.target === caseVis) {
          runCaseLoop();
        }
        lo.unobserve(e.target);
      });
    }, { rootMargin: '120px' });
    loopObs = lo;
    if (deskVis) lo.observe(deskVis);
    if (caseVis) lo.observe(caseVis);

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }
  apply();
  window.addEventListener('pagehide', cleanup, { once: true });
})();
