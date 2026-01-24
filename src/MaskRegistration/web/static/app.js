const state = {
    source: { slices: 0, hasMask: false, size: [0, 0], origin: [0, 0, 0], spacing: [1, 1, 1], echos: 1, currentEcho: 0, imageData: null },
    target: {
        slices: 0,
        hasMask: false,
        size: [0, 0],
        origin: [0, 0, 0],
        spacing: [1, 1, 1],
        echos: 1,
        currentEcho: 0,
        imageData: null,
        originalImageData: null,
        manualTransformData: null,
        maskMode: 'off',
        hasRegisteredMask: false,
        hasCustomMask: false
    },
    lastDicomParent: '',
    pan: { x: 0, y: 0, isDragging: false, lastX: 0, lastY: 0, canPan: false },
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
    targetView: 'auto',
    manualTransform: {
        offset: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0 },
        scale: { x: 1, y: 1, z: 1 },
        applyOffset: false,
        applyRotation: false,
        applyScale: false,
        active: false,
        userEdited: false
    }
};

let sliceUpdateTimeout = null;
function isTargetAligned() {
    return state.targetView === 'auto';
}

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
    // Only sync sliders when target view is auto-aligned.
    if (!isTargetAligned()) return;

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
    const show = state.target.slices > 0;
    document.getElementById('target-slice-control').style.display = show ? 'flex' : 'none';
}

function toggleTransformPanel() {
    const panel = document.getElementById('transform-panel');
    const btn = document.getElementById('transform-toggle');
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'flex';
    btn.classList.toggle('active', !isVisible);
}

function updateTargetViewVisibility() {
    // Show toggle when both DICOMs are loaded
    const show = state.source.slices > 0 && state.target.slices > 0;
    document.getElementById('target-view-control').style.display = show ? 'flex' : 'none';
}

function updateTargetMaskControls() {
    const control = document.getElementById('target-mask-control');
    const hasRegistered = state.target.hasRegisteredMask;
    const hasCustom = state.target.hasCustomMask;
    const show = hasRegistered || hasCustom;
    if (control) control.style.display = show ? 'flex' : 'none';

    if (state.target.maskMode === 'registered' && !hasRegistered) {
        state.target.maskMode = hasCustom ? 'custom' : 'off';
    }
    if (state.target.maskMode === 'custom' && !hasCustom) {
        state.target.maskMode = hasRegistered ? 'registered' : 'off';
    }
    if (!show) state.target.maskMode = 'off';

    document.querySelectorAll('[data-target-mask]').forEach(btn => {
        const mode = btn.dataset.targetMask;
        let enabled = true;
        if (mode === 'registered') enabled = hasRegistered;
        if (mode === 'custom') enabled = hasCustom;
        btn.disabled = !enabled;
        btn.classList.toggle('active', mode === state.target.maskMode);
    });
}

function getTargetMaskQuery() {
    const mode = state.target.maskMode;
    if (mode === 'off') return { mask: false };
    const hasMask = mode === 'custom' ? state.target.hasCustomMask : state.target.hasRegisteredMask;
    if (!hasMask) return { mask: false };
    return { mask: true, maskMode: mode };
}

function getOriginalTargetMaskQuery() {
    if (state.target.hasCustomMask) {
        return { mask: true, maskMode: 'custom' };
    }
    if (state.target.hasRegisteredMask) {
        return { mask: true, maskMode: 'registered' };
    }
    return { mask: false };
}

function setTargetView(view) {
    state.targetView = view;
    document.querySelectorAll('[data-target-view]').forEach(b => {
        b.classList.toggle('active', b.dataset.targetView === view);
    });
}

function resetPan() {
    state.pan.x = 0;
    state.pan.y = 0;
    state.pan.isDragging = false;
    state.pan.canPan = false;
}

function normalizePath(path) {
    return (path || '').trim().replace(/\\/g, '/').replace(/\/+$/, '');
}

function getParentDir(path) {
    const normalized = normalizePath(path);
    if (!normalized) return '';
    const parts = normalized.split('/');
    if (parts.length <= 1) return normalized;
    parts.pop();
    return parts.join('/') || '/';
}

function setLastDicomParent(path) {
    const parent = getParentDir(path);
    if (parent) state.lastDicomParent = parent;
}

function getComputedBaseline() {
    const computed = state.computedTransform || {};
    return {
        offset: computed.offset || [0, 0, 0],
        rotation: computed.rotation || { x: 0, y: 0, z: 0 },
        scale: computed.scale || [1, 1, 1]
    };
}

