"use strict";

const TOKEN_KEY = "token";
const CHAT_ANSWER_SUFFIX = "\u2014 AI-generated answer";

let employeesCache = [];
let editingEmployeeId = null;

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function escapeHtml(value) {
  const entities = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return String(value ?? "").replace(/[&<>"']/g, (character) => entities[character]);
}

function showToast(message, type = "error") {
  const host = document.querySelector("dialog[open]") || document.body;
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.setAttribute("aria-live", "polite");
  }
  if (container.parentElement !== host) {
    host.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type === "success" ? "success" : "error"}`;
  toast.setAttribute("role", type === "success" ? "status" : "alert");
  toast.textContent = message || "Something went wrong.";
  container.appendChild(toast);

  window.setTimeout(() => {
    toast.classList.add("toast-out");
    window.setTimeout(() => toast.remove(), 200);
  }, 4000);
}

async function parseError(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg || "Invalid input").join("; ");
    }
  } catch (_error) {
    // Fall through to the generic message.
  }
  return `Request failed (${response.status})`;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    clearToken();
    window.location.replace("/login");
    throw new ApiError("Session expired", 401);
  }
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function handleFetchError(error) {
  if (error instanceof ApiError && error.status === 401) {
    return;
  }
  showToast(error instanceof Error ? error.message : "Request failed");
}

async function withBusy(button, task, busyLabel) {
  const originalLabel = button.textContent;
  button.disabled = true;
  if (busyLabel) {
    button.textContent = busyLabel;
  }
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

function labelize(value) {
  return String(value ?? "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function statusBadge(status) {
  const normalized = String(status ?? "").toLowerCase();
  const allowed = new Set([
    "present",
    "late",
    "absent",
    "pending",
    "approved",
    "rejected",
  ]);
  const className = allowed.has(normalized) ? `badge-${normalized}` : "badge-neutral";
  return `<span class="badge ${className}">${escapeHtml(normalized || "unknown")}</span>`;
}

function formatTime(value) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? escapeHtml(value)
    : escapeHtml(date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
}

function formatDates(startDate, endDate) {
  if (!startDate && !endDate) {
    return "—";
  }
  if (!endDate || startDate === endDate) {
    return escapeHtml(startDate || endDate);
  }
  return `${escapeHtml(startDate)} – ${escapeHtml(endDate)}`;
}

function isAdminOrHr(user) {
  return Boolean(user) && (user.role === "admin" || user.role === "hr");
}

function localDateString(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateOnly(value) {
  const parts = String(value ?? "").split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return null;
  }
  const [year, month, day] = parts;
  if (!year || !month || !day) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDisplayDate(value) {
  if (!value) {
    return "—";
  }
  const date = parseDateOnly(value);
  if (!date) {
    return escapeHtml(value);
  }
  return escapeHtml(
    date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }),
  );
}

function formatDateRange(startDate, endDate) {
  if (!startDate && !endDate) {
    return "—";
  }
  if (!endDate || startDate === endDate) {
    return formatDisplayDate(startDate || endDate);
  }
  return `${formatDisplayDate(startDate)} – ${formatDisplayDate(endDate)}`;
}

function inclusiveDays(startDate, endDate) {
  const start = parseDateOnly(startDate);
  const end = parseDateOnly(endDate);
  if (!start || !end) {
    return 0;
  }
  return Math.round((end.getTime() - start.getTime()) / 86400000) + 1;
}

function setActiveNav() {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const isActive = link.getAttribute("href") === window.location.pathname;
    link.classList.toggle("active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    }
  });
}

function initNav(user) {
  const topnav = document.getElementById("topnav");
  if (!topnav) {
    return;
  }

  document.querySelectorAll("[data-roles]").forEach((element) => {
    const roles = (element.dataset.roles || "")
      .split(",")
      .map((role) => role.trim())
      .filter(Boolean);
    element.classList.toggle("hidden", !roles.includes(user.role));
  });

  const userLabel = document.getElementById("nav-user-label");
  if (userLabel) {
    userLabel.textContent = user.email || "";
  }

  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.addEventListener("click", () => {
      clearToken();
      window.location.replace("/login");
    });
  }

  setActiveNav();
  topnav.hidden = false;
}

function initLoginPage() {
  if (getToken()) {
    window.location.replace("/dashboard");
    return;
  }

  const form = document.getElementById("login-form");
  const button = document.getElementById("login-button");
  if (!form || !button) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    withBusy(button, async () => {
      try {
        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value;
        const response = await fetch("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ username, password }),
        });
        if (!response.ok) {
          throw new ApiError(await parseError(response), response.status);
        }

        const payload = await response.json();
        if (!payload.access_token) {
          throw new Error("Login response did not include an access token.");
        }

        setToken(payload.access_token);
        await api("/auth/me");
        window.location.replace("/dashboard");
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Login failed");
      }
    }, "Signing in…");
  });
}

function renderAdminStats(summary) {
  const container = document.getElementById("admin-stats");
  if (!container) {
    return;
  }

  const stats = [
    ["Total employees", summary.total_employees],
    ["Present today", summary.present_today],
    ["Late today", summary.late_today],
    ["On leave today", summary.on_leave_today],
    ["Pending approvals", summary.pending_leave_requests],
  ];

  container.innerHTML = stats
    .map(
      ([label, value]) => `
        <article class="stat-card">
          <p class="stat-label">${escapeHtml(label)}</p>
          <p class="stat-value">${escapeHtml(value ?? "—")}</p>
        </article>
      `,
    )
    .join("");
}

function renderHeadcount(rows) {
  const tbody = document.getElementById("headcount-body");
  if (!tbody) {
    return;
  }

  const departments = Array.isArray(rows) ? rows : [];
  if (!departments.length) {
    tbody.innerHTML = '<tr><td class="empty" colspan="2">No departments found.</td></tr>';
    return;
  }

  const maxCount = Math.max(
    1,
    ...departments.map((row) => Number(row.count) || 0),
  );
  tbody.innerHTML = departments
    .map((row) => {
      const count = Number(row.count) || 0;
      const width = count === 0 ? 0 : Math.max(6, Math.round((count / maxCount) * 100));
      return `
        <tr>
          <td class="headcount-label">${escapeHtml(row.department)}</td>
          <td class="headcount-value">
            <span class="headcount-track" aria-hidden="true">
              <span class="headcount-bar" style="--bar-width: ${width}%"></span>
            </span>
            <span class="headcount-count">${escapeHtml(row.count)}</span>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function loadAdminDashboard() {
  try {
    const summary = await api("/dashboard/summary");
    renderAdminStats(summary);
    renderHeadcount(summary.headcount_by_department);
  } catch (error) {
    const tbody = document.getElementById("headcount-body");
    if (tbody) {
      tbody.innerHTML = '<tr><td class="empty" colspan="2">Unable to load headcount.</td></tr>';
    }
    handleFetchError(error);
  }
}

function renderAttendance(attendance) {
  const card = document.getElementById("attendance-card");
  const checkInButton = document.getElementById("check-in-button");
  const checkOutButton = document.getElementById("check-out-button");
  if (!card || !checkInButton || !checkOutButton) {
    return;
  }

  if (!attendance) {
    card.innerHTML = `
      <div class="attendance-line">
        <span class="badge">Not checked in</span>
        <span class="muted">No check-in recorded for today.</span>
      </div>
    `;
    checkInButton.hidden = false;
    checkOutButton.hidden = true;
    return;
  }

  const checkIn = formatTime(attendance.check_in);
  const checkOut = formatTime(attendance.check_out);
  card.innerHTML = `
    <div class="attendance-line">
      ${statusBadge(attendance.status)}
      <span class="attendance-time">Check-in: ${checkIn}</span>
      <span class="attendance-time">Check-out: ${checkOut}</span>
    </div>
  `;

  const hasCheckIn = Boolean(attendance.check_in);
  const hasCheckOut = Boolean(attendance.check_out);
  checkInButton.hidden = true;
  checkOutButton.hidden = !(hasCheckIn && !hasCheckOut);
}

function renderBalances(balances) {
  const container = document.getElementById("balance-cards");
  if (!container) {
    return;
  }

  const rows = Array.isArray(balances) ? balances : [];
  if (!rows.length) {
    container.innerHTML = '<p class="empty">No leave balances found.</p>';
    return;
  }

  container.innerHTML = rows
    .map(
      (balance) => `
        <article class="stat-card">
          <p class="stat-label">${escapeHtml(labelize(balance.leave_type))}</p>
          <p class="stat-value">
            ${escapeHtml(balance.remaining)}
            <span class="stat-unit">days left</span>
          </p>
          <p class="stat-meta">
            ${escapeHtml(balance.used_days)} used of ${escapeHtml(balance.total_days)}
          </p>
        </article>
      `,
    )
    .join("");
}

function renderPendingRequests(requests) {
  const tbody = document.getElementById("pending-requests-body");
  if (!tbody) {
    return;
  }

  const rows = Array.isArray(requests) ? requests : [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td class="empty" colspan="4">No pending requests.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map(
      (request) => `
        <tr>
          <td>${escapeHtml(labelize(request.leave_type))}</td>
          <td>${formatDates(request.start_date, request.end_date)}</td>
          <td>${escapeHtml(request.reason)}</td>
          <td>${statusBadge(request.status)}</td>
        </tr>
      `,
    )
    .join("");
}

async function loadEmployeeBalances() {
  try {
    renderBalances(await api("/leaves/balance/me"));
  } catch (error) {
    handleFetchError(error);
  }
}

async function loadEmployeeDashboardData() {
  try {
    const data = await api("/dashboard/me");
    renderAttendance(data.my_attendance_today);
    renderPendingRequests(data.my_pending_requests);
  } catch (error) {
    handleFetchError(error);
  }
}

function bindAttendanceActions(onChange) {
  const checkInButton = document.getElementById("check-in-button");
  const checkOutButton = document.getElementById("check-out-button");
  if (!checkInButton || !checkOutButton) {
    return;
  }

  checkInButton.addEventListener("click", () => {
    withBusy(checkInButton, async () => {
      try {
        const attendance = await api("/attendance/check-in", { method: "POST" });
        renderAttendance(attendance);
        showToast("Checked in successfully.", "success");
        if (onChange) {
          await onChange(attendance);
        }
      } catch (error) {
        handleFetchError(error);
      }
    }, "Checking in…");
  });

  checkOutButton.addEventListener("click", () => {
    withBusy(checkOutButton, async () => {
      try {
        const attendance = await api("/attendance/check-out", { method: "POST" });
        renderAttendance(attendance);
        showToast("Checked out successfully.", "success");
        if (onChange) {
          await onChange(attendance);
        }
      } catch (error) {
        handleFetchError(error);
      }
    }, "Checking out…");
  });
}

async function initDashboardPage(user) {
  const isAdminHr = user.role === "admin" || user.role === "hr";
  const adminSection = document.getElementById("admin-dashboard");
  const employeeSection = document.getElementById("employee-dashboard");

  if (adminSection) {
    adminSection.classList.toggle("hidden", !isAdminHr);
  }
  if (employeeSection) {
    employeeSection.classList.toggle("hidden", isAdminHr);
  }

  if (isAdminHr) {
    await loadAdminDashboard();
    return;
  }

  if (user.role === "employee") {
    bindAttendanceActions();
    await Promise.all([loadEmployeeBalances(), loadEmployeeDashboardData()]);
    return;
  }

  showToast("This account has an unsupported role.");
}

function populateDepartmentFilter(employees) {
  const select = document.getElementById("department-filter");
  if (!select) {
    return;
  }

  const previous = select.value;
  const departments = [...new Set(employees.map((employee) => employee.department))].sort(
    (left, right) => left.localeCompare(right),
  );
  select.innerHTML =
    '<option value="">All departments</option>' +
    departments
      .map(
        (department) =>
          `<option value="${escapeHtml(department)}">${escapeHtml(department)}</option>`,
      )
      .join("");
  select.value = departments.includes(previous) ? previous : "";
}

function renderEmployeeTable() {
  const tbody = document.getElementById("employees-body");
  if (!tbody) {
    return;
  }

  const filter = document.getElementById("department-filter")?.value || "";
  const rows = employeesCache.filter(
    (employee) => !filter || employee.department === filter,
  );
  if (!rows.length) {
    tbody.innerHTML =
      '<tr><td class="empty" colspan="6">No employees found.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map(
      (employee) => `
        <tr>
          <td>${escapeHtml(employee.full_name)}</td>
          <td>${escapeHtml(employee.email)}</td>
          <td>${escapeHtml(employee.department)}</td>
          <td>${escapeHtml(employee.designation)}</td>
          <td>${formatDisplayDate(employee.join_date)}</td>
          <td class="numeric table-actions">
            <button class="btn btn-small" data-edit-id="${escapeHtml(employee.id)}" type="button">
              Edit
            </button>
          </td>
        </tr>
      `,
    )
    .join("");
}

async function loadEmployees() {
  try {
    employeesCache = await api("/employees");
    populateDepartmentFilter(employeesCache);
    renderEmployeeTable();
  } catch (error) {
    const tbody = document.getElementById("employees-body");
    if (tbody) {
      tbody.innerHTML =
        '<tr><td class="empty" colspan="6">Unable to load employees.</td></tr>';
    }
    handleFetchError(error);
  }
}

function openEmployeeModal(employee) {
  const modal = document.getElementById("employee-modal");
  const form = document.getElementById("employee-form");
  const title = document.getElementById("employee-modal-title");
  const email = document.getElementById("employee-email");
  const emailHint = document.getElementById("employee-email-hint");
  const passwordField = document.getElementById("employee-password-field");
  const password = document.getElementById("employee-password");
  if (
    !modal ||
    !form ||
    !title ||
    !email ||
    !emailHint ||
    !passwordField ||
    !password
  ) {
    return;
  }

  form.reset();
  editingEmployeeId = employee ? employee.id : null;
  const editing = editingEmployeeId !== null;

  title.textContent = editing ? "Edit Employee" : "Add Employee";
  email.disabled = editing;
  emailHint.hidden = !editing;
  passwordField.classList.toggle("hidden", editing);
  password.required = !editing;

  if (employee) {
    document.getElementById("employee-full-name").value = employee.full_name;
    email.value = employee.email;
    document.getElementById("employee-department").value = employee.department;
    document.getElementById("employee-designation").value = employee.designation;
  }

  if (!modal.open) {
    modal.showModal();
  }
  document.getElementById("employee-full-name")?.focus();
}

function closeEmployeeModal() {
  const modal = document.getElementById("employee-modal");
  if (modal?.open) {
    modal.close();
  }
}

function bindEmployeePage() {
  const addButton = document.getElementById("add-employee-button");
  const filter = document.getElementById("department-filter");
  const tbody = document.getElementById("employees-body");
  const form = document.getElementById("employee-form");
  const modal = document.getElementById("employee-modal");
  const closeButton = document.getElementById("employee-modal-close");
  const cancelButton = document.getElementById("employee-cancel");

  addButton?.addEventListener("click", () => openEmployeeModal(null));
  filter?.addEventListener("change", renderEmployeeTable);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeEmployeeModal();
    }
  });
  closeButton?.addEventListener("click", closeEmployeeModal);
  cancelButton?.addEventListener("click", closeEmployeeModal);

  tbody?.addEventListener("click", (event) => {
    const button =
      event.target instanceof Element ? event.target.closest("[data-edit-id]") : null;
    if (!button) {
      return;
    }
    const employee = employeesCache.find(
      (item) => item.id === Number(button.dataset.editId),
    );
    if (employee) {
      openEmployeeModal(employee);
    }
  });

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const saveButton = document.getElementById("employee-save");
    const fullName = document.getElementById("employee-full-name");
    const email = document.getElementById("employee-email");
    const password = document.getElementById("employee-password");
    const department = document.getElementById("employee-department");
    const designation = document.getElementById("employee-designation");
    if (
      !saveButton ||
      !fullName ||
      !email ||
      !password ||
      !department ||
      !designation
    ) {
      return;
    }

    const editing = editingEmployeeId !== null;
    const payload = {
      full_name: fullName.value.trim(),
      department: department.value.trim(),
      designation: designation.value.trim(),
    };
    if (!editing) {
      payload.email = email.value.trim();
      payload.password = password.value;
    }

    withBusy(
      saveButton,
      async () => {
        try {
          const path = editing ? `/employees/${editingEmployeeId}` : "/employees";
          await api(path, {
            method: editing ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          showToast(editing ? "Employee updated." : "Employee added.", "success");
          closeEmployeeModal();
          editingEmployeeId = null;
          await loadEmployees();
        } catch (error) {
          handleFetchError(error);
        }
      },
      "Saving…",
    );
  });
}

