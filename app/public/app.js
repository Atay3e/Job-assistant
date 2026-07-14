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
  trackerStatus: "all",
  trackerDate: "",
  trackerMonth: "",
  trackerQuery: "",
  trackerPage: 1,
  trackerPageSize: 40,
  notionStatus: {},
  daily: {},
  profile: {},
  careerFit: {},
  scan: {},
  workbench: {},
  companyJobs: {},
  companyJobsLoading: {},
  workspaceDataLoaded: false,
  workspaceDataKey: "",
  workspaceDataPromise: null,
  notionDataLoaded: false,
  notionDataPromise: null,
  activeWorkbenchPanel: "today",
  todayRecommendationBucket: "today_new",
  todayRecommendationVisibleCount: 8,
  supplementalRecommendationVisibleCount: 8,
  jobsPanel: "recommendations",
  expandedJobId: null,
  compactMode: true,
  scanPollTimer: null,
  focusRefreshTimer: null,
  onboardingStep: 1,
  companyTab: "watched",
  showAllCompanyRecommendations: false,
  dailyRunChecked: false,
  auth: {
    config: { auth_required: false },
    client: null,
    session: null,
    userId: "",
  },
};

const TODAY_RECOMMENDATION_PAGE_SIZE = 8;
const SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE = 8;
const SUPPLEMENTAL_RECOMMENDATION_POOL_SIZE = 40;
const WORKBENCH_CORE_TAGS = new Set([
  "internship", "graduate", "full_time", "contract",
  "conversion_strong", "conversion_possible", "conversion_none",
  "visa_possible", "visa_unclear", "visa_unlikely",
  "chinese_friendly", "english_first",
  "company_greater_china", "company_sg_anchor", "company_ai_startup",
  "company_product_design", "company_fintech", "company_service_brand",
  "ai_related", "product_related", "ux_related", "operations_related", "marketing_related",
  "high_experience",
]);

let detailReturnFocus = null;
let followupReturnFocus = null;

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

const RECOMMENDATION_EXCLUDED_STATUSES = new Set(["Apply Queue", "Drafted", "Applied", "Dropped", "Closed"]);
const PATHWAY_PRESETS = {
  internship: {
    label: "实习优先",
    patch: { employment_priority: "internship", career_goal: "sg_internship_to_fulltime", job_types: ["Internship", "Graduate"], preferred_job_tags: ["internship", "graduate"], muted_job_tags: ["full_time", "high_experience"] },
  },
  conversion: {
    label: "可转正优先",
    patch: { career_goal: "sg_internship_to_fulltime", employment_priority: "internship", conversion_priority: "high", job_types: ["Internship", "Graduate"], preferred_job_tags: ["conversion_strong", "conversion_possible"], muted_job_tags: ["conversion_none"] },
  },
  sponsorship: {
    label: "工签机会优先",
    patch: { career_goal: "sg_internship_to_fulltime", sponsorship_priority: "high", preferred_company_groups: ["sg_anchor", "greater_china", "fintech"], preferred_job_tags: ["visa_possible", "company_sg_anchor", "company_greater_china"], muted_job_tags: ["visa_unlikely"] },
  },
  chinese: {
    label: "中文友好优先",
    patch: { language_preference: "chinese_friendly", preferred_company_groups: ["greater_china", "ai_startup"], preferred_job_tags: ["chinese_friendly", "company_greater_china"], muted_job_tags: ["english_first"] },
  },
  ai_product: {
    label: "AI/Product",
    patch: { target_directions: ["ai-product", "ux-product-design", "product-ops"], preferred_company_groups: ["ai_startup", "product_design", "greater_china"], preferred_job_tags: ["ai_related", "product_related", "ux_related", "company_ai_startup"] },
  },
};

