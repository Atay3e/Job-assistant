if (window.location.protocol === "file:") {
  window.location.replace("http://127.0.0.1:8787/");
}

const state = {
  jobs: [],
  aiJobs: [],
  recommendations: { jobs: [], active_direction_ids: [], direction_source: "base_score" },
  summary: {},
  watchlist: [],
  regions: { regions: [], active_region: "SG" },
  userContext: { active_region: "SG", contexts: {} },
  profileOptions: {},
  companyCatalog: [],
  activeFilter: "",
  recommendationView: "fit",
  selectedCompany: "",
  trackerMode: "all",
  trackerDate: "",
  trackerMonth: "",
  notionStatus: {},
  daily: {},
  profile: {},
  careerFit: {},
  scan: {},
  scanPollTimer: null,
  focusRefreshTimer: null,
  dailyRunChecked: false,
};

const icon = {
  apply: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>',
  watch: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><path d="M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z"/></svg>',
  drop: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  detail: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg>',
  submit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>',
  assist: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h13a3 3 0 0 1 3 3v10H4z"/><path d="M8 8h7M8 12h5"/><path d="M14 16l5 5M14 16l1.4 5.4 1.6-3.1 3.2-1.4z"/></svg>',
  upload: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4"/><path d="M8 8l4-4 4 4"/><path d="M20 16v3a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3"/></svg>',
};

const STATUS_ZH = {
  New: "新岗位",
  Recommended: "推荐",
  "Apply Queue": "待投递",
  Drafted: "已生成材料",
  Applied: "已投递",
  Watch: "关注",
  Dropped: "已放弃",
  "Follow Up": "待跟进",
  Interview: "面试中",
  Rejected: "已拒绝",
  Offer: "Offer",
  Closed: "已关闭",
};

const FLAG_ZH = {
  citizen_or_pr_only: "仅限公民/PR",
  local_only: "仅限本地人",
  clearance_required: "需要安全审查",
  experience_too_high: "经验要求偏高",
  visa_unclear: "签证要求不明确",
  custom_questions: "有定制问题",
  captcha_or_login_wall: "可能有验证码/登录墙",
  duplicate: "重复岗位",
  already_applied: "已投递过",
  dropped_before: "之前已放弃",
};

const SCAN_STATUS_ZH = {
  pending: "等待",
  running: "扫描中",
  success: "成功",
  partial: "部分成功",
  limited: "受限",
  failed: "失败",
  interrupted: "已中断",
};

const COMPANY_ALIASES = {
  ByteDance: ["ByteDance", "TikTok"],
  PDD: ["PDD", "Pinduoduo", "Temu"],
  Sea: ["Sea", "Shopee", "Garena"],
};

const RECOMMENDATION_EXCLUDED_STATUSES = new Set(["Apply Queue", "Drafted", "Applied", "Dropped", "Closed"]);