async function initEmployeesPage(user) {
  if (!isAdminOrHr(user)) {
    window.location.replace("/dashboard");
    return;
  }

  bindEmployeePage();
  await loadEmployees();
}

function renderAttendanceHistory(rows) {
  const tbody = document.getElementById("attendance-history-body");
  if (!tbody) {
    return;
  }

  const records = Array.isArray(rows) ? rows : [];
  if (!records.length) {
    tbody.innerHTML =
      '<tr><td class="empty" colspan="4">No attendance records in the last 30 days.</td></tr>';
    return;
  }

  tbody.innerHTML = records
    .map(
      (row) => `
        <tr>
          <td>${formatDisplayDate(row.date)}</td>
          <td>${statusBadge(row.status)}</td>
          <td>${formatTime(row.check_in)}</td>
          <td>${formatTime(row.check_out)}</td>
        </tr>
      `,
    )
    .join("");
}

async function loadAttendancePage() {
  try {
    const data = await api("/attendance/me");
    const rows = Array.isArray(data) ? data : [];
    const today = localDateString();
    renderAttendance(rows.find((row) => row.date === today) ?? null);
    renderAttendanceHistory(rows);
  } catch (error) {
    handleFetchError(error);
  }
}

async function loadAttendanceHistory() {
  try {
    const data = await api("/attendance/me");
    renderAttendanceHistory(data);
  } catch (error) {
    handleFetchError(error);
  }
}