async function api(path, options = {}) {
  const init = { ...options };
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  init.headers = { ...headers, ...(options.headers || {}) };
  const token = state.auth.session?.access_token;
  if (token) init.headers.Authorization = `Bearer ${token}`;
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
    if (response.status === 401 && state.auth.config?.auth_required) {
      showAuthScreen("请先登录后再继续。");
    }
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function setAppVisibility(showApp) {
  const app = document.querySelector(".app-shell");
  const auth = document.getElementById("authScreen");
  if (app) app.hidden = !showApp;
  if (auth) auth.hidden = showApp;
}

function resetPrivateState() {
  Object.assign(state, {
    jobs: [],
    aiJobs: [],
    recommendations: { jobs: [], active_direction_ids: [], direction_source: "base_score" },
    summary: {},
    watchlist: [],
    regions: { regions: [], active_region: "SG" },
    userContext: { active_region: "SG", contexts: {} },
    profileOptions: {},
    companyCatalog: [],
    daily: {},
    profile: {},
    careerFit: {},
    workbench: {},
    scan: {},
    companyJobs: {},
    companyJobsLoading: {},
    workspaceDataLoaded: false,
    workspaceDataKey: "",
    workspaceDataPromise: null,
    notionDataLoaded: false,
    notionDataPromise: null,
    dailyRunChecked: false,
  });
}

function showAuthScreen(message = "") {
  setAppVisibility(false);
  const status = document.getElementById("authStatus");
  if (status) status.textContent = message;
  const accountBox = document.getElementById("accountBox");
  if (accountBox) accountBox.hidden = true;
}

function showAppScreen() {
  setAppVisibility(true);
  const accountBox = document.getElementById("accountBox");
  const accountEmail = document.getElementById("accountEmail");
  if (accountBox) accountBox.hidden = !state.auth.config?.auth_required;
  if (accountEmail) accountEmail.textContent = state.auth.session?.user?.email || "已登录";
}

async function initAuth() {
  state.auth.config = await api("/api/auth/config");
  if (!state.auth.config.auth_required) {
    showAppScreen();
    return true;
  }
  if (!window.supabase?.createClient) {
    showAuthScreen("登录组件暂时没有加载出来，请刷新页面。");
    return false;
  }
  if (!state.auth.config.supabase_url || !state.auth.config.supabase_anon_key) {
    showAuthScreen("服务器还没有配置登录服务。");
    return false;
  }
  state.auth.client = window.supabase.createClient(state.auth.config.supabase_url, state.auth.config.supabase_anon_key);
  const { data } = await state.auth.client.auth.getSession();
  state.auth.session = data.session || null;
  state.auth.userId = state.auth.session?.user?.id || "";
  state.auth.client.auth.onAuthStateChange(async (_event, session) => {
    const nextUserId = session?.user?.id || "";
    const changedUser = nextUserId !== state.auth.userId;
    state.auth.session = session || null;
    state.auth.userId = nextUserId;
    if (!session) {
      resetPrivateState();
      showAuthScreen("已退出登录。");
      return;
    }
    showAppScreen();
    if (changedUser) {
      resetPrivateState();
      await refresh();
      await checkDailyAutoRun();
    }
  });
  if (!state.auth.session) {
    showAuthScreen("");
    return false;
  }
  showAppScreen();
  return true;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(message, type = "info", action = null) {
  const host = document.getElementById("toastHost");
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.setAttribute("role", type === "error" ? "alert" : "status");
  const text = document.createElement("span");
  text.textContent = message;
  node.appendChild(text);
  let removeTimer;
  if (action?.label && typeof action.onClick === "function") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action.label;
    button.addEventListener("click", async () => {
      window.clearTimeout(removeTimer);
      button.disabled = true;
      button.textContent = action.pendingLabel || "处理中...";
      try {
        await action.onClick();
        node.remove();
      } catch (error) {
        node.remove();
        toast(error.message || "操作失败，请重试。", "error");
      }
    }, { once: true });
    node.appendChild(button);
  }
  host.appendChild(node);
  removeTimer = window.setTimeout(() => node.remove(), action ? 6000 : (type === "error" ? 5200 : 3200));
  return node;
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
  return job.supplemental_candidate !== false
    && !RECOMMENDATION_EXCLUDED_STATUSES.has(job.status)
    && !job.company_hidden_by_watchlist
    && !job.company_watched_by_user
    && String(job.source || "").trim() !== "关注公司公开来源"
    && !isLocallyWatchedCompanyJob(job);
}

function normalizeCompanyName(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/\b(private limited|pte\.?\s*ltd\.?|limited|ltd\.?|inc\.?|corp\.?|corporation|co\.?)\b/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function isLocallyWatchedCompanyJob(job) {
  const company = ` ${normalizeCompanyName(job.company || job.name)} `;
  if (!company.trim()) return false;
  return (state.watchlist || []).some((item) => {
    const aliases = [item.company, ...(item.aliases || [])];
    return aliases.some((alias) => {
      const term = normalizeCompanyName(alias);
      return term && (company === ` ${term} ` || company.includes(` ${term} `));
    });
  });
}

function workbenchShortlistJobIds() {
  const wb = state.workbench || {};
  return new Set([
    ...(wb.today_new_recommendations || []),
    ...(wb.weekly_unqueued_recommendations || []),
  ].flatMap((job) => [job.id, ...(job.alternate_links || []).map((link) => link.id)]).map(String).filter(Boolean));
}

function isSupplementalRecommendationCandidate(job, shortlistIds = workbenchShortlistJobIds()) {
  return (
    isRecommendationCandidate(job)
    && !shortlistIds.has(String(job.id))
    && !job.company_watched_by_user
  );
}

function collapseSupplementalJobs(jobs) {
  const collapsed = [];
  const byKey = new Map();
  (jobs || []).forEach((job) => {
    const key = job.dedupe_key || `id:${job.id}`;
    const existing = byKey.get(key);
    if (!existing) {
      const item = { ...job, alternate_links: [...(job.alternate_links || [])] };
      item.source_count = Math.max(Number(item.source_count || 1), 1 + item.alternate_links.length);
      collapsed.push(item);
      byKey.set(key, item);
      return;
    }
    if (job.url && job.url !== existing.url && !existing.alternate_links.some((link) => link.url === job.url)) {
      existing.alternate_links.push({ id: job.id, source: job.source || "其它来源", url: job.url });
    }
    existing.source_count = 1 + existing.alternate_links.length;
  });
  return collapsed;
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

function activeCity() {
  const config = activeRegionConfig();
  const context = activeRegionContext();
  return context.city || config.default_city || "";
}

function regionQuery() {
  const params = new URLSearchParams({ region: activeRegion() });
  if (activeCity()) params.set("city", activeCity());
  return params.toString();
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

function renderGroupedOptionButtons(containerId, options, selectedValues, config = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const groups = new Map();
  (options || []).forEach((item) => {
    const category = item.category || "其他方向";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(item);
  });
  container.innerHTML = Array.from(groups.entries()).map(([category, items]) => `
    <div class="option-group">
      <div class="option-group-title">${escapeHtml(category)}</div>
      <div class="option-chip-row">
        ${items.map((item) => {
          const selected = new Set(selectedValues || []);
          const multi = config.multi !== false;
          return `
            <button
              type="button"
              class="option-chip ${selected.has(item.value) ? "active" : ""}"
              data-option-target="${escapeHtml(config.target || "")}"
              data-option-value="${escapeHtml(item.value)}"
              data-option-multi="${multi ? "true" : "false"}"
            >${escapeHtml(item.label)}</button>
          `;
        }).join("")}
      </div>
    </div>
  `).join("");
}

function salaryPreferenceLabel(context) {
  const currency = context.salary_currency || state.profileOptions.salary_currency || "";
  const period = periodLabel(context.salary_period || "monthly");
  const minimum = context.salary_min ? `${currency} ${formatMoney(context.salary_min)}+` : "最低不限";
  const preferred = context.salary_preferred ? `理想 ${currency} ${formatMoney(context.salary_preferred)}+` : "理想可空";
  return `${minimum} · ${preferred} · ${period}`;
}

function priorityLevelLabel(value) {
  return {
    high: "优先",
    medium: "加权",
    low: "不强求",
    unspecified: "暂不确定",
  }[value || "unspecified"] || value || "暂不确定";
}

function languagePreferenceLabel(value) {
  return {
    chinese_friendly: "中文友好优先",
    bilingual: "中英双语都可",
    english_ok: "英文为主也可以",
    unspecified: "语言不限",
  }[value || "unspecified"] || value || "语言不限";
}

function companyGroupLabel(value) {
  return {
    greater_china: "大中华/中文友好",
    sg_anchor: "新加坡本地大厂",
    ai_startup: "AI/高潜力初创",
    product_design: "产品/设计",
    fintech: "Fintech",
    service_brand: "服务体验品牌",
  }[value] || value;
}

function jobTagLabel(value) {
  return optionLabel(state.profileOptions.job_tag_options, value) || value;
}

function renderTagSummaryChips(containerId, values, fallbackText) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const visible = (values || []).filter(Boolean).slice(0, 8);
  const extra = Math.max(0, (values || []).filter(Boolean).length - visible.length);
  container.innerHTML = visible.length
    ? `${visible.map((value) => `<span class="chip-label active">${escapeHtml(jobTagLabel(value))}</span>`).join("")}${extra ? `<span class="chip-label">+${extra}</span>` : ""}`
    : `<span class="chip-label">${escapeHtml(fallbackText)}</span>`;
}

function renderPreferenceSummary(context) {
  renderTagSummaryChips("preferredTagSummary", context.preferred_job_tags || [], "未设置，按默认留新算法排序");
  renderTagSummaryChips("mutedTagSummary", context.muted_job_tags || [], "未设置，不额外降权");
}

function recommendationScopeMessage(baseMessage, recommendations) {
  const scope = recommendations?.tag_scope;
  if (!scope?.effective) return baseMessage;
  const matched = Number(scope.matched_jobs || 0);
  const muted = Number(scope.muted_jobs || 0);
  const pieces = [];
  if (matched) pieces.push(`${matched} 个岗位命中优先标签`);
  if (muted) pieces.push(`${muted} 个岗位被少看标签降权`);
  return pieces.length ? `${baseMessage} ${pieces.join("，")}。` : baseMessage;
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

function resumeAnalyzed() {
  return Boolean(state.userContext?.resume_analyzed || state.careerFit?.resume_analyzed || state.careerFit?.analysis);
}

function suggestedDirectionIds(limit = 3) {
  return (state.careerFit?.suggested_directions || [])
    .filter((item) => item.id && Number(item.score || 0) > 0)
    .slice(0, limit)
    .map((item) => item.id);
}

function directionOptionsById() {
  return new Map((state.profileOptions.direction_options || []).map((item) => [item.value, item]));
}

function resumeSuggestedDirectionOptions(limit = 6) {
  const byId = directionOptionsById();
  return (state.careerFit?.suggested_directions || [])
    .filter((item) => item.id && Number(item.score || 0) > 0 && byId.has(item.id))
    .slice(0, limit)
    .map((item) => {
      const option = byId.get(item.id);
      const score = Math.round(Number(item.score || 0) * 100);
      return {
        ...option,
        label: `${option.label} · ${score}%`,
        category: "简历推荐方向",
        resume_score: item.score,
      };
    });
}

function directionOptionsForChoice(selectedValues = []) {
  const suggested = resumeSuggestedDirectionOptions();
  if (!resumeAnalyzed() || !suggested.length) return state.profileOptions.direction_options || [];
  const suggestedIds = new Set(suggested.map((item) => item.value));
  const byId = directionOptionsById();
  const selectedOther = (selectedValues || [])
    .filter((id) => !suggestedIds.has(id) && byId.has(id))
    .map((id) => ({ ...byId.get(id), category: "手动保留方向" }));
  return [...suggested, ...selectedOther];
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ");
}

function dateToTime(value) {
  const text = String(value || "").trim();
  if (!text) return 0;
  const normalized = text.length === 10 ? `${text}T00:00:00` : text;
  const time = new Date(normalized).getTime();
  return Number.isFinite(time) ? time : 0;
}

function daysSince(value) {
  const time = dateToTime(value);
  if (!time) return 9999;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const date = new Date(time);
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  return Math.max(0, Math.floor((today - day) / 86400000));
}

function deadlineInfo(job) {
  const code = String(job.deadline_status || "unknown");
  const label = String(job.deadline_label || "");
  const days = job.deadline_days_remaining;
  return {
    code,
    label,
    days: days === null || days === undefined ? null : Number(days),
  };
}

function compareQueueUrgency(a, b) {
  const order = { today: 0, urgent: 1, soon: 2, scheduled: 3, unknown: 4, expired: 5 };
  const left = deadlineInfo(a);
  const right = deadlineInfo(b);
  const statusDifference = (order[left.code] ?? 4) - (order[right.code] ?? 4);
  if (statusDifference) return statusDifference;
  if (left.days !== null && right.days !== null && left.days !== right.days) {
    return left.code === "expired" ? Math.abs(left.days) - Math.abs(right.days) : left.days - right.days;
  }
  return dateToTime(b.updated_at || b.batch_date || b.found_date) - dateToTime(a.updated_at || a.batch_date || a.found_date)
    || displayJobScore(b) - displayJobScore(a);
}

function freshnessInfo(job) {
  const foundDays = daysSince(job.found_date);
  const updatedDays = daysSince(job.last_checked_at || job.updated_at || job.batch_date);
  if (foundDays === 0) return { label: "今日新增", className: "fresh" };
  if (foundDays <= 2) return { label: `${foundDays} 天内新增`, className: "fresh" };
  if (foundDays <= 7) return { label: "本周新增", className: "recent" };
  const listingStatus = String(job.listing_freshness_status || "");
  const listingLabel = String(job.listing_freshness_label || "");
  if (["aging", "verify", "unknown", "likely_closed"].includes(listingStatus) && listingLabel) {
    return { label: listingLabel, className: "stale" };
  }
  if (["verified", "recent"].includes(listingStatus) && listingLabel) {
    return { label: listingLabel, className: "recent" };
  }
  if (updatedDays === 0) return { label: "今日刷新", className: "recent" };
  if (updatedDays <= 7) return { label: "本周刷新", className: "recent" };
  return { label: "旧岗位", className: "stale" };
}

function freshnessWeight(job) {
  const foundDays = daysSince(job.found_date);
  const updatedDays = daysSince(job.last_checked_at || job.updated_at || job.batch_date);
  if (foundDays === 0) return 1.25;
  if (foundDays <= 2) return 1.05;
  if (foundDays <= 7) return 0.72;
  if (updatedDays === 0) return 0.45;
  if (updatedDays <= 7) return 0.28;
  return 0;
}

function numericScore(value, fallback = 0) {
  const score = Number(value);
  return Number.isFinite(score) ? score : fallback;
}

function baseJobScore(job) {
  return numericScore(job.base_score ?? job.score, 0);
}

function rankJobScore(job) {
  return numericScore(job.rank_score, baseJobScore(job));
}

function displayJobScore(job) {
  return numericScore(job.fit_score, Math.max(0, Math.min(5, rankJobScore(job))));
}

function scoreCaption(job, options = {}) {
  if (job.fit_score !== undefined || job.rank_score !== undefined) return "匹配分";
  if (options.ai) return "基础分";
  return "/ 5.0";
}

function generalJobRank(job) {
  const score = displayJobScore(job);
  const rankScore = rankJobScore(job);
  return (score * 10) + (rankScore * 1.4) + (freshnessWeight(job) * 7);
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
  if (name.includes("Internship.sg")) return "Internship.sg";
  if (name.includes("MyCareersFuture")) return "MyCareersFuture";
  if (name.includes("Indeed")) return "Indeed";
  if (name.includes("JobStreet")) return "JobStreet";
  if (name.includes("创业") || name.includes("Startup") || name.includes("Glints") || name.includes("NodeFlair")) return "创业与 AI 机会";
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
  const focusCity = document.getElementById("focusCity");
  const contextRegion = document.getElementById("contextRegion");
  const onboardingRegion = document.getElementById("onboardingRegion");
  if (focusRegion) focusRegion.innerHTML = options;
  if (contextRegion) contextRegion.innerHTML = options;
  if (onboardingRegion) onboardingRegion.innerHTML = options;
  if (focusRegion) focusRegion.value = activeRegion();
  if (contextRegion) contextRegion.value = activeRegion();
  if (onboardingRegion) onboardingRegion.value = activeRegion();

  const cityOptions = (config.cities || [config.default_city || "Singapore"])
    .map((city) => `<option value="${escapeHtml(city)}" ${city === (context.city || config.default_city) ? "selected" : ""}>${escapeHtml(city)}</option>`)
    .join("");
  const citySelect = document.getElementById("contextCity");
  if (citySelect) citySelect.innerHTML = cityOptions;
  if (focusCity) focusCity.innerHTML = cityOptions;
  const onboardingCity = document.getElementById("onboardingCity");
  if (onboardingCity) onboardingCity.innerHTML = cityOptions;
  const cityHiddenValue = context.city || config.default_city || "";
  if (focusCity) focusCity.value = cityHiddenValue;
  if (onboardingCity) onboardingCity.value = cityHiddenValue;
  const focusCityField = document.getElementById("focusCityField");
  const onboardingCityField = document.getElementById("onboardingCityField");
  const showCityPicker = Boolean(state.profileOptions.city_required || (config.cities || []).length > 1);
  if (focusCityField) focusCityField.hidden = !showCityPicker;
  if (onboardingCityField) onboardingCityField.hidden = !showCityPicker;

  const form = document.getElementById("contextForm");
  if (form) {
    form.elements.active_region.value = activeRegion();
    form.elements.city.value = context.city || config.default_city || "";
    form.elements.work_authorisation.value = context.work_authorisation || "";
    form.elements.target_directions.value = (context.target_directions || []).join(", ");
    form.elements.job_types.value = (context.job_types || []).join(", ");
    form.elements.employment_priority.value = context.employment_priority || "both";
    form.elements.career_goal.value = context.career_goal || "sg_internship_to_fulltime";
    form.elements.sponsorship_priority.value = context.sponsorship_priority || "high";
    form.elements.language_preference.value = context.language_preference || "chinese_friendly";
    form.elements.conversion_priority.value = context.conversion_priority || "high";
    form.elements.preferred_company_groups.value = (context.preferred_company_groups || []).join(", ");
    form.elements.preferred_job_tags.value = (context.preferred_job_tags || []).join(", ");
    form.elements.muted_job_tags.value = (context.muted_job_tags || []).join(", ");
    form.elements.salary_currency.value = context.salary_currency || state.profileOptions.salary_currency || "";

    const workAuthValues = new Set((state.profileOptions.work_authorisation_options || []).map((item) => item.value));
    const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
    const jobTypeValues = new Set((state.profileOptions.job_type_options || []).map((item) => item.value));
    document.getElementById("customWorkAuth").value = workAuthValues.has(context.work_authorisation) ? "" : (context.work_authorisation || "");
    document.getElementById("customDirections").value = (context.target_directions || []).filter((item) => !directionValues.has(item)).join(", ");
    document.getElementById("customJobTypes").value = (context.job_types || []).filter((item) => !jobTypeValues.has(item)).join(", ");

    renderOptionButtons("workAuthOptions", state.profileOptions.work_authorisation_options || [], [context.work_authorisation || ""], { target: "context:work_authorisation", multi: false });
    renderOptionButtons("contextPriorityOptions", state.profileOptions.employment_priority_options || [], [context.employment_priority || "both"], { target: "context:employment_priority", multi: false });
    renderOptionButtons("contextDirectionOptions", directionOptionsForChoice(context.target_directions || []), context.target_directions || [], { target: "context:target_directions" });
    renderOptionButtons("contextJobTypeOptions", state.profileOptions.job_type_options || [], context.job_types || [], { target: "context:job_types" });
    renderGroupedOptionButtons("contextPreferredTagOptions", state.profileOptions.job_tag_options || [], context.preferred_job_tags || [], { target: "context:preferred_job_tags" });
    renderGroupedOptionButtons("contextMutedTagOptions", state.profileOptions.job_tag_options || [], context.muted_job_tags || [], { target: "context:muted_job_tags" });
    renderPreferenceSummary(context);

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
  const city = context.city || config.default_city || "";
  const conversionText = `转正${priorityLevelLabel(context.conversion_priority || "high")}`;
  const sponsorshipText = `工签${priorityLevelLabel(context.sponsorship_priority || "high")}`;
  const languageText = languagePreferenceLabel(context.language_preference || "chinese_friendly");
  document.getElementById("focusTitle").textContent = `${config.label || activeRegion()}${city ? " · " + city : ""} · 留用型实习`;
  document.getElementById("focusSummary").textContent = `${priorityLabel} · ${conversionText} · ${sponsorshipText} · ${languageText} · 简历${resumeAnalyzed() ? "已分析" : "待分析"} · 关注公司 ${state.watchlist.length || 0} 家`;
  renderOptionButtons("focusPriorityQuick", state.profileOptions.employment_priority_options || [], [priority], { target: "focus:employment_priority", multi: false });
  document.querySelectorAll("[data-pathway-action]").forEach((button) => {
    const action = button.dataset.pathwayAction;
    const active = (
      (action === "internship" && priority === "internship")
      || (action === "conversion" && context.conversion_priority === "high")
      || (action === "sponsorship" && context.sponsorship_priority === "high")
      || (action === "chinese" && context.language_preference === "chinese_friendly")
      || (action === "ai_product" && (context.target_directions || []).includes("ai-product"))
    );
    button.classList.toggle("active", active);
  });
  const directionOptions = state.profileOptions.direction_options || [];
  const directionLabels = (context.target_directions || []).slice(0, 4).map((id) => optionLabel(directionOptions, id) || id);
  const jobTypes = (context.job_types || []).slice(0, 3);
  const groups = (context.preferred_company_groups || []).slice(0, 3).map(companyGroupLabel);
  const preferredTags = (context.preferred_job_tags || []).slice(0, 5).map(jobTagLabel);
  const mutedTags = (context.muted_job_tags || []).slice(0, 3).map((tag) => `少看 ${jobTagLabel(tag)}`);
  const tags = [
    priorityLabel,
    city,
    conversionText,
    sponsorshipText,
    languageText,
    ...directionLabels,
    ...jobTypes,
    ...groups,
    ...preferredTags,
    ...mutedTags,
  ].filter(Boolean);
  document.getElementById("focusTags").innerHTML = tags.length
    ? tags.map((tag) => `<span class="chip-label active">${escapeHtml(tag)}</span>`).join("")
    : `<span class="chip-label">方向可空</span>`;
}

function renderOnboarding() {
  const panel = document.getElementById("onboardingPanel");
  const form = document.getElementById("onboardingForm");
  if (!panel || !form) return;
  const config = activeRegionConfig();
  const context = activeRegionContext();
  panel.hidden = Boolean(state.userContext?.onboarding_completed);
  const analyzed = resumeAnalyzed();
  const savedStep = Number(state.userContext?.onboarding_step || 1);
  if (!state.onboardingStep || state.onboardingStep < savedStep) state.onboardingStep = savedStep;
  if (analyzed && state.onboardingStep < 3) state.onboardingStep = 3;
  if (!analyzed && state.onboardingStep > 2) state.onboardingStep = 2;
  state.onboardingStep = Math.max(1, Math.min(3, state.onboardingStep));

  form.elements.active_region.value = activeRegion();
  form.elements.city.value = context.city || config.default_city || "";
  form.elements.employment_priority.value = context.employment_priority || "both";
  form.elements.target_directions.value = (context.target_directions || []).join(", ");
  form.elements.job_types.value = (context.job_types || []).join(", ");
  form.elements.work_authorisation.value = context.work_authorisation || "";
  form.elements.career_goal.value = context.career_goal || "sg_internship_to_fulltime";
  form.elements.sponsorship_priority.value = context.sponsorship_priority || "high";
  form.elements.language_preference.value = context.language_preference || "chinese_friendly";
  form.elements.conversion_priority.value = context.conversion_priority || "high";
  form.elements.preferred_company_groups.value = (context.preferred_company_groups || ["greater_china", "ai_startup", "sg_anchor"]).join(", ");
  form.elements.preferred_job_tags.value = (context.preferred_job_tags || []).join(", ");
  form.elements.muted_job_tags.value = (context.muted_job_tags || []).join(", ");
  const directionValues = new Set((state.profileOptions.direction_options || []).map((item) => item.value));
  const customDirectionInput = document.getElementById("onboardingCustomDirections");
  if (customDirectionInput) {
    customDirectionInput.value = (context.target_directions || []).filter((item) => !directionValues.has(item)).join(", ");
  }
  document.querySelectorAll("[data-onboarding-step]").forEach((step) => {
    step.classList.toggle("active", Number(step.dataset.onboardingStep) === state.onboardingStep);
  });
  document.querySelectorAll("[data-step-dot]").forEach((dot) => {
    const step = Number(dot.dataset.stepDot);
    dot.classList.toggle("active", step === state.onboardingStep);
    dot.classList.toggle("done", step < state.onboardingStep);
  });
  renderOptionButtons("onboardingPriorityOptions", state.profileOptions.employment_priority_options || [], [context.employment_priority || "both"], { target: "onboarding:employment_priority", multi: false });
  renderGroupedOptionButtons("onboardingDirectionOptions", directionOptionsForChoice(context.target_directions || []), context.target_directions || [], { target: "onboarding:target_directions" });
  renderOptionButtons("onboardingJobTypeOptions", state.profileOptions.job_type_options || [], context.job_types || [], { target: "onboarding:job_types" });
  renderOptionButtons("onboardingWorkAuthOptions", state.profileOptions.work_authorisation_options || [], [context.work_authorisation || ""], { target: "onboarding:work_authorisation", multi: false });
  renderGroupedOptionButtons("onboardingPreferredTagOptions", state.profileOptions.job_tag_options || [], context.preferred_job_tags || [], { target: "onboarding:preferred_job_tags" });
  renderGroupedOptionButtons("onboardingMutedTagOptions", state.profileOptions.job_tag_options || [], context.muted_job_tags || [], { target: "onboarding:muted_job_tags" });
  setSelectOptions(document.getElementById("onboardingSalaryPeriod"), state.profileOptions.salary_period_options || [], context.salary_period || "monthly");
  const salaryBands = salaryBandsForPeriod(context.salary_period || "monthly");
  setSelectOptions(document.getElementById("onboardingSalaryMin"), salaryBands, context.salary_min ?? "");
  setSelectOptions(document.getElementById("onboardingSalaryPreferred"), salaryBands, context.salary_preferred ?? "");
  const preview = document.getElementById("onboardingAnalysisPreview");
  if (preview) {
    const labels = (state.careerFit?.suggested_directions || []).slice(0, 3).map((item) => item.label);
    preview.innerHTML = analyzed
      ? `<strong>已完成简历分析</strong><p class="small-text">${escapeHtml(state.careerFit?.analysis?.summary || "可以继续确认求职偏好。")}</p><div class="chip-row">${labels.map((label) => `<span class="chip-label active">${escapeHtml(label)}</span>`).join("")}</div>`
      : `<span class="small-text">还没有简历分析结果。请选择文件后点击“分析简历”。</span>`;
  }
  const locationStatus = document.getElementById("onboardingLocationStatus");
  if (locationStatus) {
    locationStatus.textContent = state.profileOptions.city_required ? "中国大陆会按城市搜索相关岗位。" : "当前地区已准备好。";
  }
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
  const conversionBadge = Number(job.conversion_opportunity || 0) > 0 && !(job.pathway_tags || []).some((tag) => String(tag).includes("转正"))
    ? `<span class="badge good">可转正</span>`
    : "";
  const salaryLabel = salaryBadgeLabel(job);
  const salaryBadge = salaryLabel
    ? `<span class="badge salary-badge ${job.salary_fit === "low" ? "warn" : ""}">${escapeHtml(salaryLabel)}</span>`
    : "";
  const pathwayBadges = (job.pathway_tags || [])
    .slice(0, 5)
    .map((tag) => {
      const text = String(tag);
      const cls = text.includes("风险") || text.includes("无转正") ? "warn" : (text.includes("工签") || text.includes("转正") || text.includes("中文") ? "pathway-badge" : "fit-badge");
      return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
    })
    .join("");
  const userTagBadges = (job.user_tag_matches || [])
    .slice(0, 4)
    .map((tag) => `<span class="badge user-tag-badge">我选 · ${escapeHtml(tag.label || tag.id)}</span>`)
    .join("");
  const mutedTagBadges = (job.user_tag_mutes || [])
    .slice(0, 3)
    .map((tag) => `<span class="badge warn">少看 · ${escapeHtml(tag.label || tag.id)}</span>`)
    .join("");
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
  const displayScore = displayJobScore(job);
  const notes = job.recommendation_reason || (options.fit && job.fit_reasons?.length ? job.fit_reasons.join(" | ") : job.match_notes);
  const freshness = freshnessInfo(job);
  const freshnessBadge = `<span class="badge freshness-badge ${freshness.className}">${escapeHtml(freshness.label)}</span>`;
  const sourceCountBadge = Number(job.source_count || 1) > 1
    ? `<span class="badge source-count-badge">${Number(job.source_count)} 个来源</span>`
    : "";
  const deadline = deadlineInfo(job);
  const deadlineBadge = deadline.label
    ? `<span class="badge ${["today", "urgent", "soon", "expired"].includes(deadline.code) ? "warn" : "quiet-badge"}">${escapeHtml(deadline.label)}</span>`
    : "";
  const dateMeta = [
    `发现 ${job.found_date || "-"}`,
    `更新 ${(job.updated_at || job.last_checked_at || "").slice(0, 10) || "-"}`,
    job.applied_date ? `投递 ${job.applied_date}` : "",
  ].filter(Boolean).join(" · ");

  return `
    <article class="job-card freshness-${escapeHtml(freshness.className)}" data-job-id="${job.id}">
      <div>
        <div class="job-title-row">
          <h3>
            <button class="job-title-button" data-action="detail" data-id="${job.id}" aria-label="查看 ${escapeHtml(job.company)} ${escapeHtml(job.position)} 的详情">
              ${escapeHtml(job.company)} - ${escapeHtml(job.position)}
            </button>
          </h3>
          <span class="badge">${escapeHtml(statusLabel(job.status))}</span>
          <span class="badge">${escapeHtml(job.source)}</span>
          ${sourceCountBadge}
          ${freshnessBadge}
        </div>
        <div class="job-meta">${escapeHtml(dateMeta)}</div>
        <div class="badge-row">${deadlineBadge}${regionBadge}${employmentBadge}${conversionBadge}${pathwayBadges}${userTagBadges}${mutedTagBadges}${salaryBadge}${fitBadge}${companyBadge}${aiBadge}${matched}${badges}${draftLinks}</div>
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
        <span class="badge good">${scoreTone(displayScore)}</span>
        <strong>${displayScore.toFixed(1)}</strong>
        <span class="small-text">${scoreCaption(job, options)}</span>
        ${job.pathway_score !== undefined ? `<span class="pathway-meter">留新 ${Number(job.pathway_score || 0).toFixed(1)}</span>` : ""}
      </div>
    </article>
  `;
}

function compactJobTags(job, limit = 5) {
  const deadline = deadlineInfo(job);
  const tags = [
    deadline.label,
    employmentTypeLabel(job.employment_type || "Unknown"),
    ...(job.pathway_tags || []),
    ...(job.user_tag_matches || []).map((item) => item.label || item.id),
    salaryBadgeLabel(job),
  ].filter(Boolean);
  const unique = uniqueList(tags).slice(0, limit);
  const extra = Math.max(0, uniqueList(tags).length - unique.length);
  return `
    ${unique.map((tag) => {
      const text = String(tag);
      const cls = text.includes("风险") || text.includes("偏低") || text.includes("无转正") || text.includes("待确认") || text.includes("未知") || text.includes("截止")
        ? "warn"
        : (text.includes("工签") || text.includes("转正") || text.includes("中文") ? "pathway-badge" : "quiet-badge");
      return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
    }).join("")}
    ${extra ? `<span class="badge quiet-badge">+${extra}</span>` : ""}
  `;
}

function compactJobRow(job, options = {}) {
  const score = displayJobScore(job);
  const freshness = freshnessInfo(job);
  const reason = options.queue
    ? (job.next_step || trackerNextStep(job))
    : (job.decision_summary || job.recommendation_reason || job.next_step || job.match_notes || "打开详情确认转正、工签和岗位要求。");
  const isQueue = job.status === "Apply Queue";
  const isApplied = job.status === "Applied";
  const tagLimit = options.mini ? 3 : 5;
  const canDismiss = !options.mini && !isQueue && !isApplied && isRecommendationCandidate(job);
  const canDropFromQueue = Boolean(options.queue && isQueue);
  const primaryAction = options.followup
    ? `<button class="primary-button compact-button" data-action="followup-draft" data-id="${job.id}">${icon.detail} 写跟进</button>`
    : isQueue
    ? `<button class="primary-button compact-button" data-action="assist" data-id="${job.id}">${icon.assist} 填表</button>`
    : isApplied
      ? `<button class="secondary-button compact-button" data-action="detail" data-id="${job.id}">${icon.detail} 查看</button>`
      : `<button class="primary-button compact-button" data-action="Apply" data-id="${job.id}">${icon.apply} 加入投递</button>`;
  const secondaryAction = isQueue
    ? `<button class="secondary-button compact-button" data-action="confirm" data-id="${job.id}">${icon.submit} 已投</button>`
    : isApplied
      ? ""
      : `<button class="secondary-button compact-button" data-action="detail" data-id="${job.id}">${icon.detail} 详情</button>`;
  return `
    <article class="inbox-row ${options.mini ? "is-mini" : ""}" data-job-id="${job.id}">
      <div class="inbox-main">
        <div class="inbox-title-row">
          <button class="job-title-button inbox-title" data-action="detail" data-id="${job.id}">
            <span>${escapeHtml(job.company || "-")}</span>
            <strong>${escapeHtml(job.position || "-")}</strong>
          </button>
          ${canDismiss || canDropFromQueue ? `<button class="icon-button inbox-dismiss-button" type="button" data-action="Drop" data-id="${job.id}"${canDropFromQueue ? ' data-undo-action="Apply"' : ""} aria-label="${canDropFromQueue ? "移出投递队列" : "隐藏"} ${escapeHtml(job.company || "")} ${escapeHtml(job.position || "")}" title="${canDropFromQueue ? "移出队列并保留记录" : "隐藏此岗位"}">${icon.drop}</button>` : ""}
        </div>
        <div class="inbox-meta">${escapeHtml(job.source || "-")}${Number(job.source_count || 1) > 1 ? ` · ${Number(job.source_count)} 个来源` : ""} · ${escapeHtml(freshness.label)} · ${escapeHtml((job.updated_at || job.last_checked_at || job.found_date || "").slice(0, 10) || "-")}</div>
        <div class="inbox-tags">${compactJobTags(job, tagLimit)}</div>
        <p class="inbox-reason">${escapeHtml(reason)}</p>
      </div>
      <div class="inbox-score">
        <strong>${score.toFixed(1)}</strong>
        <span>综合</span>
      </div>
      <div class="inbox-actions">${primaryAction}${secondaryAction}</div>
    </article>
  `;
}

function actionItemTemplate(action) {
  const kindLabels = {
    recommendations: "优先查看",
    queue: "待投递",
    followup: "待跟进",
    stale: "待整理",
    scan_limited: "来源状态",
    scan: "岗位扫描",
    resume: "简历分析",
    todo: "下一步",
  };
  return `
    <button class="action-item" type="button" data-action-view="${escapeHtml(action.view || "today")}" data-action-kind="${escapeHtml(action.kind || "todo")}">
      <span class="action-kind">${escapeHtml(kindLabels[action.kind] || kindLabels.todo)}</span>
      <strong>${escapeHtml(action.title || "下一步")}</strong>
      <span>${escapeHtml(action.body || "")}</span>
    </button>
  `;
}

function sourceMiniRow(row) {
  const status = row.status || "pending";
  const label = SCAN_STATUS_ZH[status] || status;
  const discovered = Number(row.new_count || 0);
  const updated = Number(row.updated_count || 0);
  const duplicates = Number(row.duplicate_count || 0);
  const failures = Number(row.failure_count || 0);
  const hasQualityCounts = discovered > 0 || updated > 0 || duplicates > 0;
  const quality = hasQualityCounts
    ? `${discovered} 新 · ${updated} 更新${duplicates ? ` · ${duplicates} 重复` : ""}`
    : `${Number(row.saved_count || 0)} 保存/更新`;
  const meta = `${scanModeLabel(row.mode)} · ${quality}${failures ? ` · ${failures} 受限` : ""}`;
  return `
    <div class="source-mini-row ${escapeHtml(status)}">
      <span class="source-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(row.source || "未知来源")}</strong>
        <span>${escapeHtml(meta)}</span>
      </div>
      <span class="status-pill ${escapeHtml(status)}">${escapeHtml(label)}</span>
    </div>
  `;
}

function setTopbar(headlineText, subtitleText) {
  const headline = document.getElementById("todayHeadline");
  const subtitle = document.getElementById("todaySubtitle");
  if (headline) headline.textContent = headlineText;
  if (subtitle) subtitle.textContent = subtitleText;
}

function renderTopbarForView(view) {
  const labels = {
    today: ["今天要做什么", "正在整理今日行动、今日推荐和投递跟进。"],
    queue: ["岗位", "推荐、投递队列和关注公司集中在这里。"],
    tracker: ["追踪", "查看今日已投、历史已投和需要跟进的岗位。"],
    profile: ["设置", "调整画像、推荐偏好和同步设置。"],
    fit: ["简历与职业定位", "上传简历并生成适合投递的方向。"],
    notion: ["Notion 同步", "把投递记录同步到你自己的 Notion 数据库。"],
  };
  const [headline, subtitle] = labels[view] || labels.today;
  setTopbar(headline, subtitle);
}

function renderWorkbenchLoading() {
  const skeleton = (count) => Array.from({ length: count }, () => `
    <div class="skeleton-row" aria-hidden="true">
      <span></span><span></span><span></span>
    </div>
  `).join("");
  const actionList = document.getElementById("todayActionList");
  const priorityList = document.getElementById("priorityJobList");
  const queuePreview = document.getElementById("workbenchQueuePreview");
  if (actionList) actionList.innerHTML = skeleton(3);
  if (priorityList) priorityList.innerHTML = skeleton(4);
  if (queuePreview) queuePreview.innerHTML = `<h3>正在整理投递与跟进</h3>${skeleton(2)}`;
}

function renderWorkbench() {
  const wb = state.workbench || {};
  const summary = wb.summary || state.summary || {};
  const scan = wb.scan_overview || {};
  const todayJobs = Array.isArray(wb.today_new_recommendations) ? wb.today_new_recommendations : (wb.top_recommendations || []);
  const weeklyJobs = wb.weekly_unqueued_recommendations || [];
  const discovery = wb.discovery_summary || {};
  const selectedJobs = state.todayRecommendationBucket === "weekly_unqueued" ? weeklyJobs : todayJobs;
  const visibleRecommendationCount = Math.max(
    TODAY_RECOMMENDATION_PAGE_SIZE,
    Number(state.todayRecommendationVisibleCount || TODAY_RECOMMENDATION_PAGE_SIZE),
  );
  const visibleSelectedJobs = selectedJobs.slice(0, visibleRecommendationCount);
  const queue = (wb.queue_preview || []).slice(0, 3);
  const followups = (wb.followups || []).slice(0, 3);
  const followupCount = Number(wb.followup_count ?? followups.length);
  const staleApplicationCount = Number(wb.stale_application_count || 0);
  const todayApplied = wb.today_applied || [];
  const actions = wb.today_actions || [];
  const context = activeRegionContext();
  const preferredCoreTags = (context.preferred_job_tags || []).filter((tag) => WORKBENCH_CORE_TAGS.has(tag));
  const mutedCoreTags = (context.muted_job_tags || []).filter((tag) => WORKBENCH_CORE_TAGS.has(tag));
  const activeTags = [
    ...preferredCoreTags.slice(0, 5).map(jobTagLabel),
    ...mutedCoreTags.slice(0, 2).map((tag) => `少看 ${jobTagLabel(tag)}`),
  ].filter(Boolean);

  const todayViewActive = document.getElementById("todayView")?.classList.contains("active");
  if (todayViewActive) {
    const highCount = todayJobs.length;
    const scanText = scan.status ? (SCAN_STATUS_ZH[scan.status] || scan.status) : "待命";
    setTopbar("今天要做什么", `${highCount} 个优先机会 · ${Number(summary.apply_queue || 0)} 个待投 · ${followupCount} 个需跟进 · 扫描${scanText}`);
  }

  const actionList = document.getElementById("todayActionList");
  const tagSummary = document.getElementById("activeTagSummary");
  const priorityList = document.getElementById("priorityJobList");
  const recommendationFooter = document.getElementById("todayRecommendationFooter");
  const recommendationProgress = document.getElementById("todayRecommendationProgress");
  const showMoreRecommendations = document.getElementById("showMoreTodayRecommendations");
  const queueStats = document.getElementById("workbenchQueueStats");
  const queuePreview = document.getElementById("workbenchQueuePreview");
  const followupList = document.getElementById("workbenchFollowups");
  const queuePreviewCount = document.getElementById("workbenchQueuePreviewCount");
  const followupPreviewLabel = document.getElementById("workbenchFollowupPreviewLabel");
  const followupPreviewCount = document.getElementById("workbenchFollowupPreviewCount");

  if (actionList) {
    actionList.innerHTML = actions.length
      ? actions.map(actionItemTemplate).join("")
      : `<div class="empty-state">今天没有必须处理的事项。可以看 Top 岗位或复盘追踪表。</div>`;
  }

  if (tagSummary) {
    const visibleTags = activeTags.slice(0, 5);
    const extraTagCount = Math.max(0, activeTags.length - visibleTags.length);
    const chips = [
      ...visibleTags,
      ...(extraTagCount ? [`+${extraTagCount} 标签`] : []),
    ];
    tagSummary.innerHTML = chips.length
      ? chips.map((tag) => `<span class="chip-label active">${escapeHtml(tag)}</span>`).join("")
      : `<span class="chip-label">标签偏好可在设置里调整</span>`;
  }

  document.querySelectorAll("[data-today-bucket]").forEach((button) => {
    button.classList.toggle("active", button.dataset.todayBucket === state.todayRecommendationBucket);
  });
  const todayCount = document.getElementById("todayNewCount");
  const weeklyCount = document.getElementById("weeklyUnqueuedCount");
  if (todayCount) todayCount.textContent = todayJobs.length;
  if (weeklyCount) weeklyCount.textContent = weeklyJobs.length;

  if (priorityList) {
    const emptyText = state.todayRecommendationBucket === "weekly_unqueued"
      ? "近一周还没有未投递的综合推荐。可以启动扫描，或先处理投递队列。"
      : Number(discovery.today_discovered || 0) > 0
        ? `今天已入库 ${Number(discovery.today_discovered)} 个岗位，但暂无符合当前条件的可投推荐。可以看“近一周未投”或调整偏好。`
        : "今天还没有新发现岗位。可以看“近一周未投”，或启动扫描。";
    priorityList.innerHTML = selectedJobs.length
      ? visibleSelectedJobs.map((job) => compactJobRow(job, { priority: true })).join("")
      : emptyState(emptyText);
  }
  if (recommendationProgress) {
    recommendationProgress.textContent = selectedJobs.length
      ? `已显示 ${visibleSelectedJobs.length} / ${selectedJobs.length}`
      : "";
    recommendationProgress.hidden = !selectedJobs.length;
  }
  if (recommendationFooter) recommendationFooter.hidden = !selectedJobs.length;
  if (showMoreRecommendations) {
    const remaining = Math.max(0, selectedJobs.length - visibleSelectedJobs.length);
    showMoreRecommendations.hidden = remaining === 0;
    showMoreRecommendations.textContent = remaining
      ? `再看 ${Math.min(TODAY_RECOMMENDATION_PAGE_SIZE, remaining)} 个`
      : "";
  }

  if (queueStats) {
    queueStats.innerHTML = `
    <div><span>待投</span><strong>${summary.apply_queue || 0}</strong></div>
    <div><span>今日已投</span><strong>${summary.today_applied || 0}</strong></div>
    <div><span>待跟进</span><strong>${followupCount}</strong></div>
    <div><span>待整理</span><strong>${staleApplicationCount}</strong></div>
  `;
  }

  if (queuePreview) {
    queuePreview.innerHTML = queue.length
      ? queue.map((job) => compactJobRow(job, { queue: true, mini: true })).join("")
      : `<div class="empty-state">队列为空，从优先岗位里加入投递。</div>`;
  }
  if (queuePreviewCount) queuePreviewCount.textContent = Number(summary.apply_queue || 0);
  if (followupList) {
    followupList.innerHTML = followups.length
      ? followups.map((job) => compactJobRow(job, { followup: true, mini: true })).join("")
      : todayApplied.length
        ? todayApplied.map((job) => compactJobRow(job, { applied: true, mini: true })).join("")
        : `<div class="empty-state">暂无需要跟进的已投递岗位。</div>`;
  }
  if (followupPreviewLabel) followupPreviewLabel.textContent = followups.length ? "需要跟进" : "今日已投";
  if (followupPreviewCount) {
    followupPreviewCount.textContent = followups.length
      ? followupCount
      : Number(summary.today_applied || todayApplied.length);
  }

  const scanLabel = document.getElementById("workbenchScanLabel");
  const scanSummary = document.getElementById("workbenchScanSummary");
  const scanMeta = document.getElementById("workbenchScanMeta");
  const sourceList = document.getElementById("workbenchSourceList");
  if (scanLabel) scanLabel.textContent = `扫描${SCAN_STATUS_ZH[scan.status] || scan.status || "待命"}`;
  if (scanSummary) scanSummary.textContent = scan.summary || "今天还没有扫描记录。";
  if (scanMeta) scanMeta.textContent = `${scan.source_count || 0} 个来源 · ${scan.limited_count || 0} 个受限 · ${scan.failure_count || 0} 条失败/受限`;
  if (sourceList) {
    const sources = scan.sources || [];
    sourceList.innerHTML = sources.length
      ? sources.map(sourceMiniRow).join("")
      : `<div class="empty-state">还没有来源记录，点击刷新开始扫描。</div>`;
  }
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
  return `最近扫描 ${SCAN_STATUS_ZH[run.status] || run.status}：${run.new_count || 0} 条新发现，${run.updated_count || 0} 条更新，合并 ${run.duplicate_count || 0} 条重复；推荐 ${run.recommended_count || 0} 条。失败/受限：${failures} 条。`;
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
  const scanBtnCompact = document.getElementById("scanBtnCompact");

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
  if (scanBtnCompact && runStatus === "running") {
    setButtonState(scanBtnCompact, "loading");
  } else if (scanBtnCompact) {
    setButtonState(scanBtnCompact, "idle");
  }

  const aggregate = new Map();
  expected.map((item) => typeof item === "string" ? scanSourceLabel(item) : scanSourceLabel(item.source)).forEach((source) => {
    aggregate.set(source, { source, status: "pending", mode: sourceModes.get(source) || "primary", scanned_count: 0, saved_count: 0, new_count: 0, updated_count: 0, duplicate_count: 0, failure_count: 0 });
  });
  (run?.sources || []).forEach((item) => {
    const source = scanSourceLabel(item.source);
    const existing = aggregate.get(source) || { source, status: "pending", mode: item.mode || sourceModes.get(source) || "primary", scanned_count: 0, saved_count: 0, new_count: 0, updated_count: 0, duplicate_count: 0, failure_count: 0 };
    existing.status = mergeScanStatus(existing.status, item.status || "pending");
    existing.mode = item.mode || existing.mode;
    existing.scanned_count += Number(item.scanned_count || 0);
    existing.saved_count += Number(item.saved_count || 0);
    existing.new_count += Number(item.new_count || 0);
    existing.updated_count += Number(item.updated_count || 0);
    existing.duplicate_count += Number(item.duplicate_count || 0);
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
          <span>${escapeHtml(scanModeLabel(row.mode))} · ${row.new_count || 0} 新发现 · ${row.updated_count || 0} 更新 · ${row.duplicate_count || 0} 合并重复 · ${row.failure_count || 0} 失败</span>
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
  const suggested = (fit.suggested_directions || []).filter((item) => item.id && Number(item.score || 0) > 0);
  const suggestedScores = new Map(suggested.map((item) => [item.id, item.score]));

  document.getElementById("activeResume").textContent = active.stored_path
    ? `当前简历：${active.original_filename || active.filename || fileName(active.stored_path)} · ${active.stored_path}`
    : "当前还没有可分析的简历。";
  document.getElementById("careerFitSummary").textContent = analysis?.summary || "还没有分析结果。上传简历或点击本地分析后，这里会生成适合投递的方向。";
  const suggestedIds = new Set(suggested.map((item) => item.id));
  const manualDirections = (fit.all_directions || []).filter((direction) => !suggestedIds.has(direction.id));
  const chip = (direction) => {
    const score = suggestedScores.has(direction.id) ? ` ${Math.round(suggestedScores.get(direction.id) * 100)}%` : "";
    return `<button class="chip-button ${selected.has(direction.id) ? "active" : ""}" data-direction-id="${escapeHtml(direction.id)}">${escapeHtml(direction.label)}${score}</button>`;
  };
  document.getElementById("directionChips").innerHTML = suggested.length
    ? `
      ${suggested.map((direction) => chip(direction)).join("")}
      <details class="custom-option direction-more">
        <summary>其它候选方向</summary>
        <div class="chip-row">${manualDirections.map((direction) => chip(direction)).join("")}</div>
      </details>
    `
    : emptyState(analysis ? "这份简历暂时没有明显方向信号。可以补充项目经历，或在资料页手动添加方向。" : "分析简历后会按内容生成方向。");

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
  const hiddenStaleCount = (state.jobs || []).filter((job) => (
    job.listing_freshness_status === "likely_closed"
    && !RECOMMENDATION_EXCLUDED_STATUSES.has(job.status)
    && !job.company_watched_by_user
    && !job.company_hidden_by_watchlist
    && String(job.source || "").trim() !== "关注公司公开来源"
    && baseJobScore(job) >= 3
  )).length;
  const freshnessNote = hiddenStaleCount ? ` 已自动收起 ${hiddenStaleCount} 个可能已下架岗位。` : "";
  const viewCopy = {
    fit: "留新补充会综合方向、转正、工签和语言信号。",
    ai: "AI 方向只保留额外的 AI、Product 与 UX 机会。",
    general: "高分补漏按综合匹配排序，适合最后快速扫一遍。",
  };
  const prefix = viewCopy[state.recommendationView] || viewCopy.fit;
  if (source === "user_context") {
    document.getElementById("recommendationContext").textContent = `${prefix} 已排除今日推荐、投递队列、关注公司岗位和已隐藏公司；按画像里的 ${count} 个方向重排。${freshnessNote}`;
    return;
  }
  const text = source === "user_selected"
    ? `${prefix} 正在按你选择的 ${count} 个方向重排。`
    : source === "resume_analysis"
      ? `${prefix} 系统暂时按简历分析出的 ${count} 个方向重排。`
      : `${prefix} 当前按基础评分排序。`;
  document.getElementById("recommendationContext").textContent = `${text}${freshnessNote}`;
}

function renderJobs() {
  const panelHints = {
    recommendations: "这里补充今日推荐之外的机会；不会重复今日推荐、投递队列或关注公司岗位。",
    queue: "这里完整显示你加入投递队列的岗位，不再截断。",
    companies: "关注公司和公司岗位集中在这里，左侧选公司，右侧看岗位。",
  };
  document.querySelectorAll("[data-jobs-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.jobsPanel === state.jobsPanel);
  });
  document.querySelectorAll("[data-jobs-panel-section]").forEach((section) => {
    const active = section.dataset.jobsPanelSection === state.jobsPanel;
    section.hidden = !active;
    section.classList.toggle("active", active);
  });
  const jobsPanelHint = document.getElementById("jobsPanelHint");
  if (jobsPanelHint) jobsPanelHint.textContent = panelHints[state.jobsPanel] || panelHints.recommendations;
  if (!state.workspaceDataLoaded && state.workspaceDataPromise) {
    renderWorkspaceDataLoading();
    return;
  }

  const shortlistIds = workbenchShortlistJobIds();
  const fitJobs = collapseSupplementalJobs((state.recommendations.jobs || []).filter((job) => isSupplementalRecommendationCandidate(job, shortlistIds))).slice(0, SUPPLEMENTAL_RECOMMENDATION_POOL_SIZE);
  const aiJobs = collapseSupplementalJobs(state.aiJobs.filter((job) => isSupplementalRecommendationCandidate(job, shortlistIds))).slice(0, 20);
  const visible = state.jobs
    .filter((job) => isSupplementalRecommendationCandidate(job, shortlistIds))
    .filter((job) => !state.activeFilter || job.status === state.activeFilter);
  const generalJobs = collapseSupplementalJobs([...visible]
    .sort((a, b) =>
      generalJobRank(b) - generalJobRank(a)
      || baseJobScore(b) - baseJobScore(a)
      || dateToTime(b.found_date || b.updated_at) - dateToTime(a.found_date || a.updated_at)
    ))
    .slice(0, SUPPLEMENTAL_RECOMMENDATION_POOL_SIZE);
  const jobsByRecommendationView = { fit: fitJobs, ai: aiJobs, general: generalJobs };
  const activeRecommendationJobs = jobsByRecommendationView[state.recommendationView] || fitJobs;
  const visibleRecommendationCount = Math.max(
    SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE,
    Number(state.supplementalRecommendationVisibleCount || SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE),
  );

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
  const supplementalFooter = document.getElementById("supplementalRecommendationFooter");
  const supplementalProgress = document.getElementById("supplementalRecommendationProgress");
  const showMoreSupplemental = document.getElementById("showMoreSupplementalRecommendations");
  fitList.hidden = state.recommendationView !== "fit";
  aiList.hidden = state.recommendationView !== "ai";
  generalList.hidden = state.recommendationView !== "general";
  fitList.innerHTML = fitJobs.length ? fitJobs.slice(0, visibleRecommendationCount).map((job) => compactJobRow(job)).join("") : emptyState("今日推荐已覆盖主要候选；这里暂时没有额外推荐。");
  aiList.innerHTML = aiJobs.length ? aiJobs.slice(0, visibleRecommendationCount).map((job) => compactJobRow(job)).join("") : emptyState("今日推荐之外暂时没有新的 AI、Product 或 UX 候选。");
  generalList.innerHTML = generalJobs.length ? generalJobs.slice(0, visibleRecommendationCount).map((job) => compactJobRow(job)).join("") : emptyState("今日推荐之外暂时没有其它高分补充岗位。");
  const visibleSupplementalCount = Math.min(visibleRecommendationCount, activeRecommendationJobs.length);
  const remainingSupplementalCount = Math.max(0, activeRecommendationJobs.length - visibleSupplementalCount);
  if (supplementalFooter) supplementalFooter.hidden = !activeRecommendationJobs.length;
  if (supplementalProgress) supplementalProgress.textContent = activeRecommendationJobs.length
    ? `已显示 ${visibleSupplementalCount} / ${activeRecommendationJobs.length}`
    : "";
  if (showMoreSupplemental) {
    showMoreSupplemental.hidden = remainingSupplementalCount === 0;
    showMoreSupplemental.textContent = remainingSupplementalCount
      ? `再看 ${Math.min(SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE, remainingSupplementalCount)} 个`
      : "";
  }

  const queue = state.jobs
    .filter((job) => job.status === "Apply Queue")
    .sort(compareQueueUrgency);
  const today = state.summary.date || new Date().toISOString().slice(0, 10);
  const todayApplied = state.jobs.filter((job) => job.status === "Applied" && job.applied_date === today);
  const queueList = document.getElementById("queueList");
  queueList.setAttribute("aria-busy", "false");
  queueList.innerHTML = queue.length
    ? queue.map((job) => compactJobRow(job, { queue: true })).join("")
    : emptyState("投递队列为空。你可以从今日推荐里选择“加入投递”。");
  const queueListStatus = document.getElementById("queueListStatus");
  if (queueListStatus) {
    if (state.jobsPanel === "companies") {
      const recommended = (state.companyCatalog || []).filter((company) => !company.watched);
      queueListStatus.textContent = `${state.watchlist.length} 已关注 · ${recommended.length} 推荐`;
    } else if (state.jobsPanel === "recommendations") {
      queueListStatus.textContent = `${fitJobs.length} 个推荐 · ${queue.length} 个待投递`;
    } else {
      queueListStatus.textContent = `${queue.length} 个待投递 · 已完整显示`;
    }
  }
  document.getElementById("queueMiniCount").textContent = `${queue.length} 队列 · ${todayApplied.length} 已投`;
  const queuePreview = queue.slice(0, 4).map((job) => `<div class="mini-item"><strong>${escapeHtml(job.company)}</strong><span class="small-text">${escapeHtml(job.position)}</span></div>`).join("");
  const appliedPreview = todayApplied.slice(0, 5).map((job) => `<div class="mini-item applied-mini-item"><strong>${escapeHtml(job.company)}</strong><span class="small-text">${escapeHtml(job.position)}</span></div>`).join("");
  document.getElementById("queueMiniList").innerHTML = `
    <div class="mini-group">
      <div class="mini-group-title">待投递预览</div>
      ${queuePreview || `<div class="mini-item"><span class="small-text">还没有待投递岗位。</span></div>`}
      ${queue.length > 4 ? `<button class="tertiary-button compact-button mini-nav-button" type="button" data-nav-queue>查看全部 ${queue.length} 个</button>` : ""}
    </div>
    <div class="mini-group">
      <div class="mini-group-title">今日已投</div>
      ${appliedPreview || `<div class="mini-item"><span class="small-text">今天还没有确认已投递。</span></div>`}
    </div>
  `;

  renderTrackerRows();
}

function filterTrackerJobs() {
  const today = state.summary.date || new Date().toISOString().slice(0, 10);
  const query = String(state.trackerQuery || "").trim().toLowerCase();
  const trackingStatuses = new Set(["Apply Queue", "Applied", "Follow Up", "Interview", "Rejected", "Dropped", "Closed", "Watch"]);
  const actionPriority = {
    "Apply Queue": 6,
    "Follow Up": 5,
    Interview: 5,
    Applied: 4,
    Watch: 3,
    Rejected: 2,
    Dropped: 1,
    Closed: 1,
  };
  return state.jobs
    .filter((job) => {
      if (state.trackerStatus === "all" && !trackingStatuses.has(job.status)) return false;
      if (state.trackerStatus === "AppliedToday") {
        if (!(job.status === "Applied" && job.applied_date === today)) return false;
      } else if (state.trackerStatus === "Applied") {
        if (!(job.status === "Applied" && job.applied_date !== today)) return false;
      } else if (state.trackerStatus === "Follow Up") {
        const elapsed = daysSince(job.applied_date);
        const needsFollowUp = job.status === "Follow Up" || (job.status === "Applied" && elapsed >= 3 && elapsed <= 14);
        if (!needsFollowUp) return false;
      } else if (state.trackerStatus === "Stale") {
        if (!(job.status === "Applied" && daysSince(job.applied_date) > 14)) return false;
      } else if (state.trackerStatus === "Paused") {
        if (!["Dropped", "Closed"].includes(job.status)) return false;
      } else if (state.trackerStatus !== "all" && job.status !== state.trackerStatus) {
        return false;
      }
      const dates = trackerDates(job);
      if (state.trackerMode === "day" && !dates.includes(state.trackerDate)) return false;
      if (state.trackerMode === "month" && !dates.some((date) => date.startsWith(state.trackerMonth))) return false;
      if (query && ![job.company, job.position, job.name, job.source]
        .some((value) => String(value || "").toLowerCase().includes(query))) return false;
      return true;
    })
    .sort((a, b) =>
      (state.trackerStatus === "all" ? (actionPriority[b.status] || 0) - (actionPriority[a.status] || 0) : 0)
      || timelineDate(b).localeCompare(timelineDate(a))
      || displayJobScore(b) - displayJobScore(a)
    );
}

function trackerNextStep(job) {
  if (job.status === "Apply Queue") {
    const deadline = deadlineInfo(job);
    if (deadline.code === "expired") return "截止日期已过，请先确认岗位是否仍开放。";
    if (deadline.code === "today") return "今天截止，优先完成投递。";
    if (["urgent", "soon"].includes(deadline.code)) return `${deadline.label}，建议优先投递。`;
    return "打开填表助手，完成后确认已投。";
  }
  if (job.status === "Follow Up") return "今天安排一次轻量跟进。";
  if (job.status === "Applied") {
    const elapsed = daysSince(job.applied_date);
    const followupElapsed = daysSince(job.last_followup_at);
    const followupCount = Number(job.followup_count || 0);
    if (job.last_followup_at && followupElapsed < 7) return `已记录第 ${followupCount} 次跟进，等待反馈。`;
    if (job.last_followup_at && followupElapsed >= 7 && followupCount >= 2) return `已跟进 ${followupCount} 次仍无回复，可暂停归档。`;
    if (job.last_followup_at && followupElapsed >= 7) return "可以安排第二次跟进。";
    if (elapsed > 14) return `已投 ${elapsed} 天，最后确认一次后可暂停。`;
    return elapsed >= 3 ? `已投 ${elapsed} 天，可以跟进。` : "等待反馈，保留岗位记录。";
  }
  if (job.status === "Interview") return "准备面试并记录下一轮时间。";
  if (job.status === "Rejected") return "已结束，可保留用于复盘。";
  if (job.status === "Dropped" || job.status === "Closed") return "已暂停，不进入每日行动；需要时可恢复。";
  return "查看岗位详情，决定是否加入队列。";
}

function trackerActionButtons(job) {
  const elapsed = daysSince(job.applied_date);
  const followupElapsed = daysSince(job.last_followup_at);
  const followupCount = Number(job.followup_count || 0);
  const queueButtons = job.status === "Apply Queue"
    ? `<button class="primary-button compact-button" data-action="assist" data-id="${job.id}" title="打开浏览器并填常见字段，最终提交前停住">${icon.assist} 填表</button><button class="secondary-button compact-button" data-action="confirm" data-id="${job.id}" title="仅在你已经完成外部申请后记录">${icon.submit} 确认已投</button>`
    : "";
  const followupDue = job.status === "Follow Up"
    || (job.status === "Applied" && (followupElapsed >= 7 ? followupCount < 2 : !job.last_followup_at && elapsed >= 3 && elapsed <= 14));
  const stale = job.status === "Applied" && ((job.last_followup_at && followupElapsed >= 7 && followupCount >= 2) || (!job.last_followup_at && elapsed > 14));
  const followupButton = followupDue || stale
    ? `<button class="secondary-button compact-button" data-action="followup-draft" data-id="${job.id}" title="生成可复制的跟进邮件，不会自动发送">${stale ? "最后跟进" : "写跟进"}</button>`
    : "";
  const pauseButton = stale
    ? `<button class="tertiary-button compact-button" data-action="Pause" data-id="${job.id}">暂停</button>`
    : "";
  const restoreButton = ["Dropped", "Closed"].includes(job.status)
    ? `<button class="secondary-button compact-button" data-action="Restore" data-id="${job.id}">恢复推荐</button>`
    : "";
  return `<div class="tracker-row-actions">${queueButtons}<a href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">原岗位</a>${followupButton}${pauseButton}${restoreButton}</div>`;
}

function renderTrackerControls(filteredCount, startIndex, endIndex, totalPages) {
  document.querySelectorAll(".tracker-mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.trackerMode === state.trackerMode);
  });
  document.querySelectorAll(".tracker-status-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.trackerStatus === state.trackerStatus);
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
  const searchInput = document.getElementById("trackerSearchInput");
  if (searchInput && searchInput.value !== state.trackerQuery) searchInput.value = state.trackerQuery;
  const trackerStatusLabels = {
    all: "追踪记录",
    "Apply Queue": "投递队列岗位",
    AppliedToday: "今日已投递岗位",
    Applied: "历史已投递岗位",
    "Follow Up": "待跟进岗位",
    Stale: "长期无回复岗位",
    Paused: "暂停/放弃岗位",
    Rejected: "已拒绝岗位",
  };
  const statusLabelText = trackerStatusLabels[state.trackerStatus] || "岗位";
  const label = state.trackerMode === "day" ? `${state.trackerDate} 的${statusLabelText}` : state.trackerMode === "month" ? `${state.trackerMonth} 整月${statusLabelText}` : `全部${statusLabelText}`;
  const range = filteredCount ? `${startIndex + 1}-${endIndex}` : "0";
  document.getElementById("trackerCount").textContent = `${label} · 显示 ${range}，共 ${filteredCount}`;
  document.getElementById("trackerPageLabel").textContent = `第 ${state.trackerPage} / ${totalPages} 页`;
  document.getElementById("trackerPrevPage").disabled = state.trackerPage <= 1;
  document.getElementById("trackerNextPage").disabled = state.trackerPage >= totalPages;
}

function renderTrackerRows() {
  const jobs = filterTrackerJobs();
  const totalPages = Math.max(1, Math.ceil(jobs.length / state.trackerPageSize));
  state.trackerPage = Math.max(1, Math.min(state.trackerPage, totalPages));
  const startIndex = (state.trackerPage - 1) * state.trackerPageSize;
  const pageJobs = jobs.slice(startIndex, startIndex + state.trackerPageSize);
  renderTrackerControls(jobs.length, startIndex, startIndex + pageJobs.length, totalPages);
  const trackerRows = document.getElementById("trackerRows");
  trackerRows.closest("table")?.setAttribute("aria-busy", "false");
  trackerRows.innerHTML = jobs.length
    ? pageJobs.map((job) => `
        <tr>
          <td class="tracker-job-cell" data-label="岗位"><strong>${escapeHtml(job.company || "-")}</strong><span>${escapeHtml(job.position || "-")}</span><small>${escapeHtml(job.source || "-")}</small></td>
          <td data-label="状态"><span class="status-pill">${escapeHtml(statusLabel(job.status))}</span></td>
          <td data-label="匹配">${displayJobScore(job).toFixed(1)}</td>
          <td data-label="关键日期">${escapeHtml(timelineDate(job) || "-")}</td>
          <td class="tracker-next-cell" data-label="下一步">${escapeHtml(trackerNextStep(job))}</td>
          <td class="tracker-link-cell" data-label="操作">${trackerActionButtons(job)}</td>
        </tr>
      `).join("")
    : `<tr><td colspan="6">这个筛选范围里还没有岗位记录。</td></tr>`;
}

function renderWorkspaceDataLoading() {
  const skeleton = Array.from({ length: 3 }, () => `
    <div class="skeleton-row" aria-hidden="true"><span></span><span></span><span></span></div>
  `).join("");
  const queueList = document.getElementById("queueList");
  if (queueList) {
    queueList.setAttribute("aria-busy", "true");
    queueList.innerHTML = skeleton;
  }
  document.querySelectorAll("[data-recommendation-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.recommendationView === state.recommendationView);
  });
  [["fitJobList", "fit"], ["aiJobList", "ai"], ["jobList", "general"]].forEach(([id, view]) => {
    const list = document.getElementById(id);
    if (!list) return;
    list.hidden = state.recommendationView !== view;
    list.setAttribute("aria-busy", "true");
    list.innerHTML = skeleton;
  });
  ["fitJobCount", "aiJobCount", "generalJobCount"].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.textContent = "…";
  });
  const supplementalFooter = document.getElementById("supplementalRecommendationFooter");
  if (supplementalFooter) supplementalFooter.hidden = true;
  const knownQueueCount = Number(state.summary.apply_queue || state.workbench?.summary?.apply_queue || 0);
  const queueListStatus = document.getElementById("queueListStatus");
  if (queueListStatus) {
    queueListStatus.textContent = state.jobsPanel === "queue"
      ? `${knownQueueCount} 个待投递 · 正在加载明细`
      : state.jobsPanel === "companies"
        ? "正在加载关注公司…"
        : `正在加载补充候选… · ${knownQueueCount} 个待投递`;
  }
  const queueMiniCount = document.getElementById("queueMiniCount");
  if (queueMiniCount) queueMiniCount.textContent = `${knownQueueCount} 队列 · 明细加载中`;
  const companyList = document.getElementById("companyList");
  const companyCatalog = document.getElementById("companyCatalog");
  const companyJobs = document.getElementById("companyJobs");
  if (companyList) companyList.innerHTML = skeleton;
  if (companyCatalog) companyCatalog.innerHTML = skeleton;
  if (companyJobs) companyJobs.innerHTML = skeleton;
  const trackerRows = document.getElementById("trackerRows");
  if (trackerRows) {
    trackerRows.closest("table")?.setAttribute("aria-busy", "true");
    trackerRows.innerHTML = `<tr><td colspan="6">正在加载完整岗位记录...</td></tr>`;
  }
  const trackerCount = document.getElementById("trackerCount");
  if (trackerCount) trackerCount.textContent = "正在加载完整岗位记录...";
  const trackerPageLabel = document.getElementById("trackerPageLabel");
  if (trackerPageLabel) trackerPageLabel.textContent = "加载中";
  document.getElementById("trackerPrevPage").disabled = true;
  document.getElementById("trackerNextPage").disabled = true;
}

function jobsForCompany(company) {
  return state.companyJobs?.[company]?.jobs || [];
}

function companyJobCount(company) {
  return Number(state.companyJobs?.[company]?.matched_jobs_count ?? companyByName(company)?.matched_jobs_count ?? 0);
}

function companyByName(companyName) {
  return [...(state.watchlist || []), ...(state.companyCatalog || [])].find((item) => item.company === companyName);
}

async function loadCompanyJobs(companyName) {
  if (!companyName || state.companyJobs[companyName] || state.companyJobsLoading[companyName]) return;
  state.companyJobsLoading[companyName] = true;
  const company = companyByName(companyName) || {};
  const params = new URLSearchParams(regionQuery());
  params.set("company", companyName);
  if (company.id) params.set("company_id", company.id);
  try {
    state.companyJobs[companyName] = await api(`/api/company-jobs?${params.toString()}`);
  } catch (error) {
    toast(error.message, "error");
    state.companyJobs[companyName] = { company: companyName, jobs: [], matched_jobs_count: 0, last_scan_note: "加载公司岗位失败。" };
  } finally {
    delete state.companyJobsLoading[companyName];
    renderWatchlist();
  }
}

function companyRow(company, config = {}) {
  const watched = Boolean(config.watched || company.watched);
  const dismissed = Boolean(company.dismissed || company.status === "Dropped");
  const tags = [
    company.region || activeRegion(),
    company.company_type || company.source,
    companyGroupLabel(company.company_group),
    ...(company.tags || []).slice(0, 2),
    company.language_signal || "",
    company.sponsorship_signal === "possible" ? "工签可能待确认" : "",
    dismissed ? "已隐藏岗位" : "",
  ].filter(Boolean);
  const jobsCount = dismissed ? 0 : companyJobCount(company.company);
  return `
    <article class="company-row ${state.selectedCompany === company.company ? "active" : ""} ${dismissed ? "is-dismissed" : ""}" data-company="${escapeHtml(company.company)}">
      <button class="company-select" type="button" data-company="${escapeHtml(company.company)}">
        <span class="company-row-main">
          <strong>${escapeHtml(company.company)}</strong>
          <span>${escapeHtml(company.focus || "关注官网岗位")}</span>
        </span>
        <span class="company-row-meta">
          ${tags.slice(0, 3).map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`).join("")}
          <span class="badge fit-badge">${jobsCount} 岗位</span>
        </span>
      </button>
      <div class="company-row-actions">
        <a class="tertiary-button compact-button" href="${escapeHtml(company.url)}" target="_blank" rel="noreferrer">官网</a>
        ${watched
          ? `<button class="tertiary-button compact-button" data-watch-action="remove" data-watch-id="${company.id}">取消</button>`
          : dismissed
            ? `<button class="primary-button compact-button" data-watch-action="add-catalog" data-company="${escapeHtml(company.company)}">重新关注</button>`
            : `<button class="secondary-button compact-button" data-watch-action="add-catalog" data-company="${escapeHtml(company.company)}">关注</button><button class="tertiary-button compact-button" data-watch-action="dismiss-catalog" data-company="${escapeHtml(company.company)}">不关注</button>`}
      </div>
    </article>
  `;
}

function renderCompanyJobs() {
  const title = document.getElementById("companyJobsTitle");
  const container = document.getElementById("companyJobs");
  const detail = document.getElementById("companyDetailCard");
  const detailText = document.getElementById("companyDetailText");
  const actions = document.getElementById("companyDetailActions");
  if (!state.selectedCompany) {
    title.textContent = "选择一家公司查看岗位";
    if (detailText) detailText.textContent = "点击左侧公司后，这里会立即显示公司信息和相关岗位。";
    if (detail) detail.innerHTML = "";
    if (actions) actions.innerHTML = "";
    container.innerHTML = emptyState("点击上方公司卡片后，这里会显示该公司相关岗位。");
    return;
  }
  const company = companyByName(state.selectedCompany) || {};
  const isWatched = (state.watchlist || []).some((item) => item.company === state.selectedCompany);
  const isDismissed = Boolean(company.dismissed || company.status === "Dropped");
  if (!isDismissed && !state.companyJobs[state.selectedCompany] && !state.companyJobsLoading[state.selectedCompany]) {
    loadCompanyJobs(state.selectedCompany);
  }
  const payload = state.companyJobs[state.selectedCompany] || {};
  const jobs = isDismissed ? [] : jobsForCompany(state.selectedCompany);
  const loading = Boolean(state.companyJobsLoading[state.selectedCompany]);
  const totalCount = isDismissed ? 0 : Number(payload.matched_jobs_count ?? company.matched_jobs_count ?? jobs.length);
  const officialCount = jobs.filter((job) => job.company_match_source_group === "official").length || Number(company.matched_official_count || 0);
  const publicCount = Math.max(0, totalCount - officialCount);
  title.textContent = isDismissed ? `${state.selectedCompany} 已隐藏岗位` : `${state.selectedCompany} 相关岗位`;
  if (detailText) {
    detailText.textContent = isDismissed
      ? "你已选择暂时不关注这家公司；重新关注后才会显示它的岗位。"
      : loading
      ? "正在匹配官网、ATS 和公共来源岗位..."
      : `${totalCount} 个匹配岗位 · 官网/ATS ${officialCount} · 公共来源 ${publicCount} · ${isWatched ? "已关注，会进入官网扫描" : "推荐关注，可加入雷达"}`;
  }
  if (detail) {
    const badges = [
      company.company_type || company.source,
      companyGroupLabel(company.company_group),
      ...(company.city_tags || []),
      ...(company.tags || []),
      company.language_signal || "",
      company.sponsorship_signal === "possible" ? "工签可能待确认" : "",
      company.intern_to_fulltime_signal === "possible" ? "可转正待确认" : "",
    ].filter(Boolean).slice(0, 6);
    detail.innerHTML = `
      <div>
        <h3>${escapeHtml(company.company || state.selectedCompany)}</h3>
        <p>${escapeHtml(company.focus || "暂无方向说明。")}</p>
        <div class="badge-row">${badges.map((tag) => `<span class="badge ${String(tag).includes("AI") || String(tag).includes("产品") ? "fit-badge" : ""}">${escapeHtml(tag)}</span>`).join("")}</div>
        ${company.recommend_reason ? `<p class="company-reason">${escapeHtml(company.recommend_reason)}</p>` : ""}
        ${(payload.last_scan_note || company.last_scan_note) ? `<p class="company-scan-note">${escapeHtml(payload.last_scan_note || company.last_scan_note)}</p>` : ""}
      </div>
    `;
  }
  if (actions) {
    actions.innerHTML = `
      ${company.url ? `<a class="secondary-button compact-button" href="${escapeHtml(company.url)}" target="_blank" rel="noreferrer">岗位入口</a>` : ""}
      ${isWatched
        ? ""
        : `<button class="primary-button compact-button" data-watch-action="add-catalog" data-company="${escapeHtml(company.company || state.selectedCompany)}">${isDismissed ? "重新关注" : "关注"}</button>`}
    `;
  }
  if (isDismissed) {
    container.innerHTML = emptyState("已隐藏这家公司岗位。重新关注后，它的岗位会回到公司岗位区和扫描逻辑里。");
  } else if (loading) {
    container.innerHTML = emptyState("正在加载这家公司匹配岗位...");
  } else if (jobs.length) {
    container.innerHTML = jobs.map((job) => jobCard({
      ...job,
      source: job.company_match_source_label || job.source,
    })).join("");
  } else {
    container.innerHTML = emptyState(payload.last_scan_note || company.last_scan_note || "暂时没有抓到这家公司可展示岗位。");
  }
}

function renderWatchlist() {
  const watched = document.getElementById("companyList");
  const catalog = document.getElementById("companyCatalog");
  if (!watched || !catalog) return;
  const recommended = (state.companyCatalog || [])
    .filter((company) => !company.watched)
    .sort((a, b) => Number(Boolean(a.dismissed || a.status === "Dropped")) - Number(Boolean(b.dismissed || b.status === "Dropped")));
  const allNames = new Set([...(state.watchlist || []), ...(state.companyCatalog || [])].map((item) => item.company));
  if (state.selectedCompany && !allNames.has(state.selectedCompany)) state.selectedCompany = "";
  if (!state.selectedCompany) {
    state.selectedCompany = state.watchlist[0]?.company || recommended[0]?.company || "";
  }
  const visibleRecommended = state.showAllCompanyRecommendations ? recommended : recommended.slice(0, 6);
  watched.hidden = state.companyTab !== "watched";
  catalog.hidden = state.companyTab !== "recommended";
  watched.innerHTML = state.watchlist.length ? state.watchlist.map((company) => companyRow(company, { watched: true })).join("") : emptyState("还没有关注公司。可以从推荐里选择，或粘贴官网招聘链接。");
  catalog.innerHTML = visibleRecommended.length ? visibleRecommended.map((company) => companyRow(company)).join("") : emptyState("当前地区推荐公司都已关注。");
  document.querySelectorAll("[data-company-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.companyTab === state.companyTab);
  });
  const moreBtn = document.getElementById("companyMoreBtn");
  if (moreBtn) {
    moreBtn.hidden = state.companyTab !== "recommended" || recommended.length <= 6;
    moreBtn.textContent = state.showAllCompanyRecommendations ? "收起推荐" : `展开更多推荐（${recommended.length - 6}）`;
  }
  renderCompanyMiniList(recommended);
  renderCompanyJobs();
}

function renderCompanyMiniList(recommended = []) {
  const mini = document.getElementById("companyMiniList");
  if (!mini) return;
  const top = recommended.filter((company) => !(company.dismissed || company.status === "Dropped")).slice(0, 3);
  mini.innerHTML = top.length ? top.map((company) => `
    <button class="mini-item mini-company-button" type="button" data-company-mini="${escapeHtml(company.company)}">
      <strong>${escapeHtml(company.company)}</strong>
      <span class="small-text">${escapeHtml(company.company_type || company.focus || "推荐关注")}</span>
    </button>
  `).join("") : `<div class="mini-item"><span class="small-text">当前重点公司都已关注。</span></div>`;
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
    const tokenLabel = status.token_configured ? "Token 已配置" : "缺少 Notion token";
    const databaseLabel = status.database_id_configured ? "Database ID 已配置" : "缺少 database ID";
    const sourceLabel = status.source === "user" ? "当前账号配置" : (status.source === "env" ? "本地开发配置" : "未配置");
    document.getElementById("notionConfigStatus").innerHTML = `
      <span class="config-pill ${status.token_configured ? "ok" : "warn"}">${escapeHtml(tokenLabel)}</span>
      <span class="config-pill ${status.database_id_configured ? "ok" : "warn"}">${escapeHtml(databaseLabel)}</span>
      <span class="small-text">${escapeHtml(sourceLabel)}${status.updated_at ? " · " + escapeHtml(status.updated_at) : ""}</span>
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

async function submitNotionConfig(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const statusNode = document.getElementById("notionConfigSaveStatus");
  statusNode.textContent = "保存中...";
  try {
    await api("/api/notion-config", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    statusNode.textContent = "已保存当前账号的 Notion 配置。";
    await renderNotionSchema();
  } catch (error) {
    statusNode.textContent = error.message;
    toast(error.message, "error");
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

function workspaceDataKey() {
  return regionQuery();
}

function invalidateWorkspaceData() {
  state.workspaceDataLoaded = false;
  state.workspaceDataKey = "";
  state.workspaceDataPromise = null;
  state.jobs = [];
  state.aiJobs = [];
  state.watchlist = [];
  state.companyCatalog = [];
  state.companyJobs = {};
  state.companyJobsLoading = {};
}

async function loadWorkspaceData({ force = false } = {}) {
  const key = workspaceDataKey();
  if (!force && state.workspaceDataLoaded && state.workspaceDataKey === key) return;
  if (state.workspaceDataPromise) return state.workspaceDataPromise;
  const regionParam = regionQuery();
  state.workspaceDataPromise = (async () => {
    const [jobs, aiJobs, recommendations, watchlist, companyCatalog] = await Promise.all([
      api(`/api/jobs?${regionParam}&compact=1`),
      api(`/api/jobs/ai?limit=20&${regionParam}&compact=1`),
      api(`/api/recommendations/today?limit=120&${regionParam}&compact=1`),
      api(`/api/watchlist?${regionParam}`),
      api(`/api/company-catalog?${regionParam}`),
    ]);
    if (key !== workspaceDataKey()) return;
    state.jobs = jobs;
    state.aiJobs = aiJobs;
    state.recommendations = recommendations;
    state.watchlist = watchlist;
    state.companyCatalog = companyCatalog;
    state.workspaceDataLoaded = true;
    state.workspaceDataKey = key;
    renderJobs();
    if (document.getElementById("queueView")?.classList.contains("active") && state.jobsPanel === "companies") {
      renderWatchlist();
    }
  })();
  try {
    await state.workspaceDataPromise;
  } finally {
    state.workspaceDataPromise = null;
  }
}

async function loadNotionData({ force = false } = {}) {
  if (!force && state.notionDataLoaded) return;
  if (state.notionDataPromise) return state.notionDataPromise;
  state.notionDataPromise = renderNotionSchema();
  try {
    await state.notionDataPromise;
    state.notionDataLoaded = true;
  } finally {
    state.notionDataPromise = null;
  }
}

async function refresh() {
  if (!state.workbench?.date) renderWorkbenchLoading();
  const reloadWorkspace = state.workspaceDataLoaded;
  const [regions, userContext] = await Promise.all([
    api("/api/regions"),
    api("/api/user-context"),
  ]);
  state.regions = regions;
  state.userContext = userContext;
  const region = activeRegion();
  state.profileOptions = await api(`/api/profile-options?region=${encodeURIComponent(region)}`);
  const regionParam = regionQuery();
  const [workbench, daily, profile, careerFit, scanStatus] = await Promise.all([
    api(`/api/workbench?${regionParam}`),
    api(`/api/daily/status?${regionParam}`),
    api("/api/profile"),
    api("/api/career-fit"),
    api(`/api/scan/status?${regionParam}`),
  ]);
  state.workbench = workbench;
  state.todayRecommendationVisibleCount = TODAY_RECOMMENDATION_PAGE_SIZE;
  state.summary = workbench.summary || {};
  state.daily = daily;
  state.profile = profile;
  state.careerFit = careerFit;
  state.recommendations = workbench.recommendations || { jobs: [], active_direction_ids: [], direction_source: "base_score" };
  state.scan = scanStatus;
  state.companyJobs = {};
  state.companyJobsLoading = {};
  setTrackerDefaults();
  renderUserContextControls();
  renderMetrics();
  renderScanRun(scanStatus);
  renderWorkbench();
  renderCareerFit();
  renderProfileForm();
  if (reloadWorkspace) {
    try {
      await loadWorkspaceData({ force: true });
    } catch (error) {
      toast(`完整岗位数据暂时没加载完：${error.message}`, "error");
    }
  }
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
  const isCompactScanButton = button?.id === "scanBtnCompact";
  setButtonState(button, "loading", isCompactScanButton ? "" : "启动扫描...");
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
          career_goal: payload.career_goal || "sg_internship_to_fulltime",
          sponsorship_priority: payload.sponsorship_priority || "high",
          language_preference: payload.language_preference || "chinese_friendly",
          conversion_priority: payload.conversion_priority || "high",
          preferred_company_groups: splitList(payload.preferred_company_groups),
          preferred_job_tags: splitList(payload.preferred_job_tags),
          muted_job_tags: splitList(payload.muted_job_tags),
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
  if (!resumeAnalyzed()) {
    toast("请先上传并分析简历，再保存首次设置。", "error");
    state.onboardingStep = 2;
    renderOnboarding();
    return;
  }
  syncOnboardingCustomInputs(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  const active_region = payload.active_region || activeRegion();
  const target_directions = splitList(payload.target_directions);
  const status = document.getElementById("onboardingStatus");
  await withButton(button, "保存中...", async () => {
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({
        active_region,
        context: {
          city: payload.city,
          target_directions,
          job_types: splitList(payload.job_types),
          work_authorisation: payload.work_authorisation,
          employment_priority: payload.employment_priority,
          career_goal: payload.career_goal || "sg_internship_to_fulltime",
          sponsorship_priority: payload.sponsorship_priority || "high",
          language_preference: payload.language_preference || "chinese_friendly",
          conversion_priority: payload.conversion_priority || "high",
          preferred_company_groups: splitList(payload.preferred_company_groups),
          preferred_job_tags: splitList(payload.preferred_job_tags),
          muted_job_tags: splitList(payload.muted_job_tags),
          salary_currency: state.profileOptions.salary_currency,
          salary_period: payload.salary_period,
          salary_min: payload.salary_min,
          salary_preferred: payload.salary_preferred,
        },
        resume_analyzed: true,
        onboarding_step: 3,
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

async function advanceOnboardingLocation(event) {
  const button = event.currentTarget;
  const form = document.getElementById("onboardingForm");
  const region = document.getElementById("onboardingRegion")?.value || activeRegion();
  const city = document.getElementById("onboardingCity")?.value || "";
  if (state.profileOptions.city_required && !city) {
    document.getElementById("onboardingLocationStatus").textContent = "请先选择城市。";
    toast("中国大陆岗位需要先选择城市。", "error");
    return;
  }
  if (form) {
    form.elements.active_region.value = region;
    form.elements.city.value = city;
  }
  await withButton(button, "保存地区...", async () => {
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({
        active_region: region,
        context: {
          city,
          salary_currency: state.profileOptions.salary_currency,
        },
        onboarding_step: 2,
      }),
    });
    state.onboardingStep = 2;
    state.dailyRunChecked = false;
    renderUserContextControls();
  }, "已保存");
}

async function analyzeOnboardingResume(event) {
  const button = event.currentTarget;
  const fileInput = document.getElementById("onboardingResumeInput");
  const status = document.getElementById("onboardingAnalyzeStatus");
  if (!fileInput?.files?.length) {
    status.textContent = "请选择 PDF、DOCX、MD 或 TXT 简历。";
    toast("请先选择简历文件。", "error");
    return;
  }
  await withButton(button, "分析中...", async () => {
    const resumeData = new FormData();
    resumeData.append("resume", fileInput.files[0]);
    await api("/api/resumes", { method: "POST", body: resumeData });
    state.careerFit = await api("/api/career-fit");
    const context = activeRegionContext();
    const suggested = suggestedDirectionIds();
    const nextDirections = suggested.length ? suggested : (context.target_directions || []);
    state.userContext = await api("/api/user-context", {
      method: "PUT",
      body: JSON.stringify({
        active_region: activeRegion(),
        context: {
          city: activeCity(),
          target_directions: nextDirections,
          job_types: context.job_types || ["Internship", "Graduate", "Full-time"],
          employment_priority: context.employment_priority || "internship",
          career_goal: context.career_goal || "sg_internship_to_fulltime",
          sponsorship_priority: context.sponsorship_priority || "high",
          language_preference: context.language_preference || "chinese_friendly",
          conversion_priority: context.conversion_priority || "high",
          preferred_company_groups: context.preferred_company_groups || ["greater_china", "ai_startup", "sg_anchor"],
          preferred_job_tags: context.preferred_job_tags || ["internship", "conversion_possible", "visa_possible", "chinese_friendly", "ai_related", "product_related"],
          muted_job_tags: context.muted_job_tags || ["visa_unlikely", "conversion_none", "high_experience"],
          salary_currency: state.profileOptions.salary_currency,
        },
        resume_analyzed: true,
        onboarding_step: 3,
      }),
    });
    if (nextDirections.length) {
      await api("/api/career-fit/preferences", {
        method: "PUT",
        body: JSON.stringify({ selected_directions: nextDirections }),
      });
    }
    state.onboardingStep = 3;
    await refreshFocusData("简历已分析，已按结果预选方向。");
    status.textContent = "分析完成，可以确认偏好。";
  }, "已分析");
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
  const reloadWorkspace = state.workspaceDataLoaded;
  const target = document.getElementById("jobFocusPanel");
  target?.classList.add("is-updating");
  document.querySelector(".recommendation-switch-head")?.classList.add("is-updating");
  try {
    const [workbench, scanStatus] = await Promise.all([
      api(`/api/workbench?${regionParam}`),
      api(`/api/scan/status?${regionParam}`),
    ]);
    state.workbench = workbench;
    state.todayRecommendationVisibleCount = TODAY_RECOMMENDATION_PAGE_SIZE;
    state.summary = workbench.summary || {};
    state.recommendations = workbench.recommendations || { jobs: [], active_direction_ids: [], direction_source: "base_score" };
    state.scan = scanStatus;
    state.companyJobs = {};
    state.companyJobsLoading = {};
    renderUserContextControls();
    renderMetrics();
    renderScanRun(scanStatus);
    renderWorkbench();
    renderJobs();
    toast(recommendationScopeMessage(message, state.recommendations), "success");
    if (reloadWorkspace) {
      try {
        await loadWorkspaceData({ force: true });
      } catch (error) {
        toast(`完整岗位数据暂时没加载完：${error.message}`, "error");
      }
    }
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
    body: JSON.stringify({ active_region: region, onboarding_step: state.userContext?.onboarding_step || state.onboardingStep || 1 }),
  });
  state.selectedCompany = "";
  state.showAllCompanyRecommendations = false;
  state.dailyRunChecked = false;
  await refresh();
}

async function changeCity(city) {
  const context = activeRegionContext();
  context.city = city;
  renderUserContextControls();
  state.selectedCompany = "";
  state.showAllCompanyRecommendations = false;
  state.userContext = await api("/api/user-context", {
    method: "PUT",
    body: JSON.stringify({
      active_region: activeRegion(),
      context: {
        city,
        salary_currency: context.salary_currency || state.profileOptions.salary_currency,
      },
      onboarding_step: state.userContext?.onboarding_step || state.onboardingStep || 1,
    }),
  });
  scheduleFocusRefresh(`已切换到 ${city || activeRegionConfig().label}，岗位和公司正在重排。`);
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

async function applyPathwayPreset(action) {
  const preset = PATHWAY_PRESETS[action];
  if (!preset) return;
  const context = activeRegionContext();
  const patch = { ...preset.patch };
  if (patch.target_directions) {
    patch.target_directions = uniqueList([...(context.target_directions || []), ...patch.target_directions]);
  }
  if (patch.job_types) {
    patch.job_types = uniqueList([...(context.job_types || []), ...patch.job_types]);
  }
  if (patch.preferred_company_groups) {
    patch.preferred_company_groups = uniqueList([...(context.preferred_company_groups || []), ...patch.preferred_company_groups]);
  }
  if (patch.preferred_job_tags) {
    patch.preferred_job_tags = uniqueList([...(context.preferred_job_tags || []), ...patch.preferred_job_tags]);
  }
  if (patch.muted_job_tags) {
    patch.muted_job_tags = uniqueList([...(context.muted_job_tags || []), ...patch.muted_job_tags]);
  }
  if (patch.preferred_job_tags && patch.muted_job_tags) {
    const preferred = new Set(patch.preferred_job_tags);
    patch.muted_job_tags = patch.muted_job_tags.filter((tag) => !preferred.has(tag));
  }
  Object.assign(context, patch);
  renderUserContextControls();
  state.userContext = await api("/api/user-context", {
    method: "PUT",
    body: JSON.stringify({
      active_region: activeRegion(),
      context: {
        ...patch,
        salary_currency: context.salary_currency || state.profileOptions.salary_currency,
      },
      onboarding_completed: true,
    }),
  });
  if (patch.target_directions?.length) {
    await api("/api/career-fit/preferences", {
      method: "PUT",
      body: JSON.stringify({ selected_directions: patch.target_directions }),
    });
  }
  scheduleFocusRefresh(`已切换为「${preset.label}」，推荐会按留新加坡路径重排。`);
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
  if (action === "dismiss-catalog") {
    const item = catalogCompany(button.dataset.company);
    if (!item) return;
    await withButton(button, "隐藏中...", async () => {
      await api("/api/watchlist/dismiss", {
        method: "POST",
        body: JSON.stringify({ ...item, region: activeRegion() }),
      });
      if (state.selectedCompany === item.company) state.selectedCompany = "";
      await refresh();
      toast(`${item.company} 的岗位已暂时隐藏。`, "success");
    }, "已隐藏");
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
    state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}&compact=1`);
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
    state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}&compact=1`);
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
  state.recommendations = await api(`/api/recommendations/today?limit=20&${regionQuery()}&compact=1`);
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
    toast(`已保存：${job.company}，评分 ${displayJobScore(job).toFixed(1)}/5.0`, "success");
  }, "已保存");
}

async function handleJobAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const fromDetail = Boolean(button.closest("#detailDialog"));
  const fromFollowup = Boolean(button.closest("#followupDialog"));
  const action = button.dataset.action;
  const id = button.dataset.id;
  if (action === "detail") {
    await showDetail(Number(id), button);
    return;
  }
  if (action === "followup-draft") {
    await showFollowupDraft(Number(id), button);
    return;
  }
  if (action === "assist") {
    await withButton(button, "打开浏览器...", async () => {
      const result = await api(`/api/jobs/${id}/apply-assist`, { method: "POST", body: "{}" });
      toast(result.message || "填表助手已打开。最终提交前请逐项检查。", "success");
      await refresh();
      if (fromDetail) closeDetailDialog();
    }, "已打开");
    return;
  }
  if (action === "confirm") {
    await withButton(button, "确认中...", async () => {
      await api(`/api/jobs/${id}/confirm-applied`, { method: "POST", body: "{}" });
      await refresh();
      if (fromDetail) closeDetailDialog();
      toast("已记录为已投递。", "success");
    }, "已确认");
    return;
  }
  await withButton(button, "更新中...", async () => {
    await api(`/api/jobs/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: action }) });
    await refresh();
    const messages = {
      Apply: "已加入投递队列。",
      Watch: "已加入关注。",
      FollowUpSent: "已记录本次跟进，7 天内不会重复提醒。",
      Pause: "已暂停并保留历史记录。",
      Restore: "已恢复，可重新进入推荐候选。",
    };
    if (action === "Drop") {
      const undoAction = button.dataset.undoAction || "Restore";
      const droppedFromQueue = undoAction === "Apply";
      toast(droppedFromQueue ? "已移出投递队列，记录仍保留。" : "已隐藏此岗位，不再进入推荐。", "success", {
        label: "撤销",
        pendingLabel: "恢复中...",
        onClick: async () => {
          await api(`/api/jobs/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: undoAction }) });
          await refresh();
          toast(droppedFromQueue ? "岗位已放回投递队列。" : "岗位已恢复。", "success");
        },
      });
    } else {
      toast(messages[action] || "岗位状态已更新。", "success");
    }
    if (fromDetail) closeDetailDialog();
    if (fromFollowup) closeFollowupDialog();
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
  const pathwayEvidence = (job.evidence || job.pathway_evidence_json || [])
    .slice(0, 6)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const alternateLinks = (job.alternate_links || [])
    .filter((item) => item.url)
    .map((item) => `<a class="secondary-button source-link-button" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.source || "其它来源")}</a>`)
    .join("");
  const pathwayQuestions = (job.pathway_questions || [])
    .slice(0, 4)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  return `
    <div class="detail-block">
      <h3>记录</h3>
      <p class="small-text">状态 ${escapeHtml(statusLabel(job.status))} · 匹配 ${displayJobScore(job).toFixed(1)}/5.0 · 留新路径 ${Number(job.pathway_score || 0).toFixed(1)}</p>
      ${alternateLinks ? `<div class="alternate-source-links"><span class="small-text">同一岗位的其它入口</span>${alternateLinks}</div>` : ""}
    </div>
    <div class="detail-block">
      <h3>一句判断</h3>
      <p>${escapeHtml(job.decision_summary || job.recommendation_reason || "请打开原始 JD 确认转正、工签和语言要求。")}</p>
      ${pathwayEvidence ? `<ul class="evidence-mini-list">${pathwayEvidence}</ul>` : ""}
      ${pathwayQuestions ? `<div class="pathway-question-box"><h4>投递前建议确认</h4><ul>${pathwayQuestions}</ul></div>` : ""}
    </div>
    <details class="detail-block detail-disclosure">
      <summary><strong>完整推荐依据</strong><span>查看算法命中的方向、标签与风险</span></summary>
      <p>${escapeHtml(job.recommendation_reason || "暂无完整推荐依据。")}</p>
    </details>
    <div class="detail-block">
      <h3>匹配说明</h3>
      <p>${escapeHtml(job.match_notes || "暂无匹配说明。")}</p>
    </div>
    <details class="detail-block detail-disclosure">
      <summary><strong>中文 JD</strong><span>展开阅读完整翻译</span></summary>
      <pre>${escapeHtml(cnText || "正在生成中文 JD，请稍等...")}</pre>
    </details>
    <div class="detail-block">
      <h3>材料路径</h3>
      <div class="material-list">
        ${materialPathTemplate("简历", job.resume_path)}
        ${materialPathTemplate("Cover letter", job.cover_letter_path)}
      </div>
    </div>
    <details class="detail-block detail-disclosure">
      <summary><strong>原始 JD</strong><span>以官方英文内容为准</span></summary>
      <pre>${escapeHtml(job.jd_text)}</pre>
    </details>
  `;
}

