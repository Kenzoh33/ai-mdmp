// Mock Data based on team contracts
const mockDeployments = [
    { id: "dep_01", model: "sentiment", version: "v1", track: "stable", traffic: 100, replicas: 3, status: "promoted" },
    { id: "dep_02", model: "sentiment", version: "v2", track: "canary", traffic: 0, replicas: 0, status: "rolled_back" }
];

$(document).ready(function() {
    console.log("AI-MDMP Dashboard initialized.");
    loadDeployments();

    // AI Insights Button Click Handler
    $('#btn-suggest-plan').click(function() {
        $('#insights-container').html('<span class="spinner-border spinner-border-sm"></span> Analyzing risk levels...');
        setTimeout(() => {
            $('#insights-container').html('<strong>Recommendation:</strong> Proceed with 10% canary. Risk level is LOW based on historical model stability.');
        }, 1500);
    });
});

function loadDeployments() {
    let html = '<ul class="list-group">';
    mockDeployments.forEach(dep => {
        let badgeClass = dep.status === 'promoted' ? 'bg-success' : (dep.status === 'rolled_back' ? 'bg-danger' : 'bg-warning');
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
