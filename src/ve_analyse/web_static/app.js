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
  graph_groups: [],
  active_graph_id: "",
  graph_zoom: {},
  active_tab: "Graphs",
  geometry: "",
};
let currentColumns = [];
let latestGraphPayload = null;
let saveTimer = null;
let dragZoom = null;

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
    state.graph_variables = uniqueVariablesFromGroups();
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
  normalizeState();
  renderAll();
  setStatus("Session restored.", "status-ok");
  if (state.graph_log && uniqueVariablesFromGroups().length) {
    await loadVariables({ keepSelection: true });
  }
}

function normalizeState() {
  state.parameters = { ...defaultParameters, ...(state.parameters || {}) };
  state.log_paths = Array.isArray(state.log_paths) ? state.log_paths : [];
  state.graph_variables = Array.isArray(state.graph_variables) ? state.graph_variables : [];
  state.graph_groups = Array.isArray(state.graph_groups) ? state.graph_groups : [];
  state.graph_zoom = state.graph_zoom && typeof state.graph_zoom === "object" ? state.graph_zoom : {};

  state.graph_groups = state.graph_groups
    .filter((group) => group && typeof group === "object")
    .map((group, index) => ({
      id: String(group.id || makeGraphId()),
      name: String(group.name || `Graph ${index + 1}`),
      variables: Array.isArray(group.variables) ? group.variables.filter((item) => typeof item === "string") : [],
    }));

  if (!state.graph_groups.length) {
    state.graph_groups = [
      {
        id: makeGraphId(),
        name: "Graph 1",
        variables: [...new Set(state.graph_variables)],
      },
    ];
  }
  if (!state.graph_groups.some((group) => group.id === state.active_graph_id)) {
    state.active_graph_id = state.graph_groups[0].id;
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
  renderGraphGroupList();
  renderVariableList();
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
        resetGraphData();
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

function renderGraphGroupList() {
  const list = $("graphGroupList");
  list.innerHTML = "";
  state.graph_groups.forEach((group) => {
    const row = document.createElement("div");
    row.className = `graph-group${group.id === state.active_graph_id ? " active" : ""}`;
    const main = document.createElement("div");
    main.className = "graph-group-main";
    const name = document.createElement("input");
    name.className = "graph-group-name";
    name.value = group.name;
    name.addEventListener("focus", () => selectGraphGroup(group.id));
    name.addEventListener("input", () => {
      group.name = name.value || "Graph";
      renderGraphTracks();
      debounceSave();
    });
    const meta = document.createElement("div");
    meta.className = "graph-group-meta";
    meta.textContent = `${group.variables.length} variable${group.variables.length === 1 ? "" : "s"}`;
    main.append(name, meta);

    const actions = document.createElement("div");
    actions.className = "graph-group-actions";
    const select = document.createElement("button");
    select.type = "button";
    select.textContent = "Select";
    select.addEventListener("click", () => selectGraphGroup(group.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.disabled = state.graph_groups.length <= 1;
    remove.addEventListener("click", () => removeGraphGroup(group.id));
    actions.append(select, remove);
    row.append(main, actions);
    list.append(row);
  });
}

function renderVariableList() {
  const list = $("variableList");
  const active = activeGraphGroup();
  $("activeGraphLabel").textContent = active ? `Assign variables to ${active.name}.` : "Select a graph.";
  const filter = $("variableFilter").value.trim().toLowerCase();
  list.innerHTML = "";
  const visibleColumns = currentColumns.filter((column) => column.toLowerCase().includes(filter));
  if (!active) {
    const empty = document.createElement("div");
    empty.className = "status-line";
    empty.textContent = "Select or add a graph.";
    list.append(empty);
    return;
  }
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
    checkbox.checked = active.variables.includes(column);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        active.variables = [...new Set([...active.variables, column])];
      } else {
        active.variables = active.variables.filter((item) => item !== column);
      }
      state.graph_variables = uniqueVariablesFromGroups();
      renderGraphGroupList();
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
    state.graph_groups.forEach((group) => {
      group.variables = group.variables.filter((column) => currentColumns.includes(column));
    });
    if (!keepSelection && !uniqueVariablesFromGroups().length) {
      const preferred = new Set(["RPM", "MAP", "O2", "PW", "Spark Angle"]);
      activeGraphGroup().variables = currentColumns.filter((column) => preferred.has(column));
    }
    state.graph_variables = uniqueVariablesFromGroups();
    renderGraphGroupList();
    renderVariableList();
    setStatus(`${metadata.row_count} rows loaded from ${state.graph_log}.`, "status-ok");
    debounceSave();
    await drawSelectedVariables();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

async function drawSelectedVariables() {
  const variables = uniqueVariablesFromGroups();
  if (!state.graph_log || !variables.length) {
    latestGraphPayload = null;
    renderGraphTracks();
    return;
  }
  try {
    latestGraphPayload = await api("/api/graph", {
      method: "POST",
      body: JSON.stringify({
        path: state.graph_log,
        variables,
        max_points_per_series: Number($("maxGraphPoints").value || 2500),
      }),
    });
    clampZoomToPayload();
    renderGraphTracks();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

function renderGraphTracks() {
  const tracks = $("graphTracks");
  const summary = $("graphSummary");
  const zoomSummary = $("zoomSummary");
  tracks.innerHTML = "";
  updateZoomSummary();

  if (!latestGraphPayload || !latestGraphPayload.series?.length) {
    summary.textContent = "Select variables on one or more graphs to draw tracks.";
    zoomSummary.textContent = "Full time range.";
    return;
  }

  const seriesByName = new Map(latestGraphPayload.series.map((series) => [series.name, series]));
  const groupsToDraw = state.graph_groups
    .map((group) => ({
      group,
      series: group.variables.map((variable) => seriesByName.get(variable)).filter(Boolean),
    }))
    .filter((item) => item.series.length);

  summary.textContent = `${groupsToDraw.length} graph${groupsToDraw.length === 1 ? "" : "s"} from ${latestGraphPayload.row_count} log rows.`;
  if (!groupsToDraw.length) {
    summary.textContent = "Add variables to a graph to draw it.";
    return;
  }

  const [xMin, xMax] = visibleXRange();
  groupsToDraw.forEach(({ group, series }, groupIndex) => {
    const track = document.createElement("article");
    track.className = "track";
    const header = document.createElement("div");
    header.className = "track-header";
    const title = document.createElement("div");
    title.className = "track-title";
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = palette[groupIndex % palette.length];
    const name = document.createElement("span");
    name.textContent = group.name;
    title.append(swatch, name);
    const range = document.createElement("div");
    range.className = "track-range";
    range.textContent = `${series.length} variable${series.length === 1 ? "" : "s"}`;
    header.append(title, range);

    const legend = document.createElement("div");
    legend.className = "track-legend";
    series.forEach((item, seriesIndex) => {
      const legendItem = document.createElement("span");
      legendItem.className = "legend-item";
      const dot = document.createElement("span");
      dot.className = "swatch";
      dot.style.background = palette[seriesIndex % palette.length];
      const text = document.createElement("span");
      text.textContent = `${item.name}: ${formatNumber(item.minimum)} to ${formatNumber(item.maximum)}`;
      legendItem.append(dot, text);
      legend.append(legendItem);
    });

    const canvas = document.createElement("canvas");
    const readout = document.createElement("div");
    readout.className = "track-readout";
    readout.style.padding = "0 12px 9px";
    readout.textContent = "Wheel to zoom X. Drag across a time range to zoom in.";
    track.append(header, legend, canvas, readout);
    tracks.append(track);
    drawTrack(canvas, series, xMin, xMax, readout);
  });
}

function drawTrack(canvas, seriesList, xMin, xMax, readout) {
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(160, Math.floor(rect.height));
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  drawTrackCanvas(ctx, width, height, seriesList, xMin, xMax, null);

  canvas.onwheel = (event) => {
    event.preventDefault();
    const plot = plotMetrics(width, height);
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const anchor = xToTime(x, plot, xMin, xMax);
    zoomAround(anchor, event.deltaY < 0 ? 0.55 : 1.65);
  };

  canvas.onmousedown = (event) => {
    const bounds = canvas.getBoundingClientRect();
    dragZoom = {
      canvas,
      readout,
      startX: event.clientX - bounds.left,
      currentX: event.clientX - bounds.left,
      seriesList,
      xMin,
      xMax,
      width,
      height,
    };
  };

  canvas.onmousemove = (event) => {
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const plot = plotMetrics(width, height);
    const time = xToTime(x, plot, xMin, xMax);
    if (dragZoom?.canvas === canvas) {
      dragZoom.currentX = x;
      drawTrackCanvas(ctx, width, height, seriesList, xMin, xMax, [dragZoom.startX, dragZoom.currentX]);
      readout.textContent = `Zoom range: ${formatNumber(xToTime(dragZoom.startX, plot, xMin, xMax))} to ${formatNumber(time)}`;
      return;
    }
    readout.textContent = readoutForTime(seriesList, time);
  };

  canvas.onmouseup = (event) => {
    if (!dragZoom || dragZoom.canvas !== canvas) {
      return;
    }
    const bounds = canvas.getBoundingClientRect();
    const endX = event.clientX - bounds.left;
    const startX = dragZoom.startX;
    dragZoom = null;
    drawTrackCanvas(ctx, width, height, seriesList, xMin, xMax, null);
    if (Math.abs(endX - startX) < 8) {
      return;
    }
    const plot = plotMetrics(width, height);
    const first = xToTime(startX, plot, xMin, xMax);
    const second = xToTime(endX, plot, xMin, xMax);
    setZoomRange(Math.min(first, second), Math.max(first, second));
  };

  canvas.onmouseleave = () => {
    if (dragZoom?.canvas === canvas) {
      dragZoom = null;
      drawTrackCanvas(ctx, width, height, seriesList, xMin, xMax, null);
    }
    readout.textContent = "Wheel to zoom X. Drag across a time range to zoom in.";
  };
}

function drawTrackCanvas(ctx, width, height, seriesList, xMin, xMax, selection) {
  const plot = plotMetrics(width, height);
  const xSpan = xMax === xMin ? 1 : xMax - xMin;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d7dde5";
  ctx.strokeRect(plot.left, plot.top, plot.width, plot.height);

  ctx.strokeStyle = "#edf0f4";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i += 1) {
    const y = plot.top + (plot.height * i) / 4;
    ctx.beginPath();
    ctx.moveTo(plot.left, y);
    ctx.lineTo(plot.left + plot.width, y);
    ctx.stroke();
  }

  ctx.fillStyle = "#647083";
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("100%", plot.left - 8, plot.top + 4);
  ctx.fillText("0%", plot.left - 8, plot.top + plot.height);
  ctx.textAlign = "center";
  ctx.fillText(formatNumber(xMin), plot.left, height - 7);
  ctx.fillText(formatNumber(xMax), plot.left + plot.width, height - 7);

  seriesList.forEach((series, index) => {
    const yMin = series.minimum;
    const yMax = series.maximum === series.minimum ? series.minimum + 1 : series.maximum;
    ctx.strokeStyle = palette[index % palette.length];
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    series.points.forEach(([time, value]) => {
      if (time < xMin || time > xMax) {
        return;
      }
      const x = plot.left + ((time - xMin) / xSpan) * plot.width;
      const y = plot.top + (1 - (value - yMin) / (yMax - yMin)) * plot.height;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    if (started) {
      ctx.stroke();
    }
  });

  if (selection) {
    const left = Math.max(plot.left, Math.min(selection[0], selection[1]));
    const right = Math.min(plot.left + plot.width, Math.max(selection[0], selection[1]));
    ctx.fillStyle = "rgba(37, 99, 235, 0.14)";
    ctx.fillRect(left, plot.top, Math.max(0, right - left), plot.height);
    ctx.strokeStyle = "rgba(37, 99, 235, 0.85)";
    ctx.strokeRect(left, plot.top, Math.max(0, right - left), plot.height);
  }
}

function plotMetrics(width, height) {
  const left = 54;
  const right = 14;
  const top = 12;
  const bottom = 24;
  return {
    left,
    top,
    width: width - left - right,
    height: height - top - bottom,
  };
}

function xToTime(x, plot, xMin, xMax) {
  const clamped = Math.min(plot.left + plot.width, Math.max(plot.left, x));
  return xMin + ((clamped - plot.left) / plot.width) * (xMax - xMin);
}

function readoutForTime(seriesList, time) {
  const values = seriesList.map((series) => {
    const nearest = nearestPoint(series.points, time);
    return `${series.name}=${formatNumber(nearest[1])}`;
  });
  return `t=${formatNumber(time)} | ${values.join(" | ")}`;
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

function fullXRange() {
  if (!latestGraphPayload) {
    return [0, 1];
  }
  const min = Number(latestGraphPayload.x_min);
  const max = Number(latestGraphPayload.x_max);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return [0, 1];
  }
  return [min, max];
}

function visibleXRange() {
  const [fullMin, fullMax] = fullXRange();
  const xMin = Number(state.graph_zoom?.x_min);
  const xMax = Number(state.graph_zoom?.x_max);
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax) || xMax <= xMin) {
    return [fullMin, fullMax];
  }
  return [Math.max(fullMin, xMin), Math.min(fullMax, xMax)];
}

function setZoomRange(xMin, xMax) {
  const [fullMin, fullMax] = fullXRange();
  const fullSpan = fullMax - fullMin;
  const minSpan = Math.max(fullSpan * 0.002, 0.001);
  let nextMin = Math.max(fullMin, Math.min(fullMax, xMin));
  let nextMax = Math.max(fullMin, Math.min(fullMax, xMax));
  if (nextMax - nextMin < minSpan) {
    const center = (nextMin + nextMax) / 2;
    nextMin = center - minSpan / 2;
    nextMax = center + minSpan / 2;
  }
  if (nextMin < fullMin) {
    nextMax += fullMin - nextMin;
    nextMin = fullMin;
  }
  if (nextMax > fullMax) {
    nextMin -= nextMax - fullMax;
    nextMax = fullMax;
  }
  state.graph_zoom = { x_min: nextMin, x_max: nextMax };
  renderGraphTracks();
  debounceSave();
}

function zoomAround(anchor, factor) {
  const [xMin, xMax] = visibleXRange();
  const span = xMax - xMin;
  const nextSpan = span * factor;
  const leftRatio = span === 0 ? 0.5 : (anchor - xMin) / span;
  const nextMin = anchor - nextSpan * leftRatio;
  const nextMax = nextMin + nextSpan;
  setZoomRange(nextMin, nextMax);
}

function zoomOut() {
  const [xMin, xMax] = visibleXRange();
  const center = (xMin + xMax) / 2;
  const span = (xMax - xMin) * 2;
  setZoomRange(center - span / 2, center + span / 2);
}

function resetZoom() {
  state.graph_zoom = {};
  renderGraphTracks();
  debounceSave();
}

function clampZoomToPayload() {
  const xMin = Number(state.graph_zoom?.x_min);
  const xMax = Number(state.graph_zoom?.x_max);
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax)) {
    return;
  }
  const [fullMin, fullMax] = fullXRange();
  if (xMax <= fullMin || xMin >= fullMax) {
    state.graph_zoom = {};
  }
}

function updateZoomSummary() {
  const zoomSummary = $("zoomSummary");
  if (!latestGraphPayload) {
    zoomSummary.textContent = "Full time range.";
    return;
  }
  const [fullMin, fullMax] = fullXRange();
  const [xMin, xMax] = visibleXRange();
  const isFull = Math.abs(xMin - fullMin) < 0.000001 && Math.abs(xMax - fullMax) < 0.000001;
  zoomSummary.textContent = isFull
    ? `Full time range: ${formatNumber(fullMin)} to ${formatNumber(fullMax)}.`
    : `Zoomed time range: ${formatNumber(xMin)} to ${formatNumber(xMax)}.`;
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
    renderVeTables(result.tables);
    renderUpdates(result.updates || []);
    activateView("Results");
    setStatus("Analysis complete.", "status-ok");
    await saveState();
  } catch (error) {
    setStatus(error.message, "status-error");
  }
}

function renderVeTables(tables) {
  const container = $("veTables");
  container.innerHTML = "";
  if (!tables?.old || !tables?.new) {
    return;
  }

  const allValues = [...flattenTableValues(tables.old), ...flattenTableValues(tables.new)];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  container.append(
    buildVeTableCard("Old VE Table", tables.old, min, max),
    buildVeTableCard("New VE Table", tables.new, min, max),
  );
}

function buildVeTableCard(title, table, min, max) {
  const card = document.createElement("section");
  card.className = "ve-table-card";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const wrap = document.createElement("div");
  wrap.className = "ve-grid-wrap";
  const grid = document.createElement("table");
  grid.className = "ve-grid";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const corner = document.createElement("th");
  corner.className = "axis-corner";
  corner.textContent = `${table.y_label || "MAP"}/${table.x_label || "RPM"}`;
  headerRow.append(corner);
  table.x_bins.forEach((rpm) => {
    const th = document.createElement("th");
    th.textContent = formatAxis(rpm);
    headerRow.append(th);
  });
  thead.append(headerRow);

  const tbody = document.createElement("tbody");
  table.y_bins.forEach((mapValue, rowIndex) => {
    const row = document.createElement("tr");
    const axis = document.createElement("th");
    axis.className = "y-axis";
    axis.textContent = formatAxis(mapValue);
    row.append(axis);
    table.values[rowIndex].forEach((value) => {
      const cell = document.createElement("td");
      cell.className = "ve-cell";
      cell.textContent = formatNumber(value);
      cell.style.backgroundColor = veCellColor(value, min, max);
      row.append(cell);
    });
    tbody.append(row);
  });

  grid.append(thead, tbody);
  wrap.append(grid);
  card.append(heading, wrap);
  return card;
}

function flattenTableValues(table) {
  return (table.values || [])
    .flat()
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
}

function veCellColor(value, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number) || !Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return "hsl(95, 58%, 72%)";
  }
  const ratio = Math.max(0, Math.min(1, (number - min) / (max - min)));
  const hue = 120 - ratio * 120;
  const lightness = 78 - ratio * 12;
  return `hsl(${hue}, 64%, ${lightness}%)`;
}