function resetManualTransformUI() {
    state.manualTransform = {
        offset: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0 },
        scale: { x: 1, y: 1, z: 1 },
        applyOffset: false,
        applyRotation: false,
        applyScale: false,
        active: false,
        userEdited: false
    };

    const checkboxIds = ['apply-offset', 'apply-rotation', 'apply-scale'];
    checkboxIds.forEach(id => {
        const checkbox = document.getElementById(id);
        if (checkbox) checkbox.checked = false;
    });

    const defaults = {
        'offset-x': 0, 'offset-y': 0, 'offset-z': 0,
        'rotation-x': 0, 'rotation-y': 0, 'rotation-z': 0,
        'scale-x': 1, 'scale-y': 1, 'scale-z': 1
    };
    Object.entries(defaults).forEach(([id, value]) => {
        const input = document.getElementById(id);
        if (input) input.value = value;
    });

    syncTransformInputs();
}

function seedManualInputsFromComputed() {
    if (state.manualTransform.userEdited) return;
    const baseline = getComputedBaseline();
    const setValue = (id, value, decimals) => {
        const input = document.getElementById(id);
        if (!input) return;
        const num = Number.isFinite(value) ? value : 0;
        input.value = decimals === null ? num : num.toFixed(decimals);
    };

    setValue('offset-x', baseline.offset[0], 1);
    setValue('offset-y', baseline.offset[1], 1);
    setValue('offset-z', baseline.offset[2], 1);
    setValue('rotation-x', baseline.rotation.x, 1);
    setValue('rotation-y', baseline.rotation.y, 1);
    setValue('rotation-z', baseline.rotation.z, 1);
    setValue('scale-x', baseline.scale[0], 2);
    setValue('scale-y', baseline.scale[1], 2);
    setValue('scale-z', baseline.scale[2], 2);
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
        setLastDicomParent(path);
        resetPan();
        state[side].slices = data.slices;
        state[side].size = data.size;
        state[side].origin = data.origin;
        state[side].spacing = data.spacing;
        state[side].echos = data.echos || 1;
        state[side].currentEcho = 0;
        if (side === 'source') {
            state.source.hasMask = false;
        } else {
            state.target.hasRegisteredMask = false;
            state.target.hasCustomMask = false;
            state.target.maskMode = 'off';
            updateTargetMaskControls();
        }
        resetManualTransformUI();

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
        updateTargetViewVisibility();

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

        if (side === 'source') {
            state.source.hasMask = true;
        } else {
            state.target.hasCustomMask = true;
            state.target.maskMode = 'custom';
            updateTargetMaskControls();
        }
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
        state.target.hasRegisteredMask = true;
        if (state.target.maskMode === 'off') {
            state.target.maskMode = 'registered';
        }
        updateTargetMaskControls();

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

async function resetAll() {
    const confirmed = window.confirm('Reset all loaded data?');
    if (!confirmed) return;
    showStatus('Resetting...', 'info');
    try {
        const res = await fetch('/api/reset', { method: 'POST' });
        if (!res.ok) throw new Error((await res.json()).detail || 'Reset failed');
    } catch (e) {
        showStatus(`Reset error: ${e.message}`, 'error');
        return;
    }
    window.location.reload();
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
    const maskQuery = getTargetMaskQuery();
    const params = new URLSearchParams({
        mask: maskQuery.mask,
        reverse,
        t: Date.now()
    });
    if (maskQuery.maskMode) params.set('mask_mode', maskQuery.maskMode);
    const url = `/api/slice/aligned/${state.currentSlice}?${params}`;
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = url;
    });
}

