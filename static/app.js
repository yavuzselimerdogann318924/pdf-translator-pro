/* PDF Translator Pro - Cyber HUD Logic */

const $ = (id) => document.getElementById(id);

document.addEventListener('DOMContentLoaded', () => {
  // ── State ──
  let state = {
    file: null,
    taskId: null,
    isTranslating: false,
    settings: {
      workers: 4,
      chunk_size: 4000,
      save_every: 50
    },
    preview: {
      originalName: null,
      translatedName: null,
      currentPage: 1,
      totalPages: 1,
      mode: 'original' // 'original' or 'translated'
    }
  };

  const socket = io();

  // ── Initialize ──
  let lexNet = null; // Global reference to lexical network controller

  function init() {
    initMatrix();
    lexNet = initLexicalNetwork();
    updateClock();
    setInterval(updateClock, 100);
    loadSettings();
    bindEvents();
    bindSocket();
  }

  // ── ZEYNEP MEYDAN — Accumulating Letter Reveal + Choreography ──
  function initLexicalNetwork() {
    const canvas = $('waveform-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let W = 600, H = 400;
    function resize() {
      const r = canvas.parentElement.getBoundingClientRect();
      if (r.width  > 10) { W = r.width;  canvas.width  = W; }
      if (r.height > 10) { H = r.height; canvas.height = H; }
    }
    resize();
    window.addEventListener('resize', resize);
    setTimeout(resize, 300); setTimeout(resize, 900);

    // ── State ──
    let nodes = [], particles = [], wordQueue = [];
    let isActive = false, globalT = 0;

    // ── Letter build phase ──
    const TEXT = 'ZEYNEP MEYDAN';
    let charIdx = 0, stampedText = '';
    let buildPhase = 'IDLE', buildTimer = 0;
    const BUILD_FLY = 40, BUILD_HOLD = 55, BUILD_STAMP = 20;

    // 5x7 pixel font (col, row)
    const G = {
      Z:[[0,0],[1,0],[2,0],[3,0],[4,0],[3,1],[2,2],[3,2],[1,3],[2,3],[0,4],[1,4],[0,5],[0,6],[1,6],[2,6],[3,6],[4,6]],
      E:[[0,0],[1,0],[2,0],[3,0],[4,0],[0,1],[0,2],[0,3],[1,3],[2,3],[3,3],[0,4],[0,5],[0,6],[1,6],[2,6],[3,6],[4,6]],
      Y:[[0,0],[4,0],[0,1],[4,1],[1,2],[3,2],[2,3],[2,4],[2,5],[2,6]],
      N:[[0,0],[4,0],[0,1],[1,1],[4,1],[0,2],[2,2],[4,2],[0,3],[2,3],[4,3],[0,4],[3,4],[4,4],[0,5],[4,5],[0,6],[4,6]],
      P:[[0,0],[1,0],[2,0],[3,0],[0,1],[4,1],[0,2],[4,2],[0,3],[1,3],[2,3],[3,3],[0,4],[0,5],[0,6]],
      M:[[0,0],[4,0],[0,1],[1,1],[3,1],[4,1],[0,2],[2,2],[4,2],[0,3],[4,3],[0,4],[4,4],[0,5],[4,5],[0,6],[4,6]],
      D:[[0,0],[1,0],[2,0],[3,0],[0,1],[4,1],[0,2],[4,2],[0,3],[4,3],[0,4],[4,4],[0,5],[4,5],[0,6],[1,6],[2,6],[3,6]],
      A:[[1,0],[2,0],[3,0],[0,1],[4,1],[0,2],[4,2],[0,3],[1,3],[2,3],[3,3],[4,3],[0,4],[4,4],[0,5],[4,5],[0,6],[4,6]],
      ' ':[]
    };

    function getLayout() {
      const charW = 6; // 5 cols + 1 gap
      const totalCells = TEXT.length * charW;
      const cellSize = Math.min(W * 0.88 / totalCells, H * 0.68 / 7);
      const ox = (W - totalCells * cellSize) / 2;
      const oy = (H - 7 * cellSize) / 2;
      return { cellSize, ox, oy, charW };
    }

    function getCharDots(ci) {
      const { cellSize, ox, oy, charW } = getLayout();
      const ch = TEXT[ci], dots = G[ch] || [];
      const baseX = ox + ci * charW * cellSize;
      return dots.map(([c,r]) => ({ x: baseX+(c+.5)*cellSize, y: oy+(r+.5)*cellSize }));
    }

    function pickWord() { return wordQueue.length > 0 ? wordQueue.shift() : null; }

    function startBuildingChar() {
      if (charIdx >= TEXT.length) {
        buildPhase = 'CELEBRATE'; buildTimer = 0;
        startCelebration(); return;
      }
      if (TEXT[charIdx] === ' ') {
        stampedText += ' '; charIdx++; startBuildingChar(); return;
      }
      const dots = getCharDots(charIdx);
      const { cellSize } = getLayout();
      nodes = dots.map((dot, i) => ({
        word: pickWord(),
        x: W/2+(Math.random()-.5)*W*.7, y: H+30+Math.random()*40,
        tx: dot.x, ty: dot.y,
        r: 2, tr: Math.max(3.5, cellSize*.38),
        opacity: 0, glow: 5, glowing: false,
      }));
      buildPhase = 'FORMING'; buildTimer = 0;
    }

    function drawStamped() {
      if (!stampedText) return;
      const { cellSize, ox, oy, charW } = getLayout();
      for (let ci = 0; ci < stampedText.length; ci++) {
        const ch = stampedText[ci]; if (ch === ' ') continue;
        const dots = G[ch] || [];
        const baseX = ox + ci * charW * cellSize;
        // edges
        for (let i = 0; i < dots.length; i++) for (let j = i+1; j < dots.length; j++) {
          const ax=baseX+(dots[i][0]+.5)*cellSize, ay=oy+(dots[i][1]+.5)*cellSize;
          const bx=baseX+(dots[j][0]+.5)*cellSize, by=oy+(dots[j][1]+.5)*cellSize;
          const d=Math.hypot(ax-bx,ay-by);
          if (d < cellSize*2.4) {
            ctx.beginPath(); ctx.moveTo(ax,ay); ctx.lineTo(bx,by);
            ctx.strokeStyle=`rgba(0,255,120,${(1-d/(cellSize*2.6))*.38})`; ctx.lineWidth=.9; ctx.stroke();
          }
        }
        // dots as hexagons
        dots.forEach(([c,r]) => {
          const px=baseX+(c+.5)*cellSize, py=oy+(r+.5)*cellSize, dr=cellSize*.28;
          ctx.beginPath();
          for (let s=0;s<=6;s++) { const a=(s/6)*Math.PI*2-Math.PI/6; s===0?ctx.moveTo(px+Math.cos(a)*dr,py+Math.sin(a)*dr):ctx.lineTo(px+Math.cos(a)*dr,py+Math.sin(a)*dr); }
          ctx.fillStyle='rgba(0,255,120,.22)'; ctx.strokeStyle='rgba(0,255,120,.8)';
          ctx.shadowColor='#00ff78'; ctx.shadowBlur=5+Math.sin(globalT*.03+c+r)*2;
          ctx.lineWidth=1.1; ctx.fill(); ctx.stroke(); ctx.shadowBlur=0;
        });
      }
    }

    // ── Celebration layouts ──
    const CEL_LAYOUTS = ['hexagon','spiral','triangle','grid','circle','burst'];
    let celIdx=0, celTimer=0, celDone=false;
    const CEL_SWITCH=85, CEL_TOTAL=6;

    const LAYOUTS = {
      hexagon(n,cx,cy,R){const p=[{x:cx,y:cy}];for(let r=1;p.length<n;r++){const c=6*r;for(let i=0;i<c&&p.length<n;i++){const a=(i/c)*Math.PI*2-Math.PI/2;p.push({x:cx+Math.cos(a)*R*r*.42,y:cy+Math.sin(a)*R*r*.42});}}return p;},
      spiral(n,cx,cy,R){return Array.from({length:n},(_,i)=>{const t=(i/Math.max(1,n-1))*4*Math.PI,r=(i/Math.max(1,n-1))*R;return{x:cx+Math.cos(t)*r,y:cy+Math.sin(t)*r};});},
      triangle(n,cx,cy,R){const p=[];for(let s=0;s<3;s++){const a1=(s/3)*Math.PI*2-Math.PI/2,a2=((s+1)/3)*Math.PI*2-Math.PI/2,ps=Math.ceil(n/3);for(let t=0;t<ps&&p.length<n;t++){const f=t/ps;p.push({x:cx+(Math.cos(a1)*(1-f)+Math.cos(a2)*f)*R,y:cy+(Math.sin(a1)*(1-f)+Math.sin(a2)*f)*R});}}return p;},
      grid(n,cx,cy,R){const c=Math.ceil(Math.sqrt(n)),s=(R*2)/c;return Array.from({length:n},(_,i)=>({x:cx-R+(i%c)*s+s/2,y:cy-R+Math.floor(i/c)*s+s/2}));},
      circle(n,cx,cy,R){return Array.from({length:n},(_,i)=>{const a=(i/n)*Math.PI*2;return{x:cx+Math.cos(a)*R,y:cy+Math.sin(a)*R};});},
      burst(n,cx,cy,R){return Array.from({length:n},(_,i)=>{const a=Math.random()*Math.PI*2,r=R*(.5+Math.random()*.6);return{x:cx+Math.cos(a)*r,y:cy+Math.sin(a)*r};});}
    };

    function startCelebration() {
      const N=32;
      nodes=Array.from({length:N},()=>({word:pickWord(),x:W/2+(Math.random()-.5)*W,y:H/2+(Math.random()-.5)*H,tx:W/2,ty:H/2,r:3,tr:6+Math.random()*4,opacity:0,glow:5,glowing:false}));
      celIdx=0; celTimer=0; celDone=false; retargetCel();
    }

    function retargetCel() {
      const lay=CEL_LAYOUTS[celIdx%CEL_LAYOUTS.length],cx=W/2,cy=H/2,R=Math.min(W,H)*.36;
      const pos=LAYOUTS[lay](nodes.length,cx,cy,R);
      nodes.forEach((n,i)=>{ const p=pos[i]||{x:cx,y:cy}; n.tx=p.x; n.ty=p.y; n.glowing=false; if(wordQueue.length>0)n.word=wordQueue.shift(); });
    }

    // ── Dust ──
    function spawnDust(){if(particles.length>70)return;particles.push({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.2+.3,vx:(Math.random()-.5)*.4,vy:(Math.random()-.5)*.4,life:0,maxLife:260+Math.random()*280,opacity:Math.random()*.28+.04});}

    // ══════════════════════════════════════════════
    function draw() {
      ctx.fillStyle=isActive?'rgba(0,3,8,.14)':'rgba(0,3,8,.1)';
      ctx.fillRect(0,0,W,H); globalT++;

      if(globalT%7===0)spawnDust();
      for(let i=particles.length-1;i>=0;i--){const p=particles[i];p.x+=p.vx;p.y+=p.vy;p.life++;const f=1-p.life/p.maxLife;if(f<=0){particles.splice(i,1);continue;}ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(0,170,255,${p.opacity*f})`;ctx.fill();}

      if(!isActive){
        ctx.strokeStyle='rgba(0,160,255,.03)'; ctx.lineWidth=1;
        for(let x=0;x<W;x+=50){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}
        for(let y=0;y<H;y+=50){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}
        requestAnimationFrame(draw); return;
      }

      buildTimer++;
      drawStamped();

      if(buildPhase==='FORMING'){
        nodes.forEach((n,i)=>{if(buildTimer<i*2)return;n.x+=(n.tx-n.x)*.1;n.y+=(n.ty-n.y)*.1;n.opacity+=(1-n.opacity)*.08;n.r+=(n.tr-n.r)*.1;n.glow=5+Math.sin(globalT*.1+i)*3;});
        if(buildTimer>BUILD_FLY){buildPhase='HOLDING';buildTimer=0;nodes.forEach(n=>{n.glowing=true;});}
      }
      else if(buildPhase==='HOLDING'){
        nodes.forEach((n,i)=>{n.x+=(n.tx-n.x)*.3;n.y+=(n.ty-n.y)*.3;n.glow=14+Math.sin(globalT*.08+i)*5;});
        if(buildTimer>BUILD_HOLD){stampedText+=TEXT[charIdx];charIdx++;buildPhase='STAMPING';buildTimer=0;}
      }
      else if(buildPhase==='STAMPING'){
        nodes.forEach(n=>{n.opacity*=.84;n.r*=.9;});
        if(buildTimer>BUILD_STAMP)startBuildingChar();
      }
      else if(buildPhase==='CELEBRATE'){
        celTimer++;
        if(celTimer>CEL_SWITCH){celIdx++;celTimer=0;retargetCel();}
        nodes.forEach((n,i)=>{
          n.x+=(n.tx-n.x)*.07+(Math.random()-.5)*.4;
          n.y+=(n.ty-n.y)*.07+(Math.random()-.5)*.4;
          n.opacity+=(1-n.opacity)*.06; n.r+=(n.tr-n.r)*.08;
          const d=Math.hypot(n.x-n.tx,n.y-n.ty); n.glowing=d<9;
          n.glow=n.glowing?12+Math.sin(globalT*.05+i*.3)*5:4;
        });
        // After CEL_TOTAL cycles, restart
        if(celIdx>=CEL_TOTAL){charIdx=0;stampedText='';buildPhase='IDLE';buildTimer=0;nodes=[];startBuildingChar();}
      }

      // Edges
      const maxD=buildPhase==='CELEBRATE'?92:68;
      for(let i=0;i<nodes.length;i++){const a=nodes[i];if(a.opacity<.05)continue;for(let j=i+1;j<nodes.length;j++){const b=nodes[j];if(b.opacity<.05)continue;const dx=a.x-b.x,dy=a.y-b.y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<maxD){const al=(1-dist/maxD)*Math.min(a.opacity,b.opacity)*.52;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=(a.glowing||b.glowing)?`rgba(0,255,120,${al})`:`rgba(0,185,255,${al*.7})`;ctx.lineWidth=(a.glowing||b.glowing)?1.4:1;ctx.stroke();}}}

      // Nodes
      nodes.forEach(n=>{
        if(n.opacity<.02||n.r<.5)return;
        ctx.beginPath();
        if(n.glowing){for(let s=0;s<=6;s++){const a=(s/6)*Math.PI*2-Math.PI/6,px=n.x+Math.cos(a)*n.r,py=n.y+Math.sin(a)*n.r;s===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}}
        else ctx.arc(n.x,n.y,Math.max(1,n.r),0,Math.PI*2);
        const col=n.glowing?'0,255,120':'0,185,255';
        ctx.fillStyle=`rgba(${col},${n.opacity*.2})`; ctx.strokeStyle=`rgba(${col},${n.opacity})`;
        ctx.shadowColor=n.glowing?'#00ff78':'#00b9ff'; ctx.shadowBlur=n.glow; ctx.lineWidth=1.5;
        ctx.fill(); ctx.stroke(); ctx.shadowBlur=0;
        if(n.opacity>.2&&n.r>3&&n.word&&n.word!=='•'){
          ctx.fillStyle=`rgba(255,255,255,${n.opacity*.84})`;
          ctx.font=`${Math.min(10,Math.max(7,n.r*.78))}px 'Share Tech Mono',monospace`;
          ctx.textAlign='center'; ctx.textBaseline='middle';
          ctx.shadowColor=n.glowing?'#00ff78':'#00b9ff'; ctx.shadowBlur=3;
          ctx.fillText(n.word,n.x,n.y-n.r-8); ctx.shadowBlur=0;
        }
      });
      requestAnimationFrame(draw);
    }
    draw();

    return {
      addWords(words){ if(words&&words.length)wordQueue.push(...words.filter(w=>w&&w.length>=4)); },
      activate(iw){ if(iw&&iw.length)wordQueue.push(...iw.filter(w=>w&&w.length>=4)); isActive=true;charIdx=0;stampedText='';buildPhase='IDLE';buildTimer=0;nodes=[];startBuildingChar(); },
      deactivate(){ isActive=false;nodes=[];wordQueue=[];charIdx=0;stampedText='';buildPhase='IDLE';buildTimer=0; }
    };
  }


  function updateClock() {
    const now = new Date();
    const ms = now.getMilliseconds().toString().padStart(3, '0');
    const time = now.toLocaleTimeString('en-US', { hour12: false }) + ':' + ms;
    $('sys-time').textContent = time;
  }

  // ── Matrix Rain (HUD style) ──
  function initMatrix() {
    const canvas = $('matrix-canvas');
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    
    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;
    
    const chars = '01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*()_+{}[]|:;<>,.?/~'.split('');
    const fontSize = 12;
    let columns = width / fontSize;
    const drops = [];
    
    for (let x = 0; x < columns; x++) {
      drops[x] = 1;
    }
    
    function draw() {
      ctx.fillStyle = 'rgba(3, 6, 10, 0.08)'; // Cyber void
      ctx.fillRect(0, 0, width, height);
      
      // Randomly switch between cyan and green for variety
      ctx.font = fontSize + 'px "Share Tech Mono", monospace';
      
      for (let i = 0; i < drops.length; i++) {
        const text = chars[Math.floor(Math.random() * chars.length)];
        ctx.fillStyle = Math.random() > 0.5 ? '#0ff' : '#00ff41';
        ctx.fillText(text, i * fontSize, drops[i] * fontSize);
        
        if (drops[i] * fontSize > height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i]++;
      }
    }
    
    setInterval(draw, 40);
    
    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      columns = width / fontSize;
      while(drops.length < columns) drops.push(1);
    });
  }

  // ── File Upload ──
  function handleFileSelect(e) {
    if (state.isTranslating) return;
    const file = e.target.files ? e.target.files[0] : e.dataTransfer.files[0];
    if (!file || file.type !== 'application/pdf') {
      showToast('INVALID_PAYLOAD: System requires PDF format.', 'error');
      return;
    }

    state.file = file;
    const formData = new FormData();
    formData.append('file', file);

    $('file-meta').textContent = 'Authenticating...';
    $('upload-zone').style.display = 'none';
    $('file-info').classList.add('visible');
    $('file-name').textContent = file.name;

    fetch('/api/upload', { method: 'POST', body: formData })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          $('file-meta').textContent = `SIZE: ${data.size_mb}MB | SECTORS: ${data.pages}`;
          $('translate-btn').disabled = false;
          state.preview.totalPages = data.pages;
          state.preview.originalName = data.filename;
          
          showToast(`PAYLOAD_ACCEPTED: [${file.name}] ready for injection.`, 'success');
        } else {
          resetFile();
          showToast(data.error, 'error');
        }
      })
      .catch(err => {
        resetFile();
        showToast('SYSTEM_ERROR: Connection dropped.', 'error');
      });
  }

  function resetFile() {
    state.file = null;
    $('file-input').value = '';
    $('upload-zone').style.display = 'block';
    $('file-info').classList.remove('visible');
    $('translate-btn').disabled = true;
    $('file-name').textContent = 'target_file.pdf';
    $('file-meta').textContent = 'Analyzing...';
  }

  // ── Translation Process ──
  function startTranslation() {
    if (!state.file) return;

    const sourceLang = $('source-lang').value;
    const targetLang = $('target-lang').value;
    const startPage = $('page-start').value ? parseInt($('page-start').value) - 1 : 0;
    const endPage = $('page-enabled') && $('page-enabled').checked && $('page-end').value 
                    ? parseInt($('page-end').value) : null;

    state.isTranslating = true;
    if (lexNet) lexNet.activate(null); // Kick off animation immediately
    
    // UI Update
    $('upload-section').style.opacity = '0.5';
    $('settings-section').style.opacity = '0.5';
    $('translate-btn').disabled = true;
    $('progress-section').classList.add('visible');
    $('completion-section').classList.remove('visible');
    $('cancel-btn').style.display = 'block';
    updateStatus('Injecting decryption logic...', 'translating');

    fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: state.preview.originalName,
        source_lang: sourceLang,
        target_lang: targetLang,
        workers: state.settings.workers,
        chunk_size: state.settings.chunk_size,
        save_every: state.settings.save_every,
        start_page: startPage,
        end_page: endPage
      })
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        state.taskId = data.task_id;
        state.preview.translatedName = data.output_file;
      } else {
        handleTranslationError(data.error);
      }
    })
    .catch(err => handleTranslationError('CONNECTION_FAILED'));
  }

  function cancelTranslation() {
    if (!state.taskId) return;
    fetch('/api/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.taskId })
    }).then(r => r.json()).then(data => {
      if(data.success) {
        updateStatus('ABORTING SEQUENCE...', 'idle');
        $('cancel-btn').disabled = true;
      }
    });
  }

  function handleTranslationError(msg) {
    state.isTranslating = false;
    state.taskId = null;
    $('upload-section').style.opacity = '1';
    $('settings-section').style.opacity = '1';
    $('translate-btn').disabled = false;
    $('cancel-btn').style.display = 'none';
    $('cancel-btn').disabled = false;
    updateStatus('CRITICAL FAILURE: ' + msg, 'error');
    showToast('CRITICAL_FAILURE: ' + msg, 'error');
  }

  function setCircularProgress(percent) {
    const circle = $('progress-circle');
    if(circle) {
      const radius = circle.r.baseVal.value;
      const circumference = radius * 2 * Math.PI;
      const offset = circumference - percent / 100 * circumference;
      circle.style.strokeDashoffset = offset;
    }
  }

  // ── Socket Event Listeners ──
  function bindSocket() {
    socket.on('lexical_chunk', data => {
      if (lexNet && data.words) lexNet.addWords(data.words);
    });

    socket.on('translation_progress', data => {
      if (data.task_id !== state.taskId) return;
      // Feed words to lexical network from progress too
      if (lexNet && data.lexical_words) lexNet.addWords(data.lexical_words);
      
      $('progress-pct').textContent = data.progress + '%';
      $('progress-bar').style.width = data.progress + '%';
      setCircularProgress(data.progress);
      
      $('progress-page').textContent = `SECTOR ${data.current_page} OF ${data.total_pages}`;
      $('progress-page').setAttribute('data-text', `SECTOR ${data.current_page} OF ${data.total_pages}`);
      
      $('stat-translated').textContent = data.stats.translated;
      $('stat-cached').textContent = data.stats.cached;
      $('stat-eta').textContent = data.eta;
      $('stat-errors').textContent = data.stats.errors;

      updateStatus(`PROCESSING BLOCKS... [${data.stats.avg_quality ? Math.round(data.stats.avg_quality*100)+'%' : 'N/A'} Q-RATING]`, 'translating');
      
      // Update preview if looking at current page
      if (state.preview.mode === 'translated' && state.preview.currentPage === data.current_page) {
        loadPreviewPage();
      }
    });

    socket.on('translation_complete', data => {
      if (data.task_id !== state.taskId) return;
      
      state.isTranslating = false;
      state.taskId = null;
      if (lexNet) lexNet.deactivate();
      
      $('progress-pct').textContent = '100%';
      $('progress-bar').style.width = '100%';
      setCircularProgress(100);
      $('cancel-btn').style.display = 'none';
      $('cancel-btn').disabled = false;
      
      updateStatus('PAYLOAD DECRYPTED.', 'complete');
      showToast('OPERATION SUCCESSFUL', 'success');
      
      $('progress-section').classList.remove('visible');
      $('completion-section').classList.add('visible');
      $('completion-subtitle').textContent = `Time elapsed: ${data.elapsed} | Fragments mutated: ${data.stats.translated}`;
      
      $('download-btn').href = '/api/download/' + data.output_file;
      
      // Reset sections
      $('upload-section').style.opacity = '1';
      $('settings-section').style.opacity = '1';
      $('translate-btn').disabled = false;

      // Enable preview
      $('preview-section').classList.add('visible');
      state.preview.mode = 'translated';
      $('tab-original').classList.remove('active');
      $('tab-translated').classList.add('active');
      $('preview-img').style.display = 'block';
      $('preview-placeholder').style.display = 'none';
      $('prev-page-btn').disabled = false;
      $('next-page-btn').disabled = false;
      loadPreviewPage();
    });

    socket.on('translation_error', data => {
      if (data.task_id !== state.taskId) return;
      if (lexNet) lexNet.deactivate();
      handleTranslationError(data.error);
    });
  }

  // ── Preview & Interaction ──
  function loadPreviewPage() {
    let filename = state.preview.mode === 'original' ? state.preview.originalName : state.preview.translatedName;
    if (!filename) return;

    $('preview-page-info').textContent = `0x${state.preview.currentPage.toString(16).toUpperCase().padStart(2, '0')}`;
    const url = `/api/preview/${filename}/${state.preview.currentPage}?t=${Date.now()}`;
    
    // Add visual scan effect
    $('preview-img').style.opacity = '0.5';
    $('preview-img').src = url;
    $('preview-img').onload = () => {
      $('preview-img').style.opacity = '1';
    };
  }

  function updateStatus(text, st) {
    $('status-text').textContent = text;
    $('status-dot').className = `status-dot ${st}`;
  }

  function showToast(msg, type='info') {
    const c = $('toast-container');
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    let icon = 'ℹ️';
    if(type === 'success') icon = '✓';
    if(type === 'error') icon = '⚠️';
    if(type === 'warning') icon = '⚡';
    
    t.innerHTML = `<span class="toast-icon">${icon}</span> <span>${msg}</span>`;
    c.appendChild(t);
    
    setTimeout(() => {
      t.classList.add('toast-out');
      setTimeout(() => t.remove(), 300);
    }, 4000);
  }

  // ── Settings ──
  function loadSettings() {
    const saved = localStorage.getItem('pdf-translator-settings');
    if (saved) {
      state.settings = JSON.parse(saved);
      $('setting-workers').value = state.settings.workers;
      $('setting-chunk-size').value = state.settings.chunk_size;
      $('setting-save-every').value = state.settings.save_every;
    }
  }

  function saveSettings() {
    state.settings = {
      workers: parseInt($('setting-workers').value),
      chunk_size: parseInt($('setting-chunk-size').value),
      save_every: parseInt($('setting-save-every').value)
    };
    localStorage.setItem('pdf-translator-settings', JSON.stringify(state.settings));
    $('settings-modal').classList.remove('visible');
    showToast('SYS_CONFIG UPDATED', 'success');
  }

  // ── Events ──
  function bindEvents() {
    // Upload Zone Drag & Drop
    const uz = $('upload-zone');
    uz.addEventListener('click', () => $('file-input').click());
    uz.addEventListener('dragover', e => { e.preventDefault(); uz.classList.add('drag-over'); });
    uz.addEventListener('dragleave', () => uz.classList.remove('drag-over'));
    uz.addEventListener('drop', e => {
      e.preventDefault();
      uz.classList.remove('drag-over');
      handleFileSelect(e);
    });
    $('file-input').addEventListener('change', handleFileSelect);
    $('file-remove').addEventListener('click', resetFile);

    // Page Range Toggle
    const prTog = $('page-range-enabled');
    if(prTog) {
      prTog.addEventListener('change', e => {
        $('page-range-row').style.display = e.target.checked ? 'flex' : 'none';
      });
    }

    // Buttons
    $('translate-btn').addEventListener('click', startTranslation);
    $('cancel-btn').addEventListener('click', cancelTranslation);
    
    // Settings Modal
    $('settings-btn').addEventListener('click', () => $('settings-modal').classList.add('visible'));
    $('modal-close').addEventListener('click', () => $('settings-modal').classList.remove('visible'));
    $('save-settings-btn').addEventListener('click', saveSettings);

    $('clear-cache-btn').addEventListener('click', () => {
      fetch('/api/clear-cache', { method: 'POST' })
        .then(r => r.json())
        .then(d => {
          showToast(d.message, 'success');
          $('settings-modal').classList.remove('visible');
        });
    });

    // Preview Navigation
    $('prev-page-btn').addEventListener('click', () => {
      if (state.preview.currentPage > 1) {
        state.preview.currentPage--;
        loadPreviewPage();
      }
    });
    $('next-page-btn').addEventListener('click', () => {
      if (state.preview.currentPage < state.preview.totalPages) {
        state.preview.currentPage++;
        loadPreviewPage();
      }
    });

    // Preview Tabs
    $('tab-original').addEventListener('click', () => {
      $('tab-translated').classList.remove('active');
      $('tab-original').classList.add('active');
      state.preview.mode = 'original';
      loadPreviewPage();
    });
    $('tab-translated').addEventListener('click', () => {
      if (!state.preview.translatedName) return;
      $('tab-original').classList.remove('active');
      $('tab-translated').classList.add('active');
      state.preview.mode = 'translated';
      loadPreviewPage();
    });
  }

  // Run
  init();
});