function detailActionsTemplate(job) {
  const id = Number(job.id);
  const canQueue = isRecommendationCandidate(job);
  const isQueue = job.status === "Apply Queue";
  const isApplied = ["Applied", "Follow Up", "Interview"].includes(job.status);
  const nextStep = isQueue
    ? "准备材料并完成申请"
    : isApplied
      ? "已记录，按追踪提醒跟进"
      : canQueue
        ? "值得投递就加入队列"
        : "打开官方岗位进一步确认";
  return `
    <div class="detail-next-step">
      <span>下一步</span>
      <strong>${escapeHtml(nextStep)}</strong>
    </div>
    <div class="detail-action-buttons">
      <a class="secondary-button" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">打开原岗位</a>
      ${canQueue ? `<button class="primary-button" type="button" data-action="Apply" data-id="${id}">${icon.apply} 加入投递</button>` : ""}
      ${isQueue ? `<button class="primary-button" type="button" data-action="assist" data-id="${id}">${icon.assist} 打开填表助手</button><button class="secondary-button" type="button" data-action="confirm" data-id="${id}">${icon.submit} 确认已投</button>` : ""}
      ${isApplied ? `<span class="status-pill">${escapeHtml(statusLabel(job.status))}</span>` : ""}
    </div>
  `;
}

