const state = {
    source: { slices: 0, hasMask: false, size: [0, 0], origin: [0, 0, 0], spacing: [1, 1, 1], echos: 1, currentEcho: 0, imageData: null },
    target: { slices: 0, hasMask: false, size: [0, 0], origin: [0, 0, 0], spacing: [1, 1, 1], echos: 1, currentEcho: 0, imageData: null, originalImageData: null },
    mode: 'curtain',
    curtainPos: 0.5,
    curtainDir: 'horizontal',
    blend: 0.5,
    zoom: 1,
    currentSlice: 0,
    targetSlice: 0,
    direction: 'normal',
    registrationDone: false,
    settingsChanged: false,
    showAligned: true
};

let sliceUpdateTimeout = null;
function debouncedUpdateSlice(changedSide = null) {
    if (sliceUpdateTimeout) clearTimeout(sliceUpdateTimeout);

    // Immediately update the changed side, debounce the other
    if (changedSide) {
        updateSliceSingle(changedSide);
        sliceUpdateTimeout = setTimeout(() => {
            updateSliceSingle(changedSide === 'source' ? 'target' : 'source');
        }, 50);
    } else {
        sliceUpdateTimeout = setTimeout(() => updateSlice(), 50);
    }
}

function syncSlices(changedSide) {
    // Only sync sliders when showing aligned images
    if (!state.showAligned) return;

    if (changedSide === 'source') {
        // Source changed -> calculate corresponding target slice
        if (state.target.slices > 0 && state.source.slices > 0) {
            const physZ = state.source.origin[2] + state.currentSlice * state.source.spacing[2];
            let targetSlice = Math.round((physZ - state.target.origin[2]) / state.target.spacing[2]);
            targetSlice = Math.max(0, Math.min(state.target.slices - 1, targetSlice));
            state.targetSlice = targetSlice;
            document.getElementById('target-slice-slider').value = targetSlice;
            document.getElementById('target-slice-slider-info').textContent = `${targetSlice + 1} / ${state.target.slices}`;
        }
    } else {
        // Target changed -> calculate corresponding source slice
        if (state.source.slices > 0 && state.target.slices > 0) {
            const physZ = state.target.origin[2] + state.targetSlice * state.target.spacing[2];
            let sourceSlice = Math.round((physZ - state.source.origin[2]) / state.source.spacing[2]);
            sourceSlice = Math.max(0, Math.min(state.source.slices - 1, sourceSlice));
            state.currentSlice = sourceSlice;
            document.getElementById('slice-slider').value = sourceSlice;
            document.getElementById('slice-info').textContent = `${sourceSlice + 1} / ${state.source.slices}`;
        }
    }
}

function changeSlice(side, delta) {
    if (side === 'source') {
        const newSlice = Math.max(0, Math.min(state.source.slices - 1, state.currentSlice + delta));
        if (newSlice !== state.currentSlice) {
            state.currentSlice = newSlice;
            document.getElementById('slice-slider').value = newSlice;
            document.getElementById('slice-info').textContent = `${newSlice + 1} / ${state.source.slices}`;
            syncSlices('source');
            debouncedUpdateSlice('source');
        }
    } else {
        const newSlice = Math.max(0, Math.min(state.target.slices - 1, state.targetSlice + delta));
        if (newSlice !== state.targetSlice) {
            state.targetSlice = newSlice;
            document.getElementById('target-slice-slider').value = newSlice;
            document.getElementById('target-slice-slider-info').textContent = `${newSlice + 1} / ${state.target.slices}`;
            syncSlices('target');
            debouncedUpdateSlice('target');
        }
    }
}

function updateTargetSliderVisibility() {
    const show = state.target.slices > 0 && (state.mode === 'curtain' || state.mode === 'split' || state.mode === 'blend');
    document.getElementById('target-slice-control').style.display = show ? 'flex' : 'none';
}

function updateAlignToggleVisibility() {
    // Show toggle when both DICOMs are loaded and not in split mode
    const show = state.source.slices > 0 && state.target.slices > 0 && state.mode !== 'split';
    document.getElementById('align-toggle-control').style.display = show ? 'flex' : 'none';
}

const spatialViz = { rotX: -0.5, rotY: 0.5, isDragging: false, lastX: 0, lastY: 0, data: null };

function showStatus(message, type) {
    const bar = document.getElementById('status-bar');
    bar.textContent = message;
    bar.className = type;
}