function formatAxis(value) {
  const number = Number(value);
  if (Number.isFinite(number) && Number.isInteger(number)) {
    return String(number);
  }
  return formatNumber(value);
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
  state.graph_groups = [
    { id: makeGraphId(), name: "Engine speed/load", variables: ["RPM", "MAP"] },
    { id: makeGraphId(), name: "Fueling", variables: ["O2", "PW"] },
  ];
  state.active_graph_id = state.graph_groups[0].id;
  state.graph_variables = uniqueVariablesFromGroups();
  state.graph_zoom = {};
  state.ve_path = "examples/ve.tsv";
  state.afr_path = "examples/afr.tsv";
  state.output_path = "examples/ve-new.csv";
  currentColumns = [];
  latestGraphPayload = null;
  renderAll();
  renderGraphTracks();
  debounceSave();
}

function addGraphGroup() {
  const nextNumber = state.graph_groups.length + 1;
  const group = {
    id: makeGraphId(),
    name: `Graph ${nextNumber}`,
    variables: [],
  };
  state.graph_groups.push(group);
  state.active_graph_id = group.id;
  renderGraphGroupList();
  renderVariableList();
  renderGraphTracks();
  debounceSave();
}

function removeGraphGroup(id) {
  if (state.graph_groups.length <= 1) {
    return;
  }
  state.graph_groups = state.graph_groups.filter((group) => group.id !== id);
  if (!state.graph_groups.some((group) => group.id === state.active_graph_id)) {
    state.active_graph_id = state.graph_groups[0].id;
  }
  state.graph_variables = uniqueVariablesFromGroups();
  renderGraphGroupList();
  renderVariableList();
  drawSelectedVariables();
  debounceSave();
}

