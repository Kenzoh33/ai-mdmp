from types import SimpleNamespace
from unittest.mock import MagicMock

from kubernetes.client.exceptions import ApiException
from mdmp_deployer.k8s import KubernetesClient
from mdmp_deployer.manifests import build_deployment, build_service


def make_client() -> KubernetesClient:
    """KubernetesClient with mocked APIs; __init__ is skipped so no kubeconfig is loaded."""
    kube = KubernetesClient.__new__(KubernetesClient)
    kube.namespace = "mdmp-models"
    kube.apps, kube.core, kube.networking = MagicMock(), MagicMock(), MagicMock()
    return kube


def deployment_body() -> dict:
    return build_deployment("sentiment", "v1", "stable", 2, "img:v1", {}, "mdmp-models")


def test_apply_creates_new_objects() -> None:
    kube = make_client()
    kube.apply(deployment_body())
    kube.apps.create_namespaced_deployment.assert_called_once()
    kube.apps.replace_namespaced_deployment.assert_not_called()


def test_existing_deployment_is_replaced_not_patched() -> None:
    # A strategic merge patch would keep env vars from the old version.
    kube = make_client()
    kube.apps.create_namespaced_deployment.side_effect = ApiException(status=409)

    kube.apply(deployment_body())

    kube.apps.replace_namespaced_deployment.assert_called_once()
    kube.apps.patch_namespaced_deployment.assert_not_called()


def test_existing_service_is_patched() -> None:
    kube = make_client()
    kube.core.create_namespaced_service.side_effect = ApiException(status=409)

    kube.apply(build_service("sentiment", "stable", "mdmp-models"))

    kube.core.patch_namespaced_service.assert_called_once()


def test_delete_ignores_missing_objects() -> None:
    kube = make_client()
    kube.networking.delete_namespaced_ingress.side_effect = ApiException(status=404)
    kube.delete("Ingress", "sentiment-canary")


def test_deployment_ready_needs_all_replicas_updated_and_available() -> None:
    kube = make_client()

    def status(updated: int, available: int) -> SimpleNamespace:
        return SimpleNamespace(
            spec=SimpleNamespace(replicas=2),
            metadata=SimpleNamespace(generation=3),
            status=SimpleNamespace(
                observed_generation=3,
                updated_replicas=updated,
                available_replicas=available,
                replicas=2,
            ),
        )

    kube.apps.read_namespaced_deployment_status.return_value = status(1, 2)
    assert kube.deployment_ready("sentiment-stable") is False
    kube.apps.read_namespaced_deployment_status.return_value = status(2, 2)
    assert kube.deployment_ready("sentiment-stable") is True
