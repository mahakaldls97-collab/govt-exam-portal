// India Map Engine - Interactive SVG Background Map
const INDIA_STATES = {
  'Rajasthan': { cx: 220, cy: 250, color: '#FF6B35', abbr: 'RJ', path: 'M150,180 L200,160 L280,170 L310,200 L300,260 L280,320 L240,340 L190,320 L160,280 L140,230 Z' },
  'Uttar Pradesh': { cx: 350, cy: 240, color: '#004E89', abbr: 'UP', path: 'M310,200 L380,180 L420,200 L430,240 L410,280 L370,300 L320,280 L300,260 Z' },
  'Bihar': { cx: 440, cy: 240, color: '#1A936F', abbr: 'BR', path: 'M420,210 L470,200 L490,220 L480,260 L450,280 L420,270 L410,240 Z' },
  'Madhya Pradesh': { cx: 310, cy: 310, color: '#C1292E', abbr: 'MP', path: 'M240,280 L320,270 L380,290 L400,320 L380,360 L320,370 L260,350 L230,320 Z' },
  'Maharashtra': { cx: 280, cy: 400, color: '#F26419', abbr: 'MH', path: 'M200,360 L270,350 L340,370 L370,400 L350,440 L280,460 L220,440 L190,400 Z' },
  'Gujarat': { cx: 170, cy: 340, color: '#86BBD8', abbr: 'GJ', path: 'M100,280 L170,280 L200,300 L210,350 L180,380 L130,370 L100,340 L90,300 Z' },
  'Karnataka': { cx: 260, cy: 480, color: '#33658A', abbr: 'KA', path: 'M210,440 L280,430 L320,450 L330,500 L300,530 L250,540 L210,510 L200,470 Z' },
  'Tamil Nadu': { cx: 310, cy: 540, color: '#F6AE2D', abbr: 'TN', path: 'M280,500 L330,490 L360,510 L370,560 L340,590 L290,580 L270,540 Z' },
  'Kerala': { cx: 250, cy: 560, color: '#2F9C95', abbr: 'KL', path: 'M230,520 L260,510 L270,540 L260,580 L240,600 L220,580 L225,540 Z' },
  'Andhra Pradesh': { cx: 330, cy: 440, color: '#9B2335', abbr: 'AP', path: 'M300,400 L370,390 L400,420 L390,470 L350,490 L300,480 L280,440 Z' },
  'Telangana': { cx: 320, cy: 400, color: '#E8C547', abbr: 'TS', path: 'M290,370 L350,360 L380,380 L370,410 L340,420 L300,410 L280,390 Z' },
  'West Bengal': { cx: 470, cy: 290, color: '#023047', abbr: 'WB', path: 'M450,240 L490,230 L510,260 L500,310 L480,340 L460,330 L440,290 Z' },
  'Odisha': { cx: 420, cy: 350, color: '#219EBC', abbr: 'OD', path: 'M380,310 L430,300 L460,330 L460,370 L430,390 L390,380 L370,350 Z' },
  'Punjab': { cx: 260, cy: 140, color: '#FFB703', abbr: 'PB', path: 'M240,110 L280,100 L300,120 L290,150 L260,160 L240,140 Z' },
  'Haryana': { cx: 280, cy: 170, color: '#8338EC', abbr: 'HR', path: 'M260,150 L300,140 L320,160 L310,190 L280,200 L250,180 Z' },
  'Delhi': { cx: 295, cy: 185, color: '#FF006E', abbr: 'DL', path: 'M288,178 L302,178 L305,192 L292,195 L285,188 Z' },
  'Jharkhand': { cx: 440, cy: 290, color: '#06D6A0', abbr: 'JH', path: 'M410,270 L450,260 L470,280 L460,310 L430,320 L400,310 Z' },
  'Chhattisgarh': { cx: 380, cy: 340, color: '#118AB2', abbr: 'CG', path: 'M350,300 L400,290 L420,320 L410,360 L380,380 L350,360 L340,330 Z' },
  'Uttarakhand': { cx: 320, cy: 140, color: '#073B4C', abbr: 'UK', path: 'M300,110 L340,100 L360,120 L350,150 L320,160 L300,140 Z' },
  'Himachal Pradesh': { cx: 280, cy: 110, color: '#EF476F', abbr: 'HP', path: 'M260,90 L300,80 L320,100 L310,120 L280,130 L260,110 Z' },
  'Jammu & Kashmir': { cx: 240, cy: 70, color: '#06D6A0', abbr: 'JK', path: 'M200,40 L260,30 L290,50 L280,80 L250,100 L210,90 L190,70 Z' },
  'Assam': { cx: 540, cy: 230, color: '#FFD166', abbr: 'AS', path: 'M510,210 L560,200 L580,220 L570,250 L540,260 L510,245 Z' },
  'Goa': { cx: 220, cy: 460, color: '#06D6A0', abbr: 'GA', path: 'M210,450 L230,445 L235,465 L220,475 L208,465 Z' },
  'All India': { cx: 310, cy: 350, color: '#FF9933', abbr: 'IN', path: '' }
};