function applyManualTransform() {
    state.manualTransform.userEdited = true;
    const mt = state.manualTransform;
    mt.offset.x = parseFloat(document.getElementById('offset-x').value) || 0;
    mt.offset.y = parseFloat(document.getElementById('offset-y').value) || 0;
    mt.offset.z = parseFloat(document.getElementById('offset-z').value) || 0;
    mt.rotation.x = parseFloat(document.getElementById('rotation-x').value) || 0;
    mt.rotation.y = parseFloat(document.getElementById('rotation-y').value) || 0;
    mt.rotation.z = parseFloat(document.getElementById('rotation-z').value) || 0;
    mt.scale.x = parseFloat(document.getElementById('scale-x').value) || 1;
    mt.scale.y = parseFloat(document.getElementById('scale-y').value) || 1;
    mt.scale.z = parseFloat(document.getElementById('scale-z').value) || 1;
    mt.applyOffset = document.getElementById('apply-offset').checked;
    mt.applyRotation = document.getElementById('apply-rotation').checked;
    mt.applyScale = document.getElementById('apply-scale').checked;
    const eps = 1e-3;
    const offsetActive = mt.applyOffset &&
        (Math.abs(mt.offset.x) > eps || Math.abs(mt.offset.y) > eps || Math.abs(mt.offset.z) > eps);
    const rotationActive = mt.applyRotation &&
        (Math.abs(mt.rotation.x) > eps || Math.abs(mt.rotation.y) > eps || Math.abs(mt.rotation.z) > eps);
    const scaleActive = mt.applyScale &&
        (Math.abs(mt.scale.x - 1) > eps || Math.abs(mt.scale.y - 1) > eps || Math.abs(mt.scale.z - 1) > eps);
    mt.active = offsetActive || rotationActive || scaleActive;

    if (mt.active && state.targetView === 'auto') {
        setTargetView('manual');
    }

    updateSlice();
}

async function loadTargetOriginal() {
    if (state.target.slices === 0) return null;
    let targetSliceIdx = state.targetSlice;
    // Only sync with source when target view is auto-aligned and not in split mode.
    if (isTargetAligned() && state.mode !== 'split' && state.source.slices > 0) {
        const physZ = state.source.origin[2] + state.currentSlice * state.source.spacing[2];
        targetSliceIdx = Math.round((physZ - state.target.origin[2]) / state.target.spacing[2]);
        targetSliceIdx = Math.max(0, Math.min(state.target.slices - 1, targetSliceIdx));
    }
    if (state.direction === 'reverse') {
        targetSliceIdx = state.target.slices - 1 - targetSliceIdx;
    }
    const maskQuery = state.targetView === 'original'
        ? getOriginalTargetMaskQuery()
        : getTargetMaskQuery();
    const params = new URLSearchParams({
        mask: maskQuery.mask,
        t: Date.now()
    });
    if (maskQuery.maskMode) params.set('mask_mode', maskQuery.maskMode);
    const url = `/api/slice/target/${targetSliceIdx}?${params}`;
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = url;
    });
}

async function loadTargetWithManualTransform() {
    if (state.target.slices === 0) return null;
    if (!state.manualTransform.active || state.targetView !== 'manual') return null;

    const mt = state.manualTransform;
    const reverse = state.direction === 'reverse';
    const sliceIndex = state.targetSlice;
    const maskQuery = getTargetMaskQuery();
    const params = new URLSearchParams({
        mask: maskQuery.mask,
        offset_x: mt.offset.x,
        offset_y: mt.offset.y,
        offset_z: mt.offset.z,
        rotation_x: mt.rotation.x,
        rotation_y: mt.rotation.y,
        rotation_z: mt.rotation.z,
        scale_x: mt.scale.x,
        scale_y: mt.scale.y,
        scale_z: mt.scale.z,
        apply_offset: mt.applyOffset,
        apply_rotation: mt.applyRotation,
        apply_scale: mt.applyScale,
        output: 'target',
        reverse,
        t: Date.now()
    });
    if (maskQuery.maskMode) params.set('mask_mode', maskQuery.maskMode);
    const url = `/api/transform/${sliceIndex}?${params}`;
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
        const [aligned, original, manual] = await Promise.all([
            loadTargetAligned(),
            loadTargetOriginal(),
            loadTargetWithManualTransform()
        ]);
        state.target.imageData = aligned || original;
        state.target.originalImageData = original;
        state.target.manualTransformData = manual;
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

    const [sourceImg, targetAligned, targetOriginal, targetManual] = await Promise.all([
        loadSourceImage(),
        loadTargetAligned(),
        loadTargetOriginal(),
        loadTargetWithManualTransform()
    ]);

    state.source.imageData = sourceImg;
    state.target.imageData = targetAligned || targetOriginal;
    state.target.originalImageData = targetOriginal;
    state.target.manualTransformData = targetManual;

    document.getElementById('viewer-placeholder').classList.toggle('hidden', sourceImg || targetAligned || targetOriginal);
    renderViewer();
}