function hideStatus() {
    document.getElementById('status-bar').className = '';
}

function updateUI() {
    const hasSource = state.source.slices > 0;
    const hasTarget = state.target.slices > 0;
    const hasMask = state.source.hasMask;

    document.getElementById('run-button').style.display = state.settingsChanged ? 'block' : 'none';
    document.getElementById('export-section').style.display = (state.registrationDone && hasMask) ? 'block' : 'none';
}

async function loadDicom(side) {
    const path = document.getElementById(`${side}-dicom-path`).value.trim();
    if (!path) return showStatus('Enter a DICOM path', 'error');

    showStatus('Loading DICOM...', 'info');

    try {
        const res = await fetch(`/api/dicom/${side}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        if (!res.ok) throw new Error((await res.json()).detail);

        const data = await res.json();
        state[side].slices = data.slices;
        state[side].size = data.size;
        state[side].origin = data.origin;
        state[side].spacing = data.spacing;
        state[side].echos = data.echos || 1;
        state[side].currentEcho = 0;
        state[side].hasMask = false;

        const slider = document.getElementById('slice-slider');
        if (state.source.slices > 0) {
            slider.max = state.source.slices - 1;
            slider.value = Math.floor(state.source.slices / 2);
            slider.disabled = false;
            state.currentSlice = parseInt(slider.value);
        }

        if (side === 'target' && state.target.slices > 0) {
            const targetSlider = document.getElementById('target-slice-slider');
            targetSlider.max = state.target.slices - 1;
            targetSlider.value = Math.floor(state.target.slices / 2);
            targetSlider.disabled = false;
            state.targetSlice = parseInt(targetSlider.value);
            document.getElementById('target-slice-slider-info').textContent = `${state.targetSlice + 1} / ${state.target.slices}`;
        }

        const echoControl = document.getElementById(`${side}-echo-control`);
        const echoButtons = document.getElementById(`${side}-echo-buttons`);
        if (state[side].echos > 1) {
            echoControl.style.display = 'flex';
            echoButtons.innerHTML = '';
            for (let i = 0; i < state[side].echos; i++) {
                const btn = document.createElement('button');
                btn.className = 'echo-btn' + (i === 0 ? ' active' : '');
                btn.textContent = i + 1;
                btn.onclick = () => changeEcho(side, i);
                echoButtons.appendChild(btn);
            }
        } else {
            echoControl.style.display = 'none';
        }

        await updateSlice();
        hideStatus();
        updateSpatialRelation();
        updateUI();
        updateTargetSliderVisibility();
        updateAlignToggleVisibility();

        // Auto-register if both DICOMs loaded and mask exists
        if (side === 'target' && state.source.slices > 0 && state.source.hasMask) {
            await autoRegister();
        }

    } catch (e) {
        showStatus(`Error: ${e.message}`, 'error');
    }
}

async function loadMask(side) {
    const path = document.getElementById(`${side}-mask-path`).value.trim();
    if (!path) return showStatus('Enter a mask path', 'error');

    showStatus('Loading mask...', 'info');

    try {
        const res = await fetch(`/api/mask/${side}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        if (!res.ok) throw new Error((await res.json()).detail);

        state[side].hasMask = true;
        await updateSlice();
        hideStatus();
        updateUI();

        // Auto-register if both DICOMs loaded
        if (side === 'source' && state.source.slices > 0 && state.target.slices > 0) {
            await autoRegister();
        }

    } catch (e) {
        showStatus(`Error: ${e.message}`, 'error');
    }
}

async function autoRegister() {
    showStatus('Registering...', 'info');

    const reverse = document.getElementById('reverse-select').value;
    const subpixel = parseInt(document.getElementById('subpixel-input').value);

    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reverse, subpixel })
        });
        if (!res.ok) throw new Error((await res.json()).detail);

        const { task_id } = await res.json();
        await pollRegistration(task_id);
    } catch (e) {
        showStatus(`Registration error: ${e.message}`, 'error');
    }
}

async function pollRegistration(taskId) {
    const data = await (await fetch(`/api/status/${taskId}`)).json();
    if (data.status === 'running') {
        return setTimeout(() => pollRegistration(taskId), 500);
    }

    if (data.status === 'done') {
        state.registrationDone = true;
        state.settingsChanged = false;
        state.target.hasMask = true;

        // Update direction dropdown if auto was used
        if (data.used_direction) {
            document.getElementById('reverse-select').value = data.used_direction;
            state.direction = data.used_direction;
        }

        showStatus(data.message, 'success');
        await updateSlice();
        updateUI();
    } else {
        showStatus(`Error: ${data.message}`, 'error');
    }
}

