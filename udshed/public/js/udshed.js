window.Udshed = window.Udshed || {};

window.Udshed.Loading = (function () {
    let active = 0;
    let overlay = null;
    let startedAt = 0;
    let hideTimer = null;

    const styles = `
        .udshed-loading-overlay {
            position: fixed;
            inset: 0;
            z-index: 19000;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: rgba(15, 23, 42, 0.3);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.15s ease;
        }
        .udshed-loading-overlay.is-visible {
            opacity: 1;
            pointer-events: auto;
        }
        .udshed-loading-card {
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 260px;
            max-width: 420px;
            padding: 14px 18px;
            background: #fff;
            border: 1px solid #d0d5dd;
            border-radius: 10px;
            box-shadow: 0 18px 48px rgba(15, 23, 42, 0.28);
            transform: translateY(6px);
            transition: transform 0.15s ease;
        }
        .udshed-loading-overlay.is-visible .udshed-loading-card {
            transform: translateY(0);
        }
        .udshed-loading-spinner {
            width: 22px;
            height: 22px;
            flex: 0 0 22px;
            border: 3px solid #dbe3ef;
            border-top-color: #1d4ed8;
            border-radius: 50%;
            animation: udshed-loading-spin 0.75s linear infinite;
        }
        .udshed-loading-label {
            font-size: 13px;
            font-weight: 600;
            color: #344054;
            line-height: 1.4;
        }
        @keyframes udshed-loading-spin {
            to { transform: rotate(360deg); }
        }
    `;

    function ensure_styles() {
        if ($('#udshed-loading-styles').length) return;
        $('<style id="udshed-loading-styles"></style>').text(styles).appendTo('head');
    }

    function show(message) {
        ensure_styles();
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        if (!active) startedAt = Date.now();
        active += 1;
        if (!overlay) {
            overlay = $(`
                <div class="udshed-loading-overlay" role="status" aria-live="polite">
                    <div class="udshed-loading-card">
                        <span class="udshed-loading-spinner"></span>
                        <span class="udshed-loading-label"></span>
                    </div>
                </div>
            `).appendTo('body');
        }
        const label = message || __('Chargement des données...');
        overlay.find('.udshed-loading-label').text(active > 1 ? `${label} (${active})` : label);
        overlay.addClass('is-visible');
        $('body').attr('aria-busy', 'true');
    }

    function finish_hide() {
        hideTimer = null;
        if (active) return;
        if (overlay) {
            overlay.removeClass('is-visible');
            setTimeout(() => {
                if (!active && overlay) {
                    overlay.remove();
                    overlay = null;
                }
            }, 160);
        }
        $('body').removeAttr('aria-busy');
    }

    function hide() {
        active = Math.max(0, active - 1);
        if (active) return;
        const remaining = Math.max(0, 250 - (Date.now() - startedAt));
        if (remaining) hideTimer = setTimeout(finish_hide, remaining);
        else finish_hide();
    }

    function call(options) {
        const opts = Object.assign({}, options);
        const message = opts.loading_message || opts.freeze_message || __('Chargement des données...');
        const userCallback = opts.callback;
        const userError = opts.error;
        const userAlways = opts.always;
        const silentError = Boolean(opts.silent_error);

        delete opts.loading_message;
        delete opts.silent_error;
        opts.freeze = false;

        show(message);

        opts.callback = function (response) {
            if (typeof userCallback === 'function') return userCallback(response);
        };
        opts.error = function (err) {
            if (!silentError) {
                if (window.Udshed && Udshed.Messages && Udshed.Messages.error) {
                    Udshed.Messages.error(err, __('Erreur lors du chargement'));
                } else {
                    frappe.show_alert({ message: __('Erreur lors du chargement des données.'), indicator: 'red' });
                }
            }
            if (typeof userError === 'function') return userError(err);
        };
        opts.always = function () {
            hide();
            if (typeof userAlways === 'function') return userAlways();
        };

        return frappe.call(opts);
    }

    return { show, hide, call };
})();

$(document).on('app_ready', function() {
    frappe.router.on('change', () => {
        const route = frappe.get_route();
        const [doctype, name] = route;

        if (doctype === 'app' && name === 'inscription___reinscription') {
            frappe.set_route('app', 'rapport-general');
            return;
        }

        if (doctype === 'workspace-sidebar' && name === 'inscription___reinscription') {
            frappe.set_route('app', 'rapport-general');
            return;
        }

        if (route[1] === 'planning-academique' && frappe.desk.sidebar) {
            frappe.desk.sidebar.set_item_active("Planning Academique");
        }
    });
});