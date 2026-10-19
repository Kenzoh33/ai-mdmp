"""Kubernetes object bodies for model serving. Same shape as k8s/models/*.yaml.

Plain dicts: the kubernetes client accepts them as request bodies, and tests can assert on them.
"""

from typing import Any

CONTAINER_PORT = 8080


def object_name(model: str, track: str) -> str:
    return f"{model}-{track}"


def canary_ingress_name(model: str) -> str:
    return f"{model}-canary"


def stable_ingress_name(model: str) -> str:
    return model


def _path(model: str) -> str:
    return f"/models/{model}(/|$)(.*)"


def build_deployment(
    model: str,
    version: str,
    track: str,
    replicas: int,
    image: str,
    env: dict[str, str],
    namespace: str,
) -> dict[str, Any]:
    # Selector is app + track only: selectors are immutable and a promote changes the version.
    selector = {"app": model, "track": track}
    labels = {**selector, "version": version}
    probe = {"httpGet": {"path": "/health", "port": "http"}}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": object_name(model, track), "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": {
                        "prometheus.io/scrape": "true",
                        "prometheus.io/port": str(CONTAINER_PORT),
                        "prometheus.io/path": "/metrics",
                    },
                },
                "spec": {
                    "containers": [
                        {
                            "name": model,
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "env": [{"name": k, "value": str(v)} for k, v in sorted(env.items())],
                            "ports": [{"name": "http", "containerPort": CONTAINER_PORT}],
                            "readinessProbe": {
                                **probe,
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            },
                            "livenessProbe": {
                                **probe,
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                            },
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "128Mi"},
                                "limits": {"memory": "256Mi"},
                            },
                        }
                    ]
                },
            },
        },
    }


def build_service(model: str, track: str, namespace: str) -> dict[str, Any]:
    selector = {"app": model, "track": track}
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": object_name(model, track), "namespace": namespace, "labels": selector},
        "spec": {
            "selector": selector,
            "ports": [{"name": "http", "port": 80, "targetPort": "http"}],
        },
    }


def _ingress(name: str, model: str, track: str, namespace: str, annotations: dict) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"app": model, "track": track},
            "annotations": annotations,
        },
        "spec": {
            "ingressClassName": "nginx",
            "rules": [
                {
                    "http": {
                        "paths": [
                            {
                                "path": _path(model),
                                "pathType": "ImplementationSpecific",
                                "backend": {
                                    "service": {
                                        "name": object_name(model, track),
                                        "port": {"name": "http"},
                                    }
                                },
                            }
                        ]
                    }
                }
            ],
        },
    }


def build_stable_ingress(model: str, namespace: str) -> dict[str, Any]:
    annotations = {
        "nginx.ingress.kubernetes.io/use-regex": "true",
        "nginx.ingress.kubernetes.io/rewrite-target": "/$2",
    }
    return _ingress(stable_ingress_name(model), model, "stable", namespace, annotations)


def canary_annotations(weight: int) -> dict[str, str]:
    return {
        "nginx.ingress.kubernetes.io/canary": "true",
        "nginx.ingress.kubernetes.io/canary-weight": str(weight),
    }


def build_canary_ingress(model: str, weight: int, namespace: str) -> dict[str, Any]:
    # ingress-nginx takes every non-canary annotation (like the rewrite) from the main Ingress.
    return _ingress(
        canary_ingress_name(model), model, "canary", namespace, canary_annotations(weight)
    )
