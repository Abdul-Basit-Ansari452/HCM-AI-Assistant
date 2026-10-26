"use strict";

const TOKEN_KEY = "token";

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
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
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

  tbody.innerHTML = departments
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.department)}</td>
          <td class="numeric">${escapeHtml(row.count)}</td>
        </tr>
      `,
    )
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

function bindAttendanceActions() {
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
      } catch (error) {
        handleFetchError(error);
      }
    }, "Checking out…");
  });
}

async function initDashboardPage(user) {
  const isAdminOrHr = user.role === "admin" || user.role === "hr";
  const adminSection = document.getElementById("admin-dashboard");
  const employeeSection = document.getElementById("employee-dashboard");

  if (adminSection) {
    adminSection.classList.toggle("hidden", !isAdminOrHr);
  }
  if (employeeSection) {
    employeeSection.classList.toggle("hidden", isAdminOrHr);
  }

  if (isAdminOrHr) {
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
  }
}

document.addEventListener("DOMContentLoaded", () => {
  boot().catch((error) => handleFetchError(error));
});