async function showDetail(id, trigger = null) {
  detailReturnFocus = trigger || document.activeElement;
  let baseJob = state.jobs.find((item) => item.id === id);
  if (!baseJob?.jd_text) {
    const fullJob = await api(`/api/jobs/${id}`);
    baseJob = { ...(baseJob || {}), ...fullJob };
    const index = state.jobs.findIndex((job) => job.id === fullJob.id);
    if (index >= 0) state.jobs[index] = baseJob;
  }
  const detailBody = document.getElementById("detailBody");
  const detailActions = document.getElementById("detailActions");
  const liveStatus = document.getElementById("detailLiveStatus");
  document.getElementById("detailTitle").textContent = `${baseJob.company} - ${baseJob.position}`;
  detailBody.innerHTML = detailTemplate(baseJob, baseJob.jd_cn_text);
  detailActions.innerHTML = detailActionsTemplate(baseJob);
  detailBody.setAttribute("aria-busy", baseJob.jd_cn_text ? "false" : "true");
  liveStatus.textContent = baseJob.jd_cn_text ? "岗位详情已加载。" : "岗位详情已加载，正在生成中文 JD。";
  document.getElementById("detailDialog").showModal();
  if (!baseJob.jd_cn_text) {
    try {
      const translatedJob = await api(`/api/jobs/${id}/translate`, { method: "POST", body: "{}" });
      detailBody.innerHTML = detailTemplate(translatedJob, translatedJob.jd_cn_text);
      detailActions.innerHTML = detailActionsTemplate(translatedJob);
      detailBody.setAttribute("aria-busy", "false");
      liveStatus.textContent = "中文 JD 已生成。";
      const index = state.jobs.findIndex((job) => job.id === translatedJob.id);
      if (index >= 0) state.jobs[index] = translatedJob;
    } catch (error) {
      detailBody.innerHTML = detailTemplate(baseJob, `中文 JD 生成失败：${error.message}`);
      detailBody.setAttribute("aria-busy", "false");
      liveStatus.textContent = "中文 JD 生成失败，仍可查看原始 JD。";
    }
  }
}

