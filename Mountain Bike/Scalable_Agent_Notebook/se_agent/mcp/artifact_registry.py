# se_agent/mcp/artifact_registry.py

import json
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

class Artifact:
    """A lightweight container for model or file content."""

    def __init__(self, type_: str, content: Any, metadata: Optional[Dict] = None):
        self.id = str(uuid.uuid4())
        self.type = type_
        self.content = content
        self.metadata = metadata or {}


    
    @property
    def name(self) -> Optional[str]:
        return self.metadata.get("name")
        
    @name.setter
    def name(self, value):
        if value is None:
            self.metadata.pop("name", None)
        else:
            self.metadata["name"] = str(value)   
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: Dict) -> "Artifact":
        return Artifact(
            type_=data["type"],
            content=data["content"],
            metadata=data.get("metadata", {}),
        )


class ArtifactPackage:
    """A named collection of artifacts and optional pipelines."""

    def __init__(self, name: str):
        self.name = name
        self.artifacts: Dict[str, Artifact] = {}
        self.pipelines: List[Dict] = []  # Each pipeline = list of steps




    
    def add_artifact(self, artifact: "Artifact") -> "Artifact":
        self.artifacts[artifact.id] = artifact
    
        # Attach a short, human-friendly announcement to the artifact itself
        if artifact.name:
            artifact._announce = (
                f"✅ Artifact created: name='{artifact.name}' "
                f"id='{artifact.id[:8]}' "
                f"type='{artifact.type}' in package '{self.name}'"
            )
        else:
            artifact._announce = (
                f"✅ Artifact created: id='{artifact.id[:8]}' "
                f"type='{artifact.type}' in package '{self.name}'"
            )
    
        # Store timestamp
        artifact._created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    
        print(artifact._announce)
        return artifact

    def add_pipeline(self, pipeline: List[Dict]):
        self.pipelines.append(pipeline)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "artifacts": [a.to_dict() for a in self.artifacts.values()],
            "pipelines": self.pipelines,
        }

    @staticmethod
    def from_dict(data: Dict) -> "ArtifactPackage":
        pkg = ArtifactPackage(data["name"])
        for art in data.get("artifacts", []):
            pkg.add_artifact(Artifact.from_dict(art))
        for pl in data.get("pipelines", []):
            pkg.add_pipeline(pl)
        return pkg

    def get_by_id(self, artifact_id: str):
        """Return an artifact by its unique id, or None if not found."""
        return self.artifacts.get(artifact_id)

    def get_by_name(self, name: str):
        """Return the most recent artifact with the given name, or None."""
        matches = [a for a in self.artifacts.values() if a.name == name]
        return matches[-1] if matches else None

    def list_artifacts(self, type_filter: str = None):
        """Return a list of artifacts, optionally filtered by type."""
        if type_filter:
            return [a for a in self.artifacts.values() if a.type == type_filter]
        return list(self.artifacts.values())