async function api(path, options = {}) {
  const init = { ...options };
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  init.headers = { ...headers, ...(options.headers || {}) };
  const response = await fetch(path, init);
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(message, type = "info") {
  const host = document.getElementById("toastHost");
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  host.appendChild(node);
  window.setTimeout(() => node.remove(), type === "error" ? 5200 : 3200);
}

function setButtonState(button, mode, label) {
  if (!button) return;
  if (!button.dataset.defaultHtml) button.dataset.defaultHtml = button.innerHTML;
  button.classList.remove("is-loading", "is-success", "is-error");
  button.removeAttribute("aria-busy");
  if (mode === "idle") {
    button.innerHTML = button.dataset.defaultHtml;
    button.disabled = false;
    return;
  }
  button.classList.add(`is-${mode}`);
  button.disabled = mode === "loading";
  if (mode === "loading") button.setAttribute("aria-busy", "true");
  if (label) button.textContent = label;
}

async function withButton(button, loadingLabel, task, successLabel = "已完成") {
  setButtonState(button, "loading", loadingLabel);
  try {
    const result = await task();
    setButtonState(button, "success", successLabel);
    window.setTimeout(() => setButtonState(button, "idle"), 900);
    return result;
  } catch (error) {
    setButtonState(button, "error", error.message);
    toast(error.message, "error");
    window.setTimeout(() => setButtonState(button, "idle"), 1800);
    throw error;
  }
}

function statusLabel(status) {
  return STATUS_ZH[status] || status || "-";
}

function flagLabel(flag) {
  return FLAG_ZH[flag] || flag || "未发现硬性本地身份限制";
}

function badgeClass(flag) {
  if (!flag) return "badge good";
  if (["citizen_or_pr_only", "local_only", "clearance_required", "experience_too_high"].includes(flag)) {
    return "badge warn";
  }
  return "badge";
}

function scoreTone(score) {
  if (score >= 4) return "高匹配";
  if (score >= 3) return "可投";
  if (score >= 2) return "待判断";
  return "低匹配";
}

function isRecommendationCandidate(job) {
  return !RECOMMENDATION_EXCLUDED_STATUSES.has(job.status);
}

function timelineDate(job) {
  return job.applied_date || job.batch_date || job.recommended_date || job.found_date || "";
}

function trackerDates(job) {
  return [job.found_date, job.batch_date, job.recommended_date, job.applied_date].filter(Boolean);
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || path || "";
}

function activeRegion() {
  return state.userContext?.active_region || state.regions?.active_region || "SG";
}

function activeRegionConfig() {
  return (state.regions.regions || []).find((item) => item.code === activeRegion()) || { code: "SG", label: "Singapore", cities: ["Singapore"] };
}

function activeRegionContext() {
  return state.userContext?.contexts?.[activeRegion()] || {};
}

function regionQuery() {
  return `region=${encodeURIComponent(activeRegion())}`;
}

function splitList(value) {
  return String(value || "")
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueList(values) {
  return Array.from(new Set((values || []).map((item) => String(item || "").trim()).filter(Boolean)));
}

function optionLabel(options, value) {
  return (options || []).find((item) => item.value === value)?.label || value || "";
}

function selectedValuesFromHidden(form, name) {
  return uniqueList(splitList(form?.elements?.[name]?.value || ""));
}

function setHiddenList(form, name, values) {
  if (form?.elements?.[name]) form.elements[name].value = uniqueList(values).join(", ");
}

function toggleValue(values, value, multi = true) {
  if (!multi) return [value];
  const set = new Set(values);
  if (set.has(value)) set.delete(value);
  else set.add(value);
  return Array.from(set);
}

function salaryBandsForPeriod(period) {
  const bands = state.profileOptions.salary_band_options || {};
  return bands[period] || bands.monthly || [{ value: "", label: "先不填" }];
}

function setSelectOptions(select, options, selectedValue = "") {
  if (!select) return;
  const selected = String(selectedValue ?? "");
  const normalized = [...(options || [])];
  if (selected && !normalized.some((item) => String(item.value) === selected)) {
    normalized.push({ value: selected, label: selected });
  }
  select.innerHTML = normalized
    .map((item) => `<option value="${escapeHtml(item.value)}" ${String(item.value) === selected ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
}

function renderOptionButtons(containerId, options, selectedValues, config = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const selected = new Set(selectedValues || []);
  const multi = config.multi !== false;
  container.innerHTML = (options || [])
    .map((item) => `
      <button
        type="button"
        class="option-chip ${selected.has(item.value) ? "active" : ""}"
        data-option-target="${escapeHtml(config.target || "")}"
        data-option-value="${escapeHtml(item.value)}"
        data-option-multi="${multi ? "true" : "false"}"
      >${escapeHtml(item.label)}</button>
    `)
    .join("");
}

function salaryPreferenceLabel(context) {
  const currency = context.salary_currency || state.profileOptions.salary_currency || "";
  const period = periodLabel(context.salary_period || "monthly");
  const minimum = context.salary_min ? `${currency} ${formatMoney(context.salary_min)}+` : "最低不限";
  const preferred = context.salary_preferred ? `理想 ${currency} ${formatMoney(context.salary_preferred)}+` : "理想可空";
  return `${minimum} · ${preferred} · ${period}`;
}

function syncContextCustomInputs(form) {
  if (!form) return;
  const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
  const jobTypeValues = new Set((state.profileOptions.job_type_options || []).map((item) => item.value));
  const selectedDirections = selectedValuesFromHidden(form, "target_directions").filter((item) => directionValues.has(item));
  const customDirections = splitList(document.getElementById("customDirections")?.value || "");
  setHiddenList(form, "target_directions", [...selectedDirections, ...customDirections]);
  const selectedJobTypes = selectedValuesFromHidden(form, "job_types").filter((item) => jobTypeValues.has(item));
  const customJobTypes = splitList(document.getElementById("customJobTypes")?.value || "");
  setHiddenList(form, "job_types", [...selectedJobTypes, ...customJobTypes]);
  const customWorkAuth = String(document.getElementById("customWorkAuth")?.value || "").trim();
  if (customWorkAuth) form.elements.work_authorisation.value = customWorkAuth;
}

function syncOnboardingCustomInputs(form) {
  if (!form) return;
  const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
  const selectedDirections = selectedValuesFromHidden(form, "target_directions").filter((item) => directionValues.has(item));
  const customDirections = splitList(document.getElementById("onboardingCustomDirections")?.value || "");
  setHiddenList(form, "target_directions", [...selectedDirections, ...customDirections]);
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ");
}

function employmentTypeLabel(value) {
  return {
    Internship: "实习",
    "Full-time": "正式工",
    Graduate: "Graduate",
    Contract: "Contract",
    Unknown: "类型待确认",
  }[value] || "类型待确认";
}

function periodLabel(value) {
  return {
    monthly: "月薪",
    yearly: "年薪",
    daily: "日薪",
    hourly: "时薪",
  }[value] || "薪资";
}

function formatMoney(value) {
  const number = Number(value || 0);
  if (!number) return "";
  return number.toLocaleString("en-SG", { maximumFractionDigits: number % 1 ? 1 : 0 });
}

function salaryBadgeLabel(job) {
  if (job.salary_fit_label && !["薪资未设置偏好"].includes(job.salary_fit_label)) {
    return job.salary_fit_label;
  }
  if (!job.salary_max) return "薪资未知";
  const currency = job.salary_currency || "";
  const min = formatMoney(job.salary_min);
  const max = formatMoney(job.salary_max);
  const range = min && max && min !== max ? `${min}-${max}` : (max || min);
  return `${currency} ${range} · ${periodLabel(job.salary_period)}`.trim();
}

function scanSourceLabel(source) {
  const name = String(source || "");
  if (name.includes("LinkedIn")) return "LinkedIn（含 AI 关键词）";
  if (name.includes("InternSG")) return "InternSG（含 AI 关键词）";
  if (name.includes("Indeed")) return "Indeed";
  if (name.includes("JobStreet")) return "JobStreet";
  if (name.includes("Company Site") || name.includes("公司官网")) return "公司官网";
  return name || "未知来源";
}

function scanStatusPriority(status) {
  return { failed: 6, limited: 5, partial: 4, running: 3, success: 2, interrupted: 1, pending: 0 }[status] ?? 0;
}

function mergeScanStatus(current, incoming) {
  return scanStatusPriority(incoming) > scanStatusPriority(current) ? incoming : current;
}

function scanModeLabel(mode) {
  return {
    primary: "主来源",
    supplemental: "补充",
    limited: "受限",
    company: "官网",
  }[mode] || "来源";
}

function setTrackerDefaults() {
  const currentDate = state.summary.date || new Date().toISOString().slice(0, 10);
  if (!state.trackerDate) state.trackerDate = currentDate;
  if (!state.trackerMonth) state.trackerMonth = currentDate.slice(0, 7);
}

function renderUserContextControls() {
  const config = activeRegionConfig();
  const context = activeRegionContext();
  const options = (state.regions.regions || [])
    .map((region) => `<option value="${escapeHtml(region.code)}" ${region.code === activeRegion() ? "selected" : ""}>${escapeHtml(region.label)}</option>`)
    .join("");
  const focusRegion = document.getElementById("focusRegion");
  const contextRegion = document.getElementById("contextRegion");
  const onboardingRegion = document.getElementById("onboardingRegion");
  if (focusRegion) focusRegion.innerHTML = options;
  if (contextRegion) contextRegion.innerHTML = options;
  if (onboardingRegion) onboardingRegion.innerHTML = options;

  const cityOptions = (config.cities || [config.default_city || "Singapore"])
    .map((city) => `<option value="${escapeHtml(city)}" ${city === (context.city || config.default_city) ? "selected" : ""}>${escapeHtml(city)}</option>`)
    .join("");
  const citySelect = document.getElementById("contextCity");
  if (citySelect) citySelect.innerHTML = cityOptions;

  const form = document.getElementById("contextForm");
  if (form) {
    form.elements.active_region.value = activeRegion();
    form.elements.city.value = context.city || config.default_city || "";
    form.elements.work_authorisation.value = context.work_authorisation || "";
    form.elements.target_directions.value = (context.target_directions || []).join(", ");
    form.elements.job_types.value = (context.job_types || []).join(", ");
    form.elements.employment_priority.value = context.employment_priority || "both";
    form.elements.salary_currency.value = context.salary_currency || state.profileOptions.salary_currency || "";

    const workAuthValues = new Set((state.profileOptions.work_authorisation_options || []).map((item) => item.value));
    const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
    const jobTypeValues = new Set((state.profileOptions.job_type_options || []).map((item) => item.value));
    document.getElementById("customWorkAuth").value = workAuthValues.has(context.work_authorisation) ? "" : (context.work_authorisation || "");
    document.getElementById("customDirections").value = (context.target_directions || []).filter((item) => !directionValues.has(item)).join(", ");
    document.getElementById("customJobTypes").value = (context.job_types || []).filter((item) => !jobTypeValues.has(item)).join(", ");

    renderOptionButtons("workAuthOptions", state.profileOptions.work_authorisation_options || [], [context.work_authorisation || ""], { target: "context:work_authorisation", multi: false });
    renderOptionButtons("contextPriorityOptions", state.profileOptions.employment_priority_options || [], [context.employment_priority || "both"], { target: "context:employment_priority", multi: false });
    renderOptionButtons("contextDirectionOptions", state.profileOptions.direction_options || [], context.target_directions || [], { target: "context:target_directions" });
    renderOptionButtons("contextJobTypeOptions", state.profileOptions.job_type_options || [], context.job_types || [], { target: "context:job_types" });

    setSelectOptions(document.getElementById("contextSalaryPeriod"), state.profileOptions.salary_period_options || [], context.salary_period || "monthly");
    const salaryBands = salaryBandsForPeriod(context.salary_period || "monthly");
    setSelectOptions(document.getElementById("contextSalaryMin"), salaryBands, context.salary_min ?? "");
    setSelectOptions(document.getElementById("contextSalaryPreferred"), salaryBands, context.salary_preferred ?? "");
    document.getElementById("salaryCurrencyDisplay").textContent = context.salary_currency || state.profileOptions.salary_currency || "-";
  }
  renderFocusPanel();
  renderOnboarding();
}

function renderFocusPanel() {
  const config = activeRegionConfig();
  const context = activeRegionContext();
  const priority = context.employment_priority || "both";
  const priorityLabel = optionLabel(state.profileOptions.employment_priority_options, priority) || "都考虑";
  document.getElementById("focusTitle").textContent = `${config.label || activeRegion()} · ${priorityLabel}`;
  document.getElementById("focusSummary").textContent = `${context.city || config.default_city || ""} · ${salaryPreferenceLabel(context)} · 关注公司 ${state.watchlist.length || 0} 家`;
  renderOptionButtons("focusPriorityQuick", state.profileOptions.employment_priority_options || [], [priority], { target: "focus:employment_priority", multi: false });
  const directionOptions = state.profileOptions.direction_options || [];
  const directionLabels = (context.target_directions || []).slice(0, 4).map((id) => optionLabel(directionOptions, id) || id);
  const jobTypes = (context.job_types || []).slice(0, 3);
  const tags = [
    context.city || config.default_city || "",
    ...directionLabels,
    ...jobTypes,
  ].filter(Boolean);
  document.getElementById("focusTags").innerHTML = tags.length
    ? tags.map((tag) => `<span class="chip-label active">${escapeHtml(tag)}</span>`).join("")
    : `<span class="chip-label">方向可空</span>`;
}

function renderOnboarding() {
  const panel = document.getElementById("onboardingPanel");
  const form = document.getElementById("onboardingForm");
  if (!panel || !form) return;
  const context = activeRegionContext();
  panel.hidden = Boolean(state.userContext?.onboarding_completed);
  form.elements.active_region.value = activeRegion();
  form.elements.employment_priority.value = context.employment_priority || "both";
  form.elements.target_directions.value = (context.target_directions || []).join(", ");
  const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
  const customDirectionInput = document.getElementById("onboardingCustomDirections");
  if (customDirectionInput) {
    customDirectionInput.value = (context.target_directions || []).filter((item) => !directionValues.has(item)).join(", ");
  }
  renderOptionButtons("onboardingPriorityOptions", state.profileOptions.employment_priority_options || [], [context.employment_priority || "both"], { target: "onboarding:employment_priority", multi: false });
  renderOptionButtons("onboardingDirectionOptions", state.profileOptions.direction_options || [], context.target_directions || [], { target: "onboarding:target_directions" });
  setSelectOptions(document.getElementById("onboardingSalaryPeriod"), state.profileOptions.salary_period_options || [], context.salary_period || "monthly");
  const salaryBands = salaryBandsForPeriod(context.salary_period || "monthly");
  setSelectOptions(document.getElementById("onboardingSalaryMin"), salaryBands, context.salary_min ?? "");
  setSelectOptions(document.getElementById("onboardingSalaryPreferred"), salaryBands, context.salary_preferred ?? "");
}

function jobCard(job, compact = false, options = {}) {
  const isQueue = job.status === "Apply Queue";
  const canWatch = !["Applied", "Apply Queue", "Dropped"].includes(job.status);
  const canDrop = !["Applied", "Dropped"].includes(job.status);
  const flags = job.eligibility_flags?.length ? job.eligibility_flags : [""];
  const badges = flags.map((flag) => `<span class="${badgeClass(flag)}">${escapeHtml(flagLabel(flag))}</span>`).join("");
  const aiBadge = options.ai ? `<span class="badge ai-badge">AI 匹配 ${Number(job.ai_relevance || 0).toFixed(1)}</span>` : "";
  const fitBadge = options.fit && Number(job.preference_boost || 0) > 0
    ? `<span class="badge fit-badge">定位 +${Number(job.preference_boost).toFixed(2)}</span>`
    : "";
  const regionBadge = job.region ? `<span class="badge">${escapeHtml(job.region)} · ${escapeHtml(job.city || job.location || "")}</span>` : "";
  const employmentBadge = `<span class="badge job-type-badge">${escapeHtml(employmentTypeLabel(job.employment_type || "Unknown"))}</span>`;
  const conversionBadge = Number(job.conversion_opportunity || 0) > 0
    ? `<span class="badge good">可转正</span>`
    : "";
  const salaryLabel = salaryBadgeLabel(job);
  const salaryBadge = salaryLabel
    ? `<span class="badge salary-badge ${job.salary_fit === "low" ? "warn" : ""}">${escapeHtml(salaryLabel)}</span>`
    : "";
  const companyBadge = Number(job.company_boost || 0) > 0
    ? `<span class="badge fit-badge">关注公司 +${Number(job.company_boost).toFixed(2)}</span>`
    : "";
  const matched = (job.matched_directions || [])
    .slice(0, 3)
    .map((item) => `<span class="badge fit-badge">${escapeHtml(item.label)}</span>`)
    .join("");
  const draftLinks = [job.resume_path, job.cover_letter_path]
    .filter(Boolean)
    .map((path) => `<span class="badge good">${escapeHtml(fileName(path))}</span>`)
    .join("");
  const score = Number(job.score || job.base_score || 0);
  const rankScore = Number(job.rank_score || score);
  const notes = options.fit && job.fit_reasons?.length ? job.fit_reasons.join(" | ") : job.match_notes;

  return `
    <article class="job-card" data-job-id="${job.id}">
      <div>
        <div class="job-title-row">
          <h3>
            <button class="job-title-button" data-action="detail" data-id="${job.id}" aria-label="查看 ${escapeHtml(job.company)} ${escapeHtml(job.position)} 的详情">
              ${escapeHtml(job.company)} - ${escapeHtml(job.position)}
            </button>
          </h3>
          <span class="badge">${escapeHtml(statusLabel(job.status))}</span>
          <span class="badge">${escapeHtml(job.source)}</span>
        </div>
        <div class="job-meta">推荐日期 ${escapeHtml(job.batch_date || "-")} · 发现日期 ${escapeHtml(job.found_date || "-")} · 投递日期 ${escapeHtml(job.applied_date || "-")}</div>
        <div class="badge-row">${regionBadge}${employmentBadge}${conversionBadge}${salaryBadge}${fitBadge}${companyBadge}${aiBadge}${matched}${badges}${draftLinks}</div>
        <a class="job-url" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">${escapeHtml(job.url)}</a>
        ${options.ai && job.ai_match_notes ? `<p class="small-text">${escapeHtml(job.ai_match_notes)}</p>` : ""}
        ${compact ? "" : `<p class="small-text">${escapeHtml(notes || "")}</p>`}
        <div class="job-actions">
          ${isQueue ? `<button class="primary-button" data-action="assist" data-id="${job.id}" title="打开浏览器并填常见字段，最终提交前停住">${icon.assist} 打开填表助手</button>` : ""}
          ${isQueue ? `<button class="secondary-button" data-action="confirm" data-id="${job.id}">${icon.submit} 确认已投</button>` : ""}
          ${isRecommendationCandidate(job) ? `<button class="primary-button" data-action="Apply" data-id="${job.id}">${icon.apply} 加入投递</button>` : ""}
          ${canWatch ? `<button class="secondary-button" data-action="Watch" data-id="${job.id}">${icon.watch} 关注</button>` : ""}
          ${canDrop ? `<button class="danger-button" data-action="Drop" data-id="${job.id}">${icon.drop} 放弃</button>` : ""}
        </div>
      </div>
      <div class="score">
        <span class="badge good">${scoreTone(score)}</span>
        <strong>${(options.fit ? rankScore : score).toFixed(1)}</strong>
        <span class="small-text">${options.fit ? "排序分" : "/ 5.0"}</span>
      </div>
    </article>
  `;
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function renderMetrics() {
  const target = state.summary.recommendation_target || 20;
  document.getElementById("recommendedMetric").textContent = `${Math.min(state.summary.today_recommended || 0, target)}/${target}`;
  document.getElementById("queueMetric").textContent = state.summary.apply_queue || 0;
  document.getElementById("appliedMetric").textContent = state.summary.today_applied || 0;
  document.getElementById("totalMetric").textContent = state.summary.total || 0;
}

function scanRunSummary(run) {
  if (!run) return "今天还没有扫描记录。";
  const failures = Array.isArray(run.failures_json) ? run.failures_json.length : 0;
  return `最近扫描 ${SCAN_STATUS_ZH[run.status] || run.status}：抓到 ${run.scanned_count || 0} 条，保存/更新 ${run.saved_count || 0} 条，推荐 ${run.recommended_count || 0} 条。失败/受限：${failures} 条。`;
}

function renderScanRun(payload = {}) {
  const run = payload.run || state.daily.latest_run;
  const expectedDetails = payload.expected_source_details || state.scan.expected_source_details || [];
  const expected = payload.expected_sources || state.scan.expected_sources || expectedDetails.map((item) => item.source) || ["LinkedIn（含 AI 关键词）", "InternSG（含 AI 关键词）", "Indeed", "JobStreet", "公司官网"];
  const sourceModes = new Map(expectedDetails.map((item) => [scanSourceLabel(item.source), item.mode]));
  const status = document.getElementById("scanStatus");
  const pill = document.getElementById("scanStatusPill");
  const progress = document.getElementById("scanProgress");
  const scanBtn = document.getElementById("scanBtn");

  if (status) status.textContent = scanRunSummary(run);
  const runStatus = run?.status || "pending";
  if (pill) {
    pill.className = `status-pill ${runStatus}`;
    pill.textContent = SCAN_STATUS_ZH[runStatus] || "待命";
  }
  if (scanBtn && runStatus === "running") {
    setButtonState(scanBtn, "loading", "扫描中...");
  } else if (scanBtn) {
    setButtonState(scanBtn, "idle");
  }

  const aggregate = new Map();
  expected.map((item) => typeof item === "string" ? scanSourceLabel(item) : scanSourceLabel(item.source)).forEach((source) => {
    aggregate.set(source, { source, status: "pending", mode: sourceModes.get(source) || "primary", scanned_count: 0, saved_count: 0, failure_count: 0 });
  });
  (run?.sources || []).forEach((item) => {
    const source = scanSourceLabel(item.source);
    const existing = aggregate.get(source) || { source, status: "pending", mode: item.mode || sourceModes.get(source) || "primary", scanned_count: 0, saved_count: 0, failure_count: 0 };
    existing.status = mergeScanStatus(existing.status, item.status || "pending");
    existing.mode = item.mode || existing.mode;
    existing.scanned_count += Number(item.scanned_count || 0);
    existing.saved_count += Number(item.saved_count || 0);
    existing.failure_count += Number(item.failure_count || 0);
    aggregate.set(source, existing);
  });
  const sourceRows = Array.from(aggregate.values()).map((row) => ({
    source: row.source,
    row,
    label: SCAN_STATUS_ZH[row.status] || row.status,
  }));
  const shouldExpandSources = ["running", "partial", "limited", "failed"].includes(runStatus);
  const problemRows = sourceRows.filter(({ row }) => ["failed", "partial", "limited"].includes(row.status) || Number(row.failure_count || 0) > 0);
  const visibleRows = shouldExpandSources ? sourceRows : problemRows;
  progress.className = `source-progress ${shouldExpandSources ? "is-expanded" : "is-compact"}`;
  progress.innerHTML = visibleRows.length ? visibleRows.map(({ source, row, label }) => `
      <div class="source-row ${escapeHtml(row.status || "pending")}">
        <span class="source-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(source)}</strong>
          <span>${escapeHtml(scanModeLabel(row.mode))} · ${row.scanned_count || 0} 抓到 · ${row.saved_count || 0} 保存 · ${row.failure_count || 0} 失败</span>
        </div>
        <span class="status-pill ${row.status}">${escapeHtml(label)}</span>
      </div>
    `).join("") : `
      <div class="source-summary">
        ${runStatus === "success" ? `${sourceRows.length} 个来源已检查，暂无失败来源。` : "来源明细会在扫描运行时展开。"}
      </div>
    `;

  const latestSuccess = state.daily.latest_successful_run;
  document.getElementById("lastSuccessText").textContent = `上次成功：${latestSuccess ? formatDateTime(latestSuccess.finished_at || latestSuccess.started_at) : "-"}`;
  const failureCount = Array.isArray(run?.failures_json) ? run.failures_json.length : 0;
  document.getElementById("failureText").textContent = `失败/受限：${failureCount}`;
}

function startScanPolling(runId) {
  if (!runId) return;
  if (state.scanPollTimer) window.clearInterval(state.scanPollTimer);
  state.scanPollTimer = window.setInterval(async () => {
    try {
      const payload = await api(`/api/scan-runs/${runId}`);
      state.scan = payload;
      renderScanRun(payload);
      if (!payload.running) {
        window.clearInterval(state.scanPollTimer);
        state.scanPollTimer = null;
        toast("扫描完成，推荐列表已刷新。", payload.run?.status === "failed" ? "error" : "success");
        await refresh();
      }
    } catch (error) {
      window.clearInterval(state.scanPollTimer);
      state.scanPollTimer = null;
      toast(error.message, "error");
    }
  }, 1800);
}

function renderCareerSnapshot() {
  const analysis = state.careerFit.analysis;
  const selected = state.careerFit.selected_directions || [];
  const all = state.careerFit.all_directions || [];
  const labels = selected.length
    ? all.filter((item) => selected.includes(item.id))
    : (state.careerFit.suggested_directions || []).slice(0, 3);
  document.getElementById("careerSnapshotText").textContent = analysis?.summary || "上传或分析简历后，这里会显示适合投递的岗位方向。";
  const action = `<button class="secondary-button compact-button" data-nav-fit>${labels.length ? "调整定位" : "上传简历定位"}</button>`;
  document.getElementById("careerSnapshotChips").innerHTML = labels.length
    ? labels.map((item) => `<span class="chip-label active">${escapeHtml(item.label)}</span>`).join("") + action
    : action;
}

function renderCareerFit() {
  const fit = state.careerFit || {};
  const analysis = fit.analysis;
  const active = fit.active_resume || {};
  const selected = new Set(fit.selected_directions || []);
  const suggestedScores = new Map((fit.suggested_directions || []).map((item) => [item.id, item.score]));

  document.getElementById("activeResume").textContent = active.stored_path
    ? `当前简历：${active.original_filename || active.filename || fileName(active.stored_path)} · ${active.stored_path}`
    : "当前还没有可分析的简历。";
  document.getElementById("careerFitSummary").textContent = analysis?.summary || "还没有分析结果。上传简历或点击本地分析后，这里会生成适合投递的方向。";
  document.getElementById("directionChips").innerHTML = (fit.all_directions || []).map((direction) => {
    const score = suggestedScores.has(direction.id) ? ` ${Math.round(suggestedScores.get(direction.id) * 100)}%` : "";
    return `<button class="chip-button ${selected.has(direction.id) ? "active" : ""}" data-direction-id="${escapeHtml(direction.id)}">${escapeHtml(direction.label)}${score}</button>`;
  }).join("");

  const strengths = analysis?.strengths || [];
  document.getElementById("strengthList").innerHTML = strengths.length
    ? strengths.map((item) => `
        <div class="insight-item">
          <strong>${escapeHtml(item.label || "能力")}</strong>
          ${escapeHtml((item.evidence_terms || []).join(", ") || (item.snippets || []).join(" "))}
        </div>
      `).join("")
    : emptyState("还没有能力证据。");

  const gaps = analysis?.gaps || [];
  document.getElementById("gapList").innerHTML = gaps.length
    ? gaps.map((item) => `
        <div class="insight-item">
          <strong>${escapeHtml(item.direction || "补强项")}</strong>
          ${escapeHtml((item.items || []).join("；"))}
        </div>
      `).join("")
    : emptyState("暂时没有明显缺口，或需要更多简历文本。");

  const evidence = analysis?.evidence || [];
  document.getElementById("evidenceList").innerHTML = evidence.length
    ? evidence.map((item) => `
        <div class="insight-item">
          <strong>${escapeHtml(item.direction || "证据")}</strong>
          ${escapeHtml(item.text || "")}
        </div>
      `).join("")
    : emptyState("分析后会显示简历里被系统引用的证据片段。");

  renderCareerSnapshot();
}

function renderRecommendationContext() {
  const source = state.recommendations.direction_source;
  const count = state.recommendations.active_direction_ids?.length || 0;
  if (source === "user_context") {
    document.getElementById("recommendationContext").textContent = `正在按画像里的 ${count} 个方向、地区、工作类型和薪资偏好重排；薪资不匹配只降权不隐藏。`;
    return;
  }
  const text = source === "user_selected"
    ? `正在按你选择的 ${count} 个方向重排；工作类型、薪资和可转正只做软排序。`
    : source === "resume_analysis"
      ? `还没有手动选择方向，系统暂时按简历分析出的 ${count} 个方向重排。`
      : "还没有职业定位偏好，当前按基础 5.0 评分排序。";
  document.getElementById("recommendationContext").textContent = text;
}

function renderJobs() {
  const aiIds = new Set(state.aiJobs.map((job) => job.id));
  const fitJobs = (state.recommendations.jobs || []).filter((job) => isRecommendationCandidate(job)).slice(0, 20);
  const aiJobs = state.aiJobs.filter((job) => isRecommendationCandidate(job)).slice(0, 20);
  const visible = state.jobs
    .filter((job) => !state.activeFilter ? isRecommendationCandidate(job) : job.status === state.activeFilter)
    .filter((job) => !aiIds.has(job.id));
  const generalJobs = visible.slice(0, 20);

  document.querySelectorAll("[data-recommendation-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.recommendationView === state.recommendationView);
  });
  document.getElementById("fitJobCount").textContent = fitJobs.length;
  document.getElementById("aiJobCount").textContent = aiJobs.length;
  document.getElementById("generalJobCount").textContent = generalJobs.length;
  renderRecommendationContext();

  const fitList = document.getElementById("fitJobList");
  const aiList = document.getElementById("aiJobList");
  const generalList = document.getElementById("jobList");
  fitList.hidden = state.recommendationView !== "fit";
  aiList.hidden = state.recommendationView !== "ai";
  generalList.hidden = state.recommendationView !== "general";
  fitList.innerHTML = fitJobs.length ? fitJobs.map((job) => jobCard(job, false, { fit: true })).join("") : emptyState("还没有可推荐岗位。先扫描或设置职业定位。");
  aiList.innerHTML = aiJobs.length ? aiJobs.map((job) => jobCard(job, false, { ai: true })).join("") : emptyState("暂时没有 3.0 分以上的 AI 相关岗位。");
  generalList.innerHTML = generalJobs.length ? generalJobs.map((job) => jobCard(job)).join("") : emptyState("还没有岗位。请点击开始自动扫描。");

  const queue = state.jobs.filter((job) => job.status === "Apply Queue");
  document.getElementById("queueList").innerHTML = queue.length
    ? queue.slice(0, 15).map((job) => jobCard(job, true)).join("")
    : emptyState("投递队列为空。你可以从今日推荐里选择“加入投递”。");
  document.getElementById("queueMiniCount").textContent = queue.length;
  document.getElementById("queueMiniList").innerHTML = queue.length
    ? queue.slice(0, 5).map((job) => `<div class="mini-item"><strong>${escapeHtml(job.company)}</strong><span class="small-text">${escapeHtml(job.position)}</span></div>`).join("")
    : `<div class="mini-item"><span class="small-text">还没有待投递岗位。</span></div>`;

  renderTrackerRows();
}

function filterTrackerJobs() {
  return state.jobs
    .filter((job) => {
      const dates = trackerDates(job);
      if (state.trackerMode === "day") return dates.includes(state.trackerDate);
      if (state.trackerMode === "month") return dates.some((date) => date.startsWith(state.trackerMonth));
      return true;
    })
    .sort((a, b) => timelineDate(b).localeCompare(timelineDate(a)) || Number(b.score) - Number(a.score));
}

function renderTrackerControls(filteredCount) {
  document.querySelectorAll(".tracker-mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.trackerMode === state.trackerMode);
  });
  const dateLabel = document.getElementById("trackerDateLabel");
  const monthLabel = document.getElementById("trackerMonthLabel");
  const dateInput = document.getElementById("trackerDateInput");
  const monthInput = document.getElementById("trackerMonthInput");
  dateInput.value = state.trackerDate;
  monthInput.value = state.trackerMonth;
  dateLabel.hidden = state.trackerMode !== "day";
  monthLabel.hidden = state.trackerMode !== "month";
  dateInput.disabled = state.trackerMode !== "day";
  monthInput.disabled = state.trackerMode !== "month";
  const label = state.trackerMode === "day" ? `${state.trackerDate} 的岗位` : state.trackerMode === "month" ? `${state.trackerMonth} 整月岗位` : "全部岗位";
  document.getElementById("trackerCount").textContent = `${label}：${filteredCount}/${state.jobs.length}`;
}

function renderTrackerRows() {
  const jobs = filterTrackerJobs();
  renderTrackerControls(jobs.length);
  document.getElementById("trackerRows").innerHTML = jobs.length
    ? jobs.map((job) => `
        <tr>
          <td>${escapeHtml(job.name)}</td>
          <td>${escapeHtml(statusLabel(job.status))}</td>
          <td>${Number(job.score).toFixed(1)}</td>
          <td>${escapeHtml(timelineDate(job) || "-")}</td>
          <td>${escapeHtml(job.found_date || "-")}</td>
          <td>${escapeHtml(job.batch_date || "-")}</td>
          <td>${escapeHtml(job.applied_date || "-")}</td>
          <td><a href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">${escapeHtml(job.url)}</a></td>
        </tr>
      `).join("")
    : `<tr><td colspan="8">这个时间范围里还没有岗位记录。</td></tr>`;
}

function aliasesForCompany(company) {
  return COMPANY_ALIASES[company] || [company];
}

function jobsForCompany(company) {
  const aliases = aliasesForCompany(company).map((item) => item.toLowerCase());
  return state.jobs
    .filter((job) => aliases.some((alias) => `${job.company} ${job.name}`.toLowerCase().includes(alias)))
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
}

function renderCompanyJobs() {
  const title = document.getElementById("companyJobsTitle");
  const container = document.getElementById("companyJobs");
  if (!state.selectedCompany) {
    title.textContent = "选择一家公司查看岗位";
    container.innerHTML = emptyState("点击上方公司卡片后，这里会显示该公司相关岗位。");
    return;
  }
  const jobs = jobsForCompany(state.selectedCompany);
  title.textContent = `${state.selectedCompany} 相关岗位`;
  container.innerHTML = jobs.length ? jobs.map((job) => jobCard(job)).join("") : emptyState("暂时没有抓到这家公司可展示岗位。");
}

function renderWatchlist() {
  const watched = document.getElementById("companyList");
  const catalog = document.getElementById("companyCatalog");
  watched.innerHTML = state.watchlist.length ? state.watchlist.map((company) => `
    <article class="company-item ${state.selectedCompany === company.company ? "active" : ""}" data-company="${escapeHtml(company.company)}">
      <button class="company-select" data-company="${escapeHtml(company.company)}">
        <span>
          <h3>${escapeHtml(company.company)}</h3>
          <p class="small-text">${escapeHtml(company.focus)}</p>
          <span class="badge-row">
            <span class="badge">${escapeHtml(company.region || activeRegion())}</span>
            <span class="badge">${escapeHtml(company.company_type || company.source)}</span>
            <span class="badge">${escapeHtml(company.source)}</span>
          </span>
          <span class="job-url">${escapeHtml(company.url)}</span>
        </span>
      </button>
      <button class="tertiary-button compact-button" data-watch-action="remove" data-watch-id="${company.id}">取消关注</button>
    </article>
  `).join("") : emptyState("还没有关注公司。可以从右侧推荐里选择，或粘贴官网招聘链接。");

  const recommended = (state.companyCatalog || []).filter((company) => !company.watched);
  catalog.innerHTML = recommended.length ? recommended.map((company) => `
    <article class="company-item catalog-item">
      <div>
        <h3>${escapeHtml(company.company)}</h3>
        <p class="small-text">${escapeHtml(company.focus)}</p>
        <span class="badge-row">
          <span class="badge">${escapeHtml(company.company_type || "Company")}</span>
          <span class="badge">${escapeHtml((company.city_tags || []).join(", "))}</span>
          ${(company.tags || []).slice(0, 2).map((tag) => `<span class="badge fit-badge">${escapeHtml(tag)}</span>`).join("")}
          ${company.language_signal ? `<span class="badge salary-badge">${escapeHtml(company.language_signal)}</span>` : ""}
        </span>
        ${company.recommend_reason ? `<p class="company-reason">${escapeHtml(company.recommend_reason)}</p>` : ""}
        <span class="job-url">${escapeHtml(company.url)}</span>
      </div>
      <button class="secondary-button compact-button" data-watch-action="add-catalog" data-company="${escapeHtml(company.company)}">关注</button>
    </article>
  `).join("") : emptyState("当前地区推荐公司都已关注。");
  renderCompanyJobs();
}

async function renderNotionSchema() {
  try {
    const [schema, status] = await Promise.all([api("/api/notion-schema"), api("/api/notion-status")]);
    state.notionStatus = status;
    const required = schema.required.map((field) => `
      <article class="schema-item">
        <h3>${escapeHtml(field.name)}</h3>
        <p class="small-text">${escapeHtml(field.type)}</p>
        <p>${escapeHtml(field.purpose)}</p>
      </article>
    `).join("");
    const tokenLabel = status.token_configured ? "Token 已写入本地配置" : "缺少 Notion token";
    const databaseLabel = status.database_id_configured ? "Database ID 已写入本地配置" : "缺少 database ID";
    document.getElementById("notionConfigStatus").innerHTML = `
      <span class="config-pill ${status.token_configured ? "ok" : "warn"}">${escapeHtml(tokenLabel)}</span>
      <span class="config-pill ${status.database_id_configured ? "ok" : "warn"}">${escapeHtml(databaseLabel)}</span>
      <span class="small-text">${status.env_file ? "配置文件：" + escapeHtml(status.env_file) : "还没有本地配置文件"}</span>
    `;
    document.getElementById("notionSchema").innerHTML = required + `
      <article class="schema-item">
        <h3>推荐字段</h3>
        <p class="small-text">${schema.recommended.map(escapeHtml).join(", ")}</p>
      </article>
    `;
  } catch (error) {
    document.getElementById("notionSchema").innerHTML = emptyState(error.message);
  }
}

function renderProfileForm() {
  const form = document.getElementById("profileForm");
  if (!form || !state.profile) return;
  Object.entries(state.profile).forEach(([key, value]) => {
    const field = form.elements[key];
    if (!field || Array.isArray(value) || typeof value === "object") return;
    field.value = value ?? "";
  });
}

async function refresh() {
  const [regions, userContext] = await Promise.all([
    api("/api/regions"),
    api("/api/user-context"),
  ]);
  state.regions = regions;
  state.userContext = userContext;
  const region = activeRegion();
  const regionParam = `region=${encodeURIComponent(region)}`;
  state.profileOptions = await api(`/api/profile-options?${regionParam}`);
  const [summary, jobs, aiJobs, watchlist, daily, profile, careerFit, recommendations, scanStatus, companyCatalog] = await Promise.all([
    api("/api/summary"),
    api(`/api/jobs?${regionParam}`),
    api(`/api/jobs/ai?limit=20&${regionParam}`),
    api(`/api/watchlist?${regionParam}`),
    api(`/api/daily/status?${regionParam}`),
    api("/api/profile"),
    api("/api/career-fit"),
    api(`/api/recommendations/today?limit=20&${regionParam}`),
    api(`/api/scan/status?${regionParam}`),
    api(`/api/company-catalog?${regionParam}`),
  ]);
  state.summary = summary;
  state.jobs = jobs;
  state.aiJobs = aiJobs;
  state.watchlist = watchlist;
  state.daily = daily;
  state.profile = profile;
  state.careerFit = careerFit;
  state.recommendations = recommendations;
  state.scan = scanStatus;
  state.companyCatalog = companyCatalog;
  setTrackerDefaults();
  renderUserContextControls();
  renderMetrics();
  renderScanRun(scanStatus);
  renderCareerFit();
  renderJobs();
  renderWatchlist();
  renderProfileForm();
  await renderNotionSchema();
  if (scanStatus.running && scanStatus.run?.id) startScanPolling(scanStatus.run.id);
}

async function checkDailyAutoRun() {
  if (state.dailyRunChecked) return;
  state.dailyRunChecked = true;
  if (state.daily.has_successful_scan) {
    renderScanRun(state.scan);
    return;
  }
  try {
    const result = await api("/api/daily/run", {
      method: "POST",
      body: JSON.stringify({ force: false, triggered_by: "auto_open", async: true, region: activeRegion() }),
    });
    if (result.skipped) {
      renderScanRun({ run: result.scan_run, expected_sources: state.scan.expected_sources });
      return;
    }
    state.scan = result;
    renderScanRun(result);
    if (result.run?.id) {
      toast("今天还没有成功扫描，已在后台补跑。", "success");
      startScanPolling(result.run.id);
    }
  } catch (error) {
    toast(`今日自动扫描失败：${error.message}`, "error");
  }
}

async function scanJobs(event) {
  const button = event.currentTarget;
  setButtonState(button, "loading", "启动扫描...");
  try {
    const result = await api("/api/scan/async", {
      method: "POST",
      body: JSON.stringify({ force: true, triggered_by: "manual", region: activeRegion() }),
    });
    state.scan = result;
    renderScanRun(result);
    toast(result.started ? "扫描已开始，来源进度会自动更新。" : "已有扫描正在运行。", "success");
    if (result.run?.id) startScanPolling(result.run.id);
  } catch (error) {
    setButtonState(button, "error", error.message);
    toast(error.message, "error");
    window.setTimeout(() => setButtonState(button, "idle"), 1600);
  }
}

async function submitProfile(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  await withButton(button, "保存中...", async () => {
    state.profile = await api("/api/profile", { method: "POST", body: JSON.stringify(payload) });
    renderProfileForm();
    toast("资料已保存。", "success");
  }, "已保存");
}

async function submitUserContext(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  syncContextCustomInputs(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  const active_region = payload.active_region || activeRegion();
  const target_directions = splitList(payload.target_directions);
  await withButton(button, "保存中...", async () => {
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({
        active_region,
        context: {
          city: payload.city,
          work_authorisation: payload.work_authorisation,
          target_directions,
          job_types: splitList(payload.job_types),
          employment_priority: payload.employment_priority,
          salary_currency: state.profileOptions.salary_currency || payload.salary_currency,
          salary_period: payload.salary_period,
          salary_min: payload.salary_min,
          salary_preferred: payload.salary_preferred,
        },
        onboarding_completed: true,
      }),
    });
    if (target_directions.length) {
      await api("/api/career-fit/preferences", {
        method: "PUT",
        body: JSON.stringify({ selected_directions: target_directions }),
      });
    }
    state.dailyRunChecked = false;
    await refreshFocusData("求职画像已更新，今日推荐已重排。");
  }, "已保存");
}

async function submitOnboarding(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  syncOnboardingCustomInputs(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  const active_region = payload.active_region || activeRegion();
  const target_directions = splitList(payload.target_directions);
  const status = document.getElementById("onboardingStatus");
  await withButton(button, "保存中...", async () => {
    const fileInput = document.getElementById("onboardingResumeInput");
    if (fileInput?.files?.length) {
      const resumeData = new FormData();
      resumeData.append("resume", fileInput.files[0]);
      await api("/api/resumes", { method: "POST", body: resumeData });
    }
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({
        active_region,
        context: {
          target_directions,
          employment_priority: payload.employment_priority,
          salary_currency: state.profileOptions.salary_currency,
          salary_period: payload.salary_period,
          salary_min: payload.salary_min,
          salary_preferred: payload.salary_preferred,
        },
        onboarding_completed: true,
      }),
    });
    if (target_directions.length) {
      await api("/api/career-fit/preferences", {
        method: "PUT",
        body: JSON.stringify({ selected_directions: target_directions }),
      });
    }
    state.dailyRunChecked = false;
    await refresh();
    status.textContent = "设置已保存。";
    toast("首次设置已保存。", "success");
  }, "已保存");
}

async function skipOnboarding(event) {
  const button = event.currentTarget;
  const form = document.getElementById("onboardingForm");
  const active_region = form?.elements.active_region.value || activeRegion();
  await withButton(button, "跳过中...", async () => {
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({ active_region, onboarding_completed: true }),
    });
    await refresh();
    toast("已跳过首次设置，之后可在资料页修改。", "success");
  }, "已跳过");
}

async function refreshFocusData(message = "推荐已按新画像重排。") {
  const regionParam = regionQuery();
  const target = document.getElementById("jobFocusPanel");
  target?.classList.add("is-updating");
  document.querySelector(".recommendation-switch-head")?.classList.add("is-updating");
  try {
    const [summary, jobs, aiJobs, recommendations, scanStatus, watchlist, companyCatalog] = await Promise.all([
      api("/api/summary"),
      api(`/api/jobs?${regionParam}`),
      api(`/api/jobs/ai?limit=20&${regionParam}`),
      api(`/api/recommendations/today?limit=20&${regionParam}`),
      api(`/api/scan/status?${regionParam}`),
      api(`/api/watchlist?${regionParam}`),
      api(`/api/company-catalog?${regionParam}`),
    ]);
    state.summary = summary;
    state.jobs = jobs;
    state.aiJobs = aiJobs;
    state.recommendations = recommendations;
    state.scan = scanStatus;
    state.watchlist = watchlist;
    state.companyCatalog = companyCatalog;
    renderUserContextControls();
    renderMetrics();
    renderScanRun(scanStatus);
    renderJobs();
    renderWatchlist();
    toast(message, "success");
  } finally {
    window.setTimeout(() => {
      target?.classList.remove("is-updating");
      document.querySelector(".recommendation-switch-head")?.classList.remove("is-updating");
    }, 360);
  }
}

function scheduleFocusRefresh(message) {
  if (state.focusRefreshTimer) window.clearTimeout(state.focusRefreshTimer);
  state.focusRefreshTimer = window.setTimeout(() => {
    refreshFocusData(message).catch((error) => toast(error.message, "error"));
  }, 280);
}

async function changeRegion(region) {
  await api("/api/user-context", {
    method: "PUT",
    body: JSON.stringify({ active_region: region }),
  });
  state.selectedCompany = "";
  state.dailyRunChecked = false;
  await refresh();
}

async function quickUpdateEmploymentPriority(priority) {
  const context = activeRegionContext();
  context.employment_priority = priority;
  renderUserContextControls();
  state.userContext = await api("/api/user-context", {
    method: "PUT",
    body: JSON.stringify({
      active_region: activeRegion(),
      context: {
        employment_priority: priority,
        salary_currency: context.salary_currency || state.profileOptions.salary_currency,
      },
      onboarding_completed: true,
    }),
  });
  scheduleFocusRefresh(`已切换为「${optionLabel(state.profileOptions.employment_priority_options, priority)}」，岗位正在重排。`);
}

function catalogCompany(companyName) {
  return (state.companyCatalog || []).find((item) => item.company === companyName);
}

async function submitCompany(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.region = activeRegion();
  await withButton(button, "添加中...", async () => {
    await api("/api/watchlist", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    state.selectedCompany = payload.company;
    await refresh();
    toast("公司已加入雷达。", "success");
  }, "已添加");
}

async function handleWatchAction(event) {
  const button = event.target.closest("[data-watch-action]");
  if (!button) return;
  const action = button.dataset.watchAction;
  if (action === "add-catalog") {
    const item = catalogCompany(button.dataset.company);
    if (!item) return;
    await withButton(button, "关注中...", async () => {
      await api("/api/watchlist", {
        method: "POST",
        body: JSON.stringify({ ...item, region: activeRegion(), user_added: false }),
      });
      state.selectedCompany = item.company;
      await refresh();
      toast(`${item.company} 已加入公司雷达。`, "success");
    }, "已关注");
  }
  if (action === "remove") {
    await withButton(button, "取消中...", async () => {
      await api(`/api/watchlist/${button.dataset.watchId}`, { method: "DELETE" });
      state.selectedCompany = "";
      await refresh();
      toast("已取消关注。", "success");
    }, "已取消");
  }
}

async function uploadResume(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  const fileInput = document.getElementById("resumeInput");
  const status = document.getElementById("resumeStatus");
  if (!fileInput.files.length) {
    status.textContent = "请选择 PDF、DOCX 或 MD 简历。";
    return;
  }
  await withButton(button, "上传并分析...", async () => {
    const formData = new FormData(form);
    await api("/api/resumes", { method: "POST", body: formData });
    state.careerFit = await api("/api/career-fit");
    state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}`);
    renderCareerFit();
    renderJobs();
    status.textContent = "已上传并完成本地分析。";
    toast("简历已上传，职业定位已更新。", "success");
  }, "已分析");
}