function closeDetailDialog() {
  const dialog = document.getElementById("detailDialog");
  if (dialog.open) dialog.close();
}

function followupDraft(job) {
  const name = String(state.profile?.full_name || "").trim();
  const signature = name && name !== "Your Name" ? name : "";
  const secondFollowup = Number(job.followup_count || 0) > 0;
  const subject = `Following up on my application for ${job.position}`;
  const opening = secondFollowup
    ? `I wanted to follow up once more on my application for the ${job.position} role at ${job.company}.`
    : `I hope you're well. I'm following up on my application for the ${job.position} role at ${job.company}, submitted on ${job.applied_date || "the application date"}.`;
  const body = [
    "Hi Hiring Team,",
    "",
    opening,
    "",
    "I remain very interested in the opportunity and would be grateful for any update you can share. Please let me know if I can provide any additional information.",
    "",
    "Thank you for your time and consideration.",
    "",
    "Best regards,",
    signature,
  ].filter((line, index, lines) => line || index !== lines.length - 1).join("\n");
  return { subject, body };
}

async function showFollowupDraft(id, trigger = null) {
  const job = await api(`/api/jobs/${id}`);
  const draft = followupDraft(job);
  followupReturnFocus = trigger || document.activeElement;
  document.getElementById("followupContext").textContent = `${job.company} · ${job.position} · 已投 ${job.applied_date || "日期待确认"}`;
  document.getElementById("followupSubject").value = draft.subject;
  document.getElementById("followupMessage").value = draft.body;
  document.getElementById("markFollowupSent").dataset.id = String(job.id);
  document.getElementById("followupDialog").showModal();
}

