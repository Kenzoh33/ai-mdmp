"""The only code that changes Kubernetes objects. Tests replace KubernetesClient with a fake."""

from typing import Any, Protocol

from mdmp_deployer.logs import logger
from mdmp_deployer.manifests import canary_annotations


class KubeClient(Protocol):
    def apply(self, body: dict[str, Any]) -> None: ...
    def delete(self, kind: str, name: str) -> None: ...
    def scale(self, name: str, replicas: int) -> None: ...
    def set_canary_weight(self, ingress_name: str, weight: int) -> None: ...
    def deployment_ready(self, name: str) -> bool: ...


class SimulatedKubeClient:
    """K8S_SIMULATE=true: logs each Kubernetes action instead of calling a cluster, and reports
    every Deployment as ready. The database, policy and history run as usual."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def _log(self, action: str) -> None:
        logger.info(f"[simulated k8s] {action} in {self.namespace}")

    def apply(self, body: dict[str, Any]) -> None:
        self._log(f"apply {body['kind']}/{body['metadata']['name']}")

    def delete(self, kind: str, name: str) -> None:
        self._log(f"delete {kind}/{name}")

    def scale(self, name: str, replicas: int) -> None:
        self._log(f"scale Deployment/{name} to {replicas}")

    def set_canary_weight(self, ingress_name: str, weight: int) -> None:
        self._log(f"set canary weight on Ingress/{ingress_name} to {weight}%")

    def deployment_ready(self, name: str) -> bool:
        return True


class KubernetesClient:
    """Wraps the official client. Uses kubeconfig locally and the ServiceAccount in the cluster."""

    def __init__(self, namespace: str, in_cluster: bool) -> None:
        from kubernetes import client, config

        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()
        self.namespace = namespace
        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()
        self.networking = client.NetworkingV1Api()

    def _api(self, kind: str) -> tuple[Any, str]:
        """(api object, method suffix) for a kind, e.g. create_namespaced_deployment."""
        return {
            "Deployment": (self.apps, "deployment"),
            "Service": (self.core, "service"),
            "Ingress": (self.networking, "ingress"),
        }[kind]

    def apply(self, body: dict[str, Any]) -> None:
        """Create the object, or update it if it already exists.

        Deployments are replaced: the client sends dict patches as strategic merge, which
        merges env by name and never drops a variable, so v2's ERROR_RATE would survive a
        rollback to v1. Services and Ingresses are patched: a replace would be rejected for
        a Service because the body has no clusterIP, and their shape never changes.
        """
        from kubernetes.client.exceptions import ApiException

        kind = body["kind"]
        api, suffix = self._api(kind)
        name = body["metadata"]["name"]
        try:
            getattr(api, f"create_namespaced_{suffix}")(self.namespace, body)
        except ApiException as exc:
            if exc.status != 409:
                raise
            verb = "replace" if kind == "Deployment" else "patch"
            getattr(api, f"{verb}_namespaced_{suffix}")(name, self.namespace, body)

    def delete(self, kind: str, name: str) -> None:
        from kubernetes.client.exceptions import ApiException

        api, suffix = self._api(kind)
        try:
            getattr(api, f"delete_namespaced_{suffix}")(name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    def scale(self, name: str, replicas: int) -> None:
        self.apps.patch_namespaced_deployment_scale(
            name, self.namespace, {"spec": {"replicas": replicas}}
        )

    def set_canary_weight(self, ingress_name: str, weight: int) -> None:
        patch = {"metadata": {"annotations": canary_annotations(weight)}}
        self.networking.patch_namespaced_ingress(ingress_name, self.namespace, patch)

    def deployment_ready(self, name: str) -> bool:
        """True once the newest ReplicaSet is fully rolled out and every replica is available."""
        dep = self.apps.read_namespaced_deployment_status(name, self.namespace)
        want = dep.spec.replicas or 0
        status = dep.status
        return (
            (status.observed_generation or 0) >= (dep.metadata.generation or 0)
            and (status.updated_replicas or 0) == want
            and (status.available_replicas or 0) == want
            and (status.replicas or 0) == want
        )