class IndiaMapEngine {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;
    this.currentState = 'All India';
    this.init();
  }
  init() {
    this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.svg.setAttribute('viewBox', '0 0 650 700');
    this.svg.style.cssText = 'width:100%;height:100%;position:absolute;top:0;left:0;opacity:0.08;pointer-events:none;transition:opacity 0.5s ease;';
    Object.entries(INDIA_STATES).forEach(([name, data]) => {
      if (!data.path) return;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('data-state', name);
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', data.path);
      path.setAttribute('fill', data.color);
      path.setAttribute('stroke', '#fff');
      path.setAttribute('stroke-width', '1.5');
      path.setAttribute('opacity', '0.7');
      path.style.transition = 'all 0.4s ease';
      g.appendChild(path);
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', data.cx);
      text.setAttribute('y', data.cy);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', '#fff');
      text.setAttribute('font-size', '11');
      text.setAttribute('font-weight', 'bold');
      text.textContent = data.abbr;
      g.appendChild(text);
      this.svg.appendChild(g);
    });
    this.container.appendChild(this.svg);
    this.badge = document.createElement('div');
    this.badge.id = 'map-state-badge';
    this.badge.className = 'map-state-badge hidden';
    this.badge.innerHTML = '<div class="badge-content"><span>\ud83d\uddfa\ufe0f</span><span class="badge-text">\u092d\u093e\u0930\u0924 \u0915\u093e \u0928\u0915\u094d\u0936\u093e</span><button class="badge-reset" onclick="window.indiaMap.resetToIndia()">\u21ba Reset</button></div>';
    this.container.appendChild(this.badge);
  }
  highlightState(stateName) {
    if (!this.svg || !INDIA_STATES[stateName]) return;
    this.currentState = stateName;
    this.svg.style.opacity = '0.15';
    this.svg.querySelectorAll('g').forEach(g => {
      const s = g.getAttribute('data-state');
      const p = g.querySelector('path');
      if (s === stateName) {
        p.setAttribute('opacity', '1');
        p.setAttribute('stroke-width', '3');
        p.setAttribute('stroke', '#FFD700');
        g.style.transform = 'scale(1.1)';
        g.style.transformOrigin = `${INDIA_STATES[stateName].cx}px ${INDIA_STATES[stateName].cy}px`;
        g.style.transition = 'transform 0.5s ease';
      } else {
        p.setAttribute('opacity', '0.2');
        p.setAttribute('stroke-width', '0.5');
        p.setAttribute('stroke', '#ccc');
        g.style.transform = 'scale(1)';
      }
    });
    this.badge.classList.remove('hidden');
    this.badge.querySelector('.badge-text').textContent = '\ud83d\udccd ' + stateName + ' \u0915\u0947 \u092a\u0930\u0940\u0915\u094d\u0937\u093e\u090f\u0902';
    this.badge.style.borderColor = INDIA_STATES[stateName].color;
  }
  resetToIndia() {
    this.currentState = 'All India';
    this.svg.style.opacity = '0.08';
    this.svg.querySelectorAll('g').forEach(g => {
      const p = g.querySelector('path');
      p.setAttribute('opacity', '0.7');
      p.setAttribute('stroke-width', '1.5');
      p.setAttribute('stroke', '#fff');
      g.style.transform = 'scale(1)';
    });
    this.badge.classList.add('hidden');
    if (typeof filterByState === 'function') filterByState('all');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.innerWidth >= 1024) {
    window.indiaMap = new IndiaMapEngine('india-map-container');
  }
  document.querySelectorAll('[data-state]').forEach(el => {
    if (el.tagName === 'A' || el.classList.contains('exam-item')) {
      el.addEventListener('mouseenter', () => {
        const state = el.getAttribute('data-state');
        if (state && window.indiaMap) window.indiaMap.highlightState(state);
      });
    }
  });
  document.querySelectorAll('.state-pill').forEach(pill => {
    pill.addEventListener('click', e => {
      e.preventDefault();
      const state = pill.getAttribute('data-state');
      if (state === 'all') {
        if (window.indiaMap) window.indiaMap.resetToIndia();
        filterByState('all');
      } else {
        if (window.indiaMap) window.indiaMap.highlightState(state);
        filterByState(state);
      }
      document.querySelectorAll('.state-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });
});

function filterByState(state) {
  document.querySelectorAll('.exam-item').forEach(item => {
    if (state === 'all') { item.style.display = ''; }
    else {
      const s = item.getAttribute('data-state');
      item.style.display = (s === state || s === 'All India') ? '' : 'none';
    }
  });
}

async function triggerSync() {
  const btn = document.getElementById('sync-btn');
  if (btn) { btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Syncing...'; btn.disabled = true; }
  try {
    const resp = await fetch('/api/sync/sarkariresult', { method: 'POST' });
    const data = await resp.json();
    if (data.status === 'success') {
      showToast('\u2705 Sync Complete! ' + data.inserted + ' new exams added.', 'success');
      setTimeout(() => location.reload(), 2000);
    } else { showToast('\u26a0\ufe0f Sync failed.', 'error'); }
  } catch(e) { showToast('\u26a0\ufe0f Network error.', 'error'); }
  if (btn) { btn.innerHTML = '\u26a1 Sync Now'; btn.disabled = false; }
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast-notification toast-' + type;
  t.innerHTML = msg;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add('show'), 10);
  setTimeout(() => t.remove(), 4000);
}