function renderViewer() {
    const container = document.getElementById('viewer-container');
    const sourceCanvas = document.getElementById('source-canvas');
    const targetCanvas = document.getElementById('target-canvas');
    const curtain = document.getElementById('curtain');

    const sourceImg = state.source.imageData;
    // Determine which target image to use:
    // - Manual view: use transformed (fallback to original)
    // - Auto view: use auto-aligned
    // - Original view: use original (native grid)
    let targetImg;
    if (state.targetView === 'manual') {
        targetImg = state.target.manualTransformData || state.target.originalImageData;
    } else if (state.targetView === 'auto') {
        targetImg = state.target.imageData;
    } else {
        targetImg = state.target.originalImageData;
    }

    if (!sourceImg && !targetImg) {
        state.pan.canPan = false;
        container.style.cursor = 'default';
        return;
    }

    const containerW = container.clientWidth;
    const containerH = container.clientHeight;

    if (state.mode === 'split') {
        curtain.style.display = 'none';
        container.classList.add('split-mode');

        const gap = 24;
        const paneW = Math.max(1, Math.floor((containerW - gap) / 2));
        const paneH = containerH;

        const getSplitMetrics = (img) => {
            if (!img) return null;
            const scale = Math.min(paneW / img.width, paneH / img.height) * state.zoom;
            const w = Math.floor(img.width * scale);
            const h = Math.floor(img.height * scale);
            const maxPanX = Math.max(0, (w - paneW) / 2);
            const maxPanY = Math.max(0, (h - paneH) / 2);
            return { w, h, maxPanX, maxPanY };
        };

        const sourceMetrics = getSplitMetrics(sourceImg);
        const targetMetrics = getSplitMetrics(targetImg);
        const metricsList = [sourceMetrics, targetMetrics].filter(Boolean);
        const maxPanX = metricsList.length ? Math.min(...metricsList.map(m => m.maxPanX)) : 0;
        const maxPanY = metricsList.length ? Math.min(...metricsList.map(m => m.maxPanY)) : 0;
        state.pan.x = Math.min(maxPanX, Math.max(-maxPanX, state.pan.x));
        state.pan.y = Math.min(maxPanY, Math.max(-maxPanY, state.pan.y));
        const canPan = maxPanX > 0 || maxPanY > 0;
        state.pan.canPan = canPan;
        container.style.cursor = state.pan.isDragging ? 'grabbing' : (canPan ? 'grab' : 'default');

        const renderSplit = (canvas, img, metrics) => {
            if (!img || !metrics) {
                canvas.style.display = 'none';
                return;
            }
            canvas.style.display = 'block';
            canvas.style.position = 'relative';
            canvas.style.left = '0';
            canvas.style.top = '0';
            canvas.width = paneW;
            canvas.height = paneH;
            canvas.style.width = paneW + 'px';
            canvas.style.height = paneH + 'px';
            canvas.style.clipPath = 'none';
            canvas.style.opacity = 1;
            const offsetX = Math.round((paneW - metrics.w) / 2 + state.pan.x);
            const offsetY = Math.round((paneH - metrics.h) / 2 + state.pan.y);
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, paneW, paneH);
            ctx.drawImage(img, offsetX, offsetY, metrics.w, metrics.h);
        };

        renderSplit(sourceCanvas, sourceImg, sourceMetrics);
        renderSplit(targetCanvas, targetImg, targetMetrics);

        return;
    }

    container.classList.remove('split-mode');
    sourceCanvas.style.position = 'absolute';
    targetCanvas.style.position = 'absolute';

    const baseImg = state.mode === 'target' ? (targetImg || sourceImg) : (sourceImg || targetImg);
    if (!baseImg) return;
    const baseW = baseImg.width;
    const baseH = baseImg.height;
    const displayScale = Math.min(containerW / baseW, containerH / baseH) * state.zoom;

    const w = Math.floor(baseW * displayScale);
    const h = Math.floor(baseH * displayScale);

    const maxPanX = Math.max(0, (w - containerW) / 2);
    const maxPanY = Math.max(0, (h - containerH) / 2);
    state.pan.x = Math.min(maxPanX, Math.max(-maxPanX, state.pan.x));
    state.pan.y = Math.min(maxPanY, Math.max(-maxPanY, state.pan.y));
    const panOffsetX = Math.round((containerW - w) / 2 + state.pan.x);
    const panOffsetY = Math.round((containerH - h) / 2 + state.pan.y);
    const canPan = maxPanX > 0 || maxPanY > 0;
    state.pan.canPan = canPan;
    container.style.cursor = state.pan.isDragging ? 'grabbing' : (canPan ? 'grab' : 'default');

    [sourceCanvas, targetCanvas].forEach(canvas => {
        canvas.style.display = 'block';
        canvas.width = w;
        canvas.height = h;
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';
        canvas.style.left = panOffsetX + 'px';
        canvas.style.top = panOffsetY + 'px';
    });

    const sourceCtx = sourceCanvas.getContext('2d');
    const targetCtx = targetCanvas.getContext('2d');

    sourceCtx.clearRect(0, 0, w, h);
    targetCtx.clearRect(0, 0, w, h);

    if (sourceImg) sourceCtx.drawImage(sourceImg, 0, 0, w, h);
    if (targetImg) {
        const showOriginalOverlay = (state.targetView === 'original' ||
            (state.targetView === 'manual' && !state.manualTransform.active)) &&
            sourceImg &&
            state.mode !== 'target';
        if (showOriginalOverlay) {
            // Map target into source pixel space using origin/spacing (approx, no rotation).
            const sourceSpacingX = state.source.spacing[0] || 1;
            const sourceSpacingY = state.source.spacing[1] || 1;
            const targetSpacingX = state.target.spacing[0] || 1;
            const targetSpacingY = state.target.spacing[1] || 1;
            const offsetX = ((state.target.origin[0] || 0) - (state.source.origin[0] || 0)) / sourceSpacingX;
            const offsetY = ((state.target.origin[1] || 0) - (state.source.origin[1] || 0)) / sourceSpacingY;
            const scaleX = (targetSpacingX / sourceSpacingX) * displayScale;
            const scaleY = (targetSpacingY / sourceSpacingY) * displayScale;
            targetCtx.drawImage(
                targetImg,
                Math.floor(offsetX * displayScale),
                Math.floor(offsetY * displayScale),
                Math.floor(targetImg.width * scaleX),
                Math.floor(targetImg.height * scaleY)
            );
        } else {
            targetCtx.drawImage(targetImg, 0, 0, w, h);
        }
    }

    if (state.mode === 'curtain') {
        curtain.style.display = 'block';
        const pos = state.curtainPos * 100;

        if (state.curtainDir === 'horizontal') {
            sourceCanvas.style.clipPath = `inset(0 ${100 - pos}% 0 0)`;
            targetCanvas.style.clipPath = `inset(0 0 0 ${pos}%)`;
            curtain.style.left = `${Math.round(panOffsetX + state.curtainPos * w)}px`;
            curtain.style.top = `${panOffsetY}px`;
            curtain.style.width = '3px';
            curtain.style.height = `${h}px`;
            curtain.style.cursor = 'ew-resize';
            curtain.style.transform = 'translateX(-50%)';
        } else {
            sourceCanvas.style.clipPath = `inset(0 0 ${100 - pos}% 0)`;
            targetCanvas.style.clipPath = `inset(${pos}% 0 0 0)`;
            curtain.style.left = `${panOffsetX}px`;
            curtain.style.top = `${Math.round(panOffsetY + state.curtainPos * h)}px`;
            curtain.style.width = `${w}px`;
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
    const currentParent = getParentDir(input.value);
    const initialDir = state.lastDicomParent || currentParent;
    try {
        const res = await fetch('/api/browse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, initial_dir: initialDir })
        });
        const data = await res.json();
        if (data.path) {
            input.value = data.path;
            if (mode === 'dir' && (inputId === 'source-dicom-path' || inputId === 'target-dicom-path')) {
                setLastDicomParent(data.path);
            }
        }
    } catch (e) {}
}

