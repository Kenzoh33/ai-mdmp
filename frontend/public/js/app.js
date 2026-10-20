const mockDeployments = [
    { id: "dep_01", model: "sentiment", version: "v1", track: "stable", traffic: 100, replicas: 3, status: "promoted" }
];

$(document).ready(function() {
    loadDeployments();
    // Refresh so automatic rollbacks show up without reloading the page.
    setInterval(loadDeployments, 5000);
    listenForLiveUpdates();

    $('#deploy-form').submit(function(event) {
        event.preventDefault();
        const body = {
            model: 'sentiment',
            version: $('#deploy-version').val(),
            strategy: $('#deploy-strategy').val(),
        };
        if (body.strategy === 'canary') {
            body.initial_weight = Number($('#deploy-weight').val());
        }
        $('#btn-deploy').prop('disabled', true);
        postJSON('/api/v1/deployments', body, `Deploying ${body.version} (${body.strategy})`)
            .always(() => $('#btn-deploy').prop('disabled', false));
    });

    // Promote / Rollback buttons are rendered per canary, so bind them on the list.
    $('#deployments-list').on('click', '[data-action]', function() {
        const id = $(this).data('id');
        const action = $(this).data('action');
        const body = action === 'rollback' ? { reason: 'manual rollback from dashboard' } : {};
        postJSON(`/api/v1/deployments/${id}/${action}`, body, `${action} ${id}`);
    });

    $('#btn-suggest-plan').click(function() {
        $('#insights-container').html('<span class="spinner-border spinner-border-sm"></span> Analyzing risk levels...');
        $.getJSON('/api/v1/feedback/risk', { model: 'sentiment', version: $('#deploy-version').val() })
            .done(risk => {
                $('#insights-container').html(
                    `<strong>Risk level:</strong> ${risk.risk_level.toUpperCase()}<br>` +
                    `<strong>Recommended canary start:</strong> ${risk.recommended_initial_weight}%<br>` +
                    `<strong>Reasoning:</strong> ${risk.reasoning}`
                );
            })
            .fail(() => {
                $('#insights-container').html('Could not reach the deployer for a risk assessment.');
            });
    });
});

function notify(message, alertType) {
    $('#notification-area').prepend(`
        <div class="alert ${alertType} alert-dismissible fade show mt-2" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>`);
}

function postJSON(url, body, label) {
    return $.ajax({ url: url, method: 'POST', contentType: 'application/json', data: JSON.stringify(body) })
        .done(() => notify(`<strong>Done:</strong> ${label}`, 'alert-success'))
        .fail(xhr => {
            const error = xhr.responseJSON && xhr.responseJSON.error;
            notify(`<strong>Failed:</strong> ${label}: ${error ? error.message : xhr.statusText}`, 'alert-danger');
        })
        .always(loadDeployments);
}

function loadDeployments() {
    // Live data from the deployer (through the api service); mock data if it is not reachable.
    $.getJSON('/api/v1/deployments')
        .done(renderDeployments)
        .fail(() => renderDeployments(mockDeployments));
}

function renderDeployments(deployments) {
    let html = '<ul class="list-group">';
    deployments.forEach(dep => {
        let badgeClass = dep.status === 'promoted' ? 'bg-success'
            : ['rolled_back', 'failed'].includes(dep.status) ? 'bg-danger' : 'bg-warning';
        let traffic = dep.weight ?? dep.traffic;
        let actions = dep.status === 'canary' ? `
            <button class="btn btn-sm btn-outline-success me-1" data-action="promote" data-id="${dep.id}">Promote</button>
            <button class="btn btn-sm btn-outline-danger me-2" data-action="rollback" data-id="${dep.id}">Rollback</button>` : '';
        html += `<li class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <strong>${dep.model} (${dep.version})</strong> - ${dep.track}
                <br><small>Weight: ${traffic}% | Replicas: ${dep.replicas}${dep.reason ? ' | ' + dep.reason : ''}</small>
            </div>
            <div>${actions}<span class="badge ${badgeClass} rounded-pill">${dep.status}</span></div>
        </li>`;
    });
    html += '</ul>';
    $('#deployments-list').html(html);
}

function listenForLiveUpdates() {
    const evtSource = new EventSource("/api/v1/events");
    
    evtSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        const alertType = data.event === "anomaly" ? "alert-danger" : "alert-info";
        
        const alertHtml = `
            <div class="alert ${alertType} alert-dismissible fade show mt-2" role="alert">
                <strong>Live Update:</strong> ${data.message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>`;
            
        $('#notification-area').prepend(alertHtml);
    };
}
