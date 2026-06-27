const palette = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#ea580c", "#0891b2", "#be123c", "#4d7c0f"];

const defaultParameters = {
  min_rpm: "400",
  min_clt: "60",
  max_clt: "",
  min_pw: "0.5",
  max_tpsacc: "110",
  min_gego: "",
  max_gego: "",
  authority: "1.0",
  max_sample_correction: "0.25",
  max_cell_change: "0.15",
  min_samples: "3",
  min_cell_weight: "0",
  smoothing_passes: "0",
  smoothing_factor: "0.20",
  afr_0v: "10",
  afr_5v: "20",
  output_decimals: "2",
  distribution: "bilinear",
  out_of_bounds: "skip",
};

let state = {
  log_paths: [],
  ve_path: "",
  afr_path: "",
  output_path: "",
  parameters: { ...defaultParameters },
  graph_log: "",
  graph_variables: [],
  active_tab: "Graphs",
  geometry: "",
};
let currentColumns = [];
let latestGraphPayload = null;
let saveTimer = null;

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function setStatus(message, kind = "") {
  const status = $("status");
  status.textContent = message;
  status.className = `status-line ${kind}`;
}

function debounceSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveState, 250);
}

async function saveState() {
  try {
    await api("/api/state", {
      method: "POST",
      body: JSON.stringify(state),
    });
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

async function loadState() {
  state = await api("/api/state");
  state.parameters = { ...defaultParameters, ...(state.parameters || {}) };
  renderAll();
  setStatus("Session restored.", "status-ok");
  if (state.graph_log && state.graph_variables?.length) {
    await loadVariables({ keepSelection: true });
  }
}

function renderAll() {
  $("vePath").value = state.ve_path || "";
  $("afrPath").value = state.afr_path || "";
  $("outputPath").value = state.output_path || "";
  document.querySelectorAll("[data-param]").forEach((input) => {
    input.value = state.parameters[input.dataset.param] ?? "";
  });
  renderLogList();
  renderGraphLogSelect();
  activateView(state.active_tab || "Graphs", false);
}

function renderLogList() {
  const list = $("logList");
  list.innerHTML = "";
  if (!state.log_paths.length) {
    const empty = document.createElement("div");
    empty.className = "status-line";
    empty.textContent = "No logs added.";
    list.append(empty);
    return;
  }
  state.log_paths.forEach((path) => {
    const row = document.createElement("div");
    row.className = "file-item";
    const name = document.createElement("div");
    name.className = "file-name";
    name.title = path;
    name.textContent = path;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      state.log_paths = state.log_paths.filter((item) => item !== path);
      if (state.graph_log === path) {
        state.graph_log = state.log_paths[0] || "";
        state.graph_variables = [];
        currentColumns = [];
        latestGraphPayload = null;
      }
      renderLogList();
      renderGraphLogSelect();
      renderVariableList();
      renderGraphTracks();
      debounceSave();
    });
    row.append(name, remove);
    list.append(row);
  });
}

function renderGraphLogSelect() {
  const select = $("graphLogSelect");
  select.innerHTML = "";
  state.log_paths.forEach((path) => {
    const option = document.createElement("option");
    option.value = path;
    option.textContent = path;
    select.append(option);
  });
  if (!state.graph_log || !state.log_paths.includes(state.graph_log)) {
    state.graph_log = state.log_paths[0] || "";
  }
  select.value = state.graph_log;
}

function renderVariableList() {
  const list = $("variableList");
  const filter = $("variableFilter").value.trim().toLowerCase();
  list.innerHTML = "";
  const visibleColumns = currentColumns.filter((column) => column.toLowerCase().includes(filter));
  if (!visibleColumns.length) {
    const empty = document.createElement("div");
    empty.className = "status-line";
    empty.textContent = currentColumns.length ? "No matching variables." : "Load variables for a log.";
    list.append(empty);
    return;
  }
  visibleColumns.forEach((column) => {
    const label = document.createElement("label");
    label.className = "variable-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.graph_variables.includes(column);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.graph_variables = [...new Set([...state.graph_variables, column])];
      } else {
        state.graph_variables = state.graph_variables.filter((item) => item !== column);
      }
      debounceSave();
      drawSelectedVariables();
    });
    const text = document.createElement("span");
    text.textContent = column;
    label.append(checkbox, text);
    list.append(label);
  });
}

