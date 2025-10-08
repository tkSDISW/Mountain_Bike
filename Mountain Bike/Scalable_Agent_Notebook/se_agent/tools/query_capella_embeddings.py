# se_agent/tools/query_capella_embeddings.py
from se_agent.tools.tool_patterns import  TransformTool



class QueryCapellaEmbeddingsTool(TransformTool):
    """
    Transform: query Capella embeddings and materialize the selection as an artifact.

    Required query params:
      - query (or 'search'): string, e.g. "[ocb] Mountain Bike"
      - top_n: positive int

    Preferred inputs via saved artifacts:
      - model_path_alias: alias of an artifact with content=str (.aird path)
      - resources_alias : alias of an artifact with content=dict (capellambse resources)

    Direct inputs fallback (only if aliases not provided):
      - path_to_model: str (.aird path)
      - resources: dict (capellambse resources)
      - embedding_file: str (default "embeddings.json")

    Result:
      - Creates artifact type 'capella_selection' with content = list[dict] for each selected object:
          {"uuid": "...", "name": "...", "type": "...", "id": "...", "attrs": {...}}
      - Returns a short UI message summarizing found names.
    """

    name = "query_capella_embeddings"
    description = (
        "Query Capella embeddings to return top object UUIDs. "
        "Prefer using saved artifacts: model_path_alias (type=capella_model_path) and "
        "resources_alias (type=capella_resources). Required inputs: query (string), "
        "top_n (int). If aliases are not given, you may pass path_to_model ('.aird' path) "
        "and resources (dict). The tool reconstructs a MelodyModel and calls the "
        "EmbeddingManager to select the top-N matches. Ouput includes create of artifact. "
    )
    artifact_type = "capella_selection"  # downstream tools (context diagrams, yaml) can target this

    # --- simple helpers consistent with your current registry (no alias API) ---
    def _pkg_name(self, artifacts, package_name):
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_alias(self, artifacts, pkg_name, alias):
        """Scan package for artifact whose .alias matches."""
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
        # 1) Parse inputs
        query = (input_data.get("query") or input_data.get("search") or "").strip()
        if not query:
            raise ValueError("Missing required 'query' (or 'search').")

        try:
            top_n = int(input_data.get("top_n", 1))
            if top_n <= 0:
                raise ValueError
        except Exception:
            raise ValueError("'top_n' must be a positive integer.")

        embedding_file = input_data.get("embedding_file", "embeddings.json")
        pkg_name = self._pkg_name(artifacts, package_name)

        # 2) Resolve path/resources (prefer aliases)
        model_path_alias = input_data.get("model_path_alias")
        resources_alias  = input_data.get("resources_alias")
        path_to_model    = input_data.get("path_to_model")
        resources        = input_data.get("resources")

        # If the planner provided alias strings in the direct-input keys, resolve them.
        if isinstance(path_to_model, str) and not os.path.exists(path_to_model):
            art_path = self._get_by_alias(artifacts, pkg_name, path_to_model)
            if art_path and isinstance(art_path.content, str):
                path_to_model = art_path.content
        
        if isinstance(resources, str):
            art_res = self._get_by_alias(artifacts, pkg_name, resources)
            if art_res and isinstance(art_res.content, dict):
                resources = art_res.content

        
        if artifacts and (model_path_alias or resources_alias):
            if model_path_alias and not path_to_model:
                art_path = self._get_by_alias(artifacts, pkg_name, model_path_alias)
                if not art_path or not isinstance(art_path.content, str):
                    raise ValueError(
                        f"Artifact '{model_path_alias}' not found or content is not a string path."
                    )
                path_to_model = art_path.content

            if resources_alias and resources is None:
                art_res = self._get_by_alias(artifacts, pkg_name, resources_alias)
                if not art_res or not isinstance(art_res.content, dict):
                    raise ValueError(
                        f"Artifact '{resources_alias}' not found or content is not a dict."
                    )
                resources = art_res.content

        # Minimal guidance if still missing
        if not path_to_model or resources is None:
            raise ValueError(
                "Provide model_path_alias & resources_alias (preferred) "
                "or path_to_model & resources."
            )

        # 3) Build dependencies
        try:
            import capellambse
        except Exception as e:
            raise RuntimeError(f"Missing capellambse: {e}")

        try:
            from capella_tools import capella_embeddings_manager
        except Exception as e:
            raise RuntimeError(f"Missing capella_tools.capella_embeddings_manager: {e}")

        # 4) Build model
        try:
            model_obj = capellambse.MelodyModel(path_to_model, resources=resources)
        except Exception as e:
            raise RuntimeError(f"Failed to construct MelodyModel: {e}")

        # 5) Run embeddings & query
        try:
            mgr = capella_embeddings_manager.EmbeddingManager()
            mgr.set_files(path_to_model or "", embedding_file)
            mgr.create_model_embeddings(model_obj)
            selected = mgr.query_and_select_top_objects(query, top_n=top_n) or []
        except Exception as e:
            raise RuntimeError(f"Capella embeddings error: {e}")

        # 6) Normalize selected objects → serializable records
        records = []
        names   = []

        def _safe(obj, attr, default=None):
            try:
                return getattr(obj, attr, default)
            except Exception:
                return default

        for obj in selected:
            rec = {}
            if hasattr(obj, "uuid") or hasattr(obj, "id"):
                rec["uuid"] = str(_safe(obj, "uuid") or _safe(obj, "id") or "")
            elif isinstance(obj, dict):
                rec["uuid"] = str(obj.get("uuid") or obj.get("id") or "")
            else:
                # fallback to string repr
                rec["uuid"] = str(obj)

            # name
            if hasattr(obj, "name"):
                rec["name"] = str(_safe(obj, "name") or "")
            elif isinstance(obj, dict) and "name" in obj:
                rec["name"] = str(obj["name"])
            else:
                rec["name"] = ""

            # type/class
            rec["type"] = type(obj).__name__

            # optional id
            rec["id"] = str(_safe(obj, "id") or "") if hasattr(obj, "id") else (
                str(obj.get("id")) if isinstance(obj, dict) and "id" in obj else ""
            )

            # capture a few safe attrs if present
            attrs = {}
            for k in ("category", "kind", "state"):
                if hasattr(obj, k):
                    attrs[k] = _safe(obj, k)
                elif isinstance(obj, dict) and k in obj:
                    attrs[k] = obj[k]
            if attrs:
                rec["attrs"] = attrs

            records.append(rec)
            if rec.get("name"):
                names.append(rec["name"])

        # 7) Metadata for downstream tools
        metadata = {
            "query": query,
            "top_n": top_n,
            "model_path": path_to_model,
            "count": len(records),
            "source": "capella_embeddings",
        }

        # ✅ Return content + metadata; TransformTool.run() will add the artifact
        #     and return a standard message + artifact_message.
        # Keep the UI concise: include a short names summary in 'message'
        summary_names = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        if not summary_names:
            summary_names = "(no names)"

        # By returning (content, metadata) here, your TransformTool base will:
        #   - artifacts.add_artifact(package_name, type_=artifact_type, content=records, metadata=metadata)
        #   - return {"message": ..., "artifact_message": ..., ...}
        # We pass the short message via metadata, and the base class can ignore or we can return as-is;
        # since your TransformTool.run returns a generic message, we just return the content + metadata.
        # The agent will still show artifact_message and you’ll see the summary in artifact metadata.

        # Optionally embed a friendly message in metadata for your UI
        metadata["ui_summary"] = f"Found {len(records)} matches: {summary_names}"

        return records, metadata