async function runRegistration() {
    document.getElementById('run-button').disabled = true;
    await autoRegister();
    document.getElementById('run-button').disabled = false;
}

async function exportMask() {
    try {
        const res = await fetch('/api/browse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'save', initial_dir: '' })
        });
        const data = await res.json();
        if (!data.path) return;

        showStatus('Exporting...', 'info');
        const exportRes = await fetch('/api/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: data.path })
        });

        if (!exportRes.ok) throw new Error((await exportRes.json()).detail);
        showStatus(`Exported to ${data.path}`, 'success');
    } catch (e) {
        showStatus(`Export error: ${e.message}`, 'error');
    }
}

async function loadSourceImage() {
    if (state.source.slices === 0) return null;
    const url = `/api/slice/source/${state.currentSlice}?mask=${state.source.hasMask}&t=${Date.now()}`;
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = url;
    });
}

async function loadTargetAligned() {
    if (state.target.slices === 0) return null;
    const reverse = state.direction === 'reverse';
    const url = `/api/slice/aligned/${state.currentSlice}?mask=${state.target.hasMask}&reverse=${reverse}&t=${Date.now()}`;
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = url;
    });
}

async function loadTargetOriginal() {
    if (state.target.slices === 0) return null;
    let targetSliceIdx = state.targetSlice;
    // Only sync with source when showing aligned (not original) and not in split mode
    if (state.showAligned && state.mode !== 'split' && state.source.slices > 0) {
        const physZ = state.source.origin[2] + state.currentSlice * state.source.spacing[2];
        targetSliceIdx = Math.round((physZ - state.target.origin[2]) / state.target.spacing[2]);
        targetSliceIdx = Math.max(0, Math.min(state.target.slices - 1, targetSliceIdx));
    }
    if (state.direction === 'reverse') {
        targetSliceIdx = state.target.slices - 1 - targetSliceIdx;
    }
    const url = `/api/slice/target/${targetSliceIdx}?mask=${state.target.hasMask}&t=${Date.now()}`;
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = url;
    });
}

async function updateSliceSingle(side) {
    if (side === 'source') {
        document.getElementById('slice-info').textContent =
            `${state.currentSlice + 1} / ${state.source.slices}`;
        const img = await loadSourceImage();
        if (img) state.source.imageData = img;
    } else {
        if (state.target.slices > 0) {
            document.getElementById('target-slice-slider-info').textContent =
                `${state.targetSlice + 1} / ${state.target.slices}`;
        }
        const [aligned, original] = await Promise.all([loadTargetAligned(), loadTargetOriginal()]);
        state.target.imageData = aligned || original;
        state.target.originalImageData = original;
    }
    document.getElementById('viewer-placeholder').classList.toggle('hidden',
        state.source.imageData || state.target.imageData);
    renderViewer();
}

async function updateSlice() {
    document.getElementById('slice-info').textContent =
        `${state.currentSlice + 1} / ${state.source.slices}`;

    if (state.target.slices > 0) {
        document.getElementById('target-slice-slider-info').textContent =
            `${state.targetSlice + 1} / ${state.target.slices}`;
    }

    const [sourceImg, targetAligned, targetOriginal] = await Promise.all([
        loadSourceImage(),
        loadTargetAligned(),
        loadTargetOriginal()
    ]);

    state.source.imageData = sourceImg;
    state.target.imageData = targetAligned || targetOriginal;
    state.target.originalImageData = targetOriginal;

    document.getElementById('viewer-placeholder').classList.toggle('hidden', sourceImg || targetAligned || targetOriginal);
    renderViewer();
}

