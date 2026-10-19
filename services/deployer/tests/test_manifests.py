from mdmp_deployer.manifests import (
    build_canary_ingress,
    build_deployment,
    build_service,
    build_stable_ingress,
)


def test_deployment_selector_excludes_version() -> None:
    body = build_deployment(
        "sentiment", "v2", "canary", 1, "img:v2", {"ERROR_RATE": "0.2"}, "mdmp-models"
    )

    assert body["metadata"]["name"] == "sentiment-canary"
    assert body["spec"]["selector"]["matchLabels"] == {"app": "sentiment", "track": "canary"}
    template = body["spec"]["template"]
    assert template["metadata"]["labels"]["version"] == "v2"
    assert template["metadata"]["annotations"]["prometheus.io/scrape"] == "true"
    container = template["spec"]["containers"][0]
    assert container["image"] == "img:v2"
    assert container["env"] == [{"name": "ERROR_RATE", "value": "0.2"}]
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"


def test_service_targets_track() -> None:
    body = build_service("sentiment", "stable", "mdmp-models")
    assert body["spec"]["selector"] == {"app": "sentiment", "track": "stable"}


def test_ingresses_share_path_and_canary_has_weight() -> None:
    stable = build_stable_ingress("sentiment", "mdmp-models")
    canary = build_canary_ingress("sentiment", 20, "mdmp-models")

    stable_path = stable["spec"]["rules"][0]["http"]["paths"][0]
    canary_path = canary["spec"]["rules"][0]["http"]["paths"][0]
    assert stable_path["path"] == canary_path["path"] == "/models/sentiment(/|$)(.*)"
    assert stable["metadata"]["annotations"]["nginx.ingress.kubernetes.io/rewrite-target"] == "/$2"
    assert canary["metadata"]["annotations"] == {
        "nginx.ingress.kubernetes.io/canary": "true",
        "nginx.ingress.kubernetes.io/canary-weight": "20",
    }
    assert canary_path["backend"]["service"]["name"] == "sentiment-canary"
