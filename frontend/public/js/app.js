const mockDeployments = [
    { id: "dep_01", model: "sentiment", version: "v1", track: "stable", traffic: 100, replicas: 3, status: "promoted" }
];

$(document).ready(function() {
    loadDeployments();
    // Refresh so automatic rollbacks show up without reloading the page.
    setInterval(loadDeployments, 5000);
    listenForLiveUpdates();

    $('#btn-suggest-plan').click(function() {
        $('#insights-container').html('<span class="spinner-border spinner-border-sm"></span> Analyzing risk levels...');
        $.getJSON('/api/v1/feedback/risk', { model: 'sentiment', version: 'v2' })
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
        html += `<li class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <strong>${dep.model} (${dep.version})</strong> - ${dep.track}
                <br><small>Weight: ${traffic}% | Replicas: ${dep.replicas}${dep.reason ? ' | ' + dep.reason : ''}</small>
            </div>
            <span class="badge ${badgeClass} rounded-pill">${dep.status}</span>
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