function renderViewer() {
    const container = document.getElementById('viewer-container');
    const sourceCanvas = document.getElementById('source-canvas');
    const targetCanvas = document.getElementById('target-canvas');
    const curtain = document.getElementById('curtain');

    const sourceImg = state.source.imageData;
    // Use original or aligned based on toggle (split mode always uses original)
    const targetImg = (state.mode === 'split' || !state.showAligned)
        ? state.target.originalImageData
        : state.target.imageData;

    if (!sourceImg && !targetImg) return;

    const containerW = container.clientWidth;
    const containerH = container.clientHeight;

    if (state.mode === 'split') {
        curtain.style.display = 'none';
        container.classList.add('split-mode');

        const gap = 20;
        const availW = (containerW - gap) / 2;

        const renderSplit = (canvas, img) => {
            if (!img) {
                canvas.style.display = 'none';
                return;
            }
            canvas.style.display = 'block';
            const scale = Math.min(availW / img.width, containerH / img.height) * state.zoom;
            const w = Math.floor(img.width * scale);
            const h = Math.floor(img.height * scale);
            canvas.width = w;
            canvas.height = h;
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';
            canvas.style.clipPath = 'none';
            canvas.style.opacity = 1;
            canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        };

        renderSplit(sourceCanvas, sourceImg);
        renderSplit(targetCanvas, targetImg);

        sourceCanvas.style.position = 'relative';
        targetCanvas.style.position = 'relative';
        return;
    }

    container.classList.remove('split-mode');
    sourceCanvas.style.position = 'absolute';
    targetCanvas.style.position = 'absolute';

    const img = sourceImg || targetImg;
    const baseW = img.width;
    const baseH = img.height;
    const scale = Math.min(containerW / baseW, containerH / baseH) * state.zoom;

    const w = Math.floor(baseW * scale);
    const h = Math.floor(baseH * scale);

    [sourceCanvas, targetCanvas].forEach(canvas => {
        canvas.style.display = 'block';
        canvas.width = w;
        canvas.height = h;
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';
    });

    const sourceCtx = sourceCanvas.getContext('2d');
    const targetCtx = targetCanvas.getContext('2d');

    sourceCtx.clearRect(0, 0, w, h);
    targetCtx.clearRect(0, 0, w, h);

    if (sourceImg) sourceCtx.drawImage(sourceImg, 0, 0, w, h);
    if (targetImg) targetCtx.drawImage(targetImg, 0, 0, w, h);

    if (state.mode === 'curtain') {
        curtain.style.display = 'block';
        const pos = state.curtainPos * 100;

        if (state.curtainDir === 'horizontal') {
            sourceCanvas.style.clipPath = `inset(0 ${100 - pos}% 0 0)`;
            targetCanvas.style.clipPath = `inset(0 0 0 ${pos}%)`;
            curtain.style.left = `calc(50% + ${(state.curtainPos - 0.5) * w}px)`;
            curtain.style.top = '0';
            curtain.style.width = '3px';
            curtain.style.height = '100%';
            curtain.style.cursor = 'ew-resize';
            curtain.style.transform = 'translateX(-50%)';
        } else {
            sourceCanvas.style.clipPath = `inset(0 0 ${100 - pos}% 0)`;
            targetCanvas.style.clipPath = `inset(${pos}% 0 0 0)`;
            curtain.style.left = '0';
            curtain.style.top = `calc(50% + ${(state.curtainPos - 0.5) * h}px)`;
            curtain.style.width = '100%';
            curtain.style.height = '3px';
            curtain.style.cursor = 'ns-resize';
            curtain.style.transform = 'translateY(-50%)';
        }

        sourceCanvas.style.opacity = 1;
        targetCanvas.style.opacity = 1;
    } else if (state.mode === 'blend') {
        curtain.style.display = 'none';
        sourceCanvas.style.clipPath = 'none';
        targetCanvas.style.clipPath = 'none';
        sourceCanvas.style.opacity = 1 - state.blend;
        targetCanvas.style.opacity = state.blend;
    } else if (state.mode === 'source') {
        curtain.style.display = 'none';
        sourceCanvas.style.clipPath = 'none';
        targetCanvas.style.clipPath = 'none';
        sourceCanvas.style.opacity = 1;
        targetCanvas.style.opacity = 0;
    } else if (state.mode === 'target') {
        curtain.style.display = 'none';
        sourceCanvas.style.clipPath = 'none';
        targetCanvas.style.clipPath = 'none';
        sourceCanvas.style.opacity = 0;
        targetCanvas.style.opacity = 1;
    }
}

async function changeEcho(side, echoIdx) {
    document.querySelectorAll(`#${side}-echo-buttons .echo-btn`).forEach((btn, i) => {
        btn.classList.toggle('active', i === echoIdx);
    });

    try {
        const res = await fetch(`/api/echo/${side}/${echoIdx}`, { method: 'POST' });
        const data = await res.json();
        state[side].slices = data.slices;
        state[side].size = data.size;
        state[side].origin = data.origin;
        state[side].spacing = data.spacing;
        state[side].currentEcho = echoIdx;

        const slider = document.getElementById('slice-slider');
        if (state.source.slices > 0) {
            slider.max = state.source.slices - 1;
            if (state.currentSlice > state.source.slices - 1) {
                state.currentSlice = Math.floor(state.source.slices / 2);
                slider.value = state.currentSlice;
            }
        }

        await updateSlice();
        updateSpatialRelation();
    } catch (e) {
        showStatus(`Echo error: ${e.message}`, 'error');
    }
}

