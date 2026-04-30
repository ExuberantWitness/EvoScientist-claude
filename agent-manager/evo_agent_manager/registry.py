"""RSPL — Resource Substrate Protocol Layer (minimal, Autogenesis-aligned).

Each resource type (tool, prompt, memory, agent) gets a typed Registry
with version tracking. This is the foundation for future SEPL optimizers
to operate on versioned resources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceVersion:
    """A single version record for a registered resource."""

    version: str  # "1.0.0"
    status: str = "active"  # "active" | "deprecated" | "archived"
    created_at: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)


class ResourceRegistry:
    """Typed registry for evolvable resources.

    Each resource registered gets a version history. Future SEPL optimizers
    can operate on versioned resources: propose variants, assess, commit/rollback.
    """

    def __init__(self, resource_type: str):
        self.resource_type = resource_type
        self._resources: dict[str, Any] = {}
        self._versions: dict[str, list[ResourceVersion]] = {}

    def register(
        self,
        name: str,
        instance: Any,
        version: str = "1.0.0",
        description: str = "",
        **metadata,
    ) -> None:
        """Register a resource with version tracking.

        If the resource already exists, adds a new version record.
        """
        self._resources[name] = instance
        if name not in self._versions:
            self._versions[name] = []
        # Mark previous active version as deprecated
        for v in self._versions[name]:
            if v.status == "active":
                v.status = "deprecated"
        from datetime import datetime, timezone

        self._versions[name].append(
            ResourceVersion(
                version=version,
                status="active",
                created_at=datetime.now(timezone.utc).isoformat(),
                description=description,
                metadata=metadata,
            )
        )

    def get(self, name: str, version: str | None = None) -> Any | None:
        """Get resource by name. If version is None, returns current active."""
        return self._resources.get(name)

    def get_version_history(self, name: str) -> list[ResourceVersion]:
        """Get full version history for a registered resource."""
        return list(self._versions.get(name, []))

    def get_current_version(self, name: str) -> str | None:
        """Get the currently active version string for a resource."""
        versions = self._versions.get(name, [])
        for v in reversed(versions):
            if v.status == "active":
                return v.version
        return None

    def list_resources(self) -> list[str]:
        """List all registered resource names."""
        return list(self._resources.keys())

    def deprecate(self, name: str) -> bool:
        """Mark the active version of a resource as deprecated."""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.status == "active":
                v.status = "deprecated"
                return True
        return False

    def archive(self, name: str) -> bool:
        """Archive all versions of a resource."""
        if name not in self._resources:
            return False
        for v in self._versions.get(name, []):
            v.status = "archived"
        del self._resources[name]
        return True


# Global registries — one per resource type
prompt_registry = ResourceRegistry("prompt")
tool_registry = ResourceRegistry("tool")
memory_registry = ResourceRegistry("memory")
agent_registry = ResourceRegistry("agent")
environment_registry = ResourceRegistry("environment")