function activateView(viewName, persist = true) {
  const viewMap = {
    Graphs: "graphsView",
    Analyse: "analyseView",
    Results: "resultsView",
  };
  const targetId = viewMap[viewName] || viewName;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === targetId);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === targetId);
  });
  if (persist) {
    state.active_tab = Object.entries(viewMap).find(([, id]) => id === targetId)?.[0] || "Graphs";
    debounceSave();
  }
}

async function loadVariables({ keepSelection = false } = {}) {
  if (!state.graph_log) {
    setStatus("Add a log before loading variables.", "status-error");
    return;
  }
  try {
    const metadata = await api(`/api/log?path=${encodeURIComponent(state.graph_log)}`);
    currentColumns = metadata.numeric_columns || [];
    if (!keepSelection) {
      const preferred = new Set(["RPM", "MAP", "O2", "PW", "Spark Angle"]);
      state.graph_variables = currentColumns.filter((column) => preferred.has(column));
    } else {
      state.graph_variables = state.graph_variables.filter((column) => currentColumns.includes(column));
    }
    renderVariableList();
    setStatus(`${metadata.row_count} rows loaded from ${state.graph_log}.`, "status-ok");
    debounceSave();
    await drawSelectedVariables();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

async function drawSelectedVariables() {
  if (!state.graph_log || !state.graph_variables.length) {
    latestGraphPayload = null;
    renderGraphTracks();
    return;
  }
  try {
    latestGraphPayload = await api("/api/graph", {
      method: "POST",
      body: JSON.stringify({
        path: state.graph_log,
        variables: state.graph_variables,
        max_points_per_series: Number($("maxGraphPoints").value || 2500),
      }),
    });
    renderGraphTracks();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

function renderGraphTracks() {
  const tracks = $("graphTracks");
  const summary = $("graphSummary");
  tracks.innerHTML = "";
  if (!latestGraphPayload || !latestGraphPayload.series?.length) {
    summary.textContent = "Select variables to create stacked graph tracks.";
    return;
  }
  const count = latestGraphPayload.series.length;
  const rows = latestGraphPayload.row_count;
  summary.textContent = `${count} stacked tracks from ${rows} log rows.`;
  latestGraphPayload.series.forEach((series, index) => {
    const track = document.createElement("article");
    track.className = "track";
    const header = document.createElement("div");
    header.className = "track-header";
    const title = document.createElement("div");
    title.className = "track-title";
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = palette[index % palette.length];
    const name = document.createElement("span");
    name.textContent = series.name;
    title.append(swatch, name);
    const range = document.createElement("div");
    range.className = "track-range";
    range.textContent = `${formatNumber(series.minimum)} to ${formatNumber(series.maximum)}`;
    header.append(title, range);
    const canvas = document.createElement("canvas");
    const readout = document.createElement("div");
    readout.className = "track-readout";
    readout.style.padding = "0 12px 9px";
    readout.textContent = "Move over the graph for a value.";
    track.append(header, canvas, readout);
    tracks.append(track);
    drawTrack(canvas, series, latestGraphPayload.x_min, latestGraphPayload.x_max, palette[index % palette.length], readout);
  });
}

function drawTrack(canvas, series, xMin, xMax, color, readout) {
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(140, Math.floor(rect.height));
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const padLeft = 54;
  const padRight = 14;
  const padTop = 12;
  const padBottom = 24;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const yMin = series.minimum;
  const yMax = series.maximum === series.minimum ? series.minimum + 1 : series.maximum;
  const xSpan = xMax === xMin ? 1 : xMax - xMin;

  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d7dde5";
  ctx.strokeRect(padLeft, padTop, plotWidth, plotHeight);

  ctx.strokeStyle = "#edf0f4";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i += 1) {
    const y = padTop + (plotHeight * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(padLeft + plotWidth, y);
    ctx.stroke();
  }

  ctx.fillStyle = "#647083";
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "right";
  ctx.fillText(formatNumber(yMax), padLeft - 8, padTop + 4);
  ctx.fillText(formatNumber(yMin), padLeft - 8, padTop + plotHeight);
  ctx.textAlign = "center";
  ctx.fillText(formatNumber(xMin), padLeft, height - 7);
  ctx.fillText(formatNumber(xMax), padLeft + plotWidth, height - 7);

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  series.points.forEach(([time, value], index) => {
    const x = padLeft + ((time - xMin) / xSpan) * plotWidth;
    const y = padTop + (1 - (value - yMin) / (yMax - yMin)) * plotHeight;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  canvas.onmousemove = (event) => {
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const time = xMin + ((x - padLeft) / plotWidth) * xSpan;
    const nearest = nearestPoint(series.points, time);
    readout.textContent = `t=${formatNumber(nearest[0])}, ${series.name}=${formatNumber(nearest[1])}`;
  };
  canvas.onmouseleave = () => {
    readout.textContent = "Move over the graph for a value.";
  };
}

function nearestPoint(points, time) {
  if (!points.length) {
    return [0, 0];
  }
  let best = points[0];
  let bestDistance = Math.abs(best[0] - time);
  for (const point of points) {
    const distance = Math.abs(point[0] - time);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

async function runAnalyse() {
  collectFormState();
  setStatus("Running VE analysis...");
  try {
    const result = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify(state),
    });
    $("resultSummary").textContent = `${result.summary_text}\nWrote: ${result.output_path}`;
    renderUpdates(result.updates || []);
    activateView("Results");
    setStatus("Analysis complete.", "status-ok");
    await saveState();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

function renderUpdates(updates) {
  const body = $("updatesBody");
  body.innerHTML = "";
  updates.forEach((update) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${formatNumber(update.rpm)}</td>
      <td>${formatNumber(update.load)}</td>
      <td>${formatNumber(update.old_ve)}</td>
      <td>${formatNumber(update.new_ve)}</td>
      <td>${formatNumber(update.delta_percent)}%</td>
      <td>${update.samples}</td>
    `;
    body.append(row);
  });
}

function collectFormState() {
  state.ve_path = $("vePath").value.trim();
  state.afr_path = $("afrPath").value.trim();
  state.output_path = $("outputPath").value.trim();
  document.querySelectorAll("[data-param]").forEach((input) => {
    state.parameters[input.dataset.param] = input.value;
  });
}

function addLogPath(path) {
  const cleaned = path.trim();
  if (!cleaned) {
    return;
  }
  if (!state.log_paths.includes(cleaned)) {
    state.log_paths.push(cleaned);
  }
  if (!state.graph_log) {
    state.graph_log = cleaned;
  }
  $("logPathInput").value = "";
  renderLogList();
  renderGraphLogSelect();
  debounceSave();
}

function useExampleData() {
  addLogPath("examples/example.msl");
  state.graph_log = "examples/example.msl";
  state.graph_variables = [];
  state.ve_path = "examples/ve.tsv";
  state.afr_path = "examples/afr.tsv";
  state.output_path = "examples/ve-new.csv";
  currentColumns = [];
  latestGraphPayload = null;
  renderAll();
  renderVariableList();
  renderGraphTracks();
  debounceSave();
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "";
  }
  if (Math.abs(number) >= 1000) {
    return number.toFixed(0);
  }
  if (Math.abs(number) >= 10) {
    return number.toFixed(1).replace(/\.0$/, "");
  }
  return number.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function wireEvents() {
  $("addLog").addEventListener("click", () => addLogPath($("logPathInput").value));
  $("logPathInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      addLogPath(event.currentTarget.value);
    }
  });
  $("useExample").addEventListener("click", useExampleData);
  ["vePath", "afrPath", "outputPath"].forEach((id) => {
    $(id).addEventListener("input", () => {
      collectFormState();
      debounceSave();
    });
  });
  document.querySelectorAll("[data-param]").forEach((input) => {
    input.addEventListener("input", () => {
      collectFormState();
      debounceSave();
    });
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => activateView(button.dataset.view));
  });
  $("graphLogSelect").addEventListener("change", (event) => {
    state.graph_log = event.currentTarget.value;
    state.graph_variables = [];
    currentColumns = [];
    latestGraphPayload = null;
    renderVariableList();
    renderGraphTracks();
    debounceSave();
  });
  $("loadVariables").addEventListener("click", () => loadVariables());
  $("variableFilter").addEventListener("input", renderVariableList);
  $("maxGraphPoints").addEventListener("change", drawSelectedVariables);
  $("runAnalyse").addEventListener("click", runAnalyse);
  window.addEventListener("resize", () => {
    if (latestGraphPayload) {
      renderGraphTracks();
    }
  });
}

wireEvents();
loadState().catch((error) => setStatus(error.message, "status-error"));
