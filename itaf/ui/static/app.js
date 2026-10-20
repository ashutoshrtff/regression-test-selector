// ITAF Quality Engineering Workspace JavaScript Client

let assessmentsData = [];
let selectedRequirement = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  runAnalysis();
});

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      switchTab(targetId);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const targetPane = document.getElementById(tabId);
  if (targetBtn) targetBtn.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  if (tabId === "screen-e") {
    loadReport();
  }
}

async function runAnalysis() {
  try {
    const res = await fetch("/api/assessments");
    const data = await res.json();
    assessmentsData = data.assessments || [];
    renderSummaryMetrics(data.summary);
    renderRequirementsTable(assessmentsData);
  } catch (err) {
    console.error("Failed to load assessments:", err);
  }
}

function renderSummaryMetrics(summary) {
  if (!summary) return;
  document.getElementById("stat-total-reqs").textContent = summary.total_requirements || 0;
  document.getElementById("stat-covered-reqs").textContent = summary.covered_requirements || 0;
  document.getElementById("stat-covered-pct").textContent = `${summary.coverage_percentage || 0}% covered`;
  document.getElementById("stat-partial-reqs").textContent = summary.partially_covered || 0;
  document.getElementById("stat-missing-reqs").textContent = summary.missing_coverage || 0;
  document.getElementById("stat-failing-gates").textContent = summary.failing_gates_count || 0;

  const alertBanner = document.getElementById("gate-alert-banner");
  if (summary.failing_gates_count > 0) {
    alertBanner.classList.remove("hidden");
    document.getElementById("gate-alert-details").textContent =
      `${summary.failing_gates_count} mandatory policy gate(s) failed across ${summary.missing_coverage} requirements with unmitigated coverage gaps.`;
  } else {
    alertBanner.classList.add("hidden");
  }
}

function renderRequirementsTable(items) {
  const tbody = document.getElementById("requirements-table-body");
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 20px;">No requirements match filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    let statusClass = "badge-neutral";
    if (item.coverage_status === "COVERED") statusClass = "badge-success";
    else if (item.coverage_status === "PARTIALLY_COVERED") statusClass = "badge-warning";
    else if (item.coverage_status === "MISSING_COVERAGE") statusClass = "badge-danger";

    const failingGates = item.failing_gate_ids && item.failing_gate_ids.length > 0
      ? `<span class="badge badge-danger">${item.failing_gate_ids.join(", ")}</span>`
      : `<span class="badge badge-success">0 Failing</span>`;

    const mappedCount = item.mapped_tests ? item.mapped_tests.length : 0;
    const execStatus = item.execution_status || "TEST_NOT_EXECUTED";

    return `
      <tr>
        <td><code>${item.requirement_id}</code></td>
        <td><strong>${item.title}</strong></td>
        <td>${item.domain} / ${item.service}</td>
        <td><span class="badge ${statusClass}">${item.coverage_status}</span></td>
        <td>${failingGates}</td>
        <td>${mappedCount} test(s)</td>
        <td><span class="badge badge-neutral">${execStatus}</span></td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="inspectRequirement('${item.requirement_id}')">Inspect</button>
        </td>
      </tr>
    `;
  }).join("");
}

function applyFilters() {
  const statusFilter = document.getElementById("filter-status").value;
  const domainFilter = document.getElementById("filter-domain").value;
  const searchFilter = document.getElementById("filter-search").value.toLowerCase();

  const filtered = assessmentsData.filter(item => {
    if (statusFilter !== "ALL" && item.coverage_status !== statusFilter) return false;
    if (domainFilter !== "ALL" && item.domain !== domainFilter) return false;
    if (searchFilter) {
      const matchText = (item.requirement_id + " " + item.title + " " + item.service).toLowerCase();
      if (!matchText.includes(searchFilter)) return false;
    }
    return true;
  });

  renderRequirementsTable(filtered);
}

