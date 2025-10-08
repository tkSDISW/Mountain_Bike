# se_agent/tools/export_capella_yaml.py
from se_agent.tools.tool_patterns import  TransformTool

class ExportCapellaYAMLTool(TransformTool):
    """
    Transform: Generate YAML from a Capella model selection and store it as an artifact.

    Preferred inputs:
      • selection_alias   : alias of a 'capella_selection' artifact (list of {uuid, name, ...})
      • model_path_alias  : alias of artifact with content=str (.aird path), e.g., "Bike_Path"
      • resources_alias   : alias of artifact with content=dict (capellambse resources), e.g., "Bike_Resources"

    Alternatives (if no selection_alias):
      • uuids             : list[str] of UUIDs to export
      • uuid              : single UUID string

    Optional:
      • alias             : alias to assign to the created YAML artifact (e.g., "MB_yaml")

    Behavior:
      1) Builds a capellambse.MelodyModel from provided aliases.
      2) Uses capella_tools.capellambse_yaml_manager.CapellaYAMLHandler:
           - generate_yaml(model.by_uuid(uuid)) for each object
           - generate_yaml_referenced_objects()
           - write_output_file()
           - get_yaml_content()
      3) Creates artifact type 'yaml_content' with full YAML string and metadata.
      4) Returns a concise UI summary via metadata['ui_summary'] for the chat.
    """

    name = "export_capella_yaml"
    description = (
        "Generate YAML for a set of Capella objects and persist it as an artifact. "
        "Preferred inputs: selection_alias (capella_selection), model_path_alias (e.g., 'Bike_Path'), "
        "resources_alias (e.g., 'Bike_Resources'). Alternatively provide uuids=[...] or uuid='...'. "
    )
    artifact_type = "yaml_content"

    # minimal alias lookup consistent with your registry (scan package)
    def _pkg_name(self, artifacts, package_name):
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_alias(self, artifacts, pkg_name, alias):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg or not hasattr(pkg, "artifacts"):
                return None
            arts = list(pkg.artifacts.values())
            matches = [a for a in arts if getattr(a, "alias", None) == alias]
            if not matches:
                return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def transform(self, input_data, artifacts, package_name=None):
        # ---- Parse selection
        selection_alias = input_data.get("selection_alias")
        uuids = input_data.get("uuids")
        single_uuid = input_data.get("uuid")

        targets = []
        pkg_name = self._pkg_name(artifacts, package_name)

        if selection_alias and artifacts:
            sel_art = self._get_by_alias(artifacts, pkg_name, selection_alias)
            if not sel_art or not isinstance(sel_art.content, list):
                raise ValueError(f"Selection alias '{selection_alias}' not found or content is not a list.")
            for it in sel_art.content:
                if isinstance(it, dict) and it.get("uuid"):
                    targets.append({"uuid": str(it["uuid"]), "name": it.get("name", "")})
        elif isinstance(uuids, list) and uuids:
            targets = [{"uuid": str(u), "name": ""} for u in uuids]
        elif isinstance(single_uuid, str) and single_uuid:
            targets = [{"uuid": single_uuid, "name": ""}]
        else:
            raise ValueError("Provide selection_alias, uuids (list), or uuid (string).")

        # ---- Resolve model path / resources via aliases
        model_path_alias = input_data.get("model_path_alias")
        resources_alias  = input_data.get("resources_alias")
        if not (model_path_alias and resources_alias):
            raise ValueError("Provide model_path_alias and resources_alias.")

        art_path = self._get_by_alias(artifacts, pkg_name, model_path_alias) if artifacts else None
        art_res  = self._get_by_alias(artifacts, pkg_name, resources_alias) if artifacts else None
        if not art_path or not isinstance(art_path.content, str):
            raise ValueError(f"Artifact '{model_path_alias}' not found or content is not a string path.")
        if not art_res or not isinstance(art_res.content, dict):
            raise ValueError(f"Artifact '{resources_alias}' not found or content is not a dict.")

        path_to_model = art_path.content
        resources     = art_res.content


        # ---- Imports
        try:
            import capellambse
        except Exception as e:
            raise RuntimeError(f"Missing capellambse: {e}")

        try:
            from capella_tools import capellambse_yaml_manager
        except Exception as e:
            raise RuntimeError(f"Missing capella_tools.capellambse_yaml_manager: {e}")

        # ---- Build model
        try:
            model = capellambse.MelodyModel(path_to_model, resources=resources)
        except Exception as e:
            raise RuntimeError(f"Failed to construct MelodyModel: {e}")

        # ---- Generate YAML
        try:
            yaml_handler = capellambse_yaml_manager.CapellaYAMLHandler()
            # main objects
            for t in targets:
                uuid = t["uuid"]
                obj = model.by_uuid(uuid)
                yaml_handler.generate_yaml(obj)
            # referenced objects
            yaml_handler.generate_yaml_referenced_objects()
            # write to disk (as per your workflow)
            yaml_handler.write_output_file()
            # collect string content
            yaml_content = yaml_handler.get_yaml_content()
        except Exception as e:
            raise RuntimeError(f"YAML generation error: {e}")

        # ---- Metadata + concise UI summary
        names = [t.get("name") for t in targets if t.get("name")]
        if names:
            shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        else:
            # fall back to uuids if names missing
            uuids_shown = ", ".join([t["uuid"] for t in targets[:5]]) + ("…" if len(targets) > 5 else "")
            shown = uuids_shown or "(none)"
        
        count = len(targets)
        metadata = {
            # 👇 this line is what makes the assistant show a helpful, compact message
            "ui_summary": f"Generated YAML for {count} object(s): {shown}",
            "model_path": path_to_model,
            "selection_alias": selection_alias,
            "count": count,
            "source": "capellambse_yaml_manager",
        }
        
        # Optional: give the YAML artifact a default alias if none provided
        alias = input_data.get("alias")
        if not alias:
            base = (selection_alias or "capella").strip().replace(" ", "_")
            alias = f"{base}_yaml"
        metadata["alias"] = alias
        
        # The artifact content is the YAML string
        return yaml_content, metadata
