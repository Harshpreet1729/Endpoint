// Cookie-authenticated API writes need the same CSRF token as HTML forms.
const csrf = document.querySelector(".forms").dataset.csrf;
const notice = document.querySelector("#notice");
const previousNotice = sessionStorage.getItem("eventgate-notice");
if (previousNotice) {
    notice.textContent = previousNotice;
    sessionStorage.removeItem("eventgate-notice");
}
for (const form of document.querySelectorAll(".api-form")) {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button");
        button.disabled = true;
        notice.className = "";
        try {
            const data = Object.fromEntries(new FormData(form));
            for (const name of ["endpoint", "max_attempts", "retry_base_delay"]) {
                if (name in data) data[name] = Number(data[name]);
            }
            if ("payload" in data) data.payload = JSON.parse(data.payload);
            if (data.idempotency_key === "") delete data.idempotency_key;
            const response = await fetch(form.dataset.api, {
                method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Check the form values and try again.");
            sessionStorage.setItem("eventgate-notice", `Saved successfully (ID ${result.id}).`);
            location.reload();
        } catch (error) {
            notice.className = "error";
            notice.textContent = error.message;
            notice.scrollIntoView({behavior: "smooth", block: "center"});
        } finally {
            button.disabled = false;
        }
    });
}
