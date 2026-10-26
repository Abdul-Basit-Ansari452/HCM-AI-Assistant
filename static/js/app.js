"use strict";

const TOKEN_KEY = "token";

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
  if (canApprove) {
    bindPendingActions();
  }
  await Promise.all([
    loadLeavePageBalances(),
    loadMyLeaves(),
    canApprove ? loadPendingApprovals() : Promise.resolve(),
  ]);
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