function selectGraphGroup(id) {
  state.active_graph_id = id;
  renderGraphGroupList();
  renderVariableList();
  debounceSave();
}

function activeGraphGroup() {
  return state.graph_groups.find((group) => group.id === state.active_graph_id) || state.graph_groups[0] || null;
}

function resetGraphData() {
  currentColumns = [];
  latestGraphPayload = null;
  state.graph_groups.forEach((group) => {
    group.variables = [];
  });
  state.graph_variables = [];
  state.graph_zoom = {};
}

function uniqueVariablesFromGroups() {
  return [...new Set(state.graph_groups.flatMap((group) => group.variables || []))];
}

function makeGraphId() {
  return `graph-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
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
    resetGraphData();
    renderVariableList();
    renderGraphGroupList();
    renderGraphTracks();
    debounceSave();
  });
  $("addGraph").addEventListener("click", addGraphGroup);
  $("loadVariables").addEventListener("click", () => loadVariables());
  $("variableFilter").addEventListener("input", renderVariableList);
  $("maxGraphPoints").addEventListener("change", drawSelectedVariables);
  $("zoomOut").addEventListener("click", zoomOut);
  $("resetZoom").addEventListener("click", resetZoom);
  $("runAnalyse").addEventListener("click", runAnalyse);
  window.addEventListener("resize", () => {
    if (latestGraphPayload) {
      renderGraphTracks();
    }
  });
}

wireEvents();
loadState().catch((error) => setStatus(error.message, "status-error"));