class ArtifactRegistry:
    """Registry to manage packages and active context."""

    def __init__(self):
        self.packages: Dict[str, ArtifactPackage] = {}
        self.active_package: Optional[str] = None

    # --- Package lifecycle ---
    def create_package(self, name: str) -> ArtifactPackage:
        pkg = ArtifactPackage(name)
        self.packages[name] = pkg
        return pkg

    def use_package(self, name: str):
        if name not in self.packages:
            raise ValueError(f"Package '{name}' does not exist.")
        self.active_package = name

    def get_active_package(self) -> Optional[ArtifactPackage]:
        if not self.active_package:
            return None
        return self.packages[self.active_package]

    # --- Artifact management ---
    def add_artifact(self, package_name: str, type_: str, content: Any, metadata: Optional[Dict] = None) -> Artifact:
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")
        artifact = Artifact(type_, content, metadata)
        self.packages[package_name].add_artifact(artifact)
        return artifact

    # --- Pipeline management ---
    def add_pipeline(self, package_name: str, pipeline: List[Dict]):
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")
        self.packages[package_name].add_pipeline(pipeline)

    # --- Import / Export ---
    def export_package(self, package_name: str, out_path: Path):
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")

        pkg = self.packages[package_name]
        data = pkg.to_dict()

        out_path = Path(out_path)
        if out_path.suffix != ".zip":
            out_path = out_path.with_suffix(".zip")

        with zipfile.ZipFile(out_path, "w") as zf:
            zf.writestr(f"{package_name}.json", json.dumps(data, indent=2))

    def import_package(self, zip_path: Path) -> ArtifactPackage:
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Expect JSON inside
            names = [n for n in zf.namelist() if n.endswith(".json")]
            if not names:
                raise ValueError("No JSON file found in package ZIP.")

            data = json.loads(zf.read(names[0]).decode("utf-8"))
            pkg = ArtifactPackage.from_dict(data)
            self.packages[pkg.name] = pkg
            return pkg

    def get_package(self, name: str):
        """Return ArtifactPackage by name or None."""
        return self.packages.get(name)

    def list_artifacts(self, package_name: str, type_filter: str = None):
        pkg = self.get_package(package_name)
        if not pkg:
            return []
        # compact surface for LLM/UX
        out = []
        for a in pkg.artifacts.values():
            if type_filter and getattr(a, "type", None) != type_filter:
                continue
            out.append({
                "id": getattr(a, "id", None),
                "type": getattr(a, "type", None),
                "name": a.name,
                "created_at": getattr(a, "_created_at", None),
                "metadata": getattr(a, "metadata", None),
            })
        # newest first if timestamp exists
        out.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
        return out

    # ---------- NEW / UPDATED LOOKUP API (backward compatible) ----------

    def get_artifact(self, package_name: str, artifact_id: Optional[str] = None, **kwargs):
        """
        Backward-compatible getter:
          - Old style: get_artifact(package_name, artifact_id)
          - New style: get_artifact(package_name, name='foo')
          - New style: get_artifact(package_name, type_='bar', latest=True)

        Returns a single Artifact or None.
        """
        pkg = self.get_package(package_name)
        if not pkg:
            return None

        # Old behavior: by id
        if artifact_id:
            return pkg.get_by_id(artifact_id)

        # New behavior: by name
        name = kwargs.get("name")
        if name:
            return pkg.get_by_name(name)

        # New behavior: by type (latest by default)
        type_ = kwargs.get("type_")
        if type_:
            arts = pkg.list_artifacts(type_filter=type_)
            if not arts:
                return None
            # 'arts' here is a list[Artifact], not the dict we produce in list_artifacts()
            # If you kept list_artifacts returning dicts, switch to:
            # arts = [a for a in pkg.artifacts.values() if a.type == type_]
            arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == type_]
            if not arts:
                return None
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            latest = kwargs.get("latest", True)
            return arts[0] if latest else arts

        return None

    def get_artifact_by_name(self, package_name: str, name: str) -> Optional[Artifact]:
        """Explicit name helper (returns most-recent match)."""
        pkg = self.get_package(package_name)
        if not pkg:
            return None
        return pkg.get_by_name(name)

    def get_latest_by_type(self, package_name: str, type_: str) -> Optional[Artifact]:
        """Explicit helper to fetch the latest artifact of a given type."""
        pkg = self.get_package(package_name)
        if not pkg:
            return None
        arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == type_]
        if not arts:
            return None
        arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
        return arts[0]    

    def name_artifact(self, package_name: str, artifact_type: str, name: str) -> Optional[Artifact]:
        """Assign an name to the most recent artifact of a given type in a package."""
        pkg = self.get_package(package_name)
        if not pkg:
            raise ValueError(f"Package '{package_name}' not found.")
    
        # filter artifacts by type
        arts = [a for a in pkg.artifacts.values() if a.type == artifact_type]
        if not arts:
            return None
    
        # pick latest
        arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
        target = arts[0]
        target.metadata["name"] = name
        target._announce = (
            f"✅ name '{name}' assigned to artifact id='{target.id[:8]}' "
            f"type='{target.type}' in package '{pkg.name}'"
        )
        print(target._announce)
        return target