async function analyzeCareerFit(mode, button) {
  await withButton(button, mode === "ai" ? "AI 分析中..." : "本地分析中...", async () => {
    await api("/api/career-fit/analyze", { method: "POST", body: JSON.stringify({ mode }) });
    state.careerFit = await api("/api/career-fit");
    state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}`);
    renderCareerFit();
    renderJobs();
    toast(mode === "ai" ? "AI 深度分析已完成。" : "本地分析已完成。", "success");
  }, "已分析");
}

async function toggleDirection(directionId) {
  const selected = new Set(state.careerFit.selected_directions || []);
  if (selected.has(directionId)) selected.delete(directionId);
  else selected.add(directionId);
  const result = await api("/api/career-fit/preferences", {
    method: "PUT",
    body: JSON.stringify({ selected_directions: Array.from(selected) }),
  });
  state.careerFit = result.career_fit;
  state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}`);
  renderCareerFit();
  renderJobs();
  toast("今日推荐排序已更新。", "success");
}

async function submitJob(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.region = activeRegion();
  payload.city = activeRegionContext().city || activeRegionConfig().default_city || "";
  await withButton(button, "评分并保存...", async () => {
    const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await refresh();
    toast(`已保存：${job.company}，评分 ${Number(job.score).toFixed(1)}/5.0`, "success");
  }, "已保存");
}