async function browse(inputId, mode) {
    const input = document.getElementById(inputId);
    try {
        const res = await fetch('/api/browse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, initial_dir: input.value.split('/').slice(0, -1).join('/') })
        });
        const data = await res.json();
        if (data.path) input.value = data.path;
    } catch (e) {}
}

async function updateSpatialRelation() {
    if (state.source.slices === 0 || state.target.slices === 0) {
        document.getElementById('spatial-section').style.display = 'none';
        return;
    }

    try {
        const res = await fetch('/api/spatial-relation');
        const data = await res.json();

        document.getElementById('spatial-section').style.display = 'block';

        const status = document.getElementById('spatial-status');
        if (data.error) { status.textContent = 'No Overlap'; status.className = 'error'; }
        else if (data.warning) { status.textContent = 'Low Overlap'; status.className = 'warning'; }
        else { status.textContent = 'OK'; status.className = 'ok'; }

        document.getElementById('overlap-pct').textContent = `${Math.min(data.overlap_pct_source, data.overlap_pct_target)}%`;
        document.getElementById('offset-mm').textContent = `${data.offset_mm.map(v => v.toFixed(1)).join('/')}`;

        spatialViz.data = data;
        renderSpatialViz();

    } catch (e) {}
}

function renderSpatialViz() {
    const data = spatialViz.data;
    if (!data) return;

    const canvas = document.getElementById('spatial-canvas');
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const allBounds = {
        minX: Math.min(data.source.min[0], data.target.min[0]),
        maxX: Math.max(data.source.max[0], data.target.max[0]),
        minY: Math.min(data.source.min[1], data.target.min[1]),
        maxY: Math.max(data.source.max[1], data.target.max[1]),
        minZ: Math.min(data.source.min[2], data.target.min[2]),
        maxZ: Math.max(data.source.max[2], data.target.max[2])
    };

    const maxRange = Math.max(allBounds.maxX - allBounds.minX, allBounds.maxY - allBounds.minY, allBounds.maxZ - allBounds.minZ) || 1;
    const scale = 60 / maxRange;
    const cx = w / 2, cy = h / 2;
    const cosX = Math.cos(spatialViz.rotX), sinX = Math.sin(spatialViz.rotX);
    const cosY = Math.cos(spatialViz.rotY), sinY = Math.sin(spatialViz.rotY);

    function project(x, y, z) {
        let nx = (x - (allBounds.minX + allBounds.maxX) / 2) * scale;
        let ny = (y - (allBounds.minY + allBounds.maxY) / 2) * scale;
        let nz = (z - (allBounds.minZ + allBounds.maxZ) / 2) * scale;
        let y1 = ny * cosX - nz * sinX, z1 = ny * sinX + nz * cosX;
        let x1 = nx * cosY + z1 * sinY;
        return [cx + x1, cy - y1];
    }

    function drawCube(bounds, color, alpha) {
        const c = [[bounds.min[0],bounds.min[1],bounds.min[2]], [bounds.max[0],bounds.min[1],bounds.min[2]],
                   [bounds.max[0],bounds.max[1],bounds.min[2]], [bounds.min[0],bounds.max[1],bounds.min[2]],
                   [bounds.min[0],bounds.min[1],bounds.max[2]], [bounds.max[0],bounds.min[1],bounds.max[2]],
                   [bounds.max[0],bounds.max[1],bounds.max[2]], [bounds.min[0],bounds.max[1],bounds.max[2]]];
        const p = c.map(v => project(...v));
        const faces = [[4,5,6,7],[1,2,6,5],[0,1,5,4]];

        ctx.globalAlpha = alpha;
        faces.forEach(f => {
            ctx.beginPath();
            ctx.moveTo(p[f[0]][0], p[f[0]][1]);
            f.slice(1).forEach(i => ctx.lineTo(p[i][0], p[i][1]));
            ctx.closePath();
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;
            ctx.stroke();
        });
        ctx.globalAlpha = 1;
    }

    drawCube(data.source, '#3b82f6', 0.3);
    drawCube(data.target, '#f97316', 0.3);
    if (data.overlap_vol_mm3 > 0) {
        drawCube({
            min: [Math.max(data.source.min[0],data.target.min[0]), Math.max(data.source.min[1],data.target.min[1]), Math.max(data.source.min[2],data.target.min[2])],
            max: [Math.min(data.source.max[0],data.target.max[0]), Math.min(data.source.max[1],data.target.max[1]), Math.min(data.source.max[2],data.target.max[2])]
        }, '#22c55e', 0.5);
    }
}

