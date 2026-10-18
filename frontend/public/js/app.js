const mockDeployments = [
    { id: "dep_01", model: "sentiment", version: "v1", track: "stable", traffic: 100, replicas: 3, status: "promoted" }
];

$(document).ready(function() {
    loadDeployments();
    listenForLiveUpdates();

    $('#btn-suggest-plan').click(function() {
        $('#insights-container').html('<span class="spinner-border spinner-border-sm"></span> Analyzing risk levels...');
        setTimeout(() => {
            $('#insights-container').html('<strong>Recommendation:</strong> Proceed with 10% canary. Risk level is LOW.');
        }, 1500);
    });
});

function loadDeployments() {
    let html = '<ul class="list-group">';
    mockDeployments.forEach(dep => {
        let badgeClass = dep.status === 'promoted' ? 'bg-success' : 'bg-warning';
        html += `<li class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <strong>${dep.model} (${dep.version})</strong> - ${dep.track}
                <br><small>Traffic: ${dep.traffic}% | Replicas: ${dep.replicas}</small>
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