function closeFollowupDialog() {
  const dialog = document.getElementById("followupDialog");
  if (dialog.open) dialog.close();
}

async function writeClipboardText(value) {
  if (navigator.clipboard?.writeText) {
    try {
      await Promise.race([
        navigator.clipboard.writeText(value),
        new Promise((_, reject) => window.setTimeout(() => reject(new Error("Clipboard timeout")), 900)),
      ]);
      return;
    } catch (_error) {
      // Some embedded browsers expose Clipboard API but leave permission requests pending.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("浏览器未允许复制，请手动选择正文复制。");
}

async function copyFollowupDraft(event) {
  const subject = document.getElementById("followupSubject").value.trim();
  const message = document.getElementById("followupMessage").value.trim();
  await withButton(event.currentTarget, "复制中...", async () => {
    await writeClipboardText(`Subject: ${subject}\n\n${message}`);
    toast("跟进邮件已复制，可以粘贴到邮箱或 LinkedIn。", "success");
  }, "已复制");
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

async function submitAuth(event) {
  event.preventDefault();
  if (!state.auth.client) {
    showAuthScreen("登录服务还没有准备好，请刷新页面。");
    return;
  }
  const email = document.getElementById("authEmail").value.trim();
  if (!email) return;
  const status = document.getElementById("authStatus");
  if (status) status.textContent = "正在发送登录链接...";
  const { error } = await state.auth.client.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: window.location.origin },
  });
  if (error) {
    if (status) status.textContent = error.message;
    toast(error.message, "error");
    return;
  }
  if (status) status.textContent = "登录链接已发送，请去邮箱点击后回到这里。";
  toast("登录链接已发送。", "success");
}