async function initAttendancePage() {
  const dateLabel = document.getElementById("attendance-date");
  if (dateLabel) {
    dateLabel.textContent = formatDisplayDate(localDateString());
  }
  bindAttendanceActions(loadAttendanceHistory);
  await loadAttendancePage();
}

function renderLeaveBalances(balances) {
  const container = document.getElementById("leave-balance-cards");
  if (!container) {
    return;
  }

  const rows = Array.isArray(balances) ? balances : [];
  if (!rows.length) {
    container.innerHTML = '<p class="empty">No leave balances found.</p>';
    return;
  }

  container.innerHTML = rows
    .map(
      (balance) => `
        <article class="stat-card">
          <p class="stat-label">${escapeHtml(labelize(balance.leave_type))}</p>
          <p class="stat-value">
            ${escapeHtml(balance.remaining)}
            <span class="stat-unit">of ${escapeHtml(balance.total_days)} remaining</span>
          </p>
          <p class="stat-meta">${escapeHtml(balance.used_days)} used</p>
        </article>
      `,
    )
    .join("");
}

function renderMyLeaves(requests) {
  const tbody = document.getElementById("my-leaves-body");
  if (!tbody) {
    return;
  }

  const rows = Array.isArray(requests) ? requests : [];
  if (!rows.length) {
    tbody.innerHTML =
      '<tr><td class="empty" colspan="5">No leave requests yet.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map(
      (request) => `
        <tr>
          <td>${escapeHtml(labelize(request.leave_type))}</td>
          <td>${formatDateRange(request.start_date, request.end_date)}</td>
          <td class="numeric">${escapeHtml(inclusiveDays(request.start_date, request.end_date))}</td>
          <td>${escapeHtml(request.reason)}</td>
          <td>${statusBadge(request.status)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderPendingApprovals(requests) {
  const tbody = document.getElementById("pending-leaves-body");
  if (!tbody) {
    return;
  }

  const rows = Array.isArray(requests) ? requests : [];
  if (!rows.length) {
    tbody.innerHTML =
      '<tr><td class="empty" colspan="6">No pending approvals.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map(
      (request) => `
        <tr>
          <td>${escapeHtml(request.employee_name)}</td>
          <td>${escapeHtml(labelize(request.leave_type))}</td>
          <td>${formatDateRange(request.start_date, request.end_date)}</td>
          <td class="numeric">${escapeHtml(inclusiveDays(request.start_date, request.end_date))}</td>
          <td>${escapeHtml(request.reason)}</td>
          <td class="numeric table-actions">
            <button
              class="btn btn-small btn-primary"
              data-leave-action="approve"
              data-leave-id="${escapeHtml(request.id)}"
              type="button"
            >
              Approve
            </button>
            <button
              class="btn btn-small btn-danger"
              data-leave-action="reject"
              data-leave-id="${escapeHtml(request.id)}"
              type="button"
            >
              Reject
            </button>
          </td>
        </tr>
      `,
    )
    .join("");
}

async function loadLeavePageBalances() {
  try {
    renderLeaveBalances(await api("/leaves/balance/me"));
  } catch (error) {
    handleFetchError(error);
  }
}

async function loadMyLeaves() {
  try {
    renderMyLeaves(await api("/leaves/me"));
  } catch (error) {
    handleFetchError(error);
  }
}

async function loadPendingApprovals() {
  try {
    renderPendingApprovals(await api("/leaves/pending"));
  } catch (error) {
    handleFetchError(error);
  }
}

function bindLeaveForm(canApprove) {
  const form = document.getElementById("leave-form");
  const submitButton = document.getElementById("leave-submit");
  const startInput = document.getElementById("leave-start");
  const endInput = document.getElementById("leave-end");
  const errorElement = document.getElementById("leave-date-error");
  const leaveType = document.getElementById("leave-type");
  const reason = document.getElementById("leave-reason");
  if (
    !form ||
    !submitButton ||
    !startInput ||
    !endInput ||
    !errorElement ||
    !leaveType ||
    !reason
  ) {
    return;
  }

  const clearDateError = () => {
    errorElement.hidden = true;
  };
  startInput.addEventListener("input", clearDateError);
  endInput.addEventListener("input", clearDateError);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!startInput.value || !endInput.value) {
      form.reportValidity();
      return;
    }
    if (endInput.value < startInput.value) {
      errorElement.hidden = false;
      showToast("End date must be on or after start date.");
      return;
    }
    errorElement.hidden = true;

    withBusy(
      submitButton,
      async () => {
        try {
          await api("/leaves", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              leave_type: leaveType.value,
              start_date: startInput.value,
              end_date: endInput.value,
              reason: reason.value.trim(),
            }),
          });
          showToast("Leave request submitted.", "success");
          form.reset();
          errorElement.hidden = true;
          await Promise.all([
            loadMyLeaves(),
            loadLeavePageBalances(),
            canApprove ? loadPendingApprovals() : Promise.resolve(),
          ]);
        } catch (error) {
          handleFetchError(error);
        }
      },
      "Submitting…",
    );
  });
}

function fillLeaveFormFromDraft(draft) {
  const leaveType = document.getElementById("leave-type");
  const startInput = document.getElementById("leave-start");
  const endInput = document.getElementById("leave-end");
  const reason = document.getElementById("leave-reason");
  const dateError = document.getElementById("leave-date-error");
  if (!leaveType || !startInput || !endInput || !reason || !draft) {
    return false;
  }

  leaveType.value = draft.leave_type;
  startInput.value = draft.start_date;
  endInput.value = draft.end_date;
  reason.value = draft.reason;
  if (dateError) {
    dateError.hidden = true;
  }
  reason.focus();
  return true;
}

function buildLeaveDraftCard(leaveDraft, options = {}) {
  const draft = leaveDraft && leaveDraft.draft;
  if (!draft) {
    return null;
  }

  const card = document.createElement("section");
  card.className = "draft-card";
  if (options.className) {
    card.classList.add(
      ...String(options.className).split(" ").filter(Boolean),
    );
  }
  card.setAttribute("aria-label", "AI leave draft");

  const head = document.createElement("div");
  head.className = "draft-card-head";

  const heading = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "draft-eyebrow";
  eyebrow.textContent = "AI leave draft";
  const title = document.createElement("h3");
  title.textContent = `${labelize(draft.leave_type)} leave`;
  heading.append(eyebrow, title);

  const badge = document.createElement("span");
  badge.className = "badge badge-pending";
  badge.textContent = "Review";
  head.append(heading, badge);
  card.appendChild(head);

  const meta = document.createElement("dl");
  meta.className = "draft-meta";

  const addMeta = (label, value, wide = false) => {
    const field = document.createElement("div");
    if (wide) {
      field.className = "draft-meta-wide";
    }
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    field.append(term, detail);
    meta.appendChild(field);
  };

  addMeta("Dates", formatDateRange(draft.start_date, draft.end_date), true);
  const days = Number.isFinite(Number(leaveDraft.requested_days))
    ? Number(leaveDraft.requested_days)
    : inclusiveDays(draft.start_date, draft.end_date);
  addMeta("Days", String(days));

  const remainingValue = Number(leaveDraft.remaining_balance);
  const remaining = Number.isFinite(remainingValue)
    ? `${remainingValue} ${labelize(draft.leave_type).toLowerCase()} ${
        remainingValue === 1 ? "day" : "days"
      } left`
    : "Not available";
  addMeta("Balance", remaining);
  addMeta("Reason", draft.reason, true);
  card.appendChild(meta);

  const warnings = Array.isArray(leaveDraft.warnings)
    ? leaveDraft.warnings
    : [];
  if (warnings.length > 0) {
    const warningList = document.createElement("div");
    warningList.className = "draft-warnings";
    warnings.forEach((warning) => {
      const row = document.createElement("p");
      row.className = "draft-warning";
      row.textContent = String(
        warning?.message || warning || "Review this draft.",
      );
      warningList.appendChild(row);
    });
    card.appendChild(warningList);
  }

  const actions = document.createElement("div");
  actions.className = "draft-actions";
  const button = document.createElement("button");
  button.className = "btn btn-primary btn-small";
  button.type = "button";
  button.textContent = options.buttonLabel || "Apply to form";
  button.addEventListener("click", () => {
    if (typeof options.onApply === "function") {
      options.onApply(leaveDraft);
    }
  });
  actions.appendChild(button);

  const note = document.createElement("p");
  note.className = "draft-note";
  note.textContent = "Nothing is submitted until you click Submit.";
  actions.appendChild(note);
  card.appendChild(actions);

  return card;
}

function storeLeaveDraftForForm(leaveDraft) {
  try {
    sessionStorage.setItem("leave_draft", JSON.stringify(leaveDraft));
  } catch (_error) {
    showToast(
      "Could not save the draft in this browser. Use the form instead.",
    );
    return;
  }
  window.location.assign("/leave");
}

function initLeaveDraftReview() {
  const host = document.getElementById("leave-draft-review");
  if (!host) {
    return;
  }

  let raw = null;
  try {
    raw = sessionStorage.getItem("leave_draft");
  } catch (_error) {
    return;
  }
  if (!raw) {
    return;
  }
  try {
    sessionStorage.removeItem("leave_draft");
  } catch (_error) {
    // The in-memory draft below is still usable for this page load.
  }

  let leaveDraft = null;
  try {
    leaveDraft = JSON.parse(raw);
  } catch (_error) {
    return;
  }
  if (!leaveDraft || !leaveDraft.draft) {
    return;
  }

  const card = buildLeaveDraftCard(leaveDraft, {
    buttonLabel: "Apply to form",
    className: "leave-review-card",
    onApply: (draftEnvelope) => {
      if (fillLeaveFormFromDraft(draftEnvelope.draft)) {
        host.hidden = true;
        host.replaceChildren();
        showToast("Draft applied. Review the form and submit.", "success");
      }
    },
  });
  if (!card) {
    return;
  }
  host.replaceChildren(card);
  host.hidden = false;
}

function initLeaveTip() {
  const tip = document.getElementById("leave-tip");
  const close = document.getElementById("leave-tip-close");
  if (!tip || !close) {
    return;
  }
  close.addEventListener("click", () => {
    tip.hidden = true;
  });
}

function bindPendingActions() {
  const tbody = document.getElementById("pending-leaves-body");
  if (!tbody) {
    return;
  }

  tbody.addEventListener("click", (event) => {
    const button =
      event.target instanceof Element
        ? event.target.closest("[data-leave-action]")
        : null;
    if (!button) {
      return;
    }

    const action = button.dataset.leaveAction;
    const leaveId = Number(button.dataset.leaveId);
    if (!["approve", "reject"].includes(action) || !Number.isInteger(leaveId)) {
      return;
    }

    withBusy(
      button,
      async () => {
        try {
          await api(`/leaves/${leaveId}/${action}`, { method: "POST" });
          showToast(
            action === "approve"
              ? "Leave request approved."
              : "Leave request rejected.",
            "success",
          );
          await Promise.all([
            loadPendingApprovals(),
            loadLeavePageBalances(),
            loadMyLeaves(),
          ]);
        } catch (error) {
          handleFetchError(error);
          if (error instanceof ApiError && error.status === 409) {
            await loadPendingApprovals();
          }
        }
      },
      action === "approve" ? "Approving…" : "Rejecting…",
    );
  });
}

async function initLeavesPage(user) {
  const canApprove = isAdminOrHr(user);
  bindLeaveForm(canApprove);
  if (user.role === "employee") {
    initLeaveDraftReview();
  } else {
    try {
      sessionStorage.removeItem("leave_draft");
    } catch (_error) {
      // Storage can be unavailable in hardened browser modes.
    }
  }
  initLeaveTip();
  if (canApprove) {
    bindPendingActions();
  }
  await Promise.all([
    loadLeavePageBalances(),
    loadMyLeaves(),
    canApprove ? loadPendingApprovals() : Promise.resolve(),
  ]);
}

function initChatWidget(user) {
  const root = document.getElementById("chat-widget-root");
  const fab = document.getElementById("chat-widget-fab");
  const panel = document.getElementById("chat-widget-panel");
  const closeButton = document.getElementById("chat-widget-close");
  const messagesElement = document.getElementById("chat-widget-messages");
  const emptyState = document.getElementById("chat-widget-empty");
  const examplesElement = document.getElementById("chat-widget-examples");
  const form = document.getElementById("chat-widget-form");
  const input = document.getElementById("chat-widget-input");
  const sendButton = document.getElementById("chat-widget-send");

  if (
    !root ||
    !fab ||
    !panel ||
    !closeButton ||
    !messagesElement ||
    !examplesElement ||
    !form ||
    !input ||
    !sendButton
  ) {
    return;
  }

  root.hidden = false;

  const chatHistory = [];
  const chipButtons = [];
  let busy = false;
  let limitReached = false;

  const examples = isAdminOrHr(user)
    ? [
        {
          label: "Headcount",
          question: "What is the headcount by department?",
        },
        {
          label: "Attendance today",
          question: "How many employees are present today?",
        },
        {
          label: "Pending leave",
          question: "How many leave requests are pending?",
        },
      ]
    : [
        {
          label: "Leave balance",
          question: "How many sick leave days do I have left?",
        },
        {
          label: "Work from home policy",
          question: "What is the work from home policy?",
        },
      ];

  examples.forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-chip";
    button.textContent = example.label;
    button.title = example.question;
    button.setAttribute("aria-label", example.question);
    button.addEventListener("click", () => {
      sendMessage(example.question);
    });
    examplesElement.appendChild(button);
    chipButtons.push(button);
  });

  function scrollToBottom() {
    messagesElement.scrollTop = messagesElement.scrollHeight;
  }

  function addUserMessage(text) {
    if (emptyState) {
      emptyState.hidden = true;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "chat-message chat-message-user";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = text;

    wrapper.appendChild(bubble);
    messagesElement.appendChild(wrapper);
    chatHistory.push({ role: "user", text });
    scrollToBottom();
  }

  function addAssistantMessage(answer, toolsUsed, leaveDraft) {
    const text = String(answer ?? "").trim();
    const body = text.endsWith(CHAT_ANSWER_SUFFIX)
      ? text.slice(0, -CHAT_ANSWER_SUFFIX.length).trimEnd()
      : text;
    const tools = Array.isArray(toolsUsed)
      ? toolsUsed.filter((tool) => typeof tool === "string" && tool)
      : [];

    const wrapper = document.createElement("div");
    wrapper.className = "chat-message chat-message-assistant";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";

    const answerElement = document.createElement("p");
    answerElement.className = "chat-answer";
    answerElement.textContent = body || "No additional details.";
    bubble.appendChild(answerElement);

    const footer = document.createElement("p");
    footer.className = "chat-ai-footer";
    footer.textContent = CHAT_ANSWER_SUFFIX;
    bubble.appendChild(footer);

    wrapper.appendChild(bubble);

    const badgeRow = document.createElement("div");
    badgeRow.className = "chat-tools";
    badgeRow.setAttribute("aria-label", "Tools used");

    if (tools.length === 0) {
      const badge = document.createElement("span");
      badge.className = "chat-tool-badge chat-tool-none";
      badge.textContent = "No tools";
      badgeRow.appendChild(badge);
    } else {
      tools.forEach((tool) => {
        const badge = document.createElement("span");
        badge.className = "chat-tool-badge";
        badge.textContent = labelize(tool);
        badgeRow.appendChild(badge);
      });
    }

    wrapper.appendChild(badgeRow);

    if (leaveDraft) {
      const draftCard = buildLeaveDraftCard(leaveDraft, {
        buttonLabel: "Apply draft to form",
        className: "chat-draft-card",
        onApply: storeLeaveDraftForForm,
      });
      if (draftCard) {
        wrapper.appendChild(draftCard);
      }
    }

    messagesElement.appendChild(wrapper);
    chatHistory.push({
      role: "assistant",
      text: body,
      tools,
      leaveDraft: leaveDraft || null,
    });
    scrollToBottom();
  }

  function addErrorMessage(message) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-message chat-message-assistant chat-message-error";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = message;

    wrapper.appendChild(bubble);
    messagesElement.appendChild(wrapper);
    chatHistory.push({ role: "error", text: message });
    scrollToBottom();
  }

  function setInputDisabled(disabled) {
    input.disabled = disabled;
    sendButton.disabled = disabled;
  }

  function showLoading() {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-message chat-message-assistant";
    wrapper.id = "chat-widget-loading";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble chat-bubble-loading";
    bubble.setAttribute("role", "status");

    const spinner = document.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.textContent = "Thinking...";

    bubble.append(spinner, label);
    wrapper.appendChild(bubble);
    messagesElement.appendChild(wrapper);
    scrollToBottom();
  }

  function removeLoading() {
    const loading = document.getElementById("chat-widget-loading");
    if (loading) {
      loading.remove();
    }
  }

  function setPanelOpen(open) {
    panel.hidden = !open;
    fab.setAttribute("aria-expanded", String(open));
    fab.setAttribute(
      "aria-label",
      open ? "Close AI assistant" : "Open AI assistant",
    );
    if (open) {
      input.focus();
      scrollToBottom();
    } else {
      fab.focus();
    }
  }

  async function sendMessage(rawMessage) {
    const message = String(rawMessage ?? "").trim();
    if (!message || busy || limitReached) {
      return;
    }

    busy = true;
    addUserMessage(message);
    input.value = "";
    input.style.height = "";
    setInputDisabled(true);
    showLoading();

    try {
      const response = await api("/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      removeLoading();
      addAssistantMessage(
        response?.answer ?? "",
        response?.tools_used ?? [],
        response?.leave_draft ?? null,
      );
    } catch (error) {
      removeLoading();
      if (error instanceof ApiError && error.status === 401) {
        return;
      }
      if (error instanceof ApiError && error.status === 429) {
        limitReached = true;
        addErrorMessage(
          error.message || "Hourly AI limit reached (20/hour).",
        );
        setInputDisabled(true);
        chipButtons.forEach((button) => {
          button.disabled = true;
        });
        input.placeholder = "Hourly AI limit reached";
        return;
      }
      addErrorMessage(
        "I couldn't get an answer right now. Please try again.",
      );
    } finally {
      removeLoading();
      busy = false;
      if (!limitReached) {
        setInputDisabled(false);
        if (!panel.hidden) {
          input.focus();
        }
      }
    }
  }

  fab.addEventListener("click", () => {
    setPanelOpen(panel.hidden);
  });

  closeButton.addEventListener("click", () => {
    setPanelOpen(false);
  });

  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      setPanelOpen(false);
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 112)}px`;
  });
}

async function boot() {
  const page = document.body.dataset.page;
  if (page === "login") {
    initLoginPage();
    return;
  }

  if (!getToken()) {
    window.location.replace("/login");
    return;
  }

  let user;
  try {
    user = await api("/auth/me");
  } catch (error) {
    handleFetchError(error);
    return;
  }

  initNav(user);
  initChatWidget(user);

  if (page === "dashboard") {
    await initDashboardPage(user);
  } else if (page === "employees") {
    await initEmployeesPage(user);
  } else if (page === "attendance") {
    await initAttendancePage(user);
  } else if (page === "leaves") {
    await initLeavesPage(user);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  boot().catch((error) => handleFetchError(error));
});