function inspectRequirement(reqId) {
  const req = assessmentsData.find(a => a.requirement_id === reqId);
  if (!req) return;
  selectedRequirement = req;

  document.getElementById("detail-title").textContent = `${req.requirement_id}: ${req.title}`;
  document.getElementById("d-req-id").textContent = req.requirement_id;
  document.getElementById("d-req-type").textContent = req.domain;
  document.getElementById("d-req-interface").textContent = req.service;
  document.getElementById("d-req-mandatory").textContent = "Yes (Mandatory)";
  document.getElementById("d-req-artifact").textContent = "Ingested Spec (Verified Provenance)";
  document.getElementById("d-req-desc").textContent = req.title;

  const gatesContainer = document.getElementById("d-req-gates");
  if (req.assessment_notes && req.assessment_notes.length > 0) {
    gatesContainer.innerHTML = req.assessment_notes.map(note => {
      const isPass = note.startsWith("[PASS]");
      return `<div class="gate-item ${isPass ? 'pass' : 'fail'}">${note}</div>`;
    }).join("");
  } else {
    gatesContainer.innerHTML = `<p style="color:#64748b;">No gate notes recorded.</p>`;
  }

  const testsContainer = document.getElementById("d-req-tests");
  if (req.mapped_tests && req.mapped_tests.length > 0) {
    testsContainer.innerHTML = req.mapped_tests.map(m => `
      <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:10px; margin-bottom:8px;">
        <div><strong>Test ID:</strong> <code>${m.test_id}</code></div>
        <div style="font-size:12px; color:#64748b; margin-top:2px;">
          Confidence: <strong>${m.confidence}</strong> | Source: ${m.mapping_source} | Asserts Outcome: ${m.asserts_outcome ? '✅ Yes' : '⚠️ No (Visits only)'}
        </div>
        <div style="font-size:12px; margin-top:4px;">${m.evidence_summary}</div>
      </div>
    `).join("");
  } else {
    testsContainer.innerHTML = `<p style="color:#ef4444; font-weight:500;">❌ No automated tests currently mapped to this requirement.</p>`;
  }

  const remediationBox = document.getElementById("d-req-remediation-box");
  if (req.suggested_test_scenario) {
    remediationBox.classList.remove("hidden");
    document.getElementById("d-remediation-title").innerHTML = `<strong>${req.suggested_test_scenario.title}</strong>`;
    document.getElementById("d-remediation-steps").innerHTML = req.suggested_test_scenario.steps.map(s => `<li>${s}</li>`).join("");
  } else {
    remediationBox.classList.add("hidden");
  }

  switchTab("screen-c");
}

async function executeRegressionSelection() {
  const diffFile = document.getElementById("diff-selector").value;
  const tbody = document.getElementById("regression-table-body");
  tbody.innerHTML = `<tr><td colspan="6" class="loading">Evaluating code change fingerprints against requirement matrix...</td></tr>`;

  try {
    const res = await fetch("/api/select-regression", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ diff_file: diffFile })
    });
    const data = await res.json();
    const decisions = data.decisions || [];
    const warnings = data.warning_notes || [];

    const warningBanner = document.getElementById("regression-warning-banner");
    if (warnings.length > 0) {
      warningBanner.classList.remove("hidden");
      document.getElementById("regression-warning-text").innerHTML = warnings.map(w => `<p style="margin-bottom:4px;">${w}</p>`).join("");
    } else {
      warningBanner.classList.add("hidden");
    }

    if (decisions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px;">No tests matched for this change.</td></tr>`;
      return;
    }

    tbody.innerHTML = decisions.map(d => {
      const priorityClass = d.priority === "MUST_RUN" ? "badge-danger" : (d.priority === "SHOULD_RUN" ? "badge-warning" : "badge-neutral");
      return `
        <tr>
          <td><span class="badge ${priorityClass}"><strong>${d.priority}</strong></span></td>
          <td><span class="badge badge-neutral">${d.confidence}</span></td>
          <td><code>${d.title}</code></td>
          <td>${d.in_regression_suite ? 'Yes' : '<strong>No (Outside)</strong>'}</td>
          <td>${d.affected_requirement_ids.join(", ")}</td>
          <td>${d.selection_reasons.join("; ")}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Regression selection failed:", err);
  }
}

async function loadReport() {
  const pre = document.getElementById("report-content-pre");
  try {
    const res = await fetch("/api/report");
    const data = await res.json();
    pre.textContent = data.markdown || "No report generated.";
  } catch (err) {
    pre.textContent = "Error loading report.";
  }
}

function copyReport() {
  const text = document.getElementById("report-content-pre").textContent;
  navigator.clipboard.writeText(text);
  alert("Markdown report copied to clipboard!");
}

function downloadReport() {
  const text = document.getElementById("report-content-pre").textContent;
  const blob = new Blob([text], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ITAF-Assurance-Report.md";
  a.click();
}
