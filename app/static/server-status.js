(function () {
    const healthPath = "/health";
    const maxAttempts = 5;
    const requestTimeoutMs = 5000;

    function sleep(milliseconds) {
        return new Promise(resolve => window.setTimeout(resolve, milliseconds));
    }

    async function fetchWithRetry(url, options = {}, attempts = maxAttempts) {
        const method = (options.method || "GET").toUpperCase();
        const retryCount = method === "GET" || method === "HEAD" ? attempts : 1;
        let lastError;

        for (let attempt = 0; attempt < retryCount; attempt += 1) {
            const controller = new AbortController();
            const timeout = window.setTimeout(() => controller.abort(), requestTimeoutMs);

            try {
                const response = await fetch(url, {
                    ...options,
                    method,
                    cache: "no-store",
                    signal: controller.signal
                });
                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }
                return response;
            } catch (error) {
                lastError = error;
            } finally {
                window.clearTimeout(timeout);
            }

            if (attempt + 1 < retryCount) {
                await sleep(Math.min(500 * (2 ** attempt), 4000));
            }
        }

        throw lastError;
    }

    window.fetchWithRetry = fetchWithRetry;

    const status = document.querySelector("[data-server-status]");
    const compareForms = document.querySelectorAll('form[action="/compare"]');

    compareForms.forEach(form => {
        form.addEventListener("submit", () => {
            if (status) {
                status.hidden = false;
                status.textContent = "Your check is starting. On the free tier, a waking server can take up to a minute.";
            }
        });
    });

    fetchWithRetry(healthPath).catch(() => {
        if (status) {
            status.hidden = false;
            status.textContent = "The server is taking longer than usual to respond. Please wait a moment and try again.";
        }
    });
})();