async function signOut() {
  if (!state.auth.client) return;
  await state.auth.client.auth.signOut();
}

function showView(view) {
  if (view === "companies") {
    state.jobsPanel = "companies";
    view = "queue";
  }
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  document.querySelectorAll(".view").forEach((panel) => panel.classList.remove("active"));
  document.getElementById(`${view}View`)?.classList.add("active");
  renderTopbarForView(view);
  if (view === "queue" || view === "tracker") {
    const workspaceLoad = loadWorkspaceData();
    if (!state.workspaceDataLoaded) {
      renderJobs();
      renderWorkspaceDataLoading();
    } else {
      renderJobs();
    }
    workspaceLoad.catch((error) => toast(`完整岗位数据暂时没加载完：${error.message}`, "error"));
    if (view === "queue" && state.jobsPanel === "companies" && state.workspaceDataLoaded) renderWatchlist();
  }
  if (view === "notion") {
    loadNotionData().catch((error) => toast(error.message, "error"));
  }
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
  if (field === "preferred_job_tags" || field === "muted_job_tags") {
    const opposite = field === "preferred_job_tags" ? "muted_job_tags" : "preferred_job_tags";
    const cleanedOpposite = selectedValuesFromHidden(form, opposite).filter((item) => !next.includes(item));
    setHiddenList(form, opposite, cleanedOpposite);
    context[opposite] = cleanedOpposite;
  }
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
  document.getElementById("authForm")?.addEventListener("submit", submitAuth);
  document.getElementById("signOutBtn")?.addEventListener("click", signOut);
  document.getElementById("jobForm").addEventListener("submit", submitJob);
  document.getElementById("profileForm").addEventListener("submit", submitProfile);
  document.getElementById("contextForm").addEventListener("submit", submitUserContext);
  document.getElementById("onboardingForm").addEventListener("submit", submitOnboarding);
  document.getElementById("onboardingNextBtn").addEventListener("click", advanceOnboardingLocation);
  document.getElementById("onboardingAnalyzeBtn").addEventListener("click", analyzeOnboardingResume);
  document.getElementById("onboardingBackToLocationBtn").addEventListener("click", () => {
    state.onboardingStep = 1;
    renderOnboarding();
  });
  document.getElementById("onboardingBackToResumeBtn").addEventListener("click", () => {
    state.onboardingStep = 2;
    renderOnboarding();
  });
  document.getElementById("companyAddForm").addEventListener("submit", submitCompany);
  document.getElementById("resumeUploadForm").addEventListener("submit", uploadResume);
  document.getElementById("focusRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("focusCity").addEventListener("change", (event) => changeCity(event.target.value));
  document.getElementById("contextRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("contextCity").addEventListener("change", (event) => changeCity(event.target.value));
  document.getElementById("onboardingRegion").addEventListener("change", (event) => changeRegion(event.target.value));
  document.getElementById("onboardingCity").addEventListener("change", (event) => {
    const form = document.getElementById("onboardingForm");
    if (form?.elements?.city) form.elements.city.value = event.target.value;
  });
  document.getElementById("contextSalaryPeriod").addEventListener("change", () => syncSalaryPeriodControls("context"));
  document.getElementById("onboardingSalaryPeriod").addEventListener("change", () => syncSalaryPeriodControls("onboarding"));
  document.getElementById("scanBtn").addEventListener("click", scanJobs);
  document.getElementById("scanBtnCompact")?.addEventListener("click", scanJobs);
  document.getElementById("reportBtn").addEventListener("click", makeReport);
  document.getElementById("notionSyncBtn").addEventListener("click", syncNotion);
  document.getElementById("notionConfigForm")?.addEventListener("submit", submitNotionConfig);
  document.getElementById("localAnalyzeBtn").addEventListener("click", (event) => analyzeCareerFit("local", event.currentTarget));
  document.getElementById("aiAnalyzeBtn").addEventListener("click", (event) => analyzeCareerFit("ai", event.currentTarget));
  const detailDialog = document.getElementById("detailDialog");
  document.getElementById("closeDialog").addEventListener("click", closeDetailDialog);
  detailDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDetailDialog();
  });
  detailDialog.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    closeDetailDialog();
  });
  detailDialog.addEventListener("close", () => {
    if (detailReturnFocus?.isConnected) detailReturnFocus.focus();
    detailReturnFocus = null;
  });
  const followupDialog = document.getElementById("followupDialog");
  document.getElementById("closeFollowupDialog").addEventListener("click", closeFollowupDialog);
  document.getElementById("copyFollowupDraft").addEventListener("click", copyFollowupDraft);
  followupDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeFollowupDialog();
  });
  followupDialog.addEventListener("close", () => {
    if (followupReturnFocus?.isConnected) followupReturnFocus.focus();
    followupReturnFocus = null;
  });
  document.body.addEventListener("click", handleJobAction);
  document.body.addEventListener("click", handleOpenPath);
  document.body.addEventListener("click", handleWatchAction);
  document.body.addEventListener("click", handleOptionChip);
  document.body.addEventListener("click", (event) => {
    const pathwayButton = event.target.closest("[data-pathway-action]");
    if (pathwayButton) {
      applyPathwayPreset(pathwayButton.dataset.pathwayAction).catch((error) => toast(error.message, "error"));
      return;
    }
    const actionItem = event.target.closest("[data-action-view]");
    if (actionItem) {
      if (actionItem.dataset.actionView === "queue" && actionItem.dataset.actionKind === "queue") {
        state.jobsPanel = "queue";
      }
      showView(actionItem.dataset.actionView || "today");
      return;
    }
    const todayBucket = event.target.closest("[data-today-bucket]");
    if (todayBucket) {
      state.todayRecommendationBucket = todayBucket.dataset.todayBucket;
      state.todayRecommendationVisibleCount = TODAY_RECOMMENDATION_PAGE_SIZE;
      renderWorkbench();
      return;
    }
    if (event.target.closest("[data-show-more-today-recommendations]")) {
      state.todayRecommendationVisibleCount += TODAY_RECOMMENDATION_PAGE_SIZE;
      renderWorkbench();
      return;
    }
    if (event.target.closest("[data-show-more-supplemental-recommendations]")) {
      state.supplementalRecommendationVisibleCount += SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE;
      renderJobs();
      return;
    }
    if (event.target.closest("[data-nav-fit]")) showView("fit");
    if (event.target.closest("[data-nav-companies]")) {
      state.jobsPanel = "companies";
      showView("queue");
      return;
    }
    if (event.target.closest("[data-nav-notion]")) showView("notion");
    if (event.target.closest("[data-nav-queue]")) {
      state.jobsPanel = "queue";
      showView("queue");
      return;
    }
    const miniCompany = event.target.closest("[data-company-mini]");
    if (miniCompany) {
      state.selectedCompany = miniCompany.dataset.companyMini;
      state.companyTab = "recommended";
      state.jobsPanel = "companies";
      showView("queue");
      renderWatchlist();
      return;
    }
    const chip = event.target.closest("[data-direction-id]");
    if (chip) toggleDirection(chip.dataset.directionId);
  });
  document.querySelectorAll("#companyList, #companyCatalog").forEach((list) => list.addEventListener("click", (event) => {
    const card = event.target.closest("[data-company]");
    if (!card) return;
    if (event.target.closest("[data-watch-action]")) return;
    state.selectedCompany = card.dataset.company;
    renderWatchlist();
  }));
  document.querySelectorAll("[data-company-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.companyTab = button.dataset.companyTab;
      renderWatchlist();
    });
  });
  document.getElementById("companyMoreBtn").addEventListener("click", () => {
    state.showAllCompanyRecommendations = !state.showAllCompanyRecommendations;
    renderWatchlist();
  });
  document.querySelectorAll("[data-jobs-panel]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobsPanel = button.dataset.jobsPanel;
      renderJobs();
      if (state.jobsPanel === "companies") renderWatchlist();
    });
  });
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-recommendation-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.recommendationView = button.dataset.recommendationView;
      state.supplementalRecommendationVisibleCount = SUPPLEMENTAL_RECOMMENDATION_PAGE_SIZE;
      renderJobs();
    });
  });
  document.querySelectorAll(".tracker-mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.trackerMode = button.dataset.trackerMode;
      state.trackerPage = 1;
      renderJobs();
    });
  });
  document.querySelectorAll(".tracker-status-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.trackerStatus = button.dataset.trackerStatus;
      state.trackerPage = 1;
      renderJobs();
    });
  });
  document.getElementById("trackerSearchInput").addEventListener("input", (event) => {
    state.trackerQuery = event.target.value;
    state.trackerPage = 1;
    renderTrackerRows();
  });
  document.getElementById("trackerDateInput").addEventListener("change", (event) => {
    state.trackerDate = event.target.value;
    state.trackerMode = "day";
    state.trackerPage = 1;
    renderJobs();
  });
  document.getElementById("trackerMonthInput").addEventListener("change", (event) => {
    state.trackerMonth = event.target.value;
    state.trackerMode = "month";
    state.trackerPage = 1;
    renderJobs();
  });
  document.getElementById("trackerPrevPage").addEventListener("click", () => {
    state.trackerPage = Math.max(1, state.trackerPage - 1);
    renderTrackerRows();
  });
  document.getElementById("trackerNextPage").addEventListener("click", () => {
    state.trackerPage += 1;
    renderTrackerRows();
  });
}

async function boot() {
  bindEvents();
  const ready = await initAuth();
  if (!ready) return;
  await refresh();
  await checkDailyAutoRun();
}

boot().catch((error) => {
  document.getElementById("fitJobList").innerHTML = emptyState(error.message);
  toast(error.message, "error");
});
