// Injects a floating "minsky" panel into the SWAYAM course-catalog page.
// The panel takes a free-text goal, sends it to the background service
// worker (which calls the local minsky API), and renders the resolved
// filters + ranked course shortlist + rationale it gets back.
//
// All rendering uses createElement/textContent rather than innerHTML, since
// course titles/rationale text ultimately originate from an external API
// response and must never be interpreted as HTML.

const FILTER_LABELS = {
  national_coordinator: "National Coordinator",
  course_mode: "Course Mode",
  course_duration: "Course Duration",
  course_language: "Course Language",
  educational_level: "Educational Level",
  industry_sector: "Industry/Sector",
  credits: "Credits",
  category: "Category",
};

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") node.className = value;
    else if (key === "textContent") node.textContent = value;
    else if (key === "href") node.setAttribute("href", value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.appendChild(child);
  return node;
}

function buildPanel() {
  const root = document.createElement("div");
  root.id = "minsky-root";

  const toggle = el("button", { id: "minsky-toggle", title: "minsky", type: "button" });
  toggle.textContent = "M";

  const panel = el("div", { id: "minsky-panel", hidden: "" }, [
    el("h3", { textContent: "minsky" }),
    el("p", {
      className: "minsky-subtitle",
      textContent: "What are you trying to accomplish?",
    }),
  ]);

  const input = el("textarea", {
    id: "minsky-intent-input",
    placeholder: "e.g. I want to become job-ready in data analytics within 3 months",
  });
  panel.appendChild(input);

  const submit = el("button", { id: "minsky-submit", type: "button", textContent: "Resolve" });
  panel.appendChild(submit);

  const status = el("div", { id: "minsky-status" });
  panel.appendChild(status);

  const results = el("div", { id: "minsky-results" });
  panel.appendChild(results);

  root.appendChild(panel);
  root.appendChild(toggle);

  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
  });

  submit.addEventListener("click", () => handleSubmit(input, submit, status, results));
  input.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" && (evt.metaKey || evt.ctrlKey)) {
      handleSubmit(input, submit, status, results);
    }
  });

  return root;
}

function handleSubmit(input, submit, status, results) {
  const intent = input.value.trim();
  results.replaceChildren();
  if (!intent) {
    status.textContent = "Type what you're trying to accomplish first.";
    return;
  }

  submit.disabled = true;
  status.textContent = "Resolving...";

  chrome.runtime.sendMessage({ type: "MINSKY_RESOLVE", intent, topN: 5 }, (response) => {
    submit.disabled = false;
    if (chrome.runtime.lastError) {
      status.textContent = "";
      renderError(results, chrome.runtime.lastError.message);
      return;
    }
    if (!response || !response.ok) {
      status.textContent = "";
      renderError(results, (response && response.error) || "Unknown error");
      return;
    }
    status.textContent = "";
    renderResult(results, response.data);
  });
}

function renderError(results, message) {
  results.appendChild(el("div", { className: "minsky-error", textContent: message }));
}

function renderResult(results, data) {
  results.replaceChildren();

  // -- resolved filters --------------------------------------------------
  results.appendChild(el("div", { className: "minsky-section-title", textContent: "Resolved filters" }));
  const nonNullFilters = Object.entries(data.filters || {}).filter(([, v]) => v !== null && v !== "");
  if (nonNullFilters.length === 0) {
    results.appendChild(el("div", { textContent: "(nothing confidently resolved)" }));
  } else {
    for (const [key, value] of nonNullFilters) {
      results.appendChild(
        el("div", { className: "minsky-filter-row" }, [
          el("span", { className: "minsky-filter-key", textContent: FILTER_LABELS[key] || key }),
          el("span", { textContent: String(value) }),
        ])
      );
    }
  }

  // -- ranked courses ------------------------------------------------------
  results.appendChild(el("div", { className: "minsky-section-title", textContent: "Top matches" }));
  const ranked = data.ranked_courses || [];
  if (ranked.length === 0) {
    results.appendChild(el("div", { textContent: "No matching courses found." }));
  } else {
    for (const entry of ranked) {
      const course = entry.course || {};
      const courseDiv = el("div", { className: "minsky-course" });
      if (course.url) {
        courseDiv.appendChild(
          el("a", { href: course.url, target: "_blank", rel: "noopener noreferrer", textContent: course.title })
        );
      } else {
        courseDiv.appendChild(el("span", { textContent: course.title || "(untitled course)" }));
      }
      courseDiv.appendChild(
        el("div", {
          className: "minsky-course-meta",
          textContent: `${course.provider || "?"} · ${course.duration_weeks || "?"} weeks · score ${entry.score}`,
        })
      );
      results.appendChild(courseDiv);
    }
  }

  // -- rationale -------------------------------------------------------------
  if (data.rationale) {
    results.appendChild(el("div", { className: "minsky-rationale", textContent: data.rationale }));
  }
}

if (!document.getElementById("minsky-root")) {
  document.body.appendChild(buildPanel());
}