async function updateSpatialRelation() {
    if (state.source.slices === 0 || state.target.slices === 0) {
        document.getElementById('spatial-section').style.display = 'none';
        document.getElementById('transform-toggle').style.display = 'none';
        return;
    }

    try {
        const res = await fetch('/api/spatial-relation');
        const data = await res.json();

        document.getElementById('spatial-section').style.display = 'block';
        document.getElementById('transform-toggle').style.display = 'block';

        const status = document.getElementById('spatial-status');
        if (data.error) { status.textContent = 'No Overlap'; status.className = 'error'; }
        else if (data.warning) { status.textContent = 'Low Overlap'; status.className = 'warning'; }
        else { status.textContent = 'OK'; status.className = 'ok'; }

        document.getElementById('overlap-pct').textContent = `${Math.min(data.overlap_pct_source, data.overlap_pct_target)}%`;
        document.getElementById('offset-mm').textContent = `${data.offset_mm.map(v => v.toFixed(1)).join('/')}`;

        // Store and display computed values for reference
        state.computedTransform = {
            offset: data.offset_mm,
            rotation: data.rotation_deg,
            scale: data.spacing_ratio
        };

        // Show computed values as info
        document.getElementById('computed-offset').textContent =
            `Offset ${data.offset_mm.map(v => v.toFixed(1)).join('/')}`;
        if (data.rotation_deg) {
            document.getElementById('computed-rotation').textContent =
                `Rot ${data.rotation_deg.x.toFixed(1)}/${data.rotation_deg.y.toFixed(1)}/${data.rotation_deg.z.toFixed(1)}`;
        }
        if (data.spacing_ratio) {
            document.getElementById('computed-scale').textContent =
                `Scale ${data.spacing_ratio.map(v => v.toFixed(2)).join('/')}`;
        }

        seedManualInputsFromComputed();

        spatialViz.data = data;
        renderSpatialViz();

        if (state.targetView === 'auto') {
            updateSlice();
        }

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

document.getElementById('target-slice-slider').addEventListener('input', (e) => {
    state.targetSlice = parseInt(e.target.value);
    document.getElementById('target-slice-slider-info').textContent = `${state.targetSlice + 1} / ${state.target.slices}`;
    syncSlices('target');
    debouncedUpdateSlice('target');
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

document.querySelectorAll('[data-target-view]').forEach(btn => {
    btn.addEventListener('click', () => {
        setTargetView(btn.dataset.targetView);
        updateSlice();
    });
});

document.querySelectorAll('[data-target-mask]').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        state.target.maskMode = btn.dataset.targetMask;
        updateTargetMaskControls();
        updateSlice();
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

// Pan drag
const viewerContainer = document.getElementById('viewer-container');
viewerContainer.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    if (e.target.closest('#curtain')) return;
    if (!state.pan.canPan) return;
    state.pan.isDragging = true;
    state.pan.lastX = e.clientX;
    state.pan.lastY = e.clientY;
});
window.addEventListener('mousemove', (e) => {
    if (!state.pan.isDragging) return;
    const dx = e.clientX - state.pan.lastX;
    const dy = e.clientY - state.pan.lastY;
    state.pan.lastX = e.clientX;
    state.pan.lastY = e.clientY;
    state.pan.x += dx;
    state.pan.y += dy;
    renderViewer();
});
window.addEventListener('mouseup', () => {
    if (!state.pan.isDragging) return;
    state.pan.isDragging = false;
    renderViewer();
});

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

// Transform controls - live update
const transformGroups = [
    { checkboxId: 'apply-offset', inputs: ['offset-x', 'offset-y', 'offset-z'] },
    { checkboxId: 'apply-rotation', inputs: ['rotation-x', 'rotation-y', 'rotation-z'] },
    { checkboxId: 'apply-scale', inputs: ['scale-x', 'scale-y', 'scale-z'] }
];

function syncTransformInputs() {
    transformGroups.forEach(group => {
        const enabled = document.getElementById(group.checkboxId).checked;
        group.inputs.forEach(id => {
            const input = document.getElementById(id);
            input.disabled = !enabled;
            const field = input.closest('.transform-field');
            if (field) field.classList.toggle('disabled', !enabled);
        });
    });
}

let transformDebounce = null;
function debouncedTransformUpdate() {
    if (transformDebounce) clearTimeout(transformDebounce);
    transformDebounce = setTimeout(applyManualTransform, 150);
}

['apply-offset', 'apply-rotation', 'apply-scale'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => {
        syncTransformInputs();
        applyManualTransform();
    });
});

const transformValueInputs = [
    'offset-x', 'offset-y', 'offset-z',
    'rotation-x', 'rotation-y', 'rotation-z',
    'scale-x', 'scale-y', 'scale-z'
];

function handleTransformValueChange() {
    if (document.getElementById('apply-offset').checked ||
        document.getElementById('apply-rotation').checked ||
        document.getElementById('apply-scale').checked) {
        debouncedTransformUpdate();
    }
}

transformValueInputs.forEach(id => {
    const input = document.getElementById(id);
    input.addEventListener('input', handleTransformValueChange);
    input.addEventListener('change', handleTransformValueChange);
});

syncTransformInputs();
updateTargetMaskControls();