// Event Listeners
document.getElementById('slice-slider').addEventListener('input', (e) => {
    state.currentSlice = parseInt(e.target.value);
    document.getElementById('slice-info').textContent = `${state.currentSlice + 1} / ${state.source.slices}`;
    syncSlices('source');
    debouncedUpdateSlice('source');
});

document.getElementById('zoom-slider').addEventListener('input', (e) => {
    state.zoom = parseInt(e.target.value) / 100;
    document.getElementById('zoom-info').textContent = `${e.target.value}%`;
    renderViewer();
});

document.getElementById('blend-slider').addEventListener('input', (e) => {
    state.blend = parseInt(e.target.value) / 100;
    document.getElementById('blend-info').textContent = `${e.target.value}%`;
    renderViewer();
});

document.getElementById('target-slice-slider').addEventListener('input', (e) => {
    state.targetSlice = parseInt(e.target.value);
    document.getElementById('target-slice-slider-info').textContent = `${state.targetSlice + 1} / ${state.target.slices}`;
    syncSlices('target');
    debouncedUpdateSlice('target');
});

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (!btn.dataset.mode) return; // Skip align toggle buttons
        document.querySelectorAll('.mode-btn[data-mode]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.mode = btn.dataset.mode;
        document.querySelector('.blend-control').style.display = state.mode === 'blend' ? 'flex' : 'none';
        document.getElementById('dir-toggle').style.display = state.mode === 'curtain' ? 'flex' : 'none';
        updateTargetSliderVisibility();
        updateAlignToggleVisibility();
        updateSlice();
    });
});

document.querySelectorAll('.dir-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.curtainDir = btn.dataset.dir;
        state.curtainPos = 0.5;

        const curtainEl = document.getElementById('curtain');
        curtainEl.className = `curtain ${state.curtainDir}`;
        document.getElementById('curtain-handle').textContent = state.curtainDir === 'horizontal' ? '↔' : '↕';

        renderViewer();
    });
});

document.querySelectorAll('[data-align]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('[data-align]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.showAligned = btn.dataset.align === 'aligned';
        renderViewer();
    });
});

document.getElementById('reverse-select').addEventListener('change', (e) => {
    state.direction = e.target.value;
    if (state.registrationDone) {
        state.settingsChanged = true;
        updateUI();
    }
    updateSlice();
});

document.getElementById('subpixel-input').addEventListener('change', () => {
    if (state.registrationDone) {
        state.settingsChanged = true;
        updateUI();
    }
});

// Curtain drag
const curtain = document.getElementById('curtain');
let draggingCurtain = false;

curtain.addEventListener('mousedown', () => draggingCurtain = true);
window.addEventListener('mousemove', (e) => {
    if (!draggingCurtain) return;
    const container = document.getElementById('viewer-container');
    const rect = container.getBoundingClientRect();

    if (state.curtainDir === 'horizontal') {
        state.curtainPos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    } else {
        state.curtainPos = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    }
    renderViewer();
});
window.addEventListener('mouseup', () => draggingCurtain = false);

// Spatial drag
const spatialCanvas = document.getElementById('spatial-canvas');
spatialCanvas.addEventListener('mousedown', (e) => {
    spatialViz.isDragging = true;
    spatialViz.lastX = e.clientX;
    spatialViz.lastY = e.clientY;
});
window.addEventListener('mousemove', (e) => {
    if (!spatialViz.isDragging) return;
    spatialViz.rotY += (e.clientX - spatialViz.lastX) * 0.01;
    spatialViz.rotX += (e.clientY - spatialViz.lastY) * 0.01;
    spatialViz.lastX = e.clientX;
    spatialViz.lastY = e.clientY;
    renderSpatialViz();
});
window.addEventListener('mouseup', () => spatialViz.isDragging = false);

// Resize
window.addEventListener('resize', renderViewer);