async function handleJobAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  const id = button.dataset.id;
  if (action === "detail") {
    await showDetail(Number(id));
    return;
  }
  if (action === "assist") {
    await withButton(button, "打开浏览器...", async () => {
      const result = await api(`/api/jobs/${id}/apply-assist`, { method: "POST", body: "{}" });
      toast(result.message || "填表助手已打开。最终提交前请逐项检查。", "success");
      await refresh();
    }, "已打开");
    return;
  }
  if (action === "confirm") {
    await withButton(button, "确认中...", async () => {
      await api(`/api/jobs/${id}/confirm-applied`, { method: "POST", body: "{}" });
      await refresh();
      toast("已记录为已投递。", "success");
    }, "已确认");
    return;
  }
  await withButton(button, "更新中...", async () => {
    await api(`/api/jobs/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: action }) });
    await refresh();
    toast(action === "Apply" ? "已加入投递队列。" : action === "Watch" ? "已加入关注。" : "已放弃并不会再推荐。", "success");
  }, "已更新");
}

function materialPathTemplate(label, path) {
  if (!path) {
    return `<div class="material-item"><span class="small-text">${escapeHtml(label)}：加入投递后自动生成</span></div>`;
  }
  return `
    <div class="material-item">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span class="job-url">${escapeHtml(path)}</span>
      </div>
      <div class="material-actions">
        <button class="tertiary-button" data-open-path="${escapeHtml(path)}" data-open-mode="file">打开文件</button>
        <button class="tertiary-button" data-open-path="${escapeHtml(path)}" data-open-mode="folder">打开文件夹</button>
      </div>
    </div>
  `;
}

function detailTemplate(job, cnText) {
  return `
    <div class="detail-block">
      <h3>记录</h3>
      <p class="small-text">状态 ${escapeHtml(statusLabel(job.status))} · 评分 ${Number(job.score).toFixed(1)}/5.0</p>
      <a class="job-url" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">${escapeHtml(job.url)}</a>
    </div>
    <div class="detail-block">
      <h3>匹配说明</h3>
      <p>${escapeHtml(job.match_notes || "暂无匹配说明。")}</p>
    </div>
    <div class="detail-block">
      <h3>中文 JD</h3>
      <pre>${escapeHtml(cnText || "正在生成中文 JD，请稍等...")}</pre>
    </div>
    <div class="detail-block">
      <h3>材料路径</h3>
      <div class="material-list">
        ${materialPathTemplate("简历", job.resume_path)}
        ${materialPathTemplate("Cover letter", job.cover_letter_path)}
      </div>
    </div>
    <div class="detail-block">
      <h3>原始 JD</h3>
      <pre>${escapeHtml(job.jd_text)}</pre>
    </div>
  `;
}

async function showDetail(id) {
  const baseJob = state.jobs.find((item) => item.id === id) || await api(`/api/jobs/${id}`);
  document.getElementById("detailTitle").textContent = `${baseJob.company} - ${baseJob.position}`;
  document.getElementById("detailBody").innerHTML = detailTemplate(baseJob, baseJob.jd_cn_text);
  document.getElementById("detailDialog").showModal();
  if (!baseJob.jd_cn_text) {
    try {
      const translatedJob = await api(`/api/jobs/${id}/translate`, { method: "POST", body: "{}" });
      document.getElementById("detailBody").innerHTML = detailTemplate(translatedJob, translatedJob.jd_cn_text);
      const index = state.jobs.findIndex((job) => job.id === translatedJob.id);
      if (index >= 0) state.jobs[index] = translatedJob;
    } catch (error) {
      document.getElementById("detailBody").innerHTML = detailTemplate(baseJob, `中文 JD 生成失败：${error.message}`);
    }
  }
}

async function handleOpenPath(event) {
  const button = event.target.closest("button[data-open-path]");
  if (!button) return;
  await withButton(button, "正在打开...", async () => {
    await api("/api/open-path", {
      method: "POST",
      body: JSON.stringify({ path: button.dataset.openPath, mode: button.dataset.openMode || "folder" }),
    });
  }, "已打开");
}

async function makeReport(event) {
  await withButton(event.currentTarget, "生成中...", async () => {
    const report = await api("/api/report/today");
    toast(`日报已保存：${report.path}`, "success");
    await refresh();
  }, "已生成");
}

async function syncNotion(event) {
  await withButton(event.currentTarget, "同步中...", async () => {
    const result = await api("/api/notion/sync", { method: "POST", body: "{}" });
    document.getElementById("notionStatus").textContent = `已同步 ${result.synced}/${result.total} 个投递岗位；跳过 ${result.skipped || 0} 个；失败：${result.failures.length}`;
    await refresh();
  }, "已同步");
}

function showView(view) {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  document.querySelectorAll(".view").forEach((panel) => panel.classList.remove("active"));
  document.getElementById(`${view}View`).classList.add("active");
}

function handleOptionChip(event) {
  const button = event.target.closest("[data-option-target]");
  if (!button) return;
  const [scope, field] = button.dataset.optionTarget.split(":");
  const value = button.dataset.optionValue;
  const multi = button.dataset.optionMulti !== "false";
  if (scope === "focus" && field === "employment_priority") {
    quickUpdateEmploymentPriority(value).catch((error) => toast(error.message, "error"));
    return;
  }
  const form = document.getElementById(scope === "onboarding" ? "onboardingForm" : "contextForm");
  if (!form?.elements?.[field]) return;
  const next = toggleValue(selectedValuesFromHidden(form, field), value, multi);
  setHiddenList(form, field, next);
  const context = activeRegionContext();
  context[field] = multi ? next : (next[0] || "");
  renderUserContextControls();
}

function syncSalaryPeriodControls(scope) {
  const form = document.getElementById(scope === "onboarding" ? "onboardingForm" : "contextForm");
  const periodSelect = document.getElementById(scope === "onboarding" ? "onboardingSalaryPeriod" : "contextSalaryPeriod");
  const minSelect = document.getElementById(scope === "onboarding" ? "onboardingSalaryMin" : "contextSalaryMin");
  const preferredSelect = document.getElementById(scope === "onboarding" ? "onboardingSalaryPreferred" : "contextSalaryPreferred");
  if (!form || !periodSelect) return;
  const context = activeRegionContext();
  const salaryBands = salaryBandsForPeriod(periodSelect.value || "monthly");
  setSelectOptions(minSelect, salaryBands, form.elements.salary_min?.value ?? context.salary_min ?? "");
  setSelectOptions(preferredSelect, salaryBands, form.elements.salary_preferred?.value ?? context.salary_preferred ?? "");
}

function bindEvents() {
  document.getElementById("jobForm").addEventListener("submit", submitJob);
  document.getElementById("profileForm").addEventListener("submit", submitProfile);
  document.getElementById("contextForm").addEventListener("submit", submitUserContext);
  document.getElementById("onboardingForm").addEventListener("submit", submitOnboarding);
  document.getElementById("skipOnboardingBtn").addEventListener("click", skipOnboarding);
  document.getElementById("companyAddForm").addEventListener("submit", submitCompany);
  document.getElementById("resumeUploadForm").addEventListener("submit", uploadResume);
  document.getElementById("focusRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("contextRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("onboardingRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("contextSalaryPeriod").addEventListener("change", () => syncSalaryPeriodControls("context"));
  document.getElementById("onboardingSalaryPeriod").addEventListener("change", () => syncSalaryPeriodControls("onboarding"));
  document.getElementById("scanBtn").addEventListener("click", scanJobs);
  document.getElementById("reportBtn").addEventListener("click", makeReport);
  document.getElementById("notionSyncBtn").addEventListener("click", syncNotion);
  document.getElementById("localAnalyzeBtn").addEventListener("click", (event) => analyzeCareerFit("local", event.currentTarget));
  document.getElementById("aiAnalyzeBtn").addEventListener("click", (event) => analyzeCareerFit("ai", event.currentTarget));
  document.getElementById("closeDialog").addEventListener("click", () => document.getElementById("detailDialog").close());
  document.body.addEventListener("click", handleJobAction);
  document.body.addEventListener("click", handleOpenPath);
  document.body.addEventListener("click", handleWatchAction);
  document.body.addEventListener("click", handleOptionChip);
  document.body.addEventListener("click", (event) => {
    if (event.target.closest("[data-nav-fit]")) showView("fit");
    const chip = event.target.closest("[data-direction-id]");
    if (chip) toggleDirection(chip.dataset.directionId);
  });
  document.getElementById("companyList").addEventListener("click", (event) => {
    const card = event.target.closest("[data-company]");
    if (!card) return;
    if (event.target.closest("[data-watch-action]")) return;
    state.selectedCompany = card.dataset.company;
    renderWatchlist();
  });
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-recommendation-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.recommendationView = button.dataset.recommendationView;
      renderJobs();
    });
  });
  document.querySelectorAll(".tracker-mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.trackerMode = button.dataset.trackerMode;
      renderJobs();
    });
  });
  document.getElementById("trackerDateInput").addEventListener("change", (event) => {
    state.trackerDate = event.target.value;
    state.trackerMode = "day";
    renderJobs();
  });
  document.getElementById("trackerMonthInput").addEventListener("change", (event) => {
    state.trackerMonth = event.target.value;
    state.trackerMode = "month";
    renderJobs();
  });
}

async function boot() {
  bindEvents();
  await refresh();
  await checkDailyAutoRun();
}

boot().catch((error) => {
  document.getElementById("fitJobList").innerHTML = emptyState(error.message);
  toast(error.message, "error");
});
